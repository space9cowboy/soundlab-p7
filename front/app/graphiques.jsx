"use client";
import { useRef, useState } from "react";

const LARGEUR = 640, M = { h: 16, d: 96, b: 36, g: 48 };
const fmt = (v, d = 2) => (typeof v === "number" ? v.toLocaleString("fr-FR", { maximumFractionDigits: d }) : v);

function Infobulle({ pos, children }) {
  if (!pos) return null;
  return <div className="infobulle" style={{ left: `${pos.x}%`, top: `${pos.y}%` }} role="status">{children}</div>;
}

export function Legende({ series }) {
  if (series.length < 2) return null;
  return (
    <ul className="legende">
      {series.map((s) => (
        <li key={s.nom}><span className="pastille-serie" style={{ background: s.couleur, borderStyle: s.pointille ? "dashed" : "solid" }} />{s.nom}</li>
      ))}
    </ul>
  );
}

export function TableDonnees({ colonnes, lignes, titre = "Voir les données" }) {
  return (
    <details className="table-donnees">
      <summary>{titre}</summary>
      <div className="tableau">
        <table>
          <thead><tr>{colonnes.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
          <tbody>{lignes.map((l, i) => <tr key={i}>{l.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : ""}>{fmt(v, 4)}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </details>
  );
}

function axeY(yMin, yMax, n = 4) {
  return Array.from({ length: n + 1 }, (_, i) => yMin + ((yMax - yMin) * i) / n);
}

// Courbes : x numerique ou categoriel (index), une seule echelle y
export function Courbes({ titre, series, x, xEtiquettes, yMin = 0, yMax, yFormat = (v) => fmt(v), references = [], zones = [], hauteur = 240, etiquettesX = 6, xTitre, yTitre, carres = false, xFormatNum , largeur = LARGEUR }) {
  const L = largeur;
  const ref = useRef(null);
  const [survol, setSurvol] = useState(null);
  const H = hauteur;
  const n = x.length;
  const xMin = carres ? x[0] : 0, xMax = carres ? x[n - 1] : n - 1;
  const sx = (i) => M.g + ((carres ? x[i] : i) - xMin) / (xMax - xMin || 1) * (L - M.g - M.d);
  const sxv = (v) => M.g + (v - xMin) / (xMax - xMin || 1) * (L - M.g - M.d);
  const sy = (v) => H - M.b - ((v - yMin) / (yMax - yMin)) * (H - M.b - M.h);
  const pas = Math.max(1, Math.ceil(n / etiquettesX));
  const bouger = (e) => {
    const r = ref.current.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * L;
    let meilleur = 0;
    for (let i = 0; i < n; i++) if (Math.abs(sx(i) - px) < Math.abs(sx(meilleur) - px)) meilleur = i;
    setSurvol(meilleur);
  };
  return (
    <figure className="graphique">
      <figcaption>{titre}</figcaption>
      <Legende series={series} />
      <div className="zone">
        <svg ref={ref} viewBox={`0 0 ${L} ${H}`} width="100%" role="img" aria-label={titre} onPointerMove={bouger} onPointerLeave={() => setSurvol(null)}>
          {zones.map((z) => (
            <g key={z.nom}>
              <rect x={sx(z.de)} y={M.h} width={sx(z.a) - sx(z.de)} height={H - M.b - M.h} className="zone-fond" />
              <text x={sx(z.de) + 4} y={M.h + 12} className="etiquette">{z.nom}</text>
            </g>
          ))}
          {axeY(yMin, yMax).map((v) => (
            <g key={v}>
              <line x1={M.g} x2={L - M.d} y1={sy(v)} y2={sy(v)} className="grille" />
              <text x={M.g - 6} y={sy(v) + 4} textAnchor="end" className="etiquette">{yFormat(v)}</text>
            </g>
          ))}
          {carres && axeY(xMin, xMax).map((v) => (
            <text key={"t" + v} x={sxv(v)} y={H - M.b + 16} textAnchor="middle" className="etiquette">{xFormatNum ? xFormatNum(v) : fmt(v)}</text>
          ))}
          {!carres && x.map((v, i) => (i % pas === 0 || i === n - 1) && !(i !== n - 1 && n - 1 - i < pas / 2) ? (
            <text key={i} x={sx(i)} y={H - M.b + 16} textAnchor="middle" className="etiquette">{xEtiquettes ? xEtiquettes[i] : v}</text>
          ) : null)}
          {xTitre && <text x={(M.g + L - M.d) / 2} y={H - 4} textAnchor="middle" className="etiquette">{xTitre}</text>}
          {yTitre && <text x={M.g} y={M.h - 4} className="etiquette">{yTitre}</text>}
          {references.map((r) => r.x !== undefined ? (
            <g key={r.nom}>
              <line x1={sxv(r.x)} x2={sxv(r.x)} y1={M.h} y2={H - M.b} className="reference" />
              <text x={sxv(r.x) + 4} y={M.h + 24} className="etiquette">{r.nom}</text>
            </g>
          ) : (
            <g key={r.nom}>
              <line x1={M.g} x2={L - M.d} y1={sy(r.y)} y2={sy(r.y)} className="reference" />
              <text x={L - M.d + 4} y={sy(r.y) + 4} className="etiquette">{r.nom}</text>
            </g>
          ))}
          {series.map((s) => {
            const d = s.valeurs.map((v, i) => (v == null ? null : `${sx(i).toFixed(1)},${sy(v).toFixed(1)}`)).filter(Boolean);
            const dernier = s.valeurs.length - 1;
            return (
              <g key={s.nom}>
                <polyline points={d.join(" ")} fill="none" stroke={s.couleur} strokeWidth="2" strokeDasharray={s.pointille ? "5 4" : undefined} strokeLinejoin="round" />
                {s.points && s.valeurs.map((v, i) => <circle key={i} cx={sx(i)} cy={sy(v)} r="4" fill={s.couleur} stroke="var(--surface)" strokeWidth="2" />)}
                {series.length > 1 && !s.sansEtiquette && <text x={sx(dernier) + 8} y={sy(s.valeurs[dernier]) + 4} className="etiquette-serie">{s.nom}</text>}
              </g>
            );
          })}
          {survol !== null && (
            <g>
              <line x1={sx(survol)} x2={sx(survol)} y1={M.h} y2={H - M.b} className="curseur" />
              {series.map((s) => s.valeurs[survol] != null && <circle key={s.nom} cx={sx(survol)} cy={sy(s.valeurs[survol])} r="5" fill={s.couleur} stroke="var(--surface)" strokeWidth="2" />)}
            </g>
          )}
        </svg>
        <Infobulle pos={survol !== null ? { x: (sx(survol) / L) * 100, y: 8 } : null}>
          {survol !== null && <><b>{xEtiquettes ? xEtiquettes[survol] : x[survol]}</b>
          {series.map((s) => <div key={s.nom}>{s.nom} : {s.valeurs[survol] == null ? "—" : yFormat(s.valeurs[survol])}</div>)}</>}
        </Infobulle>
      </div>
    </figure>
  );
}

// Barres verticales (une serie) avec ligne de reference optionnelle
export function Barres({ titre, etiquettes, valeurs, couleur, yMax, yFormat = (v) => fmt(v), reference, hauteur = 220, xTitre, detail , largeur = LARGEUR }) {
  const L = largeur;
  const [survol, setSurvol] = useState(null);
  const H = hauteur, n = valeurs.length;
  const pas = (L - M.g - M.d) / n, lb = Math.max(4, pas - 6);
  const sy = (v) => H - M.b - (v / yMax) * (H - M.b - M.h);
  return (
    <figure className="graphique">
      <figcaption>{titre}</figcaption>
      <div className="zone">
        <svg viewBox={`0 0 ${L} ${H}`} width="100%" role="img" aria-label={titre} onPointerLeave={() => setSurvol(null)}>
          {axeY(0, yMax).map((v) => (
            <g key={v}>
              <line x1={M.g} x2={L - M.d} y1={sy(v)} y2={sy(v)} className="grille" />
              <text x={M.g - 6} y={sy(v) + 4} textAnchor="end" className="etiquette">{yFormat(v)}</text>
            </g>
          ))}
          {valeurs.map((v, i) => {
            const x = M.g + i * pas + (pas - lb) / 2, y = sy(v), h = Math.max(0, H - M.b - y);
            return (
              <g key={i} onPointerEnter={() => setSurvol(i)}>
                <rect x={M.g + i * pas} y={M.h} width={pas} height={H - M.b - M.h} fill="transparent" />
                <path d={`M${x},${H - M.b} V${y + Math.min(4, h)} q0,-4 4,-4 h${lb - 8} q4,0 4,4 V${H - M.b} Z`} fill={couleur} opacity={survol === null || survol === i ? 1 : 0.55} />
                <text x={x + lb / 2} y={H - M.b + 16} textAnchor="middle" className="etiquette">{etiquettes[i]}</text>
              </g>
            );
          })}
          {reference && (
            <g>
              <line x1={M.g} x2={L - M.d} y1={sy(reference.y)} y2={sy(reference.y)} className="reference" />
              <text x={L - M.d + 4} y={sy(reference.y) + 4} className="etiquette">{reference.nom}</text>
            </g>
          )}
          {xTitre && <text x={(M.g + L - M.d) / 2} y={H - 4} textAnchor="middle" className="etiquette">{xTitre}</text>}
        </svg>
        <Infobulle pos={survol !== null ? { x: ((M.g + (survol + 0.5) * pas) / L) * 100, y: 8 } : null}>
          {survol !== null && <><b>{etiquettes[survol]}</b><div>{yFormat(valeurs[survol])}</div>{detail && detail(survol)}</>}
        </Infobulle>
      </div>
    </figure>
  );
}

// Barres horizontales groupees (1 ou 2 valeurs par ligne)
export function BarresH({ titre, lignes, series, xMax, xFormat = (v) => fmt(v), hauteurLigne = 26, gauche = 150 , largeur = LARGEUR }) {
  const L = largeur;
  const [survol, setSurvol] = useState(null);
  const G = gauche, D = 72, H = M.h + lignes.length * hauteurLigne + 24;
  const sx = (v) => G + (v / xMax) * (L - G - D);
  const nv = lignes[0].valeurs.length;
  const ep = nv === 1 ? 14 : 9;
  return (
    <figure className="graphique">
      <figcaption>{titre}</figcaption>
      <Legende series={series} />
      <div className="zone">
        <svg viewBox={`0 0 ${L} ${H}`} width="100%" role="img" aria-label={titre} onPointerLeave={() => setSurvol(null)}>
          {axeY(0, xMax).map((v) => (
            <g key={v}>
              <line x1={sx(v)} x2={sx(v)} y1={M.h - 4} y2={H - 22} className="grille" />
              <text x={sx(v)} y={H - 6} textAnchor="middle" className="etiquette">{xFormat(v)}</text>
            </g>
          ))}
          {lignes.map((l, i) => {
            const y0 = M.h + i * hauteurLigne;
            return (
              <g key={l.nom} onPointerEnter={() => setSurvol(i)}>
                <rect x={0} y={y0} width={L} height={hauteurLigne} fill="transparent" />
                <text x={G - 8} y={y0 + hauteurLigne / 2 + 4} textAnchor="end" className="etiquette-ligne">{l.nom}</text>
                {l.valeurs.map((v, j) => {
                  const y = y0 + (hauteurLigne - ep * nv - 2 * (nv - 1)) / 2 + j * (ep + 2);
                  const w = Math.max(1, sx(v) - G);
                  return <path key={j} d={`M${G},${y} H${G + Math.max(0, w - 4)} q4,0 4,4 V${y + ep - 4} q0,4 -4,4 H${G} Z`} fill={l.couleurs ? l.couleurs[j] : series[j].couleur} opacity={survol === null || survol === i ? 1 : 0.55} />;
                })}
                {nv === 1 && <text x={sx(l.valeurs[0]) + 6} y={y0 + hauteurLigne / 2 + 4} className="etiquette">{xFormat(l.valeurs[0])}</text>}
              </g>
            );
          })}
        </svg>
        <Infobulle pos={survol !== null ? { x: 60, y: ((M.h + survol * hauteurLigne) / H) * 100 } : null}>
          {survol !== null && <><b>{lignes[survol].nom}</b>
          {series.length > 1 || !lignes[survol].couleurs ? series.map((s, j) => <div key={s.nom}>{s.nom} : {xFormat(lignes[survol].valeurs[j])}</div>) : <div>{xFormat(lignes[survol].valeurs[0])}</div>}
          {lignes[survol].note && <div>{lignes[survol].note}</div>}</>}
        </Infobulle>
      </div>
    </figure>
  );
}

export function Matrice({ titre, mc, seuil }) {
  const cases = [
    ["Succès réel", "Prioritaire", mc.vrais_positifs, "vrais positifs"], ["Succès réel", "Non prioritaire", mc.faux_negatifs, "faux négatifs"],
    ["Pas un succès", "Prioritaire", mc.faux_positifs, "faux positifs"], ["Pas un succès", "Non prioritaire", mc.vrais_negatifs, "vrais négatifs"],
  ];
  const max = Math.max(...cases.map((c) => c[2]));
  const total = cases.reduce((a, c) => a + c[2], 0);
  return (
    <figure className="graphique">
      <figcaption>{titre}</figcaption>
      <table className="matrice">
        <caption className="sous">Seuil de priorité {fmt(seuil, 3)} — lignes : réalité ; colonnes : décision du modèle.</caption>
        <thead><tr><td /><th scope="col">Prioritaire</th><th scope="col">Non prioritaire</th></tr></thead>
        <tbody>
          {["Succès réel", "Pas un succès"].map((r) => (
            <tr key={r}>
              <th scope="row">{r}</th>
              {cases.filter((c) => c[0] === r).map((c) => {
                const t = c[2] / max;
                return (
                  <td key={c[1]} style={{ background: `color-mix(in srgb, var(--s1) ${Math.round(12 + t * 60)}%, var(--surface))`, color: t > 0.55 ? "#fff" : "var(--texte)" }}>
                    <b>{fmt(c[2], 0)}</b><br /><small>{c[3]} · {fmt((100 * c[2]) / total, 1)} %</small>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export function Tuiles({ items }) {
  return (
    <div className="tuiles">
      {items.map((t) => (
        <div key={t.titre} className="tuile">
          <div className="tuile-titre">{t.titre}</div>
          <div className="tuile-valeur">{t.valeur}</div>
          {t.note && <div className="tuile-note">{t.note}</div>}
        </div>
      ))}
    </div>
  );
}
