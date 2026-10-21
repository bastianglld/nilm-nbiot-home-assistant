"""
EMS côté serveur (Energy Management System) – projet M1 ESET NILM / NB-IoT.

Regroupe les deux briques étudiées dans les notebooks :
  - semaine 8 : planning du lendemain selon le prix (règles simples) et message descendant de 32 caractères ;
  - semaine 9 : profils d'usage, habitudes des appareils, recommandations chiffrées et alertes.

Les deux briques partagent les mêmes données : l'historique des messages de 15 minutes envoyés par la carte
(énergie en Wh du frigo, de la bouilloire, du lave-linge, du lave-vaisselle selon le NILM, et total mesuré).
Les habitudes (semaine 9) fixent l'heure conseillée des machines dans le planning (semaine 8), et l'historique
fournit la prévision de consommation du lendemain.

Utilisation en ligne de commande :
    python ems_serveur.py enregistreur --historique messages.csv          (en continu : historique des messages de la carte)
    python ems_serveur.py planning  --historique messages.csv --offre Tempo [--publier]      (chaque jour vers 13 h 30)
    python ems_serveur.py analyse   --historique messages.csv --offre-actuelle Base [--publier]   (chaque semaine)

Dépendances : numpy, pandas ; paho-mqtt seulement pour publier sur le broker (sinon la commande mosquitto_pub est affichée).
"""
from __future__ import annotations

import argparse
import json
import math
import ssl
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

APPS = ["fridge", "kettle", "washing_machine", "dishwasher"]
NOMS = {"fridge": "frigo", "kettle": "bouilloire", "washing_machine": "lave-linge", "dishwasher": "lave-vaisselle"}


# ============================================================================ réglages
@dataclass
class Config:
    # tarifs EDF TTC au 1er août 2026, 6 kVA
    base: float = 0.2001
    hphc: dict = field(default_factory=lambda: {"HP": 0.2142, "HC": 0.1589})
    hc_hours: tuple = (22, 23, 0, 1, 2, 3, 4, 5)
    tempo: dict = field(default_factory=lambda: {"BLEU": (0.1356, 0.1654), "BLANC": (0.1536, 0.1921), "ROUGE": (0.1615, 0.7295)})
    abonnement: dict = field(default_factory=lambda: {"Base": 190.32, "HP/HC": 190.32, "Tempo": 189.60, "Dynamique": 190.32})
    dyn_hors_energie: float = 0.085          # €/kWh HT ajoutés au spot (hypothèse)
    tva: float = 1.20
    # chauffe-eau (cumulus) et batterie
    wh_cap: float = 7.0
    wh_p: float = 2.0
    wh_day: float = 5.0
    wh_loss: float = 0.01
    wh_min: float = 1.0
    puisage: dict = field(default_factory=lambda: {6: .10, 7: .20, 8: .10, 12: .05, 13: .05, 18: .10, 19: .15, 20: .10, 21: .10, 22: .05})
    batterie: bool = True
    bat_cap: float = 5.0
    bat_p: float = 2.5
    bat_eta: float = 0.95
    bat_soc_min: float = 0.5
    marge_regle_bat: float = 0.05
    # appareils décalables : forme d'un cycle (part de l'énergie par heure) et départs autorisés
    cycles: dict = field(default_factory=lambda: {"washing_machine": [0.8, 0.2], "dishwasher": [0.75, 0.25]})
    departs: tuple = tuple([22] + list(range(0, 22)))
    detection: dict = field(default_factory=lambda: {"washing_machine": (25, 2, 200), "dishwasher": (25, 2, 300), "kettle": (30, 0, 30)})
    # MQTT
    topic_plan: str = "maison/nilm_01/plan"
    topic_conseils: str = "maison/nilm_01/conseils"
    broker: str = "localhost"
    port: int = 1883
    prix_dir: Path = Path("prix")

    @property
    def draw(self):
        d = np.zeros(24)
        for h, w in self.puisage.items():
            d[h] = w * self.wh_day
        return d


