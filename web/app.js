/* Touchline web client: live pitch, timed overlays, personalised insight feed. No build step. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const L = 105, W = 68;

const store = {
  get(k, d) { try { const v = localStorage.getItem("tl." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("tl." + k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

const S = {
  sid: "demo",
  es: null,
  meta: null,
  players: {},
  snap: null,
  insights: [],
  lastPass: null,
  i18n: null,
  llm: { backend: "offline" },
  prefs: Object.assign({ persona: "casual", lang: "en", club: "", focus: "", metric: "", speak: false }, store.get("prefs", {})),
  pos: {}, from: {}, to: {}, t0: 0, dur: 1,
  ball: [52.5, 34], ballFrom: [52.5, 34], ballMid: [52.5, 34], ballTo: [52.5, 34],
  lastT: 0,
  draws: [],          // temporary pitch drawings {kind, until, ...}
  layers: {},         // DOM overlay per layer
  tags: [],           // player tags {pid, el, until}
  speechQ: [],
  paused: false,
};

const KIND_LABEL = {
  goal: "Goal", chance_saved: "Big save", chance_missed: "Big chance", chance_blocked: "Blocked", line_break: "Line-breaking pass",
  hard_pass: "Pass quality", sprint: "Speed", long_carry: "Carry", momentum: "Momentum", phase: "Control vs chaos", press: "Pressing",
  card_yellow: "Booking", card_red: "Sending off", wp_swing: "Win probability", brace: "Milestone", hat_trick: "Milestone",
  saves: "Goalkeeping", record_shot: "Speed record", rhythm: "Game rhythm", standout: "Player focus", half_time: "Half-time", full_time: "Full-time",
};
const EXTRA_LANGS = { de: "Deutsch", ja: "日本語", hi: "हिन्दी", ar: "العربية", zh: "中文", ta: "தமிழ்", sw: "Kiswahili" };
const CLUB_WORDS = {
  en: { mine: "Your club", against: "Against your club", player: "Your player" },
  es: { mine: "Tu club", against: "Contra tu club", player: "Tu jugador" },
  fr: { mine: "Ton club", against: "Contre ton club", player: "Ton joueur" },
  pt: { mine: "O teu clube", against: "Contra o teu clube", player: "O teu jogador" },
};
const POSITIVE = new Set(["goal", "chance_saved", "chance_missed", "chance_blocked", "line_break", "hard_pass", "sprint", "long_carry",
  "momentum", "phase", "press", "brace", "hat_trick", "record_shot", "standout", "saves", "wp_swing"]);

/* ------------------------------------------------------------------ boot */
async function boot() {
  try {
    const [i18n, health] = await Promise.all([fetch("/api/i18n").then((r) => r.json()), fetch("/api/health").then((r) => r.json())]);
    S.i18n = i18n; S.llm = health.llm;
  } catch { S.i18n = { languages: { en: "English" }, banks: { en: {} } }; }
  buildLangSelect();
  bindControls();
  applyPrefs();
  resizeCanvas();
  addEventListener("resize", resizeCanvas);
  requestAnimationFrame(frame);
  connect();
  loadModels();
  setInterval(tickSpeech, 400);
}

function buildLangSelect() {
  const sel = $("#lang");
  sel.innerHTML = "";
  for (const [k, v] of Object.entries(S.i18n.languages)) sel.add(new Option(v, k));
  const llmOn = S.llm && S.llm.backend !== "offline";
  for (const [k, v] of Object.entries(EXTRA_LANGS)) {
    const o = new Option(llmOn ? v : `${v} (needs Azure AI)`, k);
    o.disabled = !llmOn;
    sel.add(o);
  }
  sel.value = S.prefs.lang in S.i18n.languages || llmOn ? S.prefs.lang : "en";
}

function savePrefs() { store.set("prefs", S.prefs); }

/* ------------------------------------------------------------------ stream */
function connect() {
  if (S.es) S.es.close();
  S.insights = []; S.pos = {}; S.draws = [];
  $("#cards").innerHTML = `<p class="empty">Moments appear here as they happen, each one checked against the match data before it's shown.</p>`;
  $("#trace").innerHTML = "";
  const es = new EventSource(`/api/matches/${S.sid}/stream`);
  S.es = es;
  es.addEventListener("open", () => $("#liveDot").classList.add("live"));
  es.addEventListener("error", () => $("#liveDot").classList.remove("live"));
  es.addEventListener("hello", (e) => onHello(JSON.parse(e.data)));
  es.addEventListener("state", (e) => onState(JSON.parse(e.data)));
  es.addEventListener("event", (e) => onEvent(JSON.parse(e.data)));
  es.addEventListener("insight", (e) => { const m = JSON.parse(e.data); onInsight(m.insight, m.replayed); });
  es.addEventListener("trace", (e) => onTrace(JSON.parse(e.data)));
  es.addEventListener("cue_update", (e) => onCueUpdate(JSON.parse(e.data).cue));
  es.addEventListener("control", (e) => { const m = JSON.parse(e.data); if (m.action === "pause") setPaused(true); if (m.action === "resume") setPaused(false); });
  es.addEventListener("done", () => toast("Full-time. A fresh live match starts shortly."));
  $("#auditLink").href = `/api/matches/${S.sid}/audit`;
  $("#datasetLink").href = `/api/matches/${S.sid}/dataset.jsonl`;
}

function onHello(h) {
  S.meta = h.match; S.llm = h.llm || S.llm;
  S.players = {};
  for (const t of [h.match.home, h.match.away]) for (const p of t.players) S.players[p.id] = { ...p, color: t.color };
  const { home, away } = h.match;
  $("#matchLabel").textContent = `${home.name} v ${away.name}, ${h.match.venue}`;
  $("#homeShort").textContent = home.short; $("#awayShort").textContent = away.short;
  $("#homeSwatch").style.background = home.color; $("#awaySwatch").style.background = away.color;
  $("#lgHome").textContent = home.name; $("#lgAway").textContent = away.name;
  document.documentElement.style.setProperty("--home", home.color);
  document.documentElement.style.setProperty("--away", away.color);
  const club = $("#club");
  club.innerHTML = `<option value="">None</option><option value="home">${esc(home.name)}</option><option value="away">${esc(away.name)}</option>`;
  club.value = S.prefs.club;
  const focus = $("#focus");
  focus.innerHTML = `<option value="">Nobody</option>` + [home, away].map((t) =>
    `<optgroup label="${esc(t.name)}">` + t.players.map((p) => `<option value="${p.id}">#${p.number} ${esc(p.name)} (${p.position})</option>`).join("") + "</optgroup>").join("");
  focus.value = S.players[S.prefs.focus] ? S.prefs.focus : "";
  drawTopology(h.topology);
  $("#speed").value = String(h.speed);
  renderSuggestions();
  applyPrefs();
}

