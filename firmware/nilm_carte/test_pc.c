/* Accès à nilm_flux et envoi_groupe depuis Python (ctypes) pour les tests sur PC :
       gcc -shared -fPIC -o libnilm_flux.so nilm_flux.c test_pc.c -lm
       gcc -shared -fPIC -o libenvoi_groupe.so envoi_groupe.c test_pc.c */
#include <stddef.h>
#include "nilm_flux.h"
#include "envoi_groupe.h"

size_t nf_taille(void) { return sizeof(nilm_flux_t); }
const float *nf_entree(const nilm_flux_t *f) { return f->entree; }
const char *nf_message(const nilm_flux_t *f) { return f->message; }
int32_t nf_fin_fenetre(const nilm_flux_t *f) { return f->fin_fenetre; }

size_t eg_taille(void) { return sizeof(envoi_groupe_t); }
int eg_en_file(const envoi_groupe_t *e) { return e->nb; }
int eg_mesures_en_file(const envoi_groupe_t *e) { return e->nb_mesures; }
uint32_t eg_compteur(const envoi_groupe_t *e, int i)
{
    return i == 0 ? e->connexions : i == 1 ? e->echecs : i == 2 ? e->publies : i == 3 ? e->perdus : e->refuses;
}
