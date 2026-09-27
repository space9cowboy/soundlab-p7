"""P7 - Suivi de derive Evidently, temoin reel Kaggle / ListenBrainz.

Reference : ecoutes Kaggle (titres communs ponderes par total_plays). Courant : ecoutes ListenBrainz (ponderees par lb_ecoutes).
Temoin exact : TVD genre = 0.1425 et TVD decennie = 0.0704 (AN4, 3v_42) sur les 29 315 titres communs.
Temoin Evidently : derive de la colonne genre detectee Kaggle -> ListenBrainz ; contre-temoin : deux tirages Kaggle,
aucune colonne en derive. La derive globale (part des colonnes) est rapportee sans servir de temoin.
Fenetres : TVD des parts de genre de chaque mois publiable (genre_mois, k = 11) face a la reference Kaggle.
Codes : 0 = temoins reproduits (l'alerte est dans rapport_derive.json) ; 1 = temoin non reproduit.
"""
import argparse, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

NUMERIQUES = ["danceability", "energy", "valence", "acousticness", "tempo", "anciennete"]


def genre_norm(g):
    return g if isinstance(g, str) and g.strip() and g.strip().lower() not in ("nan", "none", "null") else "(absent)"


def decennie(y):
    return "inconnue" if pd.isna(y) or y <= 0 else "%d0s" % (int(y) // 10)


def parts(poids, cles):
    s = pd.Series(poids.values, index=cles.values).groupby(level=0).sum()
    return s / s.sum()


def tvd(p, q):
    i = p.index.union(q.index)
    return 0.5 * float((p.reindex(i, fill_value=0) - q.reindex(i, fill_value=0)).abs().sum())


def tirage(A, poids, n, graine):
    r = np.random.default_rng(graine)
    idx = r.choice(len(A), size=n, replace=True, p=(poids / poids.sum()).values)
    return A.iloc[idx][["genre", "decennie"] + [c for c in NUMERIQUES if c in A.columns]].reset_index(drop=True)


def evidently(ref, cur, chemin):
    from evidently.report import Report
    from evidently.metric_preset import DataDriftPreset
    from evidently import ColumnMapping
    num = [c for c in NUMERIQUES if c in ref.columns]
    cm = ColumnMapping(numerical_features=num, categorical_features=["genre", "decennie"])
    # Methodes par defaut d'Evidently au-dela de 1 000 lignes : Jensen-Shannon (categorielles), Wasserstein normee
    # (numeriques), seuil 0,1. Le chi2 est ecarte : invalide sous 5 effectifs attendus (decennies rares, 27/09).
    rep = Report(metrics=[DataDriftPreset(cat_stattest="jensenshannon", num_stattest="wasserstein", stattest_threshold=0.1)])
    rep.run(reference_data=ref, current_data=cur, column_mapping=cm)
    rep.save_html(str(chemin))
    d = next(m["result"] for m in rep.as_dict()["metrics"] if m["metric"] == "DatasetDriftMetric")
    cols = next(m["result"]["drift_by_columns"] for m in rep.as_dict()["metrics"] if m["metric"] == "DataDriftTable")
    return {"derive": bool(d["dataset_drift"]), "colonnes_en_derive": int(d["number_of_drifted_columns"]),
            "colonnes": int(d["number_of_columns"]), "part": round(float(d["share_of_drifted_columns"]), 3),
            "par_colonne": {k: bool(v["drift_detected"]) for k, v in cols.items()}}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--kaggle", required=True)
    p.add_argument("--lb", required=True)
    p.add_argument("--sortie", required=True)
    p.add_argument("--genre-mois")
    p.add_argument("--communs-attendus", type=int)
    p.add_argument("--tvd-genre-attendue", type=float)
    p.add_argument("--tvd-decennie-attendue", type=float)
    p.add_argument("--n", type=int, default=20000)
    p.add_argument("--seuil-alerte-tvd", default="auto",
                   help="nombre, ou auto = P95 des TVD mensuelles des periodes de calibration (avant --debut-surveillance)")
    p.add_argument("--debut-surveillance", default="2016-01")
    p.add_argument("--injecter", action="store_true", help="ajoute une fenetre synthetique en derive (test de la chaine d'alerte)")
    a = p.parse_args(argv)
    out = Path(a.sortie); out.mkdir(parents=True, exist_ok=True)

    lab = pd.read_parquet(a.kaggle).drop_duplicates("track_id")
    lb = pd.read_parquet(a.lb)[["track_id", "lb_ecoutes"]]
    A = lab.merge(lb, on="track_id")
    A = A[A["is_hit"].notna() & A["lb_ecoutes"].notna()].reset_index(drop=True)
    A["genre"] = A["genre"].map(genre_norm)
    A["decennie"] = A["year"].map(decennie)
    ref_genre = parts(A["total_plays"], A["genre"])
    tg = round(tvd(ref_genre, parts(A["lb_ecoutes"], A["genre"])), 4)
    td = round(tvd(parts(A["total_plays"], A["decennie"]), parts(A["lb_ecoutes"], A["decennie"])), 4)
    ok = True
    for nom, v, att in (("communs", len(A), a.communs_attendus), ("tvd_genre", tg, a.tvd_genre_attendue),
                        ("tvd_decennie", td, a.tvd_decennie_attendue)):
        bon = att is None or v == att
        ok = ok and bon
        print("TEMOIN", nom, v, "ATTENDU", att, "OK" if bon else "ECHEC", flush=True)

    ref = tirage(A, A["total_plays"], a.n, 1)
    lbt = tirage(A, A["lb_ecoutes"], a.n, 2)
    ref2 = tirage(A, A["total_plays"], a.n, 3)
    r1 = evidently(ref, lbt, out / "derive_kaggle_vers_listenbrainz.html")
    r0 = evidently(ref, ref2, out / "contre_temoin_kaggle_kaggle.html")
    print("EVIDENTLY kaggle_vers_listenbrainz", json.dumps(r1), flush=True)
    print("EVIDENTLY contre_temoin", json.dumps(r0), flush=True)
    ev_ok = r1["par_colonne"]["genre"] and not any(r0["par_colonne"].values())
    ok = ok and ev_ok
    print("TEMOIN_EVIDENTLY genre_en_derive", r1["par_colonne"]["genre"], "contre_temoin_colonnes_en_derive",
          r0["colonnes_en_derive"], "OK" if ev_ok else "ECHEC", flush=True)

    rapport = {"tvd_genre": tg, "tvd_decennie": td, "evidently": r1, "contre_temoin": r0, "fenetres": []}
    alerte = False
    if a.genre_mois:
        gm = pd.read_parquet(a.genre_mois)
        gm = gm[gm["genre"] != "(hors_catalogue)"]
        for per, g in gm.groupby("periode"):
            if g["ecoutes"].sum() < 1000:
                continue
            rapport["fenetres"].append({"periode": per, "tvd_genre": round(tvd(ref_genre, parts(g["ecoutes"], g["genre"])), 4),
                                        "ecoutes": int(g["ecoutes"].sum())})
        if a.injecter:
            inj = ref_genre.copy() * 0.3
            inj[inj.idxmin()] += 0.7
            rapport["fenetres"].append({"periode": "9999-injection", "tvd_genre": round(tvd(ref_genre, inj / inj.sum()), 4), "ecoutes": 0})
        f = pd.DataFrame(rapport["fenetres"]).sort_values("periode")
        f.to_csv(out / "fenetres_tvd_genre.csv", index=False)
        calib = f[f["periode"] < a.debut_surveillance]["tvd_genre"]
        seuil = float(np.percentile(calib, 95)) if a.seuil_alerte_tvd == "auto" else float(a.seuil_alerte_tvd)
        surv = f[f["periode"] >= a.debut_surveillance]
        en_alerte = surv[surv["tvd_genre"] > seuil]
        derniere = f.iloc[-1]
        alerte = bool(derniere["tvd_genre"] > seuil)
        rapport.update(seuil_alerte=round(seuil, 4), fenetres_calibration=int(len(calib)), fenetres_surveillees=int(len(surv)),
                       fenetres_surveillees_en_alerte=int(len(en_alerte)))
        print("FENETRES", len(f), "calibration", len(calib), "seuil_P95", round(seuil, 4), "surveillees", len(surv),
              "surveillees_en_alerte", len(en_alerte), "derniere", derniere["periode"], "tvd_derniere", derniere["tvd_genre"],
              "ALERTE" if alerte else "sans_alerte", flush=True)
    rapport["alerte"] = alerte
    (out / "rapport_derive.json").write_text(json.dumps(rapport, indent=1))
    if not ok:
        print("DERIVE_TEMOIN_ECHEC", flush=True); return 1
    print("DERIVE_ALERTE" if alerte else "DERIVE_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
