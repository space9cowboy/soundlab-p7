"use client";
import { useCallback, useEffect, useState } from "react";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function lire(chemin, essais = 8) {
  for (let i = 0; i < essais; i++) {
    try {
      const r = await fetch(API + chemin, { cache: "no-store" });
      if (r.ok) return await r.json();
      if (r.status !== 502 && r.status !== 503) throw new Error("HTTP " + r.status);
    } catch (e) {
      if (i === essais - 1) throw e;
    }
    await new Promise((ok) => setTimeout(ok, 8000));
  }
  throw new Error("API injoignable");
}

function Tendance({ points }) {
  if (!points || points.length < 2) return <p className="sous">Pas assez de périodes publiables pour tracer une tendance.</p>;
  const L = 640, H = 200, m = 36;
  const max = Math.max(...points.map((p) => p.ecoutes));
  const x = (i) => m + (i * (L - 2 * m)) / (points.length - 1);
  const y = (v) => H - m + 8 - (v / max) * (H - m - 8 - 8);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.ecoutes).toFixed(1)}`).join(" ");
  const pas = Math.max(1, Math.ceil(points.length / 6)), n = points.length;
  const etiquettes = points.filter((_, i) => i === n - 1 || (i % pas === 0 && n - 1 - i >= pas / 2));
  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${L} ${H}`} width="100%" role="img" aria-label={`Écoutes par période, de ${points[0].periode} à ${points[points.length - 1].periode}, maximum ${max.toLocaleString("fr-FR")}`}>
        <line x1={m} x2={L - m} y1={H - m + 8} y2={H - m + 8} stroke="currentColor" opacity=".3" />
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth="2" />
        {etiquettes.map((p) => {
          const i = points.indexOf(p);
          return <text key={p.periode} x={x(i)} y={H - 8} textAnchor="middle">{p.periode}</text>;
        })}
        <text x={m} y={14}>{max.toLocaleString("fr-FR")} écoutes</text>
      </svg>
      <figcaption className="sous">Seules les périodes publiables sont tracées (seuil d'auditeurs distincts et règle de dominance).</figcaption>
    </figure>
  );
}

