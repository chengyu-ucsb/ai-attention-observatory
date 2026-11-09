'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
class Element{
 constructor(tag,text=''){this.tag=tag;this.children=[];this.textContent=text;this.className='';this.classList={add:name=>this.className+=' '+name}}
 append(...nodes){this.children.push(...nodes)}
}
const context={URL,URLSearchParams,document:{createElement:tag=>new Element(tag),createTextNode:text=>new Element('#text',text)},S:{issue:{}}};
vm.createContext(context);
vm.runInContext(app.slice(app.indexOf('function make('),app.indexOf('function date('))+app.slice(app.indexOf('function issueCitationUrl('),app.indexOf('function renderIssueGlossary(')),context);
const {issueTextSpans,issueProse,compactIssueReading,issueCitationUrl}=context;
const source={id:'a',title:'Source & title',source_url:'javascript:bad()',url:'https://example.org/paper.pdf?version=2'};
const issue={sources:[source],glossary:[{term:'uncertainty',definition:'What we do not know.'},{term:'Alpha',definition:'A source.'}]};
const section={text:'Alpha & <study>. Beta uncertainty.\n\n'+('Remaining detail. '.repeat(30)),source_ids:['a'],citations:[{text:'Alpha & <study>. Beta',source_id:'a',page:3,locator:'Results'}]};
const spans=issueTextSpans(section.text,section,issue);
assert.equal(spans.length,2);assert.equal(spans[0].url,'https://example.org/paper.pdf?version=2#page=3');
assert.equal(spans[1].url,'#issue?term=issue-term-uncertainty-1');
function all(node,tag){return [...(node.tag===tag?[node]:[]),...node.children.flatMap(child=>all(child,tag))]}
function text(node){return node.textContent+node.children.map(text).join('')}
const full=issueProse(section.text,section,issue);
assert.equal(all(full,'p').length,2);assert.equal(all(full,'a').length,2);
assert.equal(text(all(full,'a')[0]),'Alpha & <study>. Beta');
assert.equal(all(full,'study').length,0,'Text must never become HTML');
const compact=compactIssueReading(section,'Full',issue);
assert.equal(text(compact.children[0]),'Alpha & <study>. Beta');
assert.equal(all(compact,'details').length,1);
assert.equal(text(all(compact,'details')[0].children[1]),section.text.replace('\n\n',''));
assert.equal(issueCitationUrl({url:'https://user:pass@example.org'}),'');
assert.equal(issueCitationUrl({url:'https://bad host/path'}),'');
assert.equal(issueCitationUrl({source_url:'https://example.org/v1',url:'https://example.org/v2'}),'https://example.org/v1');
for(const citations of [[{text:'missing',source_id:'a'}],[{text:'Remaining detail.',source_id:'a'}],[{text:'Alpha',source_id:'no'}]]){
 assert.equal(issueTextSpans(section.text,{...section,citations},{sources:[source]}).length,0);
}
const overlap=issueTextSpans(section.text,{...section,citations:[...section.citations,{text:'Alpha',source_id:'a'}]},issue);
assert.equal(overlap.filter(s=>s.className==='issue-inline-citation').length,1);
assert.equal(all(issueProse('Legacy prose.',{},{}),'a').length,0);
assert.match(app,/if\(page==="issue"\)focusIssueTerm\(raw\)/);
assert.match(app,/target\.focus\(\{preventScroll:true\}\)/);
console.log('Weekly DOM tests passed: citations, PDF locators, glossary priority, exact previews, paragraphs, escaping, URL safety and legacy prose.');
