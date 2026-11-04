/*
 * Intégration de mesure_vi sur la NUCLEO-N657X0-Q (STM32CubeMX + STM32CubeIDE, HAL, projet FSBL).
 * Fichier à ne pas compiler tel quel : chaque bloc va dans la section « USER CODE » indiquée.
 * Il s'ajoute au décodeur TIC (firmware/tic/integration_stm32.c) : les deux tournent ensemble.
 * Validé sur carte le 4 novembre 2026 (GBF 1 Vpp sur A0 et A1 : Vrms = Irms = 0,370 V, fp = 0,9999).
 *
 * Entrées utilisées (manuel UM3417, table 17) :
 *   A0 (CN4) -> ampli abaisseur de la carte -> PA8 -> ADC1 canal 5  : courant
 *   A1 (CN4) -> ampli abaisseur de la carte -> PA9 -> ADC1 canal 10 : tension
 * L'ampli ramène 0..3,3 V du connecteur à 0..1,8 V sur la broche (rapport mesuré 0,54).
 * Attention : la documentation Zephyr et les essais au GBF sur des entrées « aveugles » donnent de faux brochages.
 *
 * Piège du STM32N6 (isolation RIF) : au démarrage, les broches sont sécurisées (GPIOx_SECCFGR = 0xFFFF)
 * mais l'ADC12 ne l'est pas. L'ADC ne voit alors aucune broche : il lit ~1200 sur tous les canaux,
 * même une broche reliée à la masse. Il faut donner le même attribut aux deux (ici : broches non sécurisées).
 *
 * Réglages CubeMX (contexte FSBL) :
 *   - ADC1 : IN5 et IN10 en Single-ended. Resolution 12 bits, Scan Conversion Mode Enabled, Number Of Conversion 2,
 *     Rank 1 = Channel 5, Rank 2 = Channel 10, Sampling Time 1499.5 Cycles (voir plus bas),
 *     External Trigger Conversion Source = Timer 6 Trigger Out event, front montant,
 *     End Of Conversion Selection = End of single conversion, Continuous Mode Disabled,
 *     Overrun = data overwritten. NVIC : ADC1/ADC2 global interrupt coché.
 *   - Clock Configuration : diviseur de « To ADC1,2 » à /4 (200 MHz -> 50 MHz), sinon erreur [Clock].
 *   - TIM6 : Activated, Prescaler 99, Counter Period 999 (400 MHz / 100 / 1000 = 4 kHz),
 *     Trigger Event Selection = Update Event.
 *
 * Sampling Time : avec 46,5 cycles, les deux conversions finissent avant l'entrée dans l'interruption
 * et la valeur du rang 1 est écrasée (nb_rang1 reste à 0). 1499,5 cycles (~30 µs par voie) laissent le temps
 * de la lire ; 2 x 30 µs restent très inférieurs aux 250 µs entre deux mesures.
 *
 * Après génération par CubeMX, si l'éditeur de liens ne trouve pas HAL_ADC_xxx ou HAL_TIM_xxx :
 * ajouter stm32n6xx_hal_adc(_ex).c et stm32n6xx_hal_tim(_ex).c au projet (New > File > Link to file).
 *
 * Copier mesure_vi.h dans FSBL/Core/Inc et mesure_vi.c dans FSBL/Core/Src.
 */

/* ===== main.c : USER CODE BEGIN Includes ===== */
#include "mesure_vi.h"

/* ===== main.c : USER CODE BEGIN PD ===== */
#define ADC_VOLTS_PAR_POINT  (1.8f / 4096.0f)  /* référence de l'ADC du STM32N6 : 1,8 V */
#define RAPPORT_CARTE        0.54f             /* ampli abaisseur de la carte entre A0/A1 et PA8/PA9 */
#define V_CONNECTEUR         (ADC_VOLTS_PAR_POINT / RAPPORT_CARTE)   /* volts sur le connecteur par point ADC */

