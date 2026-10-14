# 🌿 uOttawa Evergreen Optimizer

MVP local de planification de déplacements d'ordinateurs, en français, avec Streamlit et NetworkX. Projet indépendant, sans affiliation officielle à l'Université d'Ottawa.

**Toutes les salles, connexions, distances, capacités, règles de compatibilité et quantités sont fictives.** Les noms MRT, UCU, STE et CBY sont une inspiration nominale. Ce projet ne représente ni un plan du campus, ni son inventaire, ni ses passages intérieurs réels.

## Démarrage sur Mac

Installer Python 3.11 ou 3.12 et Git, puis ouvrir Terminal :

```sh
git clone --branch feat/evergreen-mvp https://github.com/mhdiagne7/Evergreen.git
cd Evergreen
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Avec Python 3.11, remplacer `python3.12` par `python3.11`. Le Python 3.9 livré avec certains Mac est trop ancien.

## Démarrage sur Windows

Installer Python 3.11 ou 3.12 et Git, puis ouvrir PowerShell :

```powershell
git clone --branch feat/evergreen-mvp https://github.com/mhdiagne7/Evergreen.git
cd Evergreen
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Avec Python 3.11, utiliser `py -3.11`. Ces commandes n'exigent pas d'activer un script PowerShell. Après fusion de la PR, un simple `git clone` sans `--branch` utilisera la version de `main`.

Ouvrir http://127.0.0.1:8501 ; arrêter avec Ctrl+C. L'installation nécessite Internet ; les calculs utilisent ensuite les fichiers locaux. Aucun compte ni clé API requis. L'écoute est limitée à la machine locale et la collecte de statistiques Streamlit est désactivée.

## Parcours de démonstration

1. **Trajet** : MRT 1140 → UCU 214 donne **195 m simulés** via MRT Hall, MRT Exit et UCU Entry. Une même source/destination donne 0 m ; une salle isolée ne donne aucun chemin.
2. **Destinations compatibles** : déplacer 10 Dell OptiPlex 7050 de MRT 1140 propose MRT 120 (50 m), UCU 214 (195 m), STE 1030 (490 m). Chaque résultat est une alternative, pas un plan cumulatif.
3. **Regroupement Evergreen** : demander 25 Dell OptiPlex 7050 supplémentaires dans UCU 214 propose 10 depuis MRT 1140 et 8 depuis MRT 120. Les 12 ordinateurs existants laissent 18 places : il reste donc 7 unités non satisfaites. Exporter la proposition en CSV si nécessaire.
4. **Données fictives** : consulter les capacités, modèles autorisés et inventaires mixtes.

La compatibilité signifie : modèle explicitement autorisé, stock source suffisant, destination différente, chemin disponible et capacité totale suffisante **tous modèles confondus**. Elle ne constitue pas une évaluation technique réelle du matériel.

Le regroupement collecte un modèle vers une cible, depuis les sources accessibles par distance croissante. Il peut fractionner le stock d'une source. La quantité demandée est **supplémentaire** à l'inventaire de la cible. Chaque calcul repart des données initiales : aucune écriture, réservation ou exécution des déplacements. L'effort en ordinateur·m est la somme quantité × distance ; ce n'est pas une durée ni une distance de tournée.

## Structure

```text
app.py                  Interface Streamlit
core/data.py            CSV et validation
core/graph.py           Graphe bidirectionnel
core/routing.py         Dijkstra et absence de chemin
core/optimizer.py       Compatibilité et regroupement élémentaire
data/demo/              Trois CSV entièrement fictifs
tests/                  Tests métier et interactions Streamlit
ci/                     Configuration CI prête à activer
```

Le code métier ne dépend pas de Streamlit. Les chemins de données sont résolus depuis le code, sans chemin absolu lié au poste.

## Format des données

CSV UTF-8 avec en-têtes exacts, dans l'ordre indiqué :

| Fichier | Colonnes | Règles |
|---|---|---|
| `rooms.csv` | `room_id,building,capacity,allowed_models` | Salle unique ; capacité entière ≥ 0 ; modèles séparés par `\|` |
| `inventory.csv` | `room_id,model,quantity` | Paire salle/modèle unique ; quantité entière ≥ 0 ; salle existante ; modèle autorisé |
| `connections.csv` | `source,target,distance_m,distance_type` | Distance finie > 0 ; pas de boucle ni doublon non orienté ; `simulated` ou `estimated` |

Les points de connexion absents de `rooms.csv` sont des points de transit, sans inventaire. Une salle sans connexion reste valide mais inaccessible. Les inventaires qui dépassent une capacité sont rejetés. Les lignes incomplètes, colonnes incorrectes et fichiers vides sont rejetés avec un message dans l'interface.

**Simulée** signifie inventée pour la démonstration. **Estimée** signifie une approximation explicitement renseignée ; aucune distance estimée n'est fournie ici. Un chemin mélangeant les deux est marqué mixte. Aucune distance n'est présentée comme mesurée ou réelle.

## Vérification

Dans l'environnement virtuel sur Mac :

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Sur Windows :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Les tests couvrent les distances pondérées, trajets nuls et impossibles, compatibilité, stock, capacités mixtes, regroupements partiels, conservation des quantités, absence de mutation, CSV invalides et interactions de l'interface. La configuration `ci/github-actions-tests.yml` prévoit Python 3.11/3.12 sur Linux, macOS et Windows. Elle reste inactive : le jeton Git utilisé pour la livraison ne possède pas le droit `workflow`. Pour activer la CI, déplacer ce fichier vers `.github/workflows/tests.yml` puis publier avec un accès autorisé. Les tests locaux ont été exécutés sur macOS avec Python 3.12 ; les autres plateformes restent à vérifier par cette CI. Les dépendances utilisent des bornes de version majeure ; elles ne sont pas entièrement verrouillées.

## Données internes et limites

Conserver les données réelles hors du dépôt, idéalement dans un emplacement contrôlé par votre organisation. `.gitignore` exclut les données hors `data/demo/`, `private/`, `internal/`, `exports/`, secrets, bases et classeurs. Cette exclusion ne protège pas un fichier déjà suivi ni un ajout forcé : examiner `git diff --cached` avant chaque commit. Ne jamais remplacer les CSV de démonstration par de vrais inventaires dans une branche publiée.

Le MVP ne charge que `data/demo/` et ne propose pas d'import de données internes. Aucun plan géographique n'est inventé ou récupéré. Le graphe ne décrit ni accessibilité, escaliers, horaires, étages, obstacles ni règles de sécurité. Le regroupement est une heuristique simple à cible unique : pas de plan global multi-salles, durée, chariot, budget, âge matériel ou politique officielle Evergreen. Il ne doit pas être utilisé pour des déplacements réels sans données validées et revue humaine.

Pour évoluer : ajouter des contraintes validées, importer des données autorisées hors dépôt, puis comparer plusieurs cibles et suivre les mouvements approuvés.

## Références techniques

- [Streamlit : tests d'application](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)
- [NetworkX : Dijkstra](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths/dijkstra.html)
