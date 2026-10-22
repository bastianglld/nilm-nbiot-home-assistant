#!/usr/bin/env python3
"""
Simulateur de la TIC (téléinformation client) du compteur Linky – projet M1 ESET NILM / NB-IoT.

Il joue le rôle du compteur pour tester le décodeur de la carte sans Linky ni interface optocoupleur :
le PC envoie des trames TIC sur un port série (adaptateur USB-série 3,3 V ou port série virtuel du ST-LINK).

Trois commandes :
    envoyer : fabrique et envoie des trames (mode standard ou historique), avec une puissance constante,
              aléatoire, ou rejouée depuis une journée UK-DALE ; erreurs volontaires possibles
    lire    : lit des trames (port série ou fichier), vérifie les sommes de contrôle et affiche les valeurs ;
              sert aussi à enregistrer un vrai Linky pour le rejouer ensuite
    rejouer : renvoie un enregistrement brut sur un port série

Exemples :
    python simulateur_tic.py envoyer --port /dev/tty.usbmodem1103 --mode standard --offre tempo
    python simulateur_tic.py envoyer --port COM5 --ukdale ~/UK-DALE/house_1 --jour 2013-12-31 --accel 60
    python simulateur_tic.py envoyer --sortie trames.bin --nb 20 --erreurs 10
    python simulateur_tic.py lire --fichier trames.bin
    python simulateur_tic.py lire --port /dev/tty.usbserial-A1 --mode historique --enregistrer linky.bin

Format sur la ligne : 7 bits, parité paire, 1 bit de stop, 9 600 bauds (standard) ou 1 200 bauds (historique).
Si le port série ne propose pas le 7E1 (certains ports virtuels), --8n1 envoie en 8N1 en plaçant le bit de
parité dans le 8e bit : c'est exactement le même signal sur le fil.

Référence : Enedis-NOI-CPT_54E (sortie de téléinformation client des compteurs Linky).
Dépendance : pyserial, seulement pour utiliser un vrai port série (pip install pyserial).
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import math
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

STX, ETX, EOT, LF, CR, HT, SP = b"\x02", b"\x03", b"\x04", b"\n", b"\r", b"\t", b" "
DEBIT = {"standard": 9600, "historique": 1200}
COULEURS = ("BLEU", "BLANC", "ROUGE")
CODE_COULEUR = {None: 0, "BLEU": 1, "BLANC": 2, "ROUGE": 3}          # registre STGE, bits 24-25 et 26-27
DEMAIN_HISTO = {None: "----", "BLEU": "BLEU", "BLANC": "BLAN", "ROUGE": "ROUG"}


# =============================================================================== sommes de contrôle
def somme_controle(octets: bytes) -> bytes:
    """Somme des codes ASCII, gardée sur 6 bits, plus 0x20 (caractère imprimable)."""
    return bytes([(sum(octets) & 0x3F) + 0x20])


def groupe_standard(etiquette: str, donnee: str, horodate: str | None = None) -> bytes:
    """Mode standard : LF étiquette HT [horodate HT] donnée HT somme CR. La somme couvre le dernier HT."""
    corps = etiquette.encode("ascii") + HT
    if horodate is not None:
        corps += horodate.encode("ascii") + HT
    corps += donnee.encode("ascii") + HT
    return LF + corps + somme_controle(corps) + CR


def groupe_historique(etiquette: str, donnee: str) -> bytes:
    """Mode historique : LF étiquette SP donnée SP somme CR. La somme s'arrête avant le dernier espace."""
    corps = etiquette.encode("ascii") + SP + donnee.encode("ascii")
    return LF + corps + SP + somme_controle(corps) + CR


def ajouter_parite_8n1(octets: bytes) -> bytes:
    """7 bits + parité paire dans le bit 7 : même signal que du 7E1, envoyable par un port réglé en 8N1."""
    return bytes([b | ((bin(b).count("1") & 1) << 7) for b in octets])


