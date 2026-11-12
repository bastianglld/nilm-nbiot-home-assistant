# Firmware de la carte

Responsable : Merveil Joresse N'Goulou Wamena (B) pour le module NB-IoT ST87M01, avec Bastian Guilloud (C) pour la mesure (capteur de courant, interface TIC) et l'intégration du modèle NILM.

## Ce qui existe déjà

| Dossier | Contenu | Auteur |
|---|---|---|
| [`tests_st87m01/`](tests_st87m01/) | Procédure du premier jour du kit ([`jour1_kit.md`](tests_st87m01/jour1_kit.md)), script qui l'automatise depuis le PC ([`test_jour1.py`](tests_st87m01/test_jour1.py)) et faux module pour l'essayer sans le kit | Merveil (B) |
| [`tic/`](tic/) | Simulateur TIC Linky pour tester le décodeur de la carte sans compteur | Bastian (C) |
| [`mesure_vi/`](mesure_vi/) | Calcul de Vrms, Irms, P, S et facteur de puissance à partir de l'ADC (pince et adaptateur secteur), validé au générateur | Bastian (C) |
| [`nilm_carte/`](nilm_carte/) | Programme complet de la carte : source TIC ou mesure V/I, NILM (processeur ou NPU) toutes les 15 minutes, message par une seule fonction d'envoi ; référence PC et validations | Bastian (C) |
| [`nilm_npu/`](nilm_npu/) | Modèle NILM sur le NPU Neural-ART : projet de validation d'ST adapté, puis génération sans mémoire externe pour le programme complet | Bastian (C) |

## Ce qui arrive

Ce dossier accueillera aussi le code de la NUCLEO-N657X0-Q :

- pilote AT du ST87M01 sur le STM32 (la même séquence que `test_jour1.py`, en C), par Merveil ;
- branchement de la pince SCT-013 et de l'adaptateur 9 V sur la mesure V/I déjà validée au générateur, par Bastian ;
- envoi des mesures et décodage du planning reçu (formats dans [`../docs/protocole_messages.md`](../docs/protocole_messages.md)).
