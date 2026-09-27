"""API SoundLab : un score par titre, jamais par personne.

MODELE_URI : dossier local d'artefact (modele.joblib, scores.parquet, meta.json) ou models:/<nom>@<alias> (MLflow).
Sans modele.joblib (offre gratuite a 512 Mo), l'API sert les scores precalcules et /predict repond 503.
"""
import json, os, time
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from soundlab_p7.modele import VARIABLES, preparer

COLONNES_TENDANCES = {"genre", "periode", "ecoutes"}
ETAT = {"modele": None, "variables": None, "seuil": None, "scores": None, "meta": {}, "source": None,
        "tendances": None, "t_chargement": None}


def resoudre(uri):
    if uri.startswith("models:/"):
        import mlflow
        from mlflow import MlflowClient
        chemin = mlflow.artifacts.download_artifacts(artifact_uri=uri)
        nom, _, alias = uri[len("models:/"):].partition("@")
        version = MlflowClient().get_model_version_by_alias(nom, alias).version if alias else None
        return Path(chemin), version
    return Path(uri), None


def charger(uri=None):
    uri = uri or os.environ.get("MODELE_URI", "artefacts")
    d, version = resoudre(uri)
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
    if version is not None:
        meta["version"] = int(version)
    ETAT.update(meta=meta, source=uri, t_chargement=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    ETAT["scores"] = pd.read_parquet(d / "scores.parquet").set_index("track_id") if (d / "scores.parquet").exists() else None
    ETAT["tendances"] = None
    ft = Path(os.environ["TENDANCES_CHEMIN"]) if os.environ.get("TENDANCES_CHEMIN") else d / "tendances.parquet"
    if ft.exists():
        t = pd.read_parquet(ft)
        if set(t.columns) != COLONNES_TENDANCES:
            raise ValueError("tendances.parquet refuse : colonnes %s, attendu %s" % (sorted(t.columns), sorted(COLONNES_TENDANCES)))
        ETAT["tendances"] = t
    if (d / "modele.joblib").exists() and os.environ.get("SERVIR_MODELE", "1") == "1":
        import joblib
        a = joblib.load(d / "modele.joblib")
        if hasattr(a["modele"], "n_jobs"):
            a["modele"].n_jobs = int(os.environ.get("N_JOBS_PREDICTION", "1"))
        ETAT.update(modele=a["modele"], variables=a["variables"], seuil=a["seuil_recommande"])
    else:
        ETAT.update(modele=None, variables=None, seuil=meta.get("seuil_recommande"))


app = FastAPI(title="SoundLab API", version="1.0")
origines = [o for o in os.environ.get("CORS_ORIGINES", "http://localhost:3000").split(",") if o]
app.add_middleware(CORSMiddleware, allow_origins=origines, allow_methods=["GET", "POST"], allow_headers=["content-type"])


def verifier_champion():
    """Recharge l'artefact si l'alias du registre pointe vers une autre version. Renvoie True si recharge."""
    uri = ETAT["source"] or ""
    if not uri.startswith("models:/") or "@" not in uri:
        return False
    from mlflow import MlflowClient
    nom, _, alias = uri[len("models:/"):].partition("@")
    v = int(MlflowClient().get_model_version_by_alias(nom, alias).version)
    if v != ETAT["meta"].get("version"):
        charger(uri)
        return True
    return False


def boucle_rechargement(periode):
    import threading
    def tourner():
        while True:
            time.sleep(periode)
            try:
                if verifier_champion():
                    print("RECHARGE version", ETAT["meta"].get("version"), flush=True)
            except Exception as err:
                print("RECHARGEMENT_ECHEC", type(err).__name__, flush=True)
    threading.Thread(target=tourner, daemon=True).start()


@app.on_event("startup")
def demarrage():
    if ETAT["meta"] == {} and ETAT["scores"] is None:
        charger()
    periode = int(os.environ.get("RECHARGEMENT_S", "0"))
    if periode > 0:
        boucle_rechargement(periode)


def version():
    m = ETAT["meta"]
    return {"nom": m.get("nom"), "version": m.get("version"), "date_entrainement": m.get("date_entrainement"),
            "auc_cv": m.get("auc_cv"), "auc_ecart_type": m.get("auc_ecart_type"), "validation": m.get("validation"),
            "seuil_recommande": m.get("seuil_recommande"), "modele_charge": ETAT["modele"] is not None}


@app.get("/health")
def sante():
    ok = ETAT["scores"] is not None or ETAT["modele"] is not None
    if not ok:
        raise HTTPException(503, "aucun artefact charge")
    return {"statut": "ok"}


@app.get("/model-version")
def model_version():
    return version()


class Caracteristiques(BaseModel):
    model_config = ConfigDict(extra="forbid")
    danceability: Optional[float] = None
    energy: Optional[float] = None
    key: Optional[float] = None
    loudness: Optional[float] = None
    mode: Optional[float] = None
    speechiness: Optional[float] = None
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None
    liveness: Optional[float] = None
    valence: Optional[float] = None
    tempo: Optional[float] = None
    time_signature: Optional[float] = None
    duration_ms: Optional[float] = None
    anciennete: Optional[float] = None
    duration_min: Optional[float] = None
    artist_nb_titres_hors_piste: Optional[float] = None
    artist_plays_moyen_hors_piste: Optional[float] = None
    artist_taux_hits_hors_piste: Optional[float] = None


assert list(Caracteristiques.model_fields) == VARIABLES


@app.post("/predict")
def predire(c: Caracteristiques):
    if ETAT["modele"] is None:
        raise HTTPException(503, "prediction a la volee indisponible sur cette instance ; utiliser /score")
    X = preparer(pd.DataFrame([c.model_dump()], dtype=float), ETAT["variables"])
    s = float(ETAT["modele"].predict_proba(X)[:, 1][0])
    return {"score": round(s, 4), "seuil": ETAT["seuil"], "prioritaire": s >= ETAT["seuil"],
            "version": ETAT["meta"].get("version")}


def ligne(tid, r):
    d = {"track_id": tid, "score": float(r["score"])}
    for c in ("name", "artist", "genre", "year"):
        if c in r.index and pd.notna(r[c]):
            d[c] = r[c].item() if hasattr(r[c], "item") else r[c]
    return d


@app.get("/score/{track_id}")
def score(track_id: str):
    sc = ETAT["scores"]
    if sc is None or track_id not in sc.index:
        raise HTTPException(404, "titre inconnu")
    return {**ligne(track_id, sc.loc[track_id]), "seuil": ETAT["seuil"], "version": ETAT["meta"].get("version")}


@app.get("/titres")
def titres(genre: Optional[str] = None, decennie: Optional[int] = Query(None, ge=1900, le=2030),
           artiste: Optional[str] = Query(None, max_length=100), limite: int = Query(50, ge=1, le=200)):
    sc = ETAT["scores"]
    if sc is None:
        raise HTTPException(503, "scores indisponibles")
    f = sc
    if genre:
        f = f[f["genre"].fillna("(absent)") == genre] if "genre" in f else f.iloc[0:0]
    if decennie is not None and "year" in f:
        f = f[(f["year"] // 10 * 10) == decennie]
    if artiste:
        f = f[f["artist"].str.contains(artiste, case=False, regex=False, na=False)]
    f = f.sort_values("score", ascending=False).head(limite)
    return {"total": int(len(f)), "seuil": ETAT["seuil"], "version": ETAT["meta"].get("version"),
            "titres": [ligne(t, r) for t, r in f.iterrows()]}


@app.get("/genres")
def genres():
    sc = ETAT["scores"]
    if sc is None or "genre" not in sc:
        return {"genres": []}
    g = sc["genre"].fillna("(absent)").value_counts()
    return {"genres": [{"genre": k, "titres": int(v)} for k, v in g.items()]}


@app.get("/tendances")
def tendances(genre: Optional[str] = None):
    t = ETAT["tendances"]
    if t is None:
        raise HTTPException(503, "tendances indisponibles")
    if genre:
        t = t[t["genre"] == genre][["periode", "ecoutes"]]
    else:
        t = t.groupby("periode", as_index=False)["ecoutes"].sum()
    return {"genre": genre, "points": [{"periode": p, "ecoutes": int(e)} for p, e in t.sort_values("periode").itertuples(index=False)]}
