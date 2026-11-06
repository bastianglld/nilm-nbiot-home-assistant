# NILM sur le NPU Neural-ART (partie C)

Même chaîne que [`../nilm_carte`](../nilm_carte) (décodeur TIC → `nilm_flux` → modèle → message de 15 minutes), mais le modèle est exécuté par l'accélérateur **Neural-ART** de la NUCLEO-N657X0-Q au lieu du Cortex-M55.

Le projet est une copie de l'application **NPU_Validation** de X-CUBE-AI 10.2 (celle qui a validé le modèle sur le NPU en semaine 7) : horloges, mémoires du NPU, flash externe des poids et droits d'accès y sont déjà réglés. Seul l'appel final de `main.c` change.

| Fichier | Rôle |
|---|---|
| [`nilm_npu.c`](nilm_npu.c), [`nilm_npu.h`](nilm_npu.h) | Application : USART1 à 9 600 bauds 8N1, décodeur TIC, `nilm_flux`, inférence LL_ATON (`LL_ATON_RT_RunEpochBlock`), message `NILM hhmm;… t=<µs>us` |
| [`lancer_npu.sh`](lancer_npu.sh) | Compile, charge la carte (mode développement) et écrit les poids en flash externe avec `n6_loader.py` de ST |
| `config_nilm_npu*.json` | Configuration de `n6_loader.py` (avec ou sans écriture des poids) |

## Construire le projet

1. Copier `Projects/STM32N6570-DK/Applications/NPU_Validation` (pack X-CUBE-AI) en `NILM_NPU`, avec un lien `Middlewares` vers celui du pack à la racine.
2. `Core/Src/main.c` : remplacer `aiValidationInit(); aiValidationProcess();` par `nilm_npu_app();` en gardant le texte `aiValidationInit();` en commentaire sur la même ligne (`n6_loader.py` y place son point d'arrêt).
3. `armgcc/Makefile` : `PROJECT_PATH = $(BASE_PATH)/Applications/NILM_NPU` ; remplacer les sources de validation par `Core/Src/nilm_npu.c`, `tic_decodeur.c`, `nilm_flux.c` (garder `network.c`) ; retirer `ai_wrapper_ATON.c`, `aiValidation_ATON.c` et `ai_io_buffers_ATON.c`.
4. Copier `nilm_npu.*`, `tic_decodeur.*` et `nilm_flux.*` dans `Core/Src` et `Core/Inc`.
5. Code du modèle : `stedgeai generate --target stm32n6 --st-neural-art n6-allmems-O3@…/user_neuralart.json -m nilm_int8.onnx` (même commande qu'en semaine 7).

## Essai

```bash
./lancer_npu.sh                  # première fois sur une carte (écrit aussi les poids)
python simulateur_tic.py envoyer --port /dev/tty.usbmodem102 --ukdale ../Modele_IA/house_1/an1 \
    --jour 2014-01-15 --accel 60 --retour --journal carte.txt --8n1
```

Résultats sur une journée complète (5 novembre 2026) : **78 messages sur 78, 2,155 ms par calcul** (conversion des entrées et sorties comprise), contre 62 ms sur le Cortex-M55 ; total identique au PC, 58 messages identiques au PC à 1 Wh près. Détail : [`../nilm_carte/validation_carte.md`](../nilm_carte/validation_carte.md).

## Version sans mémoire externe, intégrée au programme complet

Le dossier [`interne/`](interne/) régénère le modèle avec tout en RAM interne :

| Fichier | Rôle |
|---|---|
| [`interne/nilm_interne.mpool`](interne/nilm_interne.mpool) | Carte mémoire pour ST Edge AI : AXISRAM1 (624 Ko) et RAM du NPU (AXISRAM3 à 6) ; AXISRAM2 exclue (programme FSBL), pas de flash ni de RAM externes |
| [`interne/nilm_neuralart.json`](interne/nilm_neuralart.json) | Profil `nilm-interne` (mêmes options du compilateur Neural-ART que `n6-allmems-O3`) |
| [`interne/generer.sh`](interne/generer.sh) | `stedgeai generate --target stm32n6 --st-neural-art nilm-interne@…` |
| [`interne/raw_vers_c.py`](interne/raw_vers_c.py) | Poids (`network_atonbuf.AXISRAM3.raw`) vers un tableau C, recopié dans l'AXISRAM3 au démarrage |
| [`interne/rapport_generation.txt`](interne/rapport_generation.txt) | Rapport de ST Edge AI : 23 Ko de poids et 59,5 Ko d'activations dans npuRAM3, 54 étapes dont 16 en logiciel |

Le compilateur a tout placé dans npuRAM3 (la plus rapide). Intégration et résultats : [`../nilm_carte/README.md`](../nilm_carte/README.md#nilm-sur-le-npu-dans-le-programme-complet-nilm_sur_npu-1) et [`../nilm_carte/validation_carte.md`](../nilm_carte/validation_carte.md) — 25 messages identiques au caractère près à ceux de ce projet, 6 ms par calcul (NPU à 300 MHz).
