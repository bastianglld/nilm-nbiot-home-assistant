"""Test automatique du premier jour du kit EVKITST87M01-2 (partie B, module NB-IoT).

Déroule depuis le PC la procédure de `jour1_kit.md` : dialogue AT, SIM, attache au
réseau NB-IoT, qualité du signal, test IP (ping), puis, si un broker est donné, un
premier message MQTT. Chaque commande et chaque réponse sont écrites dans un journal
horodaté, et une ligne est ajoutée à la fiche de relevé (CSV).

Exemples :

    # sans le kit : avec le faux module, pour vérifier que le script tourne
    python test_jour1.py --simulateur

    # avec le kit branché en USB (Standard COM Port du CP2105)
    python test_jour1.py --port COM5 --lieu "tableau électrique"
    python test_jour1.py --port /dev/ttyUSB0 --broker 20.19.1.2 --utilisateur nilm_01

Le mot de passe MQTT n'est jamais passé en ligne de commande : il est lu dans la
variable d'environnement ST87M01_MQTT_MDP, ou demandé au clavier (--demander-mdp).
IMSI, ICCID et IMEI sont masqués dans le journal.

Références : manuel ST87MXX_UM_AT (rév. 0.3), notes ST87MXX_MQTT et ST87MXX_TCP_UDP_IP,
manuel de la carte EVKITST87M01-2.
"""

import argparse
import csv
import datetime as dt
import getpass
import ipaddress
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Contexte IP utilisé par défaut par le ST87M01 (note ST87MXX_TCP_UDP_IP).
CONTEXTE = 5
# Limites du module (manuel AT, chapitre MQTT).
LIMITE_TOPIC = 50
LIMITE_MESSAGE = 50
LIMITE_CLIENT = 25
LIMITE_UTILISATEUR = 25
LIMITE_MDP = 50

RE_ERREUR = re.compile(r"^(ERROR|\+CME ERROR:.*|\+CMS ERROR:.*)$")
RE_LONG_NOMBRE = re.compile(r"\d{14,20}")

DOSSIER = Path(__file__).resolve().parent
DOSSIER_JOURNAUX = DOSSIER / "journaux"


# ---------------------------------------------------------------- journal

def masquer(texte, secrets=()):
    """Masque les longs numéros (IMSI, ICCID, IMEI) et les secrets connus."""
    texte = RE_LONG_NOMBRE.sub(lambda m: m.group(0)[:4] + "*" * (len(m.group(0)) - 4), texte)
    for s in secrets:
        if s:
            texte = texte.replace(s, "***")
    return texte


class Journal:
    """Écrit chaque échange avec l'heure, dans un fichier et à l'écran."""

    def __init__(self, chemin=None, ecran=True):
        self.chemin = chemin
        self.ecran = ecran
        self.secrets = []
        self._f = open(chemin, "a", encoding="utf-8") if chemin else None

    def ecrire(self, sens, texte):
        ligne = f"{dt.datetime.now():%H:%M:%S.%f}"[:-3] + f" {sens} {masquer(texte, self.secrets)}"
        if self._f:
            self._f.write(ligne + "\n")
            self._f.flush()
        if self.ecran:
            print(ligne)

    def fermer(self):
        if self._f:
            self._f.close()


# ---------------------------------------------------------------- liaison série

class TransportSerie:
    """Port série réel (pyserial, chargé seulement ici)."""

    def __init__(self, port, debit=115200):
        import serial  # pip install pyserial

        # Manuel de la carte, § 8.2 : 115 200 bauds, 8 bits, sans parité, 1 bit de stop, sans contrôle de flux.
        self.serie = serial.Serial(port, debit, bytesize=8, parity="N", stopbits=1,
                                   rtscts=False, xonxoff=False, timeout=1)

    def ecrire(self, texte):
        self.serie.write(texte.encode("ascii", errors="replace"))

    def lire_ligne(self, delai):
        self.serie.timeout = max(delai, 0.05)
        brut = self.serie.readline()
        if not brut:
            return None
        return brut.decode("ascii", errors="replace").strip()

    def fermer(self):
        self.serie.close()


@dataclass
class Reponse:
    commande: str
    ok: bool
    lignes: list = field(default_factory=list)
    erreur: str = ""
    duree: float = 0.0

    def ligne(self, prefixe):
        """Première ligne de réponse qui commence par `prefixe` (par exemple '+CEREG:')."""
        for l in self.lignes:
            if l.startswith(prefixe):
                return l
        return None


