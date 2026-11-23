/* The complete public library must render one consistent idea-first reading page. */
"use strict";
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path"),assert=require("node:assert/strict");
const ROOT=path.resolve(__dirname,"..");
// A clean checkout excludes generated SVGs. Build only editorial art, without
// acquisition or mutation of the public source readings, for every caller.
// Use the freshly accepted metadata in memory: committed payloads can refer to
// an older renderer whose ignored assets are absent in a clean checkout.
const builtArt=JSON.parse(require("node:child_process").execFileSync("python",["-c",
 'import json,sys; from pathlib import Path; sys.path.insert(0,"scripts"); from article_art import attach_art; rows=json.loads(Path("data/public-library.json").read_text()); attach_art(rows,Path.cwd()); print(json.dumps([r["editorial_art"] for r in rows]))'
],{cwd:ROOT,encoding:"utf8",maxBuffer:16*1024*1024}));
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
 constructor(tag){this.tag=tag;this.textContent="";this.className="";this.children=[];this.style={};this.hidden=false;this.open=false;this.attributes={};this.dataset={};this.parentNode=null}
 append(...els){for(const e of els){assert(e instanceof Element,"Non-element child");if(e.parentNode)e.parentNode.children=e.parentNode.children.filter(child=>child!==e);e.parentNode=this;this.children.push(e)}}
 replaceChildren(...els){for(const child of this.children)child.parentNode=null;this.children=[];this.textContent="";this.append(...els)}
 setAttribute(k,v){this.attributes[k]=v}
 getAttribute(k){return this.attributes[k]??null}
 addEventListener(_name,_callback){}
}
const paperContainer=new Element("div");
const libraryContainer=new Element("div"),libraryCount=new Element("div"),backlogContainer=new Element("div");
const inputs={"#search":{value:""},"#scope-filter":{value:"all"},"#topic-filter":{value:""},"#depth-filter":{value:"readable"},"#type-filter":{value:""}};
const doc={createElement:tag=>new Element(tag),createElementNS:(_ns,tag)=>new Element(tag),querySelector:q=>q==="#paper-content"?paperContainer:q==="#library-results"?libraryContainer:q==="#library-count"?libraryCount:q==="#backlog-coverage"?backlogContainer:inputs[q]||null};
const prefix=app.slice(0,app.lastIndexOf('$("[data-route]").forEach('));
assert(prefix.length>10000,"Unable to load application functions");
const ctx=vm.createContext({document:doc,URL,console,window:{scrollTo(){}}});
vm.runInContext(prefix+"\nconst TEST={showPaper,showLibrary,shortIdea,ideaInfo,processedIdea,matchesSourceType,renderBacklog,issueSourceShelfItem,readableSourceTitle,readingHeadline,readingKind,readingBasisName,editorialImage,make,S,readingParagraphs,sourceFields,readingBullets,sourceFamily,compactReading};",ctx);
const nodes=root=>[root,...root.children.flatMap(nodes)];
const match=(root,cls)=>nodes(root).find(n=>n.className.split(" ").includes(cls));
const matching=(root,cls)=>nodes(root).filter(n=>n.className.split(" ").includes(cls));
const textContent=root=>nodes(root).map(n=>n.textContent).filter(Boolean).join(" | ");
const proseText=root=>nodes(root).map(n=>n.textContent).filter(Boolean).join(" ").replace(/\s+/g," ").trim();
const hiddenBySection=node=>Boolean(node?.hidden||(node?.parentNode&&hiddenBySection(node.parentNode)));
const hasLayer=node=>Boolean(node&&match(node,"layer-trigger")&&node.children.some(child=>child.hidden));
// Previously published links must resolve to an honest pending-source view,
// not a fabricated one-paragraph reading when the full article was never read.
const pending={kind:"nonacademic",title:"Not-yet-reviewed commentary",url:"https://theconversation.com/a-source-pending-full-reading",source_quality:{decision:"awaiting_full_article_reading"}};
ctx.selected=pending;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(match(paperContainer,"rv-awaiting-reading"),"Missing transparent pending-source route");
assert(textContent(paperContainer).includes("A summary of this article is not yet available."),"Pending article falsely presented as analysis");
assert(!match(paperContainer,"rv-longform"),"RSS snippet must not be dressed up as an article reading");
assert.equal(match(paperContainer,"rv-source-title").textContent,pending.title);
const db=JSON.parse(read("data/public-library.json"));
assert.equal(builtArt.length,db.length,"Art generation must not change source membership");
db.forEach((r,i)=>{r.editorial_art=builtArt[i]});
assert(db.length>50,"Expected public, citation-screened library");
ctx.database=db;vm.runInContext("TEST.S.records=database",ctx);
let checked=0,edited=0,sourceOnly=0;
for(const r of db){
 ctx.selected=r;vm.runInContext("TEST.showPaper(selected)",ctx);
 const page=match(paperContainer,"rv-article");
 const headline=match(page,"rv-headline"),source=match(page,"rv-source-title");
 assert(page&&headline&&headline.tag==="h1","Missing primary insight heading for "+r.title);
 assert(headline.textContent.length>=4&&headline.textContent.length<=55&&headline.textContent.split(/\s+/).length<=10,"Headline overflows for "+r.title);
 if(!r.reading?.original_summary)assert(!/^(?:the authors|the researchers|this study|this paper|we found)\b/i.test(headline.textContent),"Paper-centred headline: "+r.title+" / "+headline.textContent);
 assert(source&&source.textContent===r.title.trim(),"Source title missing for "+r.title);
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
 if(r.editorial_art?.status!=="needs_review"){
 assert(art&&image&&image.src===r.editorial_art.src,"Article-specific illustration missing: "+r.title);
 assert(image.alt===r.editorial_art.alt&&image.alt.length>10,"Meaningful illustration alt missing");
 assert(fs.existsSync(path.join(ROOT,image.src)),"Illustration asset missing");
 assert(match(art,"story-visual-caption").textContent==="Editorial illustration","Art must be separate from evidence");
 }else assert(!art&&!image,"Review-required art must not use a generic fallback");
 const autogenerated=match(page,"automatic-evidence");
 const family=vm.runInContext("TEST.sourceFamily(selected)",ctx);
 assert.equal(page.getAttribute("data-source-family"),family);
 if(r.reading.source_version==="arxiv_preprint_v1"){
  assert.equal(match(page,"rv-source-version").textContent,"arXiv preprint v1");
 }
 assert.equal(match(page,"rv-dot").textContent,vm.runInContext("TEST.readingKind(selected)",ctx));
 assert(!match(page,"rv-evidence")&&!match(page,"rv-source-locator")&&!match(page,"rv-provenance"));
 const pageText=proseText(page);
 for(const leak of ["Source locators for this summary","Qualifications and unresolved issues","Source version identifier:",
   "No historical snapshot of the original publication was verified","extraction and semantic completeness are not verified",
   "AI source-check scope:","How hard a task feels, how many problems someone starts"])
  assert(!pageText.includes(leak),"Editorial process or filler leaked into a reading: "+r.title+" / "+leak);
 const digest=r.reading.digest;
 if(r.reading.original_summary){
   assert.equal(match(match(page,"rv-source"),"rv-primary-link").href,r.reading.source_url);
   assert(!autogenerated&&!match(page,"rv-original-figure"),"A checked source must not borrow older graphics");
   assert(!match(page,"rv-research-longform"),"Older discussions must not replace the checked version");
   if(r.visual?.kind==="reviewed_comparison"){
     const table=match(page,"reviewed-comparison-table");
     assert.equal(table.getAttribute("aria-label"),r.visual.description);
     for(const row of r.visual.rows)for(const cell of row)assert(textContent(table).includes(cell));
     assert.equal(match(match(page,"reviewed-evidence"),"rv-secondary-link").href,r.reading.source_url);
   }
   if(family==="research"){
     if(digest.finding&&r.reader_genre!=="proposal")assert(pageText.includes(digest.finding),"Finding omitted: "+r.title);
     if(digest.approach)assert(pageText.includes(digest.approach),"Study design omitted: "+r.title);
   }
 }
 if(family!=="research"){
  for(const cls of ["automatic-evidence","rv-original-figure","rv-context-grid","rv-source-excerpts","reviewed-evidence"])
   assert(!match(page,cls),"Unrelated research context leaked into "+r.title);
  assert(!pageText.includes("How it was studied"));
 }
 if(digest.status==="editorially_written_from_indexed_sections")edited++;else sourceOnly++;
 assert(match(page,"rv-source"),"Original citation must remain within reach");
 const overview=match(page,"rv-overview");
 if(overview)assert(hasLayer(overview),"Supporting context should open from the short overview");
 const excerpt=match(page,"rv-drawer");
 if(excerpt)assert(hiddenBySection(excerpt),"Raw passages should start in the optional Evidence view");
 if(digest.status==="journal_abstract_preview"){
  assert(!match(page,"rv-ai-notice"),"A publisher’s abstract must not be labeled as an AI summary");
  assert.equal(match(page,"rv-section-title").textContent,"From the published abstract");
 }else assert.equal(match(page,"rv-ai-notice").textContent,"AI-generated summary. AI can make mistakes.");
 assert.equal(page.getAttribute("data-reading-view"),"overview");
 assert(!match(page,"rv-panel-overview").hidden,"The finding and material limits must be available without a click");
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
assert.equal(matching(libraryContainer,"story-visual-card").length,db.filter(row=>row.editorial_art?.src&&row.editorial_art.status!=="needs_review").length,"Show every accepted card illustration and withhold unapproved ones");
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
assert.equal(matching(automatic,"auto-evidence-source").length,1,"A shared source belongs on the figure once");
assert(!match(automatic,"auto-evidence-n"),"Evidence headings should read without decorative numbers");
assert(!match(paperContainer,"rv-context-grid"),"Do not repeat all the visual evidence as text cards");
assert(textContent(automatic).includes("cannot establish a causal mechanism"));
// A future checked article can have older licensed extracts and a terse legacy snapshot.
const checkedReading={...future,title:"Two practice formats in one class",reading:{...future.reading,level:"full_text",
 methods:"One class tried two activities in consecutive weeks. Students used a tutor first and a quiz second.",
 findings:"The log counted practice sessions. Half the sessions included an answer to the opening question.",
 interpretation:"The authors suggest that some students opened the activity to look at the questions.",
 limitations:"Every student tried the tutor first, so practice and topic could explain the difference.",
 digest:{...future.reading.digest,status:"editorially_written_from_indexed_sections",editorial_basis:"publisher_full_article_paraphrased",finding_source:"editorial"}},
 analysis:{fulltext_url:"https://example.org/study",methods:"Older indexed paper section."}};
ctx.selected=checkedReading;vm.runInContext("TEST.showPaper(selected)",ctx);
const studyOverview=match(paperContainer,"rv-panel-overview"),account=match(studyOverview,"rv-study-account");
assert(account&&!hiddenBySection(account),"Full study account must be available on the first view");
for(const field of ["methods","findings","interpretation","limitations"])assert(proseText(account).includes(checkedReading.reading[field]),field);
assert(!match(studyOverview,"automatic-evidence")&&!proseText(account).includes("Older indexed paper section."));
assert(proseText(match(paperContainer,"rv-source-row")).includes("Based on the full article"));
const framework={...checkedReading,reader_genre:"conceptual",reading:{...checkedReading.reading,findings:"",
 digest:{...checkedReading.reading.digest,status:"conceptual_framework",finding:"",finding_source:"none"}}};
ctx.selected=framework;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(match(paperContainer,"rv-study-account"));
assert(!proseText(match(paperContainer,"rv-panel-overview")).includes("What the researchers observed"));
assert(proseText(match(paperContainer,"rv-panel-overview")).includes("What the framework proposes"));
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
   interpretation:"The authors suggest checking whether this relationship holds without assistance.",limitation:"Original limitation.",
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
assert.equal(match(originalPage,"rv-headline").textContent,vm.runInContext("TEST.readingHeadline(selected)",ctx));
assert.equal(proseText(match(match(originalPage,"rv-overview"),"rv-prose")),originalDigest.explain);
assert(textContent(match(originalPage,"rv-claim")).includes(originalDigest.finding),"Original reported finding missing from primary prose");
assert(textContent(match(originalPage,"rv-context-grid")).includes(originalDigest.approach));
assert(textContent(match(originalPage,"rv-context-grid")).includes(originalDigest.limitation));
assert(textContent(match(originalPage,"rv-take")).includes(originalDigest.interpretation),"Original interpretation must be shown separately");
assert(!textContent(originalPage).includes("Interpretation and implications"));
assert(!textContent(originalPage).includes(original.reading.review_scope));
assert(textContent(match(originalPage,"rv-head")).includes(original.reading.source_version),"Exact checked version must be visible up front");
assert(!match(originalPage,"automatic-evidence"),"An older machine visual must not substitute for the checked summary");
assert(!match(originalPage,"rv-research-longform"),"Do not mix older long-form notes into the original summary");
const excerpts=match(originalPage,"rv-source-excerpts");
assert(excerpts&&hiddenBySection(excerpts),"Machine excerpts must remain in the optional Evidence view");
assert(textContent(excerpts).includes("Source excerpts"));
for(const field of ["methods","results","discussion","limitations"])
 assert(textContent(excerpts).includes(original.analysis[field]),"Unchanged machine "+field+" must be retained separately");
for(const field of ["methods","findings","interpretation","limitations"])
 assert(!textContent(excerpts).includes(original.reading[field]),"Original prose mislabeled as machine excerpts: "+field);
const visibleText=root=>root.hidden?"":[root.textContent,...root.children.map(visibleText)].filter(Boolean).join(" | ");
assert(!visibleText(originalPage).includes("machine results sentinel"),"Raw machine output leaked into primary reading");
assert(!textContent(originalPage).includes("Stale unreviewed"),"Older claims must not override the checked source version");
assert(!match(originalPage,"rv-evidence")&&!match(originalPage,"rv-source-locator"));
const citation=match(originalPage,"rv-source"),sourceLink=match(citation,"rv-primary-link");
assert.equal(sourceLink.href,original.reading.source_url,"The original link opens the exact source used");
assert(!textContent(citation).includes(originalDigest.basis));
assert(!textContent(citation).includes(original.reading.notice));
const journalLink=matching(citation,"rv-secondary-link").find(n=>n.textContent.includes("Related journal publication"));
assert(journalLink);
assert.equal(journalLink.href,"https://doi.org/"+original.reading.related_journal_doi);
assert(!textContent(citation).includes("Reviewed full article")&&!textContent(citation).includes("Full-text sections"),"Original summary must not be labeled as machine extraction or publisher full-article review");
assert.equal(JSON.stringify(original),originalBefore,"Rendering must never rewrite the machine analysis or original summary");
const readingWorkspace=match(originalPage,"rv-reading-workspace"),articleNavigation=match(originalPage,"rv-section-controls"),readingLayout=match(originalPage,"rv-layout"),originalProse=proseText(readingLayout);
assert(readingWorkspace&&readingWorkspace.children[0]===articleNavigation&&readingWorkspace.children[1]===readingLayout,"The chapter rail and reading content must share one workspace");
assert.equal(articleNavigation.tag,"nav");assert.equal(articleNavigation.id,"article-section");
assert.equal(articleNavigation.dataset.activeSection,"overview");
assert(!nodes(articleNavigation).some(node=>node.tag==="select"),"Chapter choices must remain visible instead of a duplicate select control");
const chapterButtons=matching(articleNavigation,"rv-section-tab");
assert.equal(chapterButtons.length,4,"Every available chapter needs a visible destination");
for(const [index,button] of chapterButtons.entries()){
 assert.equal(match(button,"rv-section-number").textContent,String(index+1).padStart(2,"0"));
 assert(match(button,"rv-section-label").textContent&&match(button,"rv-section-description").textContent,"Chapter choices need a readable label and short description");
 assert(!button.hidden,"Chapter options must remain visible on narrow layouts");
}
const overviewPanel=match(originalPage,"rv-panel-overview"),analysisPanel=match(originalPage,"rv-analysis"),evidencePanel=match(originalPage,"rv-evidence-panel"),sourcePanel=match(originalPage,"rv-sidebar");
assert(!overviewPanel.hidden&&analysisPanel.hidden&&evidencePanel.hidden&&sourcePanel.hidden,"Overview is the only default reading view");
assert(visibleText(originalPage).includes(originalDigest.finding)&&visibleText(originalPage).includes(originalDigest.limitation),"The finding and material limit must be visible together without opening a layer");
const analysisTab=matching(originalPage,"rv-section-tab").find(button=>button.getAttribute("data-reading-view")==="analysis");
analysisTab.onclick();
assert(overviewPanel.hidden&&!analysisPanel.hidden&&evidencePanel.hidden&&sourcePanel.hidden,"Analysis replaces the overview instead of adding another long section");
assert.equal(articleNavigation.dataset.activeSection,"analysis");assert.equal(analysisTab.getAttribute("aria-pressed"),"true");
assert.equal(match(articleNavigation,"rv-section-position").textContent,"02 / 04 · Discussion");
assert(visibleText(originalPage).includes(originalDigest.interpretation),"Analysis retains the full original interpretation");
chapterButtons.find(button=>button.getAttribute("data-reading-view")==="evidence").onclick();
assert(evidencePanel.hidden===false&&analysisPanel.hidden&&sourcePanel.hidden,"The Evidence chapter must reveal Evidence only");
assert(visibleText(originalPage).includes(original.analysis.methods),"The source reader must remain reachable from the Evidence view");
chapterButtons.find(button=>button.getAttribute("data-reading-view")==="source").onclick();
assert(!sourcePanel.hidden&&evidencePanel.hidden&&analysisPanel.hidden&&overviewPanel.hidden,"The Source chapter must reveal Source only");
assert(!visibleText(originalPage).includes(original.reading.review_scope),"Detailed process notes belong in the optional provenance card");
match(originalPage,"rv-read-all").onclick();
assert([overviewPanel,analysisPanel,evidencePanel,sourcePanel].every(panel=>!panel.hidden),"Read all must reveal every major section");
assert.equal(articleNavigation.dataset.activeSection,"all");
assert.equal(match(articleNavigation,"rv-section-position").textContent,"All 4 sections");
assert(chapterButtons.every(button=>button.getAttribute("aria-pressed")==="false"),"Read all must clear the single-chapter selection");
assert.equal(proseText(readingLayout),originalProse,"Changing chapters must not duplicate, delete or rewrite the original content");
chapterButtons.find(button=>button.getAttribute("data-reading-view")==="overview").onclick();
assert(!overviewPanel.hidden&&[analysisPanel,evidencePanel,sourcePanel].every(panel=>panel.hidden),"Returning to Overview must restore a compact page");
assert.equal(vm.runInContext("TEST.shortIdea(selected,200)",ctx),original.title);
assert.equal(vm.runInContext("TEST.processedIdea(selected)",ctx),original.title);
assert.equal(vm.runInContext("TEST.ideaInfo(selected).label",ctx),"Research");
ctx.original=original;
vm.runInContext("TEST.S.records=[original];TEST.showLibrary()",ctx);
const originalCard=match(libraryContainer,"library-story");
assert(textContent(originalCard).includes(original.title),"Use the shorter bibliographic title when an idea exceeds the display limit");
assert(textContent(originalCard).includes("Preprint"));
assert(!textContent(originalCard).includes(original.reading.review_scope));
assert(!textContent(originalCard).includes("machine results sentinel"));
inputs["#search"].value="checking whether this relationship holds";
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
assert(textContent(backlogContainer).includes("1 of 1 scholarly papers"),"Reader coverage counts the public research collection independently of acquisition status");
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
assert(textContent(match(paperContainer,"rv-source-row")).includes("Published article"));
assert(!textContent(match(paperContainer,"rv-source")).includes("Related journal DOI"),"One source DOI must not be relabeled as a separate journal version");

// Checked graphics bind to the stated source; a later source/version must not
// inherit a visual merely because the DOI is unchanged.
const comparisonFixture=JSON.parse(read('data/reviewed-visuals.json')).visuals[0];
const withComparison=JSON.parse(JSON.stringify(publisherSummary));
withComparison.doi=comparisonFixture.doi;
withComparison.visual=comparisonFixture;
Object.assign(withComparison.reading,{
 original_summary_id:comparisonFixture.reading_id,
 source_url:comparisonFixture.source.url,source_version:comparisonFixture.source.version,
 source_sha256:comparisonFixture.source.sha256
});
ctx.selected=withComparison;vm.runInContext('TEST.showPaper(selected)',ctx);
assert(match(paperContainer,'reviewed-evidence'),'Exact checked source should display its comparison');
assert.equal(match(paperContainer,'reviewed-comparison-table').getAttribute('aria-label'),comparisonFixture.description);
for(const key of ['source_url','source_version','source_sha256','original_summary_id']){
 const changed=JSON.parse(JSON.stringify(withComparison));changed.reading[key]+='-changed';
 ctx.selected=changed;vm.runInContext('TEST.showPaper(selected)',ctx);
 assert(!match(paperContainer,'rv-artwork'),'Changed source cannot inherit an old comparison: '+key);
}

const conceptualOriginal={...original,research_type:"conceptual_framework"};
ctx.selected=conceptualOriginal;vm.runInContext("TEST.showPaper(selected)",ctx);
assert.equal(match(paperContainer,"rv-headline").textContent,vm.runInContext("TEST.readingHeadline(selected)",ctx));
assert.equal(match(paperContainer,"rv-section-title").textContent,"What the paper proposes");
assert(vm.runInContext("TEST.ideaInfo(selected).label",ctx).includes("Conceptual paper"));
const conceptualWithoutFinding={...conceptualOriginal,
 framework_notes:{idea:"Legacy framework idea sentinel.",stages:["First: Legacy framework stage sentinel."]},
 reading:{...conceptualOriginal.reading,findings:"",digest:{...conceptualOriginal.reading.digest,finding:""}}
};
ctx.selected=conceptualWithoutFinding;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(textContent(paperContainer).includes(originalDigest.idea),"The original proposal remains accessible");
assert(textContent(match(paperContainer,"rv-claim")).includes(originalDigest.interpretation),"Keep the original proposal without implying a measured effect");
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
 assert(textContent(shelfItem).includes("Preprint"),"Identify the frozen working paper even after a journal version appears");
 assert(!textContent(shelfItem).includes("Publisher version of record"));
 assert(!textContent(shelfItem).includes(issueOriginal.review_label));
 const checkedLink=match(shelfItem,"issue-source-checked-link");
 assert.equal(checkedLink.href,original.reading.source_url);
 const publicationLink=match(shelfItem,"issue-source-publication-link");
 assert.equal(publicationLink.href,"https://doi.org/"+original.reading.related_journal_doi);
 assert(!textContent(shelfItem).includes(original.reading.review_scope));
 assert(!match(shelfItem,"rv-source-locator"));
}
ctx.unsafeShelf={...issueOriginal,source_url:"javascript:invalid()",source_version:'Working paper <svg onload="invalid()">'};
const safeShelf=vm.runInContext("TEST.issueSourceShelfItem(unsafeShelf,1)",ctx);
assert(!match(safeShelf,"issue-source-checked-link"),"Weekly shelf must reject unsafe checked-source links");
assert(!textContent(safeShelf).includes("<svg"));
assert(!nodes(safeShelf).some(n=>["svg","script","img"].includes(n.tag)),"Weekly provenance must render as plain text");
ctx.legacyShelf={id:"synthetic-legacy",title:"Synthetic older source",url:"https://example.org/legacy",venue:"Synthetic Journal"};
const legacyShelf=vm.runInContext("TEST.issueSourceShelfItem(legacyShelf,2)",ctx);
assert(!match(legacyShelf,"issue-source-review")&&!match(legacyShelf,"issue-source-version"),"Legacy shelf entries must not acquire an unverified AI review label");
assert(nodes(legacyShelf).some(node=>node.href===ctx.legacyShelf.url&&node.textContent===ctx.legacyShelf.title));
vm.runInContext("TEST.S.records=database",ctx);

