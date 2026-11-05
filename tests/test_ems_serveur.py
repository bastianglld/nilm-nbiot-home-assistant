"""Tests du programme EMS côté serveur (flexibilite/ems_serveur.py).

Ils tournent sans connexion internet : les prix viennent des fichiers rangés dans nilm/notebooks/prix/.
Lancement depuis la racine du dépôt :  python -m unittest discover tests   (ou  pytest tests/)
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "flexibilite"))
import ems_serveur as ems  # noqa: E402

PRIX_DIR = RACINE / "nilm" / "notebooks" / "prix"
HISTORIQUE = RACINE / "nilm" / "notebooks" / "profils_s9" / "messages_15min_nilm.csv"


def config():
    cfg = ems.Config()
    cfg.prix_dir = PRIX_DIR
    return cfg


class MessageDescendant(unittest.TestCase):
    """Le planning envoyé à la carte (topic nilm/maison/cmd/plan) : 32 caractères, décodage sans perte."""

    def test_aller_retour(self):
        rng = np.random.default_rng(0)
        for _ in range(200):
            autor = rng.random(24) < 0.3
            modes = rng.integers(0, 3, 24)
            ll, lv = int(rng.integers(0, 24)), int(rng.integers(0, 24))
            msg = ems.encoder_plan("2026-01-21", autor, modes, ll, lv, "ROUGE")
            self.assertEqual(len(msg), 32)
            d = ems.decoder_plan(msg)
            self.assertEqual((d["jour"], d["mois"], d["couleur"]), (21, 1, "R"))
            np.testing.assert_array_equal(d["chauffe_eau"], autor)
            np.testing.assert_array_equal(d["batterie"], modes)
            self.assertEqual((d["lave_linge"], d["lave_vaisselle"]), (ll, lv))

    def test_exemple_documente(self):
        # exemple de docs/protocole_messages.md
        d = ems.decoder_plan("2101;R;000003;0002AAAAA005;22;22")
        self.assertEqual(np.flatnonzero(d["chauffe_eau"]).tolist(), [0, 1])
        self.assertEqual(np.flatnonzero(d["batterie"] == 1).tolist(), [0, 1])
        self.assertEqual(np.flatnonzero(d["batterie"] == 2).tolist(), list(range(6, 17)))


class MessageMontant(unittest.TestCase):
    """Les mesures envoyées par la carte toutes les 15 minutes (topic nilm/maison/etat)."""

    def test_meme_jour(self):
        m = ems.decoder_mesures("1030;12.5;0;180;0;450", pd.Timestamp("2026-10-21 12:40"))
        self.assertEqual(m["time"], pd.Timestamp("2026-10-21 10:30"))
        self.assertEqual((m["fridge"], m["washing_machine"], m["total"]), (12.5, 180.0, 450.0))

    def test_quart_d_heure_de_la_veille(self):
        m = ems.decoder_mesures("2345;10;0;0;0;300", pd.Timestamp("2026-10-21 01:30"))
        self.assertEqual(m["time"], pd.Timestamp("2026-10-20 23:45"))


class Planning(unittest.TestCase):

    def test_prix_tempo_jour_rouge(self):
        p, couleur = ems.prix_horaires("Tempo", pd.Timestamp("2025-01-21"), config())
        self.assertEqual(couleur, "ROUGE")
        self.assertAlmostEqual(p[12], 0.7295)          # heure pleine rouge
        self.assertAlmostEqual(p[23], 0.1615)          # heure creuse rouge

    def test_chauffe_eau_sans_inconfort(self):
        cfg = config()
        for offre in ["Base", "HP/HC", "Tempo", "Dynamique"]:
            p, _ = ems.prix_horaires(offre, pd.Timestamp("2025-01-21"), cfg)
            autor = ems.regle_chauffe_eau(p, 0.6 * cfg.wh_cap, cfg)
            r = ems.executer_jour(autor, np.zeros(24, int), np.zeros(24), 0.6 * cfg.wh_cap, 0.0, cfg)
            self.assertEqual(r["inconfort"], 0, offre)

    def test_batterie_decharge_aux_heures_cheres(self):
        cfg = config()
        p, _ = ems.prix_horaires("Tempo", pd.Timestamp("2025-01-21"), cfg)
        modes = ems.regle_batterie(p, np.full(24, 0.5), cfg)
        self.assertTrue(np.all(p[modes == 2] > p[modes == 1].max()))

    def test_planifier_jour_rouge(self):
        cfg = config()
        plan = ems.planifier(pd.Timestamp("2025-01-21"), "Tempo", np.full(24, 0.4), 0.6 * cfg.wh_cap, cfg)
        self.assertEqual(len(plan["message"]), 32)
        self.assertTrue(plan["message"].startswith("2101;R;"))
        self.assertGreaterEqual(plan["lave_linge"], 22)   # départ conseillé en heures creuses


@unittest.skipUnless(HISTORIQUE.exists(), "historique de démonstration absent")
class Analyse(unittest.TestCase):

    def test_historique_et_habitudes(self):
        hist = ems.charger_historique(HISTORIQUE)
        self.assertTrue(hist.index.is_monotonic_increasing)
        hab, _ = ems.habitudes(hist, config())
        self.assertIn("washing_machine", hab.index)


if __name__ == "__main__":
    unittest.main()
