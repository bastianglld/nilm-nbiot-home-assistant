"""Tests du script de test du premier jour du kit ST87M01, avec le faux module."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "tests_st87m01"))

import test_jour1 as tj  # noqa: E402
from faux_st87m01 import FauxST87M01, HorlogeSimulee  # noqa: E402


def lancer(args=(), **faux):
    """Déroule la séance avec le faux module ; renvoie (résultat, faux module)."""
    o = tj.options(["--simulateur", *args])
    h = HorlogeSimulee()
    module = FauxST87M01(horloge=h, **faux)
    journal = tj.Journal(None, ecran=False)
    journal.secrets.append(o.mdp)
    r = tj.seance(tj.Modem(module, journal, h.maintenant), o, h.avancer, h.maintenant)
    return r, module


class TestLecture(unittest.TestCase):
    def test_signal(self):
        self.assertEqual(tj.signal_cesq("+CESQ: 99,99,255,255,20,50"), (-91, -10.0))
        self.assertEqual(tj.signal_cesq("+CESQ: 99,99,255,255,255,255"), (None, None))
        self.assertEqual(tj.signal_cesq("+CESQ: 99,99,255,255,0,0"), (-141, -20.0))

    def test_cereg(self):
        self.assertEqual(tj.etat_cereg('+CEREG: 2,5,"1A2B","01A2B3C4",9'), 5)
        self.assertEqual(tj.etat_cereg("+CEREG: 2,2"), 2)
        self.assertIsNone(tj.etat_cereg(None))

    def test_masquage(self):
        texte = "IMSI 208011234567890, ICCID 8933011234567890123, mdp secret42"
        m = tj.masquer(texte, ["secret42"])
        self.assertNotIn("208011234567890", m)
        self.assertNotIn("8933011234567890123", m)
        self.assertNotIn("secret42", m)
        self.assertIn("2080", m)

    def test_limites(self):
        self.assertEqual(tj.verifier_limites("nilm_01", "u", "p", ["maison/nilm_01/q"], "1615;21;48;0;0;310"), [])
        pbs = tj.verifier_limites("c" * 26, "u" * 26, "p" * 51, ["t" * 51], "m" * 51)
        self.assertEqual(len(pbs), 5)


class TestSeance(unittest.TestCase):
    def test_nominal_sans_broker(self):
        r, module = lancer()
        self.assertTrue(r.reussi, r.etapes)
        self.assertEqual(r.cereg, 5)
        self.assertGreaterEqual(r.temps_attache, 40)
        self.assertEqual((r.rsrp, r.rsrq), (-91, -10.0))
        self.assertEqual(r.adresse_ip, "10.0.0.2")
        self.assertTrue(r.ping)
        self.assertFalse(any(c.startswith("AT#MQTT") for c in module.recues))

    def test_nominal_avec_broker(self):
        r, module = lancer(["--broker", "20.19.1.2", "--utilisateur", "nilm_01"])
        self.assertTrue(r.reussi, r.etapes)
        self.assertTrue(r.mqtt_publie)
        self.assertTrue(r.mqtt_recu)
        self.assertIn("AT#SOCKETCREATE=5,0,TCP,,10,10", module.recues)
        self.assertIn("AT#MQTTPUB=maison/nilm_01/q,1615;21;48;0;0;310,3,1,0", module.recues)
        self.assertIn("AT#SOCKETCLOSE=5,0", module.recues)

    def test_broker_par_nom(self):
        r, module = lancer(["--broker", "broker.exemple.fr", "--attente-plan", "0"])
        self.assertTrue(r.reussi, r.etapes)
        self.assertIn("AT#DNS=5,0,broker.exemple.fr", module.recues)
        self.assertTrue(any(c.startswith("AT#MQTTCONNECT=5,0,20.19.1.2,1883") for c in module.recues))

    def test_sim_absente(self):
        r, module = lancer(sim=False)
        self.assertFalse(r.reussi)
        self.assertEqual(r.etapes[-1][0], "3.1")
        self.assertNotIn("AT+CEREG?", module.recues)

    def test_refus_reseau(self):
        r, _ = lancer(refus=True)
        self.assertFalse(r.reussi)
        self.assertEqual(r.cereg, 3)

    def test_pas_de_couverture(self):
        r, module = lancer(["--attente-attache", "60", "--intervalle", "10"], couverture=False)
        self.assertFalse(r.reussi)
        self.assertEqual(r.cereg, 2)
        self.assertIsNone(r.temps_attache)
        self.assertLessEqual(module.recues.count("AT+CEREG?"), 8)

    def test_module_muet(self):
        r, _ = lancer(muet=True)
        self.assertFalse(r.reussi)
        self.assertEqual(len(r.etapes), 1)

    def test_broker_injoignable(self):
        r, _ = lancer(["--broker", "20.19.1.2"], broker_ok=False)
        self.assertFalse(r.reussi)
        self.assertIsNone(r.mqtt_publie)

    def test_mot_de_passe_trop_long(self):
        o = tj.options(["--simulateur", "--broker", "20.19.1.2", "--utilisateur", "u"])
        o.mdp = "x" * 51
        h = HorlogeSimulee()
        module = FauxST87M01(horloge=h)
        r = tj.seance(tj.Modem(module, tj.Journal(None, ecran=False), h.maintenant), o, h.avancer, h.maintenant)
        self.assertFalse(r.reussi)
        self.assertFalse(any(c.startswith("AT#MQTTCONNECT") for c in module.recues))

    def test_ping_sans_reponse(self):
        # cas vu sur le kit le 6 nov : « #IPPING: 1,0,1,999999,0,0 » doit être un échec
        r, module = lancer(ping_ok=False)
        self.assertFalse(r.ping)
        self.assertFalse(r.reussi)
        self.assertIn("AT#IPPING=5,8.8.8.8,30,10,3", module.recues)

    def test_ping_recus(self):
        self.assertEqual(tj.ping_recus("#IPPING: 1,0,1,999999,0,0"), 0)
        self.assertEqual(tj.ping_recus("#IPPING: 3,2,1,1518,2210,1790"), 2)
        self.assertIsNone(tj.ping_recus(None))

    def test_module_endormi(self):
        # cas vu à la fac le 12 nov : le premier AT ne fait que réveiller le module
        r, module = lancer(endormi=1)
        self.assertTrue(r.reussi, r.etapes)
        self.assertEqual(module.recues[:2], ["AT", "AT"])

    def test_veille_desactivee(self):
        r, module = lancer()
        self.assertIn("AT#SLEEPMODE=0", module.recues)
        r, module = lancer(["--garder-veille"])
        self.assertNotIn("AT#SLEEPMODE=0", module.recues)

    def test_echo_active(self):
        r, _ = lancer(echo=True)
        self.assertTrue(r.reussi, r.etapes)


class TestFiche(unittest.TestCase):
    def test_fiche_csv(self):
        r, _ = lancer(["--broker", "20.19.1.2"])
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "fiche.csv"
            tj.ajouter_fiche(chemin, tj.ligne_fiche(r, "fenêtre"))
            tj.ajouter_fiche(chemin, tj.ligne_fiche(r, "tableau"))
            lignes = chemin.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), 3)
        self.assertTrue(lignes[0].startswith("date;lieu;firmware;cereg"))
        self.assertIn("-91", lignes[1])


if __name__ == "__main__":
    unittest.main()