function onState(s) {
  S.snap = s;
  const sc = s.score;
  $("#score").textContent = `${sc.home}–${sc.away}`;
  $("#clock").textContent = s.status === "half_time" ? "HT" : s.status === "full_time" ? "FT" : `${s.minute}'`;
  const wp = s.win_prob;
  const pct = (v) => Math.round(v * 100);
  $("#wpH").style.width = pct(wp.home) + "%"; $("#wpD").style.width = pct(wp.draw) + "%"; $("#wpA").style.width = pct(wp.away) + "%";
  $("#wpHl").textContent = pct(wp.home) + "%"; $("#wpDl").textContent = "Draw " + pct(wp.draw) + "%"; $("#wpAl").textContent = pct(wp.away) + "%";
  const ph = s.phase;
  const team = (side) => (S.meta ? S.meta[side].name : side);
  const phaseText = { chaos: "Chaos", balanced: "Balanced", home_control: `${team("home")} in control`, away_control: `${team("away")} in control` }[ph.label];
  $("#phase").firstChild.nodeValue = phaseText;
  $("#phaseSub").textContent = `${ph.turnovers_per_min} turnovers a minute, ${ph.avg_passes_per_possession} passes a possession`;
  setPaused(s.paused);
  drawTimeline();
  updateMetric();
  if (!$("#tab-players").hidden) renderPlayers();
  if (!$("#tab-ops").hidden) renderOps();
}

/* ------------------------------------------------------------------ events -> pitch */
function onEvent(ev) {
  const now = performance.now();
  if (ev.frame) {
    for (const [pid, p] of Object.entries(ev.frame)) {
      S.from[pid] = S.pos[pid] ? [...S.pos[pid]] : p;
      S.to[pid] = p;
      if (!S.pos[pid]) S.pos[pid] = [...p];
    }
  }
  const speed = Number($("#speed").value) || 10;
  const gap = Math.max(0, ev.t - S.lastT);
  S.lastT = ev.t;
  S.t0 = now;
  S.dur = Math.min(Math.max((gap / speed) * 1000, 120), 1600);
  if (ev.x != null) {
    S.ballFrom = [...S.ball];
    S.ballMid = [ev.x, ev.y];
    S.ballTo = ev.end_x != null ? [ev.end_x, ev.end_y] : [ev.x, ev.y];
  }
  if (ev.etype === "pass") S.lastPass = ev;
  if (ev.etype === "kickoff") S.ball = [52.5, 34];
  if (S.prefs.focus && (ev.player_id === S.prefs.focus || ev.target_id === S.prefs.focus)) focusTicker(ev);
}

function focusTicker(ev) {
  const bank = (S.i18n.banks[S.prefs.lang] || S.i18n.banks.en);
  const en = S.i18n.banks.en;
  const v = (k) => bank[k] || en[k] || k;
  const p = S.players[S.prefs.focus];
  let txt = "";
  if (ev.player_id === S.prefs.focus) {
    if (ev.etype === "pass" && ev.difficulty != null) {
      txt = v("r.focus_pass").replace("{outcome}", v(ev.outcome === "complete" ? "v.outcome.complete" : "v.outcome.failed")).replace("{difficulty}", ev.difficulty);
    } else if ((ev.etype === "carry" || ev.etype === "dribble") && ev.q.speed_kmh) {
      txt = `${v("v.action." + ev.etype)}, ${ev.q.speed_kmh} km/h`;
    } else if (ev.etype === "shot") {
      txt = `${v("v.action.shot")}, ${ev.xg} xG, ${ev.q.shot_speed_kmh} km/h`;
    } else if (["tackle", "interception"].includes(ev.etype)) {
      txt = v("v.action." + ev.etype);
    } else return;
  } else if (ev.etype === "pass" && ev.outcome === "complete") {
    txt = `receives from ${ev.player}`;
  } else return;
  const el = layerEl("focus", "focus-ticker");
  el.innerHTML = `<b>#${p.number} ${esc(p.name.split(" ").slice(-1)[0])}</b> ${esc(txt)}`;
  clearTimeout(el._t);
  el._t = setTimeout(() => el.remove(), 3500);
}

/* ------------------------------------------------------------------ insights */
function rendersFor(ins, persona = S.prefs.persona) {
  const byLang = (ins.renders || {})[persona] || {};
  return byLang[S.prefs.lang] || byLang.en;
}

function onInsight(ins, replayed) {
  S.insights.push(ins);
  if (S.insights.length > 400) S.insights.shift();
  const card = renderCard(ins);
  const cards = $("#cards");
  $(".empty", cards)?.remove();
  cards.prepend(card);
  while (cards.children.length > 80) cards.lastChild.remove();
  $("#feedCount").textContent = `${S.insights.length} moments explained`;
  if (!replayed && ins.cue && ins.cue.approval === "auto") playCue(ins);
  if (!replayed && (S.prefs.speak || S.prefs.persona === "access")) queueSpeech(ins);
  if (!$("#tab-producer").hidden) renderProducer();
  if (ins.kind === "half_time" || ins.kind === "full_time") loadRecap();
}

function clubFlag(ins) {
  const words = CLUB_WORDS[S.prefs.lang] || CLUB_WORDS.en;
  if (S.prefs.focus && (ins.player_id === S.prefs.focus || (ins.viz && ins.viz.player_id === S.prefs.focus))) return words.player;
  if (!S.prefs.club || !ins.team) return "";
  if (ins.team === S.prefs.club) return POSITIVE.has(ins.kind) ? words.mine : words.mine;
  return ["goal", "chance_saved", "chance_missed", "momentum", "press", "phase", "wp_swing", "line_break"].includes(ins.kind) ? words.against : "";
}

