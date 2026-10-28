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
  judge: location.pathname === "/judge" || new URLSearchParams(location.search).get("judge") === "1",
  judgeToken: null, judgeResume: false, story: null, centre: null,
  sid: new URLSearchParams(location.search).get("session") || "demo",
  es: null,
  historyTimer: null, pendingHistory: [],
  meta: null,
  players: {},
  snap: null,
  insights: [],
  lastPass: null,
  i18n: null,
  llm: { backend: "offline" },
  prefs: Object.assign({ persona: "casual", lang: "en", club: "", focus: "", favs: [], metric: "", speak: false, booth: false, view: "tactical" }, store.get("prefs", {})),
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
  story_duel: "Storyline", story_channel: "Storyline", story_keeper: "Storyline", story_waste: "Storyline", story_fatigue: "Storyline",
};
const EXTRA_LANGS = { de: "Deutsch", ja: "日本語", hi: "हिन्दी", ar: "العربية", zh: "中文", ta: "தமிழ்", sw: "Kiswahili" };
const isMine = (team) => !!team && (S.prefs.club === team || S.prefs.club === "both");
const isFav = (pid) => !!pid && (pid === S.prefs.focus || (S.prefs.favs || []).includes(pid));
const insPlayers = (ins) => [ins.player_id, ins.viz && ins.viz.player_id].filter(Boolean);
const CLUB_WORDS = {
  en: { mine: "Your club", against: "Against your club", player: "Your player" },
  es: { mine: "Tu club", against: "Contra tu club", player: "Tu jugador" },
  fr: { mine: "Ton club", against: "Contre ton club", player: "Ton joueur" },
  pt: { mine: "O teu clube", against: "Contra o teu clube", player: "O teu jogador" },
};
const POSITIVE = new Set(["goal", "chance_saved", "chance_missed", "chance_blocked", "line_break", "hard_pass", "sprint", "long_carry",
  "momentum", "phase", "press", "brace", "hat_trick", "record_shot", "standout", "saves", "wp_swing"]);

/* ------------------------------------------------------------------ boot */
async function startupJson(url) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(url, {signal: controller.signal});
    if (!response.ok) throw new Error(`Unavailable: ${url}`);
    return await response.json();
  } finally { clearTimeout(timer); }
}

function streamStatus(message = "") {
  const status = $("#connectionStatus");
  status.textContent = message; status.hidden = !message;
}

async function boot() {
  S.playerSpotlight = TouchlinePlayer.create({getState: () => S, getRender: rendersFor, openReceipt,
    onFollow: pid => {
      if (S.judge && $("#storyReplay")) $("#storyReplay").open = true;
      S.prefs.focus = pid; S.prefs.view = "player"; savePrefs(); applyPrefs(); applyView();
      $("#pitchBox").scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center"});
    }
  });
  if (!S.judge) S.centre = TouchlineCentre.create({getPrefs: () => S.prefs, getRender: rendersFor, getMemory: TouchlineStory.memoryLine});
  if (S.judge) {
    document.body.classList.add("judge-mode");
    const panel = $("#judgePanel"), hero = $("#judgeHeroImage");
    panel.hidden = false; panel.setAttribute("role", "main"); panel.tabIndex = -1;
    $(".skip-link").href = "#judgePanel";
    $("#judgeStart").disabled = true;
    streamStatus();
    hero.sizes = "(max-width: 767px) calc(100vw - 32px), min(100vw - 64px, 1376px)";
    hero.srcset = "/static/assets/varga-editorial-480.webp 480w, /static/assets/varga-editorial-960.webp 960w, /static/assets/varga-editorial.webp 1600w";
    hero.src = hero.dataset.src;
  }
  const [i18n, health] = await Promise.allSettled([startupJson("/api/i18n"), startupJson("/api/health")]);
  S.i18n = i18n.status === "fulfilled" ? i18n.value : { languages: { en: "English" }, banks: { en: {} } };
  if (health.status === "fulfilled") {
    S.llm = health.value.llm; S.speechNeural = !!health.value.speech?.available;
  }
  buildLangSelect();
  bindControls();
  bindTour();
  bindJudgeMode();
  loadMe();
  applyPrefs();
  applyView();
  addEventListener("resize", resizeCanvas);
  requestAnimationFrame(frame);
  if (S.judge) restoreJudge(); else connect();
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
  S.prefs.lang = sel.value;
}

let pitchLoad = null;
function loadPitch3D() {
  if (!pitchLoad) pitchLoad = import("/static/tv3d.js").catch(error => {
    console.warn("3D view unavailable; the tactical canvas remains available.", error);
    pitchLoad = null;
  });
}

function savePrefs() { store.set("prefs", S.prefs); }

/* ------------------------------------------------------------------ stream */
function connect() {
  if (S.es) S.es.close();
  clearTimeout(S.historyTimer); S.historyTimer = null; S.pendingHistory = [];
  S.insights = []; S.pos = {}; S.draws = []; S.snap = null;
  $("#mainStage").setAttribute("aria-busy", "true");
  streamStatus("Connecting to the match…");
  S.playerSpotlight?.reset();
  $("#cards").innerHTML = `<p class="empty">Moments appear here as they happen, each one checked against the match data before it's shown.</p>`;
  $("#trace").innerHTML = "";
  const es = new EventSource(`/api/matches/${S.sid}/stream`);
  S.es = es;
  es.addEventListener("open", () => $("#liveDot").classList.add("live"));
  es.addEventListener("error", () => {
    $("#liveDot").classList.remove("live");
    streamStatus(S.snap ? "Reconnecting… Showing the last received match state." : "Connection interrupted. Retrying automatically…");
  });
  es.addEventListener("session_expired", () => {
    es.close(); $("#liveDot").classList.remove("live");
    $("#pauseBtn").disabled = true; $("#mainStage").setAttribute("aria-busy", "false");
    const message = "This private replay has expired. Start a new replay.";
    streamStatus(message);
    if (S.judge) { $("#judgeStatus").textContent = message; try { sessionStorage.removeItem("tl.judge"); } catch { /* storage is optional */ } }
  });
  es.addEventListener("hello", (e) => onHello(JSON.parse(e.data)));
  es.addEventListener("state", (e) => onState(JSON.parse(e.data)));
  es.addEventListener("event", (e) => onEvent(JSON.parse(e.data)));
  es.addEventListener("insight", (e) => { const m = JSON.parse(e.data); onInsight(m.insight, m.replayed); });
  es.addEventListener("trace", (e) => onTrace(JSON.parse(e.data)));
  es.addEventListener("render", (e) => {
    const m = JSON.parse(e.data), ins = S.insights.find((x) => x.id === m.insight_id);
    if (!ins) return;
    ((ins.renders = ins.renders || {})[m.persona] = ins.renders[m.persona] || {})[m.lang] = m.render;
    S.story?.refresh();
    S.centre?.refresh();
    S.playerSpotlight?.refresh();
    if (m.persona === S.prefs.persona && m.lang === S.prefs.lang) {
      const old = document.querySelector(`.card[data-id="${CSS.escape(ins.id)}"]`);
      if (old) old.replaceWith(renderCard(ins));
    }
  });
  es.addEventListener("drill", (e) => onDrill(JSON.parse(e.data).drill));
  es.addEventListener("cue_update", (e) => onCueUpdate(JSON.parse(e.data).cue));
  es.addEventListener("control", (e) => { const m = JSON.parse(e.data); if (m.action === "pause") setPaused(true); if (m.action === "resume") setPaused(false); });
  es.addEventListener("judge_chapter", (e) => {
    const chapter = JSON.parse(e.data);
    const hint = "The next chapter unlocks when its goal arrives. Explore any chapter you have seen.";
    $("#judgeStatus").textContent = `${chapter.title}. ${hint}`;
  });
  es.addEventListener("done", (event) => {
    const replayed = JSON.parse(event.data || "{}").replayed;
    if (S.judge) {
      $("#judgeStatus").textContent = "The story is complete. Revisit a chapter, compare perspectives, and follow the thread back to its source.";
      $("#pauseBtn").disabled = true;
    } else if (!replayed) toast(["demo", "live"].includes(S.sid) ? "Full-time. A fresh live match starts shortly." : "Full-time. Explore this match's stories and evidence.");
  });
  $("#auditLink").href = `/api/matches/${S.sid}/audit`;
  $("#datasetLink").href = `/api/matches/${S.sid}/dataset.jsonl`;
}

function onHello(h) {
  // A reconnected SSE stream sends its history again. Rebuild rather than duplicate it.
  clearTimeout(S.historyTimer); S.historyTimer = null; S.pendingHistory = [];
  S.insights = []; rerenderCards();
  S.snap = null;
  S.pos = {}; S.from = {}; S.to = {}; S.lastT = 0; S.lastPass = null; S.ballEv = null; S.draws = [];
  for (const layer of Object.values(S.layers)) { clearTimeout(layer._t); layer.remove(); }
  S.layers = {}; S.speechQ = [];
  S.drills = {}; S.fb = {}; S.tags.forEach(tag => tag.el?.remove()); S.tags = [];
  window.TV3D?.reset?.();
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  S.playerSpotlight?.reset();
  S.centre?.reset();
  if (S.story) {
    document.body.classList.add("story-playing");
    $("#judgePanel").removeAttribute("role");
    $(".skip-link").href = "#mainStage";
    S.story.reset(h.judge?.moments);
    if ($("#storyReplay")?.open) loadPitch3D();
  }
  S.meta = h.match; S.llm = h.llm || S.llm;
  S.players = {};
  for (const t of [h.match.home, h.match.away]) for (const p of t.players) S.players[p.id] = { ...p, color: t.color };
  const { home, away } = h.match;
  $("#homeName").textContent = home.name; $("#awayName").textContent = away.name;
  $(".phone-link").href = `/phone?session=${encodeURIComponent(S.sid)}`;
  $("#matchLabel").textContent = `${home.name} v ${away.name}, ${h.match.venue}`;
  $("#homeShort").textContent = home.short; $("#awayShort").textContent = away.short;
  $("#homeSwatch").style.background = home.color; $("#awaySwatch").style.background = away.color;
  $("#lgHome").textContent = home.name; $("#lgAway").textContent = away.name;
  document.documentElement.style.setProperty("--home", home.color);
  document.documentElement.style.setProperty("--away", away.color);
  const club = $("#club");
  club.innerHTML = `<option value="">None</option><option value="home">${esc(home.name)}</option><option value="away">${esc(away.name)}</option><option value="both">Both clubs</option>`;
  club.value = S.prefs.club;
  const focus = $("#focus");
  focus.innerHTML = `<option value="">Nobody</option>` + [home, away].map((t) =>
    `<optgroup label="${esc(t.name)}">` + t.players.map((p) => `<option value="${p.id}">#${p.number} ${esc(p.name)} (${p.position})</option>`).join("") + "</optgroup>").join("");
  focus.value = S.players[S.prefs.focus] ? S.prefs.focus : "";
  drawTopology(h.topology);
  $("#speed").value = String(h.speed);
  renderSuggestions();
  applyPrefs();
  if (S.judge && S.judgeResume) {
    S.judgeResume = false;
    control("resume").catch(() => { $("#judgeStatus").textContent = "Could not start playback. Please restart."; });
  }
}

