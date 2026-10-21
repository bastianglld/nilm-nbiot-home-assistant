# Données

Les données brutes ne sont pas versionnées (dossier `data/raw/`, ignoré par Git).

## UK-DALE

- Nom : UK Domestic Appliance-Level Electricity (UK-DALE), maison 1
- Lien : https://jack-kelly.com/data/ (archive du UK Energy Research Centre)
- Licence : CC BY 4.0
- Référence : J. Kelly et W. Knottenbelt, « The UK-DALE dataset, domestic appliance-level electricity demand and whole-house demand from five UK homes », *Scientific Data* 2:150007, 2015

Fichiers utilisés (dossier de la maison 1, format `.dat` à 6 s) : `labels.dat` et les canaux de la maison entière (`aggregate`), du frigo, de la bouilloire, du lave-linge et du lave-vaisselle.

Placez le dossier téléchargé dans `data/raw/ukdale/house_1/` (ou ailleurs) et indiquez son chemin dans la variable `DATA_DIR` de la première cellule de code de chaque notebook.

## Données simulées

La semaine 5 ajoute des foyers simulés avec LoadProfileGenerator (https://www.loadprofilegenerator.de). Les fichiers générés, très volumineux, restent en local.

## Prix de l'électricité

Les couleurs Tempo et les prix spot utilisés dans les simulations sont versionnés dans [`../nilm/notebooks/prix/`](../nilm/notebooks/prix/) (quelques dizaines de Ko).

## Mesures réelles

Anonymisez-les avant de les versionner : une courbe de consommation révèle les habitudes du foyer.
