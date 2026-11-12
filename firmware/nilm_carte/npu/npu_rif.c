/*
 * Pilote HAL RIF compilé uniquement pour le NPU (partie C).
 * Le module RIF n'est pas activé dans le stm32n6xx_hal_conf.h généré par CubeMX : on l'active ici, pour ce seul
 * fichier, et on compile la copie du pilote présente dans Drivers. (Si un jour RIF est activé dans CubeMX,
 * supprimer ce fichier pour éviter les fonctions en double.)
 */
#define HAL_RIF_MODULE_ENABLED
#include "stm32n6xx_hal.h"
#include "../../../../Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_rif.c"
