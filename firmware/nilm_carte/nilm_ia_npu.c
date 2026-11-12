/*
 * Modèle NILM exécuté par le NPU Neural-ART (partie C) – même interface que nilm_ia.c (processeur), voir nilm_ia.h.
 *
 * Code du modèle : npu/network_npu.c, généré par ST Edge AI 2.2 avec le profil « nilm-interne »
 * (nilm_npu/interne) : tout tient dans l'AXISRAM3, mémoire du NPU – poids au début (23 Ko, recopiés ici depuis
 * npu/nilm_npu_poids.c), puis entrées, sorties et calculs intermédiaires (59,5 Ko). Pas de mémoire externe.
 * Moteur : LL_ATON (X-CUBE-AI 10.2, dossier npu), comme dans le projet nilm_npu validé le 5 novembre.
 */
#include "nilm_ia.h"
#if NILM_SUR_NPU
#include <math.h>
#include <string.h>
#include "main.h"
#include "npu/ll_aton_runtime.h"
#include "npu/mcu_cache.h"
#include "npu/npu_rif.h"

LL_ATON_DECLARE_NAMED_NN_INSTANCE_AND_INTERFACE(Default);

extern const uint32_t nilm_npu_poids_adresse, nilm_npu_poids_taille;
extern const uint8_t nilm_npu_poids[];

#define NPU_ZONE_OCTETS 84512u              /* zone utilisée dans l'AXISRAM3 (rapport de ST Edge AI) */

static const LL_Buffer_InfoTypeDef *entree_npu, *sortie_npu;
static float sortie[NILM_NB_SORTIES * NILM_FENETRE];
static int pret = 0;
volatile int32_t nilm_npu_etape;
volatile uint32_t nilm_npu_tours, nilm_npu_bloque;  /* diagnostic du calcul */
volatile int32_t nilm_npu_dernier_r;           /* dernière étape atteinte au démarrage (diagnostic) */

int nilm_ia_init(void)
{
    nilm_npu_etape = 1;
    npu_materiel_init();                                   /* RAM du NPU, horloge, droits d'accès */

    /* poids à leur place : zone remise à zéro puis copie (la RAM du NPU n'est pas initialisée à l'allumage) */
    nilm_npu_etape = 2;
    uint8_t *zone = (uint8_t *)nilm_npu_poids_adresse;
    memset(zone, 0, NPU_ZONE_OCTETS);
    memcpy(zone, nilm_npu_poids, nilm_npu_poids_taille);
    if (memcmp(zone, nilm_npu_poids, nilm_npu_poids_taille) != 0) return -5;
    mcu_cache_clean_range((uint32_t)zone, (uint32_t)zone + NPU_ZONE_OCTETS);   /* le NPU lit la RAM, pas le cache */

    nilm_npu_etape = 3;
    entree_npu = LL_ATON_Input_Buffers_Info_Default();
    sortie_npu = LL_ATON_Output_Buffers_Info_Default();
    if (!entree_npu || !sortie_npu || !entree_npu[0].name || !sortie_npu[0].name) return -1;
    if (LL_Buffer_len(&entree_npu[0]) != NILM_NB_ENTREES * NILM_FENETRE) return -2;      /* int8 [1,3,272] */
    if (LL_Buffer_len(&sortie_npu[0]) != NILM_NB_SORTIES * NILM_FENETRE) return -3;      /* int8 [1,8,272] */
    if (entree_npu[0].chpos != CHPos_First || sortie_npu[0].chpos != CHPos_First) return -4;

    nilm_npu_etape = 4;
    LL_ATON_RT_RuntimeInit();
    nilm_npu_etape = 5;
    LL_ATON_RT_Init_Network(&NN_Instance_Default);

    /* compteur de cycles du processeur, pour mesurer la durée du calcul */
#if defined(DCB)
    DCB->DEMCR |= DCB_DEMCR_TRCENA_Msk;
#else
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
#endif
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    nilm_npu_etape = 6;
    pret = 1;
    return 0;
}

int nilm_ia_calculer(nilm_flux_t *f, uint32_t *duree_us)
{
    if (!pret) return -1;
    const float e_echelle = entree_npu[0].scale[0];
    const int e_zero = entree_npu[0].offset[0];
    const float s_echelle = sortie_npu[0].scale[0];
    const int s_zero = sortie_npu[0].offset[0];
    int8_t *in = (int8_t *)LL_Buffer_addr_start(&entree_npu[0]);
    uint32_t t0 = DWT->CYCCNT;

    /* entrée : float -> int8, même ordre [canal][minute] que sur le processeur */
    for (int i = 0; i < NILM_NB_ENTREES * NILM_FENETRE; i++) {
        long v = lrintf(f->entree[i] / e_echelle) + e_zero;
        in[i] = (int8_t)(v < -128 ? -128 : v > 127 ? 127 : v);
    }
    mcu_cache_clean_range((uint32_t)LL_Buffer_addr_start(&entree_npu[0]), (uint32_t)LL_Buffer_addr_end(&entree_npu[0]));

    LL_ATON_RT_Reset_Network(&NN_Instance_Default);
    LL_ATON_RT_RetValues_t r;
    nilm_npu_tours = 0;
    do {
        r = LL_ATON_RT_RunEpochBlock(&NN_Instance_Default);
        nilm_npu_tours++;
        nilm_npu_dernier_r = (int32_t)r;
        /* Pas de WFE ici : en veille, le processeur coupait l'horloge du NPU et de sa RAM, et le calcul ne
           finissait jamais (essai du 6 novembre). On attend en boucle : quelques millisecondes seulement. */
        if (DWT->CYCCNT - t0 > SystemCoreClock) {          /* plus d'une seconde : le NPU ne répond plus */
            nilm_npu_bloque++;
            pret = 0;                                      /* NPU abandonné jusqu'au prochain redémarrage */
            return -10;
        }
    } while (r != LL_ATON_RT_DONE);

    mcu_cache_invalidate_range((uint32_t)LL_Buffer_addr_start(&sortie_npu[0]), (uint32_t)LL_Buffer_addr_end(&sortie_npu[0]));
    const int8_t *out = (const int8_t *)LL_Buffer_addr_start(&sortie_npu[0]);
    for (int i = 0; i < NILM_NB_SORTIES * NILM_FENETRE; i++)
        sortie[i] = (float)(out[i] - s_zero) * s_echelle;
    nilm_flux_resultat(f, sortie, 0);

    if (duree_us) *duree_us = (DWT->CYCCNT - t0) / (SystemCoreClock / 1000000u);
    return 0;
}

#endif /* NILM_SUR_NPU */
