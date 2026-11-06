"""Convertit les poids du modèle NILM pour le NPU (network_atonbuf.AXISRAM3.raw, ST Edge AI) en fichier C.

Les poids sont au début de l'AXISRAM3 (0x34200000), suivis des entrées, sorties et calculs intermédiaires :
seule la partie non nulle est gardée, la carte remet le reste à zéro au démarrage (nilm_ia_npu.c).

    python raw_vers_c.py sortie/network_atonbuf.AXISRAM3.raw nilm_npu_poids.c
"""
import sys

ADRESSE = 0x34200000          # début du pool npuRAM3 dans nilm_interne.mpool


def main(source, destination):
    d = open(source, "rb").read()
    n = (len(d.rstrip(b"\0")) + 31) // 32 * 32
    lignes = ["  " + ", ".join("0x%02x" % x for x in d[i:i + 16]) + "," for i in range(0, n, 16)]
    open(destination, "w").write(f"""/*
 * Poids du modèle NILM pour le NPU (partie C) – généré par nilm_npu/interne/raw_vers_c.py
 * à partir de {source.split('/')[-1]} (ST Edge AI 2.2, profil nilm-interne).
 * Attendus à l'adresse 0x{ADRESSE:08X} (AXISRAM3) : nilm_ia_npu.c les y recopie au démarrage.
 * Zone utilisée : {len(d)} octets, dont {n} de poids (le reste est remis à zéro par la carte).
 */
#include <stdint.h>

const uint32_t nilm_npu_poids_adresse = 0x{ADRESSE:08X}UL;
const uint32_t nilm_npu_poids_taille = {n};
const uint8_t nilm_npu_poids[{n}] __attribute__((aligned(32))) = {{
""" + "\n".join(lignes) + "\n};\n")
    print(f"{n} octets de poids sur {len(d)} -> {destination}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
