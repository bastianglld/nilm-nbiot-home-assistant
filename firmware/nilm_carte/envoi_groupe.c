/* Envoi groupé des messages MQTT de la carte – voir envoi_groupe.h */
#include "envoi_groupe.h"
#include <string.h>

/* longueur de s, ou max + 1 si s est plus long que max */
static size_t longueur(const char *s, size_t max)
{
    size_t n = 0;
    while (n <= max && s[n] != 0) n++;
    return n;
}

static void compter(envoi_groupe_t *e, const envoi_message_t *m, int sens)
{
    if (m->urgent) e->nb_urgents = (uint8_t)(e->nb_urgents + sens);
    else           e->nb_mesures = (uint8_t)(e->nb_mesures + sens);
}

/* retire le plus ancien message de la file et le copie dans *m */
static void retirer(envoi_groupe_t *e, envoi_message_t *m)
{
    *m = e->file[e->debut];
    compter(e, m, -1);
    e->debut = (uint8_t)((e->debut + 1) % ENVOI_CAPACITE);
    e->nb--;
}

void envoi_init(envoi_groupe_t *e, const envoi_liaison_t *liaison)
{
    memset(e, 0, sizeof *e);
    e->liaison = *liaison;
}

int envoi_vider(envoi_groupe_t *e)
{
    if (e->en_connexion) return 0;          /* déjà en cours : la boucle ci-dessous enverra tout */
    if (e->liaison.ouvrir() != 0) {
        e->echecs++;
        return 0;
    }
    e->en_connexion = 1;
    e->connexions++;
    uint16_t n = 0;
    while (e->nb > 0) {                      /* la file peut grandir pendant la connexion (message reçu) */
        envoi_message_t m;
        retirer(e, &m);
        if (e->liaison.publier(m.topic, m.message) == 0) {
            n++;
            e->publies++;
            continue;
        }
        /* échec : le message reprend sa place en tête de file, avec ceux qui le suivent */
        e->echecs++;
        if (e->nb < ENVOI_CAPACITE) {
            e->debut = (uint8_t)((e->debut + ENVOI_CAPACITE - 1) % ENVOI_CAPACITE);
            e->file[e->debut] = m;
            e->nb++;
            compter(e, &m, +1);
        } else {
            e->perdus++;                     /* file remplie entre-temps : c'était le plus ancien */
        }
        break;
    }
    e->liaison.fermer(n);
    e->en_connexion = 0;
    return n;
}

static int ajouter(envoi_groupe_t *e, const char *topic, const char *message, uint8_t urgent)
{
    if (!topic || !message || topic[0] == 0 || longueur(topic, ENVOI_TOPIC_MAX) > ENVOI_TOPIC_MAX
        || longueur(message, ENVOI_MESSAGE_MAX) > ENVOI_MESSAGE_MAX) {
        e->refuses++;
        return ENVOI_REFUSE;
    }
    if (e->nb == ENVOI_CAPACITE) {           /* file pleine : on jette le plus ancien */
        envoi_message_t jete;
        retirer(e, &jete);
        e->perdus++;
    }
    envoi_message_t *m = &e->file[(e->debut + e->nb) % ENVOI_CAPACITE];
    strcpy(m->topic, topic);
    strcpy(m->message, message);
    m->urgent = urgent;
    e->nb++;
    compter(e, m, +1);
    /* connexion si un message urgent attend, ou une heure de mesures ; nouvel essai à chaque ajout si échec */
    if (e->nb_urgents > 0 || e->nb_mesures >= ENVOI_MESURES_PAR_CONNEXION) envoi_vider(e);
    return ENVOI_OK;
}

int envoi_mesure(envoi_groupe_t *e, const char *topic, const char *message)
{
    return ajouter(e, topic, message, 0);
}

int envoi_urgent(envoi_groupe_t *e, const char *topic, const char *message)
{
    return ajouter(e, topic, message, 1);
}
