/*
 * Appel du modèle NILM généré par ST Edge AI – partie C. Même interface pour le processeur et le NPU.
 * Le modèle a des entrées/sorties int8 : la conversion float <-> int8 utilise l'échelle et le zéro
 * lus dans le code généré (entrée 0,0252 / -88, sortie 0,1626 / 37 pour nilm_int8.onnx).
 */
#ifndef NILM_IA_H
#define NILM_IA_H


#include <stdint.h>
#include "nilm_flux.h"

/* Où tourne le modèle : 1 = NPU Neural-ART (nilm_ia_npu.c, code dans Src/npu), 0 = processeur Cortex-M55 (nilm_ia.c) */
#ifndef NILM_SUR_NPU
#define NILM_SUR_NPU 1
#endif

/* 0 si le modèle est prêt */
int nilm_ia_init(void);

/* Lance le modèle sur la fenêtre préparée par nilm_flux_mesure, puis remplit f->wh et f->message.
   Renvoie 0 si tout va bien. duree_us : temps du calcul (peut être NULL). */
int nilm_ia_calculer(nilm_flux_t *f, uint32_t *duree_us);

#endif
