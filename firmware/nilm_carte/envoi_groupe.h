/*
 * Envoi groupé des messages MQTT de la carte (partie C).
 *
 * Ouvrir une connexion NB-IoT (TLS + MQTT) coûte bien plus cher que les messages eux-mêmes
 * (docs/budget_donnees_sim.md). La carte garde donc ses messages dans une file et ne se connecte que :
 *   - quand ENVOI_MESURES_PAR_CONNEXION messages de mesure attendent (4 messages de 15 min = une heure) ;
 *   - tout de suite pour un message urgent (confirmation d'un relais, plus tard une alerte).
 * Chaque connexion envoie toute la file, dans l'ordre d'arrivée, un PUBLISH par message.
 *
 * Si la connexion ou une publication échoue (réseau absent), les messages non publiés restent en file :
 * nouvel essai au prochain message ajouté. La file est bornée (ENVOI_CAPACITE) : au-delà, le plus ancien
 * message est jeté et compté dans « perdus ».
 *
 * L'envoi passe par trois fonctions fournies par l'appelant (envoi_liaison_t) : aujourd'hui des lignes
 * vers le PC, demain le pilote AT du ST87M01 (partie B).
 *
 * Portable : ni HAL ni allocation dynamique.
 */
#ifndef ENVOI_GROUPE_H
#define ENVOI_GROUPE_H

#include <stdint.h>

#define ENVOI_TOPIC_MAX              48   /* caractères, sans le zéro final */
#define ENVOI_MESSAGE_MAX            50   /* limite du ST87M01 */
#define ENVOI_CAPACITE               16   /* messages en file : 4 h de mesures */
#define ENVOI_MESURES_PAR_CONNEXION  4    /* une connexion par heure */

#define ENVOI_OK       0
#define ENVOI_REFUSE (-1)                 /* topic vide, ou topic ou message trop long */

/* Fonctions d'envoi fournies par l'appelant. */
typedef struct {
    int  (*ouvrir)(void);                                      /* 0 : connexion ouverte */
    int  (*publier)(const char *topic, const char *message);   /* 0 : message publié */
    void (*fermer)(uint16_t nb_publies);                       /* appelée après chaque ouverture réussie */
} envoi_liaison_t;

typedef struct {
    char    topic[ENVOI_TOPIC_MAX + 1];
    char    message[ENVOI_MESSAGE_MAX + 1];
    uint8_t urgent;
} envoi_message_t;

typedef struct {
    envoi_liaison_t liaison;
    envoi_message_t file[ENVOI_CAPACITE];   /* file circulaire */
    uint8_t  debut, nb;                     /* plus ancien message, nombre de messages en file */
    uint8_t  nb_mesures, nb_urgents;        /* dont mesures et messages urgents */
    uint8_t  en_connexion;                  /* 1 pendant une connexion */
    /* compteurs (lisibles dans Live Expressions) */
    uint32_t connexions;                    /* connexions ouvertes */
    uint32_t echecs;                        /* ouvertures ou publications ratées */
    uint32_t publies, perdus, refuses;
} envoi_groupe_t;

void envoi_init(envoi_groupe_t *e, const envoi_liaison_t *liaison);

/* Message de mesure (nilm/maison/etat) : mis en file ; connexion quand 4 mesures attendent.
   Renvoie ENVOI_OK, ou ENVOI_REFUSE (message non gardé). */
int envoi_mesure(envoi_groupe_t *e, const char *topic, const char *message);

/* Message urgent (nilm/maison/cmd/<appareil>/etat, alerte) : connexion tout de suite, qui envoie toute la file.
   Pendant une connexion (message reçu puis confirmé), il part dans la même connexion. */
int envoi_urgent(envoi_groupe_t *e, const char *topic, const char *message);

/* Connexion tout de suite, quel que soit le contenu de la file. Renvoie le nombre de messages publiés. */
int envoi_vider(envoi_groupe_t *e);

#endif
