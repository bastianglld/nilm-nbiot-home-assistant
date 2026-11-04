/*
 * Intégration de mesure_vi sur la NUCLEO-N657X0-Q (STM32CubeMX + STM32CubeIDE, HAL, projet FSBL).
 * Fichier à ne pas compiler tel quel : chaque bloc va dans la section « USER CODE » indiquée du main.c.
 * Il s'ajoute au décodeur TIC (firmware/tic/integration_stm32.c) : les deux tournent ensemble.
 *
 * Réglages CubeMX (contexte FSBL) :
 *   - ADC1 : IN10 (PA9, connecteur A1) = courant, IN11 (PA10, connecteur A2) = tension, en Single-ended.
 *     Resolution 12 bits, Scan Conversion Mode Enabled, Number Of Conversion 2,
 *     Rank 1 = Channel 10, Rank 2 = Channel 11 (Sampling Time assez long, par ex. 46.5 ou 64.5 cycles),
 *     External Trigger Conversion Source = Timer 6 Trigger Out event, front montant,
 *     End Of Conversion Selection = End of single conversion, Continuous Mode Disabled,
 *     Overrun = data overwritten. NVIC : ADC1 global interrupt coché.
 *   - TIM6 : Activated, Trigger Event Selection = Update Event,
 *     Prescaler et Counter Period pour 4 kHz : f_timer / ((PSC+1)(ARR+1)) = 4000.
 *
 * Copier mesure_vi.h dans FSBL/Core/Inc et mesure_vi.c dans FSBL/Core/Src.
 */

/* ===== USER CODE BEGIN Includes ===== */
#include "mesure_vi.h"

/* ===== USER CODE BEGIN PD ===== */
#define ADC_VOLTS_PAR_POINT  (1.8f / 4096.0f)  /* référence de l'ADC du STM32N6 : 1,8 V */
#define RAPPORT_CARTE        0.54f             /* pont de la NUCLEO entre connecteur et broche (1.0f s'il n'existe pas) */
#define V_CONNECTEUR         (ADC_VOLTS_PAR_POINT / RAPPORT_CARTE)   /* volts sur le connecteur par point ADC */

/* Test au GBF : on lit directement les volts sur le connecteur. */
#define K_V  V_CONNECTEUR
#define K_I  V_CONNECTEUR
/* Avec les vrais capteurs (à mettre à la place des deux lignes ci-dessus) :
 *   tension : pont R5 = 100 kΩ / R6 = 3,9 kΩ puis adaptateur 230 V -> ~9 V (rapport à mesurer au multimètre)
 *     #define K_V (V_CONNECTEUR * (100.0f + 3.9f) / 3.9f * (230.0f / 9.0f))
 *   courant : SCT-013-000 (rapport 2000) sur R3 = 22 Ω, N spires dans la pince
 *     #define K_I (V_CONNECTEUR / 22.0f * 2000.0f / 1.0f)
 */

/* ===== USER CODE BEGIN PV ===== */
mesure_vi_t mes;                    /* à surveiller dans Live Expressions : mes.vrms, mes.irms, mes.p, mes.s, mes.fp */
static uint16_t brut_i;             /* rang 1 de la séquence, en attente du rang 2 */
volatile uint32_t nb_echantillons;  /* doit augmenter de 4000 par seconde */

/* ===== USER CODE BEGIN WHILE (avant « while (1) », après le bloc TIC) ===== */
mesure_init(&mes, 4000, K_V, K_I, 60);          /* blocs de 1 s (50 périodes), minute = 60 blocs */
if (HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED) != HAL_OK) {
    Error_Handler();
}
if (HAL_ADC_Start_IT(&hadc1) != HAL_OK) {
    Error_Handler();
}
HAL_TIM_Base_Start(&htim6);                     /* chaque débordement du timer lance une séquence courant + tension */

/* ===== USER CODE BEGIN 4 ===== */
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    if (hadc->Instance != ADC1) return;
    uint16_t x = (uint16_t)HAL_ADC_GetValue(hadc);
    if (!__HAL_ADC_GET_FLAG(hadc, ADC_FLAG_EOS)) {    /* rang 1 : courant (IN10) */
        brut_i = x;
        return;
    }
    nb_echantillons++;                                 /* rang 2, fin de séquence : tension (IN11) */
    mesure_echantillon(&mes, x, brut_i);
}
