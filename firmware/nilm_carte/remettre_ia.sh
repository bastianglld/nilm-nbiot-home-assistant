#!/bin/sh
# CubeMX efface tic_test/Middlewares à chaque « Generate Code » : remet la bibliothèque du modèle NILM.
cd "$(dirname "$0")" && mkdir -p Middlewares/ST && { [ -d Middlewares/ST/AI ] && echo "déjà en place" || { cp -R sauvegardes/AI_middleware Middlewares/ST/AI && echo "Middlewares/ST/AI remis"; }; }
