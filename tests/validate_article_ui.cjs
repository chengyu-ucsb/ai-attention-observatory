/* The complete public library must render one consistent idea-first reading page. */
"use strict";
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path"),assert=require("node:assert/strict");
const ROOT=path.resolve(__dirname,"..");
// A clean checkout excludes generated SVGs. Build only editorial art, without
// acquisition or mutation of the public source readings, for every caller.
require("node:child_process").execFileSync("python",["scripts/article_art.py"],{cwd:ROOT,stdio:"pipe"});
const read=p=>fs.readFileSync(path.join(ROOT,p),"utf8");
const app=read("app.js"),html=read("index.html"),styles=read("styles.css");
assert(!app.includes("discovery provider warning(s)"),"Workflow warnings leaked into visitor UI");
assert(!html.includes('id="research-warning"'),"Internal warning banner leaked into HTML");
assert(!app.includes('make("div","paper-identity",add('),"DOM node passed into text-only helper");
for(const id of ["paper-content","feature-grid","library-results"])assert(html.includes('id="'+id+'"'));
assert(styles.includes(".rv-article"),"New coherent reading stylesheet missing");
assert(styles.includes("2026-10-22 design system"),"Shared typography and compact imagery layer missing");

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
const libraryContainer=new Element("div"),libraryCount=new Element("div"),backlogContainer=new Element("div");
const inputs={"#search":{value:""},"#scope-filter":{value:"all"},"#topic-filter":{value:""},"#depth-filter":{value:"readable"},"#type-filter":{value:""}};
const doc={createElement:tag=>new Element(tag),createElementNS:(_ns,tag)=>new Element(tag),querySelector:q=>q==="#paper-content"?paperContainer:q==="#library-results"?libraryContainer:q==="#library-count"?libraryCount:q==="#backlog-coverage"?backlogContainer:inputs[q]||null};
const prefix=app.slice(0,app.lastIndexOf('$("[data-route]").forEach('));
assert(prefix.length>10000,"Unable to load application functions");
const ctx=vm.createContext({document:doc,URL,console,window:{scrollTo(){}}});
vm.runInContext(prefix+"\nconst TEST={showPaper,showLibrary,shortIdea,ideaInfo,processedIdea,featureCoverage,renderBacklog,issueSourceShelfItem,readableSourceTitle,editorialImage,make,S,readingParagraphs,sourceFields,readingBullets,readingQualifications,compactReading};",ctx);
const nodes=root=>[root,...root.children.flatMap(nodes)];
const match=(root,cls)=>nodes(root).find(n=>n.className.split(" ").includes(cls));
const matching=(root,cls)=>nodes(root).filter(n=>n.className.split(" ").includes(cls));
const textContent=root=>nodes(root).map(n=>n.textContent).filter(Boolean).join(" | ");
const proseText=root=>nodes(root).map(n=>n.textContent).filter(Boolean).join(" ").replace(/\s+/g," ").trim();
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
 if(!r.reading?.original_summary)assert(!/^(?:the authors|the researchers|this study|this paper|we found)\b/i.test(headline.textContent),"Paper-centred headline: "+r.title+" / "+headline.textContent);
 assert(source&&source.textContent===vm.runInContext("TEST.readableSourceTitle(selected)",ctx),"Source title missing for "+r.title);
 assert(!matching(page,"concept-scene").length,"Decorative generic concept diagram present");
 assert(match(page,"rv-layout")&&match(page,"rv-content"),"Consistent story layout missing");
 const art=match(page,"story-visual-reading"),image=match(page,"story-image");
 const indexedFields=vm.runInContext("TEST.sourceFields(selected).filter(([,content])=>content)",ctx);
 const indexedReader=match(page,"rv-source-excerpts");
 if(indexedFields.length){
   assert(indexedReader,"Available indexed sources need a reader: "+r.title);
   const sections=matching(indexedReader,"rv-source-section");
   assert.equal(sections.length,indexedFields.length,"Source section missing: "+r.title);
   for(let i=0;i<indexedFields.length;i++){
     const prose=match(sections[i],"rv-prose");
     assert.equal(prose.children.map(p=>p.textContent).join(" "),String(indexedFields[i][1]).replace(/\s+/g," ").trim(),"Source words or numeric details changed: "+indexedFields[i][0]+" / "+r.title);
   }
 }else assert(!indexedReader,"Unavailable or unrelated source material must not create a reader: "+r.title);
 assert(art&&image&&image.src===r.editorial_art.src,"Article-specific illustration missing: "+r.title);
 assert(image.alt===r.editorial_art.alt&&image.alt.length>10,"Meaningful illustration alt missing");
 assert(fs.existsSync(path.join(ROOT,image.src)),"Illustration asset missing");
 assert(match(art,"story-visual-caption").textContent==="Editorial illustration","Art must be separate from evidence");
 const autogenerated=match(page,"automatic-evidence");
 if(r.reading?.original_summary){
   const reading=r.reading,approved=r.original_reading?.summary,digest=reading.digest||{};
   assert(approved,"Public originals must retain the accepted summary for traceability");
   assert(proseText(match(page,"rv-head")).includes(approved.idea||approved.thesis),"Preserve the exact approved idea, including cautious attribution, beside the concise topic heading");
   // Reader paragraph boundaries are whitespace, not changes to approved prose.
   const primaryText=proseText(match(page,"rv-head"))+" "+proseText(match(page,"rv-content"));
   for(const [field,value] of Object.entries(approved)){
     if(value)assert(primaryText.includes(value),"Approved original field missing from reading or disclosure: "+field+" / "+r.title);
   }
   const citation=match(page,"rv-source"),evidence=match(page,"rv-evidence");
   assert.equal(match(citation,"rv-primary-link").href,reading.source_url,"Original must link the exact checked source");
   for(const key of ["source_version","review_scope","notice","quality_note"]){
     if(reading[key])assert(textContent(citation).includes(reading[key]),"Original source qualification missing: "+key);
   }
   assert(textContent(page).includes("not human review"),"AI source-check must not imply human review");
   if(reading.temporal_notice)assert(textContent(match(page,"rv-head")).includes(reading.temporal_notice),"Original date/version caveat must be prominent");
   assert(evidence&&evidence.open===false,"Original source locators must have a collapsed disclosure");
   const locators=Object.values(reading.evidence).flat();
   assert.equal(matching(evidence,"rv-source-locator").length,locators.length,"Every approved locator must be rendered");
   const commentary=reading.research_type==="attributed_commentary";
   for(const locator of locators){
     const expected=["Section: "+locator.section];
     if(locator.page)expected.push("page "+locator.page);
     if(locator.paragraph)expected.push((commentary&&reading.source_format==="html"?"extracted block ":"paragraph ")+locator.paragraph);
     assert(textContent(evidence).includes(expected.join(" · ")),"Exact approved locator missing");
   }
   assert(!autogenerated&&!match(page,"rv-artwork")&&!match(page,"rv-original-figure"),"Original summary must not reuse stale indexed graphics");
   assert(!match(page,"rv-research-longform"),"Original summary must not borrow older research prose");
   if(commentary){
     assert(match(page,"rv-longform")&&!match(page,"rv-context-grid"),"Original commentary must retain its argument structure");
     for(const label of ["How it was studied","Study approach","REPORTED FINDING","Methods as indexed","Results as indexed"])
       assert(!textContent(page).includes(label),"Original commentary inherited a scholarly label: "+label);
   }else{
     assert(match(page,"rv-context-grid"),"Original scholarly method and qualifications must remain visible");
     assert(proseText(match(page,"rv-context-grid")).includes(digest.limitation),"Complete original qualifications must remain available in their limitation section");
   }
 }else if(r.visual?.kind==="evidence_snapshot"||r.visual?.kind==="research_design"){
   assert(autogenerated||match(page,"rv-context-grid"),"Automatic visual or source context missing for "+r.title);
 }else if(r.kind==="nonacademic"){
   assert(match(page,"rv-longform"),"Nonacademic reading must use an argument-led structure");
   assert(!match(page,"rv-context-grid"),"Do not force commentary into research methods cards");
   assert(!textContent(page).includes("This source advances an argument rather than measuring the effect of an intervention."),"Boilerplate commentary substituted for source analysis");
   assert(!textContent(page).includes("This is a commentary or editorial account, not a controlled study."),"Faux study methods on commentary");
 }else assert(match(page,"rv-context-grid"),"Source context and caveats missing");
 assert(match(page,"rv-source"),"Source citation/links missing");
 assert(match(page,"rv-status"),"Reader cannot distinguish edited and automatic content");
 const provenance=match(page,"rv-provenance");
 assert(provenance&&provenance.tag==="details"&&!provenance.open,"Source details must start collapsed");
 assert(match(provenance,"rv-status"),"Review status must remain in source details");
 const overview=match(page,"rv-overview");
 if(overview)assert(overview.tag==="details"&&!overview.open,"Overview must be optional");
 for(const cls of ["rv-take","rv-research-longform"]){
  const section=match(page,cls);if(section)assert(section.tag==="details"&&!section.open,"Long reading section must be optional: "+cls);
 }
 if(r.reading?.original_summary){
  const version=match(page,"rv-source-row");
  const expectedVersion=r.reading.source_version.replace(/^arxiv_preprint_v(\d+)$/,"arXiv preprint v$1 · review unverified").replace(/^publisher_article$/,"Publisher article");
  assert(version&&proseText(version).includes(expectedVersion),"Specific readable version must be outside optional disclosures");
  assert(proseText(provenance).includes(r.reading.source_version),"Raw source version must remain in provenance");
 }

 const d=r.reading?.digest||{};
 if(d.status==="editorially_written_from_indexed_sections"){
  edited++;
  assert(proseText(page).includes(d.idea),"Full edited takeaway missing: "+r.title);
  assert(match(page,"rv-overview")&&proseText(match(page,"rv-overview")).includes(d.explain),"Edited reading lacks its complete explanation: "+r.title);
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
assert(!match(paperContainer,"story-visual-reading"),"New articles must not add decorative header covers");
const automatic=match(paperContainer,"automatic-evidence");
assert(automatic,"A new unrecognized DOI must receive a data-grounded evidence graphic");
assert.equal(matching(automatic,"auto-evidence-item").length,3,"Evidence figure needs three supported sections");
assert(!match(paperContainer,"rv-context-grid"),"Do not repeat all the visual evidence as text cards");
assert(textContent(automatic).includes("cannot establish a causal mechanism"));
const unknown={...future,doi:"10.9999/unknown-2027",
 reading:{level:"abstract",digest:{idea:"What helps people manage attention?",status:"automatically_condensed_source_text",finding:"",finding_source:"none"}},
 visual:{kind:"illustration_only",reason:"insufficient_indexed_evidence"}};
ctx.selected=unknown;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(!match(paperContainer,"story-visual-reading"),"Unknown papers must not add decorative header covers");
assert(!match(paperContainer,"automatic-evidence"),"No fabricated result charts for an unknown paper");

// Synthetic original summaries are independent from machine extraction. Never
// copy private research drafts into these fixtures.
const original={
 ...future,doi:"10.9999/synthetic-journal",title:"Synthetic attention working paper",
 url:"https://example.org/synthetic-journal",venue:"Synthetic Journal",source_group:"AI-specific",
 analysis:{provenance:"Synthetic machine extraction from an older source version",
  fulltext_url:"https://example.org/synthetic-machine-v1.pdf",
  methods:"Unchanged machine methods sentinel.",results:"Unchanged machine results sentinel.",
  discussion:"Unchanged machine discussion sentinel.",limitations:"Unchanged machine limitations sentinel."},
 reading:{original_summary:true,level:"full_text",review_kind:"ai_source_check",
  source_version:"Working paper v2 (2027-01-15)",source_format:"pdf",
  source_url:"https://example.org/synthetic-working-paper-v2.pdf",
  source_doi:"10.9999/synthetic-working-paper.v2",related_journal_doi:"10.9999/synthetic-journal",
  review_scope:"Working-paper PDF, including Methods, Results and Discussion; journal version not checked.",
  provenance:"Original paraphrase checked against the stated working-paper version by a separate AI pass.",
  notice:"This summary concerns the working-paper version, not the related journal publication.",
  methods:"Original study approach.",findings:"Original reported finding.",
  interpretation:"Original interpretation.",limitations:"Original limitation.",
  evidence:{
   idea:[{section:"Results",page:7,paragraph:2}],
   explain:[{section:"Introduction",page:2,paragraph:3}],
   approach:[{section:"Methods",page:4}],
   finding:[{section:"Results",page:7,paragraph:2},{section:"Table 2",page:8}],
   interpretation:[{section:"Discussion",page:10}],
   limitation:[{section:"Limitations",page:11,paragraph:1}]
  },
  digest:{status:"ai_source_checked_original_summary",
   idea:"Different prompting habits were associated with different attention ratings.",
   explain:"An original explanation summarizes the checked working-paper version.",
   approach:"Original study approach.",finding:"Original reported finding.",
   interpretation:"Original interpretation.",limitation:"Original limitation.",
   basis:"Original summary checked against the stated source by a separate AI pass; not human review or independent replication.",
   source_version:"Working paper v2 (2027-01-15)",
   source_url:"https://example.org/synthetic-working-paper-v2.pdf",
   review_scope:"Working-paper PDF, including Methods, Results and Discussion; journal version not checked.",
   longform:{reported_results:"Stale unreviewed long-form sentinel."}
  }
 },
 visual:{kind:"evidence_snapshot",basis:"full_text",blocks:[
  {label:"Older machine graphic",text:"Stale unreviewed visual sentinel."}
 ]}
};
const originalBefore=JSON.stringify(original);
ctx.selected=original;vm.runInContext("TEST.showPaper(selected)",ctx);
const originalPage=match(paperContainer,"rv-article"),originalDigest=original.reading.digest;
assert.equal(match(originalPage,"rv-headline").textContent,originalDigest.idea,"Original idea must be the primary detail heading");
assert.equal(proseText(match(match(originalPage,"rv-overview"),"rv-prose")),originalDigest.explain);
assert(textContent(match(originalPage,"rv-claim")).includes(originalDigest.finding),"Original reported finding missing from primary prose");
assert(textContent(match(originalPage,"rv-context-grid")).includes(originalDigest.approach));
assert(textContent(match(originalPage,"rv-context-grid")).includes(originalDigest.limitation));
assert(textContent(match(originalPage,"rv-take")).includes(originalDigest.interpretation),"Original interpretation must be shown separately");
assert(textContent(match(originalPage,"rv-take")).includes("Interpretation and implications"));
assert(match(originalPage,"rv-status").textContent.includes("AI source-check"));
assert(match(originalPage,"rv-status").textContent.includes("not human review or independent replication"));
assert(!textContent(match(originalPage,"rv-meta")).includes("Edited reading"),"AI source-check must not imply human editorial review");
assert(textContent(match(originalPage,"rv-head")).includes(original.reading.source_version),"Exact checked version must be visible up front");
assert(!match(originalPage,"automatic-evidence"),"An older machine visual must not substitute for the checked summary");
assert(!match(originalPage,"rv-research-longform"),"Do not mix older long-form notes into the original summary");
const excerpts=match(originalPage,"rv-source-excerpts");
assert(excerpts&&excerpts.tag==="details"&&excerpts.open===false,"Machine excerpts must remain optional and collapsed");
assert(textContent(excerpts).includes("Inspect machine-indexed excerpts and abstract"));
for(const field of ["methods","results","discussion","limitations"])
 assert(textContent(excerpts).includes(original.analysis[field]),"Unchanged machine "+field+" must be retained separately");
for(const field of ["methods","findings","interpretation","limitations"])
 assert(!textContent(excerpts).includes(original.reading[field]),"Original prose mislabeled as machine excerpts: "+field);
const visibleText=root=>root.tag==="details"?"":[root.textContent,...root.children.map(visibleText)].filter(Boolean).join(" | ");
assert(!visibleText(originalPage).includes("machine results sentinel"),"Raw machine output leaked into primary reading");
assert(!textContent(originalPage).includes("Stale unreviewed"),"Older claims must not override the checked source version");
const evidence=match(originalPage,"rv-evidence");
assert(evidence&&evidence.tag==="details"&&evidence.open===false,"Source locators need an accessible, collapsed disclosure");
assert.equal(matching(evidence,"rv-source-locator").length,7,"Every summary-field locator must remain traceable");
assert(textContent(evidence).includes("Section: Results · page 7 · paragraph 2"));
assert(textContent(evidence).includes(original.reading.source_version));
const citation=match(originalPage,"rv-source"),sourceLink=match(citation,"rv-primary-link");
assert.equal(sourceLink.href,original.reading.source_url,"Checked source link must open the exact version read");
assert.equal(sourceLink.textContent,"Read the source","Source action should be concise; version stays in source metadata");
assert.equal(proseText(match(originalPage,"rv-provenance")).split("Source version identifier: "+original.reading.source_version).length-1,1,"Source version identifier must not be duplicated in provenance");
assert(textContent(citation).includes("AI source-check scope: "+original.reading.review_scope));
assert.equal(textContent(citation).split("AI source-check scope: "+original.reading.review_scope).length-1,1,"Do not repeat the source-check scope in the citation sidebar");
assert(textContent(citation).includes(originalDigest.basis));
assert(textContent(citation).includes(original.reading.notice));
assert(textContent(citation).includes("Checked source DOI: "+original.reading.source_doi));
assert(textContent(citation).includes("Related journal DOI (not checked here): "+original.reading.related_journal_doi));
const journalLink=matching(citation,"rv-secondary-link").find(n=>n.textContent.includes("Related journal publication"));
assert(journalLink&&journalLink.textContent.includes("not the checked source"));
assert.equal(journalLink.href,"https://doi.org/"+original.reading.related_journal_doi);
assert(!textContent(citation).includes("Reviewed full article")&&!textContent(citation).includes("Full-text sections"),"Original summary must not be labeled as machine extraction or publisher full-article review");
assert.equal(JSON.stringify(original),originalBefore,"Rendering must never rewrite the machine analysis or original summary");
assert.equal(vm.runInContext("TEST.shortIdea(selected,200)",ctx),originalDigest.idea);
assert.equal(vm.runInContext("TEST.processedIdea(selected)",ctx),originalDigest.idea);
assert.equal(vm.runInContext("TEST.ideaInfo(selected).text",ctx),originalDigest.idea);
assert.equal(vm.runInContext("TEST.ideaInfo(selected).label",ctx),"RESEARCH READING");
const coverage=vm.runInContext("TEST.featureCoverage(selected)",ctx);
assert(textContent(coverage).includes(original.reading.source_version));
assert(matching(coverage,"feature-evidence-mark").some(n=>n.title==="Checked source text"));
ctx.original=original;
vm.runInContext("TEST.S.records=[original];TEST.showLibrary()",ctx);
const originalCard=match(libraryContainer,"library-story");
assert(textContent(originalCard).includes(originalDigest.idea),"Original idea must be the primary library-card prose");
assert.equal(match(originalCard,"card-summary").textContent,originalDigest.explain);
assert(textContent(originalCard).includes("not human review")&&textContent(originalCard).includes(original.reading.source_version));
assert(!textContent(originalCard).includes("machine results sentinel"));
inputs["#search"].value="Original interpretation";
vm.runInContext("TEST.showLibrary()",ctx);
assert.equal(matching(libraryContainer,"library-story").length,1,"Original summary prose must be searchable");
inputs["#search"].value="";
vm.runInContext("TEST.S.backlog={};TEST.renderBacklog()",ctx);
assert(textContent(backlogContainer).includes("1 of 1 scholarly papers"),"Original summaries must retain the count of separately stored machine extraction");
vm.runInContext("TEST.S.records=[{...original,analysis:undefined}];TEST.renderBacklog()",ctx);
assert(textContent(backlogContainer).includes("0 of 1 scholarly papers"),"An original summary alone must not count as machine extraction");
vm.runInContext("TEST.S.records=[{...original,analysis:{...original.analysis,original_paraphrases_only:true}}];TEST.renderBacklog()",ctx);
assert(textContent(backlogContainer).includes("0 of 1 scholarly papers"),"Original paraphrases in analysis must not count as machine extraction");
vm.runInContext("TEST.S.records=[{...original,analysis:{...original.analysis,fulltext_url:undefined}}];TEST.renderBacklog()",ctx);
assert(textContent(backlogContainer).includes("0 of 1 scholarly papers"),"Machine extraction count requires an actual full-text source");
vm.runInContext("TEST.S.records=[original];TEST.S.backlog={full_text_extracted:0};TEST.renderBacklog()",ctx);
assert(textContent(backlogContainer).includes("0 of 1 scholarly papers"),"An explicit zero extraction count must not be overwritten");
vm.runInContext("TEST.S.records=[{kind:'scholarly',analysis:original.analysis,reading:{level:'abstract'}}];TEST.S.backlog={};TEST.renderBacklog()",ctx);
assert(textContent(backlogContainer).includes("1 of 1 scholarly papers"),"Stored machine extraction must count independently of projected reading level");
vm.runInContext("TEST.S.records=[{kind:'scholarly',reading:{level:'full_text'}}];TEST.renderBacklog()",ctx);
assert(textContent(backlogContainer).includes("0 of 1 scholarly papers"),"Reading depth alone must not be counted as machine extraction");
vm.runInContext("TEST.S.records=database;TEST.S.backlog={}",ctx);

const publisherSummary=JSON.parse(JSON.stringify(original));
publisherSummary.reading.source_version="Publisher version of record";
publisherSummary.reading.source_format="html";
publisherSummary.reading.source_url="https://example.org/synthetic-publisher-version";
publisherSummary.reading.source_doi=publisherSummary.doi;
publisherSummary.reading.review_scope="Publisher HTML Methods, Results and Discussion.";
publisherSummary.reading.provenance="Original paraphrase checked against publisher HTML by a separate AI pass.";
publisherSummary.reading.notice="This summary concerns the publisher version of record.";
Object.assign(publisherSummary.reading.digest,{
 source_version:publisherSummary.reading.source_version,source_url:publisherSummary.reading.source_url,
 review_scope:publisherSummary.reading.review_scope
});
delete publisherSummary.reading.related_journal_doi;
ctx.selected=publisherSummary;vm.runInContext("TEST.showPaper(selected)",ctx);
assert.equal(match(paperContainer,"rv-primary-link").href,publisherSummary.reading.source_url);
assert.equal(match(paperContainer,"rv-primary-link").textContent,"Read the source");
assert(textContent(match(paperContainer,"rv-source-row")).includes("Publisher version of record · HTML"));
assert(!textContent(match(paperContainer,"rv-source")).includes("Related journal DOI"),"One source DOI must not be relabeled as a separate journal version");

const conceptualOriginal={...original,research_type:"conceptual_framework"};
ctx.selected=conceptualOriginal;vm.runInContext("TEST.showPaper(selected)",ctx);
assert.equal(match(paperContainer,"rv-headline").textContent,originalDigest.idea);
assert(textContent(match(paperContainer,"rv-claim")).includes("PROPOSED MODEL, NOT A TESTED EFFECT"));
assert(vm.runInContext("TEST.ideaInfo(selected).label",ctx).includes("CONCEPTUAL PROPOSAL"));
const conceptualWithoutFinding={...conceptualOriginal,
 framework_notes:{idea:"Legacy framework idea sentinel.",stages:["First: Legacy framework stage sentinel."]},
 reading:{...conceptualOriginal.reading,findings:"",digest:{...conceptualOriginal.reading.digest,finding:""}}
};
ctx.selected=conceptualWithoutFinding;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(textContent(match(paperContainer,"rv-claim")).includes(originalDigest.idea),"Conceptual original must use its own approved idea when no finding exists");
assert(textContent(match(paperContainer,"rv-take")).includes(originalDigest.interpretation),"Conceptual original must retain its own interpretation without a measured finding");
assert(!textContent(paperContainer).includes("Legacy framework"),"Empty findings must never introduce older framework ideas or stages");
assert(!match(paperContainer,"rv-longform"),"Legacy framework stages must not become original summary prose");
assert(!match(paperContainer,"rv-source-gap"),"An approved conceptual summary is not a failed finding extraction");

// Weekly source provenance belongs to the archived edition, even when the
// current library reading has since moved to the publisher's version.
const issueOriginal={id:original.doi,title:original.title,url:original.url,venue:original.venue,
 editorial_role:"collection_week",original_summary:true,
 source_url:original.reading.source_url,source_version:original.reading.source_version,
 source_format:original.reading.source_format,source_doi:original.reading.source_doi,
 related_journal_doi:original.reading.related_journal_doi,review_kind:"ai_source_check",
 review_scope:original.reading.review_scope,
 review_label:"AI source-check against this source version; not human review or independent replication."
};
ctx.issueOriginal=issueOriginal;ctx.publisherSummary=publisherSummary;
vm.runInContext("TEST.S.records=[publisherSummary]",ctx);
for(const hasCurrentReading of [true,false]){
 if(!hasCurrentReading)vm.runInContext("TEST.S.records=[]",ctx);
 const shelfItem=vm.runInContext("TEST.issueSourceShelfItem(issueOriginal,0)",ctx);
 assert(textContent(shelfItem).includes(original.reading.source_version),"Weekly shelf must preserve the actual checked version");
 assert(!textContent(shelfItem).includes("Publisher version of record"),"Current reading must not overwrite archived source-version metadata");
 assert(textContent(shelfItem).includes(issueOriginal.review_label),"Weekly shelf must retain its explicit AI review label");
 const checkedLink=match(shelfItem,"issue-source-checked-link");
 assert.equal(checkedLink.href,original.reading.source_url,"Weekly shelf must link the actual working-paper source");
 assert(checkedLink.textContent.includes(original.reading.source_version)&&checkedLink.textContent.includes("PDF"));
 const publicationLink=match(shelfItem,"issue-source-publication-link");
 assert.equal(publicationLink.href,"https://doi.org/"+original.reading.related_journal_doi);
 assert(publicationLink.textContent.includes("not the checked source"));
 assert(textContent(shelfItem).includes("Checked source DOI: "+original.reading.source_doi));
 assert(textContent(shelfItem).includes("Related journal DOI (not checked here): "+original.reading.related_journal_doi));
 assert(textContent(shelfItem).includes("AI source-check scope: "+original.reading.review_scope));
 assert.equal(match(shelfItem,"issue-source-review").open,false,"Weekly review details should be optional and collapsed");
}
ctx.unsafeShelf={...issueOriginal,source_url:"javascript:invalid()",source_version:'Working paper <svg onload="invalid()">'};
const safeShelf=vm.runInContext("TEST.issueSourceShelfItem(unsafeShelf,1)",ctx);
assert(!match(safeShelf,"issue-source-checked-link"),"Weekly shelf must reject unsafe checked-source links");
assert.equal(match(safeShelf,"issue-source-version").textContent,"Checked source: "+ctx.unsafeShelf.source_version+" · PDF");
assert(!nodes(safeShelf).some(n=>["svg","script","img"].includes(n.tag)),"Weekly provenance must render as plain text");
ctx.legacyShelf={id:"synthetic-legacy",title:"Synthetic older source",url:"https://example.org/legacy",venue:"Synthetic Journal"};
const legacyShelf=vm.runInContext("TEST.issueSourceShelfItem(legacyShelf,2)",ctx);
assert(!match(legacyShelf,"issue-source-review")&&!match(legacyShelf,"issue-source-version"),"Legacy shelf entries must not acquire an unverified AI review label");
assert(textContent(legacyShelf).includes("Not in current reading library · Original source"));
vm.runInContext("TEST.S.records=database",ctx);

const safeSummary=JSON.parse(JSON.stringify(original));
safeSummary.reading.source_version='Working paper <svg onload="invalid()">';
safeSummary.reading.evidence.finding=[{section:'Results <img src=x onerror="invalid()">',page:9,paragraph:1}];
safeSummary.analysis.fulltext_url="javascript:invalid()";
for(const unsafe of ["javascript:invalid()","http://example.org/unsecured","https://user:password@example.org/source"]){
 safeSummary.reading.source_url=unsafe;
 ctx.selected=safeSummary;vm.runInContext("TEST.showPaper(selected)",ctx);
 assert(!match(match(paperContainer,"rv-source"),"rv-primary-link"),"Unsafe checked-source link must not be rendered: "+unsafe);
 assert(!matching(match(paperContainer,"rv-source-excerpts"),"rv-secondary-link").length,"Unsafe machine-source link must not be rendered");
 assert(textContent(match(paperContainer,"rv-evidence")).includes(safeSummary.reading.evidence.finding[0].section));
 assert(!nodes(match(paperContainer,"rv-evidence")).some(n=>["img","svg","script"].includes(n.tag)),"Source locator text must never become markup");
 assert(!nodes(match(paperContainer,"rv-head")).some(n=>["svg","script"].includes(n.tag)),"Source-version text must never become markup");
}
const noMachine={...original,analysis:undefined,abstract_text:undefined};
ctx.selected=noMachine;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(!match(paperContainer,"rv-source-excerpts"),"Do not fabricate a machine-excerpt drawer when no extraction exists");
assert(match(paperContainer,"rv-evidence"),"Source locators must remain available without machine extraction");

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
// Typed commentary uses checked argument layers, never scholarly fallback text.
const commentary=JSON.parse(JSON.stringify(original));
commentary.kind="nonacademic";commentary.doi="";commentary.url="https://example.org/synthetic-policy";
Object.assign(commentary.reading,{level:"curated",research_type:"attributed_commentary",
 source_version:"publisher_article",source_format:"html",source_url:commentary.url,
 source_doi:"",related_journal_doi:"",review_scope:"Main-argument HTML only; completeness not verified.",
 quality_note:"Suitable for attributed analysis, not empirical evidence.",
 notice:"Limited reading · AI source-check · not human review. Figures, supplements and linked claims not independently checked.",
 temporal:{original_published:"2026-10-29",reported_modified:"2026-11-05",checked_on:"2026-11-07",historical_snapshot_verified:false},
 temporal_notice:"Included by original publication on 2026-10-29. Current HTML modified 2026-11-05 and checked 2026-11-07; not an original-week snapshot."});
const lenses={thesis:"Synthetic author proposes reviewable decisions.",reasoning:"Context can change a decision's meaning.",
 examples:"A fictional appeal supplies missing context.",tension:"Speed competes with reviewability.",qualification:"The proposed safeguards have not been tested."};
commentary.reading.digest={idea:lenses.thesis,explain:lenses.thesis,approach:"",finding:"",interpretation:lenses.reasoning,
 longform:{...lenses,genre:"policy_analysis",attributed_to:"Synthetic policy author",source_depth:"main_argument_html"}};
commentary.reading.evidence=Object.fromEntries(Object.keys(lenses).map((k,i)=>[k,[{section:"Synthetic argument",paragraph:i+1}]]));
ctx.selected=commentary;vm.runInContext("TEST.showPaper(selected)",ctx);
const commentaryText=textContent(paperContainer);
assert(textContent(match(paperContainer,"rv-head")).includes(commentary.reading.temporal_notice),"Date-version caveat must remain accessible from the header");
for(const value of Object.values(lenses))assert(commentaryText.includes(value),"Missing commentary lens: "+value);
for(const forbidden of ["How it was studied","Study approach","REPORTED FINDING","Reported finding","Methods as indexed","Stale unreviewed"])
 assert(!commentaryText.includes(forbidden),"Commentary borrowed scholarly content: "+forbidden);
assert(!match(paperContainer,"rv-context-grid"));assert(!match(paperContainer,"automatic-evidence"));
assert(!match(paperContainer,"rv-source-excerpts"),"Checked commentary must not inherit an indexed-source reader");
assert.equal(vm.runInContext("TEST.sourceFields(selected).length",ctx),0,"Commentary must not expose stale scholarly or publisher fields");
assert.equal(matching(paperContainer,"rv-source-locator").length,5);
assert(textContent(match(paperContainer,"rv-evidence")).includes("extracted block 1"),"Typed HTML locators index extracted blocks, including headings and list items");
assert(!textContent(match(paperContainer,"rv-evidence")).includes("paragraph 1"),"Typed HTML blocks must not be mislabeled as prose paragraphs");
assert.equal(match(paperContainer,"rv-primary-link").href,commentary.url);
assert.equal(textContent(match(paperContainer,"rv-source")).split("AI source-check scope: "+commentary.reading.review_scope).length-1,1);
const required=["Limited reading","not human review","policy analysis","Synthetic policy author",commentary.reading.review_scope,commentary.reading.quality_note,"2026-11-05","2026-11-07","not an original-week snapshot"];
for(const value of required)assert(commentaryText.includes(value),"Missing reading caveat: "+value);
ctx.commentary=commentary;vm.runInContext("TEST.S.records=[commentary];TEST.showLibrary()",ctx);
for(const value of required)assert(textContent(libraryContainer).includes(value),"Missing card caveat: "+value);
const commentarySource={id:commentary.url,title:commentary.title,url:commentary.url,...commentary.reading};
ctx.commentarySource=commentarySource;
const commentaryShelf=vm.runInContext("TEST.issueSourceShelfItem(commentarySource,0)",ctx);
for(const value of required)assert(textContent(commentaryShelf).includes(value),"Missing shelf caveat: "+value);
assert.equal(matching(commentaryShelf,"rv-source-locator").length,5);
// Missing optional metadata or invalid locators must not create fabricated prose.
const minimalCommentary=JSON.parse(JSON.stringify(commentary));
for(const key of ["quality_note","temporal","temporal_notice","notice","review_scope","source_version"])delete minimalCommentary.reading[key];
minimalCommentary.reading.digest.longform={thesis:lenses.thesis};
minimalCommentary.reading.evidence={thesis:[null,{section:""},{section:"Synthetic argument",page:-1,paragraph:0}]};
ctx.selected=minimalCommentary;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(!/undefined|\[object Object\]|How it was studied/.test(textContent(paperContainer)));
assert.equal(matching(paperContainer,"rv-source-locator").length,1);
assert(!textContent(match(paperContainer,"rv-evidence")).includes("paragraph 0"));
// A screened preprint remains scholarly but never silently becomes peer reviewed.
const preprint=JSON.parse(JSON.stringify(original));
preprint.reading.notice="Preprint, not verified peer-reviewed evidence. Article screening is not peer review.";
preprint.reading.quality_note="Acceptable for a qualified reading; no strong causal claim.";
ctx.selected=preprint;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(textContent(paperContainer).includes(preprint.reading.notice));
assert(textContent(paperContainer).includes("How it was studied"));
assert(textContent(paperContainer).includes(originalDigest.finding));
assert(textContent(match(paperContainer,"rv-evidence")).includes("page 7 · paragraph 2"),"PDF page and paragraph locators must remain unchanged");
ctx.preprint=preprint;vm.runInContext("TEST.S.records=[preprint];TEST.showLibrary()",ctx);
assert(textContent(libraryContainer).includes(preprint.reading.notice));
ctx.preprintSource={id:preprint.doi,title:preprint.title,url:preprint.url,...preprint.reading};
assert(textContent(vm.runInContext("TEST.issueSourceShelfItem(preprintSource,0)",ctx)).includes(preprint.reading.notice));
// Optional integration input is generated by the backend's synthetic receipt tests.
if(process.env.CHECKED_RENDER_FIXTURE){
 const fixture=JSON.parse(fs.readFileSync(process.env.CHECKED_RENDER_FIXTURE,"utf8"));
 ctx.backendShelf=fixture.shelf;
 const backendShelf=vm.runInContext("TEST.issueSourceShelfItem(backendShelf,0)",ctx);
 for(const key of ["review_scope","review_label","temporal_notice","quality_note","attributed_to"])assert(textContent(backendShelf).includes(fixture.shelf[key]));
 assert.equal(matching(backendShelf,"rv-source-locator").length,5);
 for(const candidate of [fixture.accepted,fixture.modified_after_original_week]){
  ctx.selected=candidate;vm.runInContext("TEST.showPaper(selected)",ctx);
  assert(textContent(paperContainer).includes(candidate.reading.notice));
  if(candidate.reading.research_type==="attributed_commentary"){
   for(const key of Object.keys(lenses))assert(textContent(paperContainer).includes(candidate.reading.digest.longform[key]));
   assert(!textContent(paperContainer).includes("How it was studied"));
  }
 }
 for(const candidate of [fixture.revoked,fixture.stale]){
  assert(!candidate.reading?.original_summary,"Backend must revoke stale receipts before publication");
  ctx.selected=candidate;vm.runInContext("TEST.showPaper(selected)",ctx);
  assert(!match(paperContainer,"rv-evidence"));
  assert(!textContent(paperContainer).includes("Original summary"));
 }
}

console.log("Validated",checked,"reading pages including",edited,"edited notes and",sourceOnly,"automated/publisher readings, plus synthetic original-summary/source-version/excerpt regressions.");


// The source reader preserves richness and source separation, not a clipped card.
const longPassage="Participants completed the task while notifications were delivered at fixed intervals. ".repeat(35)+"Final source detail must remain visible.";
const richSource={...future,analysis:{fulltext_url:"https://example.org/source.pdf",methods:longPassage,results:"The source reports a result with its own qualification."},abstract_text:"An abstract that remains distinguishable from the indexed full-text methods."};
ctx.selected=richSource;vm.runInContext("TEST.showPaper(selected)",ctx);
const sourceReader=match(paperContainer,"rv-source-excerpts");
const sourceSections=matching(sourceReader,"rv-source-section");
assert(sourceSections.length>=3,"All available source sections need independent disclosures");
assert(sourceSections.every(section=>section.tag==="details"&&!section.open),"Sections begin collapsed rather than reveal a wall of text");
const methodProse=match(sourceSections[0],"rv-prose");
assert(methodProse.children.length>3,"Long source text must be split into readable paragraphs");
assert.equal(methodProse.children.map(p=>p.textContent).join(" "),longPassage.trim(),"Formatting must preserve every source word");
assert(textContent(sourceReader).includes("Final source detail must remain visible."),"The complete indexed section must not be clipped to reading-card length");
assert(match(sourceReader,"rv-reader-contents"),"Source sections need navigation");
const controls=matching(sourceReader,"rv-reader-control");
controls[0].onclick();assert(sourceSections.every(s=>s.open),"Expand all failed");
controls[1].onclick();assert(sourceSections.every(s=>!s.open),"Collapse all failed");
matching(sourceReader,"rv-reader-jump")[0].onclick();assert(sourceSections[0].open,"Section navigation must open the selected source section");
assert(!sourceSections[1].open,"Section navigation should leave other sections unchanged");
assert(match(paperContainer,"rv-coverage-table"),"Every scholarly reading needs a source-coverage table");
ctx.selected=unknown;vm.runInContext("TEST.showPaper(selected)",ctx);
for(const placeholder of ["Method details are not clear enough", "A source-specific limitation could not be verified"])
 assert(!textContent(paperContainer).includes(placeholder),"Generic placeholder must not substitute for a source-specific appraisal");
assert(textContent(paperContainer).includes("Not indexed"),"Missing source fields need honest availability labels");
assert(textContent(paperContainer).includes("not a flaw in the study"),"Coverage must be distinct from research quality");
const rawParagraphs=vm.runInContext("TEST.readingParagraphs('Sentence with p = 0.047 and a 95% CI [0.02, 0.15]. Another result remains qualified.')",ctx);
assert.equal(rawParagraphs.join(" "),"Sentence with p = 0.047 and a 95% CI [0.02, 0.15]. Another result remains qualified.","Numeric tokens must remain unchanged");
const joinedExtraction="An extracted sentence ends...Next sentence lacks a source-space. The result is p = 0.047.";
ctx.joinedExtraction=joinedExtraction;
assert.equal(vm.runInContext("TEST.readingParagraphs(joinedExtraction).join(' ')",ctx),joinedExtraction,"Sentence segmentation must not invent whitespace inside source tokens");
console.log("Source-reader preservation, section navigation, disclosure controls, and missing-field tests passed.");

const mixedBasis={...future,visual:{...future.visual,basis:"full_text",finding_source:"abstract"}};
ctx.selected=mixedBasis;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(textContent(match(paperContainer,"automatic-evidence")).includes("Source: abstract"),"A full-text record must not relabel an abstract-derived result as full-text evidence");

// Formatting must retain every word, including statistics, abbreviations and caveats.
for(const passage of [
 "A sample of n = 47 participated. The difference was 0.047 (95% CI [0.02, 0.15]). This cannot establish causality.",
 "Dr. Chen used Fig. 2 and U.S. data. No preregistered causal test was reported.",
 "Sentence ends...Next sentence has no source-space. The final detail remains.",
 "  Repeated   spaces\nare normalized. No additional claim is added."
]){
 ctx.passage=passage;
 const bullets=vm.runInContext("TEST.readingBullets(passage)",ctx);
 assert.equal(bullets.tag,"ul");assert(bullets.children.every(n=>n.tag==="li"));
 assert.equal(proseText(bullets),passage.replace(/\s+/g," ").trim(),"Bullet conversion changed source words");
}
const weeklyProse="A complete source-grounded opening remains visible. "+"The second sentence retains qualifications and does not claim a causal result. ".repeat(8)+"Final source detail remains intact.";
ctx.passage=weeklyProse;
const compact=vm.runInContext("TEST.compactReading(passage)",ctx),expansion=match(compact,"reading-expansion");
assert(expansion&&expansion.tag==="details"&&!expansion.open,"Long weekly prose must have a collapsed remainder");
assert.equal(match(compact,"compact-lead").textContent,"A complete source-grounded opening remains visible.");
assert.equal(proseText(match(compact,"compact-lead"))+" "+proseText(match(expansion,"rv-prose")),weeklyProse,"Weekly disclosure lost or changed words");
console.log("Redesign disclosure, visible source-version, bullet and weekly-prose fidelity checks passed.");

const processNotices=["Limited reading.","Article screening is not peer review; reported results do not establish strong causal evidence."];
const studyLimits="Preprint, not verified peer-reviewed evidence. Cross-sectional self-reports cannot establish causal mediation. The uncertainty calculation conflicts across source sections.";
ctx.qualifications=processNotices[0]+" "+studyLimits+" "+processNotices[1];
const fullQualifications=vm.runInContext("TEST.readingQualifications(qualifications)",ctx);
const fullDrawer=match(fullQualifications,"rv-full-qualifications");
assert(fullDrawer&&fullDrawer.tag==="details"&&!fullDrawer.open);
assert.equal(proseText(match(fullDrawer,"rv-prose")),ctx.qualifications,"Full approved qualification prose must be preserved exactly");
const upfront=visibleText(fullQualifications);
for(const sentence of processNotices)assert(!upfront.includes(sentence),"Generic process notice leaked into primary bullets");
for(const sentence of studyLimits.split(/(?<=\.) /))assert(upfront.includes(sentence),"Material study limitation or preprint status moved backstage");
ctx.qualifications=studyLimits;
const ordinaryQualifications=vm.runInContext("TEST.readingQualifications(qualifications)",ctx);
assert.equal(ordinaryQualifications.tag,"ul");assert.equal(proseText(ordinaryQualifications),studyLimits);
ctx.qualifications="Limited reading prevented assessment of the appendix. Article screening is not peer review in this specific validation design.";
assert.equal(proseText(vm.runInContext("TEST.readingQualifications(qualifications)",ctx)),ctx.qualifications,"Similar but nonidentical sentences must not be hidden");
console.log("Qualification disclosure, visible substantive limits, concise source action and unique version provenance passed.");
const qualifiedOriginal=JSON.parse(JSON.stringify(original));
qualifiedOriginal.reading.digest.limitation=processNotices[0]+" "+studyLimits+" "+processNotices[1];
ctx.selected=qualifiedOriginal;vm.runInContext("TEST.showPaper(selected)",ctx);
const renderedQualifications=match(paperContainer,"rv-qualifications");
assert(renderedQualifications,"Reading route must use the qualification disclosure");
assert.equal(proseText(match(match(renderedQualifications,"rv-full-qualifications"),"rv-prose")),qualifiedOriginal.reading.digest.limitation);
for(const sentence of processNotices)assert(!visibleText(renderedQualifications).includes(sentence));
for(const sentence of studyLimits.split(/(?<=\.) /))assert(visibleText(renderedQualifications).includes(sentence));
assert.equal(match(paperContainer,"rv-primary-link").href,original.reading.source_url);

for(const prefix of ["", "Preprint, not verified peer-reviewed evidence. "]){
 ctx.qualifications=prefix+processNotices.join(" ");
 const limited=vm.runInContext("TEST.readingQualifications(qualifications)",ctx);
 assert(visibleText(limited).includes("Reported results do not establish strong causal evidence."),"A process-only or preprint-only reading must retain visible causal caution");
 assert.equal(proseText(match(match(limited,"rv-full-qualifications"),"rv-prose")),ctx.qualifications);
}
ctx.qualifications=processNotices.join(" ")+" Cross-sectional self-reports cannot establish causal mediation.";
const causallyLimited=vm.runInContext("TEST.readingQualifications(qualifications)",ctx);
assert(visibleText(causallyLimited).includes("Cross-sectional self-reports cannot establish causal mediation."));
assert(!visibleText(causallyLimited).includes("Reported results do not establish strong causal evidence."),"Do not duplicate an already visible substantive causal limit");

// Public arrows must not depend on installed symbol fonts.
for(const source of ["app.js","lab-play.js","index.html","subscribe.html","styles.css","assets/feed.xsl","scripts/build_newsletter.py"])
 assert(!read(source).includes(String.fromCodePoint(0x2197)),"Font-dependent diagonal arrow in "+source);
const direction=vm.runInContext('TEST.make("span","issue-signal-icon","direction-mark")',ctx);
assert.equal(direction.textContent,"");
assert(direction.className.includes("ui-icon"));
assert(direction.children[0].children[0].attributes.href==="#icon-external");
assert.equal(direction.attributes["aria-hidden"],"true");
assert(styles.includes(".font-independent-arrow::before")&&styles.includes(".font-independent-arrow::after"),"Direction mark must be drawn without fonts");

// Cards are decorative; only safe article assets can reach the reader.
ctx.artRecord=db.find(r=>r.editorial_art?.thumbnail_src);
let thumb=vm.runInContext('TEST.editorialImage(artRecord,"card")',ctx);
assert.equal(thumb.src,ctx.artRecord.editorial_art.thumbnail_src);
assert.equal(thumb.alt,"");assert.equal(thumb.loading,"lazy");
for(const unsafe of ["https://untrusted.example/art.svg","assets/article-art/../secret.svg","javascript:alert(1)","data:image/svg+xml,bad"]){
 ctx.artRecord={...db[0],editorial_art:{kind:"editorial_illustration",src:unsafe,alt:"Not trusted"}};
 const rejected=vm.runInContext('TEST.editorialImage(artRecord,"card")',ctx);
 assert(rejected.src.startsWith("assets/reading-"),"Unsafe art path was accepted");
}
assert(html.includes('id="icon-focus"')&&html.includes('id="icon-search"'),"Icon sprite missing");
console.log("Article-specific asset safety, thumbnail loading, decorative alt and SVG icon tests passed.");