# ============================================================================ prix
_SSL = ssl.create_default_context()
try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

CODES = {1: "BLEU", 2: "BLANC", 3: "ROUGE"}


def _json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "projet-M1-ESET-ems"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        return json.loads(r.read().decode("utf-8"))


def saison_tempo(jour: pd.Timestamp) -> str:
    a = jour.year if jour.month >= 9 else jour.year - 1
    return f"{a}-{a + 1}"


def couleurs_tempo(saison: str, cfg: Config) -> pd.Series:
    """Couleurs d'une saison Tempo (cache dans prix/tempo_<saison>.csv, sinon API api-couleur-tempo.fr)."""
    f = Path(cfg.prix_dir) / f"tempo_{saison}.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["date"]).set_index("date")["couleur"]
    js = _json(f"https://www.api-couleur-tempo.fr/api/joursTempo?periode={saison}")
    if isinstance(js, dict):
        js = next((v for v in js.values() if isinstance(v, list)), [js])
    s = pd.Series({pd.Timestamp(str(it["dateJour"])[:10]): CODES[int(it["codeJour"])] for it in js if int(it.get("codeJour", 0)) in CODES},
                  name="couleur").sort_index()
    Path(cfg.prix_dir).mkdir(exist_ok=True)
    s.rename_axis("date").to_frame().to_csv(f)
    return s


def couleur_du_jour(jour: pd.Timestamp, cfg: Config, cache: dict | None = None) -> str | None:
    """Couleur Tempo d'un jour : historique de la saison, ou API du jour / du lendemain pour les dates récentes.
    En déploiement, cette information peut aussi venir de la TIC du compteur Linky (champ PJOURF+1)."""
    jour = pd.Timestamp(jour).normalize()
    cache = {} if cache is None else cache
    s = saison_tempo(jour)
    try:
        if s not in cache:
            cache[s] = couleurs_tempo(s, cfg)
        if jour in cache[s].index:
            return cache[s][jour]
    except Exception:
        pass
    aujourd_hui = pd.Timestamp.today().normalize()
    for cle, d in (("today", aujourd_hui), ("tomorrow", aujourd_hui + pd.Timedelta(days=1))):
        if jour == d:
            try:
                js = _json(f"https://www.api-couleur-tempo.fr/api/jourTempo/{cle}")
                return CODES.get(int(js.get("codeJour", 0)))
            except Exception:
                return None
    return None


def spot_du_jour(jour: pd.Timestamp, cfg: Config) -> np.ndarray | None:
    """Prix spot France du jour (€/MWh, 24 valeurs) : fichiers spot_FR_*.csv de prix/, sinon API Energy-Charts."""
    jour = pd.Timestamp(jour).normalize()
    for f in sorted(Path(cfg.prix_dir).glob("spot_FR_*.csv")):
        s = pd.read_csv(f, parse_dates=["time"]).set_index("time")["eur_mwh"]
        s = s[~s.index.duplicated()]
        v = s.reindex(pd.date_range(jour, periods=24, freq="1h"))
        if v.notna().sum() >= 20:
            return v.interpolate(limit_direction="both").values
    try:
        js = _json(f"https://api.energy-charts.info/price?bzn=FR&start={jour.date()}&end={(jour + pd.Timedelta(days=1)).date()}")
        t = pd.to_datetime(js["unix_seconds"], unit="s", utc=True).tz_convert("Europe/Paris").tz_localize(None)
        v = pd.Series(js["price"], index=t, dtype=float).resample("1h").mean().reindex(pd.date_range(jour, periods=24, freq="1h"))
        return v.interpolate(limit_direction="both").values if v.notna().sum() >= 20 else None
    except Exception:
        return None


