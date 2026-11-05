/*
 * NILM sur le NPU Neural-ART de la NUCLEO-N657X0-Q (partie C).
 *
 * Même chaîne que sur le Cortex-M55 (projet tic_test) :
 *   trames TIC sur le port du ST-LINK (USART1, 9 600 bauds 8N1, simulateur lancé avec --8n1)
 *   -> décodeur TIC -> nilm_flux (minutes, fenêtre de 272 minutes)
 *   -> modèle exécuté par le NPU (code généré par ST Edge AI avec --st-neural-art, poids en flash externe)
 *   -> message « NILM hhmm;frigo;bouilloire;lave_linge;lave_vaisselle;total t=<durée>us » renvoyé au PC.
 *
 * Le projet est une copie de l'application NPU_Validation de X-CUBE-AI : horloges, mémoires du NPU,
 * flash externe et droits d'accès (RIF) sont déjà réglés par main.c ; seul l'appel final change.
 */
#include <stdio.h>
#include <string.h>
#include <math.h>

#include "main.h"
#include "misc_toolbox.h"
#include "mcu_cache.h"
#include "npu_cache.h"
#include "ll_aton_runtime.h"
#include "tic_decodeur.h"
#include "nilm_flux.h"
#include "nilm_npu.h"

LL_ATON_DECLARE_NAMED_NN_INSTANCE_AND_INTERFACE(Default);

/* à surveiller dans Live Expressions si besoin */
tic_t tic;
nilm_flux_t nilm;
volatile uint32_t nb_octets_recus, nb_erreurs_uart, nilm_messages, nilm_duree_us;
volatile int32_t nilm_etat_npu;          /* 0 = prêt ; négatif = problème à l'initialisation */

static const LL_Buffer_InfoTypeDef *entree_npu, *sortie_npu;
static float sortie[NILM_NB_SORTIES * NILM_FENETRE];

static void envoyer(const char *s)
{
  HAL_UART_Transmit(&UartHandle, (uint8_t *)s, (uint16_t)strlen(s), 200);
}

static int npu_preparer(void)
{
  entree_npu = LL_ATON_Input_Buffers_Info_Default();
  sortie_npu = LL_ATON_Output_Buffers_Info_Default();
  if (!entree_npu || !sortie_npu || !entree_npu[0].name || !sortie_npu[0].name) return -1;
  if (LL_Buffer_len(&entree_npu[0]) != NILM_NB_ENTREES * NILM_FENETRE) return -2;      /* int8 [1,3,272] */
  if (LL_Buffer_len(&sortie_npu[0]) != NILM_NB_SORTIES * NILM_FENETRE) return -3;      /* int8 [1,8,272] */
  if (entree_npu[0].chpos != CHPos_First || sortie_npu[0].chpos != CHPos_First) return -4;
  mcu_cache_clean_invalidate();
  npu_cache_invalidate();            /* cache du NPU activé par NPU_Config() (misc_toolbox.c) */
  LL_ATON_RT_RuntimeInit();
  LL_ATON_RT_Init_Network(&NN_Instance_Default);
  /* compteur de cycles pour mesurer la durée d'un calcul */
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  return 0;
}

static int npu_lancer(void)
{
  const float e_echelle = entree_npu[0].scale[0];
  const int e_zero = entree_npu[0].offset[0];
  const float s_echelle = sortie_npu[0].scale[0];
  const int s_zero = sortie_npu[0].offset[0];
  int8_t *in = (int8_t *)LL_Buffer_addr_start(&entree_npu[0]);
  uint32_t t0 = DWT->CYCCNT;

  /* entrée : float -> int8, même ordre [canal][minute] (canaux en premier) */
  for (int i = 0; i < NILM_NB_ENTREES * NILM_FENETRE; i++) {
    long v = lrintf(nilm.entree[i] / e_echelle) + e_zero;
    in[i] = (int8_t)(v < -128 ? -128 : v > 127 ? 127 : v);
  }
  mcu_cache_clean_range((uint32_t)LL_Buffer_addr_start(&entree_npu[0]), (uint32_t)LL_Buffer_addr_end(&entree_npu[0]));

  LL_ATON_RT_Reset_Network(&NN_Instance_Default);
  LL_ATON_RT_RetValues_t r;
  do {
    r = LL_ATON_RT_RunEpochBlock(&NN_Instance_Default);
    if (r == LL_ATON_RT_WFE) LL_ATON_OSAL_WFE();
  } while (r != LL_ATON_RT_DONE);

  mcu_cache_invalidate_range((uint32_t)LL_Buffer_addr_start(&sortie_npu[0]), (uint32_t)LL_Buffer_addr_end(&sortie_npu[0]));
  const int8_t *out = (const int8_t *)LL_Buffer_addr_start(&sortie_npu[0]);
  for (int i = 0; i < NILM_NB_SORTIES * NILM_FENETRE; i++)
    sortie[i] = (float)(out[i] - s_zero) * s_echelle;
  nilm_duree_us = (DWT->CYCCNT - t0) / (SystemCoreClock / 1000000u);

  nilm_flux_resultat(&nilm, sortie, 0);
  return 0;
}

static void apres_trame(void)
{
  int32_t minute = nilm_minute_horodate(tic.horodate);
  if (!nilm_flux_mesure(&nilm, minute, (float)tic.papp_va)) return;
  if (nilm_etat_npu != 0) return;
  npu_lancer();
  nilm_messages++;
  char ligne[80];
  snprintf(ligne, sizeof ligne, "NILM %s t=%luus\r\n", nilm.message, (unsigned long)nilm_duree_us);
  envoyer(ligne);
}

void nilm_npu_app(void)
{
  /* port du ST-LINK : 9 600 bauds 8N1 (simulateur avec --8n1) */
  UartHandle.Init.BaudRate = 9600;
  UartHandle.Init.WordLength = UART_WORDLENGTH_8B;
  UartHandle.Init.Parity = UART_PARITY_NONE;
  HAL_UART_Init(&UartHandle);

  tic_init(&tic);
  nilm_flux_init(&nilm);
  nilm_etat_npu = npu_preparer();

  char l[96];
  snprintf(l, sizeof l, "NILM_NPU pret (etat %ld, horloge CPU %lu MHz)\r\n", (long)nilm_etat_npu,
           (unsigned long)(SystemCoreClock / 1000000u));
  envoyer(l);

  for (;;) {
    uint8_t octet;
    HAL_StatusTypeDef st = HAL_UART_Receive(&UartHandle, &octet, 1, 5);
    if (st == HAL_OK) {
      nb_octets_recus++;
      if (tic_octet(&tic, octet) == TIC_TRAME_OK) apres_trame();
    } else if (st == HAL_ERROR) {
      nb_erreurs_uart++;
      __HAL_UART_CLEAR_FLAG(&UartHandle, UART_CLEAR_PEF | UART_CLEAR_FEF | UART_CLEAR_NEF | UART_CLEAR_OREF);
      UartHandle.ErrorCode = HAL_UART_ERROR_NONE;
      UartHandle.RxState = HAL_UART_STATE_READY;
    }
  }
}
