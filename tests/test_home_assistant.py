"""Tests de la partie Home Assistant / broker : simulateur, configs de découverte et droits du broker."""
import datetime as dt
import json
import random
import re
import sys
import unittest
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "cloud" / "simulateur"))
sys.path.insert(0, str(RACINE / "flexibilite"))
import nilm_simulateur as sim  # noqa: E402
import ems_serveur as ems  # noqa: E402

DECOUVERTE = RACINE / "homeassistant" / "mqtt-discovery"
TOPICS_PROTOCOLE = {"nilm/maison/etat", "nilm/maison/dispo", "nilm/maison/conseils"}


class Simulateur(unittest.TestCase):
    def setUp(self):
        random.seed(1)

    def test_format_du_protocole(self):
        msg = sim.mesure(dt.datetime(2026, 11, 20, 16, 15))
        champs = msg.split(";")
        self.assertEqual(len(champs), 6)
        self.assertEqual(champs[0], "1615")
        wh = [int(c) for c in champs[1:]]
        self.assertGreaterEqual(wh[-1], sum(wh[:-1]))  # le total contient tous les appareils
        self.assertLessEqual(len(msg), 50)             # limite du ST87M01

    def test_lu_par_l_ems(self):
        # l'EMS doit pouvoir enregistrer les messages du simulateur
        msg = sim.mesure(dt.datetime(2026, 11, 20, 16, 15))
        r = ems.decoder_mesures(msg, pd.Timestamp("2026-11-20 18:30"))
        self.assertEqual(r["time"], pd.Timestamp("2026-11-20 16:15"))
        self.assertEqual(r["total"], float(msg.split(";")[-1]))

    def test_quart_d_heure(self):
        self.assertEqual(sim.quart_d_heure(dt.datetime(2026, 1, 1, 9, 44, 31)), dt.datetime(2026, 1, 1, 9, 30))


class Decouverte(unittest.TestCase):
    def setUp(self):
        self.configs = list(sim.configs_decouverte())

    def test_toutes_les_configs_sont_trouvees(self):
        self.assertEqual(len(self.configs), len(list(DECOUVERTE.glob("*/*.json"))))
        self.assertGreater(len(self.configs), 0)

    def test_identifiants_uniques(self):
        ids = [cfg["unique_id"] for _, cfg in self.configs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_topics_du_protocole(self):
        for topic, cfg in self.configs:
            if "command_topic" in cfg:
                self.assertRegex(cfg["command_topic"], r"^nilm/maison/cmd/[a-z_]+$")
                self.assertNotEqual(cfg["command_topic"], "nilm/maison/cmd/plan")  # nom réservé
                self.assertEqual(cfg["state_topic"], cfg["command_topic"] + "/etat")
                self.assertTrue(cfg["retain"])  # la carte dort : l'ordre doit l'attendre
            else:
                self.assertIn(cfg["state_topic"], TOPICS_PROTOCOLE, topic)


class DroitsBroker(unittest.TestCase):
    def lire_acl(self, chemin):
        droits, compte = {}, None
        for ligne in Path(chemin).read_text().splitlines():
            if ligne.startswith("user "):
                compte = ligne.split()[1]
                droits[compte] = set()
            elif ligne.startswith("topic "):
                droits[compte].add(tuple(ligne.split()[1:]))
        return droits

    def test_acl_identiques_vps_docker_script(self):
        vps = (RACINE / "cloud" / "broker-vps" / "acl").read_text()
        self.assertEqual(vps, (RACINE / "cloud" / "broker-local-docker" / "acl").read_text())
        self.assertIn(vps, (RACINE / "cloud" / "broker-vps" / "installer-broker.sh").read_text())

    def test_comptes_du_protocole(self):
        d = self.lire_acl(RACINE / "cloud" / "broker-vps" / "acl")
        self.assertIn(("read", "nilm/maison/cmd/+"), d["module_nbiot"])
        self.assertIn(("write", "nilm/maison/cmd/+/etat"), d["module_nbiot"])
        self.assertIn(("write", "nilm/maison/cmd/plan"), d["ems"])
        self.assertIn(("write", "nilm/maison/conseils"), d["ems"])
        self.assertIn(("read", "nilm/maison/etat"), d["ems"])
        self.assertIn(("write", "nilm/maison/cmd/+"), d["homeassistant"])

    def test_aucun_secret_versionne(self):
        motif = re.compile(r"(remote_password|password)\s+(?!MOT_DE_PASSE)\S+", re.I)
        for f in list((RACINE / "cloud").rglob("*.conf")) + list((RACINE / "homeassistant").rglob("*.conf")):
            self.assertIsNone(motif.search(f.read_text()), f)


if __name__ == "__main__":
    unittest.main()
