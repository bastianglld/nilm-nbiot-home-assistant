# Pilotage des appareils flexibles par la carte (partie C)

La carte reçoit le planning de l'EMS et les ordres de Home Assistant sur `nilm/maison/cmd/+` ([`../../docs/protocole_messages.md`](../../docs/protocole_messages.md)), décide chaque minute de l'état des relais et du mode de la batterie, et confirme chaque changement sur `nilm/maison/cmd/<appareil>/etat`.

| Fichier | Rôle |
|---|---|
| [`pilotage.h`](pilotage.h), [`pilotage.c`](pilotage.c) | Décodage du planning (32 caractères), ordres ON/OFF, secours, décision minute par minute. Portable, sans HAL |
| [`test_pc.c`](test_pc.c) | Accès depuis Python pour les tests ([`../../tests/test_pilotage_c.py`](../../tests/test_pilotage_c.py)) |
| [`essai_appli_pc.c`](essai_appli_pc.c), [`essai_pc/main.h`](essai_pc/main.h) | Le programme complet de la carte (`appli_nilm.c`) compilé sur PC, alimenté par le simulateur |

## Règles

Dans l'ordre :

1. **Ordre de Home Assistant** (`ON` / `OFF` sur `nilm/maison/cmd/chauffe_eau`) : appliqué tout de suite, **jusqu'au prochain changement prévu** par le planning (ou le secours), puis le planning reprend la main. Un ordre identique au précédent est ignoré : c'est le message *retain* renvoyé par le broker à chaque connexion de la carte, il ne doit pas recouper la chauffe tous les jours.
2. **Planning du jour** (`nilm/maison/cmd/plan`) : chauffe-eau selon le bit de l'heure, batterie selon ses 2 bits (repos, charge, décharge). Le planning arrive la veille vers 13 h 30 : la carte garde celui du jour et celui du lendemain.
3. **Secours** si aucun planning n'est arrivé pour ce jour : chauffe-eau en heures creuses (22 h à 6 h, comme l'EMS), batterie au repos.

Le radiateur (`chauffage`, présent dans Home Assistant) n'a pas de planning : il suit le dernier ordre, autorisé par défaut. Un planning mal formé est rejeté et ne change rien ; `batterie` et les autres noms d'appareils sont ignorés pour l'instant.

L'heure est celle du NILM (minute depuis le 1er janvier 2000) : donnée par la TIC aujourd'hui, par le réseau NB-IoT plus tard. Sans heure connue, la carte ne pilote rien.

## Dans le programme de la carte

`appli_nilm.c` :

- `appli_message_recu(topic, message)` : **point d'entrée pour le pilote du ST87M01** (partie B), à appeler pour chaque message reçu sur `nilm/maison/cmd/+` ;
- chaque minute, `piloter()` décide l'état des appareils ; à chaque changement, `commander_relais()` (aujourd'hui la **LED rouge** pour le chauffe-eau, demain la sortie du relais) et `publier("nilm/maison/cmd/chauffe_eau/etat", "ON")` ;
- `publier(topic, message)` : aujourd'hui une ligne `MQTT <topic> <message>` vers le PC, demain `AT#MQTTPUB`.

Sur le PC, la carte affiche aussi `RECU …`, `RELAIS hhmm appareil ON (plan|ordre|secours)` et `BATTERIE hhmm mode`.

## Essais

Sur PC (`python -m unittest tests.test_pilotage_c`) :

- calendrier de la carte comparé à Python sur 40 ans ;
- 300 plannings fabriqués par `ems_serveur.encoder_plan` décodés sans perte (chauffe-eau, batterie, couleur, départs) ; 10 plannings mal formés rejetés ;
- secours, planning du jour et du lendemain, ordre jusqu'au prochain changement, ordre répété ignoré, radiateur, topics ignorés ;
- programme complet de la carte compilé sur PC avec le flux du simulateur : planning reçu à 13 h 30, chauffe en secours à 22 h, passage au planning à minuit, ordre de Home Assistant, ordre répété, confirmations.

Sur la carte, avec le simulateur (`--mqtt "N topic message"` envoie un message MQTT simulé après la trame N) :

```bash
python simulateur_tic.py envoyer --port /dev/tty.usbmodem102 --8n1 --retour --puissance 800 \
    --debut "2026-01-20 12:00:00" --accel 60 --nb 1800 \
    --mqtt "90 nilm/maison/cmd/plan 2101;R;C00003;0002AAAAA005;22;22" \
    --mqtt "1335 nilm/maison/cmd/chauffe_eau ON" --mqtt "1500 nilm/maison/cmd/chauffage OFF"
```

La LED rouge suit le chauffe-eau : allumée de 22 h à 2 h, éteinte ensuite, rallumée par l'ordre de 10 h 15.

## Essai sur la carte (12 novembre 2026)

Programme complet `tic_test` (NILM sur le NPU), simulateur à 2 trames par seconde, une minute simulée par trame (du 20 janvier 13 h au 21 janvier 11 h en 11 minutes), commande ci-dessus avec `--debut "2026-01-20 13:00:00" --periode 0.5 --accel 120 --nb 1320`, planning après la trame 30, ordre `ON` du chauffe-eau après la trame 1275, ordre `OFF` du radiateur après la trame 1290.

| Heure simulée | Attendu | Carte | LED rouge |
|---|---|---|---|
| 13:00 | secours : chauffe-eau coupé, radiateur autorisé, batterie au repos | `RELAIS 1300 chauffe_eau OFF (secours)`, `chauffage ON`, `BATTERIE repos` + confirmations | éteinte |
| 13:30 | planning du 21 reçu, gardé pour le lendemain | `RECU nilm/maison/cmd/plan : planning ok` | éteinte |
| 22:00 | secours, heures creuses | `RELAIS 2200 chauffe_eau ON (secours)` | allumée |
| 00:00 | planning du 21 : chauffe 0 h - 2 h, batterie en charge | `BATTERIE 0000 charge` | allumée |
| 02:00 | fin de chauffe du planning | `RELAIS 0200 chauffe_eau OFF (plan)`, `BATTERIE 0200 repos` | éteinte |
| 06:00 | décharge de 6 h à 17 h | `BATTERIE 0600 decharge` | éteinte |
| 10:14 | ordre ON de Home Assistant | `ordre ok`, `RELAIS 1014 chauffe_eau ON (ordre)` | allumée |
| 10:29 | ordre OFF du radiateur | `ordre ok`, `RELAIS 1029 chauffage OFF (ordre)` | - |

Tout est conforme, et le NILM continue en parallèle (6,0 ms par calcul, un message par quart d'heure, total de 200 Wh pour 800 VA). Avec une puissance constante, irréaliste pour une maison, le modèle attribue par moments 50 à 80 Wh au lave-linge : cet essai ne vérifie que le pilotage.
