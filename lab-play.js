/* Attention Playground — experimental, client-side interactions.
   No API, account, analytics, localStorage or persistence. NOT a cognitive test. */
(() => {
  "use strict";
  const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
  const E=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=String(txt);return n};
  const add=(p,...kids)=>{kids.filter(Boolean).forEach(n=>p.append(n));return p};
  const button=(label,fn,cls="")=>{const n=E("button",cls,label);n.type="button";n.addEventListener("click",fn);return n};
  const round=n=>Math.round(n);
  const med=xs=>{if(!xs.length)return 0;const a=xs.slice().sort((x,y)=>x-y);return a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2};
  const practice={switch:{active:false,trial:0,results:[],current:null,locked:false,shownAt:null,interrupted:false,timer:null,generation:0,kind:"snapshot",timed:true,length:20},recovery:{mode:"cue",stage:"ready",interrupt:0,correct:0,start:0,history:[],round:0,interrupted:false,comparison:null,comparisonCount:0},assist:{mode:"reflect",scenario:0,chosen:false}};
  function activate(name){
    $$("[data-play-tab]").forEach(b=>{let on=b.dataset.playTab===name;b.classList.toggle("is-active",on);b.setAttribute("aria-selected",String(on));b.tabIndex=on?0:-1});
    ["switch","recovery","assist"].forEach(k=>$("#play-"+k).hidden=k!==name);
    syncVisibility();
    if(document.defaultView)document.dispatchEvent(new CustomEvent("observatory:lab-classic",{detail:name}));
  }
  document.addEventListener("observatory:lab-activate",event=>{if(["switch","recovery","assist"].includes(event.detail))activate(event.detail)});
  document.addEventListener("observatory:lab-visibility",()=>syncVisibility());
  document.addEventListener("observatory-layer-change",()=>syncVisibility());
  $$("[data-play-tab]").forEach(b=>{
    b.addEventListener("click",()=>activate(b.dataset.playTab));
    b.addEventListener("keydown",e=>{if(!["ArrowRight","ArrowLeft","Home","End"].includes(e.key))return;e.preventDefault();e.stopPropagation();const all=$$("[data-play-tab]");let i=all.indexOf(b);let next=all[e.key==="Home"?0:e.key==="End"?all.length-1:(i+(e.key==="ArrowRight"?1:-1)+all.length)%all.length];next.focus();activate(next.dataset.playTab)});
  });
  const visible=name=>!document.hidden&&!document.querySelector("dialog[open]")&&!$("#lab").hidden&&!$("#lab-activities")?.hidden&&!$("#play-"+name).hidden;
  function syncVisibility(){
    const g=practice.switch;
    if(g.active&&!g.locked){
      if(!visible("switch")){
        if(g.shownAt!==null)g.interrupted=true;
        g.shownAt=null;
      } else if(g.shownAt===null){
        g.shownAt=performance.now();
        if(g.interrupted)$("#switch-note").textContent=g.timed?"Resumed · this response will not count toward timing.":"Resumed · continue at your own pace.";
      }
    }
    const r=practice.recovery;
    if(r.stage==="return"&&!visible("recovery"))r.interrupted=true;
  }
  // Include browser tabs and navigation to another Observatory page. A response
  // seen before an interruption is not a fresh reaction-time observation.
  document.addEventListener("visibilitychange",syncVisibility);
  new MutationObserver(syncVisibility).observe($("#lab"),{attributes:true,attributeFilter:["hidden"]});
  if($("#lab-activities"))new MutationObserver(syncVisibility).observe($("#lab-activities"),{attributes:true,attributeFilter:["hidden"]});
  // 1 / Switch Lab: repeat a single rule, then alternate parity and magnitude.
  const choices=[1,2,3,4,6,7,8,9];
  const challengeLength=20;
  const switchTrack=$("#switch-track");
  for(let i=0;i<challengeLength;i++)switchTrack.append(E("span","switch-dot"));
  function switchCue(rule){return rule==="parity"?"ODD OR EVEN?":"LOW (1–4) OR HIGH (6–9)?"}
  function switchRender(){
    const g=practice.switch,phase=g.kind==="practice"?"PRACTICE · UNTIMED":g.trial<8?"SAME RULE":"SWITCHING RULES";
    $("#switch-phase").textContent=phase;
    $("#switch-progress").textContent=(g.trial+1)+" / "+g.length;
    $("#switch-cue").textContent=switchCue(g.current.rule);
    $("#switch-number").textContent=g.current.value;
    $("#switch-note").textContent=g.current.rule==="parity"?"LEFT = ODD     ·     RIGHT = EVEN":"LEFT = LOW     ·     RIGHT = HIGH";
    $("#switch-left").disabled=false;$("#switch-right").disabled=false;
    $("#switch-left").setAttribute("aria-disabled","false");$("#switch-right").setAttribute("aria-disabled","false");
    $("#switch-left").setAttribute("aria-label",g.current.rule==="parity"?"Left: odd":"Left: low, 1 to 4");
    $("#switch-right").setAttribute("aria-label",g.current.rule==="parity"?"Right: even":"Right: high, 6 to 9");
    $("#switch-next").hidden=true;
    $("#switch-announcement").textContent="Turn "+(g.trial+1)+" of "+g.length+". "+(g.current.rule==="parity"?"Odd or even? ":"Low, 1 to 4, or high, 6 to 9? ")+g.current.value+". "+(g.current.rule==="parity"?"Left for odd; right for even.":"Left for low; right for high.");
    $("#switch-start").hidden=true;
    $$(".switch-dot").forEach((d,i)=>{d.className="switch-dot";d.hidden=i>=g.length;if(i<g.trial)d.classList.add(g.results[i].correct?"is-correct":"is-wrong");else if(i===g.trial)d.classList.add("is-now")});
    g.locked=false;g.interrupted=false;g.shownAt=visible("switch")?performance.now():null;
  }
  function nextSwitch(){
    const g=practice.switch;
    if(g.trial>=g.length){switchFinish();return}
    const value=choices[Math.floor(Math.random()*choices.length)];
    let rule=g.trial<(g.kind==="practice"?2:8)?"parity":(g.trial%2===0?"parity":"magnitude");
    g.current={value,rule};
    switchRender();
  }
  function cancelSwitch(){
    const g=practice.switch;g.generation++;clearTimeout(g.timer);g.timer=null;g.active=false;g.shownAt=null;
  }
  function startSwitch(kind="snapshot"){
    cancelSwitch();
    const g=practice.switch;g.active=true;g.trial=0;g.results=[];g.locked=false;g.kind=kind;g.length=kind==="practice"?4:challengeLength;g.timed=kind!=="practice"&&$("#switch-timing").value!=="untimed";
    $("#switch-timing").disabled=true;$("#switch-practice").disabled=true;
    $("#play-session-status").textContent="";
    $("#switch-results").hidden=true;$("#switch-results").replaceChildren();
    $("#switch-start").textContent="Start 20-trial snapshot";nextSwitch();$("#switch-left").focus();
  }
  function respond(side){
    const g=practice.switch;
    if(!g.active||g.locked||!visible("switch")||g.shownAt===null)return;
    const item=g.current;
    const correctSide=item.rule==="parity"?(item.value%2?"left":"right"):(item.value<5?"left":"right");
    const rt=!g.timed||g.interrupted?null:Math.max(0,Math.round(performance.now()-g.shownAt));
    const correct=correctSide===side;
    g.results.push({phase:g.trial<8?"repeat":"alternate",rt,correct,rule:item.rule,value:item.value,interrupted:g.interrupted});
    g.locked=true;$("#switch-left").setAttribute("aria-disabled","true");$("#switch-right").setAttribute("aria-disabled","true");
    $("#switch-note").textContent=correct?"✓ Correct":"↪ Different rule—keep going";
    g.trial+=1;g.shownAt=null;
    if(!g.timed){
      $("#switch-next").hidden=false;$("#switch-next").textContent=g.trial>=g.length?"See debrief":"Next turn";
      $("#switch-announcement").textContent=(correct?"Correct.":"Different choice. Check the rule.")+" Choose "+(g.trial>=g.length?"See debrief":"Next turn")+" when ready.";
      $("#switch-next").focus();
    } else {
      const generation=g.generation;
      g.timer=setTimeout(()=>{if(g.active&&g.generation===generation){g.timer=null;nextSwitch()}},correct?240:480);
    }
  }
  function switchFinish(){
    const g=practice.switch;g.active=false;
    $("#switch-left").disabled=true;$("#switch-right").disabled=true;$("#switch-next").hidden=true;
    $("#switch-timing").disabled=false;$("#switch-practice").disabled=false;
    $("#switch-announcement").textContent="";
    $$(".switch-dot").forEach((d,i)=>{d.hidden=i>=g.length;d.className="switch-dot";if(i<g.length)d.classList.add(g.results[i].correct?"is-correct":"is-wrong")});
    $("#switch-phase").textContent="COMPLETE";
    $("#switch-progress").textContent=g.length+" / "+g.length;
    $("#switch-cue").textContent="YOUR PLAY SESSION";
    $("#switch-number").textContent="✓";
    $("#switch-note").textContent="What did you notice about changing rules?";
    $("#switch-start").hidden=false;$("#switch-start").textContent="Start 20-trial snapshot";
    const root=$("#switch-results");root.replaceChildren();root.hidden=false;
    if(g.kind==="practice"){
      add(root,E("p","play-kicker","PRACTICE COMPLETE"),E("h4","","Ready for the two rules?"),E("p","play-chart-caption","These four untimed turns only introduced the controls. Practice results are discarded and never enter the 20-trial snapshot. Start a snapshot when you want to explore the change in rules."));
      g.results=[];if(visible("switch"))root.focus();return;
    }
    const repeat=g.results.filter(x=>x.phase==="repeat"),mixed=g.results.filter(x=>x.phase==="alternate");
    const rtA=round(med(repeat.filter(x=>x.correct&&x.rt!==null).map(x=>x.rt)));
    const rtB=round(med(mixed.filter(x=>x.correct&&x.rt!==null).map(x=>x.rt)));
    const accA=repeat.filter(x=>x.correct).length,accB=mixed.filter(x=>x.correct).length;
    add(root,E("p","play-kicker",g.timed?"SESSION SNAPSHOT":"UNTIMED SESSION SNAPSHOT"),E("h4","","Repeat vs. switching"));
    const chart=E("div","play-chart"),maximum=Math.max(rtA,rtB,1);
    [["Same rule",rtA,accA,8],["Alternating",rtB,accB,12]].forEach(([name,ms,good,total])=>{
      const r=E("div","play-chart-line"),bar=E("div","play-chart-track"),fill=E("span","play-chart-fill");
      fill.style.width=(ms/maximum*100)+"%";bar.append(fill);
      add(r,E("span","",name),g.timed?bar:null,E("strong","",g.timed?(ms?ms+" ms":"—"):good+" / "+total+" correct"));if(!g.timed)r.classList.add("play-chart-untimed");chart.append(r);
      const note=E("p","play-chart-sub",good+" / "+total+" correct");if(g.timed)chart.append(note);
    });
    const omitted=g.results.filter(x=>x.interrupted).length;
    if(g.timed&&omitted)chart.append(E("p","play-chart-caption",omitted+" interrupted response(s) excluded from timing."));
    add(root,chart,E("p","play-chart-caption",(g.timed?"Medians from uninterrupted correct responses only. Device, browser and input method affect timing. ":"No response times were recorded. ")+"The same rule always comes first (8 turns), followed by alternating rules (12 turns). Fixed order, small samples and practice effects prevent a valid estimate of switch cost or attention. Faster is not necessarily better real-world attention."));
    add(root,E("p","play-chart-caption","Reflect: did keeping the rule in mind, noticing the cue, or choosing a response feel most effortful? This comparison cannot tell those processes apart."));
    if(visible("switch"))root.focus();
  }
  $("#switch-start").addEventListener("click",()=>startSwitch());
  $("#switch-practice").addEventListener("click",()=>startSwitch("practice"));
  $("#switch-next").addEventListener("click",()=>{const g=practice.switch;if(g.active&&g.locked&&!g.timed){nextSwitch();if(g.active)$("#switch-left").focus()}});
  $("#switch-left").addEventListener("click",()=>respond("left"));
  $("#switch-right").addEventListener("click",()=>respond("right"));
  document.addEventListener("keydown",e=>{
    // Native Enter activates focused buttons on keydown. Suppress auto-repeat
    // before returning so held keys cannot answer or advance multiple turns.
    if(visible("switch")&&e.repeat&&e.key==="Enter"&&["switch-start","switch-practice","switch-left","switch-right","switch-next"].includes(document.activeElement?.id)){e.preventDefault();return}
    if(e.defaultPrevented||e.repeat||document.hidden||$("#lab").hidden||$("#play-switch").hidden||e.altKey||e.ctrlKey||e.metaKey||document.activeElement?.isContentEditable||document.activeElement?.getAttribute?.("role")==="tab"||/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName||""))return;
    if(["switch-left","switch-right"].includes(document.activeElement?.id)&&(e.key==="ArrowLeft"||e.key==="ArrowRight")){e.preventDefault();respond(e.key==="ArrowLeft"?"left":"right")}
  });

  // 2 / Return Point: contextual resumption after a small distraction.
  // Original fictional learning scenarios, not summaries of actual studies.
  // Edition: 2026-11-06. Update only alongside substantive tested changes.
  const recoveryCases=[
    {context:"You're writing about AI and attention. You've read two studies about cognitive effort.",next:"Compare the two studies' measures",options:["Format the references","Compare the two studies' measures","Export your calendar"]},
    {context:"You're preparing a group presentation. Your slides are drafted but not yet connected to your argument.",next:"Connect slide evidence to your central claim",options:["Choose a cover color","Connect slide evidence to your central claim","Book next month's room"]},
    {context:"You're checking an AI-generated explanation. You've found the original article, but haven't checked its results yet.",next:"Compare the explanation with the reported results",options:["Compare the explanation with the reported results","Polish the explanation's tone","Share the explanation immediately"]},
    {context:"You're organizing a literature review. Two papers use the word attention for different kinds of tasks.",next:"Record how each paper defines and measures attention",options:["Average all the scores together","Rename the project folder","Record how each paper defines and measures attention"]}
  ];
  // Parallel templates make task identity explicit; they are not validated as
  // equally difficult. Each pair uses both conditions, with independent random
  // choices for starting condition and task variant. No causal estimate is made.
  const recoveryPairs=[
    [
      {context:"You're drafting a research brief. You've collected two studies about reading, but haven't compared how they measured understanding.",next:"Compare how the two studies measured understanding",options:["Choose a cover image for the brief","Compare how the two studies measured understanding","Send the brief before comparing the studies"]},
      {context:"You're drafting a research brief. You've collected two studies about memory, but haven't compared how they measured recall.",next:"Compare how the two studies measured recall",options:["Choose a cover image for the brief","Compare how the two studies measured recall","Send the brief before comparing the studies"]}
    ],
    [
      {context:"You're preparing a presentation. You've selected two examples about AI writing, but haven't connected them to your central claim.",next:"Connect the writing examples to your central claim",options:["Change the presentation's background color","Connect the writing examples to your central claim","Delete the examples before reviewing them"]},
      {context:"You're preparing a presentation. You've selected two examples about AI search, but haven't connected them to your central claim.",next:"Connect the search examples to your central claim",options:["Change the presentation's background color","Connect the search examples to your central claim","Delete the examples before reviewing them"]}
    ]
  ];
  const modeName=mode=>mode==="cue"?"With checkpoint":"Without checkpoint";
  const recoveryMode=()=>{const r=practice.recovery;return r.comparison?r.comparison.conditions[r.comparison.step]:r.mode};
  const recoveryStory=()=>{const r=practice.recovery,c=r.comparison;return c?recoveryPairs[c.pairIndex][c.variants[c.step]]:recoveryCases[r.round%recoveryCases.length]};
  function shuffled(items){
    const result=items.slice();
    for(let i=result.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[result[i],result[j]]=[result[j],result[i]]}
    return result;
  }
  function recoveryComparisonControls(){
    const c=practice.recovery.comparison;
    $$("[data-recovery-mode]").forEach(b=>b.disabled=!!c);
    $("#recovery-compare").disabled=!!c;
    $("#recovery-exit-comparison").hidden=!c;$("#recovery-exit-help").hidden=!c;
    $("#recovery-comparison-plan").hidden=!c;
    $("#recovery-comparison-plan").textContent=c?"Pair "+(c.pairIndex+1)+" · "+modeName(c.conditions[0])+" → "+modeName(c.conditions[1])+". Task "+"AB"[c.variants[0]]+" → "+"AB"[c.variants[1]]+". Read each new task before starting.":"";
  }
  function startRecoveryComparison(){
    const r=practice.recovery,condition=Math.random()<.5?"cue":"none",variant=Math.random()<.5?0:1;
    r.comparison={id:++r.comparisonCount,pairIndex:(r.comparisonCount-1)%recoveryPairs.length,step:0,conditions:[condition,condition==="cue"?"none":"cue"],variants:[variant,1-variant],results:[]};
    $("#recovery-comparison-results").replaceChildren();$("#recovery-comparison-results").hidden=true;
    recoveryComparisonControls();recoveryPreview();$("#recovery-headline").focus();
  }
  $("#recovery-compare").addEventListener("click",startRecoveryComparison);
  $("#recovery-exit-comparison").addEventListener("click",()=>{
    practice.recovery.comparison=null;
    $("#recovery-comparison-results").replaceChildren();$("#recovery-comparison-results").hidden=true;
    recoveryComparisonControls();recoveryPreview();$("#recovery-headline").focus();
  });
  const distractions=[
    {prompt:"Choose the option with two diamonds",options:["◇","●","◇ ◇"],labels:["One diamond","One circle","Two diamonds"],right:2},
    {prompt:"Which number is smallest?",options:["19","7","13"],right:1},
    {prompt:"Find the different shape",options:["□","□","△"],labels:["Square, first option","Square, second option","Triangle"],right:2},
    {prompt:"Which word has four letters?",options:["focus","plan","think"],right:1}
  ];
  function recoveryPreview(){
    const r=practice.recovery,c=r.comparison,story=recoveryStory();
    r.stage="ready";r.interrupt=0;r.correct=0;r.start=0;r.interrupted=false;
    $("#recovery-round-context").textContent=c?"COMPARISON "+c.id+" · ROUND "+(c.step+1)+" / 2 · PAIR "+(c.pairIndex+1)+" · TASK "+"AB"[c.variants[c.step]]+" · "+modeName(recoveryMode()):"SINGLE ROUND · "+modeName(r.mode);
    $("#recovery-stage-label").textContent="THE TASK";
    $("#recovery-progress").textContent=(c?"ROUND "+(c.step+1)+" / 2":"TASK "+(r.round%recoveryCases.length+1)+" / "+recoveryCases.length)+" · STAGE 1 / 3";
    $("#recovery-headline").setAttribute("aria-describedby","recovery-round-context recovery-description");
    $("#recovery-headline").textContent="A half-finished project";
    $("#recovery-description").textContent=story.context+" Your next action: "+story.next+".";
    $("#recovery-interaction").replaceChildren();
    $("#recovery-start").hidden=false;$("#recovery-start").textContent="Begin interruption";
  }
  $$("[data-recovery-mode]").forEach(btn=>btn.addEventListener("click",()=>{
    if(practice.recovery.comparison)return;
    practice.recovery.mode=btn.dataset.recoveryMode;
    $$("[data-recovery-mode]").forEach(x=>{const active=x===btn;x.classList.toggle("is-active",active);x.setAttribute("aria-pressed",String(active))});
    recoveryPreview();
  }));
  function recoveryDistract(){
    const r=practice.recovery,stim=distractions[r.interrupt];
    if(!stim){recoveryReturn();return}
    r.stage="interrupt";
    $("#recovery-stage-label").textContent="INTERRUPTION";
    $("#recovery-progress").textContent="STAGE 2 / 3";
    $("#recovery-headline").textContent=stim.prompt;
    $("#recovery-description").textContent="Complete these four quick distractions, then return to your project.";
    $("#recovery-start").hidden=true;
    const place=$("#recovery-interaction");place.replaceChildren();
    const options=E("div","recovery-options");
    stim.options.forEach((t,i)=>{const option=button(t,()=>{
      if(r.stage!=="interrupt")return;
      if(i===stim.right)r.correct++;
      r.interrupt++;
      recoveryDistract();
    },"recovery-option");if(stim.labels)option.setAttribute("aria-label",stim.labels[i]);options.append(option)});
    add(place,E("p","play-kicker","MICRO-TASK "+(r.interrupt+1)+" / 4"),options);
    $("#recovery-headline").focus();
  }
  function recoveryReturn(){
    const r=practice.recovery; r.stage="return";
    const story=recoveryStory();
    $("#recovery-stage-label").textContent="BACK TO YOUR WORK";
    $("#recovery-progress").textContent="STAGE 3 / 3";
    $("#recovery-headline").textContent="What was your next step?";
    $("#recovery-description").textContent="Choose the step that continues your project.";
    const place=$("#recovery-interaction");place.replaceChildren();
    const hasCue=recoveryMode()==="cue";
    if(hasCue){const cue=E("div","recovery-cue","↩  CHECKPOINT   ·   "+story.next);cue.id="recovery-checkpoint";place.append(cue)}
    $("#recovery-headline").setAttribute("aria-describedby","recovery-round-context recovery-description"+(hasCue?" recovery-checkpoint":""));
    const options=E("div","recovery-options recovery-return-options");
    r.start=performance.now();
    shuffled(story.options).forEach((choice)=>options.append(button(choice,()=>recoveryFinish(choice===story.next), "recovery-option")));
    place.append(options);
    r.interrupted=!visible("recovery");
    $("#recovery-headline").focus();
  }
  function recoveryFinish(correct){
    const r=practice.recovery;if(r.stage!=="return")return;r.stage="done";
    const elapsed=r.interrupted?null:Math.max(0,round(performance.now()-r.start));
    const c=r.comparison;
    if(c)c.results.push({mode:recoveryMode(),correct,ms:elapsed,variant:c.variants[c.step],round:c.step+1});
    else r.history.push({mode:r.mode,correct,ms:elapsed,task:r.round%recoveryCases.length+1,round:r.history.length+1});
    $("#recovery-stage-label").textContent="SESSION COMPLETE";
    $("#recovery-progress").textContent="DONE";
    $("#recovery-headline").textContent=correct?"Found your return point.":"Returning isn't always simple.";
    $("#recovery-description").textContent=(correct?"You selected the intended next step.":"You selected a different step.")+" What helped you decide where to resume?";
    $("#recovery-headline").setAttribute("aria-describedby","recovery-round-context recovery-description");
    const place=$("#recovery-interaction");place.replaceChildren();
    add(place,E("div","recovery-outcome",correct?"✓ Correct next action":"↩ Notice what was lost"),E("div","recovery-time",elapsed===null?"Timing omitted: you left this activity before choosing.":elapsed+" ms to choose"));
    $("#recovery-start").hidden=false;$("#recovery-start").textContent=c?(c.step===0?"Preview second round":"Try another comparison"):"Try another round";
    if(c){
      if(c.results.length===2)recoveryComparisonFinish();
      else $("#recovery-headline").focus();
      return;
    }
    $("#recovery-headline").focus();
    const history=$("#recovery-history");history.replaceChildren();
    const table=E("div","recovery-trial-list");
    r.history.slice(-4).forEach((x,i)=>{let row=E("div","recovery-trial");add(row,E("span","","Round "+x.round+" · Task "+x.task+" · "+(x.mode==="cue"?"With checkpoint":"Without checkpoint")),E("strong","",(x.ms===null?"timing omitted":round(x.ms/100)/10+" s")+"  ·  "+(x.correct?"correct":"different choice")));table.append(row)});
    add(history,E("p","play-kicker","YOUR LAST "+Math.min(r.history.length,4)+" SINGLE ROUNDS"),table,E("p","play-chart-caption","Timings begin when the return choices appear and are omitted after leaving the activity. Task numbers identify different materials; repeats introduce practice. You choose condition and order, and the checkpoint repeats the intended answer. These rounds cannot establish whether checkpoints improve performance. Reflect: what information would help you resume your own work?"));
  }
  function recoveryComparisonFinish(){
    const c=practice.recovery.comparison,root=$("#recovery-comparison-results");
    root.replaceChildren();root.hidden=false;
    add(root,E("p","play-kicker","TWO ROUNDS · ONE EXPLORATION"),E("h4","","What helped you return?"));
    const list=E("ol","recovery-comparison-list");
    c.results.forEach(x=>{const row=E("li","recovery-comparison-result");
      add(row,E("strong","","Round "+x.round+" · Pair "+(c.pairIndex+1)+", Task "+"AB"[x.variant]+" · "+modeName(x.mode)),E("p","",(x.correct?"Intended next step":"Different choice")+" · "+(x.ms===null?"timing omitted after leaving this activity":x.ms+" ms to choose")));list.append(row)});
    add(root,list,E("p","play-chart-caption","Each condition appeared once, using different versions of a parallel fictional task. Starting condition and task order were randomized independently. These materials are not validated as equally difficult. The same four distractions repeat, so practice, wording and order can still shape your experience."),E("p","play-chart-caption","Two responses do not estimate a checkpoint effect. The checkpoint repeats the intended answer, timing includes reading and input differences, and faster does not mean better real-world attention. Interrupted timings are omitted; no difference score is calculated."),E("p","play-chart-caption","Reflect: did the checkpoint help you recover the task context, or simply reveal the answer? What would a useful checkpoint need to preserve in your own work?"));
    if(visible("recovery"))root.focus();
  }
  $("#recovery-start").addEventListener("click",()=>{
    const r=practice.recovery;
    if(r.stage==="done"){
      if(r.comparison){if(r.comparison.step===1){startRecoveryComparison();return}r.comparison.step=1}
      else r.round++;
      recoveryPreview();$("#recovery-headline").focus();return;
    }
    if(r.stage==="ready")recoveryDistract();
  });
  recoveryPreview();
  // 3 / Assistance Dial: five fictional research-interpretation decisions.
  // Source-informed update: 2026-11-09; sources support context, not Lab validity.
  const scenarios=[
    {prompt:"A survey finds that students using AI summaries report spending less time reading. Can we conclude AI caused weaker comprehension?",
      options:["Yes. AI caused the comprehension change.","Not from this survey; cause and comprehension remain untested.","Yes, because the sample includes students."],
      correct:1,
      modes:{reflect:"Which outcome did the researchers actually measure? What kind of design would establish causality?",
             hint:"The study reports reading time in a survey, not a randomized test of comprehension.",
             answer:"No. The survey reports an association with reading time; it does not establish causality or a comprehension effect."},
      feedback:"This example distinguishes a self-report association from a causal claim. Measuring reading time is also not the same as measuring comprehension."},
    {prompt:"An experiment randomly assigns workers to batch notifications or receive them as usual. The batching group reports less stress. What can we infer?",
      options:["The design offers stronger causal evidence for this measured stress outcome.","The study proves batching increases concentration for everyone.","Any difference must be caused by participants' personalities."],
      correct:0,
      modes:{reflect:"What does random assignment change? Which outcome was actually reported?",
             hint:"Random assignment helps causal inference; the recorded outcome was stress, not concentration.",
             answer:"The study provides stronger causal evidence for reduced reported stress in that setting, not proof of improved concentration or universal effects."},
      feedback:"Random assignment is helpful for causal interpretation of the measured outcome, while external validity and whether focus itself improves remain separate questions."},
    {prompt:"An AI assistant gives a fluent, confident explanation of a study. You have not opened the original paper. What is the best next step?",
      options:["Treat confident language as evidence of accuracy.","Check the original paper's methods and results before relying on the claim.","Reject the claim only because an AI produced it."],
      correct:1,
      modes:{reflect:"What evidence could support the explanation, independently of how it sounds?",
             hint:"Fluency is a feature of the explanation. It does not verify the underlying study.",
             answer:"Check the original methods and results, including what was measured and what limitations apply. Neither confidence nor AI authorship settles accuracy."},
      feedback:"A persuasive explanation can be right or wrong. Trace the specific claim to its source rather than using tone as a substitute for evidence."},
    {prompt:"In a fictional randomized study, students finish a task faster with AI help. There is no later test without help. Does this show that they learned more?",
      options:["Yes. Faster completion always means deeper learning.","No. It proves AI prevents learning.","Neither conclusion follows; retained learning was not measured."],
      correct:2,
      modes:{reflect:"Is performing a task with help the same outcome as remembering how to do it later?",
             hint:"The measured outcome is completion speed. A later unassisted test would address retention.",
             answer:"The study supports a conclusion about task speed in that setting, not about retained learning. Both stronger and weaker learning remain untested."},
      feedback:"Assisted performance and retained learning are distinct outcomes. A delayed, unassisted assessment would help test the learning claim."},
    {prompt:"A design team interviews adult researchers who try a learning chatbot while imagining being students. What can this study tell us?",
      options:["It shows the chatbot improves students' learning.","How these adults experienced the prototype; student outcomes still need testing.","Nothing useful, because interviews are not experiments."],
      correct:1,
      modes:{reflect:"Who actually took part? What did the researchers observe, and whose experience remains untested?",
             hint:"Adults imagining student use can raise design questions. They are not a sample of students learning with the tool.",
             answer:"The interviews can inform design through these adults' experiences. They do not establish students' experiences or learning outcomes."},
      feedback:"Match the conclusion to the people and activity studied. Qualitative feedback can identify useful design tensions without establishing an effect for intended users.",
      context:{note:"This fictional teaching example is informed by Lin and colleagues’ exploratory v1 preprint, not a replication. Seven adult researchers role-played student use of one AI peer prototype, then gave interviews. The study examined expert interpretations; it did not test student learning or compare teaching conditions. Peer review is unverified. These accounts can inform design questions, but do not establish benefits for learners or validate this Lab.",
               source:"https://arxiv.org/pdf/2610.38990v1#page=6",
               issue:"https://chengyu-ucsb.github.io/ai-attention-observatory/issues/2026-11-07.html"}}
  ];
  function assistDraw(){
    const r=practice.assist,data=scenarios[r.scenario];r.chosen=false;
    $("#assist-scenario").value=String(r.scenario);
    $("#assist-counter").textContent="SCENARIO "+(r.scenario+1)+" / "+scenarios.length;
    $("#assist-prompt").textContent=data.prompt;
    const reply=$("#assist-reply");reply.replaceChildren();
    const box=E("div","assist-bubble");
    add(box,E("span","assist-bubble-label",r.mode==="reflect"?"REFLECTION FIRST":r.mode==="hint"?"JUST A HINT":"FULL ANSWER"),E("p","",data.modes[r.mode]));
    reply.append(box);
    $("#assist-feedback").replaceChildren();$("#assist-feedback").hidden=true;$("#assist-next").hidden=true;
    const choices=$("#assist-choices");choices.replaceChildren();
    data.options.forEach((x,i)=>choices.append(button(x,()=>assistChoose(i),"assist-option")));
  }
  function assistChoose(i){
    const r=practice.assist;if(r.chosen)return;r.chosen=true;
    const data=scenarios[r.scenario],ok=i===data.correct;
    $$("#assist-choices .assist-option").forEach((b,n)=>{b.disabled=true;if(n===data.correct)b.classList.add("correct");if(n===i&&!ok)b.classList.add("incorrect")});
    const root=$("#assist-feedback");root.replaceChildren();
    add(root,E("strong","",ok?"✓ Supported conclusion":"↩ Another interpretation is stronger"),E("p","",data.feedback));
    if(data.context){
      const details=E("details","assist-source"),summary=E("summary","","Source and limits");
      add(details,summary,E("p","",data.context.note));
      const sources=E("div","assist-source-links");
      [["Original study (v1, PDF)",data.context.source],["Published issue · 7 Nov",data.context.issue]].forEach(([label,url])=>{
        const a=E("a","",label);a.setAttribute("href",url);a.setAttribute("target","_blank");a.setAttribute("rel","noopener noreferrer");sources.append(a);
      });
      add(details,sources);root.append(details);
    }
    root.hidden=false;$("#assist-next").hidden=false;root.focus();
    $("#assist-next").textContent=r.scenario<scenarios.length-1?"Try another scenario":"Replay the first scenario";
  }
  $$("[data-assist-mode]").forEach(b=>b.addEventListener("click",()=>{
    const r=practice.assist;r.mode=b.dataset.assistMode;
    $$("[data-assist-mode]").forEach(x=>{let active=x===b;x.classList.toggle("is-active",active);x.setAttribute("aria-pressed",String(active))});
    assistDraw();$("#assist-prompt").focus();
  }));
  $("#assist-scenario").addEventListener("change",()=>{
    const index=Number($("#assist-scenario").value);
    if(!Number.isInteger(index)||index<0||index>=scenarios.length)return;
    practice.assist.scenario=index;assistDraw();
  });
  $("#assist-next").addEventListener("click",()=>{practice.assist.scenario=(practice.assist.scenario+1)%scenarios.length;assistDraw();$("#assist-prompt").focus()});
  $("#play-reset").addEventListener("click",()=>{
    cancelSwitch();
    const g=practice.switch;g.trial=0;g.results=[];g.current=null;g.locked=false;g.interrupted=false;
    $("#switch-results").replaceChildren();$("#switch-results").hidden=true;
    $("#switch-start").hidden=false;$("#switch-start").textContent="Start 20-trial snapshot";$("#switch-next").hidden=true;
    $("#switch-left").disabled=true;$("#switch-right").disabled=true;
    $("#switch-timing").disabled=false;$("#switch-practice").disabled=false;
    $("#switch-phase").textContent="READY TO PLAY";$("#switch-progress").textContent="0 / 20";$("#switch-cue").textContent="TWO RULES · ONE BRAIN";$("#switch-number").textContent="?";
    $("#switch-note").textContent="Start when you're ready.";$("#switch-announcement").textContent="";
    $$(".switch-dot").forEach(d=>{d.className="switch-dot";d.hidden=false});
    const r=practice.recovery;r.history=[];r.round=0;r.comparison=null;r.comparisonCount=0;
    $("#recovery-comparison-results").replaceChildren();$("#recovery-comparison-results").hidden=true;
    recoveryComparisonControls();recoveryPreview();$("#recovery-history").replaceChildren();
    practice.assist.scenario=0;assistDraw();
    $("#play-session-status").textContent="Lab stopped and reset. This visit’s results are cleared. Your selected modes are unchanged.";
    $("#play-reset").focus();
  });
  assistDraw();
  activate("switch");
})();



