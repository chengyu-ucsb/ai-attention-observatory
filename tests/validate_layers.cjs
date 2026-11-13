/* Shared reading cards must preserve live content, focus, and modal timing. */
"use strict";
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),assert=require("node:assert/strict");
const source=fs.readFileSync(path.join(__dirname,"../app.js"),"utf8");
const queued=[];
let doc;
class Element{
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this.hidden=false;this.open=false;this.style={};this.attributes={};this.listeners={};this.textContent="";this.className="";}
 get nextSibling(){if(!this.parentNode)return null;return this.parentNode.children[this.parentNode.children.indexOf(this)+1]||null;}
 get isConnected(){return this===doc.body||Boolean(this.parentNode?.isConnected);}
 append(...nodes){for(const node of nodes)this.insertBefore(node,null);}
 insertBefore(node,next){
  if(node.parentNode){const old=node.parentNode;old.children.splice(old.children.indexOf(node),1);}
  const index=next?this.children.indexOf(next):this.children.length;
  assert(index>=0,"Insertion anchor must belong to its parent");this.children.splice(index,0,node);node.parentNode=this;
 }
 replaceChildren(...nodes){for(const child of this.children)child.parentNode=null;this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attributes[key]=String(value);}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
 dispatchEvent(event){event.target??=this;for(const fn of this.listeners[event.type]||[])fn(event);return !event.defaultPrevented;}
 querySelector(selector){return walk(this).find(node=>selector[0]==="#"?node.id===selector.slice(1):selector[0]==="."?node.className.split(" ").includes(selector.slice(1)):false)||null;}
 focus(){assert(this.isConnected,"Focus target must remain connected");let node=this;while(node){assert(!node.hidden,"Focus cannot return to a hidden card");node=node.parentNode;}doc.activeElement=this;}
 showModal(){this.open=true;}
 close(){if(!this.open)return;this.open=false;queued.push(()=>this.dispatchEvent({type:"close"}));}
 getBoundingClientRect(){return {left:10,top:10,right:90,bottom:90};}
}
const walk=node=>[node,...node.children.flatMap(walk)];
doc={body:new Element("body"),activeElement:null,events:[],createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelector(selector){return this.body.querySelector(selector);},querySelectorAll(){return [];},dispatchEvent(event){this.events.push(event);}};
class Event{constructor(type,init={}){this.type=type;Object.assign(this,init);this.defaultPrevented=false;}preventDefault(){this.defaultPrevented=true;}}
const context=vm.createContext({document:doc,CustomEvent:Event,console});
vm.runInContext(source.slice(0,source.indexOf("function layerDisclosure("))+"\nthis.api={openLayer,closeLayer,closeAllLayers,layerButton};",context);
const {openLayer,closeLayer,closeAllLayers,layerButton}=context.api;
const select=s=>doc.querySelector(s),flush=()=>{while(queued.length)queued.shift()();};
const text=doc.createElement("p");text.textContent="Full source text and its exact numbers: 12, 34, 56.";
const innerContent=doc.createElement("section");innerContent.append(text);
const inner=layerButton("Inspect evidence","Evidence",innerContent);
const outerContent=doc.createElement("section"),before=doc.createElement("p"),after=doc.createElement("p");
outerContent.append(before,inner,after);
const outer=layerButton("Open source shelf","Source shelf",outerContent),outerTrigger=outer.children[0],innerTrigger=inner.children[0];
doc.body.append(outer);doc.body.style.overflow="scroll";outerTrigger.focus();

outerTrigger.onclick();
const dialog=select("#reading-layer");
assert(dialog.open);assert.equal(doc.body.style.overflow,"hidden");
assert.equal(select("#reading-layer-body").children[0],outerContent);
assert.equal(doc.activeElement,dialog.querySelector(".layer-close"));
innerTrigger.onclick();
assert(dialog.open,"Opening a child card must retain the same open modal");
assert.equal(select("#reading-layer-title").textContent,"Evidence");
assert.equal(select("#reading-layer-body").children[0],innerContent);
assert.equal(text.textContent,"Full source text and its exact numbers: 12, 34, 56.");
assert.equal(doc.events.at(-1).detail.depth,2);

const firstEscape=new Event("cancel");dialog.dispatchEvent(firstEscape);
assert(firstEscape.defaultPrevented,"Native Escape must pop one card before dismissing the modal");
assert(dialog.open);assert.equal(select("#reading-layer-title").textContent,"Source shelf");
assert.equal(doc.activeElement,innerTrigger,"Closing a child returns focus to its opener inside the parent");
assert.equal(innerContent.parentNode,inner);assert(innerContent.hidden);
assert.equal(doc.body.style.overflow,"hidden","Parent card still locks background scrolling");
assert.equal(doc.events.at(-1).detail.depth,1);

dialog.dispatchEvent(new Event("cancel"));
assert(!dialog.open);assert.equal(doc.activeElement,outerTrigger);
assert.equal(outerContent.parentNode,outer);assert(outerContent.hidden);
assert.equal(doc.body.style.overflow,"scroll","Final close restores the original overflow value");
assert.equal(doc.events.at(-1).detail.open,false);

// A native close event is asynchronous. Reopening before it arrives must not
// restore/remove the new card, even if the same content is reopened.
outerTrigger.onclick();flush();
assert(dialog.open);assert.equal(select("#reading-layer-body").children[0],outerContent);
assert.equal(doc.body.style.overflow,"hidden");
innerTrigger.onclick();
closeAllLayers(false);flush();
assert(!dialog.open);assert.equal(outerContent.parentNode,outer);assert.equal(innerContent.parentNode,inner);
assert(outerContent.hidden&&innerContent.hidden);assert.equal(doc.body.style.overflow,"scroll");
assert.deepEqual(outerContent.children,[before,inner,after],"Closing every layer restores original sibling order");
assert.equal(doc.events.at(-1).detail.depth,0);

// Programmatic/native closure outside our buttons must still release content
// and the scroll lock, including when there is a suspended parent card.
outerTrigger.onclick();innerTrigger.onclick();dialog.close();flush();
assert.equal(outerContent.parentNode,outer);assert.equal(innerContent.parentNode,inner);
assert.equal(doc.body.style.overflow,"scroll");assert.equal(doc.activeElement,outerTrigger);

// A repeated request for an already open ancestor unwinds safely instead of
// pushing a cyclic frame whose original parent is the dialog itself.
outerTrigger.onclick();innerTrigger.onclick();openLayer("Source shelf",outerContent,outerTrigger);
assert(dialog.open);assert.equal(select("#reading-layer-body").children[0],outerContent);
assert.equal(doc.events.at(-1).detail.depth,1);closeLayer();flush();
assert.equal(outerContent.parentNode,outer);assert.equal(innerContent.parentNode,inner);
assert.equal(walk(doc.body).filter(node=>node===text).length,1,"Live source content must never be cloned");
assert(source.includes('if(event?.type==="hashchange")closeAllLayers(false);'),"Route changes must dismiss all layers");
console.log("Shared reading layers passed: nested Escape/close, live DOM, focus, scroll lock, queued-close races, route cleanup, and activity visibility events.");
