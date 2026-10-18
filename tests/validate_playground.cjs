/* Zero-dependency smoke test for the interactive Attention Playground.
   Runs in GitHub Actions without downloading a browser. */
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.resolve(__dirname,"..");
const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
const js=fs.readFileSync(path.join(root,"lab-play.js"),"utf8");
const publish=fs.readFileSync(path.join(root,".github/workflows/publish.yml"),"utf8");
for(const p of ["lab-play.js","lab-play.css"])assert(html.includes(p),"Missing linked asset "+p);
for(const p of ["lab-play.js","lab-play.css"])assert(publish.includes(p),"File not included in GitHub Pages publish workflow: "+p);
for(const id of ["play-switch","play-recovery","play-assist","switch-start","switch-left","switch-right","switch-results","recovery-start","recovery-interaction","assist-choices","assist-feedback"]){
 assert(html.includes('id="'+id+'"'),"Missing expected Lab DOM id: "+id);
}
const usedIds=[...js.matchAll(/\$\("#([^"]+)"\)/g)].map(x=>x[1]);
for(const id of new Set(usedIds))assert(html.includes('id="'+id+'"'),"Lab script selects nonexistent id "+id);
const all=[],ids={};
class FakeElement{
 constructor(tag="div",cls="",id=null){
  this.tagName=tag.toUpperCase();this._className=cls;this.classes=new Set(cls.split(/\s+/).filter(Boolean));
  this.dataset={};this.children=[];this.handlers={};this.style={};this.hidden=false;this.disabled=false;this.tabIndex=0;this.value="";this.textContent="";this.attributes={};
  this.classList={add:(...n)=>n.forEach(x=>this.classes.add(x)),remove:(...n)=>n.forEach(x=>this.classes.delete(x)),toggle:(n,v)=>{if(v===undefined)v=!this.classes.has(n);v?this.classes.add(n):this.classes.delete(n);return v},contains:n=>this.classes.has(n)};
  if(id){this.id=id;ids[id]=this}all.push(this);
 }
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
const environment={document:doc,performance:{now:()=>{environment.time+=135;return environment.time}},time:0,console,setTimeout:fn=>{fn();return 1},setInterval:()=>1,clearInterval:()=>{}};
vm.runInNewContext(js,environment,{timeout:4000,filename:"lab-play.js"});
const by=id=>{assert(ids[id],"No node "+id);return ids[id]};
assert.equal(doc.querySelectorAll("[data-play-tab]").length,3);
assert.equal(doc.querySelectorAll(".switch-dot").length,20);
// Task-switching game: automatically choose correct arrow for the displayed rule.
by("lab").hidden=false;by("switch-start").click();
assert.equal(by("switch-progress").textContent,"1 / 20");
for(let i=0;i<20;i++){
 const rule=by("switch-cue").textContent,num=Number(by("switch-number").textContent);
 const left=rule.startsWith("ODD")?num%2===1:num<5;
 (left?by("switch-left"):by("switch-right")).click();
}
assert.equal(by("switch-phase").textContent,"COMPLETE");
assert.equal(by("switch-results").hidden,false);
assert(descendants(by("switch-results")).some(x=>x.className==="play-chart"));
// Interruption recovery trial with checkpoint and without.
by("tab-recovery").click();
for(const mode of ["cue","none"]){
 const modeEl=doc.querySelectorAll("[data-recovery-mode]").find(x=>x.dataset.recoveryMode===mode);
 modeEl.click();by("recovery-start").click();
 for(const correctIndex of [2,1,2,1]){
  const choices=descendants(by("recovery-interaction")).filter(x=>x.className==="recovery-option");
  assert.equal(choices.length,3);choices[correctIndex].click();
 }
 if(mode==="cue")assert(descendants(by("recovery-interaction")).some(x=>x.className==="recovery-cue"));
 const options=descendants(by("recovery-interaction")).filter(x=>x.classes.has("recovery-option"));
 assert.equal(options.length,3);
 const matching=options.find(x=>x.textContent.includes(mode==="cue"?"Compare the two studies":"Compare the two studies"));
 matching.click();
 assert.equal(by("recovery-progress").textContent,"DONE");
}
assert(descendants(by("recovery-history")).some(x=>x.classes.has("recovery-trial-list")));
// Assisted reasoning: answer in reflective mode, then change assistance level.
by("tab-assist").click();
let options=descendants(by("assist-choices")).filter(x=>x.classes.has("assist-option"));
assert.equal(options.length,3);options[1].click();
assert.equal(by("assist-feedback").hidden,false);
by("assist-next").click();
options=descendants(by("assist-choices")).filter(x=>x.classes.has("assist-option"));
options[0].click();
const hint=doc.querySelectorAll("[data-assist-mode]").find(x=>x.dataset.assistMode==="hint");
hint.click();assert(by("assist-reply").children.length>0);
console.log("Attention Playground smoke test passed: tabs, 20 switching trials, two recovery modes, and both assistance scenarios.");
