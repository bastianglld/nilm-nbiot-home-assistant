#!/bin/bash
# Installe l'EMS (flexibilite/ems_serveur.py) sur le serveur du broker (Ubuntu 24.04, voir cloud/README.md).
#
#   sudo bash installer-ems.sh            (depuis une copie du dépôt sur le serveur)
#
# Relancer le même script après une mise à jour du dépôt : il remplace le programme et garde l'historique,
# les prix et le mot de passe. Le mot de passe du compte « ems » du broker est demandé une seule fois
# (il a été affiché par cloud/broker-vps/installer-broker.sh) et rangé dans /etc/ems/ems.env.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$ICI/../ems_serveur.py"
DOSSIER=/opt/ems
CONFIG=/etc/ems/ems.env

[ "$(id -u)" -eq 0 ] || { echo "À lancer avec sudo : sudo bash $0"; exit 1; }
[ -f "$SOURCE" ] || { echo "ems_serveur.py introuvable à côté de ce dossier ($SOURCE)"; exit 1; }
command -v mosquitto >/dev/null || echo "Attention : Mosquitto n'est pas installé ici (cloud/broker-vps/installer-broker.sh)."

echo "1. Compte système et dossiers"
id ems >/dev/null 2>&1 || useradd --system --home-dir "$DOSSIER" --shell /usr/sbin/nologin ems
install -d -o ems -g ems -m 750 "$DOSSIER" "$DOSSIER/prix"
install -d -o root -g ems -m 750 /etc/ems

echo "2. Python et bibliothèques (numpy, pandas, paho-mqtt)"
apt-get install -y -q python3-venv >/dev/null
[ -x "$DOSSIER/venv/bin/python" ] || python3 -m venv "$DOSSIER/venv"
"$DOSSIER/venv/bin/pip" install -q --upgrade pip
"$DOSSIER/venv/bin/pip" install -q "numpy" "pandas" "paho-mqtt>=2.0" "certifi"
install -o ems -g ems -m 640 "$SOURCE" "$DOSSIER/ems_serveur.py"

echo "3. Réglages ($CONFIG)"
if [ ! -f "$CONFIG" ]; then
    read -r -s -p "   Mot de passe du compte « ems » du broker : " MDP; echo
    read -r -p "   Offre pour le planning (Base, HP/HC, Tempo, Dynamique) [Tempo] : " OFFRE
    read -r -p "   Offre actuelle du foyer (Base, HP/HC, Tempo) [Base] : " ACTUELLE
    umask 077
    printf 'MQTT_PASSWORD=%s\nEMS_OFFRE=%s\nEMS_OFFRE_ACTUELLE=%s\n' "$MDP" "${OFFRE:-Tempo}" "${ACTUELLE:-Base}" > "$CONFIG"
    chown root:ems "$CONFIG"; chmod 640 "$CONFIG"
else
    echo "   déjà présent, gardé tel quel"
fi

echo "4. Services systemd"
install -m 644 "$ICI"/ems-enregistreur.service "$ICI"/ems-planning.service "$ICI"/ems-planning.timer \
    "$ICI"/ems-analyse.service "$ICI"/ems-analyse.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ems-planning.timer ems-analyse.timer
systemctl enable ems-enregistreur.service
systemctl restart ems-enregistreur.service

sleep 3
echo
systemctl --no-pager --lines=5 status ems-enregistreur.service || true
echo
systemctl --no-pager list-timers 'ems-*'
echo
echo "EMS installé. Historique : $DOSSIER/historique.csv"
echo "Journal en direct : journalctl -u ems-enregistreur -f"
echo "Planning tout de suite (test) : sudo systemctl start ems-planning.service && journalctl -u ems-planning -n 20"
