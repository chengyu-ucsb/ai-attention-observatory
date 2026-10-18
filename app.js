"use strict";
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const state = {library: [], weekly: null, runs: [], view: "weekly", search:"", topic:"", type:""};
const lanes = ["AI & cognition","Fragmentation","Interventions","Technology & society"];
const laneShort = {"AI & cognition":"AI & cognition","Fragmentation":"Fragmentation","Interventions":"Interventions","Technology & society":"Technology & society"};
function el(tag, cls, text) { const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=String(text); return e; }
function add(parent,...children) { children.forEach(child=>{if(child)parent.append(child)}); return parent; }
function fmtDate(s) { if(!s)return "Undated";const d=new Date(s.slice(0,10)+"T12:00:00Z");return Number.isNaN(d.valueOf())?"Undated":d.toLocaleDateString("en-US",{timeZone:"UTC",year:"numeric",month:"short",day:"numeric"}); }
function recordId(x){return String(x.doi||x.url||x.title);}
function preview(x){return x.analysis?.key_idea||x.preview||"Only the citation is available; no substantive synopsis has been verified.";}
function tag(text,kind){return el("span","chip"+(kind?" "+kind:""),text);}
function recordById(id){return state.library.find(x=>recordId(x)===id);}
function sourceDate(x){return [fmtDate(x.published),x.venue].filter(Boolean).join("  ·  ");}
function validUrl(url){try{const u=new URL(url);return u.protocol==="https:"?url:null}catch{return null}}
function dateValue(x){return x.published&&/^\d{4}/.test(x.published)?x.published:"";}
function isNew(x){return !!x.first_seen&&state.weekly?.run?.mode!=="curated-starter"&&x.first_seen===state.weekly?.run?.date;}
function card(x,featured=false){
 const article=el("article",featured?"story story-featured":"story");
 const top=el("div","story-top"); add(top,tag(x.lane||"Research","topic"),tag(x.kind==="scholarly"?"Research": "Perspective","kind"));
 const title=el("button","story-title",x.title); title.type="button";title.addEventListener("click",()=>navigate("read",recordId(x)));
 const meta=el("p","meta",sourceDate(x));
 const p=el("p","story-summary",preview(x).slice(0,featured?390:280));
 const foot=el("div","story-foot"); add(foot,tag(x.analysis?"Full-text sections":x.curated?"Curated starter":"Metadata only",x.analysis?"verified":""));
 const go=el("button","text-link","Read the research card  ↗");go.type="button";go.onclick=()=>navigate("read",recordId(x));
 add(foot,go);add(article,top,title,meta,p,foot);return article;
}
function infoRow(label,value){const row=el("div","info-row");add(row,el("span","info-label",label),el("span","info-value",value));return row;}
function navigate(page,id){
 const value=page==="read"?"read/"+encodeURIComponent(id):page;
 const next="#"+value;if(location.hash===next){renderRoute();return}location.hash=next;
}
function renderRoute(){
 const raw=decodeURIComponent(location.hash.slice(1)||"weekly");const reading=raw.startsWith("read/");
 const page=reading?"read":(["weekly","library","about"].includes(raw)?raw:"weekly");
 state.view=page;$$("[data-view]").forEach(section=>{section.hidden=section.id!==page});
 $$("[data-nav]").forEach(e=>{const active=e.dataset.nav===page; e.classList.toggle("active",active);if(active)e.setAttribute("aria-current","page");else e.removeAttribute("aria-current")});
 if(page==="read"){const id=raw.slice(5);const x=recordById(id);if(x)renderArticle(x);else {$("#article-content").replaceChildren(el("p","empty","That record was not found in the current library."));}}
 if(page==="library")renderLibrary();
 window.scrollTo({top:0,behavior:"instant"});
}
function displayStatus(run){
 const stamp=$("#index-date");stamp.textContent=run?.mode==="curated-starter"?"Starter collection":run?.date?"Indexed "+fmtDate(run.date):"No successful index yet";
 const text=$("#index-caption");text.textContent=run?.mode==="curated-starter"?"First live research update not yet completed":"Latest saved search; refreshes weekly, not continuously";
 const count=$("#total-count");count.textContent=state.library.length.toLocaleString();
}
function renderWeekly(){
 const run=state.weekly?.run||{};displayStatus(run);
 let entries=(state.weekly?.items||[]).map(z=>recordById(recordId(z))||state.library.find(x=>x.title===z.title)||z).filter(x=>x.title);
 const starter=run.mode==="curated-starter";const label=starter?"The starting shelf":"Indexed in the last seven days";
 $("#issue-kicker").textContent=starter?"ISSUE 00 / BASELINE":"LATEST / "+fmtDate(run.date);
 $("#issue-heading").textContent=starter?"An evolving map of AI and attention.":entries.length?"What emerged this week.":"A quieter week for new research.";
 $("#issue-deck").textContent=starter?"This is the initial curated collection. The automated scholarly and news search has not yet populated the weekly index.":"The past seven days added "+entries.length+" indexed items. Records are screened automatically; full-text evidence is separately labeled.";
 $("#updated-label").textContent=starter?"Awaiting first scheduled search":"Last index: "+fmtDate(run.date);
 const highlight=$("#weekly-items");highlight.replaceChildren();
 if(!entries.length)highlight.append(el("p","empty","No new indexed items in this cycle. Browse the complete library instead."));
 else entries.slice(0,7).forEach((x,i)=>highlight.append(card(x,i===0)));
 const countMap={};lanes.forEach(l=>countMap[l]=0);entries.forEach(x=>{if(countMap[x.lane]!==undefined)countMap[x.lane]++});
 const distribution=$("#distribution");distribution.replaceChildren();
 const max=Math.max(1,...Object.values(countMap));
 lanes.forEach(l=>{const r=el("div","distribution-row"),label=el("span","axis-label",l),track=el("div","distribution-track"),fill=el("span","distribution-fill"),number=el("span","distribution-count",countMap[l]);fill.style.width=(100*countMap[l]/max)+"%";add(track,fill);add(r,label,track,number);distribution.append(r)});
 const points=$("#weekly-points");points.replaceChildren();
 if(starter)points.append(el("p","side-copy","Initial reading list only. Interpretive weekly summaries will be available after the first successful collector run."));
 else if(!entries.length)points.append(el("p","side-copy","No newly indexed publications in this run. That is not evidence that no relevant work was published."));
 else entries.slice(0,3).forEach(x=>{const p=el("div","brief-point");add(p,el("span","brief-dot","↗"),el("p","",x.analysis?.key_idea||("New "+(x.kind==="scholarly"?"research":"commentary")+": "+x.title)));points.append(p)});
 const tally=$("#source-tally");tally.textContent=state.library.length+" indexed sources • "+entries.length+" in this update";
 const alert=$("#run-alert");alert.replaceChildren();
 if(run.stats?.errors?.length){add(alert,el("strong","","Some sources were unavailable in the last collection."),el("span","",run.stats.errors.length+" provider warning(s); see the GitHub Actions logs."));alert.hidden=false;}
 else alert.hidden=true;
}
function renderLibrary(){
 const term=$("#search").value.trim().toLocaleLowerCase();const lane=$("#topic-filter").value;const kind=$("#type-filter").value;
 let rows=state.library.filter(x=>(!lane||x.lane===lane)&&(!kind||x.kind===kind)&&(!term||[x.title,x.preview,x.venue,(x.authors||[]).join(" "),x.doi].join(" ").toLocaleLowerCase().includes(term)));
 rows.sort((a,b)=>dateValue(b).localeCompare(dateValue(a)));
 $("#result-count").textContent=rows.length+" of "+state.library.length+" sources";
 const root=$("#library-items");root.replaceChildren();
 if(!rows.length)root.append(el("p","empty","No matches. Try a broader phrase or clear the filters."));
 else rows.forEach(x=>root.append(card(x)));
}
function contentSection(root,label,text){
 if(!text)return;
 const section=el("section","reading-section");add(section,el("h3","",label),el("p","section-text",text));root.append(section);
}
function renderArticle(x){
 const root=$("#article-content");root.replaceChildren();
 const back=el("button","back-link","← Back to the library");back.onclick=()=>navigate("library");
 const head=el("div","reading-head");add(head,el("div","eyebrow","SOURCE READING / "+(x.lane||"Unclassified")),el("h1","reading-title",x.title),el("p","reading-byline",[x.venue,fmtDate(x.published)].join(" · ")));
 const chips=el("div","chips");add(chips,tag(x.kind==="scholarly"?"Academic research":"Commentary / technology"),tag(x.analysis?"Open-access sections extracted":x.curated?"Curated synopsis":"Metadata screening only"));head.append(chips);
 const grid=el("div","reading-grid");
 const main=el("div","reading-main");
 const stand=el("section","reading-section spotlight");add(stand,el("div","eyebrow","THE CENTRAL IDEA"),el("p","standfirst",preview(x)));
 if(!x.analysis){add(stand,el("p","source-notice",x.curated?"Editorial starter note; not a verified extraction of the paper's full methodology or findings.":"Automated title/abstract indexing only. Study design, results, and effect sizes have not been verified."))}
 main.append(stand);
 if(x.analysis){const a=x.analysis;const disclosure=el("p","source-notice","These notes are automatically extracted excerpts from permitted open-access sections, not independent analysis. Verify claims in the linked original.");main.append(disclosure);["methods","results","discussion","limitations"].forEach(k=>contentSection(main,k[0].toUpperCase()+k.slice(1)+" · extracted text",a[k]));}
 else {
 const questions={"AI & cognition":["Which cognitive tasks shift from a person to an AI system?","Does the paper measure attention directly, or another cognitive construct?"],"Fragmentation":["What causes the interruption or switching demand?","Are lasting attention costs measured?","Does the study examine AI specifically?"],"Interventions":["What changes about the intervention design?","Is there a controlled comparison showing improved attention?"],"Technology & society":["Which propositions are descriptive versus normative?","What kind of evidence could test these ideas?"]}[x.lane]||["What is the central claim and supporting evidence?"];
 const section=el("section","reading-section");section.append(el("h3","","Questions worth asking"));const ul=el("ul","question-list");questions.forEach(q=>ul.append(el("li","",q)));section.append(ul);main.append(section);
 }
 const side=el("aside","reading-aside");
 const meta=el("div","aside-block");add(meta,el("div","eyebrow","AT A GLANCE"),infoRow("Type",x.kind==="scholarly"?"Academic":"Essay / technology"),infoRow("Published",fmtDate(x.published)),infoRow("Coverage",x.analysis?"Selected open-access sections":x.curated?"Curated starter":"Citation / abstract"),infoRow("Relevance",x.relation||"Unclassified"));if(x.doi)meta.append(infoRow("DOI",x.doi));side.append(meta);
 const figure=el("div","aside-block");add(figure,el("div","eyebrow","CONCEPT MAP"),el("p","side-copy","An interpretive pathway to guide reading—not a causal finding or figure from this source."));let paths={"AI & cognition":["AI assistance","Cognitive delegation","Attention & judgment"],"Fragmentation":["Interruptions","Task switching","Focus recovery"],"Interventions":["Design choice","User behavior","Attention outcomes"],"Technology & society":["Technology design","Economic incentives","Human agency"]};let seq=paths[x.lane]||["Technology","Human behavior","Attention"];const blocks=el("div","path-diagram");seq.forEach((v,i)=>{blocks.append(el("div","path-node",v));if(i!==seq.length-1)blocks.append(el("div","path-arrow","↓"))});figure.append(blocks);side.append(figure);
 if(x.analysis?.figures?.length){const f=el("div","aside-block");add(f,el("div","eyebrow","FIGURES IN THE ORIGINAL PAPER"));x.analysis.figures.forEach(z=>{const p=el("div","figure-caption");add(p,el("strong","",z.label||"Figure"),el("p","",z.caption||"No caption extracted"));f.append(p)});side.append(f);}
 const link=validUrl(x.url);if(link){const a=el("a","source-button","Read original publication  ↗");a.href=link;a.target="_blank";a.rel="noopener noreferrer";side.append(a);}
 if(x.analysis?.fulltext_url){const u=validUrl(x.analysis.fulltext_url);if(u){const a=el("a","plain-link","Open licensed full text ↗");a.href=u;a.target="_blank";a.rel="noopener noreferrer";side.append(a)}}
 const find=el("a","plain-link","Find by title on Google Scholar ↗");find.href="https://scholar.google.com/scholar?q="+encodeURIComponent(x.title);find.target="_blank";find.rel="noopener noreferrer";side.append(find);
 add(grid,main,side);add(root,back,head,grid);
}
async function load(){
 try{
 const res=await Promise.all(["data/library.json","data/weekly.json","data/runs.json"].map(p=>fetch(p+"?t="+Date.now(),{cache:"no-store"})));
 if(!res[0].ok)throw Error("The library index could not be loaded (HTTP "+res[0].status+").");
 state.library=await res[0].json();
 if(!Array.isArray(state.library))throw Error("Library data is not an array.");
 state.weekly=res[1].ok?await res[1].json():{run:{mode:"unavailable"},items:[]};
 state.runs=res[2].ok?await res[2].json():[];
 renderWeekly();renderLibrary();renderRoute();
 }catch(error){
 $("#index-date").textContent="Library unavailable";$("#index-caption").textContent="There is a problem retrieving published research data.";
 const box=$("#load-error");box.hidden=false;box.textContent=error.message||String(error);
 }
}
$$("[data-nav]").forEach(btn=>btn.addEventListener("click",ev=>{ev.preventDefault();navigate(btn.dataset.nav)}));
$("#search").addEventListener("input",renderLibrary);$("#topic-filter").addEventListener("change",renderLibrary);$("#type-filter").addEventListener("change",renderLibrary);
window.addEventListener("hashchange",renderRoute);
load();