class Modem:
    """Envoie une commande AT et attend OK ou une erreur."""

    def __init__(self, transport, journal, horloge=time.monotonic):
        self.t = transport
        self.j = journal
        self.horloge = horloge
        self.urc = []  # messages spontanés reçus pendant la séance

    def commande(self, cmd, delai=5.0):
        self.j.ecrire(">>", cmd)
        debut = self.horloge()
        self.t.ecrire(cmd + "\r")
        lignes = []
        while self.horloge() - debut < delai:
            l = self.t.lire_ligne(delai - (self.horloge() - debut))
            if l is None:
                break
            if not l or l == cmd:  # ligne vide ou écho de la commande
                continue
            self.j.ecrire("<<", l)
            if l == "OK":
                return Reponse(cmd, True, lignes, "", self.horloge() - debut)
            if RE_ERREUR.match(l):
                return Reponse(cmd, False, lignes, l, self.horloge() - debut)
            lignes.append(l)
            if l.startswith("#") or l.startswith("+CEREG") or l.startswith("+CGEV"):
                self.urc.append(l)
        self.j.ecrire("!!", f"pas de réponse finale après {delai:.0f} s")
        return Reponse(cmd, False, lignes, "délai dépassé", self.horloge() - debut)

    def attendre(self, motif, delai):
        """Attend un message spontané qui commence par `motif` (par exemple '#MQTTRECV:')."""
        for l in self.urc:
            if l.startswith(motif):
                self.urc.remove(l)
                return l
        debut = self.horloge()
        while self.horloge() - debut < delai:
            l = self.t.lire_ligne(delai - (self.horloge() - debut))
            if l is None:
                break
            if not l:
                continue
            self.j.ecrire("<<", l)
            if l.startswith(motif):
                return l
            self.urc.append(l)
        return None


# ---------------------------------------------------------------- lecture des réponses

def champs(ligne):
    """'+CESQ: 99,99,255,255,20,50' -> ['99', '99', '255', '255', '20', '50']"""
    if ligne is None or ":" not in ligne:
        return []
    return [c.strip().strip('"') for c in ligne.split(":", 1)[1].split(",")]


def ping_recus(ligne):
    """Nombre de réponses reçues dans « #IPPING: envoyés,reçus,perdus,min,max,moy »."""
    v = champs(ligne)
    try:
        return int(v[1])
    except (IndexError, TypeError, ValueError):
        return None


def etat_cereg(ligne):
    """État d'enregistrement : 2e champ en lecture (+CEREG: n,stat,…). None si illisible."""
    c = champs(ligne)
    if len(c) >= 2 and c[1].isdigit():
        return int(c[1])
    return None


def signal_cesq(ligne):
    """RSRP (dBm) et RSRQ (dB) d'après +CESQ (manuel AT § 7.5). None si inconnu (255)."""
    c = champs(ligne)
    if len(c) < 6:
        return None, None
    rsrq, rsrp = int(c[4]), int(c[5])
    rsrp_dbm = None if rsrp == 255 else rsrp - 141
    rsrq_db = None if rsrq == 255 else rsrq / 2 - 20
    return rsrp_dbm, rsrq_db


def operateur_cops(ligne):
    c = champs(ligne)
    return c[2] if len(c) >= 3 else ""


def apn_cgcontrdp(ligne):
    c = champs(ligne)
    return c[2] if len(c) >= 3 else ""


def adresse_cgpaddr(ligne):
    c = champs(ligne)
    return c[1] if len(c) >= 2 else ""


ETATS_CEREG = {0: "pas enregistré", 1: "enregistré (opérateur)", 2: "recherche en cours",
               3: "enregistrement refusé", 4: "inconnu", 5: "enregistré (itinérance)"}


def verifier_limites(client, utilisateur, mdp, topics, message):
    """Liste des dépassements des limites du module (vide si tout tient)."""
    pbs = []
    if len(client) > LIMITE_CLIENT:
        pbs.append(f"nom du client : {len(client)} caractères (> {LIMITE_CLIENT})")
    if utilisateur and len(utilisateur) > LIMITE_UTILISATEUR:
        pbs.append(f"utilisateur : {len(utilisateur)} caractères (> {LIMITE_UTILISATEUR})")
    if mdp and len(mdp) > LIMITE_MDP:
        pbs.append(f"mot de passe : {len(mdp)} caractères (> {LIMITE_MDP})")
    for t in topics:
        if len(t) > LIMITE_TOPIC:
            pbs.append(f"topic {t} : {len(t)} caractères (> {LIMITE_TOPIC})")
    if len(message) > LIMITE_MESSAGE:
        pbs.append(f"message : {len(message)} caractères (> {LIMITE_MESSAGE})")
    return pbs


