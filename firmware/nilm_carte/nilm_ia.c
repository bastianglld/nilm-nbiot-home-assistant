/* Appel du modèle NILM généré par ST Edge AI – voir nilm_ia.h */
#include "nilm_ia.h"
#include <math.h>
#include "main.h"            /* CMSIS : DWT, SystemCoreClock */
#include "network.h"
#include "network_data.h"

static ai_handle reseau = AI_HANDLE_NULL;
AI_ALIGNED(32) static ai_u8 activations[AI_NETWORK_DATA_ACTIVATIONS_SIZE];
static float sortie[NILM_NB_SORTIES * NILM_FENETRE];
static ai_buffer *entree_ai, *sortie_ai;
static float e_echelle, s_echelle;
static int e_zero, s_zero;

int nilm_ia_init(void)
{
    const ai_handle acts[] = { activations };
    ai_error err = ai_network_create_and_init(&reseau, acts, NULL);
    if (err.type != AI_ERROR_NONE) return -1;
    entree_ai = ai_network_inputs_get(reseau, NULL);
    sortie_ai = ai_network_outputs_get(reseau, NULL);
    if (!entree_ai || !sortie_ai) return -2;
    if (entree_ai[0].size != NILM_NB_ENTREES * NILM_FENETRE || sortie_ai[0].size != NILM_NB_SORTIES * NILM_FENETRE)
        return -3;
    e_echelle = AI_BUFFER_META_INFO_INTQ_GET_SCALE(entree_ai[0].meta_info, 0);
    e_zero    = AI_BUFFER_META_INFO_INTQ_GET_ZEROPOINT(entree_ai[0].meta_info, 0);
    s_echelle = AI_BUFFER_META_INFO_INTQ_GET_SCALE(sortie_ai[0].meta_info, 0);
    s_zero    = AI_BUFFER_META_INFO_INTQ_GET_ZEROPOINT(sortie_ai[0].meta_info, 0);
    if (e_echelle <= 0.0f || s_echelle <= 0.0f) return -4;

    /* compteur de cycles du processeur, pour mesurer la durée du calcul */
#if defined(DCB)
    DCB->DEMCR |= DCB_DEMCR_TRCENA_Msk;
#else
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
#endif
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    return 0;
}

int nilm_ia_calculer(nilm_flux_t *f, uint32_t *duree_us)
{
    if (reseau == AI_HANDLE_NULL) return -1;
    uint32_t t0 = DWT->CYCCNT;

    /* entrée : float -> int8 (arrondi au plus proche, comme QuantizeLinear d'ONNX) */
    ai_i8 *q = (ai_i8 *)entree_ai[0].data;
    for (int i = 0; i < NILM_NB_ENTREES * NILM_FENETRE; i++) {
        long v = lrintf(f->entree[i] / e_echelle) + e_zero;      /* même ordre [canal][minute] (chfirst) */
        q[i] = (ai_i8)(v < -128 ? -128 : v > 127 ? 127 : v);
    }
    if (ai_network_run(reseau, &entree_ai[0], &sortie_ai[0]) != 1) return -2;

    /* sortie : int8 -> float, puis énergies et message */
    const ai_i8 *r = (const ai_i8 *)sortie_ai[0].data;
    for (int i = 0; i < NILM_NB_SORTIES * NILM_FENETRE; i++)
        sortie[i] = (float)(r[i] - s_zero) * s_echelle;
    nilm_flux_resultat(f, sortie, 0);

    if (duree_us) *duree_us = (DWT->CYCCNT - t0) / (SystemCoreClock / 1000000u);
    return 0;
}
