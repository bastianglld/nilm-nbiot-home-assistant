# Home Assistant

Responsable : Mathieu Hegoburu (A).

Ce dossier accueillera la configuration MQTT de Home Assistant (capteurs par appareil, tableau Énergie) et les automatisations :

- capteurs sur `nilm/maison/etat` : énergie par appareil et totale, par quart d'heure ;
- capteur sur `nilm/maison/conseils` : conseils de l'EMS, envoyés en notification sur l'application Companion.

Formats des messages : [`../docs/protocole_messages.md`](../docs/protocole_messages.md).
