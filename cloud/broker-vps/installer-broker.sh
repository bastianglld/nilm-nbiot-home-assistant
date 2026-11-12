#!/bin/bash
# Installe le broker Mosquitto du projet NILM sur le VPS Azure (Ubuntu 24.04).
# Usage : sudo bash installer-broker.sh mon-broker.exemple.com
# (sur Azure : portail > VM > Exécuter la commande > RunShellScript, en fixant DOMAINE ci-dessous)
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

DOMAINE="${1:?Donne le nom DNS public du serveur, ex : sudo bash installer-broker.sh mon-broker.exemple.com}"

# 1. Paquets
apt-get update
apt-get install -y mosquitto mosquitto-clients certbot

# 2. Certificat Let's Encrypt (utilise le port 80 le temps de la vérification)
certbot certonly --standalone -d "$DOMAINE" --non-interactive --agree-tos --register-unsafely-without-email

# Mosquitto ne peut pas lire /etc/letsencrypt : on copie les fichiers à chaque renouvellement
cat > /etc/letsencrypt/renewal-hooks/deploy/mosquitto.sh <<EOF
#!/bin/bash
mkdir -p /etc/mosquitto/certs
cp /etc/letsencrypt/live/$DOMAINE/fullchain.pem /etc/mosquitto/certs/
cp /etc/letsencrypt/live/$DOMAINE/privkey.pem /etc/mosquitto/certs/
chown mosquitto:mosquitto /etc/mosquitto/certs/*.pem
chmod 600 /etc/mosquitto/certs/privkey.pem
systemctl restart mosquitto
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/mosquitto.sh
/etc/letsencrypt/renewal-hooks/deploy/mosquitto.sh || true

# 3. Configuration
cat > /etc/mosquitto/conf.d/nilm.conf <<'EOF'
per_listener_settings false
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl

# Clients du serveur lui-même (EMS, tests) : non exposé sur Internet
listener 1883 127.0.0.1

# Internet : carte NB-IoT et Home Assistant, TLS obligatoire
listener 8883
certfile /etc/mosquitto/certs/fullchain.pem
keyfile  /etc/mosquitto/certs/privkey.pem
tls_version tlsv1.2
EOF

cat > /etc/mosquitto/acl <<'EOF'
# Droits par compte : voir docs/protocole_messages.md

# Home Assistant : découverte MQTT, lit toutes les données, envoie les ordres aux relais
user homeassistant
topic readwrite homeassistant/#
topic read nilm/#
topic write nilm/maison/cmd/+

# Carte NB-IoT : publie mesures, présence et état des relais, lit ses ordres et le planning
user module_nbiot
topic write nilm/maison/etat
topic write nilm/maison/dispo
topic read nilm/maison/cmd/+
topic write nilm/maison/cmd/+/etat

# EMS (flexibilite/ems_serveur.py) : lit les mesures, publie le planning et les conseils
user ems
topic read nilm/maison/etat
topic write nilm/maison/cmd/plan
topic write nilm/maison/conseils

# Simulateur sur PC (à supprimer quand la carte tourne)
user simulateur
topic write nilm/maison/etat
topic write nilm/maison/dispo
topic write nilm/maison/cmd/+/etat
topic write homeassistant/#
EOF

# 4. Comptes, mots de passe aléatoires
rm -f /etc/mosquitto/passwd
touch /etc/mosquitto/passwd && chmod 600 /etc/mosquitto/passwd
echo
echo "===== MOTS DE PASSE (à noter, ils ne seront plus affichés) ====="
for u in homeassistant module_nbiot ems simulateur; do
  p=$(openssl rand -base64 18 | tr -d '/+=')
  mosquitto_passwd -b /etc/mosquitto/passwd "$u" "$p"
  echo "$u : $p"
done
echo "================================================================="
chown mosquitto:mosquitto /etc/mosquitto/passwd /etc/mosquitto/acl
chmod 600 /etc/mosquitto/passwd

systemctl enable mosquitto
systemctl restart mosquitto
systemctl --no-pager status mosquitto | head -5
echo
echo "Broker prêt sur mqtts://$DOMAINE:8883"
