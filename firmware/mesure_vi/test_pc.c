/*
 * Test de mesure_vi sur PC, sans carte : fabrique des sinusoïdes 50 Hz échantillonnées à 4 kHz
 * comme les donnerait l'ADC 12 bits, et compare au calcul théorique.
 *     gcc -Wall -Wextra -std=c11 -o test_pc test_pc.c mesure_vi.c -lm && ./test_pc
 * Arguments facultatifs : amplitude_v amplitude_i (en points ADC) dephasage_deg harmonique3_i (0..1)
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include "mesure_vi.h"

#define FE 4000.0
#define F  50.0
#define PI 3.14159265358979323846

static uint16_t adc(double x)
{
    long r = lround(x);
    return (uint16_t)(r < 0 ? 0 : r > 4095 ? 4095 : r);
}

int main(int argc, char **argv)
{
    double av = argc > 1 ? atof(argv[1]) : 1500.0;   /* amplitude crête en points ADC */
    double ai = argc > 2 ? atof(argv[2]) : 1000.0;
    double phi = (argc > 3 ? atof(argv[3]) : 0.0) * PI / 180.0;
    double h3 = argc > 4 ? atof(argv[4]) : 0.0;      /* part d'harmonique 3 dans le courant */
    double mid = 2048.0;

    mesure_vi_t m;
    mesure_init(&m, 4000, 1.0f, 1.0f, 60);           /* k = 1 : résultats en points ADC */
    for (long n = 0; n < 4000L * 60; n++) {
        double t = n / FE;
        double v = mid + av * sin(2 * PI * F * t);
        double i = mid + ai * (sin(2 * PI * F * t - phi) + h3 * sin(3 * 2 * PI * F * t));
        mesure_echantillon(&m, adc(v), adc(i));
    }
    double irms_th = ai / sqrt(2.0) * sqrt(1.0 + h3 * h3);
    double p_th = av * ai / 2.0 * cos(phi);
    printf("Vrms %.2f (théorie %.2f)\n", m.vrms, av / sqrt(2.0));
    printf("Irms %.2f (théorie %.2f)\n", m.irms, irms_th);
    printf("P    %.1f (théorie %.1f)\n", m.p, p_th);
    printf("S    %.1f (théorie %.1f)\n", m.s, av / sqrt(2.0) * irms_th);
    printf("fp   %.4f (théorie %.4f)\n", m.fp, p_th / (av / sqrt(2.0) * irms_th));
    printf("VMID %.1f / %.1f  extrêmes v %u..%u i %u..%u\n", m.v_moy_brut, m.i_moy_brut,
           m.v_min, m.v_max, m.i_min, m.i_max);
    printf("blocs %lu minutes %lu  P_minute %.1f S_minute %.1f\n",
           (unsigned long)m.blocs, (unsigned long)m.minutes, m.p_minute, m.s_minute);
    return 0;
}