function renderCard(ins) {
  const r = rendersFor(ins);
  const el = document.createElement("article");
  el.className = "card " + (ins.team || "");
  el.dataset.id = ins.id;
  if (S.prefs.club && ins.team === S.prefs.club) el.classList.add("mine");
  if (S.prefs.focus && ins.player_id === S.prefs.focus) el.classList.add("focus");
  if (!r) { el.innerHTML = `<div class="meta">${ins.minute}' ${esc(KIND_LABEL[ins.kind] || ins.kind)}</div>`; return el; }
  const flag = clubFlag(ins);
  const v = ins.verification || {};
  const src = r.source && r.source.startsWith("llm") ? "AI-written, checked" : "";
  el.innerHTML = `
    <div class="meta"><span class="min">${ins.minute}'</span><span>${esc(KIND_LABEL[ins.kind] || ins.kind)}</span>
      ${flag ? `<span style="color:var(--sodium)">${esc(flag)}</span>` : ""}
      ${v.status === "verified" ? `<span class="verified" title="${v.checks} checks against the match data"><svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.5l2.5 2.5L10 3.5" stroke="currentColor" stroke-width="2" fill="none"/></svg>Checked</span>` : ""}
      <span class="src">${src}</span></div>
    <h3>${esc(r.title)}</h3>
    ${r.lines.length ? `<ul>${r.lines.map((l) => `<li>${esc(l.text)}</li>`).join("")}</ul>` : ""}
    <div class="chips">${(ins.event_ids || []).slice(-4).map((id) => `<button class="chip" data-ev="${id}" title="Show the evidence">${id}</button>`).join("")}
      ${S.prefs.persona === "access" ? `<button class="chip speak" data-say="${ins.id}">Read aloud</button>` : ""}</div>`;
  return el;
}

function rerenderCards() {
  const cards = $("#cards");
  cards.innerHTML = "";
  for (const ins of S.insights.slice(-80)) cards.prepend(renderCard(ins));
  if (!S.insights.length) cards.innerHTML = `<p class="empty">Moments appear here as they happen, each one checked against the match data before it's shown.</p>`;
}

/* ------------------------------------------------------------------ overlays */
function layerEl(name, cls) {
  let el = S.layers[name];
  if (!el || !el.isConnected) {
    el = document.createElement("div");
    $("#overlay").appendChild(el);
    S.layers[name] = el;
  }
  el.className = cls;
  return el;
}

function hideLayer(name, el) {
  if (S.layers[name] !== el) return;
  el.classList.add("out");
  setTimeout(() => { if (S.layers[name] === el) { el.remove(); delete S.layers[name]; } }, 320);
}

function playCue(ins) {
  const cue = ins.cue;
  const persona = S.prefs.persona === "analyst" ? "analyst" : S.prefs.persona === "casual" ? "casual" : "studio";
  const r = rendersFor(ins, persona) || rendersFor(ins, "studio");
  if (!r) return;
  const wall = Math.max(4.5, Math.min(cue.duration_s, 9)) * 1000;
  const cur = S.layers[cue.layer];
  if (cur && cur._prio > cue.priority && cur._until > performance.now()) return;
  const viz = ins.viz || {};
  if (cue.layer === "player_tag") {
    showTag(viz.player_id, `${esc(viz.name)}<b>${viz.speed_kmh ? viz.speed_kmh + " km/h" : ""}</b>`, wall);
    return;
  }
  let el;
  if (cue.layer === "lower_third") {
    el = layerEl("lower_third", "lower-third" + (cue.template === "full_banner" ? " banner" : ""));
    el.innerHTML = `<div class="bar"></div><div class="body"><div class="ttl">${esc(r.title)}</div>
      ${r.lines[0] ? `<div class="ln">${esc(r.lines[0].text)}</div>` : ""}
      ${persona !== "casual" && r.lines[1] ? `<div class="ln">${esc(r.lines[1].text)}</div>` : ""}</div>`;
  } else if (cue.layer === "side_panel") {
    el = layerEl("side_panel", "side-panel");
    el.innerHTML = `<div class="ttl">${esc(r.title)}</div>${r.lines.slice(0, 2).map((l) => `<div class="ln">${esc(l.text)}</div>`).join("")}${sidePanelViz(viz)}`;
  } else if (cue.layer === "full_screen") {
    el = layerEl("full_screen", "full-screen");
    el.innerHTML = `<div class="ttl">${esc(r.title)}</div>${r.lines.map((l) => `<div class="ln">${esc(l.text)}</div>`).join("")}`;
  } else return;
  el._prio = cue.priority; el._until = performance.now() + wall;
  clearTimeout(el._t);
  el._t = setTimeout(() => hideLayer(cue.layer, el), wall);
  // pitch drawings
  const until = performance.now() + wall;
  if (viz.type === "pass") S.draws.push({ kind: "pass", until, ...viz });
  if (viz.type === "shot") S.draws.push({ kind: "shot", until, ...viz });
  if (viz.type === "shot" && viz.chain && viz.chain.length) S.draws.push({ kind: "chain", until, ids: viz.chain });
}

function sidePanelViz(viz) {
  if (viz.type === "momentum" && viz.series) {
    const pts = viz.series.map((p, i) => `${(i / Math.max(1, viz.series.length - 1)) * 280},${30 - p.momentum * 26}`).join(" ");
    return `<svg viewBox="0 0 280 60" height="60"><line x1="0" y1="30" x2="280" y2="30" stroke="#6f8a7b" stroke-dasharray="3 3"/><polyline points="${pts}" fill="none" stroke="#f2c14e" stroke-width="2.5"/></svg>`;
  }
  if (viz.type === "phase") {
    const x = Math.round(viz.chaos * 280);
    return `<svg viewBox="0 0 280 26" height="26"><rect width="280" height="8" y="9" rx="2" fill="#184232"/><rect width="${x}" height="8" y="9" rx="2" fill="#f2c14e"/><text x="0" y="26" fill="#a6b3a9" font-size="10">control</text><text x="280" y="26" fill="#a6b3a9" font-size="10" text-anchor="end">chaos</text></svg>`;
  }
  if (viz.type === "player_card" && viz.player) {
    const p = viz.player;
    return `<svg viewBox="0 0 280 24" height="24"><text x="0" y="16" fill="#eef0e8" font-size="13">${p.passes ?? 0} passes, ${p.xg ?? 0} xG, ${p.top_speed_kmh ?? 0} km/h</text></svg>`;
  }
  return "";
}

function showTag(pid, html, ms) {
  if (!pid) return;
  const el = document.createElement("div");
  el.className = "player-tag" + (pid === S.prefs.focus ? " focus" : "");
  el.innerHTML = html;
  $("#overlay").appendChild(el);
  const tag = { pid, el, until: performance.now() + ms };
  S.tags.push(tag);
  setTimeout(() => { el.remove(); S.tags = S.tags.filter((t) => t !== tag); }, ms);
}

