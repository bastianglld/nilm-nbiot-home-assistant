# Installer l'EMS sur le serveur

L'EMS ([`../ems_serveur.py`](../ems_serveur.py)) tourne sur le même serveur que le broker Mosquitto (VPS Azure, Ubuntu 24.04, installé par [`../../cloud/broker-vps/installer-broker.sh`](../../cloud/broker-vps/installer-broker.sh)). Il s'y connecte **en local**, sur `127.0.0.1:1883`, avec le compte **`ems`** du broker : pas de TLS à régler, et rien à ouvrir de plus sur Internet.

| Fichier | Rôle |
|---|---|
| [`installer-ems.sh`](installer-ems.sh) | Installe tout en une commande : compte système `ems`, `/opt/ems`, Python et bibliothèques, réglages, services |
| [`ems-enregistreur.service`](ems-enregistreur.service) | En continu : chaque message de la carte (`nilm/maison/etat`) est ajouté à `/opt/ems/historique.csv` ; redémarre seul en cas d'erreur ou de coupure du broker |
| [`ems-planning.service`](ems-planning.service), [`ems-planning.timer`](ems-planning.timer) | Chaque jour à **13 h 30** (heure française) : planning du lendemain publié avec *retain* sur `nilm/maison/cmd/plan` |
| [`ems-analyse.service`](ems-analyse.service), [`ems-analyse.timer`](ems-analyse.timer) | Chaque **lundi à 8 h** : habitudes, profils de journées et conseils publiés sur `nilm/maison/conseils` (lus par Home Assistant) |
| [`ems.env.example`](ems.env.example) | Modèle de `/etc/ems/ems.env` : mot de passe du compte `ems`, offre du foyer. Le vrai fichier n'est jamais versionné |

Les services tournent avec `TZ=Europe/Paris` : la carte envoie l'heure française (`hhmm`), et le serveur Azure est à l'heure UTC.

## Installation (avec Mathieu, une demi-heure)

Il faut : un accès SSH au serveur, et le **mot de passe du compte `ems`** affiché par `installer-broker.sh` (Mathieu l'a noté).

```bash
# 1. Depuis le PC : copier le dossier flexibilite sur le serveur (le dépôt est privé)
scp -r flexibilite utilisateur@mon-broker.exemple.com:~/

# 2. Sur le serveur
ssh utilisateur@mon-broker.exemple.com
sudo bash ~/flexibilite/deploiement/installer-ems.sh
#    -> demande le mot de passe du compte ems, l'offre pour le planning (Tempo par défaut) et l'offre actuelle (Base)
```

Le script affiche l'état de l'enregistreur et la date des prochains plannings et analyses. Pour une mise à jour : recopier le dossier et relancer le script (l'historique, les prix et les réglages sont gardés). Pour changer d'offre : modifier `/etc/ems/ems.env`.

## Vérifier que tout marche, sans la carte

1. **Enregistreur** : lancer le simulateur de Mathieu depuis un PC ([`../../cloud/README.md`](../../cloud/README.md#le-simulateur)) et regarder les messages arriver :
   ```bash
   journalctl -u ems-enregistreur -f        # « connecté à 127.0.0.1:1883, abonné à nilm/maison/etat »
   tail -f /opt/ems/historique.csv          # une ligne par quart d'heure reçu
   ```
2. **Planning tout de suite** (sans attendre 13 h 30), et réception côté Home Assistant ou carte :
   ```bash
   sudo systemctl start ems-planning.service && journalctl -u ems-planning -n 20
   mosquitto_sub -h 127.0.0.1 -u homeassistant -P "$MDP_HA" -t nilm/maison/cmd/plan -v    # message de 32 caractères
   ```
3. **Conseils** : l'analyse attend au moins 7 jours d'historique (sinon elle l'écrit dans le journal et ne publie rien). Pour une démonstration tout de suite, la lancer à la main sur l'année simulée des notebooks (2013-2014, rejouée sur les prix 2024-2025 avec `--decalage-jours 4018`) : les conseils apparaissent dans le capteur `sensor.ems_conseils` de Home Assistant.
   ```bash
   # copier aussi depuis le PC : scp nilm/notebooks/profils_s9/messages_15min_nilm.csv utilisateur@…:~/
   sudo install -o ems -g ems -m 640 ~/messages_15min_nilm.csv /opt/ems/demo_annee.csv
   sudo -u ems env $(sudo cat /etc/ems/ems.env | xargs) TZ=Europe/Paris /opt/ems/venv/bin/python /opt/ems/ems_serveur.py analyse \
       --historique /opt/ems/demo_annee.csv --offre-actuelle Base --decalage-jours 4018 --cumulus 5 \
       --prix /opt/ems/prix --publier --broker 127.0.0.1 --utilisateur ems
   ```
   Résultat attendu (essai sur PC) : passer à Tempo (1 067 €/an au lieu de 1 180), lave-linge en heures creuses (19 €/an), veille de 159 W, lave-vaisselle en heures creuses.

Le simulateur fait défiler une journée en 16 minutes mais n'envoie que l'heure (`hhmm`), comme la carte : l'enregistreur date chaque message au jour courant. Il sert à tester la chaîne, pas à remplir des semaines d'historique.

## Commandes utiles

| Besoin | Commande |
|---|---|
| État des services et prochaines exécutions | `systemctl status ems-enregistreur` ; `systemctl list-timers 'ems-*'` |
| Journal du dernier planning | `journalctl -u ems-planning -n 30` |
| Arrêter l'EMS | `sudo systemctl disable --now ems-enregistreur ems-planning.timer ems-analyse.timer` |

En cas de « pas d'accusé du broker » ou de connexion refusée dans le journal : vérifier le mot de passe dans `/etc/ems/ems.env` et le compte `ems` dans `/etc/mosquitto/acl`.

## Essai réalisé (12 novembre 2026)

Sur un Mosquitto local avec les mêmes droits que le VPS ([`../../cloud/broker-vps/acl`](../../cloud/broker-vps/acl), comptes `ems`, `simulateur`, `homeassistant`), après `installer-ems.sh` et en tant que compte système `ems` : messages enregistrés (un doublon QoS 1 ignoré, un message mal formé rejeté), planning publié et reçu par le compte `homeassistant`, analyse reportée faute de 7 jours, connexion refusée avec un mauvais mot de passe. Le téléchargement des prix Tempo et spot n'a pas pu être testé hors du serveur (accès Internet limité) : à vérifier au premier planning sur le VPS.
