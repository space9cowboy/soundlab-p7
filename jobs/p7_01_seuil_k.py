import sys, time
t_app = time.time()

# P7-01 (action B6) : mesure de l'effet du seuil k sur les agregats ListenBrainz publiables.
# Lit la table aplatie (jetons pseudonymises) et la correspondance d'AN1. Aucune table a jetons n'est ecrite :
# la table (titre, jeton, jour) reste sur le disque ephemere des executeurs (persist DISK_ONLY), detruit avec le job.
# N'ecrit en sortie que des comptages par granularite et par k, sans jeton ni case.

KS = [3, 5, 11, 20, 50]
K_ELIGIBLES = [11, 20, 50]
K_PLANCHER = 11
DOMINANCE = 0.85
TITRE_TEMPORELS = ["titre_jour", "titre_semaine", "titre_mois", "titre_annee"]
GRAINS = TITRE_TEMPORELS + ["titre_total", "genre_jour", "genre_mois"]


def publiable(auditeurs, ecoutes, max_auditeur, k):
    return auditeurs >= k and max_auditeur <= DOMINANCE * ecoutes


def choisir(mesures, critere):
    for g in TITRE_TEMPORELS:
        m = mesures.get((g, K_PLANCHER))
        if m is not None and m["part_catalogue_tendance"] >= critere:
            return g
    return None


def controler_chemins(sortie):
    return "/trois_v/analyse/" in sortie and "/listenbrainz/" not in sortie


