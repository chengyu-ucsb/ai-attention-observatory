/* Real Chromium regression: weekly citations/glossary must not alter articles. */
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:8765';
const approved=JSON.parse(fs.readFileSync(path.join(root,'data/public-featured-issue.json'),'utf8'));
const drafts=JSON.parse(fs.readFileSync(path.join(root,'data/issue-editorial.json'),'utf8'));
const draft=drafts['2026-11-07'];
const issue={...approved,...draft,status:'published',citation_schema_version:1};
for(const section of [...issue.signals,issue.tension]){
 section.source_ids=section.sources.map(title=>{
  const hits=issue.sources.filter(source=>source.title.toLowerCase().includes(title.toLowerCase()));
  assert.equal(hits.length,1,'Source title resolution: '+title);return hits[0].id;
 });
 for(const c of section.citations)c.source_id=issue.sources.find(source=>source.title===c.source).id;
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const results=[];
 try{
  for(const mobile of [false,true]){
   const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,hasTouch:mobile});
   const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.route('**/data/public-featured-issue.json*',route=>route.fulfill({json:issue}));
   await page.goto(base+'/#issue');
   await page.waitForSelector('#issue-signals .issue-inline-citation');
   const citation=page.locator('#issue-signals .issue-inline-citation').first();
   assert.match(await citation.getAttribute('href'),/^https:\/\//);
   assert.match(await citation.getAttribute('title'),/./);
   // Open the full analysis with keyboard, then follow a real glossary link.
   const summary=page.locator('#issue-signals .reading-expansion summary').first();
   await summary.focus();await page.keyboard.press('Enter');
   const term=page.locator('#issue-signals .issue-glossary-term:visible').first();
   const href=await term.getAttribute('href');assert.match(href,/#issue\?term=issue-term-/);
   if(mobile)await term.tap();else{await term.focus();await page.keyboard.press('Enter')}
   await page.waitForFunction(()=>document.activeElement?.id.startsWith('issue-term-'));
   assert.equal(await page.locator('#issue').isVisible(),true);
   const focused=await page.evaluate(()=>document.activeElement.id);
   assert.equal(focused,new URLSearchParams(href.split('?')[1]).get('term'));
   assert.equal(await page.locator('#'+focused+' + dd').isVisible(),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),true,'No horizontal overflow');
   const folder=process.env.SCREENSHOT_DIR||'/tmp/weekly-citation-ui';fs.mkdirSync(folder,{recursive:true});
   await page.screenshot({path:path.join(folder,mobile?'mobile-glossary.png':'desktop-glossary.png')});
   await page.goBack();await page.waitForURL('**/#issue');
   await page.locator('#issue-signals .issue-ref').first().click();
   await page.waitForSelector('#paper:not([hidden]) .rv-article');
   assert.equal(await page.locator('#paper .issue-glossary-term').count(),0);
   assert.equal(await page.locator('#paper .issue-inline-citation').count(),0);
   assert.ok((await page.locator('#paper').innerText()).length>500);
   await page.screenshot({path:path.join(folder,mobile?'mobile-article.png':'desktop-article.png')});
   // Synthetic edge cases use the same real DOM helpers, not mocked elements.
   const edge=await page.evaluate(()=>{
    const section={text:'Alpha & <study>. Beta uncertainty.\n\n'+('Long detail. '.repeat(30)),source_ids:['a'],citations:[{text:'Alpha & <study>. Beta',source_id:'a',page:3,locator:'Results'}]};
    const fixture={sources:[{id:'a',title:'Alpha source',source_url:'javascript:bad()',url:'https://example.org/paper.pdf'}],glossary:[{term:'uncertainty',definition:'What we do not know.'},{term:'Alpha',definition:'A source.'}]};
    const box=compactIssueReading(section,'Read more',fixture);
    return {html:box.innerHTML,preview:box.firstElementChild.textContent,paragraphs:box.querySelectorAll('details p').length,source:box.querySelector('a').getAttribute('href'),nested:box.querySelectorAll('a a').length};
   });
   assert.equal(edge.preview,'Alpha & <study>. Beta');assert.equal(edge.paragraphs,2);
   assert.ok(edge.html.includes('&lt;study&gt;'));assert.ok(!edge.html.includes('<study>'));
   assert.equal(edge.source,'https://example.org/paper.pdf#page=3');assert.equal(edge.nested,0);
   assert.deepEqual(errors,[]);
   results.push({viewport:mobile?'390x844 mobile':'1440x1000 desktop',glossaryFocus:focused,article:'rendered',consoleErrors:errors.length});
   await context.close();
  }
  console.log(JSON.stringify(results,null,2));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
