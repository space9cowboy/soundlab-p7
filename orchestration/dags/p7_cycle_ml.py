"""P7 - Cycle ML SoundLab : derive -> (alerte + reentrainement + promotion) -> verification de l'API.

Chaque etape tourne dans son image (DockerOperator). Le redeploiement est implicite : l'API recharge l'alias
champion du registre MLflow toutes les RECHARGEMENT_S secondes, sans reconstruction ni redemarrage.
Parametre injecter_derive : ajoute une fenetre synthetique en derive pour tester la chaine d'alerte.
"""
import json, os, time, urllib.request
from datetime import datetime

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

HOTE = os.environ["HOTE_P7"]
RESEAU = os.environ.get("RESEAU_P7", "soundlab-p7_default")
DONNEES = "/opt/airflow/p7data"
MLFLOW = "http://mlflow:5000"
COMMUN = dict(network_mode=RESEAU, auto_remove="success", mount_tmp_dir=False, docker_url="unix://var/run/docker.sock",
              mounts=[Mount(source=HOTE + "/data", target="/donnees", type="bind")])


def brancher(**ctx):
    r = json.load(open(DONNEES + "/derive/%s/rapport_derive.json" % ctx["ds"]))
    print("TVD_genre", r["tvd_genre"], "seuil", r.get("seuil_alerte"), "alerte", r["alerte"])
    return ["alerter", "reentrainer"] if r["alerte"] else ["sans_derive"]


def alerter(**ctx):
    r = json.load(open(DONNEES + "/derive/%s/rapport_derive.json" % ctx["ds"]))
    msg = "SoundLab P7 : derive detectee le %s, TVD genre derniere fenetre %.4f > seuil %.4f ; reentrainement lance." % (
        ctx["ds"], r["fenetres"][-1]["tvd_genre"] if r["fenetres"] else r["tvd_genre"], r.get("seuil_alerte") or 0)
    os.makedirs(DONNEES + "/alertes", exist_ok=True)
    with open(DONNEES + "/alertes/%s.json" % ctx["ds"], "w") as f:
        json.dump({"date": ctx["ds"], "message": msg}, f)
    arn = os.environ.get("SNS_TOPIC_ARN")
    if arn:
        import boto3
        boto3.client("sns").publish(TopicArn=arn, Subject="SoundLab P7 - derive", Message=msg)
    print("ALERTE", msg, "SNS" if arn else "fichier seulement")


def verifier_api(**_):
    req = urllib.request.Request(MLFLOW + "/api/2.0/mlflow/registered-models/alias?name=soundlab-hit&alias=champion")
    champion = int(json.load(urllib.request.urlopen(req, timeout=10))["model_version"]["version"])
    for _ in range(12):
        v = json.load(urllib.request.urlopen("http://api:8000/model-version", timeout=10)).get("version")
        if v == champion:
            print("API_SERT_CHAMPION", v); return
        time.sleep(10)
    raise RuntimeError("l'API sert %s, champion %s" % (v, champion))


with DAG("p7_cycle_ml", start_date=datetime(2026, 9, 27), schedule="30 3 * * *", catchup=False, max_active_runs=1,
         params={"injecter_derive": Param(False, type="boolean")}, tags=["soundlab", "p7"]) as dag:
    derive = DockerOperator(
        task_id="derive", image="soundlab-derive:1.0",
        command="--kaggle /donnees/features --lb /donnees/an2 --genre-mois /donnees/publie/genre_mois "
                "--sortie /donnees/derive/{{ ds }} --communs-attendus 29315 --tvd-genre-attendue 0.1425 "
                "--tvd-decennie-attendue 0.0704 {{ '--injecter' if params.injecter_derive else '' }}", **COMMUN)
    branche = BranchPythonOperator(task_id="brancher", python_callable=brancher)
    alerte = PythonOperator(task_id="alerter", python_callable=alerter)
    reentrainer = DockerOperator(
        task_id="reentrainer", image="soundlab-entrainement:1.0",
        command="--features /donnees/features --sortie /tmp/artefact --auc-temoin 0.7875 --tolerance-temoin 0.005 "
                "--mlflow-uri %s --code-refus 0" % MLFLOW,
        environment={"MLFLOW_TRACKING_URI": MLFLOW}, **COMMUN)
    verif = PythonOperator(task_id="verifier_api", python_callable=verifier_api)
    rien = EmptyOperator(task_id="sans_derive")
    derive >> branche >> [alerte, reentrainer, rien]
    reentrainer >> verif