def prix_horaires(offre: str, jour: pd.Timestamp, cfg: Config, cache: dict | None = None) -> tuple[np.ndarray, str | None]:
    """24 prix (€/kWh TTC) pour l'offre choisie, et la couleur Tempo du jour (None hors Tempo)."""
    hc = np.isin(np.arange(24), cfg.hc_hours)
    if offre == "Base":
        return np.full(24, cfg.base), None
    if offre == "HP/HC":
        return np.where(hc, cfg.hphc["HC"], cfg.hphc["HP"]), None
    if offre == "Tempo":
        cj = couleur_du_jour(jour, cfg, cache)
        cv = couleur_du_jour(pd.Timestamp(jour) - pd.Timedelta(days=1), cfg, cache) or cj
        if cj is None:
            raise RuntimeError(f"couleur Tempo inconnue pour le {pd.Timestamp(jour).date()} (pas encore publiée ?)")
        p = np.array([cfg.tempo[cv][0] if h < 6 else (cfg.tempo[cj][0] if h >= 22 else cfg.tempo[cj][1]) for h in range(24)])
        return p, cj
    if offre == "Dynamique":
        s = spot_du_jour(jour, cfg)
        if s is None:
            raise RuntimeError(f"prix spot inconnu pour le {pd.Timestamp(jour).date()}")
        return cfg.tva * (s / 1000 + cfg.dyn_hors_energie), None
    raise ValueError(offre)


