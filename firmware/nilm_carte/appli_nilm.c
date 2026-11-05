/* Application de la carte (partie C) – voir appli_nilm.h */
#include <stdio.h>
#include <string.h>
#include "main.h"
#include "appli_nilm.h"
#include "tic_decodeur.h"
#include "mesure_vi.h"
#include "nilm_flux.h"
#include "nilm_ia.h"

/* ------------------------------------------------------------------ étalonnage de la mesure */
#define ADC_VOLTS_PAR_POINT  (1.8f / 4096.0f)  /* référence de l'ADC du STM32N6 : 1,8 V */
#define RAPPORT_CARTE        0.54f             /* ampli de la carte entre A0/A1 et PA8/PA9 (mesuré au GBF) */
#define V_CONNECTEUR         (ADC_VOLTS_PAR_POINT / RAPPORT_CARTE)   /* volts sur le connecteur par point ADC */
#define CORRECTION_V         1.0f              /* à régler au multimètre (écart de 4,6 % commun aux deux voies au GBF) */
#define CORRECTION_I         1.0f

#if CAPTEURS_REELS
/* tension : adaptateur 230 V -> 9 V (rapport à mesurer au multimètre), pont R5 = 100 kΩ / R6 = 8,2 kΩ */
#define K_V  (V_CONNECTEUR * CORRECTION_V * (100.0f + 8.2f) / 8.2f * (230.0f / 9.0f))
/* courant : pince SCT-013-000 (rapport 2000) sur R3 = 22 Ω, SPIRES tours de fil dans la pince */
#define SPIRES 1.0f
#define K_I  (V_CONNECTEUR * CORRECTION_I / 22.0f * 2000.0f / SPIRES)
#else
#define K_V  (V_CONNECTEUR * CORRECTION_V)
#define K_I  (V_CONNECTEUR * CORRECTION_I)
#endif

/* ------------------------------------------------------------------ état (lisible dans Live Expressions) */
tic_t tic;
mesure_vi_t mes;
nilm_flux_t nilm;
volatile int32_t nilm_etat_ia;           /* 0 = modèle prêt */
volatile uint32_t nb_octets_recus, nb_erreurs_uart;
volatile uint32_t nilm_messages, nilm_erreurs, nilm_duree_us, nilm_envois_rates;
volatile float cadence_hz;               /* échantillons par seconde : ~4000 */
volatile int32_t minute_vi;              /* minute courante en mode V/I */
static volatile uint8_t minute_vi_prete;
static uint32_t t_bloc;

/* ------------------------------------------------------------------ envoi */
/* Un seul point de sortie : aujourd'hui le port du ST-LINK (PC), demain la liaison vers le ST87M01. */
static void envoyer_message(const char *ligne)
{
  if (HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t *)ligne, (uint16_t)strlen(ligne), 100) != HAL_OK)
    nilm_envois_rates++;
}

/* Une puissance datée -> NILM ; si une fenêtre est prête, le modèle tourne et le message part. */
static void puissance_vers_nilm(int32_t minute, float puissance)
{
  if (!nilm_flux_mesure(&nilm, minute, puissance)) return;
  if (nilm_etat_ia != 0) return;
  uint32_t duree;
  if (nilm_ia_calculer(&nilm, &duree) != 0)
  {
    nilm_erreurs++;
    return;
  }
  nilm_duree_us = duree;
  nilm_messages++;
  char ligne[64];
  snprintf(ligne, sizeof ligne, "NILM %s\r\n", nilm.message);
  envoyer_message(ligne);
  BSP_LED_Toggle(LED_BLUE);
}

/* ------------------------------------------------------------------ interface */
void appli_init(void)
{
  tic_init(&tic);
  mesure_init(&mes, 4000, K_V, K_I, 60);
  nilm_flux_init(&nilm);
  nilm_etat_ia = nilm_ia_init();
  minute_vi = nilm_minute_horodate(DEPART_HORODATE);
}

/* Interruption de l'ADC : un couple (tension, courant) toutes les 250 µs. */
void appli_echantillon(uint16_t v_brut, uint16_t i_brut)
{
  int r = mesure_echantillon(&mes, v_brut, i_brut);
  if (r == MESURE_RIEN) return;
  uint32_t t = HAL_GetTick();                     /* un bloc = 4000 échantillons = 1 s */
  if (t_bloc != 0 && t != t_bloc) cadence_hz = 4000000.0f / (float)(t - t_bloc);
  t_bloc = t;
  if (r == MESURE_MINUTE) minute_vi_prete = 1;    /* traité dans la boucle, hors interruption */
}

static void trame_tic_valide(void)
{
  BSP_LED_Toggle(LED_GREEN);
  int32_t minute = nilm_minute_horodate(tic.horodate);
#if SOURCE_PUISSANCE == SOURCE_TIC
  puissance_vers_nilm(minute, (float)tic.papp_va);
#else
  if (minute >= 0) minute_vi = minute;            /* une trame TIC remet l'horloge à l'heure */
#endif
}

void appli_pas(void)
{
  uint8_t octet;
  HAL_StatusTypeDef st = HAL_UART_Receive(&hcom_uart[COM1], &octet, 1, 5);
  if (st == HAL_OK)
  {
    nb_octets_recus++;
    if (tic_octet(&tic, octet) == TIC_TRAME_OK) trame_tic_valide();
  }
  else if (st == HAL_ERROR)
  {
    nb_erreurs_uart++;
    __HAL_UART_CLEAR_FLAG(&hcom_uart[COM1], UART_CLEAR_PEF | UART_CLEAR_FEF | UART_CLEAR_NEF | UART_CLEAR_OREF);
    hcom_uart[COM1].ErrorCode = HAL_UART_ERROR_NONE;
    hcom_uart[COM1].RxState = HAL_UART_STATE_READY;
  }

#if SOURCE_PUISSANCE == SOURCE_VI
  if (minute_vi_prete)
  {
    minute_vi_prete = 0;
    int32_t m = minute_vi++;                      /* minute qui vient de se terminer */
    float s = mes.s_minute, p = mes.p_minute;
    /* une ligne par minute pour l'étalonnage : U (dV), I (cA), P (W), S (VA), fp (centièmes) */
    char ligne[96];
    snprintf(ligne, sizeof ligne, "VI %02ld%02ld U=%ld dV I=%ld cA P=%ld W S=%ld VA fp=%ld\r\n",
             (long)((m % 1440) / 60), (long)(m % 60), (long)(mes.vrms * 10.0f), (long)(mes.irms * 100.0f),
             (long)p, (long)s, (long)(mes.fp * 100.0f));
    envoyer_message(ligne);
    puissance_vers_nilm(m, s);
  }
#endif
}
