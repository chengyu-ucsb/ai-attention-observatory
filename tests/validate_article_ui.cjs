/* Regression tests for concise research headlines and DOM-element rendering. */
"use strict";
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path"),assert=require("node:assert/strict");
const ROOT=path.resolve(__dirname,"..");
const read=p=>fs.readFileSync(path.join(ROOT,p),"utf8");
const app=read("app.js"),html=read("index.html"),styles=read("styles.css");
assert(!app.includes("discovery provider warning(s)"),"Raw provider warnings must never appear on homepage");
assert(!html.includes('id="research-warning"'),"Internal warning banner leaked into public HTML");
assert(!app.includes('make("div","paper-identity",add('),"Node passed as text into make()");
for(const id of ["paper-content","feature-grid","library-results"])assert(html.includes('id="'+id+'"'));
let created=[];
class Element{
 constructor(tag){this.tag=tag;this.textContent="";this.className="";this.children=[];this.style={};this.hidden=false;this.open=false;this.attributes={};created.push(this)}
 append(...els){for(const e of els){assert(e instanceof Element,"Non-element child");this.children.push(e)}}
 replaceChildren(...els){this.children=[];this.textContent="";this.append(...els)}
 setAttribute(k,v){this.attributes[k]=v}
}
const paperContainer=new Element("div");
const doc={createElement:t=>new Element(t),querySelector:q=>q==="#paper-content"?paperContainer:null};
const prefix=app.slice(0,app.indexOf('$$("[data-route]").forEach('));
assert(prefix.length>10000,"Unexpected app initialization structure");
const ctx=vm.createContext({document:doc,URL,console,window:{scrollTo(){}}});
vm.runInContext(prefix+"\nconst TEST={showPaper,make,shortIdea,ideaInfo,S};",ctx);
function nodes(root){return [root,...root.children.flatMap(nodes)]}
function nodeClass(root,cls){return nodes(root).find(n=>n.className.split(" ").includes(cls))}
function texts(root){return nodes(root).map(n=>n.textContent).filter(Boolean)}
const db=JSON.parse(read("data/public-library.json"));
assert(db.length>50,"Expected public article data for regression testing");
let verified=0;
for(const r of db){
 ctx.selected=r;
 created=[];
 vm.runInContext("TEST.showPaper(selected)",ctx);
 const allText=texts(paperContainer).join(" | ");
 assert(!allText.includes("[object HTMLDivElement]"),"Object-to-string rendering for "+r.title);
 assert(!allText.includes("[object Object]"),"Object-to-string rendering for "+r.title);
 const insight=nodeClass(paperContainer,"paper-insight");
 assert(insight&&insight.textContent.length<=148,"Oversized article headline for "+r.title);
 const source=nodeClass(paperContainer,"paper-source-title");
 assert(source&&source.textContent===r.title,"Original source title omitted");
 const details=nodeClass(paperContainer,"paper-detail-excerpts");
 assert(details&&details.open===true,"Substantive source notes should be initially expanded");
 verified++;
}
const good=db.find(x=>x.doi==="10.58304/ijts.260930");
if(good){
 ctx.selected=good;
 const headline=vm.runInContext("TEST.shortIdea(selected,96)",ctx);
 assert.equal(headline,"AI literacy linked to critical thinking through problem-solving and AI reliance");
 assert(headline.length<96);
}
assert.throws(()=>vm.runInContext('TEST.make("div","x",document.createElement("span"))',ctx),/accepts text only/);
console.log("Article UI passed:",verified,"reading pages render without object strings; concise headline/source-title structure intact.");
