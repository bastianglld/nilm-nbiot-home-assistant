# Format des messages MQTT

Proposition de la partie C (contenu des messages), alignée le 5 novembre 2026 sur les topics du broker de la partie A (droits du compte du module) et vérifiée côté module par la partie B. Les messages de la carte et du planning sont courts : ils doivent tenir dans la limite de 50 caractères par topic et par message du ST87M01, et chaque octet envoyé en NB-IoT coûte de l'énergie et du forfait.

| Sens | Topic | Fréquence | Taille | Producteur, consommateur |
|---|---|---|---|---|
| Carte vers serveur | `nilm/maison/etat` | toutes les 15 min (envoyées par paquets, voir [budget de données](budget_donnees_sim.md)) | environ 20 caractères | carte, puis EMS et Home Assistant |
| Carte vers serveur | `nilm/maison/dispo` | à la connexion ; `offline` publié par le broker si la carte disparaît | `online` / `offline`, *retain* | carte (message de dernière volonté), puis Home Assistant |
| Serveur vers carte | `nilm/maison/cmd/plan` | une fois par jour, *retain*, QoS 1 | 32 caractères | EMS, puis carte |
| Serveur vers carte | `nilm/maison/cmd/<appareil>` | ponctuel (facultatif), *retain*, QoS 1 | `ON` / `OFF` | Home Assistant, puis carte |
| Carte vers serveur | `nilm/maison/cmd/<appareil>/etat` | après chaque changement d'un relais | `ON` / `OFF` | carte, puis Home Assistant |
| Serveur vers Home Assistant | `nilm/maison/conseils` | une fois par semaine, *retain* | JSON | EMS, puis Home Assistant |

La carte s'abonne à `nilm/maison/cmd/+` en QoS 1 : elle reçoit ainsi le planning et les commandes ponctuelles avec un seul abonnement. Ce filtre ne couvre qu'un niveau : la carte ne reçoit pas ses propres confirmations `cmd/<appareil>/etat`.

Côté carte, chaque message reçu est traité selon la fin de son topic :

- `nilm/maison/cmd/plan` : planning du lendemain, décodé comme décrit plus bas (32 caractères) ;
- `nilm/maison/cmd/<appareil>` : commande ponctuelle `ON` / `OFF` du relais de cet appareil, puis confirmation sur `nilm/maison/cmd/<appareil>/etat` ;
- tout autre nom : ignoré. `plan` est donc un nom réservé, qui ne peut pas désigner un appareil.

Droits des comptes du broker (ACL) :

| Compte | Écriture | Lecture |
|---|---|---|
| Carte (module NB-IoT) | `nilm/maison/etat`, `nilm/maison/dispo`, `nilm/maison/cmd/+/etat` | `nilm/maison/cmd/+` |
| EMS (serveur, `flexibilite/ems_serveur.py`) | `nilm/maison/cmd/plan`, `nilm/maison/conseils` | `nilm/maison/etat` |
| Home Assistant | `nilm/maison/cmd/<appareil>` | `nilm/maison/etat`, `nilm/maison/dispo`, `nilm/maison/cmd/+/etat`, `nilm/maison/conseils` |

Les messages vers la carte sont publiés en *retain* : la carte dort entre deux connexions, et le manuel AT du ST87M01 ne propose aucun réglage de session persistante (à vérifier sur le kit). Avec *retain*, la carte reçoit le dernier planning et la dernière commande à chaque connexion. Le planning envoyé la veille reste la voie principale : une commande ponctuelle peut mettre jusqu'à une heure à arriver si la carte ne se connecte qu'une fois par heure.

Noms d'appareils pour `cmd/<appareil>` : `chauffe_eau` (testé le 5 novembre) ; `batterie` proposé. Liste à confirmer avec Mathieu.

Limite connue : ces topics ne contiennent pas d'identifiant de boîtier. C'est suffisant pour le prototype ; pour un déploiement à plusieurs maisons, il faudra un niveau `nilm/<id>/…`.

## Mesures de la carte : `nilm/maison/etat`

```
hhmm;frigo;bouilloire;lave_linge;lave_vaisselle;total
1615;21;48;0;0;310
```

| Champ | Contenu |
|---|---|
| `hhmm` | heure locale du quart d'heure mesuré |
| `frigo` … `lave_vaisselle` | énergie de chaque appareil sur le quart d'heure, en Wh, estimée par le NILM |
| `total` | énergie totale mesurée sur le quart d'heure, en Wh |

Le réseau a besoin de 127 minutes de mesures *après* une minute pour bien la reconnaître : chaque message décrit donc le quart d'heure d'il y a environ 2 h 10. Le serveur retrouve la date complète à la réception (si `hhmm` est plus tard que l'heure actuelle, c'est la veille).

## Planning du lendemain : `nilm/maison/cmd/plan`

```
JJMM;C;RRRRRR;BBBBBBBBBBBB;LL;VV
2101;R;000003;0002AAAAA005;22;22
```

| Champ | Taille | Contenu |
|---|---|---|
| `JJMM` | 4 | jour et mois concernés |
| `C` | 1 | couleur Tempo : `B` bleu, `W` blanc, `R` rouge, `-` hors Tempo |
| `RRRRRR` | 6 | relais du chauffe-eau, 24 bits en hexadécimal : le bit *h* à 1 autorise la chauffe de *h* h à *h*+1 h |
| `BBBBBBBBBBBB` | 12 | batterie, 2 bits par heure en hexadécimal (bits 2*h* et 2*h*+1) : 0 au repos, 1 charge, 2 décharge |
| `LL` | 2 | heure de départ conseillée du lave-linge |
| `VV` | 2 | heure de départ conseillée du lave-vaisselle |

L'exemple se lit ainsi : le 21 janvier, jour rouge ; chauffe-eau autorisé de 0 h à 2 h ; batterie en charge de 0 h à 2 h et en décharge de 6 h à 17 h ; machines conseillées à 22 h.

Décodage en C sur la carte :

```c
uint32_t relais = strtoul(champ_R, NULL, 16);
uint64_t batt   = strtoull(champ_B, NULL, 16);
bool chauffe    = (relais >> heure) & 1u;
uint8_t mode    = (batt >> (2 * heure)) & 3u;   /* 0 repos, 1 charge, 2 décharge */
```

Le message est publié avec *retain* : la carte le reçoit à son prochain réveil NB-IoT, même si elle dormait au moment de la publication. Proposition pour la carte : si aucun planning n'arrive, elle repasse en fonctionnement de secours (chauffe-eau en heures creuses, batterie au repos).

## Conseils : `nilm/maison/conseils`

Liste JSON triée par gain, par exemple ([fichier complet](../flexibilite/exemples/conseils.json)) :

```json
[
  {
    "type": "offre",
    "titre": "Passer à l'offre Tempo",
    "texte": "Avec votre consommation, l'offre Tempo coûterait 1066 €/an contre 1180 €/an avec votre offre actuelle (Base).",
    "gain_eur_an": 113.7
  }
]
```

`type` vaut `offre`, `decalage`, `veille` ou `alerte`. Côté Home Assistant, un capteur MQTT lit ce topic et une automatisation envoie le texte en notification sur l'application Companion.
