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
assert(fs.existsSync(path.join(root,"issues/index.html")),"Missing archived edition directory index");
assert(site.includes('href="issues/"'),"Newsletter archive navigation missing");
assert(site.includes('href="issue-feed.xml" class="issue-rss"'),"Homepage weekly RSS must point to approved editorials, not record feed");
assert(app.includes("function renderIssue()"),"Missing issue renderer");
const deployment=text(".github/workflows/publish.yml");
assert(deployment.includes("Catch up full-text research backlog"),"Catch-up results must trigger a Pages redeployment");
assert(!site.includes('id="issue-source-landscape"'),"Internal source-coverage dashboard should not appear in the public edition");
assert(!site.includes('THE ATTENTION EDIT · IN PREPARATION'),"Editorial workflow statuses leaked into public markup");
const featured=JSON.parse(text("data/public-featured-issue.json"));
assert(featured.status==="published"||featured.status==="none","Only completed editorials may appear as featured issues");
if(featured.status==="published"){
 assert(featured.headline&&featured.sources.length>0,"Featured issue must have a published headline and citations");
 assert(featured.edition_date<=issue.edition_date,"Featured issue cannot be dated after the weekly indexing run");
 assert(fs.existsSync(path.join(root,"data/approved-issues",featured.edition_date+".json")),"Featured editorial is not archived");
}
if(issue.status==="published"){
 assert(issue.signals.length>=3&&issue.signals.length<=4,"A small number of cross-source signals is required");
 for(const sig of issue.signals){
  assert(sig.source_ids.length>=2,"Each cross-source signal needs multiple sources");
  for(const id of sig.source_ids)assert(issue.sources.some(s=>s.id===id),"Unresolved source citation "+id);
 }
 assert(issue.tension.source_ids.length>=2,"Tension must compare multiple sources");
 assert(newsletter.includes(issue.headline.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#x27;"))||newsletter.includes(issue.headline),"Newsletter headline not in HTML");
 assert(!newsletter.includes("unsubscribe here"),"Don't fabricate unsubscribe support");
 assert(newsletter.includes(issue.editorial_note.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#x27;")),"Editorial production and evidence limits must be visible");
 const approved="data/approved-issues/"+issue.edition_date+".json";
 const archived="issues/"+issue.edition_date+".html";
 assert(fs.existsSync(path.join(root,approved)),"Published issue missing permanently archived JSON");
 assert(fs.existsSync(path.join(root,archived)),"Published issue missing permanent newsletter HTML");
 assert(text("issue-feed.xml").includes("issues/"+issue.edition_date+".html"),"RSS must link permanent edition");
}else{
 const stored=fs.existsSync(path.join(root,"data/approved-issues"))?fs.readdirSync(path.join(root,"data/approved-issues")).filter(x=>/^\d{4}-\d{2}-\d{2}\.json$/.test(x)).sort().reverse():[];
 if(stored.length){
  const approved=JSON.parse(text("data/approved-issues/"+stored[0]));
  const escaped=approved.headline.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#x27;");
  assert(newsletter.includes(escaped)||newsletter.includes(approved.headline),"In-review week erased the most recently approved letter");
 }else{
  assert(!newsletter.includes("SIGNAL 1"),"No invented newsletter content before editorial review");
 }
}
const rss=text("issue-feed.xml");
assert(rss.includes("The Attention Edit"),"Missing synthesized editorial feed");
console.log("Weekly issue test passed:",issue.status,issue.source_count,"source-backed readings, complete shelf, source-linked themes.");
