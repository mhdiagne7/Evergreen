# Groupes d’ordinateurs

Dans **Regroupements**, choisir **Nouveau groupe**. Le bouton **Sélectionner des bâtiments sur la carte** ouvre une grande fenêtre. Maintenir Ctrl (ou Cmd) pendant les clics pour sélectionner plusieurs bâtiments, puis cliquer sur **Confirmer les bâtiments**. Annuler conserve la sélection précédente. Effacer la sélection rétablit tous les bâtiments.

Les filtres Salle et Modèle sont facultatifs : sans sélection, tous les postes admissibles sont inclus. La liste est triée par modèle puis salle et tous les résultats sont cochés par défaut ; il reste possible d’en décocher avant de prévisualiser le groupe. Seuls les postes actifs, disponibles et installés en salle sont proposés. Les liens de renouvellement et le filtre Bâtiment ont été retirés de cette page.

Chaque groupe conserve son nom, sa description, ses membres et leurs salles d’origine. Son détail affiche les emplacements actuels, une carte filtrée et un export. Les groupes peuvent être renommés, modifiés ou supprimés. Plusieurs groupes peuvent contenir le même poste : une alerte le signale, sans réservation de stock. Un groupe lié à un déplacement actif doit être annulé avant de modifier ses membres.

## Identifiants et catégories

Le CSV contient des quantités par salle et modèle, pas des numéros de série individuels. Evergreen crée donc des identifiants locaux stables par unité. Ils ne certifient pas l’identité physique du matériel : renseigner le numéro réel dans les caractéristiques pour établir cette correspondance. Un numéro réel actif doit être unique dans le même inventaire.

Les catégories sont des entiers facultatifs de 1 à 99. Aucune signification officielle n’est présumée : l’équipe doit définir ses critères avant de les attribuer. Ni l’ancienneté, ni la performance, ni l’état ne sont inférés du modèle. Les anciennes caractéristiques restent conservées dans la base ; leur panneau de saisie est retiré de cette page simplifiée. Un poste déjà marqué hors service reste indisponible.

## Déplacements

1. Sélectionner une salle existante et prévisualiser le déplacement. Les postes déjà sur place ne sont pas déplacés. Les postes indisponibles ou retirés empêchent la préparation.
2. Confirmer l’enregistrement du lot : le groupe devient **Planifié**, sans changer les quantités.
3. Dans **Lots de déplacements**, confirmer seulement les opérations physiquement réalisées. Les quantités et les identifiants locaux changent d’emplacement dans la même transaction. Le statut devient **En cours**, puis **Terminé**.

Les capacités connues sont contrôlées. Une capacité manquante doit être vérifiée et renseignée avant une arrivée en salle ; le stock central reste à Morisset. Les arrivées en réserve depuis une salle sont du matériel retourné, distinct des ordinateurs neufs. Une modification concurrente de l’inventaire invalide les anciennes préparations : annuler puis préparer un nouveau lot.

Créer, supprimer ou planifier un groupe ne déplace aucun poste. Annuler le reste d’un lot ne défait pas les mouvements déjà confirmés. Les outils historiques de renouvellement restent accessibles dans leur section dédiée.

## Conservation et vérification

Groupes, caractéristiques et identifiants sont stockés dans la base SQLite existante, sans service externe ni nouvelle dépendance. Une sauvegarde complète SQLite conserve ces données ; un simple export du CSV agrégé ne les contient pas. Les corrections agrégées ou remises à zéro peuvent retirer des identifiants locaux : les groupes les conservent comme membres inactifs afin de signaler le changement.

Les tests utilisent des inventaires temporaires synthétiques et couvrent les filtres, limites de taille, groupes persistants, conflits, indisponibilités, confirmations partielles, mouvements de matériel retourné et conservation des identifiants. Aucun jeu fictif n’est ajouté à l’inventaire réel.

## Destinations individuelles et échanges

Après création du groupe, **Une destination par ordinateur** permet de conserver chaque poste sur place, de le déplacer, ou de choisir un poste de la destination à ramener en échange. Les salles du même bâtiment apparaissent d’abord, puis les bâtiments par proximité géographique ; cette distance est à vol d’oiseau et ne mesure pas les couloirs.

La liste récapitule les hostnames, modèles, salles de départ et destinations, avec export CSV. **Vérifier les déplacements et échanges** contrôle les capacités, les modèles autorisés, la disponibilité et les doublons. Un échange entre deux salles pleines est une opération indivisible : les deux postes sont retirés puis réinstallés. Il ne passe pas par le stock central et doit être confirmé entièrement après réalisation physique.

