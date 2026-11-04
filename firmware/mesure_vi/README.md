# Mesure tension / courant (partie C)

[`mesure_vi.h`](mesure_vi.h) / [`mesure_vi.c`](mesure_vi.c) calculent, à partir des échantillons de l'ADC, la tension et le courant efficaces, la puissance active P, la puissance apparente S et le facteur de puissance, puis leur moyenne sur la minute (l'entrée du modèle NILM). Le code ne dépend pas du HAL.

La composante continue (point milieu VMID) est retirée par le calcul : `Vrms² = moyenne(v²) − moyenne(v)²` et `P = moyenne(v·i) − moyenne(v)·moyenne(i)`. Pas besoin de connaître VMID exactement.

| Fichier | Rôle |
|---|---|
| `mesure_vi.h`, `mesure_vi.c` | Calcul, échantillon par échantillon (4 kHz conseillé, blocs d'une seconde) |
| `test_pc.c` | Test sur PC avec des sinusoïdes synthétiques (déphasage, harmonique 3) |
| `integration_stm32.c` | Réglages CubeMX et blocs à coller dans `main.c` : ADC1 déclenché par TIM6 à 4 kHz, interruption de fin de conversion |

## Entrées de la NUCLEO-N657X0-Q

| Connecteur | Broche | Voie ADC | Signal |
|---|---|---|---|
| A1 | PA9 | ADC1_INP10 | courant (pince) |
| A2 | PA10 | ADC1_INP11 | tension (adaptateur secteur) |

L'ADC du STM32N6 accepte 1,8 V au plus. Sur cette NUCLEO, au moins l'entrée A5 passe par un suiveur et un pont de rapport 0,54 qui permettent jusqu'à 3,3 V sur le connecteur (réponse ST sur le forum, schéma MB1940). Le premier test au GBF vérifie si A1 et A2 ont le même pont : il décide si le point milieu doit être à 1,65 V ou à 0,9 V.

## Test sur PC

```bash
gcc -Wall -Wextra -std=c11 -o test_pc test_pc.c mesure_vi.c -lm
./test_pc                     # tension et courant en phase
./test_pc 1500 800 60 0.3     # courant déphasé de 60° avec 30 % d'harmonique 3
```

## Test sur la carte avec un GBF (avant d'avoir la pince)

Sortie du GBF en mode « High Z », vérifiée à l'oscilloscope avant de brancher. Masse du GBF sur une broche GND de la carte, signal sur A1 et A2.

1. **Détection du pont, signal sans risque** : sinus 50 Hz, 1 Vpp, offset 0,9 V (le signal reste entre 0,4 et 1,4 V). Lire `mes.v_moy_brut` :
   - environ 1 100 : pont de 0,54 présent, le connecteur accepte 0 à 3,3 V, point milieu à 1,65 V ;
   - environ 2 050 : pas de pont, rester entre 0 et 1,8 V, point milieu à 0,9 V, et mettre `RAPPORT_CARTE` à 1.0f.
2. **Valeurs efficaces** : avec `K_V = K_I = V_CONNECTEUR`, `mes.vrms` et `mes.irms` doivent valoir 0,354 V (1 Vpp), `mes.fp` doit valoir 1. Comparer au multimètre ou à l'oscilloscope.
3. **Déphasage** (GBF à deux voies, même fréquence, voie 2 déphasée de 60°) : `mes.fp` ≈ 0,5.
4. **Saturation** : `mes.v_min`/`mes.v_max` ne doivent jamais atteindre 0 ou 4095.

Ensuite, avec les capteurs, il suffit de changer `K_V` et `K_I` (formules dans `integration_stm32.c`) et d'étalonner contre une charge connue.
