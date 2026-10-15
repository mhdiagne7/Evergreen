# Evergreen

Evergreen prépare les renouvellements d'ordinateurs **par bâtiment**, puis donne les interventions à effectuer dans chaque salle. Il conserve l'inventaire courant et le met à jour quand les déplacements sont confirmés.

Le fonctionnement repose sur deux choses distinctes :

- **Le référentiel** : bâtiments, salles, capacités et distances. Les CSV de l'université servent à le créer et ne sont jamais écrasés par les opérations.
- **L'inventaire vivant** : modèles présents dans les classes, stock en réserve, arrivages et déplacements réalisés. Il est enregistré dans une base locale avec un historique.

La démonstration est entièrement fictive. CBY y compte 25 classes à un poste, avec des modèles 7060, 7090, 7086 et 5043. MRT, UCU et STE possèdent aussi des classes et des réserves. Ces salles et distances ne représentent pas le campus réel. Ce projet n'est pas un outil officiel de l'université.

## Ouvrir l'application sur cet ordinateur

Ouvrir **Documents/Evergreen**, puis double-cliquer sur **Lancer-Evergreen.command**. Ou utiliser Terminal :

```sh
cd ~/Documents/Evergreen
.venv/bin/python -m streamlit run app.py
```

Ouvrir http://127.0.0.1:8501. Garder le Terminal ouvert et utiliser Ctrl+C pour arrêter le serveur. Les données enregistrées restent disponibles au prochain lancement.

Une erreur de chemin contenant `.codex` vient d'une ancienne instance : l'arrêter avec Ctrl+C, puis utiliser le lanceur dans Documents. Le lanceur retrouve le projet depuis son propre dossier. Si le port 8501 est occupé, vérifier si une autre instance est déjà ouverte.

## Exemple : préparer CBY

Dans **Vue par bâtiment**, consulter les quantités installées et les réserves, par bâtiment puis par modèle. Le détail d'un bâtiment montre chaque salle et son modèle actuel. Les postes en réserve sont séparés de ceux déjà utilisés dans une classe.

Dans **Planifier Evergreen** :

1. Choisir CBY.
2. Sélectionner les modèles 7060 et 7090.
3. Demander **15 classes en 7060 et 10 classes en 7090**. Ce sont des totaux souhaités après les travaux, pas des quantités à ajouter : les classes déjà conformes comptent.
4. Choisir la réserve de CBY où déposer les anciens ordinateurs.
5. Calculer les propositions et vérifier le tableau avant/après.
6. Consulter le transport entre bâtiments puis les interventions salle par salle : modèle actuel, modèle à installer et provenance.
7. Exporter la feuille de route et enregistrer le lot à réaliser.

Enregistrer un lot **ne modifie aucun stock**. Il n'effectue pas non plus de réservation. On peut préparer plusieurs scénarios, mais une mise à jour de l'inventaire rend les autres scénarios anciens : ils devront être recalculés.

### Comment sont choisies les propositions ?

Le plan conserve en priorité les classes déjà conformes aux objectifs. Il cherche ensuite le matériel en réserve, puis classe les livraisons possibles par distance du plus court chemin. Les noms servent à départager les égalités. Les modèles sont traités par ordre alphabétique : c'est une méthode simple et prévisible, pas un optimiseur global de toutes les tournées.

Par défaut, le plan ne prélève pas un ordinateur installé dans une autre classe. L'option **Autoriser les échanges avec des classes d'autres bâtiments** permet ce cas : le poste retiré de la classe cible est alors remis dans la classe source. La source doit accepter ce modèle. Même avec cette option, le matériel disponible en réserve reste prioritaire sur un poste installé plus proche.

Une intervention suit cet ordre :

1. Retirer l'ancien poste vers la réserve de retour du bâtiment cible.
2. Acheminer le nouveau poste depuis sa source vers la classe cible.
3. Dans le cas d'un échange, acheminer l'ancien poste de la réserve vers la classe source.

La réserve doit avoir une place libre pour le transit ; toutes les étapes doivent avoir un chemin et respecter les capacités. Les vieux ordinateurs ne disparaissent pas de l'inventaire. Un échange conserve aussi le poste de la classe source. Une classe initialement vide peut recevoir un poste de réserve ; le plan ne vide pas une autre classe pour la remplir.

