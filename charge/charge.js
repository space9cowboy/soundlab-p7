import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE || "http://host.docker.internal:8088/api";
const RPS = Number(__ENV.RPS || 30);
const IDS = (__ENV.IDS || "").split(",").filter(Boolean);

export const options = {
  scenarios: {
    montee: {
      executor: "ramping-arrival-rate", startRate: 5, timeUnit: "1s", preAllocatedVUs: 50, maxVUs: 200,
      stages: [
        { target: Math.round(RPS / 4), duration: "1m" }, { target: RPS, duration: "2m" }, { target: RPS, duration: "3m" }, { target: 2, duration: "2m" },
      ],
    },
  },
  thresholds: { http_req_failed: ["rate<0.01"], http_req_duration: ["p(95)<500"] },
};

const CORPS = JSON.stringify({ danceability: 0.6, energy: 0.7, key: 5, loudness: -6, mode: 1, speechiness: 0.05,
  acousticness: 0.1, instrumentalness: 0.0, liveness: 0.1, valence: 0.5, tempo: 120, time_signature: 4,
  duration_ms: 210000, anciennete: 10, duration_min: 3.5, artist_nb_titres_hors_piste: 12,
  artist_plays_moyen_hors_piste: 300, artist_taux_hits_hors_piste: 0.3 });

export default function () {
  if (Math.random() < 0.5 || IDS.length === 0) {
    const r = http.post(`${BASE}/predict`, CORPS, { headers: { "Content-Type": "application/json" } });
    check(r, { "predict 200": (x) => x.status === 200 });
  } else {
    const r = http.get(`${BASE}/score/${IDS[Math.floor(Math.random() * IDS.length)]}`);
    check(r, { "score 200": (x) => x.status === 200 });
  }
}
