/*
 * Décodeur TIC Linky – voir tic_decodeur.h.
 */
#include "tic_decodeur.h"
#include <string.h>

#define STX 0x02
#define ETX 0x03
#define EOT 0x04
#define LF  0x0A
#define CR  0x0D
#define HT  0x09
#define SP  0x20

/* ------------------------------------------------------------------ outils */
static uint32_t lire_entier(const char *s)
{
    uint32_t v = 0;
    while (*s == ' ') s++;
    while (*s >= '0' && *s <= '9') v = v * 10u + (uint32_t)(*s++ - '0');
    return v;
}

static uint32_t lire_hexa(const char *s)
{
    uint32_t v = 0;
    for (;; s++) {
        char c = *s;
        if (c >= '0' && c <= '9')      v = (v << 4) | (uint32_t)(c - '0');
        else if (c >= 'A' && c <= 'F') v = (v << 4) | (uint32_t)(c - 'A' + 10);
        else if (c >= 'a' && c <= 'f') v = (v << 4) | (uint32_t)(c - 'a' + 10);
        else break;
    }
    return v;
}

static void copier(char *dst, const char *src, unsigned taille)
{
    unsigned i = 0;
    for (; i + 1 < taille && src[i]; i++) dst[i] = src[i];
    while (i > 0 && dst[i - 1] == ' ') i--;              /* retire les espaces de fin (LTARF est complété) */
    dst[i] = '\0';
}

static tic_couleur_t couleur_2bits(uint32_t v)
{
    return (tic_couleur_t)(v & 3u);                      /* 0 inconnue, 1 bleu, 2 blanc, 3 rouge */
}

static uint8_t somme_controle(const char *s, unsigned n)
{
    unsigned somme = 0;
    for (unsigned i = 0; i < n; i++) somme += (uint8_t)s[i];
    return (uint8_t)((somme & 0x3Fu) + 0x20u);
}

/* ------------------------------------------------------------------ interprétation d'une ligne valide */
static void ranger(tic_t *t, const char *etiquette, const char *horodate, const char *donnee)
{
    if (t->mode == TIC_MODE_STANDARD) {
        if      (!strcmp(etiquette, "SINSTS")) t->papp_va = lire_entier(donnee);
        else if (!strcmp(etiquette, "EAST"))   t->index_total_wh = lire_entier(donnee);
        else if (!strcmp(etiquette, "IRMS1"))  t->irms_a = (uint16_t)lire_entier(donnee);
        else if (!strcmp(etiquette, "URMS1"))  t->urms_v = (uint16_t)lire_entier(donnee);
        else if (!strcmp(etiquette, "PREF"))   t->pref_kva = (uint8_t)lire_entier(donnee);
        else if (!strcmp(etiquette, "LTARF"))  copier(t->tarif, donnee, sizeof t->tarif);
        else if (!strcmp(etiquette, "DATE") && horodate) copier(t->horodate, horodate, sizeof t->horodate);
        else if (!strcmp(etiquette, "STGE")) {
            t->stge = lire_hexa(donnee);
            t->couleur_jour = couleur_2bits(t->stge >> 24);
            t->couleur_demain = couleur_2bits(t->stge >> 26);
        }
    } else {
        if      (!strcmp(etiquette, "PAPP"))   t->papp_va = lire_entier(donnee);
        else if (!strcmp(etiquette, "IINST"))  t->irms_a = (uint16_t)lire_entier(donnee);
        else if (!strcmp(etiquette, "ISOUSC")) t->pref_kva = (uint8_t)(lire_entier(donnee) / 5u);
        else if (!strcmp(etiquette, "BASE") || !strcmp(etiquette, "HCHC") || !strcmp(etiquette, "HCHP")
                 || !strncmp(etiquette, "BBRH", 4))
            t->somme_index_histo += lire_entier(donnee);
        else if (!strcmp(etiquette, "PTEC")) {
            copier(t->tarif, donnee, sizeof t->tarif);
            /* Tempo : HCJB, HPJW, HCJR... */
            if (strlen(donnee) >= 4 && donnee[2] == 'J')
                t->couleur_jour = donnee[3] == 'B' ? TIC_BLEU : donnee[3] == 'W' ? TIC_BLANC
                                : donnee[3] == 'R' ? TIC_ROUGE : TIC_COULEUR_INCONNUE;
        }
        else if (!strcmp(etiquette, "DEMAIN"))
            t->couleur_demain = !strncmp(donnee, "BLEU", 4) ? TIC_BLEU : !strncmp(donnee, "BLAN", 4) ? TIC_BLANC
                              : !strncmp(donnee, "ROUG", 4) ? TIC_ROUGE : TIC_COULEUR_INCONNUE;
    }
}