/* ------------------------------------------------------------------ canvas pitch */
const cv = $("#pitch");
const ctx = cv.getContext("2d");
let PX = 1, DPR = 1;

function resizeCanvas() {
  const box = $("#pitchBox").getBoundingClientRect();
  DPR = Math.min(2, devicePixelRatio || 1);
  cv.width = Math.round(box.width * DPR);
  cv.height = Math.round(box.height * DPR);
  PX = cv.width / L;
}
const X = (x) => x * PX, Y = (y) => (W - y) * PX; // y up = left touchline for the home attack

function pitchLines() {
  ctx.strokeStyle = "rgba(238,240,232,.78)";
  ctx.lineWidth = Math.max(1, 0.12 * PX);
  ctx.strokeRect(X(0.3), Y(W - 0.3), X(L - 0.6), (W - 0.6) * PX);
  ctx.beginPath(); ctx.moveTo(X(L / 2), Y(0)); ctx.lineTo(X(L / 2), Y(W)); ctx.stroke();
  ctx.beginPath(); ctx.arc(X(L / 2), Y(W / 2), 9.15 * PX, 0, Math.PI * 2); ctx.stroke();
  for (const side of [0, 1]) {
    const x0 = side ? L - 16.5 : 0, x6 = side ? L - 5.5 : 0;
    ctx.strokeRect(X(x0), Y(W / 2 + 20.16), 16.5 * PX, 40.32 * PX);
    ctx.strokeRect(X(x6), Y(W / 2 + 9.16), 5.5 * PX, 18.32 * PX);
    const spot = side ? L - 11 : 11;
    ctx.beginPath(); ctx.arc(X(spot), Y(W / 2), 0.25 * PX, 0, Math.PI * 2); ctx.fillStyle = "rgba(238,240,232,.8)"; ctx.fill();
    ctx.beginPath();
    const a = Math.acos(5.5 / 9.15);
    if (side) ctx.arc(X(spot), Y(W / 2), 9.15 * PX, Math.PI - a, Math.PI + a);
    else ctx.arc(X(spot), Y(W / 2), 9.15 * PX, -a, a);
    ctx.stroke();
    ctx.fillStyle = "rgba(238,240,232,.25)";
    ctx.fillRect(side ? X(L) - 0.6 * PX : X(0) - 1.4 * PX, Y(W / 2 + 3.66), 2 * PX, 7.32 * PX);
  }
}

function lerp(a, b, t) { return a + (b - a) * t; }
function ease(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

function frame(now) {
  requestAnimationFrame(frame);
  ctx.clearRect(0, 0, cv.width, cv.height);
  pitchLines();
  const t = Math.min(1, (now - S.t0) / S.dur);
  const e = ease(t);
  for (const pid of Object.keys(S.to)) {
    const f = S.from[pid] || S.to[pid], to = S.to[pid];
    S.pos[pid] = [lerp(f[0], to[0], e), lerp(f[1], to[1], e)];
  }
  // ball: to the event origin quickly, then along the action
  if (t < 0.25) { const k = ease(t / 0.25); S.ball = [lerp(S.ballFrom[0], S.ballMid[0], k), lerp(S.ballFrom[1], S.ballMid[1], k)]; }
  else { const k = ease((t - 0.25) / 0.75); S.ball = [lerp(S.ballMid[0], S.ballTo[0], k), lerp(S.ballMid[1], S.ballTo[1], k)]; }

  S.draws = S.draws.filter((d) => d.until > now);
  for (const d of S.draws) drawViz(d, now);

  const r = Math.max(4, 1.05 * PX);
  for (const [pid, p] of Object.entries(S.pos)) {
    const pl = S.players[pid];
    if (!pl) continue;
    const focus = pid === S.prefs.focus;
    ctx.beginPath(); ctx.arc(X(p[0]), Y(p[1]), r, 0, Math.PI * 2);
    ctx.fillStyle = pl.position === "GK" ? (pl.team === "home" ? "#7cc4ff" : "#ffb36b") : pl.color;
    ctx.fill();
    ctx.lineWidth = focus ? Math.max(2, 0.35 * PX) : Math.max(1, 0.12 * PX);
    ctx.strokeStyle = focus ? "#f2c14e" : "rgba(10,25,18,.7)";
    ctx.stroke();
    if (PX > 5) {
      ctx.fillStyle = "#fff"; ctx.font = `600 ${Math.round(r * 1.05)}px Barlow Condensed, sans-serif`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(pl.number, X(p[0]), Y(p[1]) + 0.5);
    }
    if (focus) {
      ctx.font = `600 ${Math.round(Math.max(11, 1.4 * PX))}px Barlow, sans-serif`;
      ctx.fillStyle = "#f2c14e"; ctx.textAlign = "center";
      ctx.fillText(pl.name.split(" ").slice(-1)[0], X(p[0]), Y(p[1]) - r - Math.max(8, PX));
    }
  }
  ctx.beginPath(); ctx.arc(X(S.ball[0]), Y(S.ball[1]), Math.max(3, 0.55 * PX), 0, Math.PI * 2);
  ctx.fillStyle = "#fff"; ctx.shadowColor = "rgba(0,0,0,.6)"; ctx.shadowBlur = 6; ctx.fill(); ctx.shadowBlur = 0;

  for (const tg of S.tags) {
    const p = S.pos[tg.pid];
    if (!p) continue;
    tg.el.style.left = (X(p[0]) / DPR) + "px";
    tg.el.style.top = (Y(p[1]) / DPR) + "px";
  }
}

function arrow(x1, y1, x2, y2, color, width, dash) {
  ctx.save();
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash || []);
  ctx.beginPath(); ctx.moveTo(X(x1), Y(y1)); ctx.lineTo(X(x2), Y(y2)); ctx.stroke();
  ctx.setLineDash([]);
  const a = Math.atan2(Y(y2) - Y(y1), X(x2) - X(x1)), h = Math.max(8, 1.6 * PX);
  ctx.beginPath(); ctx.moveTo(X(x2), Y(y2));
  ctx.lineTo(X(x2) - h * Math.cos(a - 0.4), Y(y2) - h * Math.sin(a - 0.4));
  ctx.lineTo(X(x2) - h * Math.cos(a + 0.4), Y(y2) - h * Math.sin(a + 0.4));
  ctx.closePath(); ctx.fill(); ctx.restore();
}

