"""Cycle d'échange du boîtier NILM avec le broker, piloté depuis le PC (partie B).

Reproduit le cycle validé à la main sur le kit le 26 novembre 2026 (journal des tests) :
connexion au broker, publication de la mesure, abonnement aux topics de commande,
lecture des commandes retenues, confirmation de l'état des relais, déconnexion.
Entre deux cycles, le module reste attaché au réseau et dort (PSM) : pas de AT+CFUN.

C'est la séquence que devra suivre le programme de la carte STM32 (B-32). Le script sert
aussi à mesurer la durée et le volume de données d'un cycle (B-29).

Exemples :

    # sans le kit, avec le faux module
    python cycle_st87m01.py --simulateur --cycles 3

    # 10 cycles d'affilée dans une seule session de données, pour lire le volume dans SIMPro
    python cycle_st87m01.py --port COM4 --broker <adresse IP> --utilisateur <compte> --demander-mdp \\
        --cycles 10 --nouvelle-session --fermer-session

    # fonctionnement réel : un cycle toutes les 15 minutes
    python cycle_st87m01.py --port COM4 --broker <adresse IP> --utilisateur <compte> --demander-mdp \\
        --cycles 8 --intervalle 900

Le mot de passe MQTT n'est jamais passé en ligne de commande : variable d'environnement
ST87M01_MQTT_MDP, ou saisie au clavier (--demander-mdp). Il est masqué dans le journal.

Règles tirées des essais (20, 25 et 26 nov 2026) :
- une commande à la fois, en attendant sa réponse ;
- message publié entre guillemets (le « ; » sépare deux commandes AT) ;
- abonnements aux topics exacts : avec un joker (+), le module acquitte sans afficher #MQTTRECV ;
- en cas d'erreur de la pile MQTT ou TCP (2215, 2218, 2220, 2152, #TCPSENDFAIL), redémarrer
  avec AT#RESET=1 (jamais AT#RESET=0, qui ne sauvegarde pas la configuration) ;
- vérifier l'APN au démarrage (il s'est effacé une fois, le 25 nov).
"""

import argparse
import csv
import datetime as dt
import getpass
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from test_jour1 import CONTEXTE, DOSSIER_JOURNAUX, Journal, Modem, TransportSerie, champs, etat_cereg, \
    verifier_limites

# Codes d'erreur après lesquels seule une remise à zéro du module a débloqué la situation
ERREURS_BLOCAGE = ("2152", "2215", "2218", "2220", "2226")


# ---------------------------------------------------------------- démarrage

def reveiller(modem, essais=4):
    """Le module peut dormir (DRX, PSM) : la première commande ne fait souvent que le réveiller."""
    for _ in range(essais):
        if modem.commande("AT", delai=3.0).ok:
            return True
    return False


def apn_correct(ligne, apn):
    """'+CGDCONT: 5,"IP","EAPN1.NET",...' -> True si le contexte 5 est en IP avec le bon APN."""
    c = champs(ligne)
    return len(c) >= 3 and c[0] == str(CONTEXTE) and c[1] == "IP" and c[2].lower() == apn.lower()


def relancer_radio(modem, opts):
    """AT+CFUN=0 puis AT+CFUN=1, et attente de #IPCFG: 5,0,1 (connexion de données prête)."""
    modem.commande("AT+CFUN=0", delai=15)
    modem.urc.clear()
    if not modem.commande("AT+CFUN=1", delai=15).ok:
        return False
    return modem.attendre(f"#IPCFG: {CONTEXTE},0,1", opts.attente_attache) is not None


def demarrer(modem, opts, forcer_radio=False):
    """Prépare le module. Renvoie (ok, détail)."""
    c = modem.commande
    if not reveiller(modem):
        return False, "le module ne répond pas à AT"
    if opts.sans_veille:
        c("AT#SLEEPMODE=0")
    rep = c("AT+CGDCONT?")
    ligne = next((l for l in rep.lignes if l.startswith(f"+CGDCONT: {CONTEXTE},")), None)
    if not apn_correct(ligne, opts.apn):
        if not opts.corriger_apn:
            return False, f"APN incorrect ({ligne or 'contexte 5 absent'}) : relancer avec --corriger-apn"
        c("AT+CFUN=0", delai=15)
        if not c(f'AT+CGDCONT={CONTEXTE},"IP","{opts.apn}"').ok:
            return False, "impossible d'écrire l'APN"
        forcer_radio = True
    if not forcer_radio:
        etat = etat_cereg(c("AT+CEREG?").ligne("+CEREG:"))
        adresse = champs(c(f"AT+CGPADDR={CONTEXTE}").ligne("+CGPADDR:"))
        if etat in (1, 5) and len(adresse) >= 2 and adresse[1]:
            return True, "déjà attaché, adresse IP présente : pas de AT+CFUN"
    if not relancer_radio(modem, opts):
        return False, f"pas de #IPCFG: {CONTEXTE},0,1 après {opts.attente_attache:.0f} s"
    return True, "connexion de données ouverte (AT+CFUN=0 puis AT+CFUN=1)"


