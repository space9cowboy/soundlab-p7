import json, os, subprocess, sys
import numpy as np, pandas as pd, pytest
from fastapi.testclient import TestClient

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from soundlab_p7.modele import VARIABLES, decider_promotion
from train import entrainer
import api.main as api


def donnees(n=900, graine=0, melanger=False):
    r = np.random.default_rng(graine)
    df = pd.DataFrame({v: r.normal(size=n) for v in VARIABLES})
    df["artist"] = ["A%03d" % (i % 90) for i in range(n)]
    force = df.groupby("artist")["artist_taux_hits_hors_piste"].transform("mean")
    df["is_hit"] = ((df["artist_taux_hits_hors_piste"] + 2 * force + r.normal(scale=.8, size=n)) > 1).astype(int)
    if melanger:
        df["is_hit"] = r.permutation(df["is_hit"].values)
    df.loc[r.random(n) < .1, "anciennete"] = np.nan
    df["track_id"] = ["T%05d" % i for i in range(n)]
    df["name"] = ["Titre %d" % i for i in range(n)]
    df["genre"] = [None if i % 4 == 0 else ["Rock", "Pop", "Jazz"][i % 3] for i in range(n)]
    df["year"] = [1960 + i % 55 for i in range(n)]
    return df


@pytest.fixture(scope="module")
def dossier(tmp_path_factory):
    d = tmp_path_factory.mktemp("p7")
    donnees().to_parquet(d / "features.parquet")
    donnees(melanger=True).to_parquet(d / "features_degradees.parquet")
    return d


def test_porte_promotion_regle():
    assert decider_promotion(0.78, None, 0.005)[0]
    assert decider_promotion(0.786, 0.79, 0.005)[0]
    assert not decider_promotion(0.784, 0.79, 0.005)[0]


def test_entrainement_temoin(dossier, capsys):
    assert entrainer.main(["--features", str(dossier / "features.parquet"), "--sortie", str(dossier / "a0"), "--n-jobs", "2"]) == 0
    auc = json.loads((dossier / "a0" / "meta.json").read_text())["auc_cv"]
    assert auc > 0.7
    assert entrainer.main(["--features", str(dossier / "features.parquet"), "--sortie", str(dossier / "a1"), "--n-jobs", "2",
                           "--auc-temoin", str(auc)]) == 0
    assert entrainer.main(["--features", str(dossier / "features.parquet"), "--sortie", str(dossier / "a2"), "--n-jobs", "2",
                           "--auc-temoin", str(auc + 0.02)]) == 1
    assert not (dossier / "a2" / "modele.joblib").exists()


def test_mlflow_promotion(dossier):
    uri = "sqlite:///" + str(dossier / "mlflow.db")
    os.environ["MLFLOW_TRACKING_URI"] = uri
    base = ["--mlflow-uri", uri, "--n-jobs", "2"]
    assert entrainer.main(["--features", str(dossier / "features.parquet"), "--sortie", str(dossier / "m1")] + base) == 0
    assert entrainer.main(["--features", str(dossier / "features_degradees.parquet"), "--sortie", str(dossier / "m2")] + base) == 3
    from mlflow import MlflowClient
    assert str(MlflowClient(uri).get_model_version_by_alias("soundlab-hit", "champion").version) == "1"
    assert entrainer.main(["--features", str(dossier / "features.parquet"), "--sortie", str(dossier / "m3")] + base) == 0
    assert str(MlflowClient(uri).get_model_version_by_alias("soundlab-hit", "champion").version) == "3"
    api.charger("models:/soundlab-hit@champion")
    assert api.ETAT["meta"]["version"] == 3 and api.ETAT["modele"] is not None
    assert api.verifier_champion() is False
    MlflowClient(uri).set_registered_model_alias("soundlab-hit", "champion", "1")
    assert api.verifier_champion() is True and api.ETAT["meta"]["version"] == 1
    MlflowClient(uri).set_registered_model_alias("soundlab-hit", "champion", "3")


