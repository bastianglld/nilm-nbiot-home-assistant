# Mesure tension / courant (partie C)

[`mesure_vi.h`](mesure_vi.h) / [`mesure_vi.c`](mesure_vi.c) calculent, à partir des échantillons de l'ADC, la tension et le courant efficaces, la puissance active P, la puissance apparente S et le facteur de puissance, puis leur moyenne sur la minute (l'entrée du modèle NILM). Le code ne dépend pas du HAL.

La composante continue (point milieu VMID) est retirée par le calcul : `Vrms² = moyenne(v²) − moyenne(v)²` et `P = moyenne(v·i) − moyenne(v)·moyenne(i)`. Pas besoin de connaître VMID exactement.

| Fichier | Rôle |
|---|---|
| `mesure_vi.h`, `mesure_vi.c` | Calcul, échantillon par échantillon (4 kHz conseillé, blocs d'une seconde) |
| `test_pc.c` | Test sur PC avec des sinusoïdes synthétiques (déphasage, harmonique 3) |
| `integration_stm32.c` | Réglages CubeMX et blocs à coller dans `main.c` : ADC1 déclenché par TIM6 à 4 kHz, interruption de fin de conversion |

## Entrées de la NUCLEO-N657X0-Q

| Connecteur | Broche | Voie ADC | Signal | Plage sur le connecteur |
|---|---|---|---|---|
| A0 (CN4) | PA8 | ADC1 canal 5 | courant (pince) | 0 à 3,3 V |
| A1 (CN4) | PA9 | ADC1 canal 10 | tension (adaptateur secteur) | 0 à 3,3 V |

D'après le manuel UM3417 (table 17), chaque trou A0 à A5 est relié à deux broches : une entrée ADC derrière un ampli qui ramène 0..3,3 V à 0..1,8 V (rapport mesuré 0,54), et une broche numérique en direct. Le point milieu des capteurs est donc à **1,65 V** (deux résistances de 10 kΩ depuis le 3V3).

**Piège du STM32N6 : l'isolation RIF.** Au démarrage, les broches sont « sécurisées » mais l'ADC12 ne l'est pas : l'ADC ne voit alors aucune broche et lit environ 1 200 sur tous les canaux, même une broche reliée au GND. Il faut donner aux broches le même attribut que l'ADC (`HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_8 | GPIO_PIN_9, GPIO_PIN_NSEC | GPIO_PIN_NPRIV)`), ou rendre les deux sécurisés comme dans les exemples d'ST.

Autres réglages trouvés sur carte : Sampling Time de 1 499,5 cycles (sinon le rang 1 est perdu en interruption), horloge ADC divisée par 4 (50 MHz), Prescaler de TIM6 à 99 pour 4 kHz. Détails dans [`integration_stm32.c`](integration_stm32.c).

## Validation sur carte (4 novembre 2026)

GBF : sinus 50 Hz, 1 Vpp, offset 1,65 V, sortie High Z.

| Montage | Vrms (A1) | Irms (A0) | fp | Cadence |
|---|---|---|---|---|
| A0 seul | 0,002 V | 0,370 V | - | 4 000 Hz |
| A1 seul | 0,370 V | 0,001 V | - | 4 000 Hz |
| A0 et A1 reliés | 0,370 V | 0,370 V | 0,9999 | 4 000 Hz |

Les deux voies concordent à 0,05 % près. L'écart de 4,6 % avec les 0,354 V théoriques est commun aux deux voies (amplitude réelle du GBF ou gain exact de l'ampli) : il se corrige par étalonnage contre un multimètre.

## Test sur PC

```bash
gcc -Wall -Wextra -std=c11 -o test_pc test_pc.c mesure_vi.c -lm
./test_pc                     # tension et courant en phase
./test_pc 1500 800 60 0.3     # courant déphasé de 60° avec 30 % d'harmonique 3
```

## Test sur la carte avec un GBF (avant d'avoir la pince)

Sortie du GBF en mode « High Z », réglage vérifié à l'oscilloscope **avant** de brancher (rester entre 0 et 3,3 V). Masse du GBF sur une boucle GND de la carte, signal sur A0 et/ou A1.

1. **Contrôle de la mesure** : `cadence_hz` ≈ 4 000 et `nb_rang1` qui suit `nb_echantillons`.
2. **Valeurs efficaces** : sinus 50 Hz, 1 Vpp, offset 1,65 V. `mes.vrms` et `mes.irms` ≈ 0,354 V, `mes.fp` ≈ 1 avec A0 et A1 reliés. Comparer au multimètre (V~).
3. **Déphasage** (GBF à deux voies, même fréquence, voie 2 déphasée de 60°) : `mes.fp` ≈ 0,5.
4. **Saturation** : `mes.v_min`/`mes.v_max` ne doivent jamais atteindre 0 ou 4095.

Ensuite, avec les capteurs, il suffit de changer `K_V` et `K_I` (formules dans `integration_stm32.c`) et d'étalonner contre une charge connue.

## Voie tension réelle sur la carte (25 novembre 2026)

Montage sur breadboard, carte avec le Grove Base Shield (3V3 et GND du shield) :

- adaptateur **Mascot 8510** (230 V → 9 V AC, 780 mA, double isolation), branché sur la multiprise mesurée, relié par un jack DC femelle pour circuit imprimé (patte du milieu et patte du fond ; la patte de côté est le contact de coupure) ;
- secondaire mesuré à vide : **10,7 V efficaces** (rapport `SECTEUR_V / SECONDAIRE_V` = 230 / 10,7 dans `appli_nilm.c`) ;
- pont R5 = 100 kΩ / R6 = 8,2 kΩ, point milieu R7 = R8 = 10 kΩ + C2 = 10 µF ; signal sur A1 entre 0,5 et 2,8 V ;
- A0 relié au point milieu tant que la pince n'est pas là (courant nul).

Contrôles avant de relier A1 : 1,65 V (V⎓) sur le point milieu et sur la jonction R5-R6, 0,8 V (V~) entre les deux, transformateur branché. Une erreur trouvée ainsi : R7 et R8 inversées avec des valeurs différentes donnaient 3,0 V au lieu de 1,65 V.

Programme `tic_test` avec `SOURCE_PUISSANCE = SOURCE_VI` et `CAPTEURS_REELS = 1`, une ligne par minute :

| Grandeur | Relevé sur 13 minutes | Commentaire |
|---|---|---|
| U | 225,6 à 227,1 V | stable à ± 0,4 % ; écart à 230 V dans la tolérance du secteur et de l'étalonnage (à affiner avec le wattmètre de prise) |
| I | 0,11 à 0,12 A | bruit de la voie courant sans pince : plancher de mesure |
| S | 26 à 27 VA | conséquence du bruit sur I (U × I) ; à retirer à l'étalonnage de la pince |
| P | 2 à 3 W | le bruit n'est pas en phase avec la tension : il pèse peu sur P |

Ordre de branchement : 3V3 et GND d'abord, puis le transformateur, et le fil vers A1 en dernier (sans 3V3, le point milieu tombe à 0 V et A1 verrait des tensions négatives). Débrancher dans l'ordre inverse.
