# SoundLab Analytics — Projet 7 : documentation de l'infrastructure de production

**Auteur :** Loïc Rabetsanta — **Date :** 27 septembre 2026 — **Certification :** Architecte en intelligence artificielle, bloc 7 (compétences C2.5, C2.6, C2.8, C4.3, C4.5)

**Dépôt :** `github.com/space9cowboy/soundlab-p7` (privé) — **Tableau de bord :** https://soundlab-p7.vercel.app — **API publique :** https://soundlab-api.onrender.com

Tous les chiffres de ce document sont des mesures du 27 septembre 2026. Chacun renvoie à un journal conservé dans `data/` (hors dépôt) ou à un test du dépôt. Une valeur non mesurée est signalée comme telle.

## Sommaire

1. Objet et périmètre
2. Architecture d'ensemble
3. Données et gouvernance : le seuil k
4. Conteneurisation (Docker, Compose)
5. Registre et suivi des modèles (MLflow)
6. Orchestration Kubernetes
7. API de prédiction
8. Tableau de bord et hébergement public
9. Surveillance de la dérive (Evidently)
10. Automatisation du cycle ML (Airflow)
11. Performances mesurées
12. Accessibilité
13. Incidents et corrections
14. Écarts assumés au brief
15. Procédures d'exploitation et de reprise
16. Limites et suites

## 1. Objet et périmètre

SoundLab Analytics (société fictive) aide des labels indépendants à répartir un budget de promotion. Le produit estime la probabilité qu'un titre atteigne le quart supérieur des écoutes : **un score par titre, jamais par personne**.

Le projet 7 met en production le modèle validé au Bloc 6 (forêt aléatoire, AUC 0,7875 ± 0,0059 en validation croisée groupée par artiste) et l'alimente avec les écoutes réelles ListenBrainz chargées chaque nuit par la chaîne « trois V ».

Le brief générique parle de « prédiction de churn ». Transposition retenue :

| Brief | SoundLab |
| --- | --- |
| Prédiction de churn par client | Score de succès par titre |
| Données client en temps réel | Chargement quotidien ListenBrainz (02:00 UTC), scores servis à la demande |
| Tableau de bord Dash ou Streamlit | Next.js sur Vercel (écart, § 14) |
| Heroku | Render et Vercel, offres gratuites (écart, § 14) |

## 2. Architecture d'ensemble

| Couche | Local (Docker Compose) | Cluster (Kubernetes, kind) | En ligne |
| --- | --- | --- | --- |
| Données | Lac S3 et EMR Serverless (Bloc 6 et trois V) | idem | idem |
| Registre et suivi | MLflow 2.18 + Postgres 16 | MLflow + Postgres (StatefulSet) | — |
| Entraînement | service `entrainement` (profil) | Job Kubernetes | — |
| API FastAPI | service `api` | Deployment 2 à 6 réplicas, autoscaling, Ingress `/api` | Render (offre gratuite) |
| Dérive | image `soundlab-derive` (Evidently 0.4.40) | — | — |
| Orchestration | Airflow 2.10.5, DAG `p7_cycle_ml` | — | — |
| Tableau de bord | `front/` (Next.js 14) | — | Vercel (offre Hobby) |

Flux principal : les écoutes ListenBrainz arrivent chaque nuit dans le lac → les agrégats publiables (k = 11) sont calculés sur EMR Serverless → le DAG mesure la dérive → en cas d'alerte, il réentraîne, soumet le candidat à la porte de promotion et l'enregistre dans MLflow → l'API recharge l'alias `champion` sans reconstruction → le tableau de bord lit l'API.

## 3. Données et gouvernance : le seuil k

**Problème.** Un tableau de bord public diffuse des agrégats d'écoutes, classés C2 (restreint) dans le plan de gouvernance. Or l'AIPD (amendement n° 1) avait mesuré que 89,8 % des couples écoute-jour ListenBrainz n'ont qu'un auditeur. Publier sans seuil revient à publier des comportements individuels.

