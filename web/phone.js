/* Touchline second screen: the match in your pocket, next to the TV.
   Live score and win probability, the latest checked moment, your player's numbers, two-voice commentary,
   ask by voice, and a buzz when your club scores. No 3D here, to save battery. */
"use strict";
(() => {
  const qs = new URLSearchParams(location.search);
  const sid = qs.get("session") || "demo";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const store = { get(k, d) { try { return JSON.parse(localStorage.getItem("tl-phone-" + k)) ?? d; } catch { return d; } },
                  set(k, v) { try { localStorage.setItem("tl-phone-" + k, JSON.stringify(v)); } catch { /* private mode */ } } };
  const S = { meta: null, players: {}, insights: [], persona: store.get("persona", "casual"), lang: qs.get("lang") || store.get("lang", "en"),
              player: store.get("player", ""), booth: false, q: [], speaking: false };

  function render(ins) {
    const by = (ins.renders || {})[S.persona] || (ins.renders || {}).casual || {};
    return by[S.lang] || by.en;
  }
  function showLatest(ins, flash) {
    const r = render(ins); if (!r) return;
    $("lmin").textContent = ins.minute + "'";
    $("lkind").textContent = (ins.kind || "").replace(/_/g, " ").replace(/^story /, "storyline: ");
    $("lok").textContent = (ins.verification || {}).status === "verified" ? "Checked" : "";
    $("ltitle").textContent = r.title;
    const story = r.lines.filter((l) => (l.k || "").startsWith("s."));
    const lines = story.length ? [story[story.length - 1], ...r.lines.filter((l) => !story.includes(l))] : r.lines;
    $("llines").innerHTML = lines.slice(0, S.persona === "analyst" ? 3 : 2).map((l) => `<p class="line">${esc(l.text)}</p>`).join("");
    if (flash) { const c = $("latest"); c.classList.remove("goal-flash"); void c.offsetWidth; c.classList.add("goal-flash"); }
  }
  function feed() {
    $("feed").innerHTML = S.insights.slice(-9, -1).reverse().map((i) => {
      const r = render(i); return r ? `<div class="row"><b>${i.minute}'</b><span>${esc(r.title)}</span></div>` : "";
    }).join("") || `<p class="muted">Moments appear here as the match goes on.</p>`;
  }
  function onHello(h) {
    S.meta = h.match;
    const { home, away } = h.match;
    $("hs").textContent = home.short; $("as").textContent = away.short;
    $("hc").style.background = home.color; $("ac").style.background = away.color;
    $("wph").style.background = home.color; $("wpa").style.background = away.color;
    S.players = {};
    const opts = ['<option value="">Choose your player</option>'];
    for (const t of [home, away]) {
      opts.push(`<optgroup label="${esc(t.name)}">`);
      for (const p of t.players) { S.players[p.id] = { ...p, team: t === home ? "home" : "away" }; opts.push(`<option value="${p.id}">#${p.number} ${esc(p.name)}</option>`); }
      opts.push("</optgroup>");
    }
    $("player").innerHTML = opts.join(""); $("player").value = S.player;
  }
  function onState(s) {
    $("score").textContent = `${s.score.home}-${s.score.away}`;
    $("min").textContent = s.status === "full_time" ? "FT" : `${s.minute}'`;
    const w = s.win_prob;
    $("wph").style.width = w.home * 100 + "%"; $("wpd").style.width = w.draw * 100 + "%"; $("wpa").style.width = w.away * 100 + "%";
    if (S.meta) {
      $("wphl").textContent = `${S.meta.home.short} ${Math.round(w.home * 100)}%`;
      $("wpdl").textContent = `draw ${Math.round(w.draw * 100)}%`;
      $("wpal").textContent = `${S.meta.away.short} ${Math.round(w.away * 100)}%`;
      $("wpbar").setAttribute("aria-label", `Win probability: ${$("wphl").textContent}, ${$("wpdl").textContent}, ${$("wpal").textContent}`);
    }
    const me = S.player && s.players && s.players[S.player];
    $("me").innerHTML = me ? [[me.rating, "rating"], [me.distance_km, "km run"], [me.top_speed_kmh, "top km/h"],
      [me.passes ? Math.round(me.completed / me.passes * 100) + "%" : "–", "passes found"], [me.xg, "xG"], [me.xt, "threat added"]]
      .map(([v, l]) => `<div><b>${esc(v)}</b><span>${l}</span></div>`).join("") : "";
  }
  function onInsight(ins, replayed) {
    S.insights.push(ins); if (S.insights.length > 200) S.insights.shift();
    const goal = ins.kind === "goal";
    showLatest(ins, goal && !replayed); feed();
    if (!replayed && goal && S.meta) {
      const mine = S.player && S.players[S.player] ? S.players[S.player].team : null;
      if (mine && ins.team === mine && navigator.vibrate) navigator.vibrate([200, 80, 200, 80, 400]);
    }
    if (!replayed && S.booth && ins.commentary && (ins.salience >= 0.5 || goal)) {
      const ex = ins.commentary[S.lang] || ins.commentary.en || [];
      if (goal) S.q = [];
      for (const l of ex) S.q.push(l);
    }
  }
  function speakNext() {
    if (S.speaking || !S.q.length || !("speechSynthesis" in window)) return;
    const l = S.q.shift(), u = new SpeechSynthesisUtterance(l.text);
    u.lang = { en: "en-GB", es: "es-ES", fr: "fr-FR", pt: "pt-PT" }[S.lang] || S.lang;
    u.rate = l.who === "lead" ? 1.12 : 0.98; u.pitch = l.who === "lead" ? 1.08 : 0.82;
    S.speaking = true; u.onend = u.onerror = () => { S.speaking = false; };
    speechSynthesis.speak(u);
  }
  setInterval(speakNext, 300);

  async function ask(q) {
    if (!q) return;
    $("answer").innerHTML = `<span class="muted">${esc(q)}</span><br>Thinking…`;
    try {
      const r = await fetch(`/api/matches/${sid}/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, lang: S.lang }) }).then((x) => x.json());
      $("answer").innerHTML = `<span class="muted">${esc(q)}</span><br>${esc(r.answer)}`;
      if (S.booth && "speechSynthesis" in window) S.q.unshift({ who: "analyst", text: r.answer });
    } catch { $("answer").textContent = "Couldn't reach the analyst. Try again."; }
  }
  // hold to speak (Web Speech API); a tap without speech support falls back to typing
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null, held = false;
  $("ask").addEventListener("pointerdown", () => {
    held = false;
    if (!Rec) return;
    rec = new Rec(); rec.lang = { en: "en-GB", es: "es-ES", fr: "fr-FR", pt: "pt-PT" }[S.lang] || S.lang; rec.interimResults = false;
    rec.onresult = (e) => ask(e.results[0][0].transcript);
    rec.onerror = () => { rec = null; };
    try { rec.start(); held = true; $("ask").textContent = "Listening…"; } catch { rec = null; }
  });
  $("ask").addEventListener("pointerup", () => {
    $("ask").textContent = "Ask";
    if (rec && held) { rec.stop(); return; }
    $("askInput").focus();
  });
  $("askForm").addEventListener("submit", (e) => { e.preventDefault(); const q = $("askInput").value.trim(); $("askInput").value = ""; ask(q); });
  $("booth").addEventListener("click", () => {
    S.booth = !S.booth; $("booth").setAttribute("aria-pressed", String(S.booth));
    if (!S.booth && "speechSynthesis" in window) { speechSynthesis.cancel(); S.q = []; }
  });
  $("persona").addEventListener("click", () => {
    S.persona = S.persona === "analyst" ? "casual" : "analyst"; store.set("persona", S.persona);
    $("persona").setAttribute("aria-pressed", String(S.persona === "analyst"));
    if (S.insights.length) showLatest(S.insights[S.insights.length - 1]); feed();
  });
  $("persona").setAttribute("aria-pressed", String(S.persona === "analyst"));
  $("player").addEventListener("change", (e) => { S.player = e.target.value; store.set("player", S.player); });

  function connect() {
    const es = new EventSource(`/api/matches/${sid}/stream`);
    es.addEventListener("hello", (e) => onHello(JSON.parse(e.data)));
    es.addEventListener("state", (e) => onState(JSON.parse(e.data)));
    es.addEventListener("insight", (e) => { const m = JSON.parse(e.data); onInsight(m.insight, m.replayed); });
    es.onerror = () => { es.close(); setTimeout(connect, 2000); };
  }
  connect();
})();
