/* Accès à pilotage depuis Python (ctypes) pour les tests sur PC :
       gcc -shared -fPIC -o libpilotage.so pilotage.c test_pc.c */
#include "pilotage.h"

size_t pl_taille(void) { return sizeof(pilotage_t); }
int pl_etat(const pilotage_t *p, int a) { return p->app[a].etat; }
int pl_origine(const pilotage_t *p, int a) { return p->app[a].origine; }
int pl_batterie(const pilotage_t *p) { return p->batterie; }
uint32_t pl_compteur(const pilotage_t *p, int i)
{
    return i == 0 ? p->plans_recus : i == 1 ? p->plans_rejetes : i == 2 ? p->ordres_recus : p->ignores;
}
