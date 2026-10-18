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
function preview(x){if(x.reading?.overview)return x.reading.overview;if(x.analysis?.discussion)return x.analysis.discussion.slice(0,360);if(x.preview&&!/abstract unavailable|bibliographic metadata only/i.test(x.preview))return x.preview;return "Citation indexed. A source-based research summary is not available yet.";}
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
 const foot=el("div","story-foot"); add(foot,tag(x.reading?.level==="full_text"?"Full-text notes":x.reading?.level==="abstract"?"Abstract-based":x.curated?"Curated overview":"Citation only",x.reading?.level==="full_text"?"verified":""));
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
function paperPriority(x){
 const level=x.reading?.level;let v=level==="full_text"?95:level==="abstract"?65:level==="curated"?42:0;
 if(x.reading?.findings)v+=20;
 if(x.reading?.methods)v+=10;
 if(x.reading?.limitations)v+=3;
 if(x.lane==="AI & cognition"||x.lane==="Interventions")v+=7;
 if(x.relation==="Adjacent digital-attention evidence")v-=10;
 return v;
}
function renderWeekly(){
 const run=state.weekly?.run||{};displayStatus(run);
 let entries=(state.weekly?.items||[]).map(z=>recordById(recordId(z))||state.library.find(x=>x.title===z.title)||z).filter(x=>x.title);
 const starter=run.mode==="curated-starter";
 // Weekly homepage features source-rich papers; citation-only entries remain in the library.
 const readable=entries.filter(x=>x.reading?.level&&x.reading.level!=="citation_only");
 readable.sort((a,b)=>paperPriority(b)-paperPriority(a));
 const featured=readable.slice(0,5);
 $("#issue-kicker").textContent=starter?"ISSUE 00 / STARTING COLLECTION":"THE WEEKLY RESEARCH DIGEST / "+fmtDate(run.date);
 $("#issue-heading").textContent=starter?"A starting map of AI and attention.":featured.length?"Research worth reading this week.":"The index is growing.";
 $("#issue-deck").textContent=starter?"Initial literature selected for the research library.":"Five source-rich publications selected from "+entries.length+" recent index records. Sections below distinguish reported research from source metadata.";
 $("#updated-label").textContent=starter?"Awaiting live collection":"Last indexed "+fmtDate(run.date);
 const highlight=$("#weekly-items");highlight.replaceChildren();
 if(!featured.length)highlight.append(el("p","empty","No sufficiently detailed research summaries have been indexed for this update yet. Explore the complete research library."));
 else featured.forEach((x,i)=>highlight.append(card(x,i===0)));
 const countMap={};lanes.forEach(l=>countMap[l]=0);entries.forEach(x=>{if(countMap[x.lane]!==undefined)countMap[x.lane]++});
 const distribution=$("#distribution");distribution.replaceChildren();
 const max=Math.max(1,...Object.values(countMap));
 lanes.forEach(l=>{const r=el("div","distribution-row"),label=el("span","axis-label",l),track=el("div","distribution-track"),fill=el("span","distribution-fill"),number=el("span","distribution-count",countMap[l]);fill.style.width=(100*countMap[l]/max)+"%";add(track,fill);add(r,label,track,number);distribution.append(r)});
 const points=$("#weekly-points");points.replaceChildren();
 const notes=featured.filter(x=>x.reading?.findings).slice(0,3);
 if(!notes.length){points.append(el("p","side-copy","No source-backed findings are available for the latest selection. They will appear here when the collector retrieves substantive text."));}
 else notes.forEach(x=>{
   const wrap=el("div","brief-point");
   const link=el("button","brief-finding-title",x.title);link.type="button";link.onclick=()=>navigate("read",recordId(x));
   const fact=el("p","brief-finding",x.reading.findings.slice(0,260));
   const src=el("span","brief-source",x.reading.level==="full_text"?"From open-access article sections":"From indexed abstract");
   add(wrap,link,fact,src);points.append(wrap);
 });
 $("#source-tally").textContent=state.library.length+" library records · "+entries.length+" indexed this week";
 const alert=$("#run-alert");alert.replaceChildren();
 if(run.stats?.errors?.length){add(alert,el("strong","","Some data providers were unavailable in this cycle."),el("span","",run.stats.errors.length+" search-provider warning(s). See GitHub Actions logs."));alert.hidden=false;}else alert.hidden=true;
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
 const back=el("button","back-link","← Back to the research library");back.onclick=()=>navigate("library");
 const head=el("div","reading-head");
 add(head,el("div","eyebrow","RESEARCH READING / "+(x.lane||"Unclassified")),el("h1","reading-title",x.title),el("p","reading-byline",[(x.authors||[]).slice(0,3).join(", ")+(x.authors?.length>3?" et al.":""),x.venue,fmtDate(x.published)].filter(Boolean).join(" · ")));
 const rd=x.reading||{},tier=rd.level==="full_text"?"Open-access article excerpts":rd.level==="abstract"?"Source abstract highlights":rd.level==="curated"?"Editorial synopsis":"Citation only";
 const chips=el("div","chips");add(chips,tag(x.kind==="scholarly"?"Academic publication":"Commentary / technology"),tag(tier,rd.level==="full_text"?"verified":""));head.append(chips);
 const grid=el("div","reading-grid"),main=el("div","reading-main");
 const stand=el("section","reading-section spotlight");
 add(stand,el("div","eyebrow","OVERVIEW"),el("p","standfirst",rd.overview||preview(x)));
 if(rd.notice)stand.append(el("p","source-notice",rd.notice));main.append(stand);
 if(rd.level==="citation_only"||!rd.level){
   const info=el("section","reading-section");
   add(info,el("h3","","What we have indexed"),el("p","section-text","Citation and original-source links only. No accessible abstract or openly licensed text was found yet, so this record is not presented as a substantive finding."));
   main.append(info);
 } else {
   const sections=[["How the study was conducted",rd.methods],["What the paper reports",rd.findings],["Limitations and qualifications",rd.limitations]];
   let included=0;
   sections.forEach(([label,detail])=>{if(detail){contentSection(main,label,detail);included++;}});
   if(!included&&x.kind==="scholarly")contentSection(main,"Evidence status","The accessible source material does not specify a verifiable method or result. This is an overview, not a complete paper analysis.");
   if(rd.level==="abstract"&&x.abstract_text){
     const section=el("section","reading-section");
     const details=el("details","abstract-expander"),sum=el("summary","","Read the indexed abstract");
     details.append(sum,el("p","section-text",x.abstract_text));section.append(details);main.append(section);
   }
 }
 const side=el("aside","reading-aside"),meta=el("div","aside-block");
 add(meta,el("div","eyebrow","SOURCE INFORMATION"),infoRow("Type",x.kind==="scholarly"?"Academic publication":"Commentary / technology"),infoRow("Date",fmtDate(x.published)),infoRow("Available material",tier),infoRow("Provenance",rd.provenance||x.source||"Unspecified"),infoRow("Connection",x.relation||"Not classified"));
 if(rd.sample)meta.append(infoRow("Reported sample",rd.sample));if(x.doi)meta.append(infoRow("DOI",x.doi));side.append(meta);
 if(x.analysis?.figures?.length){
  const f=el("div","aside-block");add(f,el("div","eyebrow","FIGURES IN THE SOURCE"));
  x.analysis.figures.forEach(z=>{const p=el("div","figure-caption");add(p,el("strong","",z.label||"Figure"),el("p","",z.caption||"Caption not extracted"));f.append(p)});side.append(f);
 }
 const orig=validUrl(x.url);
 if(orig){const a=el("a","source-button","Read original publication ↗");a.href=orig;a.target="_blank";a.rel="noopener noreferrer";side.append(a);}
 if(x.analysis?.fulltext_url){const link=validUrl(x.analysis.fulltext_url);if(link){const a=el("a","plain-link","View open-access full text ↗");a.href=link;a.target="_blank";a.rel="noopener noreferrer";side.append(a)}}
 const find=el("a","plain-link","Find on Google Scholar ↗");find.href="https://scholar.google.com/scholar?q="+encodeURIComponent(x.title);find.target="_blank";find.rel="noopener noreferrer";side.append(find);
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
