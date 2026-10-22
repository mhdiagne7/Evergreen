# Prompt de référence — Dashboard Evergreen

Améliore l’application locale Evergreen dans le dépôt existant, en conservant
les données et les fonctions déjà validées. Le projet est actuellement dans
`/Users/habiballah/Documents/Evergreen` ; il doit rester portable Mac/Windows.

## Besoin métier

Le superviseur doit savoir quels ordinateurs sont installés dans chaque salle
et bâtiment, quels modèles sont disponibles à Morisset et quels lots restent
à réaliser. L’objectif Evergreen comprend le regroupement de modèles par
bâtiment ou par bloc proche, puis leur remplacement au moment prévu.

Un modèle majoritaire peut devenir une cible de regroupement. Les modèles
anciens peuvent aussi être regroupés volontairement pour préparer une future
campagne. Ne pas déduire leur ancienneté de leur numéro commercial. Distinguer
regroupement et amélioration de génération. Ne pas laisser une salle sans poste
pour améliorer artificiellement le regroupement d’un autre bâtiment.

## Expérience attendue

Créer un dashboard sobre, accueillant et accessible, avec une couleur d’accent,
des titres courts et une page par tâche. Prévoir les parcours Accueil →
Bâtiments → Détail, Regroupements → Modèle dominant ou Blocs proches ou
Renouvellement, et Lots → Détail du lot. Permettre un retour au niveau parent et
un accès permanent au menu. Montrer le contexte, les quantités avant/après, les
manques, les salles concernées et les étapes de transport.

## Données et décisions

Conserver le référentiel de salles séparé de l’inventaire vivant. Un import doit
être validé et créer un espace indépendant sans écraser le travail courant.
Recevoir un ou plusieurs modèles à Morisset, séparer stock neuf et retours,
persister les modifications et conserver l’historique. Ajouter un modèle au
catalogue ne doit pas créer de quantité. Fournir export et sauvegarde complète.

Une proposition n’est pas une réalisation. Enregistrer un lot sans changer les
stocks, puis confirmer uniquement les opérations physiquement réalisées.
Vérifier les capacités, la conservation des quantités, les dépendances et les
versions d’inventaire ; bloquer les confirmations doubles ou périmées.

Privilégier des propositions explicables à partir des modèles présents, des
quantités et des distances. Distinguer marche renseignée, vol d’oiseau,
estimation et simulation ; ne pas inventer des plans intérieurs ou des stocks.
Utiliser un moteur déterministe pour les calculs. Une éventuelle IA
conversationnelle doit appeler ce moteur, expliquer ses limites et proposer
sans écrire directement dans l’inventaire. Définir explicitement son accès aux
données avant de connecter un service externe.

## Livraison

Inspecter le dépôt et ses mises à jour avant de modifier. Préserver les fonctions
récentes, garder le code modulaire et compréhensible, tester les vrais parcours
métier avec des données synthétiques isolées, vérifier visuellement l’interface
et actualiser le README. Ne publier aucune donnée interne. Utiliser l’identité
Git de l’utilisateur, vérifier les commits avant de pousser et rendre compte
honnêtement de ce qui fonctionne et de ce qui reste à faire.
