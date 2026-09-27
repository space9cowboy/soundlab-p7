"use client";
import { Barres, BarresH, Courbes, Matrice, TableDonnees, Tuiles } from "./graphiques";
import evaluation from "./donnees/evaluation.json";
import shap from "./donnees/shap.json";
import seuilK from "./donnees/seuil_k.json";
import derive from "./donnees/derive.json";
import representativite from "./donnees/representativite.json";
import production from "./donnees/production.json";

const S = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];
const pct = (v) => `${(v * 100).toLocaleString("fr-FR", { maximumFractionDigits: 0 })} %`;
const num = (v, d = 2) => v.toLocaleString("fr-FR", { maximumFractionDigits: d });

export function OngletModele() {
  const e = evaluation, mc = e.matrice_confusion;
  const fprSeuil = mc.faux_positifs / (mc.faux_positifs + mc.vrais_negatifs);
  const rocX = e.roc.map((p) => p.fpr);
  const centres = e.histogramme.bornes.slice(0, -1).map((b, i) => (b + e.histogramme.bornes[i + 1]) / 2);
  const nS = e.histogramme.succes.reduce((a, b) => a + b, 0), nA = e.histogramme.autres.reduce((a, b) => a + b, 0);
  const groupes = { artiste: S[0], contexte: S[1], audio: S[2] };
  return (
    <>
      <p className="sous">Toutes les courbes de cette page viennent de prédictions <b>hors pli</b> : chaque titre est noté par un modèle qui ne l'a pas vu, et les plis sont groupés par artiste. {e.titres.toLocaleString("fr-FR")} titres, {pct(e.taux_base)} de succès.</p>
      <Tuiles items={[
        { titre: "AUC (validation croisée par artiste)", valeur: `${num(e.auc_moyenne, 4)} ± ${num(e.auc_ecart_type, 4)}`, note: `Plis : ${e.auc_par_pli.map((a) => num(a, 3)).join(" · ")}` },
        { titre: "Rappel au seuil", valeur: pct(e.rappel_au_seuil), note: "des succès réels sont repérés" },
        { titre: "Précision au seuil", valeur: pct(e.precision_au_seuil), note: `contre ${pct(e.taux_base)} au hasard` },
        { titre: "Gain sur le hasard", valeur: `× ${num(e.precision_au_seuil / e.taux_base, 2)}`, note: `seuil ${num(e.seuil, 3)}` },
      ]} />
      <div className="grille-graphiques">
        <div>
          <Courbes titre="Courbe ROC (hors pli)" x={rocX} carres yMin={0} yMax={1} yFormat={pct} xTitre="Taux de faux positifs" yTitre="Taux de vrais positifs"
            xEtiquettes={rocX.map(pct)} xFormatNum={pct}
            series={[{ nom: "Modèle", couleur: S[0], valeurs: e.roc.map((p) => p.tpr), sansEtiquette: true }, { nom: "Hasard", couleur: "var(--texte-2)", valeurs: rocX, pointille: true, sansEtiquette: true }]}
            references={[{ nom: `seuil ${num(e.seuil, 2)}`, x: fprSeuil }]} />
          <p className="note">AUC globale hors pli {num(e.auc_globale_hors_pli, 4)}. La ligne verticale marque le point de fonctionnement retenu (rappel {pct(e.rappel_au_seuil)}, faux positifs {pct(fprSeuil)}).</p>
        </div>
        <div>
          <Matrice titre="Matrice de confusion au seuil de priorité" mc={mc} seuil={e.seuil} />
          <p className="note">Le seuil est abaissé sous 0,5 pour viser un rappel de 75 % : pour un label, rater un futur succès coûte plus cher que promouvoir un titre de trop.</p>
        </div>
        <div>
          <Courbes titre="Précision et rappel selon le seuil" x={e.seuils.map((s) => s.seuil)} xEtiquettes={e.seuils.map((s) => num(s.seuil, 2))} yMax={1} yFormat={pct} xTitre="Seuil de score"
            series={[{ nom: "Précision", couleur: S[0], valeurs: e.seuils.map((s) => s.precision) }, { nom: "Rappel", couleur: S[1], valeurs: e.seuils.map((s) => s.rappel) }]}
            references={[{ nom: "seuil retenu", x: e.seuils.findIndex((s) => s.seuil >= e.seuil) }]} />
        </div>
        <div>
          <Courbes titre="Répartition des scores selon la réalité" x={centres} xEtiquettes={centres.map((c) => num(c, 2))} yMax={Math.ceil(Math.max(...e.histogramme.succes.map((v) => v / nS), ...e.histogramme.autres.map((v) => v / nA)) * 20) / 20} yFormat={pct} xTitre="Score du modèle"
            series={[{ nom: "Succès réels", couleur: S[0], valeurs: e.histogramme.succes.map((v) => v / nS), points: true, sansEtiquette: true }, { nom: "Autres titres", couleur: S[1], valeurs: e.histogramme.autres.map((v) => v / nA), points: true, sansEtiquette: true }]} />
          <p className="note">Part des titres de chaque groupe par tranche de score. Plus les deux courbes sont séparées, mieux le modèle distingue les succès.</p>
        </div>
        <div>
          <Barres titre="Taux de succès par décile de score" etiquettes={e.deciles.map((d) => `D${d.decile}`)} valeurs={e.deciles.map((d) => d.taux_succes)} couleur={S[0]} yMax={1} yFormat={pct}
            reference={{ y: e.taux_base, nom: "hasard" }} xTitre="D1 = 10 % des titres les mieux notés" detail={(i) => <div>{e.deciles[i].titres.toLocaleString("fr-FR")} titres</div>} />
        </div>
        <div>
          <BarresH titre="Variables les plus influentes (SHAP, |valeur| moyenne)" xMax={0.12} gauche={205} xFormat={(v) => num(v, 3)}
            series={[{ nom: "Historique de l'artiste", couleur: S[0] }, { nom: "Contexte", couleur: S[1] }, { nom: "Audio", couleur: S[2] }]}
            lignes={shap.variables.map((v) => ({ nom: v.variable, valeurs: [v.shap_moyen], couleurs: [groupes[v.groupe]], note: `effet ${v.sens > 0 ? "croissant" : "décroissant"} (corrélation ${num(v.sens, 2)})` }))} />
          <p className="note">Les deux variables d'historique de l'artiste pèsent ensemble environ 9 fois plus que la meilleure variable audio. Le modèle s'appuie sur l'artiste ; il ne dit pas que l'artiste cause le succès. {shap.methode}.</p>
        </div>
        <div>
          <BarresH titre="Ablation : AUC selon les variables utilisées" xMax={1} xFormat={(v) => num(v, 4)} series={[{ nom: "AUC", couleur: S[0] }]}
            lignes={shap.ablation.map((a) => ({ nom: a.variables.replace(/ \(\d+\)/, ""), valeurs: [a.auc] }))} hauteurLigne={34} gauche={180} />
          <p className="note">{shap.ablation_methode}. Le son seul prédit à peine mieux que le hasard (0,5).</p>
        </div>
      </div>
      <TableDonnees colonnes={["Décile", "Taux de succès", "Titres"]} lignes={e.deciles.map((d) => [`D${d.decile}`, d.taux_succes, d.titres])} titre="Voir les données des déciles" />
      <TableDonnees colonnes={["Variable", "Groupe", "SHAP moyen", "Sens"]} lignes={shap.variables.map((v) => [v.variable, v.groupe, v.shap_moyen, v.sens])} titre="Voir les données SHAP" />
    </>
  );
}