Si le stock, les chemins ou la place de retour manquent, le plan est partiel et affiche le nombre de classes restant à équiper. Ajouter un modèle au catalogue ne crée pas de stock : les arrivages doivent être enregistrés séparément.

Le remplacement automatique vise les classes de capacité **1**. Les salles de plusieurs postes restent visibles dans le tableau de bord et dans la recherche de destinations, mais ne sont pas remplacées automatiquement.

## Mettre à jour après les travaux

Dans **Lots et historique**, ouvrir le lot puis sélectionner les salles dont l'intervention est **entièrement terminée**. Ajouter une note de réalisation, cocher la confirmation physique, puis cliquer sur **Mettre à jour l'inventaire**.

On peut confirmer une partie du lot et revenir plus tard pour le reste. Pour une salle, les étapes de retrait, livraison et éventuel retour sont indivisibles : ne pas la cocher si une étape manque. Suivre l'ordre de la feuille de route ; une opération peut réutiliser du stock provenant d'une étape précédente.

Lors de la confirmation, l'application vérifie à nouveau les quantités et les capacités. Toute la confirmation est enregistrée ensemble ; en cas d'erreur, aucun de ses mouvements n'est appliqué. Une opération déjà confirmée ne peut pas l'être une deuxième fois. Les totaux par bâtiment se mettent à jour au même moment.

Annuler le reste d'un lot ne revient pas sur ce qui a déjà été réalisé. L'historique conserve la date UTC, la note et le détail des mouvements. Les erreurs d'enregistrement nécessitent une revue ; il n'y a pas encore d'annulation automatique d'un déplacement réalisé.

## Nouveaux modèles et arrivages

Dans **Stock et modèles** :

- Ajouter un modèle au catalogue, sans changer les quantités.
- Enregistrer un arrivage dans une réserve existante, avec une quantité et une provenance.
- Confirmer la réception physique avant l'enregistrement.

L'application vérifie la capacité de la réserve et les modèles autorisés. Les classes ne sont pas utilisées comme réserve par défaut. Les sorties définitives, mises au rebut et corrections libres de stock ne sont pas encore proposées ; les retours des classes restent dans l'inventaire. Le stock en réserve est considéré réutilisable : ne pas y compter du matériel hors service sans traitement préalable.

## Importer les données de l'université

Dans la barre latérale, **Créer un inventaire depuis des CSV** crée un nouvel espace indépendant. Donner un nom et sélectionner les trois fichiers. Les autres espaces, leurs stocks et leurs historiques sont conservés. Choisir ensuite le nouvel espace dans la liste.

Importer une fois le référentiel et l'inventaire initial. Pour le travail courant, utiliser les arrivages et les confirmations de lots ; ne pas réimporter les CSV initiaux après chaque déplacement. Ils ne représentent plus l'état courant après les premières opérations.

Les fichiers doivent être en UTF-8, avec une virgule ou un point-virgule comme séparateur. Les colonnes peuvent être dans un ordre différent. Les exemples téléchargeables dans l'application sont fictifs.

| Fichier | Colonnes | Règles |
|---|---|---|
| `rooms.csv` | `room_id,building,capacity,allowed_models,room_type` | Identifiant unique ; capacité entière ≥ 0 ; usage `classroom` ou `storage` |
| `inventory.csv` | `room_id,model,quantity` | Une ligne par paire salle/modèle, quantité entière ≥ 0 |
| `connections.csv` | `source,target,distance_m,distance_type` | Connexion bidirectionnelle, distance finie strictement positive |

Dans `rooms.csv`, utiliser `capacity=1` pour une classe à un poste. Décrire aussi les vraies réserves, leur bâtiment et leur capacité. Ne pas inventer de réserve si aucune n'existe : il faut alors définir le lieu de retour réel avant de planifier.

`allowed_models` accepte une liste séparée par `|`, ou `*` pour autoriser tout modèle du catalogue. Avec une liste fermée, l'ajout d'un nouveau modèle au catalogue ne modifie pas les autorisations de la salle. La colonne `room_type` est facultative pour les anciens fichiers ; une salle sans cette colonne est considérée comme une classe, jamais comme une réserve.

Les trois types de distance sont `simulated` (inventée), `estimated` (approximative) et `measured` (déclarée mesurée dans le fichier, sans contrôle indépendant). Un chemin mélangeant plusieurs types est indiqué comme mixte. Les points présents dans les liaisons mais absents des salles sont des points de transit ; vérifier leur orthographe.

