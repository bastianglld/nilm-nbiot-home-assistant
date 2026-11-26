"""Faux module ST87M01, pour tester `test_jour1.py` et `cycle_st87m01.py` sans le kit.

Il répond aux commandes AT de la procédure du premier jour avec les formats du manuel
ST87MXX_UM_AT et des notes d'application (MQTT, TCP_UDP_IP). Les valeurs (réseau,
adresse IP, APN, signal) sont fictives. Il peut simuler des pannes : SIM absente,
enregistrement refusé, pas de couverture, module muet, broker injoignable, ping sans réponse, APN effacé, pile MQTT bloquée.

Comportements reproduits d'après les essais sur le kit (journal des 20, 25 et 26 nov 2026) :
- `AT+CFUN=1` est suivi, une fois attaché, du message spontané `#IPCFG: 5,0,1` ;
- après `AT#MQTTSUB`, le broker livre les messages retenus (`#MQTTRECV: <topic>,<message>`),
  mais **seulement pour les abonnements exacts** : un message reçu par un joker (`+`) est
  acquitté sans être affiché ;
- une pile MQTT bloquée répond 2215 à la publication et 2220 à la connexion, jusqu'à `AT#RESET=1`.

Le temps est simulé : attendre l'attache au réseau ne prend pas de vraies secondes.
"""


class HorlogeSimulee:
    def __init__(self):
        self.t = 0.0

    def maintenant(self):
        return self.t

    def avancer(self, secondes):
        self.t += max(secondes, 0)