function drawViz(d, now) {
  const fadeIn = Math.min(1, (now - (d.until - 9000)) / 300);
  ctx.globalAlpha = Math.max(0.35, fadeIn);
  if (d.kind === "pass") {
    arrow(d.x, d.y, d.end_x, d.end_y, "#f2c14e", Math.max(2, 0.3 * PX), [0.9 * PX, 0.6 * PX]);
    label(d.end_x, d.end_y, `${d.difficulty}/100`);
  } else if (d.kind === "shot") {
    arrow(d.x, d.y, d.end_x, d.end_y, "#eef0e8", Math.max(2, 0.25 * PX));
    ctx.beginPath(); ctx.arc(X(d.x), Y(d.y), Math.max(6, (0.8 + d.xg * 5) * PX), 0, Math.PI * 2);
    ctx.fillStyle = "rgba(242,193,78,.25)"; ctx.fill(); ctx.strokeStyle = "#f2c14e"; ctx.lineWidth = 2; ctx.stroke();
    label(d.x, d.y, `${d.xg} xG`);
  } else if (d.kind === "chain") {
    // build-up: we only know event ids; draw from cached events if present in feed history
  } else if (d.kind === "control" && d.grid) {
    const nx = d.nx, ny = d.ny, cw = L / nx, ch = W / ny;
    for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) {
      const c = d.grid[i][j];
      ctx.fillStyle = c >= 0.5 ? `rgba(47,124,246,${(c - 0.5) * 0.9})` : `rgba(229,72,77,${(0.5 - c) * 0.9})`;
      ctx.fillRect(X(i * cw), Y((j + 1) * ch), cw * PX + 1, ch * PX + 1);
    }
  } else if (d.kind === "evidence") {
    if (d.end_x != null) arrow(d.x, d.y, d.end_x, d.end_y, "#f2c14e", Math.max(2, 0.35 * PX));
    ctx.beginPath(); ctx.arc(X(d.x), Y(d.y), Math.max(8, 1.8 * PX), 0, Math.PI * 2);
    ctx.strokeStyle = "#f2c14e"; ctx.lineWidth = 3; ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

function label(x, y, text) {
  ctx.font = `700 ${Math.round(Math.max(12, 1.5 * PX))}px Barlow Condensed, sans-serif`;
  const w = ctx.measureText(text).width + 10, h = Math.max(16, 1.9 * PX);
  ctx.fillStyle = "rgba(12,36,27,.9)";
  ctx.fillRect(X(x) + 8, Y(y) - h - 6, w, h);
  ctx.fillStyle = "#f2c14e"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(text, X(x) + 13, Y(y) - h / 2 - 6);
}

/* ------------------------------------------------------------------ timeline + metric */
function drawTimeline() {
  const s = S.snap; if (!s || !s.timeline || !s.timeline.length) return;
  const svg = $("#timeline"), w = 960, h = 120, maxM = 96;
  const tl = s.timeline;
  const x = (m) => (m / maxM) * w;
  const home = tl.map((p) => `${x(p.minute)},${h - p.wp.home * h}`).join(" ");
  const away = tl.map((p) => `${x(p.minute)},${p.wp.away * h}`).join(" ");
  const mom = tl.map((p) => `${x(p.minute)},${h / 2 - p.momentum * (h / 2 - 6)}`).join(" ");
  const last = x(tl[tl.length - 1].minute), first = x(tl[0].minute);
  const goals = S.insights.filter((i) => i.kind === "goal").map((g) =>
    `<line x1="${x(g.minute)}" x2="${x(g.minute)}" y1="0" y2="${h}" style="stroke:${g.team === "home" ? "var(--home)" : "var(--away)"}" stroke-width="2" vector-effect="non-scaling-stroke"/>`).join("");
  svg.innerHTML = `
    <line x1="${x(45)}" x2="${x(45)}" y1="0" y2="${h}" stroke="#2a5242" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>
    <polygon points="${first},${h} ${home} ${last},${h}" style="fill:var(--home)" opacity=".35"/>
    <polygon points="${first},0 ${away} ${last},0" style="fill:var(--away)" opacity=".35"/>
    ${goals}
    <polyline points="${mom}" fill="none" stroke="#f2c14e" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
}

function updateMetric() {
  const m = S.prefs.metric, s = S.snap;
  $("#metricBox").hidden = !m;
  if (!m || !s) return;
  const meta = S.meta, side = S.prefs.club || "home";
  let label = "", val = "–", sub = "";
  if (m === "wp") { label = `${meta[side].short} win probability`; val = Math.round(s.win_prob[side] * 100) + "%"; sub = `draw ${Math.round(s.win_prob.draw * 100)}%`; }
  if (m === "xg") { label = "xG race"; val = `${s.home.xg} – ${s.away.xg}`; sub = `${s.home.shots} v ${s.away.shots} shots`; }
  if (m === "difficulty" && S.lastPass) { label = "Last pass difficulty"; val = `${S.lastPass.difficulty}/100`; sub = `${S.lastPass.player}, ${S.lastPass.outcome === "complete" ? "found its man" : "lost"}`; }
  if (m === "speed" && s.records.top_speed_kmh) { label = "Top speed"; val = `${s.records.top_speed_kmh.value} km/h`; sub = s.records.top_speed_kmh.player; }
  if (m === "press") { label = "Pressures"; val = `${s.home.pressures} – ${s.away.pressures}`; sub = `high turnovers ${s.home.high_turnovers} – ${s.away.high_turnovers}`; }
  if (m === "possession") { label = "Possession"; val = `${s.home.possession}% – ${s.away.possession}%`; sub = `${s.home.passes} v ${s.away.passes} passes`; }
  if (S.prefs.focus && s.players && s.players[S.prefs.focus] && m === "speed") {
    const p = s.players[S.prefs.focus]; label = `${S.players[S.prefs.focus].name.split(" ").slice(-1)[0]} top speed`; val = `${p.top_speed_kmh} km/h`; sub = `${p.distance_km} km covered`;
  }
  $("#metricLabel").textContent = label;
  $("#metricVal").firstChild.nodeValue = val;
  $("#metricSub").textContent = sub;
}

/* ------------------------------------------------------------------ speech (audio description) */
function queueSpeech(ins) {
  if (!("speechSynthesis" in window)) return;
  const r = rendersFor(ins, "access");
  if (!r) return;
  if (S.speechQ.length > 2 && ins.salience < 0.6) return;
  S.speechQ.push({ text: r.speech || r.title, lang: S.prefs.lang });
}
function tickSpeech() {
  if (!("speechSynthesis" in window) || speechSynthesis.speaking || !S.speechQ.length) return;
  const { text, lang } = S.speechQ.shift();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = { en: "en-GB", es: "es-ES", fr: "fr-FR", pt: "pt-PT" }[lang] || lang;
  u.rate = 1.05;
  speechSynthesis.speak(u);
}

/* ------------------------------------------------------------------ evidence drawer */
async function openEvidence(id) {
  const res = await fetch(`/api/matches/${S.sid}/events/${id}`);
  if (!res.ok) return toast("That event isn't available yet.");
  const d = await res.json();
  const f = d.facts, ev = d.event;
  const rows = Object.entries(f).filter(([k]) => !["event_id"].includes(k)).map(([k, v]) =>
    `<tr><td>${esc(k.replace(/_/g, " "))}</td><td class="num">${esc(typeof v === "object" ? Object.entries(v).map(([a, b]) => `${a} ${b}%`).join(", ") : v)}</td></tr>`).join("");
  const expl = d.xg_explain || d.pass_explain;
  const bars = expl && expl.length ? `<h4 style="margin:14px 0 4px;font:700 16px var(--display)">${d.xg_explain ? "What drove the chance quality" : "What made this pass hard or easy"}</h4>
    <p class="muted" style="margin:0 0 6px;font-size:13px">Compared with a typical ${d.xg_explain ? "shot" : "pass"} in our synthetic league. Right helps, left hurts.</p>
    <div class="bars">${expl.slice(0, 6).map((c) => {
      const w = Math.min(50, Math.abs(c.logodds) * 25);
      const left = c.logodds >= 0 ? 50 : 50 - w;
      return `<div class="row"><span>${esc(c.label)}</span><span class="track"><span class="mid"></span><span class="fill" style="left:${left}%;width:${w}%;background:${c.logodds >= 0 ? "var(--ok)" : "var(--bad)"}"></span></span><span class="num" style="text-align:right">${c.logodds > 0 ? "+" : ""}${c.logodds}</span></div>`;
    }).join("")}</div>` : "";
  $("#drawerBody").innerHTML = `<h3>${esc(f.player || f.type)}, ${f.minute}'</h3>
    <p class="muted" style="margin:0 0 10px">${esc(id)}: ${esc(ev.type)}${ev.outcome ? ", " + esc(ev.outcome) : ""}. Every number here is recomputed from the raw event and its tracking snapshot.</p>
    <table class="data"><tbody>${rows}</tbody></table>${bars}
    ${d.pitch_control ? `<p class="muted" style="margin-top:12px;font-size:13px">The pitch now shows who controlled each patch of grass at that instant: ${S.meta.home.short} ${Math.round(d.pitch_control.home_share * 100)}%, ${S.meta.away.short} ${Math.round((1 - d.pitch_control.home_share) * 100)}%.</p>` : ""}`;
  $("#drawer").hidden = false;
  $("#drawerClose").focus();
  const until = performance.now() + 9000;
  S.draws = S.draws.filter((x) => x.kind !== "control" && x.kind !== "evidence");
  if (d.pitch_control) S.draws.push({ kind: "control", until, ...d.pitch_control });
  if (ev.x != null) S.draws.push({ kind: "evidence", until, x: ev.x, y: ev.y, end_x: ev.end_x, end_y: ev.end_y });
}

/* ------------------------------------------------------------------ tabs */
function renderSuggestions() {
  if (!S.meta) return;
  const st = S.meta.home.players.find((p) => p.position === "ST");
  const qs = ["Why did they score?", "Who is the standout player?", `How is ${st.name} playing?`, "What's the win probability?", "Who is pressing harder?", "Fastest moments so far?"];
  $("#suggest").innerHTML = qs.map((q) => `<button class="btn small" data-q="${esc(q)}">${esc(q)}</button>`).join("");
}

async function ask(q) {
  const box = document.createElement("div");
  box.innerHTML = `<div class="q">${esc(q)}</div><div class="a muted">Thinking…</div>`;
  $("#qa").prepend(box);
  try {
    const r = await fetch(`/api/matches/${S.sid}/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, lang: S.prefs.lang }) }).then((x) => x.json());
    box.innerHTML = `<div class="q">${esc(q)}</div><div class="a">${esc(r.answer)}</div>
      <div class="chips">${(r.citations || []).slice(0, 6).map((id) => `<button class="chip" data-ev="${id}">${id}</button>`).join("")}</div>
      <div class="by">${r.source === "router" ? "Answered from the live match data" : "Written by the analyst agent, numbers checked against its tools"} in ${r.ms} ms</div>`;
  } catch { box.querySelector(".a").textContent = "The analyst couldn't be reached. Check your connection and ask again."; }
}