if __name__ == "__main__":
    (aplati, cur, res, an2, sortie, total_att, couv_att, trouves_att, catalogue_att, critere) = sys.argv[1:11]
    total_att, couv_att, trouves_att, catalogue_att, critere = (int(total_att), int(couv_att), int(trouves_att),
                                                                 int(catalogue_att), float(critere))
    if not controler_chemins(sortie):
        print("CHEMINS_REFUSES sortie attendue sous /trois_v/analyse/, jamais sous listenbrainz/", flush=True)
        sys.exit(2)
    print("REGLE k_plancher", K_PLANCHER, "dominance", DOMINANCE, "critere_part_catalogue_tendance", critere,
          "ks", KS, "eligibles", K_ELIGIBLES, flush=True)

    from pyspark.sql import SparkSession, functions as F
    from pyspark import StorageLevel
    spark = SparkSession.builder.appName("p7_01_seuil_k").getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    spark.conf.set("spark.sql.parquet.compression.codec", "zstd")
    col = F.col
    VIDE = F.lit("~")

    def cle_ascii(t):
        return F.when(t.rlike("^[\\x00-\\x7F]*$"), F.nullif(F.regexp_replace(F.lower(t), "[^a-z0-9_]", ""), F.lit("")))

    def sp_extrait(x):
        return (F.when(x.rlike("^[0-9A-Za-z]{22}$"), x)
                 .when(x.rlike("track[/:][0-9A-Za-z]{22}"), F.regexp_extract(x, "track[/:]([0-9A-Za-z]{22})", 1)))

    # 1. Correspondance d'AN1 (meme regle que 3v_42)
    corr = (spark.read.parquet(res).where(col("track_id").isNotNull())
            .select("recording_msid", F.coalesce("cle", VIDE).alias("k_cle"), F.coalesce("sp", VIDE).alias("k_sp"), "track_id")
            .distinct())
    ambig = corr.groupBy("recording_msid", "k_cle", "k_sp").agg(F.countDistinct("track_id").alias("n")).where(col("n") > 1).count()
    print("CORRESPONDANCE cles_ambigues", ambig, flush=True)

    # 2. Table (titre, jeton, jour) sur disque ephemere des executeurs, jamais ecrite sur S3
    t0 = time.time()
    e = (spark.read.parquet(aplati)
         .select("user_id", "date", "recording_msid",
                 F.coalesce(cle_ascii(F.concat_ws("", col("artist_name"), col("track_name"))), VIDE).alias("k_cle"),
                 F.coalesce(sp_extrait(col("spotify_id")), sp_extrait(col("spotify_track_uri")), VIDE).alias("k_sp")))
    total = e.count()
    base = (e.groupBy("user_id", "date", "recording_msid", "k_cle", "k_sp").agg(F.count(F.lit(1)).alias("n"))
             .join(corr, ["recording_msid", "k_cle", "k_sp"])
             .groupBy("track_id", "user_id", "date").agg(F.sum("n").alias("n"))
             .persist(StorageLevel.DISK_ONLY))
    couv = base.agg(F.sum("n")).first()[0]
    print("ENTREES ecoutes", total, "ATTENDU", total_att, "couvertes", couv, "ATTENDU", couv_att,
          "duree_s", round(time.time() - t0, 1), flush=True)

    # 3. Dimensions : genre du catalogue (meme normalisation que 3v_42)
    mi = spark.read.parquet(cur + "/music_info").select("track_id", "genre").dropDuplicates(["track_id"])
    catalogue = mi.count()
    g_ok = col("genre").isNotNull() & (F.trim(col("genre")) != "") & ~F.lower(F.trim(col("genre"))).isin("nan", "none", "null")
    mi = mi.select("track_id", F.when(g_ok, col("genre")).otherwise(F.lit("(absent)")).alias("genre"))
    print("CATALOGUE titres", catalogue, "ATTENDU", catalogue_att, flush=True)
    base = base.join(F.broadcast(mi), "track_id", "left").withColumn("genre", F.coalesce("genre", F.lit("(hors_catalogue)")))

    jour = F.date_format("date", "yyyy-MM-dd")
    PERIODE = {"jour": jour, "semaine": F.date_format(F.date_trunc("week", col("date")), "yyyy-MM-dd"),
               "mois": F.date_format("date", "yyyy-MM"), "annee": F.date_format("date", "yyyy"), "total": F.lit("tout")}

    def cases(grain):
        cle, per = grain.split("_")
        cle = "track_id" if cle == "titre" else "genre"
        return (base.select(col(cle).alias("cle"), PERIODE[per].alias("periode"), "user_id", "n")
                .groupBy("cle", "periode", "user_id").agg(F.sum("n").alias("n"))
                .groupBy("cle", "periode").agg(F.count(F.lit(1)).alias("aud"), F.sum("n").alias("ec"), F.max("n").alias("mx")))

    # 4. Temoin : le grain titre_total doit reproduire an2_auditeurs_par_titre (3v_42)
    tt = cases("titre_total").select(col("cle").alias("track_id"), "aud", "ec")
    ref = spark.read.parquet(an2).select("track_id", "lb_auditeurs", "lb_ecoutes")
    cmp_ = tt.join(ref, "track_id", "full")
    ecarts = cmp_.where(col("aud").isNull() | col("lb_auditeurs").isNull()
                        | (col("aud") != col("lb_auditeurs")) | (col("ec") != col("lb_ecoutes"))).count()
    trouves = tt.count()
    print("TEMOIN_AN2 titres", trouves, "ATTENDU", trouves_att, "ecarts", ecarts, flush=True)

    # 5. Mesures : une passe par grain, toutes les valeurs de k a la fois
    mesures, lignes = {}, []
    for g in GRAINS:
        tg = time.time()
        c = cases(g)
        pub = {k: ((col("aud") >= k) & (col("mx") <= DOMINANCE * col("ec"))).cast("long") for k in KS}
        par_cle = c.groupBy("cle").agg(
            F.count(F.lit(1)).alias("cs"), F.sum("ec").alias("ec"), F.sum((col("aud") == 1).cast("long")).alias("un"),
            F.sum(((col("aud") >= K_PLANCHER) & (col("mx") > DOMINANCE * col("ec"))).cast("long")).alias("dom"),
            *[F.sum(pub[k]).alias("c%d" % k) for k in KS], *[F.sum(pub[k] * col("ec")).alias("e%d" % k) for k in KS])
        r = par_cle.agg(
            F.count(F.lit(1)).alias("cles"), F.sum("cs").alias("cs"), F.sum("ec").alias("ec"), F.sum("un").alias("un"),
            F.sum("dom").alias("dom"),
            *[F.sum("c%d" % k).alias("c%d" % k) for k in KS], *[F.sum("e%d" % k).alias("e%d" % k) for k in KS],
            *[F.sum((col("c%d" % k) >= 1).cast("long")).alias("u%d" % k) for k in KS],
            *[F.sum((col("c%d" % k) >= 2).cast("long")).alias("d%d" % k) for k in KS]).first()
        print("GRAIN", g, "cles", r["cles"], "cases", r["cs"], "ecoutes", r["ec"],
              "part_cases_1_auditeur_%", round(100.0 * r["un"] / r["cs"], 2),
              "exclues_dominance_k11", r["dom"], "duree_s", round(time.time() - tg, 1), flush=True)
        for k in KS:
            m = {"grain": g, "k": k, "eligible": k in K_ELIGIBLES, "cles": int(r["cles"]), "cases": int(r["cs"]),
                 "cases_publiables": int(r["c%d" % k]), "part_cases": r["c%d" % k] / float(r["cs"]),
                 "part_ecoutes": r["e%d" % k] / float(r["ec"]),
                 "cles_1_case": int(r["u%d" % k]), "cles_2_cases": int(r["d%d" % k]),
                 "part_catalogue_tendance": (r["d%d" % k] / float(catalogue)) if g.startswith("titre") else None,
                 "part_trouves_tendance": (r["d%d" % k] / float(r["cles"])) if g.startswith("titre") else None}
            mesures[(g, k)] = m
            lignes.append(m)
            print("MESURE", g, "k", k, "eligible" if m["eligible"] else "comparaison",
                  "cases_pub", m["cases_publiables"], "part_cases_%", round(100 * m["part_cases"], 2),
                  "part_ecoutes_%", round(100 * m["part_ecoutes"], 2), "cles_1", m["cles_1_case"], "cles_2", m["cles_2_cases"],
                  "catalogue_tendance_%", None if m["part_catalogue_tendance"] is None else round(100 * m["part_catalogue_tendance"], 2),
                  flush=True)

    choix = choisir(mesures, critere)
    print("CHOIX k", K_PLANCHER, "granularite", choix if choix else "aucune_par_titre_repli_titre_total",
          "critere", critere, flush=True)

    # 6. Ecriture : resultats par (grain, k), sans jeton ni case
    out = spark.createDataFrame(lignes, "grain string, k int, eligible boolean, cles long, cases long, cases_publiables long, "
                                        "part_cases double, part_ecoutes double, cles_1_case long, cles_2_cases long, "
                                        "part_catalogue_tendance double, part_trouves_tendance double")
    out.coalesce(1).write.mode("overwrite").parquet(sortie)
    relu = spark.read.parquet(sortie)
    sans_jeton = "user_id" not in relu.columns and "cle" not in relu.columns
    n_relu = relu.count()
    print("ECRIT resultats", n_relu, "sans_jeton", sans_jeton, flush=True)
    base.unpersist()

    ok = (total == total_att and couv == couv_att and ambig == 0 and catalogue == catalogue_att
          and trouves == trouves_att and ecarts == 0 and sans_jeton and n_relu == len(GRAINS) * len(KS))
    print("P7K_OK" if ok else "P7K_ECHEC", "duree_s", round(time.time() - t_app, 1), flush=True)
    if not ok:
        sys.exit(1)