class FauxST87M01:
    """Même interface que TransportSerie : ecrire(texte), lire_ligne(delai), fermer()."""

    def __init__(self, horloge=None, sim=True, refus=False, couverture=True, attache_apres=40.0,
                 rsrp=50, rsrq=20, broker_ok=True, muet=False, echo=False, veille=1, ping_ok=True, endormi=0,
                 plan="2101;R;000003;0002AAAAA005;22;22", retenus=None, apn="eapn1.net",
                 bloque_apres=None):
        self.h = horloge or HorlogeSimulee()
        self.sim, self.refus, self.couverture = sim, refus, couverture
        self.attache_apres, self.rsrp, self.rsrq = attache_apres, rsrp, rsrq
        self.broker_ok, self.muet, self.echo, self.veille, self.plan = broker_ok, muet, echo, veille, plan
        self.ping_ok = ping_ok
        self.endormi = endormi  # nombre de commandes perdues au réveil (veille DRX ou PSM)
        self.debut_radio = self.h.maintenant()
        self.sortie = [] if muet else ["", "#SYSSTART"]
        self.recues = []  # commandes reçues, pour les tests
        self.connecte = False
        self.abonnements = []
        self.tampon = ""
        self.radio = True
        self.ipcfg_attendu = False
        self.apn = apn
        # messages gardés par le broker (retain), livrés à chaque abonnement exact
        self.retenus = dict(retenus) if retenus is not None else {
            "nilm/maison/cmd/plan": plan, "nilm/maison/cmd/chauffe_eau": "OFF"}
        self.publies = []  # (topic, message) acceptés
        self.bloque_apres = bloque_apres  # nombre de publications réussies avant blocage de la pile MQTT
        self.bloque = False

    # -- interface transport
    def ecrire(self, texte):
        self.tampon += texte
        while "\r" in self.tampon:
            cmd, self.tampon = self.tampon.split("\r", 1)
            cmd = cmd.strip()
            if cmd:
                self.recues.append(cmd)
                if self.endormi > 0 and not self.muet:
                    self.endormi -= 1
                    self.sortie.append("#WAKEUP DRX")  # la commande réveille le module mais se perd
                    continue
                if not self.muet:
                    if self.echo:
                        self.sortie.append(cmd)
                    self.sortie.extend(self._repondre(cmd))

    def lire_ligne(self, delai):
        if self.sortie:
            return self.sortie.pop(0)
        if self.ipcfg_attendu and self.couverture and self.sim and not self.refus:
            reste = self.attache_apres - (self.h.maintenant() - self.debut_radio)
            if reste <= delai:
                self.h.avancer(max(reste, 0))
                self.ipcfg_attendu = False
                return "#IPCFG: 5,0,1"
        self.h.avancer(delai)  # rien à lire : le délai s'écoule
        return None

    def fermer(self):
        pass

    # -- état du réseau
    def _etat_reseau(self):
        if not self.sim or not self.radio:
            return 0
        if self.refus:
            return 3
        if not self.couverture or self.h.maintenant() - self.debut_radio < self.attache_apres:
            return 2
        return 5  # itinérance, comme attendu avec une SIM Wireless Logic

    def _attache(self):
        return self._etat_reseau() in (1, 5)

    # -- réponses
    def _repondre(self, cmd):
        ok = ["OK"]
        erreur = ["ERROR"]
        c = cmd.upper()
        if c == "AT" or c.startswith("AT+CMEE=") or c == "AT+CEREG=2" or c.startswith("AT+CGEREP"):
            return ok
        if c == "ATI":
            return ["ST87M01 (faux module)", "OK"]
        if c == "AT+CGMR":
            return ["FAUX-1.0.0", "OK"]
        if c.startswith("AT#SLEEPMODE="):
            self.veille = int(c.split("=", 1)[1].split(",")[0])
            return ok
        if c == "AT#SLEEPMODE?":
            return [f"#SLEEPMODE: {self.veille},10,0", "OK"]
        if c == "AT#SIMST?":
            return [f"#SIMST: {1 if self.sim else 0}", "OK"]
        if c == "AT+CPIN?":
            return ["+CPIN: READY", "OK"] if self.sim else ["+CME ERROR: SIM not inserted"]
        if c == "AT#BANDSEL?":
            return ["#BANDSEL: 3,8,20", "OK"]
        if c == "AT+CFUN?":
            return ["+CFUN: 1", "OK"]
        if c == "AT+CFUN=1":
            self.radio = True
            self.debut_radio = self.h.maintenant()
            self.ipcfg_attendu = True
            return ok
        if c == "AT+CFUN=0":
            self.radio = False
            self.connecte = False
            return ["+CGEV: ME PDN DEACT 5", "OK"]
        if c == "AT+CGDCONT?":
            return [f'+CGDCONT: 5,"IP","{self.apn.upper()}","10.0.0.2"' if self.apn else '+CGDCONT: 5,"IPV4V6",""', "OK"]
        if c.startswith("AT+CGDCONT=5,"):
            self.apn = cmd.split(",")[2].strip('"')
            return ok
        if c.startswith("AT#RESET="):
            self.connecte = self.bloque = False
            self.radio = True
            self.debut_radio = self.h.maintenant()
            self.ipcfg_attendu = True
            return ok + ["", "#SYSSTART"]
        if c == "AT+CEREG?":
            e = self._etat_reseau()
            return [f'+CEREG: 2,{e}' + (',"1A2B","01A2B3C4",9' if e in (1, 5) else ""), "OK"]
        if c == "AT+COPS?":
            return ['+COPS: 0,2,"00101",9', "OK"] if self._attache() else ["+COPS: 0", "OK"]
        if c == "AT+CGCONTRDP=5":
            if not self._attache():
                return ok
            return ['+CGCONTRDP: 5,5,"apn.simule","10.0.0.2.255.255.255.0","","10.0.0.53","10.0.0.54"', "OK"]
        if c == "AT+CGPADDR=5":
            return ['+CGPADDR: 5,"10.0.0.2"', "OK"] if self._attache() else ["+CGPADDR: 5", "OK"]
        if c == "AT#IPCFG?":
            return [f"#IPCFG: 5,1,10.0.0.2" if self._attache() else "#IPCFG: 5,0,0.0.0.0", "OK"]
        if c.startswith("AT#IPPING="):
            if not self._attache():
                return ["+CME ERROR: 3"]
            # format du manuel AT : envoyés, reçus, perdus, min, max, moyenne (999999 = pas de réponse)
            return ["#IPPING: 3,3,0,1518,2210,1790", "OK"] if self.ping_ok else ["#IPPING: 3,0,3,999999,0,0", "OK"]
        if c == "AT+CESQ":
            if not self._attache():
                return ["+CESQ: 99,99,255,255,255,255", "OK"]
            return [f"+CESQ: 99,99,255,255,{self.rsrq},{self.rsrp}", "OK"]
        if c.startswith("AT#DNS="):
            return ["#DNS: 20.19.1.2,300", "OK"] if self._attache() else ["+CME ERROR: 3"]
        if c.startswith("AT#MQTTCFG="):
            return ok
        if c.startswith("AT#SOCKETCREATE="):
            return ["#SOCKETCREATE: 0", "OK"] if self._attache() else erreur
        if c.startswith("AT#MQTTCONNECT="):
            if self.bloque or self.connecte:
                return ["+CME ERROR: 2220"]
            if self._attache() and self.broker_ok:
                self.connecte = True
                return ok
            return ["+CME ERROR: 1100"]
        if c.startswith("AT#MQTTPUB="):
            if self.bloque:
                return ["+CME ERROR: 2215"]
            if not self.connecte:
                return ["+CME ERROR: 2218"]
            if self.bloque_apres is not None and len(self.publies) >= self.bloque_apres:
                self.bloque, self.bloque_apres = True, None
                return ["#TCPSENDFAIL: 5,0,204", "+CME ERROR: 2215"]
            # sans guillemets, le module coupe le message au premier « ; » (séparateur de commandes AT)
            corps = cmd.split("=", 1)[1]
            topic, reste = corps.split(",", 1)
            message = reste.split('"')[1] if reste.startswith('"') else reste.split(";")[0]
            self.publies.append((topic, message))
            return ok
        if c.startswith("AT#MQTTSUB="):
            if not self.connecte or self.bloque:
                return ["+CME ERROR: 2216"]
            v = cmd.split("=", 1)[1].split(",")
            topics = [t.strip('"') for t in v[0::2]]
            self.abonnements.extend(topics)
            # le firmware n'affiche que les messages des abonnements exacts (essais du 25 et du 26 nov)
            return ok + [f"#MQTTRECV: {t},{self.retenus[t]}" for t in topics if "+" not in t and t in self.retenus]
        if c == "AT#MQTTDISC":
            if not self.connecte:
                return ["+CME ERROR: 2218"]
            self.connecte = False
            return ok
        if c.startswith("AT#SOCKETCLOSE="):
            return ["+CME ERROR: 2104"] if not self.connecte else ok
        if c == "AT#PWROFF":
            return ok + ["#SHUTDOWN"]
        return erreur