# ---------------------------------------------------------------- séance de test

@dataclass
class Resultat:
    etapes: list = field(default_factory=list)  # (numéro, nom, ok, détail)
    firmware: str = ""
    cereg: object = None
    operateur: str = ""
    apn: str = ""
    adresse_ip: str = ""
    temps_attache: object = None
    rsrp: object = None
    rsrq: object = None
    ping: object = None
    mqtt_publie: object = None
    mqtt_recu: object = None

    def noter(self, num, nom, ok, detail=""):
        self.etapes.append((num, nom, ok, detail))
        return ok

    @property
    def reussi(self):
        return all(ok for _, _, ok, _ in self.etapes)


def seance(modem, opts, dormir=time.sleep, horloge=time.monotonic):
    """Déroule la procédure du premier jour. Renvoie un Resultat."""
    r = Resultat()
    c = modem.commande

    # 2. Dialogue
    # le module peut dormir (DRX, PSM) : la première commande ne fait souvent que le réveiller
    for essai in range(4):
        rep = c("AT", delai=3.0)
        if rep.ok:
            break
    if not r.noter("2.1", "AT -> OK", rep.ok, rep.erreur if essai == 0 else f"{rep.erreur} ({essai + 1} essais)"):
        return r
    c("AT+CMEE=2")
    c("ATI")
    rep = c("AT+CGMR")
    r.firmware = rep.lignes[0] if rep.lignes else ""
    rep = c("AT#SLEEPMODE?")
    l = rep.ligne("#SLEEPMODE:")
    veille = champs(l)[0] if l else "?"
    if veille == "1" and opts.sans_veille:
        rep = c("AT#SLEEPMODE=0")
        r.noter("2.5", "mise en veille", rep.ok, "désactivée pour la séance (AT#SLEEPMODE=0)" if rep.ok else rep.erreur)
    else:
        r.noter("2.5", "mise en veille", True, "active : penser à AT#SLEEPMODE=0 pour la séance" if veille == "1" else f"état {veille}")

    # 3. SIM
    rep = c("AT#SIMST?")
    sim_ok = rep.ok and (rep.ligne("#SIMST:") or "").endswith("1")
    if not r.noter("3.1", "SIM valide (#SIMST: 1)", sim_ok, rep.ligne("#SIMST:") or rep.erreur):
        return r
    rep = c("AT+CPIN?")
    if not r.noter("3.2", "SIM prête (+CPIN: READY)", "READY" in (rep.ligne("+CPIN:") or ""), rep.ligne("+CPIN:") or rep.erreur):
        return r

    # 4. Attache au réseau
    rep = c("AT#BANDSEL?")
    r.noter("4.0", "bandes actives", rep.ok, rep.ligne("#BANDSEL:") or rep.erreur)
    rep = c("AT+CFUN?")
    if "+CFUN: 1" not in (rep.ligne("+CFUN:") or ""):
        c("AT+CFUN=1", delai=15)
    c("AT+CEREG=2")
    debut = horloge()
    etat = None
    while True:
        rep = c("AT+CEREG?")
        etat = etat_cereg(rep.ligne("+CEREG:"))
        if etat in (1, 5, 3) or horloge() - debut >= opts.attente_attache:
            break
        dormir(opts.intervalle)
    r.cereg = etat
    if etat in (1, 5):
        r.temps_attache = round(horloge() - debut, 1)
    detail = f"{etat} : {ETATS_CEREG.get(etat, 'illisible')}"
    if r.temps_attache is not None:
        detail += f", en {r.temps_attache} s"
    if not r.noter("4.3", "attache au réseau (+CEREG 1 ou 5)", etat in (1, 5), detail):
        return r
    r.operateur = operateur_cops(c("AT+COPS?").ligne("+COPS:"))
    r.apn = apn_cgcontrdp(c(f"AT+CGCONTRDP={CONTEXTE}").ligne("+CGCONTRDP:"))
    r.adresse_ip = adresse_cgpaddr(c(f"AT+CGPADDR={CONTEXTE}").ligne("+CGPADDR:"))
    r.noter("4.6", "adresse IP", bool(r.adresse_ip), f"APN {r.apn or '?'}, réseau {r.operateur or '?'}")
    rep = c("AT#IPCFG?")
    r.noter("4.7", "pile IP active", rep.ok, rep.ligne("#IPCFG:") or rep.erreur)
    if opts.ping:
        # 3 pings, 30 s d'attente chacun : la première réponse peut être lente en NB-IoT
        rep = c(f"AT#IPPING={CONTEXTE},8.8.8.8,30,10,3", delai=120)
        bilan = rep.ligne("#IPPING:")
        recus = ping_recus(bilan)
        r.ping = rep.ok and recus is not None and recus > 0
        r.noter("4.8", "ping 8.8.8.8 (au moins une réponse)", r.ping, bilan or rep.erreur)

    # 5. Signal
    rep = c("AT+CESQ")
    r.rsrp, r.rsrq = signal_cesq(rep.ligne("+CESQ:"))
    r.noter("5.1", "qualité du signal", r.rsrp is not None, f"RSRP {r.rsrp} dBm, RSRQ {r.rsrq} dB")

    # 6. MQTT (seulement si un broker est donné)
    if opts.broker:
        mqtt(modem, opts, r)

    # 7. Arrêt
    if opts.eteindre:
        rep = c("AT#PWROFF", delai=10)
        r.noter("7", "arrêt propre", rep.ok, rep.erreur)
    return r