**Méthode (fixée avant la mesure).**

1. Plancher **k = 11** : règle des unités appliquée aux données de personnes, avalisée par la CNIL pour les données fiscales. Les valeurs 3 et 5 sont mesurées pour comparaison seulement.
2. Règle de dominance : une case est exclue si un auditeur y pèse plus de 85 % des écoutes.
3. Critère d'utilité : au moins 50 % des 50 683 titres du catalogue doivent garder une tendance (au moins deux cases publiables).
4. Choix : la granularité la plus fine qui respecte le critère avec k = 11. On agrège davantage plutôt que de baisser k.

**Mesure** (`jobs/p7_01_seuil_k.py`, job EMR `00g93d5kh33pso1f`, 1 420 s). Témoins reproduits : 695 640 731 écoutes, dont 135 259 030 couvertes par le catalogue, et 0 écart sur les 48 671 titres de `an2_auditeurs_par_titre`.

| Granularité, k = 11 | Cases publiables | Écoutes couvertes | Catalogue avec une tendance |
| --- | --- | --- | --- |
| Titre × jour | 0,66 % | 6,05 % | 10,80 % |
| Titre × semaine | 10,51 % | 45,36 % | 36,56 % |
| **Titre × mois (retenu)** | 36,12 % | 80,35 % | **68,52 %** |
| Titre × année | 88,95 % | 99,24 % | 92,97 % |
| Genre × mois | 94,78 % | 100 % | 16 genres sur 16 |

**Hypothèse réfutée.** Il était prévu que titre × mois échoue au critère, par extrapolation des 78 % de cases mensuelles à un seul auditeur mesurés dans l'AIPD. Cette mesure portait sur les enregistrements ListenBrainz ; un titre du catalogue regroupe toutes ses versions et est plus écouté en moyenne. Mesuré : 9,24 % de cases titre × mois à un auditeur.

**Publication** (`jobs/p7_02_publier_k.py`, job `00g93dod9u930o1f`, 1 068 s) : 2 288 cases genre × mois et 2 041 517 cases titre × mois, exactement les nombres annoncés par la mesure. Colonnes : clé, période, écoutes. Aucun nombre d'auditeurs n'est publié.

**Protection des jetons.** Aucune table contenant des jetons d'auditeurs n'est écrite : la table (titre, jeton, jour) reste sur le disque éphémère des exécuteurs (`persist(DISK_ONLY)`) et disparaît avec le job. Le job refuse de démarrer si sa sortie n'est pas sous `trois_v/analyse/`. Leçon de l'action B13 du Bloc 6, où deux tables intermédiaires à jetons avaient été écrites en zone affinée.

**Secret secondaire.** Le tableau de bord n'affiche que genre × mois, dont toutes les cases sont au-dessus de k. Si titre × mois est un jour affiché, les totaux par genre devront être recalculés comme somme des cases titre publiées, pour qu'aucune soustraction ne révèle une case masquée.

## 4. Conteneurisation

| Image | Rôle | Particularités |
| --- | --- | --- |
| `soundlab-entrainement` | réentraînement, témoin, promotion | dépendances épinglées (`requirements/train.txt`) |
| `soundlab-api` | service FastAPI | construction en deux étapes, utilisateur non root (uid 10001), sonde de santé, aucun secret |
| `soundlab-mlflow` | serveur MLflow | pilote Postgres, non root |
| `soundlab-derive` | rapports Evidently | dépendances épinglées (`requirements/derive.txt`) |

**Preuve de reproductibilité.** L'image d'entraînement réentraîne le modèle du Bloc 6 et contrôle l'AUC contre la valeur publiée ; au-delà de 0,005 d'écart, elle échoue sans produire d'artefact (test par mutation dans `tests/test_p7.py`).

