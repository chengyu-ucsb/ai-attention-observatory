"use strict";
const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
const S={records:[],companions:[],pending:[],week:{},issue:{},runs:[],backlog:{},duration:10,left:600,timer:null,running:false,checkpoint:null};
const themes=[["AI & cognition","When thinking is delegated","Offloading, metacognition and reasoning","◎","#E00122"],["Fragmentation","The cost of switching","Distraction, interruptions and re-entry","direction-mark","#A8001A"],["Interventions","Designing for focus","Focus tools and digital well-being","✳","#646464"],["Technology & society","Who shapes attention?","Platform incentives and human agency","◇","#9A9193"]];
const depths=[["full_text","Full-text material","#E00122"],["abstract","Abstract-based","#666666"],["curated","Curated synopsis","#C6C0C1"]];
function uiIcon(name,cls=""){
 const wrap=document.createElement("span");wrap.className="ui-icon"+(cls?" "+cls:"");wrap.setAttribute("aria-hidden","true");
 const svg=document.createElementNS("http://www.w3.org/2000/svg","svg"),use=document.createElementNS("http://www.w3.org/2000/svg","use");
 svg.setAttribute("viewBox","0 0 24 24");svg.setAttribute("focusable","false");use.setAttribute("href","#icon-"+name);svg.append(use);wrap.append(svg);return wrap;
}
function make(t,c,s){if(s==="direction-mark")return uiIcon("external",c);const e=document.createElement(t);if(c)e.className=c;if(s!==undefined){if(s!==null&&typeof s==="object")throw new TypeError("make() accepts text only; use add() to append elements");e.textContent=String(s)}return e}
function add(p,...els){for(const e of els)if(e)p.append(e);return p}
function btn(s,fn,c){const e=make("button",c,s);e.type="button";e.onclick=fn;return e}
function link(s,u,c){const e=make("a",c,s);e.href=u;if(u.startsWith("https://")){e.target="_blank";e.rel="noopener noreferrer"}return e}
function date(s){if(!s||!/^20\d\d/.test(s))return "Undated";let d=new Date(s.slice(0,10)+"T12:00:00Z");return isNaN(d.getTime())?"Undated":d.toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"})}
function id(x){return String(x.doi||x.url||x.title)}
function record(k){const found=S.records.find(x=>id(x)===k||(x.legacy_urls||[]).includes(k))||S.companions.find(x=>id(x)===k||(x.legacy_urls||[]).includes(k))||S.pending.find(x=>id(x)===k);return found?.companion_to?S.records.find(x=>id(x)===found.companion_to)||found:found}
function depth(x){return x.reading?.level||"citation_only"}
function originalSummary(x){return x.reading?.original_summary===true}
function originalCommentary(reading){return reading?.original_summary===true&&reading.research_type==="attributed_commentary"}
function checkedReadingContext(reading,cls="source-meta"){
 const box=make("div",cls),deep=reading.digest?.longform||{};
 if(originalCommentary(reading))box.append(make("p","","Attributed commentary · "+(reading.genre||deep.genre||"commentary").replace(/_/g," ")+((reading.attributed_to||deep.attributed_to)?" · "+(reading.attributed_to||deep.attributed_to):"")));
 box.append(make("p","",reading.notice||reading.review_label||"AI source-check · not human review or independent replication"));
 if(reading.review_scope)box.append(make("p","","AI source-check scope: "+reading.review_scope));
 if(reading.quality_note)box.append(make("p","","Article quality screening: "+reading.quality_note));
 if(reading.temporal_notice&&!String(reading.notice||"").includes(reading.temporal_notice))box.append(make("p","",reading.temporal_notice));
 return box;
}
function readingDetails(reading){
 const details=make("details","card-reading-details");
 add(details,make("summary","","Reading details"),checkedReadingContext(reading));
 if(reading.source_version)details.append(make("p","source-meta","Source version identifier: "+reading.source_version));
 const basis=reading.digest?.basis;
 if(basis&&!String(reading.notice||"").includes(basis))details.append(make("p","source-meta",basis));
 if(!/not human review|not independently reviewed/i.test(String(reading.notice||"")+String(basis||"")))details.append(make("p","source-meta","AI source-check; not human review or independent replication."));
 return details;
}
function depthName(x){if(originalSummary(x))return "Original summary";if(x.kind==="nonacademic"&&depth(x)!=="citation_only"){const src=x.reading?.digest?.longform?.source_depth;return src==="read_article"?"Reviewed essay":src==="machine_read_full_article"?"Article-based synthesis":src==="product_documentation"?"Product documentation":src==="editorial_synopsis"?"Editorial synopsis":"Publisher synopsis";}return ({"full_text":x.analysis?.original_paraphrases_only?"Reviewed full article":"Full-text sections","abstract":"Abstract-based","curated":"Curated overview","citation_only":"Citation only"})[depth(x)]}
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
function editorialArt(x){
 const art=x?.editorial_art,valid=src=>typeof src==="string"&&/^assets\/(?:article-art|editorial-covers)\/[a-z0-9-]+\.(?:svg|webp|png|jpg)$/.test(src);
 if(!art||art.status==="needs_review"||art.kind!=="editorial_illustration"||!valid(art.src)||typeof art.alt!=="string"||!art.alt.trim())return null;
 return {...art,thumbnail_src:valid(art.thumbnail_src)?art.thumbnail_src:null};
}
function editorialImage(x,context="reading"){
 const art=editorialArt(x),reading=context==="reading";
 if(!art)return null;
 const img=make("img","story-image");
 img.src=reading?art.src:art.thumbnail_src||art.src;
 // Repeated card covers are decorative; the visible headline names the link.
 img.alt=reading&&art?art.alt:"";
 img.loading=reading?"eager":"lazy";img.decoding="async";
 img.width=art?.width||1200;img.height=art?.height||760;
 return img;
}
function editorialMedia(x,context="reading"){
 const img=editorialImage(x,context);if(!img)return null;
 const fig=make("figure","story-visual story-visual-"+context);fig.append(img);
 if(context==="reading")fig.append(make("figcaption","story-visual-caption","Editorial illustration"));
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
const readingTitles={
 "10.48550/arxiv.2610.38910":"How students describe critical engagement with AI",
 "10.48550/arxiv.2610.38950":"Changing how students ask AI for help",
 "10.48550/arxiv.2610.38990":"What makes an AI feel like a peer?",
 "https://www.eff.org/deeplinks/2026/10/victory-you-can-now-exclude-apps-siri-ai":"Choosing what an AI assistant can access",
 "https://www.eff.org/deeplinks/2026/10/social-media-when-elections-are-close-doing-impossible-better":"Challenging an automated moderation decision",
 "https://www.eff.org/deeplinks/2026/10/tech-tips-parents-digital-parenting-week":"Building a family safety plan together"
};
function shortIdea(x,limit=105){
 if(readingTitles[id(x)])return readingTitles[id(x)];
 const d=x.reading?.digest||{};
 // Source findings and edited ideas take priority. The common fallback is a
 // visibly topic-framed question, never an all-caps bibliographic title.
 const value=originalSummary(x)||d.status==="editorially_written_from_indexed_sections"?
    d.idea||d.finding:d.finding||d.idea||readableSourceTitle(x);
 return originalSummary(x)?value:cleanLead(value,readableSourceTitle(x));
}
function ideaInfo(x){
 const r=x.reading||{},d=r.digest||{},notes=x.editorial_notes||{};
 let value="",label="";
 if(originalSummary(x))return {text:d.idea||d.finding||"",label:originalCommentary(r)?"ATTRIBUTED COMMENTARY":x.research_type==="conceptual_framework"?"CONCEPTUAL PROPOSAL":"RESEARCH READING"};
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
function libraryHash(theme){return "#library?theme="+encodeURIComponent(theme)+"&scope=all"}
function goto(page,k){
 const value=page==="paper"?"#paper/"+encodeURIComponent(k):page==="library"&&k?libraryHash(k):"#"+page;
 if(location.hash===value)route({type:"hashchange"});else location.hash=value;
}
function route(event){
 const raw=location.hash.slice(1)||"home";
 let page=raw.startsWith("paper/")?"paper":raw.split("?")[0];
 if(!["home","library","atlas","lab","paper","about","perspectives","issue"].includes(page))page="home";
 if(page==="library"&&raw.includes("?")){
  const params=new URLSearchParams(raw.slice(raw.indexOf("?")+1)),theme=params.get("theme"),scope=params.get("scope");
  $("#topic-filter").value=themes.some(t=>t[0]===theme)?theme:"";
  $("#scope-filter").value=["core","adjacent","historical","all"].includes(scope)?scope:"all";
  $("#search").value="";$("#type-filter").value="";$("#depth-filter").value="readable";
 }
 $$(".view").forEach(v=>v.hidden=v.id!==page);
 $$("[data-route]").forEach(v=>{v.classList.toggle("active",v.dataset.route===page);if(v.dataset.route===page)v.setAttribute("aria-current","page");else v.removeAttribute("aria-current")});
 if(page==="paper"){let key;try{key=decodeURIComponent(raw.slice(6))}catch{key=""}showPaper(record(key))}
 if(page==="library")showLibrary();if(page==="atlas")showAtlas();
 window.scrollTo({top:0,behavior:"instant"});
 if(event?.type==="hashchange"){
  closeNavigation();
  const heading=$("#"+page+" h1");if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true})}
 }
}
function counts(){const result={};for(const d of depths)result[d[0]]=S.records.filter(x=>depth(x)===d[0]).length;return result}
function topicBars(selector){const root=$(selector);root.replaceChildren();const max=Math.max(1,...themes.map(t=>S.records.filter(x=>x.lane===t[0]).length));for(const t of themes){const n=S.records.filter(x=>x.lane===t[0]).length,p=btn("",()=>goto("library",t[0]),"topic-bar-line"),track=make("span","bar-track"),fill=make("span","bar-fill");fill.style.width=n/max*100+"%";fill.style.background=t[4];add(track,fill);add(p,make("span","bar-label",t[0]),track,make("span","bar-value",n));root.append(p)}}
function donut(){const cc=counts(),total=Math.max(1,S.records.length),legend=$("#depth-legend");$("#record-count").textContent=S.records.length;legend.replaceChildren();let at=0,parts=[];for(const d of depths){let pct=cc[d[0]]/total*100;parts.push(d[2]+" "+at.toFixed(2)+"% "+(at+pct).toFixed(2)+"%");at+=pct;const r=make("div","legend-item"),sw=make("span","legend-swatch"),copy=make("div");sw.style.background=d[2];add(copy,make("div","legend-title",d[1]+" · "+cc[d[0]]),make("span","legend-caption",Math.round(pct)+"% of records"));add(r,sw,copy);legend.append(r)}$("#evidence-donut").style.background="conic-gradient("+parts.join(",")+")"}
function featureCoverage(x){
 const area=make("div","feature-evidence"),row=make("div","feature-evidence-row");
 const tiers=["Citation","Abstract",originalSummary(x)?"Checked source text":"Full text"],active=depth(x)==="full_text"?3:depth(x)==="abstract"?2:1;
 const track=make("div","feature-evidence-track");
 for(let i=0;i<3;i++){const mark=make("span","feature-evidence-mark"+(i<active?" covered":""));mark.title=tiers[i];track.append(mark)}
 add(row,make("span","", "AVAILABLE MATERIAL"),make("span","",depthName(x)));
 add(area,row,track);
 if(originalSummary(x))add(area,make("p","source-meta","Checked source: "+checkedSourceLabel(x.reading)),readingDetails(x.reading));
 return area;
}

