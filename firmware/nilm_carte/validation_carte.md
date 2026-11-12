# Validation du NILM sur la carte (5 novembre 2026)

Montage : NUCLEO-N657X0-Q, modèle `nilm_int8.onnx` généré par ST Edge AI Core 2.2 pour le Cortex-M55 seul (API legacy), caches I et D activés. Le simulateur TIC rejoue la journée UK-DALE du 15 janvier 2014 (maison 1, période de test du modèle) à raison d'une minute simulée par seconde ; la carte décode les trames, calcule ses fenêtres de 272 minutes et renvoie ses messages sur le port du ST-LINK. Référence : le même modèle exécuté sur PC par onnxruntime (`attendu_nilm.py`).

```bash
python simulateur_tic.py envoyer --port /dev/tty.usbmodem102 --ukdale ../Modele_IA/house_1/an1 \
    --jour 2014-01-15 --accel 60 --retour --journal carte.txt --8n1
python nilm_carte/attendu_nilm.py --ukdale ../Modele_IA/house_1/an1 --jour 2014-01-15 --journal carte.txt
```

## Résultats

78 messages de 15 minutes attendus (02:15 à 21:30), **78 reçus**, aucune trame TIC rejetée.

| Appareil | Énergie PC | Énergie carte | Écart sur la journée | Quarts d'heure allumé/éteint identiques | Écart max sur un quart d'heure |
|---|---|---|---|---|---|
| Frigo | 1 011 Wh | 1 000 Wh | -1,1 % | 78 / 78 | 4 Wh |
| Bouilloire | 690 Wh | 691 Wh | +0,1 % | 78 / 78 | 7 Wh |
| Lave-linge | 2 587 Wh | 2 596 Wh | +0,3 % | 78 / 78 | 11 Wh |
| Lave-vaisselle | 26 Wh | 26 Wh | 0 % | 78 / 78 | 0 Wh |
| Total mesuré | 10 062 Wh | 10 062 Wh | 0 % | - | 0 Wh |

- Le total est identique sur les 78 messages : simulateur, décodeur TIC et moyennes par minute ne perdent rien.
- Les appareils sont reconnus dans les mêmes quarts d'heure que sur PC (bouilloire à 07:30, 07:45, 08:15, 12:45, 13:15, 17:00, 19:30, 20:15 ; lave-linge de 14:00 à 15:45 et de 18:15 à 20:00 ; lave-vaisselle à 18:15).
- 58 messages sont identiques à 1 Wh près ; les 20 autres diffèrent de 2 à 11 Wh, surtout pendant le lave-linge. Ce sont les arrondis du moteur int8 de ST (Cortex-M55) par rapport à onnxruntime : quelques minutes changent d'état près du seuil. Sur la journée, l'écart reste sous 1,1 % par appareil.

Durée d'un calcul du modèle sur le Cortex-M55 : **651 ms sans cache, 62 ms avec les caches** (un calcul toutes les 15 minutes).

## Même journée sur le NPU Neural-ART

Application [`../nilm_npu`](../nilm_npu) (dérivée de NPU_Validation de ST), même simulateur, même journée. **78 messages sur 78, 2,155 ms par calcul** (2,19 ms pour le premier), conversion des entrées et sorties comprise : environ 29 fois plus rapide que le Cortex-M55.

| Appareil | PC | Cortex-M55 | NPU | Quarts d'heure allumé/éteint identiques (NPU) | Écart max (NPU) |
|---|---|---|---|---|---|
| Frigo | 1 011 Wh | 1 000 Wh (-1,1 %) | 1 001 Wh (-1,0 %) | 76 / 78 | 5 Wh |
| Bouilloire | 690 Wh | 691 Wh (+0,1 %) | 723 Wh (+4,8 %) | 78 / 78 | 20 Wh |
| Lave-linge | 2 587 Wh | 2 596 Wh (+0,3 %) | 2 572 Wh (-0,6 %) | 77 / 78 | 11 Wh |
| Lave-vaisselle | 26 Wh | 26 Wh | 26 Wh | 78 / 78 | 0 Wh |
| Total mesuré | 10 062 Wh | 10 062 Wh | 10 062 Wh | - | 0 Wh |

- Comme sur le Cortex-M55, 58 messages sur 78 sont identiques au PC à 1 Wh près, et le total est identique partout.
- Le NPU n'arrondit pas exactement comme le moteur int8 du processeur ni comme onnxruntime : 38 messages sont strictement identiques entre processeur et NPU. Les écarts restent de quelques Wh, sauf pour la bouilloire à 19:30 (59 Wh au lieu de 39 sur PC) et à 12:45 (91 au lieu de 85), d'où les +4,8 % sur la journée.
- Les 3 quarts d'heure allumé/éteint différents sont des cas limites de quelques Wh (lave-linge à 5 Wh à 20:15 au lieu de 0).

## Problèmes rencontrés

- **Sonde ST-LINK qui décroche** (« libusb … pipe is stalled », « Target is not responding », « Load failed ») : le programme avec le modèle est plus gros et plus long à charger. Corrigé en réglant la fréquence de la sonde à 1 000 kHz (Debug Configurations > Debugger > Frequency).
- **Plantage de la sonde au bout de quelques minutes en débogage** : trop de Live Expressions lues en continu (dont des expressions en erreur) en plus du port série. Pendant ce plantage, les messages de la carte n'arrivent plus au PC. Pour un essai long, lancer en **Run** (la sonde se déconnecte du débogage et ne gère plus que le port série).
- **Liaison en 8N1** : la carte est réglée en 8N1 et le simulateur lancé avec `--8n1` (parité TIC calculée par le script dans le 8e bit, même signal sur le fil).
- **Envoi au milieu d'une trame** : un message envoyé par la carte pendant la réception d'une trame fait perdre des octets (envoi et réception par scrutation dans la même boucle). Les messages NILM partent juste après la fin d'une trame et ne sont pas concernés.

