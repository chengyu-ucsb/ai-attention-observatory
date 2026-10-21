/* The complete public library must render one consistent idea-first reading page. */
"use strict";
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path"),assert=require("node:assert/strict");
const ROOT=path.resolve(__dirname,"..");
const read=p=>fs.readFileSync(path.join(ROOT,p),"utf8");
const app=read("app.js"),html=read("index.html"),styles=read("styles.css");
assert(!app.includes("discovery provider warning(s)"),"Workflow warnings leaked into visitor UI");
assert(!html.includes('id="research-warning"'),"Internal warning banner leaked into HTML");
assert(!app.includes('make("div","paper-identity",add('),"DOM node passed into text-only helper");
for(const id of ["paper-content","feature-grid","library-results"])assert(html.includes('id="'+id+'"'));
assert(styles.includes(".rv-article"),"New coherent reading stylesheet missing");
assert(!styles.includes("Article reading experience v2"),"Obsolete layered article CSS still present");
class Element{
 constructor(tag){this.tag=tag;this.textContent="";this.className="";this.children=[];this.style={};this.hidden=false;this.open=false;this.attributes={}}
 append(...els){for(const e of els){assert(e instanceof Element,"Non-element child");this.children.push(e)}}
 replaceChildren(...els){this.children=[];this.textContent="";this.append(...els)}
 setAttribute(k,v){this.attributes[k]=v}
 addEventListener(_name,_callback){}
}
const paperContainer=new Element("div");
const doc={createElement:tag=>new Element(tag),querySelector:q=>q==="#paper-content"?paperContainer:null};
const prefix=app.slice(0,app.lastIndexOf('$("[data-route]").forEach('));
assert(prefix.length>10000,"Unable to load application functions");
const ctx=vm.createContext({document:doc,URL,console,window:{scrollTo(){}}});
vm.runInContext(prefix+"\nconst TEST={showPaper,shortIdea,ideaInfo,make,S};",ctx);
const nodes=root=>[root,...root.children.flatMap(nodes)];
const match=(root,cls)=>nodes(root).find(n=>n.className.split(" ").includes(cls));
const matching=(root,cls)=>nodes(root).filter(n=>n.className.split(" ").includes(cls));
const textContent=root=>nodes(root).map(n=>n.textContent).filter(Boolean).join(" | ");
const db=JSON.parse(read("data/public-library.json"));
assert(db.length>50,"Expected public, citation-screened library");
ctx.database=db;vm.runInContext("TEST.S.records=database",ctx);
let checked=0,edited=0,sourceOnly=0;
for(const r of db){
 ctx.selected=r;vm.runInContext("TEST.showPaper(selected)",ctx);
 const page=match(paperContainer,"rv-article");
 const headline=match(page,"rv-headline"),source=match(page,"rv-source-title");
 assert(page&&headline&&headline.tag==="h1","Missing primary insight heading for "+r.title);
 assert(headline.textContent.length>=10&&headline.textContent.length<=231,"Headline overflows for "+r.title);
 assert(!/^(?:the authors|the researchers|this study|this paper|we found)\b/i.test(headline.textContent),"Paper-centred headline: "+r.title+" / "+headline.textContent);
 assert(source&&source.textContent===r.title,"Source title missing for "+r.title);
 assert(!matching(page,"concept-scene").length,"Decorative generic concept diagram present");
 assert(match(page,"rv-layout")&&match(page,"rv-content"),"Consistent story layout missing");
 assert(match(page,"rv-context-grid"),"Source context and caveats missing");
 assert(match(page,"rv-source"),"Source citation/links missing");
 assert(match(page,"rv-status"),"Reader cannot distinguish edited and automatic content");
 const d=r.reading?.digest||{};
 if(d.status==="editorially_written_from_indexed_sections"){
  edited++;
  assert(headline.textContent.includes(d.idea.slice(0,Math.min(d.idea.length,25))),"Edited takeaway missing: "+r.title);
  assert(match(page,"rv-deck"),"Edited reading lacks a concise explanation: "+r.title);
 }else sourceOnly++;
 const excerpt=match(page,"rv-drawer");
 if(excerpt)assert(excerpt.open===false,"Raw passages should be collapsed");
 assert(!/\[object (?:HTML\w+Element|Object)\]/.test(textContent(page)),"Broken object rendering: "+r.title);
 checked++;
}
assert(edited>=20,"Expected source-grounded editorial coverage to expand");
const idea=db.find(x=>x.doi==="10.58304/ijts.260930");
assert(idea,"Literacy reference should appear in the public library");
ctx.selected=idea;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(match(paperContainer,"rv-claim"),"Important specific findings should be immediately readable");
assert(match(paperContainer,"article-data-visual"),"Specific source-grounded method graphic missing");
const adjacent=db.find(x=>x.doi==="10.3389/fpsyg.2026.1930030");
assert(adjacent);
ctx.selected=adjacent;vm.runInContext("TEST.showPaper(selected)",ctx);
assert.equal(matching(paperContainer,"study-coefficient-row").length,4,"Study chart should use four sourced coefficients");
assert(textContent(paperContainer).includes("did not examine generative AI"),"Adjacent evidence must be distinguished from GenAI evidence");
const conceptual=db.find(x=>x.doi==="10.35542/osf.io/64qz7_v1");
if(conceptual){
 ctx.selected=conceptual;vm.runInContext("TEST.showPaper(selected)",ctx);
 assert(match(paperContainer,"rv-source-gap"),"Conceptual work without new findings should not be presented as empirical evidence");
}
const title=vm.runInContext('TEST.shortIdea({kind:"scholarly",title:"A Study of Attention",reading:{digest:{idea:"AI use can support attention.",status:"editorially_written_from_indexed_sections"}}},100)',ctx);
assert.equal(title,"AI use can support attention.");
assert.throws(()=>vm.runInContext('TEST.make("div","x",document.createElement("span"))',ctx),/accepts text only/);
console.log("Validated",checked,"reading pages including",edited,"edited notes and",sourceOnly,"automated/publisher readings.");
