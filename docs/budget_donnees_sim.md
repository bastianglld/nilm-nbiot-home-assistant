# Budget de données de la SIM NB-IoT

Partie B (Merveil), tâche B-45. Combien de données consomme l'envoi des mesures en MQTT sur TLS, et quelle stratégie d'envoi tient dans le forfait de la SIM du kit.

**Ce sont des estimations.** Les tailles TLS et TCP sont des valeurs typiques et chaque segment est compté avec un accusé de réception séparé, ce qui majore un peu le total. Les vraies valeurs seront mesurées sur le kit (tâche B-29) et remplaceront celles-ci. Le calcul est dans [`firmware/tests_st87m01/budget_donnees.py`](../firmware/tests_st87m01/budget_donnees.py) : changer une hypothèse et relancer `python budget_donnees.py`.

## Le forfait

SIM Wireless Logic du kit : **50 Mo sur 6 mois**, soit environ **274 ko par jour**. On compte les octets au niveau IP, dans les deux sens, comme le fait en général l'opérateur.

Besoin, d'après [`protocole_messages.md`](protocole_messages.md) : une mesure de 18 caractères toutes les 15 minutes (96 par jour) sur `maison/nilm_01/q`, et un planning de 32 caractères par jour sur `maison/nilm_01/plan`.

## Ce que coûte une mesure

| Cas | Octets |
|---|---|
| Message MQTT seul (PUBLISH QoS 1 : en-tête, topic, message) | 40 |
| La même mesure dans une connexion TLS déjà ouverte (+ TLS, TCP/IP, PUBACK, accusés) | 262 |
| Une session complète pour une seule mesure : TCP, poignée de main TLS, CONNECT, PUBLISH, DISCONNECT, fermeture | 2 737 |
| La même session avec reprise de session TLS (poignée de main abrégée) | 1 658 |

La mesure elle-même pèse 40 octets ; c'est **l'ouverture de la connexion TLS** qui coûte cher (environ 1,5 ko pour la poignée de main complète, dont le certificat du broker). Le budget dépend donc surtout du nombre de connexions par jour, pas du nombre de mesures.

## Stratégies comparées

| | Stratégie | ko / jour | Part du forfait | Sur 6 mois |
|---|---|---|---|---|
| A | Reconnexion toutes les 15 min, TLS complet | 263 | **96 %** | 48 Mo |
| B | Reconnexion toutes les 15 min, reprise de session TLS | 160 | 58 % | 29 Mo |
| C | 1 connexion par heure (4 mesures), TLS complet | 85 | 31 % | 16 Mo |
| D | 1 connexion par heure, reprise de session TLS | 59 | 22 % | 11 Mo |
| E | 1 connexion toutes les 2 h (8 mesures), reprise TLS | 42 | 15 % | 8 Mo |
| F1 | Connexion gardée, keep-alive 60 s | 327 | **119 %** | 60 Mo |
| F2 | Connexion gardée, keep-alive 300 s | 71 | 26 % | 13 Mo |
| F3 | Connexion gardée, keep-alive ≥ 900 s | 28 | 10 % | 5 Mo |
| Réf. | Sans TLS (essais seulement), reconnexion toutes les 15 min | 76 | 28 % | 14 Mo |

Avec une publication toutes les 15 minutes, un keep-alive de 900 s ou plus n'envoie aucun PINGREQ : chaque publication remet le compteur à zéro.

## Ce qu'on en retient

- **À éviter : A et F1.** Se reconnecter à chaque mesure consomme presque tout le forfait, sans marge pour les essais ni les erreurs. Un keep-alive court le dépasse.
- **Stratégie proposée : regrouper les envois, une connexion par heure (C, ou D si le module sait reprendre une session TLS).** Entre 22 et 31 % du forfait, ce qui laisse de la marge pour les semaines d'essais. Le module peut dormir (PSM) entre deux connexions, ce qui économise aussi l'énergie. Le retard ajouté est d'une heure au plus, alors que chaque mesure décrit déjà le quart d'heure d'il y a 2 h 10 : l'EMS n'y perd presque rien. Le planning, publié avec *retain*, arrive à la connexion suivante.
- **Optimisation à essayer : garder la connexion ouverte (F3).** C'est le moins cher, mais seulement si le réseau garde la connexion TCP inactive pendant 15 minutes (délai d'expiration du NAT de l'opérateur, inconnu) et si le module la conserve entre deux envois. À mesurer sur le kit.
- Chaque mesure part dans son propre PUBLISH : le regroupement se fait en plusieurs messages dans une même connexion, la limite de 50 caractères par message du module reste donc respectée.

## À vérifier

| Question | Où | Tâche |
|---|---|---|
| Le ST87M01 sait-il reprendre une session TLS (session ID ou ticket) ? | Note d'application TLS de ST, puis essai | B-28 |
| Combien pèse vraiment la poignée de main avec le certificat du broker de Mathieu (un certificat ECDSA, ou une chaîne) ? | Journal du module ou capture côté broker | B-28, B-29 |
| Comment Wireless Logic compte les données : octets IP dans les deux sens, arrondi par session ? | Contrat ou support Wireless Logic | B-22 |
| Au bout de combien de temps le NAT de l'opérateur coupe une connexion TCP inactive ? | Essai sur le kit avec des keep-alive de 300, 900 et 1 200 s | B-29 |
| Consommation réelle d'une journée, comparée à ces estimations | Compteur de données de la SIM sur le portail de l'opérateur | B-29 |

## Hypothèses du calcul

- IPv4 sans option, TCP sans horodatage (40 octets d'en-tête), un accusé de réception de 40 octets pour chaque segment de données.
- TLS 1.2 ECDHE-ECDSA avec AES-128-GCM (29 octets ajoutés par enregistrement), broker authentifié par un seul certificat ECDSA, appareil authentifié par identifiant et mot de passe MQTT : poignée de main complète ≈ 1,5 ko avec TCP, reprise ≈ 0,6 ko.
- MQTT 3.1.1, mesures en QoS 1 (avec PUBACK), identifiant et utilisateur de 7 caractères, mot de passe de 20.
- Pas de requête DNS (adresse IP du broker fixe) ; l'attache au réseau NB-IoT ne consomme pas de données IP.
