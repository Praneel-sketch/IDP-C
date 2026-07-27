/* CityChange — City Time Machine frontend.
 * Vanilla ES6, no build step. Talks to the FastAPI backend under /api.
 */
"use strict";

const STATE_LABELS = {
  water: "Water", vegetation: "Vegetation", crops: "Crops",
  built: "Built-up", bare: "Bare / open", snow_ice: "Snow / ice",
};
const STATE_COLORS = {
  water: "#419BDF", vegetation: "#4C8C4A", crops: "#E4B031",
  built: "#C4281B", bare: "#A59B8F", snow_ice: "#A8EBFF",
};

const el = (id) => document.getElementById(id);
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

/* ---------- map ---------- */
const map = L.map("map", { zoomControl: true }).setView([20, 30], 3);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const state = {
  region: null,      // summary.json of the loaded region
  overlays: null,    // overlays.json manifest
  overlayLayer: null,
  activeLayer: "states",
  yearIdx: 0,
  playTimer: null,
  hotspotMarkers: [],
  aoiRect: null,
};

function overlayUrl(file) {
  return `/api/region/${state.region.region}/overlays/${file}`;
}

function currentOverlayFile() {
  const L_ = state.overlays.layers;
  if (state.activeLayer === "states") {
    const year = state.region.years[state.yearIdx];
    return (L_[`states_${year}`] || {}).file;
  }
  return (L_[state.activeLayer] || {}).file;
}

function refreshOverlay() {
  if (!state.region || !state.overlays) return;
  const file = currentOverlayFile();
  if (!file) return;
  const bounds = state.overlays.bounds;
  const opacity = el("opacity-slider").value / 100;
  if (state.overlayLayer) map.removeLayer(state.overlayLayer);
  state.overlayLayer = L.imageOverlay(overlayUrl(file), bounds, { opacity }).addTo(map);
  renderLegend();
}

function renderLegend() {
  const box = el("legend");
  let entries = [];
  if (state.activeLayer === "states" || state.activeLayer === "change") {
    entries = Object.keys(STATE_LABELS).map((k) => [STATE_LABELS[k], STATE_COLORS[k]]);
    if (state.activeLayer === "change") entries.unshift(["became →", null]);
  } else {
    const legend = (state.overlays.layers[state.activeLayer] || {}).legend || {};
    entries = Object.entries(legend);
  }
  box.innerHTML = entries
    .map(([label, color]) =>
      color
        ? `<span class="key"><span class="swatch" style="background:${color}"></span>${label}</span>`
        : `<span class="key"><strong>${label}</strong></span>`)
    .join("");
  box.classList.toggle("hidden", entries.length === 0);
}

/* ---------- layer chips / time bar ---------- */
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    state.activeLayer = chip.dataset.layer;
    el("timebar").classList.toggle("hidden", state.activeLayer !== "states");
    stopPlay();
    refreshOverlay();
  });
});

el("year-slider").addEventListener("input", (e) => {
  state.yearIdx = +e.target.value;
  el("year-label").textContent = state.region ? state.region.years[state.yearIdx] : "—";
  refreshOverlay();
});
el("opacity-slider").addEventListener("input", () => {
  if (state.overlayLayer) state.overlayLayer.setOpacity(el("opacity-slider").value / 100);
});

function stopPlay() {
  if (state.playTimer) { clearInterval(state.playTimer); state.playTimer = null; el("play-btn").textContent = "▶"; }
}
el("play-btn").addEventListener("click", () => {
  if (state.playTimer) { stopPlay(); return; }
  el("play-btn").textContent = "⏸";
  state.playTimer = setInterval(() => {
    state.yearIdx = (state.yearIdx + 1) % state.region.years.length;
    el("year-slider").value = state.yearIdx;
    el("year-label").textContent = state.region.years[state.yearIdx];
    refreshOverlay();
  }, 900);
});

