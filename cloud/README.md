# Cloud : broker MQTT sécurisé

Responsable : Mathieu Hegoburu (A).

Ce dossier contient tout ce qui tourne **dans le cloud** : le serveur MQTT (Mosquitto) par lequel passent tous les messages entre la carte NB-IoT, l'EMS et Home Assistant. Le format des messages est décrit dans [`../docs/protocole_messages.md`](../docs/protocole_messages.md).

## Pourquoi un broker dans le cloud ?

La carte envoie ses mesures par le réseau cellulaire, donc via Internet. Il lui faut une adresse fixe, joignable de partout (voir aussi [`../docs/hebergement_joignabilite.md`](../docs/hebergement_joignabilite.md)).

| Option | Problème |
|---|---|
| Broker à la maison (box Internet, NAS) | Il faut ouvrir un port sur la box : impossible sur le réseau de l'université, et risqué pour le réseau domestique. |
| **Broker sur un serveur cloud (VPS)** ✅ | Adresse publique fixe, rien à ouvrir à la maison. Coût couvert par les crédits Azure for Students. |

Choix retenu : une petite machine virtuelle **Ubuntu 24.04** sur **Microsoft Azure** (région Belgique, taille B2ats_v2, environ 8 $ par mois sur les crédits étudiants), avec **Mosquitto**. L'EMS ([`../flexibilite/ems_serveur.py`](../flexibilite/ems_serveur.py)) tourne sur ce même serveur. Home Assistant reste à la maison et n'est pas exposé : c'est lui qui se connecte au broker (voir [`../homeassistant/`](../homeassistant/)).

```
                                    Internet
  Carte NB-IoT ──── mesures, état des relais ───►  ┌───────────────────────────┐
               ◄─── planning, ordres ON/OFF ─────  │  VPS Azure                │
                                       TLS 8883    │  Broker Mosquitto         │
                                                   │  (comptes + ACL + TLS)    │
  Home Assistant ── connexion sortante ──────────► │  EMS (planning, conseils) │
  (maison)                             TLS 8883    └───────────────────────────┘
```

Plan B si le VPS n'est plus disponible : un broker gratuit HiveMQ Cloud, avec la même configuration côté clients (seuls l'adresse et les comptes changent).

## Sécurité

| Mesure | Ce qu'elle protège |
|---|---|
| **TLS obligatoire** (port 8883, TLS 1.2) avec un certificat **Let's Encrypt** renouvelé automatiquement | Personne ne peut lire ni modifier les messages en chemin. Le client vérifie qu'il parle bien au vrai serveur. |
| **Pas d'accès anonyme** (`allow_anonymous false`) | Seuls les clients qui ont un compte peuvent se connecter. |
| **Un compte par client** : `homeassistant`, `module_nbiot`, `ems`, `simulateur` | Si un mot de passe fuite, on ne change que celui-là. |
| **ACL** : liste des droits par compte | Chaque compte ne lit et n'écrit que ses propres topics. La carte, par exemple, ne peut ni publier de planning ni piloter un autre appareil. |
| **Port 1883 (non chiffré) limité au serveur lui-même** (`127.0.0.1`) | Utilisé seulement par l'EMS et pour les tests. Il n'est pas joignable depuis Internet. |
| **Mots de passe aléatoires** générés par le script, jamais écrits dans le dépôt | Le `.gitignore` empêche de versionner mots de passe, clés et certificats. |

Le certificat Let's Encrypt est signé par l'autorité **ISRG Root X1** : c'est ce certificat racine qu'il faut charger dans le ST87M01 pour qu'il vérifie le serveur.

## Droits des comptes (ACL)

Ils reprennent le tableau de [`../docs/protocole_messages.md`](../docs/protocole_messages.md) :

| Compte | Peut écrire | Peut lire |
|---|---|---|
| `module_nbiot` (carte) | `nilm/maison/etat`, `nilm/maison/dispo`, `nilm/maison/cmd/+/etat` | `nilm/maison/cmd/+` (planning et ordres) |
| `ems` | `nilm/maison/cmd/plan`, `nilm/maison/conseils` | `nilm/maison/etat` |
| `homeassistant` | `nilm/maison/cmd/+` (ordres), `homeassistant/#` (découverte) | `nilm/#`, `homeassistant/#` |
| `simulateur` | `nilm/maison/etat`, `nilm/maison/dispo`, `nilm/maison/cmd/+/etat`, `homeassistant/#` | rien |

Le compte `simulateur` sert pendant les tests. Il sera supprimé quand la carte fonctionnera.

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| [`broker-vps/installer-broker.sh`](broker-vps/installer-broker.sh) | Installe et configure tout le broker sur un serveur Ubuntu neuf, en une commande. |
| [`broker-vps/acl`](broker-vps/acl) | Les droits de chaque compte (le script installe exactement ce fichier). |
| [`broker-local-docker/`](broker-local-docker/) | Le même broker sur un PC avec Docker, pour tester sans serveur. |
| [`simulateur/nilm_simulateur.py`](simulateur/nilm_simulateur.py) | Joue le rôle de la carte : envoie de fausses mesures pour tester toute la chaîne. |

