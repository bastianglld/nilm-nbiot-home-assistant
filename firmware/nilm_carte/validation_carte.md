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
