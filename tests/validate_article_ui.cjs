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
assert(styles.includes("2026-10-22 design system"),"Shared typography and compact imagery layer missing");
assert(styles.includes("grid-template-columns:minmax(0,1fr) 176px"),"Editorial artwork must stay thumbnail-sized in readings");
assert(styles.includes(".editorial-grid{grid-template-columns:repeat(2"),"Editorial listings must allow room for text");
assert(styles.includes("font:400 var(--reading-size)/var(--reading-leading) var(--reading-font)"),"Unified explanatory prose style missing");
assert(!styles.includes("Article reading experience v2"),"Obsolete layered article CSS still present");
class Element{
 constructor(tag){this.tag=tag;this.textContent="";this.className="";this.children=[];this.style={};this.hidden=false;this.open=false;this.attributes={}}
 append(...els){for(const e of els){assert(e instanceof Element,"Non-element child");this.children.push(e)}}
 replaceChildren(...els){this.children=[];this.textContent="";this.append(...els)}
 setAttribute(k,v){this.attributes[k]=v}
 addEventListener(_name,_callback){}
}
const paperContainer=new Element("div");
const libraryContainer=new Element("div"),libraryCount=new Element("div");
const inputs={"#search":{value:""},"#scope-filter":{value:"all"},"#topic-filter":{value:""},"#depth-filter":{value:"readable"},"#type-filter":{value:""}};
const doc={createElement:tag=>new Element(tag),querySelector:q=>q==="#paper-content"?paperContainer:q==="#library-results"?libraryContainer:q==="#library-count"?libraryCount:inputs[q]||null};
const prefix=app.slice(0,app.lastIndexOf('$("[data-route]").forEach('));
assert(prefix.length>10000,"Unable to load application functions");
const ctx=vm.createContext({document:doc,URL,console,window:{scrollTo(){}}});
vm.runInContext(prefix+"\nconst TEST={showPaper,showLibrary,shortIdea,ideaInfo,readableSourceTitle,editorialImage,make,S};",ctx);
const nodes=root=>[root,...root.children.flatMap(nodes)];
const match=(root,cls)=>nodes(root).find(n=>n.className.split(" ").includes(cls));
const matching=(root,cls)=>nodes(root).filter(n=>n.className.split(" ").includes(cls));
const textContent=root=>nodes(root).map(n=>n.textContent).filter(Boolean).join(" | ");
// Previously published links must resolve to an honest pending-source view,
// not a fabricated one-paragraph reading when the full article was never read.
const pending={kind:"nonacademic",title:"Not-yet-reviewed commentary",url:"https://theconversation.com/a-source-pending-full-reading",source_quality:{decision:"awaiting_full_article_reading"}};
ctx.selected=pending;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(match(paperContainer,"rv-awaiting-reading"),"Missing transparent pending-source route");
assert(textContent(paperContainer).includes("has not been retrieved and verified"),"Pending article falsely presented as analysis");
assert(!match(paperContainer,"rv-longform"),"RSS snippet must not be dressed up as an article reading");
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
 assert(source&&source.textContent===vm.runInContext("TEST.readableSourceTitle(selected)",ctx),"Source title missing for "+r.title);
 assert(!matching(page,"concept-scene").length,"Decorative generic concept diagram present");
 assert(match(page,"rv-layout")&&match(page,"rv-content"),"Consistent story layout missing");
 const art=match(page,"story-visual-reading"),image=match(page,"story-image");
 assert(art&&image&&/^assets\/reading-(?:focus|offloading|fragmentation|learning|interventions|work|society|wellbeing|trust|critical|reflection|notification|measurement|recovery|research|creativity)\.svg$/.test(image.src),"Study-themed artwork missing for "+r.title);
 assert(match(match(page,"rv-head"),"story-visual-reading"),"Illustrative thumbnail must live within reading header: "+r.title);
 assert(/not a visualization of study findings/.test(textContent(art)),"Concept art must not look like empirical evidence");
 const autogenerated=match(page,"automatic-evidence");
 if(r.visual?.kind==="evidence_snapshot"||r.visual?.kind==="research_design"){
   assert(autogenerated||match(page,"rv-context-grid"),"Automatic visual or source context missing for "+r.title);
 }else if(r.kind==="nonacademic"){
   assert(match(page,"rv-longform"),"Nonacademic reading must use an argument-led structure");
   assert(!match(page,"rv-context-grid"),"Do not force commentary into research methods cards");
   assert(!textContent(page).includes("This source advances an argument rather than measuring the effect of an intervention."),"Boilerplate commentary substituted for source analysis");
   assert(!textContent(page).includes("This is a commentary or editorial account, not a controlled study."),"Faux study methods on commentary");
 }else assert(match(page,"rv-context-grid"),"Source context and caveats missing");
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
assert(edited>=3,"The source-screened reading room should retain checked editorial research notes");
assert(db.every(x=>["AI-specific","Adjacent digital-attention evidence","Earlier digital-attention foundation","Historical AI context"].includes(x.source_group)),"Source classification missing");
const earlier=db.filter(x=>/^\d{4}$/.test((x.published||"").slice(0,4))&&Number((x.published||"").slice(0,4))<2023);
assert(earlier.every(x=>x.source_group.startsWith("Earlier")||x.source_group.startsWith("Historical")),
 "Earlier digital attention work must not be classified as recent GenAI research");
