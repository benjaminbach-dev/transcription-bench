"""Moteurs d'inférence : déclarations, registre et adaptateurs d'exécution.

Ce paquet vit à la racine du dépôt pour que le serveur puisse importer les
déclarations (`engines.declarations`) sans aucun paquet moteur. Les adaptateurs
d'exécution (`engines.adaptateurs.*`) vivent à part : le moteur factice et les
trois moteurs réels y sont fournis. Eux seuls font, à l'intérieur de leurs
fonctions, les imports des bibliothèques de moteur.
"""