# ============================================================================ historique des messages
def charger_historique(path) -> pd.DataFrame:
    """Messages de 15 min : colonnes total + 4 appareils (Wh), index = début du quart d'heure (heure locale)."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[["total"] + APPS].sort_index(kind="stable")


def horaire_par_jour(hist: pd.DataFrame, col="total") -> pd.DataFrame:
    h = hist[col].groupby([hist.index.normalize(), hist.index.hour]).mean() * 4 / 1000   # kWh par heure
    H = h.unstack().reindex(columns=range(24))
    return H[H.notna().sum(axis=1) >= 20].interpolate(axis=1, limit_direction="both")


def prevision_lendemain(hist: pd.DataFrame, jour: pd.Timestamp) -> np.ndarray:
    """Moyenne heure par heure des 7 derniers jours complets avant `jour` (meilleure méthode en semaine 9)."""
    H = horaire_par_jour(hist.loc[: pd.Timestamp(jour) - pd.Timedelta(minutes=15)])
    return H.tail(7).mean().values if len(H) else np.full(24, 0.35)


# ============================================================================ habitudes (semaine 9)
def detecter_cycles(s: pd.Series, seuil_wh, trou, min_wh) -> pd.DataFrame:
    v = s.fillna(0).values; t = s.index; res = []; i = 0; n = len(v)
    while i < n:
        if v[i] <= seuil_wh:
            i += 1; continue
        j, fin = i, i
        while j < n and (v[j] > seuil_wh or (j - fin) <= trou):
            if v[j] > seuil_wh:
                fin = j
            j += 1
        e = v[i:fin + 1].sum()
        if e >= min_wh:
            res.append({"debut": t[i], "duree_min": 15 * (fin - i + 1), "energie_wh": e})
        i = fin + 1
    return pd.DataFrame(res, columns=["debut", "duree_min", "energie_wh"])


def habitudes(hist: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, dict]:
    semaines = max((hist.index[-1] - hist.index[0]).days / 7, 1e-9)
    cyc = {a: detecter_cycles(hist[a], *cfg.detection[a]) for a in cfg.detection}
    rows = []
    for a, c in cyc.items():
        h = c["debut"].dt.hour
        rows.append({"appareil": a, "cycles par semaine": len(c) / semaines,
                     "énergie d'un cycle (kWh)": c["energie_wh"].mean() / 1000 if len(c) else 0.0,
                     "heure habituelle": int(h.mode()[0]) if len(c) else None,
                     "part en heures pleines (%)": 100 * (~h.isin(cfg.hc_hours)).mean() if len(c) else 0.0,
                     "part le week-end (%)": 100 * (c["debut"].dt.dayofweek >= 5).mean() if len(c) else 0.0})
    return pd.DataFrame(rows).set_index("appareil"), cyc


def depart_conseille(p: np.ndarray, forme, cfg: Config) -> int:
    couts = {s: sum(f * p[s + j] for j, f in enumerate(forme)) for s in cfg.departs if s + len(forme) <= 24}
    return min(couts, key=couts.get)


# ============================================================================ planning (semaine 8, règles simples)
def executer_jour(autor, modes, conso, e0, s0, cfg: Config):
    """Ce que fait le boîtier avec les consignes : relais du chauffe-eau et mode de la batterie, heure par heure."""
    draw = cfg.draw; e, s = e0, s0
    G, H, E = np.zeros(24), np.zeros(24), np.zeros(24); inconfort = 0
    for t in range(24):
        e_pre = max(e * (1 - cfg.wh_loss) - draw[t], 0.0)
        H[t] = min(cfg.wh_p, max(0.0, cfg.wh_cap - e_pre)) if autor[t] else 0.0
        e = e_pre + H[t]
        inconfort += e < cfg.wh_min - 1e-3
        c = min(cfg.bat_p, max(0.0, (cfg.bat_cap - s) / cfg.bat_eta)) if (cfg.batterie and modes[t] == 1) else 0.0
        d = min(cfg.bat_p, max(0.0, (s - cfg.bat_soc_min) * cfg.bat_eta), conso[t] + H[t]) if (cfg.batterie and modes[t] == 2) else 0.0
        s += cfg.bat_eta * c - d / cfg.bat_eta
        G[t] = conso[t] + H[t] + c - d; E[t] = e
    return {"G": G, "H": H, "E": E, "e_fin": e, "s_fin": s, "inconfort": int(inconfort)}


def regle_chauffe_eau(p, e0, cfg: Config):
    autor = np.zeros(24, bool)
    for h in np.argsort(p, kind="stable"):
        if executer_jour(autor, np.zeros(24, int), np.zeros(24), e0, 0.0, cfg)["inconfort"] == 0:
            break
        autor[h] = True
    return autor


def regle_batterie(p, prevision, cfg: Config):
    modes = np.zeros(24, int)
    if not cfg.batterie:
        return modes
    n_ch = int(math.ceil((cfg.bat_cap - cfg.bat_soc_min) / cfg.bat_p))
    bas = np.argsort(p, kind="stable")[:n_ch]
    seuil = p[bas].max() * (1 + cfg.marge_regle_bat)
    stock = (cfg.bat_cap - cfg.bat_soc_min) * cfg.bat_eta
    for h in np.argsort(-p, kind="stable"):
        if stock <= 0 or p[h] * cfg.bat_eta ** 2 <= seuil or h in bas:
            break
        modes[h] = 2; stock -= min(cfg.bat_p, prevision[h])
    if (modes == 2).any():
        modes[bas] = 1
    return modes


CODE_COULEUR = {"BLEU": "B", "BLANC": "W", "ROUGE": "R"}


def encoder_plan(jour, autor, modes, depart_ll, depart_lv, couleur=None) -> str:
    relais = sum(1 << h for h in range(24) if autor[h])
    batt = sum(int(modes[h]) << (2 * h) for h in range(24))
    j = pd.Timestamp(jour)
    return f"{j.day:02d}{j.month:02d};{CODE_COULEUR.get(couleur, '-')};{relais:06X};{batt:012X};{depart_ll:02d};{depart_lv:02d}"


def decoder_plan(msg: str) -> dict:
    jjmm, c, relais, batt, ll, lv = msg.split(";")
    r, b = int(relais, 16), int(batt, 16)
    return {"jour": int(jjmm[:2]), "mois": int(jjmm[2:]), "couleur": c,
            "chauffe_eau": np.array([(r >> h) & 1 for h in range(24)], bool),
            "batterie": np.array([(b >> (2 * h)) & 3 for h in range(24)], int),
            "lave_linge": int(ll), "lave_vaisselle": int(lv)}


def planifier(jour, offre, prevision, e0, cfg: Config, cache=None, prix=None, couleur=None) -> dict:
    """Planning du lendemain : relais du chauffe-eau, batterie, départs conseillés, message de 32 caractères."""
    if prix is None:
        prix, couleur = prix_horaires(offre, jour, cfg, cache)
    autor = regle_chauffe_eau(prix, e0, cfg)
    modes = regle_batterie(prix, prevision, cfg)
    ll = depart_conseille(prix, cfg.cycles["washing_machine"], cfg)
    lv = depart_conseille(prix, cfg.cycles["dishwasher"], cfg)
    msg = encoder_plan(jour, autor, modes, ll, lv, couleur)
    assert len(msg) <= 50
    return {"jour": str(pd.Timestamp(jour).date()), "offre": offre, "couleur": couleur, "prix": prix,
            "chauffe_eau": autor, "batterie": modes, "lave_linge": ll, "lave_vaisselle": lv, "message": msg}


# ============================================================================ analyse (semaine 9)
def kmeans(X, k, n_init=10, iters=200, seed=0):
    rng = np.random.default_rng(seed); meilleur = None
    for _ in range(n_init):
        C = [X[rng.integers(len(X))]]
        for _ in range(1, k):
            d2 = np.min(((X[:, None, :] - np.array(C)[None]) ** 2).sum(-1), 1)
            C.append(X[rng.choice(len(X), p=d2 / d2.sum())])
        C = np.array(C)
        for _ in range(iters):
            lab = ((X[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
            C2 = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
            if np.allclose(C2, C):
                break
            C = C2
        inertie = ((X - C[lab]) ** 2).sum()
        if meilleur is None or inertie < meilleur[0]:
            meilleur = (inertie, C, lab)
    return meilleur[1], meilleur[2]


def silhouette(X, lab):
    D = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1)); s = []
    for i in range(len(X)):
        m = lab == lab[i]
        if m.sum() <= 1:
            s.append(0.0); continue
        a = D[i, m].sum() / (m.sum() - 1)
        b = min(D[i, lab == j].mean() for j in np.unique(lab) if j != lab[i])
        s.append((b - a) / max(a, b))
    return float(np.mean(s))


def profils_journees(hist: pd.DataFrame, k: int | None = None):
    H = horaire_par_jour(hist)
    F = H.div(H.sum(axis=1), axis=0).values
    if k is None:
        scores = {kk: silhouette(F, kmeans(F, kk)[1]) for kk in range(2, 7)}
        k = max(scores, key=scores.get)
    C, lab = kmeans(F, k)
    ordre = np.argsort([-(lab == j).sum() for j in range(k)])
    C = C[ordre]
    lab = ((F[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
    return C, pd.Series(lab, index=H.index), H


def cout_annuel(hist: pd.DataFrame, offre: str, cfg: Config, decalage_jours=0, cumulus_kwh=0.0, cache=None) -> float:
    """Coût de l'énergie de l'historique avec une offre, ramené à un an (sans abonnement).
    `decalage_jours` sert seulement à rejouer un historique ancien sur des prix récents (démonstration)."""
    H = horaire_par_jour(hist)
    ce = np.zeros(24)
    if cumulus_kwh:
        ce[22], ce[23], ce[0] = 0.4 * cumulus_kwh, 0.4 * cumulus_kwh, 0.2 * cumulus_kwh
    total = 0.0
    for d, row in H.iterrows():
        p, _ = prix_horaires(offre, d + pd.Timedelta(days=decalage_jours), cfg, cache)
        total += float(((row.values + ce) * p).sum())
    return total * 365 / len(H)


def analyse(hist: pd.DataFrame, offre_actuelle: str, cfg: Config, decalage_jours=0, cumulus_kwh=0.0, offres=("Base", "HP/HC", "Tempo")) -> dict:
    """Analyse hebdomadaire : carte d'identité, habitudes, profils, coût des offres, recommandations, alertes."""
    cache = {}
    jour = hist.index.normalize()
    J = hist.groupby(jour).sum(min_count=80) / 1000
    J = J.dropna(subset=["total"])
    nuit = hist["total"][(hist.index.hour >= 1) & (hist.index.hour < 5)] * 4
    talon = float(nuit.groupby(nuit.index.normalize()).min().median())
    hab, cyc = habitudes(hist, cfg)
    C, lab, H = profils_journees(hist)
    couts = {}
    for o in dict.fromkeys(list(offres) + [offre_actuelle]):
        try:
            couts[o] = cout_annuel(hist, o, cfg, decalage_jours, cumulus_kwh, cache) + cfg.abonnement[o]
        except RuntimeError as e:
            print(f"offre {o} non évaluée : {e}")
    if offre_actuelle not in couts:
        raise RuntimeError("impossible d'évaluer l'offre actuelle")
    meilleure = min(couts, key=couts.get)
    reco = []
    if couts[meilleure] < couts[offre_actuelle] - 20:
        reco.append({"type": "offre", "titre": f"Passer à l'offre {meilleure}",
                     "texte": f"Avec votre consommation, l'offre {meilleure} coûterait {couts[meilleure]:.0f} €/an contre "
                              f"{couts[offre_actuelle]:.0f} €/an avec votre offre actuelle ({offre_actuelle}).",
                     "gain_eur_an": couts[offre_actuelle] - couts[meilleure]})
    ref = meilleure if couts[meilleure] < couts[offre_actuelle] - 20 else offre_actuelle
    for a in cfg.cycles:
        r = hab.loc[a]
        if r["part en heures pleines (%)"] < 30 or ref == "Base":
            continue
        g = 0.0
        for _, c in cyc[a].iterrows():
            d = c["debut"].normalize()
            p, _ = prix_horaires(ref, d + pd.Timedelta(days=decalage_jours), cfg, cache)
            dep = depart_conseille(p, cfg.cycles[a], cfg)
            e = c["energie_wh"] / 1000
            h0 = c["debut"].hour
            cout_avant = sum(f * e * p[min(h0 + j, 23)] for j, f in enumerate(cfg.cycles[a]))
            cout_apres = sum(f * e * p[dep + j] for j, f in enumerate(cfg.cycles[a]))
            g += cout_avant - cout_apres
        g *= 365 / max(len(J), 1)
        reco.append({"type": "decalage", "titre": f"Lancer le {NOMS[a]} en heures creuses",
                     "texte": f"Vous lancez le {NOMS[a]} {r['cycles par semaine']:.1f} fois par semaine, le plus souvent vers {int(r['heure habituelle'])} h "
                              f"({r['part en heures pleines (%)']:.0f} % en heures pleines). Avec le départ conseillé dans le planning du jour : "
                              f"environ {g:.0f} €/an d'économie en {ref}.", "gain_eur_an": g})
    reco.append({"type": "veille", "titre": f"Veille : {talon:.0f} W en permanence",
                 "texte": f"Vos appareils en veille consomment environ {talon * 8.76:.0f} kWh par an ({talon * 8.76 * cfg.base:.0f} €). "
                          f"Chaque tranche de 10 W en moins fait gagner {10 * 8.76 * cfg.base:.0f} €/an.", "gain_eur_an": 10 * 8.76 * cfg.base})
    fr = J["fridge"]; ratio = fr / fr.rolling(28, min_periods=14).median().shift(1)
    hausse = (ratio > 1.3).astype(int)
    suite = hausse.groupby((hausse != hausse.shift()).cumsum()).transform("sum") * hausse
    if (suite >= 3).any():
        reco.append({"type": "alerte", "titre": "Frigo : consommation en hausse",
                     "texte": f"Le frigo consomme plus de 30 % au-dessus de son habitude depuis plusieurs jours (dernier : {ratio[suite >= 3].index.max().date()}).",
                     "gain_eur_an": 0.0})
    tot = H.sum(axis=1); m = tot.groupby(lab).transform("mean"); s = tot.groupby(lab).transform("std")
    anormaux = tot[(tot - m) > 3 * s]
    recents = anormaux[anormaux.index >= tot.index.max() - pd.Timedelta(days=7)]
    if len(recents):
        reco.append({"type": "alerte", "titre": "Journée inhabituelle",
                     "texte": "Consommation très au-dessus de votre profil habituel le " + ", ".join(str(d.date()) for d in recents.index) + ".",
                     "gain_eur_an": 0.0})
    reco = sorted(reco, key=lambda r: -r["gain_eur_an"])
    return {"identite": {"kWh par jour": float(J["total"].mean()), "veille (W)": talon,
                         **{f"part {NOMS[a]} (%)": float(100 * J[a].sum() / J["total"].sum()) for a in APPS}},
            "habitudes": hab, "cycles": cyc, "profils": C, "labels": lab, "couts_offres": couts, "offre_conseillee": meilleure,
            "anormaux": anormaux, "recommandations": reco}