## Programme complet (`appli_nilm`, mode `SOURCE_TIC`) — 5 novembre 2026

Même essai (UK-DALE maison 1, 2014-01-15, `--accel 60 --8n1 --retour`) avec le programme unifié de `tic_test` (mesure, NILM et envoi réunis dans `appli_nilm.c`). Les 25 premiers messages (02:15 → 08:15) sont **identiques au caractère près** à ceux du premier essai CPU : le passage au programme complet ne change rien au résultat.

**Trames abîmées** (`--erreurs 5 --nb 400`) : 9 messages sur 9, aux bonnes heures (02:15 → 04:15), pas de plantage. Le total baisse de 3 à 8 Wh par quart d'heure : avec `--accel 60` une trame vaut une minute, donc une trame rejetée retire une minute de mesure. Avec le vrai Linky (une trame par seconde), une trame rejetée ne retire qu'un soixantième de la minute.

## Programme complet, mode `SOURCE_VI` — premier essai sans générateur (5 novembre 2026)

A0 et A1 à la masse, simulateur à l'heure réelle (`--puissance 0 --nb 200 --retour`) pour donner l'heure : une ligne par minute, à l'heure juste (`VI 1518`, `VI 1519`, `VI 1520`), valeurs nulles (U = 0, I = 0, P = 0, S = 0). Reste à faire au générateur : valeurs non nulles, étalonnage, déphasage.

## Programme complet avec le NILM sur le NPU — 6 novembre 2026

Même programme `tic_test`, `NILM_SUR_NPU 1` (`nilm_ia_npu.c`) : modèle régénéré avec tout en mémoire interne (profil `nilm-interne`, [`../nilm_npu/interne`](../nilm_npu/interne)), poids recopiés dans l'AXISRAM3 au démarrage. Plus de flash externe ni de `n6_loader.py` : un simple **Run** dans CubeIDE suffit.

| Essai (UK-DALE 2014-01-15, `--accel 60 --8n1 --retour`) | Messages | Temps par calcul | Résultat |
|---|---|---|---|
| Programme complet, NILM sur le Cortex-M55 (`NILM_SUR_NPU 0`) | 15 | 64,5 à 65,3 ms | identique à l'essai CPU du 5 novembre |
| Programme complet, NILM sur le NPU (`NILM_SUR_NPU 1`) | 25 (02:15 → 08:15) | **6,03 à 6,07 ms** | **identique au caractère près** au NPU du 5 novembre (projet `nilm_npu`, poids en flash externe), bouilloire de 07:30 comprise |

Le calcul prend 6 ms au lieu de 2,2 ms parce que le NPU est cadencé à 300 MHz dans `tic_test` (IC6, réglage CubeMX) contre 1 GHz dans le projet d'ST ; c'est 10 fois plus rapide que le processeur et largement suffisant pour un calcul toutes les 15 minutes.

**Problème rencontré : le premier calcul ne finissait jamais.** Le moteur LL_ATON met le processeur en veille (`WFE`) en attendant la fin de chaque étape du NPU ; or, par défaut, la veille coupe aussi l'horloge du NPU et de ses RAM. La carte recevait les trames pendant 4 min 30 puis restait bloquée au premier calcul (diagnostic : délai d'une seconde ajouté, message `NILM ERREUR calcul=-10`). Corrigé dans `npu/npu_materiel.c` en gardant ces horloges pendant la veille (`__HAL_RCC_xxx_CLK_SLEEP_ENABLE`, comme `set_clk_sleep_mode()` d'ST) et en attendant le NPU en boucle plutôt qu'en veille.

## Mesure V/I au générateur, programme complet — 6 novembre 2026

`SOURCE_PUISSANCE SOURCE_VI`, `CAPTEURS_REELS 0` : la ligne de chaque minute donne U et I efficaces en mV sur le connecteur et le facteur de puissance en centièmes. Générateur Keysight deux voies, 50 Hz, offset 1,65 V : voie 1 sur A1 (tension), voie 2 sur A0 (courant). Référence : oscilloscope Keysight EDUX1052A, mesure « CA EFF – N cycles » et phase.

| Grandeur | Oscilloscope | Carte | Écart |
|---|---|---|---|
| U (A1) | 383,9 mV | 384 mV | < 0,1 % |
| I (A0) | 182,9 mV | 181 à 182 mV | 0,5 % |
| Déphasage voies synchronisées | 0° → cos = 1,00 | fp = 0,99 | 0,01 |
| Déphasage 60° | −59,6° → cos = 0,507 | fp = 0,50 à 0,51 | < 0,01 |
| Voies non synchronisées (piège du générateur) | −127° → cos = −0,60 | fp = −0,65 | angle à 3° près |

**Étalonnage : `CORRECTION_V = CORRECTION_I = 1,00`.** Le gain théorique de l'étage d'entrée Arduino de la carte (0,54) est juste, les écarts sont dans la précision de l'oscilloscope. Reste à vérifier avec la pince SCT-013 et l'adaptateur 230 V → 9 V (`CAPTEURS_REELS 1`) dès leur réception.

Pièges : sur un générateur deux voies, « phase 0° » ne suffit pas, il faut **aligner les phases** (menu Phase > Align Phase) ; sonde de l'oscilloscope en ×10 avec la voie réglée en 1:1 → valeur affichée 10 fois trop petite (régler « Sonde » sur 10:1).