/* ---------- search ---------- */
let searchTimer = null;
el("search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (q.length < 3) { el("search-results").classList.add("hidden"); return; }
  searchTimer = setTimeout(async () => {
    try {
      const results = await api(`/api/geocode?q=${encodeURIComponent(q)}`);
      const box = el("search-results");
      box.innerHTML = results.map((r, i) =>
        `<div data-i="${i}">${r.display_name}</div>`).join("") || "<div>No results</div>";
      box.classList.remove("hidden");
      box.querySelectorAll("div[data-i]").forEach((d) => {
        d.addEventListener("click", () => {
          const r = results[+d.dataset.i];
          map.flyTo([r.lat, r.lon], 12, { duration: 1.2 });
          box.classList.add("hidden");
        });
      });
    } catch { /* geocode unavailable — typing a place still allows manual pan */ }
  }, 350);
});
document.addEventListener("click", (e) => {
  if (!el("searchbox").contains(e.target)) el("search-results").classList.add("hidden");
});

/* ---------- analyze current view ---------- */
el("analyze-btn").addEventListener("click", async () => {
  const b = map.getBounds();
  let w = b.getWest(), e_ = b.getEast(), s = b.getSouth(), n = b.getNorth();
  // Clamp to ~12 km half-box around the centre to stay well under the API area cap.
  const cLat = (s + n) / 2, cLon = (w + e_) / 2;
  const maxHalfLat = 0.055;
  const maxHalfLon = 0.055 / Math.max(Math.cos(cLat * Math.PI / 180), 0.2);
  s = Math.max(s, cLat - maxHalfLat); n = Math.min(n, cLat + maxHalfLat);
  w = Math.max(w, cLon - maxHalfLon); e_ = Math.min(e_, cLon + maxHalfLon);

  const btn = el("analyze-btn");
  btn.disabled = true;
  showJob("Requesting analysis…");
  try {
    const resp = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ west: w, south: s, east: e_, north: n }),
    });
    if (resp.status === "done") {
      await loadRegion(resp.region);
      hideJob();
    } else {
      await pollJob(resp.job, resp.region);
    }
  } catch (err) {
    showJob(`Analysis failed: ${err.message}`);
    setTimeout(hideJob, 6000);
  } finally {
    btn.disabled = false;
    refreshRegionList();
  }
});

function showJob(text) { const j = el("job-status"); j.textContent = text; j.classList.remove("hidden"); }
function hideJob() { el("job-status").classList.add("hidden"); }

async function pollJob(jobId, regionName) {
  const started = Date.now();
  showJob("Fetching satellite observations and reconstructing history… (30–90 s for a new area)");
  while (true) {
    await new Promise((r) => setTimeout(r, 2500));
    const job = await api(`/api/jobs/${jobId}`);
    if (job.status === "done") { await loadRegion(regionName); hideJob(); return; }
    if (job.status === "error") throw new Error(job.error || "analysis failed");
    const secs = Math.round((Date.now() - started) / 1000);
    showJob(`Analysing… ${secs}s (fetching ${7} years of observations, detecting change events)`);
  }
}

/* ---------- region loading ---------- */
async function refreshRegionList() {
  try {
    const regions = await api("/api/regions");
    const sel = el("region-select");
    const current = sel.value;
    sel.innerHTML = '<option value="">Saved areas…</option>' +
      regions.map((r) => `<option value="${r.region}">${r.display_name}</option>`).join("");
    sel.value = current;
  } catch { /* backend down; leave list */ }
}
el("region-select").addEventListener("change", (e) => {
  if (e.target.value) loadRegion(e.target.value);
});

async function loadRegion(name) {
  const [summary, overlays] = await Promise.all([
    api(`/api/region/${name}/summary`),
    api(`/api/region/${name}/overlays`),
  ]);
  state.region = summary;
  state.overlays = overlays;
  state.yearIdx = summary.years.length - 1;

  const slider = el("year-slider");
  slider.max = summary.years.length - 1;
  slider.value = state.yearIdx;
  el("year-label").textContent = summary.years[state.yearIdx];
  el("timebar").classList.toggle("hidden", state.activeLayer !== "states");

  map.fitBounds(overlays.bounds, { padding: [20, 20] });
  if (state.aoiRect) map.removeLayer(state.aoiRect);
  state.aoiRect = L.rectangle(overlays.bounds, {
    color: "#58a6ff", weight: 1.5, fill: false, dashArray: "5 5",
  }).addTo(map);

  refreshOverlay();
  renderPanel(summary);
  el("region-select").value = name;
}

