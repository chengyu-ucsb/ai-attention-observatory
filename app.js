"use strict";
const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
const S={records:[],companions:[],week:{},issue:{},runs:[],backlog:{},duration:10,left:600,timer:null,running:false,checkpoint:null};
const themes=[["AI & cognition","When thinking is delegated","Offloading, metacognition and reasoning","◎","#a52c3e"],["Fragmentation","The cost of switching","Distraction, interruptions and re-entry","↗","#d77c83"],["Interventions","Designing for focus","Focus tools and digital well-being","✳","#bf7868"],["Technology & society","Who shapes attention?","Platform incentives and human agency","◇","#947783"]];
const depths=[["full_text","Full-text sections","#a52c3e"],["abstract","Abstract-based","#d78f98"],["curated","Curated synopsis","#c6a6a9"]];
function make(t,c,s){const e=document.createElement(t);if(c)e.className=c;if(s!==undefined){if(s!==null&&typeof s==="object")throw new TypeError("make() accepts text only; use add() to append elements");e.textContent=String(s)}return e}
function add(p,...els){for(const e of els)if(e)p.append(e);return p}
function btn(s,fn,c){const e=make("button",c,s);e.type="button";e.onclick=fn;return e}
function link(s,u,c){const e=make("a",c,s);e.href=u;if(u.startsWith("https://")){e.target="_blank";e.rel="noopener noreferrer"}return e}
function date(s){if(!s||!/^20\d\d/.test(s))return "Undated";let d=new Date(s.slice(0,10)+"T12:00:00Z");return isNaN(d.getTime())?"Undated":d.toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"})}
function id(x){return String(x.doi||x.url||x.title)}
function record(k){const found=S.records.find(x=>id(x)===k||(x.legacy_urls||[]).includes(k))||S.companions.find(x=>id(x)===k||(x.legacy_urls||[]).includes(k));return found?.companion_to?S.records.find(x=>id(x)===found.companion_to)||found:found}
function depth(x){return x.reading?.level||"citation_only"}
function depthName(x){if(x.kind==="nonacademic"&&depth(x)!=="citation_only"){const src=x.reading?.digest?.longform?.source_depth;return src==="read_article"?"Reviewed essay":src==="machine_read_full_article"?"Article-based synthesis":src==="product_documentation"?"Product documentation":src==="editorial_synopsis"?"Editorial synopsis":"Publisher synopsis";}return ({"full_text":"Full-text excerpts","abstract":"Abstract-based","curated":"Curated overview","citation_only":"Citation only"})[depth(x)]}
function excerpt(x){return x.reading?.findings||x.reading?.overview||x.preview||"Citation only."}

function readableSourceTitle(x){
 // Preserve the exact bibliographic title in the data, but avoid shouting
 // ALL-CAPS titles at readers throughout the website.
 const title=String(x?.title||"").replace(/\s+/g," ").trim();
 const letters=title.match(/[A-Za-z]/g)||[],upper=title.match(/[A-Z]/g)||[];
 if(letters.length<12||upper.length/letters.length<.76)return title;
 let normalized=title.toLowerCase().replace(/\b(?:ai|genai|llm|llms|hci|vr|ar|xr|nlp|ux|stem|ict|it|sem|ml|gpt|chatgpt|lms|eu|usa|us|uk|sdg|covid)\b/gi,m=>({
  ai:"AI",genai:"GenAI",llm:"LLM",llms:"LLMs",hci:"HCI",vr:"VR",ar:"AR",xr:"XR",
  nlp:"NLP",ux:"UX",stem:"STEM",ict:"ICT",it:"IT",sem:"SEM",ml:"ML",
  gpt:"GPT",chatgpt:"ChatGPT",lms:"LMS",eu:"EU",usa:"USA",us:"US",uk:"UK",sdg:"SDG",covid:"COVID"
 })[m.toLowerCase()]);
 return normalized.slice(0,1).toUpperCase()+normalized.slice(1);
}
function artTopic(x){
 const title=String(x?.title||"").toLowerCase(),lane=String(x?.lane||"");
 if(/notification|alerts?|hover effect|interrupt/.test(title))return "notification";
 if(/trust|verification|reliability|credib|consent/.test(title))return "trust";
 if(/measurement|measure|scale develop|construct definition|psychometr/.test(title))return "measurement";
 if(/reflect|metacognit|self.regulat|deliberat|mindful/.test(title))return "reflection";
 if(/washout|recover|reversib|skill decay|skill retention/.test(title))return "recovery";
 if(/creativ|co.creat|writing|content generation|artwork|language model/.test(title))return "creativity";
 if(/research process|doctoral research|scientific reasoning|knowledge production/.test(title))return "research";
 if(/critical thinking|reasoning|judgment|judgement/.test(title))return "critical";
 if(/offload|reliance|dependenc|autonom|agency transfer/.test(title))return "offloading";
 if(/distraction|switching|multitask|fragment/.test(title))return "fragmentation";
 if(/well.being|wellbeing|mental health|technostress|stress|resilien/.test(title))return "wellbeing";
 if(/workplace|employee|gig.work|algorithmic management|workforce|professional/.test(title))return "work";
 if(/intervention|design|interface|tools?|mitigat|protect|regulat/.test(title))return "interventions";
 if(/pedagog|educat|teaching|student|learning|literacy/.test(title))return "learning";
 if(/platform|policy|governance|ethic|social media|recommendation|trust economy/.test(title))return "society";
 if(lane==="Fragmentation")return "fragmentation";
 if(lane==="Interventions")return "interventions";
 if(lane==="Technology & society")return "society";
 return "focus";
}
function editorialImage(x,context="reading"){
 const img=make("img","story-image");
 img.src="assets/reading-"+artTopic(x)+".svg";
 img.alt="Conceptual editorial illustration for "+(x?.lane||"the research theme")+
   "; it does not show measured study data";
 img.loading=context==="reading"?"eager":"lazy";
 img.decoding="async";
 img.width=880;img.height=530;
 return img;
}
function editorialMedia(x,context="reading"){
 const fig=make("figure","story-visual story-visual-"+context);
 fig.append(editorialImage(x,context));
 if(context==="reading")
  fig.append(make("figcaption","story-visual-caption",
    "Editorial illustration · not a visualization of study findings"));
 return fig;
}

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
function cleanLead(s,sourceTitle=""){
 // Keep claims and qualifiers intact while avoiding paper-centred introductions.
 let x=String(s||"").replace(/\s+/g," ").trim();
 x=x.replace(/^(?:the authors|the researchers|we) (?:found|observed|reported|showed) that\s+/i,"");
 x=x.replace(/^(?:this study|the study|our results|the findings|the results) (?:found|reported|showed|show|indicate|indicated) that\s+/i,"");
 x=x.replace(/^(?:the authors|the researchers) (?:argue|suggest|propose) that\s+/i,"A possible explanation is that ");
 x=x.replace(/^(?:this study|the study|this paper|the paper) compares?\s+/i,"A comparison of ");
 x=x.replace(/^(?:this study|the study|this paper|the paper) (?:examines?|investigates?|explores?|assesses?|evaluates?|analy[sz]es?|discusses?|tests?)\s+/i,"");
 x=x.replace(/^(?:the authors|the researchers)['’] (?:analysis|findings|results)\s+/i,"Results ");
 x=x.replace(/^(?:the authors|the researchers) (?:describe|discuss|review|consider|examine)\s+/i,"");
 // If an abstract never reaches a finding and merely introduces the paper,
 // show its research topic rather than advertise the introduction as an insight.
 if(sourceTitle&&/^(?:(?:this|the|our) (?:study|paper|article|research)\b|(?:the authors|the researchers)\b|we (?:found|show|argue)\b)/i.test(x)){
  return String(sourceTitle).trim();
 }
 const letters=x.match(/[A-Za-z]/g)||[],uppers=x.match(/[A-Z]/g)||[];
 if(letters.length>17&&uppers.length/letters.length>.80){x=readableSourceTitle({title:x});}
 return x?x[0].toUpperCase()+x.slice(1):"";
}
function shortIdea(x,limit=105){
 const d=x.reading?.digest||{};
 // Source findings and edited ideas take priority. The common fallback is a
 // visibly topic-framed question, never an all-caps bibliographic title.
 const value=d.status==="editorially_written_from_indexed_sections"?
    d.idea||d.finding:d.finding||d.idea||readableSourceTitle(x);
 return cut(cleanLead(value,readableSourceTitle(x)),limit);
}
function ideaInfo(x){
 const r=x.reading||{},d=r.digest||{},notes=x.editorial_notes||{};
 let value="",label="";
 if(x.research_type==="conceptual_framework"){
  value=d.idea||r.overview||"";
  label="CONCEPTUAL FRAMEWORK / NOT AN EMPIRICAL FINDING";
 }else if(x.kind!=="scholarly"){
  value=d.idea||notes.argument||r.overview||"";
  label=notes.argument?"PERSPECTIVE / ATTRIBUTED":"PUBLISHER SYNOPSIS";
 }else if(d.status==="editorially_written_from_indexed_sections"&&d.idea){
  value=d.idea;label="EDITORIAL TAKEAWAY / SOURCE-GROUNDED";
 }else if(d.finding){
  value=d.finding;
  label=d.finding_source==="abstract"?"RESULT FROM ABSTRACT":
    d.finding_source==="full_text"?"RESULT FROM FULL TEXT":"SOURCE-DERIVED RESULT";
 }else{
  value=d.idea||r.overview||"";label="RESEARCH TOPIC / NOT AN ESTABLISHED FINDING";
 }
 return {text:cleanLead(value,readableSourceTitle(x))||"No substantive source text is available.",label};
}
function rank(x){let r=x.reading||{},v=({"full_text":80,"abstract":46,"curated":25,"citation_only":0})[depth(x)]||0;v+=r.digest?.finding?26:0;v+=r.methods?10:0;v+=r.limitations?4:0;v+=x.lane==="AI & cognition"||x.lane==="Interventions"?6:0;v+=/ai|generative|chatgpt|attention|offloading|focus/i.test(x.title)?9:0;v+=x.relation==="Adjacent digital-attention evidence"?-25:0;return v}
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
   const b=matches?btn(readableSourceTitle(src),()=>goto("paper",id(matches)),"issue-ref"):link(readableSourceTitle(src),src.url||"#library","issue-ref");
   container.append(b);
 }
 return container;
}
function renderIssueLandscape(issue){
 const root=$("#issue-source-landscape");if(!root)return;root.replaceChildren();
 const n=Number(issue.source_count)||0;
 const groups=[
  {title:"WHAT WE READ",rows:[["Scholarly literature",Number(issue.types?.scholarly)||0],["Public essays & other sources",Number(issue.types?.commentary)||0]],note:"Material covered by this edition, not evidence of agreement."},
  {title:"HOW MUCH SOURCE TEXT",rows:[["Full-text extracts",Number(issue.material?.full_text)||0],["Abstract-based",Number(issue.material?.abstract)||0],["Publisher or editorial synopses",Number(issue.material?.publisher_or_editorial)||0]],note:"Coverage depth, not confidence in conclusions."}
 ];
 for(const [groupIndex,g] of groups.entries()){
  const card=make("div","issue-mix-card");
  const top=make("div","issue-mix-heading");
  add(top,make("span","eyebrow",g.title),make("strong","",n+" sources"));
  card.append(top);
  const bar=make("div","issue-mix-bar");
  bar.setAttribute("role","img");
  bar.setAttribute("aria-label",g.rows.map(([name,value])=>name+": "+value).join("; "));
  g.rows.forEach(([label,value],i)=>{
    if(value<=0)return;
    const piece=make("span","issue-mix-segment mix-"+groupIndex+"-"+i);
    piece.style.width=(n?100*value/n:0)+"%";
    piece.title=label+": "+value;
    bar.append(piece)
  });
  card.append(bar);
  const legend=make("div","issue-mix-legend");
  g.rows.forEach(([label,value],i)=>{
   const item=make("div","issue-mix-legend-item");
   add(item,make("span","issue-mix-key mix-"+groupIndex+"-"+i),make("span","",label),make("strong","",String(value)));
   legend.append(item)
  });
  add(card,legend,make("p","issue-mix-caveat",g.note));
  root.append(card)
 }
}
function renderIssue(){
 const issue=S.issue||{},published=issue.status==="published";
 const edition=issue.edition_date||S.week.run?.date||"";
 const sourceCount=Number(issue.source_count)||0;
 renderIssueLandscape(issue);
 $("#weekly-kicker").textContent=published?"THE ATTENTION EDIT · ISSUE "+issue.number:"THE ATTENTION EDIT";
 $("#weekly-title").textContent=published?issue.headline:"Good questions about AI and attention.";
 $("#weekly-deck").textContent=published?issue.deck:"Browse research and ideas about thinking, distraction, and how we work with AI.";
 $("#weekly-scope").textContent=published?"An issue of The Attention Edit · "+date(edition):"Browse the research library for the latest findings.";
 $("#issue-edition").textContent=published?"THE ATTENTION EDIT / ISSUE "+issue.number+" / "+date(edition):"THE ATTENTION EDIT";
 $("#issue-headline").textContent=published?issue.headline:"Ideas for thinking clearly.";
 $("#issue-deck").textContent=published?issue.deck:"Explore research, commentary, and experiments about AI and attention.";
 $("#issue-letter-text").textContent=published?issue.letter:"Start with a question, follow the evidence, and explore the research library.";
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
 $("#issue-qualification").textContent="";
 $("#issue-coverage").textContent="Explore the original research and reporting behind these ideas.";
 const shelf=$("#issue-sources");shelf.replaceChildren();
 for(const [i,src] of (issue.sources||[]).entries()){
  const r=make("div","issue-shelf-item");let candidate=S.records.find(x=>id(x)===src.id);
  const title=candidate?btn(readableSourceTitle(src),()=>goto("paper",src.id)):link(readableSourceTitle(src),src.url||"#library");
  add(r,make("span","issue-shelf-number",String(i+1).padStart(2,"0")),add(make("div","issue-shelf-content"),title,make("p","",[src.venue,src.reading_level==="full_text"?"Full-text extract":src.reading_level==="abstract"?"Abstract-based":"Publisher/editorial"].filter(Boolean).join(" · "))));
  shelf.append(r);
 }
}

function home(){
 const run=S.week.run||{},all=(S.week.items||[]).map(x=>record(id(x))||S.records.find(r=>r.title===x.title)||x);
 const top=all.filter(x=>x.kind==="scholarly"&&depth(x)!=="citation_only"&&x.reading?.digest?.finding).sort((a,b)=>rank(b)-rank(a)).filter(x=>x.relation!=="Adjacent digital-attention evidence"||!all.some(y=>y.relation!=="Adjacent digital-attention evidence"&&y.reading?.digest?.finding)).slice(0,3);
 const start=run.mode==="curated-starter";$("#issue-label").textContent=start?"STARTER COLLECTION / LIVE UPDATE PENDING":"LATEST INDEX / "+date(run.date);$("#issue-meta").textContent=(run.last_seven_days??all.length)+" recently indexed · "+S.records.length+" total";
 const root=$("#feature-grid");root.replaceChildren();
 if(!top.length)root.append(make("div","empty-state","The latest index contains no source-rich highlights yet. Browse the research library."));
 top.forEach((x,i)=>{const c=make("article","feature-card"+(i===0?" primary":"")),head=make("div","feature-top"),foot=make("div","feature-foot");
 add(head,make("span","feature-number",String(i+1).padStart(2,"0")),make("span","feature-icon",["◎","↗","✳"][i]));
 add(foot,make("span","source-pill",depthName(x)),btn("Read the evidence ↗",()=>goto("paper",id(x)),"feature-go"));
 add(c,head,editorialMedia(x,"feature"),make("p","feature-idea-label",ideaInfo(x).label),make("h3","feature-idea",shortIdea(x,96)),make("p","feature-source-title",readableSourceTitle(x)),make("p","source-meta",(x.venue||"")+" · "+date(x.published)),featureCoverage(x),foot);root.append(c)});
 // Provider diagnostics belong in repository workflow logs, never in public content.
 renderEditorial();
 topicBars("#topic-bars");donut();
 const grid=$("#lens-grid");grid.replaceChildren();themes.forEach(t=>{const a=link("","#library","lens");a.setAttribute("aria-label","Explore "+t[0]);a.onclick=e=>{e.preventDefault();$("#topic-filter").value=t[0];goto("library")};add(a,make("span","lens-mark",t[3]),make("h3","",t[1]),make("p","",t[2]),make("span","",S.records.filter(x=>x.lane===t[0]).length+" records →"));grid.append(a)});
 const arr=$("#arrivals-body");arr.replaceChildren();
 const sorted=S.records.filter(x=>depth(x)!=="citation_only").slice().sort((a,b)=>(b.published||"").localeCompare(a.published||"")).slice(0,7);
 for(const x of sorted){let tr=make("tr"),name=make("td"),go=make("td","align-right");name.append(btn(shortIdea(x,94),()=>goto("paper",id(x))));name.append(make("span","arrival-source-title",readableSourceTitle(x)));go.append(btn("↗",()=>goto("paper",id(x))));add(tr,make("td","mono-date",date(x.published)),name,make("td","",x.lane||"Research"),make("td","coverage-tag",depthName(x)),go);arr.append(tr)}
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
  add(card,editorialMedia(x,"editorial"),label,articleTitle,make("p","editorial-source-title",readableSourceTitle(x)),foot);root.append(card)
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
    const summary=make("p","perspective-source-title",readableSourceTitle(x));
    const bottom=make("div","perspective-bottom");
    add(bottom,make("span","",x.venue||"Original source"),btn("Read source notes ↗",()=>goto("paper",id(x)),"editorial-cta"));
    add(item,editorialMedia(x,"perspective"),icon,label,title,summary,bottom);container.append(item);
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
 const q=$("#search").value.trim().toLowerCase(),t=$("#topic-filter").value,d=$("#depth-filter").value,k=$("#type-filter").value,scope=$("#scope-filter").value;
 const xs=S.records.filter(x=>(!q||[x.title,x.venue,x.abstract_text,x.preview,x.reading?.findings,x.reading?.methods,(x.authors||[]).join(" ")].join(" ").toLowerCase().includes(q))&&(!t||x.lane===t)&&(!k||x.kind===k)&&(
   scope==="all"||(scope==="core"&&x.source_group==="AI-specific")||
   (scope==="adjacent"&&x.source_group==="Adjacent digital-attention evidence")||
   (scope==="historical"&&/^(Earlier|Historical)/.test(x.source_group||""))
  )&&(d!=="full_text"||depth(x)==="full_text")).sort((a,b)=>(b.published||"").localeCompare(a.published||"")||rank(b)-rank(a));
 $("#library-count").textContent=xs.length+" matching sources · "+S.records.length+" in the complete archive";
 const box=$("#library-results");box.replaceChildren();
 if(!xs.length){box.append(make("div","empty-state","No source-backed items match those filters. Try a broader search."));return}
 for(const x of xs){
  const c=make("article","library-card library-story"),body=make("div","library-story-body"),h=make("h3"),foot=make("div","card-foot");
  const image=editorialMedia(x,"card");
  image.onclick=()=>goto("paper",id(x));
  image.setAttribute("role","button");
  image.tabIndex=0;
  image.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();goto("paper",id(x));}});
  h.append(btn(shortIdea(x,115),()=>goto("paper",id(x))));
  add(foot,make("span","",date(x.published)+" · "+(x.venue||"")),make("span","",depthName(x)));
  if(/^(Earlier|Historical)/.test(x.source_group||""))foot.append(make("span","", "Earlier foundation"));
  add(body,make("span","card-type",ideaInfo(x).label),h,make("p","library-citation",readableSourceTitle(x)),foot);
  add(c,image,body);box.append(c);
 }
}
function showAtlas(){
 const cc=counts(),n=S.records.length,stat=$("#atlas-stats");stat.replaceChildren();
 for(const [label,value] of [["Indexed sources",n],["Abstract readings",cc.abstract],["Full-text excerpts",cc.full_text],["Records with findings",S.records.filter(x=>x.reading?.digest?.finding).length]]){let c=make("div","atlas-stat");add(c,make("strong","",value),make("span","",label));stat.append(c)}
 topicBars("#atlas-topic-bars");
 const years={};for(let y=2023;y<=new Date().getFullYear();y++)years[String(y)]=0;
 S.records.forEach(x=>{const y=(x.published||"").slice(0,4);if(x.source_group==="AI-specific"&&Object.prototype.hasOwnProperty.call(years,y))years[y]++});
 const foundation=S.records.filter(x=>/^(Earlier|Historical)/.test(x.source_group||"")).length;
 $("#year-context").textContent="AI-specific records published in 2023–"+new Date().getFullYear()+". "+foundation+" earlier foundation"+(foundation===1?" is":"s are")+" excluded from this chart but remain searchable. These counts describe this collection, not the field’s total publications.";
 const values=Object.entries(years),max=Math.max(1,...values.map(x=>x[1])),chart=$("#year-chart");chart.replaceChildren();
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
  if(idea)return cut(cleanLead(idea,readableSourceTitle(x)),145);
 }
 return shortIdea(x,145);
}
function comparisonArtwork(title,columns,caption){
 const w=make("section","article-concept-art article-data-visual");
 add(w,make("p","eyebrow","RESEARCH DESIGN / SOURCE-GROUNDED COMPARISON"),make("h3","figure-insight-title",title));
 const grid=make("div","source-comparison-grid");
 columns.forEach(([k,label,desc])=>add(grid,add(make("article","source-comparison-card"),make("span","source-comparison-num",k),make("h4","",label),make("p","",desc))));
 add(w,grid,make("p","concept-note",caption));
 return w;
}
function reviewArtwork(){
 const w=make("section","article-concept-art article-data-visual");
 add(w,make("p","eyebrow","REVIEW COVERAGE / REPORTED SOURCE COUNT"),make("h3","figure-insight-title","A literature map, not a controlled intervention"));
 const row=make("div","review-big-number");
 add(row,make("strong","", "123"),make("span","","studies included"),make("p","","Two interpretive patterns: agency-supportive and agency-eroding uses of AI. The reviewed studies are heterogeneous."));
 add(w,row,make("p","concept-note","123 is the included-study count reported in the source's Results, not a count of positive, negative, or causal effects."));
 return w;
}
function wellbeingArtwork(){
 const w=make("section","article-concept-art article-data-visual");
 add(w,make("p","eyebrow","REVIEW EVIDENCE / TWO REPORTED ENDPOINTS"),make("h3","figure-insight-title","Interest in digital well-being research grew"));
 const bars=make("div","review-year-bars");
 [["2008",2],["2024",43]].forEach(([year,n])=>{
  const row=make("div","review-year-row");
  const track=make("div","review-year-track"),bar=make("span","review-year-fill");
  bar.style.width=(n/43*100)+"%";track.append(bar);
  add(row,make("span","",year),track,make("strong","",n+" papers"));bars.append(row)
 });
 add(w,make("p","review-kicker","240 PUBLICATIONS CONSIDERED IN TOTAL"),bars,make("p","concept-note","The paper reports 2 included publications for 2008 and 43 for 2024; only these two endpoints are shown. The bars do not reconstruct a complete annual time series or demonstrate intervention effectiveness."));
 return w;
}

