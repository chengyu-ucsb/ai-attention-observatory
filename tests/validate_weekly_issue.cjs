"use strict";
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const root=path.resolve(__dirname,".."),text=p=>fs.readFileSync(path.join(root,p),"utf8");
const issue=JSON.parse(text("data/public-issue.json"));
const weekly=JSON.parse(text("data/public-weekly.json"));
const site=text("index.html"),app=text("app.js"),newsletter=text("newsletter.html");
// Every new source must remain in the editorial shelf; older contextual
// readings are allowed only when explicitly identified as previously indexed.
const discoveredIds=new Set(weekly.items.map(s=>(s.doi||"").toLowerCase()||s.url||s.title));
const editorialIds=new Set(issue.sources.map(s=>s.id));
assert.equal(issue.source_count,issue.sources.length,"Editorial source count must match its actual citations");
for(const id of discoveredIds)
 assert(editorialIds.has(id),"Newly indexed source missing from editorial evidence: "+id);
for(const source of issue.sources)
 if(!discoveredIds.has(source.id))
  assert.equal(source.editorial_role,"previously_indexed_context","Older evidence must be transparently marked");
assert.equal(editorialIds.size,issue.sources.length,"Editorial evidence must not contain duplicate sources");
assert(issue.sources.every(s=>s.reading_level!=="citation_only"),"Citation-only source cannot enter an issue");
assert(site.includes('id="issue"')&&site.includes('id="weekly-title"'),"Weekly issue not discoverable");
assert(fs.existsSync(path.join(root,"issues/index.html")),"Missing archived edition directory index");
assert(site.includes('href="issues/"'),"Newsletter archive navigation missing");
assert(site.includes('href="issue-feed.xml" class="issue-rss"'),"Homepage weekly RSS must point to approved editorials, not record feed");
assert(app.includes("function renderIssue()"),"Missing issue renderer");
const deployment=text(".github/workflows/publish.yml");
assert(deployment.includes("Catch up full-text research backlog"),"Catch-up results must trigger a Pages redeployment");
assert(!site.includes('id="issue-source-landscape"'),"Internal source-coverage dashboard should not appear in the public edition");
assert(!site.includes('THE ATTENTION BRIEF · IN PREPARATION'),"Editorial workflow statuses leaked into public markup");
const featured=JSON.parse(text("data/public-featured-issue.json"));
assert(featured.status==="published"||featured.status==="none","Only completed editorials may appear as featured issues");
if(featured.status==="published"){
 assert(featured.headline&&featured.sources.length>0,"Featured issue must have a published headline and citations");
 assert(featured.edition_date<=issue.edition_date,"Featured issue cannot be dated after the weekly indexing run");
 assert(fs.existsSync(path.join(root,"data/approved-issues",featured.edition_date+".json")),"Featured editorial is not archived");
}
if(issue.status==="published"){
 assert(issue.signals.length>=(issue.edition_format==="compact"?1:3)&&issue.signals.length<=4,"A small number of cross-source signals is required");
 for(const sig of issue.signals){
  assert(sig.source_ids.length>=1,"Each signal needs a checked source");
  for(const id of sig.source_ids)assert(issue.sources.some(s=>s.id===id),"Unresolved source citation "+id);
 }
 assert(issue.tension.source_ids.length>=1,"Tension must cite a checked source");
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
// Source-only changes may precede the publication workflow regenerating RSS.
// Preserve the stable subscription endpoint and accept only the two real mastheads;
// current-generator branding is checked independently in test_newsletter_feed.py.
assert(/<channel>\s*<title>The Attention (?:Brief|Edit) \| AI &amp; Attention Observatory<\/title>/.test(rss),"Missing synthesized editorial feed masthead");
assert(/<atom:link\b[^>]*href="https:\/\/chengyu-ucsb\.github\.io\/ai-attention-observatory\/issue-feed\.xml"[^>]*rel="self"[^>]*type="application\/rss\+xml"/.test(rss),"Editorial feed must retain its canonical subscription endpoint");
console.log("Weekly issue test passed:",issue.status,issue.source_count,"source-backed readings, complete shelf, source-linked themes.");
