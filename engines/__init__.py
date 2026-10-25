"""Moteurs d'inférence : déclarations, registre et adaptateurs d'exécution.

Ce paquet vit à la racine du dépôt pour que le serveur puisse importer les
déclarations (`engines.declarations`) sans aucun paquet moteur. Les adaptateurs
d'exécution (`engines.adaptateurs.*`) seront ajoutés par les tâches 4.3 et 8.x :
eux seuls font, à l'intérieur de leurs fonctions, les imports des bibliothèques
de moteur.
"""
