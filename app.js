"use strict";
const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
const S={records:[],week:{},runs:[],duration:10,left:600,timer:null,running:false,checkpoint:null};
const themes=[["AI & cognition","When thinking is delegated","Offloading, metacognition and reasoning","◎","#a52c3e"],["Fragmentation","The cost of switching","Distraction, interruptions and re-entry","↗","#d77c83"],["Interventions","Designing for focus","Focus tools and digital well-being","✳","#bf7868"],["Technology & society","Who shapes attention?","Platform incentives and human agency","◇","#947783"]];
const depths=[["full_text","Full-text sections","#a52c3e"],["abstract","Abstract-based","#d78f98"],["curated","Curated synopsis","#c6a6a9"],["citation_only","Citation only","#ddd4cf"]];
function make(t,c,s){const e=document.createElement(t);if(c)e.className=c;if(s!==undefined)e.textContent=String(s);return e}
function add(p,...els){for(const e of els)if(e)p.append(e);return p}
function btn(s,fn,c){const e=make("button",c,s);e.type="button";e.onclick=fn;return e}
function link(s,u,c){const e=make("a",c,s);e.href=u;if(u.startsWith("https://")){e.target="_blank";e.rel="noopener noreferrer"}return e}
function date(s){if(!s||!/^20\d\d/.test(s))return "Undated";let d=new Date(s.slice(0,10)+"T12:00:00Z");return isNaN(d.getTime())?"Undated":d.toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"})}
function id(x){return String(x.doi||x.url||x.title)}
function record(k){return S.records.find(x=>id(x)===k)}
function depth(x){return x.reading?.level||"citation_only"}
function depthName(x){return ({"full_text":"Full-text excerpts","abstract":"Abstract-based","curated":"Curated overview","citation_only":"Citation only"})[depth(x)]}
function excerpt(x){return x.reading?.findings||x.reading?.overview||x.preview||"Citation only."}
function cut(t,n){t=String(t||"").trim();return t.length>n?t.slice(0,n).replace(/\s+\S*$/,"")+"…":t}
function rank(x){let r=x.reading||{},v=({"full_text":80,"abstract":46,"curated":25,"citation_only":0})[depth(x)]||0;v+=r.findings?26:0;v+=r.methods?10:0;v+=r.limitations?4:0;v+=x.lane==="AI & cognition"||x.lane==="Interventions"?6:0;v+=/ai|generative|chatgpt|attention|offloading|focus/i.test(x.title)?9:0;v+=x.relation==="Adjacent digital-attention evidence"?-25:0;return v}
function goto(page,k){let v="#"+(page==="paper"?"paper/"+encodeURIComponent(k):page);if(location.hash===v)route();else location.hash=v}
function route(){let raw=location.hash.slice(1)||"home";try{raw=decodeURIComponent(raw)}catch{raw="home"}let page=raw.startsWith("paper/")?"paper":raw;if(!["home","library","atlas","lab","paper","about"].includes(page))page="home";$$(".view").forEach(v=>v.hidden=v.id!==page);$$("[data-route]").forEach(v=>{v.classList.toggle("active",v.dataset.route===page);if(v.dataset.route===page)v.setAttribute("aria-current","page");else v.removeAttribute("aria-current")});if(page==="paper")showPaper(record(raw.slice(6)));if(page==="library")showLibrary();if(page==="atlas")showAtlas();window.scrollTo({top:0,behavior:"instant"})}
function counts(){const result={};for(const d of depths)result[d[0]]=S.records.filter(x=>depth(x)===d[0]).length;return result}
function topicBars(selector){const root=$(selector);root.replaceChildren();const max=Math.max(1,...themes.map(t=>S.records.filter(x=>x.lane===t[0]).length));for(const t of themes){const n=S.records.filter(x=>x.lane===t[0]).length,p=btn("",()=>{$("#topic-filter").value=t[0];goto("library")},"topic-bar-line"),track=make("span","bar-track"),fill=make("span","bar-fill");fill.style.width=n/max*100+"%";fill.style.background=t[4];add(track,fill);add(p,make("span","bar-label",t[0]),track,make("span","bar-value",n));root.append(p)}}
function donut(){const cc=counts(),total=Math.max(1,S.records.length),legend=$("#depth-legend");$("#record-count").textContent=S.records.length;legend.replaceChildren();let at=0,parts=[];for(const d of depths){let pct=cc[d[0]]/total*100;parts.push(d[2]+" "+at.toFixed(2)+"% "+(at+pct).toFixed(2)+"%");at+=pct;const r=make("div","legend-item"),sw=make("span","legend-swatch"),copy=make("div");sw.style.background=d[2];add(copy,make("div","legend-title",d[1]+" · "+cc[d[0]]),make("span","legend-caption",Math.round(pct)+"% of records"));add(r,sw,copy);legend.append(r)}$("#evidence-donut").style.background="conic-gradient("+parts.join(",")+")"}
function home(){
 const run=S.week.run||{},all=(S.week.items||[]).map(x=>record(id(x))||S.records.find(r=>r.title===x.title)||x);
 const top=all.filter(x=>depth(x)!=="citation_only"&&x.reading?.findings).sort((a,b)=>rank(b)-rank(a)).filter(x=>x.relation!=="Adjacent digital-attention evidence"||!all.some(y=>y.relation!=="Adjacent digital-attention evidence"&&y.reading?.findings)).slice(0,3);
 const start=run.mode==="curated-starter";$("#issue-label").textContent=start?"STARTER COLLECTION / LIVE UPDATE PENDING":"LATEST INDEX / "+date(run.date);$("#issue-meta").textContent=(run.last_seven_days??all.length)+" recently indexed · "+S.records.length+" total";
 const root=$("#feature-grid");root.replaceChildren();
 if(!top.length)root.append(make("div","empty-state","The latest index contains no source-rich highlights yet. Browse the research library."));
 top.forEach((x,i)=>{const c=make("article","feature-card"+(i===0?" primary":"")),head=make("div","feature-top"),foot=make("div","feature-foot");
 add(head,make("span","feature-number",String(i+1).padStart(2,"0")),make("span","feature-icon",["◎","↗","✳"][i]));
 add(foot,make("span","source-pill",depthName(x)),btn("Read the evidence ↗",()=>goto("paper",id(x)),"feature-go"));
 add(c,head,make("h3","",x.title),make("p","feature-quote",cut(excerpt(x),i===0?360:250)),make("p","source-meta",(x.venue||"")+" · "+date(x.published)),foot);root.append(c)});
 const alert=$("#research-warning"),errors=run.stats?.errors||[];alert.hidden=errors.length===0;if(errors.length)alert.textContent=errors.length+" discovery provider warning(s); see the repository Actions log.";
 topicBars("#topic-bars");donut();
 const grid=$("#lens-grid");grid.replaceChildren();themes.forEach(t=>{const a=link("","#library","lens");a.setAttribute("aria-label","Explore "+t[0]);a.onclick=e=>{e.preventDefault();$("#topic-filter").value=t[0];goto("library")};add(a,make("span","lens-mark",t[3]),make("h3","",t[1]),make("p","",t[2]),make("span","",S.records.filter(x=>x.lane===t[0]).length+" records →"));grid.append(a)});
 const arr=$("#arrivals-body");arr.replaceChildren();
 const sorted=S.records.filter(x=>depth(x)!=="citation_only").slice().sort((a,b)=>(b.published||"").localeCompare(a.published||"")).slice(0,7);
 for(const x of sorted){let tr=make("tr"),name=make("td"),go=make("td","align-right");name.append(btn(x.title,()=>goto("paper",id(x))));go.append(btn("↗",()=>goto("paper",id(x))));add(tr,make("td","mono-date",date(x.published)),name,make("td","",x.lane||"Research"),make("td","coverage-tag",depthName(x)),go);arr.append(tr)}
}
function showLibrary(){
 const q=$("#search").value.trim().toLowerCase(),t=$("#topic-filter").value,d=$("#depth-filter").value,k=$("#type-filter").value;
 const xs=S.records.filter(x=>(!q||[x.title,x.venue,x.abstract_text,x.preview,x.reading?.findings,x.reading?.methods,(x.authors||[]).join(" ")].join(" ").toLowerCase().includes(q))&&(!t||x.lane===t)&&(!k||x.kind===k)&&(d==="all"||(d==="full_text"?depth(x)==="full_text":depth(x)!=="citation_only"))).sort((a,b)=>(b.published||"").localeCompare(a.published||"")||rank(b)-rank(a));
 $("#library-count").textContent=xs.length+" results · "+S.records.length+" total sources";
 const box=$("#library-results");box.replaceChildren();
 if(!xs.length){box.append(make("div","empty-state","No matches. Try another keyword or include citation-only records."));return}
 for(const x of xs){const c=make("article","library-card"),h=make("h3"),foot=make("div","card-foot");h.append(btn(x.title,()=>goto("paper",id(x))));add(foot,make("span","",date(x.published)+" · "+(x.venue||"")),make("span","",depthName(x)));add(c,make("span","card-type",x.lane||"Research"),h,make("p","",cut(excerpt(x),205)),foot);box.append(c)}
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
function section(title,text,origin){const s=make("section","reading-section");add(s,make("p","eyebrow",title),make("h3","",title==="HOW IT WAS STUDIED"?"Method & data":title==="WHAT THE PAPER REPORTS"?"Findings":title==="LIMITATIONS"?"Limitations":"Overview"),make("p","",text));if(origin)s.append(make("div","section-source",origin));return s}
function paperFact(k,v){return add(make("div","paper-fact"),make("span","",k),make("span","",v))}
function showPaper(x){
 const area=$("#paper-content");area.replaceChildren();if(!x){area.append(make("div","empty-state","This record could not be located."));return}
 const r=x.reading||{},meta=[...(x.authors||[]).slice(0,3),x.venue,date(x.published)].filter(Boolean).join(" · ");
 const chips=make("div","paper-controls");for(const a of [x.lane||"Research",depthName(x),x.kind==="scholarly"?"Scholarly":"Commentary"])chips.append(make("span","paper-label",a));
 const cols=make("div","paper-columns"),left=make("div"),right=make("aside","paper-side"),lead=make("section","reading-lead");
 add(lead,make("p","eyebrow","CENTRAL IDEA"),make("h2","","At a glance"),make("p","",r.overview||cut(excerpt(x),500)));left.append(lead);
 if(r.methods)left.append(section("HOW IT WAS STUDIED",r.methods,r.provenance));
 if(r.findings)left.append(section("WHAT THE PAPER REPORTS",r.findings,r.provenance));
 if(r.limitations)left.append(section("LIMITATIONS",r.limitations,r.provenance));
 if(!r.methods&&!r.findings)left.append(make("div","citation-notice","The accessible source does not contain an identifiable method or result. This is a discovery record, not a verified research summary."));
 if(x.abstract_text){const details=make("details"),box=make("section","reading-section");add(details,make("summary","","Show the indexed abstract"),make("p","",x.abstract_text));box.append(details);left.append(box)}
 left.append(make("p","paper-smallprint",r.notice||"Automatically indexed material. Verify the original publication before citing findings."));
 const at=make("section","paper-side-block");add(at,make("p","eyebrow","SOURCE INFORMATION"),make("h3","","Reading details"));
 for(const [k,v] of [["Published",date(x.published)],["Venue",x.venue||"Not supplied"],["Coverage",depthName(x)],["Evidence",x.relation||"Unclassified"],["Provenance",r.provenance||x.source||"Index"]])at.append(paperFact(k,v));
 if(r.sample)at.append(paperFact("Sample",r.sample));if(x.doi)at.append(paperFact("DOI",x.doi));right.append(at);
 if(x.analysis?.figures?.length){const fig=make("section","paper-side-block");add(fig,make("p","eyebrow","FIGURES IN THE SOURCE"),make("h3","","What to inspect"));for(const f of x.analysis.figures.slice(0,3))fig.append(add(make("div","figure-caption"),make("strong","",f.label||"Figure"),make("p","",f.caption||"Caption not extracted")));right.append(fig)}
 const paths=({"AI & cognition":["AI use","Cognitive activity","Attention"],"Fragmentation":["Interruption","Task switching","Recovery"],"Interventions":["Design change","User response","Focus"],"Technology & society":["Platforms","Incentives","Agency"]})[x.lane]||["Technology","Behavior","Outcome"];
 const pane=make("section","paper-side-block"),diagram=make("div","paper-diagram");add(pane,make("p","eyebrow","CONCEPTUAL CONTEXT"),make("h3","","A possible pathway"));
 paths.forEach((v,i)=>{diagram.append(make("span","",v));if(i<2)diagram.append(make("i","","→"))});add(pane,diagram,make("p","paper-smallprint","An illustrative question, not a reported causal model or reconstructed result."));right.append(pane);
 function valid(u){try{const v=new URL(u);return v.protocol==="https:"?u:null}catch{return null}}
 if(valid(x.url))right.append(link("Open original publication ↗",x.url,"paper-original"));
 if(valid(x.analysis?.fulltext_url))right.append(link("View open-access version ↗",x.analysis.fulltext_url,"paper-extra"));
 right.append(link("Search on Google Scholar ↗","https://scholar.google.com/scholar?q="+encodeURIComponent(x.title),"paper-extra"));
 let related=S.records.filter(y=>y!==x&&y.lane===x.lane&&depth(y)!=="citation_only").sort((a,b)=>rank(b)-rank(a)).slice(0,3);
 if(related.length){const panel=make("section","paper-side-block");add(panel,make("p","eyebrow","EXPLORE FURTHER"),make("h3","","Related papers"));for(const y of related)panel.append(btn(y.title,()=>goto("paper",id(y)),"paper-extra"));right.append(panel)}
 add(cols,left,right);add(area,btn("← Back to the library",()=>goto("library"),"back-button"),make("p","eyebrow paper-eyebrow","RESEARCH READING / "+(x.lane||"Research")),make("h1","paper-heading",x.title),make("p","paper-meta",meta),chips,cols)
}
function lab(){
 function updateTime(){let m=Math.floor(S.left/60),s=S.left%60;$("#focus-timer").textContent=String(m).padStart(2,"0")+":"+String(s).padStart(2,"0")}
 function pause(){if(S.timer)clearInterval(S.timer);S.timer=null;S.running=false;$("#focus-toggle").textContent="Start focus session"}
 function reset(){pause();S.left=S.duration*60;updateTime();$("#focus-caption").textContent="A small commitment to one task"}
 $$("[data-duration]").forEach(b=>b.onclick=()=>{$$("[data-duration]").forEach(x=>x.classList.toggle("selected",x===b));S.duration=Number(b.dataset.duration);reset()});
 $("#focus-reset").onclick=reset;
 $("#focus-toggle").onclick=()=>{if(S.running){pause();return}if(!S.left)reset();S.running=true;$("#focus-toggle").textContent="Pause session";$("#focus-caption").textContent=$("#focus-task").value.trim()||"Stay with your chosen intention";let last=Date.now();S.timer=setInterval(()=>{let now=Date.now(),elapsed=Math.floor((now-last)/1000);if(elapsed<=0)return;last+=elapsed*1000;S.left=Math.max(0,S.left-elapsed);updateTime();if(!S.left){pause();$("#focus-caption").textContent="Focus session complete."}},250)};
 const prompts={1:"Before asking for an explanation, write down one mechanism you suspect is involved. What evidence would disconfirm it?",2:"Consider cognitive offloading: a provided summary may change how much original material the learner processes. What alternative explanations could account for the same result?",3:"A possible reasoning plan:\n1. Define recall versus comprehension.\n2. Compare reading-only, summary-only and mixed conditions.\n3. Measure immediate and delayed outcomes.\n4. Consider prior knowledge and motivation.\n5. Test competing mechanisms."};
 $$("[data-scaffold]").forEach(b=>b.onclick=()=>{$$("[data-scaffold]").forEach(x=>x.classList.toggle("selected",x===b));$("#scaffold-output").textContent=prompts[b.dataset.scaffold]});
 $("#resume-save").onclick=()=>{let task=$("#resume-context").value.trim(),next=$("#resume-next").value.trim();if(!task||!next){$("#resume-output").textContent="Add both a task and a next step first.";return}S.checkpoint={task,next};$("#resume-output").textContent="Checkpoint saved in this page. Now simulate an interruption.";$("#resume-interrupt").disabled=false;$("#resume-restore").disabled=true};
 $("#resume-interrupt").onclick=()=>{if(!S.checkpoint)return;$("#resume-context").value="";$("#resume-next").value="";$("#resume-output").textContent="Interruption simulated. Your checkpoint is hidden. Choose Resume to restore it.";$("#resume-interrupt").disabled=true;$("#resume-restore").disabled=false};
 $("#resume-restore").onclick=()=>{if(!S.checkpoint)return;$("#resume-context").value=S.checkpoint.task;$("#resume-next").value=S.checkpoint.next;$("#resume-output").textContent="Your task: "+S.checkpoint.task+"\nYour next step: "+S.checkpoint.next;$("#resume-interrupt").disabled=false;$("#resume-restore").disabled=true};
}
async function init(){
 lab();
 try{
  const rs=await Promise.all(["data/library.json","data/weekly.json","data/runs.json"].map(p=>fetch(p+"?v="+Date.now(),{cache:"no-store"})));
  if(!rs[0].ok)throw new Error("Library download failed (HTTP "+rs[0].status+")");
  S.records=await rs[0].json();if(!Array.isArray(S.records))throw new Error("Unexpected library format");
  S.week=rs[1].ok?await rs[1].json():{run:{mode:"unavailable"},items:[]};
  S.runs=rs[2].ok?await rs[2].json():[];
  home();showLibrary();route();
 }catch(e){$("#issue-label").textContent="INDEX OFFLINE";$("#issue-meta").textContent="Research data could not load";$("#feature-grid").replaceChildren(make("div","empty-state","Could not load the research archive: "+e.message));route()}
}
$$("[data-route]").forEach(a=>a.onclick=e=>{e.preventDefault();goto(a.dataset.route)});
["search","topic-filter","depth-filter","type-filter"].forEach(s=>$("#"+s).addEventListener(s==="search"?"input":"change",showLibrary));
window.addEventListener("hashchange",route);
init();
