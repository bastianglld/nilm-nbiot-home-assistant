# Simulateur TIC Linky

Partie C (Bastian Guilloud). [`simulateur_tic.py`](simulateur_tic.py) joue le rôle du compteur Linky pour tester le décodeur TIC de la carte sans compteur ni interface optocoupleur. Il sait aussi lire et enregistrer un vrai Linky, puis rejouer l'enregistrement.

Format des trames et câblage de l'interface réelle : [`../../docs/interface_tic.md`](../../docs/interface_tic.md). Référence : spécification Enedis-NOI-CPT_54E.

## Installation

```bash
pip install pyserial        # seulement pour utiliser un vrai port série
```

## Les trois commandes

| Commande | À quoi elle sert |
|---|---|
| `envoyer` | Fabrique des trames et les envoie sur un port série (ou dans un fichier) |
| `lire` | Lit des trames (port série ou fichier), vérifie les sommes de contrôle, affiche les valeurs ; peut enregistrer les octets bruts |
| `rejouer` | Renvoie un enregistrement brut sur un port série |

```bash
# trames en mode standard, offre Tempo jour rouge, une par seconde
python simulateur_tic.py envoyer --port /dev/tty.usbmodem1103 --offre tempo --couleur ROUGE --demain BLANC

# rejouer une journée UK-DALE dans SINSTS, 1 minute simulée par trame, 5 % de trames abîmées
python simulateur_tic.py envoyer --port COM5 --ukdale ~/UK-DALE/house_1 --jour 2013-12-31 --accel 60 --erreurs 5

# mode historique (1 200 bauds), offre heures creuses
python simulateur_tic.py envoyer --port COM5 --mode historique --offre hphc

# sans carte : écrire 20 trames dans un fichier, puis les relire
python simulateur_tic.py envoyer --sortie trames.bin --nb 20 --erreurs 10 --afficher
python simulateur_tic.py lire --fichier trames.bin

# enregistrer un vrai Linky (à travers l'interface optocoupleur et un adaptateur USB-série), puis le rejouer
python simulateur_tic.py lire --port /dev/tty.usbserial-A1 --enregistrer linky.bin
python simulateur_tic.py rejouer --port /dev/tty.usbmodem1103 --fichier linky.bin
```

`python simulateur_tic.py envoyer -h` liste toutes les options.

## Branchement pour tester le décodeur de la carte

| Montage | Branchement | Côté carte |
|---|---|---|
| Port série virtuel du ST-LINK | Câble USB de la NUCLEO, rien d'autre | L'USART relié au ST-LINK (probablement USART1, à confirmer dans le manuel UM3417) |
| Adaptateur USB-série 3,3 V (CP2102, FTDI, CH340) | TX de l'adaptateur sur la broche RX choisie pour la TIC, masses reliées | L'USART prévu pour la TIC |

Réglage de l'USART de la carte : 9 600 bauds (standard) ou 1 200 bauds (historique), mot de 8 bits avec parité paire, 1 bit de stop. On masque ensuite le bit 7 de chaque octet reçu.

Si le port série du PC refuse le format 7 bits et parité paire (certains ports virtuels), ajouter `--8n1` : le script envoie en 8N1 en plaçant lui-même le bit de parité dans le 8e bit. Le signal sur le fil est identique.

## Ce que contiennent les trames

- **Mode standard** : `ADSC`, `VTIC`, `DATE`, `NGTF`, `LTARF`, `EAST`, `EASF01`/`EASF02`, `IRMS1`, `URMS1`, `PREF`, `PCOUP`, `SINSTS`, `SMAXSN`, `UMOY1`, `STGE` (couleur Tempo du jour en bits 24-25, du lendemain en bits 26-27), `NTARF`, `MSG1`.
- **Mode historique** : `ADCO`, `OPTARIF`, `ISOUSC`, index (`BASE`, `HCHC`/`HCHP` ou `BBRxxx`), `PTEC`, `IINST`, `IMAX`, `PAPP`, `HHPHC`, `MOTDETAT`, et `DEMAIN` en Tempo.
- Les index augmentent avec la puissance simulée (facteur de puissance de 0,9). Les libellés de tarif (`LTARF`) sont indicatifs : chaque fournisseur choisit les siens.

Erreurs volontaires (`--erreurs`) : somme de contrôle fausse, caractère modifié, trame interrompue (EOT), ETX manquant. Le décodeur doit rejeter la ligne ou la trame concernée.

La somme de contrôle de la TIC ne tient que sur 6 bits : un caractère remplacé par un autre dont le code diffère d'un multiple de 64 passe inaperçu. C'est une limite du protocole ; le simulateur n'injecte pas ce cas.

## Décodeur en C pour la carte

| Fichier | Rôle |
|---|---|
| [`tic_decodeur.h`](tic_decodeur.h), [`tic_decodeur.c`](tic_decodeur.c) | Décodeur portable : octet par octet, trames, sommes de contrôle, modes standard et historique détectés automatiquement |
| [`test_pc.c`](test_pc.c) | Test sur PC avec les fichiers du simulateur, sans carte |
| [`integration_stm32.c`](integration_stm32.c) | Blocs à coller dans le `main.c` de STM32CubeIDE (réception par scrutation) |

Valeurs disponibles après chaque trame valide : `papp_va` (SINSTS ou PAPP), `index_total_wh`, `irms_a`, `urms_v`, `pref_kva`, `tarif`, `horodate`, `stge`, `couleur_jour`, `couleur_demain`, et des compteurs de diagnostic (`trames_ok`, `trames_erreur`, `trames_interrompues`, `lignes_rejetees`).

Test sur PC :

```bash
python simulateur_tic.py envoyer --sortie trames.bin --nb 20 --erreurs 10
gcc -Wall -Wextra -std=c11 -o test_pc test_pc.c tic_decodeur.c && ./test_pc trames.bin
```

Test sur la carte :

1. Dans STM32CubeMX (carte NUCLEO-N657X0-Q, « Secure domain only »), catégorie **Bsp** > NUCLEO-N657X0-Q : contexte FSBL et « Virtual Com Port » cochés. Le port du ST-LINK (USART1, PE5/PE6) est géré par le BSP sous le nom `COM1`. Générer le code pour STM32CubeIDE et l'importer.
   Copier le décodeur dans `FSBL/Core/`, coller les blocs de `integration_stm32.c` dans `main.c` (sections Includes, PV, WHILE avant `while (1)`, et 3) : le port est réinitialisé en 9 600 bauds, 8 bits avec parité paire, et lu par scrutation dans la boucle principale.
2. Lancer en débogage et ajouter dans « Live Expressions » : `nb_octets_recus`, `nb_erreurs_uart`, `tic.papp_va`, `tic.trames_ok`, `tic.lignes_rejetees`, `tic.couleur_jour`. La LED verte change d'état à chaque trame valide.
3. Sur le PC, envoyer des trames sur le port du ST-LINK (`ls /dev/tty.usbmodem*` sur Mac) :
   `python simulateur_tic.py envoyer --port /dev/tty.usbmodemXXXX --offre tempo --couleur ROUGE --afficher`
4. `tic.papp_va` doit suivre la puissance affichée par le simulateur. Avec `--erreurs 20`, `tic.lignes_rejetees` augmente et `tic.papp_va` reste juste.

Si `nb_octets_recus` reste à 0 : mauvais USART ou port. S'il augmente sans trame valide : vérifier 9 600 bauds, mot de 8 bits avec parité paire, ou relancer le simulateur avec `--8n1`.

Tests : `python -m unittest tests.test_simulateur_tic tests.test_decodeur_tic_c` depuis la racine du dépôt.