def remettre_a_zero(modem, opts, dormir):
    """AT#RESET=1 (sauvegarde la configuration), puis nouvelle connexion de données."""
    modem.commande("AT#RESET=1", delai=10)
    dormir(opts.attente_reset)
    modem.urc.clear()
    return demarrer(modem, opts, forcer_radio=True)


# ---------------------------------------------------------------- cycle

def lire_recus(modem, delai, horloge):
    """Collecte les #MQTTRECV déjà arrivés, puis ceux qui arrivent pendant `delai` secondes."""
    recus = [l for l in modem.urc if l.startswith("#MQTTRECV:")]
    modem.urc = [l for l in modem.urc if not l.startswith("#MQTTRECV:")]
    debut = horloge()
    while horloge() - debut < delai:
        l = modem.t.lire_ligne(delai - (horloge() - debut))
        if l is None:
            break
        if not l:
            continue
        modem.j.ecrire("<<", l)
        (recus if l.startswith("#MQTTRECV:") else modem.urc).append(l)
    return recus


def decoder_recu(ligne):
    """'#MQTTRECV: nilm/maison/cmd/chauffe_eau,ON' -> ('nilm/maison/cmd/chauffe_eau', 'ON')"""
    corps = ligne.split(":", 1)[1].strip()
    topic, _, message = corps.partition(",")
    return topic.strip(), message.strip()


@dataclass
class Cycle:
    numero: int
    debut: str = ""
    ok: bool = False
    etape_echec: str = ""
    erreur: str = ""
    durees: dict = field(default_factory=dict)
    recus: list = field(default_factory=list)       # (topic, message)
    confirmes: list = field(default_factory=list)   # (topic d'état, message)
    total: float = 0.0
    reprise: bool = False

    @property
    def bloque(self):
        return any(code in self.erreur for code in ERREURS_BLOCAGE) or "TCPSENDFAIL" in self.erreur


