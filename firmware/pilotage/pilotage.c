/* Pilotage des appareils flexibles : planning de l'EMS, ordres de Home Assistant, secours – voir pilotage.h */
#include "pilotage.h"
#include <string.h>

static const char *const NOMS[PILOTAGE_NB_APPAREILS] = { "chauffe_eau", "chauffage" };

const char *pilotage_nom(int a) { return (a >= 0 && a < PILOTAGE_NB_APPAREILS) ? NOMS[a] : "?"; }

const char *pilotage_nom_origine(int o)
{
    return o == PILOTAGE_PLAN ? "plan" : o == PILOTAGE_ORDRE ? "ordre" : "secours";
}

/* ------------------------------------------------------------------ calendrier */
void pilotage_date(int32_t minute, int *jour, int *mois, int *heure)
{
    int32_t jours = minute >= 0 ? minute / 1440 : -((-minute + 1439) / 1440);
    int32_t reste = minute - jours * 1440;
    /* jours depuis le 1er mars 2000 (algorithme « civil_from_days » de H. Hinnant) */
    int32_t z = jours - 60;                                  /* 2000-01-01 + 60 jours = 2000-03-01 (bissextile) */
    int32_t era = (z >= 0 ? z : z - 146096) / 146097;
    int32_t doe = z - era * 146097;
    int32_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    int32_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    int32_t mp = (5 * doy + 2) / 153;
    if (jour)  *jour = (int)(doy - (153 * mp + 2) / 5 + 1);
    if (mois)  *mois = (int)(mp < 10 ? mp + 3 : mp - 9);
    if (heure) *heure = (int)(reste / 60);
}

/* ------------------------------------------------------------------ planning */
static int chiffre(char c) { return (c >= '0' && c <= '9') ? c - '0' : -1; }

