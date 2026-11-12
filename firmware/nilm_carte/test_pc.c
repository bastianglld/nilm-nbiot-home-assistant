/* Accès à nilm_flux depuis Python (ctypes) pour les tests sur PC :
       gcc -shared -fPIC -o libnilm_flux.so nilm_flux.c test_pc.c -lm */
#include <stddef.h>
#include "nilm_flux.h"

size_t nf_taille(void) { return sizeof(nilm_flux_t); }
const float *nf_entree(const nilm_flux_t *f) { return f->entree; }
const char *nf_message(const nilm_flux_t *f) { return f->message; }
int32_t nf_fin_fenetre(const nilm_flux_t *f) { return f->fin_fenetre; }