// A news explainer can share a research contribution with the paper it covers.
// An edition citing the news report must still open that report.
ctx.primary={doi:"10.0000/parent",kind:"scholarly",title:"Review of AI tutoring",reading:{level:"abstract"}};
ctx.paired={url:"https://example.org/coverage",title:"Districts debate AI tutoring",kind:"nonacademic",
 reader_genre:"reporting",reading:{level:"curated"},companion_to:ctx.primary.doi};
ctx.citedReport={id:ctx.paired.url,url:ctx.paired.url,title:ctx.paired.title,kind:"nonacademic",reader_genre:"reporting"};
vm.runInContext("TEST.S.records=[primary];TEST.S.companions=[paired]",ctx);
const reportShelf=vm.runInContext("TEST.issueSourceShelfItem(citedReport,0)",ctx);
assert.equal(match(reportShelf,"card-type").textContent,"News report");
assert(nodes(reportShelf).some(node=>node.href===ctx.paired.url));
assert(nodes(reportShelf).some(node=>node.href==="#paper/"+encodeURIComponent(ctx.paired.url)));
vm.runInContext("TEST.showPaper(primary)",ctx);
const coverage=match(paperContainer,"rv-paired-coverage");
assert(nodes(coverage).some(node=>node.href==="#paper/"+encodeURIComponent(ctx.paired.url)&&node.textContent===ctx.paired.title));
assert(nodes(coverage).some(node=>node.href===ctx.paired.url));
vm.runInContext("TEST.showPaper(paired)",ctx);
const study=match(paperContainer,"rv-paired-publication");
assert(nodes(study).some(node=>node.href==="#paper/"+encodeURIComponent(ctx.primary.doi)&&node.textContent===ctx.primary.title));
vm.runInContext("TEST.S.records=database;TEST.S.companions=[]",ctx);