/* Test au GBF : résultats en volts sur le connecteur. */
#define K_V  V_CONNECTEUR
#define K_I  V_CONNECTEUR
/* Avec les capteurs (point milieu à 1,65 V, deux résistances de 10 kΩ depuis le 3V3) :
 *   tension : pont R5 = 100 kΩ / R6 = 8,2 kΩ après l'adaptateur 230 V -> 9 V (rapport à mesurer au multimètre)
 *     #define K_V (V_CONNECTEUR * (100.0f + 8.2f) / 8.2f * (230.0f / 9.0f))
 *   courant : SCT-013-000 (rapport 2000) sur R3 = 22 Ω, N spires dans la pince
 *     #define K_I (V_CONNECTEUR / 22.0f * 2000.0f / 1.0f)
 */

/* ===== main.c : USER CODE BEGIN PV ===== */
mesure_vi_t mes;                    /* Live Expressions : mes.vrms, mes.irms, mes.p, mes.s, mes.fp */
static uint16_t brut_i;             /* rang 1 de la séquence, en attente du rang 2 */
volatile uint32_t nb_echantillons;  /* doit augmenter de 4000 par seconde */
volatile uint32_t nb_rang1;         /* conversions du rang 1 : doit suivre nb_echantillons */
volatile float cadence_hz;          /* échantillons par seconde mesurés avec HAL_GetTick : ~4000 */
static uint32_t t_bloc;

/* ===== main.c : USER CODE BEGIN ADC1_Init 2 (fin de MX_ADC1_Init) ===== */
/* Seulement si le .ioc n'a pas encore les bons canaux et le bon Sampling Time. */
sConfig.SamplingTime = ADC_SAMPLETIME_1499CYCLES_5;
sConfig.Channel = ADC_CHANNEL_5;
sConfig.Rank = ADC_REGULAR_RANK_1;
if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK) {
    Error_Handler();
}
sConfig.Channel = ADC_CHANNEL_10;
sConfig.Rank = ADC_REGULAR_RANK_2;
if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK) {
    Error_Handler();
}

/* ===== stm32n6xx_hal_msp.c : USER CODE BEGIN ADC1_MspInit 1 ===== */
{
    GPIO_InitTypeDef gpio_vi = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    gpio_vi.Mode = GPIO_MODE_ANALOG;
    gpio_vi.Pull = GPIO_NOPULL;
    gpio_vi.Pin = GPIO_PIN_8 | GPIO_PIN_9;
    HAL_GPIO_Init(GPIOA, &gpio_vi);
    /* indispensable : même attribut de sécurité que l'ADC12 (non sécurisé au démarrage) */
    HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_8 | GPIO_PIN_9, GPIO_PIN_NSEC | GPIO_PIN_NPRIV);
}

/* ===== main.c : USER CODE BEGIN WHILE (avant « while (1) », après le bloc TIC) ===== */
mesure_init(&mes, 4000, K_V, K_I, 60);          /* blocs de 1 s (50 périodes), minute = 60 blocs */
if (HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED) != HAL_OK) {
    Error_Handler();
}
if (HAL_ADC_Start_IT(&hadc1) != HAL_OK) {
    Error_Handler();
}
HAL_TIM_Base_Start(&htim6);                     /* chaque débordement du timer lance une séquence courant + tension */

/* ===== main.c : USER CODE BEGIN 4 ===== */
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    if (hadc->Instance != ADC1) return;
    uint16_t x = (uint16_t)HAL_ADC_GetValue(hadc);
    if (!__HAL_ADC_GET_FLAG(hadc, ADC_FLAG_EOS)) {    /* rang 1 : courant (canal 5, A0) */
        brut_i = x;
        nb_rang1++;
        return;
    }
    nb_echantillons++;                                 /* rang 2, fin de séquence : tension (canal 10, A1) */
    if (mesure_echantillon(&mes, x, brut_i) != MESURE_RIEN) {
        uint32_t t = HAL_GetTick();
        if (t_bloc != 0 && t != t_bloc) cadence_hz = 4000000.0f / (float)(t - t_bloc);
        t_bloc = t;
    }
}