static int hexa(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static int deux_chiffres(const char *s)
{
    int a = chiffre(s[0]), b = chiffre(s[1]);
    return (a < 0 || b < 0) ? -1 : 10 * a + b;
}

/* Longueur utile : sans espaces ni fin de ligne à la fin */
static size_t longueur_utile(const char *s)
{
    size_t n = strlen(s);
    while (n > 0 && (s[n - 1] == '\r' || s[n - 1] == '\n' || s[n - 1] == ' ')) n--;
    return n;
}

int pilotage_decoder_plan(const char *m, pilotage_plan_t *plan)
{
    if (!m || !plan || longueur_utile(m) != PILOTAGE_LONGUEUR_PLAN) return -1;
    /* JJMM;C;RRRRRR;BBBBBBBBBBBB;LL;VV : séparateurs aux positions 4, 6, 13, 26, 29 */
    if (m[4] != ';' || m[6] != ';' || m[13] != ';' || m[26] != ';' || m[29] != ';') return -2;
    int jj = deux_chiffres(m), mm = deux_chiffres(m + 2);
    if (jj < 1 || jj > 31 || mm < 1 || mm > 12) return -3;
    char c = m[5];
    if (c != 'B' && c != 'W' && c != 'R' && c != '-') return -4;
    uint32_t r = 0;
    for (int i = 7; i < 13; i++) {
        int h = hexa(m[i]);
        if (h < 0) return -5;
        r = (r << 4) | (uint32_t)h;
    }
    uint64_t b = 0;
    for (int i = 14; i < 26; i++) {
        int h = hexa(m[i]);
        if (h < 0) return -6;
        b = (b << 4) | (uint64_t)h;
    }
    for (int h = 0; h < 24; h++)
        if (((b >> (2 * h)) & 3u) == 3u) return -7;          /* mode 3 : n'existe pas */
    int ll = deux_chiffres(m + 27), lv = deux_chiffres(m + 30);
    if (ll < 0 || ll > 23 || lv < 0 || lv > 23) return -8;
    plan->valide = 1;
    plan->jour = (uint8_t)jj;
    plan->mois = (uint8_t)mm;
    plan->couleur = c;
    plan->chauffe_eau = r;
    plan->batterie = b;
    plan->depart_lave_linge = (uint8_t)ll;
    plan->depart_lave_vaisselle = (uint8_t)lv;
    return 0;
}

static const pilotage_plan_t *plan_du_jour(const pilotage_t *p, int jour, int mois)
{
    for (int i = 0; i < 2; i++)
        if (p->plan[i].valide && p->plan[i].jour == jour && p->plan[i].mois == mois) return &p->plan[i];
    return 0;
}

static void ranger_plan(pilotage_t *p, const pilotage_plan_t *nouveau, int32_t minute)
{
    int j, m;
    pilotage_date(minute, &j, &m, 0);
    int place = -1;
    for (int i = 0; i < 2 && place < 0; i++)                 /* même jour : on remplace */
        if (p->plan[i].valide && p->plan[i].jour == nouveau->jour && p->plan[i].mois == nouveau->mois) place = i;
    for (int i = 0; i < 2 && place < 0; i++)                 /* place libre */
        if (!p->plan[i].valide) place = i;
    for (int i = 0; i < 2 && place < 0; i++)                 /* sinon : celui qui n'est pas pour aujourd'hui */
        if (!(p->plan[i].jour == j && p->plan[i].mois == m)) place = i;
    if (place < 0) place = 0;
    p->plan[place] = *nouveau;
}

/* ------------------------------------------------------------------ état prévu (sans ordre) */
static uint8_t prevu(const pilotage_t *p, int a, int32_t minute, uint8_t *origine)
{
    if (a == PILOTAGE_CHAUFFAGE) {                           /* pas de planning : suit le dernier ordre */
        if (origine) *origine = PILOTAGE_SECOURS;
        return p->app[a].ordre_connu ? p->app[a].dernier_ordre : 1;
    }
    int j, m, h;
    pilotage_date(minute, &j, &m, &h);
    const pilotage_plan_t *pl = plan_du_jour(p, j, m);
    if (pl) {
        if (origine) *origine = PILOTAGE_PLAN;
        return (uint8_t)((pl->chauffe_eau >> h) & 1u);
    }
    if (origine) *origine = PILOTAGE_SECOURS;
    return (uint8_t)(h >= PILOTAGE_HC_DEBUT || h < PILOTAGE_HC_FIN);
}

/* Début de la prochaine heure où l'état prévu change (au plus 48 h plus tard) */
static int32_t prochain_changement(const pilotage_t *p, int a, int32_t minute)
{
    uint8_t avant = prevu(p, a, minute, 0);
    int32_t t = (minute / 60 + 1) * 60;
    for (int k = 0; k < 48; k++, t += 60)
        if (prevu(p, a, t, 0) != avant) return t;
    return minute + 24 * 60;
}

/* ------------------------------------------------------------------ interface */
void pilotage_init(pilotage_t *p)
{
    memset(p, 0, sizeof *p);
    p->minute = -1;
    for (int a = 0; a < PILOTAGE_NB_APPAREILS; a++) p->app[a].etat = 0xFF;   /* inconnu : publié à la 1re évaluation */
}

int pilotage_message(pilotage_t *p, const char *topic, const char *message, int32_t minute)
{
    size_t nb = strlen(PILOTAGE_TOPIC_BASE);
    if (!topic || !message || strncmp(topic, PILOTAGE_TOPIC_BASE, nb) != 0 || strchr(topic + nb, '/')) {
        p->ignores++;
        return PILOTAGE_IGNORE;                              /* autre topic, ou confirmation …/etat */
    }
    const char *nom = topic + nb;
    if (strcmp(nom, "plan") == 0) {
        pilotage_plan_t pl;
        if (pilotage_decoder_plan(message, &pl) != 0) {
            p->plans_rejetes++;
            return PILOTAGE_ERREUR;
        }
        ranger_plan(p, &pl, minute);
        p->plans_recus++;
        return PILOTAGE_RECU_PLAN;
    }
    for (int a = 0; a < PILOTAGE_NB_APPAREILS; a++) {
        if (strcmp(nom, NOMS[a]) != 0) continue;
        size_t n = longueur_utile(message);
        uint8_t v;
        if (n == 2 && strncmp(message, "ON", 2) == 0) v = 1;
        else if (n == 3 && strncmp(message, "OFF", 3) == 0) v = 0;
        else return PILOTAGE_ERREUR;
        pilotage_appareil_t *ap = &p->app[a];
        if (ap->ordre_connu && ap->dernier_ordre == v) return PILOTAGE_RECU_REPETE;
        ap->ordre_connu = 1;
        ap->dernier_ordre = v;
        ap->force = 1;
        ap->force_jusqua = (a == PILOTAGE_CHAUFFAGE) ? INT32_MAX : prochain_changement(p, a, minute);
        p->ordres_recus++;
        return PILOTAGE_RECU_ORDRE;
    }
    p->ignores++;
    return PILOTAGE_IGNORE;                                  /* appareil inconnu de cette carte (ex. batterie) */
}

uint32_t pilotage_evaluer(pilotage_t *p, int32_t minute)
{
    uint32_t change = 0;
    for (int a = 0; a < PILOTAGE_NB_APPAREILS; a++) {
        pilotage_appareil_t *ap = &p->app[a];
        uint8_t origine, etat = prevu(p, a, minute, &origine);
        if (ap->force && minute < ap->force_jusqua) {
            etat = ap->dernier_ordre;
            origine = PILOTAGE_ORDRE;
        } else {
            ap->force = 0;
        }
        if (etat != ap->etat) change |= 1u << a;
        ap->etat = etat;
        ap->origine = origine;
    }
    int j, m, h;
    pilotage_date(minute, &j, &m, &h);
    const pilotage_plan_t *pl = plan_du_jour(p, j, m);
    p->batterie = pl ? (uint8_t)((pl->batterie >> (2 * h)) & 3u) : BATTERIE_REPOS;
    p->minute = minute;
    return change;
}

int pilotage_confirmation(const pilotage_t *p, int a, char *topic, size_t tt, char *message, size_t tm)
{
    if (a < 0 || a >= PILOTAGE_NB_APPAREILS || !topic || !message || tt < 40 || tm < 4) return -1;
    strcpy(topic, PILOTAGE_TOPIC_BASE);
    strcat(topic, NOMS[a]);
    strcat(topic, "/etat");
    strcpy(message, p->app[a].etat ? "ON" : "OFF");
    return 0;
}
