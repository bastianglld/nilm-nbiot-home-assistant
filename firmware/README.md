# Firmware de la carte

Responsable : Merveil Joresse N'Goulou Wamena (B) pour le module NB-IoT ST87M01, avec Bastian Guilloud (C) pour la mesure (capteur de courant, interface TIC) et l'intégration du modèle NILM.

Ce dossier accueillera le code de la NUCLEO-N657X0-Q et les tests du module NB-IoT ST87M01 :

- commandes AT et scripts de test du ST87M01 (attachement au réseau, envoi MQTT) ;
- acquisition de la mesure, par Bastian (capteur de courant et prise TIC, voir [`../docs/interface_tic.md`](../docs/interface_tic.md)) ;
- [`tic/`](tic/) : simulateur TIC Linky pour tester le décodeur de la carte sans compteur ;
- appel du modèle NILM toutes les 15 minutes (modèle int8 et paramètres dans [`../nilm/notebooks/export_s7/`](../nilm/notebooks/export_s7/)) ;
- envoi des mesures et décodage du planning reçu (formats dans [`../docs/protocole_messages.md`](../docs/protocole_messages.md)).
