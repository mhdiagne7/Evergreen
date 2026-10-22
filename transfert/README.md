# Récupérer Evergreen avec ses données

Cette archive est publiée dans le dépôt public à la demande explicite de son propriétaire. Elle contient les CSV, le fichier système de référence et une copie cohérente de la base locale.

[Télécharger la sauvegarde complète](evergreen-donnees-20261022T113917Z.zip)

## Sur un autre ordinateur

1. Récupérer la branche `feat/evergreen-mvp` du dépôt `mhdiagne7/Evergreen`.
2. Extraire l’archive ci-dessus dans un dossier temporaire. Elle contient un dossier `private`.
3. Arrêter Evergreen. Si un dossier `private` existe déjà dans le projet, le sauvegarder et le mettre de côté avant restauration.
4. Copier le dossier `private` extrait dans le dossier Evergreen, au même niveau que `app.py`.
5. Installer les dépendances selon le README principal, puis lancer Evergreen avec le lanceur adapté au système.

La base conserve l’inventaire corrigé (UCU-AUD inclus, FTX-147 à un seul poste), les réglages, la confirmation du format Micro des 3060, les lots et les historiques. Les CSV originaux et le fichier système sont dans `private/sources` ; ce dernier est une référence et ne crée aucun ordinateur en stock.

La sauvegarde est un instantané, pas une synchronisation automatique. Les changements de stock effectués simultanément sur différents ordinateurs ne se fusionnent pas. Choisir la sauvegarde à restaurer et conserver la base précédente.

Les mots de passe, clés API, environnements Python, Ollama et modèles IA ne sont pas inclus. Ollama doit être installé séparément pour l’assistant IA local.
