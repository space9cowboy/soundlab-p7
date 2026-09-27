"""Extrait du registre MLflow les scores et metadonnees du champion pour l'image Render (sans le modele)."""
import json, shutil
import mlflow
from mlflow import MlflowClient

p = mlflow.artifacts.download_artifacts(artifact_uri="models:/soundlab-hit@champion")
v = int(MlflowClient().get_model_version_by_alias("soundlab-hit", "champion").version)
meta = json.load(open(p + "/meta.json"))
meta["version"] = v
json.dump(meta, open("/sortie/meta.json", "w"), indent=1)
shutil.copy(p + "/scores.parquet", "/sortie/scores.parquet")
print("EXTRAIT version", v, "auc_cv", meta["auc_cv"], "titres", meta["titres"], "empreinte", meta["empreinte_donnees"])
