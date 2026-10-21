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
 addEventListener(_name,_callback){}
}
const paperContainer=new Element("div");
const doc={createElement:t=>new Element(t),querySelector:q=>q==="#paper-content"?paperContainer:null};
const prefix=app.slice(0,app.lastIndexOf('$("[data-route]").forEach('));
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
 assert(insight&&insight.textContent.length>18&&insight.textContent.length<=430,"Missing or unbounded reading summary for "+r.title);
 const snapshot=nodeClass(paperContainer,"paper-snapshot");
 assert(snapshot,"Missing processed reading snapshot for "+r.title);
 const studyCards=nodes(snapshot).filter(n=>n.className.split(" ").includes("snapshot-tile"));
 assert.equal(studyCards.length,3,"Expected separate design / result / limitation notes for "+r.title);
 const source=nodeClass(paperContainer,"paper-source-title");
 assert(source&&source.tag==="h3"&&source.textContent===r.title,"Original publication must remain available as evidence provenance");
 assert(insight.tag==="h1","The idea must be the primary reading-page heading");
 const header=nodeClass(paperContainer,"paper-reading-header");
 assert(header&&nodes(header).includes(insight),"Readers must see the idea before the evidence");
 assert(!nodes(header).includes(source),"Do not foreground bibliographic titles over the idea");
 const evidence=nodeClass(paperContainer,"paper-section-title");
 assert(evidence&&/evidence|supports|informs/i.test(evidence.textContent),"Supporting evidence must be explicitly signposted");
 const generic=nodes(paperContainer).filter(n=>n.className.split(" ").includes("concept-scene"));
 assert.equal(generic.length,0,"Generic concept diagrams were supposed to be removed");
 const notes=nodeClass(paperContainer,"reading-lead-note");
 assert(notes&&/source|article|index|passages|synopsis/i.test(notes.textContent),"Missing provenance warning for "+r.title);
 const details=nodeClass(paperContainer,"paper-detail-excerpts");
 const editorial=r.kind==="nonacademic";
 const hasNotes=editorial?!!(r.editorial_notes?.argument||r.editorial_notes?.design_relevance||r.editorial_notes?.caveat):!!(r.reading?.methods||r.reading?.findings||r.reading?.interpretation||r.reading?.limitations);
 if(hasNotes)assert(details&&details.open===false,"Raw extracted passages must stay collapsed behind processed notes for "+r.title);
 else assert(!details,"Empty structured source notes must not display a pointless panel for "+r.title);
 verified++;
}
const literacy=db.find(x=>x.doi==="10.58304/ijts.260930");
if(literacy){
 ctx.selected=literacy;
 vm.runInContext("TEST.showPaper(selected)",ctx);
 const textAll=texts(paperContainer).join(" | ");
 assert(textAll.includes("450 non-English-major undergraduates"),"Specific sample details missing from accessible summary");
 assert(textAll.includes("20 selected participants"),"Mixed-methods follow-up sample missing");
 assert(nodeClass(paperContainer,"article-data-visual"),"Study-specific research-design visual not rendered");
 assert(!nodeClass(paperContainer,"concept-scene"),"Generic concept illustration should be absent");
}
const digital=db.find(x=>x.doi==="10.3389/fpsyg.2026.1930030");
if(digital){
 ctx.selected=digital;
 vm.runInContext("TEST.showPaper(selected)",ctx);
 assert.equal(nodes(paperContainer).filter(n=>n.className.split(" ").includes("study-coefficient-row")).length,4,
  "Expected four explicitly sourced LASSO coefficients");
 assert(texts(paperContainer).join(" | ").includes("not generative AI"),"Adjacent research must be qualified");
}

const good=db.find(x=>x.doi==="10.58304/ijts.260930");
if(good){
 ctx.selected=good;
 const headline=vm.runInContext("TEST.shortIdea(selected,96)",ctx);
 assert(typeof headline==="string"&&headline.length>22,"Missing substantive finding headline");
 assert(!/Harman|single.factor|method bias/i.test(headline),"Methods artifact rendered as a research finding");
 assert(headline.length<96);
}
// Raw results can contain validity/reliability diagnostics. Public research
// headlines and cards must use the screened digest with a truthful source label.
ctx.selected={
 kind:"scholarly",doi:"10.1234/methods",title:"AI literacy and attention",
 reading:{
  level:"full_text",
  findings:"Harman's single-factor test showed acceptable common method bias.",
  digest:{
   finding:"AI literacy was positively correlated with attention in the survey.",
   finding_source:"abstract",
   idea:"The study examined AI literacy and attention.",
   status:"automatically_condensed_source_text"
  }
 }
};
const safeInfo=vm.runInContext("TEST.ideaInfo(selected)",ctx);
assert.equal(safeInfo.label,"RESULT REPORTED IN ABSTRACT");
assert(safeInfo.text.includes("positively correlated"));
assert(!/Harman|single.factor|common method bias/i.test(safeInfo.text));
const safeHeadline=vm.runInContext("TEST.shortIdea(selected,105)",ctx);
assert(!/Harman|single.factor|common method bias/i.test(safeHeadline));

assert.throws(()=>vm.runInContext('TEST.make("div","x",document.createElement("span"))',ctx),/accepts text only/);
console.log("Article UI passed:",verified,"idea-first pages, evidence support, study provenance and grounded visuals validated.");