/* Vérifie et découpe la ligne reçue entre LF et CR. Renvoie 1 si elle est valide. */
static int traiter_ligne(tic_t *t)
{
    char *l = t->ligne;
    unsigned n = t->n;
    if (n < 4) return 0;
    l[n] = '\0';

    /* le mode se déduit du séparateur : tabulation en standard, espace en historique */
    tic_mode_t mode = memchr(l, HT, n) ? TIC_MODE_STANDARD : TIC_MODE_HISTORIQUE;
    if (mode == TIC_MODE_STANDARD) {
        if (l[n - 2] != HT || somme_controle(l, n - 1) != (uint8_t)l[n - 1]) return 0;
        l[n - 2] = '\0';                                         /* coupe « HT somme » */
        char *champ[3] = { l, NULL, NULL };
        unsigned k = 1;
        for (char *p = l; *p && k < 3; p++)
            if (*p == HT) { *p = '\0'; champ[k++] = p + 1; }
        if (k < 2) return 0;
        t->mode = mode;
        if (k == 3) ranger(t, champ[0], champ[1], champ[2]);     /* étiquette, horodate, donnée */
        else        ranger(t, champ[0], NULL, champ[1]);
    } else {
        if (l[n - 2] != SP || somme_controle(l, n - 2) != (uint8_t)l[n - 1]) return 0;
        l[n - 2] = '\0';                                         /* coupe « SP somme » */
        char *sep = strchr(l, SP);
        if (!sep) return 0;
        *sep = '\0';
        t->mode = mode;
        ranger(t, l, NULL, sep + 1);
    }
    return 1;
}

/* ------------------------------------------------------------------ interface */
void tic_init(tic_t *t)
{
    memset(t, 0, sizeof *t);
}

tic_resultat_t tic_octet(tic_t *t, uint8_t octet)
{
    uint8_t c = octet & 0x7Fu;                    /* le bit 7 porte la parité (lecture en 8 bits) */

    if (c == STX) {
        if (t->dans_trame) t->trames_interrompues++;
        t->dans_trame = 1; t->dans_ligne = 0; t->erreur_trame = 0; t->somme_index_histo = 0;
        return TIC_RIEN;
    }
    if (!t->dans_trame) return TIC_RIEN;

    switch (c) {
    case EOT:                                     /* trame interrompue par le compteur */
        t->dans_trame = 0;
        t->trames_interrompues++;
        return TIC_RIEN;
    case ETX:
        t->dans_trame = 0;
        if (t->dans_ligne) { t->lignes_rejetees++; t->erreur_trame = 1; }
        if (t->mode == TIC_MODE_HISTORIQUE && t->somme_index_histo) t->index_total_wh = t->somme_index_histo;
        if (t->erreur_trame) { t->trames_erreur++; return TIC_TRAME_ERREUR; }
        t->trames_ok++;
        return TIC_TRAME_OK;
    case LF:
        if (t->dans_ligne) { t->lignes_rejetees++; t->erreur_trame = 1; }   /* ligne précédente sans CR */
        t->dans_ligne = 1; t->n = 0;
        return TIC_RIEN;
    case CR:
        if (t->dans_ligne && !traiter_ligne(t)) { t->lignes_rejetees++; t->erreur_trame = 1; }
        t->dans_ligne = 0;
        return TIC_RIEN;
    default:
        if (t->dans_ligne) {
            if (t->n < TIC_GROUPE_MAX - 1) t->ligne[t->n++] = (char)c;
            else { t->dans_ligne = 0; t->lignes_rejetees++; t->erreur_trame = 1; }   /* ligne trop longue */
        }
        return TIC_RIEN;
    }
}