Les salles inconnues dans l'inventaire, doublons, cellules manquantes, modèles incompatibles et dépassements de capacité sont refusés. Un inventaire ou réseau vide peut contenir seulement ses en-têtes. Une salle isolée reste dans l'inventaire, mais ne peut pas participer à un déplacement sans chemin.

Les fichiers Excel `.xlsx` doivent d'abord être exportés ou convertis en ces trois CSV. Si les données réelles ont un autre schéma, une étape de correspondance des colonnes sera nécessaire. Le référentiel n'est pas modifiable dans l'interface actuelle : un référentiel révisé crée un nouvel espace à partir de l'inventaire courant exporté, avec conservation de l'ancien espace pour son historique.

## Conservation et sauvegarde

L'application enregistre les espaces, stocks, catalogues, lots et historiques dans :

```text
Documents/Evergreen/private/evergreen.sqlite3
```

Le chemin est relatif au projet. Les fichiers de démonstration ne sont jamais modifiés. SQLite est fourni avec Python ; aucun serveur de base de données supplémentaire n'est nécessaire.

Dans **Stock et modèles**, on peut exporter l'inventaire courant ou préparer puis télécharger une sauvegarde complète. Cette sauvegarde contient **tous** les espaces et leur historique au moment de sa préparation. La conserver dans un emplacement autorisé. Pour restaurer : arrêter l'application, mettre de côté la base actuelle, placer la sauvegarde dans `private/evergreen.sqlite3`, puis relancer. Exporter seulement `inventory.csv` permet de récupérer les quantités, mais pas les lots ni l'historique.

La base est locale, sans synchronisation entre ordinateurs ni gestion des comptes. Elle n'est pas chiffrée par l'application. Les protections du poste et les règles de l'université s'appliquent. `.gitignore` exclut `private/`, les exports, bases et fichiers internes ; ne jamais forcer leur ajout à Git. Les fichiers déjà suivis restent suivis : ne pas remplacer les exemples publiés par de vraies données.

## Installation sur un autre ordinateur

Prérequis : Git et Python 3.11 ou 3.12. L'installation des dépendances nécessite Internet. L'application écoute ensuite uniquement sur la machine locale et la collecte de statistiques Streamlit est désactivée.

### Mac

```sh
cd ~/Documents
git clone --branch feat/evergreen-mvp https://github.com/mhdiagne7/Evergreen.git
cd Evergreen
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Remplacer `python3.12` par `python3.11` si nécessaire. Utiliser ensuite `Lancer-Evergreen.command`. Ne pas copier l'environnement `.venv` sur une autre machine : le recréer avec ces commandes. Copier une sauvegarde séparément pour retrouver l'inventaire courant.

### Windows — PowerShell

```powershell
cd ([Environment]::GetFolderPath('MyDocuments'))
git clone --branch feat/evergreen-mvp https://github.com/mhdiagne7/Evergreen.git
cd Evergreen
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Utiliser `py -3.11` si nécessaire, puis `Lancer-Evergreen.bat` pour les lancements suivants.

## Code et vérifications

- `app.py` : tableau de bord, planification, confirmation et arrivages.
- `core/buildings.py` : objectifs par bâtiment et étapes des remplacements.
- `core/store.py` : base locale, historique et transactions.
- `core/data.py` : lecture et validation du référentiel et du stock initial.
- `core/graph.py`, `core/routing.py`, `core/optimizer.py` : chemins et recherche de salles libres.
- `room_views.py` : recherche ponctuelle de destinations, conservée dans « Salles et trajets ».
- `data/demo/campus/` : nouvelle démonstration par bâtiment ; `data/demo/` conserve aussi le petit jeu utilisé par les premiers tests de routage.
- `tests/` : tests métier, persistance et parcours de l'interface. Les bases de test sont temporaires.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Sous Windows, remplacer `.venv/bin/python` par `.\.venv\Scripts\python.exe`. Pour un environnement isolé, la variable `EVERGREEN_DB` permet de choisir une autre base.

La configuration CI `ci/github-actions-tests.yml` reste prête à activer avec la permission GitHub `workflow`. Les tests locaux sur Mac ne remplacent pas une vérification Windows. Le projet ne gère pas encore les numéros de série individuels, les chariots, les durées, l'accessibilité ou une optimisation globale de plusieurs bâtiments.

Références : [NetworkX — Dijkstra](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths/dijkstra.html), [Streamlit — import de fichiers](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader).
