const test = require('node:test');
const assert = require('node:assert/strict');
const {chapterFor, memoryLine, orderedEvidence, geometry, pitch, comparison, eventSummary, provenance} = require('../web/story.js');
const player = require('../web/player-spotlight.js');

test('Q&A execution distinguishes the final router answer from the completed model attempt', () => {
  const fs = require('node:fs');
  const vm = require('node:vm');
  const app = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
  const start = app.indexOf('function answerExecution(r) {');
  assert.ok(start >= 0);
  const context = {esc: (value) => String(value)};
  vm.runInNewContext(app.slice(start, app.indexOf('\nasync function ask(q)', start)), context);
  const attempt = {path:'foundry_hosted',completed:true,fallback:false,model:'example',request_id:'R1'};
  const r = {source:'router',fallback_reason:'unbound_model_answer',execution:{path:'application_fallback',fallback:true,model_attempt:attempt}};
  const html = context.answerExecution(r);
  assert.match(html, /<p>Application fallback · answered from match data<\/p>/);
  assert.match(html, /Model attempt: Microsoft Foundry hosted agent · completed; answer not accepted/);
  assert.match(html, /unbound_model_answer/);
  assert.match(html, /Request R1/);
  // Older responses with the filmed inconsistent provenance still must label their actual source.
  assert.match(context.answerExecution({...r,execution:attempt}), /<p>Application fallback/);
  const offline = context.answerExecution({...r,execution:{path:'application_fallback',model_attempt:null}});
  assert.match(offline, /No model attempt/);
  assert.doesNotMatch(offline, /Local Agent Framework agent/);
  const selected = context.answerExecution({source:'llm:foundry',execution:attempt});
  assert.match(selected, /<p>Microsoft Foundry hosted agent<\/p>/);
  assert.doesNotMatch(selected, /Application fallback|answer not accepted/);
});

test('a player participates through a cited loss without becoming the scorer', () => {
  const varga = {id:'H9',name:'Kofi Varga'};
  const goal = {player_id:'A9',participants:[{player_id:'H9',role:'involved'},{player_id:'H9',role:'possession loss'}]};
  assert.equal(player.involvement(goal,varga),'possession loss');
  assert.equal(player.involvement(goal,{id:'H8',name:'Other'}),null);
  assert.equal(player.involvement({...goal,player_id:'H9'},varga),'Primary player');
  assert.equal(player.involvement({reasons:[{k:'s.error',p:{culprit:'Kofi Varga'}}]},varga),'Earlier possession loss');
  assert.equal(player.involvement({reasons:[{k:'unknown',p:{culprit:'Kofi Varga'}}]},varga),null);
});

test('player statistics lead with goals or saves without inventing missing totals', () => {
  const stats={goals:3,shots:7,saves:4,passes:25,completed:21,xg:1.32,top_speed_kmh:28.7};
  assert.deepEqual(player.statistics(stats,'ST')[0],['3','Goals','7 shots · match total']);
  assert.equal(player.statistics(stats,'GK')[0][1],'Saves');
  assert.equal(player.statistics({...stats,goals:undefined},'ST')[0][0],'—');
});

test('event board distinguishes recorded measurements from model estimates and missing data', () => {
  const html=eventSummary({facts:{player:'Theo <script>',type:'shot',outcome:'goal',xg:.11,shot_speed_kmh:92},position:{x:90,y:34,end_x:105,end_y:34}});
  assert(html.includes('0.11') && html.includes('xG · model estimate'));
  assert(html.includes('Recorded shot speed') && html.includes('Recorded endpoint'));
  assert(!html.includes('<script>'));
  assert(!eventSummary({facts:{type:'shot'},position:{}}).includes('Recorded start'));
});

test('generated narrator wording never inherits source-rendered provenance', () => {
  assert.equal(provenance({source:'phrasebank'}).preview,false);
  assert.equal(provenance({source:'llm:foundry'}).preview,true);
  assert.equal(provenance({preview:true,verification_scope:'Numeric checks only'}).scope,'Numeric checks only');
});

test('chapters match the goal itself, never a cited earlier goal or a milestone', () => {
  const chapters = [{event_id:'G1'}, {event_id:'G2'}];
  const insight = {kind:'goal', headline:{ev:['G2']}, event_ids:['G1','G2']};
  assert.equal(chapterFor(insight, chapters), 1);
  assert.equal(chapterFor({...insight, kind:'hat_trick'}, chapters), -1);
  assert.equal(chapterFor({...insight, headline:{ev:['future']}}, chapters), -1);
});

test('redemption survives the shorter Fan rendering and is prioritized over generic comeback', () => {
  const redemption = {k:'s.redemption', text:'Earlier loss', ev:['L1','G2']};
  assert.equal(memoryLine({lines:[{k:'s.comeback'}, redemption]}), redemption);
  assert.equal(memoryLine({lines:[{k:'r.chance_quality'}]}), undefined);
});

test('evidence remains chronological without mutating the original receipt', () => {
  const receipt = {evidence:[{event_id:'G2',t:4500},{event_id:'L1',t:2000}]};
  assert.deepEqual(orderedEvidence(receipt).map(x=>x.event_id), ['L1','G2']);
  assert.equal(receipt.evidence[0].event_id, 'G2');
});

test('missing, nonnumeric and off-pitch coordinates never become an invented location', () => {
  for (const x of [null, undefined, NaN, Infinity, '10', -1, 106]) {
    assert.equal(geometry({position:{x,y:34}}).start, null);
  }
  assert.deepEqual(geometry({position:{x:0,y:68,end_x:105,end_y:0}}), {start:[0,68],end:[105,0]});
  const svg = pitch({facts:{player:'<script>alert(1)</script>', type:'goal', minute:36},position:{}});
  assert(!svg.includes('<script>'));
  assert(svg.includes('Position unavailable'));
  assert(!svg.includes('marker-end='));
});

test('map connects only the selected event endpoints, and escapes source labels', () => {
  const svg = pitch({facts:{player:'A" onload="alert(1)',type:'pass',minute:35},position:{x:10,y:20,end_x:30,end_y:40}});
  assert(svg.includes('M10 20L30 40'));
  assert(svg.includes('&quot;'));
  assert(!svg.includes(' onload="'));
});

test('alternate endings show both branches, source and model limits', () => {
  const html = comparison({as_it_was:{result:{home:.7,draw:.2,away:.1}},what_if:{result:{home:.3,draw:.5,away:.2}},
    replays:1000, scenario:{event_id:'G2'},summary:'A < B',note:'Model estimate'}, {home:'H',away:'A'});
  assert(html.includes('With goal') && html.includes('Without goal'));
  assert(html.includes('H 70%, draw 20%, A 10%'));
  assert(html.includes('1000 simulations per branch · G2'));
  assert(html.includes('does not model changes in tactics'));
  assert(html.includes('A &lt; B'));
});
