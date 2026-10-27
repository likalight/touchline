/* Record actual UI interactions with editorial captions. No fabricated cloud footage.
   Run against a local test server using the same Playwright variables as browser tests.
   DEMO_RECORDING selects the raw video/clip manifest directory. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const base=process.env.TOUCHLINE_URL || 'http://127.0.0.1:8766';
const output=process.env.DEMO_RECORDING || 'work/demo-recording';
(async()=>{
 await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:output,size:{width:1440,height:1000}}});
 const started=Date.now(), page=await context.newPage(), clips=[];
 let owner;
 const markers=['#ff0000','#00ff00','#0000ff','#ffff00','#ff00ff','#00ffff','#ffffff','#ff8000','#8000ff','#008080'];
 const caption=async(text,color)=>page.evaluate(({text,color})=>{
   let bar=document.getElementById('recording-caption');
   if(!bar){bar=document.createElement('div');bar.id='recording-caption';bar.style.cssText='position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#291735;color:#fff;padding:18px 38px;font:500 24px/1.35 Barlow,system-ui,sans-serif;box-shadow:0 -1px 0 #655570;pointer-events:none';document.body.appendChild(bar);}
   bar.replaceChildren();const scope=document.createElement('small');scope.textContent='LOCAL REHEARSAL · SYNTHETIC MATCH';scope.style.cssText='display:block;color:#d6f77b;font-size:12px;letter-spacing:1.5px;margin-bottom:8px';bar.append(scope,document.createTextNode(text));
   let marker=document.getElementById('recording-marker');if(!marker){marker=document.createElement('div');marker.id='recording-marker';marker.style.cssText='position:fixed;bottom:0;left:0;width:8px;height:8px;z-index:10000;pointer-events:none';document.body.appendChild(marker);}marker.style.background=color;
   if(!document.getElementById('recording-tick')){const tick=document.createElement('div');tick.id='recording-tick';tick.style.cssText='position:fixed;bottom:0;left:8px;width:8px;height:8px;z-index:10000;background:#000;pointer-events:none';document.body.appendChild(tick);tick.animate([{background:'#000'},{background:'#fff'}],{duration:200,iterations:Infinity});}
 },{text,color});
 const clip=async(name,text,seconds)=>{const marker=markers[clips.length];await caption(text,marker);await page.screenshot({path:path.join(output,`${name}.png`)});await page.waitForTimeout(350);const start=(Date.now()-started)/1000;await page.waitForTimeout(seconds*1000);clips.push({name,start,end:(Date.now()-started)/1000,caption:text,marker});};
 try {
  await page.goto(`${base}/judge`);
  await page.locator('#storyRail button').first().waitFor();
  await page.locator('#storyTheme').selectOption('light');
  await page.locator('#judgeHeroImage').evaluate(i=>i.decode());
  await clip('opening','Touchline remembers the match, explains why a moment matters, and shows the evidence.',9);
  await page.locator('#judgeStart').click();
  await page.waitForFunction(()=>document.querySelector('#storyMinute').textContent==='28′' && !document.querySelector('#storyEvidence').hidden,null,{timeout:30000});
  owner=await page.evaluate(()=>({sid:S.sid,token:S.judgeToken}));
  await page.getByRole('button',{name:'Pause',exact:true}).click();
  await page.locator('.stage').evaluate(el=>el.scrollIntoView({block:'start'}));
  await clip('mistake','The mistake: a goal begins with Kofi Varga losing possession. The story keeps that connection.',12);
  await page.getByRole('button',{name:'Resume',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#storyMinute').textContent==='44′' && !document.querySelector('#storyEvidence').hidden,null,{timeout:60000});
  await page.getByRole('button',{name:'Pause',exact:true}).click();
  await page.locator('.stage').evaluate(el=>el.scrollIntoView({block:'start'}));
  await clip('redemption','Sixteen minutes later, Varga scores. Touchline connects the goal to his earlier mistake.',12);
  await page.locator('#storyLinks button').first().click();
  await clip('memory-source','Follow the connection back to the earlier event and its recorded position. No inferred player trajectory.',9);
  await page.locator('#storyCompare').click();
  await page.locator('.stage').evaluate(el=>el.scrollIntoView({block:'start'}));
  await clip('audiences','One moment, different audiences. Analyst adds tactical evidence; Fan keeps the explanation concise.',9);
  await page.locator('#storyReceipt').click();
  await page.getByText('Compare Fan and Analyst',{exact:true}).click();
  await clip('receipt','The downloadable receipt preserves source facts, the original checks, agent handoffs and audience versions.',10);
  await page.locator('#drawerClose').click();
  await page.locator('#checkerRun').click();
  await page.locator('.checker-summary').waitFor();
  await page.locator('#checkerProof').evaluate(el=>el.scrollIntoView({block:'start'}));
  await clip('checker','Try an incorrect estimate. The production numeric checker rejects the altered copy; the match stays untouched.',12);
  await page.getByRole('button',{name:'Resume',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#pauseBtn').disabled && document.querySelector('#storyMinute').textContent==='90′',null,{timeout:60000});
  await page.locator('.stage').evaluate(el=>el.scrollIntoView({block:'start'}));
  await clip('winner','Then the late winner. The replay follows one complete story: mistake, redemption, victory.',9);
  await page.locator('#storyWhatIf').click();
  await page.locator('.alternate-row').first().waitFor();
  await page.locator('.story-alternate').evaluate(el=>el.scrollIntoView({block:'start'}));
  await clip('alternate','Remove the goal and compare 1,000 simulated endings per branch. Estimates remain distinct from match facts.',10);
  await page.locator('#checkerProof').evaluate(el=>el.scrollIntoView({block:'start'}));
  await clip('close','Built with Microsoft Agent Framework. Azure deployment, hosted Foundry proof and participant validation are still pending.',9);
 } finally {
  if(owner) await page.request.delete(`${base}/api/judge/${owner.sid}`,{headers:{'X-Touchline-Judge-Token':owner.token}}).catch(()=>{});
  const video=page.video();await context.close();
  if(video) await video.saveAs(path.join(output,'rehearsal-raw.webm'));
  await fs.writeFile(path.join(output,'clips.json'),JSON.stringify({scope:'Local UI rehearsal. Edited pauses between observed match chapters; no cloud execution is represented.',clips},null,2));
  await browser.close();
 }
 if(clips.length!==10) throw new Error(`Incomplete recording: ${clips.length}/10 clips`);
 console.log(`Recorded ${clips.length} clips (${clips.reduce((n,c)=>n+c.end-c.start,0).toFixed(1)} seconds).`);
})().catch(error=>{console.error(error);process.exitCode=1});