/* Research graphics below are editorial representations of indexed source data.
   No arrows here imply causal effects; published figures are treated separately. */
function visualComparison(title,panels,caption,kind="comparison"){
 const figure=make("figure","article-concept-art article-data-visual evidence-graphic graphic-"+kind);
 add(figure,make("p","eyebrow","SOURCE-GROUNDED RESEARCH VISUAL"),
   make("h3","figure-insight-title",title));
 const graphic=make("div","evidence-graphic-grid");
 for(const [i,item] of panels.entries()){
  const [signal,heading,detail]=item;
  const card=make("div","evidence-graphic-panel graphic-panel-"+(i+1));
  add(card,make("span","graphic-signal",signal),
    make("strong","graphic-heading",heading),
    make("p","graphic-detail",detail));
  graphic.append(card);
 }
 add(figure,graphic,make("figcaption","concept-note",caption));
 return figure;
}
function visualStudyFlow(title,steps,caption){
 const figure=make("figure","article-concept-art article-data-visual evidence-graphic graphic-flow");
 add(figure,make("p","eyebrow","ILLUSTRATED RESEARCH DESIGN"),
   make("h3","figure-insight-title",title));
 const row=make("div","evidence-flow");
 for(const [i,step] of steps.entries()){
  if(i)row.append(make("span","graphic-arrow","→"));
  const node=make("div","evidence-flow-step");
  add(node,make("span","graphic-step-index",String(i+1).padStart(2,"0")),
    make("strong","",step[0]),
    make("p","",step[1]));
  row.append(node);
 }
 add(figure,row,make("figcaption","concept-note",caption));
 return figure;
}
function visualKeyStats(title,stats,caption){
 const figure=make("figure","article-concept-art article-data-visual evidence-graphic graphic-stats");
 add(figure,make("p","eyebrow","REPORTED STUDY DETAILS"),
   make("h3","figure-insight-title",title));
 const row=make("div","evidence-stats");
 for(const [value,label,detail] of stats){
  const pane=make("div","evidence-stat");
  add(pane,make("strong","evidence-stat-value",value),
    make("span","evidence-stat-label",label),
    make("p","evidence-stat-detail",detail));
  row.append(pane);
 }
 add(figure,row,make("figcaption","concept-note",caption));
 return figure;
}
function additionalArtwork(x){
 switch((x.doi||"").toLowerCase()){
  case "10.1007/s44217-026-02332-w":
   return visualComparison("Students described two ways AI enters their learning",[
    ["+","Support","AI was seen as helpful when used alongside independent work."],
    ["?","Overreliance","Students described lower confidence and reduced independent engagement."]
   ],"Themes from interviews with 15 postgraduate students in Morocco, not measured effects of AI on learning.");
  case "10.1515/humaff-2026-0011":
   return visualStudyFlow("How supportive help might become substitution",[
    ["Complement","AI supports the user's reasoning"],
    ["Delegate","Trust can expand what is handed to AI"],
    ["Substitute","Essential reasoning may be practiced less"]
   ],"A proposed six-step theoretical account simplified into three stages. This is a hypothesis, not an observed longitudinal progression.");
  case "10.3389/fpsyg.2026.1960382":
   return visualComparison("Two appraisals of algorithmic management",[
    ["↗","Challenge","More positive appraisal was associated with better workplace well-being."],
    ["↘","Threat","More threatening appraisal was associated with poorer well-being."]
   ],"Survey of 389 food-delivery workers in China. These are reported associations, not causal effects.");
  case "10.1177/21582440261497404":
   return visualComparison("Trust in AI was linked to contrasting pathways",[
    ["+","Perceived usefulness and confidence","These were positively associated with critical thinking."],
    ["−","Cognitive offloading","This was negatively associated with critical thinking."]
   ],"Survey-based structural model. Symbols indicate directions of association, not experimental effect sizes.");
  case "10.1080/17501229.2026.2730676":
   return visualKeyStats("Patterns of AI-assisted writing",[
    ["540","English writers","Survey participants"],
    ["4","Engagement profiles","Different approaches to evaluation and automation"]
   ],"Reported study design and profile count. The graphic does not indicate the prevalence of each profile.");
  case "10.3389/feduc.2026.1952725":
   return visualStudyFlow("The AI-integrated classroom activity",[
    ["Prepare","Students used AI to prepare short lessons"],
    ["Teach","Students presented lessons to peers"],
    ["Discuss","Classroom discussion covered responsible AI use"]
   ],"Classroom activity undertaken by 104 undergraduates. Students reported positive experiences; this sequence does not prove learning gains.");
  case "10.48550/arxiv.2609.38029":
   return visualComparison("The 14-student pilot had mixed learning measures",[
    ["↗","Course learning and AI literacy","Pre/post scores rose in reported measures."],
    ["=","Standardized critical thinking","Test percentiles did not change."]
   ],"Small uncontrolled design-based research pilot; the graphic shows reported directional differences, not comparable effect sizes.");
  case "10.21203/rs.3.rs-10212076/v1":
   return visualComparison("Two forms of offloading, different links with processing",[
    ["+","Scaffolded offloading","Positively associated with deeper processing after the AI answer."],
    ["−","Substitutive offloading","Negatively associated with deeper processing after the AI answer."]
   ],"Associations from a 426-student survey and modeled pathways. These are not causal effects.");
  case "10.3389/fcomm.2026.1828344":
   return visualComparison("Two ways to think about cultural recommendation",[
    ["◎","Attention economy","Platforms compete to surface content and capture attention."],
    ["◇","Trust economy","AI-era discovery raises questions of origin, authenticity, and trust."]
   ],"Conceptual comparison proposed by the paper; not an empirically documented market-wide shift.");
  case "10.3390/educsci16091470":
   return visualKeyStats("What Dutch medical educators discussed",[
    ["17","Educators interviewed","Qualitative interview study"],
    ["3","Themes","Value, thinking risks, and responsible integration"]
   ],"Counts from the source abstract. Themes are reported qualitative categories, not outcome frequencies.");
  case "10.54359/ps.v19i108.2216":
   return visualComparison("Interface feedback changed how notifications mattered",[
    ["✓","Hover feedback","Helped sustained-attention accuracy in some task conditions."],
    ["~","Notifications with content","The sustained-attention advantage disappeared in this condition."]
   ],"Findings summarized from five experiments using attention tasks; no universal claim that notifications improve or worsen attention.");
  case "10.3389/fpsyg.2026.1832219":
   return visualComparison("What the adolescent smartphone review suggests",[
    ["↘","Excessive use","Modest associations with some sleep and attentional difficulties."],
    ["?","School phone restrictions","Some classroom attention improvements; long-term effects unclear."]
   ],"Narrative review of heterogeneous evidence; not a pooled causal estimate.");
  case "10.36948/ijfmr.2026.v08i05.87207":
   return visualKeyStats("What ten digital well-being tools were reviewed for",[
    ["10","Tools examined","Public documentation and exploratory observations"],
    ["4","Common approaches","Usage monitoring, blocking, focus tools, and timers"]
   ],"An exploratory comparison. Four approaches are an editorial grouping, not four exhaustive study-coded categories.");
  case "10.31234/osf.io/wy8z3_v1":
   return visualStudyFlow("A proposed research program, not a validated scale",[
    ["Define","Distinguish fragmentation from related constructs"],
    ["Develop","Generate measures and proposed dimensions"],
    ["Validate","Test reliability and validity in future samples"]
   ],"Proposed program in a conceptual manuscript. No new validation data were reported.");
  case "10.35542/osf.io/64qz7_v1":
   return visualStudyFlow("The unanswered question after AI withdrawal",[
    ["With AI","Performance can differ under assistance"],
    ["Withdraw","Remove the tool and observe independent work"],
    ["Follow up","Test whether performance rebounds or persists"]
   ],"Proposed longitudinal protocol. The recovery paths are hypotheses and have not been observed in this manuscript.");
  case "10.1007/s10648-026-10224-6":
   return visualComparison("Which thinking should the learner still do?",[
    ["✓","Peripheral operations","Offloading nonessential operations may support the main learning goal."],
    ["!","Constitutive processing","Offloading the very work needed to learn may undermine skill building."]
   ],"Theoretical framework, not a new experiment. Outcomes depend on the learning goal and subsequent processing.");
  default:return null;
 }
}

