"""P7 - Donnees d'evaluation pour le tableau de bord (predictions hors pli, validation croisee groupee par artiste).

Meme modele, memes plis que train.entrainer : l'AUC moyenne doit reproduire celle du champion (temoin).
Sortie JSON sans aucune donnee individuelle : points de courbes, matrice de confusion, histogrammes, deciles.
Usage : python -m train.evaluer --features DIR --sortie evaluation.json --auc-temoin 0.7888 --tolerance 0.0005
"""
import argparse, json, sys
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve, roc_auc_score, roc_curve
from sklearn.model_selection import GroupKFold

from soundlab_p7.modele import N_PLIS, construire_foret, matrice_sentinelle, precision_au_rappel


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--features", required=True)
    p.add_argument("--sortie", required=True)
    p.add_argument("--auc-temoin", type=float)
    p.add_argument("--tolerance", type=float, default=0.0005)
    p.add_argument("--n-jobs", type=int, default=-1)
    a = p.parse_args(argv)
    df = pd.read_parquet(a.features)
    y, g = df["is_hit"].astype(int).values, df["artist"].values
    X = matrice_sentinelle(df)
    oof, aucs, seuils = np.zeros(len(df)), [], []
    for i_tr, i_te in GroupKFold(n_splits=N_PLIS).split(X, y, groups=g):
        m = construire_foret(a.n_jobs); m.fit(X.iloc[i_tr], y[i_tr])
        p_ = m.predict_proba(X.iloc[i_te])[:, 1]; oof[i_te] = p_
        aucs.append(float(roc_auc_score(y[i_te], p_)))
        seuils.append(precision_au_rappel(y[i_te], p_)[2])
    auc_moy, seuil = round(float(np.mean(aucs)), 4), round(float(np.mean(seuils)), 4)
    print("AUC_PAR_PLI", [round(x, 4) for x in aucs], "MOYENNE", auc_moy, "SEUIL", seuil, flush=True)
    if a.auc_temoin is not None and abs(auc_moy - a.auc_temoin) > a.tolerance:
        print("TEMOIN_ECHEC attendu", a.auc_temoin, flush=True); return 1
    fpr, tpr, _ = roc_curve(y, oof)
    idx = np.unique(np.linspace(0, len(fpr) - 1, 120).astype(int))
    pr, rc, th = precision_recall_curve(y, oof)
    grille = [s for s in np.round(np.arange(0.05, 0.96, 0.01), 2) if (oof >= s).sum() >= 200]
    seuils_pr = [{"seuil": float(s), "precision": round(float(y[oof >= s].mean()) if (oof >= s).any() else 1.0, 4),
                  "rappel": round(float(((oof >= s) & (y == 1)).sum() / (y == 1).sum()), 4)} for s in grille]
    pred = (oof >= seuil).astype(int)
    mc = {"vrais_negatifs": int(((pred == 0) & (y == 0)).sum()), "faux_positifs": int(((pred == 1) & (y == 0)).sum()),
          "faux_negatifs": int(((pred == 0) & (y == 1)).sum()), "vrais_positifs": int(((pred == 1) & (y == 1)).sum())}
    bornes = np.linspace(0, 1, 21)
    hist = {"bornes": [round(float(b), 2) for b in bornes],
            "succes": np.histogram(oof[y == 1], bornes)[0].tolist(), "autres": np.histogram(oof[y == 0], bornes)[0].tolist()}
    dec = pd.qcut(pd.Series(oof).rank(method="first"), 10, labels=False)
    deciles = [{"decile": int(10 - d), "taux_succes": round(float(y[dec.values == d].mean()), 4), "titres": int((dec.values == d).sum())}
               for d in range(9, -1, -1)]
    out = {"methode": "predictions hors pli, GroupKFold %d plis groupes par artiste" % N_PLIS, "titres": int(len(df)),
           "taux_base": round(float(y.mean()), 4), "auc_par_pli": [round(x, 4) for x in aucs], "auc_moyenne": auc_moy,
           "auc_ecart_type": round(float(np.std(aucs)), 4), "auc_globale_hors_pli": round(float(roc_auc_score(y, oof)), 4),
           "seuil": seuil, "precision_au_seuil": round(float(y[pred == 1].mean()), 4),
           "rappel_au_seuil": round(float(pred[y == 1].mean()), 4),
           "roc": [{"fpr": round(float(fpr[i]), 4), "tpr": round(float(tpr[i]), 4)} for i in idx],
           "seuils": seuils_pr, "matrice_confusion": mc, "histogramme": hist, "deciles": deciles}
    json.dump(out, open(a.sortie, "w"), indent=1)
    print("EVALUATION_OK", a.sortie, "matrice", mc, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