/* Versioned Lab collection: new activities and preserved classics share one catalog. */
(() => {
  "use strict";
  const CATALOG = [
    {id:"evidence-detective",title:"Evidence Detective",status:"new",version:"1.0.0",released:"2026-11-13",duration:"3 minutes",topic:"Reading AI claims",evidenceBasis:"Fictional teaching scenarios",description:"Turn over the evidence. Decide how far a claim can go.",glyph:"◈"},
    {id:"notification-studio",title:"Notification Studio",status:"new",version:"1.0.0",released:"2026-11-13",duration:"2 minutes",topic:"Designing interruptions",evidenceBasis:"Explicit arithmetic simulation",description:"Remix a stream of messages. See the trade-off between alerts and waiting.",glyph:"▥"},
    {id:"switch",title:"Switch Lab",status:"classic",version:"2026.11",released:"2026-11-05",updated:"2026-11-06",duration:"2 minutes",topic:"Task switching",evidenceBasis:"Exploratory task demonstration",description:"Try a stable rule, then a changing rule. Timed and untimed play.",glyph:"⇄"},
    {id:"recovery",title:"Return Point",status:"classic",version:"2026.11",released:"2026-11-05",updated:"2026-11-06",duration:"3 minutes",topic:"Returning to a task",evidenceBasis:"Fictional task comparison",description:"Leave a task and find your way back, with or without a checkpoint.",glyph:"↩"},
    {id:"assist",title:"Assistance Dial",status:"classic",version:"2026.11",released:"2026-11-05",updated:"2026-11-09",duration:"3 minutes",topic:"Choosing AI help",evidenceBasis:"Scripted reasoning scenarios",description:"Choose reflection, a hint, or an answer. Keep the judgment yours.",glyph:"◐"}
  ];
  const CASES = [
    {title:"The confident headline",claim:"An AI coach improves concentration at work.",cards:[
      {label:"Who took part?",detail:"Volunteers who already used the coach answered a one-time survey."},
      {label:"What was measured?",detail:"They rated how focused they felt. No attention task or work output was measured."},
      {label:"What was compared?",detail:"There was no comparison group and no measurement before using the coach."}
    ],verdict:"overreach",explanation:"The survey describes users’ impressions. It cannot establish that the coach caused better concentration.",takeaway:"A confident verb such as “improves” needs a design that can support a causal claim."},
    {title:"The narrow result",claim:"In this task, the reminder group missed fewer planned check-ins.",cards:[
      {label:"Who took part?",detail:"Volunteers were randomly assigned to receive reminders or no reminders during one simulated work session."},
      {label:"What was measured?",detail:"Researchers counted missed check-ins during that session. They did not test learning or long-term work habits."},
      {label:"What was found?",detail:"The reminder group missed fewer check-ins than the comparison group in the recorded session."}
    ],verdict:"supported",explanation:"The wording matches the comparison and the outcome measured. It stays within this simulated task.",takeaway:"A useful conclusion can be narrow. A task result is not a claim about every workplace."},
    {title:"The missing outcome",claim:"The assistant reduced people’s stress.",cards:[
      {label:"Who took part?",detail:"A small design team tried a fictional assistant prototype and discussed its interface."},
      {label:"What was measured?",detail:"The notes describe whether controls were easy to find. Stress was not measured or discussed."},
      {label:"What was found?",detail:"Participants suggested clearer labels and fewer steps. There is no evidence about stress in this dossier."}
    ],verdict:"unanswered",explanation:"This dossier does not answer the stress question. Interface feedback cannot establish a change in an unmeasured outcome.",takeaway:"An unanswered question is a reason to seek evidence, not proof that an effect is absent."}
  ];
  const MESSAGES = [
    {at:2,kind:"team",text:"Project update"},{at:4,kind:"social",text:"Group chat"},{at:6,kind:"team",text:"Document comment"},
    {at:8,kind:"urgent",text:"Time-sensitive request"},{at:11,kind:"social",text:"Photo shared"},{at:13,kind:"team",text:"Meeting question"},
    {at:16,kind:"team",text:"Review request"},{at:18,kind:"social",text:"Event invitation"},{at:21,kind:"urgent",text:"Decision needed"},
    {at:23,kind:"team",text:"Status check"},{at:26,kind:"social",text:"New reply"},{at:28,kind:"team",text:"File ready"}
  ];
  function notificationPlan(mode="batch",urgent=true){
    if(!["immediate","batch","end"].includes(mode))throw Error("Unknown delivery mode");
    const deliveries=MESSAGES.map(message=>({...message,delivered:mode==="immediate"||(urgent&&message.kind==="urgent")?message.at:mode==="end"?30:Math.ceil(message.at/10)*10}));
    const moments=[...new Set(deliveries.map(message=>message.delivered))].sort((a,b)=>a-b);
    const gaps=[0,...moments,30].slice(1).map((at,index)=>at-[0,...moments,30][index]);
    return {deliveries,moments,alerts:moments.length,meanWait:deliveries.reduce((sum,message)=>sum+message.delivered-message.at,0)/deliveries.length,longestGap:Math.max(...gaps),urgentWait:Math.max(...deliveries.filter(message=>message.kind==="urgent").map(message=>message.delivered-message.at))};
  }
  // The export lets the offline test verify the actual catalog and arithmetic.
  if(typeof module==="object"&&module.exports)module.exports={CATALOG,CASES,MESSAGES,notificationPlan};
  const catalog=document.querySelector("#lab-catalog"),workbench=document.querySelector("#lab-workbench");
  // Classic-only fixtures can run without the collection enhancement.
  if(!catalog||!workbench||!catalog.ownerDocument)return;
  const view=document.defaultView,q=selector=>document.querySelector(selector);
  const node=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el};
  const add=(el,...children)=>{children.forEach(child=>el.append(child));return el};
  const control=(text,fn,cls="play-secondary")=>{const el=node("button",cls,text);el.type="button";el.addEventListener("click",fn);return el};
  const state={active:null,filter:"new",caseIndex:0,answers:Array(CASES.length).fill(null),flipped:Array(CASES.length).fill(null).map(()=>[false,false,false]),mode:"batch",urgent:true};
  let pendingNavigationFocus;
  const classicTabs=q(".play-tabs"),sessionControls=q(".play-session-controls");
  const panels=["switch","recovery","assist"].map(id=>q("#play-"+id));
  const filter=node("select","lab-collection-select");filter.id="lab-collection-filter";
  [["new","New experiments"],["all","All experiments"],["classic","Classic collection"]].forEach(([value,text])=>{const option=node("option","",text);option.value=value;filter.append(option)});
  const label=node("label","","Browse the collection");label.htmlFor=filter.id;
  const count=node("p","lab-catalog-count");count.setAttribute("role","status");
  const grid=node("div","lab-catalog-grid");
  add(catalog,add(node("div","lab-catalog-toolbar"),add(node("div"),label,filter),count),grid);
  filter.addEventListener("change",()=>{state.filter=filter.value;drawCatalog()});
  function drawCatalog(){
    grid.replaceChildren();
    const shown=CATALOG.filter(entry=>state.filter==="all"||entry.status===state.filter);
    count.textContent=shown.length+" experiments · "+CATALOG.filter(entry=>entry.status==="new").length+" new + "+CATALOG.filter(entry=>entry.status==="classic").length+" classics available";
    shown.forEach(entry=>{
      const card=node("article","lab-catalog-card"),symbol=node("span","lab-catalog-symbol",entry.glyph);symbol.setAttribute("aria-hidden","true");
      const title=node("h3","",entry.title),open=control("Open experiment →",()=>navigate(entry.id),"play-primary");open.dataset.labOpen=entry.id;open.setAttribute("aria-label","Open "+entry.title);
      add(card,add(node("div","lab-catalog-meta"),node("span","",entry.status==="new"?"NEW · NOVEMBER":"CLASSIC"),node("span","",entry.duration)),symbol,title,node("p","",entry.description),node("p","lab-catalog-topic",entry.topic),open);
      grid.append(card);
    });
  }
  function hideClassics(){
    if(classicTabs)classicTabs.hidden=true;
    panels.forEach(panel=>{if(panel)panel.hidden=true});
    if(sessionControls)sessionControls.hidden=true;
    document.dispatchEvent(new CustomEvent("observatory:lab-visibility"));
  }
  function navigate(id){
    const hash=id?"#lab?experiment="+encodeURIComponent(id):"#lab";
    if(view.location.hash===hash){if(pendingNavigationFocus===undefined)select(id,true);return}
    // Expose the new controls only after the hash router has finished. A
    // synchronous preview here would let a visitor act before navigation settles.
    pendingNavigationFocus=id;
    view.location.hash=hash;
  }
  function routeSelection(){
    const [page,search=""]=view.location.hash.replace(/^#/,"").split("?");
    if(page!=="lab"){const openHelp=q(".lab-help-dialog");if(openHelp)openHelp.close();pendingNavigationFocus=undefined;return}
    const id=new URLSearchParams(search).get("experiment");
    const selected=CATALOG.some(entry=>entry.id===id)?id:null;
    const needsFocus=pendingNavigationFocus!==undefined&&pendingNavigationFocus===selected;
    pendingNavigationFocus=undefined;
    if(selected!==state.active){const openHelp=q(".lab-help-dialog");if(openHelp)openHelp.close()}
    select(selected,needsFocus);
  }
  function select(id,focus){
    if(id===state.active&&id!==null){if(focus)q("#lab-workbench-title")?.focus();return}
    state.active=id;hideClassics();workbench.replaceChildren();
    catalog.hidden=Boolean(id);workbench.hidden=!id;
    if(!id){if(focus)filter.focus();return}
    const entry=CATALOG.find(item=>item.id===id);
    const back=control("← Experiment collection",()=>navigate(null));back.id="lab-back-to-catalog";
    const title=node("h2","lab-workbench-title",entry.title);title.id="lab-workbench-title";title.tabIndex=-1;
    const version=node("p","lab-workbench-meta",entry.topic+" · "+entry.duration+" · v"+entry.version);
    add(workbench,add(node("div","lab-workbench-header"),back,add(node("div"),title,version)));
    if(entry.status==="classic"){
      if(classicTabs)classicTabs.hidden=false;
      if(sessionControls)sessionControls.hidden=false;
      document.dispatchEvent(new CustomEvent("observatory:lab-activate",{detail:id}));
    } else if(id==="evidence-detective")drawDetective();else drawStudio();
    if(focus)title.focus();
  }
  function helpDialog(title,texts,opener){
    const dialog=node("dialog","lab-help-dialog"),heading=node("h2","",title);heading.id="lab-help-title";dialog.setAttribute("aria-labelledby",heading.id);
    const close=control("Close",()=>dialog.close());
    add(dialog,heading,...texts.map(text=>node("p","",text)),close);document.body.append(dialog);
    dialog.addEventListener("click",event=>{if(event.target===dialog)dialog.close()});
    dialog.addEventListener("close",()=>{dialog.remove();document.dispatchEvent(new CustomEvent("observatory-layer-change"));if(opener.isConnected)opener.focus()});
    dialog.showModal();document.dispatchEvent(new CustomEvent("observatory-layer-change"));close.focus();
  }
  function drawDetective(){
    const stage=node("div","lab-detective"),toolbar=node("div","lab-activity-toolbar"),picker=node("select","lab-collection-select");picker.id="lab-case-picker";
    const pickerLabel=node("label","","Choose a dossier");pickerLabel.htmlFor=picker.id;
    CASES.forEach((item,index)=>{const option=node("option","",(index+1)+" · "+item.title);option.value=String(index);picker.append(option)});picker.value=String(state.caseIndex);
    picker.addEventListener("change",()=>{state.caseIndex=Number(picker.value);drawCase()});
    const reset=control("Start over",()=>{state.answers.fill(null);state.flipped=CASES.map(()=>[false,false,false]);state.caseIndex=0;picker.value="0";drawCase();reset.focus()});reset.id="lab-detective-reset";
    add(toolbar,add(node("div"),pickerLabel,picker),reset);stage.append(toolbar);
    const content=node("div");content.id="lab-detective-case";stage.append(content);workbench.append(stage);
    function drawCase(){
      content.replaceChildren();const example=CASES[state.caseIndex];
      const progress=node("div","lab-case-progress");progress.setAttribute("aria-label",state.answers.filter(Boolean).length+" of "+CASES.length+" dossiers checked");
      CASES.forEach((item,index)=>{const dot=node("span",state.answers[index]?"is-done":"",String(index+1));dot.setAttribute("aria-hidden","true");progress.append(dot)});
      const claim=node("blockquote","lab-claim",example.claim);claim.id="lab-detective-claim";
      add(content,node("p","lab-fiction-label","Fictional evidence dossier · no real study is described"),progress,node("p","eyebrow","THE CLAIM"),claim,node("p","","Turn over each card, then decide whether this wording fits the evidence."));
      const cards=node("div","lab-evidence-cards");
      example.cards.forEach((card,index)=>{
        const flip=control("",()=>{state.flipped[state.caseIndex][index]=!state.flipped[state.caseIndex][index];face()},"lab-evidence-card");flip.dataset.evidenceCard=String(index);
        function face(){const turned=state.flipped[state.caseIndex][index];flip.classList.toggle("is-flipped",turned);flip.setAttribute("aria-pressed",String(turned));flip.setAttribute("aria-label",card.label+(turned?" "+card.detail+" Flip back.":" Reveal evidence."));flip.replaceChildren(node("span","lab-card-number","0"+(index+1)),node("strong","",card.label),node("span","lab-card-copy",turned?card.detail:"Tap to inspect"),node("span","lab-card-action",turned?"↶ Turn back":"↻ Reveal evidence"))}
        face();cards.append(flip);
      });content.append(cards);
      const choices=node("div","lab-verdicts");choices.setAttribute("role","group");choices.setAttribute("aria-label","Your verdict");
      [["supported","Fits the evidence"],["overreach","Claims too much"],["unanswered","Question not studied"]].forEach(([value,text])=>{const answer=control(text,()=>{state.answers[state.caseIndex]=value;drawCase();q("#lab-detective-feedback").focus()},"lab-verdict");answer.dataset.labVerdict=value;answer.setAttribute("aria-pressed",String(state.answers[state.caseIndex]===value));choices.append(answer)});
      add(content,node("h3","","Your verdict"),choices);
      if(state.answers[state.caseIndex]){
        const feedback=node("div","lab-detective-feedback");feedback.id="lab-detective-feedback";feedback.tabIndex=-1;feedback.setAttribute("role","status");
        add(feedback,node("strong","",state.answers[state.caseIndex]===example.verdict?"You matched the claim to the evidence.":"Reconsider the scope of the claim."),node("p","",example.explanation),node("p","lab-takeaway",example.takeaway));
        const next=control(state.caseIndex<CASES.length-1?"Next dossier →":"Return to first dossier",()=>{state.caseIndex=(state.caseIndex+1)%CASES.length;picker.value=String(state.caseIndex);drawCase();q("#lab-detective-claim").tabIndex=-1;q("#lab-detective-claim").focus()},"play-primary");next.id="lab-detective-next";feedback.append(next);content.append(feedback);
      }
    }
    drawCase();
    const help=control("How to use this experiment",()=>helpDialog("Read the claim against the evidence",["All three dossiers are fictional. The feedback follows the evidence supplied on the cards.","The goal is to practice matching a claim to its participants, design, and measured outcome. This is not a test of your ability or a score of the website’s research."],help));stage.append(help);
  }
  function drawStudio(){
    const stage=node("div","lab-studio"),controls=node("div","lab-studio-controls"),mode=node("select","lab-collection-select");mode.id="lab-notification-policy";
    [["immediate","As they arrive"],["batch","Every 10 minutes"],["end","At the end"]].forEach(([value,text])=>{const option=node("option","",text);option.value=value;mode.append(option)});mode.value=state.mode;
    const label=node("label","","Deliver non-urgent messages");label.htmlFor=mode.id;
    const urgent=node("input");urgent.type="checkbox";urgent.id="lab-urgent-bypass";urgent.checked=state.urgent;
    const urgentLabel=node("label","lab-checkbox-label");add(urgentLabel,urgent,node("span","","Let urgent messages through immediately"));
    const reset=control("Reset simulation",()=>{state.mode="batch";state.urgent=true;mode.value=state.mode;urgent.checked=true;render();reset.focus()});reset.id="lab-notification-reset";
    add(controls,add(node("div"),label,mode),urgentLabel,reset);
    const output=node("div","lab-studio-output");output.id="lab-notification-output";
    add(stage,node("p","lab-fiction-label","Simulated 30-minute session · 12 invented messages"),node("p","","Change the delivery rule. The messages stay the same; the timing changes."),controls,output);workbench.append(stage);
    mode.addEventListener("change",()=>{state.mode=mode.value;render()});urgent.addEventListener("change",()=>{state.urgent=urgent.checked;render()});
    function render(){
      const plan=notificationPlan(state.mode,state.urgent);output.replaceChildren();
      const metrics=node("dl","lab-simulation-metrics");
      [["Alert moments",String(plan.alerts)],["Average wait",plan.meanWait.toFixed(1)+" min"],["Longest gap",plan.longestGap+" min"]].forEach(([name,value])=>add(metrics,add(node("div"),node("dt","",name),node("dd","",value))));output.append(metrics);
      const status=node("p","lab-simulation-summary",plan.alerts+" alert moment"+(plan.alerts===1?"":"s")+". Urgent messages wait up to "+plan.urgentWait+" minutes.");status.setAttribute("role","status");status.id="lab-notification-summary";output.append(status);
      const timeline=node("div","lab-timeline");timeline.setAttribute("aria-label","Delivery timeline, from minute 0 to minute 30");
      for(let minute=0;minute<=30;minute++){
        const messages=plan.deliveries.filter(message=>message.delivered===minute);
        const tick=node("div","lab-timeline-tick"+(messages.length?" has-alert":""));
        const mark=node("span","lab-timeline-mark");mark.setAttribute("aria-hidden","true");tick.append(mark);
        if(messages.length){const dot=node("span","lab-timeline-dot");dot.style.height=(10+messages.length*6)+"px";dot.setAttribute("aria-label","Minute "+minute+": "+messages.length+" messages");tick.append(dot)}
        if(minute%10===0)tick.append(node("span","lab-timeline-time",String(minute)));
        timeline.append(tick);
      }
      add(output,node("h3","","When alerts arrive"),timeline,node("p","lab-timeline-key","Red bars mark delivery times. Taller bars contain more messages. The labels show minutes from the start."));
      const inspect=node("select","lab-collection-select");inspect.id="lab-delivery-picker";
      plan.moments.forEach(minute=>{const amount=plan.deliveries.filter(message=>message.delivered===minute).length;const option=node("option","","Minute "+minute+" · "+amount+" message"+(amount===1?"":"s"));option.value=String(minute);inspect.append(option)});inspect.value=String(plan.moments[0]);
      const inspectLabel=node("label","","Inspect a delivery");inspectLabel.htmlFor=inspect.id;
      const inspectButton=control("Open delivery card",()=>{const minute=Number(inspect.value);helpDialog("Minute "+minute,plan.deliveries.filter(message=>message.delivered===minute).map(message=>message.text+" · arrived at "+message.at+" min · waited "+(message.delivered-message.at)+" min"),inspectButton)});inspectButton.id="lab-inspect-delivery";
      add(output,add(node("div","lab-delivery-inspector"),add(node("div"),inspectLabel,inspect),inspectButton));
      const tradeoff=node("ul","lab-tradeoffs");
      [plan.alerts<12?"Batching creates fewer delivery moments in this simulation.":"Immediate delivery creates one alert for each message.",plan.meanWait>0?"Fewer delivery moments come with waiting time.":"Every message arrives without a scheduled wait.","A quiet gap is time without a simulated alert, not a measure of attention or productivity."].forEach(text=>tradeoff.append(node("li","",text)));output.append(tradeoff);
    }
    render();
    const help=control("How the simulation works",()=>helpDialog("A transparent timing model",["The same 12 invented messages arrive at minutes 2, 4, 6, 8, 11, 13, 16, 18, 21, 23, 26, and 28. Two are marked urgent.","Immediate delivery uses arrival time. Batches round delivery up to minute 10, 20, or 30. End-only delivery uses minute 30. The urgent exception overrides those rules.","Messages delivered at the same minute count as one alert moment. Average wait is delivery time minus arrival time, averaged across the 12 messages. Longest gap includes the start and end of the session.","These are model outputs, not study results or predictions about your concentration."],help));stage.append(help);
  }
  q("#play-reset").addEventListener("click",()=>{state.answers.fill(null);state.flipped=CASES.map(()=>[false,false,false]);state.caseIndex=0;state.mode="batch";state.urgent=true;const active=state.active;if(active&& !["switch","recovery","assist"].includes(active)){state.active=null;select(active,false)}});
  document.addEventListener("observatory:lab-classic",event=>{
    if(!["switch","recovery","assist"].includes(state.active))return;
    state.active=event.detail;const entry=CATALOG.find(item=>item.id===event.detail);
    const title=q("#lab-workbench-title");if(title)title.textContent=entry.title;const meta=q(".lab-workbench-meta");if(meta)meta.textContent=entry.topic+" · "+entry.duration+" · v"+entry.version;
    if(view.location.hash.startsWith("#lab"))view.history.replaceState(null,"","#lab?experiment="+entry.id);
  });
  // Hash changes cover catalog links and browser Back/Forward. Processing both
  // popstate and hashchange would expose controls before the outer hash router.
  view.addEventListener("hashchange",routeSelection);
  drawCatalog();hideClassics();routeSelection();
})();
