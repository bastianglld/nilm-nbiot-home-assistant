"""Compile l'envoi groupé de la carte (firmware/nilm_carte/envoi_groupe.c) et vérifie quand la carte se connecte :
une connexion pour 4 mesures (une heure), tout de suite pour un message urgent, messages gardés si le réseau
manque, file bornée."""
import ctypes
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1] / "firmware" / "nilm_carte"
OK, REFUSE = 0, -1
CONNEXIONS, ECHECS, PUBLIES, PERDUS, REFUSES = range(5)
CAPACITE = 16
ETAT = "nilm/maison/etat"
CONFIRMATION = "nilm/maison/cmd/chauffe_eau/etat"

OUVRIR = ctypes.CFUNCTYPE(ctypes.c_int)
PUBLIER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p)
FERMER = ctypes.CFUNCTYPE(None, ctypes.c_uint16)


class Liaison(ctypes.Structure):
    _fields_ = [("ouvrir", OUVRIR), ("publier", PUBLIER), ("fermer", FERMER)]


class FauxModule:
    """Remplace le ST87M01 : note les connexions et les messages publiés ; peut simuler un réseau absent."""

    def __init__(self):
        self.reseau = True          # False : l'ouverture échoue
        self.publications_ok = None  # nombre de publications réussies avant une panne (None : pas de panne)
        self.journal = []           # ("ouvrir",), ("publier", topic, message), ("fermer", n)
        self.pendant_publication = None   # appelée après une publication (message reçu pendant la connexion)
        self.c = Liaison(OUVRIR(self.ouvrir), PUBLIER(self.publier), FERMER(self.fermer))

    def ouvrir(self):
        if not self.reseau:
            return -1
        self.journal.append(("ouvrir",))
        return 0

    def publier(self, topic, message):
        if self.publications_ok is not None:
            if self.publications_ok == 0:
                return -1
            self.publications_ok -= 1
        self.journal.append(("publier", topic.decode(), message.decode()))
        if self.pendant_publication:
            f, self.pendant_publication = self.pendant_publication, None
            f()
        return 0

    def fermer(self, n):
        self.journal.append(("fermer", n))

    def connexions(self):
        """Liste des connexions, chacune avec la liste des messages publiés."""
        res = []
        for e in self.journal:
            if e[0] == "ouvrir":
                res.append([])
            elif e[0] == "publier":
                res[-1].append(e[2])
            elif e[1] != len(res[-1]):
                raise AssertionError(f"fermer({e[1]}) après {len(res[-1])} messages publiés")
        return res