const safeSummary=JSON.parse(JSON.stringify(original));
safeSummary.reading.source_version='Working paper <svg onload="invalid()">';
safeSummary.reading.evidence.finding=[{section:'Results <img src=x onerror="invalid()">',page:9,paragraph:1}];
safeSummary.analysis.fulltext_url="javascript:invalid()";
for(const unsafe of ["javascript:invalid()","http://example.org/unsecured","https://user:password@example.org/source"]){
 safeSummary.reading.source_url=unsafe;
 ctx.selected=safeSummary;vm.runInContext("TEST.showPaper(selected)",ctx);
 assert(!match(match(paperContainer,"rv-source"),"rv-primary-link"),"Unsafe checked-source link must not be rendered: "+unsafe);
 assert(!matching(match(paperContainer,"rv-source-excerpts"),"rv-secondary-link").length,"Unsafe machine-source link must not be rendered");
 assert(!match(paperContainer,"rv-evidence")&&!textContent(paperContainer).includes(safeSummary.reading.evidence.finding[0].section));
 assert(!nodes(match(paperContainer,"rv-head")).some(n=>["svg","script"].includes(n.tag)),"Source-version text must never become markup");
}
const noMachine={...original,analysis:undefined,abstract_text:undefined};
ctx.selected=noMachine;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(!match(paperContainer,"rv-source-excerpts"),"Do not fabricate a machine-excerpt drawer when no extraction exists");
assert(!match(paperContainer,"rv-evidence"),"Internal locators must not create an empty Evidence tab");

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
 assert(match(paperContainer,"rv-claim")||match(paperContainer,"rv-study-account"),"Important specific findings should be immediately readable");
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
 assert(!textContent(paperContainer).includes("Main finding"),"A research proposal must not present a measured finding");
}
const title=vm.runInContext('TEST.shortIdea({kind:"scholarly",title:"A Study of Attention",reading:{digest:{idea:"AI use can support attention.",status:"editorially_written_from_indexed_sections"}}},100)',ctx);
assert.equal(title,"A Study of Attention");
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
assert(!commentaryText.includes(commentary.reading.temporal_notice));
for(const value of Object.values(lenses))assert(commentaryText.includes(value),"Missing commentary lens: "+value);
for(const forbidden of ["How it was studied","Study approach","Main finding","Reported finding","Methods as indexed","Stale unreviewed"])
 assert(!commentaryText.includes(forbidden),"Commentary borrowed scholarly content: "+forbidden);
