"""Compile la mesure tension/courant en C (firmware/mesure_vi) et la vérifie sur des sinusoïdes synthétiques."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1] / "firmware" / "mesure_vi"


@unittest.skipUnless(shutil.which("gcc"), "gcc absent")
class MesureVI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(tempfile.mkdtemp()) / "test_pc"
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-std=c11", "-o", str(cls.exe),
                        str(DOSSIER / "test_pc.c"), str(DOSSIER / "mesure_vi.c"), "-lm"], check=True)

    def mesurer(self, *args):
        out = subprocess.run([str(self.exe), *map(str, args)], check=True, capture_output=True, text=True).stdout
        res = {}
        for nom in ("Vrms", "Irms", "P", "S", "fp"):
            m = re.search(rf"^{nom}\s+(-?[\d.]+) \(théorie (-?[\d.]+)\)", out, re.M)
            res[nom] = (float(m.group(1)), float(m.group(2)))
        res["minutes"] = int(re.search(r"minutes (\d+)", out).group(1))
        return res

    def verifier(self, res, tol=0.002):
        for nom in ("Vrms", "Irms", "P", "S"):
            mesure, theorie = res[nom]
            self.assertAlmostEqual(mesure / theorie, 1.0, delta=tol, msg=nom)
        self.assertAlmostEqual(res["fp"][0], res["fp"][1], delta=0.002)

    def test_en_phase(self):
        res = self.mesurer(1500, 1000, 0, 0)
        self.verifier(res)
        self.assertEqual(res["minutes"], 1)

    def test_dephasage_et_harmonique(self):
        self.verifier(self.mesurer(1500, 800, 60, 0.3))

    def test_petit_courant(self):
        # quelques dizaines de points ADC (petite charge) : erreur de quantification plus grande
        self.verifier(self.mesurer(1500, 40, 30, 0), tol=0.02)


if __name__ == "__main__":
    unittest.main()
