import os, sys, re, subprocess, importlib.util
ICI = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0]]
T1 = os.path.join(ICI, "p7_01_test_seuil_k.py")
src = open(T1).read().split("env = dict(os.environ")[0]
exec(compile(src, T1, "exec"))
import pandas as pd
JOB2 = os.path.join(ICI, "..", "jobs", "p7_02_publier_k.py")
env = dict(os.environ, PYSPARK_SUBMIT_ARGS="--master local[2] pyspark-shell")
ga, _, _, _ = attendu("genre_mois", 11)
ta, _, _, _ = attendu("titre_mois", 11)
sortie = d + "/curated/trois_v/analyse/p7/publie"
q = subprocess.run([sys.executable, JOB2, d + "/aplati", cur, d + "/res", sortie, str(len(ec)), str(len(c)), str(ga), str(ta)],
                   capture_output=True, text=True, env=env)
out = q.stdout + q.stderr[-1500:]
print(out[-1500:])
g = pd.read_parquet(sortie + "/genre_mois"); t = pd.read_parquet(sortie + "/titre_mois")
x = pd.DataFrame({"cle": c["track_id"], "p": per["mois"], "u": c["user_id"]})
pu = x.groupby(["cle", "p", "u"]).size().rename("n").reset_index()
cs = pu.groupby(["cle", "p"]).agg(aud=("n", "size"), ec=("n", "sum"), mx=("n", "max")).reset_index()
cs = cs[(cs.aud >= 11) & (cs.mx <= .85 * cs.ec)]
T = [("P7P_OK", q.returncode == 0 and "P7P_OK" in out),
     ("titre_mois identique a pandas", sorted(zip(t.track_id, t.periode, t.ecoutes)) == sorted(zip(cs.cle, cs.p, cs.ec))),
     ("aucune colonne auditeurs", "aud" not in g.columns and "aud" not in t.columns and "user_id" not in t.columns),
     ("genre_mois nombre", len(g) == ga)]
for n, v in T:
    if not v: print("ECHEC", n)
print("TESTS %d/%d" % (sum(v for _, v in T), len(T)))