assert(!match(paperContainer,"rv-context-grid"));assert(!match(paperContainer,"automatic-evidence"));
assert(!match(paperContainer,"rv-source-excerpts"),"Checked commentary must not inherit an indexed-source reader");
assert.equal(vm.runInContext("TEST.sourceFields(selected).length",ctx),0,"Commentary must not expose stale scholarly or publisher fields");
assert(!match(paperContainer,"rv-source-locator"));
assert.equal(match(paperContainer,"rv-primary-link").href,commentary.url);
assert(!commentaryText.includes(commentary.reading.review_scope));
const auditFields=[commentary.reading.review_scope,commentary.reading.quality_note,"not an original-week snapshot"];
assert(commentaryText.includes("Synthetic policy author"));
for(const value of [commentary.reading.quality_note,commentary.reading.notice,commentary.reading.review_scope])assert(!commentaryText.includes(value));
ctx.commentary=commentary;vm.runInContext("TEST.S.records=[commentary];TEST.showLibrary()",ctx);
assert.equal(match(libraryContainer,"card-type").textContent,"Analysis");
for(const value of auditFields)assert(!textContent(libraryContainer).includes(value));
const commentarySource={id:commentary.url,title:commentary.title,url:commentary.url,...commentary.reading};
ctx.commentarySource=commentarySource;
const commentaryShelf=vm.runInContext("TEST.issueSourceShelfItem(commentarySource,0)",ctx);
assert(textContent(commentaryShelf).includes("Synthetic policy author"));
for(const value of auditFields)assert(!textContent(commentaryShelf).includes(value));
assert(!match(commentaryShelf,"rv-source-locator"));
// Missing optional metadata or invalid locators must not create fabricated prose.
const minimalCommentary=JSON.parse(JSON.stringify(commentary));
for(const key of ["quality_note","temporal","temporal_notice","notice","review_scope","source_version"])delete minimalCommentary.reading[key];
minimalCommentary.reading.digest.longform={thesis:lenses.thesis};
minimalCommentary.reading.evidence={thesis:[null,{section:""},{section:"Synthetic argument",page:-1,paragraph:0}]};
ctx.selected=minimalCommentary;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(!/undefined|\[object Object\]|How it was studied/.test(textContent(paperContainer)));
assert(!match(paperContainer,"rv-source-locator"));
// A screened preprint remains scholarly but never silently becomes peer reviewed.
const preprint=JSON.parse(JSON.stringify(original));
preprint.reading.notice="Preprint, not verified peer-reviewed evidence. Article screening is not peer review.";
preprint.reading.quality_note="Acceptable for a qualified reading; no strong causal claim.";
ctx.selected=preprint;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(!textContent(paperContainer).includes(preprint.reading.notice));
assert(textContent(paperContainer).includes("How it was studied"));
assert(textContent(paperContainer).includes(originalDigest.finding));
assert(!match(paperContainer,"rv-evidence"));
ctx.preprint=preprint;vm.runInContext("TEST.S.records=[preprint];TEST.showLibrary()",ctx);
assert(textContent(libraryContainer).includes("Preprint")&&!textContent(libraryContainer).includes(preprint.reading.notice));
ctx.preprintSource={id:preprint.doi,title:preprint.title,url:preprint.url,...preprint.reading};
assert(!textContent(vm.runInContext("TEST.issueSourceShelfItem(preprintSource,0)",ctx)).includes(preprint.reading.notice));
// Optional integration input is generated by the backend's synthetic receipt tests.
if(process.env.CHECKED_RENDER_FIXTURE){
 const fixture=JSON.parse(fs.readFileSync(process.env.CHECKED_RENDER_FIXTURE,"utf8"));
 ctx.backendShelf=fixture.shelf;
 const backendShelf=vm.runInContext("TEST.issueSourceShelfItem(backendShelf,0)",ctx);
 for(const key of ["review_scope","review_label","temporal_notice","quality_note"])if(fixture.shelf[key])assert(!textContent(backendShelf).includes(fixture.shelf[key]));
 assert(!match(backendShelf,"rv-source-locator"));
 for(const candidate of [fixture.accepted,fixture.modified_after_original_week]){
  ctx.selected=candidate;vm.runInContext("TEST.showPaper(selected)",ctx);
  assert(!textContent(paperContainer).includes(candidate.reading.notice));
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
assert(sourceSections.length>=3,"All available source sections need independent navigation");
assert(sourceSections.every((section,i)=>section.tag==="section"&&section.hidden===(i!==0)),"One source section begins visible rather than a wall of text");
const methodProse=match(sourceSections[0],"rv-prose");
assert(methodProse.children.length>3,"Long source text must be split into readable paragraphs");
assert.equal(methodProse.children.map(p=>p.textContent).join(" "),longPassage.trim(),"Formatting must preserve every source word");
assert(textContent(sourceReader).includes("Final source detail must remain visible."),"The complete indexed section must not be clipped to reading-card length");
assert(match(sourceReader,"rv-reader-contents"),"Source sections need navigation");
const controls=matching(sourceReader,"rv-reader-control");
controls[0].onclick();assert(sourceSections.every(s=>!s.hidden),"Read all source sections failed");
controls[1].onclick();assert(sourceSections.every((s,i)=>s.hidden===(i!==0)),"One-section source view failed");
matching(sourceReader,"rv-reader-jump")[1].onclick();assert(!sourceSections[1].hidden,"Section navigation must reveal the selected source section");
assert(sourceSections[0].hidden,"Section navigation should hide the prior section");
assert.equal(matching(sourceReader,"rv-reader-jump")[1].getAttribute("aria-pressed"),"true");
assert(!match(paperContainer,"rv-coverage-table"),"Source access should not read like a processing dashboard");
ctx.selected=unknown;vm.runInContext("TEST.showPaper(selected)",ctx);
for(const placeholder of ["Method details are not clear enough", "A source-specific limitation could not be verified"])
 assert(!textContent(paperContainer).includes(placeholder),"Generic placeholder must not substitute for a source-specific appraisal");
assert(!match(paperContainer,"rv-source-excerpts"),"An unavailable excerpt should not generate an empty chapter");
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

// An unsummarized journal opinion retains its real abstract, explicitly attributed.
ctx.selected={kind:"scholarly",reader_genre:"opinion",title:"Teaching students to question an AI answer",url:"https://example.org/opinion",
 abstract_text:"The author asks how teachers can make room for dissent when students use AI.",
 reading:{level:"abstract",digest:{status:"journal_abstract_preview",editorial_basis:"abstract"}}};
vm.runInContext("TEST.showPaper(selected)",ctx);
assert.equal(match(paperContainer,"rv-section-title").textContent,"From the published abstract");
assert(textContent(match(paperContainer,"rv-panel-overview")).includes(ctx.selected.abstract_text));
assert(!match(paperContainer,"rv-ai-notice")&&!match(paperContainer,"rv-context-grid"));
assert.equal(match(paperContainer,"rv-primary-link").href,ctx.selected.url);
const excerptLead="Researchers examined how workers use chatbots to plan their tasks.";
ctx.selected={kind:"scholarly",title:"Chatbots at work",abstract_text:excerptLead,reading:{level:"abstract",digest:{
 status:"automatically_condensed_source_text",explain:excerptLead,explain_source:"abstract_excerpt"}}};
vm.runInContext("TEST.showPaper(selected)",ctx);
const leadSection=match(paperContainer,"rv-summary-idea");
assert.equal(leadSection.children[0].textContent,"From the abstract");
assert.equal(leadSection.children[1].textContent,excerptLead);
// Older signed records may contain a clean summary and a second audit-prefixed
// digest. Preserve the source-specific limit while excluding internal notes.
const qualifiedOriginal=JSON.parse(JSON.stringify(original));
const studyLimit="Cross-sectional self-reports cannot establish causal mediation.";
qualifiedOriginal.original_reading={summary:{limitation:studyLimit}};
qualifiedOriginal.reading.digest.limitation="Limited reading. "+studyLimit;
ctx.selected=qualifiedOriginal;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(visibleText(paperContainer).includes(studyLimit));
assert(!textContent(paperContainer).includes("Limited reading."));
assert.equal(match(paperContainer,"rv-primary-link").href,original.reading.source_url);
const genericInterpretation={...qualifiedOriginal,reading:{...qualifiedOriginal.reading,digest:{...qualifiedOriginal.reading.digest,interpretation:"Different tasks measure different things."}}};
ctx.selected=genericInterpretation;vm.runInContext("TEST.showPaper(selected)",ctx);
assert(!textContent(paperContainer).includes(genericInterpretation.reading.digest.interpretation));
assert(!matching(paperContainer,"rv-section-tab").some(button=>button.getAttribute("data-reading-view")==="analysis"));
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
 assert.equal(rejected,null,"Unsafe art must not fall back to repeated topic art");
}
ctx.artRecord={...db[0],editorial_art:{...db[0].editorial_art,status:"needs_review"}};
assert.equal(vm.runInContext('TEST.editorialImage(artRecord,"card")',ctx),null,"Flagged art must be omitted even if a stale src remains");
ctx.artRecord={...db[0],editorial_art:undefined};
assert.equal(vm.runInContext('TEST.editorialImage(artRecord,"reading")',ctx),null,"Missing art must not silently reuse a topic cover");
assert(html.includes('id="icon-focus"')&&html.includes('id="icon-search"'),"Icon sprite missing");
console.log("Article-specific asset safety, thumbnail loading, decorative alt and SVG icon tests passed.");

// Headings describe the reading; raw evidence stays in the body. Test both
// old committed payloads and future records without relying on a DOI allowlist.
const statisticalHeading=/\b(?:p|r|b|t|f|se|sd|cfi|rmsea)\s*(?:\([^)]*\))?\s*[=<>≤≥]|[βχ]\s*[=<>]/i;
const obsoleteLabels=/RESULT FROM (?:FULL TEXT|ABSTRACT)|RESEARCH TOPIC \/|EDITORIAL TAKEAWAY \/|NOT AN ESTABLISHED FINDING|SOURCE-DERIVED RESULT|PERSPECTIVE \/ ATTRIBUTED/;
for(const row of db){
 ctx.selected=row;
 const heading=vm.runInContext('TEST.readingHeadline(selected)',ctx);
 assert.equal(vm.runInContext('TEST.shortIdea(selected,12)',ctx),heading,"Card titles must not clip a qualifier");
 assert.equal(vm.runInContext('TEST.processedIdea(selected)',ctx),heading,"Every heading surface needs the same policy");
 assert(!statisticalHeading.test(heading),"Statistical extract leaked into heading: "+row.title);
 assert(!/(?:…|\.\.\.)$/.test(heading),"Headline was truncated");
 if(row.display_headline){
  assert.equal(heading,row.display_headline,'Use the curated headline on article and card');
  assert(heading.length<=55&&heading.split(/\s+/).length<=10,'Edited headlines must fit a reading card');
 }else if(row.reading?.digest?.status==='automatically_condensed_source_text')
  assert.equal(heading,vm.runInContext('TEST.readableSourceTitle(selected)',ctx),'Unedited readings should retain their source title');
 vm.runInContext('TEST.showPaper(selected)',ctx);
 assert.equal(match(paperContainer,'rv-headline').textContent,heading);
 assert(!obsoleteLabels.test(textContent(paperContainer)),"Internal evidence label leaked into reader");
 assert(['Research','Research review','Research proposal','Journal editorial','Commentary','Conceptual paper','Product guide','Opinion','News report','Analysis'].includes(vm.runInContext('TEST.ideaInfo(selected).label',ctx)));
}
const genreCases=[
 ["editorial","scholarly",["nonacademic","opinion"]],["reporting","nonacademic",["nonacademic","reporting"]],
 ["review","scholarly",["scholarly"]],["guide","nonacademic",["nonacademic","guide"]],["analysis","nonacademic",["nonacademic","analysis"]]
];
for(const [reader_genre,kind,expected] of genreCases){
 ctx.selected={kind,reader_genre};
 for(const filter of ["scholarly","nonacademic","reporting","opinion","analysis","guide"]){
  ctx.filter=filter;
  assert.equal(vm.runInContext("TEST.matchesSourceType(selected,filter)",ctx),expected.includes(filter));
 }
}
const tutoring=db.find(row=>row.title.startsWith('Human tutoring, generative AI tutoring'));
assert(tutoring,'The tutoring comparison should remain discoverable by original title');
ctx.selected=tutoring;
assert.equal(vm.runInContext('TEST.readingHeadline(selected)',ctx),'Do students keep trying after AI tutoring?');
vm.runInContext('TEST.showPaper(selected)',ctx);
assert.equal(match(paperContainer,'rv-source-title').textContent,tutoring.title);
assert.equal(match(paperContainer,'rv-source-authors').textContent,tutoring.authors.join(', '));
assert.equal(match(paperContainer,'rv-byline-link').href,tutoring.reading.original_summary?tutoring.reading.source_url:tutoring.url);
const editorialRecord=db.find(row=>row.reading?.research_type==='editorial');
if(editorialRecord){
 ctx.selected=editorialRecord;vm.runInContext('TEST.showPaper(selected)',ctx);
 assert.equal(match(paperContainer,'rv-section-title').textContent,'The editorial’s argument');
 assert(!textContent(paperContainer).includes('How it was studied'),'An editorial is not an empirical study');
}
const rawStats='In contrast, cognitive load was negatively correlated with AI Literacy ( r = −0.361, p < 0.01), self-reported Complex Problem-Solving Skills ( r = −0.368, p < 0.01), and Systematic Thinking Skills ( r = −0.271, p < 0.01).';
const headlineFixture={kind:'scholarly',title:'AI literacy, cognitive load, and problem-solving skills',doi:'10.0000/future-headline',reading:{level:'full_text',digest:{status:'automatically_condensed_source_text',idea:rawStats,finding:rawStats,finding_source:'full_text'}}};
ctx.selected=headlineFixture;vm.runInContext('TEST.showPaper(selected)',ctx);
assert.equal(match(paperContainer,'rv-headline').textContent,headlineFixture.title);
assert(textContent(match(paperContainer,'rv-content')).includes(rawStats),'The fix must preserve exact statistics in the findings');
for(const bad of [rawStats, "AI literacy and cognitive load were correlated (ρ = −0.36).", "A group difference was found (χ²(1) = 4.8).", "The model explained variance (R^2 = .21).",'A long statement '.repeat(25)+'with a necessary final qualification.','A promising result, but…','Results: A result detached from its context.']){
 ctx.selected={...headlineFixture,reading:{...headlineFixture.reading,digest:{...headlineFixture.reading.digest,status:'editorially_written_from_indexed_sections',idea:bad}}};
 assert.equal(vm.runInContext('TEST.readingHeadline(selected)',ctx),headlineFixture.title,'Unsafe edited candidate must fall back intact');
}
const completeTitle='The relationship between '+('a named construct and ').repeat(16)+'the final qualifying study population';
ctx.selected={...headlineFixture,title:completeTitle};
assert.equal(vm.runInContext('TEST.shortIdea(selected,30)',ctx),'Read the original article','Legacy source links must not clip a long source title or drop its final qualifier');
for(const source of ['abstract','full_text']){
 const mixed={...headlineFixture,reading:{...headlineFixture.reading,digest:{...headlineFixture.reading.digest,finding_source:source}}};
 ctx.selected=mixed;vm.runInContext('TEST.showPaper(selected)',ctx);
 const rowText=textContent(match(paperContainer,'rv-source-row'));
 assert(rowText.includes(source==='abstract'?'Based on the abstract':'Full-text sections'),'Finding basis must remain visible independently of headline');
 assert.equal(vm.runInContext('TEST.ideaInfo(selected).label',ctx),'Research');
}
ctx.selected={...headlineFixture,research_type:'conceptual_framework',reading:{level:'abstract',digest:{idea:'A proposed model',finding:'',status:'conceptual_framework'}}};
vm.runInContext('TEST.showPaper(selected)',ctx);
assert.equal(vm.runInContext('TEST.ideaInfo(selected).label',ctx),'Conceptual paper');
assert(textContent(paperContainer).includes('What the paper proposes'),'Conceptual work must remain distinct from measured findings');
assert(!textContent(match(paperContainer,'rv-content')).includes('What the study reports'));
ctx.selected={kind:'nonacademic',title:'A product focus guide',reading:{level:'curated',digest:{longform:{source_depth:'product_documentation'}}}};
assert.equal(vm.runInContext('TEST.ideaInfo(selected).label',ctx),'Product guide');
console.log('Reader-oriented labels and whole-corpus heading safeguards passed: no raw results, clipped qualifiers, or lost source-depth distinctions.');
