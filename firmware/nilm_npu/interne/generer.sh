#!/bin/bash
# Génère le code du modèle NILM pour le NPU avec TOUT en mémoire interne :
#   poids dans l'AXISRAM1 (0x34064000), calculs dans les RAM du NPU (AXISRAM3 à 6).
# Plus besoin de la flash externe ni de n6_loader.py : les poids sont chargés avec le programme.
W="$(cd "$(dirname "$0")" && pwd)"
XC="$HOME/STM32Cube/Repository/Packs/STMicroelectronics/X-CUBE-AI/10.2.0"
STAI="$XC/Utilities/macarm/stedgeai"
MODELE="$W/../../../Modele_IA/STM32/n6_validation/nilm_int8.onnx"
cd "$W" && "$STAI" generate --target stm32n6 --st-neural-art "nilm-interne@$W/nilm_neuralart.json" \
    -m "$MODELE" --output sortie --workspace ws 2>&1 | tee generer.log
echo; ls -la sortie
