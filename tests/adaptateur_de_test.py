"""Adaptateur de test contrôlé : import de moteur volontairement différé.

Ce module n'est pas un adaptateur réel. Il sert seulement à vérifier que le
registre importe l'adaptateur à la demande et que l'import d'une bibliothèque de
moteur reste à l'intérieur d'une fonction. Le faux paquet `moteur_factice_stub`
est créé dans un dossier temporaire par `tests/test_engines.py`.
"""


def creer_moteur():
    import moteur_factice_stub

    return moteur_factice_stub
