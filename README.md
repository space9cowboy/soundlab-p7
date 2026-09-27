# SoundLab Analytics — Projet 7 : mise en production

Un score par titre, jamais par personne : probabilité qu'un titre atteigne le quart supérieur des écoutes.
Suite du Bloc 6 (modèle forêt aléatoire, AUC 0,7875 ± 0,0059 en validation croisée groupée par artiste) et du chantier « trois V » (ListenBrainz).

## Architecture

| Couche | Local (Compose) | Cluster (kind) | En ligne (gratuit) |
| --- | --- | --- | --- |
| Registre et suivi | MLflow + Postgres | MLflow + Postgres (StatefulSet) | — |
| Entraînement | service `entrainement` (profil) | Job Kubernetes | — |
| API FastAPI | `api` (modèle chargé par alias `champion`) | Deployment 2 à 6 réplicas, HPA, PDB, Ingress `/api` | Render, scores précalculés |
| Dérive | image `soundlab-derive` (Evidently) | — | — |
| Orchestration | Airflow 2.10.5 (profil `orchestration`), DAG `p7_cycle_ml` | — | — |
| Tableau de bord | `npm run dev` dans `front/` | — | Vercel (Next.js) |

Le redéploiement d'un modèle promu est automatique : l'API relit l'alias `champion` toutes les `RECHARGEMENT_S` secondes.

## Données et gouvernance

- `jobs/p7_01_seuil_k.py` : mesure de l'effet du seuil k (EMR Serverless). Décision du 27/09 : **k = 11**, règle de dominance 85 %, granularité titre × mois (68,52 % du catalogue garde une tendance ; critère de 50 % fixé avant la mesure).
- `jobs/p7_02_publier_k.py` : cases publiables (2 288 genre × mois, 2 041 517 titre × mois), sans nombre d'auditeurs.
- Aucune table à jetons n'est écrite : la table (titre, jeton, jour) reste sur le disque éphémère des exécuteurs.
- Le tableau de bord n'affiche que genre × mois ; tout total publié est une somme de cases publiables.
- Licences : Kaggle CC BY-NC 4.0, ListenBrainz CC0, étiquettes MusicBrainz CC BY-NC-SA. Usage non commercial.

## Lancer en local

```
python3 -c "import secrets;print('POSTGRES_PASSWORD='+secrets.token_urlsafe(24))" > .env
docker compose build
docker compose up -d postgres mlflow
docker compose --profile entrainement run --rm entrainement
docker compose up -d api
curl -s localhost:8000/model-version
```

Données attendues dans `data/` (hors git) : `features/` (songs_features_labeled), `an2/` (an2_auditeurs_par_titre), `publie/genre_mois/`.

## Kubernetes (kind)

Voir `k8s/` ; Ingress sur `localhost:8088/api`, installé par `k8s/ingress-kind.sh`.

Incident du 27/09 : le manifeste ingress-nginx pour kind a placé le contrôleur sur un nœud worker, alors que seul le nœud de contrôle publie le port 8088 (600 requêtes sur 600 en échec de connexion). Correctif : sélection du nœud `ingress-ready=true` et tolérance de la taint du nœud de contrôle, avec un contrôle qui échoue si le contrôleur est mal placé. Mesure ensuite : mise à jour progressive de l'API (2 pods remplacés un par un) pendant 600 requêtes, 600 réponses 200. Test de charge : `charge/charge.js` (k6).

## Déploiement gratuit

1. **API sur Render** : `deploy/extraire_artefact_render.py` copie `scores.parquet` et `meta.json` du champion dans `deploy/render/artefact/` ; Render construit `deploy/render/Dockerfile` (voir `render.yaml`). Offre gratuite : mise en veille après 15 min sans trafic, réveil d'environ une minute ; 512 Mo, donc `/predict` répond 503 et l'API sert les scores précalculés.
2. **Front sur Vercel** : racine `front/`, variable `NEXT_PUBLIC_API_URL` = URL Render. Offre Hobby : usage personnel non commercial.
3. Sur Render, `CORS_ORIGINES` = URL Vercel.

## Tests

```
pip install -r requirements/test.txt
pytest tests/
```

C'est ce que rejoue l'intégration continue (`.github/workflows/ci.yml`), avant de construire toutes les images de `docker-compose.yml` et l'image Render.

Les tests Spark des jobs `p7_01` et `p7_02` ne sont pas collectés par pytest (leurs noms ne suivent pas `test_*.py`) et ne font pas partie de la CI. Ils se lancent à part, dans un environnement qui dispose de PySpark (absent de `requirements/`) et de Java :

```
python tests/p7_01_test_seuil_k.py
python tests/p7_02_test_publier_k.py
```

## Écarts assumés au brief

- Next.js au lieu de Dash/Streamlit ; Vercel et Render au lieu de Heroku (plus d'offre gratuite).
- Kubernetes local (kind) au lieu d'un cluster managé.
- Kafka, Airbyte, RLlib, CI/CD : non réalisés dans le délai d'une journée ; justifiés dans la documentation.
