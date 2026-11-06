/* Zero-dependency smoke test for the interactive Attention Playground.
   Runs in GitHub Actions without downloading a browser. */
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.resolve(__dirname,"..");
const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
const js=fs.readFileSync(path.join(root,"lab-play.js"),"utf8");
const publish=fs.readFileSync(path.join(root,".github/workflows/publish.yml"),"utf8");
const precedentMarkup=html.slice(html.indexOf('<ul id="product-examples"'),html.indexOf('</ul>',html.indexOf('<ul id="product-examples"')));
assert.equal((precedentMarkup.match(/class="precedent-card"/g)||[]).length,4,"Four verified precedents must be available without archive data");
assert.equal((precedentMarkup.match(/<a href="https:\/\//g)||[]).length,7,"Precedents need direct feature and access sources");
for(const label of ["Intention Tracking guide","Freedom setup guide","Apple Focus setup guide","Android Digital Wellbeing guide"]){assert(precedentMarkup.includes(label),"Missing source guide: "+label)}
assert(html.includes("not independent outcome evidence"),"Product documentation must not imply outcome evidence");
assert.equal((precedentMarkup.match(/<details class="precedent-details">/g)||[]).length,4,"Full source and access details must remain available in native disclosures");
assert.equal((precedentMarkup.match(/<strong>Access:<\/strong>/g)||[]).length,4,"Keep the complete access notes, not just short labels");
assert(!fs.readFileSync(path.join(root,"app.js"),"utf8").includes("showProductExamples"),"Archive rendering must not replace the static, source-checked precedents");
for(const p of ["lab-play.js","lab-play.css"])assert(html.includes(p),"Missing linked asset "+p);
for(const p of ["lab-play.js","lab-play.css"])assert(publish.includes(p),"File not included in GitHub Pages publish workflow: "+p);
for(const id of ["play-switch","play-recovery","play-assist","switch-start","switch-left","switch-right","switch-results","recovery-start","recovery-interaction","assist-choices","assist-feedback"]){
 assert(html.includes('id="'+id+'"'),"Missing expected Lab DOM id: "+id);
}
const usedIds=[...js.matchAll(/\$\("#([^"]+)"\)/g)].map(x=>x[1]);
for(const id of new Set(usedIds)){const pure=id.split(" ")[0];assert(html.includes('id="'+pure+'"'),"Lab script selects nonexistent id "+pure)}
const all=[],ids={},observers=[];
class FakeElement{
 constructor(tag="div",cls="",id=null){
  this.tagName=tag.toUpperCase();this._className=cls;this.classes=new Set(cls.split(/\s+/).filter(Boolean));
  this.dataset={};this.children=[];this.handlers={};this.style={};this.hidden=false;this.disabled=false;this.tabIndex=0;this.value="";this.textContent="";this.attributes={};
  this.classList={add:(...n)=>n.forEach(x=>this.classes.add(x)),remove:(...n)=>n.forEach(x=>this.classes.delete(x)),toggle:(n,v)=>{if(v===undefined)v=!this.classes.has(n);v?this.classes.add(n):this.classes.delete(n);return v},contains:n=>this.classes.has(n)};
  if(id){this.id=id;ids[id]=this}all.push(this);
 }
 get hidden(){return this._hidden||false}
 set hidden(value){const changed=this._hidden!==value;this._hidden=value;if(changed)observers.filter(x=>x.target===this).forEach(x=>x.callback())}
 getAttribute(k){return this.attributes[k]??null}
 get className(){return [...this.classes].join(" ")}
 set className(c){this.classes=new Set(c.split(/\s+/).filter(Boolean))}
 append(...els){els.forEach(x=>{assert(x instanceof FakeElement,"Expected fake DOM node");this.children.push(x)})}
 replaceChildren(...els){this.children=[];this.textContent="";this.append(...els)}
 addEventListener(type,handler){(this.handlers[type]??=[]).push(handler)}
 setAttribute(k,v){this.attributes[k]=String(v)}
 click(){if(this.disabled)return;for(const fn of this.handlers.click||[])fn({type:"click",preventDefault(){}});if(typeof this.onclick==="function")this.onclick({type:"click",preventDefault(){}})}
 focus(){doc.activeElement=this}
}
const attr=(s,k)=>{const r=new RegExp("(?:^|\\s)"+k+'="([^"]*)"');return r.exec(s)?.[1]??null};
for(const match of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*)>/gi)){
 const tag=match[1],atts=match[2],id=attr(atts,"id");
 const datas=[...atts.matchAll(/data-([a-z][a-z-]*)="([^"]*)"/g)];
 if(!id&&!datas.length)continue;
 const el=new FakeElement(tag,attr(atts,"class")||"",id);
 for(const [,k,v] of datas)el.dataset[k.replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;
 if(attr(atts,"role"))el.setAttribute("role",attr(atts,"role"));
 el.hidden=/(?:^|\s)hidden(?:\s|$)/.test(atts);
 el.disabled=/(?:^|\s)disabled(?:\s|$)/.test(atts);
}
function descendants(e){const out=[];for(const c of e.children){out.push(c,...descendants(c))}return out}
const doc={
 hidden:false,activeElement:{tagName:"BODY"},listeners:{},
 querySelector(s){if(s.startsWith("#"))return ids[s.slice(1)]||null;return this.querySelectorAll(s)[0]||null},
 querySelectorAll(s){
  if(s.startsWith("[data-")){const k=s.match(/^\[data-([a-z-]+)\]$/)?.[1];if(!k)throw Error("Unknown query "+s);const name=k.replace(/-([a-z])/g,(_,c)=>c.toUpperCase());return all.filter(x=>x.dataset[name]!==undefined)}
  if(s===".switch-dot")return all.filter(x=>x.classes.has("switch-dot"));
  if(s==="#assist-choices .assist-option")return descendants(ids["assist-choices"]).filter(x=>x.classes.has("assist-option"));
  throw Error("Unexpected query "+s);
 },
 createElement(tag){return new FakeElement(tag)},
 addEventListener(type,fn){(this.listeners[type]??=[]).push(fn)}
};
const timers=[];let timerID=0;
const randomQueue=[],testMath=Object.create(Math);testMath.random=()=>randomQueue.length?randomQueue.shift():.42;
const environment={Math:testMath,document:doc,performance:{now:()=>environment.time},time:100,console,
 setTimeout:fn=>{const id=++timerID;timers.push({id,fn});return id},
 clearTimeout:id=>{const i=timers.findIndex(x=>x.id===id);if(i>=0)timers.splice(i,1)},
 MutationObserver:class{constructor(callback){this.callback=callback}observe(target){this.target=target;observers.push(this)}}};
const flush=()=>{environment.time+=500;const fn=timers.shift();assert(fn,"Expected a pending transition");fn.fn()};
const visibility=hidden=>{doc.hidden=hidden;for(const fn of doc.listeners.visibilitychange||[])fn()};
const key=(key,target=doc.activeElement,extra={})=>{
 const e={key,defaultPrevented:false,stopped:false,preventDefault(){this.defaultPrevented=true},stopPropagation(){this.stopped=true},...extra};
 for(const fn of target.handlers?.keydown||[])fn(e);
 if(!e.stopped)for(const fn of doc.listeners.keydown||[])fn(e);
 return e;
};
const answerSwitch=()=>{
 const num=Number(ids["switch-number"].textContent),left=ids["switch-cue"].textContent.startsWith("ODD")?num%2===1:num<5;
 environment.time+=135;(left?ids["switch-left"]:ids["switch-right"]).click();
};

vm.runInNewContext(js,environment,{timeout:4000,filename:"lab-play.js"});
const by=id=>{assert(ids[id],"No node "+id);return ids[id]};
assert.equal(doc.querySelectorAll("[data-play-tab]").length,3);
assert.equal(doc.querySelectorAll(".switch-dot").length,20);
// Task-switching game: automatically choose correct arrow for the displayed rule.
by("lab").hidden=false;by("switch-start").click();
assert.equal(by("switch-progress").textContent,"1 / 20");
for(let i=0;i<20;i++){answerSwitch();flush()}
assert.equal(by("switch-phase").textContent,"COMPLETE");
assert(doc.querySelectorAll(".switch-dot").every(x=>x.classes.has("is-correct")));
assert.equal(by("switch-results").hidden,false);
assert(descendants(by("switch-results")).some(x=>x.className==="play-chart"));
// Controllable timers catch navigation races that an immediate setTimeout mock misses.
by("switch-start").click();
visibility(true);environment.time+=60000;
const trialBefore=by("switch-progress").textContent;
by("switch-left").click();assert.equal(by("switch-progress").textContent,trialBefore);
visibility(false);answerSwitch();
// Leave during the feedback delay. The next trial must not start timing hidden.
by("lab").hidden=true;flush();environment.time+=60000;by("lab").hidden=false;
assert.equal(by("switch-progress").textContent,"2 / 20");
// Keyboard tab navigation must not bubble into an answer on the newly active tab.
by("tab-switch").focus();key("ArrowRight");assert.equal(by("play-recovery").hidden,false);
key("ArrowLeft");assert.equal(by("play-switch").hidden,false);
assert.equal(by("switch-progress").textContent,"2 / 20");assert.equal(timers.length,0);
by("switch-left").focus();key("ArrowRight",doc.activeElement,{repeat:true});assert.equal(timers.length,0);
key("ArrowRight",doc.activeElement,{defaultPrevented:true});assert.equal(timers.length,0);
answerSwitch();flush();
for(let i=2;i<20;i++){answerSwitch();flush()}
assert(descendants(by("switch-results")).some(x=>x.textContent==="2 interrupted response(s) excluded from timing."));
const timings=descendants(by("switch-results")).filter(x=>x.tagName==="STRONG").map(x=>x.textContent);
assert.deepEqual(timings,["135 ms","135 ms"],"Hidden time must never inflate medians");
assert.equal(doc.activeElement,by("switch-results"));
// Reset during feedback cancels pending work, including stale callbacks after replay.
by("switch-start").click();answerSwitch();
const stale=timers[0].fn;
by("play-reset").click();assert.equal(timers.length,0);assert.equal(by("switch-progress").textContent,"0 / 20");
by("tab-assist").click();stale();assert.equal(by("switch-progress").textContent,"0 / 20");
assert.equal(doc.activeElement,by("play-reset"));
by("tab-switch").click();by("switch-start").click();stale();assert.equal(by("switch-progress").textContent,"1 / 20");
by("play-reset").click();
// Untimed practice uses explicit progression, records no snapshot and cannot leak trials.
by("switch-practice").click();assert.equal(by("switch-progress").textContent,"1 / 4");
assert.equal(doc.activeElement,by("switch-left"));assert.match(by("switch-announcement").textContent,/Turn 1 of 4/);
for(let i=0;i<4;i++){
 answerSwitch();assert.equal(timers.length,0);assert.equal(doc.activeElement,by("switch-next"));
 assert.equal(key("Enter",doc.activeElement,{repeat:true}).defaultPrevented,true);
 const before=by("switch-progress").textContent;answerSwitch();assert.equal(by("switch-progress").textContent,before);
 by("switch-next").click();
}
assert(descendants(by("switch-results")).some(x=>x.textContent==="PRACTICE COMPLETE"));
assert(!descendants(by("switch-results")).some(x=>x.className==="play-chart"));
by("switch-timing").value="untimed";by("switch-start").click();
assert.equal(by("switch-progress").textContent,"1 / 20");
for(let i=0;i<20;i++){answerSwitch();assert.equal(timers.length,0);by("switch-next").click()}
assert(descendants(by("switch-results")).some(x=>x.textContent.startsWith("No response times were recorded.")));
assert.deepEqual(descendants(by("switch-results")).filter(x=>x.tagName==="STRONG").map(x=>x.textContent),["8 / 8 correct","12 / 12 correct"]);
// Home/End navigate tabs, never submit. Arrow shortcuts are scoped to answers.
by("tab-switch").focus();key("End");assert.equal(doc.activeElement,by("tab-assist"));key("Home");assert.equal(doc.activeElement,by("tab-switch"));
by("switch-timing").value="timed";by("switch-start").click();by("play-reset").focus();key("ArrowLeft");assert.equal(timers.length,0);
by("play-reset").click();
// All four return tasks, both modes; replay must stop on the new readable preview.
by("tab-recovery").click();
const stories=new Set();
for(let i=0;i<8;i++){
 const mode=i%2===0?"cue":"none";
 if(i){by("recovery-start").click();assert.match(by("recovery-progress").textContent,/STAGE 1 \/ 3/);assert.equal(by("recovery-start").hidden,false);assert.equal(by("recovery-interaction").children.length,0)}
 doc.querySelectorAll("[data-recovery-mode]").find(x=>x.dataset.recoveryMode===mode).click();
 const preview=by("recovery-description").textContent;stories.add(preview);
 by("recovery-start").click();
 for(const correctIndex of [2,1,2,1]){
  const choices=descendants(by("recovery-interaction")).filter(x=>x.className==="recovery-option");
  assert.equal(choices.length,3);choices[correctIndex].click();
 }
 const hasCue=descendants(by("recovery-interaction")).some(x=>x.className==="recovery-cue");
 assert.equal(hasCue,mode==="cue");
 assert.equal(by("recovery-headline").getAttribute("aria-describedby").includes("recovery-checkpoint"),hasCue);
 const options=descendants(by("recovery-interaction")).filter(x=>x.classes.has("recovery-option"));
 assert.equal(options.length,3);
 if(i===0){by("lab").hidden=true;environment.time+=60000;by("lab").hidden=false}
 if(i===1){visibility(true);environment.time+=60000;visibility(false)}
 if(i===2){by("tab-assist").click();environment.time+=60000;by("tab-recovery").click()}
 options.find(x=>preview.includes(x.textContent)).click();
 assert.equal(by("recovery-progress").textContent,"DONE");
 if(i<3)assert(descendants(by("recovery-interaction")).some(x=>x.textContent.startsWith("Timing omitted:")));
 assert.equal(doc.activeElement,by("recovery-headline"));
}
assert.equal(stories.size,4);
assert.equal(descendants(by("recovery-history")).filter(x=>x.classes.has("recovery-trial")).length,4);
// Guided comparisons cover every starting-condition/material combination.
// Paired results must never be pooled into exploratory single-round history.
const historyBefore=descendants(by("recovery-history")).map(x=>x.textContent).join("|");
const positionSet=new Set(),pairSet=new Set();
for(const [caseIndex,seeds] of [[.1,.1],[.1,.9],[.9,.1],[.9,.9]].entries()){
 randomQueue.push(...seeds);by("recovery-compare").click();
 assert.equal(randomQueue.length,0);assert.equal(doc.activeElement,by("recovery-headline"));
 assert.equal(by("recovery-compare").disabled,true);
 assert(doc.querySelectorAll("[data-recovery-mode]").every(x=>x.disabled));
 const firstMode=seeds[0]<.5?"With checkpoint":"Without checkpoint",firstVariant=seeds[1]<.5?"A":"B";
 assert(by("recovery-round-context").textContent.includes(firstMode));
 assert(by("recovery-round-context").textContent.includes("TASK "+firstVariant));
 pairSet.add(by("recovery-comparison-plan").textContent.split(" · ")[0]);
 const previews=[];
 for(let step=0;step<2;step++){
  const preview=by("recovery-description").textContent;previews.push(preview);
  by("recovery-start").click();
  for(const [j,correctIndex] of [2,1,2,1].entries()){
   if(j===3)randomQueue.push(...[[0,0],[.99,.99],[.5,.99]][(caseIndex+step)%3]);
   descendants(by("recovery-interaction")).filter(x=>x.className==="recovery-option")[correctIndex].click();
  }
  const options=descendants(by("recovery-interaction")).filter(x=>x.classes.has("recovery-option"));
  assert.equal(new Set(options.map(x=>x.textContent)).size,3);
  const correctIndex=options.findIndex(x=>preview.includes(x.textContent));positionSet.add(correctIndex);assert(correctIndex>=0);
  const hasCue=descendants(by("recovery-interaction")).some(x=>x.className==="recovery-cue");
  assert.equal(hasCue,step===0?seeds[0]<.5:seeds[0]>=.5);
  assert.equal(by("recovery-headline").getAttribute("aria-describedby").includes("recovery-checkpoint"),hasCue);
  if(hasCue)assert(descendants(by("recovery-interaction")).some(x=>x.id==="recovery-checkpoint"&&x.textContent.includes(options[correctIndex].textContent)));
  if(caseIndex===0&&step===0){by("tab-assist").click();environment.time+=60000;by("tab-recovery").click()}
  options[step===0?correctIndex:(correctIndex+1)%3].click();
  assert(!by("recovery-headline").getAttribute("aria-describedby").includes("recovery-checkpoint"));
  assert(by("recovery-description").textContent.includes("What helped you decide"));
  assert.equal(descendants(by("recovery-history")).map(x=>x.textContent).join("|"),historyBefore);
  if(step===0){
   assert.equal(by("recovery-comparison-results").hidden,true);
   assert.match(by("recovery-start").textContent,/Preview second/);by("recovery-start").click();
   assert.match(by("recovery-progress").textContent,/ROUND 2 \/ 2.*STAGE 1 \/ 3/);
   assert.equal(by("recovery-interaction").children.length,0,"Second task must wait for explicit start");
  }
 }
 assert.notEqual(previews[0],previews[1]);
 const result=by("recovery-comparison-results");assert.equal(result.hidden,false);assert.equal(doc.activeElement,result);
 const rows=descendants(result).filter(x=>x.classes.has("recovery-comparison-result"));assert.equal(rows.length,2);
 assert(rows[0].children[0].textContent.includes(firstMode));
 assert.match(rows[0].children[1].textContent,/Intended next step/);assert.match(rows[1].children[1].textContent,/Different choice/);
 if(caseIndex===0)assert.match(rows[0].children[1].textContent,/timing omitted/);
 assert(descendants(result).some(x=>x.textContent.startsWith("Two responses do not estimate a checkpoint effect.")));
 by("recovery-exit-comparison").click();
 assert.equal(result.hidden,true);assert.equal(result.children.length,0);
 assert.equal(by("recovery-compare").disabled,false);
 assert(doc.querySelectorAll("[data-recovery-mode]").every(x=>!x.disabled));
 assert.equal(doc.querySelectorAll("[data-recovery-mode]").find(x=>x.dataset.recoveryMode==="none").getAttribute("aria-pressed"),"true");
}
assert.equal(pairSet.size,2);assert.deepEqual([...positionSet].sort(),[0,1,2]);
// Leaving and resetting mid-comparison must return to a readable single round.
by("recovery-compare").click();by("recovery-start").click();
const oldOption=descendants(by("recovery-interaction")).find(x=>x.className==="recovery-option");
by("recovery-exit-comparison").click();oldOption.click();assert.match(by("recovery-progress").textContent,/STAGE 1 \/ 3/);
assert.equal(by("recovery-interaction").children.length,0);
by("recovery-compare").click();by("recovery-start").click();by("play-reset").click();
assert.equal(by("recovery-comparison-plan").hidden,true);assert.equal(by("recovery-comparison-results").hidden,true);
assert.equal(by("recovery-compare").disabled,false);assert.equal(by("recovery-history").children.length,0);
assert.equal(doc.activeElement,by("play-reset"));
// All four fictional scenarios are reachable under all three help settings.
by("tab-assist").click();
for(const mode of ["reflect","hint","answer"]){
 doc.querySelectorAll("[data-assist-mode]").find(x=>x.dataset.assistMode===mode).click();
 for(let i=0;i<4;i++){
  assert.equal(by("assist-counter").textContent,`SCENARIO ${i+1} / 4`);
  const options=descendants(by("assist-choices")).filter(x=>x.classes.has("assist-option"));
  assert.equal(options.length,3);options[[1,0,1,2][i]].click();
  assert.equal(by("assist-feedback").hidden,false);
  assert.equal(doc.activeElement,by("assist-feedback"));
  assert.match(by("assist-feedback").children[0].textContent,/Supported conclusion/);
  assert.equal(by("assist-next").textContent,i===3?"Replay the first scenario ↗":"Try another scenario ↗");
  by("assist-next").click();assert.equal(doc.activeElement,by("assist-prompt"));
 }
}
// Reset clears all activities while retaining explicit mode choices and focus.
by("play-reset").click();assert.equal(by("recovery-history").children.length,0);
assert.equal(by("recovery-interaction").children.length,0);assert.equal(by("assist-counter").textContent,"SCENARIO 1 / 4");
assert.equal(by("switch-results").hidden,true);assert.equal(by("switch-timing").value,"timed");
assert.equal(doc.activeElement,by("play-reset"));assert.match(by("play-session-status").textContent,/results are cleared/);
assert(html.includes('datetime="2026-11-06"'));
assert(html.includes("Fictional scenarios and scripted assistance"));
console.log("Attention Playground regressions passed: paired comparisons, randomized condition/material orders and answer positions, separate histories, interruption/cancel/reset, reset/stale callback isolation, untimed snapshots, separate practice, task announcements, focus transitions, switching timers, visibility/route pauses, keyboard bubbling/repeats, readable replay, 4 recovery tasks in both modes, and 4 scenarios at all 3 assistance levels.");


