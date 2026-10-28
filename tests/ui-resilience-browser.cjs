/* Isolated real browser checks for startup, keyboard controls and stream recovery UI.
   Uses the same environment variables as centre-browser.cjs. Fault injection is labelled. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const base=process.env.TOUCHLINE_URL || 'http://127.0.0.1:8765';
const output=process.env.UI_SCREENSHOTS || 'work/ui-resilience';
(async()=>{
 await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  // A stalled optional health request cannot indefinitely block core match controls.
  await page.route('**/api/health',async route=>{await new Promise(r=>setTimeout(r,6500));await route.abort().catch(()=>{});});
  await page.goto(base,{waitUntil:'domcontentloaded'});
  assert.equal(await page.locator('#score').innerText(),'–');
  assert.equal(await page.locator('#wpHl').innerText(),'–');
  assert.equal(await page.locator('#pauseBtn').isDisabled(),true);
  await page.screenshot({path:path.join(output,'06-startup-awaiting-data.png')});
  await page.waitForFunction(()=>S.snap && S.me,null,{timeout:10000});
  assert.equal(await page.locator('#mainStage').getAttribute('aria-busy'),'false');
  assert.equal(await page.locator('#lang option[value="es"]').isEnabled(),true,'healthy language data survives a failed health request');
  await page.unroute('**/api/health');
  console.log('PASS: stalled optional health request, honest empty metrics and independently loaded languages.');

  const response=await page.request.post(`${base}/api/matches`,{data:{seed:87,speed:40,chaos:0}});
  assert(response.ok()); const {session_id:sid}=await response.json();
  await page.goto(`${base}/?session=${sid}`); await page.waitForFunction(()=>S.snap && S.me);
  await page.request.post(`${base}/api/matches/${sid}/control`,{data:{action:'jump',value:30}});
  await page.waitForFunction(()=>S.snap.minute>=30,null,{timeout:25000});
  await page.locator('#pauseBtn').click(); await page.waitForFunction(()=>S.paused);
  await page.locator('#viewSeg [data-view="tactical"]').click();
  await page.locator('#tourBtn').click();
  for(let i=0;i<3;i++) await page.locator('#tourNext').click();
  assert.equal(await page.locator('#tourStep').innerText(),'4 of 9');
  assert(await page.locator('#booth').isVisible(),'tour exposes its commentary target');
  await page.screenshot({path:path.join(output,'07-tour-visible-target.png')});
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'tourBtn');
  assert.equal(await page.locator('#booth').isVisible(),false);
  assert.equal(await page.evaluate(()=>S.prefs.view),'tactical');
  assert.equal(await page.evaluate(()=>S.prefs.persona),'casual');
  console.log('PASS: tour reveals the target, restores camera/persona/preferences and returns keyboard focus.');

  await page.locator('#tool-players').click();
  const names=()=>page.locator('#playersTable tbody tr td:nth-child(2)').allTextContents();
  await page.getByRole('button',{name:'Sort by Player',exact:true}).focus(); await page.keyboard.press('Enter');
  let list=await names(); assert.deepEqual(list,[...list].sort((a,b)=>a.localeCompare(b)));
  assert.equal(await page.locator('#playersTable th[aria-sort]').getAttribute('aria-sort'),'ascending');
  await page.keyboard.press('Space'); list=await names(); assert.deepEqual(list,[...list].sort((a,b)=>b.localeCompare(a)));
  await page.getByRole('button',{name:'Sort by Pass %',exact:true}).click();
  const percentages=(await page.locator('#playersTable tbody tr td:nth-child(6)').allTextContents()).filter(v=>v!=='–').map(Number);
  assert.deepEqual(percentages,[...percentages].sort((a,b)=>b-a));
  await page.evaluate(()=>renderPlayers());
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.sort),'acc');
  const favourite=page.locator('#playersTable [data-fav]').first(); const pid=await favourite.getAttribute('data-fav');
  await favourite.focus(); await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.fav),pid);
  assert.equal(await page.locator(`[data-fav="${pid}"]`).getAttribute('aria-pressed'),'true');
  await page.evaluate(()=>renderPlayers());
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.fav),pid);
  await page.screenshot({path:path.join(output,'08-keyboard-player-sorting.png')});
  console.log('PASS: keyboard name/percentage sorting, reverse direction and stable action focus through live refresh.');

  // Protocol fault injection: assert visible treatment of loss/replay/expiry, without claiming a cloud failure.
  await page.evaluate(()=>S.es.dispatchEvent(new Event('error')));
  assert.match(await page.locator('#connectionStatus').innerText(),/Reconnecting.*last received/);
  await page.evaluate(()=>onState(S.snap));
  assert.equal(await page.locator('#connectionStatus').isVisible(),false);
  await page.evaluate(()=>{
    window.__liveActions=0; const original=window.TV3D;
    window.TV3D={ready:true,onEvent:()=>window.__liveActions++};
    const pid=Object.keys(S.players)[0]; S.prefs.focus=pid;
    onEvent({replayed:true,etype:'shot',t:1200,x:15,y:20,end_x:0,end_y:34,player_id:pid,q:{shot_speed_kmh:90},frame:{[pid]:[15,20]}});
    window.TV3D=original;
  });
  assert.equal(await page.evaluate(()=>window.__liveActions),0);
  assert.equal(await page.locator('.focus-ticker').count(),0);
  assert.equal(await page.evaluate(()=>S.ballEv),null);
  assert.deepEqual(await page.evaluate(()=>S.ball),[0,34]);
  await page.evaluate(()=>S.es.dispatchEvent(new MessageEvent('session_expired',{data:'{}'})));
  assert.equal(await page.evaluate(()=>S.es.readyState),2);
  assert.match(await page.locator('#connectionStatus').innerText(),/expired/);
  assert.equal(await page.locator('#pauseBtn').isDisabled(),true);
  await page.screenshot({path:path.join(output,'09-expired-replay.png')});
  console.log('PASS: visible reconnect and expiry, stopped expired stream, no historical action animation.');
  for(const width of [320,390,768]) {
    await page.setViewportSize({width,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`);
  }
  await page.screenshot({path:path.join(output,'10-table-responsive.png')});

  // The companion must label an explicitly model-generated preview and reset history on bootstrap.
  await page.route('**/api/matches/*/stream',async route=>{
    const meta=await page.request.get(`${base}/api/matches/${sid}`);
    const match=await meta.json();
    const hello={match:match.match || match};
    const insight={id:'preview-fixture',minute:30,kind:'goal',verification:{status:'verified'},renders:{casual:{en:{title:'Preview fixture',preview:true,source:'llm:test',verification_scope:'Fixture preview scope',lines:[{text:'Fixture copy'}]}}}};
    const packet=(type,data)=>`event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
    await route.fulfill({contentType:'text/event-stream',body:packet('hello',hello)+packet('insight',{insight,replayed:true})+packet('hello',hello)+packet('insight',{insight,replayed:true})});
  });
  await page.goto(`${base}/phone?session=${sid}`);
  await page.waitForFunction(()=>document.querySelector('#ltitle').textContent==='Preview fixture');
  assert.equal(await page.locator('#lok').innerText(),'Model-generated preview');
  assert.equal(await page.locator('#previewScope').innerText(),'Fixture preview scope');
  assert.equal(await page.locator('#feed .row').count(),0,'second bootstrap clears the old history');
  await page.locator('#ask').focus(); await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'askInput');
  assert(await page.getByRole('button',{name:'Ask analyst',exact:true}).isVisible());
  assert.deepEqual(errors,[]);
  console.log('PASS: companion generated-preview scope, history reset and keyboard question entry.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
