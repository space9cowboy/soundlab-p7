import os, sys, re, subprocess, tempfile, importlib.util
import numpy as np, pandas as pd
ICI = os.path.dirname(os.path.abspath(__file__))
JOB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ICI, "..", "jobs", "p7_01_seuil_k.py")
sp_ = importlib.util.spec_from_file_location("j", JOB); j = importlib.util.module_from_spec(sp_); sp_.loader.exec_module(j)
from pyspark.sql import SparkSession

d = tempfile.mkdtemp(prefix="tk_"); cur = d + "/cur"
rng = np.random.default_rng(7)
NK = 40
genres = [None if i % 5 == 0 else ("nan" if i % 7 == 0 else ["Rock", "Pop", "Jazz"][i % 3]) for i in range(NK)]
mi = pd.DataFrame({"track_id": ["K%02d" % i for i in range(NK)], "genre": genres})
rows = []
def ecoute(u, dt, i, n=1):
    for _ in range(n):
        rows.append((u, dt, "msid%d" % i, "Artist %d" % (i % 8), "Song %d" % i))
ecoute("u00", "2010-03-01", 0, 100)
for u in range(1, 12): ecoute("u%02d" % u, "2010-03-01", 0)
for u in range(12): ecoute("u%02d" % u, "2010-03-01", 1)
for u in range(10): ecoute("u%02d" % u, "2010-03-01", 2)
for _ in range(6000):
    i = int(rng.integers(3, 36)); u = "u%02d" % min(int(rng.exponential(12)), 59)
    dt = pd.Timestamp("2005-01-01") + pd.Timedelta(days=int(rng.integers(0, 12 * 365)))
    ecoute(u, dt.strftime("%Y-%m-%d"), i, int(rng.integers(1, 4)))
for _ in range(400):
    rows.append(("u%02d" % int(rng.integers(0, 60)), "2012-05-03", "bruit", "Nobody", "Nothing"))
ec = pd.DataFrame(rows, columns=["user_id", "date", "recording_msid", "artist_name", "track_name"])
ec["mois"] = ec["date"].str[:7]

spark = SparkSession.builder.master("local[2]").appName("t").getOrCreate()
sdf = spark.createDataFrame(ec.assign(spotify_id=None, spotify_track_uri=None),
                            "user_id string, date string, recording_msid string, artist_name string, track_name string, mois string, spotify_id string, spotify_track_uri string")
sdf.selectExpr("user_id", "to_date(date) as date", "recording_msid", "artist_name", "track_name", "spotify_id", "spotify_track_uri", "mois") \
   .write.partitionBy("mois").parquet(d + "/aplati")
spark.createDataFrame(mi, "track_id string, genre string").write.parquet(cur + "/music_info")
res = pd.DataFrame({"recording_msid": ["msid%d" % i for i in range(36)],
                    "cle": [re.sub("[^a-z0-9_]", "", ("Artist %dSong %d" % (i % 8, i)).lower()) for i in range(36)],
                    "sp": [None] * 36, "track_id": ["K%02d" % i for i in range(36)]})
spark.createDataFrame(res, "recording_msid string, cle string, sp string, track_id string").write.parquet(d + "/res")
c = ec[ec["recording_msid"] != "bruit"].copy(); c["track_id"] = ["K%02d" % int(m[4:]) for m in c["recording_msid"]]
an2 = c.groupby("track_id").agg(lb_ecoutes=("user_id", "size"), lb_auditeurs=("user_id", "nunique")).reset_index()
spark.createDataFrame(an2, "track_id string, lb_ecoutes long, lb_auditeurs long").write.parquet(d + "/an2")
an2b = an2.copy(); an2b.loc[3, "lb_auditeurs"] += 1
spark.createDataFrame(an2b, "track_id string, lb_ecoutes long, lb_auditeurs long").write.parquet(d + "/an2_altere")
spark.stop()