export function OngletDonnees() {
  const ks = [...new Set(seuilK.points.map((p) => p.k))].sort((a, b) => a - b);
  const grains = ["jour", "semaine", "mois", "annee"];
  const noms = { jour: "Titre × jour", semaine: "Titre × semaine", mois: "Titre × mois (retenu)", annee: "Titre × année" };
  const val = (g, k, c) => seuilK.points.find((p) => p.granularite === g && p.k === k)[c];
  const pts = derive.points;
  const iSurv = pts.findIndex((p) => p.periode >= derive.debut_surveillance);
  const r = representativite;
  return (
    <>
      <div className="grille-graphiques">
        <div>
          <Courbes titre="Seuil k : part du catalogue qui garde une tendance" x={ks} xEtiquettes={ks.map((k) => `k = ${k}`)} yMax={100} yFormat={(v) => `${num(v, 0)} %`} xTitre="Nombre minimal d'auditeurs distincts par case"
            series={grains.map((g, i) => ({ nom: noms[g], couleur: S[i], valeurs: ks.map((k) => val(g, k, "catalogue_tendance")), points: true }))}
            references={[{ nom: "critère 50 %", y: seuilK.critere }, { nom: "k retenu", x: ks.indexOf(seuilK.k_retenu) }]} />
          <p className="note">Critère fixé avant la mesure : au moins 50 % des 50 683 titres gardent une tendance. Avec k = 11, seul le grain mensuel ou annuel le respecte ; on agrège plutôt que de baisser k. Source : {seuilK.source}.</p>
        </div>
        <div>
          <Courbes titre="Seuil k : part des écoutes publiables" x={ks} xEtiquettes={ks.map((k) => `k = ${k}`)} yMax={100} yFormat={(v) => `${num(v, 0)} %`}
            series={grains.map((g, i) => ({ nom: noms[g], couleur: S[i], valeurs: ks.map((k) => val(g, k, "part_ecoutes")), points: true }))}
            references={[{ nom: "k retenu", x: ks.indexOf(seuilK.k_retenu) }]} />
          <p className="note">Au grain mensuel et k = 11, 80 % des écoutes restent publiables ; au grain journalier, 6 % seulement.</p>
        </div>
        <div className="large">
          <Courbes titre="Dérive : écart de répartition des genres entre ListenBrainz et Kaggle, par mois" x={pts.map((p) => p.periode)} yMin={0.18} yMax={0.28} yFormat={(v) => num(v, 2)} etiquettesX={8} hauteur={260} yTitre="TVD genre" largeur={960}
            series={[{ nom: "TVD mensuelle", couleur: S[0], valeurs: pts.map((p) => p.tvd_genre) }]}
            references={[{ nom: `seuil ${num(derive.seuil, 4)}`, y: derive.seuil }]} zones={[{ nom: "surveillance 2016", de: iSurv, a: pts.length - 1 }]} />
          <p className="note">Seuil d'alerte = 95e centile des mois 2005-2015, fixé avant la mesure. L'écart croît depuis 2010 ; 9 mois de 2016 sur 12 dépassent le seuil, et l'alerte de décembre 2016 a déclenché le réentraînement ({derive.source}).</p>
        </div>
        <div className="large">
          <BarresH titre={`Représentativité : part des écoutes par genre (${r.titres_communs.toLocaleString("fr-FR")} titres communs, TVD ${num(r.tvd, 4)})`} xMax={Math.ceil(Math.max(...r.genres.map((g) => Math.max(g.kaggle, g.listenbrainz))) / 10) * 10} xFormat={(v) => `${num(v, 1)} %`} largeur={960} gauche={120}
            series={[{ nom: "Kaggle (Last.fm)", couleur: S[0] }, { nom: "ListenBrainz", couleur: S[1] }]}
            lignes={r.genres.map((g) => ({ nom: g.genre, valeurs: [g.kaggle, g.listenbrainz], note: g.kaggle ? `rapport ListenBrainz / Kaggle : × ${num(g.listenbrainz / g.kaggle, 2)}` : "" }))} />
          <p className="note">ListenBrainz sur-représente le metal, le blues, le jazz et le punk, et sous-représente la country, le latin, la pop et le rap : la cible « succès » dépend du public qui la mesure.</p>
        </div>
      </div>
      <TableDonnees colonnes={["Granularité", "k", "Cases publiables %", "Écoutes %", "Catalogue avec tendance %"]} lignes={seuilK.points.map((p) => [p.granularite, p.k, p.part_cases, p.part_ecoutes, p.catalogue_tendance])} titre="Voir les données du seuil k" />
      <TableDonnees colonnes={["Mois", "TVD genre"]} lignes={pts.map((p) => [p.periode, p.tvd_genre])} titre="Voir les données de dérive" />
      <TableDonnees colonnes={["Genre", "Kaggle %", "ListenBrainz %"]} lignes={r.genres.map((g) => [g.genre, g.kaggle, g.listenbrainz])} titre="Voir les données de représentativité" />
    </>
  );
}

