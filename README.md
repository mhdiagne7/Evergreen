# Evergreen

Application locale en français pour suivre les ordinateurs par bâtiment,
préparer les renouvellements et enregistrer les déplacements réalisés.
L'interface Streamlit conserve ses cinq onglets. Le **stock central est à MRT** :
aucune réserve n'est créée dans les autres bâtiments.

## Lancer l'application

Dans le dossier du projet, avec Python 3.11 ou plus récent :

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Sur Windows, utiliser `py -3.12 -m venv .venv`, puis
`.venv\Scripts\python.exe` à la place de `.venv/bin/python`.
Les lanceurs `Lancer-Evergreen.command`, `Lancer-Evergreen.sh` et
`Lancer-Evergreen.bat` utilisent le dossier dans lequel ils se trouvent.

Ouvrir http://127.0.0.1:8501 et garder le terminal ouvert. Ctrl+C arrête le
serveur. Si un autre serveur utilise ce port, ajouter `--server.port 8502`.

## Importer l'inventaire réel

L'application démarre sans démonstration ni quantités fictives. Dans la barre
latérale, sélectionner **Importer un inventaire**, donner un nom et fournir un
CSV UTF-8 (virgule ou point-virgule) contenant :

```text
room_id,model,quantity
```

Chaque identifiant doit suivre `BATIMENT-SALLE`. Les quantités sont des entiers
strictement positifs. Les quantités des paires salle/modèle répétées sont additionnées avec un
avertissement : sans numéro de série, il faut vérifier si ces lignes décrivent
des postes distincts ou un doublon d’export. Plusieurs modèles dans une même
salle sont conservés. Le code du bâtiment est la partie
avant le premier tiret. Les salles absentes du fichier ne sont pas inventées.

Le nombre de postes recensés dans chaque salle devient sa **capacité de travail
à l'import**, pas une capacité immobilière vérifiée. Tous les modèles sont
autorisés par défaut pour ce format : cela ne valide pas leur compatibilité
technique. Le remplacement automatique concerne les salles recensées à un poste.
Les salles à plusieurs postes restent visibles et leur inventaire est conservé.

`MRT-STOCK` est un emplacement logique pour le stock central, sans numéro de salle
physique supposé. Il démarre vide : le CSV d'ordinateurs installés ne permet pas
de déduire le matériel disponible en stock. Sa capacité physique est inconnue ;
aucune limite n'est configurée par défaut. Une limite peut être définie dans
**Stock et modèles**, puis sera appliquée aux arrivages et aux retours.

Pour initialiser cet ordinateur une seule fois sans passer par l'import manuel,
placer une copie du CSV dans `private/computers_owned.csv`. Son empreinte évite de
réimporter le même fichier à chaque démarrage. Changer ce fichier crée un nouvel
espace indépendant ; cela ne remplace jamais l'inventaire vivant. La variable
`EVERGREEN_INVENTORY` permet de choisir un autre chemin. `EVERGREEN_DB` choisit la
base ; quand elle est définie, l'import automatique ne s'effectue que si
`EVERGREEN_INVENTORY` l'est aussi.

Le format avancé à trois fichiers reste disponible :

| Fichier | Colonnes |
| --- | --- |
| `rooms.csv` | `room_id,building,capacity,allowed_models,room_type` |
| `inventory.csv` | `room_id,model,quantity` |
| `connections.csv` | `source,target,distance_m,distance_type` |

`room_type` vaut `classroom` ou `storage` (facultatif, défaut `classroom`).
`allowed_models` vaut `*` ou une liste séparée par `|`. Les liaisons sont
bidirectionnelles et strictement positives. `distance_type` vaut `estimated`,
`measured` ou, pour les anciennes bases uniquement, `simulated`. Les chemins
explicites utilisent Dijkstra. Ce format permet d'apporter ultérieurement des
capacités et trajets validés ; il ne crée pas automatiquement de stock MRT.

## Carte interactive et distances