def mqtt(modem, opts, r):
    c = modem.commande
    pbs = verifier_limites(opts.client, opts.utilisateur, opts.mdp, [opts.topic, opts.topic_plan], opts.message)
    if not r.noter("6.0", "limites du module", not pbs, "; ".join(pbs)):
        return
    adresse = opts.broker
    try:
        ipaddress.ip_address(adresse)
    except ValueError:
        rep = c(f"AT#DNS={CONTEXTE},0,{opts.broker}", delai=15)
        adresse = champs(rep.ligne("#DNS:"))[0] if rep.ligne("#DNS:") else ""
        if not r.noter("6.1", f"DNS {opts.broker}", bool(adresse), adresse or rep.erreur):
            return
    c(f"AT#MQTTCFG={opts.client},20,20,10,{opts.keepalive}")
    rep = c(f"AT#SOCKETCREATE={CONTEXTE},0,TCP,,{opts.delai_socket},{opts.delai_socket}")
    socket = champs(rep.ligne("#SOCKETCREATE:"))
    if not r.noter("6.3", "socket TCP", rep.ok and bool(socket), rep.ligne("#SOCKETCREATE:") or rep.erreur):
        return
    sid = socket[0]
    cmd = f"AT#MQTTCONNECT={CONTEXTE},{sid},{adresse},{opts.port_mqtt}"
    if opts.utilisateur:
        cmd += f",{opts.utilisateur}" + (f",{opts.mdp}" if opts.mdp else "")
    rep = c(cmd, delai=25)
    if r.noter("6.4", "connexion au broker", rep.ok, rep.erreur):
        rep = c(f"AT#MQTTPUB={opts.topic},{opts.message},3,1,0", delai=25)
        r.mqtt_publie = r.noter("6.5", f"publication sur {opts.topic}", rep.ok, rep.erreur)
        if opts.attente_plan > 0:
            rep = c(f"AT#MQTTSUB={opts.topic_plan},1", delai=15)
            recu = modem.attendre("#MQTTRECV:", opts.attente_plan) if rep.ok else None
            r.mqtt_recu = recu is not None
            r.noter("6.7", f"réception sur {opts.topic_plan}", r.mqtt_recu, recu or "rien reçu")
        c("AT#MQTTDISC", delai=25)
    c(f"AT#SOCKETCLOSE={CONTEXTE},{sid}", delai=60)


# ---------------------------------------------------------------- fiche de relevé

COLONNES = ["date", "lieu", "firmware", "cereg", "reseau", "apn", "temps_attache_s",
            "rsrp_dbm", "rsrq_db", "ping", "mqtt_publie", "mqtt_recu", "remarques"]


def ligne_fiche(r, lieu, remarques=""):
    def oui_non(v):
        return "" if v is None else ("oui" if v else "non")
    return {"date": f"{dt.datetime.now():%Y-%m-%d %H:%M}", "lieu": lieu, "firmware": r.firmware,
            "cereg": "" if r.cereg is None else r.cereg, "reseau": r.operateur, "apn": r.apn,
            "temps_attache_s": "" if r.temps_attache is None else r.temps_attache,
            "rsrp_dbm": "" if r.rsrp is None else r.rsrp, "rsrq_db": "" if r.rsrq is None else r.rsrq,
            "ping": oui_non(r.ping), "mqtt_publie": oui_non(r.mqtt_publie), "mqtt_recu": oui_non(r.mqtt_recu),
            "remarques": remarques}