assert(html.includes('id="scope-filter"')&&html.includes('id="year-context"'),"Research scope controls and explanation missing");
assert(app.includes('x.source_group==="AI-specific"'),"AI-specific publication chart must not mix foundational sources");
inputs["#scope-filter"].value="core";
vm.runInContext("TEST.showLibrary()",ctx);
const core=db.filter(x=>x.source_group==="AI-specific").length;
assert.equal(matching(libraryContainer,"library-story").length,core,"AI-specific library filter must exclude historical and adjacent sources");
inputs["#scope-filter"].value="all";

assert(db.every(r=>r.visual&&typeof r.visual.kind==="string"),"Future ingestion visual metadata must cover all public records");
for(const name of ["focus","offloading","fragmentation","learning","interventions","work","society","wellbeing","trust","critical","reflection","notification","measurement","recovery","research","creativity"]){
 const svg=read("assets/reading-"+name+".svg");
 assert(svg.includes('<svg')&&svg.includes('viewBox="0 0 880 530"'),"Missing/malformed image asset: "+name);
}
const workflow=read(".github/workflows/publish.yml");
assert(workflow.includes("cp assets/reading-*.svg assets/feed.xsl _site/assets/"),"New images and RSS stylesheet are not included in the published website");
vm.runInContext("TEST.showLibrary()",ctx);
const cards=matching(libraryContainer,"library-story");
assert.equal(cards.length,db.length,"All searchable readings must use the visual library card");
assert.equal(matching(libraryContainer,"story-visual-card").length,db.length,"Library card illustrations missing");
for(const r of db.filter(x=>/^[^a-z]*[A-Z][^a-z]*$/.test(x.title)&&x.title.length>25)){
 const label=vm.runInContext("TEST.readableSourceTitle(database.find(x=>x.title===selectedTitle))",
   Object.assign(ctx,{selectedTitle:r.title}));
 assert(!/^[A-Z\s\d\W]+$/.test(label),"All-capitalized source label persists: "+r.title);
}

// A NEW DOI never needs a hand-authored switch case to get a source-based visual.
const future={
 kind:"scholarly",doi:"10.9999/new-attention-2027",title:"New attention study",
 lane:"Fragmentation",published:"2027-02-01",reading:{level:"abstract",digest:{
 idea:"Digital habits were associated with how students described concentration.",
 approach:"A survey of students examining device interruptions and self-reported attention.",
 finding:"More interruptions were associated with lower reported attention.",
 finding_source:"abstract",
 limitation:"Cross-sectional responses cannot establish a causal mechanism.",
 status:"automatically_condensed_source_text"
 }},visual:{kind:"evidence_snapshot",basis:"abstract",status:"indexed",finding_source:"abstract",
 blocks:[{label:"Research approach",text:"A survey of students examining device interruptions and self-reported attention."},
 {label:"Reported finding",text:"More interruptions were associated with lower reported attention."},
 {label:"What remains uncertain",text:"Cross-sectional responses cannot establish a causal mechanism."}]}
};
ctx.selected=future;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(match(paperContainer,"story-visual-reading"),"New article needs a topic-specific cover");
const automatic=match(paperContainer,"automatic-evidence");
assert(automatic,"A new unrecognized DOI must receive a data-grounded evidence graphic");
assert.equal(matching(automatic,"auto-evidence-item").length,3,"Evidence figure needs three supported sections");
assert(!match(paperContainer,"rv-context-grid"),"Do not repeat all the visual evidence as text cards");
assert(textContent(automatic).includes("cannot establish a causal mechanism"));
const unknown={...future,doi:"10.9999/unknown-2027",
 reading:{level:"abstract",digest:{idea:"What helps people manage attention?",status:"automatically_condensed_source_text",finding:"",finding_source:"none"}},
 visual:{kind:"illustration_only",reason:"insufficient_indexed_evidence"}};
ctx.selected=unknown;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(match(paperContainer,"story-visual-reading"),"Unknown papers must retain a themed illustration");
assert(!match(paperContainer,"automatic-evidence"),"No fabricated result charts for an unknown paper");

const visualDoi=[
 "10.1007/s44217-026-02332-w","10.1515/humaff-2026-0011",
 "10.3389/fpsyg.2026.1960382","10.1177/21582440261497404",
 "10.1080/17501229.2026.2730676","10.3389/feduc.2026.1952725",
 "10.48550/arxiv.2609.38029","10.21203/rs.3.rs-10212076/v1",
 "10.3389/fcomm.2026.1828344","10.3390/educsci16091470",
 "10.54359/ps.v19i108.2216","10.3389/fpsyg.2026.1832219",
 "10.36948/ijfmr.2026.v08i05.87207","10.31234/osf.io/wy8z3_v1",
 "10.35542/osf.io/64qz7_v1","10.1007/s10648-026-10224-6"
];
for(const doi of visualDoi){
 const source=db.find(x=>x.doi===doi);
 if(!source)continue;
 ctx.selected=source;vm.runInContext("TEST.showPaper(selected)",ctx);
 const figure=match(paperContainer,"evidence-graphic");
 assert(figure,"Missing evidence-first graphic for "+doi);
 assert(match(figure,"concept-note"),"Evidence figure needs explanatory provenance "+doi);
 assert(match(figure,"article-data-visual"),"Evidence diagram must be labeled "+doi);
}
const idea=db.find(x=>x.doi==="10.58304/ijts.260930");
if(idea){
 ctx.selected=idea;vm.runInContext("TEST.showPaper(selected)",ctx);
 assert(match(paperContainer,"rv-claim"),"Important specific findings should be immediately readable");
 assert(match(paperContainer,"article-data-visual"),"Specific source-grounded method graphic missing");
} // Journals still awaiting venue screening must not be forced into the public library.
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