Les contours et coordonnées proviennent des données publiques intégrées à la
[carte officielle de l'Université d'Ottawa](https://www.uottawa.ca/about-us/administration-services/facilities/campus-maps),
extraites le 15 octobre 2026. `data/public/buildings.geojson` contient uniquement
la géographie publique et ses références ; aucun inventaire interne.

Seuls les bâtiments présents dans l'espace courant sont affichés. Survoler un
contour affiche le nombre de salles, les quantités par modèle et le stock.
Cliquer sélectionne son détail. La couleur indique le modèle dominant ; un filtre
permet de repérer les bâtiments possédant un modèle particulier. La légende,
les tableaux et les libellés complètent les couleurs. Le cadrage permet de voir
le campus principal, Lees, Roger-Guindon ou l'ensemble des bâtiments.

Le code `LEE` est associé à **LEES-FHS, Faculté des sciences de la santé**, selon
la confirmation de l'utilisateur. Un code absent du référentiel public est
signalé ; aucune coordonnée n'est inventée et les trajets entre bâtiments
inconnus ne sont pas proposés.

Le calcul géographique utilise Haversine entre les points des bâtiments. Il
donne une **distance à vol d'oiseau**, sans mesurer un trajet piéton, une entrée,
un escalier, une passerelle ou une durée de transport. Une liaison peut être
affichée sur la carte pour comparer deux bâtiments. Dans un même bâtiment, la
distance intérieure reste **non évaluée**, avec une cellule vide, jamais un zéro
présenté comme une distance mesurée. Un trajet vers le même emplacement vaut 0.

Les calculs et tableaux fonctionnent localement. Le fond de carte CARTO /
OpenStreetMap nécessite Internet et WebGL ; seules ses tuiles publiques sont
chargées depuis le fournisseur. Les contours et informations d'inventaire sont
préparés par le serveur local pour le navigateur, sans API externe d'inventaire.
L'application n'est pas un outil officiel de l'université.

## Stock et nouveaux modèles

Dans **Stock et modèles** :

1. Ajouter le nom du nouveau modèle au catalogue.
2. Choisir ce modèle et saisir la quantité réellement reçue à MRT.
3. Confirmer la réception physique, puis enregistrer l'arrivage.

Aucune provenance n'est demandée. Ajouter seulement un modèle ne crée aucune
quantité. Les arrivages et les changements de capacité sont enregistrés avec
historique et contrôle de version pour éviter l'utilisation d'un état périmé.

## Préparer et réaliser Evergreen

Choisir le bâtiment, les modèles et le nombre total de salles souhaité par
modèle après les travaux. Les salles déjà conformes comptent. Les anciens postes
reviennent au stock central de MRT. Les réserves sont utilisées en priorité ;
les échanges avec des classes d'autres bâtiments sont facultatifs et conservent
un poste dans la salle source.

Chaque proposition vérifie le stock, les modèles autorisés, les capacités et
l'existence d'une liaison. Le classement compare la **somme des distances de
retrait, livraison et retour**, avec priorité au stock. Les trajets intérieurs
inconnus ne contribuent pas à ce classement géographique. Les modèles sont
traités par nom ; c'est une heuristique déterministe à bâtiment cible unique,
sans garantie d'optimum global ni de tournée piétonne minimale.

L'ordre proposé est : retirer l'ancien poste vers MRT, livrer le nouveau poste,
puis effectuer l'éventuel retour d'échange. Une limite de capacité configurée
doit donc permettre le transit avant la livraison. Si les contraintes empêchent
de satisfaire l'objectif, le manque apparaît dans la synthèse.

Enregistrer le lot ne réserve ni ne déplace le stock. Dans **Lots et historique**,
sélectionner les interventions entièrement terminées, ajouter une note de
réalisation et confirmer leur exécution physique. Chaque confirmation est une
transaction : tout est appliqué ensemble ou rien. Une confirmation partielle est
possible dans l'ordre de la feuille de route. Un lot périmé doit être recalculé.
Une intervention déjà confirmée ne peut pas l'être à nouveau.

## Données locales et sauvegarde

La base se trouve dans `private/evergreen.sqlite3`. Les fichiers internes,
inventaires, sauvegardes et exports sont ignorés par Git. Les CSV fictifs et les
téléchargements de démonstration ont été retirés. Un ancien espace nommé `demo`
reste conservé dans une ancienne base pour ne pas effacer son historique, mais
n'est plus proposé dans l'interface. Aucune migration n'écrase les autres espaces.

Exporter l'inventaire courant ou préparer une sauvegarde complète dans
**Stock et modèles**. La sauvegarde conserve tous les espaces et leurs historiques.
Pour restaurer, arrêter le serveur, mettre de côté la base actuelle, remplacer
la base par la sauvegarde, puis relancer. Le CSV courant seul ne conserve ni les
lots ni l'historique. La base n'est pas synchronisée entre ordinateurs.

## Organisation et vérifications

```text
app.py                  Navigation et initialisation
ui/                     Vues : import, tableau de bord, lots, stock, planification
map_view.py             Carte, filtres, survol et sélection des bâtiments
room_views.py           Recherche de destinations et trajets
core/data.py            Référentiel et validation du format avancé
core/owned_import.py    Import direct des ordinateurs recensés
core/campus.py          Coordonnées publiques et calcul Haversine
core/buildings.py       Simulation des remplacements par bâtiment
core/store.py           Transactions SQLite, lots et historique
core/routing.py         Routes géographiques ou Dijkstra sur réseau fourni
data/public/            Géographie publique uniquement
tests/                  Tests avec petites données synthétiques en Python
```

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest -q
```

Les tests utilisent des bases temporaires. Ils ne modifient pas l'inventaire
réel et ne publient pas le CSV interne. Les scénarios vérifient les imports,
salles mixtes, capacités, arrivages, conservation des quantités, confirmations
partielles, données géographiques, carte et interactions Streamlit.
La configuration `ci/github-actions-tests.yml` reste un modèle à activer avec
les droits GitHub appropriés ; une exécution locale ne prouve pas son exécution
sur les autres plateformes.
