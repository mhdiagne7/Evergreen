# Evergreen

Evergreen aide à préparer des déplacements d'ordinateurs : on choisit une salle de départ, un modèle et une quantité, puis l'application propose les salles qui peuvent les accueillir, de la plus proche à la plus éloignée.

Le projet commence avec un petit jeu de données fictives inspiré des noms MRT, UCU, STE et CBY de uOttawa. Les salles, liaisons, distances et inventaires de démonstration sont inventés. Ils ne décrivent pas le campus et le projet n'est pas affilié à l'université.

## Ouvrir l'application sur cette ordi

Le dossier se trouve maintenant dans **Documents/Evergreen**. Dans Finder, ouvrir ce dossier et double-cliquer sur **Lancer-Evergreen.command**. Garder la fenêtre du Terminal ouverte pendant l'utilisation.

On peut aussi la lancer depuis Terminal :

```sh
cd ~/Documents/Evergreen
.venv/bin/python -m streamlit run app.py
```

L'application est accessible sur http://127.0.0.1:8501. Pour l'arrêter, utiliser Ctrl+C dans le Terminal.

Si une ancienne fenêtre affiche une erreur « No such file or directory » avec un chemin contenant `.codex`, arrêter le serveur dans cette fenêtre avec Ctrl+C, puis utiliser le lanceur depuis Documents. Le lanceur retrouve le projet à partir de son propre emplacement ; il n'utilise aucun ancien chemin absolu. Un port déjà occupé signifie généralement qu'une autre instance tourne encore.

## Ce que fait l'application

### Trouver une salle

1. Choisir la salle source et le modèle présent dans cette salle.
2. Indiquer combien d'ordinateurs déplacer.
3. Consulter la salle conseillée, les alternatives et leur chemin.

Une destination est proposée si elle autorise le modèle, possède assez de places pour **tout le lot** et dispose d'un chemin depuis la source. La capacité libre tient compte de tous les modèles déjà présents. La salle source n'est pas une destination.

Le classement suit la distance totale du plus court chemin. À distance égale, les noms de salles servent à stabiliser l'ordre ; aucune salle n'est considérée meilleure sur un autre critère. La liste des exclusions explique les refus : modèle non autorisé, manque de place ou absence de chemin.

Exemple : 10 Dell OptiPlex 7050 depuis MRT 1140 donnent MRT 120 à 50 m, UCU 214 à 195 m et STE 1030 à 490 m. Ces distances sont simulées. Chaque ligne est une alternative : exporter la liste ne réserve aucune place.

### Vérifier un trajet

Choisir deux salles pour obtenir le chemin et sa distance. Le calcul utilise Dijkstra avec NetworkX. Il minimise la somme des distances renseignées, et non le nombre de couloirs traversés. Les connexions sont bidirectionnelles. Une salle peut être isolée ; dans ce cas, l'application signale l'absence de trajet. Un trajet vers la même salle vaut 0 m.

### Préparer un regroupement

Choisir un modèle, une salle cible et le nombre d'ordinateurs **supplémentaires** à y rassembler. Le plan prend le stock des sources accessibles les plus proches, dans la limite de leur stock et des places libres de la cible. Il indique séparément la quantité prévue et la demande non satisfaite.

Exemple : ajouter 25 Dell OptiPlex 7050 dans UCU 214 produit un plan de 18 unités : 10 depuis MRT 1140 et 8 depuis MRT 120. La cible contient déjà 12 ordinateurs pour 30 places. Les 7 unités restantes ne peuvent pas être ajoutées.

Les plans restent indépendants. Ils ne modifient pas l'inventaire, ne réservent pas les stocks et ne doivent pas être additionnés sans revue. L'indicateur ordinateur·m est la somme quantité × distance ; il ne représente pas un temps de travail ni une tournée de chariot.

## Quand les nouvelles données seront disponibles

Dans la barre latérale, ouvrir **Importer mes CSV**, sélectionner les trois fichiers puis cliquer sur **Vérifier et utiliser ces données**. Les nouveaux bâtiments, salles et modèles apparaissent automatiquement. Il n'y a rien à changer dans le code.

L'import remplace le jeu complet, sans le mélanger à la démonstration. Si un fichier est invalide, les données actives restent intactes. Les choix de salles et modèles repartent à zéro après un import réussi. Le bouton **Revenir à la démonstration** recharge les exemples.

Les fichiers importés restent dans la mémoire de cette session locale ; ils ne sont pas copiés dans le dépôt. Conserver les originaux : une nouvelle session ou un redémarrage nécessite de les importer à nouveau. Utiliser l'application localement avec des fichiers dont l'usage est autorisé.

### Format attendu

Télécharger les exemples CSV dans la barre latérale pour avoir un modèle. Les fichiers doivent être en UTF-8. Les virgules et points-virgules sont acceptés comme séparateurs ; l'ordre des colonnes peut changer, mais leurs noms doivent correspondre exactement.

