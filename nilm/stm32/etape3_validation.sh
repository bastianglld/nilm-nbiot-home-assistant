#!/bin/bash
# Étape 3 seule : envoie les 20 fenêtres à la carte (le programme doit déjà tourner : NE PAS débrancher la carte avant)
W="$(cd "$(dirname "$0")" && pwd)"
XC="$HOME/STM32Cube/Repository/Packs/STMicroelectronics/X-CUBE-AI/10.2.0"
STAI="$XC/Utilities/macarm/stedgeai"
PROFIL="n6-allmems-O3@$XC/scripts/N6_scripts/user_neuralart.json"
PORT="$(ls /dev/tty.usbmodem* 2>/dev/null | head -1)"
[ -n "$PORT" ] || { echo "Carte non détectée"; exit 1; }
echo "port de la carte : $PORT"
cd "$W"
"$STAI" validate --target stm32n6 --mode target --st-neural-art "$PROFIL" -m nilm_int8.onnx \
    -vi validation_nilm.npz -d "serial:$PORT:921600" --output st_ai_output --workspace st_ai_ws \
    2>&1 | tee resultat_validation_carte.txt
