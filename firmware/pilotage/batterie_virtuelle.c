#include "batterie_virtuelle.h"

void bv_init(batterie_virtuelle_t *b)
{
    b->capacite_kwh = 5.0f;
    b->puissance_kw = 2.5f;
    b->rendement = 0.95f;
    b->reserve_kwh = 0.5f;
    b->stock_kwh = 2.5f;
}

float bv_minute(batterie_virtuelle_t *b, uint8_t mode, float conso_w)
{
    const float pas_kwh = b->puissance_kw / 60.0f;          /* énergie maximale sur une minute */
    if (mode == 1)
    {
        float place = (b->capacite_kwh - b->stock_kwh) / b->rendement;   /* ce qu'on peut encore acheter */
        float c = pas_kwh < place ? pas_kwh : place;
        if (c < 0.0f) c = 0.0f;
        b->stock_kwh += b->rendement * c;
        return c * 1000.0f;
    }
    if (mode == 2)
    {
        float dispo = (b->stock_kwh - b->reserve_kwh) * b->rendement;    /* ce que la maison peut recevoir */
        float besoin = (conso_w > 0.0f ? conso_w : 0.0f) / 60000.0f;     /* conso de la minute en kWh */
        float d = pas_kwh;
        if (dispo < d) d = dispo;
        if (besoin < d) d = besoin;
        if (d < 0.0f) d = 0.0f;
        b->stock_kwh -= d / b->rendement;
        return -d * 1000.0f;
    }
    return 0.0f;
}

int bv_pourcent(const batterie_virtuelle_t *b)
{
    int p = (int)(100.0f * b->stock_kwh / b->capacite_kwh + 0.5f);
    return p < 0 ? 0 : (p > 100 ? 100 : p);
}

int bv_niveau(const batterie_virtuelle_t *b, int nb)
{
    int n = (int)((float)nb * b->stock_kwh / b->capacite_kwh + 0.5f);
    return n < 0 ? 0 : (n > nb ? nb : n);
}
