# ADR 0002 : NB-IoT pour la liaison entre le boîtier et le serveur

- Statut : proposé
- Date : 2026-10-22
- Auteur : Merveil Joresse N'Goulou Wamena

## Contexte

Le sujet impose une remontée des données « via le réseau NB-IoT vers une infrastructure cloud sécurisée ». Le client demande de justifier ce choix face aux protocoles déjà présents dans les maisons (TIC, Chain 2, Meters&More côté compteur ; EEBus, DLMS, Thread, Matter, Modbus côté équipements). Étude complète : [`../etude_protocoles_nbiot.md`](../etude_protocoles_nbiot.md).

## Décision

- **NB-IoT** (module ST87M01, MQTT sur TCP, puis TLS) pour la liaison montante (mesures toutes les 15 minutes) et descendante (planning une fois par jour) entre le boîtier et le broker.
- **TIC filaire** pour lire le tarif et la consommation du Linky.
- **Relais câblé** au boîtier pour le chauffe-eau et la batterie de démonstration.
- **Modbus** en option, pour un vrai onduleur.
- Pas de protocole domotique local (Matter, Thread, EEBus) dans le prototype : il demanderait un contrôleur dans la maison.

## Conséquences

- Le boîtier ne dépend ni de la box ni du Wi-Fi, et continue d'exécuter son planning si la liaison tombe.
- Les messages doivent rester courts : 50 caractères au plus par topic et par message (limite du module), budget de 50 Mo sur 6 mois avec la SIM du kit.
- Le broker doit être joignable depuis Internet ([`../hebergement_joignabilite.md`](../hebergement_joignabilite.md)) et accepter un certificat ECDSA.
- Le boîtier ne pilote que ce qui lui est câblé ; l'intégration avec les autres appareils passe par Home Assistant côté serveur.
- Le choix rejoint l'architecture hybride *edge–cloud* recommandée par la revue citée dans le sujet (Cruz-Rangel et al., Energy Nexus, 2025).
