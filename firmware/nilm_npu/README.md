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

Premiers résultats (5 novembre 2026) : **2,15 à 2,19 ms par calcul** (conversion des entrées et sorties comprise), contre 62 ms sur le Cortex-M55 ; premiers messages identiques à ceux du processeur (`0215;20;0;0;0;68`, `0230;26;0;0;0;76`).
