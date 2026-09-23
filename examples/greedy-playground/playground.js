/* SPDX-License-Identifier: MIT */
'use strict';
const GreedyToy = (() => {
  const cases = [
    {title:'平局里的陷阱', n:4, k:2, sets:[[0,1],[0,2],[1,3]], note:'一样大的三个集合，先选哪一个有区别吗？'},
    {title:'最大的不一定最好', n:6, k:2, sets:[[0,1,2,3],[0,1,4],[2,3,5]], note:'A 能盖住最多的点。先选它，真的划算吗？'},
    {title:'贪心也能全对', n:6, k:2, sets:[[0,1,2],[3,4,5],[0,3]], note:'找到互补的集合。这一次，贪心能做对吗？'}
  ];
  const covered = (c, chosen) => new Set(chosen.flatMap(i => c.sets[i]));
  function exact(c, prefix=[]) {
    let best = {value:-1, selected:[]};
    function visit(start, chosen) {
      if(chosen.length === c.k) {
        const value = covered(c,chosen).size;
        if(value > best.value) best = {value,selected:[...chosen]};
        return;
      }
      for(let i=start;i<c.sets.length;i++) if(!chosen.includes(i)) visit(i+1,[...chosen,i]);
    }
    visit(0,[...prefix]);
    return best;
  }
  function greedy(c) {
    const chosen=[], steps=[];
    while(chosen.length<c.k) {
      const before=covered(c,chosen);
      const gains=c.sets.map((set,i)=>chosen.includes(i)?-1:set.filter(x=>!before.has(x)).length);
      const gain=Math.max(...gains), index=gains.indexOf(gain);
      chosen.push(index);
      steps.push({index,gain,ties:gains.flatMap((g,i)=>g===gain?[i]:[]),chosen:[...chosen],value:covered(c,chosen).size});
    }
    return steps;
  }
  function validate(raw) {
    if(!raw || typeof raw!=='object') throw Error('需要一个 JSON 实例对象。');
    const c=raw.instance || raw;
    if(c.schema_version!==1 || c.encoding!=='elements') throw Error('需要 schema_version=1、encoding="elements" 的实例。');
    if(!Number.isInteger(c.universe_size)||c.universe_size<1||c.universe_size>12) throw Error('元素数必须在 1–12 之间。');
    if(!Array.isArray(c.sets)||c.sets.length<1||c.sets.length>8) throw Error('集合数必须在 1–8 之间。');
    if(!Number.isInteger(c.k)||c.k<1||c.k>c.sets.length) throw Error('可选集合数必须在 1 和集合总数之间。');
    if(c.sets.some(s=>!Array.isArray(s)||s.length>c.universe_size||new Set(s).size!==s.length||s.some(x=>!Number.isInteger(x)||x<0||x>=c.universe_size))) throw Error('集合元素必须是范围内的不重复整数。');
    return {title:'我的反例实验',note:'这是你修改或导入的实例。试试能不能胜过贪心。',n:c.universe_size,k:c.k,sets:c.sets.map(s=>[...s].sort((a,b)=>a-b))};
  }
  return {cases,covered,exact,greedy,validate};
})();
if(typeof module!=='undefined') module.exports=GreedyToy;
if(typeof document!=='undefined') (()=>{
  const $=id=>document.getElementById(id), label=i=>String.fromCharCode(65+i);
  let c,chosen=[],revealed=false,step=0,timer=null,draft,caseIndex=0;
  const stop=()=>{clearInterval(timer);timer=null;$('autoplay').textContent='自动播放';};
  function load(value,index=-1){stop();c=structuredClone(value);caseIndex=index;chosen=[];revealed=false;step=0;draft=structuredClone(c);$('status').textContent='';$('editor-status').textContent='';render();edit();}
  function render(){
    const cov=GreedyToy.covered(c,chosen), best=GreedyToy.exact(c), path=GreedyToy.greedy(c), g=path.at(-1);
    $('case-title').textContent=c.title;$('hint').textContent=c.note;$('budget').textContent=`最多选 ${c.k} 个集合`;
    $('challenge').textContent=`挑 ${c.k} 个集合，尽量盖住更多点。`;
    $('before').querySelector('li').textContent=`点左侧或上方的集合，选 ${c.k} 个。`;
    $('score').textContent=cov.size;$('total').textContent=`/ ${c.n} 个点`;
    $('selection').textContent=chosen.length?`已选 ${chosen.map(label).join(' + ')} · ${chosen.length}/${c.k}`:'还没有选择集合';
    $('elements').replaceChildren(...Array.from({length:c.n},(_,i)=>{const el=document.createElement('span');el.className='dot'+(cov.has(i)?' covered':'');el.textContent=i+1;el.setAttribute('aria-label',`点 ${i+1}，${cov.has(i)?'已覆盖':'未覆盖'}`);return el;}));
    $('sets').replaceChildren(...c.sets.map((set,i)=>{const b=document.createElement('button');b.className='set';b.setAttribute('aria-pressed',String(chosen.includes(i)));b.innerHTML=`<b>${label(i)}</b><span class="members">${set.length?set.map(x=>x+1).join(' · '):'空集合'}</span><span class="gain">${chosen.includes(i)?'已选择 ✓':`新增 ${set.filter(x=>!cov.has(x)).length} 个点`}</span>`;b.onclick=()=>{if(chosen.includes(i))chosen=chosen.filter(j=>j!==i);else if(chosen.length<c.k)chosen.push(i);else{$('status').textContent=`已选满 ${c.k} 个。再点一下已选集合，即可换选。`;return;}$('status').textContent='';render();};return b;}));
    document.querySelectorAll('[data-case]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.case)===caseIndex)));
    $('reveal').disabled=chosen.length!==c.k;$('reveal').textContent=revealed?'答案已揭晓':'选好后，揭晓答案';
    $('before').hidden=revealed;$('answer').hidden=!revealed;$('replay').hidden=!revealed;
    if(revealed){
      $('verdict').textContent=cov.size===best.value?(g.value<best.value?'你找到了贪心错过的答案！':'你找到了最优组合！'):'还有更好的组合，再换一个试试。';
      $('comparison').innerHTML=`<div class="metric"><span>你当前覆盖</span><strong>${cov.size}</strong></div><div class="metric"><span>贪心 ${g.chosen.map(label).join(' + ')}</span><strong>${g.value}</strong></div><div class="metric"><span>最优 ${best.selected.map(label).join(' + ')}</span><strong>${best.value}</strong></div>`;
      $('explanation').textContent=g.value<best.value?`这个实例中，贪心少覆盖 ${best.value-g.value} 个点。集合单独好不好，和组合起来好不好，是两回事。`:'这个实例中贪心达到了最优。一个反例可以推翻“总是正确”，却不意味着贪心总会失败。';
      $('step').textContent=`第 ${step} / ${c.k} 步`;
      $('trace').replaceChildren(...path.slice(0,step).map((s,i)=>{const el=document.createElement('div');el.className='trace-item';el.textContent=`${i+1}. 选 ${label(s.index)} → 新增 ${s.gain}，共 ${s.value}${s.ties.length>1?`（${s.ties.map(label).join('/')} 平局）`:''}`;return el;}));
      const prefix=step?path[step-1].chosen:[], reachable=GreedyToy.exact(c,prefix).value;
      $('reachability').textContent=step===0?'还没开始。下一步会选择新增覆盖最多的集合。':reachable<best.value?`保留前 ${step} 步的选择，即使后面全选对，也最多覆盖 ${reachable} 个点，已经无法达到最优的 ${best.value}。撤回一个已选集合，试着修复它。`:`保留前 ${step} 步的选择，仍能达到最优的 ${best.value} 个点。`;
      $('prev').disabled=step===0;$('next').disabled=step===c.k;$('autoplay').disabled=step===c.k;
    }
  }
  function edit(){
    $('k').replaceChildren(...draft.sets.map((_,i)=>{const o=document.createElement('option');o.value=i+1;o.textContent=i+1;return o;}));$('k').value=draft.k;
    $('matrix').replaceChildren(...draft.sets.map((set,i)=>{const row=document.createElement('div');row.className='matrix-row';const title=document.createElement('b');title.textContent=label(i);row.append(title);for(let x=0;x<draft.n;x++){const b=document.createElement('button');b.className='cell';b.textContent=x+1;b.setAttribute('aria-label',`集合 ${label(i)} 包含点 ${x+1}`);b.setAttribute('aria-pressed',String(set.includes(x)));b.onclick=()=>{draft.sets[i]=set.includes(x)?set.filter(v=>v!==x):[...set,x].sort((a,b)=>a-b);edit();$('editor-status').textContent='修改尚未应用。点击“用这个实例挑战”。';};row.append(b);}return row;}));
  }
  document.querySelectorAll('[data-case]').forEach(b=>b.onclick=()=>load(GreedyToy.cases[Number(b.dataset.case)],Number(b.dataset.case)));
  $('reveal').onclick=()=>{revealed=true;render();};$('reset').onclick=()=>load(c,caseIndex);
  $('next').onclick=()=>{stop();step=Math.min(c.k,step+1);render();};$('prev').onclick=()=>{stop();step=Math.max(0,step-1);render();};
  $('autoplay').onclick=()=>{if(timer){stop();return;}$('autoplay').textContent='暂停';timer=setInterval(()=>{step=Math.min(c.k,step+1);if(step===c.k)stop();render();},1100);};
  $('optimal').onclick=()=>{chosen=GreedyToy.exact(c).selected;render();};
  $('k').onchange=()=>{draft.k=Number($('k').value);$('editor-status').textContent='修改尚未应用。点击“用这个实例挑战”。';};
  $('apply').onclick=()=>load({...draft,title:'我的反例实验',note:'你改过了集合关系。现在再试一次。'});
  $('export').onclick=()=>{const blob=new Blob([JSON.stringify({schema_version:1,encoding:'elements',universe_size:draft.n,k:draft.k,sets:draft.sets},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='greedy-instance.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('editor-status').textContent='已导出编辑区实例（元素编号从 0 开始）。';};
  $('import').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>65536)throw Error('文件过大，请导入小于 64 KB 的实例。');const parsed=GreedyToy.validate(JSON.parse(await file.text()));load(parsed);$('editor-status').textContent='导入成功，可以开始挑战。';}catch(err){$('editor-status').textContent=`导入失败：${err.message}`;}finally{e.target.value='';}};
  load(GreedyToy.cases[0],0);
})();
