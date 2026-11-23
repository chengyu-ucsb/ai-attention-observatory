"use strict";
const $=s=>document.querySelector(s),$$=s=>Array.from(document.querySelectorAll(s));
const S={records:[],companions:[],pending:[],week:{},issue:{},manifest:null,libraryLoaded:false,duration:10,left:600,timer:null,running:false,checkpoint:null};
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
const layerStack=[];
let layerOverflow="";
function notifyLayerChange(){document.dispatchEvent(new CustomEvent("observatory-layer-change",{detail:{open:layerStack.length>0,depth:layerStack.length}}));}
function restoreLayer(){
 const state=layerStack.pop();if(!state)return null;
 const {node,parent,next,hidden}=state;node.hidden=hidden;
 parent.insertBefore(node,next?.parentNode===parent?next:null);return state;
}
function presentLayer(){
 const state=layerStack[layerStack.length-1];if(!state)return;
 $("#reading-layer-title").textContent=state.title;state.node.hidden=false;
 $("#reading-layer-body").replaceChildren(state.node);
}
function closeLayer(){
 const state=restoreLayer();if(!state)return;
 const dialog=$("#reading-layer");
 if(layerStack.length){
  presentLayer();if(!dialog.open)dialog.showModal();
  if(state.trigger?.isConnected)state.trigger.focus({preventScroll:true});
  else dialog.querySelector(".layer-close").focus();
 }else{
  if(dialog?.open)dialog.close();
  document.body.style.overflow=layerOverflow;layerOverflow="";
  if(state.trigger?.isConnected)state.trigger.focus({preventScroll:true});
 }
 notifyLayerChange();
}
function closeAllLayers(restoreFocus=true){
 if(!layerStack.length)return;
 const origin=layerStack[0].trigger;
 while(layerStack.length)restoreLayer();
 const dialog=$("#reading-layer");if(dialog?.open)dialog.close();
 document.body.style.overflow=layerOverflow;layerOverflow="";
 if(restoreFocus&&origin?.isConnected)origin.focus({preventScroll:true});
 notifyLayerChange();
}
function openLayer(title,content,trigger){
 let dialog=$("#reading-layer");
 if(!dialog){
  dialog=make("dialog","reading-layer");dialog.id="reading-layer";dialog.setAttribute("aria-labelledby","reading-layer-title");
  const header=make("header","reading-layer-head"),heading=make("h2");heading.id="reading-layer-title";
  const close=btn("Close",closeLayer,"layer-close");close.setAttribute("aria-label","Close reading card");
  const body=make("div","reading-layer-body");body.id="reading-layer-body";
  add(header,heading,close);add(dialog,header,body);document.body.append(dialog);
  // Escape steps back through nested cards; only the outer close dismisses
  // the native modal. A queued close event must not tear down a reopened card.
  dialog.addEventListener("cancel",event=>{event.preventDefault();closeLayer();});
  dialog.addEventListener("close",()=>{if(!dialog.open)closeAllLayers();});
  dialog.addEventListener("click",event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeLayer();}});
 }
 const existing=layerStack.findIndex(state=>state.node===content);
 if(existing>=0){while(layerStack.length>existing+1)closeLayer();dialog.querySelector(".layer-close").focus();return;}
 if(!layerStack.length){layerOverflow=document.body.style.overflow;document.body.style.overflow="hidden";}
 layerStack.push({title,node:content,parent:content.parentNode,next:content.nextSibling,hidden:content.hidden,trigger:trigger||document.activeElement});
 presentLayer();if(!dialog.open)dialog.showModal();dialog.querySelector(".layer-close").focus();notifyLayerChange();
}
function layerButton(label,title,content,cls=""){
 const wrap=make("div","layer-control"+(cls?" "+cls:"")),button=btn(label,()=>openLayer(title,content,button),"layer-trigger");
 button.setAttribute("aria-haspopup","dialog");content.hidden=true;add(wrap,button,content);return wrap;
}
function layerDisclosure(node,title){
 if(!node||node.dataset.layered)return;
 const summary=node.querySelector(":scope > summary");if(!summary)return;
 const body=make("div","layer-content");for(const child of Array.from(node.childNodes))if(child!==summary)body.append(child);
 const replacement=layerButton(title||summary.textContent.trim(),title||summary.textContent.trim(),body,node.className);
 if(node.id)replacement.id=node.id;replacement.hidden=node.hidden;replacement.dataset.layered="true";node.replaceWith(replacement);return replacement;
}
function sectionMenu(host,groups,id,label="Explore this page"){
 const nav=make("nav","section-menu");nav.id=id;nav.setAttribute("aria-label",label);
 const heading=make("div","section-nav-heading"),position=make("span","section-position"),tabs=make("div","section-shortcuts"),status=make("span","sr-only");
 status.setAttribute("role","status");position.setAttribute("aria-hidden","true");
 add(heading,make("p","section-nav-label",label),position);
 for(const [index,group] of groups.entries()){
  const b=btn("",()=>choose(group.key,true),"section-shortcut"),number=make("span","section-step",String(index+1).padStart(2,"0")),copy=make("span","section-option-copy");
  number.setAttribute("aria-hidden","true");b.dataset.section=group.key;
  copy.append(make("span","section-option-title",group.label));if(group.note)copy.append(make("small","section-option-note",group.note));
  const targets=[];for(const [i,node] of group.nodes.entries())if(node){if(!node.id)node.id=id+"-panel-"+index+"-"+i;node.classList.add("section-panel");targets.push(node.id);}
  b.setAttribute("aria-controls",targets.join(" "));add(b,number,copy);tabs.append(b);
 }
 add(nav,heading,tabs,status);host.prepend(nav);
 function choose(key,fromControl=false){
  const found=groups.find(g=>g.key===key)||groups[0];nav.dataset.activeSection=found.key;
  for(const group of groups)for(const node of group.nodes)if(node)node.hidden=group.key!==found.key;
  for(const button of tabs.children)button.setAttribute("aria-pressed",String(button.dataset.section===found.key));
  const index=groups.indexOf(found)+1;position.textContent=String(index).padStart(2,"0")+" / "+String(groups.length).padStart(2,"0");
  status.textContent=found.label+", section "+index+" of "+groups.length;nav.dispatchEvent(new CustomEvent("sectionchange",{detail:found.key}));
  const first=found.nodes.find(Boolean);if(fromControl&&first&&first.getBoundingClientRect().top<100)first.scrollIntoView({block:"start",behavior:"instant"});
 }
 choose(groups[0].key);return {choose,nav,focusActive:()=>Array.from(tabs.children).find(b=>b.dataset.section===nav.dataset.activeSection)?.focus({preventScroll:true})};
}
let homeMenu,issueMenu,issueThemeMenu,labPageMenu,perspectiveMenu;
function setupPageLayers(){
 const homeHost=make("div","shell home-section-controls");$("#home .field-guide").before(homeHost);
 homeMenu=sectionMenu(homeHost,[
  {key:"overview",label:"Start exploring",note:"Find your way in",nodes:[$("#home .field-guide"),$("#home .lab-teaser")]},
  {key:"ideas",label:"News & opinion",note:"Reporting, arguments & guides",nodes:[$("#beyond-journals")]},
  {key:"landscape",label:"Research landscape",note:"See the collection",nodes:[$("#home .glance-section"),$("#home .issue-strip")]},
  {key:"recent",label:"Recently added",note:"New reading material",nodes:[$("#home .arrivals-section")]},
  {key:"follow",label:"Follow the brief",note:"Keep up each week",nodes:[$("#home .follow-section")]}
 ],"home-section","Explore the Observatory");
 layerDisclosure($(".home-source-drawer"),"Sources behind this issue");
 layerDisclosure($(".collection-details"),"About the collection");
 layerDisclosure($(".library-refine"),"Filter the collection");
 layerDisclosure($(".play-update"),"What's new in the Lab");
 for(const node of $$(".precedent-details"))layerDisclosure(node,"Design notes");
 const labNote=$(".play-note"),noteBody=make("div");while(labNote.firstChild)noteBody.append(labNote.firstChild);labNote.append(layerButton("About these experiments","About these experiments",noteBody));
 labPageMenu=sectionMenu($("#lab-page-navigation"),[{key:"experiments",label:"Experiments",note:"Play, compare, reflect",nodes:[$("#lab-activities")]},{key:"design",label:"Design examples",note:"Ideas behind the tools",nodes:[$(".play-precedents")]}],"lab-section","Explore the Lab");
 const perspectiveHost=make("div","perspective-section-controls"),intro=$$("#perspectives .perspectives-intro");$(".perspectives-quick-links").after(perspectiveHost);
 perspectiveMenu=sectionMenu(perspectiveHost,[
  {key:"news",label:"News reporting",nodes:[intro[0],$("#perspectives-news")]},
  {key:"essays",label:"Opinion & analysis",nodes:[intro[1],$("#perspectives-essays")]},
  {key:"products",label:"Product guides",nodes:[intro[2],$("#perspectives-products")]}
 ],"perspectives-section","Browse by source type");
 perspectiveMenu.nav.addEventListener("sectionchange",event=>{
  if(location.hash.startsWith("#perspectives"))history.replaceState(history.state,"","#perspectives?section="+event.detail);
 });
 const atlasHost=make("div");$(".atlas-stat-row").after(atlasHost);
 sectionMenu(atlasHost,[{key:"themes",label:"Research themes",nodes:[$(".atlas-topic")]},{key:"years",label:"Publication years",nodes:[$(".atlas-years")]},{key:"material",label:"Source material",nodes:[$(".atlas-coverage"),$(".atlas-matrix")]}],"atlas-section");
}
function date(s){if(!s||!/^20\d\d/.test(s))return "Undated";let d=new Date(s.slice(0,10)+"T12:00:00Z");return isNaN(d.getTime())?"Undated":d.toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"})}
function id(x){return String(x.doi||x.url||x.title)}
function record(key){
 const published=[...S.records,...S.companions];
 return published.find(row=>id(row)===key)||S.pending.find(row=>id(row)===key)||
  published.find(row=>row.legacy_urls?.includes(key));
}
function readingPath(row){return "#paper/"+encodeURIComponent(id(row))}
function depth(x){return x.reading?.level||"citation_only"}
function originalSummary(x){return x.reading?.original_summary===true}
function originalCommentary(reading){return reading?.original_summary===true&&reading.research_type==="attributed_commentary"}
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
 return lane==="AI & cognition"?"focus":"research";
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
// Use complete edited phrases only; a published finding is never clipped into a heading.
function readingHeadline(x){
 const d=x.reading?.digest||{};
 const edited=originalSummary(x)||["editorially_written_from_indexed_sections","edited_perspective","conceptual_framework"].includes(d.status);
 const options=[x.display_headline,readableSourceTitle(x),edited?d.idea:""];
 const statistical=/\b(?:p|r(?:²|\^2)?|b|t|f|n|se|sd|cfi|rmsea)\s*(?:\([^)]*\))?\s*[=<>≤≥]|[βρχ](?:²|\^2)?\s*(?:\([^)]*\))?\s*[=<>≤≥]|\b\d+(?:\.\d+)?%\s*(?:CI|confidence)|\b(?:Table|Figure)\s+\d/i;
 const fragment=/^(?:In contrast|Similarly|Furthermore|Moreover|As shown|In conclusion|Results?|Conclusions?)\s*[,：:]|(?:…|\.\.\.)$/i;
 for(const value of options){
  const candidate=String(value||"").replace(/\s+/g," ").trim();
  if(candidate&&candidate.length<=55&&candidate.split(" ").length<=10&&!statistical.test(candidate)&&!fragment.test(candidate))return candidate;
 }
 // New long titles are held for editing before publication. Older deep links
 // still expose the full bibliographic title in their Source section.
 return "Read the original article";
}
function shortIdea(x){return readingHeadline(x)}
// A source's bibliographic identity and version belong to its edition. Only
// reuse a catalog display label when both the source ID and original title match.
function editionReading(source){
 const candidate=record(source.id);
 // An older alias can identify a different publication in the current catalog.
 // Only attach an edition's original citation to the matching reading.
 return candidate&&candidate.title===source.title&&depth(candidate)!=="citation_only"?candidate:null;
}
function editionPresentation(source){
 const labels=S.manifest?.source_labels?.[source.id];
 if(labels)return {...source,...labels};
 const current=editionReading(source);
 if(!current)return source;
 return {...source,display_headline:source.display_headline||current.display_headline,
  reader_genre:source.reader_genre||sourceGenre(current)};
}
function editionReadingHeadline(source){return readingHeadline(editionPresentation(source))}
const genreLabels={
 research:"Research",review:"Research review",conceptual:"Conceptual paper",proposal:"Research proposal",
 reporting:"News report",opinion:"Opinion",editorial:"Journal editorial",analysis:"Analysis",commentary:"Commentary",
 guide:"Product guide",other:"Source"
};
function sourceGenre(x){
 if(Object.hasOwn(genreLabels,x.reader_genre)&&
    !(x.kind==="nonacademic"&&["research","review","conceptual","proposal"].includes(x.reader_genre)))return x.reader_genre;
 // Legacy snapshots and previously shared deep links can predate reader_genre.
 const type=x.reading?.research_type||x.research_type||"",genre=x.reading?.genre||x.genre||x.reading?.digest?.longform?.genre||x.digest?.longform?.genre||"";
 const format=x.format||"";
 if(type==="editorial"||/^editorial\s*:/i.test(x.title||""))return "editorial";
 if(/^(?:reported_analysis|news(?:_report(?:ing)?)?|press_reporting|journalism|reporting)$/.test(genre)||/reporting/i.test(format))return "reporting";
 if(genre==="opinion"||format==="Opinion"||["opinion","perspective","commentary"].includes(type))return "opinion";
 if(/analysis/.test(genre)||/analysis/i.test(format))return "analysis";
 if(x.source==="Official product documentation"||x.reading?.digest?.longform?.source_depth==="product_documentation")return "guide";
 if(type==="attributed_commentary"||x.kind==="nonacademic")return "commentary";
 if(["conceptual","conceptual_framework","theoretical"].includes(type))return "conceptual";
 if(["research_synthesis","systematic_review","meta_analysis","review"].includes(type))return "review";
 if(x.kind==="scholarly"&&/\b(?:systematic (?:literature )?review|scoping review|narrative review|meta-analysis)\b/i.test(x.title||""))return "review";
 if(["proposal","protocol","research_proposal"].includes(type))return "proposal";
 return x.kind==="scholarly"?"research":"other";
}
function sourceFamily(x){
 const genre=sourceGenre(x);
 if(["research","review","conceptual","proposal"].includes(genre))return "research";
 if(genre==="guide")return "product";
 return genre==="other"?"other":"media";
}
function readingKind(x){return genreLabels[sourceGenre(x)]}
function matchesSourceType(x,filter){
 if(!filter)return true;
 const genre=sourceGenre(x);
 if(filter==="scholarly")return sourceFamily(x)==="research";
 if(filter==="nonacademic")return ["media","product"].includes(sourceFamily(x));
 if(filter==="opinion")return genre==="opinion"||genre==="editorial";
 if(filter==="analysis")return genre==="analysis"||genre==="commentary";
 return genre===filter;
}
function mediaByline(x){
 const reading=x.reading||x;
 return reading.attributed_to||reading.digest?.longform?.attributed_to||x.authors?.slice(0,2).join(" & ")||"";
}
function publicationContext(x){
 const reading=x.reading||x;
 const version=String(reading.source_version||"");
 const preprint=version.match(/arxiv[_ ]preprint[_ ]v(\d+)/i);
 if(preprint)return "arXiv preprint v"+preprint[1];
 if(/preprint|working[ _]paper/i.test(version)||reading.research_type==="preprint"||x.research_type==="preprint")return "Preprint";
 if((x.reading_level||reading.level)==="abstract")return "Based on the abstract";
 return "";
}
function readingBasisName(x){
 const d=x.reading?.digest||{};
 // The available full text and the text supporting a particular finding are
 // not interchangeable. Keep a mixed-depth finding's actual basis visible.
 if(!originalSummary(x)&&x.kind==="scholarly"&&
   (d.finding_source==="abstract"||d.editorial_basis==="abstract"||depth(x)==="abstract"))return "Based on the abstract";
 return depthName(x);
}
function ideaInfo(x){return {text:readingHeadline(x),label:readingKind(x)}}
function rank(x){let r=x.reading||{},v=({"full_text":80,"abstract":46,"curated":25,"citation_only":0})[depth(x)]||0;v+=(r.digest?.finding||x.has_finding)?26:0;v+=(r.methods||x.has_methods)?10:0;v+=(r.limitations||x.has_limitations)?4:0;v+=/ai|generative|chatgpt|attention|offloading|focus/i.test(x.title)?9:0;v+=x.relation==="Adjacent digital-attention evidence"?-25:0;return v}
// The four starting lenses keep their familiar colors; the published collection supplies the topics.
function collectionTopics(records=S.records){
 const counts=new Map();
 for(const row of records){const label=row.lane||"Unassigned";counts.set(label,(counts.get(label)||0)+1);}
 return [...counts].sort(([a],[b])=>a.localeCompare(b)).map(([label,count])=>({
  label,count,color:themes.find(theme=>theme[0]===label)?.[4]||"#74676A"
 }));
}
function extendTopicChoices(){
 const select=$("#topic-filter"),browser=$(".theme-browser");
 for(const {label} of collectionTopics()){
  if(Array.from(select.options).some(option=>option.value===label))continue;
  select.append(new Option(label,label));
  const button=btn(label,()=>chooseLibraryTheme(label));button.dataset.libraryTheme=label;
  button.setAttribute("aria-pressed","false");browser.append(button);
 }
}
const libraryControls=[
 ["theme","topic-filter",""],["scope","scope-filter","all"],["type","type-filter",""],
 ["depth","depth-filter","readable"],["sort","library-sort","added"],["size","library-page-size","12"]
];
function readLibraryRoute(raw){
 const params=new URLSearchParams(raw.split("?")[1]||"");
 $("#search").value=params.get("q")||"";
 for(const [key,id,fallback] of libraryControls){
  const select=document.getElementById(id),value=params.get(key);
  select.value=Array.from(select.options).some(option=>option.value===value)?value:fallback;
 }
 const page=Number(params.get("page"));
 return Number.isSafeInteger(page)&&page>0?page-1:0;
}
function updateLibraryRoute(){
 showLibrary();
 const params=new URLSearchParams(),q=$("#search").value.trim();
 if(q)params.set("q",q);
 for(const [key,id,fallback] of libraryControls){
  const value=document.getElementById(id).value;
  if(value!==fallback)params.set(key,value);
 }
 if(libraryPage.number)params.set("page",String(libraryPage.number+1));
 history.replaceState(history.state,"","#library"+(params.size?"?"+params:""));
}
function chooseLibraryTheme(label){$("#topic-filter").value=label;updateLibraryRoute();}
function libraryHash(theme,sourceType=""){return "#library?theme="+encodeURIComponent(theme)+"&scope=all"+(sourceType?"&type="+sourceType:"")}
function goto(page,k){
 const value=page==="paper"?"#paper/"+encodeURIComponent(k):page==="library"&&k?libraryHash(k):"#"+page;
 if(location.hash===value)route({type:"hashchange"});else location.hash=value;
}
function route(event){
 if(event?.type==="hashchange")closeAllLayers(false);
 const raw=location.hash.slice(1)||"home";
 let page=raw.startsWith("paper/")?"paper":raw.split("?")[0];
 if(!["home","library","atlas","lab","paper","about","perspectives","issue"].includes(page))page="home";
 $$(".view").forEach(v=>v.hidden=v.id!==page);
 $$("[data-route]").forEach(v=>{v.classList.toggle("active",v.dataset.route===page);if(v.dataset.route===page)v.setAttribute("aria-current","page");else v.removeAttribute("aria-current")});
 if(page==="paper"){let key;try{key=decodeURIComponent(raw.slice(6))}catch{key=""}void openPaper(key,event?.type==="hashchange")}
 if(page==="library")showLibrary(readLibraryRoute(raw));if(page==="atlas")showAtlas();
 if(page==="perspectives")perspectiveMenu?.choose(new URLSearchParams(raw.split("?")[1]||"").get("section")||"news");
 if(page==="lab"){
  const params=new URLSearchParams(raw.split("?")[1]||"");
  labPageMenu?.choose(params.get("section")==="design"?"design":"experiments");
 }
 window.scrollTo({top:0,behavior:"instant"});
 if(event?.type==="hashchange"){
  closeNavigation();
  const heading=$("#"+page+" h1");if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true})}
 }
 if(page==="issue"){
  focusIssueTerm(raw);
  const source=new URLSearchParams(raw.split("?")[1]||"").get("source");
  if(source){
   const index=(S.issue.sources||[]).findIndex(item=>item.id===source);
   const item=document.getElementById("edition-source-"+index);
   if(item){issueMenu?.choose("sources");item.focus({preventScroll:true});item.scrollIntoView({block:"center"});}
  }
 }
}
function focusIssueTerm(raw){
 const term=new URLSearchParams(raw.split("?")[1]||"").get("term");
 const target=term?.startsWith("issue-term-")?document.getElementById(term):null;
 if(target){issueMenu?.choose("about");target.focus({preventScroll:true});target.scrollIntoView({block:"center"})}
}
function researchRecords(){return S.records.filter(x=>sourceFamily(x)==="research")}
function counts(records){return Object.fromEntries(depths.map(([level])=>[level,records.filter(x=>depth(x)===level).length]))}
function topicBars(selector,records){
 const root=$(selector),topics=collectionTopics(records),max=Math.max(1,...topics.map(t=>t.count));
 root.replaceChildren();
 for(const {label,count,color} of topics){
  const row=link("",libraryHash(label,"scholarly"),"topic-bar-line"),track=make("span","bar-track"),fill=make("span","bar-fill");
  fill.style.width=count/max*100+"%";fill.style.background=color;track.append(fill);
  add(row,make("span","bar-label",label),track,make("span","bar-value",count));root.append(row);
 }
}
function donut(records){
 const cc=counts(records),total=records.length,legend=$("#depth-legend");
 $("#record-count").textContent=total;legend.replaceChildren();
 let at=0;const parts=[];
 for(const [key,label,color] of depths){
  if(!cc[key])continue;
  const pct=100*cc[key]/total;parts.push(color+" "+at.toFixed(2)+"% "+(at+pct).toFixed(2)+"%");at+=pct;
  const marker=make("span","legend-swatch");marker.style.background=color;
  const copy=add(make("div"),make("div","legend-title",label+" · "+cc[key]),make("span","legend-caption",Math.round(pct)+"% of research sources"));
  legend.append(add(make("div","legend-item"),marker,copy));
 }
 $("#evidence-donut").style.background=parts.length?"conic-gradient("+parts.join(",")+")":"";
}

