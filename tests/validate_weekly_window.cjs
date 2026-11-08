"use strict";
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const ROOT=path.resolve(__dirname,'..'),app=fs.readFileSync(path.join(ROOT,'app.js'),'utf8');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.className='';this.hidden=false;this.style={};}
 append(...els){this.children.push(...els);}
 replaceChildren(...els){this.children=[];this.textContent='';this.append(...els);}
 setAttribute(){} addEventListener(){}
}
const elements=new Map();
const doc={createElement:tag=>new Element(tag),createElementNS:(_ns,tag)=>new Element(tag),querySelector:q=>{
 if(q==='#issue-source-landscape')return null;
 if(!elements.has(q))elements.set(q,new Element('div'));
 return elements.get(q);
}};
const ctx=vm.createContext({document:doc,console,URL,window:{scrollTo(){}}});
vm.runInContext(app.slice(0,app.lastIndexOf('$("[data-route]").forEach('))+'\nconst TEST={renderIssue,S};',ctx);
ctx.issue={status:'published',edition_date:'2026-11-02',number:1,headline:'Synthetic weekly issue',deck:'A test',letter:'A test',signals:[],tension:{source_ids:[]},experiment:{},sources:[{id:'test',title:'Synthetic source',url:'https://example.org/article',editorial_role:'publication_week'}],source_count:1,publication_window:{from:'2026-10-26',to:'2026-11-01',timezone:'UTC'}};
vm.runInContext('TEST.S.issue=issue; TEST.renderIssue()',ctx);
const line=elements.get('#issue-coverage').textContent;
assert(line.includes('Oct 26, 2026')&&line.includes('Nov 1, 2026')&&line.includes('(UTC)'));
assert(line.includes('No older context sources'));
assert(!line.includes('does not mean newly published'));
ctx.issue={...ctx.issue,publication_window:undefined,sources:[]};
vm.runInContext('TEST.S.issue=issue; TEST.renderIssue()',ctx);
assert(!elements.get('#issue-coverage').textContent.includes('originally published'),'Legacy archived issue must not be retroactively relabeled');
console.log('Strict previous-publication-week UI and legacy archive labels passed.');
