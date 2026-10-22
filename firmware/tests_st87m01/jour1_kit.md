# Premier jour du kit EVKITST87M01-2 : procédure de test

Responsable : Merveil (B). Objectif : vérifier que le module ST87M01 dialogue avec le PC, lit la SIM, s'attache au réseau NB-IoT, puis envoie un premier message MQTT. Chaque étape donne la commande, la réponse attendue et quoi faire si ça échoue. Les mesures à relever sont regroupées dans la [fiche de relevé](#fiche-de-relevé) en fin de document.

> **Source des commandes.** Manuel *ST87M01 AT commands description* (ST87MXX_UM_AT, rév. 0.3), installé avec le logiciel STSW-ST87MGUI. Les commandes `AT+…` suivent les normes 3GPP TS 27.005 / 27.007 ; les commandes `AT#…` sont propres à ST. Les exemples complets sont dans les notes d'application installées avec la GUI : **ST87MXX_Startup**, **ST87MXX_MQTT** et **ST87MXX_TLS**. Les points encore à confirmer dans ces notes sont signalés par ⚠️.

> **Données personnelles.** Ne jamais copier dans le dépôt l'IMSI, l'ICCID (numéro de la SIM), l'IMEI ni aucun identifiant ou mot de passe. Les noter sur papier ou dans un fichier local ignoré par Git.

## 0. Avant l'arrivée du kit

- [ ] Installer **STSW-ST87MGUI** sur le PC (Windows, sans droits administrateur). Il contient la console AT, le **manuel des commandes AT** et les notes d'application (démarrage, MQTT, TCP/UDP).
- [ ] À défaut, prévoir un terminal série (PuTTY, Tera Term, ou le moniteur série de STM32CubeIDE) réglé à **115 200 bauds** (débit par défaut du module, commande `AT+IPR`), 8 bits, sans parité, 1 bit de stop ⚠️ (format à confirmer dans le manuel du kit). Fin de ligne : retour chariot (`<CR>`).
- [ ] Lire la note d'application **ST87MXX_MQTT** : elle donne la séquence complète d'exemple, en particulier les valeurs de délai de `AT#SOCKETCREATE`.
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
| 2.2 | `AT+CMEE=2` | `OK` | Active les messages d'erreur détaillés (`+CME ERROR: …`), bien plus parlants qu'un simple `ERROR` |
| 2.3 | `ATI` | Identification du module | — |
| 2.4 | `AT+CGMR` | Version du firmware | Noter la version : elle peut changer la syntaxe de certaines commandes |

Au démarrage, le module annonce `#SYSSTART` (après une mise sous tension) ou `#REBOOT_RESET` / `#REBOOT_HOST` (après un reset). Attendre ce message avant d'envoyer des commandes.

## 3. Carte SIM

| Étape | Commande | Réponse attendue | Si ça échoue |
|---|---|---|---|
| 3.1 | `AT#SIMST?` | `#SIMST: 1` (SIM valide) | `#SIMST: 0` : SIM mal insérée ou invalide ; la réinsérer **hors tension** |
| 3.2 | `AT+CPIN?` | `+CPIN: READY` | `SIM PIN` : SIM protégée par code (ne pas le deviner : demander à Wireless Logic) |
| 3.3 | `AT+ICCID` et `AT+CIMI` | Le numéro de la SIM et l'IMSI | Utiles pour la plateforme Wireless Logic : les noter **hors du dépôt** |

## 4. Attache au réseau NB-IoT (étape critique)

