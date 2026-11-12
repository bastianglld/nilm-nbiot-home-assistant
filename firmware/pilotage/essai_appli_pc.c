/*
 * Essai de l'application complète de la carte sur PC, sans la carte (partie C, pilotage).
 * Le flux envoyé par simulateur_tic.py (--sortie, trames TIC et lignes « MQTT … ») est lu octet par octet comme
 * par l'UART ; ce que la carte enverrait au PC est écrit sur la sortie standard. Le modèle NILM est remplacé
 * par un calcul vide (les messages NILM ont tous des appareils à 0) : seul le pilotage est vérifié ici.
 *
 *   gcc -std=c11 -Iessai_pc -I. -I../nilm_carte -I../tic -I../mesure_vi essai_appli_pc.c pilotage.c ../nilm_carte/appli_nilm.c \
 *       ../nilm_carte/nilm_flux.c ../tic/tic_decodeur.c ../mesure_vi/mesure_vi.c -lm -o essai
 *   ./essai flux.bin
 */
#include <stdio.h>
#include <stdlib.h>
#include "main.h"
#include "appli_nilm.h"
#include "nilm_ia.h"

UART_HandleTypeDef hcom_uart[1];
static FILE *flux;
static int fini;

HAL_StatusTypeDef HAL_UART_Receive(UART_HandleTypeDef *h, uint8_t *o, uint16_t n, uint32_t t)
{
    (void)h; (void)n; (void)t;
    int c = fgetc(flux);
    if (c == EOF) { fini++; return HAL_TIMEOUT; }
    *o = (uint8_t)c;
    return HAL_OK;
}

HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *h, const uint8_t *o, uint16_t n, uint32_t t)
{
    (void)h; (void)t;
    fwrite(o, 1, n, stdout);
    return HAL_OK;
}

void BSP_LED_On(int l) { (void)l; }
void BSP_LED_Off(int l) { (void)l; }
void BSP_LED_Toggle(int l) { (void)l; }
uint32_t HAL_GetTick(void) { return 0; }

int nilm_ia_init(void) { return 0; }
int nilm_ia_calculer(nilm_flux_t *f, uint32_t *duree_us)
{
    static float zero[NILM_NB_SORTIES * NILM_FENETRE];
    nilm_flux_resultat(f, zero, 0);
    if (duree_us) *duree_us = 0;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2 || !(flux = fopen(argv[1], "rb"))) { fprintf(stderr, "usage : %s flux.bin\n", argv[0]); return 1; }
    appli_init();
    while (fini < 3) appli_pas();
    return 0;
}
