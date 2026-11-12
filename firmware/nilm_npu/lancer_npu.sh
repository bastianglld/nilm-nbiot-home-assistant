#!/bin/bash
# Compile l'application NILM_NPU, la charge sur la NUCLEO-N657X0-Q (mode développement) et écrit les poids du modèle
# en flash externe, puis laisse le programme tourner. Ensuite : lancer le simulateur TIC avec --8n1 --retour.
#   ./lancer_npu.sh               première fois sur une carte (écrit aussi les poids)
#   ./lancer_npu.sh --sans-flash  poids déjà écrits sur cette carte
W="$(cd "$(dirname "$0")" && pwd)"
XC="$HOME/STM32Cube/Repository/Packs/STMicroelectronics/X-CUBE-AI/10.2.0"
N6="$XC/scripts/N6_scripts"
PY="$W/../../Modele_IA/.venv/bin/python"
CFG="$W/config_nilm_npu.json"
[ "$1" == "--sans-flash" ] && CFG="$W/config_nilm_npu_sans_flash.json"
"$PY" -c "import serial, intelhex" 2>/dev/null || "$PY" -m pip install -q pyserial intelhex
( cd "$N6" && "$PY" n6_loader.py --n6-loader-config "$CFG" ) 2>&1 | tee "$W/lancer_npu.log"
