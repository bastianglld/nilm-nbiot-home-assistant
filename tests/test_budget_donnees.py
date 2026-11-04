"""Tests du calcul du budget de données de la SIM (tâche B-45)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "tests_st87m01"))

import budget_donnees as bd  # noqa: E402


class TestBudget(unittest.TestCase):
    def test_budget_jour(self):
        self.assertAlmostEqual(bd.BUDGET_JOUR, 273973, delta=1)

    def test_limites_du_module(self):
        for texte in (bd.TOPIC_MESURE, bd.MESURE, bd.TOPIC_PLAN, bd.PLAN):
            self.assertLessEqual(len(texte), 50)

    def test_tls_coute_plus(self):
        self.assertGreater(bd.session(1), bd.session(1, reprise=True))
        self.assertGreater(bd.session(1, reprise=True), bd.session(1, tls=False))

    def test_regrouper_reduit(self):
        self.assertLess(bd.par_jour_reconnexion(24), bd.par_jour_reconnexion(96))

    def test_keep_alive(self):
        self.assertGreater(bd.par_jour_connexion_gardee(60), bd.BUDGET_JOUR)
        self.assertLess(bd.par_jour_connexion_gardee(1200), bd.par_jour_connexion_gardee(300))
        self.assertEqual(bd.par_jour_connexion_gardee(900), bd.par_jour_connexion_gardee(1200))

    def test_scenarios(self):
        codes = [c for c, _, _ in bd.scenarios()]
        self.assertEqual(len(codes), len(set(codes)))


if __name__ == "__main__":
    unittest.main()