| Étape | Commande | Réponse attendue | Si ça échoue |
|---|---|---|---|
| 4.1 | `AT+CFUN?` | `+CFUN: 1` (radio active) | Envoyer `AT+CFUN=1` |
| 4.2 | `AT+CEREG=2` | `OK` (active le détail de l'enregistrement) | — |
| 4.3 | `AT+CEREG?` à répéter toutes les 10 à 30 s | `+CEREG: 2,1,…` ou **`+CEREG: 2,5,…`** | Voir le tableau ci-dessous |
| 4.4 | `AT+COPS?` | Le réseau trouvé (nom ou code PLMN) | — |
| 4.5 | `AT+CGDCONT?` | Le contexte de données **0** (créé automatiquement au démarrage) et son APN | Si l'APN est vide ou faux : demander l'APN à Wireless Logic, puis `AT+CFUN=0`, configurer avec `AT+CGDCONT`, `AT#RESET=1` (sauvegarde et redémarrage) |
| 4.6 | `AT+CGPADDR` | Une adresse IP | Pas d'adresse : contexte de données non actif, revoir l'APN |
| 4.7 | Attendre le message `#IPCFG: 0,0,1`, ou lire `AT#IPCFG?` | Pile IPv4 active sur le contexte 0 | Si la pile IP reste inactive : `AT#IPCFG=0,0,"<adresse lue en 4.6>"` (configuration manuelle) |

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

**Conversion (vérifiée dans le manuel) :** RSRP en dBm ≈ `rsrp` − 141 (0 = moins de −140 dBm, 97 = au moins −44 dBm) ; RSRQ en dB ≈ `rsrq` / 2 − 20 (0 = moins de −19,5 dB, 34 = au moins −3 dB). Une valeur de 255 veut dire « inconnu ». Pour plus de détails radio : `AT#STENG` (mesures d'ingénierie).

Ordres de grandeur pour la RSRP : au-dessus de −100 dBm, bon ; de −100 à −115 dBm, correct ; en dessous de −115 dBm, faible (le NB-IoT tient encore grâce à la répétition des messages, mais il consomme plus).

**Faire la mesure à trois endroits :** près d'une fenêtre, dans la pièce, puis **au tableau électrique** (ou dans un placard fermé, si le tableau n'est pas accessible). C'est le test de couverture demandé par le planning.

## 6. Premier message MQTT

D'après le manuel, la connexion MQTT passe par une **socket TCP** créée sur le contexte 0. Le broker doit être donné par son **adresse IP** (pas par son nom) : si Mathieu donne un nom DNS, le résoudre d'abord avec `AT#DNS`.

| Étape | Commande | Attendu | Remarques |
|---|---|---|---|
| 6.1 | `AT#DNS=0,0,"<nom du broker>"` | `#DNS: <adresse IP>,<durée de validité>` | Seulement si le broker a un nom. Le serveur DNS se règle avec `AT#IPPARAMS` (réseau ou mémoire) |
| 6.2 | `AT#MQTTCFG="nilm_01",,,,0` | `OK` | Nom du client (25 caractères au plus). Le dernier champ est le **keep-alive** : 120 s par défaut, ce qui réveille le module toutes les 2 min. Pour les tests, 0 (désactivé) ; à régler ensuite avec la mise en veille |
| 6.3 | `AT#SOCKETCREATE=0,0,"TCP",,30,30` | `#SOCKETCREATE: 0` (numéro de la socket) | Contexte 0, IPv4, TCP, port local libre. ⚠️ Les deux délais (30, 30) sont des valeurs d'essai : prendre celles de la note MQTT. Au plus 3 sockets (1 TCP et 2 UDP) |
| 6.4 | `AT#MQTTCONNECT=0,0,"<adresse IP>",1883,"<utilisateur>","<mot de passe>"` | `OK` | Contexte 0, socket 0, port 1883 en clair pour ce premier test seulement. `AT#MQTTCONNECT` reçoit lui-même l'adresse du broker : a priori pas besoin de `AT#TCPCONNECT` avant ⚠️ (à confirmer dans la note MQTT). Utilisateur : 25 caractères au plus ; mot de passe : 50 au plus. Vérifier avec `AT#MQTTCONNECT?` → `#MQTTCONNECT: 1,…` |
| 6.5 | `AT#MQTTPUB="maison/nilm_01/q","1615;21;48;0;0;310",3,1,0` | `OK` | Topic et message : **50 caractères au plus chacun**. 3 essais, QoS 1, sans *retain*. Mathieu vérifie : `mosquitto_sub -t 'maison/nilm_01/#' -v` |
| 6.6 | `AT#MQTTSUB="maison/nilm_01/plan",1` | `OK` | Mathieu publie un planning de test |
| 6.7 | (attendre) | `#MQTTRECV: maison/nilm_01/plan, 2101;R;000003;0002AAAAA005;22;22` | Message reçu du broker |
| 6.8 | `AT#MQTTDISC` | `OK` | Déconnexion propre |
| 6.9 | `AT#SOCKETCLOSE=0,0` | `OK` | Ferme la socket (et le lien TCP s'il est encore ouvert) |

**Ensuite : TLS sur le port 8883** (planning : S5). D'après le manuel : charger le certificat de l'autorité du broker au format **DER** avec `AT#TLSCERTADD` dans un profil de sécurité, puis créer la socket avec ce profil (`AT#SOCKETCREATE=0,0,"TCP",,<délai>,<délai>,0,<profil>,1`). Le dernier paramètre active la **reprise de session TLS** (activée par défaut) : elle évite de refaire tout l'échange de certificats à chaque connexion, ce qui économise beaucoup de données. Détails : note d'application ST87MXX_TLS.

## 7. Arrêt propre

| Commande | Effet |
|---|---|
| `AT#PWROFF` | Détache le module du réseau, sauvegarde la configuration et l'éteint (`OK` puis `#SHUTDOWN`). Délai maximal de 300 s par défaut, réglable : `AT#PWROFF=30`. Pour le rallumer : bouton ou un caractère envoyé sur l'UART |
| `AT#RESET=1` | Redémarre le module en **sauvegardant** les réglages en mémoire (nécessaire après un changement de configuration) |

Éviter de reconfigurer le module à chaque démarrage : les réglages sont gardés en mémoire, et la mémoire flash supporte un nombre limité d'écritures.

## Ce que le manuel impose pour la suite

| Limite | Valeur | Conséquence pour le projet |
|---|---|---|
| Topic et message MQTT | 50 caractères au plus chacun | Le format de Bastian tient (16 à 19 et 18 à 32 caractères) |
| Nom du client, utilisateur | 25 caractères au plus | À dire à Mathieu pour la création des comptes |
| Mot de passe | 50 caractères au plus | Idem |
| Sockets | 1 TCP et 2 UDP au plus | Une seule connexion MQTT à la fois |
| Adresse du broker | Adresse IP | Résolution DNS avec `AT#DNS`, ou IP fixe côté Azure |
| Keep-alive MQTT | 120 s par défaut | À régler avec Mathieu pour ne pas empêcher la veille |
| Reprise de session TLS | Activée par défaut | Bonne nouvelle pour le budget de données |

## Économiser les 50 Mo de la SIM

La SIM du kit donne **50 Mo de données sur 6 mois** (environ 280 ko par jour). Pendant les tests :
- ne pas laisser tourner de boucle d'envoi automatique ;
- préférer quelques messages courts à des connexions répétées : chaque connexion, surtout en TLS, coûte bien plus que le message lui-même ;
- noter chaque session de test dans la fiche de relevé pour suivre la consommation.

## Problèmes fréquents

| Symptôme | Causes probables | Que faire |
|---|---|---|
| Aucune réponse à `AT` | Mauvais port, mauvais débit, module en démarrage | Changer de port, vérifier les 115 200 bauds, reset puis attendre `#SYSSTART` |
| `#SIMST: 0` ou `+CPIN` différent de `READY` | SIM mal insérée ou protégée | Réinsérer la SIM hors tension ; contacter Wireless Logic |
| `+CEREG` reste à 2 | Pas de couverture, première recherche longue, mauvaise bande | Attendre quelques minutes ; près d'une fenêtre ; vérifier l'antenne |
| `+CEREG` à 3 | SIM non activée ou refusée | Contacter Wireless Logic (plateforme de gestion de la SIM) |
| Enregistré mais pas d'adresse IP | APN absent ou faux | Configurer l'APN, puis `AT#RESET=1` |
| Connexion MQTT refusée | Nom au lieu d'une adresse IP, port fermé côté Azure, identifiants trop longs ou faux | Résoudre le nom avec `AT#DNS` ; vérifier avec Mathieu le port et le compte (25 / 50 caractères au plus) |
| `ERROR` sans détail | Erreurs détaillées non activées | `AT+CMEE=2`, puis chercher le code dans le chapitre « Error codes » du manuel |

## Fiche de relevé

À remplir pendant les tests (sans IMSI, ICCID ni IMEI). Ces mesures iront dans le rapport de période.

| Date | Lieu | Firmware | `+CEREG` | Réseau (`+COPS`) | Temps d'attache | RSRP (dBm) | RSRQ (dB) | MQTT reçu ? | Remarques |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |
| | | | | | | | | | |
| | | | | | | | | | |
