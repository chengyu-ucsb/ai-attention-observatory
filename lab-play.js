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
  const practice={switch:{active:false,trial:0,results:[],current:null,locked:false,shownAt:0},recovery:{mode:"cue",stage:"ready",interrupt:0,correct:0,start:0,history:[],round:0},assist:{mode:"reflect",scenario:0,chosen:false}};
  function activate(name){
    $$("[data-play-tab]").forEach(b=>{let on=b.dataset.playTab===name;b.classList.toggle("is-active",on);b.setAttribute("aria-selected",String(on));b.tabIndex=on?0:-1});
    ["switch","recovery","assist"].forEach(k=>$("#play-"+k).hidden=k!==name);
    if(name!=="switch"&&practice.switch.active){
      // Navigation away should never count as a prolonged reaction-time trial.
      practice.switch.shownAt=0;
      $("#switch-note").textContent="Return to the tab and use the buttons to respond.";
    } else if(name==="switch"&&practice.switch.active&&practice.switch.shownAt===0)practice.switch.shownAt=performance.now();
  }
  $$("[data-play-tab]").forEach(b=>{
    b.addEventListener("click",()=>activate(b.dataset.playTab));
    b.addEventListener("keydown",e=>{if(e.key!=="ArrowRight"&&e.key!=="ArrowLeft")return;e.preventDefault();const all=$$("[data-play-tab]");let i=all.indexOf(b);let next=all[(i+(e.key==="ArrowRight"?1:-1)+all.length)%all.length];next.focus();activate(next.dataset.playTab)});
  });
  // 1 / Switch Lab: repeat a single rule, then alternate parity and magnitude.
  const choices=[1,2,3,4,6,7,8,9];
  const challengeLength=20;
  const switchTrack=$("#switch-track");
  for(let i=0;i<challengeLength;i++)switchTrack.append(E("span","switch-dot"));
  function switchCue(rule){return rule==="parity"?"ODD OR EVEN?":"LOW (1–4) OR HIGH (6–9)?"}
  function switchRender(){
    const g=practice.switch,phase=g.trial<8?"SAME RULE":"SWITCHING RULES";
    $("#switch-phase").textContent=phase;
    $("#switch-progress").textContent=(g.trial+1)+" / "+challengeLength;
    $("#switch-cue").textContent=switchCue(g.current.rule);
    $("#switch-number").textContent=g.current.value;
    $("#switch-note").textContent=g.current.rule==="parity"?"LEFT = ODD     ·     RIGHT = EVEN":"LEFT = LOW     ·     RIGHT = HIGH";
    $("#switch-left").disabled=false;$("#switch-right").disabled=false;
    $("#switch-start").hidden=true;
    $$(".switch-dot").forEach((d,i)=>{d.className="switch-dot";if(i<g.trial)d.classList.add(g.results[i].correct?"is-correct":"is-wrong");else if(i===g.trial)d.classList.add("is-now")});
    g.locked=false;g.shownAt=performance.now();
  }
  function nextSwitch(){
    const g=practice.switch;
    if(g.trial>=challengeLength){switchFinish();return}
    const value=choices[Math.floor(Math.random()*choices.length)];
    let rule=g.trial<8?"parity":(g.trial%2===0?"parity":"magnitude");
    g.current={value,rule};
    switchRender();
  }
  function startSwitch(){
    const g=practice.switch;g.active=true;g.trial=0;g.results=[];g.locked=false;
    $("#switch-results").hidden=true;$("#switch-results").replaceChildren();
    $("#switch-start").textContent="Play again";nextSwitch();
  }
  function respond(side){
    const g=practice.switch;
    if(!g.active||g.locked||$("#play-switch").hidden||g.shownAt===0)return;
    const item=g.current;
    const correctSide=item.rule==="parity"?(item.value%2?"left":"right"):(item.value<5?"left":"right");
    const rt=Math.round(performance.now()-g.shownAt);
    const correct=correctSide===side;
    g.results.push({phase:g.trial<8?"repeat":"alternate",rt,correct,rule:item.rule,value:item.value});
    g.locked=true;$("#switch-left").disabled=true;$("#switch-right").disabled=true;
    $("#switch-note").textContent=correct?"✓ Correct":"↪ Different rule—keep going";
    g.trial+=1;g.shownAt=0;
    setTimeout(()=>{if(g.active)nextSwitch()},correct?240:480);
  }
  function switchFinish(){
    const g=practice.switch;g.active=false;
    $("#switch-phase").textContent="COMPLETE";
    $("#switch-progress").textContent="20 / 20";
    $("#switch-cue").textContent="YOUR PLAY SESSION";
    $("#switch-number").textContent="✓";
    $("#switch-note").textContent="What did you notice about changing rules?";
    $("#switch-start").hidden=false;$("#switch-start").textContent="Play again";
    const repeat=g.results.filter(x=>x.phase==="repeat"),mixed=g.results.filter(x=>x.phase==="alternate");
    const rtA=round(med(repeat.filter(x=>x.correct).map(x=>x.rt)));
    const rtB=round(med(mixed.filter(x=>x.correct).map(x=>x.rt)));
    const accA=repeat.filter(x=>x.correct).length,accB=mixed.filter(x=>x.correct).length;
    const root=$("#switch-results");root.replaceChildren();root.hidden=false;
    add(root,E("p","play-kicker","SESSION SNAPSHOT"),E("h4","","Repeat vs. switching"));
    const chart=E("div","play-chart"),maximum=Math.max(rtA,rtB,1);
    [["Same rule",rtA,accA,8],["Alternating",rtB,accB,12]].forEach(([name,ms,good,total])=>{
      const r=E("div","play-chart-line"),bar=E("div","play-chart-track"),fill=E("span","play-chart-fill");
      fill.style.width=(ms/maximum*100)+"%";bar.append(fill);
      add(r,E("span","",name),bar,E("strong","",ms?ms+" ms":"—"));chart.append(r);
      const note=E("p","play-chart-sub",good+" / "+total+" correct");chart.append(note);
    });
    add(root,chart,E("p","play-chart-caption","Medians from correct responses in this single play session. Fixed order, small trial counts and practice effects make this an experience—not a valid measure of switch cost or attention."));
  }
  $("#switch-start").addEventListener("click",startSwitch);
  $("#switch-left").addEventListener("click",()=>respond("left"));
  $("#switch-right").addEventListener("click",()=>respond("right"));
  document.addEventListener("keydown",e=>{
    if($("#lab").hidden||$("#play-switch").hidden||e.altKey||e.ctrlKey||e.metaKey||/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName||""))return;
    if(e.key==="ArrowLeft"||e.key==="ArrowRight"){e.preventDefault();respond(e.key==="ArrowLeft"?"left":"right")}
  });
  document.addEventListener("visibilitychange",()=>{const g=practice.switch;if(document.hidden&&g.active)g.shownAt=0;else if(!document.hidden&&g.active&&!$("#play-switch").hidden)g.shownAt=performance.now()});
  // 2 / Return Point: contextual resumption after a small distraction.
  const recoveryCases=[
    {context:"You're writing about AI and attention. You've read two studies about cognitive effort.",next:"Compare the two studies' measures",options:["Format the references","Compare the two studies' measures","Export your calendar"]},
    {context:"You're preparing a group presentation. Your slides are drafted but not yet connected to your argument.",next:"Connect slide evidence to your central claim",options:["Choose a cover color","Connect slide evidence to your central claim","Book next month's room"]}
  ];
  const distractions=[
    {prompt:"Tap the symbol that appears twice",options:["◇","●","◇ ◇"],right:2},
    {prompt:"Which number is smallest?",options:["19","7","13"],right:1},
    {prompt:"Find the different shape",options:["□","□","△"],right:2},
    {prompt:"Which word has four letters?",options:["focus","plan","think"],right:1}
  ];
  function recoveryPreview(){
    const r=practice.recovery,story=recoveryCases[r.round%recoveryCases.length];
    r.stage="ready";r.interrupt=0;r.correct=0;r.start=0;
    $("#recovery-stage-label").textContent="THE TASK";
    $("#recovery-progress").textContent="STAGE 1 / 3";
    $("#recovery-headline").textContent="A half-finished project";
    $("#recovery-description").textContent=story.context+" Your next action: "+story.next+".";
    $("#recovery-interaction").replaceChildren();
    $("#recovery-start").hidden=false;$("#recovery-start").textContent="Begin interruption ↗";
  }
  $$("[data-recovery-mode]").forEach(btn=>btn.addEventListener("click",()=>{
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
    stim.options.forEach((t,i)=>options.append(button(t,()=>{
      if(r.stage!=="interrupt")return;
      if(i===stim.right)r.correct++;
      r.interrupt++;
      recoveryDistract();
    },"recovery-option")));
    add(place,E("p","play-kicker","MICRO-TASK "+(r.interrupt+1)+" / 4"),options);
  }
  function recoveryReturn(){
    const r=practice.recovery; r.stage="return";
    const story=recoveryCases[r.round%recoveryCases.length];
    $("#recovery-stage-label").textContent="BACK TO YOUR WORK";
    $("#recovery-progress").textContent="STAGE 3 / 3";
    $("#recovery-headline").textContent="What was your next step?";
    $("#recovery-description").textContent="Choose the step that continues your project.";
    const place=$("#recovery-interaction");place.replaceChildren();
    if(r.mode==="cue"){add(place,E("div","recovery-cue","↩  CHECKPOINT   ·   "+story.next))}
    const options=E("div","recovery-options recovery-return-options");
    r.start=performance.now();
    story.options.forEach((choice)=>options.append(button(choice,()=>recoveryFinish(choice===story.next), "recovery-option")));
    place.append(options);
  }
  function recoveryFinish(correct){
    const r=practice.recovery;if(r.stage!=="return")return;r.stage="done";
    const elapsed=Math.max(0,round(performance.now()-r.start));
    r.history.push({mode:r.mode,correct,ms:elapsed});
    $("#recovery-stage-label").textContent="SESSION COMPLETE";
    $("#recovery-progress").textContent="DONE";
    $("#recovery-headline").textContent=correct?"Found your return point.":"Returning isn't always simple.";
    $("#recovery-description").textContent=(correct?"You selected the intended next step.":"You selected a different step.")+" How did the checkpoint change the experience?";
    const place=$("#recovery-interaction");place.replaceChildren();
    add(place,E("div","recovery-outcome",correct?"✓ Correct next action":"↩ Notice what was lost"),E("div","recovery-time",elapsed+" ms to choose"));
    $("#recovery-start").hidden=false;$("#recovery-start").textContent="Try another round ↗";
    const history=$("#recovery-history");history.replaceChildren();
    const table=E("div","recovery-trial-list");
    r.history.slice(-4).forEach((x,i)=>{let row=E("div","recovery-trial");add(row,E("span","",x.mode==="cue"?"With checkpoint":"Without checkpoint"),E("strong","",round(x.ms/100)/10+" s  ·  "+(x.correct?"correct":"different choice")));table.append(row)});
    add(history,E("p","play-kicker","YOUR LAST "+Math.min(r.history.length,4)+" ROUNDS"),table,E("p","play-chart-caption","These timings begin when the return choices appear. Trials differ in materials and order; they cannot establish whether checkpoints improve performance."));
  }
  $("#recovery-start").addEventListener("click",()=>{
    const r=practice.recovery;if(r.stage==="done"){r.round++;recoveryPreview();recoveryDistract();return}
    if(r.stage==="ready")recoveryDistract();
  });
  recoveryPreview();
  // 3 / Assistance Dial: branch through two study-design decisions.
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
      feedback:"Random assignment is helpful for causal interpretation of the measured outcome, while external validity and whether focus itself improves remain separate questions."}
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
    root.hidden=false;$("#assist-next").hidden=false;
    $("#assist-next").textContent=r.scenario===0?"Try another scenario ↗":"Replay the first scenario ↗";
  }
  $$("[data-assist-mode]").forEach(b=>b.addEventListener("click",()=>{
    const r=practice.assist;r.mode=b.dataset.assistMode;
    $$("[data-assist-mode]").forEach(x=>{let active=x===b;x.classList.toggle("is-active",active);x.setAttribute("aria-pressed",String(active))});
    assistDraw();
  }));
  $("#assist-next").addEventListener("click",()=>{practice.assist.scenario=(practice.assist.scenario+1)%scenarios.length;assistDraw()});
  assistDraw();
  activate("switch");
})();