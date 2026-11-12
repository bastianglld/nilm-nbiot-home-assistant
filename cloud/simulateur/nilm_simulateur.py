"""Simulateur de la carte NILM / NB-IoT.

Permet de tester toute la chaîne (broker, pont, Home Assistant, dashboard)
sans le matériel :
  1. publie les configs MQTT Discovery du dossier homeassistant/mqtt-discovery
     (avec retain) : Home Assistant crée tout seul les capteurs et les relais ;
  2. annonce la carte en ligne sur nilm/maison/dispo ;
  3. publie un message de mesure toutes les N secondes sur nilm/maison/etat,
     au format de docs/protocole_messages.md :
       hhmm;frigo;bouilloire;lave_linge;lave_vaisselle;total   (Wh du quart d'heure)

Pour une démonstration rapide, chaque message avance l'horloge simulée de
15 minutes : une journée entière défile en 96 messages.

Exemples :
  # broker du VPS, chiffré (TLS, port 8883)
  python nilm_simulateur.py --broker mon-broker.exemple.com --tls --user simulateur
  # broker local de Home Assistant, sur le réseau de la maison
  python nilm_simulateur.py --broker IP_DE_HOME_ASSISTANT --user UTILISATEUR_MQTT

Le mot de passe est lu dans la variable d'environnement MQTT_PASSWORD
(ou dans --password), pour ne jamais l'écrire dans un fichier versionné.
"""
import argparse
import json
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

TOPIC_ETAT = "nilm/maison/etat"
TOPIC_DISPO = "nilm/maison/dispo"
DECOUVERTE = Path(__file__).resolve().parents[2] / "homeassistant" / "mqtt-discovery"
RETARD_NILM = timedelta(minutes=130)  # chaque message décrit le quart d'heure d'il y a ~2 h 10

# Ordre des champs du message, puis (puissance en marche en W, probabilité d'être en marche)
APPAREILS = {
    "frigo": (92, 0.6),
    "bouilloire": (2380, 0.1),
    "lave_linge": (2000, 0.15),
    "lave_vaisselle": (1800, 0.15),
}
FOND_W = (300, 1000)  # consommation non attribuée (veilles, éclairage, chauffage...)


def quart_d_heure(t: datetime) -> datetime:
    return t.replace(minute=t.minute - t.minute % 15, second=0, microsecond=0)


def mesure(t: datetime) -> str:
    """Message montant de la carte pour le quart d'heure qui commence à t."""
    wh = []
    for puissance, proba_marche in APPAREILS.values():
        en_marche = random.random() < proba_marche
        # en marche une partie du quart d'heure : énergie = P x durée (0,25 h)
        wh.append(round(puissance * random.uniform(0.3, 1.0) * 0.25) if en_marche else 0)
    total = sum(wh) + round(random.uniform(*FOND_W) * 0.25)
    return ";".join([t.strftime("%H%M"), *map(str, wh), str(total)])


def composant(cfg: dict) -> str:
    """Type d'entité Home Assistant d'après le contenu de la config."""
    if "command_topic" in cfg:
        return "switch"
    if "payload_on" in cfg:
        return "binary_sensor"
    return "sensor"


def configs_decouverte():
    for fichier in sorted(DECOUVERTE.glob("*/*.json")):
        cfg = json.loads(fichier.read_text(encoding="utf-8"))
        yield f"homeassistant/{composant(cfg)}/{cfg['unique_id']}/config", cfg


def main():
    ap = argparse.ArgumentParser(description="Simule les messages de la carte NILM / NB-IoT")
    ap.add_argument("--broker", default="homeassistant.local", help="adresse du broker MQTT")
    ap.add_argument("--port", type=int, help="port (défaut : 1883, ou 8883 avec --tls)")
    ap.add_argument("--tls", action="store_true", help="connexion chiffrée (obligatoire vers le VPS)")
    ap.add_argument("--cafile", help="certificat de l'autorité, si ce n'est pas une autorité publique")
    ap.add_argument("--user")
    ap.add_argument("--password", default=os.environ.get("MQTT_PASSWORD"))
    ap.add_argument("--periode", type=float, default=10, help="secondes entre deux messages")
    ap.add_argument("--sans-decouverte", action="store_true", help="ne pas republier les configs")
    args = ap.parse_args()
    port = args.port or (8883 if args.tls else 1883)

    import paho.mqtt.client as mqtt  # importé ici : les tests n'ont pas besoin de paho

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="simulateur-nilm")
    if args.user:
        client.username_pw_set(args.user, args.password)
    if args.tls:
        client.tls_set(ca_certs=args.cafile)  # vérifie le certificat du serveur
    # Message de dernière volonté : le broker publie « offline » si le simulateur disparaît
    client.will_set(TOPIC_DISPO, "offline", qos=1, retain=True)
    client.connect(args.broker, port)
    client.loop_start()

    if not args.sans_decouverte:
        for topic, cfg in configs_decouverte():
            client.publish(topic, json.dumps(cfg, ensure_ascii=False), qos=1, retain=True)
        print("Configs de découverte publiées.")
    client.publish(TOPIC_DISPO, "online", qos=1, retain=True)

    t = quart_d_heure(datetime.now() - RETARD_NILM - timedelta(days=1))
    try:
        while True:
            msg = mesure(t)
            client.publish(TOPIC_ETAT, msg, qos=1)
            print(msg)
            t += timedelta(minutes=15)
            time.sleep(args.periode)
    except KeyboardInterrupt:
        client.publish(TOPIC_DISPO, "offline", qos=1, retain=True).wait_for_publish()
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