# =============================================================================== état simulé du compteur
@dataclass
class Compteur:
    mode: str = "standard"
    offre: str = "base"                 # base, hphc, tempo
    adresse: str = "021861348497"
    pref_kva: int = 6
    couleur: str | None = None          # couleur Tempo du jour
    demain: str | None = None           # couleur Tempo du lendemain (connue vers 11 h)
    cos_phi: float = 0.9                # pour passer de la puissance apparente (VA) à l'énergie active (Wh)
    index_wh: dict = field(default_factory=lambda: {"base": 12_345_678, "hc": 4_000_000, "hp": 8_000_000})
    smax_va: int = 0

    def heures_creuses(self, t: dt.datetime) -> bool:
        return self.offre in ("hphc", "tempo") and (t.hour >= 22 or t.hour < 6)

    def poste(self, t: dt.datetime) -> str:
        if self.offre == "base":
            return "base"
        return "hc" if self.heures_creuses(t) else "hp"

    def avancer(self, s_va: float, duree_s: float, t: dt.datetime):
        self.index_wh[self.poste(t)] += s_va * self.cos_phi * duree_s / 3600.0
        self.smax_va = max(self.smax_va, int(s_va))

    # ------------------------------------------------------------------ trames
    def trame(self, t: dt.datetime, s_va: float, u_v: float) -> bytes:
        return self._trame_standard(t, s_va, u_v) if self.mode == "standard" else self._trame_historique(t, s_va)

    def _libelle_tarif(self, t: dt.datetime) -> str:
        if self.offre == "base":
            return "BASE"
        hc = self.heures_creuses(t)
        if self.offre == "hphc":
            return "HEURE CREUSE" if hc else "HEURE PLEINE"
        return f"{'HC' if hc else 'HP'} {self.couleur or 'BLEU'}"

    def _trame_standard(self, t: dt.datetime, s_va: float, u_v: float) -> bytes:
        saison = "E" if 3 < t.month < 11 else "H"                    # simplifié : été d'avril à octobre
        hd = saison + t.strftime("%y%m%d%H%M%S")
        i_a = round(s_va / u_v)
        total = round(sum(self.index_wh.values()) if self.offre != "base" else self.index_wh["base"])
        stge = (CODE_COULEUR[self.couleur] << 24) | (CODE_COULEUR[self.demain] << 26)
        groupes = [
            groupe_standard("ADSC", self.adresse),
            groupe_standard("VTIC", "02"),
            groupe_standard("DATE", "", hd),
            groupe_standard("NGTF", {"base": "BASE", "hphc": "HC", "tempo": "TEMPO"}[self.offre].ljust(16)),
            groupe_standard("LTARF", self._libelle_tarif(t).ljust(16)),
            groupe_standard("EAST", f"{total:09d}"),
        ]
        if self.offre == "base":
            groupes.append(groupe_standard("EASF01", f"{round(self.index_wh['base']):09d}"))
        else:
            groupes.append(groupe_standard("EASF01", f"{round(self.index_wh['hc']):09d}"))
            groupes.append(groupe_standard("EASF02", f"{round(self.index_wh['hp']):09d}"))
        groupes += [
            groupe_standard("IRMS1", f"{i_a:03d}"),
            groupe_standard("URMS1", f"{round(u_v):03d}"),
            groupe_standard("PREF", f"{self.pref_kva:02d}"),
            groupe_standard("PCOUP", f"{self.pref_kva:02d}"),
            groupe_standard("SINSTS", f"{round(s_va):05d}"),
            groupe_standard("SMAXSN", f"{self.smax_va:05d}", hd),
            groupe_standard("UMOY1", f"{round(u_v):03d}", hd),
            groupe_standard("STGE", f"{stge:08X}"),
            groupe_standard("NTARF", "02" if self.poste(t) == "hp" else "01"),
            groupe_standard("MSG1", "PAS DE          MESSAGE         "),
        ]
        return STX + b"".join(groupes) + ETX

    def _trame_historique(self, t: dt.datetime, s_va: float) -> bytes:
        i_a = round(s_va / 230)
        optarif = {"base": "BASE", "hphc": "HC..", "tempo": "BBR("}[self.offre]
        groupes = [groupe_historique("ADCO", self.adresse), groupe_historique("OPTARIF", optarif),
                   groupe_historique("ISOUSC", f"{self.pref_kva * 5:02d}")]
        if self.offre == "base":
            groupes.append(groupe_historique("BASE", f"{round(self.index_wh['base']):09d}"))
            ptec = "TH.."
        elif self.offre == "hphc":
            groupes += [groupe_historique("HCHC", f"{round(self.index_wh['hc']):09d}"),
                        groupe_historique("HCHP", f"{round(self.index_wh['hp']):09d}")]
            ptec = "HC.." if self.heures_creuses(t) else "HP.."
        else:
            c = {"BLEU": "JB", "BLANC": "JW", "ROUGE": "JR"}[self.couleur or "BLEU"]
            for nom in ("BBRHCJB", "BBRHPJB", "BBRHCJW", "BBRHPJW", "BBRHCJR", "BBRHPJR"):
                v = self.index_wh["hc" if "HC" in nom else "hp"] if nom.endswith(c) else 0
                groupes.append(groupe_historique(nom, f"{round(v):09d}"))
            ptec = ("HC" if self.heures_creuses(t) else "HP") + c
            groupes.append(groupe_historique("DEMAIN", DEMAIN_HISTO[self.demain]))
        groupes += [groupe_historique("PTEC", ptec), groupe_historique("IINST", f"{i_a:03d}"),
                    groupe_historique("IMAX", "090"), groupe_historique("PAPP", f"{round(s_va):05d}"),
                    groupe_historique("HHPHC", "A"), groupe_historique("MOTDETAT", "000000")]
        return STX + b"".join(groupes) + ETX


