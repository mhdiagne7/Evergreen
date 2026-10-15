# Demande de réalisation

Faire évoluer la branche `feat/evergreen-mvp` de `mhdiagne7/Evergreen` en
conservant l'identité visuelle et les cinq onglets existants.

## Exigences

- Réorganiser le code en modules lisibles, avec indentation cohérente,
  retours à la ligne, noms explicites et commentaires utiles.
- Importer le CSV réel d'ordinateurs fourni : `room_id,model,quantity`.
  Préserver toutes les quantités et les salles contenant plusieurs modèles.
- Retirer les données fictives de l'application et du dépôt. Les données
  synthétiques nécessaires aux tests doivent rester limitées au code des tests.
- Utiliser un stock central à MRT, sans inventer de réserves par bâtiment.
  Permettre d'ajouter de nouveaux modèles et leurs quantités reçues, sans
  demander de provenance. Conserver les confirmations et l'historique.
- Utiliser la géographie publique de la carte officielle du campus pour
  afficher les bâtiments recensés, leurs informations au survol et des couleurs
  par modèle. Associer `LEE` à la Faculté des sciences de la santé, selon la
  précision donnée pendant la réalisation.
- Calculer les distances géographiques en indiquant clairement leur nature.
  Ne pas présenter une distance à vol d'oiseau comme un parcours piéton ni
  inventer de distance intérieure ou de capacité physique.
- Préparer les remplacements et les retours à MRT, vérifier les quantités,
  conserver les inventaires et bloquer les confirmations périmées.
- Tester les fonctions et les parcours de l'interface, vérifier le rendu de
  la carte et relancer la copie située dans Documents.
- Effectuer un commit puis un push sur `feat/evergreen-mvp`. Garder les données
  internes, la base et les sauvegardes hors du commit.

Source géographique :
https://www.uottawa.ca/about-us/administration-services/facilities/campus-maps