function tvBug(s) {
  let el = $("#tvbug");
  if (!el) { el = document.createElement("div"); el.id = "tvbug"; el.className = "tvbug"; $("#pitchBox").appendChild(el); }
  if (!S.meta) return;
  const clock = s.status === "half_time" ? "HT" : s.status === "full_time" ? "FT" : `${s.minute}'`;
  el.innerHTML = `<span class="c" style="--k:${S.meta.home.color}">${S.meta.home.short}</span><span class="sc">${s.score.home}-${s.score.away}</span><span class="c" style="--k:${S.meta.away.color}">${S.meta.away.short}</span><span class="clk">${clock}</span>`;
}

function onState(s) {
  S.snap = s;
  $("#mainStage").setAttribute("aria-busy", "false"); streamStatus();
  S.playerSpotlight?.refresh();
  if (s.drills && s.drills.length) { for (const d of s.drills) S.drills[d.id] = d; if (!$("#tab-ops").hidden) renderDrills(); }
  tvBug(s);
  const sc = s.score;
  $("#score").textContent = `${sc.home}-${sc.away}`;
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
  if (!$("#tab-ops").hidden) { renderOps(); renderDrills(); if (!S.svcAt || Date.now() - S.svcAt > 10000) { S.svcAt = Date.now(); renderServices(); } }
}

