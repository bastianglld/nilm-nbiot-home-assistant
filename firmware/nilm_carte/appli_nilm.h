/*
 * Application de la carte (partie C) : puissance mesurée -> NILM -> message de 15 minutes.
 *
 * Deux sources de puissance, au choix (SOURCE_PUISSANCE) :
 *   SOURCE_TIC : trames TIC (Linky ou simulateur) sur le port du ST-LINK, 9 600 bauds 8N1 ;
 *   SOURCE_VI  : mesure tension/courant de la carte (A0 = courant, A1 = tension, 4 000 échantillons/s).
 * Le modèle NILM tourne sur le Cortex-M55 (nilm_ia). Le message part par envoyer_message().
 */
#ifndef APPLI_NILM_H
#define APPLI_NILM_H

#include <stdint.h>

#define SOURCE_TIC 0
#define SOURCE_VI  1

/* ------------------------------------------------------------------ réglages */
#ifndef SOURCE_PUISSANCE
#define SOURCE_PUISSANCE SOURCE_TIC    /* SOURCE_VI quand la pince et l'adaptateur sont branchés */
#endif

#ifndef CAPTEURS_REELS
#define CAPTEURS_REELS 0                 /* 0 : volts sur le connecteur (test au GBF) ; 1 : pince et adaptateur */
#endif

/* 1 : ajoute « t=<durée du calcul>us » à la fin des lignes NILM (essais) ; 0 : message seul (envoi NB-IoT).
   Le choix processeur / NPU se fait dans nilm_ia.h (NILM_SUR_NPU). */
#ifndef NILM_AFFICHER_DUREE
#define NILM_AFFICHER_DUREE 1
#endif

/* Heure de départ en mode V/I (« SAAMMJJhhmmss », comme l'horodate TIC), tant que l'heure n'est pas connue.
   Une trame TIC valide, puis plus tard l'heure du réseau NB-IoT, remettent l'horloge à l'heure. */
#ifndef DEPART_HORODATE
#define DEPART_HORODATE "H261105000000"
#endif

void appli_init(void);                               /* après l'initialisation du port COM1, avant l'ADC */
void appli_pas(void);                                /* à appeler en boucle dans while (1) */
void appli_echantillon(uint16_t v_brut, uint16_t i_brut);   /* depuis l'interruption de l'ADC */
void appli_message_recu(const char *topic, const char *message); /* message MQTT reçu sur nilm/maison/cmd/+ */

#endif