| | Bloc 6 publié | Image du 27/09 |
| --- | --- | --- |
| AUC (validation croisée groupée) | 0,7875 ± 0,0059 | 0,7888 ± 0,0059 |
| AUC par pli | — | 0,7825 / 0,8000 / 0,7876 / 0,7862 / 0,7877 |
| Rappel au seuil | 0,7503 | 0,7503 |
| Précision | 0,4398 | 0,4421 |
| Seuil | 0,33 | 0,334 |

Données : 30 459 titres, 6 207 artistes, 25,01 % de succès. Cause probable de l'écart de 0,0013 : la version de scikit-learn (1.5.2), non vérifiée.

**Compose** (`docker-compose.yml`) : `postgres`, `mlflow`, `api`, plus les profils `entrainement`, `outils` (dérive) et `orchestration` (Airflow). Le mot de passe Postgres est généré dans `.env` (droits 600, exclu de git et des images).

## 5. Registre et suivi des modèles (MLflow)

Chaque entraînement journalise ses paramètres (300 arbres, `min_samples_leaf=5`, `balanced_subsample`, graine 42), ses métriques (AUC en validation croisée groupée, écart-type, précision au rappel 0,75, seuil), l'empreinte des données (`77481c13cff57e42`) et l'artefact (modèle, scores, métadonnées).

**Porte de promotion** (`soundlab_p7/modele.py`, `decider_promotion`) : le candidat est promu `champion` si son AUC n'est pas inférieure à celle du champion de plus de 0,005. Sinon il est enregistré mais pas promu, et la décision est tracée dans les étiquettes du run. Testé par mutation : un modèle entraîné sur des étiquettes mélangées n'est pas promu.

## 6. Orchestration Kubernetes

**Cluster** : kind, Kubernetes v1.37.0, un nœud de contrôle et deux workers (`k8s/kind-config.yaml`). Choix d'un cluster local : aucun coût permanent, contrairement au plan de contrôle d'un service managé.

| Objet | Configuration |
| --- | --- |
| Postgres | StatefulSet, volume persistant 1 Gio, secret Kubernetes |
| MLflow | Deployment, volume persistant 2 Gio pour les artefacts |
| API | Deployment : 2 réplicas minimum, mise à jour progressive (`maxUnavailable: 0`), sondes de démarrage, de disponibilité et de vie sur `/health`, requêtes 250m / 768 Mio, limites 1 CPU / 1,5 Gio, système de fichiers en lecture seule, non root |
| Budget de disponibilité | au moins 1 pod API toujours disponible |
| Autoscaling | 2 à 6 réplicas, cible 60 % de CPU, stabilisation de la descente 60 s |
| Ingress | ingress-nginx, `localhost:8088/api` (`k8s/ingress-kind.sh`) |
| Entraînement | Job Kubernetes (`k8s/50-job-entrainement.yaml`) |

Mesures : le Job d'entraînement reproduit le témoin dans le cluster (AUC 0,7888, 51,1 s) et promeut la version 1 ; les deux pods de l'API se répartissent sur deux nœuds différents.

## 7. API de prédiction

`api/main.py` (FastAPI) :

| Route | Rôle |
| --- | --- |
| `GET /health` | santé (503 si aucun artefact chargé) |
| `GET /model-version` | version, date, AUC, seuil du modèle servi |
| `POST /predict` | score d'un titre à partir de ses 18 variables |
| `GET /score/{track_id}` | score précalculé d'un titre |
| `GET /titres` | titres filtrés (genre, décennie, artiste), triés par score, 200 au plus |
| `GET /genres`, `GET /tendances` | genres et tendances mensuelles publiables |

**Garanties testées** (`tests/test_p7.py`, 11 tests) :

- une requête contenant un champ inattendu, par exemple `user_id`, est rejetée (422) ;
- `/predict` et `/score` donnent le même score pour un même titre ;
- un fichier de tendances qui contiendrait une colonne d'auditeurs est refusé au chargement ;
- l'API recharge le modèle quand l'alias `champion` change ;
- une origine CORS avec barre oblique finale est normalisée.

