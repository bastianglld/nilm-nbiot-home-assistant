"""Compile la batterie virtuelle de la carte (firmware/pilotage/batterie_virtuelle.c) et vérifie qu'elle suit
la simulation de l'EMS : charge à 2,5 kW avec 95 % de rendement, plafond à 5 kWh, réserve de 0,5 kWh,
décharge limitée à la consommation de la maison, jauge de 5 LED."""
import ctypes
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1] / "firmware" / "pilotage"
REPOS, CHARGE, DECHARGE = 0, 1, 2


class Batterie(ctypes.Structure):
    _fields_ = [("stock_kwh", ctypes.c_float), ("capacite_kwh", ctypes.c_float), ("puissance_kw", ctypes.c_float),
                ("rendement", ctypes.c_float), ("reserve_kwh", ctypes.c_float)]


@unittest.skipUnless(shutil.which("gcc"), "gcc absent")
class BatterieVirtuelle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = Path(cls.tmp.name) / "libbv.so"
        subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        str(DOSSIER / "batterie_virtuelle.c"), "-o", str(lib)], check=True)
        cls.c = ctypes.CDLL(str(lib))
        cls.c.bv_minute.restype = ctypes.c_float
        cls.c.bv_minute.argtypes = [ctypes.POINTER(Batterie), ctypes.c_uint8, ctypes.c_float]
        cls.c.bv_pourcent.argtypes = [ctypes.POINTER(Batterie)]
        cls.c.bv_niveau.argtypes = [ctypes.POINTER(Batterie), ctypes.c_int]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def nouvelle(self):
        b = Batterie()
        self.c.bv_init(ctypes.byref(b))
        return b

    def test_depart_a_moitie(self):
        b = self.nouvelle()
        self.assertAlmostEqual(b.stock_kwh, 2.5, places=4)
        self.assertEqual(self.c.bv_pourcent(ctypes.byref(b)), 50)
        self.assertEqual(self.c.bv_niveau(ctypes.byref(b), 5), 3)   # 2,5 LED arrondies à 3

    def test_repos_ne_change_rien(self):
        b = self.nouvelle()
        for _ in range(120):
            self.assertEqual(self.c.bv_minute(ctypes.byref(b), REPOS, 1000.0), 0.0)
        self.assertAlmostEqual(b.stock_kwh, 2.5, places=4)

    def test_charge_une_heure(self):
        b = self.nouvelle()
        achat = sum(self.c.bv_minute(ctypes.byref(b), CHARGE, 0.0) for _ in range(60))
        self.assertAlmostEqual(achat, 2500.0, delta=1.0)                  # 2,5 kWh achetés
        self.assertAlmostEqual(b.stock_kwh, 2.5 + 0.95 * 2.5, delta=1e-3)  # 2,375 kWh stockés

    def test_charge_plafonnee(self):
        b = self.nouvelle()
        for _ in range(300):
            self.c.bv_minute(ctypes.byref(b), CHARGE, 0.0)
        self.assertAlmostEqual(b.stock_kwh, 5.0, delta=1e-3)
        self.assertEqual(self.c.bv_pourcent(ctypes.byref(b)), 100)
        self.assertEqual(self.c.bv_niveau(ctypes.byref(b), 5), 5)
        self.assertAlmostEqual(self.c.bv_minute(ctypes.byref(b), CHARGE, 0.0), 0.0, delta=1e-3)

    def test_decharge_limitee_a_la_conso(self):
        b = self.nouvelle()
        rendu = -self.c.bv_minute(ctypes.byref(b), DECHARGE, 600.0)        # maison à 600 W : 10 Wh sur la minute
        self.assertAlmostEqual(rendu, 10.0, delta=0.01)
        self.assertAlmostEqual(b.stock_kwh, 2.5 - 0.010 / 0.95, delta=1e-5)
        rendu = -self.c.bv_minute(ctypes.byref(b), DECHARGE, 6000.0)       # 6 kW : plafonné à 2,5 kW
        self.assertAlmostEqual(rendu, 2500.0 / 60.0, delta=0.01)

    def test_decharge_garde_la_reserve(self):
        b = self.nouvelle()
        for _ in range(600):
            self.c.bv_minute(ctypes.byref(b), DECHARGE, 3000.0)
        self.assertAlmostEqual(b.stock_kwh, 0.5, delta=1e-3)
        self.assertEqual(self.c.bv_pourcent(ctypes.byref(b)), 10)
        self.assertEqual(self.c.bv_niveau(ctypes.byref(b), 5), 1)          # une LED : presque vide
        self.assertAlmostEqual(self.c.bv_minute(ctypes.byref(b), DECHARGE, 3000.0), 0.0, delta=1e-3)

    def test_jauge(self):
        b = self.nouvelle()
        for stock, attendu in [(0.0, 0), (0.4, 0), (0.6, 1), (1.4, 1), (1.6, 2), (2.6, 3), (3.6, 4), (4.6, 5)]:
            b.stock_kwh = stock
            self.assertEqual(self.c.bv_niveau(ctypes.byref(b), 5), attendu, stock)


if __name__ == "__main__":
    unittest.main()