export default function Page() {
  const [version, setVersion] = useState(null);
  const [genres, setGenres] = useState([]);
  const [filtres, setFiltres] = useState({ genre: "", decennie: "", artiste: "" });
  const [titres, setTitres] = useState(null);
  const [tendance, setTendance] = useState(null);
  const [etat, setEtat] = useState("chargement");

  const rechercher = useCallback(async (f) => {
    const q = new URLSearchParams({ limite: "50" });
    if (f.genre) q.set("genre", f.genre);
    if (f.decennie) q.set("decennie", f.decennie);
    if (f.artiste) q.set("artiste", f.artiste);
    const t = await lire("/titres?" + q.toString());
    setTitres(t);
    try {
      const g = await lire("/tendances" + (f.genre ? "?genre=" + encodeURIComponent(f.genre) : ""), 1);
      setTendance(g.points);
    } catch {
      setTendance(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setVersion(await lire("/model-version"));
        setGenres((await lire("/genres")).genres);
        await rechercher(filtres);
        setEtat("pret");
      } catch {
        setEtat("erreur");
      }
    })();
  }, []);

  const exporter = () => {
    if (!titres) return;
    const lignes = [["track_id", "titre", "artiste", "genre", "annee", "score"]].concat(
      titres.titres.map((t) => [t.track_id, t.name ?? "", t.artist ?? "", t.genre ?? "", t.year ?? "", t.score]));
    const csv = lignes.map((l) => l.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "soundlab_scores.csv";
    a.click();
  };

  const seuil = titres?.seuil ?? version?.seuil_recommande;
  return (
    <main>
      <h1>SoundLab — priorités de promotion</h1>
      <p className="sous">Probabilité qu'un titre atteigne le quart supérieur des écoutes. Un score par titre, jamais par personne.</p>

      {etat === "chargement" && <p className="message" role="status">Connexion à l'API… Sur l'offre gratuite, elle peut mettre jusqu'à une minute à se réveiller.</p>}
      {etat === "erreur" && <p className="message" role="alert">L'API ne répond pas. Réessayez dans une minute.</p>}

      {version && (
        <section className="carte bandeau" aria-label="Modèle en service">
          <span>Modèle <b>{version.nom}{version.version != null ? ` v${version.version}` : " (artefact local)"}</b></span>
          <span>AUC validation croisée par artiste <b>{version.auc_cv?.toFixed(4)} ± {version.auc_ecart_type?.toFixed(4)}</b></span>
          <span>Seuil de priorité <b>{seuil?.toFixed(2)}</b></span>
          <span>Entraîné le <b>{version.date_entrainement?.slice(0, 10)}</b></span>
        </section>
      )}

      <form className="filtres" onSubmit={(e) => { e.preventDefault(); rechercher(filtres); }}>
        <label>Genre
          <select value={filtres.genre} onChange={(e) => setFiltres({ ...filtres, genre: e.target.value })}>
            <option value="">Tous</option>
            {genres.map((g) => <option key={g.genre} value={g.genre}>{g.genre} ({g.titres})</option>)}
          </select>
        </label>
        <label>Décennie de sortie
          <select value={filtres.decennie} onChange={(e) => setFiltres({ ...filtres, decennie: e.target.value })}>
            <option value="">Toutes</option>
            {[1950, 1960, 1970, 1980, 1990, 2000, 2010].map((d) => <option key={d} value={d}>{d}s</option>)}
          </select>
        </label>
        <label>Artiste
          <input value={filtres.artiste} maxLength={100} onChange={(e) => setFiltres({ ...filtres, artiste: e.target.value })} />
        </label>
        <button type="submit">Filtrer</button>
        <button type="button" onClick={exporter} disabled={!titres}>Exporter (CSV)</button>
      </form>

      {titres && (
        <section aria-live="polite">
          <h2>Titres les mieux notés ({titres.total})</h2>
          <div className="tableau carte">
            <table>
              <caption className="sous" style={{ textAlign: "left" }}>Triés par score décroissant. « Prioritaire » : score au-dessus du seuil de priorité.</caption>
              <thead><tr><th scope="col">Titre</th><th scope="col">Artiste</th><th scope="col">Genre</th><th scope="col">Année</th><th scope="col">Score</th><th scope="col">Priorité</th></tr></thead>
              <tbody>
                {titres.titres.map((t) => (
                  <tr key={t.track_id}>
                    <td>{t.name ?? t.track_id}</td><td>{t.artist}</td><td>{t.genre ?? "—"}</td><td className="num">{t.year ?? "—"}</td>
                    <td className="num">{t.score.toFixed(3)}<span className="barre" style={{ width: `${Math.round(t.score * 80)}px` }} aria-hidden="true" /></td>
                    <td>{seuil != null && t.score >= seuil ? <span className="pastille">Prioritaire</span> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <h2>Tendance des écoutes ListenBrainz{filtres.genre ? ` — ${filtres.genre}` : ""}</h2>
      <div className="carte">{tendance ? <Tendance points={tendance} /> : <p className="sous">Tendances indisponibles sur cette instance.</p>}</div>

      <footer>
        Données : catalogue Kaggle « Million Song Dataset + Spotify + Last.fm » (CC BY-NC 4.0) ; écoutes ListenBrainz (CC0) ;
        étiquettes de genre MusicBrainz (CC BY-NC-SA). Usage non commercial uniquement. Aucune donnée d'auditeur n'est affichée ;
        les agrégats d'écoutes ne sont publiés qu'au-dessus d'un seuil d'auditeurs distincts. Projet de certification — SoundLab Analytics est une société fictive.
      </footer>
    </main>
  );
}