**Rechargement automatique** : toutes les 30 secondes (`RECHARGEMENT_S`), l'API compare la version de l'alias `champion` à celle qu'elle sert et recharge si besoin. Une promotion est donc déployée sans reconstruire ni redémarrer.

## 8. Tableau de bord et hébergement public

**Front** (`front/`, Next.js 14) : bandeau du modèle servi, filtres, tableau des titres, export CSV, courbe des écoutes par genre, message d'attente pendant le réveil de l'API, mentions de licence. Le front ne lit que l'API.

**Hébergement** :

| Service | Offre | Contraintes |
| --- | --- | --- |
| Vercel (front) | Hobby, gratuite | usage personnel non commercial, cohérent avec les licences du projet |
| Render (API) | gratuite | veille après 15 min sans trafic, réveil d'environ une minute ; 512 Mo de mémoire |

Sur Render, l'image (`deploy/render/Dockerfile`) embarque les scores et métadonnées extraits du champion (`deploy/extraire_artefact_render.py`, version 1, AUC 0,7888, 30 459 titres) mais pas le modèle de 31,8 Mo : `/predict` y répond 503 par choix. La prédiction à la volée tourne dans Compose et Kubernetes.

## 9. Surveillance de la dérive

`monitoring/derive.py`. Trois témoins font échouer le script s'ils ne sont pas reproduits :

