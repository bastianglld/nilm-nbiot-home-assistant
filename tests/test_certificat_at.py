"""Tests de certificat_at.py (commande AT#TLSCERTADD pour le ST87M01)."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "tests_st87m01"))

import certificat_at as ca  # noqa: E402


@unittest.skipUnless(shutil.which("openssl"), "openssl absent")
class TestCertificat(unittest.TestCase):
    def certificat(self, cle):
        d = tempfile.mkdtemp()
        pem = Path(d) / "c.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", cle, *(
            ["-pkeyopt", "ec_paramgen_curve:P-384"] if cle == "ec" else []),
            "-nodes", "-keyout", str(Path(d) / "k.pem"), "-out", str(pem), "-subj", "/CN=test", "-days", "1"],
            check=True, capture_output=True)
        return pem

    def test_ecdsa_accepte(self):
        pem = self.certificat("ec")
        der = ca.lire_der(pem)
        self.assertEqual(ca.type_de_cle(der), "ECDSA P-384")
        ligne = ca.commande(der)
        self.assertTrue(ligne.startswith(f"AT#TLSCERTADD=0,1,{len(der)},30"))
        self.assertEqual(ca.main([str(pem)]), 0)

    def test_der_accepte(self):
        pem = self.certificat("ec")
        der_fichier = pem.with_suffix(".der")
        der_fichier.write_bytes(ca.lire_der(pem))
        self.assertEqual(ca.lire_der(der_fichier), ca.lire_der(pem))

    def test_rsa_refuse(self):
        pem = self.certificat("rsa:2048")
        self.assertEqual(ca.type_de_cle(ca.lire_der(pem)), "RSA")
        self.assertEqual(ca.main([str(pem)]), 1)


if __name__ == "__main__":
    unittest.main()