# =============================================================================== sources de puissance
class SourceUKDALE:
    """Rejoue le canal « aggregate » (puissance apparente, VA) d'une maison UK-DALE pour un jour donné."""

    def __init__(self, dossier: Path, jour: dt.date):
        canal = None
        for ligne in (dossier / "labels.dat").read_text().splitlines():
            num, nom = ligne.split()[:2]
            if nom == "aggregate":
                canal = int(num)
        if canal is None:
            raise SystemExit(f"pas de canal « aggregate » dans {dossier / 'labels.dat'}")
        debut = dt.datetime.combine(jour, dt.time(), dt.timezone.utc).timestamp()
        fin = debut + 86400
        self.t, self.p = [], []
        with open(dossier / f"channel_{canal}.dat") as f:
            for ligne in f:
                ts, val = ligne.split()[:2]
                ts = float(ts)
                if ts < debut:
                    continue
                if ts >= fin:
                    break
                self.t.append(ts - debut)
                self.p.append(float(val))
        if not self.t:
            raise SystemExit(f"aucune mesure le {jour} dans {dossier}")
        print(f"UK-DALE : {len(self.t)} mesures le {jour}, de {min(self.p):.0f} à {max(self.p):.0f} VA", file=sys.stderr)

    def __call__(self, seconde_du_jour: float) -> float:
        k = bisect.bisect_right(self.t, seconde_du_jour % 86400) - 1
        return self.p[max(k, 0)]


def source_aleatoire(base_va: float = 350.0):
    """Talon de consommation + cycles d'appareils tirés au hasard (bouilloire, four, lave-linge)."""
    rng = random.Random(1)
    cycles = []

    def p(seconde: float) -> float:
        if rng.random() < 0.002:
            cycles.append((seconde, rng.choice([(180, 2000), (1800, 1500), (5400, 600)])))
        actifs = [c for c in cycles if c[0] <= seconde < c[0] + c[1][0]]
        cycles[:] = [c for c in cycles if seconde < c[0] + c[1][0]]
        return base_va + 40 * math.sin(seconde / 300) + sum(c[1][1] for c in actifs) + rng.uniform(-15, 15)

    return p


