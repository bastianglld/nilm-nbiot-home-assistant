# Home Assistant : affichage, conseils et commande des charges

Responsable : Mathieu Hegoburu (A).

Ce dossier contient la configuration de **Home Assistant**, l'interface utilisateur du projet. Home Assistant reçoit les mesures de la carte, les affiche par pièce et par appareil, transmet les conseils de l'EMS en notification, et coupe ou relance les appareils flexibles selon le tarif. Formats des messages : [`../docs/protocole_messages.md`](../docs/protocole_messages.md).

## Comment Home Assistant reçoit les données

Home Assistant tourne à la maison (ici dans une machine virtuelle VirtualBox, système HA OS). Il n'est **jamais exposé sur Internet** : il ouvre lui-même une connexion **sortante** et chiffrée vers le broker du cloud (voir [`../cloud/`](../cloud/)), grâce à un **pont MQTT**.

```
Carte NB-IoT ──► Broker cloud (TLS) ◄── pont sortant ── Mosquitto local (add-on) ──► Home Assistant
EMS ───────────►                                                                      │
                                                                                      │
   relais ◄── broker cloud ◄── pont ◄── ordres ON/OFF ◄── automatisation ◄────────────┘
```

Avantage : ça fonctionne depuis n'importe quel réseau (maison, université, partage 4G) sans ouvrir de port sur la box.

## Contenu du dossier

| Dossier | Rôle |
|---|---|
| [`pont-vps/`](pont-vps/) | Configuration du pont entre le Mosquitto local et le broker cloud. |
| [`mqtt-discovery/`](mqtt-discovery/) | Déclaration des capteurs et des relais : Home Assistant les crée automatiquement. |
| [`automatisations/`](automatisations/) | Délestage selon le tarif, notification des conseils de l'EMS, entrées associées. |
| [`dashboard/`](dashboard/) | Les vues du dashboard « Projet NILM » : accueil et une sous-vue par pièce. |
| [`configuration/`](configuration/) | Réglages de performance (base de données) et thème « NILM Néon ». |

Prérequis : Home Assistant avec l'add-on **Mosquitto broker** et l'intégration **MQTT**, **HACS** avec la carte **ApexCharts** (`custom:apexcharts-card`) pour les graphiques, et l'application **Home Assistant (Companion)** sur le téléphone pour les notifications.

---

## 1. Le pont vers le broker cloud (`pont-vps/`)

Le fichier [`pont-vps.conf`](pont-vps/pont-vps.conf) demande au Mosquitto local de se connecter au broker cloud avec le compte `homeassistant`, en vérifiant son certificat, et de recopier :

- **du cloud vers la maison** : les mesures (`nilm/maison/etat`), la présence de la carte (`dispo`), l'état réel des relais (`cmd/+/etat`) et les conseils de l'EMS (`conseils`) ;
- **de la maison vers le cloud** : les ordres ON/OFF des relais (`cmd/+`).

Installation :

1. Paramètres > Modules complémentaires > **Mosquitto broker** > Configuration, section *Customize* :
   ```yaml
   active: true
   folder: mosquitto
   ```
2. Copier `pont-vps.conf` dans `/share/mosquitto/` (avec l'add-on *Studio Code Server* ou *File editor*), en remplaçant `NOM_DNS_DU_VPS` et `MOT_DE_PASSE_HOMEASSISTANT`. Ce fichier rempli reste sur Home Assistant : il ne doit pas revenir dans le dépôt.
3. Redémarrer l'add-on. Dans son onglet *Journal*, la ligne `Connecting bridge vps-nilm` doit apparaître sans erreur.

Si le journal indique que `ca-certificates.crt` est introuvable, remplacer la ligne `bridge_cafile` par `bridge_capath /etc/ssl/certs`.

## 2. Les capteurs et relais (`mqtt-discovery/`)

Plutôt que d'écrire chaque capteur à la main, on utilise **MQTT Discovery** : on publie un petit JSON de description sur `homeassistant/<type>/<unique_id>/config` (avec *retain*, pour qu'il survive aux redémarrages), et Home Assistant crée l'entité tout seul.

