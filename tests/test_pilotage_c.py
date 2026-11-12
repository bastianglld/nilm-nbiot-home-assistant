"""Compile le pilotage de la carte (firmware/pilotage) et vérifie le décodage du planning de l'EMS
(mêmes messages que flexibilite/ems_serveur.py), les ordres de Home Assistant et le secours."""
import ctypes
import datetime as dt
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parents[1]
DOSSIER = RACINE / "firmware" / "pilotage"
sys.path.insert(0, str(RACINE / "flexibilite"))
import ems_serveur as ems  # noqa: E402

PLAN, ORDRE, REPETE, IGNORE, ERREUR = 1, 2, 3, 0, -1
CE, CHAUFFAGE = 0, 1
SECOURS, O_PLAN, O_ORDRE = 0, 1, 2


def minute(t: dt.datetime) -> int:
    """Minute locale depuis le 1er janvier 2000, comme nilm_minute_horodate."""
    return int((t - dt.datetime(2000, 1, 1)).total_seconds() // 60)


class PlanDecode(ctypes.Structure):
    _fields_ = [("valide", ctypes.c_uint8), ("jour", ctypes.c_uint8), ("mois", ctypes.c_uint8),
                ("couleur", ctypes.c_char), ("chauffe_eau", ctypes.c_uint32), ("batterie", ctypes.c_uint64),
                ("depart_lave_linge", ctypes.c_uint8), ("depart_lave_vaisselle", ctypes.c_uint8)]


@unittest.skipUnless(shutil.which("gcc"), "gcc absent")
class Pilotage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        so = Path(tempfile.mkdtemp()) / "libpilotage.so"
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-std=c11", "-O2", "-shared", "-fPIC", "-o", str(so),
                        str(DOSSIER / "pilotage.c"), str(DOSSIER / "test_pc.c")], check=True)
        cls.lib = lib = ctypes.CDLL(str(so))
        lib.pl_taille.restype = ctypes.c_size_t
        lib.pilotage_message.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int32]
        lib.pilotage_evaluer.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        lib.pilotage_evaluer.restype = ctypes.c_uint32
        lib.pilotage_decoder_plan.argtypes = [ctypes.c_char_p, ctypes.POINTER(PlanDecode)]
        lib.pilotage_date.argtypes = [ctypes.c_int32] + [ctypes.POINTER(ctypes.c_int)] * 3
        lib.pl_compteur.restype = ctypes.c_uint32
        lib.pilotage_confirmation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t,
                                              ctypes.c_char_p, ctypes.c_size_t]

    def nouveau(self):
        p = ctypes.create_string_buffer(self.lib.pl_taille())
        self.lib.pilotage_init(p)
        return p

    def msg(self, p, topic, m, t):
        return self.lib.pilotage_message(p, topic.encode(), m.encode(), minute(t))

    def etat(self, p, t):
        self.lib.pilotage_evaluer(p, minute(t))
        return self.lib.pl_etat(p, CE), self.lib.pl_origine(p, CE), self.lib.pl_batterie(p)

    # ---------------------------------------------------------------- calendrier et décodage
    def test_date(self):
        j, m, h = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
        t = dt.datetime(2000, 1, 1)
        while t < dt.datetime(2040, 1, 1):
            self.lib.pilotage_date(minute(t), ctypes.byref(j), ctypes.byref(m), ctypes.byref(h))
            self.assertEqual((j.value, m.value, h.value), (t.day, t.month, t.hour), t)
            t += dt.timedelta(hours=37, minutes=13)

    def test_meme_planning_que_l_ems(self):
        """Les plannings de ems_serveur.encoder_plan sont décodés sans perte par la carte."""
        rng = np.random.default_rng(1)
        for _ in range(300):
            jour = dt.date(2026, 1, 1) + dt.timedelta(days=int(rng.integers(0, 365)))
            autor = rng.random(24) < 0.3
            modes = rng.integers(0, 3, 24)
            ll, lv = int(rng.integers(0, 24)), int(rng.integers(0, 24))
            couleur = [None, "BLEU", "BLANC", "ROUGE"][int(rng.integers(0, 4))]
            msg = ems.encoder_plan(str(jour), autor, modes, ll, lv, couleur)
            pl = PlanDecode()
            self.assertEqual(self.lib.pilotage_decoder_plan(msg.encode(), ctypes.byref(pl)), 0, msg)
            self.assertEqual((pl.jour, pl.mois), (jour.day, jour.month))
            self.assertEqual(pl.couleur.decode(), msg[5])
            self.assertEqual([(pl.chauffe_eau >> h) & 1 for h in range(24)], [int(a) for a in autor])
            self.assertEqual([(pl.batterie >> (2 * h)) & 3 for h in range(24)], [int(x) for x in modes])
            self.assertEqual((pl.depart_lave_linge, pl.depart_lave_vaisselle), (ll, lv))

    def test_plannings_rejetes(self):
        bon = "2101;R;000003;0002AAAAA005;22;22"
        pl = PlanDecode()
        self.assertEqual(self.lib.pilotage_decoder_plan((bon + "\r\n").encode(), ctypes.byref(pl)), 0)
        for faux in [bon[:-1], bon + "0", bon.replace(";", ",", 1), "3201" + bon[4:], "2113" + bon[4:],
                     bon[:5] + "X" + bon[6:], bon[:7] + "00000G" + bon[13:], bon[:14] + "00000000000F" + bon[26:],
                     bon[:27] + "24" + bon[29:], ""]:
            self.assertLess(self.lib.pilotage_decoder_plan(faux.encode(), ctypes.byref(pl)), 0, faux)
        p = self.nouveau()
        self.assertEqual(self.msg(p, "nilm/maison/cmd/plan", "n'importe quoi", dt.datetime(2026, 1, 20, 14)), ERREUR)
        self.assertEqual(self.lib.pl_compteur(p, 1), 1)

    # ---------------------------------------------------------------- comportement
    def test_secours_sans_planning(self):
        p = self.nouveau()
        for h, attendu in [(0, 1), (5, 1), (6, 0), (12, 0), (21, 0), (22, 1), (23, 1)]:
            self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, h, 30)), (attendu, SECOURS, 0), h)
        self.lib.pilotage_evaluer(p, minute(dt.datetime(2026, 1, 21, 12)))
        self.assertEqual(self.lib.pl_etat(p, CHAUFFAGE), 1)                  # radiateur autorisé par défaut

    def test_planning_du_jour_et_du_lendemain(self):
        p = self.nouveau()
        # reçu le 20 janvier à 13 h 30 pour le 21 : le 20 reste en secours
        self.assertEqual(self.msg(p, "nilm/maison/cmd/plan", "2101;R;000003;0002AAAAA005;22;22",
                                  dt.datetime(2026, 1, 20, 13, 30)), PLAN)
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 20, 23)), (1, SECOURS, 0))
        # le 21 : chauffe de 0 h à 2 h, batterie en charge de 0 h à 2 h et en décharge de 6 h à 17 h
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 0, 0)), (1, O_PLAN, 1))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 1, 59)), (1, O_PLAN, 1))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 2, 0)), (0, O_PLAN, 0))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 6, 0)), (0, O_PLAN, 2))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 16, 59)), (0, O_PLAN, 2))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 17, 0)), (0, O_PLAN, 0))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 23, 0)), (0, O_PLAN, 0))   # pas de chauffe à 23 h
        # le 22 sans planning : retour au secours
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 22, 0, 30)), (1, SECOURS, 0))
        # deux jours rangés : le plan du 22 arrive le 21, celui du 21 reste utilisé le 21
        self.assertEqual(self.msg(p, "nilm/maison/cmd/plan", "2201;W;FFFFFF;000000000000;03;04",
                                  dt.datetime(2026, 1, 21, 13, 30)), PLAN)
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 14)), (0, O_PLAN, 2))   # toujours le plan du 21
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 22, 14)), (1, O_PLAN, 0))

    def test_ordre_jusqu_au_prochain_changement(self):
        p = self.nouveau()
        self.msg(p, "nilm/maison/cmd/plan", "2101;R;C00003;000000000000;22;22", dt.datetime(2026, 1, 20, 13, 30))
        # plan du 21 : chauffe 0-2 h et 22-24 h ; ordre ON à 10 h 15 -> forcé jusqu'à 22 h (prochain changement)
        t = dt.datetime(2026, 1, 21, 10, 15)
        self.assertEqual(self.etat(p, t), (0, O_PLAN, 0))
        self.assertEqual(self.msg(p, "nilm/maison/cmd/chauffe_eau", "ON", t), ORDRE)
        self.assertEqual(self.etat(p, t), (1, O_ORDRE, 0))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 21, 59)), (1, O_ORDRE, 0))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 21, 22, 0)), (1, O_PLAN, 0))
        # ordre OFF à 23 h -> coupé jusqu'à la fin de la chauffe prévue (le 22 : secours, chauffe jusqu'à 6 h)
        t = dt.datetime(2026, 1, 21, 23, 0)
        self.assertEqual(self.msg(p, "nilm/maison/cmd/chauffe_eau", "OFF", t), ORDRE)
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 22, 5, 59)), (0, O_ORDRE, 0))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 22, 6, 0)), (0, SECOURS, 0))
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 22, 22, 0)), (1, SECOURS, 0))
        # le même OFF renvoyé à chaque connexion (retain) ne recoupe pas la chauffe
        self.assertEqual(self.msg(p, "nilm/maison/cmd/chauffe_eau", "OFF\r\n", dt.datetime(2026, 1, 22, 22, 5)), REPETE)
        self.assertEqual(self.etat(p, dt.datetime(2026, 1, 22, 22, 6)), (1, SECOURS, 0))

    def test_radiateur_suit_le_dernier_ordre(self):
        p = self.nouveau()
        t = dt.datetime(2026, 1, 21, 9)
        self.assertEqual(self.msg(p, "nilm/maison/cmd/chauffage", "OFF", t), ORDRE)
        for k in range(0, 72, 7):
            self.lib.pilotage_evaluer(p, minute(t + dt.timedelta(hours=k)))
            self.assertEqual(self.lib.pl_etat(p, CHAUFFAGE), 0)
        self.assertEqual(self.msg(p, "nilm/maison/cmd/chauffage", "ON", t + dt.timedelta(days=3)), ORDRE)
        self.lib.pilotage_evaluer(p, minute(t + dt.timedelta(days=3)))
        self.assertEqual(self.lib.pl_etat(p, CHAUFFAGE), 1)

    def test_topics_et_confirmations(self):
        p = self.nouveau()
        t = dt.datetime(2026, 1, 21, 12)
        for topic, m in [("nilm/maison/cmd/chauffe_eau/etat", "ON"), ("nilm/maison/etat", "1615;21;48;0;0;310"),
                         ("nilm/maison/cmd/batterie", "ON"), ("autre/cmd/plan", "x")]:
            self.assertEqual(self.msg(p, topic, m, t), IGNORE, topic)
        self.assertEqual(self.msg(p, "nilm/maison/cmd/chauffe_eau", "on", t), ERREUR)
        # 1re évaluation : tous les états sont « nouveaux » (publiés au démarrage), puis plus rien sans changement
        self.assertEqual(self.lib.pilotage_evaluer(p, minute(t)), 0b11)
        self.assertEqual(self.lib.pilotage_evaluer(p, minute(t) + 1), 0)
        self.msg(p, "nilm/maison/cmd/chauffe_eau", "ON", t)
        self.assertEqual(self.lib.pilotage_evaluer(p, minute(t) + 2), 0b01)
        topic, m = ctypes.create_string_buffer(64), ctypes.create_string_buffer(8)
        self.assertEqual(self.lib.pilotage_confirmation(p, CE, topic, 64, m, 8), 0)
        self.assertEqual((topic.value, m.value), (b"nilm/maison/cmd/chauffe_eau/etat", b"ON"))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("gcc"), "gcc absent")
