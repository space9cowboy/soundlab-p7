"""Definitions du modele SoundLab reprises a l'identique du Bloc 6 (ml/13_comparaison_modeles.py)."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, roc_auc_score, roc_curve
from sklearn.model_selection import GroupKFold

GRAINE = 42
SENTINELLE = -1.0
N_PLIS = 5
RAPPEL_CIBLE = 0.75

AUDIO = [
    "danceability", "energy", "key", "loudness", "mode", "speechiness",
    "acousticness", "instrumentalness", "liveness", "valence", "tempo",
    "time_signature", "duration_ms",
]
CONTEXTE = ["anciennete", "duration_min", "artist_nb_titres_hors_piste"]
ARTISTE = ["artist_plays_moyen_hors_piste", "artist_taux_hits_hors_piste"]
VARIABLES = AUDIO + CONTEXTE + ARTISTE


def matrice_sentinelle(df):
    """Entrainement : indicateur _manquant pour chaque variable ayant au moins un manquant, puis sentinelle."""
    X = df[VARIABLES].copy()
    for c in VARIABLES:
        if X[c].isna().any():
            X[f"{c}_manquant"] = X[c].isna().astype(int)
            X[c] = X[c].fillna(SENTINELLE)
    return X


def preparer(df, colonnes):
    """Prediction : reconstruit exactement les colonnes vues a l'entrainement."""
    X = df[VARIABLES].copy().astype(float)
    for c in colonnes:
        if c.endswith("_manquant"):
            X[c] = X[c[: -len("_manquant")]].isna().astype(int)
    X[VARIABLES] = X[VARIABLES].fillna(SENTINELLE)
    return X[list(colonnes)]


def construire_foret(n_jobs=-1):
    return RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
                                  n_jobs=n_jobs, random_state=GRAINE)


def precision_au_rappel(y_vrai, proba, rappel_vise=RAPPEL_CIBLE):
    _, tpr, seuils = roc_curve(y_vrai, proba)
    i = int(np.argmax(tpr >= rappel_vise))
    seuil = float(seuils[min(i, len(seuils) - 1)])
    pred = (proba >= seuil).astype(int)
    return float(precision_score(y_vrai, pred, zero_division=0)), float(recall_score(y_vrai, pred)), seuil


def evaluer_cv(X, y, groupes, fabrique=construire_foret):
    aucs, precisions, rappels, seuils = [], [], [], []
    for i_tr, i_te in GroupKFold(n_splits=N_PLIS).split(X, y, groups=groupes):
        m = fabrique()
        m.fit(X.iloc[i_tr], y.iloc[i_tr])
        p = m.predict_proba(X.iloc[i_te])[:, 1]
        aucs.append(float(roc_auc_score(y.iloc[i_te], p)))
        a, b, s = precision_au_rappel(y.iloc[i_te], p)
        precisions.append(a); rappels.append(b); seuils.append(s)
    return {"auc_par_pli": [round(a, 4) for a in aucs], "auc_moyen": round(float(np.mean(aucs)), 4),
            "auc_ecart_type": round(float(np.std(aucs)), 4),
            "precision_au_rappel_075": round(float(np.mean(precisions)), 4),
            "rappel_obtenu": round(float(np.mean(rappels)), 4), "seuil_moyen": round(float(np.mean(seuils)), 4)}


def decider_promotion(auc_candidat, auc_champion, tolerance):
    """Porte de promotion : le candidat ne doit pas etre moins bon que le champion au-dela de la tolerance."""
    if auc_champion is None:
        return True, "aucun champion"
    if auc_candidat >= auc_champion - tolerance:
        return True, "candidat %.4f >= champion %.4f - %.4f" % (auc_candidat, auc_champion, tolerance)
    return False, "candidat %.4f < champion %.4f - %.4f" % (auc_candidat, auc_champion, tolerance)
