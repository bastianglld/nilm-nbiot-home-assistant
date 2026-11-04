# Firmware de la carte

Responsable : Merveil Joresse N'Goulou Wamena (B) pour le module NB-IoT ST87M01, avec Bastian Guilloud (C) pour la mesure (capteur de courant, interface TIC) et l'intégration du modèle NILM.

## Ce qui existe déjà

| Dossier | Contenu | Auteur |
|---|---|---|
| [`tests_st87m01/`](tests_st87m01/) | Procédure du premier jour du kit ([`jour1_kit.md`](tests_st87m01/jour1_kit.md)), script qui l'automatise depuis le PC ([`test_jour1.py`](tests_st87m01/test_jour1.py)) et faux module pour l'essayer sans le kit | Merveil (B) |
| [`tic/`](tic/) | Simulateur TIC Linky pour tester le décodeur de la carte sans compteur | Bastian (C) |

## Ce qui arrive

Ce dossier accueillera aussi le code de la NUCLEO-N657X0-Q :

- pilote AT du ST87M01 sur le STM32 (la même séquence que `test_jour1.py`, en C), par Merveil ;
- acquisition de la mesure, par Bastian (capteur de courant et prise TIC, voir [`../docs/interface_tic.md`](../docs/interface_tic.md)) ;
- appel du modèle NILM toutes les 15 minutes (modèle int8 et paramètres dans [`../nilm/notebooks/export_s7/`](../nilm/notebooks/export_s7/)) ;
- envoi des mesures et décodage du planning reçu (formats dans [`../docs/protocole_messages.md`](../docs/protocole_messages.md)).
