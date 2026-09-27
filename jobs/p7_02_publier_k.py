import sys, time
t_app = time.time()

# P7-02 : cases publiables a k = 11 (decision du 27/09 d'apres p7_01) pour genre x mois et titre x mois.
# Meme lecture que p7_01 ; la table (titre, jeton, jour) reste sur disque ephemere, jamais ecrite sur S3.
# Sortie : (genre, periode, ecoutes) et (track_id, periode, ecoutes), sans nombre d'auditeurs ni jeton.

K = 11
DOMINANCE = 0.85


def controler_chemins(sortie):
    return "/trois_v/analyse/" in sortie and "/listenbrainz/" not in sortie


if __name__ == "__main__":
    (aplati, cur, res, sortie, total_att, couv_att, genre_att, titre_att) = sys.argv[1:9]
    total_att, couv_att, genre_att, titre_att = int(total_att), int(couv_att), int(genre_att), int(titre_att)
    if not controler_chemins(sortie):
        print("CHEMINS_REFUSES", flush=True)
        sys.exit(2)
    from pyspark.sql import SparkSession, functions as F
    from pyspark import StorageLevel
    spark = SparkSession.builder.appName("p7_02_publier_k").getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    spark.conf.set("spark.sql.parquet.compression.codec", "zstd")
    col = F.col
    VIDE = F.lit("~")

    def cle_ascii(t):
        return F.when(t.rlike("^[\\x00-\\x7F]*$"), F.nullif(F.regexp_replace(F.lower(t), "[^a-z0-9_]", ""), F.lit("")))

    def sp_extrait(x):
        return (F.when(x.rlike("^[0-9A-Za-z]{22}$"), x)
                 .when(x.rlike("track[/:][0-9A-Za-z]{22}"), F.regexp_extract(x, "track[/:]([0-9A-Za-z]{22})", 1)))

    corr = (spark.read.parquet(res).where(col("track_id").isNotNull())
            .select("recording_msid", F.coalesce("cle", VIDE).alias("k_cle"), F.coalesce("sp", VIDE).alias("k_sp"), "track_id")
            .distinct())
    e = (spark.read.parquet(aplati)
         .select("user_id", "date", "recording_msid",
                 F.coalesce(cle_ascii(F.concat_ws("", col("artist_name"), col("track_name"))), VIDE).alias("k_cle"),
                 F.coalesce(sp_extrait(col("spotify_id")), sp_extrait(col("spotify_track_uri")), VIDE).alias("k_sp")))
    total = e.count()
    base = (e.groupBy("user_id", "date", "recording_msid", "k_cle", "k_sp").agg(F.count(F.lit(1)).alias("n"))
             .join(corr, ["recording_msid", "k_cle", "k_sp"])
             .groupBy("track_id", "user_id", F.date_format("date", "yyyy-MM").alias("periode")).agg(F.sum("n").alias("n"))
             .persist(StorageLevel.DISK_ONLY))
    couv = base.agg(F.sum("n")).first()[0]
    print("ENTREES ecoutes", total, "ATTENDU", total_att, "couvertes", couv, "ATTENDU", couv_att, flush=True)

    mi = spark.read.parquet(cur + "/music_info").select("track_id", "genre").dropDuplicates(["track_id"])
    g_ok = col("genre").isNotNull() & (F.trim(col("genre")) != "") & ~F.lower(F.trim(col("genre"))).isin("nan", "none", "null")
    mi = mi.select("track_id", F.when(g_ok, col("genre")).otherwise(F.lit("(absent)")).alias("genre"))

    def publiables(cle, df):
        c = (df.groupBy(cle, "periode", "user_id").agg(F.sum("n").alias("n"))
               .groupBy(cle, "periode").agg(F.count(F.lit(1)).alias("aud"), F.sum("n").alias("ecoutes"), F.max("n").alias("mx")))
        return c.where((col("aud") >= K) & (col("mx") <= DOMINANCE * col("ecoutes"))).select(cle, "periode", "ecoutes")

    g = publiables("genre", base.join(F.broadcast(mi), "track_id", "left").withColumn("genre", F.coalesce("genre", F.lit("(hors_catalogue)"))))
    t = publiables("track_id", base)
    g.coalesce(1).write.mode("overwrite").parquet(sortie + "/genre_mois")
    t.repartition(8).write.mode("overwrite").parquet(sortie + "/titre_mois")
    rg, rt = spark.read.parquet(sortie + "/genre_mois"), spark.read.parquet(sortie + "/titre_mois")
    ng, nt = rg.count(), rt.count()
    colonnes_ok = sorted(rg.columns) == ["ecoutes", "genre", "periode"] and sorted(rt.columns) == ["ecoutes", "periode", "track_id"]
    print("ECRIT genre_mois", ng, "ATTENDU", genre_att, "titre_mois", nt, "ATTENDU", titre_att, "colonnes_ok", colonnes_ok, flush=True)
    base.unpersist()
    ok = total == total_att and couv == couv_att and ng == genre_att and nt == titre_att and colonnes_ok
    print("P7P_OK" if ok else "P7P_ECHEC", "duree_s", round(time.time() - t_app, 1), flush=True)
    if not ok:
        sys.exit(1)
