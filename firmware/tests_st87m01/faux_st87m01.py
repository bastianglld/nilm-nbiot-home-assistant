"""Faux module ST87M01, pour tester `test_jour1.py` sans le kit.

Il répond aux commandes AT de la procédure du premier jour avec les formats du manuel
ST87MXX_UM_AT et des notes d'application (MQTT, TCP_UDP_IP). Les valeurs (réseau,
adresse IP, APN, signal) sont fictives. Il peut simuler des pannes : SIM absente,
enregistrement refusé, pas de couverture, module muet, broker injoignable.

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
                 rsrp=50, rsrq=20, broker_ok=True, muet=False, echo=False, veille=1,
                 plan="2101;R;000003;0002AAAAA005;22;22"):
        self.h = horloge or HorlogeSimulee()
        self.sim, self.refus, self.couverture = sim, refus, couverture
        self.attache_apres, self.rsrp, self.rsrq = attache_apres, rsrp, rsrq
        self.broker_ok, self.muet, self.echo, self.veille, self.plan = broker_ok, muet, echo, veille, plan
        self.debut_radio = self.h.maintenant()
        self.sortie = [] if muet else ["", "#SYSSTART"]
        self.recues = []  # commandes reçues, pour les tests
        self.connecte = False
        self.abonnements = []
        self.tampon = ""

    # -- interface transport
    def ecrire(self, texte):
        self.tampon += texte
        while "\r" in self.tampon:
            cmd, self.tampon = self.tampon.split("\r", 1)
            cmd = cmd.strip()
            if cmd:
                self.recues.append(cmd)
                if not self.muet:
                    if self.echo:
                        self.sortie.append(cmd)
                    self.sortie.extend(self._repondre(cmd))

    def lire_ligne(self, delai):
        if self.sortie:
            return self.sortie.pop(0)
        self.h.avancer(delai)  # rien à lire : le délai s'écoule
        return None

    def fermer(self):
        pass

    # -- état du réseau
    def _etat_reseau(self):
        if not self.sim:
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
            self.debut_radio = self.h.maintenant()
            return ok
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
            return ["#IPPING: 1,1,0,1518,1518,1518", "OK"] if self._attache() else ["+CME ERROR: 3"]
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
            if self._attache() and self.broker_ok:
                self.connecte = True
                return ok
            return ["+CME ERROR: 1100"]
        if c.startswith("AT#MQTTPUB="):
            return ok if self.connecte else erreur
        if c.startswith("AT#MQTTSUB="):
            if not self.connecte:
                return erreur
            topic = cmd.split("=", 1)[1].split(",")[0].strip('"')
            self.abonnements.append(topic)
            recu = topic[:-1] + "plan" if topic.endswith("/+") else topic  # le broker envoie le planning retenu
            return ok + [f"#MQTTRECV: {recu}, {self.plan}"]
        if c == "AT#MQTTDISC":
            self.connecte = False
            return ok
        if c.startswith("AT#SOCKETCLOSE="):
            return ok
        if c == "AT#PWROFF":
            return ok + ["#SHUTDOWN"]
        return erreur
