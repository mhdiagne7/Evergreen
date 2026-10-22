# Retrouver l’inventaire de l’autre ordinateur

Les modifications du programme voyagent avec GitHub. La base SQLite et les CSV
internes restent sur l’ordinateur où ils ont été importés : ils sont exclus du
suivi Git depuis la version d’import réel.

## Sur le Windows/Linux où la carte était remplie

1. Ouvrir le dossier Evergreen utilisé à cette époque. Ne pas le supprimer,
   réinitialiser ni remplacer par un nouveau téléchargement.
2. Si l’application fonctionne, utiliser sa fonction de sauvegarde complète
   (ancienne interface : Stock et modèles ; nouvelle : Données et sauvegardes).
3. Sinon, arrêter l’application puis copier le dossier `private` entier. Il
   contient normalement `evergreen.sqlite3` et éventuellement
   `computers_owned.csv`. Copier aussi les deux CSV originaux du superviseur
   s’ils se trouvent ailleurs. Si EVERGREEN_DB ou EVERGREEN_INVENTORY avaient
   été configurées, utiliser les chemins correspondants.
4. Transférer ces fichiers vers le Mac par le moyen interne autorisé. Ne pas
   les déposer dans le dépôt GitHub pour contourner leur absence.

## Sur le Mac

Conserver d’abord les fichiers reçus dans un nouveau dossier local. Ne pas
écraser immédiatement `private/evergreen.sqlite3`. Une sauvegarde de la base
actuelle doit précéder toute restauration. Vérifier les espaces, quantités,
salles, modèles, lots et historique de la base reçue avant de la rendre active.

Une base complète permet de conserver les lots et leur historique. Un CSV seul
permet de reconstruire l’inventaire, pas de retrouver les interventions passées.
Les colonnes du second CSV devront être examinées avant son intégration : ne
pas supposer son format ni remplacer les informations par un catalogue public.

## Vérification du 22 octobre 2026

Les deux branches distantes accessibles, l’état précédant ec8886a (5d892ec),
l’historique accessible des CSV et les objets Git locaux non référencés ont été
inspectés. Ils ne contiennent pas les deux CSV réels recherchés. La base de ce
Mac ne contient que l’ancien espace demo, conservé mais non affiché. Le chat
« Planifier une cartographie logistique » accessible ne fournit aucune pièce
jointe CSV. Ces constats ne prouvent pas que les fichiers ont disparu de
l’ordinateur Windows/Linux ou d’une autre copie non accessible.
