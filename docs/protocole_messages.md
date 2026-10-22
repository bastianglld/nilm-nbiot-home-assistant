# Format des messages MQTT

Proposition de la partie C, à valider avec Mathieu (broker, Home Assistant) et Merveil (carte, ST87M01). Les messages de la carte et du planning sont courts : ils doivent tenir dans la limite de 50 caractères par message retenue pour le ST87M01, et chaque octet envoyé en NB-IoT coûte de l'énergie.

| Sens | Topic | Fréquence | Taille | Producteur, consommateur |
|---|---|---|---|---|
| Carte vers serveur | `maison/nilm_01/q` | toutes les 15 min | environ 20 caractères | carte, puis EMS et Home Assistant |
| Serveur vers carte | `maison/nilm_01/plan` | une fois par jour, *retain*, QoS 1 | 32 caractères | EMS, puis carte |
| Serveur vers Home Assistant | `maison/nilm_01/conseils` | une fois par semaine, *retain* | JSON | EMS, puis Home Assistant |

## Mesures de la carte : `maison/nilm_01/q`

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

## Planning du lendemain : `maison/nilm_01/plan`

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

## Conseils : `maison/nilm_01/conseils`

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
