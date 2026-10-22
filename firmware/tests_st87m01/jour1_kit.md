# Premier jour du kit EVKITST87M01-2 : procédure de test

Responsable : Merveil (B). Objectif : vérifier que le module ST87M01 dialogue avec le PC, lit la SIM, s'attache au réseau NB-IoT, puis envoie un premier message MQTT. Chaque étape donne la commande, la réponse attendue et quoi faire si ça échoue. Les mesures à relever sont regroupées dans la [fiche de relevé](#fiche-de-relevé) en fin de document.

> **Sources des commandes.** Les commandes `AT+…` sont les commandes standard de la norme 3GPP TS 27.007, gérées par les modules NB-IoT. Les commandes `AT#…` sont propres à ST : `AT#RESET=1` et `AT#PWROFF` sont confirmées par ST sur son forum. **Tout doit être vérifié dans le manuel des commandes AT du ST87M01**, installé avec le logiciel STSW-ST87MGUI, en particulier les commandes MQTT, qui ne sont pas publiques et restent à recopier depuis ce manuel.

> **Données personnelles.** Ne jamais copier dans le dépôt l'IMSI, l'ICCID (numéro de la SIM), l'IMEI ni aucun identifiant ou mot de passe. Les noter sur papier ou dans un fichier local ignoré par Git.

## 0. Avant l'arrivée du kit

- [ ] Installer **STSW-ST87MGUI** sur le PC (Windows, sans droits administrateur). Il contient la console AT, le **manuel des commandes AT** et les notes d'application (démarrage, MQTT, TCP/UDP).
- [ ] À défaut, prévoir un terminal série (PuTTY, Tera Term, ou le moniteur série de STM32CubeIDE). Débit et format : **à lire dans le manuel du kit** (la GUI les règle elle-même).
- [ ] Repérer dans le manuel AT : la commande de version, les commandes MQTT (configuration, connexion, publication, abonnement) et la gestion des certificats TLS.
- [ ] Demander à Mathieu l'adresse et le port de test du broker Azure ; à défaut, prévoir un broker public de test pour un seul message sans donnée personnelle.

## 1. Montage

| Étape | Action | Attendu |
|---|---|---|
| 1.1 | **Visser l'antenne LTE** sur le connecteur SMA RF **avant toute mise sous tension**. L'antenne GNSS n'est pas utile pour ce test. | Antenne bien serrée |
| 1.2 | Insérer la **SIM nano** Wireless Logic dans son support, carte hors tension. | SIM en place |
| 1.3 | Brancher le câble **USB Micro-B** au PC. | Les LED d'activité s'allument |
| 1.4 | Ouvrir la GUI (ou le terminal) sur le port COM qui apparaît. | Le port est ouvert |

Si aucun port COM n'apparaît : changer de câble (certains ne transportent que l'alimentation), changer de port USB, regarder le gestionnaire de périphériques.

## 2. Dialogue avec le module

| Étape | Commande | Réponse attendue | Si ça échoue |
|---|---|---|---|
| 2.1 | `AT` | `OK` | Vérifier le port et le débit ; appuyer sur le bouton reset et attendre la fin du démarrage |
| 2.2 | `ATI` | Identification du module | — |
| 2.3 | `AT+CGMR` | Version du firmware | Noter la version : elle peut changer la syntaxe de certaines commandes |

## 3. Carte SIM

| Étape | Commande | Réponse attendue | Si ça échoue |
|---|---|---|---|
| 3.1 | `AT+CPIN?` | `+CPIN: READY` | `SIM not inserted` : SIM mal insérée. `SIM PIN` : SIM protégée par code (ne pas le deviner : demander à Wireless Logic) |
| 3.2 | `AT+CIMI` | Un IMSI (15 chiffres) | Le noter **hors du dépôt** |

## 4. Attache au réseau NB-IoT (étape critique)

