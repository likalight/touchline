/* Player identity and evidence from state already delivered to this browser.
   No endpoint reads: a private replay must never reveal its future match data. */
"use strict";
const TouchlinePlayer = {
  involvement(insight, player) {
    if ([insight.player_id, insight.viz?.player_id].includes(player.id)) return "Primary player";
    const matches = (insight.participants || []).filter(item => item.player_id === player.id);
    const explicit = matches.find(item => ["possession loss", "turnover"].includes(item.role)) || matches[0];
    if (explicit) return explicit.role || "Participant";
    // Compatibility with older delivered insights: use typed frame inputs, never
    // substring matching prose or a request for future match history.
    for (const frame of insight.reasons || []) {
      const params = frame.p || {};
      if (frame.k === "s.error" && params.culprit === player.name) return "Earlier possession loss";
      if (frame.k === "s.redemption" && params.player === player.name) return "Redemption";
    }
    return null;
  },
  statistics(stats, position) {
    const n = (value, digits = 0) => Number.isFinite(value) ? value.toFixed(digits) : "—";
    if (!stats) return [["—", "Goals", "Awaiting data"], ["—", "Expected goals", "Awaiting data"], ["—", "Passes", "Awaiting data"]];
    const passes = [n(stats.passes), "Passes", `${n(stats.completed)} completed${stats.passes > 0 ? ` · ${Math.round(stats.completed / stats.passes * 100)}%` : " · no attempts yet"}`];
    if (position === "GK") return [[n(stats.saves), "Saves", "Recorded in this match"], passes, [n(stats.top_speed_kmh, 1), "Top speed", "km/h · tracking estimate"]];
    return [[n(stats.goals), "Goals", `${n(stats.shots)} shots · match total`], [n(stats.xg, 2), "Expected goals", "Model estimate (xG)"], passes];
  },
  create({getState, getRender, onFollow, openReceipt}) {
    const $ = selector => document.querySelector(selector);
    const root = $("#playerSpotlight"), select = $("#spotlightSelect");
    let selected = "", lastFocus = "", rosterKey = "", contentKey = "", moment = null;
    let storyPlayer = "", pinnedMoment = null, availableMoments = [];
    const kinds = {goal:"Goal",brace:"Milestone",hat_trick:"Hat-trick",standout:"Standout",hard_pass:"Pass",line_break:"Pass",chance_saved:"Save",chance_missed:"Chance",chance_blocked:"Chance",sprint:"Sprint",long_carry:"Carry"};
    const priority = insight => insight.kind === "goal" ? 3 : ["brace", "hat_trick", "standout"].includes(insight.kind) ? 0 : 1;
    const roles = {GK:"Goalkeeper",RB:"Right back",RCB:"Centre back",LCB:"Centre back",LB:"Left back",DM:"Defensive midfield",RCM:"Central midfield",LCM:"Central midfield",RW:"Right wing",LW:"Left wing",ST:"Striker"};
    const set = (id, value) => { $(id).textContent = value; };
    const number = (value, digits = 0) => Number.isFinite(value) ? value.toFixed(digits) : "—";
    function refresh() {
      const state = getState(), meta = state.meta, players = state.players || {};
      if (!meta || !Object.keys(players).length) { root.hidden = true; return; }
      root.hidden = false;
      const key = `${meta.match_id}:${Object.keys(players).join(",")}`;
      if (key !== rosterKey) {
        rosterKey = key; select.replaceChildren();
        for (const team of [meta.home, meta.away]) {
          const group = document.createElement("optgroup"); group.label = team.name;
          for (const player of team.players) group.appendChild(new Option(`#${player.number} ${player.name} · ${player.position}`, player.id));
          select.appendChild(group);
        }
        selected = "";
      }
      const focus = state.prefs.focus || "";
      if (players[focus] && focus !== lastFocus) selected = focus;
      lastFocus = focus;
      if (!players[selected]) selected = players[focus] ? focus : meta.home.players.find(p => p.position === "ST")?.id || meta.home.players[0].id;
      const player = players[selected], team = meta[player.team];
      if (storyPlayer !== selected) { storyPlayer = selected; pinnedMoment = null; }
      select.value = selected;
      const stats = state.snap?.players?.[selected];
      const delivered = (state.insights || []).filter(ins => TouchlinePlayer.involvement(ins, player));
      // Several agents can explain one goal. Keep its goal explanation instead of
      // a same-minute milestone, and never request the undelivered match history.
      const byMinute = new Map();
      for (const insight of delivered) {
        const existing = byMinute.get(insight.minute);
        if (!existing || priority(insight) >= priority(existing)) byMinute.set(insight.minute, insight);
      }
      availableMoments = [...byMinute.values()].sort((a, b) => a.minute - b.minute);
      const latest = availableMoments.at(-1) || null;
      moment = availableMoments.find(ins => ins.id === pinnedMoment) || latest;
      if (pinnedMoment && moment?.id !== pinnedMoment) pinnedMoment = null;
      let railMoments = availableMoments.slice(-3);
      if (pinnedMoment && !railMoments.some(ins => ins.id === pinnedMoment)) railMoments = [moment, ...railMoments.slice(-2)];
      const render = moment && getRender(moment);
      const nextKey = JSON.stringify([key, selected, focus, state.snap?.minute, stats, state.prefs.persona, state.prefs.lang, moment?.id, pinnedMoment, railMoments.map(ins => [ins.id,ins.minute,ins.kind]), moment?.verification?.status, render]);
      if (contentKey === nextKey) return;
      contentKey = nextKey;
      // Data controls a decorative club stripe, never text contrast.
      root.style.setProperty("--spotlight-kit", /^#[a-f\d]{3,8}$/i.test(team.color) ? team.color : "#2f7cf6");
      set("#spotlightClubCode", team.short);
      set("#spotlightKitName", player.name.split(" ").slice(-1)[0]);
      set("#spotlightNumber", player.number);
      // This original illustration represents only the named fictional player.
      // Other roster members retain their own number, never somebody else's face.
      const illustrated = player.name === "Kofi Varga" && player.number === 9 && player.team === "home";
      $("#spotlightPlayerImage").hidden = !illustrated;
      root.classList.toggle("spotlight-featured", illustrated);
      set("#spotlightArtNote", illustrated ? "Original AI illustration · fictional player" : "Fictional player · squad number");
      set("#spotlightPosition", `${roles[player.position] || player.position} · #${player.number}`);
      set("#spotlightName", player.name); set("#spotlightTeam", team.name);
      set("#spotlightTime", stats ? `Match totals through ${state.snap.minute}′ · synthetic data` : "Waiting for the first match snapshot.");
      const items = TouchlinePlayer.statistics(stats, player.position);
      const fragment = document.createDocumentFragment();
      for (const [value, label, note] of items) {
        const cell = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd"), small = document.createElement("small");
        dt.textContent = label; dd.textContent = value; small.textContent = note; dd.appendChild(small); cell.append(dt, dd); fragment.appendChild(cell);
      }
      $("#spotlightStats").replaceChildren(fragment);
      const following = focus === selected;
      set("#spotlightFollow", following ? "Following · open player cam" : "Follow on pitch");
      $("#spotlightFollow").setAttribute("aria-pressed", String(following));
      set("#spotlightFollowNote", following ? "Your player stays selected as the match moves on." : "Player camera and pitch marker follow your selection.");
      const rail = $("#spotlightMoments"), retained = new Set(railMoments.map(ins => ins.id));
      for (const button of [...rail.children]) if (!retained.has(button.dataset.moment)) button.remove();
      railMoments.forEach((ins, index) => {
        let button = [...rail.children].find(el => el.dataset.moment === ins.id);
        if (!button) { button = document.createElement("button"); button.type = "button"; button.dataset.moment = ins.id; }
        const involvement = TouchlinePlayer.involvement(ins, player);
        button.textContent = `${ins.minute}′ ${["Earlier possession loss", "possession loss", "turnover"].includes(involvement) ? "Possession loss" : kinds[ins.kind] || "Moment"}`;
        button.setAttribute("aria-pressed", String(ins.id === moment?.id));
        button.setAttribute("aria-label", `${button.textContent}, explore moment at ${ins.minute} minutes`);
        if (rail.children[index] !== button) rail.insertBefore(button, rail.children[index] || null);
      });
      $("#spotlightLatest").hidden = !pinnedMoment;
      set("#spotlightMomentTime", moment ? `${moment.minute}′` : "");
      const involvement = moment && TouchlinePlayer.involvement(moment, player);
      set("#spotlightMomentTitle", ["Earlier possession loss", "possession loss", "turnover"].includes(involvement) ? "The possession before the goal." : render?.title || (moment ? "A moment to inspect." : "Their story is still unfolding."));
      $("#spotlightMomentTitle").lang = render?.lang || "en";
      const secondary = ["Earlier possession loss", "possession loss", "turnover"].includes(involvement);
      const storyRender = secondary ? getRender(moment, "analyst") || render : render;
      const storyLine = window.TouchlineStory?.memoryLine(storyRender) || storyRender?.lines?.find(line => !line.k?.startsWith("s."));
      set("#spotlightMomentLine", storyLine?.text || (moment ? "Open the receipt to see the source events for this moment." : "Explained moments involving this player will appear here as they arrive. Try another player to explore their match."));
      $("#spotlightMomentLine").lang = storyRender?.lang || "en";
      $("#spotlightReceipt").disabled = !moment;
      const perspective = secondary ? "Analyst memory" : {casual:"Fan",analyst:"Analyst",studio:"Studio",access:"Audio description"}[state.prefs.persona] || state.prefs.persona;
      const origin = window.TouchlineStory.provenance(storyRender);
      set("#spotlightSource", moment ? `${pinnedMoment ? "Selected" : "Latest delivered"} moment · ${perspective} · ${storyRender?.lang || state.prefs.lang}. ${origin.preview ? `${origin.label}. ` : ""}${moment.verification?.status === "verified" ? "Underlying source checks passed." : "Verification not confirmed."} Moment ${moment.minute}′ · totals ${state.snap?.minute ?? "—"}′.${state.judge ? " This replay shows selected chapters, not every match event." : " Inspecting a moment does not rewind the pitch."}` : "Only moments delivered to this replay appear here. All players and clubs are fictional.");
    }
    select.addEventListener("change", () => { selected = select.value; refresh(); });
    $("#spotlightFollow").addEventListener("click", () => { if (selected) { onFollow(selected); refresh(); } });
    $("#spotlightReceipt").addEventListener("click", () => { if (moment) openReceipt(moment.id); });
    $("#spotlightMoments").addEventListener("click", event => { const button = event.target.closest("[data-moment]"); if (button && availableMoments.some(ins => ins.id === button.dataset.moment)) { pinnedMoment = button.dataset.moment; refresh(); } });
    $("#spotlightLatest").addEventListener("click", () => { pinnedMoment = null; refresh(); });
    return {refresh, reset() { selected = ""; lastFocus = ""; rosterKey = ""; contentKey = ""; moment = null; pinnedMoment = null; storyPlayer = ""; availableMoments = []; $("#spotlightMoments").replaceChildren(); root.hidden = true; }};
  },
};
if (typeof module !== "undefined" && module.exports) module.exports = TouchlinePlayer;
else window.TouchlinePlayer = TouchlinePlayer;