Le plus simple est de lancer le simulateur ([`../cloud/simulateur/`](../cloud/simulateur/)) une fois : il publie tous ces fichiers. On peut aussi les publier à la main avec **MQTT Explorer**, par exemple `capteurs/nilm_frigo_energie.json` sur `homeassistant/sensor/nilm_frigo_energie/config`.

### Mesures de la carte

La carte envoie toutes les 15 minutes un message court (moins de 50 caractères, limite du ST87M01) :

```
hhmm;frigo;bouilloire;lave_linge;lave_vaisselle;total
1615;21;48;0;0;310
```

Chaque valeur est l'énergie **du quart d'heure** en Wh, pas un compteur qui augmente. Les capteurs la convertissent en kWh et utilisent `state_class: total` avec un `last_reset` égal à l'heure du quart d'heure (`hhmm`, ramenée à la veille si elle est plus tard que l'heure actuelle, car le NILM a environ 2 h 10 de retard). À chaque nouveau quart d'heure, Home Assistant comprend qu'il s'agit d'une nouvelle tranche et l'**additionne** dans ses statistiques. Les capteurs alimentent ainsi directement le **panneau Énergie** natif.

| Fichier | Entité créée |
|---|---|
| `nilm_<appareil>_energie.json` | énergie de l'appareil (kWh) : frigo, bouilloire, lave-linge, lave-vaisselle |
| `nilm_total_energie.json` | énergie totale de la maison (kWh) |
| `nilm_non_identifie.json` | part non attribuée : total − somme des appareils (kWh) |
| `nilm_frigo_puissance.json` | puissance moyenne du frigo = Wh × 4 (W) ; « indisponible » après 30 min sans message |
| `nilm_boitier_connecte.json` | carte connectée ou non (`nilm/maison/dispo`) |
| `nilm_ems_conseils.json` | nombre de conseils de l'EMS, avec la liste complète et le gain total en attributs |

Pour le panneau Énergie : Paramètres > Tableaux de bord > Énergie > *Consommation du réseau* = « Énergie totale » de *Maison (NILM)*, et *Appareils individuels* = chaque « Énergie estimée ».

### Relais

`nilm_chauffe_eau_relais.json` et `nilm_chauffage_relais.json` créent deux interrupteurs, `switch.chauffe_eau_relais` et `switch.radiateur_chambre_relais`. Deux réglages importants :

- `retain: true` : la carte dort entre deux connexions, le broker garde donc le dernier ordre pour le lui livrer à son réveil ;
- `optimistic: false` : l'interrupteur affiche l'**état confirmé par la carte** (`cmd/<appareil>/etat`), pas l'ordre envoyé. L'utilisateur voit ce que le relais a vraiment fait ; sans réponse de la carte, l'état reste « inconnu ».

## 3. Commande des charges selon le tarif (`automatisations/`)

**Principe** : couper les appareils flexibles (chauffe-eau, radiateur) quand l'électricité est chère, les relancer quand elle l'est moins. C'est la commande ponctuelle, en complément du planning du lendemain calculé par l'EMS.

```
Tarif en cours (HC / HP) ──► Automatisation ──► ordre ON/OFF ──► carte ──► relais
                                                                    │
Home Assistant affiche l'état réel ◄── confirmation de la carte ◄───┘
```

1. [`entrees.yaml`](automatisations/entrees.yaml) crée deux entrées (à coller dans `configuration.yaml`, ou à créer dans Paramètres > Appareils et services > Entrées) :
   - `input_select.tarif_en_cours` : *Heures creuses* / *Heures pleines* ;
   - `input_boolean.pilotage_automatique` : permet à l'utilisateur de reprendre la main à tout moment.
2. [`delestage-tarif.yaml`](automatisations/delestage-tarif.yaml) : l'automatisation (Paramètres > Automatisations > Créer > ⋮ > Modifier en YAML). Si le pilotage automatique est activé, elle éteint les deux relais en heures pleines et les rallume en heures creuses. Elle se relance aussi quand on réactive le pilotage, pour remettre les relais dans le bon état.

Pour l'instant, le **tarif est simulé** par la liste déroulante. À terme, il viendra du compteur Linky (sortie **TIC**, champ `PTEC`, voir [`../docs/interface_tic.md`](../docs/interface_tic.md)). Seule la source change : l'automatisation reste la même.

**Tester sans la carte** : passer le tarif sur *Heures pleines*, vérifier dans MQTT Explorer (broker cloud) que `OFF` part sur `nilm/maison/cmd/chauffe_eau`, puis jouer la carte en publiant `OFF` sur `nilm/maison/cmd/chauffe_eau/etat` avec le compte `simulateur`. L'interrupteur passe à « éteint » dans Home Assistant.

## 4. Conseils de l'EMS en notification

Une fois par semaine, l'EMS publie sur `nilm/maison/conseils` une liste de conseils triée par gain (exemple : [`../flexibilite/exemples/conseils.json`](../flexibilite/exemples/conseils.json)).

- Le capteur `sensor.ems_conseils` affiche le nombre de conseils et garde la liste complète en attributs, pour une carte du dashboard.
- L'automatisation [`notification-conseils.yaml`](automatisations/notification-conseils.yaml) envoie le premier conseil (celui qui fait gagner le plus) en notification sur le téléphone. Remplacer `notify.notify` par `notify.mobile_app_<nom_du_telephone>` pour viser un téléphone précis.

Le message étant publié avec *retain*, un redémarrage de Home Assistant peut renvoyer la dernière notification une fois.

## 5. Le dashboard (`dashboard/`)

Dashboard « Projet NILM », organisé en une vue d'accueil et une sous-vue par pièce :

| Fichier | Contenu |
|---|---|
| `vue-accueil.yaml` | Consommation et coût du jour, répartition par pièce, par appareil sur 7 jours, eau, dernières 24 h, frigo en direct |
| `sous-vue-cuisine.yaml` | Frigo, four, lave-vaisselle (électricité et eau) |
| `sous-vue-salon.yaml` | TV, console |
| `sous-vue-chambre.yaml` | Chauffage |
| `sous-vue-salle-de-bain.yaml` | Lave-linge, sèche-serviette (électricité et eau) |

Import : dans le dashboard, ⋮ > Modifier > ajouter une vue > ⋮ > *Modifier en YAML* > coller le fichier.

Choix pour garder un dashboard fluide :

- les graphes sur la journée et la semaine lisent les **statistiques long terme** de Home Assistant (quelques dizaines de points) plutôt que l'historique brut (des milliers) ;
- les cartes se rafraîchissent toutes les 1 à 5 minutes, pas à chaque message ;
- le coût est calculé directement dans la carte, sans capteur supplémentaire.

Les vues ont été construites sur une **maison de démonstration** (appareils et compteurs d'eau simulés par pièce : `sensor.energie_<appareil>`, `sensor.total_energie_<piece>`, `sensor.total_eau_<piece>`). Les totaux par pièce sont des **groupes de capteurs** (type Somme), et `sensor.total_energie_maison` la somme des pièces. Pour les brancher sur les capteurs NILM, il suffit de remplacer les noms d'entités (Ctrl+H dans l'éditeur YAML).

## 6. Configuration générale (`configuration/`)

- [`recorder.yaml`](configuration/recorder.yaml) : à ajouter dans `configuration.yaml`. Réduit les écritures en base (toutes les 30 s), garde 7 jours d'historique détaillé (les statistiques long terme du panneau Énergie sont conservées) et active le dossier des thèmes.
- [`themes/nilm_neon.yaml`](configuration/themes/nilm_neon.yaml) : thème sombre du dashboard, à copier dans `/config/themes/`, puis à choisir dans le profil utilisateur.

## Sécurité

- Home Assistant n'a **aucun port ouvert** sur Internet : il est seulement client du broker cloud.
- Le pont vérifie le certificat du broker (`bridge_insecure false`) : impossible de le détourner vers un faux serveur.
- Le compte `homeassistant` ne peut envoyer que des ordres aux relais : il ne peut ni publier de fausses mesures, ni modifier le planning de l'EMS.
- Aucun mot de passe n'est stocké dans ce dépôt : les fichiers contiennent des valeurs à remplacer, écrites en MAJUSCULES.

## Suite prévue

- Brancher la vraie carte à la place du simulateur.
- Lire le tarif réel depuis le compteur Linky.
- Piloter les relais depuis l'iPhone avec Siri, via l'intégration **HomeKit Bridge** de Home Assistant.
