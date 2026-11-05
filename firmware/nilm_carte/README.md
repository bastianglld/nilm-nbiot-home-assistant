# NILM sur la carte (partie C)

Fait tourner le modèle NILM int8 (`nilm/notebooks/export_s7/nilm_int8.onnx`) sur la NUCLEO-N657X0-Q à partir d'une puissance mesurée en continu, et produit le message NB-IoT de 15 minutes (`docs/protocole_messages.md`).

```
simulateur TIC (journée UK-DALE, 1 minute simulée par seconde)
  -> décodeur TIC (firmware/tic) : SINSTS + horodate DATE
  -> nilm_flux : moyenne par minute, 272 dernières minutes, fenêtre prête à hh:07, :22, :37, :52
  -> modèle (code généré par ST Edge AI, Cortex-M55)
  -> nilm_flux : énergies du quart d'heure retenu -> « 1615;21;48;0;0;310 »
  -> renvoyé au PC sur le port du ST-LINK : « NILM 1615;21;48;0;0;310 »
```

La mesure tension/courant (`firmware/mesure_vi`) donnera plus tard la même puissance par minute (`mes.s_minute`) : il suffira d'appeler `nilm_flux_mesure` avec elle au lieu du TIC.

| Fichier | Rôle |
|---|---|
| [`nilm_flux.h`](nilm_flux.h), [`nilm_flux.c`](nilm_flux.c) | Moyenne par minute, historique de 272 minutes, entrées (kW, sin et cos de l'heure), sortie -> Wh et message. Portable, sans HAL |
| [`attendu_nilm.py`](attendu_nilm.py) | Messages attendus sur PC pour une journée UK-DALE (même modèle, onnxruntime), et comparaison avec ce qu'a envoyé la carte |
| [`appli_nilm.h`](appli_nilm.h), [`appli_nilm.c`](appli_nilm.c) | Application complète de la carte : source de puissance au choix (`SOURCE_PUISSANCE` : TIC ou mesure V/I), étalonnage (`CAPTEURS_REELS`), NILM, envoi du message par une seule fonction (`envoyer_message`, vers le ST87M01 plus tard) |
| [`nilm_ia.h`](nilm_ia.h), [`nilm_ia.c`](nilm_ia.c) | Appel du modèle généré par ST Edge AI (API legacy, Cortex-M55) : conversion float <-> int8 avec l'échelle lue dans le code généré, durée du calcul |
| [`test_pc.c`](test_pc.c) | Accès au code C depuis Python pour les tests |
| [`validation_carte.md`](validation_carte.md) | Résultats sur la carte : journée UK-DALE complète, comparaison avec le PC |
| [`../nilm_npu/`](../nilm_npu/) | Même chaîne avec le modèle sur le NPU Neural-ART |

Réglages (identiques à `nilm_meta.json`) : fenêtre de 272 minutes, une fenêtre toutes les 15 minutes, minutes 130 à 144 retenues. Les fenêtres finissent à hh:07, :22, :37 et :52 pour que le quart d'heure retenu commence pile à hh:00, :15, :30 ou :45 (retard de 2 h 07 à 2 h 22). Une minute sans mesure est mise à 0 sur les 3 entrées, comme à l'entraînement.

Test : `python -m unittest tests.test_nilm_flux_c` (le code C donne les mêmes messages que la fenêtre glissante du notebook semaine07, à 1 Wh près, y compris avec plusieurs mesures par minute et un trou de 12 minutes).

## Générer le modèle pour le Cortex-M55

Sans l'option `--st-neural-art`, ST Edge AI génère du code pour le processeur seul (quelques dizaines de ms par calcul, pour un calcul toutes les 15 minutes). Le NPU viendra ensuite.

```bash
XC=~/STM32Cube/Repository/Packs/STMicroelectronics/X-CUBE-AI/10.2.0
$XC/Utilities/macarm/stedgeai generate --target stm32n6 --c-api legacy \
    -m ~/Desktop/MASTER/Projet/Modele_IA/export_s7/nilm_int8.onnx --name network \
    --inputs-ch-position chfirst --outputs-ch-position chfirst \
    -o ~/Desktop/MASTER/Projet/04_Carte_mesure_TIC/nilm_ia
```

Résultat (ST Edge AI Core 2.2) : 6,2 M MACC, poids 76 Ko, activations 59 Ko, **entrée et sortie en int8** (entrée : échelle 0,0252, zéro -88 ; sortie : échelle 0,1626, zéro 37). Intégration dans le projet CubeIDE : fichiers `network*.c/h` dans `FSBL/Core`, en-têtes `Middlewares/ST/AI/Inc` et bibliothèque `NetworkRuntime1020_CM55_GCC` ajoutés dans les réglages du projet, pile portée à 16 Ko.

## Essai avec le simulateur

```bash
python simulateur_tic.py envoyer --port /dev/tty.usbmodem102 --ukdale ~/Desktop/MASTER/Projet/Modele_IA/house_1/an1 \
    --jour 2014-01-15 --accel 60 --retour --journal carte.txt
python attendu_nilm.py --ukdale ~/Desktop/MASTER/Projet/Modele_IA/house_1/an1 --jour 2014-01-15 --journal carte.txt
```

Avec `--accel 60`, le simulateur envoie la moyenne de chaque minute UK-DALE (une trame par minute simulée) ; le premier message arrive après 272 trames (environ 4 min 30), puis un toutes les 15 secondes. Choisir un jour de la période de test du modèle (après fin novembre 2013).

## Programme complet de la carte (projet CubeIDE `tic_test`)

`main.c` ne garde que l'initialisation générée par CubeMX et trois appels : `appli_init()` (après le port COM1), `appli_pas()` dans `while (1)`, et `appli_echantillon(tension, courant)` dans l'interruption de l'ADC. Réglages dans `appli_nilm.h` :

| Réglage | Valeur | Effet |
|---|---|---|
| `SOURCE_PUISSANCE` | `SOURCE_TIC` (défaut) | NILM alimenté par les trames TIC (simulateur ou Linky) |
| | `SOURCE_VI` | NILM alimenté par la mesure de la carte ; une ligne `VI hhmm U=… I=… P=… S=… fp=…` par minute ; une trame TIC éventuelle remet l'horloge à l'heure |
| `CAPTEURS_REELS` | 0 (défaut) / 1 | Volts sur le connecteur (GBF) / coefficients de la pince SCT-013 (22 Ω) et de l'adaptateur 230 V → 9 V (pont 100 kΩ / 8,2 kΩ) |
| `DEPART_HORODATE` | `"H261105000000"` | Heure de départ en mode V/I tant que l'heure n'est pas connue |