1. 29 315 titres communs Kaggle / ListenBrainz ;
2. TVD genre 0,1425 et TVD décennie 0,0704 (valeurs d'AN4) ;
3. Evidently détecte la dérive du genre entre Kaggle et ListenBrainz (distance de Jensen-Shannon 0,1267 pour un seuil de 0,1) et ne détecte rien entre deux tirages Kaggle (0 colonne sur 8).

Méthodes : Jensen-Shannon pour les variables catégorielles, Wasserstein normée pour les numériques, seuil 0,1 (valeurs par défaut d'Evidently au-delà de 1 000 lignes).

**Fenêtres mensuelles.** Pour chaque mois publiable, la TVD de la répartition des genres est comparée à la référence Kaggle. Seuil d'alerte fixé avant la mesure : 95e centile des mois de calibration (2005 à 2015), soit **0,2505**. Surveillance : 2016.

| Période | TVD genre moyenne par mois |
| --- | --- |
| 2007 à 2010 | 0,209 à 0,214 |
| 2013 | 0,244 |
| 2016 | 0,253 |

Neuf mois de 2016 sur douze dépassent le seuil ; décembre 2016 (0,2568) déclenche l'alerte. La dérive est progressive depuis 2010. Réserve : les fenêtres couvrent les 48 671 titres trouvés, pas les 29 315 titres communs ; leur niveau ne se compare pas à 0,1425, seule la tendance se lit.

Sorties : `derive_kaggle_vers_listenbrainz.html`, `contre_temoin_kaggle_kaggle.html`, `fenetres_tvd_genre.csv`, `rapport_derive.json`.

## 10. Automatisation du cycle ML

DAG `orchestration/dags/p7_cycle_ml.py`, quotidien à 03:30 UTC (après le chargement ListenBrainz de 02:00) :

`derive` → `brancher` → (`alerter` + `reentrainer` → `verifier_api`) ou `sans_derive`

- chaque étape lourde tourne dans son image (DockerOperator) ;
- `alerter` écrit l'alerte dans `data/alertes/` et la publie sur SNS si `SNS_TOPIC_ARN` est défini (non configuré le 27/09) ;
- `reentrainer` applique le témoin et la porte de promotion ;
- `verifier_api` attend que l'API serve la version du champion, et échoue sinon.

**Exécution du 27/09** (`airflow dags test p7_cycle_ml 2026-09-27`, Airflow 2.10.5, journal `data/p7_07_dag.log`) :

| Tâche | Résultat |
| --- | --- |
| `derive` | témoins reproduits, contre-témoin 0 colonne en dérive ; 9 mois de 2016 sur 12 au-dessus du seuil 0,2505 ; `DERIVE_ALERTE` |
| `brancher` | alerte vraie : `alerter` et `reentrainer` lancées, `sans_derive` ignorée |
| `alerter` | « dérive détectée le 2026-09-27, TVD genre dernière fenêtre 0,2568 > seuil 0,2505 » écrit dans `data/alertes/2026-09-27.json` |
| `reentrainer` | témoin OK, AUC 0,7888 ; promotion acceptée (candidat 0,7888 ≥ champion 0,7888 − 0,005) : **version 2**, 22,1 s |
| `verifier_api` | l'API sert la version 2, sans reconstruction ni redémarrage |

Avant l'exécution, l'API servait la version 1 ; après, `/model-version` renvoie la version 2. La boucle complète dérive → alerte → réentraînement → promotion → déploiement est donc démontrée.

Premier essai en échec (incident n° 8) : la tâche `derive` tournait encore avec l'image construite avant le correctif du chi². Son témoin a échoué et le DAG s'est arrêté avant toute alerte ou tout réentraînement.

## 11. Performances mesurées

**Test de charge** (k6 0.54, 8 minutes, `POST /predict` via l'Ingress, palier à 30 requêtes par seconde) :

| Mesure | Valeur |
| --- | --- |
| Requêtes | 9 989, 20,8 par seconde en moyenne sur le profil complet |
| Échecs | 0 |
| Latence médiane / p90 / p95 | 8,3 ms / 19,8 ms / 27 ms |
| Latence maximale | 5,01 s (une requête, cause non isolée) |

**Autoscaling** : CPU à 70-74 % (cible 60 %) à 14:48:36, troisième réplica à 14:48:46, utilisation retombée à 44 % ; retour à deux réplicas à 14:51:18. La remontée à 63 % qui suit reste dans la tolérance de 10 % de l'autoscaling. Relevé : `data/p7_06_hpa.txt`.

**Mise à jour sans coupure** : remplacement des deux pods de l'API pendant 600 requêtes `/health` via l'Ingress : 600 réponses 200.

**Calculs sur EMR Serverless** : mesure du seuil k 1 420 s, publication 1 068 s. Les vCPU-heures facturées n'étaient pas encore disponibles à la fin des jobs : à relever.

**Entraînement** : 17,1 s dans Compose, 51,1 s dans le Job Kubernetes (limite de 2 CPU).

## 12. Accessibilité

Audit axe-core 4.10.2 de la page publiée (critères WCAG 2.1 A et AA, thème sombre) : **0 violation**, 313 éléments de contraste conformes. Les 8 libellés du graphique, non évaluables par axe, ont été calculés à la main : 9,56:1 en sombre, 8,86:1 en clair (minimum requis 4,5:1). Contraste le plus faible du thème clair : 6,24:1. Commandes natives, tableau avec légende et en-têtes, focus visible, priorité écrite en texte et pas seulement en couleur.

Ce document suit les mêmes règles : titres hiérarchisés, tableaux avec en-têtes, aucune information portée par la seule couleur.

## 13. Incidents et corrections

| N° | Incident | Cause | Correction |
| --- | --- | --- | --- |
| 1 | Le premier job du seuil k aurait échoué à l'écriture | le rôle EMR n'écrit que sous `listenbrainz/aplati/` et `rebut/` | aucune table à jetons écrite (disque éphémère) plutôt qu'un droit IAM supplémentaire |
| 2 | Fausse dérive sur le contre-témoin | test du chi² invalide sous 5 effectifs attendus (décennies rares, environ 1,3) | Jensen-Shannon et Wasserstein |
| 3 | Création du cluster refusée | port 8080 déjà pris par l'Airflow du Bloc 6 | Ingress sur 8088 |
| 4 | 600 requêtes sur 600 en échec de connexion | contrôleur ingress-nginx placé sur un worker, seul le nœud de contrôle publie le port | sélection du nœud et tolérance, contrôle qui échoue si le contrôleur est mal placé |
| 5 | Front bloqué sur « Connexion à l'API » | origine CORS saisie avec une barre oblique finale | valeur corrigée ; l'API normalise désormais les origines |
| 6 | Premier commit arrêté | faux positif de la recherche de secrets (commande de génération dans le README) | motif resserré ; le garde-fou a fonctionné |
| 7 | Résumé JSON de k6 non écrit | dossier monté en lecture seule | chiffres pris dans le journal ; montage à corriger |
| 8 | Premier passage du DAG arrêté à la tâche `derive` | image `soundlab-derive` non reconstruite après le correctif du chi² : le contre-témoin a de nouveau signalé une fausse dérive | image reconstruite (présence du correctif vérifiée dans l'image) ; second passage réussi |

Comme au Bloc 6, les incidents les plus instructifs sont des contrôles qui ont échoué pour de bonnes raisons (2, 6, 8) ou des hypothèses réfutées par leur mesure (§ 3).

## 14. Écarts assumés au brief

| Brief | Réalisé | Justification |
| --- | --- | --- |
| Heroku | Render (API) et Vercel (front) | plus d'offre gratuite chez Heroku ; le brief autorise « un autre service » |
| Dash ou Streamlit | Next.js | interface découplée, la logique reste dans l'API |
| Cluster Kubernetes | kind (local) | démonstration complète sans coût permanent |
| Kafka | non réalisé | le flux réel est un chargement quotidien ; un bus de messages n'apporterait rien dans le délai d'une journée |
| Airbyte | non réalisé | l'ingestion ListenBrainz et MusicBrainz existe déjà (chaîne trois V) |
| RLlib | non réalisé | apprentissage par renforcement, sans rapport avec un classifieur supervisé ; seul usage plausible : allocation du budget en bandit, hors délai |
| Ray | non réalisé | l'entraînement dure 17 s sur 30 459 titres : la distribution n'apporterait pas de gain mesurable |
| CI/CD | non réalisée | tests locaux (`pytest tests/`) ; une chaîne GitHub Actions est la suite naturelle |

## 15. Procédures d'exploitation et de reprise

**Démarrer en local**

```
python3 -c "import secrets;print('POSTGRES_PASSWORD='+secrets.token_urlsafe(24))" > .env
docker compose build
docker compose up -d postgres mlflow
docker compose --profile entrainement run --rm entrainement
docker compose up -d api
```

**Recréer le cluster** : voir le README ; installer l'Ingress avec `bash k8s/ingress-kind.sh`, qui échoue si le contrôleur est mal placé.

**Revenir à un modèle précédent** : réaffecter l'alias `champion` à la version voulue dans MLflow ; l'API la charge en moins de 30 secondes.

**API Render en veille** : ouvrir `/health` une minute avant une démonstration.

**Mettre à jour les scores publics** : `deploy/extraire_artefact_render.py` puis commit et push ; Render reconstruit automatiquement.

**Tests** : `pip install -r requirements/test.txt && pytest tests/`.

## 16. Limites et suites

- La vérité terrain arrive avec retard : le quart supérieur n'est connu qu'après accumulation des écoutes. La performance réelle du modèle en production n'est pas encore mesurée.
- La cible dépend du public qui la mesure (κ = 0,2476 entre Kaggle et ListenBrainz, AN3) : un réentraînement sur ListenBrainz changerait la définition du succès, pas seulement le modèle.
- Organisation fictive, un seul administrateur ; avis du DPO non rendu.
- Usage non commercial uniquement (licences CC BY-NC et CC BY-NC-SA).
- Suites : chaîne CI/CD, alerte SNS branchée, suivi de la performance réelle, démantèlement des ressources payantes après la soutenance.