/* ---------- story panel ---------- */
function renderPanel(s) {
  el("panel-empty").classList.add("hidden");
  el("panel-content").classList.remove("hidden");
  el("region-title").textContent = s.display_name;

  // stat cards: biggest deltas
  const deltas = Object.entries(s.fraction_deltas_first_to_last)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .filter(([, d]) => Math.abs(d) >= 0.001)
    .slice(0, 4);
  const y0 = s.years[0], y1 = s.years[s.years.length - 1];
  el("stat-cards").innerHTML = deltas.map(([name, d]) => {
    const from = s.state_fractions_by_year[name][String(y0)] * 100;
    const to = s.state_fractions_by_year[name][String(y1)] * 100;
    const color = STATE_COLORS[name] || "#9aa7b5";
    return `<div class="stat-card" style="border-left-color:${color}">
      <div class="name">${STATE_LABELS[name] || name}</div>
      <div class="value">${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)} pp</div>
      <div class="detail">${from.toFixed(1)}% → ${to.toFixed(1)}%</div>
    </div>`;
  }).join("") + `<div class="stat-card">
      <div class="name">Confirmed change</div>
      <div class="value">${(s.change_fractions.event_based * 100).toFixed(1)}%</div>
      <div class="detail">of the area, ${y0}–${y1}</div>
    </div>`;

  // peak line
  const peak = s.peak_change_period;
  el("peak-line").textContent = peak
    ? `Change was fastest between ${peak[0]} and ${peak[1]}.`
    : `No persistent change events were detected — this area stayed largely as it was.`;

  renderTrends(s);
  renderVolumes(s);
  renderHotspots(s);
  renderAnomalies(s);
  renderConfidence(s);
}

/* Minimal SVG line chart for state trends. */
function renderTrends(s) {
  const W = 380, H = 190, P = { l: 36, r: 8, t: 10, b: 22 };
  const years = s.years;
  const names = Object.keys(s.state_fractions_by_year)
    .filter((n) => Object.values(s.state_fractions_by_year[n]).some((v) => v > 0.005));
  let maxV = 0;
  names.forEach((n) => years.forEach((y) => {
    maxV = Math.max(maxV, s.state_fractions_by_year[n][String(y)] || 0);
  }));
  maxV = Math.min(1, maxV * 1.15 + 0.02);
  const x = (i) => P.l + (i / (years.length - 1)) * (W - P.l - P.r);
  const y = (v) => H - P.b - (v / maxV) * (H - P.t - P.b);

  let grid = "";
  for (let g = 0; g <= 4; g++) {
    const v = (maxV * g) / 4, yy = y(v);
    grid += `<line x1="${P.l}" y1="${yy}" x2="${W - P.r}" y2="${yy}" stroke="#2c3a4d" stroke-width="0.5"/>
             <text x="${P.l - 4}" y="${yy + 3}" text-anchor="end" font-size="8" fill="#9aa7b5">${Math.round(v * 100)}%</text>`;
  }
  const lines = names.map((n) => {
    const pts = years.map((yr, i) => `${x(i)},${y(s.state_fractions_by_year[n][String(yr)] || 0)}`).join(" ");
    return `<polyline points="${pts}" fill="none" stroke="${STATE_COLORS[n] || "#888"}" stroke-width="2"/>`;
  }).join("");
  const labels = years.map((yr, i) =>
    `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" font-size="8" fill="#9aa7b5">${yr}</text>`).join("");
  el("trends-chart").innerHTML =
    `<svg class="svg-chart" viewBox="0 0 ${W} ${H}">${grid}${lines}${labels}</svg>`;
}

/* Stacked bars: change volume per year by destination state. */
function renderVolumes(s) {
  const vols = s.change_volumes_by_year || {};
  const years = Object.keys(vols).sort();
  if (!years.length) { el("volumes-chart").innerHTML = '<p class="story">No dated change events.</p>'; return; }
  const W = 380, H = 150, P = { l: 36, r: 8, t: 8, b: 22 };
  const totals = years.map((y) => vols[y].reduce((a, r) => a + r.pixels, 0));
  const maxT = Math.max(...totals);
  const bw = Math.min(40, (W - P.l - P.r) / years.length - 8);
  let bars = "";
  years.forEach((yr, i) => {
    const cx = P.l + ((i + 0.5) / years.length) * (W - P.l - P.r);
    let yTop = H - P.b;
    vols[yr].forEach((row) => {
      const h = (row.pixels / maxT) * (H - P.t - P.b);
      yTop -= h;
      bars += `<rect x="${cx - bw / 2}" y="${yTop}" width="${bw}" height="${h}"
               fill="${STATE_COLORS[row.to] || "#888"}"><title>${yr}: → ${STATE_LABELS[row.to] || row.to} (${(row.pixels / 10000).toFixed(1)} ha)</title></rect>`;
    });
    bars += `<text x="${cx}" y="${H - 6}" text-anchor="middle" font-size="8" fill="#9aa7b5">${yr}</text>`;
  });
  const kmMax = (maxT * 100 / 1e6).toFixed(1);
  el("volumes-chart").innerHTML =
    `<svg class="svg-chart" viewBox="0 0 ${W} ${H}">
      <text x="${P.l - 4}" y="${P.t + 6}" text-anchor="end" font-size="8" fill="#9aa7b5">${kmMax} km²</text>${bars}</svg>`;
}

