/* Préparation des données du modèle NILM – voir nilm_flux.h */
#include "nilm_flux.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

/* puissance max de chaque appareil utilisée à l'entraînement (W), voir nilm_meta.json : echelles_W */
static const float ECHELLE_W[NILM_NB_APPAREILS] = { 249.6999969482422f, 2405.469970703125f,
                                                    1975.2900390625f, 2392.109130859375f };
#define PI_F 3.14159265358979f

/* ------------------------------------------------------------------ horodate */
static int deux_chiffres(const char *s)
{
    if (s[0] < '0' || s[0] > '9' || s[1] < '0' || s[1] > '9') return -1;
    return (s[0] - '0') * 10 + (s[1] - '0');
}

static int32_t jours_depuis_2000(int a, int m, int j)      /* a = 2000..2099 */
{
    static const int cumul[12] = { 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334 };
    int32_t d = (a - 2000) * 365 + (a - 2000 + 3) / 4;     /* années bissextiles 2000, 2004... déjà passées */
    d += cumul[m - 1] + (j - 1);
    if (m > 2 && a % 4 == 0) d += 1;
    return d;
}

int32_t nilm_minute_horodate(const char *h)
{
    if (!h) return -1;
    if (h[0] < '0' || h[0] > '9') h++;                      /* saison : E, H, e, h ou espace */
    int aa = deux_chiffres(h), mo = deux_chiffres(h + 2), jj = deux_chiffres(h + 4);
    int hh = deux_chiffres(h + 6), mi = deux_chiffres(h + 8);
    if (aa < 0 || mo < 1 || mo > 12 || jj < 1 || jj > 31 || hh < 0 || hh > 23 || mi < 0 || mi > 59) return -1;
    return jours_depuis_2000(2000 + aa, mo, jj) * 1440 + hh * 60 + mi;
}

/* ------------------------------------------------------------------ historique */
static int indice(int32_t minute)
{
    int32_t k = minute % NILM_FENETRE;
    return (int)(k < 0 ? k + NILM_FENETRE : k);
}

static void preparer_fenetre(nilm_flux_t *f, int32_t fin)
{
    for (int t = 0; t < NILM_FENETRE; t++) {
        int32_t minute = fin - NILM_FENETRE + t;
        int k = indice(minute);
        float kw = 0.0f, s = 0.0f, c = 0.0f;              /* minute manquante : les 3 canaux à 0 */
        if (f->valide[k]) {
            float heure = (float)(minute % 1440) / 60.0f;
            kw = f->p_w[k] / 1000.0f;
            s = sinf(2.0f * PI_F * heure / 24.0f);
            c = cosf(2.0f * PI_F * heure / 24.0f);
        }
        f->entree[0 * NILM_FENETRE + t] = kw;
        f->entree[1 * NILM_FENETRE + t] = s;
        f->entree[2 * NILM_FENETRE + t] = c;
    }
    f->fin_fenetre = fin;
    f->fenetres++;
}

/* range la minute f->fin ; renvoie 1 si une fenêtre se termine juste après elle */
static int ranger(nilm_flux_t *f, float p_w, int valide)
{
    int k = indice(f->fin);
    f->p_w[k] = valide ? p_w : 0.0f;
    f->valide[k] = (uint8_t)(valide != 0);
    if (valide) f->minutes_rangees++; else f->minutes_vides++;
    f->fin++;
    if (f->fin % NILM_PAS == NILM_FIN_FENETRE_MOD15 && f->fin - f->premiere >= NILM_FENETRE) {
        preparer_fenetre(f, f->fin);
        return 1;
    }
    return 0;
}

void nilm_flux_init(nilm_flux_t *f)
{
    memset(f, 0, sizeof *f);
    f->minute = -1;
}

int nilm_flux_mesure(nilm_flux_t *f, int32_t minute, float p)
{
    if (minute < 0) return 0;
    if (f->minute < 0) {                                   /* toute première mesure */
        f->minute = f->premiere = f->fin = minute;
        f->somme = p; f->n = 1;
        return 0;
    }
    if (minute == f->minute) { f->somme += p; f->n++; return 0; }
    if (minute < f->minute) { f->retours_arriere++; return 0; }   /* horloge revenue en arrière : mesure ignorée */

    int pret = ranger(f, f->somme / (float)f->n, 1);       /* minute terminée */
    int32_t trou = minute - f->fin;                        /* minutes sans aucune mesure */
    if (trou > NILM_FENETRE) {                             /* coupure plus longue que la fenêtre : on repart de zéro */
        f->premiere = f->fin = minute;
        trou = 0;
    }
    while (trou-- > 0) pret |= ranger(f, 0.0f, 0);
    f->minute = minute;
    f->somme = p; f->n = 1;
    return pret;
}

/* ------------------------------------------------------------------ entrée et sortie du modèle */
void nilm_flux_copier_entree(const nilm_flux_t *f, float *dst, int canaux_en_dernier)
{
    if (!canaux_en_dernier) { memcpy(dst, f->entree, sizeof f->entree); return; }
    for (int t = 0; t < NILM_FENETRE; t++)
        for (int c = 0; c < NILM_NB_ENTREES; c++)
            dst[t * NILM_NB_ENTREES + c] = f->entree[c * NILM_FENETRE + t];
}

void nilm_flux_resultat(nilm_flux_t *f, const float *y, int canaux_en_dernier)
{
    float wh[NILM_NB_APPAREILS + 1] = { 0 };
    for (int j = 0; j < NILM_PAS; j++) {
        int t = NILM_DEBUT_RETENU + j;
        for (int a = 0; a < NILM_NB_APPAREILS; a++) {
            float reg = canaux_en_dernier ? y[t * NILM_NB_SORTIES + a] : y[a * NILM_FENETRE + t];
            float on  = canaux_en_dernier ? y[t * NILM_NB_SORTIES + NILM_NB_APPAREILS + a]
                                          : y[(NILM_NB_APPAREILS + a) * NILM_FENETRE + t];
            if (on > 0.0f && reg > 0.0f) wh[a] += reg * ECHELLE_W[a];   /* W ; appareil éteint -> 0 */
        }
        int k = indice(f->fin_fenetre - NILM_FENETRE + t);
        if (f->valide[k]) wh[NILM_NB_APPAREILS] += f->p_w[k];           /* total mesuré */
    }
    for (int a = 0; a <= NILM_NB_APPAREILS; a++) {
        float e = wh[a] / 60.0f;                                         /* somme des 15 puissances / 60 = Wh */
        f->wh[a] = (uint16_t)(e < 0.0f ? 0.0f : e > 65535.0f ? 65535.0f : e + 0.5f);
    }
    int32_t debut = (f->fin_fenetre - NILM_FENETRE + NILM_DEBUT_RETENU) % 1440;
    snprintf(f->message, sizeof f->message, "%02d%02d;%u;%u;%u;%u;%u", (int)(debut / 60), (int)(debut % 60),
             f->wh[0], f->wh[1], f->wh[2], f->wh[3], f->wh[4]);
}
