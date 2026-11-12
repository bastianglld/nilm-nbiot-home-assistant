/*
 * Pilotage des appareils flexibles par la carte (partie C, flexibilité).
 *
 * Reçoit les messages MQTT de nilm/maison/cmd/+ (docs/protocole_messages.md) :
 *   - nilm/maison/cmd/plan          : planning du lendemain, 32 caractères « JJMM;C;RRRRRR;BBBBBBBBBBBB;LL;VV »
 *   - nilm/maison/cmd/<appareil>    : ordre ponctuel « ON » / « OFF » (Home Assistant)
 * et décide chaque minute de l'état des relais et du mode de la batterie.
 *
 * Règles (dans l'ordre) :
 *   1. un ordre ponctuel reçu s'applique jusqu'au prochain changement prévu par le planning (ou le secours) ;
 *      un ordre identique au précédent (message retain renvoyé à chaque connexion) est ignoré ;
 *   2. sinon, le planning du jour s'il est arrivé (chauffe-eau : bit de l'heure, batterie : 2 bits de l'heure) ;
 *   3. sinon, le secours : chauffe-eau en heures creuses (22 h - 6 h), batterie au repos.
 *   Le radiateur (« chauffage ») n'a pas de planning : il suit le dernier ordre, autorisé par défaut.
 *
 * Le temps est la minute locale depuis le 1er janvier 2000 (nilm_minute_horodate de nilm_flux.h) :
 * la même horloge que le NILM, remise à l'heure par la TIC ou, plus tard, par le réseau NB-IoT.
 * Code portable, sans HAL : testé sur PC (tests/test_pilotage_c.py) puis sur la carte (appli_nilm.c).
 */
#ifndef PILOTAGE_H
#define PILOTAGE_H

#include <stddef.h>
#include <stdint.h>

#define PILOTAGE_TOPIC_BASE   "nilm/maison/cmd/"
#define PILOTAGE_LONGUEUR_PLAN 32
#define PILOTAGE_HC_DEBUT     22              /* secours : heures creuses de 22 h à 6 h, comme l'EMS */
#define PILOTAGE_HC_FIN       6

enum { PILOTAGE_CHAUFFE_EAU = 0, PILOTAGE_CHAUFFAGE = 1, PILOTAGE_NB_APPAREILS = 2 };
enum { PILOTAGE_SECOURS = 0, PILOTAGE_PLAN = 1, PILOTAGE_ORDRE = 2 };                 /* origine d'un état */
enum { BATTERIE_REPOS = 0, BATTERIE_CHARGE = 1, BATTERIE_DECHARGE = 2 };

/* Résultat de pilotage_message */
enum {
    PILOTAGE_RECU_PLAN = 1,       /* planning valide, rangé */
    PILOTAGE_RECU_ORDRE = 2,      /* ordre ON/OFF nouveau, appliqué */
    PILOTAGE_RECU_REPETE = 3,     /* même ordre que le précédent (retain) : rien ne change */
    PILOTAGE_IGNORE = 0,          /* autre topic : ignoré */
    PILOTAGE_ERREUR = -1          /* planning ou ordre mal formé : rejeté, rien ne change */
};

typedef struct {
    uint8_t  valide;
    uint8_t  jour, mois;
    char     couleur;             /* 'B', 'W', 'R' ou '-' */
    uint32_t chauffe_eau;         /* bit h : chauffe autorisée de h à h+1 */
    uint64_t batterie;            /* bits 2h, 2h+1 : 0 repos, 1 charge, 2 décharge */
    uint8_t  depart_lave_linge, depart_lave_vaisselle;
} pilotage_plan_t;

typedef struct {
    uint8_t  ordre_connu;         /* un ordre a déjà été reçu depuis le démarrage */
    uint8_t  dernier_ordre;       /* 0 OFF, 1 ON */
    uint8_t  force;               /* ordre en cours d'application */
    int32_t  force_jusqua;        /* minute où l'ordre cesse (prochain changement prévu) */
    uint8_t  etat;                /* état décidé : 0 coupé, 1 autorisé */
    uint8_t  origine;             /* PILOTAGE_SECOURS, _PLAN ou _ORDRE */
} pilotage_appareil_t;

typedef struct {
    pilotage_plan_t     plan[2];  /* aujourd'hui et demain (le planning arrive la veille) */
    pilotage_appareil_t app[PILOTAGE_NB_APPAREILS];
    uint8_t             batterie; /* mode décidé pour l'heure en cours */
    int32_t             minute;   /* dernière minute évaluée (-1 : jamais) */
    uint32_t            plans_recus, plans_rejetes, ordres_recus, ignores;
} pilotage_t;

void pilotage_init(pilotage_t *p);

/* Un message reçu sur nilm/maison/cmd/+ ; minute = heure actuelle (pour la durée d'un ordre). */
int pilotage_message(pilotage_t *p, const char *topic, const char *message, int32_t minute);

/* Décode un planning de 32 caractères ; 0 si valide. */
int pilotage_decoder_plan(const char *message, pilotage_plan_t *plan);

/* Décide l'état de chaque appareil pour cette minute. Renvoie un masque des appareils dont l'état a changé
   (bit i = appareil i) : la carte commande alors le relais et publie la confirmation. */
uint32_t pilotage_evaluer(pilotage_t *p, int32_t minute);

const char *pilotage_nom(int appareil);                  /* "chauffe_eau", "chauffage" */
const char *pilotage_nom_origine(int origine);           /* "secours", "plan", "ordre" */

/* Confirmation pour Home Assistant : topic nilm/maison/cmd/<appareil>/etat, message ON ou OFF. */
int pilotage_confirmation(const pilotage_t *p, int appareil, char *topic, size_t taille_topic,
                          char *message, size_t taille_message);

/* Jour et mois d'une minute depuis le 1er janvier 2000 (calendrier grégorien). */
void pilotage_date(int32_t minute, int *jour, int *mois, int *heure);

#endif
