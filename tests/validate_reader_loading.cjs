"use strict";
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync('app.js','utf8');
const code=app.slice(0,app.lastIndexOf('$$("[data-route]").forEach('));
class Element{
 constructor(){this.children=[];this.textContent='';this.style={};}
 append(...children){this.children.push(...children)}
 replaceChildren(...children){this.children=children}
 setAttribute(){}
}
function environment(fetch){
 const elements=new Map();
 const context=vm.createContext({fetch,console,URL,Map,location:{hash:'#home'},window:{},
   document:{createElement:()=>new Element(),querySelector:key=>{
    if(!elements.has(key))elements.set(key,new Element());return elements.get(key)
   }}});
 vm.runInContext(code+'\nthis.state=S;this.events=[];renderIssue=()=>events.push("edition");route=()=>events.push("route");home=()=>{};renderBacklog=()=>{};renderPerspectives=()=>{};',context);
 return {context,elements};
}
(async()=>{
 const index='data/reader/indexes/'+'a'.repeat(64)+'.json';
 const manifest={schema_version:1,edition_id:'2026-11-07',issue:{edition_date:'2026-11-07',sources:[{id:'frozen'}]},index_url:index,collection:{date:'2026-11-11'}};
 let rejectIndex;const requests=[];
 const {context,elements}=environment(async(path,options)=>{
  requests.push({path,options});
  if(path==='data/reader-manifest.json')return {ok:true,json:async()=>manifest};
  if(path===index)return new Promise((_resolve,reject)=>{rejectIndex=reject});
  throw Error('Unexpected request '+path);
 });
 const started=vm.runInContext('init()',context);
 for(let n=0;n<10&&!rejectIndex;n++)await new Promise(resolve=>setImmediate(resolve));
 assert(context.events.includes('edition'),'Edition must render before archive completes');
 rejectIndex(Error('Archive offline'));await started;
 assert.equal(context.state.issue.edition_date,'2026-11-07');
 assert(elements.get('#issue-meta').textContent.includes('still available'));
 assert.equal(requests.length,2);
 assert.equal(requests[0].options.cache,'no-cache');
 assert.equal(requests[1].options.cache,'force-cache');
 assert(!app.includes('Date.now()'),'Do not defeat versioned caching');
 assert(!app.includes('data/runs.json'),'Operational logs are not reader data');
 assert.equal(vm.runInContext('matchesSearch({search_terms:"critical learning study thinking"},"critical thinking")',context),true);
 assert.equal(vm.runInContext('matchesSearch({search_terms:"critical learning study thinking"},"critical unrelated")',context),false);
 // The source cards must continue to use edition snapshots after a new index.
 vm.runInContext('renderEditionCards()',context);
 const cards=elements.get('#feature-grid').children;
 assert.equal(cards.length,1);
 console.log('Reader loading: edition survives failed archive; immutable assets and edition sources verified.');
})().catch(error=>{console.error(error);process.exitCode=1});