def ajouter_fiche(chemin, ligne):
    nouveau = not Path(chemin).exists()
    with open(chemin, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        if nouveau:
            w.writeheader()
        w.writerow(ligne)


# ---------------------------------------------------------------- programme

def options(argv=None):
    p = argparse.ArgumentParser(description="Procédure du premier jour du kit ST87M01, automatisée.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="port série du CP2105 (Standard COM Port), par exemple COM5 ou /dev/ttyUSB0")
    src.add_argument("--simulateur", action="store_true", help="utiliser le faux module (sans kit)")
    p.add_argument("--lieu", default="", help="endroit de la mesure, pour la fiche de relevé")
    p.add_argument("--remarques", default="")
    p.add_argument("--attente-attache", type=float, default=300, help="durée maximale d'attente de l'attache (s)")
    p.add_argument("--intervalle", type=float, default=10, help="intervalle entre deux AT+CEREG? (s)")
    p.add_argument("--sans-ping", dest="ping", action="store_false", help="ne pas faire AT#IPPING")
    p.add_argument("--garder-veille", dest="sans_veille", action="store_false",
                   help="ne pas désactiver la mise en veille du module (par défaut : AT#SLEEPMODE=0 pour la séance)")
    p.add_argument("--broker", help="adresse IP (ou nom) du broker MQTT ; sans broker, pas d'étape MQTT")
    p.add_argument("--port-mqtt", type=int, default=1883)
    p.add_argument("--client", default="nilm_01")
    p.add_argument("--utilisateur", default="")
    p.add_argument("--demander-mdp", action="store_true", help="demander le mot de passe MQTT au clavier")
    p.add_argument("--topic", default="nilm/maison/etat")
    p.add_argument("--message", default="1615;21;48;0;0;310")
    p.add_argument("--topic-plan", default="nilm/maison/cmd/+")
    p.add_argument("--attente-plan", type=float, default=60, help="attente du planning après abonnement (s), 0 pour ne pas s'abonner")
    p.add_argument("--keepalive", type=int, default=0, help="keep-alive MQTT (s), 0 = désactivé pour les tests")
    p.add_argument("--delai-socket", type=int, default=10, help="délais d'envoi et de réception de la socket (s)")
    p.add_argument("--eteindre", action="store_true", help="finir par AT#PWROFF")
    p.add_argument("--journaux", default=str(DOSSIER_JOURNAUX), help="dossier du journal et de la fiche de relevé")
    o = p.parse_args(argv)
    o.mdp = os.environ.get("ST87M01_MQTT_MDP", "")
    if o.demander_mdp:
        o.mdp = getpass.getpass("Mot de passe MQTT : ")
    return o


def main(argv=None):
    o = options(argv)
    Path(o.journaux).mkdir(parents=True, exist_ok=True)
    horodatage = f"{dt.datetime.now():%Y%m%d_%H%M%S}"
    journal = Journal(Path(o.journaux) / f"seance_{horodatage}.log")
    journal.secrets.append(o.mdp)
    dormir, horloge = time.sleep, time.monotonic
    if o.simulateur:
        from faux_st87m01 import FauxST87M01, HorlogeSimulee

        h = HorlogeSimulee()
        transport = FauxST87M01(horloge=h)
        dormir, horloge = h.avancer, h.maintenant
    else:
        transport = TransportSerie(o.port)
    journal.ecrire("--", f"séance {horodatage}, {'faux module' if o.simulateur else o.port}, lieu : {o.lieu or '-'}")
    try:
        r = seance(Modem(transport, journal, horloge), o, dormir, horloge)
    finally:
        transport.fermer()
    print("\nBilan")
    for num, nom, ok, detail in r.etapes:
        print(f"  {'OK ' if ok else 'ÉCHEC'} {num:4} {nom}" + (f" : {masquer(detail, [o.mdp])}" if detail else ""))
    fiche = Path(o.journaux) / "fiche_releve.csv"
    ajouter_fiche(fiche, ligne_fiche(r, o.lieu, o.remarques + (" (faux module)" if o.simulateur else "")))
    print(f"\nJournal : {journal.chemin}\nFiche de relevé : {fiche}")
    journal.fermer()
    return 0 if r.reussi else 1


if __name__ == "__main__":
    sys.exit(main())
