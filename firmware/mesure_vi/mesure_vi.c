/* Mesure tension / courant – voir mesure_vi.h */
#include "mesure_vi.h"
#include <math.h>
#include <string.h>

void mesure_init(mesure_vi_t *m, uint32_t n_par_bloc, float k_v, float k_i, uint32_t blocs_par_minute)
{
    memset(m, 0, sizeof *m);
    m->n_par_bloc = n_par_bloc;
    m->k_v = k_v;
    m->k_i = k_i;
    m->blocs_par_minute = blocs_par_minute;
    m->vmin = m->imin = 0xFFFF;
}

int mesure_echantillon(mesure_vi_t *m, uint16_t v, uint16_t i)
{
    m->sv += v;
    m->si += i;
    m->svv += (int64_t)v * v;
    m->sii += (int64_t)i * i;
    m->svi += (int64_t)v * i;
    if (v < m->vmin) m->vmin = v;
    if (v > m->vmax) m->vmax = v;
    if (i < m->imin) m->imin = i;
    if (i > m->imax) m->imax = i;
    if (++m->n < m->n_par_bloc) return MESURE_RIEN;

    /* fin du bloc : moyennes en double pour garder la précision (sommes jusqu'à ~1e11) */
    double n = (double)m->n;
    double mv = (double)m->sv / n, mi = (double)m->si / n;
    double var_v = (double)m->svv / n - mv * mv;
    double var_i = (double)m->sii / n - mi * mi;
    double cov = (double)m->svi / n - mv * mi;
    if (var_v < 0) var_v = 0;
    if (var_i < 0) var_i = 0;

    m->v_moy_brut = (float)mv;
    m->i_moy_brut = (float)mi;
    m->vrms = m->k_v * (float)sqrt(var_v);
    m->irms = m->k_i * (float)sqrt(var_i);
    m->p = m->k_v * m->k_i * (float)cov;
    m->s = m->vrms * m->irms;
    m->fp = m->s > 0.0f ? m->p / m->s : 0.0f;
    m->v_min = m->vmin; m->v_max = m->vmax; m->i_min = m->imin; m->i_max = m->imax;
    m->blocs++;

    m->n = 0;
    m->sv = m->si = m->svv = m->sii = m->svi = 0;
    m->vmin = m->imin = 0xFFFF;
    m->vmax = m->imax = 0;

    m->sp_min += m->p;
    m->ss_min += m->s;
    if (++m->nb_min < m->blocs_par_minute) return MESURE_BLOC;
    m->p_minute = m->sp_min / (float)m->nb_min;
    m->s_minute = m->ss_min / (float)m->nb_min;
    m->sp_min = m->ss_min = 0.0f;
    m->nb_min = 0;
    m->minutes++;
    return MESURE_MINUTE;
}