| Fichier | Colonnes | Contenu |
|---|---|---|
| `rooms.csv` | `room_id,building,capacity,allowed_models` | Identifiant unique, bâtiment, capacité entière ≥ 0 et modèles autorisés séparés par `\|` |
| `inventory.csv` | `room_id,model,quantity` | Une ligne par paire salle/modèle ; quantité entière ≥ 0 |
| `connections.csv` | `source,target,distance_m,distance_type` | Deux points reliés, distance en mètres strictement positive, type de distance |

Une salle d'inventaire doit exister et autoriser le modèle indiqué. Le total de son inventaire ne peut pas dépasser sa capacité. Les doublons, cellules vides et distances négatives ou non finies sont refusés. Au moins une salle est nécessaire ; un inventaire ou un réseau vide est accepté avec seulement ses en-têtes.

Les points de connexion qui ne sont pas des salles représentent des points de passage, par exemple un hall. L'application les affiche pour permettre une vérification : une faute de frappe dans le nom d'une salle pourrait sinon passer pour un hall. Les groupes de points sans liaison entre eux sont également signalés.

Valeurs de `distance_type` :

- `simulated` : distance inventée pour un essai.
- `estimated` : distance approximative.
- `measured` : distance déclarée mesurée dans le fichier ; l'application ne vérifie pas cette mesure.

Un trajet contenant plusieurs types est affiché comme mixte. Importer un fichier ne transforme jamais ses distances simulées en distances réelles.

Pour Excel en français, exporter en **CSV UTF-8** avec séparateur point-virgule ; les décimales avec virgule sont acceptées. Un fichier `.xlsx` ne peut pas être importé directement. Si les futures données ont un autre format, il faudra d'abord les convertir vers ces trois tableaux.

## Installation sur un autre ordinateur

Prérequis : Git et Python 3.11 ou 3.12. Le Python 3.9 fourni avec certains Mac est trop ancien. Internet est nécessaire pour installer les dépendances ; les calculs utilisent ensuite les fichiers locaux.

### Mac

```sh
cd ~/Documents
git clone --branch feat/evergreen-mvp https://github.com/mhdiagne7/Evergreen.git
cd Evergreen
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Remplacer `python3.12` par `python3.11` si nécessaire. Pour les prochains lancements, double-cliquer sur `Lancer-Evergreen.command`. Après un déplacement ou une copie vers une autre machine, recréer `.venv` si l'environnement Python ne fonctionne plus ; ce dossier n'est pas portable.

### Windows — PowerShell

```powershell
cd ([Environment]::GetFolderPath('MyDocuments'))
git clone --branch feat/evergreen-mvp https://github.com/mhdiagne7/Evergreen.git
cd Evergreen
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Avec Python 3.11, utiliser `py -3.11`. Ensuite, `Lancer-Evergreen.bat` permet de démarrer l'application par double-clic. Aucun script d'activation PowerShell n'est nécessaire.

## Organisation du code

- `app.py` : interface, saisie et affichage des résultats.
- `core/data.py` : lecture et validation des trois CSV.
- `core/graph.py` et `core/routing.py` : réseau et calcul des chemins.
- `core/optimizer.py` : classement des destinations et préparation des regroupements.
- `core/session.py` : activation d'un import complet.
- `core/export.py` : export CSV, avec protection contre les formules de tableur dans les libellés.
- `data/demo/` : exemples fictifs conservés dans Git.
- `tests/` : tests métier et tests de l'interface.

## Vérifier une modification

Sur Mac, depuis le dossier du projet :

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Sur Windows, remplacer `.venv/bin/python` par `.\.venv\Scripts\python.exe`.

La configuration `ci/github-actions-tests.yml` prépare les tests Linux, macOS et Windows, avec Python 3.11 et 3.12. Elle est inactive pour le moment : sa publication sous `.github/workflows/tests.yml` demande une permission GitHub `workflow` absente lors de la mise en place. Les vérifications locales sont faites sur Mac ; cela ne vaut pas une vérification Windows. Les versions des dépendances sont bornées, mais pas complètement verrouillées.

## Limites et données internes

Le projet ne connaît pas les escaliers, ascenseurs, accès fermés, horaires, durées de transport ou contraintes de chariot. Le regroupement vise une seule cible ; il ne calcule pas un plan global pour tout le campus et n'applique pas une politique officielle de renouvellement Evergreen.

Conserver les vrais fichiers hors du dépôt. `.gitignore` exclut les dossiers `private/`, `internal/`, `exports/`, les données hors démonstration, secrets et bases locales. Un fichier déjà suivi par Git reste suivi : vérifier les changements avant toute publication. Ne pas remplacer les exemples de `data/demo/` par un inventaire interne.

Références : [NetworkX — Dijkstra](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths/dijkstra.html), [Streamlit — import de fichiers](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader).
