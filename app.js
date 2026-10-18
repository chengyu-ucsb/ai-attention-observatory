"use strict";
const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
const S={records:[],week:{},issue:{},runs:[],backlog:{},duration:10,left:600,timer:null,running:false,checkpoint:null};
const themes=[["AI & cognition","When thinking is delegated","Offloading, metacognition and reasoning","◎","#a52c3e"],["Fragmentation","The cost of switching","Distraction, interruptions and re-entry","↗","#d77c83"],["Interventions","Designing for focus","Focus tools and digital well-being","✳","#bf7868"],["Technology & society","Who shapes attention?","Platform incentives and human agency","◇","#947783"]];
const depths=[["full_text","Full-text sections","#a52c3e"],["abstract","Abstract-based","#d78f98"],["curated","Curated synopsis","#c6a6a9"]];
function make(t,c,s){const e=document.createElement(t);if(c)e.className=c;if(s!==undefined){if(s!==null&&typeof s==="object")throw new TypeError("make() accepts text only; use add() to append elements");e.textContent=String(s)}return e}
function add(p,...els){for(const e of els)if(e)p.append(e);return p}
function btn(s,fn,c){const e=make("button",c,s);e.type="button";e.onclick=fn;return e}
function link(s,u,c){const e=make("a",c,s);e.href=u;if(u.startsWith("https://")){e.target="_blank";e.rel="noopener noreferrer"}return e}
function date(s){if(!s||!/^20\d\d/.test(s))return "Undated";let d=new Date(s.slice(0,10)+"T12:00:00Z");return isNaN(d.getTime())?"Undated":d.toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"})}
function id(x){return String(x.doi||x.url||x.title)}
function record(k){return S.records.find(x=>id(x)===k)}
function depth(x){return x.reading?.level||"citation_only"}
function depthName(x){if(x.kind==="nonacademic"&&depth(x)!=="citation_only")return "Publisher synopsis";return ({"full_text":"Full-text excerpts","abstract":"Abstract-based","curated":"Curated overview","citation_only":"Citation only"})[depth(x)]}
function excerpt(x){return x.reading?.findings||x.reading?.overview||x.preview||"Citation only."}
function cut(t,n){t=String(t||"").trim();return t.length>n?t.slice(0,n).replace(/\s+\S*$/,"")+"…":t}

// Editorially checked phrases come from the source text, not inferred from a title.
// Retain the full original passage in each article's reading notes.
const highlightByDOI={
 "10.58304/ijts.260930":"AI literacy linked to critical thinking through problem-solving and AI reliance",
 "10.22158/selt.v14n4p28":"Student AI use emphasized efficiency over deeper engagement",
 "10.21203/rs.3.rs-9893084/v1":"Unsupervised AI use linked to offloading and weaker self-regulation",
 "10.3389/fpsyg.2026.1930030":"Stress and social media time predicted academic impact",
 "10.1186/s12888-026-08635-4":"Insomnia group reacted faster to sleep-related stimuli",
 "10.3389/fpsyg.2026.1960382":"Algorithmic management associated with challenge and threat appraisals",
 "10.1609/aies.v9i2.43193":"Parental alerts varied substantially across tested content categories"
};
function shortIdea(x,limit=105){
 const info=ideaInfo(x),r=x.reading||{};
 // A manually reviewed abstract-based headline must not override later full-text findings.
 const keyed=(x.doi||"").toLowerCase();
 if(r.level!=="full_text"&&r.findings&&highlightByDOI[keyed])return highlightByDOI[keyed];
 let value=info.text;
 // Remove routine reporting formulae without changing the source's actual claim.
 value=value.replace(/^(?:the )?(?:quantitative )?(?:results?|findings?|analysis|analyses|data)\s+(?:show(?:ed)?|suggest(?:ed)?|indicat(?:ed|e)?|reveal(?:ed)?|demonstrat(?:ed|e)?|found)\s+(?:that\s+)?/i,"");
 value=value.replace(/^(?:we (?:found|find|observed|show(?:ed)?)\s+that\s+|this (?:study|paper|article) (?:examines?|investigates?|explores?|argues?|proposes?)\s+(?:that\s+)?)/i,"");
 value=value.replace(/\s+/g," ").trim();
 if(value.length<=limit)return value;
 // Prefer intact first clauses over a long sentence; mark any truncation explicitly.
 const firstSentence=value.match(/^.{18,150}?[.!?](?=\s|$)/);
 if(firstSentence&&firstSentence[0].length<=limit)return firstSentence[0];
 const window=value.slice(0,limit+5);
 let at=Math.max(window.lastIndexOf("; "),window.lastIndexOf(", "));
 if(at>45&&at<=limit)return window.slice(0,at).trim()+"…";
 return cut(value,limit);
}

function ideaInfo(x){
 const r=x.reading||{},notes=x.editorial_notes||{};
 let value="",label="";
 if(x.kind==="nonacademic"){
   value=notes.argument||r.overview||"";label=notes.argument?"THE AUTHOR ARGUES":"PUBLISHER SYNOPSIS";
 }else if(r.findings){
   value=r.findings;label=depth(x)==="full_text"?"REPORTED RESULT · FULL TEXT":"ABSTRACT-REPORTED RESULT";
 }else if(r.interpretation){
   value=r.interpretation;label="AUTHOR INTERPRETATION · NOT RESULTS";
 }else{
   value=r.overview||"";label="RESEARCH IDEA · NOT A VERIFIED RESULT";
 }
 // Preserve substantive source language; only strip section-name prefixes.
 value=String(value).replace(/^(?:abstract|results?|discussion|conclusions?)\s*[:.]\s*/i,"").trim();
 return {text:value||"No substantive source text is available.",label};
}
function rank(x){let r=x.reading||{},v=({"full_text":80,"abstract":46,"curated":25,"citation_only":0})[depth(x)]||0;v+=r.findings?26:0;v+=r.methods?10:0;v+=r.limitations?4:0;v+=x.lane==="AI & cognition"||x.lane==="Interventions"?6:0;v+=/ai|generative|chatgpt|attention|offloading|focus/i.test(x.title)?9:0;v+=x.relation==="Adjacent digital-attention evidence"?-25:0;return v}
function goto(page,k){let v="#"+(page==="paper"?"paper/"+encodeURIComponent(k):page);if(location.hash===v)route();else location.hash=v}
function route(){let raw=location.hash.slice(1)||"home";try{raw=decodeURIComponent(raw)}catch{raw="home"}let page=raw.startsWith("paper/")?"paper":raw;if(!["home","library","atlas","lab","paper","about","perspectives","issue"].includes(page))page="home";$$(".view").forEach(v=>v.hidden=v.id!==page);$$("[data-route]").forEach(v=>{v.classList.toggle("active",v.dataset.route===page);if(v.dataset.route===page)v.setAttribute("aria-current","page");else v.removeAttribute("aria-current")});if(page==="paper")showPaper(record(raw.slice(6)));if(page==="library")showLibrary();if(page==="atlas")showAtlas();window.scrollTo({top:0,behavior:"instant"})}
function counts(){const result={};for(const d of depths)result[d[0]]=S.records.filter(x=>depth(x)===d[0]).length;return result}
function topicBars(selector){const root=$(selector);root.replaceChildren();const max=Math.max(1,...themes.map(t=>S.records.filter(x=>x.lane===t[0]).length));for(const t of themes){const n=S.records.filter(x=>x.lane===t[0]).length,p=btn("",()=>{$("#topic-filter").value=t[0];goto("library")},"topic-bar-line"),track=make("span","bar-track"),fill=make("span","bar-fill");fill.style.width=n/max*100+"%";fill.style.background=t[4];add(track,fill);add(p,make("span","bar-label",t[0]),track,make("span","bar-value",n));root.append(p)}}
function donut(){const cc=counts(),total=Math.max(1,S.records.length),legend=$("#depth-legend");$("#record-count").textContent=S.records.length;legend.replaceChildren();let at=0,parts=[];for(const d of depths){let pct=cc[d[0]]/total*100;parts.push(d[2]+" "+at.toFixed(2)+"% "+(at+pct).toFixed(2)+"%");at+=pct;const r=make("div","legend-item"),sw=make("span","legend-swatch"),copy=make("div");sw.style.background=d[2];add(copy,make("div","legend-title",d[1]+" · "+cc[d[0]]),make("span","legend-caption",Math.round(pct)+"% of records"));add(r,sw,copy);legend.append(r)}$("#evidence-donut").style.background="conic-gradient("+parts.join(",")+")"}
function featureCoverage(x){
 const area=make("div","feature-evidence"),row=make("div","feature-evidence-row");
 const tiers=["Citation","Abstract","Full text"],active=depth(x)==="full_text"?3:depth(x)==="abstract"?2:1;
 const track=make("div","feature-evidence-track");
 for(let i=0;i<3;i++){const mark=make("span","feature-evidence-mark"+(i<active?" covered":""));mark.title=tiers[i];track.append(mark)}
 add(row,make("span","", "AVAILABLE MATERIAL"),make("span","",depthName(x)));
 add(area,row,track);
 return area;
}

function issueRefs(ids,target){
 const list=(S.issue.sources||[]),container=target||make("div","issue-references");
 for(const key of ids||[]){
   const src=list.find(x=>x.id===key);
   if(!src)continue;
   const matches=S.records.find(x=>id(x)===key);
   const b=matches?btn(src.title,()=>goto("paper",id(matches)),"issue-ref"):link(src.title,src.url||"#library","issue-ref");
   container.append(b);
 }
 return container;
}
function renderIssue(){
 const issue=S.issue||{},published=issue.status==="published";
 const edition=issue.edition_date||S.week.run?.date||"";
 const sourceCount=Number(issue.source_count)||0;
 $("#weekly-kicker").textContent=published?"THE ATTENTION EDIT · ISSUE "+issue.number:"THE ATTENTION EDIT · IN PREPARATION";
 $("#weekly-title").textContent=published?issue.headline:"This week's synthesis is being reviewed.";
 $("#weekly-deck").textContent=published?issue.deck:"New research and commentary are indexed; the editorial synthesis will appear after source review.";
 $("#weekly-scope").textContent=sourceCount+" source-backed readings reviewed for this edition · "+(issue.types?.commentary||0)+" nonacademic perspectives";
 $("#issue-edition").textContent=published?"THE ATTENTION EDIT / ISSUE "+issue.number+" / "+date(edition):"THE ATTENTION EDIT / IN REVIEW";
 $("#issue-headline").textContent=published?issue.headline:"The next edition is being prepared.";
 $("#issue-deck").textContent=published?issue.deck:issue.note||"The editorial synopsis has not been approved yet.";
 $("#issue-letter-text").textContent=published?issue.letter:"This week's reading set is available below. Editorial themes are awaiting review and won't be fabricated from titles alone.";
 const strips=$("#weekly-signal-strip"),main=$("#issue-signals");strips.replaceChildren();main.replaceChildren();
 const signs=published?issue.signals||[]:[];
 signs.forEach((sig,i)=>{
   const tile=make("a","weekly-signal");tile.href="#issue";tile.setAttribute("aria-label","Read signal "+(i+1)+": "+sig.short);
   const mark=make("div","weekly-signal-symbol",["◎","↗","◇"][i%3]);
   add(tile,mark,make("span","weekly-signal-no",String(i+1).padStart(2,"0")+" · SIGNAL"),make("h4","",sig.short),make("span","weekly-signal-arrow","Explore the thread →"));strips.append(tile);
   const panel=make("article","issue-signal"),header=make("div","issue-signal-header");
   add(header,make("span","issue-signal-icon",["◎","↗","◇"][i%3]),make("span","issue-signal-no","THREAD "+String(i+1).padStart(2,"0")));
   add(panel,header,make("h3","",sig.title),make("p","",sig.text),
       make("span","issue-cited-label","READINGS BEHIND THIS SIGNAL"),
       issueRefs(sig.source_ids));
   main.append(panel);
 });
 $("#issue-extras").hidden=!published;
 $(".issue-closing").hidden=!published;
 $("#issue-tension-title").textContent=published?issue.tension.title:"";
 $("#issue-tension-text").textContent=published?issue.tension.text:"";
 const ref=$("#issue-tension-refs");ref.replaceChildren();if(published)issueRefs(issue.tension.source_ids,ref);
 $("#issue-experiment-title").textContent=published?issue.experiment.title:"";
 $("#issue-experiment-text").textContent=published?issue.experiment.text:"";
 $("#issue-experiment-caution").textContent=published?issue.experiment.caution:"";
 $("#issue-closer").textContent=published?issue.closer:"";
 $("#issue-qualification").textContent=published?issue.editorial_note:"";
 $("#issue-coverage").textContent=sourceCount+" source-backed items in this issue: "+(issue.material?.full_text||0)+" full-text extracts, "+(issue.material?.abstract||0)+" abstract-based readings and "+(issue.material?.publisher_or_editorial||0)+" publisher/editorial synopses. Full-source reviews are not implied.";
 const shelf=$("#issue-sources");shelf.replaceChildren();
 for(const [i,src] of (issue.sources||[]).entries()){
  const r=make("div","issue-shelf-item");let candidate=S.records.find(x=>id(x)===src.id);
  const title=candidate?btn(src.title,()=>goto("paper",src.id)):link(src.title,src.url||"#library");
  add(r,make("span","issue-shelf-number",String(i+1).padStart(2,"0")),add(make("div","issue-shelf-content"),title,make("p","",[src.venue,src.reading_level==="full_text"?"Full-text extract":src.reading_level==="abstract"?"Abstract-based":"Publisher/editorial"].filter(Boolean).join(" · "))));
  shelf.append(r);
 }
}

function home(){
 const run=S.week.run||{},all=(S.week.items||[]).map(x=>record(id(x))||S.records.find(r=>r.title===x.title)||x);
 const top=all.filter(x=>x.kind==="scholarly"&&depth(x)!=="citation_only"&&x.reading?.findings).sort((a,b)=>rank(b)-rank(a)).filter(x=>x.relation!=="Adjacent digital-attention evidence"||!all.some(y=>y.relation!=="Adjacent digital-attention evidence"&&y.reading?.findings)).slice(0,3);
 const start=run.mode==="curated-starter";$("#issue-label").textContent=start?"STARTER COLLECTION / LIVE UPDATE PENDING":"LATEST INDEX / "+date(run.date);$("#issue-meta").textContent=(run.last_seven_days??all.length)+" recently indexed · "+S.records.length+" total";
 const root=$("#feature-grid");root.replaceChildren();
 if(!top.length)root.append(make("div","empty-state","The latest index contains no source-rich highlights yet. Browse the research library."));
 top.forEach((x,i)=>{const c=make("article","feature-card"+(i===0?" primary":"")),head=make("div","feature-top"),foot=make("div","feature-foot");
 add(head,make("span","feature-number",String(i+1).padStart(2,"0")),make("span","feature-icon",["◎","↗","✳"][i]));
 add(foot,make("span","source-pill",depthName(x)),btn("Read the evidence ↗",()=>goto("paper",id(x)),"feature-go"));
 add(c,head,make("p","feature-idea-label",ideaInfo(x).label),make("h3","feature-idea",shortIdea(x,96)),make("p","feature-source-title",x.title),make("p","source-meta",(x.venue||"")+" · "+date(x.published)),featureCoverage(x),foot);root.append(c)});
 // Provider diagnostics belong in repository workflow logs, never in public content.
 renderEditorial();
 topicBars("#topic-bars");donut();
 const grid=$("#lens-grid");grid.replaceChildren();themes.forEach(t=>{const a=link("","#library","lens");a.setAttribute("aria-label","Explore "+t[0]);a.onclick=e=>{e.preventDefault();$("#topic-filter").value=t[0];goto("library")};add(a,make("span","lens-mark",t[3]),make("h3","",t[1]),make("p","",t[2]),make("span","",S.records.filter(x=>x.lane===t[0]).length+" records →"));grid.append(a)});
 const arr=$("#arrivals-body");arr.replaceChildren();
 const sorted=S.records.filter(x=>depth(x)!=="citation_only").slice().sort((a,b)=>(b.published||"").localeCompare(a.published||"")).slice(0,7);
 for(const x of sorted){let tr=make("tr"),name=make("td"),go=make("td","align-right");name.append(btn(shortIdea(x,94),()=>goto("paper",id(x))));name.append(make("span","arrival-source-title",x.title));go.append(btn("↗",()=>goto("paper",id(x))));add(tr,make("td","mono-date",date(x.published)),name,make("td","",x.lane||"Research"),make("td","coverage-tag",depthName(x)),go);arr.append(tr)}
}

function renderEditorial(){
 const list=S.records.filter(x=>x.kind==="nonacademic");
 const sorted=list.filter(x=>depth(x)!=="citation_only").sort((a,b)=>(b.first_seen||"").localeCompare(a.first_seen||"")||(b.published||"").localeCompare(a.published||""));
 const featured=[];for(const test of [x=>x.format==="Product & design",x=>x.format==="Policy analysis",x=>x.source==="Publisher RSS / Google News RSS",x=>true]){const next=sorted.find(x=>!featured.includes(x)&&test(x));if(next)featured.push(next)};
 const root=$("#editorial-grid");root.replaceChildren();
 if(!featured.length){root.append(make("div","empty-state","No source-supported perspectives have been indexed yet. The editorial feeds are checked every week."));return}
 for(const x of featured){
  const card=make("article","editorial-card"),label=make("span","editorial-category",x.format||"Expert perspective");
  const articleTitle=make("h3");articleTitle.append(btn(shortIdea(x,92),()=>goto("paper",id(x))));
  const foot=make("div","editorial-foot");
  add(foot,make("span","",x.venue||"Original source"),btn("Explore ↗",()=>goto("paper",id(x)),"editorial-cta"));
  add(card,label,articleTitle,make("p","editorial-source-title",x.title),foot);root.append(card)
 }
}

function renderPerspectives(){
 const all=S.records.filter(x=>x.kind==="nonacademic"&&depth(x)!=="citation_only");
 const product=all.filter(x=>x.source==="Official product documentation"||x.format==="Product & design");
 const essays=all.filter(x=>!product.includes(x));
 const lists=[["#perspectives-essays",essays],["#perspectives-products",product]];
 for(const [selector,records] of lists){
  const container=$(selector);container.replaceChildren();
  if(!records.length){container.append(make("div","empty-state","No indexed sources in this group yet."));continue}
  records.sort((a,b)=>(b.published||"").localeCompare(a.published||""));
  for(const x of records){
    const item=make("article","perspective-item");
    const icon=make("div","perspective-glyph",x.source==="Official product documentation"?"◈":x.format==="Policy analysis"?"◇":"↗");
    const label=make("div","perspective-type",x.format||"Reporting & analysis");
    const title=make("h3");title.append(btn(shortIdea(x,105),()=>goto("paper",id(x))));
    const summary=make("p","perspective-source-title",x.title);
    const bottom=make("div","perspective-bottom");
    add(bottom,make("span","",x.venue||"Original source"),btn("Read source notes ↗",()=>goto("paper",id(x)),"editorial-cta"));
    add(item,icon,label,title,summary,bottom);container.append(item);
  }
 }
}
function renderBacklog(){
 const b=S.backlog||{},root=$("#backlog-coverage");
 root.replaceChildren();
 const scholarly=Number(b.total_scholarly)||S.records.filter(r=>r.kind==="scholarly").length;
 const done=Number(b.full_text_extracted)||S.records.filter(r=>r.kind==="scholarly"&&depth(r)==="full_text").length;
 const pct=scholarly?Math.round(100*done/scholarly):0;
 const top=make("div","coverage-status-row");
 add(top,make("strong","",done+" of "+scholarly+" scholarly papers"),make("span","",pct+"% with extracted full-text sections"));
 const rail=make("div","coverage-status-rail"),bar=make("span","coverage-status-bar");
 bar.style.width=pct+"%";rail.append(bar);
 let pending=Number(b.ready_for_attempt)||0;
 const pause=b.status==="waiting_for_budget"?"Paused by OpenAlex's daily allowance; automatic catch-up will resume after reset.":"Checking the backlog four times daily, within source access and rate limits.";
 const detail=make("p","",pending+" papers ready for another extraction attempt. "+pause);
 add(root,top,rail,detail);
}
function showLibrary(){
 const q=$("#search").value.trim().toLowerCase(),t=$("#topic-filter").value,d=$("#depth-filter").value,k=$("#type-filter").value;
 const xs=S.records.filter(x=>(!q||[x.title,x.venue,x.abstract_text,x.preview,x.reading?.findings,x.reading?.methods,(x.authors||[]).join(" ")].join(" ").toLowerCase().includes(q))&&(!t||x.lane===t)&&(!k||x.kind===k)&&(d!=="full_text"||depth(x)==="full_text")).sort((a,b)=>(b.published||"").localeCompare(a.published||"")||rank(b)-rank(a));
 $("#library-count").textContent=xs.length+" results · "+S.records.length+" total sources";
 const box=$("#library-results");box.replaceChildren();
 if(!xs.length){box.append(make("div","empty-state","No source-backed items match those filters. Try a broader search."));return}
 for(const x of xs){const c=make("article","library-card"),h=make("h3"),foot=make("div","card-foot");h.append(btn(shortIdea(x,105),()=>goto("paper",id(x))));add(foot,make("span","",date(x.published)+" · "+(x.venue||"")),make("span","",depthName(x)));add(c,make("span","card-type",ideaInfo(x).label),h,make("p","library-citation",x.title),foot);box.append(c)}
}
function showAtlas(){
 const cc=counts(),n=S.records.length,stat=$("#atlas-stats");stat.replaceChildren();
 for(const [label,value] of [["Indexed sources",n],["Abstract readings",cc.abstract],["Full-text excerpts",cc.full_text],["Records with findings",S.records.filter(x=>x.reading?.findings).length]]){let c=make("div","atlas-stat");add(c,make("strong","",value),make("span","",label));stat.append(c)}
 topicBars("#atlas-topic-bars");
 const years={};S.records.forEach(x=>{let y=(x.published||"").slice(0,4);if(/^20\d\d$/.test(y))years[y]=(years[y]||0)+1});
 const values=Object.entries(years).sort((a,b)=>Number(a[0])-Number(b[0])).slice(-9),max=Math.max(1,...values.map(x=>x[1])),chart=$("#year-chart");chart.replaceChildren();
 for(const [y,n] of values){let c=make("div","year-col"),bar=make("span","year-bar");bar.style.height=Math.max(3,185*n/max)+"px";bar.title=n+" records from "+y;add(c,make("span","year-value",n),bar,make("span","year-label",y));chart.append(c)}
 const coverage=$("#atlas-depth");coverage.replaceChildren();for(const d of depths){const n=cc[d[0]],p=n/Math.max(1,S.records.length)*100,c=make("div","coverage-row"),top=make("div","coverage-top"),track=make("div","coverage-track"),fill=make("span","coverage-fill");fill.style.background=d[2];fill.style.width=p+"%";add(top,make("strong","",d[1]),make("span","",n+" · "+Math.round(p)+"%"));track.append(fill);add(c,top,track);coverage.append(c)}
 const table=$("#matrix-table"),thead=make("thead"),r=make("tr");add(r,make("th","","Theme"),...depths.map(d=>make("th","",d[1])));thead.append(r);
 const body=make("tbody");for(const t of themes){const row=make("tr");row.append(make("td","",t[0]));for(const d of depths)row.append(make("td","count-cell",S.records.filter(x=>x.lane===t[0]&&depth(x)===d[0]).length));body.append(row)}table.replaceChildren(thead,body)
}
function section(title,text,origin){const s=make("section","reading-section");add(s,make("p","eyebrow",title),make("h3","",title==="HOW IT WAS STUDIED"?"Method & data":title==="WHAT THE PAPER REPORTS"?"Findings":title==="LIMITATIONS"?"Limitations":title==="AUTHOR INTERPRETATION (DISCUSSION)"?"Authors’ interpretation":"Overview"),make("p","",text));if(origin)s.append(make("div","section-source",origin));return s}
function paperFact(k,v){return add(make("div","paper-fact"),make("span","",k),make("span","",v))}
function processedIdea(x){
 const d=x.reading?.digest;
 if(d){
  const idea=d.status==="editorially_written_from_indexed_sections"?(d.idea||d.finding):d.finding||d.idea||d.interpretation;
  if(idea)return cut(idea,145);
 }
 return shortIdea(x,145);
}
function conceptArtwork(x){
 const doi=(x.doi||"").toLowerCase();
 if(doi==="10.3389/feduc.2026.1861548"){
  const w=make("section","article-concept-art");
  add(w,make("p","eyebrow","VISUALIZED FINDING / THREE LEARNER PROFILES"),make("h3","figure-insight-title","Not all AI reliance looks alike"));
  const row=make("div","profile-visual");
  [
   ["01","Engaged & literate","Monitoring alongside reliance"],
   ["02","Uncritical reliant","Heavy reliance, limited monitoring"],
   ["03","Skeptical minimal","Limited use, but reliance when engaged"]
  ].forEach(([num,title,descr])=>add(row,add(make("div","profile-visual-card"),make("span","profile-number",num),make("strong","",title),make("p","",descr))));
  add(w,row,make("p","concept-note","Source-grounded visualization of three profiles identified by the reported cluster analysis. Card sizes do not indicate their prevalence."));
  return w;
 }
 if(doi==="10.3389/fpsyg.2026.1920947"){
  const w=make("section","article-concept-art");
  add(w,make("p","eyebrow","VISUALIZED METHOD / QUALITATIVE CODING"),make("h3","figure-insight-title","From initial codes to broader categories"));
  const row=make("div","categories-visual"),left=make("div","categories-count"),right=make("div","categories-count");
  const dots=make("div","categories-dots");for(let i=0;i<19;i++)dots.append(make("i",""));
  add(left,make("strong","","19"),make("span","","Initial categories"),dots);
  const main=make("div","categories-dots categories-dots-big");for(let i=0;i<5;i++)main.append(make("i",""));
  add(right,make("strong","","5"),make("span","","Main categories"),main);
  add(row,left,make("span","categories-direction","→"),right);
  add(w,row,make("p","concept-note","The extracted Results section reports 19 initial categories organized into five main categories. This is a numerical summary, not a recreation of the study's model figure."));
  return w;
 }
 const tags=(x.reading?.digest?.tags||[]).slice(0,3);
 const wrapper=make("section","article-concept-art");
 add(wrapper,make("p","eyebrow","CONCEPT MAP / ORIENTATION, NOT A STUDY FIGURE"));
 const scene=make("div","concept-scene");
 const center=make("div","concept-center",x.lane==="AI & cognition"?"AI & THINKING":x.lane==="Fragmentation"?"ATTENTION":x.lane==="Interventions"?"DESIGN & FOCUS":"TECHNOLOGY");
 scene.append(center);
 for(const [i,label] of (tags.length?tags:["Human activity","Technological context","Attention"]).entries()){
  const branch=make("div","concept-node concept-node-"+i,label);
  scene.append(branch);
 }
 add(wrapper,scene,make("p","concept-note","These labels reflect topics in the available source. Their placement is illustrative, not an empirical relationship, path coefficient, or reconstructed source figure."));
 return wrapper;
}
function showPaper(x){
 const area=$("#paper-content");area.replaceChildren();if(!x){area.append(make("div","empty-state","This record could not be located."));return}
 const r=x.reading||{},d=r.digest||{},meta=[...(x.authors||[]).slice(0,3),x.venue,date(x.published)].filter(Boolean).join(" · ");
 const chips=make("div","paper-controls");for(const a of [x.lane||"Research",depthName(x),x.kind==="scholarly"?"Scholarly":"Commentary"])chips.append(make("span","paper-label",a));
 const cols=make("div","paper-columns"),left=make("div"),right=make("aside","paper-side"),lead=make("section","reading-lead");
 add(lead,make("p","eyebrow",d.status==="editorially_written_from_indexed_sections"?"EDITORIAL READING / SOURCE GROUNDED":"AT A GLANCE / SOURCE-DERIVED"),make("h2","","The idea in plain language"),
   make("p","",d.idea||cut(r.overview||excerpt(x),250)));left.append(lead);
 // High-level source-condensed notes: never invent numbers or treat Discussion as Results.
 const editorial=x.kind==="nonacademic",notes=x.editorial_notes||{};
 const cells=editorial?[
  ["THE ARGUMENT",d.idea||notes.argument||r.overview,"◆"],
  ["DESIGN IMPLICATION",d.interpretation||notes.design_relevance,"↗"],
  ["WHAT REMAINS OPEN",d.limitation||notes.caveat,"◌"]
 ]:[
  ["THE APPROACH",d.approach||"Not specified in available source text.","◈"],
  ["REPORTED RESULT",d.finding||"No clearly identifiable empirical result in the indexed text.","◎"],
  ["LIMITS / INTERPRETATION",d.limitation||d.interpretation||"No source-backed qualification available.","↗"]
 ];
 const snapshot=make("div","paper-snapshot");
 for(const [title,content,symbol] of cells){
  const tile=make("article","snapshot-tile"+(content?"":" is-missing"));
  add(tile,make("div","snapshot-symbol",symbol),make("span","snapshot-kicker",title),make("p","",content||"Not established in the indexed text."));
  snapshot.append(tile);
 }
 left.append(snapshot);
 left.append(conceptArtwork(x));
 const detailed=make("details","paper-detail-excerpts");detailed.open=false;
 detailed.append(make("summary","","Inspect original extracted passages (automated source text)"));
 const notesArea=make("div","paper-detail-body");let hasNotes=false;
 if(editorial){
  for(const [label,content,source] of [["THE AUTHOR'S ARGUMENT",notes.argument,"Editorial reading note"],["DESIGN POSSIBILITIES",notes.design_relevance,"Research-to-product interpretation (not a tested result)"],["INTERPRETIVE LIMITS",notes.caveat,"Editorial qualification"]]){
    if(content){notesArea.append(section(label,content,source));hasNotes=true}
  }
 }else{
  for(const [label,content] of [["HOW IT WAS STUDIED",r.methods],["WHAT THE PAPER REPORTS",r.findings],["AUTHOR INTERPRETATION (DISCUSSION)",r.interpretation],["LIMITATIONS",r.limitations]]){
    if(content){notesArea.append(section(label,content,r.provenance));hasNotes=true}
  }
 }
 if(hasNotes){detailed.append(notesArea);left.append(detailed)}
 else left.append(make("div","citation-notice",editorial?"Only a short description is indexed for this commentary. Open the original to read the argument in context.":"No method and result can be identified from the accessible text. This remains a discovery record."));
 if(x.abstract_text){const details=make("details"),box=make("section","reading-section");add(details,make("summary","","Show the indexed abstract"),make("p","",x.abstract_text));box.append(details);left.append(box)}
 left.append(make("p","paper-smallprint",r.notice||"Automatically indexed material. Verify the original publication before citing findings."));
 const at=make("section","paper-side-block");add(at,make("p","eyebrow","SOURCE INFORMATION"),make("h3","","Reading details"));
 for(const [k,v] of [["Published",date(x.published)],["Venue",x.venue||"Not supplied"],["Coverage",depthName(x)],["Evidence",x.relation||"Unclassified"],["Provenance",r.provenance||x.source||"Index"]])at.append(paperFact(k,v));
 if(r.sample)at.append(paperFact("Sample",r.sample));if(x.doi)at.append(paperFact("DOI",x.doi));right.append(at);
 if(x.analysis?.figures?.length){
 const fig=make("section","paper-side-block");
 add(fig,make("p","eyebrow","FIGURES FROM THE SOURCE"),make("h3","","See the study's visuals"));
 let originals=0;
 for(const f of x.analysis.figures.slice(0,3)){
   const card=make("div","figure-caption");
   const verified=typeof f.image_url==="string"&&/^https:\/\/pmc\.ncbi\.nlm\.nih\.gov\/articles\/PMC\d+\/bin\//.test(f.image_url)&&f.attribution;
   if(verified){
     const img=make("img","original-figure");img.src=f.image_url;img.loading="lazy";img.alt=(f.label||"Figure")+": "+(f.caption||"Original published figure");
     img.addEventListener("error",()=>{img.hidden=true});
     card.append(img);originals++;
   }
   add(card,make("strong","",f.label||"Figure"),make("p","",cut(f.caption||"Source figure caption unavailable.",200)));
   if(verified)card.append(make("p","figure-license","Original open-access figure · "+f.attribution+" · Parent article license checked; third-party credits may impose further conditions."));
   fig.append(card);
 }
 if(!originals)fig.append(make("p","paper-smallprint","No original image has passed the source and license checks yet. Captions are provided as a guide, not as recreated plots."));
 if(x.analysis?.fulltext_url)fig.append(link("Inspect the figures in the original article ↗",x.analysis.fulltext_url,"paper-extra"));
 right.append(fig)
}
 
 function valid(u){try{const v=new URL(u);return v.protocol==="https:"?u:null}catch{return null}}
 if(valid(x.url))right.append(link("Open original publication ↗",x.url,"paper-original"));
 if(valid(x.analysis?.fulltext_url))right.append(link("View open-access version ↗",x.analysis.fulltext_url,"paper-extra"));
 if(valid(x.open_access_url))right.append(link("Find available full text ↗",x.open_access_url,"paper-extra"));
 right.append(link("Search on Google Scholar ↗","https://scholar.google.com/scholar?q="+encodeURIComponent(x.title),"paper-extra"));
 let related=S.records.filter(y=>y!==x&&y.kind===x.kind&&y.lane===x.lane&&depth(y)!=="citation_only").sort((a,b)=>rank(b)-rank(a)).slice(0,3);
 if(related.length){const panel=make("section","paper-side-block");add(panel,make("p","eyebrow","EXPLORE FURTHER"),make("h3","","Related papers"));for(const y of related)panel.append(btn(y.title,()=>goto("paper",id(y)),"paper-extra"));right.append(panel)}
 add(cols,left,right);add(area,btn("← Back to the library",()=>goto("library"),"back-button"),make("p","eyebrow paper-eyebrow",ideaInfo(x).label),make("h1","paper-insight",processedIdea(x)),add(make("div","paper-identity"),add(make("div","paper-identity-inner"),make("p","eyebrow","THE ORIGINAL PUBLICATION"),make("h2","paper-source-title",x.title),make("p","paper-meta",meta))),chips,cols)
}
function showProductExamples(){
 const examples=S.records.filter(x=>x.source==="Official product documentation");
 const tbody=$("#product-examples");tbody.replaceChildren();
 const categories={"one sec":"Deliberate pause","Freedom":"Access restriction","Apple Developer":"Focus integration","Android":"System controls"};
 if(!examples.length){const tr=make("tr"),td=make("td","","Product design references have not been indexed yet.");td.colSpan=4;tr.append(td);tbody.append(tr);return}
 examples.forEach(x=>{
  const tr=make("tr"),go=make("td");
  go.append(btn("Read notes ↗",()=>goto("paper",id(x))));
  add(tr,make("td","",categories[x.venue]||x.venue),make("td","",cut(x.reading?.overview||x.preview,110)),make("td","",cut(x.editorial_notes?.design_relevance,125)),go);tbody.append(tr)
 });
}
async function init(){
 // The Experimental Lab initializes independently in lab-play.js.
 try{
  const rs=await Promise.all(["data/public-library.json","data/public-weekly.json","data/runs.json","data/fulltext-backfill-state.json","data/public-issue.json"].map(p=>fetch(p+"?v="+Date.now(),{cache:"no-store"})));
  if(!rs[0].ok)throw new Error("Library download failed (HTTP "+rs[0].status+")");
  S.records=await rs[0].json();if(!Array.isArray(S.records))throw new Error("Unexpected library format");S.records=S.records.filter(x=>x.reading?.level&&x.reading.level!=="citation_only");
  S.week=rs[1].ok?await rs[1].json():{run:{mode:"unavailable"},items:[]};
  S.runs=rs[2].ok?await rs[2].json():[];
  S.backlog=rs[3].ok?await rs[3].json():{};
  S.issue=rs[4].ok?await rs[4].json():{};
  home();renderIssue();renderBacklog();showLibrary();showProductExamples();renderPerspectives();route();
 }catch(e){$("#issue-label").textContent="INDEX OFFLINE";$("#issue-meta").textContent="Research data could not load";$("#feature-grid").replaceChildren(make("div","empty-state","Could not load the research archive: "+e.message));route()}
}
$$("[data-route]").forEach(a=>a.onclick=e=>{e.preventDefault();goto(a.dataset.route)});
["search","topic-filter","depth-filter","type-filter"].forEach(s=>$("#"+s).addEventListener(s==="search"?"input":"change",showLibrary));
$("#browse-editorial").addEventListener("click",e=>{e.preventDefault();goto("perspectives")});
$("#perspectives-library-link").addEventListener("click",e=>{e.preventDefault();$("#type-filter").value="nonacademic";$("#depth-filter").value="readable";goto("library")});
$("#perspectives-essays-link").addEventListener("click",e=>{e.preventDefault();$("#perspectives-essays").scrollIntoView({behavior:"smooth",block:"start"})});
window.addEventListener("hashchange",route);
init();