export function OngletProduction() {
  const p = production, h = p.hpa;
  return (
    <>
      <Tuiles items={[
        { titre: "Test de charge (8 min)", valeur: `${p.charge.requetes.toLocaleString("fr-FR")} requêtes`, note: `${p.charge.echecs} échec · ${num(p.charge.debit_moyen, 1)} req/s en moyenne` },
        { titre: "Latence p50 / p95", valeur: `${num(p.charge.p50_ms, 1)} / ${p.charge.p95_ms} ms`, note: `maximum ${num(p.charge.max_s, 2)} s (une requête)` },
        { titre: "Mise à jour sans coupure", valeur: `${p.rollout.reussies} / ${p.rollout.requetes}`, note: "réponses 200 pendant le remplacement des pods" },
        { titre: "Cycle ML automatisé", valeur: `v${p.dag.version_avant} → v${p.dag.version_apres}`, note: `dérive, alerte, réentraînement (${num(p.dag.reentrainement_s, 1)} s), promotion` },
      ]} />
      <div className="grille-graphiques">
        <div className="large">
          <Courbes titre="Autoscaling : utilisation CPU moyenne des pods de l'API" x={h.map((v) => v.heure)} xEtiquettes={h.map((v) => v.heure.slice(0, 5))} yMax={100} yFormat={(v) => `${num(v, 0)} %`} etiquettesX={8} largeur={960}
            series={[{ nom: "CPU", couleur: S[0], valeurs: h.map((v) => v.cpu) }]} references={[{ nom: "cible 60 %", y: p.cible_cpu }]} />
        </div>
        <div className="large">
          <Courbes titre="Autoscaling : nombre de réplicas de l'API" x={h.map((v) => v.heure)} xEtiquettes={h.map((v) => v.heure.slice(0, 5))} yMin={0} yMax={4} yFormat={(v) => num(v, 0)} etiquettesX={8} hauteur={180} largeur={960}
            series={[{ nom: "Réplicas", couleur: S[1], valeurs: h.map((v) => v.replicas) }]} />
          <p className="note">Relevé toutes les 10 s pendant le test de charge du 27/09 (cluster kind, 3 nœuds). À 14:48:36 le CPU atteint 70 % : un 3e réplica démarre, l'utilisation retombe à 44 %. Retour à 2 réplicas à 14:51:18, après 60 s de stabilisation.</p>
        </div>
      </div>
      <TableDonnees colonnes={["Heure", "CPU %", "Réplicas"]} lignes={h.map((v) => [v.heure, v.cpu, v.replicas])} titre="Voir le relevé d'autoscaling" />
    </>
  );
}
