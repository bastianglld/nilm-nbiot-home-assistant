# Étude des protocoles : le NB-IoT face aux protocoles existants

Auteur : Merveil (B). Réponse aux remarques d'Éric (slides 4, 5 et 8 du document d'avancement). Décision qui en découle : [ADR 0002](adr/0002-nbiot-liaison-boitier-serveur.md).

## L'idée : deux étages de communication

Le boîtier arrive dans une maison qui a déjà un compteur Linky, des appareils et une box. Deux étages de communication coexistent :

- **dans la maison**, des protocoles locaux relient les appareils entre eux et au boîtier : TIC, EEBus, Matter, Thread, Modbus ;
- **pour sortir de la maison**, le NB-IoT relie le boîtier au serveur, sans box ni Wi-Fi.

Le NB-IoT ne remplace pas les protocoles locaux : ils se complètent.

## 1. Du compteur à l'EMS

L'EMS doit connaître le tarif en cours et la consommation globale du logement. Ces informations viennent du compteur.

| | TIC du Linky (France) | Chain 2 (Italie) | Meters&More |
|---|---|---|---|
| Qui parle à qui | Compteur → maison | Compteur → maison | Compteur → distributeur |
| Support | Fil, bornes I1 / I2, porteuse 50 kHz | Courant porteur, bande C (125–140 kHz) | Courant porteur bande étroite, BPSK, 4,8 kbit/s |
| Données | Puissance, index, tarif en cours, couleur Tempo du jour et du lendemain | Consommation, production, alertes (coupure, dépassement) | Télérelève et télégestion |
| Rythme | 1 trame toutes les 1 à 2 s (mode standard, 9 600 bauds) ; mode historique à 1 200 bauds | Courbe toutes les 15 min | Selon le distributeur |
| Normes | Spécification Enedis (Enedis-NOI-CPT_54E) | CEI TS 13-82 (cas d'usage), 13-83 (modèle de données), 13-84 (profil CPL bande C) | Association Meters and More ; chiffrement AES-128 |
| Pour nous | **Retenu** : source du tarif et de la consommation | Même rôle que la TIC : le principe se transpose | Côté réseau : pas d'accès depuis la maison |

Dans notre boîtier, Bastian fabrique l'interface TIC et décode les trames ([`interface_tic.md`](interface_tic.md)) ; le module NB-IoT transmet le tarif et la puissance au serveur, en messages de 50 caractères au plus (format à ajouter à [`protocole_messages.md`](protocole_messages.md)).

## 2. Les protocoles des équipements face au NB-IoT

| Protocole | À quoi il sert | Support | Où | Face au NB-IoT |
|---|---|---|---|---|
| EEBus | Langage commun EMS ↔ pompe à chaleur, borne, onduleur (SHIP sur TLS + modèle SPINE ; référence en Allemagne, §14a EnWG) | IP local | Maison | Complémentaire |
| DLMS / COSEM | Modèle de données des compteurs | Tout support, dont IP (profil TCP-UDP, IEC 62056-9-7) | Compteur → réseau | Peut passer par le NB-IoT |
| Thread | Réseau radio maillé basse consommation (IPv6) | IEEE 802.15.4, 2,4 GHz | Maison | Local : routeur de bordure requis |
| Matter | Domotique grand public ; depuis la v1.4 : chauffe-eau, borne, batterie, solaire, pompe à chaleur | Wi-Fi, Thread, Ethernet | Maison | Local : contrôleur requis |
| Modbus | Onduleurs, batteries, compteurs d'énergie | RS-485 (RTU) ou TCP | Tableau électrique | Câblable au boîtier |
| **NB-IoT** | Réseau cellulaire basse consommation | Réseau de l'opérateur | Maison → cloud | **Le seul qui sort de la maison** |

## 3. Conclusion : le NB-IoT est-il pertinent ?

**Oui, pour :**
- envoyer les mesures et recevoir le planning sans box ni Wi-Fi ;
- fonctionner même si l'Internet de la maison est coupé ;
- déployer et gérer un grand parc de boîtiers via un opérateur ;
- consommer très peu (veille PSM, eDRX).

**Mais pas seul :**
- il ne parle pas aux appareils de la maison ;
- le boîtier ne pilote que ce qui lui est câblé (relais) ;
- Matter, Thread ou EEBus demandent un contrôleur local ;
- le débit et le budget de données sont limités : messages courts.

**Notre choix :** NB-IoT pour la liaison boîtier ↔ serveur ; TIC filaire pour le tarif et la consommation ; relais câblé pour le chauffe-eau et la batterie ; Modbus en option pour un vrai onduleur.

Ce choix rejoint la revue citée par le sujet (Cruz-Rangel et al., *Online non-intrusive load monitoring: A review*, Energy Nexus 17, 2025, DOI 10.1016/j.nexus.2024.100348) : le calcul sur l'appareil (*edge*) réduit fortement la bande passante nécessaire, ce qui rend un réseau bas débit comme le NB-IoT adapté ; les auteurs recommandent une architecture hybride *edge–cloud*, celle du projet ([ADR 0001](adr/0001-ia-repartie-carte-et-serveur.md)).

## Sources

- Selectra, prise TIC du Linky : https://selectra.info/energie/guides/compteurs/linky/prise-tic
- Home Assistant, intégration Teleinfo : https://www.home-assistant.io/integrations/teleinfo/
- Luce-gas.it, Chain 2 : https://luce-gas.it/guida/contatore/smart-meter-chain-2
- Selectra Italie, Chain 2 : https://selectra.net/energia/guida/contatore/chain-2
- Meters and More : https://metersandmore.com/
- Microchip, pile Meters And More : https://onlinedocs.microchip.com/oxy/GUID-85912321-7CF1-43FC-A1DB-EB72BC989E7B-en-US-3/GUID-6132706D-EBC9-4B0A-8BF8-9FA177FCF51A.html
- Innobu, EEBus et IEC 63380 : https://www.innobu.com/en/articles/eebus-iec-63380-han-hems-2026.html
- CSA, Matter 1.4 : https://csa-iot.org/newsroom/matter-1-4-enables-more-capable-smart-homes/
- IEC 62056-9-7 (profil TCP-UDP DLMS/COSEM) : https://online.standard.no/en/iec-62056-9-7-2013-ed1
- D. Cruz-Rangel, C. Ocampo-Martinez, J. Diaz-Rozo, *Online non-intrusive load monitoring: A review*, Energy Nexus 17 (2025) 100348