function issueRefs(ids,target){
 const list=(S.issue.sources||[]),container=target||make("div","issue-references");
 for(const key of ids||[]){
   const src=list.find(x=>x.id===key);
   if(!src)continue;
   const resolved=record(key),matches=resolved&&depth(resolved)!=="citation_only"?resolved:null;
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
function textSentences(value){
 const text=String(value||"").replace(/\s+/g," ").trim();
 if(!text)return [];
 return typeof Intl!=="undefined"&&Intl.Segmenter?Array.from(new Intl.Segmenter("en",{granularity:"sentence"}).segment(text),x=>x.segment).reduce((parts,segment)=>{if(parts.length&&!/\s$/.test(parts[parts.length-1])&&!/^\s/.test(segment))parts[parts.length-1]+=segment;else parts.push(segment);return parts;},[]).map(segment=>segment.trim()):text.split(/(?<=[.!?])\s+(?=[A-Z“])/);
}
function compactReading(value,label="Read the full context"){
 const parts=textSentences(value),box=make("div","compact-reading");
 if(parts.length<3||String(value).length<380)return readingProse(value);
 box.append(make("p","compact-lead",parts[0]));
 const more=make("details","reading-expansion");
 add(more,make("summary","",label),readingProse(parts.slice(1).join(" ")));
 box.append(more);return box;
}
function evidenceTags(sources){
 const wrap=make("div","evidence-tags"),labels=new Set();
 for(const source of sources){
  const version=String(source.source_version||source.venue||"").toLowerCase();
  labels.add(/arxiv|preprint|working.paper/.test(version)?"Preprint · review unverified":source.kind==="nonacademic"||source.research_type==="attributed_commentary"?"Commentary":source.reading_level==="abstract"?"Abstract-based":"Research");
 }
 for(const label of labels)wrap.append(make("span","",label));
 return wrap;
}
function renderIssue(){
 const issue=S.issue||{},published=issue.status==="published";
 const edition=issue.edition_date||S.week.run?.date||"";
 const sourceCount=Number(issue.source_count)||0;
 renderIssueLandscape(issue);
 $("#weekly-kicker").textContent=published?"THE WEEKLY BRIEF / ISSUE "+String(issue.number).padStart(2,"0"):"THE ATTENTION BRIEF";
 $("#weekly-title").textContent=published?issue.headline:"Good questions about AI and attention.";
 $("#weekly-deck").textContent=published?issue.deck:"Browse research and ideas about thinking, distraction, and how we work with AI.";
 $("#weekly-scope").textContent=published?"An issue of The Attention Brief · "+date(edition):"Browse the research library for the latest findings.";
 $("#issue-edition").textContent=published?"THE ATTENTION BRIEF / ISSUE "+issue.number+" / "+date(edition):"THE ATTENTION BRIEF";
 $("#issue-headline").textContent=published?issue.headline:"Ideas for thinking clearly.";
 $("#issue-deck").textContent=published?issue.deck:"Explore research, commentary, and experiments about AI and attention.";
 $("#issue-letter-text").replaceChildren(readingProse(published?issue.letter:"Start with a question, follow the evidence, and explore the research library."));
 const strips=$("#weekly-signal-strip"),main=$("#issue-signals");strips.replaceChildren();main.replaceChildren();
 const signs=published?issue.signals||[]:[];
 signs.forEach((sig,i)=>{
   const tile=make("a","weekly-signal");tile.href="#issue";tile.setAttribute("aria-label","Read signal "+(i+1)+": "+sig.short);
   const mark=uiIcon(["focus","switch","network"][i%3],"weekly-signal-symbol");
   add(tile,mark,make("span","weekly-signal-no",String(i+1).padStart(2,"0")+" / IN THIS ISSUE"),make("h4","",sig.short),make("span","weekly-signal-arrow","Read the connection"));strips.append(tile);
   const panel=make("article","issue-signal"),header=make("div","issue-signal-header");
   add(header,uiIcon(["focus","switch","network"][i%3],"issue-signal-icon"),make("span","issue-signal-no","THREAD "+String(i+1).padStart(2,"0")));
   add(panel,header,make("h3","",sig.title),evidenceTags((issue.sources||[]).filter(source=>(sig.source_ids||[]).includes(source.id))),compactReading(sig.text,"Evidence, differences & limits"),
       make("span","issue-cited-label","READINGS BEHIND THIS SIGNAL"),
       issueRefs(sig.source_ids));
   main.append(panel);
 });
 $("#issue-extras").hidden=!published;
 $(".issue-closing").hidden=!published;
 $("#issue-tension-title").textContent=published?issue.tension.title:"";
 $("#issue-tension-text").replaceChildren(compactReading(published?issue.tension.text:"","Explore the question"));
 const ref=$("#issue-tension-refs");ref.replaceChildren();if(published)issueRefs(issue.tension.source_ids,ref);
 $("#issue-experiment-title").textContent=published?issue.experiment.title:"";
 $("#issue-experiment-text").textContent=published?issue.experiment.text:"";
 $("#issue-experiment-caution").textContent=published?issue.experiment.caution:"";
 $("#issue-closer").textContent=published?issue.closer:"";
 $("#issue-qualification").textContent=published?issue.editorial_note||"":"";
 $("#issue-qualification").hidden=!published||!issue.editorial_note;
 const sourceList=issue.sources||[],earlier=sourceList.filter(source=>source.editorial_role==="previously_indexed_context").length,collection=sourceList.filter(source=>source.editorial_role==="collection_week").length;
 $("#issue-coverage").textContent=issue.publication_window?sourceList.length+" sources originally published "+date(issue.publication_window.from)+"–"+date(issue.publication_window.to)+" (UTC). No older context sources are included.":sourceList.length+" sources in this edition. "+(collection||earlier?collection+" collection-week reading"+(collection===1?"":"s")+" and "+earlier+" earlier context reading"+(earlier===1?"":"s")+". Collection-week does not mean newly published or first indexed this week.":"Explore the original research and reporting behind these ideas.");
 const shelf=$("#issue-sources");shelf.replaceChildren();
 for(const [i,src] of (issue.sources||[]).entries())shelf.append(issueSourceShelfItem(src,i));
}
function issueSourceShelfItem(src,index){
 const item=make("div","issue-shelf-item"),resolved=record(src.id),candidate=resolved&&depth(resolved)!=="citation_only"?resolved:null;
 const original=src.original_summary===true;
 const title=candidate?btn(readableSourceTitle(src),()=>goto("paper",id(candidate))):link(readableSourceTitle(src),src.url||"#library");
 const role=src.editorial_role==="previously_indexed_context"?"Earlier context":src.editorial_role==="collection_week"?"Collection-week reading":src.editorial_role==="publication_week"?"Published in previous week":"";
 const metadata=[src.venue,original?"Original summary":candidate?depthName(candidate):"Not in current reading library · Original source",candidate?.first_seen?"First indexed "+date(candidate.first_seen):"",role].filter(Boolean).join(" · ");
 const content=add(make("div","issue-shelf-content"),title,make("p","",metadata));
 if(original){
  // Use the edition's source snapshot, not the current library reading: a
  // later accepted version must not relabel an earlier working-paper source.
  content.append(make("p","issue-source-version","Checked source: "+checkedSourceLabel(src)));
  const sourceUrl=httpsSourceUrl(src.source_url),links=make("div","issue-source-links");
  if(sourceUrl)links.append(add(make("p"),link("Read checked source: "+checkedSourceLabel(src)+"",sourceUrl,"issue-source-checked-link")));
  const related=src.related_journal_doi&&src.related_journal_doi!==src.source_doi;
  const publicationUrl=related?doiUrl(src.related_journal_doi):httpsSourceUrl(src.url);
  if(publicationUrl&&publicationUrl!==sourceUrl)
   links.append(add(make("p"),link(related?"Related journal publication (not the checked source)":"Publication record",publicationUrl,"issue-source-publication-link")));
  if(links.children.length)content.append(links);
  const review=make("details","issue-source-review"),scope=make("div","issue-source-review-body");
  scope.append(checkedReadingContext(src,"issue-source-review-label"));
  if(src.source_version)scope.append(make("p","","Source version identifier: "+src.source_version));
  if(src.source_doi)scope.append(make("p","","Checked source DOI: "+src.source_doi));
  if(related)scope.append(make("p","","Related journal DOI (not checked here): "+src.related_journal_doi));
  if(scope.children.length)content.append(add(review,make("summary","","Source details & reading basis"),scope));
  const evidence=originalEvidence(src);if(evidence)content.append(evidence);
 }
 return add(item,make("span","issue-shelf-number",String(index+1).padStart(2,"0")),content);
}

function home(){
 const run=S.week.run||{},all=(S.week.items||[]).map(x=>record(id(x))||S.records.find(r=>r.title===x.title)||x);
 const top=all.filter(x=>x.kind==="scholarly"&&depth(x)!=="citation_only"&&x.reading?.digest?.finding).sort((a,b)=>rank(b)-rank(a)).filter(x=>x.relation!=="Adjacent digital-attention evidence"||!all.some(y=>y.relation!=="Adjacent digital-attention evidence"&&y.reading?.digest?.finding)).slice(0,3);
 const start=run.mode==="curated-starter";$("#issue-label").textContent=start?"STARTER COLLECTION / LIVE UPDATE PENDING":"LATEST INDEX / "+date(run.date);$("#issue-meta").textContent=(run.last_seven_days??all.length)+" in latest collection · "+S.records.length+" in library"+(run.publication_window?" · Published "+date(run.publication_window.from)+"–"+date(run.publication_window.to)+" UTC":"");
 const root=$("#feature-grid");root.replaceChildren();
 if(!top.length)root.append(make("div","empty-state","The latest index contains no source-rich highlights yet. Browse the research library."));
 top.forEach((x,i)=>{const c=make("article","feature-card"+(i===0?" primary":"")),head=make("div","feature-top"),foot=make("div","feature-foot");
 add(head,make("span","feature-number",String(i+1).padStart(2,"0")),uiIcon(["focus","switch","design"][i%3],"feature-icon"));
 add(foot,make("span","source-pill",depthName(x)),btn("Read the evidence",()=>goto("paper",id(x)),"feature-go"));
 add(c,head,editorialMedia(x,"feature"),make("p","feature-idea-label",ideaInfo(x).label),make("h3","feature-idea",shortIdea(x,96)),originalSummary(x)?make("p","source-meta",cut(x.reading.digest?.explain,220)):null,make("p","feature-source-title",readableSourceTitle(x)),make("p","source-meta",(x.venue||"")+" · "+date(x.published)),featureCoverage(x),foot);root.append(c)});
 // Provider diagnostics belong in repository workflow logs, never in public content.
 renderEditorial();
 topicBars("#topic-bars");donut();
 const grid=$("#lens-grid");if(grid){grid.replaceChildren();themes.forEach((t,i)=>{const a=link("",libraryHash(t[0]),"lens");a.setAttribute("aria-label","Explore "+t[0]);a.setAttribute("data-theme",String(i));add(a,make("span","lens-mark",t[3]),make("h3","",t[1]),make("p","",t[2]),make("span","",S.records.filter(x=>x.lane===t[0]).length+" records →"));grid.append(a)});}
 const arr=$("#arrivals-body");arr.replaceChildren();
 const sorted=S.records.filter(x=>depth(x)!=="citation_only").slice().sort((a,b)=>(b.first_seen||"").localeCompare(a.first_seen||"")||(b.published||"").localeCompare(a.published||"")).slice(0,7);
 for(const x of sorted){let tr=make("tr"),name=make("td"),go=make("td","align-right");name.append(btn(shortIdea(x,94),()=>goto("paper",id(x))));name.append(make("span","arrival-source-title",readableSourceTitle(x)));go.append(btn("Read",()=>goto("paper",id(x))));add(tr,make("td","mono-date",date(x.first_seen)),name,make("td","",x.lane||"Research"),make("td","coverage-tag",depthName(x)),go);arr.append(tr)}
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
  add(foot,make("span","",x.venue||"Original source"),btn("Explore",()=>goto("paper",id(x)),"editorial-cta"));
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
    const icon=uiIcon(x.source==="Official product documentation"?"book":x.format==="Policy analysis"?"shield":"external","perspective-glyph");
    const label=make("div","perspective-type",x.format||"Reporting & analysis");
    const title=make("h3");title.append(btn(shortIdea(x,105),()=>goto("paper",id(x))));
    const summary=make("p","perspective-source-title",readableSourceTitle(x));
    const bottom=make("div","perspective-bottom");
    add(bottom,make("span","",x.venue||"Original source"),btn("Read source notes",()=>goto("paper",id(x)),"editorial-cta"));
    add(item,editorialMedia(x,"perspective"),icon,label,title,summary,bottom);container.append(item);
  }
 }
}
function renderBacklog(){
 const b=S.backlog||{},root=$("#backlog-coverage");
 root.replaceChildren();
 const scholarly=Number(b.total_scholarly)||S.records.filter(r=>r.kind==="scholarly").length;
 const done=Number.isFinite(b.full_text_extracted)?b.full_text_extracted:S.records.filter(r=>r.kind==="scholarly"&&r.analysis?.fulltext_url&&!r.analysis.original_paraphrases_only).length;
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
 const q=$("#search").value.trim().toLowerCase(),t=$("#topic-filter").value,d=$("#depth-filter").value,k=$("#type-filter").value,scope=$("#scope-filter").value,order=$("#library-sort")?.value||"added";
 const xs=S.records.filter(x=>(!q||[x.title,x.venue,x.abstract_text,x.preview,x.reading?.findings,x.reading?.methods,...Object.values(x.reading?.digest||{}).filter(v=>typeof v==="string"),(x.authors||[]).join(" ")].join(" ").toLowerCase().includes(q))&&(!t||x.lane===t)&&(!k||x.kind===k)&&(
   scope==="all"||(scope==="core"&&x.source_group==="AI-specific")||
   (scope==="adjacent"&&x.source_group==="Adjacent digital-attention evidence")||
   (scope==="historical"&&/^(Earlier|Historical)/.test(x.source_group||""))
  )&&(d!=="full_text"||depth(x)==="full_text")).sort((a,b)=>{const field=order==="published"?"published":"first_seen";return (b[field]||"").localeCompare(a[field]||"")||(b.published||"").localeCompare(a.published||"")||rank(b)-rank(a)});
 $("#library-count").textContent=xs.length+" matching sources · "+S.records.length+" in the complete archive";
 const context=$("#library-context");
 if(context){
  const scopeNames={core:"AI-specific research",adjacent:"Adjacent digital-attention research",historical:"Earlier foundations",all:"All sources"};
  context.textContent=[scopeNames[scope]||"All sources",t,d==="full_text"?"Full-text material":"",k==="scholarly"?"Academic research":k==="nonacademic"?"Commentary & technology":""].filter(Boolean).join(" · ");
  $$("[data-library-theme]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.libraryTheme===t)));
 }

 const box=$("#library-results");box.replaceChildren();
 if(!xs.length){box.append(make("div","empty-state","No source-backed items match those filters. Try a broader search."));return}
 for(const x of xs){
  const c=make("article","library-card library-story"),body=make("div","library-story-body"),h=make("h3"),foot=make("div","card-foot");
  const image=editorialMedia(x,"card");
  if(image){
  image.onclick=()=>goto("paper",id(x));
  image.setAttribute("role","button");
  image.setAttribute("aria-label","Read: "+shortIdea(x,115));
  image.tabIndex=0;
  image.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();goto("paper",id(x));}});
  }else c.className+=" library-story-no-art";
  h.append(btn(shortIdea(x,115),()=>goto("paper",id(x))));
  add(foot,make("span","card-source-meta",(x.venue||"Original source")+" · Published "+date(x.published)),make("span","card-added",x.first_seen?"Added "+date(x.first_seen):"Added date not recorded"),make("span","card-depth",depthName(x)));
  if(/^(Earlier|Historical)/.test(x.source_group||""))foot.append(make("span","", "Earlier foundation"));
  if(originalSummary(x))add(foot,make("span","card-source-version","Checked source: "+checkedSourceLabel(x.reading)),readingDetails(x.reading));
  add(body,make("span","card-type",ideaInfo(x).label),h,originalSummary(x)?make("p","card-summary",cut(x.reading.digest?.explain,260)):null,make("p","library-citation",readableSourceTitle(x)),foot);
  c.setAttribute("data-theme",String(Math.max(0,themes.findIndex(theme=>theme[0]===x.lane))));
  add(c,image,body);box.append(c);
 }
}
function showAtlas(){
 const cc=counts(),n=S.records.length,stat=$("#atlas-stats");stat.replaceChildren();
 for(const [label,value] of [["Indexed sources",n],["Abstract readings",cc.abstract],["Full-text material",cc.full_text],["Records with findings",S.records.filter(x=>x.reading?.digest?.finding).length]]){let c=make("div","atlas-stat");add(c,make("strong","",value),make("span","",label));stat.append(c)}
 topicBars("#atlas-topic-bars");
 const years={};for(let y=2023;y<=new Date().getFullYear();y++)years[String(y)]=0;
 S.records.forEach(x=>{const y=(x.published||"").slice(0,4);if(x.source_group==="AI-specific"&&Object.prototype.hasOwnProperty.call(years,y))years[y]++});
 const foundation=S.records.filter(x=>/^(Earlier|Historical)/.test(x.source_group||"")).length;
 $("#year-context").textContent="AI-specific records published in 2023–"+new Date().getFullYear()+". "+foundation+" earlier foundation"+(foundation===1?" is":"s are")+" excluded from this chart but remain searchable. These counts describe this collection, not the field’s total publications.";
 const values=Object.entries(years),max=Math.max(1,...values.map(x=>x[1])),chart=$("#year-chart");chart.replaceChildren();
 for(const [y,n] of values){let row=make("div","year-row"),track=make("div","year-track"),bar=make("span","year-bar");bar.style.width=(n?Math.max(2,100*n/max):0)+"%";bar.title=n+" AI-specific records from "+y;track.append(bar);add(row,make("span","year-label",y),track,make("span","year-value",n));chart.append(row)}
 const coverage=$("#atlas-depth");coverage.replaceChildren();for(const d of depths){const n=cc[d[0]],p=n/Math.max(1,S.records.length)*100,c=make("div","coverage-row"),top=make("div","coverage-top"),track=make("div","coverage-track"),fill=make("span","coverage-fill");fill.style.background=d[2];fill.style.width=p+"%";add(top,make("strong","",d[1]),make("span","",n+" · "+Math.round(p)+"%"));track.append(fill);add(c,top,track);coverage.append(c)}
 const table=$("#matrix-table"),thead=make("thead"),r=make("tr");add(r,make("th","","Theme"),...depths.map(d=>make("th","",d[1])));thead.append(r);
 const body=make("tbody");for(const t of themes){const row=make("tr");row.append(make("td","",t[0]));for(const d of depths)row.append(make("td","count-cell",S.records.filter(x=>x.lane===t[0]&&depth(x)===d[0]).length));body.append(row)}table.replaceChildren(thead,body)
}
function section(title,text,origin){const s=make("section","reading-section");add(s,make("p","eyebrow",title),make("h3","",title==="HOW IT WAS STUDIED"?"Method & data":title==="WHAT THE PAPER REPORTS"?"Findings":title==="LIMITATIONS"?"Limitations":title==="AUTHOR INTERPRETATION (DISCUSSION)"?"Authors’ interpretation":"Overview"),make("p","",text));if(origin)s.append(make("div","section-source",origin));return s}
function paperFact(k,v){return add(make("div","paper-fact"),make("span","",k),make("span","",v))}
function processedIdea(x){
 const d=x.reading?.digest;
 if(d){
  const idea=originalSummary(x)||d.status==="editorially_written_from_indexed_sections"?(d.idea||d.finding):d.finding||d.idea||d.interpretation;
  if(idea)return cut(originalSummary(x)?idea:cleanLead(idea,readableSourceTitle(x)),145);
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
    ["direction-mark","Challenge","More positive appraisal was associated with better workplace well-being."],
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
    ["direction-mark","Course learning and AI literacy","Pre/post scores rose in reported measures."],
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
 const blocks=Array.isArray(spec.blocks)?spec.blocks.filter(b=>b&&typeof b.label==="string"&&typeof b.text==="string"&&b.text.length<=600).slice(0,3):[];
 if(!blocks.length)return null;
 const figure=make("figure","article-concept-art article-data-visual automatic-evidence");
 add(figure,make("p","eyebrow",spec.status==="edited"?"RESEARCH SNAPSHOT":"SOURCE-BASED READING"),
    make("h3","figure-insight-title",spec.kind==="evidence_snapshot"?"What the evidence supports":"How this question was studied"));
 const board=make("div","auto-evidence-board");
 blocks.forEach((block,i)=>{
  const item=make("div","auto-evidence-item");
  add(item,make("span","auto-evidence-n",String(i+1).padStart(2,"0")),
    make("strong","auto-evidence-label",block.label),make("p","auto-evidence-text",block.text));
  const source=block.source||(block.label==="Reported finding"?spec.finding_source:spec.basis);
  item.append(make("small","auto-evidence-source",source==="abstract"?"Source: abstract":source==="editorial"?"Source: editorial note":"Source: indexed full-text section"));
  if(block.text.length>240)item.className+=" auto-evidence-wide";
  board.append(item);
 });
 add(figure,board,make("figcaption","concept-note",
   "Source-derived statements, with the material used labelled on each card. Not an effect-size chart, causal model, or reproduction of published figures."));
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
   ["direction-mark","Ownership concern","Dependency was associated with concern over the ownership of one's instructional design work."]
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
function httpsSourceUrl(value){
 if(typeof value!=="string"||!/^https:\/\//.test(value))return "";
 try{const parsed=new URL(value);return parsed.protocol==="https:"&&parsed.hostname&&!parsed.username&&!parsed.password?value:""}catch{return ""}
}
function doiUrl(doi){return "https://doi.org/"+encodeURIComponent(doi).replace(/%2F/gi,"/")}
function checkedSourceLabel(reading){
 const version=reading.source_version||"Source version not recorded";
 const label=version.replace(/^arxiv_preprint_v(\d+)$/,"arXiv preprint v$1 · review unverified").replace(/^publisher_article$/,"Publisher article");
 return label+(reading.source_format?" · "+reading.source_format.toUpperCase():"");
}
function originalEvidence(reading){
 const fields=originalCommentary(reading)?[["thesis","Attributed central argument"],["reasoning","How the argument develops"],
  ["examples","Examples and distinctions"],["tension","The central tension"],["qualification","Qualifications"]]:[["idea","Main idea"],["explain","Explanation"],["approach","Study approach"],
  ["finding","Reported finding"],["interpretation","Interpretation"],["limitation","Limitations"]];
 const details=make("details","rv-drawer rv-evidence"),body=make("div","rv-drawer-body");
 for(const [key,label] of fields){
  const locators=reading.evidence?.[key];
  if(!Array.isArray(locators))continue;
  const list=make("ul","rv-source-locators");
  for(const locator of locators){
   if(!locator||typeof locator.section!=="string"||!locator.section.trim())continue;
   const parts=["Section: "+locator.section];
   if(Number.isInteger(locator.page)&&locator.page>0)parts.push("page "+locator.page);
   if(Number.isInteger(locator.paragraph)&&locator.paragraph>0)parts.push((originalCommentary(reading)&&reading.source_format==="html"?"extracted block ":"paragraph ")+locator.paragraph);
   list.append(make("li","rv-source-locator",parts.join(" · ")));
  }
  if(list.children.length)body.append(add(make("section","rv-excerpt"),make("h3","",label),list));
 }
 if(!body.children.length)return null;
 add(details,make("summary","","Inspect source locators for this summary"),
  make("p","rv-source-version","Locators refer to: "+checkedSourceLabel(reading)),body);
 return details;
}
// Break long readings into comfortable paragraphs without deleting or paraphrasing
// source content. These are presentation breaks, not original PDF paragraph locators.
function readingParagraphs(content){
 const text=String(content||"").replace(/\s+/g," ").trim();
 if(!text)return [];
 const sentences=typeof Intl!=="undefined"&&Intl.Segmenter?
  // Segmenter may split an extracted "...Next" without source whitespace.
  // Keep such fragments together so presentation cannot insert source words.
  Array.from(new Intl.Segmenter("en",{granularity:"sentence"}).segment(text),x=>x.segment)
   .reduce((parts,segment)=>{
    if(parts.length&&!/\s$/.test(parts[parts.length-1])&&!/^\s/.test(segment))parts[parts.length-1]+=segment;
    else parts.push(segment);
    return parts;
   },[]).map(segment=>segment.trim()):
  text.split(/(?<=[.!?])\s+(?=[A-Z“])/);
 const paragraphs=[];let pending="";
 for(const sentence of sentences){
  if(pending&&pending.length+sentence.length>540){paragraphs.push(pending);pending="";}
  // PDF extraction sometimes loses punctuation. Retain every word rather
  // than recreate a table or pretend the fragment is a complete finding.
  if(sentence.length>900){
   if(pending){paragraphs.push(pending);pending="";}
   let line="";
   for(const word of sentence.split(/\s+/)){
    if(line&&line.length+word.length>600){paragraphs.push(line);line="";}
    line+=(line?" ":"")+word;
   }
   pending=line;
  }else pending+=(pending?" ":"")+sentence;
 }
 if(pending)paragraphs.push(pending);
 return paragraphs;
}
function readingBullets(content){
 const list=make("ul","reading-bullets");
 for(const sentence of textSentences(content))list.append(make("li","",sentence));
 return list;
}
function readingQualifications(content){
 // Only these exact recurring process notices move backstage. Source-specific
 // limits and explicit preprint status remain ordinary, visible list items.
 const processNotices=new Set(["Limited reading.","Article screening is not peer review; reported results do not establish strong causal evidence."]);
 const sentences=textSentences(content);
 if(!sentences.some(sentence=>processNotices.has(sentence)))return readingBullets(content);
 const box=make("div","rv-qualifications");
 const substantive=sentences.filter(sentence=>!processNotices.has(sentence));
 // The mixed process sentence also carries a material causal qualification.
 // Keep that caution visible unless a source-specific causal limit already does.
 const mixedNotice="Article screening is not peer review; reported results do not establish strong causal evidence.";
 const hasCausalLimit=substantive.some(sentence=>/\b(?:cannot|can not|does not|do not|not establish|no|without|unverified|uncertain|limited|lack)\b[^.!?]*\bcausal(?:ity)?\b|\bcausal(?:ity)?\b[^.!?]*\b(?:cannot|not|unverified|uncertain|limited|lack)\b/i.test(sentence));
 if(sentences.includes(mixedNotice)&&!hasCausalLimit)substantive.push("Reported results do not establish strong causal evidence.");
 if(substantive.length)box.append(readingBullets(substantive.join(" ")));
 const full=make("details","rv-full-qualifications");
 add(full,make("summary","","Full qualifications"),readingProse(content));
 box.append(full);return box;
}
function readingProse(content,className=""){
 const prose=make("div","rv-prose "+className);
 for(const paragraph of readingParagraphs(content))prose.append(make("p","",paragraph));
 return prose;
}
function sourceFields(x){
 const r=x.reading||{},a=x.analysis||{};
 // Checked commentary must not inherit stale scholarly extracts or synopsis.
 if(originalCommentary(r))return [];
 if(x.kind!=="scholarly")return [
  ["Publisher or editorial synopsis",r.overview,"Synopsis"],
  ["Original editorial notes",(x.editorial_notes||{}).argument,"Editorial notes"]];
 // Do not mistake the shortened reading-card excerpts for all indexed text.
 // Original summaries always retain the separate, potentially older index.
 const original=originalSummary(x),hasSections=Boolean(a.fulltext_url);
 return [
  ["Methods as indexed",a.methods||(!original?r.methods:"") ,hasSections?"Methods section":"Abstract selection"],
  ["Results as indexed",a.results||(!original?r.findings:"") ,hasSections?"Results section":"Abstract selection"],
  ["Discussion as indexed",a.discussion||(!original?r.interpretation:"") ,hasSections?"Discussion section":"Abstract selection"],
  ["Limitations as indexed",a.limitations||(!original?r.limitations:"") ,hasSections?"Limitations section":"Abstract selection"],
  ["Abstract",x.abstract_text,x.abstract_source||"Source abstract"]
 ];
}
function sourceReader(x){
 const fields=sourceFields(x),available=fields.filter(([,content])=>content),r=x.reading||{},a=x.analysis||{},original=originalSummary(x);
 if(!available.length)return null;
 const drawer=make("details","rv-drawer rv-source-excerpts");
 drawer.append(make("summary","",original?
  a.original_paraphrases_only?"Inspect prior indexed notes and abstract":"Inspect machine-indexed excerpts and abstract":
  "Inspect source text and abstract"));
 const panel=make("div","rv-reader-panel"),intro=make("div","rv-indexed-provenance");
 intro.append(make("p","rv-mini-label","SOURCE READER · "+available.length+" SECTIONS"));
 if(original)intro.append(make("p","","Indexed reference material, separate from the original summary above. It may refer to a different source version."));
 intro.append(make("p","",a.original_paraphrases_only?
  "Original editorial paraphrases and the indexed abstract. These are not copied full-text passages.":
  "Machine-indexed source passages, not an independent appraisal. Paragraph breaks are added for readability; extraction can retain citation, equation or table artifacts."));
 if(a.provenance||r.provenance)intro.append(make("p","rv-reader-basis",a.provenance||r.provenance));
 const url=httpsSourceUrl(a.fulltext_url)||(!original?httpsSourceUrl(x.url):null);
 if(url)intro.append(link("Open indexed reference source",url,"rv-secondary-link"));
 panel.append(intro);
 const contents=make("nav","rv-reader-contents");contents.setAttribute("aria-label","Source sections");
 const drawerBody=make("div","rv-drawer-body"),sections=[];
 for(const [label,content,basis] of available){
  const section=make("details","rv-excerpt rv-source-section");
  const count=String(content).trim().split(/\s+/).length;
  add(section,add(make("summary","rv-source-section-title"),make("span","",label),make("small","",count+" words")),
   make("p","rv-section-basis",basis),readingProse(content));
  const jump=btn(label,()=>{section.open=true;section.querySelector?.("summary")?.focus();section.scrollIntoView?.({block:"start"});},"rv-reader-jump");
  contents.append(jump);sections.push(section);drawerBody.append(section);
 }
 const controls=make("div","rv-reader-controls");
 add(controls,btn("Expand all sections",()=>sections.forEach(s=>s.open=true),"rv-reader-control"),
  btn("Collapse all sections",()=>sections.forEach(s=>s.open=false),"rv-reader-control"));
 add(panel,contents,controls,drawerBody);drawer.append(panel);return drawer;
}
function evidenceCoverage(x){
 const r=x.reading||{},d=r.digest||{},fields=sourceFields(x);
 const section=make("details","rv-coverage");
 add(section,make("summary","","Available source material"),
  make("p","rv-coverage-note",depth(x)==="abstract"?"This reading uses the abstract, not the full paper.":"Indexed sections can be incomplete. Availability does not rate study quality."));
 const table=make("table","rv-coverage-table"),body=make("tbody","");
 [["Methods",fields[0]?.[1],d.approach],["Results",fields[1]?.[1],d.finding],["Discussion",fields[2]?.[1],d.interpretation],["Limitations",fields[3]?.[1],d.limitation]].forEach(([label,content,summary])=>{
  const row=make("tr",""),name=make("th","",label);name.setAttribute("scope","row");
  const status=content?(depth(x)==="abstract"?"In abstract selection":"Indexed passage"):summary?"Summary note":"Not indexed";
  add(row,name,make("td",content||summary?"rv-available":"rv-unavailable",status));body.append(row);
 });
 table.append(body);section.append(table);
 section.append(make("p","rv-coverage-note","“Not indexed” describes the material available here, not a flaw in the study or proof that the paper omitted it."));
 return section;
}

function showPaper(x){
 const root=$("#paper-content");
 root.replaceChildren();
 if(!x){root.append(make("div","empty-state","This source has not been indexed as a public reading."));return;}
 if(x.source_quality?.decision==="awaiting_full_article_reading"){
  const page=make("article","rv-article rv-awaiting-reading");
  page.append(btn("← Research library",()=>goto("library"),"rv-back"));
  const head=make("header","rv-head");
  add(head,make("p","eyebrow","DISCOVERED SOURCE · NOT YET ANALYZED"),
    make("h1","rv-headline",readableSourceTitle(x)),
    make("p","rv-deck","This article was identified by the discovery system, but its complete argument has not been retrieved and verified. A feed description is not a research reading, so no analysis is presented here."));
  page.append(head);
  const note=make("section","rv-source-gap");
  add(note,make("h2","","What is missing?"),
    make("p","","The article still needs source-level review of its reasoning, examples and qualifications before it can appear in the Observatory's editorial library."));
  if(/^https:\/\//.test(x.url||""))note.append(link("Read the original article",x.url,"rv-secondary-link"));
  page.append(note);root.append(page);return;
 }
 const r=x.reading||{},d=r.digest||{},original=originalSummary(x),editorial=d.status==="editorially_written_from_indexed_sections";
 const commentary=originalCommentary(r);
 const scholarly=x.kind==="scholarly",hasFinding=Boolean(d.finding),conceptual=x.research_type==="conceptual_framework";
 const isQuestion=scholarly&&!hasFinding&&!editorial&&!original;
 // Unreviewed extracts are identifiable as source notes, not hand-written insight.
 const headline=original?d.idea||d.finding:editorial?d.idea:hasFinding&&d.finding.length<=230?d.finding:d.idea||x.title;
 const main=make("article","rv-article");
 const back=btn("← All readings",()=>goto("library"),"rv-back");
 const head=make("header","rv-head");
 const metadata=make("div","rv-meta");
 add(metadata,make("span","rv-dot",x.lane||"Research"),
  make("span","rv-meta-separator","·"),
  make("span","",original?"Original summary":conceptual?"Conceptual framework":editorial?"Edited reading":scholarly?isQuestion?"Research topic":"Source-reported result":"Perspective"));
 const status=make("p","rv-status",original?"AI source-check · not human review or independent replication":conceptual?"Proposed educational framework · not an experimental test":editorial?"Research reading":scholarly?"Based on indexed source material":"Commentary and perspectives");
 const title=make("h1","rv-headline",readingTitles[id(x)]||(original?headline:cleanLead(headline,readableSourceTitle(x))));
 const intro=(scholarly||original)&&d.explain?make("p","rv-deck",d.explain):null;
 add(head,metadata,title);
 const introCopy=make("div","rv-intro-copy");
 if(readingTitles[id(x)]&&d.idea)introCopy.append(make("p","rv-summary-idea",d.idea));
 if(intro){const overview=make("details","rv-overview");add(overview,make("summary","","Read the full overview"),readingProse(d.explain));introCopy.append(overview);}
 const sourceRow=make("div","rv-source-row");
 add(sourceRow,make("span","",[x.venue,date(x.published)].filter(Boolean).join(" · ")),make("span","",original?checkedSourceLabel(r):depthName(x)));
 introCopy.append(sourceRow);
 if(original&&r.temporal_notice){const dates=make("details","rv-source-dates");add(dates,make("summary","","Source dates"),make("p","rv-reading-notice",r.temporal_notice));introCopy.append(dates);}
 // Editorial art is separate from the source-grounded figures below.
 if(editorialArt(x)){const lede=make("div","rv-lede-layout");add(lede,introCopy,editorialMedia(x,"reading"));head.append(lede);}else head.append(introCopy);

 main.append(back,head);
 const layout=make("div","rv-layout"),story=make("div","rv-story"),side=make("aside","rv-sidebar");
 const body=make("section","rv-content");
 // Older indexed graphics can describe a different source version. Keep the
 // checked original prose primary instead of reusing those unreviewed visuals.
 const art=original?null:conceptArtwork(x);
 const autoGraphic=Boolean(art&&art.className&&art.className.includes("automatic-evidence"));
 const lead=make("div","rv-section-head");
 add(lead,make("span","rv-section-overline","RESEARCH AT A GLANCE"),
  make("h2","rv-section-title",conceptual?"What the paper proposes":scholarly?isQuestion?"Explore the source":"Finding, method & limits":"The argument in context"));
 body.append(lead);
 if(original&&!commentary){
  // A conceptual summary can intentionally have no measured finding. Its
  // checked idea and interpretation must never fall through to legacy stages.
  if(hasFinding||conceptual){
   const claim=make("div","rv-claim");
   add(claim,make("span","rv-mini-label",conceptual?"PROPOSED MODEL, NOT A TESTED EFFECT":"REPORTED FINDING"),
      make("p","",d.finding||d.idea));
   body.append(claim);
  }
 }else if(editorial&&hasFinding&&!autoGraphic){
  const claim=make("div","rv-claim");
  add(claim,make("span","rv-mini-label","REPORTED FINDING"),make("p","",d.finding));
  body.append(claim);
 }else if(scholarly&&hasFinding&&!autoGraphic&&!commentary){
  body.append(add(make("div","rv-claim"),make("span","rv-mini-label","SOURCE-REPORTED RESULT"),readingProse(d.finding)));
 }else if(commentary||!scholarly){
  const deep=d.longform||{},hasDepth=Boolean(deep.reasoning||deep.examples||deep.tension||deep.implications);
  const reading=make("div","rv-longform");
  function lens(label,value){
   if(!value)return;
   const collapsed=!label.includes("central argument")&&!label.includes("Qualifications");
   const part=make(collapsed?"details":"section","rv-longform-part");
   add(part,make(collapsed?"summary":"h3","",label),readingProse(value));
   reading.append(part);
  }
  // Publisher metadata alone cannot justify invented counterarguments or a
  // faux methods section. Only display fields supported by source analysis.
  lens(commentary?"The attributed central argument":deep.source_depth==="publisher_synopsis"?"From the publisher’s description":"The central argument",deep.thesis||(commentary?"":r.overview));
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
  add(claim,make("span","rv-mini-label","RESEARCH QUESTION · RESULT SUMMARY PENDING"),
    make("p","",depth(x)==="abstract"?"Explore the indexed abstract below. A full-paper appraisal is not available here.":"Explore the indexed sections below. A source-checked result summary is not available here."));
  body.append(claim);
 }
 if(art){
  const visuals=make("div","rv-artwork");
  visuals.append(art);
  body.append(visuals);
 }
 const context=make("div","rv-context-grid");
 if(d.approach){
  const method=make("section","rv-context");
  add(method,make("h3","",conceptual?"How the framework was developed":"How it was studied"),readingBullets(d.approach));context.append(method);
 }
 if(d.limitation){
  const caveat=make("section","rv-context");
  add(caveat,make("h3","",conceptual?"What has not been established":"What remains uncertain"),readingQualifications(d.limitation));context.append(caveat);
 }
 if(!commentary&&(scholarly||original)&&!autoGraphic)body.append(context);
 if(!commentary&&(original||(scholarly&&editorial))&&d.interpretation){
  const relevance=make("details","rv-take");
  add(relevance,make("span","rv-section-overline","02 / INTERPRETATION"),
    make("summary","rv-section-title",original?"Interpretation and implications":"Why this matters"),
    readingProse(d.interpretation));
  body.append(relevance);
 }
 if(scholarly&&!original&&d.longform){
  const deep=d.longform;
  const extended=make("details","rv-research-longform");
  add(extended,make("span","rv-section-overline","02 / CLOSER READING"),
     make("summary","rv-section-title","A deeper look at the study"));
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
   add(part,make("h3","",label),readingProse(value));
   parts.append(part);
  }
  if(deep.basis)parts.append(make("p","rv-longform-basis",
   "Reading basis: "+deep.basis+" · Machine-generated, not independently reviewed"));
  extended.append(parts);
  body.append(extended);
 }
 // Keep the extracted text and metadata in one clearly optional evidence drawer.
 if(original){
  const evidence=originalEvidence(r);
  if(evidence)body.append(evidence);
 }
 const reader=sourceReader(x);
 if(reader)body.append(reader);
 story.append(body);
 const cite=make("section","rv-source");
 add(cite,make("span","rv-section-overline","SOURCE"),
  make("h2","","The source"),
  make("h3","rv-source-title",readableSourceTitle(x)),
  make("p","rv-source-meta",(original?"Indexed record: ":"")+[x.venue,date(x.published)].filter(Boolean).join(" · ")));
 const pills=make("div","rv-source-pills");
 add(pills,make("span","",depthName(x)),
    make("span","",x.relation||"Unclassified"));
 cite.append(pills);
 if(original){
  cite.append(make("p","rv-source-version","Checked source: "+checkedSourceLabel(r)));

  // Preserve distinct legacy basis text without repeating an entire typed notice.

  const sourceUrl=httpsSourceUrl(r.source_url);
  if(sourceUrl)cite.append(link("Read the source",sourceUrl,"rv-primary-link"));
  if(r.related_journal_doi&&r.related_journal_doi!==r.source_doi)
   cite.append(link("Related journal publication (not the checked source)",doiUrl(r.related_journal_doi),"rv-secondary-link"));
 }else{
  if(x.url&&/^https:\/\//.test(x.url))cite.append(link("Open publication",x.url,"rv-primary-link"));
  if(x.analysis?.fulltext_url&&/^https:\/\//.test(x.analysis.fulltext_url))
   cite.append(link("Read accessible full text",x.analysis.fulltext_url,"rv-secondary-link"));
  if(x.source_review?.source_url&&/^https:\/\//.test(x.source_review.source_url))
   cite.append(link("Read verified full-text republication",x.source_review.source_url,"rv-secondary-link"));
 }
 const provenance=make("details","rv-provenance"),provenanceBody=make("div","rv-provenance-body");
 provenanceBody.append(make("p","",r.provenance||"Publisher/source index"));
 if(original){
  provenanceBody.append(status);
  provenanceBody.append(checkedReadingContext(r,"rv-reading-notice"));
  if(d.basis&&!String(r.notice||"").includes(d.basis))provenanceBody.append(make("p","rv-review-basis",d.basis));
 }else provenanceBody.append(status);
  if(r.source_version)provenanceBody.append(make("p","","Source version identifier: "+r.source_version));
 if(original){
  provenanceBody.append(make("p","",r.source_doi?"Checked source DOI: "+r.source_doi:"No DOI recorded for the checked source"));
  if(r.related_journal_doi&&r.related_journal_doi!==r.source_doi)
   provenanceBody.append(make("p","","Related journal DOI (not checked here): "+r.related_journal_doi));
 }else provenanceBody.append(make("p","",x.doi?"DOI: "+x.doi:"No DOI recorded"));
 add(provenance,make("summary","","Source details & reading basis"),provenanceBody);
 cite.append(provenance);side.append(cite);
 if(scholarly&&!original)side.append(evidenceCoverage(x));
 if(!original&&x.analysis?.figures?.length){
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
   if(/^https:\/\//.test(companion.url||""))article.append(link("Read the commentary",companion.url,"rv-secondary-link"));
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
async function init(){
 // The Experimental Lab initializes independently in lab-play.js.
 try{
  const rs=await Promise.all(["data/public-library.json","data/public-weekly.json","data/runs.json","data/fulltext-backfill-state.json","data/public-featured-issue.json","data/public-pending-sources.json"].map(p=>fetch(p+"?v="+Date.now(),{cache:"no-store"})));
  if(!rs[0].ok)throw new Error("Library download failed (HTTP "+rs[0].status+")");
  S.records=await rs[0].json();if(!Array.isArray(S.records))throw new Error("Unexpected library format");S.records=S.records.filter(x=>x.reading?.level&&x.reading.level!=="citation_only");S.companions=S.records.filter(x=>Boolean(x.companion_to));S.records=S.records.filter(x=>!x.companion_to);
  S.week=rs[1].ok?await rs[1].json():{run:{mode:"unavailable"},items:[]};
  S.runs=rs[2].ok?await rs[2].json():[];
  S.backlog=rs[3].ok?await rs[3].json():{};
  S.issue=rs[4].ok?await rs[4].json():{};
  S.pending=rs[5].ok?await rs[5].json():[];
  home();renderIssue();renderBacklog();showLibrary();renderPerspectives();route();
 }catch(e){$("#issue-label").textContent="INDEX OFFLINE";$("#issue-meta").textContent="Research data could not load";$("#feature-grid").replaceChildren(make("div","empty-state","Could not load the research archive: "+e.message));route()}
}
$$("[data-route]").forEach(a=>a.onclick=e=>{e.preventDefault();goto(a.dataset.route)});
["search","scope-filter","topic-filter","depth-filter","type-filter"].forEach(s=>$("#"+s).addEventListener(s==="search"?"input":"change",showLibrary));
$("#browse-editorial").addEventListener("click",e=>{e.preventDefault();goto("perspectives")});
$("#perspectives-library-link").addEventListener("click",e=>{e.preventDefault();$("#scope-filter").value="all";$("#topic-filter").value="";$("#search").value="";$("#type-filter").value="nonacademic";$("#depth-filter").value="readable";goto("library")});
$("#perspectives-essays-link").addEventListener("click",e=>{e.preventDefault();$("#perspectives-essays").scrollIntoView({behavior:"smooth",block:"start"})});
$$("[data-library-theme]").forEach(button=>button.addEventListener("click",()=>{$("#topic-filter").value=button.dataset.libraryTheme;showLibrary()}));
$("#library-sort").addEventListener("change",showLibrary);
$("#library-reset").addEventListener("click",()=>{
 $("#search").value="";$("#scope-filter").value="all";$("#topic-filter").value="";$("#type-filter").value="";$("#depth-filter").value="readable";showLibrary();
});
function closeNavigation(){
 $(".main-nav").classList.remove("is-open");$("#nav-toggle").setAttribute("aria-expanded","false");
}
const navigation=$(".main-nav"),menuToggle=$("#nav-toggle");
navigation.classList.add("is-collapsible");menuToggle.hidden=false;
menuToggle.addEventListener("click",()=>{const open=menuToggle.getAttribute("aria-expanded")!=="true";menuToggle.setAttribute("aria-expanded",String(open));navigation.classList.toggle("is-open",open)});
navigation.addEventListener("keydown",event=>{if(event.key==="Escape"&&menuToggle.getAttribute("aria-expanded")==="true"){closeNavigation();menuToggle.focus()}});
window.addEventListener("hashchange",route);
init();



