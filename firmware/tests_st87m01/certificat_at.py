"""Prépare la commande AT qui charge un certificat racine dans le ST87M01 (TLS, partie B).

Le module n'accepte que des certificats ECDSA (P-256 ou P-384), au format DER, donnés en
hexadécimal dans AT#TLSCERTADD (note d'application ST87MXX_TLS, § 4 et 5.3). Ce script lit
un certificat PEM (ou DER), vérifie qu'il est bien en ECDSA, et écrit la commande complète.

    python certificat_at.py root-ye.pem
    python certificat_at.py root-ye.pem --profil 0 --sortie commande_certificat.txt

Ensuite, dans la console : coller la commande, attendre OK, puis AT#RESET=1 pour l'enregistrer.
Un certificat racine est public : il n'y a rien de secret dans la commande produite.
"""

import argparse
import base64
import sys
from pathlib import Path

OID_ECDSA = bytes.fromhex("2a8648ce3d0201")   # id-ecPublicKey
OID_RSA = bytes.fromhex("2a864886f70d010101")  # rsaEncryption
COURBES = {bytes.fromhex("2a8648ce3d030107"): "P-256", bytes.fromhex("2b81040022"): "P-384",
           bytes.fromhex("2b2403030208010107"): "brainpoolP256r1",
           bytes.fromhex("2b240303020801010b"): "brainpoolP384r1"}
TYPE_RACINE = 1  # <type> = 1 : certificat de l'autorité racine (CA root)


def lire_der(chemin):
    """Renvoie le premier certificat du fichier, en DER (accepte PEM ou DER)."""
    brut = Path(chemin).read_bytes()
    if b"-----BEGIN CERTIFICATE-----" in brut:
        texte = brut.decode("ascii", "ignore")
        corps = texte.split("-----BEGIN CERTIFICATE-----", 1)[1].split("-----END CERTIFICATE-----", 1)[0]
        return base64.b64decode("".join(corps.split()))
    return brut


def type_de_cle(der):
    """'ECDSA P-256', 'RSA' ou None, d'après les identifiants d'algorithme présents dans le certificat."""
    if OID_ECDSA in der:
        courbe = next((nom for oid, nom in COURBES.items() if oid in der), "courbe inconnue")
        return f"ECDSA {courbe}"
    if OID_RSA in der:
        return "RSA"
    return None


def commande(der, profil=0):
    return f"AT#TLSCERTADD={profil},{TYPE_RACINE},{len(der)},{der.hex()}"


def main(argv=None):
    p = argparse.ArgumentParser(description="Écrit la commande AT#TLSCERTADD pour un certificat racine.")
    p.add_argument("certificat", help="fichier .pem ou .der du certificat racine (Root YE ou ISRG Root X2)")
    p.add_argument("--profil", type=int, default=0, help="profil de sécurité du module (0 par défaut)")
    p.add_argument("--sortie", help="écrire aussi la commande dans ce fichier")
    o = p.parse_args(argv)
    der = lire_der(o.certificat)
    if der[:1] != b"\x30":
        print("Ce fichier ne ressemble pas à un certificat (PEM ou DER).")
        return 2
    cle = type_de_cle(der)
    if cle != "ECDSA P-256" and cle != "ECDSA P-384" and not (cle or "").startswith("ECDSA brainpool"):
        print(f"Certificat refusé : clé {cle or 'inconnue'}. Le ST87M01 n'accepte que l'ECDSA (P-256, P-384).")
        return 1
    ligne = commande(der, o.profil)
    print(f"Certificat {cle}, {len(der)} octets. Commande à envoyer, puis AT#RESET=1 :\n")
    print(ligne)
    if o.sortie:
        Path(o.sortie).write_text(ligne + "\n", encoding="ascii")
        print(f"\nCommande écrite dans {o.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
