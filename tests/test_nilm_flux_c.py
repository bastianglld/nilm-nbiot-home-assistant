"""Compile nilm_flux (firmware/nilm_carte) et vérifie qu'il donne les mêmes messages que la fenêtre glissante
du notebook semaine07 (référence numpy de attendu_nilm.py), avec le modèle int8 exécuté par onnxruntime."""
import ctypes
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

DOSSIER = Path(__file__).resolve().parents[1] / "firmware" / "nilm_carte"
spec = importlib.util.spec_from_file_location("attendu_nilm", DOSSIER / "attendu_nilm.py")
attendu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(attendu)

try:
    import onnxruntime  # noqa: F401
    ORT = True
except ImportError:
    ORT = False


def serie_synthetique(nb_min: int, graine: int = 0) -> np.ndarray:
    """Talon, cycles de frigo, bouilloires et une machine : assez réaliste pour faire réagir le modèle."""
    rng = np.random.default_rng(graine)
    t = np.arange(nb_min)
    p = 250 + 30 * np.sin(2 * np.pi * t / 1440) + rng.normal(0, 10, nb_min)
    p += 90 * ((t % 50) < 20)                                   # frigo : 20 min sur 50
    for d in rng.integers(0, nb_min - 5, nb_min // 300):          # bouilloires : 3 min à 2,2 kW
        p[d:d + 3] += 2200
    d = nb_min // 2
    p[d:d + 90] += 400 + 1800 * ((np.arange(90) % 30) < 12)       # lave-linge
    return p


@unittest.skipUnless(shutil.which("gcc") and ORT, "gcc ou onnxruntime absent")
class NilmFlux(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp())
        so = tmp / "libnilm_flux.so"
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-std=c11", "-O2", "-shared", "-fPIC", "-o", str(so),
                        str(DOSSIER / "nilm_flux.c"), str(DOSSIER / "test_pc.c"), "-lm"], check=True)
        cls.lib = lib = ctypes.CDLL(str(so))
        lib.nf_taille.restype = ctypes.c_size_t
        lib.nf_entree.restype = ctypes.POINTER(ctypes.c_float)
        lib.nf_message.restype = ctypes.c_char_p
        lib.nf_fin_fenetre.restype = ctypes.c_int32
        lib.nilm_flux_mesure.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_float]
        lib.nilm_minute_horodate.argtypes = [ctypes.c_char_p]
        lib.nilm_minute_horodate.restype = ctypes.c_int32
        lib.nilm_flux_resultat.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int]
        cls.session = attendu.ouvrir_modele()

    def carte(self, mesures):
        """Fait tourner le code C sur une liste (minute, puissance) ; renvoie [(fin de fenêtre, message)]."""
        lib, s = self.lib, self.session
        f = ctypes.create_string_buffer(lib.nf_taille())
        lib.nilm_flux_init(f)
        nom_in, nom_out = s.get_inputs()[0].name, s.get_outputs()[0].name
        res = []
        for minute, p in mesures:
            if lib.nilm_flux_mesure(f, int(minute), float(p)):
                x = np.ctypeslib.as_array(lib.nf_entree(f), shape=(3 * 272,)).reshape(1, 3, 272).copy()
                y = s.run([nom_out], {nom_in: x})[0].astype(np.float32).ravel()
                lib.nilm_flux_resultat(f, y.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), 0)
                res.append((lib.nf_fin_fenetre(f), lib.nf_message(f).decode()))
        return res

    def comparer(self, carte, reference):
        self.assertGreater(len(reference), 5)
        self.assertEqual([r[0] for r in carte], [r[0] for r in reference])
        for (_, mc), (_, mr, _) in zip(carte, reference):
            c, r = mc.split(";"), mr.split(";")
            self.assertEqual(c[0], r[0])                          # même quart d'heure
            ecart = np.abs(np.array(c[1:], dtype=int) - np.array(r[1:], dtype=int)).max()
            self.assertLessEqual(ecart, 1, f"carte {mc} / référence {mr}")   # arrondis float32 / float64

    def test_horodate(self):
        h = self.lib.nilm_minute_horodate
        self.assertEqual(h(b"E140115183000") - h(b"E140115000000"), 18 * 60 + 30)
        self.assertEqual(h(b"H140301000000") - h(b"H140228000000"), 1440)     # 2014 non bissextile
        self.assertEqual(h(b"H160301000000") - h(b"H160228000000"), 2 * 1440)  # 2016 bissextile
        self.assertEqual(h(b"H150101000000") - h(b"H141231235900"), 1)
        self.assertEqual(h(b"Exyz"), -1)

    def test_une_mesure_par_minute(self):
        p = serie_synthetique(1000)
        m0 = 5 * 1440 + 3 * 60 + 11                                # départ à 3 h 11
        carte = self.carte([(m0 + i, v) for i, v in enumerate(p)] + [(m0 + len(p), 0.0)])
        self.comparer(carte, attendu.messages_attendus(p, m0, self.session))
        self.assertTrue(all(m.split(";")[0][2:] in ("00", "15", "30", "45") for _, m in carte))

    def test_plusieurs_mesures_par_minute_et_trou(self):
        rng = np.random.default_rng(3)
        p = serie_synthetique(900, graine=1)
        m0 = 20 * 1440
        mesures, ref = [], p.copy()
        for i, v in enumerate(p):
            if 400 <= i < 412:                                     # 12 minutes sans aucune trame
                ref[i] = np.nan
                continue
            echantillons = v + rng.normal(0, 20, rng.integers(1, 6))
            ref[i] = echantillons.astype(np.float32).mean()
            mesures += [(m0 + i, e) for e in echantillons]
        mesures.append((m0 + len(p), 0.0))
        self.comparer(self.carte(mesures), attendu.messages_attendus(ref, m0, self.session))


if __name__ == "__main__":
    unittest.main()
