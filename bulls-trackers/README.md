# Bulls tracker

Suivi automatique des cotes Betclic (vainqueur du match) des Chicago Bulls, avec simulation
d'une mise de 5 € sur leur victoire à chaque match, saison régulière et playoffs inclus.

- `bulls_tracker.py` : tourne sur GitHub Actions toutes les 30 min. Enregistre la cote quand le
  match commence dans moins de 2 h, puis règle le pari une fois le match terminé.
- `data/bets.csv` : toutes les données (une ligne par match), mises à jour automatiquement.
- `summary.py` : bilan chiffré + graphiques, à lancer chez vous quand vous voulez.

## Installation (une seule fois)

1. **Clé API** : créez un compte gratuit sur https://the-odds-api.com et copiez votre clé.
2. **Dépôt GitHub** : créez un dépôt (privé ou public) et envoyez-y ce dossier :
   ```
   git init && git add . && git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/VOTRE-COMPTE/bulls-tracker.git
   git push -u origin main
   ```
3. **Secret** : dans le dépôt, *Settings → Secrets and variables → Actions → New repository secret*,
   nom `ODDS_API_KEY`, valeur = votre clé.
4. **Droits d'écriture** : *Settings → Actions → General → Workflow permissions* → **Read and write permissions**.
5. **Test** : onglet *Actions → Bulls tracker → Run workflow*. Les logs affichent les crédits API restants.

C'est tout : le workflow se déclenche ensuite tout seul.

## Faire le bilan

```
git pull
pip install -r requirements.txt
python summary.py --playoffs-from 2027-04-18
```
Remplacez la date par celle du premier match de playoffs (l'option est facultative). Le script
affiche les statistiques et crée `data/bilan.png`. Pour vos propres graphiques, `data/bets.csv`
contient notamment `date_paris`, `bulls_odds`, `result` (V/D), `profit` et `cumulative_profit`.

## Colonnes de `status`

| status | signification |
|---|---|
| `pending` | cote enregistrée, match pas encore réglé |
| `settled` | match terminé, gain ou perte calculé |
| `no_odds` | aucune cote Betclic capturée avant le match : pas de pari simulé |
| `unresolved` | score introuvable après 3 jours (match reporté ?) : à vérifier et corriger à la main |

## Bon à savoir

- **Quota API** : environ 4 crédits par match (1 pour la cote, 2 par vérification de score), soit
  une soixantaine par mois, bien en dessous du quota mensuel du plan gratuit.
- **Précision du moment de capture** : le script passe toutes les 30 min, la cote est donc relevée
  entre 2 h et 1 h 30 avant le coup d'envoi (GitHub peut ajouter quelques minutes de retard).
- **Minutes GitHub** : illimitées pour un dépôt public. Pour un dépôt privé, ce workflow
  consomme environ 1 500 min/mois sur les 2 000 incluses.
- **Inactivité** : GitHub peut désactiver les workflows planifiés d'un dépôt sans activité depuis
  60 jours (par exemple pendant l'intersaison). Il suffit de les réactiver dans l'onglet *Actions*.
- **Play-in** : ces matchs sont comptés comme de la saison régulière dans le bilan.
