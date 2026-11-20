"""Fixture synthétique réutilisable pour les tests et le contrôle navigateur.

Aucun moteur : réutilise l'écrivain de résultats et le montage de la tâche 4.1.
Usage depuis la racine :
  .venv/bin/python -m tests.extraction_web_fixture /tmp/extraction-web-data
Affiche les chemins du détail et de la comparaison à six, sans lancer de serveur.
Le dossier doit être vide ou absent : aucun résultat existant n'est écrasé.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

from tests.test_extraction_consultation import (
    ExtractionConsultationBench,
    Source,
    VALEUR_A,
)
from transcription_bench.extraction_consultation import ExtractionConsultation

FIXTURE_SOURCE = (
    "Données entièrement synthétiques. Consultation de démonstration : "
    "la personne indique une toux depuis trois jours. Aucun médicament réel "
    "n'est prescrit. Texte de test <script>alert('source')</script>. "
    + "mot-sans-espace-" * 30
)


def build_extraction_web_fixture(data_dir: Path) -> dict[str, object]:
    """Crée six résultats simulés comparables, dont un non conforme."""
    if data_dir.exists() and any(data_dir.iterdir()):
        raise ValueError("le dossier de fixture doit être vide")
    data_dir.mkdir(parents=True, exist_ok=True)
    bench = ExtractionConsultationBench()
    bench.donnees = data_dir
    bench.compteur = 0
    run_ids = []
    for index in range(1, 7):
        value = dict(
            VALEUR_A,
            motif=None if index == 1 else "" if index == 2 else f"Toux synthétique {index}",
            symptomes=["toux", "texte de test <img src=x onerror=alert(1)>", ""],
            prescription=[
                {"medicament": "Exemple fictif A", "posologie": None},
                {"medicament": "Exemple fictif B", "posologie": "(aucune prescription réelle)"},
            ],
        )
        run_id = bench.write_run(
            [Source(texte=FIXTURE_SOURCE, valeur=value, conforme=index != 6, source_factice=True)],
            factice=True,
            version_consignes=1 if index < 4 else 2,
        )
        (bench.source_dir(run_id, 1) / "sortie_brute.txt").write_text(
            json.dumps(value, ensure_ascii=False, indent=2)
            if index != 6 else '{"case_inconnue": "sortie synthétique non conforme"}',
            encoding="utf-8",
        )
        bench.rewrite_json(
            bench.run_dir(run_id) / "run.json",
            lambda run, index=index: run["modele"].update(
                identifiant=f"synthetique/Modele-de-demonstration-{index}",
                id_resolu=f"synthetique/Modele-de-demonstration-{index}",
            ),
        )
        run_ids.append(run_id)
    service = ExtractionConsultation(data_dir)
    key = service.groups()[0].key
    selections = [f"{run_id}:1" for run_id in run_ids]
    return {
        "data_dir": str(data_dir),
        "run_ids": run_ids,
        "key": key,
        "selections": selections,
        "detail": f"/extractions/{run_ids[0]}",
        "comparison": f"/extractions/comparaison/{key}?" + urlencode(
            [("extraction", selection) for selection in selections]
        ),
    }


if __name__ == "__main__":
    print(json.dumps(build_extraction_web_fixture(Path(sys.argv[1])), ensure_ascii=False, indent=2))
