# Premier jour du kit EVKITST87M01-2 : procédure de test

Responsable : Merveil (B). Objectif : vérifier que le module ST87M01 dialogue avec le PC, lit la SIM, s'attache au réseau NB-IoT, puis envoie un premier message MQTT. Chaque étape donne la commande, la réponse attendue et quoi faire si ça échoue. Les mesures à relever sont regroupées dans la [fiche de relevé](#fiche-de-relevé) en fin de document.

> **Source des commandes.** Manuel *ST87M01 AT commands description* (ST87MXX_UM_AT, rév. 0.3), installé avec le logiciel STSW-ST87MGUI. Les commandes `AT+…` suivent les normes 3GPP TS 27.005 / 27.007 ; les commandes `AT#…` sont propres à ST. Vérifié avec les notes d'application **ST87MXX_MQTT**, **ST87MXX_TLS** et **ST87MXX_Startup** (v2.1). Les points encore à confirmer sont signalés par ⚠️.

> **Données personnelles.** Ne jamais copier dans le dépôt l'IMSI, l'ICCID (numéro de la SIM), l'IMEI ni aucun identifiant ou mot de passe. Les noter sur papier ou dans un fichier local ignoré par Git.

## 0. Avant l'arrivée du kit

- [ ] Installer **STSW-ST87MGUI** sur le PC (Windows, sans droits administrateur). Il contient la console AT, le **manuel des commandes AT** et les notes d'application (démarrage, MQTT, TCP/UDP).
- [ ] À défaut, prévoir un terminal série (PuTTY, Tera Term, ou le moniteur série de STM32CubeIDE) réglé à **115 200 bauds** (débit par défaut du module, commande `AT+IPR`), 8 bits, sans parité, 1 bit de stop ⚠️ (réglage courant ; ni le manuel ni les notes ne le précisent : le logiciel de ST le règle lui-même). Fin de ligne : retour chariot (`<CR>`).
- [ ] Demander à Mathieu l'adresse et le port de test du broker Azure ; à défaut, prévoir un broker public de test pour un seul message sans donnée personnelle.
- [ ] **SIM Wireless Logic** : vérifier sur leur plateforme de gestion que la SIM est **activée**, demander l'**APN** à utiliser et **confirmer que la SIM a une couverture NB-IoT en France** (et sur quel réseau). Sans ça, l'attache échouera quoi qu'on fasse.
- [ ] Dans la GUI de ST, vérifier s'il existe un **firmware plus récent** pour le module (panneau de mise à jour) et noter la version installée.
- [ ] Configurer le terminal pour **enregistrer toute la session dans un fichier journal** : c'est la preuve des tests pour le rapport (penser à y masquer IMSI, ICCID et IMEI avant de le partager).
- [ ] Documents encore à récupérer (installés avec la GUI) : le **manuel de la carte EVKITST87M01-2** (cavaliers, choix de l'alimentation, signification des LED) et la note **ST87MXX_TCP_UDP_IP** (configuration de la couche IP, à laquelle renvoie la note MQTT).

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

| Étape | Commande | Réponse attendue | Pourquoi |
|---|---|---|---|
| 2.5 | `AT#SLEEPMODE?` | `#SLEEPMODE: <0 ou 1>,…` | Si la mise en veille est active (1), le module peut s'endormir pendant les tests et ne plus répondre. Pour la séance : `AT#SLEEPMODE=0` puis `AT#RESET=1` (prend effet après le redémarrage). **La réactiver** pour les mesures de consommation (S5–S6) |

Si le module ne répond plus en cours de test : il dort probablement. Un caractère envoyé sur l'UART le réveille.

## 3. Carte SIM

| Étape | Commande | Réponse attendue | Si ça échoue |
|---|---|---|---|
| 3.1 | `AT#SIMST?` | `#SIMST: 1` (SIM valide) | `#SIMST: 0` : SIM mal insérée ou invalide ; la réinsérer **hors tension** |
| 3.2 | `AT+CPIN?` | `+CPIN: READY` | `SIM PIN` : SIM protégée par code (ne pas le deviner : demander à Wireless Logic) |
| 3.3 | `AT+ICCID` et `AT+CIMI` | Le numéro de la SIM et l'IMSI | Utiles pour la plateforme Wireless Logic : les noter **hors du dépôt** |

## 4. Attache au réseau NB-IoT (étape critique)

| Étape | Commande | Réponse attendue | Si ça échoue |
|---|---|---|---|
| 4.0 | `AT#BANDSEL?` | `#BANDSEL: …` avec au moins les bandes **8 et 20** (bandes NB-IoT européennes) | Comparer avec `AT#BANDSEL=?` ; ne modifier qu'en cas d'échec d'attache, après avoir demandé à Wireless Logic les bandes utilisées en France (changement pris en compte après `AT#RESET=1`) |
| 4.1 | `AT+CFUN?` | `+CFUN: 1` (radio active) | Envoyer `AT+CFUN=1` |
| 4.2 | `AT+CEREG=2` | `OK` (active le détail de l'enregistrement) | — |
| 4.3 | `AT+CEREG?` à répéter toutes les 10 à 30 s | `+CEREG: 2,1,…` ou **`+CEREG: 2,5,…`** | Voir le tableau ci-dessous |
| 4.4 | `AT+COPS?` | Le réseau trouvé (nom ou code PLMN) | — |
| 4.5 | `AT+CGDCONT?` | Le contexte de données **0** (créé automatiquement au démarrage) et son APN | Si l'APN est vide ou faux : demander l'APN à Wireless Logic, puis `AT+CFUN=0`, configurer avec `AT+CGDCONT`, `AT#RESET=1` (sauvegarde et redémarrage) |
| 4.6 | `AT+CGPADDR` | Une adresse IP | Pas d'adresse : contexte de données non actif, revoir l'APN |
| 4.7 | Attendre `+CGEV: ME PDN ACT 0` (connexion de données établie, selon la note MQTT ; si ce message n'apparaît jamais, activer les notifications avec `AT+CGEREP=1`), puis lire `AT#IPCFG?` | Pile IPv4 active (`#IPCFG: 5,…` : le **contexte IP 5** est celui utilisé par défaut) | Si la pile IP reste inactive : configuration manuelle avec `AT#IPCFG` (voir la note ST87MXX_TCP_UDP_IP) |

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

D'après le manuel et la note MQTT : une fois la connexion de données établie, on configure le client MQTT, on crée une **socket TCP** sur le **contexte IP 5** (celui utilisé par défaut), puis `AT#MQTTCONNECT` se connecte directement au broker (pas besoin de `AT#TCPCONNECT`). Le broker est donné par son **adresse IP** : si Mathieu donne un nom, le résoudre d'abord avec `AT#DNS`. Les exemples de ST écrivent les textes sans guillemets.

| Étape | Commande | Attendu | Remarques |
|---|---|---|---|
| 6.1 | `AT#DNS=5,0,<nom du broker>` | `#DNS: <adresse IP>,<durée de validité>` | Seulement si le broker a un nom. Le serveur DNS se règle avec `AT#IPPARAMS` (réseau ou mémoire) |
| 6.2 | `AT#MQTTCFG?` puis `AT#MQTTCFG=nilm_01,20,20,10,0` | `OK` | Nom du client (25 caractères au plus), délai de connexion 20 s, délai de protocole 20 s, 10 essais. Dernier champ : **keep-alive**, mis à 0 pour les tests. Attention : le manuel annonce 120 s par défaut, la note MQTT 10 s ; le lire avec `AT#MQTTCFG?` et le fixer soi-même |
| 6.3 | `AT#SOCKETCREATE=5,0,TCP,,10,10` | `#SOCKETCREATE: 0` (numéro de la socket) | Contexte 5, IPv4, TCP, port local libre, délais d'envoi et de réception de 10 s (exemple de ST). Si les délais expirent, monter à 30 s : la note demande des délais « assez grands » pour le réseau. Au plus 3 sockets (1 TCP et 2 UDP) |
| 6.4 | `AT#MQTTCONNECT=5,0,<adresse IP>,1883,<utilisateur>,<mot de passe>` | `OK` | Port 1883 en clair pour ce premier test seulement. Utilisateur : 25 caractères au plus ; mot de passe : 50 au plus. Vérifier avec `AT#MQTTCONNECT?` → `#MQTTCONNECT: 1,…` |
| 6.5 | `AT#MQTTPUB=maison/nilm_01/q,1615;21;48;0;0;310,3,1,0` | `OK` | Topic et message : **50 caractères au plus chacun**. 3 essais, QoS 1, sans *retain*. Si le `;` du message pose problème, réessayer avec le message entre guillemets. Mathieu vérifie : `mosquitto_sub -t 'maison/nilm_01/#' -v` |
| 6.6 | `AT#MQTTSUB=maison/nilm_01/plan,1` | `OK` | Mathieu publie un planning de test |
| 6.7 | (attendre) | `#MQTTRECV: maison/nilm_01/plan, 2101;R;000003;0002AAAAA005;22;22` | Message reçu du broker |
| 6.8 | `AT#MQTTDISC` | `OK` | Déconnexion propre |
| 6.9 | `AT#SOCKETCLOSE=5,0` | `OK` | Ferme la socket (et le lien TCP s'il est encore ouvert) |

**Ensuite : TLS sur le port 8883** (planning : S5). D'après la note d'application ST87MXX_TLS :

- **Seuls les certificats ECDSA sont acceptés : les certificats RSA ne sont pas supportés.** Courbes : NIST P-256 ou P-384 (ou Brainpool équivalentes). Le certificat du broker de Mathieu doit donc être ECDSA.
- Versions : TLS 1.2 et TLS 1.3. En TLS 1.3, le certificat racine (CA) **doit** être chargé dans le module ; en TLS 1.2, c'est facultatif mais conseillé.
- Le certificat racine doit être **auto-signé** (une vraie racine, pas un intermédiaire), au format **DER**, envoyé en hexadécimal.
- Le module range ses clés et certificats dans un « profil de sécurité » (`sec_id`), avec **10 fichiers au plus** en tout.

| Étape | Commande | Rôle |
|---|---|---|
| T.1 | `AT#TLSCERTADD=0,1,<longueur>,<certificat racine DER en hexadécimal>` | Charge le certificat racine dans le profil 0 (type 1 = CA racine) |
| T.2 | `AT#RESET=1` | Sauvegarde et redémarre |
| T.3 | `AT#SOCKETCREATE=5,0,TCP,,10,10,8,0,1` | Socket TCP avec le profil de sécurité 0, la reprise de session TLS (1) et le message `#TLS` qui confirme la session (8) |
| T.4 | `AT#MQTTCONNECT=5,0,<adresse IP>,8883,<utilisateur>,<mot de passe>` | Connexion chiffrée au broker |

**Deux pistes à voir avec Mathieu :** créer une petite autorité de certification ECDSA pour le projet (comme dans l'exemple de ST), ce qui garantit une racine auto-signée ECDSA ; ou utiliser un **PSK** (clé partagée, `AT#TLSKEYADD` + `AT#TLSCERTADD` type 2), qui évite d'échanger des certificats à chaque connexion et économise donc des données. Mosquitto sait gérer les PSK en TLS 1.2 ⚠️ (à vérifier côté serveur).

## 7. Arrêt propre

| Commande | Effet |
|---|---|
| `AT#PWROFF` | Détache le module du réseau, sauvegarde la configuration et l'éteint (`OK` puis `#SHUTDOWN`). Délai maximal de 300 s par défaut, réglable : `AT#PWROFF=30`. Pour le rallumer : bouton ou un caractère envoyé sur l'UART |
| `AT#RESET=1` | Redémarre le module en **sauvegardant** les réglages en mémoire (nécessaire après un changement de configuration) |
| `AT#RFACTORY` | Redémarre avec la **configuration d'usine** (note Startup) : en dernier recours si le module est mal configuré |

Éviter de reconfigurer le module à chaque démarrage : les réglages sont gardés en mémoire, et la mémoire flash supporte un nombre limité d'écritures.

## Ce que le manuel impose pour la suite

| Limite | Valeur | Conséquence pour le projet |
|---|---|---|
| Topic et message MQTT | 50 caractères au plus chacun | Le format de Bastian tient (16 à 19 et 18 à 32 caractères) |
| Nom du client, utilisateur | 25 caractères au plus | À dire à Mathieu pour la création des comptes |
| Mot de passe | 50 caractères au plus | Idem |
| Sockets | 1 TCP et 2 UDP au plus | Une seule connexion MQTT à la fois |
| Adresse du broker | Adresse IP | Résolution DNS avec `AT#DNS`, ou IP fixe côté Azure |
| Keep-alive MQTT | 120 s (manuel) ou 10 s (note MQTT) par défaut | À fixer soi-même avec Mathieu pour ne pas empêcher la veille |
| Contexte IP | 5 par défaut | À utiliser dans `AT#DNS`, `AT#SOCKETCREATE`, `AT#MQTTCONNECT` |
| Reprise de session TLS | Activée par défaut | Bonne nouvelle pour le budget de données |
| Certificats TLS | ECDSA uniquement (pas de RSA), racine auto-signée en DER | À dire à Mathieu avant de créer le certificat du broker |

## Pour plus tard : mesurer la consommation

Quand le module entre en veille, il affiche l'énergie consommée, par exemple `#ENERGY: 43.6` puis `#SLEEP PSM 3187.8s` (exemple du manuel, `AT#SLEEPMODE`). Ces messages serviront aux mesures PSM / eDRX de S5–S6 : penser à les relever dans le journal.

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
| `+CEREG` reste à 2 | Pas de couverture, première recherche longue, mauvaise bande, SIM sans accès NB-IoT en France | Attendre quelques minutes ; près d'une fenêtre ; vérifier l'antenne ; `AT#BANDSEL?` ; demander à Wireless Logic le réseau et les bandes utilisés en France |
| Le module ne répond plus en cours de test | Il est entré en veille | Envoyer un caractère pour le réveiller ; pour la séance, `AT#SLEEPMODE=0` puis `AT#RESET=1` |
| `+CEREG` à 3 | SIM non activée ou refusée | Contacter Wireless Logic (plateforme de gestion de la SIM) |
| Enregistré mais pas d'adresse IP | APN absent ou faux | Configurer l'APN, puis `AT#RESET=1` |
| Connexion MQTT refusée | Mauvais contexte (utiliser 5), nom au lieu d'une adresse IP, port fermé côté Azure, identifiants trop longs ou faux | Résoudre le nom avec `AT#DNS` ; vérifier avec Mathieu le port et le compte (25 / 50 caractères au plus) |
| `ERROR` sans détail | Erreurs détaillées non activées | `AT+CMEE=2`, puis chercher le code dans le chapitre « Error codes » du manuel |

## Fiche de relevé

À remplir pendant les tests (sans IMSI, ICCID ni IMEI). Ces mesures iront dans le rapport de période.

| Date | Lieu | Firmware | `+CEREG` | Réseau (`+COPS`) | Temps d'attache | RSRP (dBm) | RSRQ (dB) | MQTT reçu ? | Remarques |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |
| | | | | | | | | | |
| | | | | | | | | | |
