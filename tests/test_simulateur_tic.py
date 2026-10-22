"""Tests du simulateur TIC (firmware/tic/simulateur_tic.py), sans port série."""
import datetime as dt
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "tic"))
import simulateur_tic as tic  # noqa: E402

T = dt.datetime(2025, 1, 21, 18, 30, 0)


class SommeControle(unittest.TestCase):
    def test_exemple_historique_connu(self):
        # groupe historique classique « IINST 002 Y »
        self.assertEqual(tic.groupe_historique("IINST", "002"), b"\nIINST 002 Y\r")

    def test_standard_inclut_la_derniere_tabulation(self):
        g = tic.groupe_standard("SINSTS", "00712")
        corps = b"SINSTS\t00712\t"
        self.assertEqual(g, b"\n" + corps + tic.somme_controle(corps) + b"\r")

    def test_parite_8n1(self):
        # 'A' = 0x41 a deux bits à 1 : parité paire 0 ; 'C' = 0x43 en a trois : bit 7 à 1
        self.assertEqual(tic.ajouter_parite_8n1(b"AC"), bytes([0x41, 0xC3]))


class AllerRetour(unittest.TestCase):
    def verifier(self, mode, offre, cle_p):
        cpt = tic.Compteur(mode=mode, offre=offre, couleur="ROUGE" if offre == "tempo" else None,
                           demain="BLANC" if offre == "tempo" else None)
        flux = cpt.trame(T, 912, 231) + cpt.trame(T, 2500, 229)
        trames = tic.decouper_trames(tic.ajouter_parite_8n1(flux))
        self.assertEqual(len(trames), 2)
        for tr, p in zip(trames, (912, 2500)):
            self.assertEqual(tic.detecter_mode(tr), mode)
            res = tic.decoder_trame(tr, mode)
            self.assertEqual(res["erreurs"], [])
            self.assertEqual(int(res["valeurs"][cle_p]), p)
        return res["valeurs"]

    def test_standard_tempo(self):
        v = self.verifier("standard", "tempo", "SINSTS")
        stge = int(v["STGE"], 16)
        self.assertEqual((stge >> 24) & 3, 3)        # aujourd'hui rouge
        self.assertEqual((stge >> 26) & 3, 2)        # demain blanc
        self.assertEqual(v["LTARF"].strip(), "HP ROUGE")
        self.assertEqual(v["DATE"][0], "H250121183000")

    def test_historique_hphc(self):
        v = self.verifier("historique", "hphc", "PAPP")
        self.assertEqual(v["PTEC"], "HP..")
        self.assertEqual(v["IINST"], "011")

    def test_historique_tempo(self):
        v = self.verifier("historique", "tempo", "PAPP")
        self.assertEqual(v["PTEC"], "HPJR")
        self.assertEqual(v["DEMAIN"], "BLAN")


class Erreurs(unittest.TestCase):
    def test_trames_abimees_detectees(self):
        rng = random.Random(3)
        cpt = tic.Compteur(mode="standard", offre="base")
        for _ in range(50):
            trame, quoi = tic.abimer(cpt.trame(T, 500, 230), rng)
            trames = tic.decouper_trames(trame)
            if quoi in ("trame interrompue", "ETX manquant"):
                self.assertEqual(trames, [], quoi)
            else:
                self.assertTrue(tic.decoder_trame(trames[0], "standard")["erreurs"], quoi)


class Index(unittest.TestCase):
    def test_index_augmente_selon_le_poste(self):
        cpt = tic.Compteur(offre="hphc")
        hc0, hp0 = cpt.index_wh["hc"], cpt.index_wh["hp"]
        cpt.avancer(1000, 3600, dt.datetime(2025, 1, 21, 23, 0))   # 1 h à 1 000 VA en heures creuses
        self.assertAlmostEqual(cpt.index_wh["hc"] - hc0, 900)      # cos phi 0,9
        self.assertEqual(cpt.index_wh["hp"], hp0)


if __name__ == "__main__":
    unittest.main()