function automaticEvidenceArtwork(x){
 const spec=x.visual||{};
 if(x.kind!=="scholarly"||!["evidence_snapshot","research_design"].includes(spec.kind))return null;
 const blocks=Array.isArray(spec.blocks)?spec.blocks.filter(b=>b&&typeof b.label==="string"&&typeof b.text==="string"&&b.text.length<=230).slice(0,3):[];
 if(!blocks.length)return null;
 const figure=make("figure","article-concept-art article-data-visual automatic-evidence");
 add(figure,make("p","eyebrow",spec.status==="edited"?"RESEARCH SNAPSHOT":"SOURCE-BASED READING"),
    make("h3","figure-insight-title",spec.kind==="evidence_snapshot"?"What the evidence supports":"How this question was studied"));
 const board=make("div","auto-evidence-board");
 blocks.forEach((block,i)=>{
  const item=make("div","auto-evidence-item");
  add(item,make("span","auto-evidence-n",String(i+1).padStart(2,"0")),
    make("strong","auto-evidence-label",block.label),make("p","auto-evidence-text",block.text));
  board.append(item);
 });
 add(figure,board,make("figcaption","concept-note",
   "Visual summary based on the "+(spec.basis==="full_text"?"indexed full text":"available abstract")+
   ". Not an effect-size chart, causal model, or reproduction of published figures."));
 return figure;
}
function conceptArtwork(x){
 const doi=(x.doi||"").toLowerCase();
 if(doi==="10.3389/fpsyg.2026.1878629")return comparisonArtwork("Two ways of offloading to AI",[
   ["A","Dependent offloading","Greater reliance on AI output while yielding cognitive authority; in this survey linked to lower intrinsic motivation."],
   ["B","Autonomous offloading","Delegation with a different pattern of retained agency and motivation, not necessarily the same as dependency."]
  ],"The three-wave survey reports associations with perceived functioning. This graphic contrasts concepts; it does not reproduce a causal diagram or quantify effect sizes.");
 if(doi==="10.3390/jintelligence14080182")return comparisonArtwork("Whose work does AI-assisted teaching feel like?",[
   ["239","Preservice teachers","Survey respondents recruited by convenience sampling in eastern China."],
   ["↗","Ownership concern","Dependency was associated with concern over the ownership of one's instructional design work."]
  ],"Source-derived study design and association. The cross-sectional survey cannot establish which came first or prove AI caused the concern.");
 if(doi==="10.3390/bs16071150")return reviewArtwork();
 if(doi==="10.2196/69533")return wellbeingArtwork();
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
 if(doi==="10.58304/ijts.260930")return comparisonArtwork("Two sources of evidence in one study",[
   ["450","University students","Questionnaire responses from five universities, analyzed using structural equation models."],
   ["20","Follow-up interviews","Selected learners described how they approached AI-assisted problem solving."]
  ],"The study used an explanatory sequential mixed-methods design. Sample counts are reported by the authors, not estimates of how many students benefited.");
 if(doi==="10.3389/fpsyg.2026.1930030"){
  const w=make("figure","article-concept-art article-data-visual article-results-chart");
  add(w,make("p","eyebrow","REPORTED MODEL COEFFICIENTS"),make("h3","figure-insight-title","Which predictors stood out?"));
  const chart=make("div","study-coefficients");
  [
   ["Stress level",0.384],["Social-media duration",0.297],
   ["Notifications",0.213],["App openings",0.186]
  ].forEach(([name,n])=>{
   const row=make("div","study-coefficient-row");
   const bar=make("span","study-coefficient-bar"),track=make("div","study-coefficient-track");
   bar.style.width=(n/0.384*100).toFixed(1)+"%";
   add(track,bar);add(row,make("span","study-coefficient-name",name),track,make("strong","study-coefficient-value",n.toFixed(3)));
   chart.append(row);
  });
  add(w,chart,make("figcaption","concept-note","Positive LASSO coefficients reported by the authors for associations with academic impact (n = 799). These are model coefficients, not effect sizes or evidence of causation. This study does not test generative AI."));
  return w;
 }
 // Show a source-grounded explanatory graphic only for validated studies.
 return additionalArtwork(x)||automaticEvidenceArtwork(x);
}
function showPaper(x){
 const root=$("#paper-content");
 root.replaceChildren();
 if(!x){root.append(make("div","empty-state","This reading is no longer in the public index."));return;}
 const r=x.reading||{},d=r.digest||{},editorial=d.status==="editorially_written_from_indexed_sections";
 const scholarly=x.kind==="scholarly",hasFinding=Boolean(d.finding),conceptual=x.research_type==="conceptual_framework";
 const isQuestion=scholarly&&!hasFinding&&!editorial;
 // Unreviewed extracts are identifiable as source notes, not hand-written insight.
 const headline=editorial?d.idea:hasFinding?d.finding:d.idea||x.title;
 const main=make("article","rv-article");
 const back=btn("← All readings",()=>goto("library"),"rv-back");
 const head=make("header","rv-head");
 const metadata=make("div","rv-meta");
 add(metadata,make("span","rv-dot",x.lane||"Research"),
  make("span","rv-meta-separator","·"),
  make("span","",conceptual?"Conceptual framework":editorial?"Edited reading":scholarly?isQuestion?"Research topic":"Source-reported result":"Perspective"));
 const status=make("p","rv-status",conceptual?"Proposed educational framework · not an experimental test":editorial?"Research reading":scholarly?"Based on indexed source material":"Commentary and perspectives");
 const title=make("h1","rv-headline",cut(cleanLead(headline,readableSourceTitle(x)),230));
 const intro=scholarly&&d.explain?make("p","rv-deck",d.explain):null;
 add(head,metadata,title,intro,status);
 main.append(back,head,editorialMedia(x,"reading"));
 const layout=make("div","rv-layout"),story=make("div","rv-story"),side=make("aside","rv-sidebar");
 const body=make("section","rv-content");
 const art=conceptArtwork(x);
 const autoGraphic=Boolean(art&&art.className&&art.className.includes("automatic-evidence"));
 const lead=make("div","rv-section-head");
 add(lead,make("span","rv-section-overline","01 / UNDER THE HOOD"),
  make("h2","rv-section-title",conceptual?"What the paper proposes":scholarly?"What the evidence actually says":"The argument in context"));
 body.append(lead);
 if(editorial&&hasFinding&&!autoGraphic){
  const claim=make("div","rv-claim");
  add(claim,make("span","rv-mini-label","REPORTED FINDING"),
     make("p","",d.finding));
  body.append(claim);
 }else if(!scholarly){
  const deep=d.longform||{},hasDepth=Boolean(deep.reasoning||deep.examples||deep.tension||deep.implications);
  const reading=make("div","rv-longform");
  function lens(label,value){
   if(!value)return;
   const part=make("section","rv-longform-part");
   add(part,make("h3","",label),make("p","",value));
   reading.append(part);
  }
  // Publisher metadata alone cannot justify invented counterarguments or a
  // faux methods section. Only display fields supported by source analysis.
  lens(deep.source_depth==="publisher_synopsis"?"From the publisher’s description":"The central argument",deep.thesis||r.overview);
  lens("How the argument develops",deep.reasoning);
  lens("Concrete examples and distinctions",deep.examples);
  lens("The central tension",deep.tension);
  lens("What this could mean for attention design",deep.implications);
  lens("A question to investigate",deep.open_question);
  lens("Qualifications and unresolved issues",deep.qualification);
  if(deep.basis)reading.append(make("p","rv-longform-basis","Reading basis: "+deep.basis));
  body.append(reading);
 }else if(conceptual){
  const framework=x.framework_notes||{};
  const claim=make("div","rv-claim");
  add(claim,make("span","rv-mini-label","PROPOSED MODEL, NOT A TESTED EFFECT"),
    make("p","",d.idea||framework.idea||"A theoretical proposal for staging AI use in learning."));
  body.append(claim);
  const phases=framework.stages||[];
  if(phases.length){
   const stages=make("div","rv-longform");
   for(const phase of phases){
    const cutAt=phase.indexOf(":");
    const section=make("section","rv-longform-part");
    add(section,make("h3","",cutAt>0?phase.slice(0,cutAt):"Stage"),
      make("p","",cutAt>0?phase.slice(cutAt+1).trim():phase));
    stages.append(section);
   }
   body.append(stages);
  }
 }else if(!hasFinding){
  const claim=make("div","rv-source-gap");
  add(claim,make("span","rv-mini-label","EVIDENCE NOT YET ESTABLISHED"),
    make("p","","A substantive result has not been identified in the accessible material. This is a research topic, not a verified finding."));
  body.append(claim);
 }
 if(art){
  const visuals=make("div","rv-artwork");
  visuals.append(art);
  body.append(visuals);
 }
 const context=make("div","rv-context-grid");
 const method=make("section","rv-context");
 add(method,make("h3","",conceptual?"How the framework was developed":"How it was studied"),
   make("p","",scholarly?d.approach||"Method details are not clear enough in the indexed material.":d.approach||"This is a commentary or editorial account, not a controlled study."));
 const caveat=make("section","rv-context");
 add(caveat,make("h3","",conceptual?"What has not been established":"What remains uncertain"),
   make("p","",d.limitation||"A source-specific limitation could not be verified from the available excerpt."));
 add(context,method,caveat);
 if(scholarly&&!autoGraphic)body.append(context);
 if(scholarly&&editorial&&d.interpretation){
  const relevance=make("section","rv-take");
  add(relevance,make("span","rv-section-overline","02 / INTERPRETATION"),
    make("h2","rv-section-title","Why this matters"),
    make("p","",d.interpretation));
  body.append(relevance);
 }
 if(scholarly&&d.longform){
  const deep=d.longform;
  const extended=make("section","rv-research-longform");
  add(extended,make("span","rv-section-overline","02 / CLOSER READING"),
     make("h2","rv-section-title","A deeper look at the study"));
  const items=[
    ["The research question",deep.research_question],
    ["Design and evidence",deep.study_design],
    ["What was actually reported",deep.reported_results],
    ["How the authors interpret it",deep.authors_interpretation],
    ["How to read this critically",deep.critical_context],
    ["Limitations",deep.limitations],
    ["A question worth pursuing",deep.open_question]
  ];
  const parts=make("div","rv-longform");
  for(const [label,value] of items){
   if(!value)continue;
   const part=make("section","rv-longform-part");
   add(part,make("h3","",label),make("p","",value));
   parts.append(part);
  }
  if(deep.basis)parts.append(make("p","rv-longform-basis",
   "Reading basis: "+deep.basis+" · Machine-generated, not independently reviewed"));
  extended.append(parts);
  body.append(extended);
 }
 // Keep the extracted text and metadata in one clearly optional evidence drawer.
 const drawer=make("details","rv-drawer"),summary=make("summary","","Inspect source text and abstract");
 const drawerBody=make("div","rv-drawer-body");
 let notes=0;
 const fields=scholarly?[
  ["Methods as indexed",r.methods],["Extracted Results (may include measurement diagnostics)",r.findings],
  ["Discussion as indexed",r.interpretation],["Reported limitations",r.limitations],
  ["Abstract",x.abstract_text]
 ]:[
  ["Publisher or editorial synopsis",r.overview],["Original editorial notes",(x.editorial_notes||{}).argument]
 ];
 for(const [label,content] of fields){
  if(!content)continue;
  const sectionEl=make("section","rv-excerpt");
  add(sectionEl,make("h3","",label),make("p","",content));
  drawerBody.append(sectionEl);notes++;
 }
 if(notes){drawer.append(summary,drawerBody);body.append(drawer);}
 story.append(body);
 const cite=make("section","rv-source");
 add(cite,make("span","rv-section-overline","SOURCE"),
  make("h2","","Behind this reading"),
  make("h3","rv-source-title",readableSourceTitle(x)),
  make("p","rv-source-meta",[x.venue,date(x.published)].filter(Boolean).join(" · ")));
 const pills=make("div","rv-source-pills");
 add(pills,make("span","",depthName(x)),
    make("span","",x.relation||"Unclassified"));
 cite.append(pills);
 if(x.url&&/^https:\/\//.test(x.url))cite.append(link("Open publication ↗",x.url,"rv-primary-link"));
 if(x.analysis?.fulltext_url&&/^https:\/\//.test(x.analysis.fulltext_url))
  cite.append(link("Read accessible full text ↗",x.analysis.fulltext_url,"rv-secondary-link"));
 const provenance=make("details","rv-provenance");
 add(provenance,make("summary","","Source details"),
    add(make("div","rv-provenance-body"),
      make("p","",r.provenance||"Publisher/source index"),
      make("p","",x.doi?"DOI: "+x.doi:"No DOI recorded")));
 cite.append(provenance);side.append(cite);
 if(x.analysis?.figures?.length){
  const figureSection=make("details","rv-figures");
  figureSection.append(make("summary","","Original paper figures ("+x.analysis.figures.length+")"));
  const figureBody=make("div","rv-figures-content");
  for(const fig of x.analysis.figures.slice(0,3)){
   const caption=make("div","rv-source-figure");
   const safe=typeof fig.image_url==="string"&&
     /^https:\/\/pmc-oa-opendata\.s3\.amazonaws\.com\/PMC\d+\.[123]\/[^?#]+\.(?:png|jpg|jpeg|webp|gif)$/.test(fig.image_url)&&fig.attribution;
   if(safe){
    const img=make("img","rv-original-figure");
    img.src=fig.image_url;img.loading="lazy";
    img.alt=(fig.label||"Figure")+": "+(fig.caption||"");
    img.addEventListener("error",()=>{img.hidden=true;});
    caption.append(img);
   }
   add(caption,make("strong","",fig.label||"Figure"),make("p","",cut(fig.caption||"See source caption",170)));
   if(safe)caption.append(make("p","rv-license",fig.attribution+" · check third-party figure rights in source"));
   figureBody.append(caption);
  }
  figureSection.append(figureBody);side.append(figureSection);
 }
 const companions=S.companions.filter(y=>y.companion_to===x.doi);
 if(companions.length){
  const origin=make("section","rv-related");
  add(origin,make("span","rv-section-overline","FROM THE ORIGINAL AUTHOR"),
    make("h2","","Related explanation and commentary"),
    make("p","","The author discusses implications of this publication in a public-facing piece. This is not an independent study."));
  for(const companion of companions){
   const article=make("div","rv-excerpt");
   add(article,make("h3","",readableSourceTitle(companion)),
     make("p","",companion.companion_relation||"Author commentary"));
   if(/^https:\/\//.test(companion.url||""))article.append(link("Read the commentary ↗",companion.url,"rv-secondary-link"));
   origin.append(article);
  }
  side.append(origin);
 }
 const related=S.records.filter(y=>y!==x&&y.lane===x.lane&&y.kind===x.kind&&depth(y)!=="citation_only")
                       .sort((a,b)=>rank(b)-rank(a)).slice(0,3);
 if(related.length){
  const next=make("section","rv-related");
  add(next,make("span","rv-section-overline","CONTINUE EXPLORING"),make("h2","","Related readings"));
  for(const y of related)next.append(btn(shortIdea(y,90),()=>goto("paper",id(y)),"rv-related-item"));
  side.append(next);
 }
 add(layout,story,side);
 main.append(layout);
 root.append(main);
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
  const rs=await Promise.all(["data/public-library.json","data/public-weekly.json","data/runs.json","data/fulltext-backfill-state.json","data/public-featured-issue.json"].map(p=>fetch(p+"?v="+Date.now(),{cache:"no-store"})));
  if(!rs[0].ok)throw new Error("Library download failed (HTTP "+rs[0].status+")");
  S.records=await rs[0].json();if(!Array.isArray(S.records))throw new Error("Unexpected library format");S.records=S.records.filter(x=>x.reading?.level&&x.reading.level!=="citation_only");S.companions=S.records.filter(x=>Boolean(x.companion_to));S.records=S.records.filter(x=>!x.companion_to);
  S.week=rs[1].ok?await rs[1].json():{run:{mode:"unavailable"},items:[]};
  S.runs=rs[2].ok?await rs[2].json():[];
  S.backlog=rs[3].ok?await rs[3].json():{};
  S.issue=rs[4].ok?await rs[4].json():{};
  home();renderIssue();renderBacklog();showLibrary();showProductExamples();renderPerspectives();route();
 }catch(e){$("#issue-label").textContent="INDEX OFFLINE";$("#issue-meta").textContent="Research data could not load";$("#feature-grid").replaceChildren(make("div","empty-state","Could not load the research archive: "+e.message));route()}
}
$$("[data-route]").forEach(a=>a.onclick=e=>{e.preventDefault();goto(a.dataset.route)});
["search","scope-filter","topic-filter","depth-filter","type-filter"].forEach(s=>$("#"+s).addEventListener(s==="search"?"input":"change",showLibrary));
$("#browse-editorial").addEventListener("click",e=>{e.preventDefault();goto("perspectives")});
$("#perspectives-library-link").addEventListener("click",e=>{e.preventDefault();$("#type-filter").value="nonacademic";$("#depth-filter").value="readable";goto("library")});
$("#perspectives-essays-link").addEventListener("click",e=>{e.preventDefault();$("#perspectives-essays").scrollIntoView({behavior:"smooth",block:"start"})});
window.addEventListener("hashchange",route);
init();
