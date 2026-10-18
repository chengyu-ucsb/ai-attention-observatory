"use strict";
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const root=path.resolve(__dirname,".."),text=p=>fs.readFileSync(path.join(root,p),"utf8");
const issue=JSON.parse(text("data/public-issue.json"));
const weekly=JSON.parse(text("data/public-weekly.json"));
const site=text("index.html"),app=text("app.js"),newsletter=text("newsletter.html");
assert.equal(issue.source_count,weekly.items.length,"Issue shelf must cover entire weekly reading set");
assert.deepEqual(new Set(issue.sources.map(s=>s.id)),new Set(weekly.items.map(s=>(s.doi||"").toLowerCase()||s.url||s.title)));
assert(issue.sources.every(s=>s.reading_level!=="citation_only"),"Citation-only source cannot enter an issue");
assert(site.includes('id="issue"')&&site.includes('id="weekly-title"'),"Weekly issue not discoverable");
assert(app.includes("function renderIssue()"),"Missing issue renderer");
if(issue.status==="published"){
 assert(issue.signals.length>=3&&issue.signals.length<=4,"A small number of cross-source signals is required");
 for(const sig of issue.signals){
  assert(sig.source_ids.length>=2,"Each cross-source signal needs multiple sources");
  for(const id of sig.source_ids)assert(issue.sources.some(s=>s.id===id),"Unresolved source citation "+id);
 }
 assert(issue.tension.source_ids.length>=2,"Tension must compare multiple sources");
 assert(newsletter.includes(issue.headline.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#x27;"))||newsletter.includes(issue.headline),"Newsletter headline not in HTML");
 assert(!newsletter.includes("unsubscribe here"),"Don't fabricate unsubscribe support");
}else{
 assert(!newsletter.includes("SIGNAL 1"),"No invented newsletter content before editorial review");
}
const rss=text("issue-feed.xml");
assert(rss.includes("The Attention Edit"),"Missing synthesized editorial feed");
console.log("Weekly issue test passed:",issue.status,issue.source_count,"source-backed readings, complete shelf, source-linked themes.");