# ============================================================================ fusion : notification du soir
def notification_du_soir(plan: dict, hab: pd.DataFrame, cfg: Config) -> str:
    """Message pour le téléphone, qui croise le planning de demain (semaine 8) et les habitudes du foyer (semaine 9)."""
    p = plan["prix"]; lignes = []
    titre = f"Demain {plan['jour']}" + (f", jour {plan['couleur'].lower()}" if plan["couleur"] else "")
    hp_cher = p.max() > 1.5 * p.min()
    for a, nom in (("washing_machine", "lave-linge"), ("dishwasher", "lave-vaisselle")):
        if a not in hab.index or hab.loc[a, "cycles par semaine"] < 0.5:
            continue
        h_hab, h_cons = int(hab.loc[a, "heure habituelle"]), plan[{"washing_machine": "lave_linge", "dishwasher": "lave_vaisselle"}[a]]
        forme = cfg.cycles[a]; e = hab.loc[a, "énergie d'un cycle (kWh)"]
        c_hab = sum(f * e * p[min(h_hab + j, 23)] for j, f in enumerate(forme))
        c_cons = sum(f * e * p[h_cons + j] for j, f in enumerate(forme))
        if c_hab - c_cons > 0.05:
            lignes.append(f"{nom} : vous le lancez souvent vers {h_hab} h ; à {h_cons} h le cycle coûtera {c_cons:.2f} € au lieu de {c_hab:.2f} €.")
    ch = [h for h in range(24) if plan["chauffe_eau"][h]]
    lignes.append(f"chauffe-eau : chauffe prévue à {', '.join(f'{h} h' for h in ch)}." if ch else "chauffe-eau : pas de chauffe nécessaire.")
    if (plan["batterie"] == 2).any():
        d = [h for h in range(24) if plan["batterie"][h] == 2]
        lignes.append(f"batterie : décharge de {d[0]} h à {d[-1] + 1} h, pendant les heures les plus chères.")
    if plan["couleur"] == "ROUGE":
        lignes.insert(0, f"Jour rouge : heures pleines à {p.max():.2f} €/kWh de 6 h à 22 h, évitez four, sèche-linge et radiateurs d'appoint.")
    elif not hp_cher:
        lignes.insert(0, "Prix stables demain : pas de précaution particulière.")
    return titre + "\n- " + "\n- ".join(lignes)


