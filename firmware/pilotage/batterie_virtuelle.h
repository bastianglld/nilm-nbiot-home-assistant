/*
 * Batterie virtuelle de démonstration : la carte suit le niveau de charge d'une batterie domestique simulée,
 * minute par minute, avec le mode décidé par le pilotage (repos, charge, décharge), et l'affiche sur une jauge
 * de 5 LED. Mêmes paramètres que la simulation de l'EMS (flexibilite/ems_serveur.py) : 5 kWh, 2,5 kW,
 * rendement 95 % à la charge et à la décharge, réserve de 0,5 kWh.
 * La décharge ne fournit jamais plus que ce que la maison consomme (pas de revente au réseau).
 * Module portable sans HAL, testé sur PC (tests/test_batterie_virtuelle_c.py).
 */
#ifndef BATTERIE_VIRTUELLE_H
#define BATTERIE_VIRTUELLE_H

#include <stdint.h>

typedef struct
{
    float stock_kwh;      /* énergie stockée */
    float capacite_kwh;   /* 5 kWh */
    float puissance_kw;   /* 2,5 kW en charge comme en décharge */
    float rendement;      /* 0,95 à la charge et à la décharge */
    float reserve_kwh;    /* 0,5 kWh jamais utilisés */
} batterie_virtuelle_t;

/* Paramètres de l'EMS, batterie à moitié pleine au départ. */
void bv_init(batterie_virtuelle_t *b);

/* Une minute dans le mode donné (0 repos, 1 charge, 2 décharge) ; conso_w : puissance de la maison sur la minute.
   Renvoie l'énergie échangée avec le réseau en Wh (positive en charge, négative en décharge). */
float bv_minute(batterie_virtuelle_t *b, uint8_t mode, float conso_w);

/* Niveau de charge en pour cent (0 à 100). */
int bv_pourcent(const batterie_virtuelle_t *b);

/* Nombre de LED à allumer sur une jauge de nb LED (arrondi au plus proche, entre 0 et nb). */
int bv_niveau(const batterie_virtuelle_t *b, int nb);

#endif