# =============================================================================== erreurs volontaires
def abimer(trame: bytes, rng: random.Random) -> tuple[bytes, str]:
    choix = rng.choice(["somme", "coupee", "octet", "sans_etx"])
    if choix == "somme":                                   # une somme de contrôle fausse
        lignes = trame.split(CR)
        k = rng.randrange(len(lignes) - 1)
        l = bytearray(lignes[k]); l[-1] = 0x20 + ((l[-1] - 0x20 + 1) & 0x3F); lignes[k] = bytes(l)
        return CR.join(lignes), "somme de contrôle fausse"
    if choix == "coupee":                                  # trame interrompue (EOT)
        return trame[: len(trame) // 2] + EOT, "trame interrompue"
    if choix == "octet":                                   # un caractère remplacé (bruit)
        b = bytearray(trame)
        while True:                                        # un caractère imprimable remplacé par un autre ;
            k = rng.randrange(2, len(b) - 2)               # écart non multiple de 64, sinon la somme sur 6 bits
            n = rng.randrange(0x21, 0x7E)                  # ne le verrait pas (limite connue de la TIC)
            if 0x20 < b[k] < 0x7F and (n - b[k]) % 64:
                b[k] = n
                return bytes(b), "caractère modifié"
    return trame[:-1], "ETX manquant"


# =============================================================================== décodage (référence pour le code C)
def decoder_groupe(ligne: bytes, mode: str) -> tuple[str, str, str | None, bool]:
    """Ligne sans LF ni CR -> (étiquette, donnée, horodate, somme_ok)."""
    if len(ligne) < 3:
        return "", "", None, False
    somme = ligne[-1:]
    if mode == "standard":
        corps = ligne[:-1]                          # se termine par HT
        champs = corps[:-1].split(HT)
        ok = corps.endswith(HT) and somme == somme_controle(corps)
        etiquette = champs[0].decode("ascii", "replace")
        if len(champs) == 3:
            return etiquette, champs[2].decode("ascii", "replace"), champs[1].decode("ascii", "replace"), ok
        return etiquette, (champs[1].decode("ascii", "replace") if len(champs) > 1 else ""), None, ok
    corps = ligne[:-2]                              # sans « SP somme »
    champs = corps.split(SP, 1)
    ok = ligne[-2:-1] == SP and somme == somme_controle(corps)
    return champs[0].decode("ascii", "replace"), (champs[1].decode("ascii", "replace") if len(champs) > 1 else ""), None, ok


def decouper_trames(flux: bytes):
    """Renvoie les trames complètes (entre STX et ETX) ; une trame interrompue par EOT est ignorée."""
    trames, courant = [], None
    for b in flux:
        o = bytes([b & 0x7F])                       # le bit 7 est la parité : on le masque
        if o == STX:
            courant = bytearray()
        elif courant is None:
            continue
        elif o == EOT:
            courant = None
        elif o == ETX:
            trames.append(bytes(courant)); courant = None
        else:
            courant += o
    return trames


def decoder_trame(trame: bytes, mode: str) -> dict:
    valeurs, erreurs = {}, []
    for ligne in trame.split(CR):
        ligne = ligne.lstrip(LF)
        if not ligne:
            continue
        etiquette, donnee, horodate, ok = decoder_groupe(ligne, mode)
        if ok:
            valeurs[etiquette] = (horodate, donnee) if horodate else donnee
        else:
            erreurs.append(etiquette or ligne[:12].decode("ascii", "replace"))
    return {"valeurs": valeurs, "erreurs": erreurs}


def detecter_mode(trame: bytes) -> str:
    return "standard" if HT in trame else "historique"


# =============================================================================== port série
def ouvrir_port(nom: str, mode: str, mode_8n1: bool):
    try:
        import serial
    except ImportError:
        raise SystemExit("pyserial manquant : pip install pyserial")
    return serial.Serial(nom, baudrate=DEBIT[mode], timeout=1,
                         bytesize=serial.EIGHTBITS if mode_8n1 else serial.SEVENBITS,
                         parity=serial.PARITY_NONE if mode_8n1 else serial.PARITY_EVEN,
                         stopbits=serial.STOPBITS_ONE)


# =============================================================================== commandes
def cmd_envoyer(a):
    if a.ukdale:
        jour = dt.date.fromisoformat(a.jour)
        source = SourceUKDALE(Path(a.ukdale).expanduser(), jour)
        t0 = dt.datetime.combine(jour, dt.time.fromisoformat(a.heure))
    else:
        source = (lambda s: a.puissance) if a.puissance is not None else source_aleatoire()
        t0 = dt.datetime.now().replace(microsecond=0) if a.debut is None else dt.datetime.fromisoformat(a.debut)
    demain = a.demain or (a.couleur if a.offre == "tempo" else None)
    cpt = Compteur(mode=a.mode, offre=a.offre, couleur=a.couleur if a.offre == "tempo" else None,
                   demain=demain if a.offre == "tempo" else None, pref_kva=a.pref)
    port = ouvrir_port(a.port, a.mode, a.mode_8n1) if a.port else None
    sortie = open(a.sortie, "wb") if a.sortie else None
    if port is None and sortie is None:
        raise SystemExit("indiquer --port (port série) ou --sortie (fichier)")
    rng = random.Random(a.graine)
    pas = a.periode * a.accel                      # secondes simulées entre deux trames
    print(f"mode {a.mode} ({DEBIT[a.mode]} bauds, 7E1{' émulé en 8N1' if a.mode_8n1 else ''}), offre {a.offre}, "
          f"une trame toutes les {a.periode} s, {pas:g} s simulées par trame", file=sys.stderr)
    n = 0
    try:
        while a.nb is None or n < a.nb:
            t = t0 + dt.timedelta(seconds=n * pas)
            sec = (t - t.replace(hour=0, minute=0, second=0)).total_seconds()
            s_va = max(0.0, source(sec))
            u_v = 230 + 3 * math.sin(sec / 900)
            trame = cpt.trame(t, s_va, u_v)
            note = ""
            if a.erreurs and rng.random() * 100 < a.erreurs:
                trame, note = abimer(trame, rng)
            octets = ajouter_parite_8n1(trame) if a.mode_8n1 else trame
            if port:
                port.write(octets); port.flush()
            if sortie:
                sortie.write(octets)
            if a.afficher or not port:
                print(f"{t:%H:%M:%S}  S = {s_va:6.0f} VA  {len(trame)} octets  {note}", file=sys.stderr)
            cpt.avancer(s_va, pas, t)
            n += 1
            if port and (a.nb is None or n < a.nb):
                time.sleep(a.periode)
    except KeyboardInterrupt:
        pass
    finally:
        if port:
            port.close()
        if sortie:
            sortie.close()
    print(f"{n} trames envoyées", file=sys.stderr)


def afficher_trame(tr: bytes, mode: str | None):
    m = mode or detecter_mode(tr)
    res = decoder_trame(tr, m)
    v = res["valeurs"]
    cle_p = "SINSTS" if m == "standard" else "PAPP"
    resume = f"[{m}] {cle_p}={v.get(cle_p, '?')}"
    for k in ("LTARF", "PTEC", "EAST", "BASE", "IRMS1", "IINST", "STGE", "DEMAIN"):
        if k in v:
            resume += f" {k}={(v[k] if not isinstance(v[k], tuple) else v[k][1]).strip()}"
    if res["erreurs"]:
        resume += f"  ERREURS : {', '.join(res['erreurs'])}"
    print(resume)


def cmd_lire(a):
    if a.fichier:
        for tr in decouper_trames(Path(a.fichier).read_bytes()):
            afficher_trame(tr, a.mode)
        return
    port = ouvrir_port(a.port, a.mode or "standard", a.mode_8n1)
    enreg = open(a.enregistrer, "ab") if a.enregistrer else None
    tampon = b""
    print("lecture en cours (Ctrl+C pour arrêter)", file=sys.stderr)
    try:
        while True:
            octets = port.read(256)
            if enreg and octets:
                enreg.write(octets); enreg.flush()
            tampon += octets
            if ETX in tampon or (bytes([ETX[0] | 0x80]) in tampon):
                for tr in decouper_trames(tampon):
                    afficher_trame(tr, a.mode)
                k = max(tampon.rfind(ETX), tampon.rfind(bytes([ETX[0] | 0x80])))
                tampon = tampon[k + 1:]
    except KeyboardInterrupt:
        pass
    finally:
        port.close()
        if enreg:
            enreg.close()


def cmd_rejouer(a):
    trames = decouper_trames(Path(a.fichier).read_bytes())
    mode = a.mode or (detecter_mode(trames[0]) if trames else "standard")
    port = ouvrir_port(a.port, mode, a.mode_8n1)
    print(f"{len(trames)} trames à rejouer en mode {mode}", file=sys.stderr)
    try:
        for i, tr in enumerate(trames):
            octets = STX + tr + ETX
            port.write(ajouter_parite_8n1(octets) if a.mode_8n1 else octets); port.flush()
            if i < len(trames) - 1:
                time.sleep(a.periode)
    finally:
        port.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Simulateur et lecteur de TIC Linky")
    sp = ap.add_subparsers(dest="commande", required=True)

    e = sp.add_parser("envoyer", help="fabriquer et envoyer des trames")
    e.add_argument("--port", help="port série (ex. /dev/tty.usbmodem1103, COM5)")
    e.add_argument("--sortie", help="écrire les trames dans un fichier au lieu (ou en plus) du port")
    e.add_argument("--mode", choices=["standard", "historique"], default="standard")
    e.add_argument("--offre", choices=["base", "hphc", "tempo"], default="base")
    e.add_argument("--couleur", choices=COULEURS, default="BLEU", help="couleur Tempo du jour")
    e.add_argument("--demain", choices=COULEURS, default=None, help="couleur Tempo du lendemain")
    e.add_argument("--pref", type=int, default=6, help="puissance souscrite (kVA)")
    e.add_argument("--puissance", type=float, default=None, help="puissance apparente constante (VA)")
    e.add_argument("--ukdale", help="dossier d'une maison UK-DALE (labels.dat, channel_N.dat)")
    e.add_argument("--jour", default="2013-12-31", help="jour UK-DALE à rejouer (AAAA-MM-JJ)")
    e.add_argument("--heure", default="00:00:00", help="heure de départ dans le jour UK-DALE")
    e.add_argument("--debut", default=None, help="date et heure simulées de départ (sans UK-DALE)")
    e.add_argument("--periode", type=float, default=1.0, help="secondes réelles entre deux trames")
    e.add_argument("--accel", type=float, default=1.0, help="accélération du temps simulé (60 = 1 min par trame)")
    e.add_argument("--nb", type=int, default=None, help="nombre de trames (par défaut : sans fin)")
    e.add_argument("--erreurs", type=float, default=0.0, help="pourcentage de trames volontairement abîmées")
    e.add_argument("--graine", type=int, default=0)
    e.add_argument("--8n1", dest="mode_8n1", action="store_true", help="émuler le 7E1 sur un port réglé en 8N1")
    e.add_argument("--afficher", action="store_true", help="afficher chaque trame envoyée")
    e.set_defaults(fonction=cmd_envoyer)

    l = sp.add_parser("lire", help="lire, vérifier et afficher des trames")
    l.add_argument("--port"); l.add_argument("--fichier")
    l.add_argument("--mode", choices=["standard", "historique"], default=None, help="par défaut : détecté")
    l.add_argument("--enregistrer", help="enregistrer les octets bruts reçus dans un fichier")
    l.add_argument("--8n1", dest="mode_8n1", action="store_true")
    l.set_defaults(fonction=cmd_lire)

    r = sp.add_parser("rejouer", help="renvoyer un enregistrement brut sur un port série")
    r.add_argument("--port", required=True); r.add_argument("--fichier", required=True)
    r.add_argument("--mode", choices=["standard", "historique"], default=None)
    r.add_argument("--periode", type=float, default=1.0)
    r.add_argument("--8n1", dest="mode_8n1", action="store_true")
    r.set_defaults(fonction=cmd_rejouer)

    a = ap.parse_args(argv)
    if a.commande == "lire" and not (a.port or a.fichier):
        ap.error("lire : indiquer --port ou --fichier")
    a.fonction(a)


if __name__ == "__main__":
    main()
