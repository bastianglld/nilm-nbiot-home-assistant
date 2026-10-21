# ADR 0001 : IA répartie entre la carte et le serveur

- Statut : accepté
- Date : 2026-10-21
- Auteur : Bastian Guilloud

## Contexte

Le projet doit reconnaître les appareils d'un logement à partir d'une seule mesure, puis aider à décaler la consommation selon le prix. Le lien NB-IoT est lent et chaque envoi coûte de l'énergie. Dans ses retours, le client distingue deux usages de l'IA : reconnaître les équipements en *edge AI*, et proposer des profils d'usage sur le serveur.

## Décision

- **Sur la carte** : le modèle NILM (réseau convolutif, 22 120 paramètres, int8) tourne sur le NPU du STM32N6 toutes les 15 minutes. Seules 5 énergies par quart d'heure partent en NB-IoT (environ 20 caractères).
- **Sur le serveur** : l'EMS (`flexibilite/ems_serveur.py`) garde l'historique, apprend les habitudes, télécharge les prix, prépare le planning du lendemain et les conseils. Il renvoie à la carte un message de 32 caractères par jour.

## Conséquences

- La courbe brute ne quitte pas le logement : moins de données envoyées et meilleure confidentialité.
- Le calcul sur la carte est négligeable (2 ms toutes les 15 minutes), ce qui laisse le microcontrôleur libre pour la mesure et la radio.
- Les traitements qui ont besoin de plusieurs semaines d'historique ou d'internet (prix, couleur Tempo) restent sur le serveur, où ils sont faciles à mettre à jour.
- Le format des messages devient un contrat entre les parties A, B et C : il est décrit dans [`../protocole_messages.md`](../protocole_messages.md).