function renderHotspots(s) {
  const list = el("hotspot-list");
  state.hotspotMarkers.forEach((m) => map.removeLayer(m));
  state.hotspotMarkers = [];
  if (!s.hotspots.length) {
    list.innerHTML = "<li>No concentrated change — what change exists is scattered.</li>";
    return;
  }
  list.innerHTML = s.hotspots.map((h, i) =>
    `<li data-i="${i}">${STATE_LABELS[h.dominant_from] || h.dominant_from} →
     <strong>${STATE_LABELS[h.dominant_to] || h.dominant_to}</strong>, visible by ${h.dominant_year}
     <span class="conf">(${Math.round(h.change_fraction * 100)}% of a ${h.block_m} m block, confidence ${h.mean_confidence.toFixed(2)})</span></li>`
  ).join("");
  s.hotspots.forEach((h) => {
    const m = L.circleMarker([h.lat, h.lon], {
      radius: 9, color: "#ffffff", weight: 1.5, fillColor: "#ff5c33", fillOpacity: 0.85,
    }).bindTooltip(`#${h.rank}: ${STATE_LABELS[h.dominant_from]} → ${STATE_LABELS[h.dominant_to]} by ${h.dominant_year}`);
    m.addTo(map);
    state.hotspotMarkers.push(m);
  });
  list.querySelectorAll("li[data-i]").forEach((li) => {
    li.addEventListener("click", () => {
      const h = s.hotspots[+li.dataset.i];
      map.flyTo([h.lat, h.lon], 15, { duration: 1.0 });
    });
  });
}

function renderAnomalies(s) {
  const a = s.anomalies;
  if (!a.top_rare_signatures.length) {
    el("anomaly-block").innerHTML = "<p>No unusual land histories at the configured threshold.</p>";
    return;
  }
  const paths = a.top_rare_signatures.slice(0, 4).map((r) =>
    `<code>${r.signature.replaceAll("→", " → ")}</code>`).join("<br>");
  el("anomaly-block").innerHTML =
    `<p>${(a.fraction_of_area * 100).toFixed(2)}% of this area followed histories that are
     statistically rare here (each under ${(a.rarity_threshold * 100).toFixed(1)}% of pixels) —
     rare means <em>uncommon</em>, not wrong or illicit. Toggle the <strong>Unusual</strong>
     layer to see where. Examples:</p><p>${paths}</p>`;
}

function renderConfidence(s) {
  const t = s.confidence.tier_counts;
  const total = Math.max((t.low || 0) + (t.medium || 0) + (t.high || 0), 1);
  const pct = (n) => ((n || 0) * 100 / total);
  el("confidence-block").innerHTML =
    `<div class="conf-bar">
       <div class="conf-high" style="width:${pct(t.high)}%" title="high"></div>
       <div class="conf-med" style="width:${pct(t.medium)}%" title="medium"></div>
       <div class="conf-low" style="width:${pct(t.low)}%" title="low"></div>
     </div>
     <p>${Math.round(pct(t.high))}% of detected changes have high supporting evidence
     (they persisted for years, replaced a stable state, and happened alongside neighbouring change).
     Mean evidence score ${s.confidence.mean_event_score.toFixed(2)}.
     These are evidence grades from the observations — not guarantees.</p>`;
}

/* ---------- boot ---------- */
refreshRegionList().then(async () => {
  try {
    const regions = await api("/api/regions");
    if (regions.length) await loadRegion(regions[0].region);
  } catch { /* fresh install: empty map is fine */ }
});
