# Contribuer au projet

## Branches

- Ne jamais pousser directement sur `main`.
- Une branche par tâche, nommée `type/sujet` : `feature/nilm-modele`, `fix/tls-config`, `chore/structure-depot`.

## Commits

Format Conventional Commits, en français :

- `feat:` nouvelle fonctionnalité
- `fix:` correction
- `docs:` documentation
- `chore:` mise en place, configuration

Exemple : `feat(nilm): ajout du classifieur de signatures`

## Tests

Avant d'ouvrir une Pull Request, lancer depuis la racine du dépôt :

```bash
python -m unittest discover tests
```

Les mêmes tests tournent automatiquement sur GitHub à chaque Pull Request.

## Notebooks

- Garder les sorties quand elles montrent un résultat (tableaux, figures) ; les vider si elles contiennent des chemins ou des données personnelles.
- Nommer les notebooks `semaineNN_sujet.ipynb` pour qu'ils restent dans l'ordre.

## Pull Requests

1. Ouvrir une Pull Request depuis votre branche vers `main`.
2. Un coéquipier relit et approuve.
3. Le merge se fait après approbation.

## Règles

- Aucun identifiant, numéro de SIM, clé TLS ou jeton dans le dépôt. Utilisez des fichiers `.env` (ignorés par Git) et un `.env.example` sans valeurs réelles.
- Les données brutes ne sont pas versionnées (`data/raw/` est ignoré).
- Les mesures réelles doivent être anonymisées avant d'être ajoutées.