@pytest.fixture()
def client(dossier):
    os.environ["SERVIR_MODELE"] = "1"
    api.charger(str(dossier / "a0"))
    return TestClient(api.app)


def test_api_sante_version(client):
    assert client.get("/health").json() == {"statut": "ok"}
    v = client.get("/model-version").json()
    assert v["modele_charge"] and v["auc_cv"] > 0.7 and "artiste" in v["validation"]


def test_api_score_et_predict_coherents(client, dossier):
    df = donnees()
    r = client.get("/score/T00007").json()
    x = df.loc[df.track_id == "T00007", VARIABLES].iloc[0]
    corps = {k: (None if pd.isna(v) else float(v)) for k, v in x.items()}
    p = client.post("/predict", json=corps).json()
    assert abs(p["score"] - r["score"]) < 1e-3
    assert client.get("/score/INCONNU").status_code == 404


def test_api_refuse_identifiant_personne(client):
    corps = {v: 0.1 for v in VARIABLES}
    assert client.post("/predict", json=corps).status_code == 200
    for champ in ("user_id", "listener", "user_name"):
        assert client.post("/predict", json={**corps, champ: "x"}).status_code == 422


def test_api_titres_filtres(client):
    t = client.get("/titres", params={"genre": "Rock", "decennie": 1970, "limite": 500})
    assert t.status_code == 422
    t = client.get("/titres", params={"genre": "Rock", "decennie": 1970, "limite": 20}).json()
    assert 0 < t["total"] <= 20
    assert all(x["genre"] == "Rock" and 1970 <= x["year"] < 1980 for x in t["titres"])
    s = [x["score"] for x in t["titres"]]
    assert s == sorted(s, reverse=True)


def test_api_mode_scores_seuls(dossier):
    os.environ["SERVIR_MODELE"] = "0"
    api.charger(str(dossier / "a0"))
    c = TestClient(api.app)
    assert c.post("/predict", json={v: 0.1 for v in VARIABLES}).status_code == 503
    assert c.get("/score/T00001").status_code == 200
    os.environ["SERVIR_MODELE"] = "1"


def test_tendances_refusees_si_colonne_auditeurs(dossier):
    d = dossier / "a0"
    pd.DataFrame({"genre": ["Rock"], "periode": ["2010"], "ecoutes": [100], "auditeurs": [12]}).to_parquet(d / "tendances.parquet")
    with pytest.raises(ValueError):
        api.charger(str(d))
    pd.DataFrame({"genre": ["Rock"], "periode": ["2010"], "ecoutes": [100]}).to_parquet(d / "tendances.parquet")
    api.charger(str(d))
    assert TestClient(api.app).get("/tendances", params={"genre": "Rock"}).json()["points"][0]["ecoutes"] == 100
    os.remove(d / "tendances.parquet")


def test_tendances_publiees_et_n_jobs(dossier):
    os.environ["TENDANCES_CHEMIN"] = os.path.join(RACINE, "deploy", "tendances", "tendances.parquet")
    api.charger(str(dossier / "a0"))
    t = pd.read_parquet(os.environ["TENDANCES_CHEMIN"])
    assert sorted(t.columns) == ["ecoutes", "genre", "periode"] and len(t) == 2288 and t.genre.nunique() == 16
    r = TestClient(api.app).get("/tendances", params={"genre": "rock"}).json()["points"]
    assert len(r) == len(t[t.genre == "rock"]) and all(p["ecoutes"] > 0 for p in r)
    tout = TestClient(api.app).get("/tendances").json()["points"]
    assert len(tout) == t.periode.nunique() and sum(p["ecoutes"] for p in tout) == int(t.ecoutes.sum())
    assert api.ETAT["modele"].n_jobs == 1
    del os.environ["TENDANCES_CHEMIN"]


def test_cors_tolere_barre_oblique():
    import importlib
    os.environ["CORS_ORIGINES"] = " https://exemple.vercel.app/ ,"
    m = importlib.reload(api)
    try:
        assert m.origines == ["https://exemple.vercel.app"]
    finally:
        os.environ.pop("CORS_ORIGINES")
        importlib.reload(api)
