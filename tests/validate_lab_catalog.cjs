/* Real catalog, scenario and timing logic; no browser or network dependency. */
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.resolve(__dirname,"..");
const source=fs.readFileSync(path.join(root,"lab-play.js"),"utf8").split("/* Versioned Lab collection:")[1];
assert(source,"Versioned Lab implementation exists");
const code="/* Versioned Lab collection:"+source;
const doc={listeners:{},activeElement:null};
class Element{
 constructor(tag){this.tagName=tag.toUpperCase();this.ownerDocument=doc;this.children=[];this.parentNode=null;this.handlers={};this.dataset={};this.attributes={};this.style={};this.hidden=false;this._text="";this._classes=new Set();this.value="";this.checked=false;this.classList={toggle:(name,on)=>{if(on===undefined)on=!this._classes.has(name);on?this._classes.add(name):this._classes.delete(name)},contains:name=>this._classes.has(name)};}
 set className(value){this._classes=new Set(value.split(/\s+/).filter(Boolean))}get className(){return [...this._classes].join(" ")}
 set textContent(value){this._text=String(value);this.children.forEach(child=>child.parentNode=null);this.children=[]}get textContent(){return this._text+this.children.map(child=>child.textContent).join(" ")}
 append(...children){children.forEach(child=>{assert(child instanceof Element);child.parentNode=this;this.children.push(child)})}
 replaceChildren(...children){this.children.forEach(child=>child.parentNode=null);this.children=[];this._text="";this.append(...children)}
 setAttribute(key,value){this.attributes[key]=String(value)}getAttribute(key){return this.attributes[key]??null}
 addEventListener(type,fn){(this.handlers[type]??=[]).push(fn)}
 emit(type,extra={}){for(const fn of this.handlers[type]||[])fn({target:this,preventDefault(){},...extra})}
 click(){if(!this.disabled)this.emit("click")}focus(){doc.activeElement=this}
 get isConnected(){let node=this;while(node){if(node===doc.body)return true;node=node.parentNode}return false}
 remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(child=>child!==this);this.parentNode=null}}
 showModal(){this.open=true}close(){this.open=false;this.emit("close")}
}
const flatten=node=>[node,...node.children.flatMap(flatten)];
doc.body=new Element("body");doc.createElement=tag=>new Element(tag);
doc.querySelector=selector=>flatten(doc.body).find(node=>selector.startsWith("#")?node.id===selector.slice(1):selector.startsWith(".")?node.classList.contains(selector.slice(1)):node.tagName===selector.toUpperCase())||null;
doc.addEventListener=(type,fn)=>(doc.listeners[type]??=[]).push(fn);doc.dispatchEvent=event=>{for(const fn of doc.listeners[event.type]||[])fn(event)};
const frames=[];
const view={location:{hash:"#lab"},listeners:{},history:{replaceState(_state,_unused,hash){view.location.hash=hash}},requestAnimationFrame(fn){frames.push(fn)},addEventListener(type,fn){(this.listeners[type]??=[]).push(fn)}};doc.defaultView=view;
const route=hash=>{view.location.hash=hash;(view.listeners.hashchange||[]).forEach(fn=>fn())};
const fixture=(id,cls="")=>{const node=doc.createElement("div");node.id=id;node.className=cls;doc.body.append(node);return node};
fixture("lab-catalog");fixture("lab-workbench");fixture("lab-classic-tabs","play-tabs");fixture("lab-session-controls","play-session-controls");["switch","recovery","assist"].forEach(id=>fixture("play-"+id));fixture("play-reset");
let classicActivations=0,visibilityNotices=0,layerNotices=0;
doc.addEventListener("observatory:lab-activate",event=>{classicActivations++;["switch","recovery","assist"].forEach(id=>doc.querySelector("#play-"+id).hidden=id!==event.detail);doc.dispatchEvent({type:"observatory:lab-classic",detail:event.detail})});
doc.addEventListener("observatory:lab-visibility",()=>visibilityNotices++);
doc.addEventListener("observatory-layer-change",()=>layerNotices++);
const context={document:doc,module:{exports:{}},CustomEvent:class{constructor(type,options={}){this.type=type;this.detail=options.detail}},URLSearchParams,console};
vm.runInNewContext(code,context,{timeout:5000});
const {CATALOG,CASES,MESSAGES,notificationPlan}=context.module.exports;
const q=id=>{const node=doc.querySelector("#"+id);assert(node,"Expected "+id);return node};
const findData=(name,value)=>flatten(doc.body).find(node=>node.dataset[name]===value);
const select=(id,value)=>{q(id).value=value;q(id).emit("change")};
assert.equal(CATALOG.length,5);assert.equal(new Set(CATALOG.map(entry=>entry.id)).size,5);
assert.deepEqual(Array.from(CATALOG.filter(entry=>entry.status==="classic"),entry=>entry.id),["switch","recovery","assist"]);
for(const entry of CATALOG){assert(entry.version&&entry.released&&entry.evidenceBasis&&entry.duration);assert.match(entry.id,/^[a-z-]+$/)}
assert.equal(q("lab-workbench").hidden,true,"Catalog must not preload a long activity");
assert.equal(q("lab-classic-tabs").hidden,true);assert.equal(q("lab-session-controls").hidden,true);
assert.equal(flatten(q("lab-catalog")).filter(node=>node.dataset.labOpen).length,2,"New is the initial collection");
select("lab-collection-filter","all");assert.equal(flatten(q("lab-catalog")).filter(node=>node.dataset.labOpen).length,5);
findData("labOpen","switch").click();assert.equal(view.location.hash,"#lab?experiment=switch");assert(q("lab-workbench").hidden,"New controls cannot appear before hash navigation settles");assert.equal(classicActivations,0);
doc.activeElement=doc.body;route(view.location.hash);assert.equal(q("play-switch").hidden,false);assert.equal(q("play-recovery").hidden,true);assert.equal(classicActivations,1);assert.equal(frames.length,0);assert.equal(doc.activeElement,q("lab-workbench-title"),"Destination focus is established during the completed hash route");
assert.equal(q("lab-catalog").hidden,true);assert.equal(q("lab-classic-tabs").hidden,false);
q("lab-back-to-catalog").click();assert.equal(q("lab-catalog").hidden,true,"Collection controls also wait for their route");
doc.activeElement=doc.body;route("#lab");assert.equal(q("play-switch").hidden,true);assert.equal(q("lab-catalog").hidden,false);assert.equal(frames.length,0);assert.equal(doc.activeElement,q("lab-collection-filter"),"Returning to the collection restores its filter during navigation");
assert.equal((view.listeners.popstate||[]).length,0,"Hash navigation must not publish controls early through a duplicate popstate handler");
route("#lab?experiment=evidence-detective");assert.equal(q("lab-workbench-title").textContent,"Evidence Detective");assert.equal(q("lab-classic-tabs").hidden,true);
for(let index=0;index<CASES.length;index++){
 select("lab-case-picker",String(index));
 for(let cardIndex=0;cardIndex<CASES[index].cards.length;cardIndex++){
  const card=findData("evidenceCard",String(cardIndex)),evidence=CASES[index].cards[cardIndex];
  assert.equal(card.getAttribute("aria-pressed"),"false");
  assert(!card.getAttribute("aria-label").includes(evidence.detail),"Unturned cards must not expose hidden evidence");
  card.click();assert.equal(card.getAttribute("aria-pressed"),"true");assert(card.textContent.includes(evidence.detail));
  assert(card.getAttribute("aria-label").includes(evidence.detail),"Revealed evidence must be available in the button's accessible name");
  card.click();assert.equal(card.getAttribute("aria-pressed"),"false");
  assert(!card.getAttribute("aria-label").includes(evidence.detail),"Turning back must restore the front's accessible name");
 }
 findData("labVerdict",CASES[index].verdict).click();assert(q("lab-detective-feedback").textContent.includes(CASES[index].explanation));assert.equal(doc.activeElement,q("lab-detective-feedback"));
 assert(q("lab-detective-feedback").textContent.includes("You matched the claim to the evidence"));
 const wrong=["supported","overreach","unanswered"].find(value=>value!==CASES[index].verdict);findData("labVerdict",wrong).click();assert(q("lab-detective-feedback").textContent.includes("Reconsider"));
}
q("lab-detective-reset").click();assert.equal(q("lab-case-picker").value,"0");assert.equal(doc.querySelector("#lab-detective-feedback"),null);assert.equal(doc.activeElement,q("lab-detective-reset"));
findData("labVerdict","overreach").click();q("lab-detective-next").click();assert.equal(q("lab-case-picker").value,"1");assert.equal(q("lab-detective-claim").textContent,CASES[1].claim);
route("#lab?experiment=notification-studio");assert.equal(q("lab-workbench-title").textContent,"Notification Studio");
assert.equal(MESSAGES.length,12);assert.equal(notificationPlan("immediate",false).alerts,12);assert.equal(notificationPlan("immediate",false).meanWait,0);
const batch=notificationPlan("batch",true);assert.equal(batch.alerts,5);assert.equal(batch.urgentWait,0);assert.equal(batch.meanWait,53/12);assert.equal(batch.longestGap,10);
const end=notificationPlan("end",false);assert.equal(end.alerts,1);assert.equal(end.urgentWait,22);assert.equal(end.longestGap,30);assert.equal(notificationPlan("end",true).alerts,3);
assert.throws(()=>notificationPlan("invented"));
for(const mode of ["immediate","batch","end"])for(const urgent of [true,false]){
 const plan=notificationPlan(mode,urgent);assert.equal(plan.deliveries.length,12);
 assert(plan.deliveries.every(message=>message.delivered>=message.at&&message.delivered<=30));
 assert.equal(plan.alerts,new Set(plan.deliveries.map(message=>message.delivered)).size);
}
select("lab-notification-policy","end");q("lab-urgent-bypass").checked=false;q("lab-urgent-bypass").emit("change");
assert(q("lab-notification-summary").textContent.includes("1 alert moment."));assert(q("lab-notification-summary").textContent.includes("22 minutes"));
q("lab-inspect-delivery").click();const modal=doc.querySelector(".lab-help-dialog");assert(modal.open);assert(modal.textContent.includes("Minute 30"));assert(modal.textContent.includes("Time-sensitive request"));
assert.equal(layerNotices,1,"Opening the activity dialog must pause any covered timing");
const modalFocus=doc.activeElement;route(view.location.hash);assert.equal(doc.querySelector(".lab-help-dialog"),modal,"A repeated route cannot close a newly opened dialog in the same workspace");assert.equal(doc.activeElement,modalFocus,"Settled navigation cannot steal focus from a delivery dialog");assert.equal(frames.length,0);
flatten(modal).find(node=>node.tagName==="BUTTON").click();assert.equal(doc.querySelector(".lab-help-dialog"),null);assert.equal(doc.activeElement,q("lab-inspect-delivery"));
assert.equal(layerNotices,2,"Closing the activity dialog must notify timing controllers");
q("lab-inspect-delivery").click();route("#home");assert.equal(doc.querySelector(".lab-help-dialog"),null,"Navigation cannot leave a Lab dialog over another page");route("#lab?experiment=notification-studio");
q("lab-notification-reset").click();assert.equal(q("lab-notification-policy").value,"batch");assert.equal(q("lab-urgent-bypass").checked,true);assert(q("lab-notification-summary").textContent.includes("5 alert moments"));
route("#lab");assert(q("lab-workbench").hidden);route("#lab?experiment=unknown");assert(q("lab-workbench").hidden,"Unknown links fall back to collection");
route("#lab?experiment=assist");assert.equal(q("play-assist").hidden,false);assert.equal(q("play-switch").hidden,true);assert(visibilityNotices>=7);
assert(!/fetch\s*\(|localStorage|sessionStorage|XMLHttpRequest|sendBeacon/.test(code),"Activities must stay local and session-only");
console.log("Lab catalog regressions passed: registry, preserved classics, landing, deep links, card flips, all evidence verdicts, feedback/reset/focus, simulation arithmetic, delivery modal and unknown-route fallback.");
