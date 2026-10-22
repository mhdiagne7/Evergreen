# Groupes d’ordinateurs

Dans **Regroupements**, choisir **Créer un groupe**, puis le mode manuel ou automatique. Les filtres combinent catégorie, bâtiment, étage, salle, modèle, état et priorité. La carte permet de sélectionner un bâtiment avant de cocher ses postes. Une prévisualisation précède l’enregistrement.

Le mode automatique partitionne les résultats selon les critères choisis et la taille maximale. Une heuristique privilégie la même salle, puis un étage renseigné du même bâtiment, puis le même bâtiment et la proximité géographique. Elle ne garantit pas un optimum ni une distance de marche mesurée. Les étages inconnus ne sont pas déduits des numéros de salle.

Chaque groupe conserve son nom, sa description, ses membres et leurs salles d’origine. Son détail affiche les emplacements actuels, une carte filtrée et un export. Les groupes peuvent être renommés, modifiés ou supprimés. Plusieurs groupes peuvent contenir le même poste : une alerte le signale, sans réservation de stock. Un groupe lié à un déplacement actif doit être annulé avant de modifier ses membres.

## Identifiants et catégories

Le CSV contient des quantités par salle et modèle, pas des numéros de série individuels. Evergreen crée donc des identifiants locaux stables par unité. Ils ne certifient pas l’identité physique du matériel : renseigner le numéro réel dans les caractéristiques pour établir cette correspondance. Un numéro réel actif doit être unique dans le même inventaire.

Les catégories sont des entiers facultatifs de 1 à 99. Aucune signification officielle n’est présumée : l’équipe doit définir ses critères avant de les attribuer. Ni l’ancienneté, ni la performance, ni l’état ne sont inférés du modèle. Étage, catégorie, numéro réel, état et priorité se renseignent dans les caractéristiques. Un poste hors service devient indisponible.

## Déplacements

1. Sélectionner une salle existante et prévisualiser le déplacement. Les postes déjà sur place ne sont pas déplacés. Les postes indisponibles ou retirés empêchent la préparation.
2. Confirmer l’enregistrement du lot : le groupe devient **Planifié**, sans changer les quantités.
3. Dans **Lots de déplacements**, confirmer seulement les opérations physiquement réalisées. Les quantités et les identifiants locaux changent d’emplacement dans la même transaction. Le statut devient **En cours**, puis **Terminé**.

Les capacités connues sont contrôlées. Une capacité manquante doit être vérifiée et renseignée avant une arrivée en salle ; le stock central reste à Morisset. Les arrivées en réserve depuis une salle sont du matériel retourné, distinct des ordinateurs neufs. Une modification concurrente de l’inventaire invalide les anciennes préparations : annuler puis préparer un nouveau lot.

Créer, supprimer ou planifier un groupe ne déplace aucun poste. Annuler le reste d’un lot ne défait pas les mouvements déjà confirmés. Les outils historiques de renouvellement restent accessibles dans leur section dédiée.

## Conservation et vérification

Groupes, caractéristiques et identifiants sont stockés dans la base SQLite existante, sans service externe ni nouvelle dépendance. Une sauvegarde complète SQLite conserve ces données ; un simple export du CSV agrégé ne les contient pas. Les corrections agrégées ou remises à zéro peuvent retirer des identifiants locaux : les groupes les conservent comme membres inactifs afin de signaler le changement.

Les tests utilisent des inventaires temporaires synthétiques et couvrent les filtres, limites de taille, groupes persistants, conflits, indisponibilités, confirmations partielles, mouvements de matériel retourné et conservation des identifiants. Aucun jeu fictif n’est ajouté à l’inventaire réel.
