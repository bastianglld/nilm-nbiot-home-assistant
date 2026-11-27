# Tests du module ST87M01

Partie B (Merveil). Tout ce qu'il faut pour tester le kit EVKITST87M01-2 branché au PC en USB : la procédure du premier jour, puis le cycle d'échange avec le broker validé le 26 novembre 2026.

| Fichier | Rôle |
|---|---|
| [`jour1_kit.md`](jour1_kit.md) | La procédure pas à pas : montage, commandes AT, réponses attendues, problèmes fréquents |
| [`test_jour1.py`](test_jour1.py) | La même procédure, automatisée : envoie les commandes, vérifie les réponses, écrit le journal et la fiche de relevé |
| [`cycle_st87m01.py`](cycle_st87m01.py) | Le cycle d'échange validé sur le kit (connexion, mesure, commandes, confirmation, déconnexion), répété à intervalle fixe : base du pilote de la carte STM32 et mesure de la durée et du volume d'un cycle |
| [`certificat_at.py`](certificat_at.py) | Écrit la commande `AT#TLSCERTADD` qui charge le certificat racine du broker dans le module (TLS, port 8883), après avoir vérifié qu'il est en ECDSA |
| [`faux_st87m01.py`](faux_st87m01.py) | Un faux module qui répond comme le ST87M01, pour essayer le script sans le kit |
| [`budget_donnees.py`](budget_donnees.py) | Estimation des données consommées par jour selon la stratégie d'envoi, comparée au forfait de la SIM (résultats : [`docs/budget_donnees_sim.md`](../../docs/budget_donnees_sim.md)) |