async function loadRecap() {
  try {
    const r = await fetch(`/api/matches/${S.sid}/recap?persona=${S.prefs.persona}&lang=${S.prefs.lang}`).then((x) => x.json());
    $("#recapTitle").textContent = r.title;
    $("#recapLines").innerHTML = r.lines.map((l) => `<li>${esc(l.text)}</li>`).join("");
    $("#recapNote").textContent = r.note || `Written at minute ${S.snap ? S.snap.minute : "?"}. Every line is built from checked match data.`;
  } catch { /* keep previous */ }
}

let playerSort = "rating";
function renderPlayers() {
  const s = S.snap; if (!s || !S.meta) return;
  const rows = Object.entries(s.players).map(([pid, v]) => ({ pid, ...S.players[pid], ...v }));
  rows.sort((a, b) => (b[playerSort] ?? 0) - (a[playerSort] ?? 0));
  const cols = [["number", "#"], ["name", "Player"], ["position", "Pos"], ["rating", "Rating"], ["passes", "Passes"], ["acc", "Pass %"], ["xt", "Threat (xT)"], ["xg", "xG"], ["top_speed_kmh", "Top km/h"], ["distance_km", "Km"]];
  $("#playersTable thead").innerHTML = `<tr>${cols.map(([k, l]) => `<th data-sort="${k}" class="${["name", "position"].includes(k) ? "" : "num"}">${l}</th>`).join("")}<th></th></tr>`;
  $("#playersTable tbody").innerHTML = rows.map((p) => {
    const acc = p.passes ? Math.round((p.completed / p.passes) * 100) : "–";
    return `<tr><td>${p.number}</td><td><span class="dot" style="background:${p.color}"></span>${esc(p.name)}</td><td>${p.position}</td>
      <td class="num">${p.rating}</td><td class="num">${p.passes}</td><td class="num">${acc}</td><td class="num">${p.xt}</td><td class="num">${p.xg}</td>
      <td class="num">${p.top_speed_kmh}</td><td class="num">${p.distance_km}</td>
      <td><button class="btn small" data-follow="${p.pid}">${S.prefs.focus === p.pid ? "Following" : "Follow"}</button></td></tr>`;
  }).join("");
}