| Étape | Commande | Réponse attendue | Si ça échoue |
|---|---|---|---|
| 4.1 | `AT+CFUN?` | `+CFUN: 1` (radio active) | Envoyer `AT+CFUN=1` |
| 4.2 | `AT+CEREG=2` | `OK` (active le détail de l'enregistrement) | — |
| 4.3 | `AT+CEREG?` à répéter toutes les 10 à 30 s | `+CEREG: 2,1,…` ou **`+CEREG: 2,5,…`** | Voir le tableau ci-dessous |
| 4.4 | `AT+COPS?` | Le réseau trouvé (nom ou code PLMN) | — |
| 4.5 | `AT+CGDCONT?` | Le contexte de données et son APN | Si l'APN est vide ou faux : demander l'APN à Wireless Logic, puis `AT+CFUN=0`, configurer, `AT#RESET=1` (redémarrage obligatoire après un changement, selon ST) |
| 4.6 | `AT+CGPADDR` | Une adresse IP | Pas d'adresse : contexte de données non actif, revoir l'APN |

**Lire le deuxième chiffre de `+CEREG`** (norme 3GPP) :

| Valeur | Sens | Action |
|---|---|---|
| 0 | Pas enregistré, ne cherche pas | `AT+CFUN=1`, vérifier la SIM |
| 1 | Enregistré sur le réseau de l'opérateur | ✅ |
| 2 | Recherche en cours | Attendre : la **première attache peut prendre plusieurs minutes** (balayage des bandes) |
| 3 | Enregistrement refusé | SIM non activée ou réseau non autorisé : contacter Wireless Logic |
| 5 | Enregistré en itinérance | ✅ Normal avec une SIM Wireless Logic, qui utilise les réseaux partenaires |

**Noter le temps d'attache** : de la mise sous tension jusqu'à la réponse 1 ou 5.

## 5. Qualité du signal

| Étape | Commande | Réponse attendue |
|---|---|---|
| 5.1 | `AT+CESQ` | `+CESQ: …,rsrq,rsrp` (les deux derniers nombres) |
| 5.2 | `AT+CSQ` | Indicateur simple, pour comparer |

**Conversion (norme 3GPP) :** RSRP en dBm = `rsrp` − 141 ; RSRQ en dB = `rsrq` / 2 − 20. Une valeur de 255 veut dire « inconnu ».

Ordres de grandeur pour la RSRP : au-dessus de −100 dBm, bon ; de −100 à −115 dBm, correct ; en dessous de −115 dBm, faible (le NB-IoT tient encore grâce à la répétition des messages, mais il consomme plus).

**Faire la mesure à trois endroits :** près d'une fenêtre, dans la pièce, puis **au tableau électrique** (ou dans un placard fermé, si le tableau n'est pas accessible). C'est le test de couverture demandé par le planning.

## 6. Premier message MQTT

Les commandes MQTT du ST87M01 sont propres à ST : **les recopier depuis le manuel AT** (chapitre MQTT, où figure aussi la limite de 50 caractères par message et par topic).

| Étape | Action | Commande (à compléter depuis le manuel) | Attendu |
|---|---|---|---|
| 6.1 | Configurer le broker : adresse, port 1883 (en clair, pour ce premier test seulement), identifiant client | `…` | `OK` |
| 6.2 | Se connecter au broker | `…` | Connexion acceptée |
| 6.3 | Publier sur `maison/nilm_01/q` le message `1615;21;48;0;0;310` | `…` | Le message apparaît chez Mathieu (`mosquitto_sub -t 'maison/nilm_01/#' -v`) |
| 6.4 | S'abonner à `maison/nilm_01/plan` ; Mathieu publie un planning de test | `…` | Le planning est reçu par le module |
| 6.5 | Se déconnecter proprement | `…` | `OK` |

Le passage en **TLS sur le port 8883** est l'étape suivante (planning : S5), avec le certificat fourni par Mathieu.

## 7. Arrêt propre

| Commande | Effet |
|---|---|
| `AT#PWROFF` | Détache le module du réseau et l'éteint proprement (orthographe à vérifier dans le manuel ; le forum ST écrit aussi `AT#poweroff`) |

Éviter de reconfigurer le module à chaque démarrage : les réglages sont gardés en mémoire, et la mémoire flash supporte un nombre limité d'écritures.

## Économiser les 50 Mo de la SIM

La SIM du kit donne **50 Mo de données sur 6 mois** (environ 280 ko par jour). Pendant les tests :
- ne pas laisser tourner de boucle d'envoi automatique ;
- préférer quelques messages courts à des connexions répétées : chaque connexion, surtout en TLS, coûte bien plus que le message lui-même ;
- noter chaque session de test dans la fiche de relevé pour suivre la consommation.

## Problèmes fréquents

| Symptôme | Causes probables | Que faire |
|---|---|---|
| Aucune réponse à `AT` | Mauvais port, mauvais débit, module en démarrage | Changer de port, vérifier le débit dans le manuel, reset puis attendre |
| `+CPIN` ne répond pas `READY` | SIM mal insérée ou protégée | Réinsérer la SIM hors tension ; contacter Wireless Logic |
| `+CEREG` reste à 2 | Pas de couverture, première recherche longue, mauvaise bande | Attendre quelques minutes ; près d'une fenêtre ; vérifier l'antenne |
| `+CEREG` à 3 | SIM non activée ou refusée | Contacter Wireless Logic (plateforme de gestion de la SIM) |
| Enregistré mais pas d'adresse IP | APN absent ou faux | Configurer l'APN, puis `AT#RESET=1` |
| Connexion MQTT refusée | Adresse ou port du broker, pare-feu Azure, identifiants | Vérifier avec Mathieu que le port est ouvert et le compte créé |

## Fiche de relevé

À remplir pendant les tests (sans IMSI, ICCID ni IMEI). Ces mesures iront dans le rapport de période.

| Date | Lieu | Firmware | `+CEREG` | Réseau (`+COPS`) | Temps d'attache | RSRP (dBm) | RSRQ (dB) | MQTT reçu ? | Remarques |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |
| | | | | | | | | | |
| | | | | | | | | | |
