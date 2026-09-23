/* SPDX-License-Identifier: MIT */
// Run: node examples/greedy-playground/verify.cjs
const assert = require('node:assert/strict');
const toy = require('./playground.js');
const popcount = value => value.toString(2).replaceAll('0','').length;
function reference(masks,k,prefix=[]) {
  let best=-1;
  for(let choice=0;choice<(1<<masks.length);choice++) {
    if(popcount(choice)!==k || prefix.some(i=>!(choice&(1<<i)))) continue;
    let covered=0;
    masks.forEach((mask,i)=>{if(choice&(1<<i))covered|=mask;});
    best=Math.max(best,popcount(covered));
  }
  return best;
}
let checked=0;
for(let a=0;a<8;a++)for(let b=0;b<8;b++)for(let d=0;d<8;d++)for(let k=1;k<=3;k++) {
  const masks=[a,b,d],c={n:3,k,sets:masks.map(mask=>[0,1,2].filter(i=>mask&(1<<i)))};
  assert.equal(toy.exact(c).value,reference(masks,k));
  let union=0, chosen=[];
  for(const step of toy.greedy(c)) {
    const candidates=masks.map((mask,i)=>({i,gain:popcount(mask&~union)})).filter(x=>!chosen.includes(x.i)).sort((x,y)=>y.gain-x.gain||x.i-y.i);
    assert.equal(step.index,candidates[0].i);
    chosen.push(step.index);union|=masks[step.index];
    assert.equal(step.value,popcount(union));
    assert.equal(toy.exact(c,chosen).value,reference(masks,k,chosen));
  }
  checked++;
}
assert.deepEqual(toy.cases.map(c=>[toy.greedy(c).at(-1).value,toy.exact(c).value]),[[3,4],[5,6],[6,6]]);
const valid={schema_version:1,encoding:'elements',universe_size:4,k:2,sets:[[0,1],[0,2],[1,3]]};
assert.equal(toy.validate(valid).n,4);
assert.equal(toy.validate({instance:valid}).k,2);
for(const bad of [null,{}, {...valid,k:0},{...valid,k:4},{...valid,sets:[[0,0]]},{...valid,sets:[[4]]},{...valid,sets:[['0']]},{...valid,universe_size:13},{...valid,sets:Array(9).fill([])},{...valid,encoding:'bitmask'}]) assert.throws(()=>toy.validate(bad));
console.log(`PASS ${checked} exhaustive small instances, all Greedy prefixes, 3 teaching cases, valid/wrapped/invalid imports`);
