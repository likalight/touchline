/* Match memory: read-only navigation over goals already delivered by this replay. */
"use strict";
(function (global) {
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const defaults = ["The mistake", "The redemption", "The winner"].map(title => ({ title }));
  const chapterFor = (insight, chapters) => insight.kind === "goal"
    ? chapters.findIndex(chapter => (insight.headline?.ev || []).includes(chapter.event_id)) : -1;
  const memoryLine = render => {
    const lines = render?.lines || [];
    return ["s.redemption", "s.error", "s.comeback"].map(key => lines.find(line => line.k === key)).find(Boolean)
      || lines.find(line => line.k?.startsWith("s."));
  };
  const orderedEvidence = receipt => [...(receipt.evidence || [])].sort((a, b) => a.t - b.t || a.event_id.localeCompare(b.event_id));
  const provenance = render => render?.preview || render?.source?.startsWith("llm:")
    ? {preview:true,label:"Model-generated preview",scope:render.verification_scope || "Source checks do not independently verify the meaning of generated wording."}
    : {preview:false,label:"Source-rendered explanation",scope:""};
  const point = (x, y) => Number.isFinite(x) && Number.isFinite(y) && x >= 0 && x <= 105 && y >= 0 && y <= 68
    ? [Number(x.toFixed(2)), Number(y.toFixed(2))] : null;
  function geometry(event) {
    const p = event?.position || {};
    return { start: point(p.x, p.y), end: point(p.end_x, p.end_y) };
  }
  function pitch(event) {
    const { start, end } = geometry(event);
    const name = escape(`${event.facts.player || "Match"}: ${event.facts.type}, minute ${event.facts.minute}`);
    const movement = start && end && (start[0] !== end[0] || start[1] !== end[1]);
    return `<svg viewBox="-5 -5 115 78" role="img" aria-label="${name}. ${start ? "Recorded position" : "Position unavailable"}${movement ? " and endpoint" : ""}." class="story-pitch">
      <defs><marker id="storyArrow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0 0L6 3L0 6Z" fill="currentColor"/></marker><pattern id="storyGrid" width="10.5" height="68" patternUnits="userSpaceOnUse"><rect width="5.25" height="68" fill="#ffffff" opacity=".025"/></pattern></defs>
      <rect width="105" height="68" fill="url(#storyGrid)"/>
      <g fill="none" stroke="#709584" stroke-width=".3"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105"/><circle cx="52.5" cy="34" r="9.15"/><circle cx="11" cy="34" r=".5"/><circle cx="94" cy="34" r=".5"/></g>
      ${movement ? `<path d="M${start.join(" ")}L${end.join(" ")}" fill="none" stroke="currentColor" stroke-width=".7" stroke-dasharray="1.5 1" marker-end="url(#storyArrow)"/>` : ""}
      ${start ? `<circle cx="${start[0]}" cy="${start[1]}" r="4.4" fill="none" stroke="currentColor" stroke-width=".35"/><circle cx="${start[0]}" cy="${start[1]}" r="2.4" fill="currentColor"/><text x="${start[0]}" y="${start[1] + .85}" text-anchor="middle" class="map-point-number">1</text>` : ""}
      ${movement ? `<circle cx="${end[0]}" cy="${end[1]}" r="2.4" fill="#eef0e8"/><text x="${end[0]}" y="${end[1] + .85}" text-anchor="middle" class="map-point-number">2</text>` : ""}
      </svg>`;
  }
  function eventSummary(event) {
    const f = event.facts || {}, facts = [];
    if (Number.isFinite(f.xg)) facts.push([f.xg.toFixed(2), "xG · model estimate"]);
    if (Number.isFinite(f.distance_m)) facts.push([`${f.distance_m.toFixed(1)} m`, "Recorded distance"]);
    if (Number.isFinite(f.pass_completion_prob)) facts.push([`${f.pass_completion_prob}%`, "Completion · model estimate"]);
    if (Number.isFinite(f.shot_speed_kmh)) facts.push([`${f.shot_speed_kmh.toFixed(1)} km/h`, "Recorded shot speed"]);
    const {start,end} = geometry(event), movement = start && end && (start[0] !== end[0] || start[1] !== end[1]);
    return `<div class="source-fact-strip"><div class="source-action"><span>${escape(f.type || "Event")}${f.outcome ? ` · ${escape(f.outcome)}` : ""}</span><strong>${escape(f.player || "Match event")}</strong>${f.target ? `<small>To ${escape(f.target)}</small>` : ""}</div>${facts.slice(0,2).map(([value,label])=>`<div><strong>${escape(value)}</strong><small>${escape(label)}</small></div>`).join("")}</div><div class="map-point-legend">${start ? '<span><b>1</b> Recorded start</span>' : '<span>Position unavailable</span>'}${movement ? '<span><b>2</b> Recorded endpoint</span>' : ""}</div>`;
  }

  function comparison(data, teams) {
    const row = (title, result) => `<div class="alternate-row"><span>${title}</span><div class="alternate-bar" role="img" aria-label="${escape(title)}: ${escape(teams.home)} ${Math.round(result.home * 100)}%, draw ${Math.round(result.draw * 100)}%, ${escape(teams.away)} ${Math.round(result.away * 100)}%">${["home", "draw", "away"].map(side => {
      const share = Number.isFinite(result[side]) ? Math.max(0, Math.min(100, result[side] * 100)) : 0;
      return `<span class="${side}" style="width:${share}%">${share >= 10 ? `${Math.round(share)}%` : ""}</span>`;
    }).join("")}</div></div>`;
    return `<div class="alternate-legend"><span>${escape(teams.home)} win</span><span>Draw</span><span>${escape(teams.away)} win</span></div>${row("With goal", data.as_it_was.result)}${row("Without goal", data.what_if.result)}<p>${escape(data.summary)}</p><p class="story-scope">${escape(data.replays)} simulations per branch · ${escape(data.scenario.event_id)} · ${escape(data.note)} This does not model changes in tactics or player behaviour caused by the removed goal.</p>`;
  }

  function create({ loadReceipt, openReceipt, openEvent, getPrefs, setPersona, loadWhatIf, getTeams, loadChallenge }) {
    const $ = selector => document.querySelector(selector);
    // One chapter workspace: its recorded event sits beside its explanation.
    // The animated match remains available, with a separate clock and scope.
    const pitchWrap = $(".pitch-wrap");
    const replay = document.createElement("details");
    replay.id = "storyReplay"; replay.className = "story-replay";
    const replaySummary = document.createElement("summary");
    replaySummary.textContent = "Watch the moving match";
    replay.append(replaySummary);
    const replayNote = document.createElement("p");
    replayNote.className = "story-scope";
    replayNote.textContent = "This camera follows the replay clock. The evidence above stays on your selected chapter.";
    replay.append(replayNote);
    [$(".view-bar"), $("#pitchBox"), $(".under")].forEach(element => replay.append(element));
    const evidenceSection = $("#storyEvidence"), alternate = $(".story-alternate");
    const waiting = document.createElement("div"); waiting.id = "storyBoardEmpty"; waiting.className = "story-board-empty";
    waiting.innerHTML = '<span class="section-label">The evidence board</span><h2>The first turning point is on its way.</h2><p>Recorded events appear here as this replay reaches each chapter. No future match data is shown.</p>';
    pitchWrap.append(waiting, evidenceSection, replay);
    const lab = document.createElement("section");
    lab.className = "story-lab"; lab.setAttribute("aria-label", "Explore this match");
    const tool = (id, title, hint, content) => {
      const details = document.createElement("details"); details.id = id;
      const summary = document.createElement("summary");
      const label = document.createElement("strong"), note = document.createElement("span");
      label.textContent = title; note.textContent = hint; summary.append(label, note);
      details.append(summary, content); lab.append(details); return details;
    };
    tool("storyAlternateTool", "Explore another ending", "Compare with and without this goal", alternate);
    tool("storyCheckerTool", "Challenge the evidence", "Try an incorrect estimate against the source", $("#checkerProof"));
    tool("storyAskTool", "Ask the analyst", "A question about the match so far", $("#workspace"));
    $("#playerSpotlight").after(lab);
    replay.addEventListener("toggle", () => { if (replay.open) window.dispatchEvent(new Event("resize")); });
    let chapters = defaults, seen = new Map(), selected = -1, following = true;
    let receipt = null, currentEvent = null, ticket = 0, alternateTicket = 0, cache = new Map();
    let challengeTicket = 0, challengeResult = null;
    const rail = $("#storyRail");
    $("#storyLens").hidden = false;
    $(".judge-broadcast-label").hidden = false;
    function railState() {
      // Keep the buttons mounted: a new SSE event must not steal keyboard focus.
      [...rail.children].forEach((button, index) => {
        const ins = seen.get(index);
        button.disabled = !ins;
        button.setAttribute("aria-pressed", String(index === selected));
        button.querySelector("small").textContent = ins ? `${ins.minute}′ · Open chapter` : "Not yet played";
      });
      $("#storyFollow").hidden = following || selected < 0;
    }
    function reset(next = defaults) {
      chapters = next; seen = new Map(); selected = -1; following = true; receipt = null; cache = new Map(); ticket++;
      currentEvent = null; alternateTicket++;
      resetChallenge(); $("#checkerProof").hidden = true;
      rail.innerHTML = chapters.map((chapter, index) => `<button disabled data-chapter="${index}" aria-pressed="false"><span><strong>${escape(chapter.title)}</strong><small>Not yet played</small></span><span class="chapter-arrow" aria-hidden="true">↗</span></button>`).join("");
      $("#storyContent").hidden = true; $("#storyEmpty").hidden = false; $("#storyEvidence").hidden = true;
      waiting.hidden = false;
      $("#storyChapter").textContent = "Match memory"; $("#storyMinute").textContent = "Ready";
      $("#storyTitle").textContent = "A goal is a moment. A comeback is a story.";
    }
    function content() {
      const ins = seen.get(selected);
      if (!ins) return;
      const { persona, lang } = getPrefs();
      const render = ins.renders?.[persona]?.[lang] || ins.renders?.[persona]?.en;
      const analyst = ins.renders?.analyst?.[lang] || ins.renders?.analyst?.en;
      const memory = memoryLine(analyst);
      $("#storyEmpty").hidden = true; $("#storyContent").hidden = false;
      $("#storyChapter").textContent = chapters[selected].title;
      $("#storyMinute").textContent = `${ins.minute}′`;
      $("#storyTitle").textContent = render?.title || "Waiting for this perspective…";
      $("#storyPerspective").textContent = `${({casual:"Fan",analyst:"Analyst",studio:"Studio",access:"Audio description"})[persona] || persona} · ${render?.lang || lang}`;
      $("#storyCompare").textContent = persona === "analyst" ? "Read as Fan" : "Read as Analyst";
      $("#storyLines").innerHTML = (render?.lines || []).filter(line => !line.k?.startsWith("s.")).slice(0, 3).map(line => `<li>${escape(line.text)}</li>`).join("");
      $("#storyMemory").textContent = memory?.text || "The match has not produced a linked story claim for this goal.";
      $("#storyMemory").lang = analyst?.lang || "en";
      $("#storyLinks").innerHTML = (memory?.ev || []).map(id => {
        const fact = receipt?.evidence.find(event => event.event_id === id)?.facts;
        const label = fact ? `${fact.minute}′ ${fact.type}${fact.outcome === "lost" ? " · possession lost" : ""}` : id;
        return `<button class="chip" data-memory-event="${escape(id)}" ${receipt ? "" : "disabled"} title="${escape(id)}">${escape(label)} ↗</button>`;
      }).join("");
      $("#storyProof").textContent = receipt ? `${receipt.verification.checks} checks across ${receipt.evidence.length} cited events.` : "";
      const origin = provenance(render);
      $("#storyScope").textContent = `${origin.preview ? `${origin.label}. ${origin.scope} ` : ""}${ins.verification?.status === "verified" ? "Underlying source checks passed" : "Check not confirmed"} · synthetic data. Selected chapter: ${ins.minute}′. The moving match uses its own replay clock.`;
      $("#storyReceipt").disabled = false;
      railState();
    }
    function showEvent(id) {
      const event = receipt?.evidence.find(item => item.event_id === id);
      if (!event) return;
      currentEvent = event;
      const f = event.facts;
      $("#storyEventTitle").textContent = `${f.player || "Match"} · ${f.type}${f.outcome ? ` / ${f.outcome}` : ""}`;
      $("#storyEventTime").textContent = `${f.minute}′ · Recorded event`;
      $("#storyEventTime").title = event.event_id;
      $("#storyMap").innerHTML = eventSummary(event) + pitch(event);
      const { start, end } = geometry(event);
      $("#storyMapNote").textContent = !start ? "No recorded position for this event. No location has been inferred."
        : end ? "Recorded start → endpoint, in pitch metres. The straight line connects those samples; it is not a tracked trajectory."
        : "Recorded position in pitch metres. This event has no recorded endpoint.";
      [...$("#storyEvents").querySelectorAll("button")].forEach(button => button.setAttribute("aria-pressed", String(button.dataset.storyEvent === id)));
      [...$("#storyLinks").querySelectorAll("button")].forEach(button => button.setAttribute("aria-pressed", String(button.dataset.memoryEvent === id)));
    }
    function evidence() {
      if (!receipt) return;
      const events = orderedEvidence(receipt);
      waiting.hidden = true;
      $("#storyEvidence").hidden = false;
      $("#storyEvidenceCount").textContent = `${events.length} sources · ${receipt.minute}′ goal`;
      $("#storyEvents").innerHTML = events.map(event => `<li><button data-story-event="${escape(event.event_id)}" aria-pressed="false"><span>${event.facts.minute}′</span><span><strong>${escape(event.facts.player || "Match")}</strong><small>${escape(event.facts.type)}${event.facts.target ? ` → ${escape(event.facts.target)}` : ""}</small></span><span class="source-id">${escape(event.event_id)}</span></button></li>`).join("");
      const shot = events.findLast(event => event.facts.type === "shot");
      showEvent(shot?.event_id || events.at(-1)?.event_id);
    }
    async function choose(index) {
      if (!seen.has(index)) return; // Locked chapters cannot fetch future data.
      selected = index; receipt = null; currentEvent = null;
      resetChallenge(); $("#checkerProof").hidden = false;
      const request = ++ticket, ins = seen.get(index);
      alternateTicket++;
      $("#storyWhatIf").disabled = false;
      $("#storyWhatIf").textContent = "Explore alternate ending";
      $("#storyAlternate").innerHTML = `<p>Compare the model's outlook with and without the ${ins.minute}′ goal.</p>`;
      $("#storyEvidence").hidden = true;
      content();
      if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
        $("#storyLens").animate([{opacity:.3,transform:"translateY(6px)"},{opacity:1,transform:"translateY(0)"}], {duration:260,easing:"ease-out"});
      }
      $("#storyLinks").querySelectorAll("button").forEach(button => { button.disabled = true; });
      $("#storyScope").textContent = "Loading the original evidence for this moment…";
      try {
        const result = cache.get(ins.id) || await loadReceipt(ins.id);
        if (request !== ticket) return; // A restart, chapter change or later request superseded this result.
        cache.set(ins.id, result); receipt = result;
        content(); evidence();
      } catch {
        if (request !== ticket) return;
        $("#storyScope").textContent = "Evidence could not load. Select this chapter again to retry, or open its receipt.";
      }
    }
    rail.addEventListener("click", event => {
      const button = event.target.closest("[data-chapter]");
      if (!button || button.disabled) return;
      following = false; choose(Number(button.dataset.chapter));
    });
    $("#storyCompare").addEventListener("click", () => setPersona(getPrefs().persona === "analyst" ? "casual" : "analyst"));
    $("#storyReceipt").addEventListener("click", () => { if (seen.has(selected)) openReceipt(seen.get(selected).id); });
    $("#storyFollow").addEventListener("click", () => { following = true; choose(Math.max(...seen.keys())); });
    $("#storyEvents").addEventListener("click", event => {
      const button = event.target.closest("[data-story-event]");
      if (button) showEvent(button.dataset.storyEvent);
    });
    $("#storyLinks").addEventListener("click", event => {
      const button = event.target.closest("[data-memory-event]");
      if (!button || button.disabled) return;
      showEvent(button.dataset.memoryEvent);
      $("#storyEvidence").scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start"});
      const target = [...$("#storyEvents").querySelectorAll("button")].find(item => item.dataset.storyEvent === button.dataset.memoryEvent);
      target?.focus({preventScroll: true});
    });
    $("#storyRawEvent").addEventListener("click", () => { if (currentEvent) openEvent(currentEvent.event_id); });
    function resetChallenge() {
      challengeTicket++; challengeResult = null;
      $("#checkerRun").disabled = false;
      $("#checkerRun").textContent = "Try an incorrect stat";
      $("#checkerDownload").hidden = true;
      $("#checkerResult").innerHTML = '<p class="muted">Run the test for this goal. The match and its original receipt stay unchanged.</p>';
    }
    $("#checkerRun").addEventListener("click", async () => {
      if (!seen.has(selected)) return;
      const request = ++challengeTicket;
      $("#checkerRun").disabled = true;
      $("#checkerResult").textContent = "Checking the original estimate and an altered copy…";
      try {
        const result = await loadChallenge(seen.get(selected).id);
        if (request !== challengeTicket) return;
        challengeResult = result;
        const row = (label, item) => `<div class="checker-row"><span>${label}</span><strong>${escape(item.value)} <small>xG</small></strong><span class="checker-verdict">${escape(item.status)}</span></div>`;
        $("#checkerResult").innerHTML = `<p class="checker-summary">${result.passed ? "Incorrect estimate caught." : "Test did not pass. Inspect the result."}</p>${row("Original claim", result.original)}${row("Altered copy", result.altered)}<p>Source estimate: <strong>${escape(result.source_value)} xG</strong> · ${escape(result.event_id)}</p><p class="story-scope">${escape(result.altered.issues.join("; "))}</p><p class="story-scope">${escape(result.scope)}</p>`;
        $("#checkerDownload").hidden = false;
        $("#checkerRun").textContent = "Run test again";
      } catch {
        if (request === challengeTicket) $("#checkerResult").textContent = "The checker test could not run. Try again.";
      } finally {
        if (request === challengeTicket) $("#checkerRun").disabled = false;
      }
    });
    $("#checkerDownload").addEventListener("click", () => {
      if (!challengeResult) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(challengeResult, null, 2)], {type:"application/json"}));
      const link = document.createElement("a"); link.href = url; link.download = "touchline-checker-test.json"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    $("#storyWhatIf").addEventListener("click", async () => {
      if (!seen.has(selected)) return;
      const request = ++alternateTicket, eventId = chapters[selected].event_id;
      $("#storyWhatIf").disabled = true;
      $("#storyAlternate").textContent = "Rebuilding this moment and simulating both endings…";
      try {
        const result = await loadWhatIf(eventId);
        if (request !== alternateTicket) return;
        $("#storyAlternate").innerHTML = comparison(result, getTeams());
        $("#storyWhatIf").textContent = "Run comparison again";
      } catch {
        if (request !== alternateTicket) return;
        $("#storyAlternate").textContent = "The comparison could not load. Try again.";
      } finally {
        if (request === alternateTicket) $("#storyWhatIf").disabled = false;
      }
    });
    reset();
    return {
      reset,
      refresh() { content(); if (currentEvent) showEvent(currentEvent.event_id); },
      add(insight) {
        const index = chapterFor(insight, chapters);
        if (index < 0) return;
        const isNew = !seen.has(index);
        seen.set(index, insight);
        if (isNew && following) choose(index); else { railState(); if (index === selected) content(); }
      },
    };
  }
  const api = { create, chapterFor, memoryLine, orderedEvidence, geometry, pitch, comparison, eventSummary, provenance };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else global.TouchlineStory = api;
})(globalThis);