# ============================================================================ enregistrement des messages reçus
def decoder_mesures(payload: str, maintenant: pd.Timestamp) -> dict:
    """Message montant de la carte : 'hhmm;frigo;bouilloire;lave_linge;lave_vaisselle;total' (Wh du quart d'heure)."""
    hhmm, fr, ke, ll, lv, tot = payload.strip().split(";")
    t = maintenant.normalize() + pd.Timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[2:]))
    if t > maintenant:                                        # quart d'heure de la veille (retard d'environ 2 h)
        t -= pd.Timedelta(days=1)
    return {"time": t, "total": float(tot), "fridge": float(fr), "kettle": float(ke), "washing_machine": float(ll), "dishwasher": float(lv)}


def enregistreur(csv_path: str, cfg: Config, topic="maison/nilm_01/q"):
    """Abonné MQTT qui ajoute chaque message de la carte à l'historique CSV utilisé par le planning et l'analyse."""
    import paho.mqtt.client as mqtt
    path = Path(csv_path)
    if not path.exists():
        path.write_text("time,total," + ",".join(APPS) + "\n")

    def on_message(client, userdata, msg):
        try:
            r = decoder_mesures(msg.payload.decode(), pd.Timestamp.now())
            with path.open("a") as f:
                f.write(f"{r['time']},{r['total']},{r['fridge']},{r['kettle']},{r['washing_machine']},{r['dishwasher']}\n")
        except Exception as e:
            print("message ignoré :", msg.payload, e)
    client = mqtt.Client()
    client.on_message = on_message
    client.connect(cfg.broker, cfg.port)
    client.subscribe(topic, qos=1)
    client.loop_forever()


