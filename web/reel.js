/* My Match in 3D: replays each highlight clip through the broadcast view at real match speed,
   composites the graphics onto one canvas, and records it in the fan's own browser.
   ?session=&club=&player=&lang=&persona=   (same arguments as the reel plan API)
   ?frames=1  exposes window.reelStep() for frame-exact offline capture. */
"use strict";
(() => {
  const qs = new URLSearchParams(location.search);
  const sid = qs.get("session") || "demo", lang = qs.get("lang") || "en";
  const FRAMES = !!qs.get("frames");
  const W = 1280, H = 720;
  const comp = document.getElementById("comp"), cx = comp.getContext("2d");
  const $ = (id) => document.getElementById(id);
  const WORDS = {
    en: { kick: "Checked against the match data", my: "My Match", foot: "Synthetic match, fictional clubs. Every line checked against the match data.", for: "Highlights for", all: "The match in highlights", play: "Play and record", again: "Play again", saved: "Your reel is ready." },
    es: { kick: "Verificado con los datos del partido", my: "Mi partido", foot: "Partido sintético, clubes ficticios. Cada línea verificada con los datos.", for: "Resumen para", all: "El partido en resumen", play: "Reproducir y grabar", again: "Ver otra vez", saved: "Tu resumen está listo." },
    fr: { kick: "Vérifié avec les données du match", my: "Mon match", foot: "Match synthétique, clubs fictifs. Chaque ligne vérifiée avec les données.", for: "Résumé pour", all: "Le match en résumé", play: "Lire et enregistrer", again: "Revoir", saved: "Ton résumé est prêt." },
    pt: { kick: "Verificado com os dados do jogo", my: "O meu jogo", foot: "Jogo sintético, clubes fictícios. Cada linha verificada com os dados.", for: "Resumo para", all: "O jogo em resumo", play: "Reproduzir e gravar", again: "Ver de novo", saved: "O teu resumo está pronto." },
  };
  const T = WORDS[lang] || WORDS.en;

  // the shared state the 3D view reads (same shape as the live app)
  const S = window.S = { pos: {}, ball: [52.5, 34], ballZ: 0.11, draws: [], players: {}, meta: null, camMode: "main", dur: 1000, tight: 0.78,
    prefs: { focus: "", favs: [] } };
  window.TV3D_PRESERVE = true;
  window.isFav = (pid) => !!pid && (pid === S.prefs.focus || S.prefs.favs.includes(pid));
  const favs = (qs.get("player") || "").split(",").filter(Boolean);
  S.prefs.favs = favs; S.prefs.focus = favs.length === 1 ? favs[0] : "";

  let plan = null, clips = [], ready = false;

  async function load() {
    const [m, p] = await Promise.all([
      fetch(`/api/matches/${sid}`).then((r) => r.json()),
      fetch(`/api/matches/${sid}/reel?${new URLSearchParams([...qs].filter(([k]) => ["club", "player", "lang", "persona"].includes(k)))}`).then((r) => r.json()),
    ]);
    S.meta = m.match; plan = p;
    for (const t of [m.match.home, m.match.away]) for (const pl of t.players) S.players[pl.id] = { ...pl, color: t.color };
    const who = [qs.get("club") && qs.get("club") !== "both" ? m.match[qs.get("club")].name : "", ...favs.map((f) => S.players[f] ? S.players[f].name : "")].filter(Boolean);
    $("title").textContent = who.length ? `${T.for} ${who.slice(0, 2).join(" & ")}` : T.all;
    $("play").textContent = T.play;
    clips = await Promise.all(plan.clips.map(async (c) => {
      const w = await fetch(`/api/matches/${sid}/window?start=${Math.max(0, c.start - 1)}&end=${c.end + 0.5}`).then((r) => r.json());
      return { ...c, events: w.events.filter((e) => e.frame || e.x != null) };
    }));
    clips = clips.filter((c) => c.events.length);
    await Promise.all(["700 40px 'Barlow Condensed'", "600 20px Barlow", "400 24px 'Source Serif 4'"].map((f) => document.fonts.load(f)));
    await import("/static/tv3d.js");
    await new Promise((res) => { const w = () => (window.TV3D && TV3D.ready ? res() : setTimeout(w, 100)); w(); });
    ready = true;
    $("status").textContent = `${clips.length} moments, about ${Math.round(clips.reduce((a, c) => a + (c.end - c.start), 0) + 6)} seconds`;
    // Show the composed title immediately; t=0 is the transparent start of its animation.
    if (!FRAMES) drawCard(1, "intro");
  }

  /* ------------------------------------------------------------ playback engine (virtual time) */
  const P = { phase: "intro", t: 0, clip: 0, simT: 0, next: 0, hold: 0, from: {}, to: {}, ev: null, t0: 0, dur: 1, ballFrom: [52.5, 34], ballMid: [52.5, 34], ballTo: [52.5, 34], score: { home: 0, away: 0 }, minute: 0, lt: null, done: false, clock: 0 };
  const INTRO = 2.6, OUTRO = 4.0, GAP = 0.45;

  function startClip(i) {
    const c = clips[i];
    P.clip = i; P.simT = c.events[0].t - 0.3; P.next = 0; P.hold = 0; P.lt = null; S.draws = [];
    const f0 = c.events.find((e) => e.frame);
    if (f0) for (const [pid, p] of Object.entries(f0.frame)) { S.pos[pid] = [...p]; P.from[pid] = [...p]; P.to[pid] = [...p]; }
    S.ball = [c.events[0].x ?? 52.5, c.events[0].y ?? 34]; P.ballFrom = P.ballMid = P.ballTo = [...S.ball]; P.ev = null;
    P.score = { ...c.events[0].score }; P.minute = c.minute;
    TV3D.board(c.title, c.team && S.meta ? S.meta[c.team].color : null);
    TV3D.cut();
  }
  function applyEvent(c, k) {
    const ev = c.events[k], nxt = c.events[k + 1];
    if (ev.frame) for (const [pid, p] of Object.entries(ev.frame)) { P.from[pid] = S.pos[pid] ? [...S.pos[pid]] : [...p]; P.to[pid] = p; if (!S.pos[pid]) S.pos[pid] = [...p]; }
    P.t0 = ev.t; P.dur = Math.max(0.15, Math.min(2.0, (nxt ? nxt.t : ev.t + 1) - ev.t));
    if (ev.x != null) { P.ev = ev; P.ballFrom = [...S.ball]; P.ballMid = [ev.x, ev.y]; P.ballTo = ev.end_x != null ? [ev.end_x, ev.end_y] : [ev.x, ev.y]; }
    P.score = ev.score; P.minute = ev.minute;
    const key = (c.evidence || []).includes(ev.id);
    if (key && ev.etype === "pass" && ev.end_x != null) S.draws.push({ kind: "pass", x: ev.x, y: ev.y, end_x: ev.end_x, end_y: ev.end_y, until: Infinity });
    if (key && ev.etype === "shot" && ev.end_x != null) S.draws.push({ kind: "shot", x: ev.x, y: ev.y, end_x: ev.end_x, end_y: ev.end_y, xg: 0.15, until: Infinity });
    const ids = c.evidence || [], lastKey = ids.length ? ids[ids.length - 1] : null;
    if (!P.lt && (ev.id === lastKey || ["goal", "card"].includes(ev.etype) || (c.kind !== "goal" && key && ev.etype === "shot"))) P.lt = { at: P.clock };
    TV3D.onEvent(ev);
  }
  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2), lerp = (a, b, t) => a + (b - a) * t;
  function stepSim() {
    const t = Math.min(1, (P.simT - P.t0) / P.dur), e = ease(Math.max(0, t));
    for (const pid of Object.keys(P.to)) { const f = P.from[pid] || P.to[pid], to = P.to[pid]; S.pos[pid] = [lerp(f[0], to[0], e), lerp(f[1], to[1], e)]; }
    S.ballZ = 0.11;
    if (t < 0.25) { const k = ease(Math.max(0, t) / 0.25); S.ball = [lerp(P.ballFrom[0], P.ballMid[0], k), lerp(P.ballFrom[1], P.ballMid[1], k)]; }
    else {
      const k = ease((t - 0.25) / 0.75); S.ball = [lerp(P.ballMid[0], P.ballTo[0], k), lerp(P.ballMid[1], P.ballTo[1], k)];
      const ev = P.ev;
      if (ev && ev.end_x != null) {
        const d = Math.hypot(ev.end_x - ev.x, ev.end_y - ev.y);
        if (ev.etype === "pass" && ev.q && ev.q.height === "high") S.ballZ += 4 * Math.min(14, d / 3.2) * k * (1 - k);
        if (ev.etype === "shot") S.ballZ += 4 * 1.1 * k * (1 - k) + 0.9 * k;
      }
    }
  }

  // advance by dt seconds of film; returns false when the reel is over
  function advance(dt) {
    P.clock += dt; P.t += dt;
    if (P.phase === "intro") { if (P.t >= INTRO) { P.phase = "clip"; P.t = 0; startClip(0); } return true; }
    if (P.phase === "gap") { if (P.t >= GAP) { P.phase = "clip"; P.t = 0; startClip(P.clip + 1); } return true; }
    if (P.phase === "outro") { if (P.t >= OUTRO) { P.done = true; return false; } return true; }
    const c = clips[P.clip];
    if (P.simT < c.end) {
      P.simT += dt;
      while (P.next < c.events.length && c.events[P.next].t <= P.simT) applyEvent(c, P.next++);
    } else {
      P.hold += dt; // let a replay or celebration finish
      if (!P.lt) P.lt = { at: P.clock };
    }
    if (P.simT >= c.end && (!TV3D.replaying() || P.hold > 5.5) && (!P.lt || P.clock - P.lt.at > 3.2)) {
      P.t = 0;
      if (P.clip + 1 < clips.length) P.phase = "gap"; else { P.phase = "outro"; S.draws = []; }
    }
    return true;
  }

  /* ------------------------------------------------------------ graphics, drawn onto the recorded canvas */
  const teamCol = (side) => (S.meta && side ? S.meta[side].color : "#f2c14e");
  function rr(x, y, w, h, r) { cx.beginPath(); cx.roundRect(x, y, w, h, r); }
  function wrap(text, maxW) {
    const words = String(text).split(" "), lines = []; let cur = "";
    for (const w of words) { const t = cur ? cur + " " + w : w; if (cx.measureText(t).width > maxW && cur) { lines.push(cur); cur = w; } else cur = t; }
    if (cur) lines.push(cur); return lines;
  }
  function scorebug() {
    if (!S.meta) return;
    const h = S.meta.home, a = S.meta.away;
    cx.font = "700 28px 'Barlow Condensed'"; cx.textBaseline = "middle";
    let x = 40; const y = 34, hh = 42;
    const seg = (txt, bg, fg, pad = 16, bar) => { const w = cx.measureText(txt).width + pad * 2; cx.fillStyle = bg; cx.fillRect(x, y, w, hh); if (bar) { cx.fillStyle = bar; cx.fillRect(x, y, 5, hh); } cx.fillStyle = fg; cx.fillText(txt, x + pad + (bar ? 3 : 0), y + hh / 2 + 1); x += w; };
    seg(h.short, "rgba(10,28,20,.92)", "#eef0e8", 16, h.color);
    seg(`${P.score.home}-${P.score.away}`, "#eef0e8", "#0f2b20", 14);
    seg(a.short, "rgba(10,28,20,.92)", "#eef0e8", 16);
    cx.fillStyle = a.color; cx.fillRect(x - 5, y, 5, hh);
    seg(`${P.minute}'`, "#f2c14e", "#1a1405", 12);
  }
  function lowerThird(c, k) {
    const goal = c.kind === "goal", x0 = 56, maxW = 860;
    cx.font = `700 ${goal ? 52 : 40}px 'Barlow Condensed'`; const tl = wrap(c.title, maxW);
    cx.font = "400 24px 'Source Serif 4'"; const ll = c.line ? wrap(c.line, maxW) : [];
    const h = 46 + tl.length * (goal ? 54 : 42) + ll.length * 32 + 18, y0 = H - 48 - h;
    const w = Math.min(maxW + 64, Math.max(...[...tl.map((t) => { cx.font = `700 ${goal ? 52 : 40}px 'Barlow Condensed'`; return cx.measureText(t).width; }), ...ll.map((t) => { cx.font = "400 24px 'Source Serif 4'"; return cx.measureText(t).width; }), 300]) + 64);
    const reveal = ease(Math.min(1, k * 2.2));
    cx.save(); cx.beginPath(); cx.rect(x0, y0 - 6, (w + 12) * reveal, h + 6); cx.clip();
    cx.fillStyle = goal ? "#eef0e8" : "rgba(12,36,27,.95)"; cx.fillRect(x0 + 10, y0, w, h);
    cx.fillStyle = "#f2c14e"; cx.fillRect(x0, y0, 10, h);
    cx.fillStyle = teamCol(c.team); cx.fillRect(x0 + 10, y0, w, 6);
    if (reveal > 0.98) {
      let y = y0 + 34; cx.textBaseline = "alphabetic";
      cx.font = "600 17px Barlow"; cx.fillStyle = goal ? "#8a5a00" : "#f2c14e"; cx.fillText("✓  " + T.kick, x0 + 40, y);
      cx.font = `700 ${goal ? 52 : 40}px 'Barlow Condensed'`; cx.fillStyle = goal ? "#0f2b20" : "#eef0e8";
      for (const t of tl) { y += goal ? 54 : 42; cx.fillText(t, x0 + 40, y); }
      cx.font = "400 24px 'Source Serif 4'"; cx.fillStyle = goal ? "#284a3a" : "#dfe5da";
      for (const t of ll) { y += 32; cx.fillText(t, x0 + 40, y); }
    }
    cx.restore();
  }
  function drawCard(k, kind) {
    cx.fillStyle = "#0b1d15"; cx.fillRect(0, 0, W, H);
    cx.fillStyle = "#f2c14e"; cx.fillRect(96, 250, 10, 220 * ease(Math.min(1, k * 3)));
    cx.globalAlpha = Math.min(1, k * 3); cx.textBaseline = "alphabetic";
    if (kind === "intro") {
      cx.font = "600 26px Barlow"; cx.fillStyle = "#f2c14e"; cx.fillText(T.my, 136, 288);
      cx.font = "700 76px 'Barlow Condensed'"; cx.fillStyle = "#eef0e8"; cx.fillText($("title").textContent, 136, 368);
      if (S.meta) { cx.font = "400 30px 'Source Serif 4'"; cx.fillStyle = "#c9d3c4"; cx.fillText(`${S.meta.home.name} v ${S.meta.away.name}`, 136, 424); }
    } else {
      const r = plan && plan.recap; cx.font = "700 60px 'Barlow Condensed'"; cx.fillStyle = "#eef0e8";
      let y = 330; for (const t of wrap(r ? r.title : "", 1000)) { cx.fillText(t, 136, y); y += 62; }
      cx.font = "400 26px 'Source Serif 4'"; cx.fillStyle = "#c9d3c4";
      for (const l of (r ? r.lines : []).slice(0, 3)) for (const t of wrap(l, 1000)) { y += 36; cx.fillText(t, 136, y); }
    }
    cx.font = "600 18px Barlow"; cx.fillStyle = "#8fa293"; cx.fillText(T.foot, 136, H - 60);
    cx.globalAlpha = 1;
  }
  function compose(now) {
    if (P.phase === "intro") return drawCard(P.t / INTRO, "intro");
    if (P.phase === "outro") return drawCard(P.t / OUTRO, "outro");
    stepSim();
    TV3D.render(now);
    cx.drawImage(document.getElementById("pitch3d"), 0, 0, W, H);
    scorebug();
    const c = clips[P.clip];
    if (P.lt && c) lowerThird(c, (P.clock - P.lt.at) / 1.0);
    if (P.phase === "gap") { const k = P.t / GAP; cx.fillStyle = "#f2c14e"; cx.fillRect(0, 0, W * ease(Math.min(1, k * 1.6)), H); }
    if (P.t < 0.35 && P.phase === "clip") { cx.fillStyle = `rgba(242,193,78,${1 - P.t / 0.35})`; cx.fillRect(0, 0, W, H); }
    const total = clips.length; $("progBar").style.width = `${Math.round(((P.clip + (P.phase === "outro" ? 1 : 0)) / Math.max(1, total)) * 100)}%`;
  }

  /* ------------------------------------------------------------ live play + in-browser recording */
  function reset() { Object.assign(P, { phase: "intro", t: 0, clip: 0, simT: 0, clock: 0, done: false, lt: null }); S.draws = []; }
  async function playAndRecord() {
    if (!ready) return;
    reset(); $("save").hidden = true; $("play").disabled = true;
    let rec = null, chunks = [];
    try {
      const type = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t));
      if (type) { rec = new MediaRecorder(comp.captureStream(30), { mimeType: type, videoBitsPerSecond: 6e6 }); rec.ondataavailable = (e) => e.data.size && chunks.push(e.data); rec.start(250); }
    } catch (e) { rec = null; }
    $("status").textContent = rec ? "Recording…" : "Playing (this browser can't record video)";
    let last = performance.now(), v = 0;
    await new Promise((res) => {
      const loop = (now) => {
        const dt = Math.min(0.05, (now - last) / 1000); last = now; v += dt * 1000;
        const more = advance(dt); compose(v);
        if (more) requestAnimationFrame(loop); else res();
      };
      requestAnimationFrame(loop);
    });
    if (rec) {
      await new Promise((res) => { rec.onstop = res; rec.stop(); });
      const blob = new Blob(chunks, { type: "video/webm" });
      const a = $("save"); a.href = URL.createObjectURL(blob); a.hidden = false;
      $("status").textContent = T.saved;
    } else $("status").textContent = "";
    $("play").disabled = false; $("play").textContent = T.again;
  }
  $("play").addEventListener("click", playAndRecord);

  // frame-exact capture for offline encoding (Playwright): each call renders the next frame at `fps`
  window.reelStep = (fps = 25) => {
    if (!ready) return { ready: false };
    if (!window.__v) { reset(); window.__v = 0; }
    const more = advance(1 / fps); window.__v += 1000 / fps; compose(window.__v);
    return { ready: true, more, phase: P.phase, clip: P.clip, clips: clips.length };
  };
  window.reelReady = () => ready;

  load().catch((e) => { $("status").textContent = "Couldn't load the reel: " + e.message; console.error(e); });
})();