Un poste ne peut participer à deux opérations dans le même lot. Si deux postes du groupe s’échangent, configurer l’échange sur l’un et laisser l’autre sur sa salle actuelle dans le formulaire. Les déplacements simples sont validés dans l’ordre affiché. Préparer puis confirmer la liste pour enregistrer le lot ; ouvrir ensuite **Lots de déplacements** pour confirmer les opérations réellement effectuées. Seules les destinations individuelles sont proposées dans le détail du groupe.

## Hostnames

Les tableaux et choix d’ordinateurs affichent le **Hostname** plutôt que la clé interne Evergreen. La colonne de numéro d’inventaire réel est retirée. Un hostname non associé est affiché « Non renseigné », sans inventer de nom.

`GroupStore.import_hostnames` accepte un CSV `Hostname,Model` et rapproche les noms par salle et modèle exact. Les doublons sont refusés et les correspondances ambiguës sont signalées, sans changer les quantités ni les emplacements. Le choix optionnel de privilégier le nom sans suffixe doit être confirmé avant usage. Les hostnames sont conservés dans la base SQLite et suivent le poste lors de ses déplacements ; le code salle contenu dans le nom n’est pas réécrit. Les clés internes restent stables et invisibles dans les tableaux utilisateurs. Une sauvegarde SQLite conserve ces associations.

## Salles LEE confirmées

Les suffixes `-1` à `-4` de LEE-105, LEE-107 et LEE-109 identifient des postes supplémentaires dans la même salle. Le hostname sans suffixe est celui du poste principal. Ces entrées sont regroupées dans la salle de base à l’import ; les anciens inventaires locaux sont corrigés sans ajouter de doublons, sans changer les identifiants internes ni le total des ordinateurs. Les capacités de travail sont fondées sur les postes observés après regroupement, sans prétendre mesurer les places physiques. Les préparations antérieures deviennent périmées et doivent être recalculées. Les autres suffixes de salle ne sont pas interprétés automatiquement.

## Affichage des références de carte mère

Le CSV technique `Hostname, Model, …, Motherboard, …` est rapproché uniquement des ordinateurs actifs existants, par hostname et modèle exact. L’affichage utilise maintenant **Référence carte mère**, par exemple `0YGWFV`, à la place du hostname. Ces références sont partagées entre plusieurs ordinateurs : elles ne sont pas présentées comme des Service Tags uniques. Les clés internes et les hostnames restent conservés pour suivre et rapprocher les postes. Aucun ordinateur du fichier technique n’est ajouté automatiquement. Les codes non associés restent non renseignés.

## Service Tags réels

L’affichage des groupes, de la sélection des postes et des échanges utilise désormais le **Service Tag** réel fourni par le CSV système. Les références de carte mère ne servent plus d’identifiant affiché. Le rapprochement exige un hostname et un modèle correspondant à un poste actif déjà inventorié ; il n’ajoute aucun ordinateur. Les tags sont uniques dans chaque inventaire, et les doublons du CSV ou conflits d’affectation sont refusés dans une transaction. Les tags absents restent non renseignés. Hostnames, références de carte mère et clés internes sont conservés dans la base, sans être affichés comme Service Tags. Une sauvegarde SQLite conserve ces données.

L’onglet Assistant IA est retiré de la navigation. Dans les regroupements, chaque ordinateur a sa propre destination ; le choix d’une destination commune est retiré.

## Fenêtre interactive des swaps

Les filtres Salle et Modèle sont limités aux bâtiments sélectionnés sur la carte. Une salle sélectionnée est retirée du filtre si elle ne fait plus partie de ces bâtiments. Le nom du groupe est mis en avant en haut du formulaire et du détail. L’aperçu comporte deux indicateurs (modèles différents et ordinateurs sélectionnés) et un tableau Modèle / Nombre d’ordinateurs.

Dans le détail, **Ouvrir la fenêtre des déplacements et swaps** ouvre deux tableaux. Choisir une ligne parmi les ordinateurs du groupe, puis une ligne parmi les autres postes disponibles. Le second tableau exclut tous les membres du groupe, les postes indisponibles, ceux déjà ajoutés à la liste et ceux de la même salle que le premier poste. Il privilégie le même bâtiment puis la proximité à vol d’oiseau. Les recherches portent sur le Service Tag, la salle et le modèle.

**Swap · ajouter à la liste** valide un échange de deux postes sans le réaliser. Les postes utilisés disparaissent des listes pour éviter les doublons. Chaque échange produit deux lignes dans la liste exportable ; une action permet de le retirer. Le brouillon est conservé pendant la session et remis à zéro si le groupe ou la révision de l’inventaire change. Cocher la confirmation puis enregistrer la liste crée le lot persistant. Les quantités ne changent qu’après confirmation physique dans Lots de déplacements. Les déplacements sans échange restent accessibles dans une section de la même fenêtre lorsque la liste des swaps est vide.
