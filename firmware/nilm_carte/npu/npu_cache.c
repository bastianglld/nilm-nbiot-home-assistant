/*
 * Cache du NPU (CACHEAXI) – version vide pour le projet tic_test (partie C).
 * Le modèle est généré avec tout en mémoire interne non « cachable » (nilm_npu/interne/nilm_interne.mpool) :
 * le cache du NPU ne sert pas, et ces fonctions ne sont jamais réellement appelées par LL_ATON.
 * Elles existent seulement pour que l'édition de liens trouve les symboles (le pilote HAL CACHEAXI n'est pas
 * activé dans CubeMX). Si un jour des poids passent en mémoire externe, reprendre npu_cache.c du pack X-CUBE-AI.
 */
#include "npu_cache.h"

void npu_cache_init(void) {}
void npu_cache_enable(void) {}
void npu_cache_disable(void) {}
void npu_cache_invalidate(void) {}
void npu_cache_clean_range(uint32_t start_addr, uint32_t end_addr) { (void)start_addr; (void)end_addr; }
void npu_cache_clean_invalidate_range(uint32_t start_addr, uint32_t end_addr) { (void)start_addr; (void)end_addr; }
