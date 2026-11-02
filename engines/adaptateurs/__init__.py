"""Adaptateurs d'exécution des moteurs, chargés uniquement par le runner.

Chaque adaptateur est le seul module qui importe les paquets de son moteur, et
il le fait à l'intérieur de ses fonctions : importer un adaptateur ne charge
aucune bibliothèque de moteur. Les trois moteurs réels (faster-whisper,
transcribe.cpp, Transformers) et le moteur factice sont fournis ; les
adaptateurs réels ne valent que pour les familles qualifiées sur le PC Linux de
test, la vérification Windows restant due à la CI (tâches 10.5 et 10.6).
"""