# attendus independants (pandas)
g = mi.set_index("track_id")["genre"]
c["genre"] = [x if isinstance(x, str) and x.strip() and x.strip().lower() not in ("nan", "none", "null") else "(absent)" for x in c["track_id"].map(g)]
dt = pd.to_datetime(c["date"])
per = {"jour": c["date"], "semaine": (dt - pd.to_timedelta(dt.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d"),
       "mois": c["date"].str[:7], "annee": c["date"].str[:4], "total": pd.Series("tout", index=c.index)}
def attendu(grain, k):
    cle, p = grain.split("_")
    x = pd.DataFrame({"cle": c["track_id"] if cle == "titre" else c["genre"], "p": per[p], "u": c["user_id"]})
    pu = x.groupby(["cle", "p", "u"]).size().rename("n").reset_index()
    cs = pu.groupby(["cle", "p"]).agg(aud=("n", "size"), ec=("n", "sum"), mx=("n", "max")).reset_index()
    cs["pub"] = (cs["aud"] >= k) & (cs["mx"] <= 0.85 * cs["ec"])
    pc = cs.groupby("cle")["pub"].sum()
    return int(cs["pub"].sum()), round(100 * cs.loc[cs["pub"], "ec"].sum() / cs["ec"].sum(), 2), int((pc >= 1).sum()), int((pc >= 2).sum())

env = dict(os.environ, PYSPARK_SUBMIT_ARGS="--master local[2] pyspark-shell")
tot, couv = len(ec), len(c)
def lancer(sortie=None, an2p=None, total=None):
    a = [sys.executable, JOB, d + "/aplati", cur, d + "/res", an2p or d + "/an2",
         sortie or d + "/curated/trois_v/analyse/p7/seuil_k", str(total or tot), str(couv), str(len(an2)), str(NK), "0.5"]
    q = subprocess.run(a, capture_output=True, text=True, env=env)
    return q.returncode, q.stdout + q.stderr[-1500:]

rc, out = lancer(); print(out[:5000])
f = lambda m: re.search(m, out) is not None
T = [("code 0 et P7K_OK", rc == 0 and f("P7K_OK")),
     ("totaux", f(r"ENTREES ecoutes %d ATTENDU %d couvertes %d ATTENDU %d" % (tot, tot, couv, couv))),
     ("temoin AN2 sans ecart", f(r"TEMOIN_AN2 titres %d ATTENDU %d ecarts 0" % (len(an2), len(an2)))),
     ("catalogue", f(r"CATALOGUE titres %d ATTENDU %d" % (NK, NK)))]
for grain in j.GRAINS:
    for k in j.KS:
        cp, pe, c1, c2 = attendu(grain, k)
        m = re.search(r"MESURE %s k %d \S+ cases_pub (\d+) part_cases_%% \S+ part_ecoutes_%% (\S+) cles_1 (\d+) cles_2 (\d+)" % (grain, k), out)
        T.append(("%s k=%d" % (grain, k), m is not None and (int(m.group(1)), float(m.group(2)), int(m.group(3)), int(m.group(4))) == (cp, pe, c1, c2)))
m = re.search(r"GRAIN titre_jour .* exclues_dominance_k11 (\d+)", out)
T.append(("dominance : la case de K00 est exclue a k=11", m is not None and int(m.group(1)) >= 1))
rc2, out2 = lancer(an2p=d + "/an2_altere")
T.append(("temoin altere -> echec", rc2 == 1 and "P7K_ECHEC" in out2 and "ecarts 1" in out2))
rc3, out3 = lancer(sortie=d + "/raw/listenbrainz/trois_v/analyse/p7")
T.append(("sortie sous listenbrainz/ -> refus sans lecture", rc3 == 2 and "CHEMINS_REFUSES" in out3 and "CORRESPONDANCE" not in out3))
T.append(("aucune ecriture hors sortie", sorted(os.listdir(d)) == ["an2", "an2_altere", "aplati", "cur", "curated", "res"]))
rc4, out4 = lancer(total=tot + 1)
T.append(("total attendu faux -> echec", rc4 == 1 and "P7K_ECHEC" in out4))
T.append(("choisir : regle", j.choisir({("titre_jour", 11): {"part_catalogue_tendance": .1}, ("titre_semaine", 11): {"part_catalogue_tendance": .2},
                                        ("titre_mois", 11): {"part_catalogue_tendance": .6}, ("titre_annee", 11): {"part_catalogue_tendance": .9}}, .5) == "titre_mois"))
T.append(("publiable : 12 auditeurs dont un a 90 %", j.publiable(12, 100, 90, 11) is False and j.publiable(12, 100, 85, 11) is True and j.publiable(10, 100, 10, 11) is False))
ok = sum(1 for _, v in T if v)
for n, v in T:
    if not v: print("ECHEC", n)
print("TESTS %d/%d" % (ok, len(T)))
sys.exit(0 if ok == len(T) else 1)
