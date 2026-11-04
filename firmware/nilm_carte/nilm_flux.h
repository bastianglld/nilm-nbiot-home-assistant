/*
 * Préparation des données du modèle NILM sur la carte (partie C).
 *
 * Reçoit des mesures de puissance datées (décodeur TIC ou mesure V/I), en fait des moyennes par minute,
 * garde les 272 dernières minutes, et toutes les 15 minutes :
 *   1. remplit le tenseur d'entrée du modèle (3 x 272 : kW, sin(heure), cos(heure)) ;
 *   2. après le calcul du modèle, transforme sa sortie (8 x 272) en message NB-IoT
 *      « hhmm;frigo;bouilloire;lave_linge;lave_vaisselle;total » (énergies en Wh sur le quart d'heure).
 *
 * Réglages identiques à nilm/notebooks/export_s7/nilm_meta.json (fenêtre 272, pas 15, contexte 127,
 * minutes 130 à 144 retenues). Les fenêtres finissent à hh:07, hh:22, hh:37 et hh:52 : le quart d'heure
 * retenu commence alors pile à hh:00, hh:15, hh:30 ou hh:45 (retard de 2 h 07 à 2 h 22).
 *
 * Portable : ni HAL ni modèle ici. Le calcul du modèle est fait par le code généré par ST Edge AI.
 */
#ifndef NILM_FLUX_H
#define NILM_FLUX_H

#include <stdint.h>

#define NILM_FENETRE        272   /* minutes vues par le modèle */
#define NILM_PAS            15    /* une fenêtre toutes les 15 minutes */
#define NILM_CONTEXTE       127   /* minutes de « futur » nécessaires au modèle */
#define NILM_DEBUT_RETENU   (NILM_FENETRE - NILM_CONTEXTE - NILM_PAS)   /* 130 */
#define NILM_NB_APPAREILS   4     /* frigo, bouilloire, lave-linge, lave-vaisselle */
#define NILM_NB_ENTREES     3
#define NILM_NB_SORTIES     (2 * NILM_NB_APPAREILS)
#define NILM_FIN_FENETRE_MOD15  ((NILM_FENETRE - NILM_DEBUT_RETENU) % NILM_PAS)   /* fin de fenêtre ≡ 7 (mod 15) */

typedef struct {
    /* minute en cours d'accumulation */
    int32_t  minute;           /* minute absolue (voir nilm_minute_horodate), -1 avant la première mesure */
    float    somme;
    uint32_t n;
    /* historique circulaire des minutes terminées */
    float    p_w[NILM_FENETRE];
    uint8_t  valide[NILM_FENETRE];
    int32_t  premiere;         /* première minute rangée depuis le départ */
    int32_t  fin;              /* minute qui suit la dernière minute rangée */
    /* fenêtre prête pour le modèle */
    int32_t  fin_fenetre;      /* minute absolue qui suit la fenêtre préparée */
    float    entree[NILM_NB_ENTREES * NILM_FENETRE];   /* [canal][minute], canal 0 = kW, 1 = sin, 2 = cos */
    /* résultat */
    uint16_t wh[NILM_NB_APPAREILS + 1];               /* énergies du dernier quart d'heure (+ total) */
    char     message[48];                              /* « hhmm;f;b;ll;lv;total » */
    /* compteurs */
    uint32_t minutes_rangees, minutes_vides, fenetres, retours_arriere;
} nilm_flux_t;

/* Minute absolue depuis le 1er janvier 2000 à partir d'une horodate TIC « SAAMMJJhhmmss » (saison + 12 chiffres)
   ou « AAMMJJhhmmss ». Renvoie -1 si l'horodate est illisible. */
int32_t nilm_minute_horodate(const char *horodate);

void nilm_flux_init(nilm_flux_t *f);

/* Une mesure de puissance (W ou VA) datée en minute absolue. Renvoie 1 quand une fenêtre complète est prête :
   f->entree est rempli et il faut alors lancer le modèle puis appeler nilm_flux_resultat. */
int nilm_flux_mesure(nilm_flux_t *f, int32_t minute, float puissance_w);

/* Copie l'entrée vers le tampon du modèle. canaux_en_dernier = 0 : [canal][minute] (forme ONNX 1x3x272) ;
   1 : [minute][canal] (forme 1x272x3, si ST Edge AI a placé les canaux en dernier). */
void nilm_flux_copier_entree(const nilm_flux_t *f, float *dst, int canaux_en_dernier);

/* Sortie du modèle (8 x 272) -> énergies du quart d'heure retenu et message. Même convention de rangement. */
void nilm_flux_resultat(nilm_flux_t *f, const float *sortie, int canaux_en_dernier);

#endif
