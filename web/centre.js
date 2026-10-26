/* Read-only exploration of moments already delivered to the full match centre. */
"use strict";
window.TouchlineCentre = {
  create({getPrefs, getRender, getMemory}) {
    const $ = selector => document.querySelector(selector);
    const rail = $("#centreGoals");
    let goals = new Map(), latest = null, selected = null, following = true;
    document.querySelectorAll(".meters .meter").forEach(meter => $("#matchNumbers").appendChild(meter));
    function refresh() {
      const insight = following ? latest : selected;
      if (!insight) return;
      const prefs = getPrefs(), render = getRender(insight);
      const analyst = insight.renders?.analyst?.[prefs.lang] || insight.renders?.analyst?.en;
      const memory = getMemory(analyst);
      $("#centreChapter").textContent = following ? "The story so far" : "Selected goal";
      $("#centreMinute").textContent = `${insight.minute}′`;
      $("#centreTitle").textContent = render?.title || "This perspective is not available yet.";
      $("#centreTitle").lang = render?.lang || "en";
      $("#centreLine").textContent = render?.lines?.find(line => !line.k?.startsWith("s."))?.text || "Open the original receipt to inspect this moment.";
      $("#centreLine").lang = render?.lang || "en";
      $("#centreMemoryWrap").hidden = !memory;
      $("#centreMemory").textContent = memory?.text || "";
      $("#centreMemory").lang = analyst?.lang || "en";
      $("#centreReceipt").disabled = false;
      $("#centreReceipt").dataset.receipt = insight.id;
      $("#centreLatest").hidden = following;
      const perspective = {casual:"Fan",analyst:"Analyst",studio:"Studio",access:"Audio description"}[prefs.persona] || prefs.persona;
      $("#centreSource").textContent = `${perspective} · ${render?.lang || prefs.lang}. ${insight.verification?.status === "verified" ? "Checked against synthetic match data." : "Verification not confirmed."}${memory ? ` Memory uses Analyst ${analyst?.lang || "en"}.` : ""} Selecting a goal does not rewind the pitch.`;
      for (const button of rail.querySelectorAll("button")) button.setAttribute("aria-pressed", String(button.dataset.insight === insight.id));
    }
    function reset() {
      goals = new Map(); latest = null; selected = null; following = true;
      rail.innerHTML = '<span class="muted">Goals appear as the match unfolds.</span>';
      $("#centreTitle").textContent = "Every match has a turning point.";
      $("#centreChapter").textContent = "The story so far";
      $("#centreMinute").textContent = "";
      $("#centreLine").textContent = "Follow the replay. The latest goal and its evidence will appear here.";
      $("#centreMemoryWrap").hidden = true;
      $("#centreReceipt").disabled = true;
      delete $("#centreReceipt").dataset.receipt;
      $("#centreLatest").hidden = true;
      $("#centreSource").textContent = "Explanations are checked against fictional match data.";
    }
    rail.addEventListener("click", event => {
      const button = event.target.closest("[data-insight]");
      if (!button || !goals.has(button.dataset.insight)) return;
      selected = goals.get(button.dataset.insight); following = false; refresh();
    });
    $("#centreLatest").addEventListener("click", () => { following = true; refresh(); });
    function add(insight, render = true) {
      if (insight.kind === "goal") {
        if (!goals.has(insight.id)) {
          if (!goals.size) rail.replaceChildren();
          const button = document.createElement("button");
          button.dataset.insight = insight.id; button.textContent = `${insight.minute}′`;
          button.setAttribute("aria-label", `Explore goal at ${insight.minute} minutes`);
          rail.appendChild(button);
        }
        goals.set(insight.id, insight); latest = insight;
      } else if (!goals.size) latest = insight;
      else return;
      if (render) refresh();
    }
    reset();
    return {reset, refresh, add, appendMany(insights) { for (const insight of insights) add(insight, false); refresh(); }};
  },
};
