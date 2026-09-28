"""P7 - Donnees de visualisation de la foret aleatoire servie (sans aucune donnee individuelle).

1. Foret complete (memes donnees, memes hyperparametres, graine 42 : meme modele que le champion) :
   - variable de la racine de chacun des 300 arbres ;
   - l'arbre le plus proche de la foret (correlation de ses probabilites avec celles de la foret), 3 premiers niveaux,
     avec pour chaque noeud le nombre de titres et le taux de succes REELS (non ponderes) ;
   - profondeur et nombre de feuilles des arbres.
2. AUC selon le nombre d'arbres : predictions hors pli (memes 5 plis groupes par artiste), moyenne des k premiers arbres.
Temoin : l'AUC hors pli a 300 arbres doit egaler l'AUC globale hors pli de evaluation.json (memes plis).
"""
import argparse, json, sys
from collections import Counter
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from soundlab_p7.modele import N_PLIS, SENTINELLE, construire_foret, matrice_sentinelle

TAILLES = [1, 2, 5, 10, 20, 50, 100, 150, 200, 300]


def noeud(arbre, i, X, y, cols, prof, prof_max, chemin):
    t = arbre.tree_
    masque = chemin[:, i].toarray().ravel().astype(bool)
    n = int(masque.sum())
    d = {"titres": n, "taux_succes": round(float(y[masque].mean()), 4) if n else None}
    if prof < prof_max and t.children_left[i] != -1:
        d["variable"] = cols[t.feature[i]]
        d["seuil"] = round(float(t.threshold[i]), 4)
        d["oui"] = noeud(arbre, t.children_left[i], X, y, cols, prof + 1, prof_max, chemin)
        d["non"] = noeud(arbre, t.children_right[i], X, y, cols, prof + 1, prof_max, chemin)
    return d


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--features", required=True)
    p.add_argument("--sortie", required=True)
    p.add_argument("--evaluation", help="evaluation.json : son AUC globale hors pli sert de temoin")
    p.add_argument("--tolerance", type=float, default=0.0005)
    p.add_argument("--profondeur", type=int, default=3)
    p.add_argument("--n-jobs", type=int, default=-1)
    a = p.parse_args(argv)
    df = pd.read_parquet(a.features)
    y, g = df["is_hit"].astype(int).values, df["artist"].values
    X = matrice_sentinelle(df)
    cols = list(X.columns)

    # 2. AUC selon le nombre d'arbres (hors pli)
    cumul = {k: np.zeros(len(df)) for k in TAILLES}
    for i_tr, i_te in GroupKFold(n_splits=N_PLIS).split(X, y, groups=g):
        m = construire_foret(a.n_jobs); m.fit(X.iloc[i_tr], y[i_tr])
        probas = np.array([e.predict_proba(X.iloc[i_te].values)[:, 1] for e in m.estimators_])
        for k in TAILLES:
            cumul[k][i_te] = probas[:k].mean(axis=0)
    courbe = [{"arbres": k, "auc": round(float(roc_auc_score(y, cumul[k])), 4)} for k in TAILLES]
    print("AUC_SELON_ARBRES", courbe, flush=True)

    # 1. Foret complete
    f = construire_foret(a.n_jobs); f.fit(X, y)
    Xv = X.values
    pf = f.predict_proba(X)[:, 1]
    racines = Counter(cols[e.tree_.feature[0]] for e in f.estimators_)
    correl = [float(np.corrcoef(e.predict_proba(Xv)[:, 1], pf)[0, 1]) for e in f.estimators_]
    ib = int(np.argmax(correl))
    arbre = f.estimators_[ib]
    racine = noeud(arbre, 0, Xv, y, cols, 0, a.profondeur, arbre.decision_path(Xv))
    prof = [e.get_depth() for e in f.estimators_]
    feuilles = [e.get_n_leaves() for e in f.estimators_]
    out = {"methode": "foret complete (30 459 titres, graine 42) ; courbe : predictions hors pli, GroupKFold %d plis par artiste" % N_PLIS,
           "sentinelle": SENTINELLE, "arbres": len(f.estimators_),
           "racines": [{"variable": v, "arbres": n} for v, n in racines.most_common()],
           "arbre_representatif": {"indice": ib, "correlation_avec_foret": round(correl[ib], 4),
                                   "correlation_mediane": round(float(np.median(correl)), 4), "profondeur_affichee": a.profondeur,
                                   "profondeur_totale": arbre.get_depth(), "feuilles": int(arbre.get_n_leaves()), "racine": racine},
           "profondeur": {"min": int(min(prof)), "mediane": float(np.median(prof)), "max": int(max(prof))},
           "feuilles": {"min": int(min(feuilles)), "mediane": float(np.median(feuilles)), "max": int(max(feuilles))},
           "auc_selon_arbres": courbe}
    json.dump(out, open(a.sortie, "w"), indent=1)
    print("FORET arbre", ib, "correlation", round(correl[ib], 4), "racines", racines.most_common(4), "profondeur", out["profondeur"], flush=True)
    if a.evaluation:
        attendu = json.load(open(a.evaluation))["auc_globale_hors_pli"]
        ok = abs(courbe[-1]["auc"] - attendu) <= a.tolerance
        print("TEMOIN auc_300_arbres", courbe[-1]["auc"], "attendu", attendu, "OK" if ok else "ECHEC", flush=True)
        if not ok:
            return 1
    print("VISUALISATION_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
