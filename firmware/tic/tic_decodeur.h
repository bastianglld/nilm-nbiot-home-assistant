/*
 * Décodeur de la TIC (téléinformation client) du compteur Linky – projet M1 ESET NILM / NB-IoT.
 *
 * Code C portable (aucune dépendance à la HAL) : on lui donne les octets reçus un par un,
 * il reconstitue les trames, vérifie les sommes de contrôle et garde les dernières valeurs.
 * Fonctionne en mode standard (9 600 bauds) et historique (1 200 bauds), détecté automatiquement.
 *
 * Utilisation :
 *     tic_t tic;
 *     tic_init(&tic);
 *     ... à chaque octet reçu sur l'USART :
 *     if (tic_octet(&tic, octet) == TIC_TRAME_OK) { puissance = tic.papp_va; ... }
 *
 * Référence : Enedis-NOI-CPT_54E.
 */
#ifndef TIC_DECODEUR_H
#define TIC_DECODEUR_H

#include <stdint.h>

#define TIC_GROUPE_MAX 96          /* longueur max d'une ligne (MSG1 fait 32 caractères de donnée) */

typedef enum { TIC_MODE_INCONNU = 0, TIC_MODE_HISTORIQUE, TIC_MODE_STANDARD } tic_mode_t;
typedef enum { TIC_COULEUR_INCONNUE = 0, TIC_BLEU, TIC_BLANC, TIC_ROUGE } tic_couleur_t;

typedef enum {
    TIC_RIEN = 0,          /* octet pris en compte, trame pas encore finie */
    TIC_TRAME_OK,          /* trame complète, toutes les lignes valides */
    TIC_TRAME_ERREUR       /* trame complète mais au moins une ligne rejetée (les lignes valides sont gardées) */
} tic_resultat_t;

typedef struct {
    /* ---- valeurs extraites (dernière trame) ---- */
    tic_mode_t    mode;
    uint32_t      papp_va;            /* puissance apparente : SINSTS (standard) ou PAPP (historique), VA */
    uint32_t      index_total_wh;     /* EAST (standard) ou somme des index (historique), Wh */
    uint16_t      irms_a;             /* IRMS1 ou IINST, A */
    uint16_t      urms_v;             /* URMS1 (standard seulement), V */
    uint8_t       pref_kva;           /* PREF (standard) ou ISOUSC / 5 (historique) */
    uint32_t      stge;               /* registre d'état (standard) */
    tic_couleur_t couleur_jour;       /* Tempo : STGE bits 24-25, ou PTEC en historique */
    tic_couleur_t couleur_demain;     /* Tempo : STGE bits 26-27, ou DEMAIN en historique */
    char          tarif[17];          /* LTARF (standard) ou PTEC (historique) */
    char          horodate[14];       /* DATE (standard), ex. H251104094500 */

    /* ---- compteurs pour le diagnostic ---- */
    uint32_t      trames_ok;
    uint32_t      trames_erreur;
    uint32_t      trames_interrompues;   /* EOT reçu ou STX avant la fin */
    uint32_t      lignes_rejetees;

    /* ---- état interne ---- */
    uint8_t       dans_trame;
    uint8_t       dans_ligne;
    uint8_t       erreur_trame;
    uint8_t       n;
    char          ligne[TIC_GROUPE_MAX];
    uint32_t      somme_index_histo;
} tic_t;

void           tic_init(tic_t *t);
tic_resultat_t tic_octet(tic_t *t, uint8_t octet);

#endif
