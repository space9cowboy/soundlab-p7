import os, sys
import numpy as np, pandas as pd, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from monitoring import derive


def jeux(d, decale=True):
    r = np.random.default_rng(0); n = 3000
    genres = np.array(["Rock", "Pop", "Jazz", None, "Country"])
    lab = pd.DataFrame({"track_id": ["T%d" % i for i in range(n)], "genre": genres[r.integers(0, 5, n)],
                        "year": r.integers(1960, 2015, n), "is_hit": r.integers(0, 2, n),
                        "total_plays": r.integers(1, 500, n)})
    for c in derive.NUMERIQUES:
        lab[c] = r.normal(size=n)
    lb = pd.DataFrame({"track_id": lab.track_id, "lb_ecoutes": lab.total_plays})
    if decale:
        lb.loc[lab.genre == "Rock", "lb_ecoutes"] *= 4
        lb.loc[lab.genre == "Country", "lb_ecoutes"] = lb.loc[lab.genre == "Country", "lb_ecoutes"] // 5 + 1
    lab.to_parquet(d / "lab.parquet"); lb.to_parquet(d / "lb.parquet")
    lab["g"] = lab.genre.map(derive.genre_norm)
    return lab, lb


def test_temoins_et_fenetres(tmp_path):
    lab, lb = jeux(tmp_path)
    tg = round(derive.tvd(derive.parts(lab.total_plays, lab.g), derive.parts(lb.lb_ecoutes, lab.g)), 4)
    import json
    r = np.random.default_rng(5); lignes = []
    part = derive.parts(lab.total_plays, lab.g)
    for m in ["2014-%02d" % i for i in range(1, 13)] + ["2016-01", "2016-02"]:
        for g, v in part.items():
            lignes.append((g, m, int(20000 * v * r.uniform(.9, 1.1))))
    lignes.append(("(hors_catalogue)", "2016-02", 99999))
    pd.DataFrame(lignes, columns=["genre", "periode", "ecoutes"]).to_parquet(tmp_path / "gm.parquet")
    arg = ["--kaggle", str(tmp_path / "lab.parquet"), "--lb", str(tmp_path / "lb.parquet"), "--communs-attendus", "3000",
           "--tvd-genre-attendue", str(tg), "--genre-mois", str(tmp_path / "gm.parquet"), "--n", "5000"]
    assert derive.main(arg + ["--sortie", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "derive_kaggle_vers_listenbrainz.html").exists()
    rp = json.loads((tmp_path / "o" / "rapport_derive.json").read_text())
    assert rp["alerte"] is False and rp["fenetres_calibration"] == 12 and rp["fenetres_surveillees"] == 2
    assert derive.main(arg + ["--sortie", str(tmp_path / "o3"), "--injecter"]) == 0
    assert json.loads((tmp_path / "o3" / "rapport_derive.json").read_text())["alerte"] is True
    assert derive.main(["--kaggle", str(tmp_path / "lab.parquet"), "--lb", str(tmp_path / "lb.parquet"), "--sortie", str(tmp_path / "o2"),
                        "--tvd-genre-attendue", str(tg + 0.01), "--n", "5000"]) == 1


def test_sans_decalage_le_temoin_evidently_echoue(tmp_path):
    jeux(tmp_path, decale=False)
    assert derive.main(["--kaggle", str(tmp_path / "lab.parquet"), "--lb", str(tmp_path / "lb.parquet"), "--sortie", str(tmp_path / "o"), "--n", "5000"]) == 1