def un_cycle(modem, opts, numero, horloge):
    """Un cycle complet. Renvoie un Cycle (ok à False et étape en cause en cas d'échec)."""
    c = modem.commande
    cy = Cycle(numero, f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    debut = horloge()

    def etape(nom, cmd, delai):
        rep = c(cmd, delai=delai)
        cy.durees[nom] = round(rep.duree, 1)
        echec_tcp = next((l for l in modem.urc if l.startswith("#TCPSENDFAIL")), None)
        if not rep.ok or echec_tcp:
            cy.etape_echec = nom
            cy.erreur = " ".join(x for x in (rep.erreur, echec_tcp) if x)
            modem.urc = [l for l in modem.urc if not l.startswith("#TCPSENDFAIL")]
        return rep if rep.ok and not echec_tcp else None

    if not etape("configuration", f"AT#MQTTCFG={opts.client},60,60,3,{opts.keepalive}", 5):
        return cy
    # TLS : 7e paramètre 0 (pas de #IPRECV), 8e = profil de sécurité, 9e = 1 (reprise de session)
    tls = f",0,{opts.profil_tls},1" if opts.tls else ""
    rep = etape("socket", f"AT#SOCKETCREATE={CONTEXTE},0,TCP,,60,60{tls}", 10)
    if not rep:
        return cy
    sid = champs(rep.ligne("#SOCKETCREATE:"))[0]
    cmd = f"AT#MQTTCONNECT={CONTEXTE},{sid},{opts.broker},{opts.port_mqtt}"
    if opts.utilisateur:
        cmd += f",{opts.utilisateur}" + (f",{opts.mdp}" if opts.mdp else "")
    if not etape("connexion", cmd, 70):
        c(f"AT#SOCKETCLOSE={CONTEXTE},{sid}", delai=10)
        return cy
    ok = bool(etape("publication", f'AT#MQTTPUB={opts.topic},"{opts.message}",3,1,0', 60))
    if ok:
        topics = [opts.topic_plan] + [f"{opts.base_cmd}/{a}" for a in opts.appareils]
        abonnement = "AT#MQTTSUB=" + ",".join(f"{t},1" for t in topics)
        # 2216 possible si le broker répond en plus de 10 s : les messages retenus peuvent arriver quand même
        if not etape("abonnement", abonnement, 30) and "2216" not in cy.erreur:
            ok = False
        else:
            cy.recus = [decoder_recu(l) for l in lire_recus(modem, opts.attente_commandes, horloge)]
            for topic, message in cy.recus:
                appareil = topic.rsplit("/", 1)[-1]
                if opts.confirmer and appareil in opts.appareils and message in ("ON", "OFF"):
                    # la carte basculerait le relais ici ; on confirme l'état à Home Assistant
                    if not etape("confirmation", f'AT#MQTTPUB={topic}/etat,"{message}",3,1,0', 60):
                        ok = False
                        break
                    cy.confirmes.append((f"{topic}/etat", message))
    if not etape("deconnexion", "AT#MQTTDISC", 30):  # ferme aussi la socket
        ok = False
    cy.ok = ok and cy.etape_echec in ("", "abonnement")
    cy.total = round(horloge() - debut, 1)
    return cy


def seance(modem, opts, dormir=time.sleep, horloge=time.monotonic):
    """Démarrage puis `opts.cycles` cycles. Renvoie (détail du démarrage, liste des cycles)."""
    ok, detail = demarrer(modem, opts, forcer_radio=opts.nouvelle_session)
    modem.j.ecrire("--", f"démarrage : {detail}")
    cycles = []
    if not ok:
        return detail, cycles
    for n in range(1, opts.cycles + 1):
        debut = horloge()
        cy = un_cycle(modem, opts, n, horloge)
        if not cy.ok and opts.reprise:
            modem.j.ecrire("--", f"cycle {n} en échec ({cy.etape_echec} : {cy.erreur}) : AT#RESET=1 et nouvel essai")
            ok, detail = remettre_a_zero(modem, opts, dormir)
            if ok:
                cy = un_cycle(modem, opts, n, horloge)
                cy.reprise = True
        cycles.append(cy)
        modem.j.ecrire("--", f"cycle {n} : {'OK' if cy.ok else 'ÉCHEC'} en {cy.total} s, "
                             f"reçu {cy.recus or '-'}, confirmé {cy.confirmes or '-'}")
        if not cy.ok and not opts.reprise:
            break
        if n < opts.cycles and opts.intervalle > 0:
            dormir(max(opts.intervalle - (horloge() - debut), 0))
    if opts.fermer_session:
        modem.commande("AT+CFUN=0", delai=15)  # ferme la session de données (comptée à part dans SIMPro)
    return detail, cycles


# ---------------------------------------------------------------- relevé

COLONNES = ["debut", "cycle", "ok", "reprise", "etape_echec", "erreur", "connexion_s", "publication_s",
            "abonnement_s", "confirmation_s", "deconnexion_s", "total_s", "recus", "confirmes"]


def ligne_releve(cy):
    d = cy.durees
    return {"debut": cy.debut, "cycle": cy.numero, "ok": "oui" if cy.ok else "non",
            "reprise": "oui" if cy.reprise else "", "etape_echec": cy.etape_echec, "erreur": cy.erreur,
            "connexion_s": d.get("connexion", ""), "publication_s": d.get("publication", ""),
            "abonnement_s": d.get("abonnement", ""), "confirmation_s": d.get("confirmation", ""),
            "deconnexion_s": d.get("deconnexion", ""), "total_s": cy.total,
            "recus": " | ".join(f"{t}={m}" for t, m in cy.recus),
            "confirmes": " | ".join(f"{t}={m}" for t, m in cy.confirmes)}


def ajouter_releve(chemin, cycles):
    nouveau = not Path(chemin).exists()
    with open(chemin, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        if nouveau:
            w.writeheader()
        for cy in cycles:
            w.writerow(ligne_releve(cy))


# ---------------------------------------------------------------- programme

def options(argv=None):
    p = argparse.ArgumentParser(description="Cycle d'échange MQTT du ST87M01, tel que validé sur le kit.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="port série du CP2105 (Standard COM Port), par exemple COM4")
    src.add_argument("--simulateur", action="store_true", help="utiliser le faux module (sans kit)")
    p.add_argument("--broker", help="adresse IP du broker (obligatoire avec --port ; pas de nom : le module ne résout pas)")
    p.add_argument("--port-mqtt", type=int, help="1883 par défaut, 8883 avec --tls")
    p.add_argument("--tls", action="store_true",
                   help="connexion chiffrée : socket liée au profil de sécurité (certificat racine chargé avant)")
    p.add_argument("--profil-tls", type=int, default=0, help="profil de sécurité du module (AT#TLSCERTADD)")
    p.add_argument("--client", default="nilm_01")
    p.add_argument("--utilisateur", default="")
    p.add_argument("--demander-mdp", action="store_true", help="demander le mot de passe MQTT au clavier")
    p.add_argument("--topic", default="nilm/maison/etat")
    p.add_argument("--message", default="1615;21;48;0;0;310")
    p.add_argument("--topic-plan", default="nilm/maison/cmd/plan")
    p.add_argument("--base-cmd", default="nilm/maison/cmd")
    p.add_argument("--appareils", nargs="+", default=["chauffe_eau"],
                   help="appareils pilotés : abonnement à <base-cmd>/<appareil> (topic exact, sans joker)")
    p.add_argument("--sans-confirmation", dest="confirmer", action="store_false",
                   help="ne pas renvoyer l'état des relais sur <topic>/etat")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--intervalle", type=float, default=0,
                   help="secondes entre le début de deux cycles (900 = 15 min) ; 0 = enchaîner")
    p.add_argument("--attente-commandes", type=float, default=10, help="attente des #MQTTRECV après l'abonnement (s)")
    p.add_argument("--keepalive", type=int, default=120)
    p.add_argument("--apn", default="eapn1.net")
    p.add_argument("--corriger-apn", action="store_true", help="réécrire l'APN s'il est effacé ou incorrect")
    p.add_argument("--nouvelle-session", action="store_true",
                   help="ouvrir une nouvelle session de données au départ (AT+CFUN=0 puis 1)")
    p.add_argument("--fermer-session", action="store_true", help="finir par AT+CFUN=0 (session fermée dans SIMPro)")
    p.add_argument("--sans-reprise", dest="reprise", action="store_false",
                   help="s'arrêter au premier échec au lieu de redémarrer le module (AT#RESET=1)")
    p.add_argument("--garder-veille", dest="sans_veille", action="store_false",
                   help="ne pas envoyer AT#SLEEPMODE=0")
    p.add_argument("--attente-attache", type=float, default=180, help="attente maximale de #IPCFG: 5,0,1 (s)")
    p.add_argument("--attente-reset", type=float, default=15, help="pause après AT#RESET=1 (s)")
    p.add_argument("--journaux", default=str(DOSSIER_JOURNAUX))
    o = p.parse_args(argv)
    if o.port and not o.broker:
        p.error("--broker est obligatoire avec --port")
    o.port_mqtt = o.port_mqtt or (8883 if o.tls else 1883)
    o.broker = o.broker or "10.0.0.1"  # adresse fictive pour le faux module
    o.mdp = os.environ.get("ST87M01_MQTT_MDP", "")
    if o.demander_mdp:
        o.mdp = getpass.getpass("Mot de passe MQTT : ")
    return o


def main(argv=None):
    o = options(argv)
    topics = [o.topic, o.topic_plan] + [f"{o.base_cmd}/{a}/etat" for a in o.appareils]
    pbs = verifier_limites(o.client, o.utilisateur, o.mdp, topics, o.message)
    if pbs:
        print("Limites du module dépassées : " + "; ".join(pbs))
        return 2
    Path(o.journaux).mkdir(parents=True, exist_ok=True)
    horodatage = f"{dt.datetime.now():%Y%m%d_%H%M%S}"
    journal = Journal(Path(o.journaux) / f"cycles_{horodatage}.log")
    journal.secrets.append(o.mdp)
    dormir, horloge = time.sleep, time.monotonic
    if o.simulateur:
        from faux_st87m01 import FauxST87M01, HorlogeSimulee

        h = HorlogeSimulee()
        transport = FauxST87M01(horloge=h)
        dormir, horloge = h.avancer, h.maintenant
    else:
        transport = TransportSerie(o.port)
    journal.ecrire("--", f"séance {horodatage}, {'faux module' if o.simulateur else o.port}, {o.cycles} cycle(s)")
    try:
        detail, cycles = seance(Modem(transport, journal, horloge), o, dormir, horloge)
    finally:
        transport.fermer()
    print(f"\nDémarrage : {detail}")
    for cy in cycles:
        etat = "OK " if cy.ok else "ÉCHEC"
        print(f"  {etat} cycle {cy.numero} ({cy.debut}) : {cy.total} s"
              + (" après remise à zéro" if cy.reprise else "")
              + (f", échec à « {cy.etape_echec} » ({cy.erreur})" if not cy.ok else "")
              + (", commandes " + ", ".join(t.rsplit("/", 1)[-1] + "=" + m for t, m in cy.recus) if cy.recus else ""))
    reussis = [cy for cy in cycles if cy.ok]
    if reussis:
        print(f"\n{len(reussis)}/{o.cycles} cycles réussis, durée moyenne {sum(c.total for c in reussis) / len(reussis):.1f} s")
    releve = Path(o.journaux) / "releve_cycles.csv"
    ajouter_releve(releve, cycles)
    print(f"Journal : {journal.chemin}\nRelevé : {releve}")
    journal.fermer()
    return 0 if cycles and len(reussis) == o.cycles else 1


if __name__ == "__main__":
    sys.exit(main())
