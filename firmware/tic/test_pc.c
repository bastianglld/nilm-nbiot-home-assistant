/*
 * Test du décodeur TIC sur PC, sans carte : lit un fichier de trames produit par le simulateur
 *     python simulateur_tic.py envoyer --sortie trames.bin --nb 20 --erreurs 10
 * Compilation et lancement :
 *     gcc -Wall -Wextra -std=c11 -o test_pc test_pc.c tic_decodeur.c && ./test_pc trames.bin
 */
#include <stdio.h>
#include "tic_decodeur.h"

static const char *nom_couleur(tic_couleur_t c)
{
    static const char *n[] = { "-", "BLEU", "BLANC", "ROUGE" };
    return n[c & 3];
}

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage : %s fichier_trames\n", argv[0]); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 2; }

    tic_t tic;
    tic_init(&tic);
    int c;
    while ((c = fgetc(f)) != EOF) {
        tic_resultat_t r = tic_octet(&tic, (uint8_t)c);
        if (r == TIC_RIEN) continue;
        printf("%-7s %s S=%5lu VA  I=%3u A  U=%3u V  index=%9lu Wh  tarif=%-12s jour=%-5s demain=%-5s %s\n",
               r == TIC_TRAME_OK ? "OK" : "ERREUR",
               tic.mode == TIC_MODE_STANDARD ? "std " : "hist",
               (unsigned long)tic.papp_va, tic.irms_a, tic.urms_v, (unsigned long)tic.index_total_wh,
               tic.tarif, nom_couleur(tic.couleur_jour), nom_couleur(tic.couleur_demain), tic.horodate);
    }
    fclose(f);
    printf("\ntrames valides %lu | avec ligne rejetée %lu | interrompues %lu | lignes rejetées %lu\n",
           (unsigned long)tic.trames_ok, (unsigned long)tic.trames_erreur,
           (unsigned long)tic.trames_interrompues, (unsigned long)tic.lignes_rejetees);
    return 0;
}
