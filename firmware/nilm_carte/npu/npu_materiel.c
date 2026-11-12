/*
 * Mise en route du NPU Neural-ART dans le programme de la carte (partie C).
 * Repris de l'application NPU_Validation de X-CUBE-AI 10.2 (misc_toolbox.c : system_init_post, NPU_Config,
 * RISAF_Config), qui a validé le modèle sur le NPU : mêmes réglages, sans la mémoire externe ni le cache du NPU.
 */
#define HAL_RIF_MODULE_ENABLED            /* déclarations du pilote RIF (compilé dans npu_rif.c) */
#include "stm32n6xx_hal.h"
#include "npu_rif.h"

static uint32_t risaf_fin(RISAF_TypeDef *r)
{
  if (r == RISAF2_S) return RISAF2_LIMIT_ADDRESS_SPACE_SIZE;
  if (r == RISAF3_S) return RISAF3_LIMIT_ADDRESS_SPACE_SIZE;
  if (r == RISAF4_S) return RISAF4_LIMIT_ADDRESS_SPACE_SIZE;
  if (r == RISAF5_S) return RISAF5_LIMIT_ADDRESS_SPACE_SIZE;
  if (r == RISAF6_S) return RISAF6_LIMIT_ADDRESS_SPACE_SIZE;
  if (r == RISAF7_S) return RISAF7_LIMIT_ADDRESS_SPACE_SIZE;
  return 0;
}

/* Une zone ouverte à tous (sécurisé et non sécurisé, tous les CID) : réglage par défaut des exemples d'ST */
static void risaf_ouvrir(RISAF_TypeDef *r)
{
  RISAF_BaseRegionConfig_t c;
  c.StartAddress = 0x0;
  c.EndAddress = risaf_fin(r);
  c.Filtering = RISAF_FILTER_ENABLE;
  c.PrivWhitelist = RIF_CID_NONE;
  c.ReadWhitelist = RIF_CID_MASK;
  c.WriteWhitelist = RIF_CID_MASK;
  c.Secure = RIF_ATTRIBUTE_SEC;
  HAL_RIF_RISAF_ConfigBaseRegion(r, 0, &c);
  c.Secure = RIF_ATTRIBUTE_NSEC;
  HAL_RIF_RISAF_ConfigBaseRegion(r, 1, &c);
}

void npu_materiel_init(void)
{
  /* RAM du NPU (AXISRAM3 à 6, 4 x 448 Ko) : horloge puis mise sous tension */
  RCC->MEMENR |= RCC_MEMENR_AXISRAM3EN | RCC_MEMENR_AXISRAM4EN | RCC_MEMENR_AXISRAM5EN | RCC_MEMENR_AXISRAM6EN;
  RAMCFG_SRAM3_AXI->CR &= ~RAMCFG_CR_SRAMSD;
  RAMCFG_SRAM4_AXI->CR &= ~RAMCFG_CR_SRAMSD;
  RAMCFG_SRAM5_AXI->CR &= ~RAMCFG_CR_SRAMSD;
  RAMCFG_SRAM6_AXI->CR &= ~RAMCFG_CR_SRAMSD;

  /* NPU : horloge et remise à zéro */
  __HAL_RCC_NPU_CLK_ENABLE();
  __HAL_RCC_NPU_FORCE_RESET();
  __HAL_RCC_NPU_RELEASE_RESET();

  /* RIF : le NPU accède à la mémoire en maître sécurisé et privilégié (CID 1), comme le processeur du FSBL */
  RIMC_MasterConfig_t m;
  m.MasterCID = RIF_CID_1;
  m.SecPriv = RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_PRIV;
  HAL_RIF_RIMC_ConfigMasterAttributes(RIF_MASTER_INDEX_NPU, &m);
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_NPU, RIF_ATTRIBUTE_PRIV | RIF_ATTRIBUTE_SEC);

  /* Horloges gardées pendant la veille du processeur (WFI/WFE), comme set_clk_sleep_mode() d'ST :
     sans cela, le NPU et ses RAM s'arrêtent dès que le processeur attend. */
  __HAL_RCC_NPU_CLK_SLEEP_ENABLE();
  __HAL_RCC_AXISRAM1_MEM_CLK_SLEEP_ENABLE();
  __HAL_RCC_AXISRAM2_MEM_CLK_SLEEP_ENABLE();
  __HAL_RCC_AXISRAM3_MEM_CLK_SLEEP_ENABLE();
  __HAL_RCC_AXISRAM4_MEM_CLK_SLEEP_ENABLE();
  __HAL_RCC_AXISRAM5_MEM_CLK_SLEEP_ENABLE();
  __HAL_RCC_AXISRAM6_MEM_CLK_SLEEP_ENABLE();
  __HAL_RCC_RIFSC_CLK_SLEEP_ENABLE();
  __HAL_RCC_RISAF_CLK_SLEEP_ENABLE();
  __HAL_RCC_USART1_CLK_SLEEP_ENABLE();
  __HAL_RCC_ADC12_CLK_SLEEP_ENABLE();
  __HAL_RCC_TIM6_CLK_SLEEP_ENABLE();

  /* pare-feux des mémoires (RISAF) : AXISRAM1 et 2, ports du NPU, AXISRAM3 à 6, FLEXMEM */
  __HAL_RCC_RISAF_CLK_ENABLE();
  risaf_ouvrir(RISAF2_S);
  risaf_ouvrir(RISAF3_S);
  risaf_ouvrir(RISAF4_S);
  risaf_ouvrir(RISAF5_S);
  risaf_ouvrir(RISAF6_S);
  risaf_ouvrir(RISAF7_S);
}
