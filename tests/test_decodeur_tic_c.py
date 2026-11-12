"""Compile le décodeur TIC en C (firmware/tic) et le vérifie sur des trames produites par le simulateur."""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1] / "firmware" / "tic"
SIMU = DOSSIER / "simulateur_tic.py"


@unittest.skipUnless(shutil.which("gcc"), "gcc absent")
class DecodeurC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.exe = cls.tmp / "test_pc"
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-std=c11", "-o", str(cls.exe),
                        str(DOSSIER / "test_pc.c"), str(DOSSIER / "tic_decodeur.c")], check=True)

    def decoder(self, *options):
        f = self.tmp / "trames.bin"
        subprocess.run([sys.executable, str(SIMU), "envoyer", "--sortie", str(f), *options],
                       check=True, capture_output=True)
        return subprocess.run([str(self.exe), str(f)], check=True, capture_output=True, text=True).stdout

    def bilan(self, sortie):
        m = re.search(r"trames valides (\d+) \| avec ligne rejetée (\d+) \| interrompues (\d+)", sortie)
        return tuple(int(x) for x in m.groups())

    def test_standard_tempo(self):
        out = self.decoder("--nb", "5", "--offre", "tempo", "--couleur", "ROUGE", "--demain", "BLANC",
                           "--puissance", "1234", "--debut", "2025-01-21T18:30:00")
        self.assertEqual(self.bilan(out), (5, 0, 0))
        self.assertIn("S= 1234 VA", out)
        self.assertIn("jour=ROUGE demain=BLANC", out)
        self.assertIn("tarif=HP ROUGE", out)

    def test_historique_8n1(self):
        out = self.decoder("--nb", "3", "--mode", "historique", "--offre", "hphc", "--puissance", "800",
                           "--8n1", "--debut", "2025-01-21T23:10:00")
        self.assertEqual(self.bilan(out), (3, 0, 0))
        self.assertIn("hist S=  800 VA", out)
        self.assertIn("tarif=HC..", out)

    def test_erreurs_toutes_detectees(self):
        f = self.tmp / "erreurs.bin"
        sim = subprocess.run([sys.executable, str(SIMU), "envoyer", "--sortie", str(f), "--nb", "60", "--erreurs", "30",
                              "--graine", "7", "--puissance", "500", "--afficher"],
                             check=True, capture_output=True, text=True).stderr
        abimees = len(re.findall(r"fausse|modifié|interrompue|manquant", sim))
        out = subprocess.run([str(self.exe), str(f)], check=True, capture_output=True, text=True).stdout
        ok, erreur, interrompues = self.bilan(out)
        self.assertGreater(abimees, 5)
        self.assertEqual(ok, 60 - abimees)                  # aucune trame abîmée n'est acceptée
        # une trame sans ETX n'est comptée qu'à l'arrivée de la suivante : la dernière peut rester en attente
        self.assertIn(erreur + interrompues, (abimees - 1, abimees))

if __name__ == "__main__":
    unittest.main()
