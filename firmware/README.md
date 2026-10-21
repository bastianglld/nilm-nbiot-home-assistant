# Firmware de la carte

Responsable : Merveille-Joresse Ngoulou-Wamena (B), avec Bastian Guilloud (C) pour l'intégration du modèle NILM.

Ce dossier accueillera le code de la NUCLEO-N657X0-Q et les tests du module NB-IoT ST87M01 :

- commandes AT et scripts de test du ST87M01 (attachement au réseau, envoi MQTT) ;
- acquisition de la mesure (capteur de courant et prise TIC, voir [`../docs/interface_tic.md`](../docs/interface_tic.md)) ;
- appel du modèle NILM toutes les 15 minutes (modèle int8 et paramètres dans [`../nilm/notebooks/export_s7/`](../nilm/notebooks/export_s7/)) ;
- envoi des mesures et décodage du planning reçu (formats dans [`../docs/protocole_messages.md`](../docs/protocole_messages.md)).
