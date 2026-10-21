# NILM connecté en NB-IoT pour l'optimisation énergétique sous Home Assistant

Projet M1 ESET (Université Savoie Mont Blanc), réalisé en équipe de 3 étudiants.
Sujet proposé par STMicroelectronics.

## Objectif

Identifier les appareils électriques d'un logement à partir d'une seule mesure au compteur (NILM), transmettre les données via NB-IoT (module ST87M01) vers un cloud sécurisé, puis les afficher dans Home Assistant. Dans une seconde phase, piloter certains équipements selon le prix de l'électricité.

## Phases

1. **Identification et télémesure** : acquisition des grandeurs électriques, classification des appareils, transmission NB-IoT, intégration dans Home Assistant.
2. **Pilotage et optimisation** : récupération des tarifs, décalage de la consommation lors des pics de prix.

## Architecture

Compteur → acquisition (STM32) → module ST87M01 (NB-IoT) → cloud (broker MQTT Mosquitto, TLS) → Home Assistant

Schéma détaillé à reprendre depuis le diaporama.

## Équipe

- Bastian Guilloud : NILM (IA) et flexibilité
- Mathieu Hegoburu : serveur, Home Assistant et sécurité (broker MQTT, TLS)
- Merveille-Joresse Ngoulou-Wamena : module NB-IoT ST87M01 et capteur

## Structure du dépôt

| Dossier | Contenu |
|---|---|
| `nilm/` | Modèle de détection des appareils : notebooks, code, modèles entraînés |
| `flexibilite/` | Simulation et pilotage : chauffe-eau, batterie, prix de l'électricité |
| `firmware/` | Commandes AT et scripts de test du ST87M01 |
| `homeassistant/` | Configuration MQTT Discovery, tableaux de bord |
| `cloud/` | Configuration Mosquitto (TLS, droits d'accès) |
| `docs/` | Rapport et décisions techniques (`docs/adr/`) |
| `data/` | Données de test anonymisées (voir `data/README.md`) |
| `tests/` | Tests automatisés |

## Lancer les notebooks

```bash
pip install -r requirements.txt
jupyter notebook nilm/notebooks/
```

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

- Code : [MIT](LICENSE) © 2026 Bastian Guilloud, Mathieu Hegoburu, Merveille-Joresse Ngoulou-Wamena
- Documents et figures (`docs/`) : [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr)
- Données UK-DALE : non incluses dans le dépôt, sous licence CC BY 4.0. Source : J. Kelly et W. Knottenbelt, « The UK-DALE dataset », *Scientific Data* 2:150007, 2015
