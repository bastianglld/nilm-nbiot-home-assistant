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
- chaque minute, `piloter()` décide l'état des appareils ; à chaque changement, `commander_relais()` (sortie D8 et **LED rouge** pour le chauffe-eau) ou `commander_batterie()` (sortie D7), puis `publier("nilm/maison/cmd/chauffe_eau/etat", "ON")` ;
- `publier(topic, message)` : aujourd'hui une ligne `MQTT <topic> <message>` vers le PC, demain `AT#MQTTPUB`.

Sur le PC, la carte affiche aussi `RECU …`, `RELAIS hhmm appareil ON (plan|ordre|secours)` et `BATTERIE hhmm mode`.

## Sorties relais

Module utilisé : **Grove 2-Channel SPDT Relay** (Seeed, deux relais SRD-05VDC-SL-C), commandé par transistor, **actif à l'état haut** (3,3 V = relais collé), alimenté en **5 V** (environ 90 mA par bobine). Réglage `RELAIS_ACTIF_BAS` dans `appli_nilm.c` : 0 pour ce module (défaut), 1 pour un module optocouplé à cavalier JD-VCC (0 V = relais collé).

| Broche Arduino | Broche STM32 | Étiquette CubeMX | Module Grove | Rôle |
|---|---|---|---|---|
| D7 | PE11 | `RELAIS_BAT` | SIG1, relais 1 | +5 V USB de la batterie par COM1 et NO1 : collé seulement en mode **charge** |
| D8 | PD12 | `RELAIS_CE` | SIG2, relais 2 | chauffe-eau (la LED rouge le montre aussi) |
| 5V | – | – | VCC | alimentation des bobines |
| GND | – | – | GND | masse commune |

Dans CubeMX (`tic_test.ioc`) : les deux broches en **GPIO_Output**, attribuées au **FSBL** (*Pin Context Assignment*, sinon elles ne sont pas générées dans `main.h`), avec ces étiquettes et un niveau de départ **Low** pour le module Grove (relais au repos ; **High** pour un module actif à l'état bas), puis *Generate Code*. Au démarrage, la carte remet les deux relais au repos ; ils ne bougent qu'une fois l'heure connue. Tant que les étiquettes ne sont pas dans `main.h`, le programme compile sans les sorties : seules la LED et les lignes vers le PC montrent l'état.

Vérification sans le module : multimètre ou LED (avec sa résistance) entre la broche et la masse. Avec le module Grove : 3,3 V = relais collé, 0 V = repos.

## Essais

Sur PC (`python -m unittest tests.test_pilotage_c`) :

- calendrier de la carte comparé à Python sur 40 ans ;
- 300 plannings fabriqués par `ems_serveur.encoder_plan` décodés sans perte (chauffe-eau, batterie, couleur, départs) ; 10 plannings mal formés rejetés ;
- secours, planning du jour et du lendemain, ordre jusqu'au prochain changement, ordre répété ignoré, radiateur, topics ignorés ;
- programme complet de la carte compilé sur PC avec le flux du simulateur : planning reçu à 13 h 30, chauffe en secours à 22 h, passage au planning à minuit, ordre de Home Assistant, ordre répété, confirmations, et niveau des sorties D7 et D8 à chaque changement.

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

## Essai des sorties relais sur la carte (25 novembre 2026)

Programme `tic_test` régénéré avec PE11 (`RELAIS_BAT`) et PD12 (`RELAIS_CE`) en sortie, attribuées au FSBL (*Pin Context Assignment*), niveau de départ *High*. Sans module relais : multimètre entre la broche et GND.

| Essai (simulateur) | Ligne de la carte | D8 (chauffe-eau) | D7 (batterie) |
|---|---|---|---|
| Journée du 20 janvier 13 h au 21 janvier 11 h (commande ci-dessus, `--nb 1320`) | démarrage, `RELAIS 1300 chauffe_eau OFF (secours)` | 3,3 V | 3,3 V |
| | `RELAIS 1014 chauffe_eau ON (ordre)`, LED rouge allumée | 0 V | 3,3 V |
| Nuit du 20 au 21 janvier (`--debut "2026-01-20 23:50:00" --nb 160`, planning après la trame 3) | `BATTERIE 2350 repos` | 0 V (secours, heures creuses) | 3,3 V |
| | `BATTERIE 0000 charge` | 0 V | 0 V |
| | `RELAIS 0200 chauffe_eau OFF (plan)`, `BATTERIE 0200 repos` | 3,3 V | 3,3 V |

Conforme : 0 V = relais collé, 3,3 V = repos (essai fait avec `RELAIS_ACTIF_BAS` à 1, avant le choix du module Grove). Attention à bien attribuer les deux broches au FSBL dans CubeMX : une broche laissée « Free » n'est pas générée dans `main.h`.

Même jour, avec le module **Grove 2-Channel SPDT Relay** branché (GND, VCC sur 5V, SIG1 sur D7, SIG2 sur D8, borniers à vide), `RELAIS_ACTIF_BAS` à 0 et niveau de départ *Low* : sur l'essai de la nuit, le relais 2 colle avec le chauffe-eau, le relais 1 pendant `BATTERIE 0000 charge`, et les deux se relâchent à 2 h. Conforme.

Montage final : module relais branché sur un **Grove Base Shield** piqué sur le connecteur Arduino de la NUCLEO (interrupteur du shield sur 5V, câble dans la prise D7, qui sort D7 et D8). Essai conforme : planning reçu, relais 1 et 2 collés de 0 h à 2 h, relâchés à 2 h. Attention : après un redémarrage, la carte met une quinzaine de secondes à être prête ; un planning envoyé avant est perdu et la carte reste en secours. Pour l'essai de la nuit : `--debut "2026-01-20 23:00:00" --nb 200 --mqtt "50 nilm/maison/cmd/plan 2101;R;C00003;0002AAAAA005;22;22"`.

### Chauffe-eau de démonstration : LED externe sur le relais 2

Le chauffe-eau est représenté par une LED alimentée **à travers le contact du relais 2** (on voit ainsi que c'est bien le relais qui commute) :

```
5V du shield -> COM2 -> [relais 2] -> NO2 -> résistance 220 Ω -> LED (patte longue) ; LED (patte courte) -> GND
```

Rien sur NC2. Si la LED reste éteinte : vérifier la valeur de la résistance (220 Ω = rouge, rouge, marron ; une 22 kΩ, rouge, rouge, orange, éteint presque la LED) et que la résistance est bien sur NO2 (5 V seulement quand le relais est collé). Essai du 25 novembre conforme : la LED externe suit la LED rouge de la carte.