## Installer le broker sur un serveur (VPS)

Prérequis : un serveur Ubuntu 24.04 avec un **nom DNS public** (sur Azure : VM > Configuration de l'adresse IP > étiquette du nom DNS) et les ports **80** (vérification Let's Encrypt) et **8883** (MQTT TLS) ouverts dans le pare-feu.

```bash
sudo bash installer-broker.sh mon-broker.exemple.com
```

Le script :

1. installe `mosquitto`, `mosquitto-clients` et `certbot` ;
2. obtient le certificat Let's Encrypt et installe un *hook* qui le recopie pour Mosquitto à chaque renouvellement automatique (tous les 90 jours) ;
3. écrit la configuration (`/etc/mosquitto/conf.d/nilm.conf`) et les droits (`/etc/mosquitto/acl`) ;
4. crée les quatre comptes avec des **mots de passe aléatoires, affichés une seule fois** : il faut les noter immédiatement.

Vérifier depuis un PC où `mosquitto-clients` est installé :

```bash
# Affiche tous les messages qui arrivent (Ctrl+C pour arrêter)
mosquitto_sub -h mon-broker.exemple.com -p 8883 --capath /etc/ssl/certs \
  -u homeassistant -P "$MQTT_PASSWORD" -t 'nilm/#' -v
```

Pour un test graphique, **MQTT Explorer** fonctionne aussi : port 8883, « Encryption (tls) » et « Validate certificate » activés.

## Tester en local avec Docker

Dans `broker-local-docker/` :

```bash
# 1. Créer les comptes (remplacer CHANGE_MOI par de vrais mots de passe)
touch passwd
docker run --rm -v "$PWD:/w" eclipse-mosquitto:2 sh -c \
  'for u in homeassistant module_nbiot ems simulateur; do mosquitto_passwd -b /w/passwd $u CHANGE_MOI_$u; done'

# 2. Créer une petite autorité de certification de test
mkdir -p certs && cd certs
openssl req -x509 -new -nodes -days 365 -newkey rsa:2048 -keyout ca.key -out ca.crt -subj "/CN=NILM-CA"
openssl req -new -nodes -newkey rsa:2048 -keyout server.key -out server.csr -subj "/CN=localhost"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 365 -out server.crt
cd ..

# 3. Démarrer
docker compose up -d

# 4. Vérifier que les droits sont appliqués
mosquitto_pub -h localhost -u module_nbiot -P CHANGE_MOI_module_nbiot -t nilm/maison/cmd/plan -m x
#    -> refusé (silencieusement) : seule l'EMS peut publier le planning
```

## Le simulateur

Il remplace la carte tant que le matériel n'est pas prêt :

1. il publie les configs de [`../homeassistant/mqtt-discovery/`](../homeassistant/mqtt-discovery/) : Home Assistant crée tout seul les capteurs et les relais ;
2. il annonce la carte `online` sur `nilm/maison/dispo` (et le broker publie `offline` s'il disparaît) ;
3. il envoie une mesure toutes les 10 secondes, au format du protocole : `1615;21;48;0;0;310`.

Pour que la démonstration soit rapide, chaque message avance l'horloge simulée de 15 minutes : une journée défile en 16 minutes.

```bash
cd simulateur
pip install -r requirements.txt
export MQTT_PASSWORD='...'     # le mot de passe n'est jamais écrit dans un fichier

# Vers le broker du VPS (chiffré)
python nilm_simulateur.py --broker mon-broker.exemple.com --tls --user simulateur

# Vers le broker local de Home Assistant (réseau de la maison)
python nilm_simulateur.py --broker IP_DE_HOME_ASSISTANT --user UTILISATEUR_MQTT
```

Options : `--periode` (secondes entre deux messages), `--port`, `--cafile` (autorité de test, comme celle de Docker), `--sans-decouverte`.

Les tests automatiques ([`../tests/test_home_assistant.py`](../tests/test_home_assistant.py)) vérifient que les messages du simulateur respectent le protocole et sont bien lus par l'EMS, que les configs de découverte utilisent les bons topics et que les droits du broker correspondent au protocole.

## Points d'attention

- **La carte dort** entre deux connexions NB-IoT. Les ordres et le planning sont donc publiés avec *retain* : le broker garde le dernier message et le livre à la carte à sa prochaine connexion.
- **L'EMS** se connecte au broker en local sur le serveur. Il devra utiliser le compte `ems` (identifiant et mot de passe), car l'accès anonyme est refusé.
