/*
 * Mesure tension / courant pour le NILM (partie C) : Vrms, Irms, P, S, facteur de puissance,
 * puis moyennes sur la minute (entrée du modèle NILM).
 *
 * Portable : aucune dépendance au HAL. On appelle mesure_echantillon() à chaque couple
 * (tension, courant) lu par l'ADC, à fréquence fixe (4 kHz conseillé, soit 80 points par période).
 *
 * La composante continue (VMID) est retirée par le calcul : on n'a pas besoin de connaître
 * sa valeur exacte, ni de la mesurer à part.
 *     Vrms² = moyenne(v²) - moyenne(v)²        P = moyenne(v·i) - moyenne(v)·moyenne(i)
 */
#ifndef MESURE_VI_H
#define MESURE_VI_H

#include <stdint.h>

typedef struct {
    /* réglages */
    uint32_t n_par_bloc;      /* échantillons par bloc : un multiple de la période (4000 à 4 kHz = 1 s = 50 périodes) */
    float    k_v;             /* volts réels par point ADC (voie tension) */
    float    k_i;             /* ampères réels par point ADC (voie courant) */
    uint32_t blocs_par_minute;/* 60 avec des blocs d'une seconde */

    /* résultats du dernier bloc */
    float vrms, irms;         /* V, A */
    float p, s, fp;           /* W, VA, facteur de puissance P/S */
    float v_moy_brut, i_moy_brut; /* composante continue en points ADC (≈ VMID), pour vérifier le montage */
    uint16_t v_min, v_max, i_min, i_max; /* extrêmes en points ADC : saturation si proche de 0 ou 4095 */

    /* résultats de la dernière minute complète */
    float p_minute, s_minute; /* W, VA moyens sur la minute */

    /* compteurs */
    uint32_t blocs, minutes;

    /* interne */
    uint32_t n;
    int64_t  sv, si, svv, sii, svi;
    uint16_t vmin, vmax, imin, imax;
    uint32_t nb_min;
    float    sp_min, ss_min;
} mesure_vi_t;

#define MESURE_RIEN    0
#define MESURE_BLOC    1   /* nouveau bloc : vrms, irms, p, s, fp à jour */
#define MESURE_MINUTE  2   /* nouveau bloc ET nouvelle minute : p_minute, s_minute à jour */

void mesure_init(mesure_vi_t *m, uint32_t n_par_bloc, float k_v, float k_i, uint32_t blocs_par_minute);
int  mesure_echantillon(mesure_vi_t *m, uint16_t v_brut, uint16_t i_brut);

#endif