@unittest.skipUnless(shutil.which("gcc"), "gcc absent")
class EnvoiGroupe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        so = Path(tempfile.mkdtemp()) / "libenvoi_groupe.so"
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-std=c11", "-O2", "-shared", "-fPIC", "-o", str(so),
                        str(DOSSIER / "envoi_groupe.c"), str(DOSSIER / "test_pc.c")], check=True)
        cls.lib = lib = ctypes.CDLL(str(so))
        lib.eg_taille.restype = ctypes.c_size_t
        lib.eg_compteur.restype = ctypes.c_uint32
        lib.envoi_init.argtypes = [ctypes.c_void_p, ctypes.POINTER(Liaison)]
        for f in (lib.envoi_mesure, lib.envoi_urgent):
            f.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        lib.envoi_vider.argtypes = [ctypes.c_void_p]

    def setUp(self):
        self.module = FauxModule()
        self.e = ctypes.create_string_buffer(self.lib.eg_taille())
        self.lib.envoi_init(self.e, ctypes.byref(self.module.c))

    def mesure(self, message, topic=ETAT):
        return self.lib.envoi_mesure(self.e, topic.encode(), message.encode())

    def urgent(self, message, topic=CONFIRMATION):
        return self.lib.envoi_urgent(self.e, topic.encode(), message.encode())

    def compteur(self, i):
        return self.lib.eg_compteur(self.e, i)

    def en_file(self):
        return self.lib.eg_en_file(self.e)

    @staticmethod
    def quart(k):
        """Message NILM du k-ième quart d'heure, au format de protocole_messages.md."""
        return f"{(k // 4) % 24:02d}{(k % 4) * 15:02d};21;48;0;0;310"

    # ---------------------------------------------------------------- regroupement
    def test_quatre_mesures_une_connexion(self):
        for k in range(3):
            self.assertEqual(self.mesure(self.quart(k)), OK)
        self.assertEqual(self.module.journal, [])                   # 3 mesures : rien ne part
        self.assertEqual(self.en_file(), 3)
        self.assertEqual(self.mesure(self.quart(3)), OK)
        self.assertEqual(self.module.journal, [("ouvrir",)] + [("publier", ETAT, self.quart(k)) for k in range(4)]
                         + [("fermer", 4)])
        self.assertEqual((self.compteur(CONNEXIONS), self.compteur(PUBLIES), self.en_file()), (1, 4, 0))

    def test_une_connexion_par_heure(self):
        for k in range(24 * 4):                                     # une journée de mesures
            self.mesure(self.quart(k))
        connexions = self.module.connexions()
        self.assertEqual(len(connexions), 24)
        self.assertEqual(sum(connexions, []), [self.quart(k) for k in range(96)])   # toutes, dans l'ordre
        self.assertTrue(all(len(c) == 4 for c in connexions))

    def test_trois_mesures_rien(self):
        for k in range(3):
            self.mesure(self.quart(k))
        self.assertEqual(self.module.journal, [])
        self.assertEqual((self.compteur(CONNEXIONS), self.en_file(), self.lib.eg_mesures_en_file(self.e)), (0, 3, 3))

    # ---------------------------------------------------------------- messages urgents
    def test_urgent_connexion_immediate_qui_vide_la_file(self):
        for k in range(2):
            self.mesure(self.quart(k))
        self.assertEqual(self.urgent("ON"), OK)
        self.assertEqual(self.module.journal, [("ouvrir",), ("publier", ETAT, self.quart(0)),
                                               ("publier", ETAT, self.quart(1)), ("publier", CONFIRMATION, "ON"),
                                               ("fermer", 3)])
        self.assertEqual(self.en_file(), 0)
        # le compte des mesures repart de zéro : il en faut 4 nouvelles pour la connexion suivante
        for k in range(2, 5):
            self.mesure(self.quart(k))
        self.assertEqual(self.compteur(CONNEXIONS), 1)
        self.mesure(self.quart(5))
        self.assertEqual(self.module.connexions()[1], [self.quart(k) for k in range(2, 6)])

    def test_urgent_seul(self):
        self.urgent("OFF")
        self.assertEqual(self.module.connexions(), [["OFF"]])

    def test_confirmation_pendant_la_connexion(self):
        """Un ordre reçu pendant la connexion (message retain) est confirmé dans la même connexion."""
        self.module.pendant_publication = lambda: self.urgent("ON")
        for k in range(4):
            self.mesure(self.quart(k))
        self.assertEqual(self.module.connexions(), [[self.quart(k) for k in range(4)] + ["ON"]])
        self.assertEqual((self.compteur(CONNEXIONS), self.en_file()), (1, 0))

    # ---------------------------------------------------------------- réseau absent
    def test_echec_ouverture_messages_gardes(self):
        self.module.reseau = False
        for k in range(4):
            self.mesure(self.quart(k))
        self.assertEqual((self.compteur(CONNEXIONS), self.compteur(ECHECS), self.en_file()), (0, 1, 4))
        self.mesure(self.quart(4))                                  # nouvel essai à chaque mesure
        self.assertEqual((self.compteur(ECHECS), self.en_file()), (2, 5))
        self.module.reseau = True
        self.mesure(self.quart(5))
        self.assertEqual(self.module.connexions(), [[self.quart(k) for k in range(6)]])
        self.assertEqual(self.en_file(), 0)

    def test_echec_publication_puis_renvoi_dans_l_ordre(self):
        self.module.publications_ok = 2                              # le réseau tombe après 2 messages
        for k in range(4):
            self.mesure(self.quart(k))
        self.assertEqual(self.module.journal[-1], ("fermer", 2))      # la connexion est fermée proprement
        self.assertEqual((self.compteur(ECHECS), self.compteur(PUBLIES), self.en_file()), (1, 2, 2))
        self.module.publications_ok = None
        self.urgent("ON")                                           # connexion suivante : le reste, dans l'ordre
        self.assertEqual(self.module.connexions(), [[self.quart(0), self.quart(1)],
                                                    [self.quart(2), self.quart(3), "ON"]])
        self.assertEqual(self.en_file(), 0)

    def test_urgent_garde_si_reseau_absent(self):
        self.module.reseau = False
        self.urgent("ON")
        self.assertEqual((self.compteur(ECHECS), self.en_file()), (1, 1))
        self.module.reseau = True
        self.mesure(self.quart(0))                                  # un urgent attend : nouvel essai tout de suite
        self.assertEqual(self.module.connexions(), [["ON", self.quart(0)]])

    def test_debordement(self):
        self.module.reseau = False
        for k in range(CAPACITE + 5):
            self.assertEqual(self.mesure(self.quart(k)), OK)
        self.assertEqual((self.en_file(), self.compteur(PERDUS)), (CAPACITE, 5))
        self.module.reseau = True
        self.assertEqual(self.lib.envoi_vider(self.e), CAPACITE)
        self.assertEqual(self.module.connexions(), [[self.quart(k) for k in range(5, CAPACITE + 5)]])  # les 5 plus anciens jetés

    # ---------------------------------------------------------------- tailles
    def test_messages_trop_longs_refuses(self):
        self.assertEqual(self.mesure("x" * 50), OK)
        self.assertEqual(self.mesure("x" * 51), REFUSE)
        self.assertEqual(self.mesure("1615;21;48;0;0;310", topic="t" * 48), OK)
        self.assertEqual(self.mesure("1615;21;48;0;0;310", topic="t" * 49), REFUSE)
        self.assertEqual(self.mesure("1615;21;48;0;0;310", topic=""), REFUSE)
        self.assertEqual(self.urgent("O" * 51), REFUSE)
        self.assertEqual((self.en_file(), self.compteur(REFUSES), self.module.journal), (2, 4, []))
        self.assertEqual(self.lib.envoi_vider(self.e), 2)
        self.assertEqual(self.module.connexions(), [["x" * 50, "1615;21;48;0;0;310"]])

    def test_vider_file_vide(self):
        self.assertEqual(self.lib.envoi_vider(self.e), 0)
        self.assertEqual(self.module.journal, [("ouvrir",), ("fermer", 0)])


if __name__ == "__main__":
    unittest.main()
