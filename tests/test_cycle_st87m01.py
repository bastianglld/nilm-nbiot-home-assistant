"""Tests du cycle d'échange du ST87M01 (cycle_st87m01.py), avec le faux module."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "tests_st87m01"))

import cycle_st87m01 as cy  # noqa: E402
import test_jour1 as tj  # noqa: E402
from faux_st87m01 import FauxST87M01, HorlogeSimulee  # noqa: E402


def lancer(args=(), attache=False, **faux):
    """Déroule la séance avec le faux module ; renvoie (détail, cycles, faux module, horloge)."""
    o = cy.options(["--simulateur", *args])
    h = HorlogeSimulee()
    module = FauxST87M01(horloge=h, **faux)
    if attache:  # module déjà attaché, comme entre deux cycles réels
        h.avancer(module.attache_apres)
        module.ipcfg_attendu = False
    detail, cycles = cy.seance(tj.Modem(module, tj.Journal(None, ecran=False), h.maintenant), o, h.avancer, h.maintenant)
    return detail, cycles, module, h


class TestLecture(unittest.TestCase):
    def test_apn(self):
        self.assertTrue(cy.apn_correct('+CGDCONT: 5,"IP","EAPN1.NET","100.0.0.1",0,0', "eapn1.net"))
        self.assertFalse(cy.apn_correct('+CGDCONT: 5,"IPV4V6","","100.0.0.1"', "eapn1.net"))  # cas du 25 nov
        self.assertFalse(cy.apn_correct(None, "eapn1.net"))

    def test_decoder_recu(self):
        self.assertEqual(cy.decoder_recu("#MQTTRECV: nilm/maison/cmd/chauffe_eau,ON"),
                         ("nilm/maison/cmd/chauffe_eau", "ON"))
        self.assertEqual(cy.decoder_recu("#MQTTRECV: nilm/maison/cmd/plan,2611;R;000003;002AAAAAAA005;00;00"),
                         ("nilm/maison/cmd/plan", "2611;R;000003;002AAAAAAA005;00;00"))


class TestCycle(unittest.TestCase):
    def test_cycle_nominal(self):
        detail, cycles, module, _ = lancer()
        self.assertEqual(len(cycles), 1)
        c = cycles[0]
        self.assertTrue(c.ok, (c.etape_echec, c.erreur))
        self.assertIn(("nilm/maison/cmd/chauffe_eau", "OFF"), c.recus)
        self.assertEqual(c.confirmes, [("nilm/maison/cmd/chauffe_eau/etat", "OFF")])
        # message entier (entre guillemets), puis confirmation de l'état du relais
        self.assertEqual(module.publies, [("nilm/maison/etat", "1615;21;48;0;0;310"),
                                          ("nilm/maison/cmd/chauffe_eau/etat", "OFF")])
        self.assertIn("AT#MQTTSUB=nilm/maison/cmd/plan,1,nilm/maison/cmd/chauffe_eau,1", module.recues)
        self.assertFalse(any("+" in t for t in module.abonnements))  # pas de joker
        self.assertIn("AT#MQTTCFG=nilm_01,60,60,3,120", module.recues)
        self.assertEqual(module.recues[-1], "AT#MQTTDISC")  # pas de AT#SOCKETCLOSE après la déconnexion

    def test_deja_attache_sans_cfun(self):
        # 26 nov : 12 min après le cycle précédent, le module était toujours attaché avec son adresse
        detail, cycles, module, _ = lancer(attache=True)
        self.assertTrue(cycles[0].ok)
        self.assertNotIn("AT+CFUN=1", module.recues)
        self.assertIn("pas de AT+CFUN", detail)

    def test_nouvelle_session_et_fermeture(self):
        detail, cycles, module, _ = lancer(["--cycles", "10", "--nouvelle-session", "--fermer-session"], attache=True)
        self.assertEqual(sum(c.ok for c in cycles), 10)
        self.assertEqual(module.recues.count("AT+CFUN=1"), 1)
        self.assertEqual(module.recues[-1], "AT+CFUN=0")

    def test_intervalle(self):
        _, cycles, _, h = lancer(["--cycles", "3", "--intervalle", "900"], attache=True)
        self.assertEqual(len(cycles), 3)
        self.assertGreaterEqual(h.maintenant(), 40 + 2 * 900)

    def test_apn_efface(self):
        detail, cycles, module, _ = lancer(apn="")
        self.assertEqual(cycles, [])
        self.assertIn("--corriger-apn", detail)
        self.assertFalse(any(c.startswith("AT#MQTT") for c in module.recues))
        detail, cycles, module, _ = lancer(["--corriger-apn"], apn="")
        self.assertTrue(cycles[0].ok)
        self.assertIn('AT+CGDCONT=5,"IP","eapn1.net"', module.recues)

    def test_pile_bloquee_puis_reprise(self):
        # 25 nov : #TCPSENDFAIL puis 2215 / 2220 ; seul AT#RESET=1 débloque la pile
        detail, cycles, module, _ = lancer(["--cycles", "2"], attache=True, bloque_apres=2)
        self.assertTrue(cycles[0].ok)
        self.assertTrue(cycles[1].ok, (cycles[1].etape_echec, cycles[1].erreur))
        self.assertTrue(cycles[1].reprise)
        self.assertIn("AT#RESET=1", module.recues)
        self.assertNotIn("AT#RESET=0", module.recues)

    def test_pile_bloquee_sans_reprise(self):
        detail, cycles, module, _ = lancer(["--cycles", "3", "--sans-reprise"], attache=True, bloque_apres=2)
        self.assertEqual(len(cycles), 2)
        self.assertFalse(cycles[1].ok)
        self.assertEqual(cycles[1].etape_echec, "publication")
        self.assertTrue(cycles[1].bloque)
        self.assertNotIn("AT#RESET=1", module.recues)

    def test_broker_injoignable(self):
        detail, cycles, module, _ = lancer(["--sans-reprise"], attache=True, broker_ok=False)
        self.assertFalse(cycles[0].ok)
        self.assertEqual(cycles[0].etape_echec, "connexion")
        self.assertIn("AT#SOCKETCLOSE=5,0", module.recues)

    def test_sans_confirmation(self):
        _, cycles, module, _ = lancer(["--sans-confirmation"], attache=True)
        self.assertTrue(cycles[0].ok)
        self.assertEqual(cycles[0].confirmes, [])
        self.assertEqual(len(module.publies), 1)

    def test_commande_non_retenue(self):
        # aucun ordre gardé par le broker : rien à confirmer, le cycle réussit quand même
        _, cycles, module, _ = lancer(attache=True, retenus={"nilm/maison/cmd/plan": "2611;R;000003;002AAAAAAA005;00;00"})
        self.assertTrue(cycles[0].ok)
        self.assertEqual(cycles[0].confirmes, [])

    def test_releve(self):
        _, cycles, _, _ = lancer(attache=True)
        ligne = cy.ligne_releve(cycles[0])
        self.assertEqual(ligne["ok"], "oui")
        self.assertIn("chauffe_eau=OFF", ligne["recus"])
        self.assertEqual(set(ligne), set(cy.COLONNES))


class TestFauxModule(unittest.TestCase):
    def test_joker_non_affiche(self):
        # comportement du firmware 2.11.0 observé le 25 et le 26 nov
        h = HorlogeSimulee()
        m = FauxST87M01(horloge=h)
        h.avancer(m.attache_apres)
        modem = tj.Modem(m, tj.Journal(None, ecran=False), h.maintenant)
        modem.commande("AT#MQTTCONNECT=5,0,10.0.0.1,1883")
        modem.commande("AT#MQTTSUB=nilm/maison/cmd/+,1")
        self.assertIsNone(modem.attendre("#MQTTRECV:", 5))
        modem.commande("AT#MQTTSUB=nilm/maison/cmd/chauffe_eau,1")
        self.assertEqual(modem.attendre("#MQTTRECV:", 5), "#MQTTRECV: nilm/maison/cmd/chauffe_eau,OFF")

    def test_message_sans_guillemets_coupe(self):
        h = HorlogeSimulee()
        m = FauxST87M01(horloge=h)
        h.avancer(m.attache_apres)
        modem = tj.Modem(m, tj.Journal(None, ecran=False), h.maintenant)
        modem.commande("AT#MQTTCONNECT=5,0,10.0.0.1,1883")
        modem.commande("AT#MQTTPUB=nilm/maison/etat,1615;21;48;0;0;310,3,1,0")
        self.assertEqual(m.publies[-1], ("nilm/maison/etat", "1615"))  # cas du 20 nov


if __name__ == "__main__":
    unittest.main()
