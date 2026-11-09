/* Attention Playground — experimental, client-side interactions.
   No API, account, analytics, localStorage or persistence. NOT a cognitive test. */
(() => {
  "use strict";
  const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
  const E=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=String(txt);return n};
  const add=(p,...kids)=>{kids.filter(Boolean).forEach(n=>p.append(n));return p};
  const button=(label,fn,cls="")=>{const n=E("button",cls,label);n.type="button";n.addEventListener("click",fn);return n};
  const interpretation=(title,...paragraphs)=>{
    const root=E("details","play-result-details"),body=E("div","play-result-details-body");
    paragraphs.forEach(text=>body.append(E("p","play-chart-caption",text)));
    return add(root,E("summary","",title),body);
  };
  const reflection=(title,questions,note)=>{
    const root=add(E("div","play-reflection"),E("p","play-kicker","REFLECT"),E("h5","",title));
    if(questions.length===1)root.append(E("p","",questions[0]));
    else{const list=E("ul","");questions.forEach(text=>list.append(E("li","",text)));root.append(list)}
    if(note)root.append(E("p","play-reflection-note",note));
    return root;
  };
  const round=n=>Math.round(n);
  const med=xs=>{if(!xs.length)return 0;const a=xs.slice().sort((x,y)=>x-y);return a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2};
  const practice={switch:{active:false,trial:0,results:[],current:null,locked:false,shownAt:null,interrupted:false,timer:null,generation:0,kind:"snapshot",timed:true,length:20},recovery:{mode:"cue",stage:"ready",interrupt:0,correct:0,start:0,history:[],round:0,interrupted:false,comparison:null,comparisonCount:0},assist:{mode:"reflect",scenario:0,chosen:false}};
  // The result heading receives focus. Avoid a second, full-history announcement.
  $("#recovery-history").setAttribute("aria-live","off");
  function activate(name){
    $$("[data-play-tab]").forEach(b=>{let on=b.dataset.playTab===name;b.classList.toggle("is-active",on);b.setAttribute("aria-selected",String(on));b.tabIndex=on?0:-1});
    ["switch","recovery","assist"].forEach(k=>$("#play-"+k).hidden=k!==name);
    syncVisibility();
  }
  $$("[data-play-tab]").forEach(b=>{
    b.addEventListener("click",()=>activate(b.dataset.playTab));
    b.addEventListener("keydown",e=>{if(!["ArrowRight","ArrowLeft","Home","End"].includes(e.key))return;e.preventDefault();e.stopPropagation();const all=$$("[data-play-tab]");let i=all.indexOf(b);let next=all[e.key==="Home"?0:e.key==="End"?all.length-1:(i+(e.key==="ArrowRight"?1:-1)+all.length)%all.length];next.focus();activate(next.dataset.playTab)});
  });
  const visible=name=>!document.hidden&&!$("#lab").hidden&&!$("#play-"+name).hidden;
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
    const timesA=repeat.filter(x=>x.correct&&x.rt!==null).map(x=>x.rt),timesB=mixed.filter(x=>x.correct&&x.rt!==null).map(x=>x.rt);
    const rtA=timesA.length?round(med(timesA)):null,rtB=timesB.length?round(med(timesB)):null;
    const accA=repeat.filter(x=>x.correct).length,accB=mixed.filter(x=>x.correct).length;
    add(root,E("p","play-kicker",g.timed?"SESSION SNAPSHOT":"UNTIMED SESSION SNAPSHOT"),E("h4","","Repeat vs. switching"));
    const chart=E("div","play-chart"),maximum=Math.max(rtA??0,rtB??0,1);
    [["Same rule",rtA,accA,8],["Alternating",rtB,accB,12]].forEach(([name,ms,good,total])=>{
      const r=E("div","play-chart-line"),bar=E("div","play-chart-track"),fill=E("span","play-chart-fill");
      fill.style.width=((ms??0)/maximum*100)+"%";bar.append(fill);
      add(r,E("span","",name),g.timed?bar:null,E("strong","",g.timed?(ms===null?"—":ms+" ms"):good+" / "+total+" correct"));if(!g.timed)r.classList.add("play-chart-untimed");chart.append(r);
      const note=E("p","play-chart-sub",good+" / "+total+" correct");if(g.timed)chart.append(note);
    });
    const omitted=g.results.filter(x=>x.interrupted).length;
    if(g.timed&&omitted)chart.append(E("p","play-chart-caption",omitted+" interrupted response(s) excluded from timing."));
    add(root,E("p","play-result-metric",g.timed?"Median response time · uninterrupted correct responses only.":"No response times were recorded."),chart);
    if(g.timed&&(rtA===null||rtB===null))root.append(E("p","play-result-metric","— means no uninterrupted correct response time is available for that block."));
    add(root,E("p","play-result-limit","This fixed-order, small-sample activity cannot estimate switch cost or attention. Faster is not necessarily better real-world attention."),interpretation("Timing, order and limitations",(g.timed?"Medians from uninterrupted correct responses only. Device, browser and input method affect timing. ":"No response times were recorded. ")+"The same rule always comes first (8 turns), followed by alternating rules (12 turns). Fixed order, small samples and practice effects prevent a valid estimate of switch cost or attention. Faster is not necessarily better real-world attention."),reflection("What felt most effortful?",["Keeping the rule in mind","Noticing the cue","Choosing a response"],"This comparison cannot tell those processes apart."));
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
    add(history,E("p","play-kicker","YOUR LAST "+Math.min(r.history.length,4)+" SINGLE ROUNDS"),table,E("p","play-result-metric","Timing starts when return choices appear; leaving the activity excludes timing."),E("p","play-result-limit","These rounds cannot establish whether checkpoints improve performance. You choose condition and order, and the checkpoint repeats the intended answer."),interpretation("Task differences and practice","Timings begin when the return choices appear and are omitted after leaving the activity. Task numbers identify different materials; repeats introduce practice. You choose condition and order, and the checkpoint repeats the intended answer. These rounds cannot establish whether checkpoints improve performance."),reflection("Carry it into your work",["What information would help you resume your own work?"]));
  }
  function recoveryComparisonFinish(){
    const c=practice.recovery.comparison,root=$("#recovery-comparison-results");
    root.replaceChildren();root.hidden=false;
    add(root,E("p","play-kicker","TWO ROUNDS · ONE EXPLORATION"),E("h4","","What helped you return?"));
    const list=E("ol","recovery-comparison-list");
    c.results.forEach(x=>{const row=E("li","recovery-comparison-result");
      add(row,E("strong","","Round "+x.round+" · Pair "+(c.pairIndex+1)+", Task "+"AB"[x.variant]+" · "+modeName(x.mode)),E("p","",(x.correct?"Intended next step":"Different choice")+" · "+(x.ms===null?"timing omitted after leaving this activity":x.ms+" ms to choose")));list.append(row)});
    const facts=E("ul","play-result-facts");
    ["Tasks are not validated as equally difficult.","Timing includes reading and input differences; faster does not mean better real-world attention."].forEach(text=>facts.append(E("li","",text)));
    add(root,list,E("p","play-result-metric","Interrupted timings are omitted; no difference score is calculated."),E("p","play-result-limit","Two responses do not estimate a checkpoint effect. The checkpoint repeats the intended answer."),facts,interpretation("Task design, random order and limitations","Each condition appeared once, using different versions of a parallel fictional task. Starting condition and task order were randomized independently. These materials are not validated as equally difficult. The same four distractions repeat, so practice, wording and order can still shape your experience.","Two responses do not estimate a checkpoint effect. The checkpoint repeats the intended answer, timing includes reading and input differences, and faster does not mean better real-world attention. Interrupted timings are omitted; no difference score is calculated."),reflection("What helped you return?",["Did the checkpoint help you recover the task context, or simply reveal the answer?","What would a useful checkpoint need to preserve in your own work?"]));
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
  // 3 / Assistance Dial: explore four fictional research-interpretation decisions.
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
      feedback:"Assisted performance and retained learning are distinct outcomes. A delayed, unassisted assessment would help test the learning claim."}
  ];
  function assistDraw(){
    const r=practice.assist,data=scenarios[r.scenario];r.chosen=false;
    $("#assist-counter").textContent="SCENARIO "+(r.scenario+1)+" / "+scenarios.length;
    $("#assist-prompt").textContent=data.prompt;
    const reply=$("#assist-reply");reply.replaceChildren();
    const box=E("div","assist-bubble");
    add(box,E("span","assist-bubble-label",r.mode==="reflect"?"REFLECTION FIRST":r.mode==="hint"?"JUST A HINT":"FULL ANSWER"),E("p","",data.modes[r.mode]));
    reply.append(box);
    $("#assist-feedback").hidden=true;$("#assist-next").hidden=true;
    const choices=$("#assist-choices");choices.replaceChildren();
    data.options.forEach((x,i)=>choices.append(button(x,()=>assistChoose(i),"assist-option")));
  }
  function assistChoose(i){
    const r=practice.assist;if(r.chosen)return;r.chosen=true;
    const data=scenarios[r.scenario],ok=i===data.correct;
    $$("#assist-choices .assist-option").forEach((b,n)=>{b.disabled=true;if(n===data.correct)b.classList.add("correct");if(n===i&&!ok)b.classList.add("incorrect")});
    const root=$("#assist-feedback");root.replaceChildren();
    add(root,E("strong","",ok?"✓ Supported conclusion":"↩ Another interpretation is stronger"),E("p","",data.feedback));
    root.hidden=false;$("#assist-next").hidden=false;root.focus();
    $("#assist-next").textContent=r.scenario<scenarios.length-1?"Try another scenario":"Replay the first scenario";
  }
  $$("[data-assist-mode]").forEach(b=>b.addEventListener("click",()=>{
    const r=practice.assist;r.mode=b.dataset.assistMode;
    $$("[data-assist-mode]").forEach(x=>{let active=x===b;x.classList.toggle("is-active",active);x.setAttribute("aria-pressed",String(active))});
    assistDraw();$("#assist-prompt").focus();
  }));
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


