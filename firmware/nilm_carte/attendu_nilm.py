#!/usr/bin/env python3
"""
Messages NILM attendus pour une journée UK-DALE rejouée par le simulateur TIC, calculés sur PC
avec le même modèle int8 (onnxruntime) que celui de la carte. Sert de référence pour vérifier la carte.

    python attendu_nilm.py --ukdale ~/.../house_1/an1 --jour 2014-01-15
    python attendu_nilm.py --ukdale ~/.../house_1/an1 --jour 2014-01-15 --journal carte.txt   # compare avec la carte

Le journal est la sortie du simulateur lancé avec --retour (lignes « NILM hhmm;... » envoyées par la carte).
Le calcul suit exactement le notebook semaine07 (fenêtre glissante) : fenêtres de 272 minutes, finies à hh:07,
hh:22, hh:37 et hh:52, minutes 130 à 144 retenues, minutes manquantes à 0 sur les 3 entrées.
"""
import argparse
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
# dossier du modèle : dans le dépôt, ou à côté du simulateur sur le Mac (Projet/Modele_IA/export_s7)
EXPORT = next((d for d in (ICI.parents[1] / "nilm" / "notebooks" / "export_s7",
                           ICI.parent.parent / "Modele_IA" / "export_s7",
                           Path.home() / "Desktop/MASTER/Projet/Modele_IA/export_s7") if (d / "nilm_meta.json").exists()),
              ICI.parents[1] / "nilm" / "notebooks" / "export_s7")
META = json.loads((EXPORT / "nilm_meta.json").read_text())
WIN, STEP, RF = META["fenetre_min"], META["pas_min"], META["contexte_min"]
SL = slice(*META["minutes_retenues"])                    # 130 à 144
ECHELLES = np.array(META["sortie"]["echelles_W"], dtype=np.float32)
N_APP = len(ECHELLES)
FIN_MOD15 = (WIN - SL.start) % STEP                      # 7 : la fenêtre finit à hh:07, :22, :37, :52


def minutes_ukdale(dossier: Path, jour: dt.date) -> np.ndarray:
    """Puissance moyenne de chaque minute du jour (1440 valeurs), canal « aggregate ». Une minute sans mesure
    reprend la valeur précédente, exactement comme le simulateur TIC (SourceUKDALE.moyenne_minute)."""
    canal = next(int(l.split()[0]) for l in (dossier / "labels.dat").read_text().splitlines()
                 if l.split()[1:2] == ["aggregate"])
    debut = dt.datetime.combine(jour, dt.time(), dt.timezone.utc).timestamp()
    somme, n = np.zeros(1440), np.zeros(1440)
    with open(dossier / f"channel_{canal}.dat") as f:
        for ligne in f:
            ts, val = ligne.split()[:2]
            s = float(ts) - debut
            if s < 0:
                continue
            if s >= 86400:
                break
            somme[int(s // 60)] += float(val)
            n[int(s // 60)] += 1
    premier = None
    with open(dossier / f"channel_{canal}.dat") as f:          # première mesure du jour (valeur de départ)
        for ligne in f:
            ts, val = ligne.split()[:2]
            if float(ts) >= debut:
                premier = float(val)
                break
    p, dernier = np.empty(1440), premier
    for i in range(1440):
        dernier = somme[i] / n[i] if n[i] else dernier
        p[i] = dernier
    return p


def messages_attendus(p_w: np.ndarray, minute0: int, session) -> list[tuple[int, str, np.ndarray]]:
    """p_w : puissance de chaque minute à partir de la minute absolue minute0 (NaN = minute manquante).
    Renvoie (fin de fenêtre, message, énergies) pour chaque fenêtre complète."""
    T = len(p_w)
    valide = ~np.isnan(p_w)
    mod = (minute0 + np.arange(T)) % 1440
    heure = mod / 60.0
    X = np.vstack([np.nan_to_num(p_w) / 1000.0, np.sin(2 * np.pi * heure / 24), np.cos(2 * np.pi * heure / 24)])
    X = X.astype(np.float32)
    X[:, ~valide] = 0.0
    nom_in, nom_out = session.get_inputs()[0].name, session.get_outputs()[0].name
    res = []
    for fin in range(WIN, T + 1):
        if (minute0 + fin) % STEP != FIN_MOD15:
            continue
        y = session.run([nom_out], {nom_in: X[None, :, fin - WIN:fin]})[0][0]
        reg = np.maximum(y[:N_APP, SL], 0) * ECHELLES[:, None]
        on = y[N_APP:, SL] > 0
        wh = (reg * on).sum(axis=1) / 60.0
        total = np.nansum(np.where(valide[fin - WIN:fin][SL], p_w[fin - WIN:fin][SL], 0)) / 60.0
        e = np.floor(np.append(wh, total) + 0.5).astype(int)
        debut = (minute0 + fin - WIN + SL.start) % 1440
        res.append((minute0 + fin, f"{debut // 60:02d}{debut % 60:02d};" + ";".join(map(str, e)), e))
    return res


def ouvrir_modele():
    import onnxruntime as ort
    return ort.InferenceSession(str(EXPORT / META["modele"]), providers=["CPUExecutionProvider"])


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--ukdale", required=True, help="dossier UK-DALE de la maison (labels.dat, channel_N.dat)")
    a.add_argument("--jour", required=True, help="jour rejoué, AAAA-MM-JJ")
    a.add_argument("--heure", default="00:00", help="heure de départ du simulateur (défaut 00:00)")
    a.add_argument("--journal", help="sortie du simulateur avec les lignes « NILM ... » de la carte")
    a = a.parse_args()
    jour = dt.date.fromisoformat(a.jour)
    p = minutes_ukdale(Path(a.ukdale).expanduser(), jour)
    h, m = map(int, a.heure.split(":"))
    p = p[h * 60 + m:]
    attendus = messages_attendus(p, h * 60 + m, ouvrir_modele())
    print(f"{len(attendus)} messages attendus (premier après {WIN} minutes simulées)")
    carte = {}
    if a.journal:
        for l in Path(a.journal).read_text(errors="replace").splitlines():
            r = re.search(r"NILM (\d{4};[\d;]+)", l)
            if r:
                carte[r.group(1)[:4]] = r.group(1)
    ok = ecart = 0
    for _, msg, e in attendus:
        ligne = f"  attendu {msg:28s}"
        if carte:
            c = carte.get(msg[:4])
            if c is None:
                ligne += " carte : -"
            else:
                ec = np.abs(np.array(c.split(";")[1:], dtype=int) - e).max()
                ok += ec <= 1; ecart += ec > 1
                ligne += f" carte : {c:28s} {'OK' if ec <= 1 else f'écart {ec} Wh'}"
        print(ligne)
    if carte:
        print(f"\n{ok} messages identiques (à 1 Wh près), {ecart} différents, {len(attendus) - ok - ecart} absents du journal")


if __name__ == "__main__":
    main()