/* ------------------------------------------------------------------ events -> pitch */
function onEvent(ev) {
  const now = performance.now();
  if (!ev.replayed && window.TV3D && TV3D.ready) TV3D.onEvent(ev);
  if (ev.frame) {
    // Tracking frames are complete snapshots, including removals after a red card.
    for (const pid of Object.keys(S.pos)) {
      if (!(pid in ev.frame)) { delete S.pos[pid]; delete S.from[pid]; delete S.to[pid]; }
    }
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
    S.ballEv = ev;
    S.ballFrom = [...S.ball];
    S.ballMid = [ev.x, ev.y];
    S.ballTo = ev.end_x != null ? [ev.end_x, ev.end_y] : [ev.x, ev.y];
  }
  if (ev.etype === "pass") S.lastPass = ev;
  if (ev.etype === "kickoff") S.ball = [52.5, 34];
  if (ev.replayed) {
    // Bootstrap restores positions; historical events must not play as new actions.
    for (const [pid, p] of Object.entries(S.to)) S.pos[pid] = S.from[pid] = [...p];
    S.ball = [...S.ballTo]; S.ballFrom = [...S.ball]; S.ballMid = [...S.ball];
    S.ballEv = null; S.t0 = now - 1; S.dur = 1;
    return;
  }
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

function flushHistory() {
  clearTimeout(S.historyTimer); S.historyTimer = null;
  S.centre?.appendMany(S.pendingHistory); S.pendingHistory = [];
  rerenderCards(); drawTimeline();
  S.playerSpotlight?.refresh();
  $("#feedCount").textContent = `${S.insights.length} moments explained`;
}

function onInsight(ins, replayed) {
  if (S.judge && !["goal", "hat_trick"].includes(ins.kind)) return;
  if (!replayed && S.historyTimer) flushHistory();
  S.insights.push(ins);
  if (!S.judge && replayed) {
    // Reconnect and seek can deliver dozens of moments in one burst. Keep the data
    // immediately, then update the feed once while preserving a pinned goal.
    if (S.insights.length > 400) S.insights.shift();
    S.pendingHistory.push(ins);
    clearTimeout(S.historyTimer); S.historyTimer = setTimeout(flushHistory, 60);
    return;
  }
  S.story?.add(ins);
  S.centre?.add(ins);
  S.playerSpotlight?.refresh();
  if (S.insights.length > 400) S.insights.shift();
  const card = renderCard(ins);
  const cards = $("#cards");
  $(".empty", cards)?.remove();
  cards.prepend(card);
  while (cards.children.length > 80) cards.lastChild.remove();
  $("#feedCount").textContent = `${S.insights.length} moments explained`;
  if (!replayed && ins.cue && ins.cue.approval === "auto") playCue(ins);
  if (!replayed && window.TV3D && TV3D.ready && ins.salience >= 0.5) { const r = rendersFor(ins, "studio"); if (r) TV3D.board(r.title, ins.team && S.meta ? S.meta[ins.team].color : null); }
  if (!replayed && S.prefs.booth && ins.commentary && (ins.salience >= 0.5 || (ins.cue && ins.cue.approval === "auto"))) queueBooth(ins);
  else if (!replayed && (S.prefs.speak || S.prefs.persona === "access")) queueSpeech(ins);
  if (!$("#tab-producer").hidden) renderProducer();
  if (ins.kind === "half_time" || ins.kind === "full_time") loadRecap();
  if (!replayed && ins.kind === "goal" && !$("#tab-mine").hidden) loadReelPlan();
}

function clubFlag(ins) {
  const words = CLUB_WORDS[S.prefs.lang] || CLUB_WORDS.en;
  if (insPlayers(ins).some(isFav)) return words.player;
  if (!S.prefs.club || !ins.team) return "";
  if (isMine(ins.team)) return words.mine;
  if (S.prefs.club === "both") return "";
  return ["goal", "chance_saved", "chance_missed", "momentum", "press", "phase", "wp_swing", "line_break"].includes(ins.kind) ? words.against : "";
}

function renderCard(ins) {
  const r = rendersFor(ins);
  const el = document.createElement("article");
  el.className = "card " + (ins.team || "");
  el.dataset.id = ins.id;
  if (isMine(ins.team)) el.classList.add("mine");
  if (insPlayers(ins).some(isFav)) el.classList.add("focus");
  if (!r) { el.innerHTML = `<div class="meta">${ins.minute}' ${esc(KIND_LABEL[ins.kind] || ins.kind)}</div>`; return el; }
  const flag = clubFlag(ins);
  const v = ins.verification || {};
  const origin = TouchlineStory.provenance(r), src = origin.preview ? origin.label : "";
  el.innerHTML = `
    <div class="meta"><span class="min">${ins.minute}'</span><span>${esc(KIND_LABEL[ins.kind] || ins.kind)}</span>
      ${flag ? `<span style="color:var(--sodium)">${esc(flag)}</span>` : ""}
      ${v.status === "verified" ? `<span class="verified" title="${v.checks} checks against the underlying source frames"><svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.5l2.5 2.5L10 3.5" stroke="currentColor" stroke-width="2" fill="none"/></svg>Source checked</span>` : ""}
      ${ins.storyline && ins.storyline.length ? `<span style="color:var(--chalk)">Storyline</span>` : ""}
      <span class="src">${src}</span></div>
    <h3>${esc(r.title)}</h3>
    ${r.lines.length ? `<ul>${r.lines.map((l) => `<li>${esc(l.text)}</li>`).join("")}</ul>` : ""}
    ${origin.preview ? `<p class="generated-preview">${esc(origin.scope)}</p>` : ""}
    <div class="card-footer"><button class="chip receipt-link" data-receipt="${esc(ins.id)}">Evidence receipt</button><details class="card-details"><summary>Sources and feedback</summary><div class="chips">
      ${(ins.event_ids || []).slice(-4).map((id) => `<button class="chip" data-ev="${id}" title="Show the evidence">${id}</button>`).join("")}
      ${S.prefs.persona === "access" ? `<button class="chip speak" data-say="${ins.id}">Read aloud</button>` : ""}
      <span class="fb" role="group" aria-label="Was this useful?"><button class="chip" data-fb="${ins.id}" data-up="1" aria-pressed="${S.fb[ins.id] === 1}">Useful</button><button class="chip" data-fb="${ins.id}" data-up="0" aria-pressed="${S.fb[ins.id] === 0}">Not for me</button></span></div></details></div>`;
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
  // the Producer agent already decided this graphic airs (and cut anything it beat), so the client just plays it
  const viz = ins.viz || {};
  if (cue.layer === "player_tag") {
    showTag(viz.player_id, `${esc(viz.name)}<b>${viz.speed_kmh ? viz.speed_kmh + " km/h" : ""}</b>`, wall);
    return;
  }
  let el;
  // on air, the storyline is the line worth saying
  const story = r.lines.filter((l) => (l.k || "").startsWith("s."));
  const lead = story.length ? story[story.length - 1] : r.lines[0];
  const second = r.lines.find((l) => l !== lead);
  if (cue.layer === "lower_third") {
    el = layerEl("lower_third", "lower-third" + (cue.template === "full_banner" ? " banner" : "") + (ins.kind.startsWith("story") ? " story" : ""));
    el.style.setProperty("--team", ins.team && S.meta ? S.meta[ins.team].color : "var(--sodium)");
    const kick = { en: "Checked against the match data", es: "Verificado con los datos del partido", fr: "Vérifié avec les données du match", pt: "Verificado com os dados do jogo" };
    el.innerHTML = `<div class="bar"></div><div class="body"><span class="strap"></span><div class="kick"><svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.5l2.5 2.5L10 3.5" stroke="currentColor" stroke-width="2" fill="none"/></svg>${kick[S.prefs.lang] || kick.en}</div><div class="ttl">${esc(r.title)}</div>
      ${lead ? `<div class="ln">${esc(lead.text)}</div>` : ""}
      ${persona !== "casual" && second ? `<div class="ln">${esc(second.text)}</div>` : ""}</div>`;
  } else if (cue.layer === "side_panel") {
    el = layerEl("side_panel", "side-panel");
    el.innerHTML = `<div class="ttl">${esc(r.title)}</div>${r.lines.slice(0, 2).map((l) => `<div class="ln">${esc(l.text)}</div>`).join("")}${sidePanelViz(viz)}`;
  } else if (cue.layer === "full_screen") {
    el = layerEl("full_screen", "full-screen");
    el.innerHTML = `<div class="ttl">${esc(r.title)}</div>${r.lines.map((l) => `<div class="ln">${esc(l.text)}</div>`).join("")}`;
  } else return;
  el._prio = cue.priority; el._until = performance.now() + wall; el._cue = cue.cue_id;
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
  el.className = "player-tag" + (isFav(pid) ? " focus" : "");
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
  if (S.view === "tv" && window.TV3D && TV3D.ready && !S.flat) { stepScene(now); TV3D.render(now); placeTags3D(); return; }
  if (S.view === "tv") { stepScene(now); drawTV(now); return; }
  pitchLines();
  stepScene(now);

  S.draws = S.draws.filter((d) => d.until > now);
  for (const d of S.draws) drawViz(d, now);

  const r = Math.max(4, 1.05 * PX);
  for (const [pid, p] of Object.entries(S.pos)) {
    const pl = S.players[pid];
    if (!pl) continue;
    const focus = isFav(pid);
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
    if (!p || S.view === "tv") continue;
    tg.el.style.left = (X(p[0]) / DPR) + "px";
    tg.el.style.top = (Y(p[1]) / DPR) + "px";
  }
}

function placeTags3D() {
  for (const tg of S.tags) {
    const p = S.pos[tg.pid]; if (!p) continue;
    const [x, y, vis] = TV3D.project(p[0], p[1], 2.15);
    tg.el.style.left = x + "px"; tg.el.style.top = (y + 4) + "px"; tg.el.style.visibility = vis ? "" : "hidden";
  }
  placePlayerIdentity();
}

// One persistent identity follows the actual camera subject, including a replay.
// The label is projected from recorded pitch positions; no new animation meshes.
function placePlayerIdentity() {
  let label = $("#playerIdentity");
  const pid = S.view === "tv" && !S.flat ? window.TV3D?.focusedPlayer?.() : null;
  const player = S.players[pid], position = S.pos[pid];
  if (!player || !position) { if (label) label.hidden = true; return; }
  if (!label) {
    label = document.createElement("div"); label.id = "playerIdentity";
    label.className = "player-identity-tag"; $("#overlay").appendChild(label);
  }
  const [x, y, visible] = TV3D.project(position[0], position[1], 2.4);
  label.hidden = !visible;
  const identity = `#${player.number} ${player.name}`;
  if (label.textContent !== identity || label.dataset.player !== pid) {
    label.textContent = identity; label.dataset.player = pid;
  }
  const width = $("#pitchBox").clientWidth, half = label.offsetWidth / 2 + 8;
  label.style.left = `${Math.max(half, Math.min(width - half, x))}px`;
  label.style.top = `${Math.max(32, y - 12)}px`;
}

function stepScene(now) {
  const t = Math.min(1, (now - S.t0) / S.dur);
  const e = ease(t);
  for (const pid of Object.keys(S.to)) {
    const f = S.from[pid] || S.to[pid], to = S.to[pid];
    S.pos[pid] = [lerp(f[0], to[0], e), lerp(f[1], to[1], e)];
  }
  // ball: to the event origin quickly, then along the action (with height for lofted passes and shots)
  S.ballZ = 0.11;
  if (t < 0.25) { const k = ease(t / 0.25); S.ball = [lerp(S.ballFrom[0], S.ballMid[0], k), lerp(S.ballFrom[1], S.ballMid[1], k)]; }
  else {
    const k = ease((t - 0.25) / 0.75);
    S.ball = [lerp(S.ballMid[0], S.ballTo[0], k), lerp(S.ballMid[1], S.ballTo[1], k)];
    const ev = S.ballEv;
    if (ev && ev.end_x != null) {
      const d = Math.hypot(ev.end_x - ev.x, ev.end_y - ev.y);
      if (ev.etype === "pass" && ev.q && ev.q.height === "high") S.ballZ += 4 * Math.min(14, d / 3.2) * k * (1 - k);
      if (ev.etype === "shot") S.ballZ += 4 * 1.1 * k * (1 - k) + 0.9 * k;
    }
  }
}

/* ------------------------------------------------------------------ TV view: the broadcast camera (mirrors touchline/vision/camera.py) */
const TV = { tx: 52.5, ty: 30, camY: -40, camZ: 23, fov: 30 };
function tvBasis() {
  const c = [TV.tx, TV.camY, TV.camZ], tg = [TV.tx, TV.ty, 0];
  let f = [tg[0] - c[0], tg[1] - c[1], tg[2] - c[2]];
  const n = Math.hypot(...f); f = f.map((v) => v / n);
  let r = [f[1], -f[0], 0]; const rn = Math.hypot(...r); r = r.map((v) => v / rn);
  const u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
  return { c, f, r, u };
}
function tvProject(B, x, y, z = 0) {
  const d = [x - B.c[0], y - B.c[1], z - B.c[2]];
  const zc = Math.max(0.1, d[0] * B.f[0] + d[1] * B.f[1] + d[2] * B.f[2]);
  const xc = d[0] * B.r[0] + d[1] * B.r[1] + d[2] * B.r[2], yc = d[0] * B.u[0] + d[1] * B.u[1] + d[2] * B.u[2];
  const fl = (cv.width / 2) / Math.tan((TV.fov / 2) * Math.PI / 180);
  return [cv.width / 2 + fl * xc / zc, cv.height / 2 - fl * yc / zc, zc];
}
function tvPoly(B, pts, fill) {
  ctx.beginPath();
  pts.forEach(([x, y, z], i) => { const [px, py] = tvProject(B, x, y, z || 0); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
  ctx.closePath(); ctx.fillStyle = fill; ctx.fill();
}
function tvLine(B, pts, stroke, w) {
  ctx.beginPath();
  pts.forEach(([x, y, z], i) => { const [px, py] = tvProject(B, x, y, z || 0); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
  ctx.strokeStyle = stroke; ctx.lineWidth = w; ctx.stroke();
}
function drawTV(now) {
  // camera follows the ball, smoothly
  const bx = Math.min(Math.max(S.ball[0], 24), L - 24);
  TV.tx += (bx - TV.tx) * 0.035; TV.ty += ((30 + (S.ball[1] - 34) * 0.18) - TV.ty) * 0.035;
  const B = tvBasis(), lw = Math.max(1.5, cv.width / 700);
  ctx.fillStyle = "#102c21"; ctx.fillRect(0, 0, cv.width, cv.height);
  // the stand: tiers of seats with a crowd, and a perimeter board
  tvPoly(B, [[-30, 78, 0], [135, 78, 0], [135, 78, 14], [-30, 78, 14]], "#0d241b");
  tvPoly(B, [[-30, 78, 14], [135, 78, 14], [135, 92, 26], [-30, 92, 26]], "#132b22");
  if (!TV.crowd) { // deterministic crowd: one dot per seat block, team-coloured by end
    TV.crowd = []; let r = 7;
    for (let i = 0; i < 900; i++) { r = (r * 9301 + 49297) % 233280; const u = r / 233280; r = (r * 9301 + 49297) % 233280; const v = r / 233280;
      TV.crowd.push([-25 + u * 155, 78 + v * 13, 14 * (v) + 1.2 + (v * 13 > 0 ? (v * 12) : 0), u < 0.5 ? 0 : 1, (i * 37) % 5]); }
  }
  const tint = [S.meta ? S.meta.home.color : "#2f7cf6", S.meta ? S.meta.away.color : "#e5484d"];
  for (const [x, y, z, end, shade] of TV.crowd) {
    const [px, py, d] = tvProject(B, x, y, z);
    if (px < -5 || px > cv.width + 5) continue;
    ctx.fillStyle = shade < 2 ? tint[end] : shade < 4 ? "#2a3f36" : "#c9d3c4";
    ctx.globalAlpha = 0.55; ctx.fillRect(px, py, Math.max(1.5, 40 / d), Math.max(1.5, 40 / d)); ctx.globalAlpha = 1;
  }
  tvPoly(B, [[-30, 77, 0], [135, 77, 0], [135, 77, 1.0], [-30, 77, 1.0]], "#0f3a29");
  tvPoly(B, [[-6, -6], [L + 6, -6], [L + 6, W + 6], [-6, W + 6]], "#184a32");
  for (let k = 0; k < 18; k++) tvPoly(B, [[k * L / 18, 0], [(k + 1) * L / 18, 0], [(k + 1) * L / 18, W], [k * L / 18, W]], k % 2 ? "#1f5c3d" : "#1c5438");
  const chalk = "rgba(232,238,226,.9)";
  tvLine(B, [[0, 0], [L, 0], [L, W], [0, W], [0, 0]], chalk, lw);
  tvLine(B, [[L / 2, 0], [L / 2, W]], chalk, lw);
  tvLine(B, Array.from({ length: 49 }, (_, i) => [L / 2 + 9.15 * Math.cos(i / 48 * 2 * Math.PI), W / 2 + 9.15 * Math.sin(i / 48 * 2 * Math.PI)]), chalk, lw);
  for (const side of [0, 1]) {
    const xe = side ? L : 0, x16 = side ? L - 16.5 : 16.5, x6 = side ? L - 5.5 : 5.5;
    tvLine(B, [[xe, W / 2 - 20.16], [x16, W / 2 - 20.16], [x16, W / 2 + 20.16], [xe, W / 2 + 20.16]], chalk, lw);
    tvLine(B, [[xe, W / 2 - 9.16], [x6, W / 2 - 9.16], [x6, W / 2 + 9.16], [xe, W / 2 + 9.16]], chalk, lw);
    tvLine(B, [[xe, W / 2 - 3.66, 0], [xe, W / 2 - 3.66, 2.44], [xe, W / 2 + 3.66, 2.44], [xe, W / 2 + 3.66, 0]], "#fff", lw * 1.6);
  }
  // live graphics on the grass
  S.draws = S.draws.filter((d) => d.until > now);
  for (const d of S.draws) {
    if ((d.kind === "pass" || d.kind === "evidence") && d.end_x != null) tvLine(B, [[d.x, d.y], [d.end_x, d.end_y]], "rgba(242,193,78,.95)", lw * 2.2);
    if (d.kind === "shot") {
      tvLine(B, [[d.x, d.y], [d.end_x, d.end_y]], "rgba(238,240,232,.9)", lw * 2);
      const ring = Array.from({ length: 33 }, (_, i) => [d.x + (0.8 + d.xg * 5) * Math.cos(i / 32 * 2 * Math.PI), d.y + (0.8 + d.xg * 5) * Math.sin(i / 32 * 2 * Math.PI)]);
      tvLine(B, ring, "#f2c14e", lw * 2);
    }
  }
  // players, far to near
  const list = Object.entries(S.pos).map(([pid, p]) => {
    const foot = tvProject(B, p[0], p[1], 0), head = tvProject(B, p[0], p[1], 1.82);
    return { pid, p, foot, head };
  }).filter((o) => o.foot[2] > 0.5).sort((a, b) => b.foot[2] - a.foot[2]);
  for (const o of list) {
    const pl = S.players[o.pid]; if (!pl) continue;
    const [fx_, fy_] = o.foot, h = Math.max(6, fy_ - o.head[1]), w = h * 0.3;
    const gk = pl.position === "GK";
    const shirt = gk ? (pl.team === "home" ? "#7cc4ff" : "#ffb36b") : pl.color;
    ctx.fillStyle = "rgba(10,30,20,.75)"; ctx.beginPath(); ctx.ellipse(fx_, fy_, w * 0.9, w * 0.25, 0, 0, 7); ctx.fill();
    ctx.fillStyle = "#1e1e1e"; ctx.fillRect(fx_ - w * 0.32, fy_ - h * 0.42, w * 0.64, h * 0.42);
    ctx.fillStyle = "#11221a"; ctx.fillRect(fx_ - w * 0.5, fy_ - h * 0.55, w, h * 0.17);
    ctx.fillStyle = shirt; ctx.beginPath(); ctx.roundRect(fx_ - w * 0.55, fy_ - h * 0.86, w * 1.1, h * 0.33, Math.max(1, w * 0.25)); ctx.fill();
    ctx.fillStyle = "#c4967a"; ctx.beginPath(); ctx.ellipse(fx_, fy_ - h * 0.92, w * 0.26, h * 0.08, 0, 0, 7); ctx.fill();
    if (h > 40) { ctx.fillStyle = "#fff"; ctx.font = `700 ${Math.round(h * 0.17)}px Barlow Condensed, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(pl.number, fx_, fy_ - h * 0.7); }
    if (isFav(o.pid)) {
      ctx.strokeStyle = o.pid === S.prefs.focus ? "#f2c14e" : "#eef0e8"; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(fx_, fy_, w * 1.3, w * 0.4, 0, 0, 7); ctx.stroke();
      ctx.fillStyle = "#f2c14e"; ctx.font = `600 ${Math.max(12, Math.round(h * 0.2))}px Barlow, sans-serif`; ctx.textAlign = "center";
      ctx.fillText(pl.name.split(" ").slice(-1)[0], fx_, o.head[1] - Math.max(10, h * 0.15));
    }
  }
  // ball and its shadow
  const sh = tvProject(B, S.ball[0], S.ball[1], 0), bl = tvProject(B, S.ball[0], S.ball[1], S.ballZ || 0.11);
  const fl = (cv.width / 2) / Math.tan((TV.fov / 2) * Math.PI / 180), br = Math.max(2.5, fl * 0.24 / bl[2]);
  ctx.fillStyle = "rgba(10,30,20,.8)"; ctx.beginPath(); ctx.ellipse(sh[0], sh[1], br * 1.2, br * 0.45, 0, 0, 7); ctx.fill();
  ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(bl[0], bl[1], br, 0, 7); ctx.fill();
  // tags follow heads in TV view
  for (const tg of S.tags) {
    const p = S.pos[tg.pid]; if (!p) continue;
    const hd = tvProject(B, p[0], p[1], 2.1);
    tg.el.style.left = (hd[0] / DPR) + "px"; tg.el.style.top = (hd[1] / DPR + 6) + "px";
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
  const ticks = [15, 30, 45, 60, 75, 90].map((m) => `<text x="${x(m)}" y="${h - 4}" fill="#6f8a7b" font-size="10" text-anchor="middle" font-family="Barlow">${m}'</text>`).join("");
  svg.innerHTML = `
    <line x1="${x(45)}" x2="${x(45)}" y1="0" y2="${h}" stroke="#2a5242" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>
    <line x1="0" x2="${w}" y1="${h / 2}" y2="${h / 2}" stroke="#2a5242" vector-effect="non-scaling-stroke"/>
    <polygon points="${first},${h} ${home} ${last},${h}" style="fill:var(--home)" opacity=".35"/>
    <polygon points="${first},0 ${away} ${last},0" style="fill:var(--away)" opacity=".35"/>
    ${goals}
    <polyline points="${mom}" fill="none" stroke="#f2c14e" stroke-width="2" vector-effect="non-scaling-stroke"/>${ticks}`;
}

function updateMetric() {
  const m = S.prefs.metric, s = S.snap;
  $("#metricBox").hidden = !m;
  if (!m || !s) return;
  const meta = S.meta, side = ["home", "away"].includes(S.prefs.club) ? S.prefs.club : "home";
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
  if (!S.speechNeural && !("speechSynthesis" in window)) return;
  const r = rendersFor(ins, "access");
  if (!r) return;
  if (S.speechQ.length > 2 && ins.salience < 0.6) return;
  S.speechQ.push({ text: r.speech || r.title, lang: S.prefs.lang });
}
function queueBooth(ins) {
  const ex = ins.commentary[S.prefs.lang] || ins.commentary.en;
  if (!ex) return;
  if (S.speechQ.length > 3 && ins.salience < 0.8) return; // don't fall behind the play
  if (ins.kind === "goal") S.speechQ = S.speechQ.filter((q) => q.goal);
  for (const l of ex) S.speechQ.push({ text: l.text, lang: S.prefs.lang, who: l.who, goal: ins.kind === "goal" });
}
const BOOTH_NAMES = { en: { lead: "Commentary", analyst: "Analysis" }, es: { lead: "Narración", analyst: "Análisis" }, fr: { lead: "Commentaire", analyst: "Analyse" }, pt: { lead: "Relato", analyst: "Análise" } };
function caption(item) {
  const c = $("#caption");
  if (!item) { c.hidden = true; return; }
  const n = BOOTH_NAMES[item.lang] || BOOTH_NAMES.en;
  $("#capWho").textContent = item.who ? (n[item.who] || "") : "";
  $("#capText").textContent = item.text; c.dataset.who = item.who || ""; c.hidden = false;
}
function browserVoice(lang, who) {
  const vs = (window.speechSynthesis && speechSynthesis.getVoices()) || [];
  const loc = { en: "en-GB", es: "es-ES", fr: "fr-FR", pt: "pt-PT" }[lang] || lang;
  const mine = vs.filter((v) => v.lang && v.lang.toLowerCase().startsWith(lang));
  const exact = mine.filter((v) => v.lang === loc);
  const pool = exact.length > 1 ? exact : mine;
  return pool.length ? pool[who === "analyst" ? Math.min(1, pool.length - 1) : 0] : null;
}
let speaking = false;
function tickSpeech() {
  if (speaking || !S.speechQ.length) return;
  const item = S.speechQ.shift();
  const done = () => { speaking = false; setTimeout(() => { if (!speaking) caption(null); }, 900); };
  speaking = true;
  if (item.who) caption(item);
  if (S.speechNeural) {
    const a = new Audio(`/api/speak?lang=${encodeURIComponent(item.lang)}&voice=${item.who || "lead"}&text=${encodeURIComponent(item.text)}`);
    a.onended = a.onerror = done;
    a.play().catch(done);
    return;
  }
  if (!("speechSynthesis" in window)) { setTimeout(done, 2200); return; }
  const u = new SpeechSynthesisUtterance(item.text);
  u.lang = { en: "en-GB", es: "es-ES", fr: "fr-FR", pt: "pt-PT" }[item.lang] || item.lang;
  const v = browserVoice(item.lang, item.who); if (v) u.voice = v;
  // two distinct voices even when the browser has only one: the lead is quicker and brighter
  u.rate = item.who === "lead" ? 1.12 : 0.98; u.pitch = item.who === "lead" ? 1.08 : item.who === "analyst" ? 0.82 : 1;
  u.onend = u.onerror = done;
  speechSynthesis.speak(u);
}

/* ------------------------------------------------------------------ evidence drawer */
let drawerTrigger = null;
let drawerBackground = [];
function showDrawer() {
  if (!$("#drawer").contains(document.activeElement)) drawerTrigger = document.activeElement;
  if ($("#drawer").hidden) {
    drawerBackground = [...document.body.children].filter(el => el !== $("#drawer")).map(el => [el, el.inert]);
    drawerBackground.forEach(([el]) => { el.inert = true; });
  }
  $("#drawer").hidden = false;
  $("#drawerClose").focus();
}
function closeDrawer() {
  $("#drawer").hidden = true;
  drawerBackground.forEach(([el, wasInert]) => { el.inert = wasInert; });
  drawerBackground = [];
  if (drawerTrigger?.isConnected) drawerTrigger.focus();
}

function drawerKeys(e) {
  const drawer = $("#drawer");
  if (drawer.hidden) return;
  if (e.key === "Escape") { e.preventDefault(); closeDrawer(); return; }
  if (e.key !== "Tab") return;
  const focusable = [...drawer.querySelectorAll('button, a[href], input, select, textarea, summary, [tabindex="0"]')]
    .filter(el => !el.disabled && el.getClientRects().length);
  const first = focusable[0], last = focusable.at(-1);
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
  if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
}

async function openReceipt(id) {
  try {
    const query = new URLSearchParams({ persona: S.prefs.persona, lang: S.prefs.lang });
    const response = await fetch(`/api/matches/${S.sid}/insights/${encodeURIComponent(id)}/receipt?${query}`);
    if (!response.ok) throw new Error("Receipt unavailable. The replay may have expired; restart to try again.");
    const raw = await response.text(), d = JSON.parse(raw), r = d.render, v = d.verification, ed = d.editorial;
    const chips = (ids) => ids.map(eid => {
      const event = d.evidence.find(item => item.event_id === eid), fact = event?.facts;
      const label = fact ? `${fact.minute}′ · ${fact.player || "Match"} · ${fact.type}${fact.outcome ? ` / ${fact.outcome}` : ""}` : eid;
      return `<button class="chip receipt-source" data-ev="${esc(eid)}" title="${esc(eid)}">${esc(label)}</button>`;
    }).join(" ");
    $("#drawerBody").innerHTML = `<span class="eyebrow">Evidence receipt · Synthetic match</span>
      <h3>${esc(r?.title || id)}</h3>
      <p class="muted">${d.minute}′ · ${({casual:"Fan",analyst:"Analyst",studio:"Studio",access:"Audio description"})[r?.persona || S.prefs.persona] || "Selected audience"} · ${esc(r?.lang || S.prefs.lang)}</p>
      ${TouchlineStory.provenance(r).preview ? `<p class="generated-preview"><strong>Model-generated preview.</strong> ${esc(TouchlineStory.provenance(r).scope)}</p>` : ""}
      <div class="receipt-verdict"><strong>${v.status === "verified" ? "Source checks passed" : esc(v.status)}</strong><p>${v.checks} checks against ${d.evidence.length} cited events. Inspect the source behind each claim below.</p></div>
      ${v.issues.length ? `<ul>${v.issues.map(issue => `<li>${esc(issue)}</li>`).join("")}</ul>` : ""}
      <p class="muted">${esc(d.scope)}</p>
      <h4>What was said → where it came from</h4>
      ${(r?.lines || []).map(line => `<div class="receipt-claim"><p>${esc(line.text)}</p>${chips(line.ev || [])}</div>`).join("")}
      <details class="receipt-comparison"><summary>Compare Fan and Analyst</summary>
        <p class="muted">The same moment and evidence, written for two audiences.</p>
        ${Object.entries(d.audiences || {}).filter(([, copy]) => copy).map(([persona, copy]) => `<article>
          <span class="eyebrow">${persona === "casual" ? "Fan" : "Analyst"} · ${esc(copy.lang)}</span>
          <h4>${esc(copy.title)}</h4>${(copy.lines || []).map(line => `<p>${esc(line.text)}</p>`).join("")}</article>`).join("")}
      </details>
      <h4>Editorial decision</h4><p>${esc(ed?.decision?.reason || "No cue emitted: the insight did not pass verification.")}</p>
      <details class="receipt-meta"><summary>Technical receipt and model inputs</summary>
      <p class="muted">Insight ${esc(id)} · ${esc(r?.source || "no render")}</p>
      ${ed ? `<p class="muted">${esc(ed.approval)} · Cue ${esc(ed.cue_id)} · ${ed.in_at_t}–${ed.out_at_t} seconds on the match clock.</p>` : ""}
      <details><summary>Inspect facts and model factors for ${d.evidence.length} events</summary>
      ${d.evidence.map(e => `<details><summary>${esc(e.facts.minute)}′ · ${esc(e.facts.player || "Match")} · ${esc(e.facts.type)} · ${esc(e.event_id)}</summary>
        <p>${chips([e.event_id])} Open the event for its facts and model factors.</p>
        <pre>${esc(JSON.stringify(e.facts, null, 2))}</pre>
        ${e.model_drivers.length ? `<p class="muted">Model contributions (log-odds relative to the synthetic league baseline)</p><pre>${esc(JSON.stringify(e.model_drivers, null, 2))}</pre>` : ""}</details>`).join("")}</details>
      <details><summary>Claim inputs and citations</summary><pre>${esc(JSON.stringify(d.claims, null, 2))}</pre></details>
      <h4>Agents that contributed</h4>
      <details><summary>${d.agents.length} recorded agent handoffs</summary>
      <ol class="receipt-agents">${d.agents.map(a => `<li><strong>${esc(a.agent)}</strong> · ${esc(a.status)} · ${a.ms} ms<br><span class="muted">${esc(a.note)}${a.handoff_to ? ` → ${esc(a.handoff_to)}` : ""}</span></li>`).join("")}</ol>
      </details>
      <p><strong>${d.pipeline_ms} ms</strong> · ${esc(d.timing_scope)}</p></details>
      <button class="btn primary" id="downloadReceipt">Download evidence receipt</button>
      <p class="muted">JSON containing this moment's facts, checks, audience versions and agent handoffs.</p>`;
    $("#downloadReceipt").addEventListener("click", () => {
      const url = URL.createObjectURL(new Blob([raw], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url;
      link.download = `touchline-${d.insight_id.replace(/[^a-z0-9_-]/gi, "_")}-receipt.json`;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    showDrawer();
  } catch (error) { toast(error.message); }
}

async function openEvidence(id) {
  const res = await fetch(`/api/matches/${S.sid}/events/${id}`);
  if (!res.ok) return toast("That event isn't available yet.");
  const d = await res.json();
  const f = d.facts, ev = d.event;
  const LABEL = { distance_m: "Distance (m)", ball_speed_kmh: "Ball speed (km/h)", shot_speed_kmh: "Shot speed (km/h)", speed_kmh: "Speed (km/h)",
    pass_type: "Pass type", body_part: "Body part", xg: "xG", pass_difficulty: "Pass difficulty (0-100)", pass_completion_prob: "Completion probability (%)",
    opponents_bypassed: "Opponents bypassed", xt_added: "Threat added (xT)", win_prob_before: "Win probability before", win_prob_after: "Win probability after",
    minute: "Minute", type: "Event", team: "Team", player: "Player", target: "Receiver", outcome: "Outcome" };
  const rows = Object.entries(f).filter(([k]) => !["event_id"].includes(k)).map(([k, v]) =>
    `<tr><td>${esc(LABEL[k] || k.replace(/_/g, " "))}</td><td class="num">${esc(v === null ? "Not recorded" : typeof v === "object" ? Object.entries(v).map(([a, b]) => `${a === "home" ? S.meta.home.short : a === "away" ? S.meta.away.short : a} ${b}%`).join(", ") : v)}</td></tr>`).join("");
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
  showDrawer();
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

function answerExecution(r) {
  if (!r.execution) return "";
  const e = r.execution;
  const fallback = r.source === "router" || e.path === "application_fallback";
  const attempt = fallback ? (e.model_attempt || (e.path !== "application_fallback" ? e : null)) : e;
  const label = (path) => path === "foundry_hosted" ? "Microsoft Foundry hosted agent"
    : path === "local_agent" ? "Local Agent Framework agent"
    : path === "capacity_limit" ? "Model capacity limit" : "Model execution unavailable";
  const heading = fallback ? "Application fallback · answered from match data" : label(e.path);
  const detail = fallback ? (attempt ? `Model attempt: ${label(attempt.path)} · ${attempt.completed ? "completed; answer not accepted" : "did not complete"}` : "No model attempt for this answer")
    : `${e.fallback ? "Model transport fallback used · " : ""}${r.grounding?.tool_results || 0} tool results checked`;
  return `<details class="qa-proof"><summary>How this answer ran</summary><p>${esc(heading)}</p>
    <p>${esc(detail)}${attempt?.model ? ` · ${esc(attempt.model)}` : ""}</p>
    ${fallback ? `<p>Reason: ${esc(r.fallback_reason || e.fallback_reason || "source route")}</p>` : ""}
    <p class="muted">${esc(r.grounding?.scope || "")}${attempt?.request_id ? ` Request ${esc(attempt.request_id)}` : ""}</p></details>`;
}

async function ask(q) {
  const box = document.createElement("div");
  box.innerHTML = `<div class="q">${esc(q)}</div><div class="a muted">Thinking…</div>`;
  $("#qa").prepend(box);
  try {
    const r = await fetch(`/api/matches/${S.sid}/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, lang: S.prefs.lang }) }).then((x) => x.json());
    box.innerHTML = `<div class="q">${esc(q)}</div><div class="a">${esc(r.answer)}</div>
      <div class="chips">${(r.citations || []).slice(0, 6).map((id) => `<button class="chip" data-ev="${id}">${id}</button>`).join("")}</div>
      <div class="by">${r.source === "router" ? "Answered from the live match data" : r.composition === "source_rendered_selection" ? "Composed from source facts selected by the analyst agent" : "Analyst response · inspect its validation scope below"} in ${r.ms} ms${r.language ? ` · ${esc(r.language)}` : ""}</div>
      ${answerExecution(r)}`;
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

let playerSort = "rating", playerSortDirection = "descending";
function renderPlayers() {
  const s = S.snap; if (!s || !S.meta) return;
  const table = $("#playersTable"), active = table.contains(document.activeElement) ? document.activeElement : null;
  const focusKey = active && ["sort", "fav", "follow"].find(key => active.dataset[key]);
  const focusValue = focusKey ? active.dataset[focusKey] : null;
  const rows = Object.entries(s.players).map(([pid, v]) => ({ pid, ...S.players[pid], ...v, acc: v.passes ? Math.round(v.completed / v.passes * 100) : null }));
  rows.sort((a, b) => {
    const av = a[playerSort], bv = b[playerSort];
    if (av == null || bv == null) return av == null ? (bv == null ? 0 : 1) : -1;
    const diff = typeof av === "string" ? av.localeCompare(bv) : av - bv;
    return (playerSortDirection === "ascending" ? diff : -diff) || a.name.localeCompare(b.name);
  });
  const cols = [["number", "#"], ["name", "Player"], ["position", "Pos"], ["rating", "Rating"], ["passes", "Passes"], ["acc", "Pass %"], ["xt", "Threat (xT)"], ["xg", "xG"], ["top_speed_kmh", "Top km/h"], ["distance_km", "Km"]];
  $("#playersTable thead").innerHTML = `<tr>${cols.map(([k, l]) => `<th scope="col" ${playerSort === k ? `aria-sort="${playerSortDirection}"` : ""} class="${["name", "position"].includes(k) ? "" : "num"}"><button type="button" data-sort="${k}" aria-label="Sort by ${esc(l === "#" ? "shirt number" : l)}">${l}<span aria-hidden="true">${playerSort === k ? (playerSortDirection === "ascending" ? " ↑" : " ↓") : " ↕"}</span></button></th>`).join("")}<th scope="col">Actions</th></tr>`;
  $("#playersTable tbody").innerHTML = rows.map((p) => {
    const acc = p.passes ? Math.round((p.completed / p.passes) * 100) : "–";
    return `<tr><td>${p.number}</td><td><span class="dot" style="background:${p.color}"></span>${esc(p.name)}</td><td>${p.position}</td>
      <td class="num">${p.rating}</td><td class="num">${p.passes}</td><td class="num">${acc}</td><td class="num">${p.xt}</td><td class="num">${p.xg}</td>
      <td class="num">${p.top_speed_kmh}</td><td class="num">${p.distance_km}</td>
      <td class="acts"><button class="btn small" data-fav="${p.pid}" aria-label="Favourite ${esc(p.name)}" aria-pressed="${(S.prefs.favs || []).includes(p.pid)}">${(S.prefs.favs || []).includes(p.pid) ? "Favourite" : "Add favourite"}</button>
      <button class="btn small" data-follow="${p.pid}" aria-label="Follow ${esc(p.name)}" aria-pressed="${S.prefs.focus === p.pid}">${S.prefs.focus === p.pid ? "Following" : "Follow"}</button></td></tr>`;
  }).join("");
  if (focusKey) table.querySelector(`[data-${focusKey}="${CSS.escape(focusValue)}"]`)?.focus({preventScroll:true});
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
  const ACT = { air: "Aired", bump: "Cut in", queue: "Queued", drop: "Dropped" };
  const dec = S.insights.filter((i) => i.cue && i.cue.decision).slice(-8).reverse();
  $("#rundown").innerHTML = dec.map((i) => {
    const d = i.cue.decision, r = rendersFor(i, "studio");
    return `<div class="cue dec ${d.action}"><span class="act">${ACT[d.action] || d.action}</span><div><div class="t">${esc(r ? r.title : i.kind)}</div><div class="s">${i.minute}', score ${Number(d.score).toFixed(2)}. ${esc(d.reason)}</div></div></div>`;
  }).join("") || `<p class="muted">Decisions appear as moments compete for the screen.</p>`;
  const last = S.insights.filter((i) => i.cue).slice(-1)[0];
  if (last) {
    const c = { ...last.cue }; delete c.data;
    $("#cueJson").textContent = JSON.stringify(c, null, 2);
  }
  applyCapabilities();
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
    [o.producer.decisions ? `${o.producer.decisions.air + o.producer.decisions.bump} / ${o.producer.decisions.bump} / ${o.producer.decisions.drop}` : o.producer.aired, "graphics aired / cut in / dropped by the Producer"],
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

async function renderServices() {
  try {
    const [h, d, fb] = await Promise.all([fetch("/api/health").then((r) => r.json()), fetch("/api/downstream").then((r) => r.json()),
      fetch(`/api/matches/${S.sid}/feedback`).then((r) => r.json())]);
    const llm = h.llm || {}, cs = h.content_safety || {}, sp = h.speech || {};
    const row = (on, name, detail) => `<div class="${on ? "on" : "off"}"><b>${esc(name)}</b><span>${esc(detail)}</span></div>`;
    $("#svcList").innerHTML = [
      row(llm.backend === "foundry", "Microsoft Foundry", llm.backend === "foundry" ? `${llm.model}; ${(llm.hosted_agents || []).length ? "hosted agents: " + llm.hosted_agents.join(", ") : "agents run locally on the Foundry model"}; ${llm.calls} calls` : llm.backend === "offline" ? "not configured here: verified phrase banks in use" : `${llm.backend}, ${llm.model}`),
      row(true, "Microsoft Agent Framework", "workflow with fan-out and fan-in, supervisor, A2A endpoint"),
      row(cs.mode === "azure", "Azure AI Content Safety", cs.mode === "azure" ? `${cs.checked} checks, ${cs.blocked} blocked, ${cs.shield_attacks} prompt attacks refused` : `local screen: ${cs.shield_attacks || 0} prompt attacks refused`),
      row(sp.available, "Azure AI Speech", sp.available ? `${sp.mode} auth, ${sp.calls} syntheses` : "browser voices in use"),
      row(h.auth === "entra", "Microsoft Entra ID", h.auth === "entra" ? "producer tools need the Producer role" : "public demo; shared controls follow deployment permissions"),
      row(fb.votes > 0, "Viewer feedback", fb.votes ? `${Math.round(fb.useful_rate * 100)}% of ${fb.votes} votes say the graphic was useful` : "no votes yet: press Useful or Not for me on any card"),
      row(d.outbound && d.outbound.enabled, "Azure Event Hubs", d.outbound && d.outbound.enabled ? `${d.outbound.sent} insights streamed to ${d.outbound.hub}` : "not configured here"),
    ].join("");
    const p = d.packages;
    $("#downstream").innerHTML = p && !p.error
      ? row(true, "Post-match packages", `${p.packages_built} built${p.latest ? `; latest ${p.latest.home} ${p.latest.score.home}-${p.latest.score.away} ${p.latest.away}` : ""}`) +
        row(true, "Social cards", `${(p.recent_social_cards || []).length} recent`) + row(true, "Watchdog", "health check every 5 minutes")
      : row(false, "Azure Functions", p && p.error ? "unreachable: " + p.error : "deployed with azd up; the package endpoint is /api/matches/{id}/package");
  } catch (e) { /* offline */ }
}

/* ------------------------------------------------------------------ what if */
async function loadWhatIf() {
  try {
    const d = await fetch(`/api/matches/${S.sid}/whatif`).then((r) => r.json());
    $("#wiList").innerHTML = d.scenarios.map((x) => `<button class="btn small wi" data-wi="${esc(x.id)}">${esc(x.label)}</button>`).join("") || `<p class="muted">Nothing to change yet.</p>`;
  } catch (e) { /* offline */ }
}
function wiBar(label, r) {
  const h = S.meta ? S.meta.home : { short: "Home", color: "#1f6feb" }, a = S.meta ? S.meta.away : { short: "Away", color: "#e5484d" };
  const seg = (v, c, t) => v > 0.001 ? `<span style="width:${v * 100}%;background:${c}" title="${t} ${Math.round(v * 100)}%">${v >= 0.08 ? Math.round(v * 100) + "%" : ""}</span>` : "";
  return `<div class="wi-row"><b>${esc(label)}</b><div class="wi-bar" role="img" aria-label="${esc(label)}: ${h.short} ${Math.round(r.home * 100)}%, draw ${Math.round(r.draw * 100)}%, ${a.short} ${Math.round(r.away * 100)}%">${seg(r.home, h.color, h.short)}${seg(r.draw, "#5b6b62", "Draw")}${seg(r.away, a.color, a.short)}</div></div>`;
}
async function runWhatIf(id) {
  $$("[data-wi]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.wi === id)));
  $("#wiOut").innerHTML = `<p class="muted">Replaying the rest of the match 1,000 times…</p>`;
  const r = await fetch(`/api/matches/${S.sid}/whatif`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario: id }) });
  if (!r.ok) { $("#wiOut").innerHTML = `<p class="muted">That moment isn't available any more.</p>`; return; }
  const d = await r.json();
  $("#wiTitle").textContent = d.scenario.label;
  const h = S.meta ? S.meta.home.short : "H", a = S.meta ? S.meta.away.short : "A";
  $("#wiOut").innerHTML = `${wiBar("As it was", d.as_it_was.result)}${wiBar("What if", d.what_if.result)}
    <p class="wi-sum">${esc(d.summary)}</p>
    <p class="muted">Likeliest final scores if it had happened: ${d.what_if.scorelines.map((x) => `${h} ${x.home}-${x.away} ${a} (${Math.round(x.share * 100)}%)`).join(", ")}.</p>
    <p class="muted small">${esc(d.note)}</p>`;
}

/* ------------------------------------------------------------------ guided tour */
const TOUR = [
  { sel: "#pitchBox", title: "The match, in a 3D stadium", text: "Watch the synthetic replay. Source checks test supported facts before a graphic airs; model-written wording is labelled as a preview.",
    go: () => { S.prefs.view = "tv"; applyView(); } },
  { sel: "#cards", title: "Why it matters", text: "Each moment is explained, not just reported. Open its Evidence receipt to trace the claims to recorded match events." },
  { sel: "#personaSeg", title: "Four voices for every moment", text: "Compare Fan, Analyst, Studio and Audio description versions. Choose from the languages available in this deployment.",
    go: () => $('[data-persona="analyst"]').click() },
  { sel: "label:has(#booth)", title: "Two-voice commentary", text: "Tick Commentary to hear the call and explanation, with captions. Check the receipt for source facts and the limits of each verification.",
    go: () => { if (!$(".prefs").classList.contains("open")) $("#moreBtn").click(); } },
  { sel: '[data-tab="whatif"]', title: "What if?", text: "Change one thing, like a red card that never happened, and replay the rest of the match 1,000 times.",
    go: async () => { $('[data-tab="whatif"]').click(); await loadWhatIf(); const b = $('[data-wi^="nored"]') || $("[data-wi]"); if (b) runWhatIf(b.dataset.wi); } },
  { sel: '[data-tab="producer"]', title: "Editorial decisions", text: "A producer agent airs, cuts in, queues or drops each graphic, and says why. Review mode supports human approval; goals, red cards and full-time remain automatic.",
    go: () => $('[data-tab="producer"]').click() },
  { sel: '[data-tab="ops"]', title: "Inspect the agents", text: "See the agent trace and service status. Where producer controls are enabled, a failure drill tests the system's recovery.",
    go: () => $('[data-tab="ops"]').click() },
  { sel: '[data-tab="mine"]', title: "Your match, your reel", text: "After the whistle, every fan gets their own highlights, replayed in the 3D stadium and saved from the browser.",
    go: () => $('[data-tab="mine"]').click() },
  { sel: ".phone-link", title: "And on your phone", text: "Open Touchline as a second screen: your player's numbers, ask by voice, and a buzz when their club scores." },
];
let tourAt = -1, tourSaved = null, tourTrigger = null;
async function tourShow(i) {
  $$(".tour-focus").forEach((x) => x.classList.remove("tour-focus"));
  if (i < 0 || i >= TOUR.length) return tourEnd();
  tourAt = i;
  const st = TOUR[i];
  if (st.go) await st.go();
  if (tourAt !== i) return;
  const el = $(st.sel);
  if (el) { el.classList.add("tour-focus"); el.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" }); }
  $("#tourStep").textContent = `${i + 1} of ${TOUR.length}`;
  $("#tourTitle").textContent = st.title; $("#tourText").textContent = st.text;
  $("#tourBack").disabled = i === 0; $("#tourNext").textContent = i === TOUR.length - 1 ? "Done" : "Next";
  $("#tour").hidden = false; $("#tourNext").focus({ preventScroll: true });
}
function tourEnd() {
  $$(".tour-focus").forEach((x) => x.classList.remove("tour-focus"));
  $("#tour").hidden = true; tourAt = -1;
  if (tourSaved) {
    S.prefs.persona = tourSaved.persona; S.prefs.view = tourSaved.view;
    savePrefs(); applyPrefs(); applyView();
    if ($(".prefs").classList.contains("open") !== tourSaved.preferencesOpen) $("#moreBtn").click();
    tourSaved = null;
  }
  if (tourTrigger?.isConnected) tourTrigger.focus({preventScroll:true});
}
function bindTour() {
  $("#tourBtn").addEventListener("click", () => {
    tourTrigger = document.activeElement;
    tourSaved = {persona:S.prefs.persona, view:S.prefs.view, preferencesOpen:$(".prefs").classList.contains("open")};
    tourShow(0);
  });
  $("#tourNext").addEventListener("click", () => tourShow(tourAt + 1));
  $("#tourBack").addEventListener("click", () => tourShow(tourAt - 1));
  $("#tourClose").addEventListener("click", tourEnd);
  document.addEventListener("keydown", (e) => { if (tourAt >= 0 && e.key === "Escape") tourEnd(); });
  if (new URLSearchParams(location.search).get("tour")) setTimeout(() => $("#tourBtn").click(), 2500);
}

S.fb = {};
async function feedback(id, up) {
  S.fb[id] = up;
  $$(`[data-fb="${id}"]`).forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.up) === up)));
  fetch(`/api/matches/${S.sid}/feedback`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ insight_id: id, useful: up === 1, persona: S.prefs.persona, lang: S.prefs.lang }) }).catch(() => {});
}

S.drills = {};
function onDrill(d) { S.drills[d.id] = d; renderDrills(); }
function renderDrills() {
  const list = Object.values(S.drills).sort((a, b) => b.started - a.started);
  $("#drillLog").innerHTML = list.map((d) => {
    const det = d.detected ? `caught by <b>${esc(d.detected_by)}</b> after ${Math.max(0, Math.round((d.detected - d.started) * 1000))} ms` : "waiting for the fault to hit…";
    const rec = d.recovered ? `recovered in ${(d.ms / 1000).toFixed(1)} s` : d.detected ? "recovering" : "";
    return `<li class="${d.recovered ? "ok" : d.detected ? "busy" : ""}"><div class="t">${esc(d.label)} <span class="muted">${d.minute}'</span></div>
      <div class="s">${det}${rec ? `, ${rec}` : ""}.</div>${d.notes.length ? `<div class="s">${d.notes.map((n) => esc(n.charAt(0).toUpperCase() + n.slice(1))).join(". ")}.</div>` : ""}</li>`;
  }).join("") || `<li class="muted">No drills run yet.</li>`;
}
async function runDrill(name) {
  const r = await control("drill", name);
  if (r && r.ok === false) toast(r.reason === "already running" ? "That drill is already running." : "Couldn't start that drill.");
}

function onCueUpdate(cue) {
  for (const i of S.insights) if (i.cue && i.cue.cue_id === cue.cue_id) {
    const was = i.cue.approval; i.cue = cue;
    if (cue.approval === "approved" || (cue.approval === "auto" && was === "queued")) playCue(i);
    if (cue.approval === "bumped") { const el = S.layers[cue.layer]; if (el && el._cue === cue.cue_id) { el._until = 0; clearTimeout(el._t); hideLayer(cue.layer, el); } }
  }
  if (!$("#tab-producer").hidden) renderProducer();
}

function drawTopology(topo) {
  const svg = $("#topology");
  svg.setAttribute("viewBox", "0 0 590 300");
  const nodes = {
    "IngestGuard": [10, 20], "MatchState": [10, 80], "MomentScout": [10, 140], "TacticalAnalyst": [10, 200], "StorylineKeeper": [190, 140], "FactChecker": [190, 200],
    "Narrator[casual]": [370, 20], "Narrator[analyst]": [370, 80], "Narrator[studio]": [370, 140], "Narrator[access]": [370, 200], "Producer": [370, 260], "CommentaryBooth": [190, 260],
  };
  const w = 170, h = 34;
  const edge = ([a, b]) => {
    if (!nodes[a] || !nodes[b]) return "";
    const [x1, y1] = nodes[a], [x2, y2] = nodes[b];
    const sx = x1 + (x2 > x1 ? w : w / 2), sy = y1 + (x2 > x1 ? h / 2 : h), ex = x2 + (x2 > x1 ? 0 : w / 2), ey = y2 + (x2 > x1 ? h / 2 : 0);
    return `<path d="M${sx},${sy} C${(sx + ex) / 2},${sy} ${(sx + ex) / 2},${ey} ${ex},${ey}" fill="none" stroke="#2a5242" stroke-width="1.5"/>`;
  };
  const fanIn = ["casual", "analyst", "studio", "access"].map((p) => {
    const [x, y] = nodes[`Narrator[${p}]`];
    return `<path d="M${x + w},${y + h / 2} C${x + w + 30},${y + h / 2} ${x + w + 30},${277} ${x + w},${277}" fill="none" stroke="#2a5242" stroke-width="1.5"/>`;
  }).join("");
  const edges = (topo ? topo.edges : []).filter(([a, b]) => b !== "Producer").map(edge).join("") + fanIn;
  svg.innerHTML = edges + Object.entries(nodes).map(([n, [x, y]]) =>
    `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="${n === "FactChecker" ? "#3d3415" : "#184232"}" stroke="${n === "FactChecker" ? "#f2c14e" : n === "StorylineKeeper" ? "#a6b3a9" : "#2a5242"}"/>
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

/* ------------------------------------------------------------------ my match */
function reelQuery() {
  const p = new URLSearchParams({ lang: S.prefs.lang, persona: S.prefs.persona === "analyst" ? "analyst" : "casual" });
  if (S.prefs.club) p.set("club", S.prefs.club);
  const pl = [...new Set([S.prefs.focus, ...(S.prefs.favs || [])].filter((x) => x && S.players[x]))];
  if (pl.length) p.set("player", pl.join(","));
  return p.toString();
}
const fmtClock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
async function loadReelPlan() {
  try {
    const plan = await fetch(`/api/matches/${S.sid}/reel?${reelQuery()}`).then((r) => r.json());
    const clubName = S.prefs.club === "both" ? "" : S.prefs.club && S.meta ? S.meta[S.prefs.club].name : "";
    const names = [...new Set([S.prefs.focus, ...(S.prefs.favs || [])].filter((x) => x && S.players[x]))].map((x) => S.players[x].name);
    const who = [clubName, names.length > 2 ? `${names.length} favourite players` : names.join(" and ")].filter(Boolean).join(" and ");
    $("#mineTitle").textContent = who ? `Highlights for ${who}` : "The match in highlights";
    $("#mineIntro").textContent = plan.clips.length ? `${plan.clips.length} moments, ${Math.round(plan.duration_s)} seconds of action, picked for you and checked against the match data.` : "Highlights appear here as the match produces them.";
    $("#clips").innerHTML = plan.clips.map((c) => `<li><span class="m">${c.minute}'</span><span><span class="t">${esc(c.title)}</span><br><span class="l">${esc(c.line)}</span></span>
      <span class="d">${fmtClock(c.start)} to ${fmtClock(c.end)}</span></li>`).join("");
    $("#edlLink").href = `/api/matches/${S.sid}/reel?${reelQuery()}`;
    $("#reel3d").href = `/reel?session=${encodeURIComponent(S.sid)}&${reelQuery()}`;
    if (plan.video && plan.video.url) showReel(plan.video.url);
  } catch { /* keep previous */ }
}
function showReel(url) {
  const v = $("#reelVideo"); v.hidden = false; if (!v.src.endsWith(url)) v.src = url;
  $("#reelStatus").textContent = "Your reel is ready. Download it from the player menu to share it.";
  $("#reelBtn").disabled = false;
}
async function makeReel() {
  $("#reelBtn").disabled = true;
  $("#reelStatus").textContent = "Rendering your reel through the broadcast camera…";
  const r = await fetch(`/api/matches/${S.sid}/reel?${reelQuery()}`, { method: "POST" });
  if (!r.ok) { $("#reelStatus").textContent = "The renderer is busy. Try again in a minute."; $("#reelBtn").disabled = false; return; }
  const job = await r.json();
  if (job.url) return showReel(job.url);
  const poll = setInterval(async () => {
    const p = await fetch(`/api/matches/${S.sid}/reel?${reelQuery()}`).then((x) => x.json());
    if (p.video && p.video.status === "ready") { clearInterval(poll); showReel(p.video.url); }
    else if (p.video && String(p.video.status).startsWith("failed")) { clearInterval(poll); $("#reelStatus").textContent = "The reel couldn't be rendered. Try again."; $("#reelBtn").disabled = false; }
  }, 3000);
}

/* ------------------------------------------------------------------ controls */
function applyView() {
  S.view = S.prefs.view === "tactical" ? "tactical" : "tv";
  S.camMode = S.prefs.view === "player" ? "player" : "main";
  const sel = S.prefs.view === "player" ? "player" : S.view;
  $$("#viewSeg button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.view === sel)));
  $("#pitchBox").classList.toggle("tv", S.view === "tv");
  if ($("#playerIdentity")) $("#playerIdentity").hidden = true;
  if (S.view === "tv" && (!S.judge || $("#storyReplay")?.open)) loadPitch3D();
  resizeCanvas();
}

function applyPrefs() {
  $$("#personaSeg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.persona === S.prefs.persona)));
  $("#club").value = S.prefs.club; $("#metric").value = S.prefs.metric; $("#speak").checked = S.prefs.speak; $("#booth").checked = !!S.prefs.booth;
  if ($("#lang").querySelector(`option[value="${S.prefs.lang}"]:not([disabled])`)) $("#lang").value = S.prefs.lang;
  if (S.meta) $("#focus").value = S.prefs.focus;
  $("#homeBug").classList.toggle("fav", isMine("home"));
  $("#awayBug").classList.toggle("fav", isMine("away"));
  document.documentElement.lang = S.prefs.lang;
  rerenderCards();
  S.story?.refresh();
  S.centre?.refresh();
  S.playerSpotlight?.refresh();
  updateMetric();
  if (!$("#tab-mine").hidden && S.meta) loadReelPlan();
}

async function control(action, value) {
  const headers = { "Content-Type": "application/json" };
  if (S.judgeToken) headers["X-Touchline-Judge-Token"] = S.judgeToken;
  const r = await fetch(`/api/matches/${S.sid}/control`, { method: "POST", headers, body: JSON.stringify({ action, value }) });
  if (!r.ok && S.judge) { const error = await r.json(); toast(error.detail || "Playback control failed."); return { ok: false }; }
  if (r.status === 401 || r.status === 403) {
    const error = await r.json();
    if (error.detail?.includes("read-only")) toast(error.detail); else needProducer(r.status);
    return { ok: false, reason: "auth" };
  }
  return r.json();
}
function needProducer(status) {
  toast(status === 401 ? "Producer access is required for this action." : "This match is read-only with your current permissions.");
  if (status === 401 && S.me?.login && S.me.identity_provider_configured) $("#who").innerHTML = `<a class="btn small" href="${esc(S.me.login)}?post_login_redirect_uri=/">Sign in with Microsoft</a>`;
}
function applyCapabilities() {
  const shared = ["demo", "live"].includes(S.sid), allowed = shared ? S.me?.can_control_shared === true : S.me?.can_produce === true;
  const privateJudge = S.judge && !!S.judgeToken;
  $$("#modeSeg button, [data-drill], [data-approve], [data-reject]").forEach(button => { button.disabled = !allowed; button.title = allowed ? "" : "Read-only match: producer access is unavailable here."; });
  $$("#pauseBtn, #speed, #jump").forEach(control => {
    control.disabled = !S.snap || S.snap.status === "full_time" || !(privateJudge || allowed);
    control.title = privateJudge ? "Controls your own replay" : shared && !allowed ? "Shared live match. Start the 90-second demo for your own playback controls." : "";
  });
}
async function loadMe() {
  try {
    const me = await startupJson("/api/me");
    S.me = me;
    $("#who").innerHTML = me.signed_in
      ? `Signed in as <b>${esc(me.name || "you")}</b>${me.roles.length ? ` (${me.roles.map((r) => esc(r.replace("Touchline.", ""))).join(", ")})` : ""}.${me.logout ? ` <a href="${esc(me.logout)}">Sign out</a>` : ""}`
      : me.identity_provider_configured && me.login ? `<a class="btn small" href="${esc(me.login)}?post_login_redirect_uri=/">Sign in with Microsoft</a> for producer access.`
      : me.can_control_shared ? "Local demo controls are enabled. Producer identity is not configured." : "You are viewing the shared broadcast. Editorial decisions are visible; controls are read-only. Start the 90-second demo for your own replay.";
    applyCapabilities();
  } catch (e) { $("#who").textContent = "Producer access could not be checked. This view remains read-only."; applyCapabilities(); }
}

function bindJudgeMode() {
  if (!S.judge) return;
  document.body.classList.add("judge-mode");
  $("#judgeHeroImage").src = $("#judgeHeroImage").dataset.src;
  S.story = TouchlineStory.create({
    loadChallenge: async id => {
      const response = await fetch(`/api/matches/${encodeURIComponent(S.sid)}/insights/${encodeURIComponent(id)}/challenge`);
      if (!response.ok) throw new Error("Checker test unavailable");
      return response.json();
    },
    loadReceipt: async id => {
      const response = await fetch(`/api/matches/${encodeURIComponent(S.sid)}/insights/${encodeURIComponent(id)}/receipt`);
      if (!response.ok) throw new Error("Evidence unavailable");
      return response.json();
    },
    openReceipt, openEvent: openEvidence,
    loadWhatIf: async eventId => {
      const response = await fetch(`/api/matches/${encodeURIComponent(S.sid)}/whatif`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario: `nogoal:${eventId}` }),
      });
      if (!response.ok) throw new Error("Comparison unavailable");
      return response.json();
    },
    getTeams: () => ({home: S.meta?.home.short || "Home", away: S.meta?.away.short || "Away"}),
    getPrefs: () => S.prefs,
    setPersona: persona => { S.prefs.persona = persona; savePrefs(); applyPrefs(); },
  });
  $("#storyReplay").addEventListener("toggle", () => { if ($("#storyReplay").open) applyView(); });
  $("#judgePanel").hidden = false;
  $("#pauseBtn").disabled = true;
  $("#matchLabel").textContent = "Your own replay, ready when you are";
  Object.assign(S.prefs, { persona: "casual", lang: "en", view: "tv", speak: false, booth: false,
                         club: "", focus: "", metric: "", favs: [] });
  $('[data-tab="ask"]').click();
  $("#judgeStart").addEventListener("click", startJudge);
  $("#judgeStart").disabled = false;
}

async function restoreJudge() {
  try {
    const saved = JSON.parse(sessionStorage.getItem("tl.judge") || "null");
    if (!saved) return;
    const response = await fetch(`/api/matches/${encodeURIComponent(saved.session_id)}`);
    if (!response.ok) { sessionStorage.removeItem("tl.judge"); return; }
    const match = await response.json();
    if (!match.judge) return;
    S.sid = saved.session_id; S.judgeToken = saved.control_token;
    $("#judgeStart").textContent = "Restart demonstration";
    $("#pauseBtn").disabled = match.done;
    $("#judgeStatus").textContent = match.done ? "Replay complete. Inspect the receipts or restart." : "Reconnected to your replay.";
    connect();
  } catch { /* storage is optional; Start always creates a fresh replay */ }
}

async function startJudge() {
  const button = $("#judgeStart");
  button.disabled = true;
  $("#judgeStatus").textContent = "Preparing the match history…";
  try {
    if (S.judgeToken) {
      const stopped = await fetch(`/api/judge/${S.sid}`, { method: "DELETE", headers: { "X-Touchline-Judge-Token": S.judgeToken } });
      if (!stopped.ok && stopped.status !== 404) throw new Error("Could not stop the previous replay. Please retry.");
    }
    S.es?.close(); S.judgeToken = null;
    S.story?.reset();
    const response = await fetch("/api/judge", { method: "POST" });
    if (!response.ok) { const error = await response.json(); throw new Error(error.detail || "Could not start replay."); }
    const match = await response.json();
    S.sid = match.session_id; S.judgeToken = match.control_token; S.judgeResume = true;
    try { sessionStorage.setItem("tl.judge", JSON.stringify(match)); } catch { /* no storage required */ }
    for (const layer of Object.values(S.layers)) layer.remove();
    S.layers = {}; S.speechQ = []; S.snap = null; S.fb = {};
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    $("#drawer").hidden = true;
    $("#pauseBtn").disabled = false;
    button.textContent = "Restart demonstration";
    connect();
  } catch (error) { $("#judgeStatus").textContent = error.message; }
  finally { button.disabled = false; }
}

function setPaused(p) { S.paused = p; $("#pauseBtn").textContent = p ? "Resume" : "Pause"; applyCapabilities(); }

function bindControls() {
  $("#viewSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    S.prefs.view = b.dataset.view; savePrefs();
    applyView();
  });
  $("#moreBtn").addEventListener("click", () => {
    const open = $(".prefs").classList.toggle("open");
    $("#moreBtn").setAttribute("aria-expanded", String(open));
    $("#moreBtn").textContent = open ? "Close preferences" : "Personalise";
  });
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
  $("#booth").addEventListener("change", (e) => { S.prefs.booth = e.target.checked; savePrefs(); if (!e.target.checked) { if ("speechSynthesis" in window) speechSynthesis.cancel(); S.speechQ = []; caption(null); } });
  $("#speak").addEventListener("change", (e) => { S.prefs.speak = e.target.checked; savePrefs(); if (!e.target.checked && "speechSynthesis" in window) { speechSynthesis.cancel(); S.speechQ = []; } });
  $("#pauseBtn").addEventListener("click", () => control(S.paused ? "resume" : "pause"));
  $("#speed").addEventListener("change", (e) => control("speed", Number(e.target.value)));
  $("#jump").addEventListener("change", (e) => { if (e.target.value) { S.jumping = true; setTimeout(() => { S.jumping = false; }, 4000); control("jump", Number(e.target.value)); } e.target.value = ""; });

  document.addEventListener("click", (e) => {
    const receipt = e.target.closest("[data-receipt]"); if (receipt) return openReceipt(receipt.dataset.receipt);
    const chip = e.target.closest("[data-ev]"); if (chip) return openEvidence(chip.dataset.ev);
    const say = e.target.closest("[data-say]"); if (say) { const i = S.insights.find((x) => x.id === say.dataset.say); if (i) queueSpeech({ ...i, salience: 1 }); return; }
    const q = e.target.closest("[data-q]"); if (q) return ask(q.dataset.q);
    const wib = e.target.closest("[data-wi]"); if (wib) { runWhatIf(wib.dataset.wi); return; }
    const fbb = e.target.closest("[data-fb]"); if (fbb) { feedback(fbb.dataset.fb, Number(fbb.dataset.up)); return; }
    const dr = e.target.closest("[data-drill]"); if (dr) { runDrill(dr.dataset.drill); return; }
    const fv = e.target.closest("[data-fav]"); if (fv) { const f = new Set(S.prefs.favs || []); f.has(fv.dataset.fav) ? f.delete(fv.dataset.fav) : f.add(fv.dataset.fav); S.prefs.favs = [...f]; savePrefs(); applyPrefs(); renderPlayers(); return; }
    const fol = e.target.closest("[data-follow]"); if (fol) { S.prefs.focus = S.prefs.focus === fol.dataset.follow ? "" : fol.dataset.follow; savePrefs(); applyPrefs(); renderPlayers(); return; }
    const ap = e.target.closest("[data-approve]"); if (ap) return decide(ap.dataset.approve, true);
    const rj = e.target.closest("[data-reject]"); if (rj) return decide(rj.dataset.reject, false);
    const sort = e.target.closest("button[data-sort]"); if (sort) {
      playerSortDirection = playerSort === sort.dataset.sort ? (playerSortDirection === "ascending" ? "descending" : "ascending") : ["name", "position", "number"].includes(sort.dataset.sort) ? "ascending" : "descending";
      playerSort = sort.dataset.sort; renderPlayers();
    }
  });
  $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#askInput").value.trim(); if (v) { ask(v); $("#askInput").value = ""; } });
  $("#recapBtn").addEventListener("click", loadRecap);
  $("#reelBtn").addEventListener("click", makeReel);
  $("#drawerClose").addEventListener("click", closeDrawer);
  addEventListener("keydown", drawerKeys);
  const workspaceTabs = $$(".tabs [role=tab]");
  workspaceTabs.forEach((tab, index) => {
    tab.id = `tool-${tab.dataset.tab}`;
    tab.setAttribute("aria-controls", `tab-${tab.dataset.tab}`);
    tab.tabIndex = tab.getAttribute("aria-selected") === "true" ? 0 : -1;
    $("#tab-" + tab.dataset.tab).setAttribute("aria-labelledby", tab.id);
    tab.addEventListener("keydown", event => {
      const delta = {ArrowRight:1, ArrowLeft:-1}[event.key];
      const next = event.key === "Home" ? 0 : event.key === "End" ? workspaceTabs.length - 1 : delta ? (index + delta + workspaceTabs.length) % workspaceTabs.length : null;
      if (next === null) return;
      event.preventDefault(); workspaceTabs[next].click(); workspaceTabs[next].focus();
    });
  });
  workspaceTabs.forEach((t) => t.addEventListener("click", () => {
    workspaceTabs.forEach((x) => { x.setAttribute("aria-selected", String(x === t)); x.tabIndex = x === t ? 0 : -1; });
    $$(".tabpanel").forEach((p) => { p.hidden = p.id !== "tab-" + t.dataset.tab; });
    if (t.dataset.tab === "players") renderPlayers();
    if (t.dataset.tab === "producer") renderProducer();
    if (t.dataset.tab === "ops") renderOps();
    if (t.dataset.tab === "recap") loadRecap();
    if (t.dataset.tab === "mine") loadReelPlan();
    if (t.dataset.tab === "whatif") loadWhatIf();
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
  const r = await fetch(`/api/matches/${S.sid}/cues/${encodeURIComponent(cueId)}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approve }) });
  if (r.status === 401 || r.status === 403) needProducer(r.status);
}

function toast(msg) {
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; t.setAttribute("role", "status");
  document.body.appendChild(t); setTimeout(() => t.remove(), 3200);
}

boot();

window.S = S; window.isFav = isFav;
