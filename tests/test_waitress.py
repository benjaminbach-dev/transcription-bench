"""Sonde HTTP locale du tampon Waitress, limitée au contrôle du serveur.

La sonde démarre le serveur réel par l'API publique `waitress.serve` sur un port
éphémère, avec une application factice instrumentée : une requête annonçant un
corps de plus de 1 Mio (ou égal à la limite) doit être rejetée en 413 par
Waitress sans appel de l'application, sur son seul en-tête `Content-Length`, sans
envoyer le corps. Elle ne remplace pas la sonde 1.7 sur les PC de test et ne met
en jeu ni moteur, ni poids, ni réseau externe.
"""

from __future__ import annotations

import http.client
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TAILLE_MAX_CORPS_SERVEUR = 1024 * 1024
DELAI_DEMARRAGE = 10.0
DELAI_REPONSE = 10.0

CODE_SERVEUR = f"""
import sys
from pathlib import Path

from waitress import serve

marqueur = Path(sys.argv[1])
port = int(sys.argv[2])


def application(environ, start_response):
    marqueur.write_text("application appelée", encoding="utf-8")
    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"ok"]


serve(
    application,
    host="127.0.0.1",
    port=port,
    threads=1,
    max_request_body_size={TAILLE_MAX_CORPS_SERVEUR},
)
"""


def port_libre() -> int:
    """Réserve brièvement un port local éphémère, puis le libère."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.bind(("127.0.0.1", 0))
        return prise.getsockname()[1]


class SondeWaitressTest(unittest.TestCase):
    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.marqueur = Path(temporaire.name) / "marqueur"
        self.port = port_libre()
        self.processus = subprocess.Popen(
            [sys.executable, "-c", CODE_SERVEUR, str(self.marqueur), str(self.port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.arreter_processus)
        self.attendre_serveur()

    def arreter_processus(self) -> None:
        if self.processus.poll() is not None:
            return
        self.processus.terminate()
        try:
            self.processus.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.processus.kill()
            self.processus.wait(timeout=5)

    def attendre_serveur(self) -> None:
        echeance = time.monotonic() + DELAI_DEMARRAGE
        while time.monotonic() < echeance:
            if self.processus.poll() is not None:
                self.fail(f"serveur arrêté prématurément (code {self.processus.returncode})")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                    return
            except OSError:
                time.sleep(0.05)
        self.fail("serveur Waitress indisponible dans le délai imparti")

    def poster(self, corps: bytes, chemin: str = "/"):
        connexion = http.client.HTTPConnection("127.0.0.1", self.port, timeout=DELAI_REPONSE)
        self.addCleanup(connexion.close)
        connexion.request(
            "POST",
            chemin,
            body=corps,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(corps)),
            },
        )
        return connexion.getresponse()

    def poster_entetes_seuls(self, longueur: int, chemin: str = "/gros"):
        """Annonce un corps de `longueur` octets sans envoyer ce corps."""
        connexion = http.client.HTTPConnection("127.0.0.1", self.port, timeout=DELAI_REPONSE)
        self.addCleanup(connexion.close)
        connexion.putrequest("POST", chemin)
        connexion.putheader("Content-Type", "application/x-www-form-urlencoded")
        connexion.putheader("Content-Length", str(longueur))
        connexion.endheaders()
        return connexion.getresponse()

    def test_entete_annoncant_plus_d_un_mio_rejete_sans_appel(self) -> None:
        reponse = self.poster_entetes_seuls(TAILLE_MAX_CORPS_SERVEUR + 1)

        self.assertEqual(reponse.status, 413)
        reponse.read()
        self.assertIsNone(self.processus.poll())
        self.assertFalse(
            self.marqueur.exists(),
            "l'application a été appelée malgré le rejet du corps par Waitress",
        )

    def test_limite_exacte_rejetee_par_waitress(self) -> None:
        """Waitress rejette dès `Content-Length >= 1 Mio` ; l'égalité n'est pas acceptée."""
        reponse = self.poster_entetes_seuls(TAILLE_MAX_CORPS_SERVEUR)

        self.assertEqual(reponse.status, 413)
        reponse.read()
        self.assertFalse(self.marqueur.exists())

    def test_corps_modeste_atteint_l_application(self) -> None:
        reponse = self.poster(b"champ=1", "/petit")

        self.assertEqual(reponse.status, 200)
        self.assertEqual(reponse.read(), b"ok")
        self.assertTrue(self.marqueur.exists())
        self.assertEqual(self.marqueur.read_text(encoding="utf-8"), "application appelée")


if __name__ == "__main__":
    unittest.main()