Tests automatiques : [`../../tests/test_jour1_st87m01.py`](../../tests/test_jour1_st87m01.py) et [`../../tests/test_cycle_st87m01.py`](../../tests/test_cycle_st87m01.py) (lancés par l'intégration continue).

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
| 2 Dialogue | `AT` (jusqu'à 4 essais : le premier ne fait souvent que réveiller le module), `AT+CMEE=2`, `ATI`, `AT+CGMR`, `AT#SLEEPMODE?`, `AT#SLEEPMODE=0` | `OK` ; la mise en veille est désactivée pour la séance (sauf `--garder-veille`) |
| 3 SIM | `AT#SIMST?`, `AT+CPIN?` | `#SIMST: 1` et `READY` ; sinon le script s'arrête |
| 4 Attache | `AT#BANDSEL?`, `AT+CFUN?`, `AT+CEREG?` toutes les 10 s, `AT+COPS?`, `AT+CGCONTRDP=5`, `AT+CGPADDR=5`, `AT#IPCFG?`, `AT#IPPING=5,8.8.8.8,120,10,3` | `+CEREG` à 1 ou 5 en moins de 300 s, une adresse IP, au moins une réponse au ping (2ᵉ champ de `#IPPING`) ; arrêt immédiat si l'enregistrement est refusé (3) |
| 5 Signal | `AT+CESQ` | RSRP en dBm = valeur − 141 ; RSRQ en dB = valeur / 2 − 20 |
| 6 MQTT | `AT#DNS` (si nom), `AT#MQTTCFG`, `AT#SOCKETCREATE=5,…`, `AT#MQTTCONNECT=5,…`, `AT#MQTTPUB`, `AT#MQTTSUB`, `AT#MQTTDISC`, `AT#SOCKETCLOSE` | Limites du module respectées (topic et message ≤ 50, client et utilisateur ≤ 25, mot de passe ≤ 50), publication acceptée, planning reçu (`#MQTTRECV`) |

## Le cycle d'échange (`cycle_st87m01.py`)

Le module ne garde pas une connexion MQTT ouverte : sans keep-alive, elle meurt en silence ; avec un keep-alive, le module n'envoie pas son PINGREQ et le broker coupe (essais du 25 novembre). Le boîtier fonctionne donc par **cycles** : il se connecte, échange, se déconnecte et se rendort. Fréquence retenue : **un cycle toutes les 15 minutes**.

```bash
# sans le kit
python cycle_st87m01.py --simulateur --cycles 3

# mesure du volume d'un cycle : 10 cycles dans une seule session de données, puis lecture dans SIMPro le lendemain
python cycle_st87m01.py --port COM4 --broker <adresse IP> --utilisateur <compte> --demander-mdp --cycles 10 --nouvelle-session --fermer-session

# fonctionnement réel : un cycle toutes les 15 minutes pendant 2 heures
python cycle_st87m01.py --port COM4 --broker <adresse IP> --utilisateur <compte> --demander-mdp --cycles 8 --intervalle 900
```

| Étape | Commande | Remarque |
|---|---|---|
| Démarrage | `AT` (jusqu'à 4 fois), `AT#SLEEPMODE=0`, `AT+CGDCONT?` | L'APN doit être `eapn1.net` en `IP` : il s'est effacé une fois (25 nov). `--corriger-apn` le réécrit |
| Connexion de données | `AT+CEREG?`, `AT+CGPADDR=5` ; sinon `AT+CFUN=0`, `AT+CFUN=1` et attente de `#IPCFG: 5,0,1` | Entre deux cycles, le module reste attaché et garde son adresse : pas de `AT+CFUN` (gain de 39 s) |
| 1 Configuration | `AT#MQTTCFG=nilm_01,60,60,3,120` | Dernier champ : keep-alive (0 le désactive) |
| 2 Socket | `AT#SOCKETCREATE=5,0,TCP,,60,60` | Numéro de socket lu dans la réponse |
| 3 Connexion | `AT#MQTTCONNECT=5,<socket>,<broker>,1883,<compte>,<mot de passe>` | |
| 4 Mesure | `AT#MQTTPUB=nilm/maison/etat,"<message>",3,1,0` | **Guillemets** obligatoires (le `;` sépare deux commandes AT). Paramètres : topic, message, essais, QoS, retain |
| 5 Commandes | `AT#MQTTSUB=nilm/maison/cmd/plan,1,nilm/maison/cmd/chauffe_eau,1`, puis lecture des `#MQTTRECV` pendant 10 s | **Topics exacts** : avec le joker `+`, le module acquitte (PUBACK) sans afficher le message. Les ordres sont gardés par le broker (*retain*) et arrivent au cycle suivant |
| 6 Confirmation | `AT#MQTTPUB=nilm/maison/cmd/chauffe_eau/etat,"ON",3,1,0` | État réel du relais, affiché par Home Assistant |
| 7 Déconnexion | `AT#MQTTDISC` | Ferme aussi la socket (`AT#SOCKETCLOSE` répondrait 2104) |
| En cas d'erreur | `AT#RESET=1`, puis nouvelle connexion de données et nouvel essai du cycle | Après 2215, 2218, 2220 ou `#TCPSENDFAIL`, seule une remise à zéro débloque la pile MQTT. Jamais `AT#RESET=0` (ne sauvegarde pas la configuration) |

Produit : un journal `journaux/cycles_<date>.log` et une ligne par cycle dans `journaux/releve_cycles.csv` (durée de chaque étape, commandes reçues, confirmations). Durées mesurées à la main le 26 novembre : connexion 1,9 s, mesure 4,3 s, commandes 3,3 s, confirmation 2,7 s, déconnexion 2,1 s, soit environ 14 s de module par cycle.

## Passer en TLS (port 8883)

Le module vérifie le certificat du broker avec un certificat racine chargé une fois pour toutes dans son stockage sécurisé (note d'application ST87MXX_TLS). Seuls les certificats **ECDSA** sont acceptés, au format **DER**. Le broker utilise la chaîne Let's Encrypt ECDSA (vérifiée le 4 novembre : broker → YE2 → Root YE → ISRG Root X2) : charger **ISRG Root YE** ([DER](https://letsencrypt.org/certs/gen-y/root-ye.der)), ou à défaut **ISRG Root X2** ([DER](https://letsencrypt.org/certs/isrg-root-x2.der)) ; jamais ISRG Root X1 (RSA).

```bash
python certificat_at.py root-ye.der --sortie commande_certificat.txt   # écrit AT#TLSCERTADD=0,1,<longueur>,<hexadécimal>
```

Dans la console : coller la commande, attendre `OK`, puis `AT#RESET=1` pour l'enregistrer. Ensuite, à chaque cycle, seules deux commandes changent :

| Commande | Changement |
|---|---|
| `AT#SOCKETCREATE=5,0,TCP,,60,60,0,0,1` | 7ᵉ paramètre : pas de notification de réception ; 8ᵉ : profil de sécurité 0 ; 9ᵉ : reprise de session TLS (moins de données à chaque cycle) |
| `AT#MQTTCONNECT=5,<socket>,<broker>,8883,<compte>,<mot de passe>` | port 8883 |

À vérifier au premier essai : le certificat du broker porte son nom DNS, alors que le module se connecte par adresse IP.