# ============================================================================ publication MQTT
def publier(topic: str, payload: str, cfg: Config, retain=True):
    try:
        import paho.mqtt.publish as publish
        publish.single(topic, payload, qos=1, retain=retain, hostname=cfg.broker, port=cfg.port)
        print(f"publié sur {topic} ({len(payload)} caractères)")
    except ImportError:
        print(f"paho-mqtt absent ; commande équivalente :\nmosquitto_pub -h {cfg.broker} -p {cfg.port} -t {topic} {'-r ' if retain else ''}-q 1 -m '{payload}'")


# ============================================================================ ligne de commande
def main():
    ap = argparse.ArgumentParser(description="EMS côté serveur : planning du lendemain et analyse des profils d'usage")
    ap.add_argument("action", choices=["planning", "analyse", "enregistreur"])
    ap.add_argument("--historique", required=True, help="CSV des messages de 15 min (total + 4 appareils, Wh)")
    ap.add_argument("--offre", default="Tempo", choices=["Base", "HP/HC", "Tempo", "Dynamique"])
    ap.add_argument("--offre-actuelle", default="Base", choices=["Base", "HP/HC", "Tempo"])
    ap.add_argument("--jour", default=None, help="jour à planifier (AAAA-MM-JJ), par défaut demain")
    ap.add_argument("--stock-cuve", type=float, default=None, help="énergie estimée dans la cuve à minuit (kWh)")
    ap.add_argument("--cumulus", type=float, default=0.0, help="kWh/jour d'un cumulus à ajouter (s'il n'est pas déjà dans les mesures)")
    ap.add_argument("--decalage-jours", type=int, default=0, help="démonstration seulement : rejouer un historique ancien sur des prix récents")
    ap.add_argument("--publier", action="store_true")
    ap.add_argument("--broker", default="localhost")
    a = ap.parse_args()
    cfg = Config(broker=a.broker)
    if a.action == "enregistreur":
        return enregistreur(a.historique, cfg)
    hist = charger_historique(a.historique)
    if a.action == "planning":
        jour = pd.Timestamp(a.jour) if a.jour else pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
        plan = planifier(jour, a.offre, prevision_lendemain(hist, jour), a.stock_cuve or 0.6 * cfg.wh_cap, cfg)
        print(f"{plan['jour']} ({a.offre}{', ' + plan['couleur'].lower() if plan['couleur'] else ''}) -> {plan['message']}")
        print(notification_du_soir(plan, habitudes(hist, cfg)[0], cfg))
        if a.publier:
            publier(cfg.topic_plan, plan["message"], cfg)
    else:
        res = analyse(hist, a.offre_actuelle, cfg, decalage_jours=a.decalage_jours, cumulus_kwh=a.cumulus)
        for r in res["recommandations"]:
            print(f"• {r['titre']}\n  {r['texte']}")
        if a.publier:
            publier(cfg.topic_conseils, json.dumps(res["recommandations"], ensure_ascii=False), cfg)


if __name__ == "__main__":
    main()
