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

Durée d'un calcul du modèle sur le Cortex-M55 : **651 ms sans cache, 62 ms avec les caches** (un calcul toutes les 15 minutes). Sur le NPU Neural-ART, la validation de la semaine 7 donnait 2 ms.

## Problèmes rencontrés

- **Sonde ST-LINK qui décroche** (« libusb … pipe is stalled », « Target is not responding », « Load failed ») : le programme avec le modèle est plus gros et plus long à charger. Corrigé en réglant la fréquence de la sonde à 1 000 kHz (Debug Configurations > Debugger > Frequency).
- **Plantage de la sonde au bout de quelques minutes en débogage** : trop de Live Expressions lues en continu (dont des expressions en erreur) en plus du port série. Pendant ce plantage, les messages de la carte n'arrivent plus au PC. Pour un essai long, lancer en **Run** (la sonde se déconnecte du débogage et ne gère plus que le port série).
- **Liaison en 8N1** : la carte est réglée en 8N1 et le simulateur lancé avec `--8n1` (parité TIC calculée par le script dans le 8e bit, même signal sur le fil).
- **Envoi au milieu d'une trame** : un message envoyé par la carte pendant la réception d'une trame fait perdre des octets (envoi et réception par scrutation dans la même boucle). Les messages NILM partent juste après la fin d'une trame et ne sont pas concernés.