function issueRefs(ids,target){
 const list=(S.issue.sources||[]),container=target||make("div","issue-references");
 for(const key of ids||[]){
   const src=list.find(x=>x.id===key);
   if(!src)continue;
   const matches=editionReading(src);
   const b=matches?link(editionReadingHeadline(src),"#paper/"+encodeURIComponent(id(matches)),"issue-ref"):link(editionReadingHeadline(src),httpsSourceUrl(src.source_url)||httpsSourceUrl(src.url)||"#library","issue-ref");
   container.append(b);
 }
 return container;
}
// Weekly editorial prose has its own span renderer. Article summaries keep
// their existing paragraph and disclosure behavior.
function issueCitationUrl(source,citation={}){
 for(const value of [source?.source_url,source?.url]){
  if(typeof value!=="string"||/[\s\\\x00-\x1f]/.test(value))continue;
  try{
   const parsed=new URL(value);
   if(parsed.protocol!=="https:"||!parsed.hostname||parsed.username||parsed.password)continue;
   if(Number.isInteger(citation.page)&&citation.page>0&&(/\.pdf$/i.test(parsed.pathname)||parsed.pathname.includes("/pdf/")))parsed.hash="page="+citation.page;
   return parsed.href;
  }catch{}
 }
 return "";
}
function issueTermId(entry,index){return "issue-term-"+(String(entry.term).toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")||"definition")+"-"+(index+1)}
function issueTextSpans(text,section={},issue=S.issue||{}){
 const spans=[];
 for(const citation of section.citations||[]){
  const phrase=citation.text;
  if(typeof phrase!=="string"||!phrase.trim())continue;
  const start=text.indexOf(phrase),end=start+phrase.length;
  if(start<0||text.indexOf(phrase,start+1)!==-1||spans.some(s=>start<s.end&&end>s.start))continue;
  const hits=(issue.sources||[]).filter(source=>(section.source_ids||[]).includes(source.id)&&(citation.source_id?source.id===citation.source_id:source.title===citation.source));
  if(hits.length!==1)continue;
  const url=issueCitationUrl(hits[0],citation);if(!url)continue;
  spans.push({start,end,url,title:hits[0].title+(citation.locator?" · "+citation.locator:""),className:"issue-inline-citation"});
 }
 for(const [index,entry] of (issue.glossary||[]).entries()){
  if(!entry.term||!entry.definition)continue;
  const pattern=new RegExp("(?<![\\p{L}\\p{N}_])"+String(entry.term).replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+"(?![\\p{L}\\p{N}_])","giu");
  for(const match of text.matchAll(pattern)){
   const start=match.index,end=start+match[0].length;
   if(!spans.some(s=>start<s.end&&end>s.start))spans.push({start,end,url:"#issue?term="+issueTermId(entry,index),title:entry.definition,className:"issue-glossary-term"});
  }
 }
 return spans.sort((a,b)=>a.start-b.start);
}
function issueProse(value,section={},issue=S.issue||{},from=0,to=String(value||"").length){
 const text=String(value||""),spans=issueTextSpans(text,section,issue),prose=make("div","rv-prose issue-prose");
 let offset=from;
 for(const paragraph of text.slice(from,to).split(/\n\s*\n/)){
  const end=offset+paragraph.length,p=make("p");let cursor=offset;
  for(const span of spans){
   const left=Math.max(span.start,offset),right=Math.min(span.end,end);if(left>=right)continue;
   p.append(document.createTextNode(text.slice(cursor,left)));
   const anchor=link(text.slice(left,right),span.url,span.className);anchor.title=span.title;
   p.append(anchor);cursor=right;
  }
  p.append(document.createTextNode(text.slice(cursor,end)));prose.append(p);
  const separator=text.slice(end,to).match(/^\n\s*\n/);offset=end+(separator?separator[0].length:0);
 }
 return prose;
}
function compactIssueReading(section,label="Read the full analysis",issue=S.issue||{}){
 const text=String(section.text||""),full=issueProse(text,section,issue);
 if(text.length<260)return full;
 // Keep an author's opening paragraph together, including the observation
 // and its qualification. Older one-paragraph editions open with three sentences.
 const paragraphEnd=text.search(/\n\s*\n/);
 let end=paragraphEnd>=0?paragraphEnd:text.length;
 if(paragraphEnd<0){
  let sentences=0;
  for(const match of text.matchAll(/[.!?][”’"']?(?=\s|$)/g)){
   const prefix=text.slice(0,match.index+match[0].length);
   if(/\b(?:e\.g|i\.e|et al|Dr|Mr|Ms|Prof|Fig|vs)\.$/i.test(prefix)||/\b[A-Z]\.$/.test(prefix))continue;
   if(++sentences===3){end=prefix.length;break;}
  }
 }
 for(const span of issueTextSpans(text,section,issue))if(span.start<end&&span.end>end)end=span.end;
 if(end===text.length)return full;
 const box=make("div","compact-reading issue-compact-reading"),preview=issueProse(text,section,issue,0,end);
 preview.classList.add("compact-lead");
 return add(box,preview,layerButton(label,section.title||label,full,"reading-expansion"));
}
function setupIssueLayers(issue){
 const host=$("#issue-navigation");if(!host)return;
 const deck=$("#issue-takeaways");deck.replaceChildren();
 for(const [i,signal] of (issue.signals||[]).entries()){
  const card=make("article","takeaway-card"),front=make("div","takeaway-face"),back=make("div","takeaway-face takeaway-back");back.hidden=true;
  add(front,make("span","eyebrow","0"+(i+1)+" / "+signal.short),uiIcon(["focus","switch","network"][i%3],"takeaway-symbol"),make("h3","",signal.title));
  const bullets=make("ul","takeaway-statements");bullets.append(make("li","",textSentences(signal.text)[0]||signal.text));
  add(back,make("span","eyebrow","KEY STATEMENT"),bullets);
  const turn=btn("Turn card",()=>{const flipped=back.hidden;front.hidden=flipped;back.hidden=!flipped;card.classList.toggle("is-flipped",flipped);turn.setAttribute("aria-pressed",String(flipped));turn.textContent=flipped?"Back to theme":"Turn card";},"flip-toggle");turn.setAttribute("aria-pressed","false");
  const read=btn("Read the discussion",()=>{issueMenu.choose("themes");issueThemeMenu.choose(String(i));issueThemeMenu.nav.scrollIntoView({block:"start"});issueThemeMenu.focusActive();},"quiet-link");
  add(card,front,back,add(make("div","takeaway-actions"),turn,read));deck.append(card);
 }
 const intro=layerDisclosure($(".issue-letter"),"The big picture")||$(".issue-letter");
 layerDisclosure($("#issue-history"),"Publication history");
 const shelf=$(".issue-reading-shelf > details");if(shelf){const summary=shelf.querySelector("summary");summary?.remove();shelf.replaceWith(...shelf.childNodes);}
 let map=$("#issue-map");if(!map){map=make("div","issue-concept-map");map.id="issue-map";$("#issue-takeaways").before(map);}
 map.replaceChildren(make("span","map-center","One edition · "+(issue.signals||[]).length+" connected themes"),make("span","map-caption","A reading map"));
 host.replaceChildren();
 issueMenu=sectionMenu(host,[
  {key:"overview",label:"At a glance",note:"The week's main ideas",nodes:[$("#issue-overview"),intro]},
  {key:"themes",label:"Explore the themes",note:"Connections and evidence",nodes:[$(".issue-signals-section"),...(issue.supplements?.length?[$("#issue-supplements")]:[])]},
  {key:"question",label:"Question & experiment",note:"Something to think through",nodes:[$("#issue-extras")]},
  {key:"sources",label:"Sources",note:"The complete reading list",nodes:[$(".issue-reading-shelf")]},
  {key:"about",label:"Notes & glossary",note:"Terms and context",nodes:[$(".issue-closing"),...((issue.glossary||[]).length?[$("#issue-glossary")]:[]),$(".issue-follow")]}
 ],"issue-section","In this edition");
 let themeHost=$("#issue-theme-navigation");if(!themeHost){themeHost=make("div");themeHost.id="issue-theme-navigation";$("#issue-signals").before(themeHost);}themeHost.replaceChildren();
 const panels=Array.from($("#issue-signals").children);
 if(panels.length)issueThemeMenu=sectionMenu(themeHost,panels.map((node,i)=>({key:String(i),label:issue.signals[i].short,nodes:[node]})),"issue-theme","Choose a theme");
}
function renderIssueGlossary(issue){
 let glossary=$("#issue-glossary");
 if(!glossary){glossary=make("section","issue-glossary");glossary.id="issue-glossary";$(".issue-reading-shelf").before(glossary)}
 glossary.replaceChildren();glossary.hidden=issue.status!=="published"||!issue.glossary?.length;
 if(glossary.hidden)return;
 glossary.setAttribute("aria-label","Plain-language glossary");
 const definitions=make("dl");
 for(const [index,entry] of issue.glossary.entries()){
  const term=make("dt","",entry.term);term.id=issueTermId(entry,index);term.tabIndex=-1;
  add(definitions,term,make("dd","",entry.definition));
 }
 add(glossary,make("h2","","A few useful terms"),definitions);
}
function textSentences(value){
 const text=String(value||"").replace(/\s+/g," ").trim();
 if(!text)return [];
 return typeof Intl!=="undefined"&&Intl.Segmenter?Array.from(new Intl.Segmenter("en",{granularity:"sentence"}).segment(text),x=>x.segment).reduce((parts,segment)=>{if(parts.length&&!/\s$/.test(parts[parts.length-1])&&!/^\s/.test(segment))parts[parts.length-1]+=segment;else parts.push(segment);return parts;},[]).map(segment=>segment.trim()):text.split(/(?<=[.!?])\s+(?=[A-Z“])/);
}
// Work only with text already cleared for the public reader. A stored abstract
// may end mid-word. Never turn an unfinished excerpt into a sentence.
function abstractSentences(value){
 const text=String(value||"").trim().replace(/^abstract\b[\s:.–—-]*/i,"");
 const parts=textSentences(text);
 const tail=parts.at(-1)||"";
 if(!/[.!?][”’"'\])]?$/.test(tail)||/\b(?:e\.g|i\.e|et al|figs?|eq|vol|dr|mr|ms|prof|vs)\.$/i.test(tail))parts.pop();
 return parts;
}
function cardContext(x){
 const d=x.reading?.digest||{},machine=x.reading?.machine_account;
 if(machine?.review_status==="machine_checked_not_independently_reviewed"){
  const text=[machine.research_question,machine.study_design].find(s=>s&&s.length<=430);
  if(text)return {text,label:"From the machine-checked summary"};
 }
 if(d.status==="automatically_condensed_source_text"){
  const sentences=abstractSentences(x.card_abstract||x.abstract_text);
  const excerpt=sentences.slice(0,2).join(" ");
  const text=excerpt.length<=310?excerpt:sentences[0]||"";
  if(text&&text.length<=430)return {text,label:"From the abstract"};
  return null;
 }
 const text=[d.explain,d.idea].find(s=>s&&s!==x.title&&s!==readingHeadline(x)&&s.length<=430);
 return text?{text,label:""}:null;
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
 for(const source of sources)labels.add(readingKind(editionPresentation(source)));
 for(const label of labels)wrap.append(make("span","",label));
 return wrap;
}
function renderIssue(){
 const issue=S.issue||{},published=issue.status==="published";
 const edition=issue.edition_date||"";
 const sourceCount=Number(issue.source_count)||0;
 renderIssueGlossary(issue);
 $("#weekly-kicker").textContent=published?"THE WEEKLY BRIEF / ISSUE "+String(issue.number).padStart(2,"0"):"THE ATTENTION BRIEF";
 $("#weekly-title").textContent=published?issue.headline:"Good questions about AI and attention.";
 $("#weekly-deck").textContent=published?issue.deck:"Browse research and ideas about thinking, distraction, and how we work with AI.";
 $("#weekly-scope").textContent=published?"Week of Monday, "+date(edition):"Browse the research library for the latest findings.";
 $("#issue-edition").textContent=published?"THE ATTENTION BRIEF / ISSUE "+issue.number+" / WEEK OF MONDAY, "+date(edition):"THE ATTENTION BRIEF";
 $("#issue-headline").textContent=published?issue.headline:"Ideas for thinking clearly.";
 $("#issue-deck").textContent=published?issue.deck:"Explore research, commentary, and experiments about AI and attention.";
 $("#issue-letter-text").replaceChildren(issueProse(published?issue.letter:"Start with a question, follow the evidence, and explore the research library.",{},issue));
 const strips=$("#weekly-signal-strip"),main=$("#issue-signals");strips.replaceChildren();main.replaceChildren();
 const signs=published?issue.signals||[]:[];
 signs.forEach((sig,i)=>{
   const tile=make("a","weekly-signal");tile.href="#issue";tile.setAttribute("aria-label","Read signal "+(i+1)+": "+sig.short);
   const mark=uiIcon(["focus","switch","network"][i%3],"weekly-signal-symbol");
   add(tile,mark,make("span","weekly-signal-no",String(i+1).padStart(2,"0")+" / IN THIS ISSUE"),make("h4","",sig.short),make("span","weekly-signal-arrow","Read the connection"));strips.append(tile);
   const panel=make("article","issue-signal"),header=make("div","issue-signal-header");
   add(header,uiIcon(["focus","switch","network"][i%3],"issue-signal-icon"),make("span","issue-signal-no","THREAD "+String(i+1).padStart(2,"0")));
   add(panel,header,make("h3","",sig.title),evidenceTags((issue.sources||[]).filter(source=>(sig.source_ids||[]).includes(source.id))),compactIssueReading(sig,"Evidence, differences & limits",issue),
       make("span","issue-cited-label","READINGS BEHIND THIS SIGNAL"),
       issueRefs(sig.source_ids));
   main.append(panel);
 });
 const supplements=$("#issue-supplements");supplements.replaceChildren();supplements.hidden=!published||!(issue.supplements||[]).length;
 for(const section of published?issue.supplements||[]:[]){
   const panel=make("article","issue-signal");
   add(panel,make("h2","",section.title),compactIssueReading(section,"Read the additional analysis",issue),issueRefs(section.source_ids));
   supplements.append(panel);
 }
 const history=$("#issue-history"),historyBody=$("#issue-history-body");historyBody.replaceChildren();
 const first=issue.first_published_date||String(issue.published_at||"").slice(0,10);
 history.hidden=!published||(!first&&!(issue.edition_history||[]).length);
 if(first)historyBody.append(make("p","","First published "+date(first)+"."));
 if(issue.updated_at)historyBody.append(make("p","","Updated "+date(issue.updated_at)+"."));
 for(const entry of issue.edition_history||[]){
   if(!/^history\/20\d\d-\d\d-\d\d\.html$/.test(entry.url||""))continue;
   const row=make("p");row.append(link("Original version · "+date(entry.original_date),"issues/"+entry.url));
   historyBody.append(row);
 }
 $("#issue-extras").hidden=!published;
 $(".issue-closing").hidden=!published;
 $("#issue-tension-title").textContent=published?issue.tension.title:"";
 $("#issue-tension-text").replaceChildren(compactIssueReading(published?issue.tension:{text:""},"Explore the question",issue));
 const ref=$("#issue-tension-refs");ref.replaceChildren();if(published)issueRefs(issue.tension.source_ids,ref);
 $("#issue-experiment-title").textContent=published?issue.experiment.title:"";
 $("#issue-experiment-text").textContent=published?issue.experiment.text:"";
 $("#issue-experiment-caution").textContent=published?issue.experiment.caution:"";
 $("#issue-closer").textContent=published?issue.closer:"";
 const sourceList=issue.sources||[];
 $("#issue-coverage").textContent=sourceList.length+(sourceList.length===1?" source":" sources")+(issue.scope_kind==="legacy_collection"?" in this historical collection.":issue.publication_window?" · "+date(issue.publication_window.from)+" – "+date(issue.publication_window.to)+" (UTC)":" in this edition.");
 const shelf=$("#issue-sources");shelf.replaceChildren();
 for(const [i,src] of (issue.sources||[]).entries())shelf.append(issueSourceShelfItem(src,i));
 renderEditionCards();
 setupIssueLayers(issue);
}
function issueSourceShelfItem(src,index){
 const item=make("div","issue-shelf-item"),current=editionReading(src),presented=editionPresentation(src);
 item.id="edition-source-"+index;item.tabIndex=-1;
 const original=httpsSourceUrl(src.source_url),publication=httpsSourceUrl(src.url);
 const title=editionReadingHeadline(src),sourceUrl=original||publication;
 const reading=Boolean(current);
 const heading=reading?link(title,"#paper/"+encodeURIComponent(id(current))):
  sourceUrl?link(title,sourceUrl,original?"issue-source-checked-link":"issue-source-publication-link"):make("strong","",title);
 const content=make("div","issue-shelf-content");
 add(content,make("span","card-type",readingKind(presented)),heading,
  make("p","source-meta",[mediaByline(src),src.venue,src.published?date(src.published):"",publicationContext(src)].filter(Boolean).join(" · ")));
 const links=make("div","issue-source-links");
 if(original&&reading)links.append(link("Read original",original,"issue-source-checked-link"));
 if(publication&&reading&&!original)links.append(link("Read original",publication,"issue-source-publication-link"));
 if(src.related_journal_doi&&src.related_journal_doi!==src.source_doi)
  links.append(link("Related journal publication",doiUrl(src.related_journal_doi),"issue-source-publication-link"));
 if(links.children.length)content.append(links);
 return add(item,make("span","issue-shelf-number",String(index+1).padStart(2,"0")),content);
}

function renderEditionCards(){
 const root=$("#feature-grid");root.replaceChildren();
 // All text and source versions come from the same frozen edition as the hero.
 for(const [i,src] of (S.issue.sources||[]).slice(0,3).entries()){
  const c=make("article","feature-card"+(i===0?" primary":""));
  add(c,make("span","feature-number",String(i+1).padStart(2,"0")),
      editorialMedia({editorial_art:editionReading(src)?.editorial_art},"feature"),
      make("p","feature-idea-label",readingKind(editionPresentation(src))),
      make("h3","feature-idea",editionReadingHeadline(src)),
      make("p","source-meta",[src.venue,src.published?date(src.published):"",publicationContext(src)].filter(Boolean).join(" · ")),
      link("View source","#issue?source="+encodeURIComponent(src.id),"feature-go"));
  root.append(c);
 }
}
function home(){
 const run=S.week.run||{},research=researchRecords();
 $("#issue-label").textContent=run.date?"Library updated "+date(run.date):"Reading library";
 $("#issue-meta").textContent=S.records.length+" readings · "+research.length+" research sources";
 renderEditionCards();
 // Provider diagnostics belong in repository workflow logs, never in public content.
 renderEditorial();
 topicBars("#topic-bars",research);donut(research);
 const grid=$("#lens-grid");if(grid){grid.replaceChildren();themes.forEach((t,i)=>{const a=link("",libraryHash(t[0]),"lens");a.setAttribute("aria-label","Explore "+t[0]);a.setAttribute("data-theme",String(i));add(a,make("span","lens-mark",t[3]),make("h3","",t[1]),make("p","",t[2]),make("span","",S.records.filter(x=>x.lane===t[0]).length+" records →"));grid.append(a)});}
 const arr=$("#arrivals-body");arr.replaceChildren();
 const sorted=S.records.filter(x=>depth(x)!=="citation_only").slice().sort((a,b)=>(b.first_seen||"").localeCompare(a.first_seen||"")||(b.published||"").localeCompare(a.published||"")).slice(0,7);
 for(const x of sorted){let tr=make("tr"),name=make("td"),go=make("td","align-right");name.append(btn(shortIdea(x),()=>goto("paper",id(x))));go.append(btn("Read",()=>goto("paper",id(x))));add(tr,make("td","mono-date",date(x.first_seen)),name,make("td","",x.lane||"Unassigned"),make("td","coverage-tag",readingKind(x)),go);arr.append(tr)}
}

function renderEditorial(){
 const list=S.records.filter(x=>matchesSourceType(x,"nonacademic"));
 const sorted=list.filter(x=>depth(x)!=="citation_only").sort((a,b)=>(b.first_seen||"").localeCompare(a.first_seen||"")||(b.published||"").localeCompare(a.published||""));
 const featured=[];for(const test of [x=>sourceGenre(x)==="reporting",x=>matchesSourceType(x,"opinion"),x=>matchesSourceType(x,"analysis"),x=>sourceGenre(x)==="guide"]){const next=sorted.find(x=>!featured.includes(x)&&test(x));if(next)featured.push(next)};
 const root=$("#editorial-grid");root.replaceChildren();
 if(!featured.length){root.append(make("div","empty-state","No perspectives are available yet."));return}
 for(const x of featured){
  const card=make("article","editorial-card"),label=make("span","editorial-category",readingKind(x));
  const articleTitle=make("h3");articleTitle.append(btn(shortIdea(x),()=>goto("paper",id(x))));
  const foot=make("div","editorial-foot");
  add(foot,make("span","",x.venue||"Original source"),btn("Explore",()=>goto("paper",id(x)),"editorial-cta"));
  add(card,editorialMedia(x,"editorial"),label,articleTitle,foot);root.append(card)
 }
}

function renderPerspectives(){
 const all=S.records.filter(x=>depth(x)!=="citation_only");
 const lists=[
  ["#perspectives-news",all.filter(x=>sourceGenre(x)==="reporting")],
  ["#perspectives-essays",all.filter(x=>sourceFamily(x)==="media"&&sourceGenre(x)!=="reporting")],
  ["#perspectives-products",all.filter(x=>sourceFamily(x)==="product")]
 ];
 for(const [selector,records] of lists){
  const container=$(selector);container.replaceChildren();
  if(!records.length){container.append(make("div","empty-state","No indexed sources in this group yet."));continue}
  records.sort((a,b)=>(b.published||"").localeCompare(a.published||""));
  for(const x of records){
    const item=make("article","perspective-item");
    const icon=uiIcon(x.source==="Official product documentation"?"book":x.format==="Policy analysis"?"shield":"external","perspective-glyph");
    const label=make("div","perspective-type",readingKind(x));
    const title=make("h3");title.append(btn(shortIdea(x),()=>goto("paper",id(x))));
    const bottom=make("div","perspective-bottom");
    add(bottom,make("span","",x.venue||"Original source"),btn("Read summary",()=>goto("paper",id(x)),"editorial-cta"));
    add(item,editorialMedia(x,"perspective"),icon,label,title,bottom);container.append(item);
  }
 }
}
function renderBacklog(){
 const root=$("#backlog-coverage");
 root.replaceChildren();
 const papers=S.records.filter(x=>sourceFamily(x)==="research");
 const scholarly=papers.length;
 const done=papers.filter(x=>x.analysis?.fulltext_url&&!x.analysis.original_paraphrases_only).length;
 const pct=scholarly?Math.round(100*done/scholarly):0;
 const top=make("div","coverage-status-row");
 add(top,make("strong","",done+" of "+scholarly+" scholarly papers"),make("span","",pct+"% with extracted full-text sections"));
 const rail=make("div","coverage-status-rail"),bar=make("span","coverage-status-bar");
 bar.style.width=pct+"%";rail.append(bar);
 add(root,top,rail);
}
const libraryPage={signature:"",number:0};
function showLibrary(requestedPage){
 const q=$("#search").value.trim().toLowerCase(),t=$("#topic-filter").value,d=$("#depth-filter").value,k=$("#type-filter").value,scope=$("#scope-filter").value,order=$("#library-sort")?.value||"added";
 const xs=S.records.filter(x=>matchesSearch(x,q)&&(!t||(x.lane||"Unassigned")===t)&&matchesSourceType(x,k)&&(
   scope==="all"||(scope==="core"&&x.source_group==="AI-specific")||
   (scope==="adjacent"&&x.source_group==="Adjacent digital-attention evidence")||
   (scope==="historical"&&/^(Earlier|Historical)/.test(x.source_group||""))
  )&&(d!=="full_text"||depth(x)==="full_text")).sort((a,b)=>{const field=order==="published"?"published":"first_seen";return (b[field]||"").localeCompare(a[field]||"")||(b.published||"").localeCompare(a.published||"")||rank(b)-rank(a)});
 $("#library-count").textContent=xs.length+" matching sources · "+S.records.length+" in the complete archive";
 const context=$("#library-context");
 if(context){
  const scopeNames={core:"AI-specific sources",adjacent:"Digital attention",historical:"Earlier foundations",all:"All sources"};
  context.textContent=[scopeNames[scope]||"All sources",t,d==="full_text"?"Full-text material":"",k?$("#type-filter").selectedOptions[0]?.textContent:""].filter(Boolean).join(" · ");
  $$("[data-library-theme]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.libraryTheme===t)));
 }

 const box=$("#library-results");box.replaceChildren();
 const pager=$("#library-pagination"),size=pager?Number($("#library-page-size").value)||12:Math.max(1,xs.length),signature=[q,t,d,k,scope,order,size].join("|");
 if(libraryPage.signature!==signature){libraryPage.signature=signature;libraryPage.number=0;}
 const pages=Math.max(1,Math.ceil(xs.length/size));libraryPage.number=Math.min(typeof requestedPage==="number"?requestedPage:libraryPage.number,pages-1);
 if(pager){pager.hidden=!xs.length;$("#library-page-status").textContent="Page "+(libraryPage.number+1)+" of "+pages+" · "+(xs.length?libraryPage.number*size+1:0)+"–"+Math.min(xs.length,(libraryPage.number+1)*size)+" of "+xs.length;
  $("#library-previous").disabled=libraryPage.number===0;$("#library-next").disabled=libraryPage.number>=pages-1;}
 if(!xs.length){box.append(make("div","empty-state","No source-backed items match those filters. Try a broader search."));return}
 for(const x of xs.slice(libraryPage.number*size,(libraryPage.number+1)*size)){
  const c=make("article","library-card library-story"),body=make("div","library-story-body"),h=make("h3"),foot=make("div","card-foot");
  const image=editorialMedia(x,"card");
  if(image){
  image.onclick=()=>goto("paper",id(x));
  image.setAttribute("role","button");
  image.setAttribute("aria-label","Read: "+shortIdea(x));
  image.tabIndex=0;
  image.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();goto("paper",id(x));}});
  }else c.className+=" library-story-no-art";
  h.append(btn(shortIdea(x),()=>goto("paper",id(x))));
  const attribution=sourceFamily(x)==="media"?mediaByline(x):"";
  const metadata=[attribution,x.venue,x.published?date(x.published):"",publicationContext(x)].filter(Boolean);
  if(metadata.length)foot.append(make("span","card-source-meta",metadata.join(" · ")));
  if(/^(Earlier|Historical)/.test(x.source_group||""))foot.append(make("span","", "Earlier foundation"));
  add(body,make("span","card-type",readingKind(x)),h);
  const preview=cardContext(x);
  if(preview){
   const summary=make("div","library-summary");
   if(preview.label)summary.append(make("small","",preview.label));
   summary.append(make("p","",preview.text));body.append(summary);
  }
  body.append(foot);
  const colorIndex=themes.findIndex(theme=>theme[0]===x.lane);
  if(colorIndex>=0)c.setAttribute("data-theme",String(colorIndex));
  add(c,image,body);box.append(c);
 }
}
function showAtlas(){
 const research=researchRecords(),cc=counts(research),n=research.length,stat=$("#atlas-stats");stat.replaceChildren();
 for(const [label,value] of [["Research sources",n],["Abstract readings",cc.abstract],["Full-text material",cc.full_text],["Research reviews",research.filter(x=>sourceGenre(x)==="review").length]]){let c=make("div","atlas-stat");add(c,make("strong","",value),make("span","",label));stat.append(c)}
 topicBars("#atlas-topic-bars",research);
 const years={};for(let y=2023;y<=new Date().getFullYear();y++)years[String(y)]=0;
 research.forEach(x=>{const y=(x.published||"").slice(0,4);if(x.source_group==="AI-specific"&&Object.prototype.hasOwnProperty.call(years,y))years[y]++});
 const foundation=research.filter(x=>/^(Earlier|Historical)/.test(x.source_group||"")).length;
 $("#year-context").textContent="AI-specific research published in 2023–"+new Date().getFullYear()+". "+foundation+" earlier research "+(foundation===1?"source is":"sources are")+" available in the library.";
 const values=Object.entries(years),max=Math.max(1,...values.map(x=>x[1])),chart=$("#year-chart");chart.replaceChildren();
 for(const [y,n] of values){let row=make("div","year-row"),track=make("div","year-track"),bar=make("span","year-bar");bar.style.width=(n?Math.max(2,100*n/max):0)+"%";bar.title=n+" AI-specific records from "+y;track.append(bar);add(row,make("span","year-label",y),track,make("span","year-value",n));chart.append(row)}
 const coverage=$("#atlas-depth");coverage.replaceChildren();for(const d of depths){const n=cc[d[0]],p=n/Math.max(1,research.length)*100,c=make("div","coverage-row"),top=make("div","coverage-top"),track=make("div","coverage-track"),fill=make("span","coverage-fill");fill.style.background=d[2];fill.style.width=p+"%";add(top,make("strong","",d[1]),make("span","",n+" · "+Math.round(p)+"%"));track.append(fill);add(c,top,track);coverage.append(c)}
 const table=$("#matrix-table"),thead=make("thead"),r=make("tr");add(r,make("th","","Theme"),...depths.map(d=>make("th","",d[1])));thead.append(r);
 const body=make("tbody");for(const {label} of collectionTopics(research)){const row=make("tr");row.append(make("th","",label));row.firstElementChild.scope="row";for(const d of depths)row.append(make("td","count-cell",research.filter(x=>(x.lane||"Unassigned")===label&&depth(x)===d[0]).length));body.append(row)}table.replaceChildren(thead,body)
}
function section(title,text,origin){const s=make("section","reading-section");add(s,make("p","eyebrow",title),make("h3","",title==="HOW IT WAS STUDIED"?"Method & data":title==="WHAT THE PAPER REPORTS"?"Findings":title==="LIMITATIONS"?"Limitations":title==="AUTHOR INTERPRETATION (DISCUSSION)"?"Authors’ interpretation":"Overview"),make("p","",text));if(origin)s.append(make("div","section-source",origin));return s}
function paperFact(k,v){return add(make("div","paper-fact"),make("span","",k),make("span","",v))}
function processedIdea(x){return readingHeadline(x)}
function comparisonArtwork(title,columns,caption){
 const w=make("section","article-concept-art article-data-visual");
 add(w,make("p","eyebrow","Study design"),make("h3","figure-insight-title",title));
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
 add(figure,make("p","eyebrow","Research summary"),
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

function reviewedEvidenceArtwork(x){
 const spec=x.visual||{},reading=x.reading||{},source=spec.source||{};
 if(spec.kind!=="reviewed_comparison"||!reading.original_summary||
    spec.reading_id!==reading.original_summary_id||spec.doi!==x.doi||
    source.url!==reading.source_url||source.version!==reading.source_version||
    source.sha256!==reading.source_sha256||!httpsSourceUrl(source.url)||
    !Array.isArray(spec.headers)||!Array.isArray(spec.rows)||
    spec.headers.length<2||spec.headers.length>4||spec.rows.length>6||
    !spec.rows.every(row=>Array.isArray(row)&&row.length===spec.headers.length))return null;
 const figure=make("figure","article-concept-art article-data-visual evidence-graphic reviewed-evidence");
 add(figure,make("p","eyebrow","Source table, simplified"),make("h3","figure-insight-title",spec.title));
 const table=make("table","matrix-table reviewed-comparison-table");
 table.setAttribute("aria-label",spec.description);
 const thead=make("thead",""),heading=make("tr","");
 for(const label of spec.headers){const th=make("th","",label);th.setAttribute("scope","col");heading.append(th);}
 thead.append(heading);table.append(thead);
 const tbody=make("tbody","");
 for(const row of spec.rows){
  const tr=make("tr","");
  row.forEach((value,index)=>{const cell=make(index?"td":"th","",value);if(!index)cell.setAttribute("scope","row");tr.append(cell);});
  tbody.append(tr);
 }
 table.append(tbody);
 const caption=make("figcaption","concept-note",spec.caption);
 caption.append(link(source.attribution+" · "+source.locator,source.url,"rv-secondary-link"));
 const tableScroll=make("div","reviewed-table-scroll");
 tableScroll.setAttribute("role","region");
 tableScroll.setAttribute("aria-label",spec.title+" comparison table");
 tableScroll.setAttribute("tabindex","0");
 tableScroll.append(table);
 add(figure,tableScroll,caption);return figure;
}
function automaticEvidenceArtwork(x){
 const spec=x.visual||{};
 if(x.kind!=="scholarly"||!["evidence_snapshot","research_design"].includes(spec.kind))return null;
 const blocks=Array.isArray(spec.blocks)?spec.blocks.filter(b=>b&&typeof b.label==="string"&&typeof b.text==="string"&&b.text.length<=600).slice(0,3):[];
 if(!blocks.length)return null;
 const figure=make("figure","article-concept-art article-data-visual automatic-evidence");
 figure.setAttribute("aria-label","Study details");
 const board=make("div","auto-evidence-board");
 const sources=blocks.map(block=>{
  const basis=block.source||(block.label==="Reported finding"?spec.finding_source:spec.basis);
  return ({abstract:"Source: abstract",editorial:"Source: editorial note",full_text:"Source: full text"})[basis]||"";
 });
 const shared=sources.every(source=>source===sources[0]);
 blocks.forEach((block,i)=>{
  const item=make("div","auto-evidence-item");
  add(item,make("strong","auto-evidence-label",block.label),make("p","auto-evidence-text",block.text));
  if(!shared&&sources[i])item.append(make("small","auto-evidence-source",sources[i]));
  if(block.text.length>240)item.className+=" auto-evidence-wide";
  board.append(item);
 });
 figure.append(board);
 if(shared&&sources[0])figure.append(make("figcaption","auto-evidence-source",sources[0]));
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
  add(w,make("p","eyebrow","Three learner profiles"),make("h3","figure-insight-title","Not all AI reliance looks alike"));
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
  add(w,make("p","eyebrow","Qualitative analysis"),make("h3","figure-insight-title","From initial codes to broader categories"));
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
 const version=String(reading.source_version||"").trim();
 const labels={publisher_article:"Published article",publisher_version_of_record:"Published article",
  "Publisher version of record":"Published article",publishedVersion:"Published version",
  author_posted_manuscript:"Author manuscript",published_institutional_report:"Institutional report"};
 return Object.hasOwn(labels,version)?labels[version]:version.replace(/^arxiv_preprint_v(\d+)$/i,"arXiv preprint v$1");
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
function readingProse(content,className=""){
 const prose=make("div","rv-prose "+className);
 for(const paragraph of readingParagraphs(content))prose.append(make("p","",paragraph));
 return prose;
}
function sourceFields(x){
 const r=x.reading||{},a=x.analysis||{};
 // Journalism and journal editorials must never inherit study passages.
 if(sourceFamily(x)!=="research")return [];
 // Do not mistake the shortened reading-card excerpts for all indexed text.
 // Original summaries always retain the separate, potentially older index.
 const original=originalSummary(x),hasSections=Boolean(a.fulltext_url);
 return [
  ["Methods",a.methods||(!original?r.methods:"") ,hasSections?"Methods section":"Abstract selection"],
  ["Results",a.results||(!original?r.findings:"") ,hasSections?"Results section":"Abstract selection"],
  ["Discussion",a.discussion||(!original?r.interpretation:"") ,hasSections?"Discussion section":"Abstract selection"],
  ["Limitations",a.limitations||(!original?r.limitations:"") ,hasSections?"Limitations section":"Abstract selection"],
  ["Abstract",x.abstract_text,x.abstract_source||"Source abstract"]
 ];
}
function sourceReader(x){
 const fields=sourceFields(x),available=fields.filter(([,content])=>content),r=x.reading||{},a=x.analysis||{},original=originalSummary(x);
 if(!available.length)return null;
 const drawer=make("section","rv-drawer rv-source-excerpts");
 drawer.append(make("h3","",a.original_paraphrases_only?"Source notes and abstract":"Source excerpts"));
 const panel=make("div","rv-reader-panel"),intro=make("div","rv-indexed-provenance");
 if(a.original_paraphrases_only)intro.append(make("p","","These notes paraphrase the publication."));
 else if(original&&a.fulltext_url&&a.fulltext_url!==r.source_url)intro.append(make("p","","These excerpts may come from a different version of the paper."));
 const url=httpsSourceUrl(a.fulltext_url);
 if(url)intro.append(link("Open full text",url,"rv-secondary-link"));
 if(intro.children.length)panel.append(intro);
 const contents=make("nav","rv-reader-contents");contents.setAttribute("aria-label","Source sections");
 const drawerBody=make("div","rv-drawer-body"),sections=[];
 for(const [label,content,basis] of available){
  const section=make("section","rv-excerpt rv-source-section");
  section.id="article-source-passage-"+(sections.length+1);
  const count=String(content).trim().split(/\s+/).length;
  add(section,add(make("h4","rv-source-section-title"),make("span","",label),make("small","",count+" words")),
   make("p","rv-section-basis",basis),readingProse(content));
  section.hidden=sections.length>0;
  const jump=btn(label,()=>{sections.forEach(s=>s.hidden=s!==section);Array.from(contents.children).forEach(b=>b.setAttribute("aria-pressed",String(b===jump)));},"rv-reader-jump");
  jump.setAttribute("aria-pressed",String(sections.length===0));
  jump.setAttribute("aria-controls",section.id);
  contents.append(jump);sections.push(section);drawerBody.append(section);
 }
 const controls=make("div","rv-reader-controls");
 add(controls,btn("Read all source sections",()=>{sections.forEach(s=>s.hidden=false);Array.from(contents.children).forEach(b=>b.setAttribute("aria-pressed","false"));},"rv-reader-control"),
  btn("One section at a time",()=>{sections.forEach((s,i)=>s.hidden=i!==0);Array.from(contents.children).forEach((b,i)=>b.setAttribute("aria-pressed",String(i===0)));},"rv-reader-control"));
 add(panel,contents,controls,drawerBody);drawer.append(panel);return drawer;
}
function articleSections(main,layout,body,side,analysis,evidence,sections){
 const overview=make("section","rv-panel rv-panel-overview");
 overview.id="article-overview";overview.setAttribute("aria-label","Reading overview");
 for(const child of Array.from(body.children))overview.append(child);
 analysis.className+=" rv-panel";analysis.id="article-analysis";analysis.setAttribute("aria-label",sections.label);
 evidence.className+=" rv-panel";evidence.id="article-evidence";evidence.setAttribute("aria-label","Source excerpts");
 side.className+=" rv-panel";side.id="article-source";side.setAttribute("aria-label","Source and related readings");
 body.append(overview,analysis,evidence);
 const groups=[{value:"overview",label:"Overview",description:sections.overview,node:overview},
  ...(analysis.children.length?[{value:"analysis",label:sections.label,description:sections.context,node:analysis}]:[]),
  ...(evidence.children.length?[{value:"evidence",label:"Source excerpts",description:"Read passages from the paper",node:evidence}]:[]),
  {value:"source",label:"Source",description:"Publication and related reads",node:side}];
 const workspace=make("div","rv-reading-workspace"),controls=make("nav","rv-section-controls");
 controls.id="article-section";controls.setAttribute("aria-label","In this reading");
 const heading=make("p","rv-section-heading","In this reading"),position=make("p","rv-section-position");
 position.setAttribute("role","status");position.setAttribute("aria-live","polite");position.setAttribute("aria-atomic","true");
 const buttons=make("div","rv-section-tabs"),readAll=btn("Read all",()=>choose("all",true),"rv-read-all");
 function choose(value,fromControl=false){
  if(value!=="all"&&!groups.some(group=>group.value===value))value="overview";
  for(const group of groups)group.node.hidden=value!=="all"&&group.value!==value;
  analysis.hidden=!analysis.children.length||value!=="all"&&value!=="analysis";
  evidence.hidden=!evidence.children.length||value!=="all"&&value!=="evidence";
  body.hidden=value==="source";
  controls.dataset.activeSection=value;main.setAttribute("data-reading-view",value);
  const index=groups.findIndex(group=>group.value===value);
  position.textContent=value==="all"?"All "+groups.length+" sections":String(index+1).padStart(2,"0")+" / "+String(groups.length).padStart(2,"0")+" · "+groups[index].label;
  Array.from(buttons.children).forEach(button=>button.setAttribute("aria-pressed",String(button.getAttribute("data-reading-view")===value)));
  readAll.setAttribute("aria-pressed",String(value==="all"));
  if(fromControl&&typeof layout.getBoundingClientRect==="function"&&layout.getBoundingClientRect().top<110)layout.scrollIntoView({block:"start",behavior:"instant"});
 }
 for(const [index,group] of groups.entries()){
  const button=btn("",()=>choose(group.value,true),"rv-section-tab"),number=make("span","rv-section-number",String(index+1).padStart(2,"0"));
  number.setAttribute("aria-hidden","true");
  const label=make("span","rv-section-label",group.label),description=make("span","rv-section-description",group.description);
  add(button,number,add(make("span","rv-section-copy"),label,description));
  button.setAttribute("data-reading-view",group.value);button.setAttribute("aria-controls",group.node.id);buttons.append(button);
 }
 add(controls,heading,position,buttons,readAll);add(workspace,controls,layout);main.append(workspace);choose("overview");
}

function showPaper(x){
 const root=$("#paper-content");
 root.replaceChildren();
 if(!x){root.append(make("div","empty-state","We couldn’t find a reading for this link."));return;}
 if(x.source_quality?.decision==="awaiting_full_article_reading"){
  const page=make("article","rv-article rv-awaiting-reading"),head=make("header","rv-head");
  const display=x.display_headline?readingHeadline(x):"About this source";
  add(head,make("p","eyebrow","Source link"),make("h1","rv-headline",display));
  if(x.title&&x.title.trim()!==display)head.append(make("p","rv-source-title",x.title.trim()));
  if(x.venue)head.append(make("p","rv-source-meta",x.venue));
  head.append(make("p","rv-deck","A summary of this article is not yet available."));
  if(httpsSourceUrl(x.url))head.append(link("Read the original article",x.url,"rv-secondary-link"));
  add(page,btn("All readings",()=>goto("library"),"rv-back"),head);root.append(page);return;
 }
 const r=x.reading||{},d=r.digest||{},deep=d.longform||{},original=originalSummary(x);
 const family=sourceFamily(x),genre=sourceGenre(x),kind=readingKind(x),research=family==="research";
 const conceptual=genre==="conceptual",proposal=genre==="proposal",review=genre==="review";
 const journalEditorial=genre==="editorial",reporting=genre==="reporting",product=genre==="guide";
 const edited=d.status==="editorially_written_from_indexed_sections";
 // These four fields come from the checked article. Other full-text fields
 // can be licensed extracts, so depth alone cannot identify editorial prose.
 const reviewedAccount=research&&!original&&!proposal&&r.level==="full_text"&&
  d.editorial_basis==="publisher_full_article_paraphrased"&&r.methods&&r.limitations&&
  (conceptual?r.interpretation:r.findings);
 const machine=research&&!original&&!reviewedAccount&&r.machine_account?.review_status==="machine_checked_not_independently_reviewed"&&
  httpsSourceUrl(r.machine_account.source_url)?r.machine_account:null;
 const abstract=research&&!original&&!machine&&d.status==="automatically_condensed_source_text"?
  abstractSentences(x.abstract_text).join(" "):"";
 const abstractPreview=d.status==="journal_abstract_preview"||(journalEditorial&&!deep.thesis&&Boolean(x.abstract_text));
 // Backward compatibility for previously cached article payloads that mixed
 // an intake notice into the public digest. Current exports supply clean text.
 function limitText(value,field){
  if(/^Limited reading(?:[.]| of current publisher HTML[.])/.test(value||""))return x.original_reading?.summary?.[field]||"";
  return value||"";
 }
 const main=make("article","rv-article"),head=make("header","rv-head"),intro=make("div","rv-intro-copy");
 main.setAttribute("data-source-family",family);
 const headline=readingHeadline(x);
 const metadata=make("div","rv-meta");
 metadata.append(make("span","rv-dot",kind));
 if(x.lane&&x.lane.toLowerCase()!==kind.toLowerCase())add(metadata,make("span","rv-meta-separator","·"),make("span","",x.lane));
 add(head,metadata,make("h1","rv-headline",headline));
 const used=new Set([headline,x.title].filter(Boolean).map(t=>t.trim().toLowerCase()));
 function fresh(value){
  const text=String(value||"").trim(),key=text.toLowerCase();
  if(!text||used.has(key))return "";
  used.add(key);return text;
 }
 const leadText=abstractPreview||abstract||machine?"":research?((original||edited||d.status==="conceptual_framework")?d.idea:d.explain):
  (deep.thesis||(x.kind==="scholarly"?"":d.explain)||d.idea);
 const lead=fresh(leadText);
 const leadParagraph=!lead?null:d.explain_source==="abstract_excerpt"
  ?add(make("div","rv-summary-idea"),make("span","rv-source-meta","From the abstract"),make("p","",lead))
  :make("p","rv-summary-idea",lead);
 if(leadParagraph)intro.append(leadParagraph);
 if(research&&!abstract&&!machine&&(original||edited||conceptual)&&
    !(reviewedAccount&&[r.methods,r.findings,r.interpretation,r.limitations].includes(d.explain))){
  const overview=fresh(d.explain);
  if(overview)intro.append(layerButton("More context","Overview",readingProse(overview),"rv-overview"));
 }
 const author=research?"":r.attributed_to||deep.attributed_to||"";
 const byline=[author,x.venue,date(x.published)].filter((v,i,a)=>v&&v!=="Undated"&&a.indexOf(v)===i);
 const sourceRow=make("div","rv-source-row");
 if(byline.length)sourceRow.append(make("span","",byline.join(" · ")));
 const basis=abstract?"Abstract excerpt":machine?"Machine-checked full document":reviewedAccount?"Based on the full article":research?(original&&r.source_version?checkedSourceLabel(r):readingBasisName(x)):"";
 if(basis)sourceRow.append(make("span","",basis));
 const machineMedia=!research&&deep.source_depth==="machine_read_full_article"&&deep.review_status==="machine_checked_not_independently_reviewed";
 const primaryUrl=httpsSourceUrl(original?r.source_url:machine?machine.source_url:machineMedia?deep.source_url:x.url);
 if(primaryUrl)sourceRow.append(link("Read original",primaryUrl,"rv-byline-link"));
 intro.append(sourceRow);
 if(!abstractPreview&&!abstract)intro.append(make("p","rv-ai-notice",machine||machineMedia?
  "AI-generated summary. Its claims were checked against the retrieved document by a model. No independent review is recorded.":
  "AI-generated summary. AI can make mistakes."));
 if(editorialArt(x)){const lede=make("div","rv-lede-layout");add(lede,intro,editorialMedia(x,"reading"));head.append(lede);}else head.append(intro);
 add(main,btn("All readings",()=>goto("library"),"rv-back"),head);
 const layout=make("div","rv-layout"),story=make("div","rv-story"),side=make("aside","rv-sidebar");
 const body=make("section","rv-content"),analysis=make("section","rv-analysis"),evidencePanel=make("section","rv-evidence-panel");
 const sections=research?{label:"Discussion",overview:conceptual?"Proposal and boundaries":proposal?"Proposed design":review?"Review findings and scope":"Findings and study design",context:"The authors’ explanation"}:
  {label:"Context",overview:product?"Features and use":reporting?"Events and perspectives":"The argument and its examples",context:product?"Trade-offs and limits":"Background and points of tension"};
 const heading=abstract?"From the abstract":abstractPreview?"From the published abstract":proposal?"What the researchers propose":journalEditorial?"The editorial’s argument":conceptual?"What the paper proposes":review?"What the review found":research?(d.finding?"What the study found":"Inside the study"):product?"How it works":reporting?"What happened":"The argument";
 body.append(add(make("div","rv-section-head"),make("h2","rv-section-title",heading)));
 function paragraph(parent,label,value,cls="rv-longform-part"){
  const text=fresh(value);if(!text)return;
  const section=make("section",cls);
  if(label)section.append(make("h3","",label));
  section.append(readingProse(text));parent.append(section);
 }
 if(research){
  const graphic=proposal||machine?null:reviewedEvidenceArtwork(x)||(original?null:conceptArtwork(x));
  const art=(conceptual||reviewedAccount||abstract||machine)&&graphic?.className.includes("automatic-evidence")?null:graphic;
  const auto=Boolean(art?.className.includes("automatic-evidence"));
  if(abstract){
   body.append(readingProse(abstract,"rv-abstract-account"));
  }else if(machine){
   const account=make("div","rv-longform rv-machine-account");
   paragraph(account,"Research question",machine.research_question);
   paragraph(account,proposal?"Proposed design":review?"What the authors reviewed":"Study design",machine.study_design);
   if(!conceptual&&!proposal)paragraph(account,review?"What the studies showed":"Reported results",machine.reported_results);
   paragraph(account,conceptual||proposal?"The authors’ proposal":"The authors’ interpretation",machine.authors_interpretation);
   paragraph(account,"Study limitations",machine.limitations);
   paragraph(analysis,"Evidence and context",machine.critical_context);
   paragraph(analysis,"Open question",machine.open_question);
   body.append(account);
  }else if(reviewedAccount){
   const account=make("div","rv-longform rv-study-account");
   paragraph(account,conceptual?"How the authors developed the framework":review?"What the authors reviewed":"How the study worked",r.methods);
   if(!conceptual)paragraph(account,review?"What the studies showed":"What the researchers observed",r.findings);
   paragraph(account,conceptual?"What the framework proposes":"How the authors interpret it",r.interpretation);
   paragraph(account,conceptual?"What still needs testing":review?"Limits of the evidence":"What the design leaves open",r.limitations);
   body.append(account);
  }else if(!auto){
   const result=proposal?"":conceptual?(d.interpretation||d.explain||d.idea):d.finding;
   const claim=fresh(result);
   if(claim)body.append(add(make("div","rv-claim"),readingBullets(claim)));
  }
  if(art)body.append(add(make("div","rv-artwork"),art));
  const context=make("div","rv-context-grid");
  if(!auto&&!reviewedAccount&&!abstract&&!machine){
   paragraph(context,proposal?"Proposed design":conceptual?"How the authors developed it":review?"What the authors reviewed":"How it was studied",d.approach,"rv-context");
   paragraph(context,proposal||conceptual?"What still needs testing":"Study limitations",limitText(d.limitation,"limitation"),"rv-context");
   if(context.children.length)body.append(context);
  }
  // The overview already carries the concrete result. A Discussion chapter is
  // for an identifiable explanation or proposal from the authors.
  if(!reviewedAccount&&!abstract&&!machine&&(conceptual||/\b(?:authors?|researchers?)\s+(?:also\s+)?(?:suggest|propos|argu|interpret|hypothes|speculat|attribut|explain|recommend)/i.test(d.interpretation||""))){
   paragraph(analysis,conceptual?"Applying the framework":"The authors’ explanation",d.interpretation,"rv-take");
  }
  if(!original&&conceptual){
   for(const phase of x.framework_notes?.stages||[]){
    const cutAt=phase.indexOf(":");paragraph(analysis,cutAt>0?phase.slice(0,cutAt):"",cutAt>0?phase.slice(cutAt+1):phase);
   }
  }
  const reader=sourceReader(x);if(reader)evidencePanel.append(reader);
 }else{
  const article=make("div","rv-longform");
  if(abstractPreview){
   const abstract=String(x.abstract_text||"").trim();
   if(abstract)article.append(compactReading(abstract,"Read the full abstract"));
  }else if(journalEditorial){
   paragraph(article,"",deep.reasoning);
   paragraph(article,"In the collection",deep.examples);
  }else{
   paragraph(article,"",deep.reasoning);
   paragraph(article,product?"In use":reporting?"Details from the story":"An example",deep.examples);
   paragraph(analysis,product?"Trade-offs":reporting?"An open issue":"A point of tension",deep.tension);
   paragraph(article,product?"Scope of the guidance":reporting?"Scope of the reporting":"Scope of the argument",limitText(deep.qualification,"qualification"));
   if(!article.children.length&&!analysis.children.length){
    if(x.kind==="scholarly"&&x.abstract_text)paragraph(article,"From the published abstract",x.abstract_text);
    else paragraph(article,"",d.explain||r.overview);
   }
  }
  if(article.children.length)body.append(article);
  if(!article.children.length&&analysis.children.length){for(const part of Array.from(analysis.children))article.append(part);body.append(article);}

 }
 // A reading with only a research question should still open on meaningful
 // content. Put its existing lead in the overview instead of repeating it.
 if(body.children.length===1){
  if(leadParagraph)body.append(leadParagraph);
  else{
   const rawAbstract=String(x.abstract_text||"").replace(/^abstract\b[:.\s]*/i,"").trim();
   const complete=textSentences(rawAbstract).filter(line=>/[.!?][”"’)]?$/.test(line));
   if(complete.length)paragraph(body,"From the abstract",complete.slice(0,2).join(" "));
   else if(primaryUrl)body.append(link("Read the original publication",primaryUrl,"rv-secondary-link"));
  }
 }
 story.append(body);
 const cite=make("section","rv-source");
 add(cite,make("h2","","Original publication"),make("h3","rv-source-title",String(x.title||"").trim()));
 if(x.authors?.length)cite.append(make("p","rv-source-authors",x.authors.join(", ")));
 if(byline.length)cite.append(make("p","rv-source-meta",byline.join(" · ")));
 if(basis)cite.append(make("p","rv-source-version",basis));
 if(primaryUrl)cite.append(link("Read the source",primaryUrl,"rv-primary-link"));
 if(original&&r.related_journal_doi&&r.related_journal_doi!==r.source_doi)
  cite.append(link("Related journal publication",doiUrl(r.related_journal_doi),"rv-secondary-link"));
 if(!original&&httpsSourceUrl(x.analysis?.fulltext_url)&&x.analysis.fulltext_url!==primaryUrl)
  cite.append(link("Read accessible full text",x.analysis.fulltext_url,"rv-secondary-link"));
 if(!original&&httpsSourceUrl(x.source_review?.source_url)&&x.source_review.source_url!==primaryUrl)
  cite.append(link("Read the republication",x.source_review.source_url,"rv-secondary-link"));
 side.append(cite);
 if(research&&!original&&x.analysis?.figures?.length){
  const figureSection=make("section","rv-figures");
  figureSection.append(make("h3","","Original paper figures ("+x.analysis.figures.length+")"));
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
 const primary=x.companion_to&&S.records.find(row=>id(row)===x.companion_to);
 if(primary){
  const section=make("section","rv-related rv-paired-publication");
  add(section,make("h2","","Research behind this story"),link(readingHeadline(primary),readingPath(primary),"rv-related-item"));
  side.append(section);
 }
 const companions=S.companions.filter(row=>row.companion_to===id(x));
 if(companions.length){
  const coverage=make("section","rv-related rv-paired-coverage");
  coverage.append(make("h2","","Coverage of this publication"));
  for(const companion of companions){
   const article=make("div","rv-excerpt");
   add(article,add(make("h3"),link(readingHeadline(companion),readingPath(companion),"rv-related-item")),
    make("p","",readingKind(companion)));
   const originalUrl=httpsSourceUrl(companion.reading?.source_url)||httpsSourceUrl(companion.url);
   if(originalUrl)article.append(link("Read the original story",originalUrl,"rv-secondary-link"));
   coverage.append(article);
  }
  side.append(coverage);
 }
 const related=S.records.filter(y=>id(y)!==id(x)&&y.lane===x.lane&&sourceFamily(y)===family&&depth(y)!=="citation_only")
                       .sort((a,b)=>rank(b)-rank(a)).slice(0,3);
 if(related.length){
  const next=make("section","rv-related");
  add(next,make("span","rv-section-overline","CONTINUE EXPLORING"),make("h2","","Related readings"));
  for(const y of related)next.append(btn(shortIdea(y,90),()=>goto("paper",id(y)),"rv-related-item"));
  side.append(next);
 }
 add(layout,story,side);
 articleSections(main,layout,body,side,analysis,evidencePanel,sections);
 root.append(main);
}
let libraryPromise=null;
const articlePromises=new Map();
function matchesSearch(x,q){
 const text=[x.title,x.display_headline,readingKind(x),x.venue,x.search_text,x.abstract_text,x.preview,x.reading?.findings,x.reading?.methods,...Object.values(x.reading?.digest||{}).filter(v=>typeof v==="string"),(x.authors||[]).join(" ")].join(" ").toLowerCase();
 return text.includes(String(q).toLowerCase());
}
async function jsonPayload(path,immutable=false){
 const response=await fetch(path,{cache:immutable?"force-cache":"no-cache"});
 if(!response.ok)throw new Error("Could not load published content (HTTP "+response.status+")");
 return response.json();
}
function readerPath(path){
 if(typeof path!=="string"||!/^data\/reader\/(?:indexes|articles)\/[a-f0-9]{64}\.json$/.test(path))throw new Error("Invalid reader asset");
 return path;
}
async function ensureLibrary(){
 if(S.libraryLoaded)return;
 if(libraryPromise)return libraryPromise;
 libraryPromise=(async()=>{
  const rows=S.manifest?await jsonPayload(readerPath(S.manifest.index_url),true):await jsonPayload("data/public-library.json");
  if(!Array.isArray(rows))throw new Error("Unexpected library format");
  const available=rows.filter(x=>x.reading?.level&&x.reading.level!=="citation_only");
  S.companions=available.filter(x=>Boolean(x.companion_to));
  S.records=available.filter(x=>!x.companion_to);S.libraryLoaded=true;
  extendTopicChoices();
  home();renderIssue();renderBacklog();renderPerspectives();showLibrary();
 })().catch(error=>{libraryPromise=null;throw error});
 return libraryPromise;
}
async function openPaper(key,focusHeading=false){
 const hash=location.hash,root=$("#paper-content");
 root.replaceChildren(make("p","empty-state","Loading the reading…"));
 try{
  await ensureLibrary();let found=record(key);
  if(!found){
   if(!S.pending.length)S.pending=await jsonPayload("data/public-pending-sources.json");
   found=record(key);
  }
  if(found?.article_payload){
   const asset=readerPath(found.article_payload);
   if(!articlePromises.has(asset))articlePromises.set(asset,jsonPayload(asset,true).catch(error=>{articlePromises.delete(asset);throw error}));
   const full=await articlePromises.get(asset);
   if(id(full)!==id(found))throw new Error("Reading identity mismatch");
   found=full;
  }
  if(location.hash===hash){
   showPaper(found);
   const heading=focusHeading&&$("#paper h1");
   if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true})}
  }
 }catch(error){
  if(location.hash===hash)root.replaceChildren(make("p","empty-state","This reading could not load. The published brief remains available."),btn("Try again",()=>openPaper(key)));
 }
}
async function init(){
 // The published edition never waits for the archive or operational history.
 try{
  try{
   const manifest=await jsonPayload("data/reader-manifest.json");
   if(manifest.schema_version!==1||manifest.edition_id!==(manifest.issue?.edition_date||null))throw new Error("Invalid publication manifest");
   S.manifest=manifest;S.issue=manifest.issue;S.week={run:manifest.collection};
  }catch{
   S.issue=await jsonPayload("data/public-featured-issue.json");
  }
  renderIssue();if(!location.hash.startsWith("#lab"))route();
 }catch{
  $("#weekly-deck").textContent="Read the published edition in the archive.";
  $("#weekly-scope").replaceChildren(link("Open the edition archive","issues/"));
  if(!location.hash.startsWith("#lab"))route();
 }
 // Optional data is isolated: a failed index cannot erase a valid edition.
 try{await ensureLibrary();if(!location.hash.startsWith("#lab"))route()}catch{
  $("#issue-label").textContent="RESEARCH INDEX TEMPORARILY UNAVAILABLE";
  $("#issue-meta").textContent="The published weekly brief is still available.";
 }
}
$$("[data-route]").forEach(a=>a.onclick=e=>{e.preventDefault();goto(a.dataset.route)});
["search","scope-filter","topic-filter","depth-filter","type-filter"].forEach(s=>$("#"+s).addEventListener(s==="search"?"input":"change",updateLibraryRoute));
$("#browse-editorial").addEventListener("click",e=>{e.preventDefault();goto("perspectives")});
$("#field-search").addEventListener("submit",event=>{
 event.preventDefault();const query=$("#field-query").value.trim();
 location.hash=query?"#library?q="+encodeURIComponent(query):"#library";
});
$(".skip").addEventListener("click",event=>{
 event.preventDefault();const main=$("#main");main.focus();main.scrollIntoView({block:"start"});
});
$$("[data-library-theme]").forEach(button=>button.addEventListener("click",()=>chooseLibraryTheme(button.dataset.libraryTheme)));
$("#library-sort").addEventListener("change",updateLibraryRoute);
$("#library-page-size")?.addEventListener("change",updateLibraryRoute);
for(const [selector,step] of [["#library-previous",-1],["#library-next",1]])$(selector)?.addEventListener("click",()=>{libraryPage.number=Math.max(0,libraryPage.number+step);updateLibraryRoute();$(".library-results-heading").scrollIntoView({block:"start"});$("#library-page-status").tabIndex=-1;$("#library-page-status").focus({preventScroll:true});});
$("#library-reset").addEventListener("click",()=>{
 $("#search").value="";$("#scope-filter").value="all";$("#topic-filter").value="";$("#type-filter").value="";$("#depth-filter").value="readable";updateLibraryRoute();
});
function closeNavigation(){
 $(".main-nav").classList.remove("is-open");$("#nav-toggle").setAttribute("aria-expanded","false");
}
const navigation=$(".main-nav"),menuToggle=$("#nav-toggle");
navigation.classList.add("is-collapsible");menuToggle.hidden=false;
menuToggle.addEventListener("click",()=>{const open=menuToggle.getAttribute("aria-expanded")!=="true";menuToggle.setAttribute("aria-expanded",String(open));navigation.classList.toggle("is-open",open)});
navigation.addEventListener("keydown",event=>{if(event.key==="Escape"&&menuToggle.getAttribute("aria-expanded")==="true"){closeNavigation();menuToggle.focus()}});
window.addEventListener("hashchange",route);
setupPageLayers();
if(location.hash.startsWith("#lab"))route();
init();




/* A fictional inbox with four explicit access rules. All trial state stays in this view. */
(() => {
  const lab = document.querySelector('#design-inbox');
  if (!lab) return;
  const stage = lab.querySelector('#design-inbox-stage');
  const history = lab.querySelector('#design-inbox-history');
  const goal = lab.querySelector('#design-goal');
  const messages = [
    {id:'lunch', account:'Work', from:'Office chat', subject:'Friday lunch poll', body:'The team is choosing between tacos and dumplings.'},
    {id:'pickup', account:'Personal', from:'School office', subject:'Pickup time change', body:'Pickup moved to 3:15 today. Use the usual gate.'},
    {id:'offer', account:'Personal', from:'Local bookshop', subject:'A new reading list', body:'The bookshop posted five short novels for the weekend.'},
    {id:'room', account:'Work', from:'Meeting organizer', subject:'Our room has changed', body:'The meeting moved to room 204.'}
  ];
  const rules = {
    open: 'Show everything',
    intent: 'Ask why',
    work: 'Work account only',
    block: 'Block the inbox'
  };
  let rule = 'open';
  let trials = [];
  let opened = new Set();

  function button(label, action, className = '') {
    const node = document.createElement('button');
    node.type = 'button';
    node.className = className;
    node.textContent = label;
    node.addEventListener('click', action);
    return node;
  }

  function show(title, description, controls = [], focus = true) {
    const heading = document.createElement('h4');
    heading.textContent = title;
    heading.tabIndex = -1;
    const body = document.createElement('p');
    body.textContent = description;
    stage.replaceChildren(heading, body, ...controls);
    if (focus) heading.focus({preventScroll:true});
  }

  function ready(focus = false) {
    opened = new Set();
    show('Back at your desk', 'Your proposal is open. You reach for your messages.', [
      button('Open the inbox', tryOpen, 'design-inbox-primary')
    ], focus);
  }

  function finish(title, detail, outcome) {
    const visibleCount = visibleMessages().length;
    const summary = rules[rule] + ' · ' + outcome;
    trials = [...trials.filter(t => t.rule !== rule), {rule, summary}].slice(-4);
    const heading = document.createElement('h5');
    heading.textContent = 'Your comparisons for this task';
    const list = document.createElement('ul');
    for (const trial of trials) {
      const entry = document.createElement('li');
      entry.textContent = trial.summary;
      list.append(entry);
    }
    history.replaceChildren(heading, list);
    history.hidden = false;
    const countText = rule === 'intent' && !opened.size ? '' : ' ' + visibleCount + ' of 4 messages available.';
    show(title, detail + countText, [
      button('Try another design', () => {
        ready();
        lab.querySelector('input:checked').focus();
      }, 'design-inbox-primary'),
      button('Start over', reset, 'design-inbox-secondary')
    ]);
  }

  function visibleMessages() {
    if (rule === 'block') return [];
    return rule === 'work' ? messages.filter(message => message.account === 'Work') : messages;
  }

  function read(message) {
    opened.add(message.id);
    if (message.id === goal.value) {
      const extra = opened.size > 1 ? ' You also opened ' + (opened.size - 1) + ' other ' + (opened.size === 2 ? 'message.' : 'messages.') : '';
      finish('You found what you needed', message.body + extra, 'Found the message');
    } else {
      show(message.subject, message.body, [button('Back to messages', inbox)]);
    }
  }

  function inbox() {
    const visible = visibleMessages();
    const controls = visible.map(message => {
      const item = button('', () => read(message), 'design-inbox-message');
      const sender = document.createElement('strong');
      sender.textContent = message.from;
      const subject = document.createElement('span');
      subject.textContent = message.subject;
      item.append(sender, subject);
      return item;
    });
    const targetVisible = visible.some(message => message.id === goal.value);
    if (!targetVisible) controls.push(button("I can't find it", () =>
      finish('The school message is hidden', 'The filter kept work mail visible. Pickup details came to your personal account.', 'Needed message hidden'), 'design-inbox-secondary'));
    show('Messages', rule === 'work' ? 'Only the work account is showing.' : 'Both accounts are showing.', controls);
  }

  function tryOpen() {
    if (rule === 'block') {
      finish('The inbox stays closed', 'The block protects your writing session. It also keeps the update you need out of reach until the session ends.', 'Needed message blocked');
    } else if (rule === 'intent') {
      show('Why open the inbox?', 'Take a moment to choose what you want to do.', [
        button(goal.value === 'room' ? 'Look for the room change' : 'Check pickup time', inbox, 'design-inbox-primary'),
        button('Keep writing instead', () => finish('Back to the proposal', 'You chose to keep writing. The update is still waiting in the inbox.', 'Deferred opening'), 'design-inbox-secondary')
      ]);
    } else {
      inbox();
    }
  }

  function clearComparisons() {
    trials = [];
    history.hidden = true;
    history.replaceChildren();
  }

  function reset() {
    goal.value = 'room';
    rule = 'open';
    lab.querySelector('input[value="open"]').checked = true;
    clearComparisons();
    ready();
    goal.focus();
  }

  goal.addEventListener('change', () => {
    clearComparisons();
    ready();
  });
  lab.querySelector('fieldset').addEventListener('change', event => {
    rule = event.target.value;
    ready();
  });
  ready();
  lab.hidden = false;
})();
