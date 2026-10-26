const test = require('node:test');
const assert = require('node:assert/strict');
const {chapterFor, memoryLine, orderedEvidence, geometry, pitch, comparison} = require('../web/story.js');

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
