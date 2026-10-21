# Serveur et broker MQTT

Responsable : Mathieu Hegoburu (A).

Ce dossier accueillera la configuration du broker Mosquitto (TLS, comptes et droits par topic) et l'installation du serveur. Ne jamais y versionner de clés, mots de passe ou certificats privés : utiliser un fichier `.env` (ignoré par Git) et un `.env.example` sans valeurs réelles.

Topics utilisés par la carte et par l'EMS : voir [`../docs/protocole_messages.md`](../docs/protocole_messages.md). L'EMS ([`../flexibilite/ems_serveur.py`](../flexibilite/ems_serveur.py)) tourne sur ce même serveur.
