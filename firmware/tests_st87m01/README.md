# Tests du module ST87M01

Partie B (Merveil). Tout ce qu'il faut pour le premier jour du kit EVKITST87M01-2, branché au PC en USB.

| Fichier | Rôle |
|---|---|
| [`jour1_kit.md`](jour1_kit.md) | La procédure pas à pas : montage, commandes AT, réponses attendues, problèmes fréquents |
| [`test_jour1.py`](test_jour1.py) | La même procédure, automatisée : envoie les commandes, vérifie les réponses, écrit le journal et la fiche de relevé |
| [`faux_st87m01.py`](faux_st87m01.py) | Un faux module qui répond comme le ST87M01, pour essayer le script sans le kit |

Tests automatiques : [`../../tests/test_jour1_st87m01.py`](../../tests/test_jour1_st87m01.py) (lancés par l'intégration continue).

## Installation

```bash
pip install pyserial        # seulement pour un vrai port série
```

Sous Windows, installer aussi le pilote du CP2105 (Silicon Labs) et choisir le **Standard COM Port** (manuel de la carte, § 8.2). Avant de lancer le script, fermer la console de la GUI de ST : un port série ne s'ouvre qu'une fois.

## Utilisation

```bash
# sans le kit : vérifier que tout tourne, avec le faux module
python test_jour1.py --simulateur

# avec le kit : dialogue, SIM, attache, signal et ping
python test_jour1.py --port COM5 --lieu "près de la fenêtre"

# même chose au tableau électrique, sans ping (pour économiser les données)
python test_jour1.py --port COM5 --lieu "tableau électrique" --sans-ping

# avec le broker : premier message MQTT, puis attente du planning (60 s)
set ST87M01_MQTT_MDP=…                     # Windows ; export ST87M01_MQTT_MDP=… sous Linux / macOS
python test_jour1.py --port COM5 --broker <adresse IP> --utilisateur nilm_01
```

`python test_jour1.py -h` liste toutes les options (délai d'attache, keep-alive, topics, `--eteindre` pour finir par `AT#PWROFF`…).

## Ce que le script produit

- un **journal** horodaté de chaque commande et réponse : `journaux/seance_<date>.log` ;
- une ligne dans la **fiche de relevé** `journaux/fiche_releve.csv` : date, lieu, firmware, état `+CEREG`, réseau, APN, temps d'attache, RSRP, RSRQ, ping, MQTT ;
- un **bilan** à l'écran, étape par étape, et un code de sortie 0 si tout a réussi.

L'IMSI, l'ICCID, l'IMEI et le mot de passe MQTT sont masqués dans le journal. Le dossier `journaux/` est ignoré par Git : relire un journal avant de le partager.

## Ce que le script vérifie

| Étape | Commandes | Réussite |
|---|---|---|
| 2 Dialogue | `AT`, `AT+CMEE=2`, `ATI`, `AT+CGMR`, `AT#SLEEPMODE?` | `OK` ; signale si la mise en veille est active |
| 3 SIM | `AT#SIMST?`, `AT+CPIN?` | `#SIMST: 1` et `READY` ; sinon le script s'arrête |
| 4 Attache | `AT#BANDSEL?`, `AT+CFUN?`, `AT+CEREG?` toutes les 10 s, `AT+COPS?`, `AT+CGCONTRDP=5`, `AT+CGPADDR=5`, `AT#IPCFG?`, `AT#IPPING=5,8.8.8.8` | `+CEREG` à 1 ou 5 en moins de 300 s, une adresse IP ; arrêt immédiat si l'enregistrement est refusé (3) |
| 5 Signal | `AT+CESQ` | RSRP en dBm = valeur − 141 ; RSRQ en dB = valeur / 2 − 20 |
| 6 MQTT | `AT#DNS` (si nom), `AT#MQTTCFG`, `AT#SOCKETCREATE=5,…`, `AT#MQTTCONNECT=5,…`, `AT#MQTTPUB`, `AT#MQTTSUB`, `AT#MQTTDISC`, `AT#SOCKETCLOSE` | Limites du module respectées (topic et message ≤ 50, client et utilisateur ≤ 25, mot de passe ≤ 50), publication acceptée, planning reçu (`#MQTTRECV`) |