function renderProducer() {
  const pend = S.insights.filter((i) => i.cue && i.cue.approval === "pending");
  $("#pending").innerHTML = pend.length ? pend.map((i) => {
    const r = rendersFor(i, "studio");
    return `<div class="cue"><div><div class="t">${esc(r ? r.title : i.kind)}</div><div class="s">${i.minute}', ${i.cue.template} on the ${i.cue.layer.replace("_", " ")}, priority ${i.cue.priority}</div></div>
      <div class="ctl"><button class="btn small primary" data-approve="${i.cue.cue_id}">Air it</button><button class="btn small" data-reject="${i.cue.cue_id}">Drop</button></div></div>`;
  }).join("") : `<p class="muted">Nothing waiting for approval.</p>`;
  const aired = S.insights.filter((i) => i.cue && ["auto", "approved"].includes(i.cue.approval)).slice(-6).reverse();
  $("#aired").innerHTML = aired.map((i) => {
    const r = rendersFor(i, "studio");
    return `<div class="cue"><div><div class="t">${esc(r ? r.title : i.kind)}</div><div class="s">${i.minute}', ${i.cue.approval === "approved" ? "approved by the producer" : "aired automatically"}, ready ${i.latency_ms} ms after the event</div></div></div>`;
  }).join("") || `<p class="muted">No graphics yet.</p>`;
  const last = S.insights.filter((i) => i.cue).slice(-1)[0];
  if (last) {
    const c = { ...last.cue }; delete c.data;
    $("#cueJson").textContent = JSON.stringify(c, null, 2);
  }
}

