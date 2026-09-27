"""P7 - Reentrainement du modele SoundLab, temoin du Bloc 6, suivi MLflow et porte de promotion.

Usage :
  python -m train.entrainer --features DIR_OU_S3 --sortie artefacts/ [--auc-temoin 0.7875 --tolerance-temoin 0.005]
         [--mlflow-uri URI --nom-modele soundlab-hit --tolerance-promotion 0.005]
Codes de sortie : 0 reussi ; 1 temoin non reproduit ; 3 promotion refusee (artefact produit, champion inchange).
"""
import argparse, hashlib, json, os, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from soundlab_p7.modele import (VARIABLES, GRAINE, N_PLIS, construire_foret, decider_promotion, evaluer_cv,
                                matrice_sentinelle)

META_TITRES = ["track_id", "name", "artist", "genre", "year"]


def charger(source):
    if source.startswith("s3://"):
        import boto3
        b, _, pre = source[5:].rstrip("/").partition("/")
        s3 = boto3.client("s3"); tmp = Path(tempfile.mkdtemp(prefix="p7_features_")); n = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=pre + "/"):
            for o in page.get("Contents", []):
                if o["Key"].endswith(".parquet"):
                    s3.download_file(b, o["Key"], str(tmp / Path(o["Key"]).name)); n += 1
        if n == 0:
            raise FileNotFoundError(source)
        source = str(tmp)
    return pd.read_parquet(source)


def empreinte(df):
    h = pd.util.hash_pandas_object(df.sort_values("track_id").reset_index(drop=True), index=False).values
    return hashlib.sha256(h.tobytes()).hexdigest()[:16]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--features", required=True)
    p.add_argument("--sortie", required=True)
    p.add_argument("--auc-temoin", type=float)
    p.add_argument("--tolerance-temoin", type=float, default=0.005)
    p.add_argument("--mlflow-uri")
    p.add_argument("--experience", default="soundlab-p7")
    p.add_argument("--nom-modele", default="soundlab-hit")
    p.add_argument("--tolerance-promotion", type=float, default=0.005)
    p.add_argument("--n-jobs", type=int, default=-1)
    p.add_argument("--code-refus", type=int, default=3, help="code de sortie si la promotion est refusee")
    a = p.parse_args(argv)
    t0 = time.time()

    df = charger(a.features)
    manquantes = [c for c in VARIABLES + ["is_hit", "artist", "track_id"] if c not in df.columns]
    if manquantes:
        print("COLONNES_MANQUANTES", manquantes, flush=True); return 1
    y, groupes = df["is_hit"].astype(int), df["artist"]
    X = matrice_sentinelle(df)
    emp = empreinte(df[["track_id"] + VARIABLES + ["is_hit"]])
    print("DONNEES titres", len(df), "artistes", groupes.nunique(), "part_hits_%", round(100 * y.mean(), 2),
          "colonnes", X.shape[1], "empreinte", emp, flush=True)

    fab = lambda: construire_foret(a.n_jobs)
    cv = evaluer_cv(X, y, groupes, fab)
    print("CV", json.dumps(cv), flush=True)
    temoin_ok = True
    if a.auc_temoin is not None:
        temoin_ok = abs(cv["auc_moyen"] - a.auc_temoin) <= a.tolerance_temoin
        print("TEMOIN auc", cv["auc_moyen"], "attendu", a.auc_temoin, "tolerance", a.tolerance_temoin,
              "OK" if temoin_ok else "ECHEC", flush=True)
        if not temoin_ok:
            return 1

    m = fab(); m.fit(X, y)
    sortie = Path(a.sortie); sortie.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {"nom": a.nom_modele, "date_entrainement": date, "auc_cv": cv["auc_moyen"], "auc_ecart_type": cv["auc_ecart_type"],
            "seuil_recommande": cv["seuil_moyen"], "precision_au_rappel_075": cv["precision_au_rappel_075"],
            "validation": "GroupKFold %d plis, groupes = artiste" % N_PLIS, "variables": list(X.columns),
            "variables_sources": VARIABLES, "graine": GRAINE, "titres": int(len(df)), "empreinte_donnees": emp,
            "sklearn": sklearn.__version__, "version": None}
    joblib.dump({"modele": m, "variables": list(X.columns), "seuil_recommande": cv["seuil_moyen"]},
                sortie / "modele.joblib", compress=3)
    sc = df[[c for c in META_TITRES if c in df.columns]].copy()
    sc["score"] = np.round(m.predict_proba(X)[:, 1], 4)
    sc.to_parquet(sortie / "scores.parquet", index=False)
    print("ARTEFACT modele_mo", round((sortie / "modele.joblib").stat().st_size / 1e6, 1), "scores", len(sc), flush=True)

    code = 0
    if a.mlflow_uri:
        import mlflow
        from mlflow import MlflowClient
        mlflow.set_tracking_uri(a.mlflow_uri); mlflow.set_experiment(a.experience)
        cl = MlflowClient()
        try:
            champ = cl.get_model_version_by_alias(a.nom_modele, "champion")
            auc_champ = float(cl.get_run(champ.run_id).data.metrics["auc_cv"])
        except Exception:
            champ, auc_champ = None, None
        promu, raison = decider_promotion(cv["auc_moyen"], auc_champ, a.tolerance_promotion)
        with mlflow.start_run(run_name="reentrainement_" + date) as run:
            mlflow.log_params({"algorithme": "foret_aleatoire", "n_estimators": 300, "min_samples_leaf": 5,
                               "class_weight": "balanced_subsample", "graine": GRAINE, "variables": len(VARIABLES),
                               "validation": meta["validation"], "empreinte_donnees": emp})
            mlflow.log_metrics({"auc_cv": cv["auc_moyen"], "auc_ecart_type": cv["auc_ecart_type"],
                                "precision_au_rappel_075": cv["precision_au_rappel_075"], "seuil": cv["seuil_moyen"]})
            mlflow.set_tags({"promotion": "acceptee" if promu else "refusee", "raison_promotion": raison})
            with open(sortie / "meta.json", "w") as f:
                json.dump(meta, f, indent=1)
            mlflow.log_artifacts(str(sortie), artifact_path="artefact")
            mv = mlflow.register_model("runs:/%s/artefact" % run.info.run_id, a.nom_modele)
        meta["version"] = int(mv.version)
        if promu:
            cl.set_registered_model_alias(a.nom_modele, "champion", mv.version)
        print("PROMOTION", "ACCEPTEE" if promu else "REFUSEE", "version", mv.version, "raison", raison, flush=True)
        code = 0 if promu else a.code_refus
    with open(sortie / "meta.json", "w") as f:
        json.dump(meta, f, indent=1)
    print("ENTRAINEMENT_OK" if code == 0 else "ENTRAINEMENT_NON_PROMU", "duree_s", round(time.time() - t0, 1), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