class AppliSurPC(unittest.TestCase):
    """Programme complet de la carte (appli_nilm.c) sur PC : trames TIC du simulateur et messages MQTT simulés."""

    def test_planning_et_ordres(self):
        fw = RACINE / "firmware"
        tmp = Path(tempfile.mkdtemp())
        essai, flux = tmp / "essai", tmp / "flux.bin"
        subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DNILM_AFFICHER_DUREE=0",
                        "-I", str(DOSSIER / "essai_pc"), "-I", str(DOSSIER), "-I", str(fw / "nilm_carte"),
                        "-I", str(fw / "tic"), "-I", str(fw / "mesure_vi"),
                        str(DOSSIER / "essai_appli_pc.c"), str(DOSSIER / "pilotage.c"),
                        str(fw / "nilm_carte" / "appli_nilm.c"), str(fw / "nilm_carte" / "nilm_flux.c"),
                        str(fw / "tic" / "tic_decodeur.c"), str(fw / "mesure_vi" / "mesure_vi.c"),
                        "-lm", "-o", str(essai)], check=True)
        subprocess.run([sys.executable, str(fw / "tic" / "simulateur_tic.py"), "envoyer", "--sortie", str(flux),
                        "--puissance", "800", "--debut", "2026-01-20 12:00:00", "--accel", "60", "--nb", "1800",
                        "--mqtt", "90 nilm/maison/cmd/plan 2101;R;C00003;0002AAAAA005;22;22",
                        "--mqtt", "95 nilm/maison/cmd/plan 21XX;R;C00003;0002AAAAA005;22;22",
                        "--mqtt", "1335 nilm/maison/cmd/chauffe_eau ON",
                        "--mqtt", "1400 nilm/maison/cmd/chauffe_eau ON",
                        "--mqtt", "1500 nilm/maison/cmd/chauffage OFF",
                        "--mqtt", "1510 nilm/maison/cmd/chauffe_eau/etat ON"],
                       check=True, capture_output=True)
        sortie = subprocess.run([str(essai), str(flux)], check=True, capture_output=True, text=True).stdout
        lignes = [l.strip() for l in sortie.splitlines() if l.startswith(("RELAIS", "BATTERIE", "RECU", "MQTT"))]
        attendu = [
            "MQTT nilm/maison/cmd/chauffe_eau/etat OFF", "RELAIS 1200 chauffe_eau OFF (secours)",
            "MQTT nilm/maison/cmd/chauffage/etat ON", "RELAIS 1200 chauffage ON (secours)", "BATTERIE 1200 repos",
            "RECU nilm/maison/cmd/plan : planning ok", "RECU nilm/maison/cmd/plan : REJETE",
            "MQTT nilm/maison/cmd/chauffe_eau/etat ON", "RELAIS 2200 chauffe_eau ON (secours)",
            "BATTERIE 0000 charge",
            "MQTT nilm/maison/cmd/chauffe_eau/etat OFF", "RELAIS 0200 chauffe_eau OFF (plan)",
            "BATTERIE 0200 repos", "BATTERIE 0600 decharge",
            "RECU nilm/maison/cmd/chauffe_eau : ordre ok",
            "MQTT nilm/maison/cmd/chauffe_eau/etat ON", "RELAIS 1014 chauffe_eau ON (ordre)",
            "RECU nilm/maison/cmd/chauffe_eau : ordre deja recu",
            "RECU nilm/maison/cmd/chauffage : ordre ok",
            "MQTT nilm/maison/cmd/chauffage/etat OFF", "RELAIS 1259 chauffage OFF (ordre)",
            "RECU nilm/maison/cmd/chauffe_eau/etat : ignore", "BATTERIE 1700 repos"]
        self.assertEqual(lignes, attendu)
        self.assertGreater(sum(l.startswith("NILM ") for l in sortie.splitlines()), 100)   # le NILM tourne toujours