function renderOps() {
  const o = S.snap && S.snap.ops; if (!o) return;
  const kv = [
    [o.insights, "moments explained"],
    [`${o.pipeline_ms_p50 ?? "–"} / ${o.pipeline_ms_p95 ?? "–"} ms`, "agent pipeline p50 / p95"],
    [`${o.event_ms_p50 ?? "–"} ms`, "event ingest to state, p50"],
    [`${o.verifier.verified} / ${o.verifier.blocked}`, "insights verified / blocked"],
    [o.ingest.accepted, "events accepted"],
    [`${o.ingest.quarantined} / ${o.ingest.duplicates} / ${o.ingest.reordered}`, "quarantined / duplicates / re-ordered"],
    [`${o.producer.aired} / ${o.producer.pending}`, "graphics aired / pending"],
    [o.llm.backend === "offline" ? "Offline" : `${o.llm.backend}`, o.llm.backend === "offline" ? "language model (phrase banks in use)" : `model ${o.llm.model}, ${o.llm.calls} calls`],
  ];
  $("#opsKv").innerHTML = kv.map(([v, l]) => `<div><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join("");
}

function onTrace(sp) {
  const el = $("#trace");
  const row = document.createElement("div");
  row.innerHTML = `<span class="ag">${esc(sp.agent)}</span><span class="muted">${esc(String(sp.ref).split("-").pop())}</span><span class="st-${esc(sp.status)}">${esc(sp.note)}${sp.handoff_to ? ", hands off to " + esc(sp.handoff_to) : ""}</span><span class="muted" style="text-align:right">${sp.ms} ms</span>`;
  el.prepend(row);
  while (el.children.length > 60) el.lastChild.remove();
}

function onCueUpdate(cue) {
  for (const i of S.insights) if (i.cue && i.cue.cue_id === cue.cue_id) { i.cue = cue; if (cue.approval === "approved") playCue(i); }
  if (!$("#tab-producer").hidden) renderProducer();
}

function drawTopology(topo) {
  const svg = $("#topology");
  const nodes = {
    "IngestGuard": [10, 20], "MatchState": [10, 80], "MomentScout": [10, 140], "TacticalAnalyst": [10, 200], "FactChecker": [190, 200],
    "Narrator[casual]": [370, 20], "Narrator[analyst]": [370, 80], "Narrator[studio]": [370, 140], "Narrator[access]": [370, 200], "Producer": [370, 260],
  };
  const w = 170, h = 34;
  const edge = ([a, b]) => {
    const [x1, y1] = nodes[a], [x2, y2] = nodes[b];
    if (!nodes[a] || !nodes[b]) return "";
    const sx = x1 + (x2 > x1 ? w : w / 2), sy = y1 + (x2 > x1 ? h / 2 : h), ex = x2 + (x2 > x1 ? 0 : w / 2), ey = y2 + (x2 > x1 ? h / 2 : 0);
    return `<path d="M${sx},${sy} C${(sx + ex) / 2},${sy} ${(sx + ex) / 2},${ey} ${ex},${ey}" fill="none" stroke="#2a5242" stroke-width="1.5"/>`;
  };
  const edges = (topo ? topo.edges : []).map(edge).join("") +
    ["casual", "analyst", "studio", "access"].map((p) => `<path d="M${370 + w / 2 + 70},${nodes[`Narrator[${p}]`][1] + h} L${370 + w / 2 + 70},260" stroke="#2a5242" fill="none"/>`).slice(-1).join("");
  svg.innerHTML = edges + Object.entries(nodes).map(([n, [x, y]]) =>
    `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="${n === "FactChecker" ? "#3d3415" : "#184232"}" stroke="${n === "FactChecker" ? "#f2c14e" : "#2a5242"}"/>
     <text x="${x + w / 2}" y="${y + h / 2 + 5}" text-anchor="middle" fill="#eef0e8" font-family="Barlow Condensed" font-weight="600" font-size="16">${n}</text></g>`).join("");
}

async function loadModels() {
  try {
    const m = await fetch("/api/models").then((r) => r.json());
    $("#modelInfo").innerHTML = `<p>Trained on ${esc(m.trained_on)}, with the last 20% held out.</p>
      <table class="data"><thead><tr><th>Model</th><th class="num">AUC</th><th class="num">Brier</th><th class="num">Test size</th></tr></thead><tbody>
      <tr><td>Expected goals (xG)</td><td class="num">${m.xg_eval.auc}</td><td class="num">${m.xg_eval.brier}</td><td class="num">${m.xg_eval.n_test}</td></tr>
      <tr><td>Pass completion / difficulty</td><td class="num">${m.pass_eval.auc}</td><td class="num">${m.pass_eval.brier}</td><td class="num">${m.pass_eval.n_test}</td></tr></tbody></table>
      <p style="margin-top:10px">Synthetic league profile: ${m.league.goals_per_match} goals, ${m.league.shots_per_match} shots and ${Math.round(m.league.passes_per_match)} passes per match, ${Math.round(m.league.pass_completion * 100)}% pass completion.</p>
      <p>Both models are glass-box logistic regressions, so every prediction breaks down into the factors you see in the evidence panel. Threat (xT) is a 16×12 value grid learned from the same matches.</p>`;
  } catch { /* optional */ }
}

/* ------------------------------------------------------------------ controls */
function applyPrefs() {
  $$("#personaSeg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.persona === S.prefs.persona)));
  $("#club").value = S.prefs.club; $("#metric").value = S.prefs.metric; $("#speak").checked = S.prefs.speak;
  if ($("#lang").querySelector(`option[value="${S.prefs.lang}"]:not([disabled])`)) $("#lang").value = S.prefs.lang;
  if (S.meta) $("#focus").value = S.prefs.focus;
  $("#homeBug").classList.toggle("fav", S.prefs.club === "home");
  $("#awayBug").classList.toggle("fav", S.prefs.club === "away");
  document.documentElement.lang = S.prefs.lang;
  rerenderCards();
  updateMetric();
}

async function control(action, value) {
  return fetch(`/api/matches/${S.sid}/control`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, value }) }).then((r) => r.json());
}

function setPaused(p) { S.paused = p; $("#pauseBtn").textContent = p ? "Resume" : "Pause"; }

function bindControls() {
  $("#personaSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    S.prefs.persona = b.dataset.persona; savePrefs(); applyPrefs();
    if (!$("#tab-recap").hidden) loadRecap();
  });
  $("#lang").addEventListener("change", (e) => {
    S.prefs.lang = e.target.value; savePrefs(); applyPrefs();
    if (!(S.prefs.lang in S.i18n.languages)) control("langs", [S.prefs.lang]);
    if (!$("#tab-recap").hidden) loadRecap();
  });
  $("#club").addEventListener("change", (e) => { S.prefs.club = e.target.value; savePrefs(); applyPrefs(); });
  $("#focus").addEventListener("change", (e) => { S.prefs.focus = e.target.value; savePrefs(); applyPrefs(); });
  $("#metric").addEventListener("change", (e) => { S.prefs.metric = e.target.value; savePrefs(); updateMetric(); });
  $("#speak").addEventListener("change", (e) => { S.prefs.speak = e.target.checked; savePrefs(); if (!e.target.checked && "speechSynthesis" in window) { speechSynthesis.cancel(); S.speechQ = []; } });
  $("#pauseBtn").addEventListener("click", () => control(S.paused ? "resume" : "pause"));
  $("#speed").addEventListener("change", (e) => control("speed", Number(e.target.value)));
  $("#jump").addEventListener("change", (e) => { if (e.target.value) control("jump", Number(e.target.value)); e.target.value = ""; });

  document.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-ev]"); if (chip) return openEvidence(chip.dataset.ev);
    const say = e.target.closest("[data-say]"); if (say) { const i = S.insights.find((x) => x.id === say.dataset.say); if (i) queueSpeech({ ...i, salience: 1 }); return; }
    const q = e.target.closest("[data-q]"); if (q) return ask(q.dataset.q);
    const fol = e.target.closest("[data-follow]"); if (fol) { S.prefs.focus = S.prefs.focus === fol.dataset.follow ? "" : fol.dataset.follow; savePrefs(); applyPrefs(); renderPlayers(); return; }
    const ap = e.target.closest("[data-approve]"); if (ap) return decide(ap.dataset.approve, true);
    const rj = e.target.closest("[data-reject]"); if (rj) return decide(rj.dataset.reject, false);
    const th = e.target.closest("th[data-sort]"); if (th) { playerSort = th.dataset.sort; renderPlayers(); }
  });
  $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#askInput").value.trim(); if (v) { ask(v); $("#askInput").value = ""; } });
  $("#recapBtn").addEventListener("click", loadRecap);
  $("#drawerClose").addEventListener("click", () => { $("#drawer").hidden = true; });
  addEventListener("keydown", (e) => { if (e.key === "Escape") $("#drawer").hidden = true; });
  $$(".tabs [role=tab]").forEach((t) => t.addEventListener("click", () => {
    $$(".tabs [role=tab]").forEach((x) => x.setAttribute("aria-selected", String(x === t)));
    $$(".tabpanel").forEach((p) => { p.hidden = p.id !== "tab-" + t.dataset.tab; });
    if (t.dataset.tab === "players") renderPlayers();
    if (t.dataset.tab === "producer") renderProducer();
    if (t.dataset.tab === "ops") renderOps();
    if (t.dataset.tab === "recap") loadRecap();
  }));
  $("#modeSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    $$("#modeSeg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    control("mode", b.dataset.mode);
  });
  $("#newMatch").addEventListener("click", async () => {
    const body = { seed: Number($("#seed").value) || 42, chaos: Number($("#chaos").value), speed: Number($("#speed").value) || 10 };
    const r = await fetch("/api/matches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) return toast("Too many matches are running. Try again in a minute.");
    const d = await r.json();
    S.sid = d.session_id; $("#backDemo").hidden = false; connect();
    toast(`New match started with seed ${body.seed}`);
  });
  $("#backDemo").addEventListener("click", () => { S.sid = "demo"; $("#backDemo").hidden = true; connect(); });
}

async function decide(cueId, approve) {
  await fetch(`/api/matches/${S.sid}/cues/${encodeURIComponent(cueId)}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approve }) });
}

function toast(msg) {
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; t.setAttribute("role", "status");
  document.body.appendChild(t); setTimeout(() => t.remove(), 3200);
}

boot();
