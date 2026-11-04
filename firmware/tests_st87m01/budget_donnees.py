"""Budget de données de la SIM du kit ST87M01 (tâche B-45).

Estime les octets échangés par jour, au niveau IP (ce que l'opérateur facture, dans
les deux sens), pour plusieurs stratégies d'envoi des mesures MQTT, et les compare
au forfait de la SIM (50 Mo sur 6 mois).

Ce sont des ESTIMATIONS : tailles TLS et TCP typiques, chaque segment de données
compté avec un accusé de réception TCP séparé (majorant). Les vraies valeurs
seront mesurées sur le kit (tâche B-29) et remplaceront celles-ci.

    python budget_donnees.py
"""

import math

# -- forfait
FORFAIT_OCTETS = 50e6
DUREE_JOURS = 182.5
BUDGET_JOUR = FORFAIT_OCTETS / DUREE_JOURS

# -- TCP / IP (IPv4 sans option, TCP sans horodatage)
ENTETE_IP_TCP = 40
SYN = 44                      # en-tête + option MSS
ACK_PUR = 40


def segment(octets):
    """Un segment de données et l'accusé de réception qu'il provoque."""
    return octets + ENTETE_IP_TCP + ACK_PUR


TCP_OUVERTURE = 2 * SYN + ENTETE_IP_TCP      # SYN, SYN-ACK, ACK
TCP_FERMETURE = 4 * ENTETE_IP_TCP            # FIN, ACK, FIN, ACK

# -- TLS 1.2, ECDHE-ECDSA-AES128-GCM, broker authentifié par un seul certificat ECDSA,
#    appareil authentifié par identifiant et mot de passe MQTT (pas de certificat client)
TLS_ENREGISTREMENT = 5 + 8 + 16              # en-tête + IV explicite + tag GCM
TLS_COMPLET = segment(150) + segment(900) + segment(270) + segment(51)
TLS_REPRISE = segment(180) + segment(141) + segment(51)
TLS_CLOSE_NOTIFY = segment(2 + TLS_ENREGISTREMENT)

# -- MQTT 3.1.1 (format de docs/protocole_messages.md)
CLIENT, UTILISATEUR, MOT_DE_PASSE = "nilm_01", "nilm_01", "x" * 20
TOPIC_MESURE, MESURE = "maison/nilm_01/q", "1615;21;48;0;0;310"
TOPIC_PLAN, PLAN = "maison/nilm_01/plan", "2101;R;000003;0002AAAAA005;22;22"

CONNECT = 2 + 10 + sum(2 + len(c) for c in (CLIENT, UTILISATEUR, MOT_DE_PASSE))
CONNACK = 4
PUBLISH_MESURE = 2 + 2 + len(TOPIC_MESURE) + 2 + len(MESURE)        # QoS 1
SUBSCRIBE = 2 + 2 + 2 + len(TOPIC_PLAN) + 1
SUBACK = 5
PUBLISH_PLAN = 2 + 2 + len(TOPIC_PLAN) + 2 + len(PLAN)
PUBACK = 4
PINGREQ = PINGRESP = 2
DISCONNECT = 2


def paquet(octets, tls):
    return segment(octets + TLS_ENREGISTREMENT if tls else octets)


def envoi_mesure(tls=True):
    return paquet(PUBLISH_MESURE, tls) + paquet(PUBACK, tls)


def reception_plan(tls=True):
    return sum(paquet(p, tls) for p in (SUBSCRIBE, SUBACK, PUBLISH_PLAN, PUBACK))


def session(mesures, tls=True, reprise=False):
    """Ouvrir TCP (+ TLS), se connecter, publier, se déconnecter, fermer."""
    total = TCP_OUVERTURE + TCP_FERMETURE
    if tls:
        total += (TLS_REPRISE if reprise else TLS_COMPLET) + TLS_CLOSE_NOTIFY
    total += paquet(CONNECT, tls) + paquet(CONNACK, tls) + paquet(DISCONNECT, tls)
    return total + mesures * envoi_mesure(tls)


def par_jour_reconnexion(connexions, tls=True, reprise=False, mesures_jour=96):
    """Les 96 mesures du jour envoyées en `connexions` sessions ; planning reçu une fois."""
    return connexions * session(mesures_jour / connexions, tls, reprise) + reception_plan(tls)


def par_jour_connexion_gardee(keep_alive_s, intervalle_s=900, mesures_jour=96):
    """Une seule session TLS par jour ; un PINGREQ seulement si rien n'a été publié
    pendant `keep_alive_s` (chaque publication remet le compteur à zéro)."""
    pings = max(math.ceil(intervalle_s / keep_alive_s) - 1, 0)
    ping = paquet(PINGREQ, True) + paquet(PINGRESP, True)
    return session(0) + reception_plan() + mesures_jour * (envoi_mesure() + pings * ping)


def scenarios():
    return [
        ("A", "Reconnexion toutes les 15 min, TLS complet", par_jour_reconnexion(96)),
        ("B", "Reconnexion toutes les 15 min, reprise de session TLS", par_jour_reconnexion(96, reprise=True)),
        ("C", "1 connexion par heure (4 mesures), TLS complet", par_jour_reconnexion(24)),
        ("D", "1 connexion par heure, reprise de session TLS", par_jour_reconnexion(24, reprise=True)),
        ("E", "1 connexion toutes les 2 h (8 mesures), reprise TLS", par_jour_reconnexion(12, reprise=True)),
        ("F1", "Connexion gardée, keep-alive 60 s", par_jour_connexion_gardee(60)),
        ("F2", "Connexion gardée, keep-alive 300 s", par_jour_connexion_gardee(300)),
        ("F3", "Connexion gardée, keep-alive 1200 s", par_jour_connexion_gardee(1200)),
        ("Réf.", "Sans TLS (essais seulement), reconnexion toutes les 15 min", par_jour_reconnexion(96, tls=False)),
    ]


def main():
    print(f"Forfait : {FORFAIT_OCTETS / 1e6:.0f} Mo sur {DUREE_JOURS:.0f} jours, soit {BUDGET_JOUR / 1000:.0f} ko par jour")
    print(f"Une mesure dans une session TLS complète : {session(1)} o ; avec reprise : {session(1, reprise=True)} o ;"
          f" dans une connexion déjà ouverte : {envoi_mesure()} o (dont {PUBLISH_MESURE} o de MQTT)\n")
    print(f"{'':5}{'Stratégie':60}{'ko/jour':>9}{'forfait':>9}{'6 mois':>9}")
    for code, nom, octets in scenarios():
        print(f"{code:5}{nom:60}{octets / 1000:9.1f}{100 * octets / BUDGET_JOUR:8.0f} %{octets * DUREE_JOURS / 1e6:6.1f} Mo")


if __name__ == "__main__":
    main()
