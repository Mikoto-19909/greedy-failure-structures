'use strict';
const $ = id => document.getElementById(id);
const source = new URLSearchParams(location.search).get('source');
const state = {
  data: null, offset: 0, total: 0, request: 0, recordRequest: 0, instanceRequest: 0, pairRequest: 0, instance: null, selection: null
};
const names = {
  r2:'R2 预算扫描',r3:'R3 原图配对',r4:'R4 前缀上界',r4_dual:'R4 DUAL 比较',failure_rate:'失效率',mean_relative_gap:'平均相对损失',mean_absolute_loss:'平均绝对损失',mean_ratio:'平均 G/O',ratio_of_means:'均值之比 G/O',certified_ratio_mean:'平均认证下界 G/U',tightening_mean:'平均上界收紧',initial_ratio_mean:'初始 G/U',prefix_ratio_mean:'前缀 G/U',dual_ratio_mean:'DUAL G/U',relative_gap:'相对损失',absolute_loss:'绝对损失',high_minus_low_first_loss:'high − low 首步不可恢复率',high_minus_low_failure:'high − low 失效率',high_minus_low_relative_gap:'high − low 相对损失',high_minus_low_exposure:'high − low 暴露量',initial_minus_prefix:'初始界 − 前缀界',prefix_minus_dual:'前缀界 − DUAL 界',base_graph_id:'原图',direction:'方向',replica:'链',k:'预算',greedy:'Greedy',optimum:'最优参考',difference:'差值',initial:'初始界',prefix:'前缀界',dual:'DUAL 界',a:'A',b:'B'
};
const label = x => names[x] || x;
Object.assign(names, {n: '全集', d: '集合大小', low_first_loss: 'low 首步损失', high_first_loss: 'high 首步损失', first_loss: '首步损失'});
const fmt = x => x === null || x === undefined ? '—' : typeof x === 'number' ? Number.isInteger(x) ? String(x) : x.toPrecision(5) : String(x);
function node(tag,text){
  const n=document.createElement(tag);
  if(text!==undefined)n.textContent=text;
  return n;
}
function option(select,values,wanted){
  select.replaceChildren(...values.map(value=>{
    const o=node('option',label(String(value)));o.value=String(value);return o;
  }));
  if(values.map(String).includes(String(wanted)))select.value=String(wanted);
}
function query(extra={
}){
  return new URLSearchParams({
    source,...extra
  });
}
async function api(path,extra={
}){
  const response=await fetch('/api/studies/'+path+'?'+query(extra));
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||'读取失败');
  return data;
}
function filters(){
  return state.data?.kind==='r3'?{
    'loss_only':String($('loss-only').checked)
  }:{
    n:$('n').value,d:$('d').value,k:$('k').value,loss_only:String($('loss-only').checked)
  };
}
function fail(error){
  $('message').textContent=error.message;
}
function table(target,rows,columns,onClick){
  const table=node('table'),head=node('tr');
  for(const c of columns)head.append(node('th',label(c)));
  if(onClick)head.append(node('th','实例'));
  table.append(head);
  for(const row of rows){
    const tr=node('tr');
    for(const c of columns)tr.append(node('td',fmt(row[c])));
    if(onClick){
      const td=node('td'),button=node('button','查看');
      button.addEventListener('click',()=>onClick(row));
      td.append(button);
      tr.append(td);
    }table.append(tr);
  }target.replaceChildren(table);
}
function svgNode(tag,attrs={
},text){
  const n=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));
  if(text!==undefined)n.textContent=text;
  return n;
}
function chart(target,points,{
  bars=false,onClick=null,title=''
}={
}){
  target.replaceChildren();
  if(!points.length){
    target.append(node('p','当前范围没有可绘制数据。'));
    return;
  }const svg=svgNode('svg',{
    viewBox:'0 0 960 300',role:'img','aria-label':title
  });
  svg.append(svgNode('title',{
  },title));
  const xvals=points.map(p=>p.x),yvals=points.flatMap(p=>[p.y,p.low??p.y,p.high??p.y]);
  const xmin=Math.min(...xvals),xmax=Math.max(...xvals),ymin=Math.min(0,...yvals),ymax=Math.max(...yvals);
  const x=v=>65+(v-xmin)/(xmax-xmin||1)*850,y=v=>245-(v-ymin)/(ymax-ymin||1)*215;
  svg.append(svgNode('path',{
    d:'M65 20V245H925',fill:'none',stroke:'#adc4b7'
  }));
  for(let i=0;i<5;i++){
    const value=ymin+(ymax-ymin)*i/4;
    svg.append(svgNode('text',{
      x:57,y:y(value)+4,'text-anchor':'end'
    },fmt(value)));
  }if(!bars)svg.append(svgNode('polyline',{
    points:points.map(p=>`${x(p.x)},${y(p.y)}`).join(' '),fill:'none',stroke:'#287f73','stroke-width':2
  }));
  points.forEach((p,i)=>{
    const titleText=`${fmt(p.x)}: ${fmt(p.y)}${p.low!==undefined?` [${
      fmt(p.low)
    }, ${
      fmt(p.high)
    }]`:''}`;if(p.low!==undefined)svg.append(svgNode('line',{
      x1:x(p.x),x2:x(p.x),y1:y(p.low),y2:y(p.high),stroke:'#397b70','stroke-width':2
    }));const mark=bars?svgNode('rect',{
      x:x(p.x)-Math.min(18,380/points.length),y:y(p.y),width:Math.min(36,760/points.length),height:Math.max(1,245-y(p.y)),fill:'#438f7c'
    }):svgNode('circle',{
      cx:x(p.x),cy:y(p.y),r:6,fill:'#236e61'
    });mark.append(svgNode('title',{
    },titleText));if(onClick){
      mark.classList.add('point');mark.setAttribute('tabindex','0');mark.setAttribute('role','button');mark.setAttribute('aria-label',titleText);mark.addEventListener('click',()=>onClick(p));mark.addEventListener('keydown',event=>{
        if(event.key==='Enter'||event.key===' '){
          event.preventDefault();onClick(p);
        }
      });
    }svg.append(mark);if(points.length<16||i===0||i===points.length-1)svg.append(svgNode('text',{
      x:x(p.x),y:270,'text-anchor':'middle'
    },fmt(p.x)));
  });
  target.append(svg);
}
function renderCurve(){
  const data=state.data,metric=$('curve-metric').value;
  const cells=data.cells.filter(r=>r.n===Number($('n').value)&&r.d===Number($('d').value)).sort((a,b)=>a.k-b.k);
  const stem=metric==='failure_rate'?'failure':metric;
  chart($('curve'),cells.filter(r=>r[metric]!==undefined&&r[metric]!==null).map(r=>({
    x:r.k,y:r[metric],low:r[stem+'_lower'],high:r[stem+'_upper']
  })),{
    title:label(metric),onClick:p=>{
      $('k').value=String(p.x);refresh();
    }
  });
}
function renderDistribution(){
  const key=$('distribution-metric').value,dist=state.data.distributions[key];
  $('distribution-summary').textContent=dist?`${dist.count} 个${state.data.kind==='r3'?'原图差值':'原图记录'}；均值 ${fmt(dist.mean)}，中位数 ${fmt(dist.median)}，nearest-rank P90 ${fmt(dist.p90)}`:'请选择一个 n、d、k 单元。';
  chart($('distribution'),dist?dist.points.map(p=>({
    x:p.value,y:p.count
  })):[],{
    bars:true,title:label(key)
  });
}
async function refresh(){
  const request=++state.request;
  state.recordRequest++;
  state.instanceRequest++;
  state.pairRequest++;
  $('budget-pair-message').textContent='';
  $('budget-pair-chart').replaceChildren();
  $('budget-pair-table').replaceChildren();
  $('records').replaceChildren();
  $('pair-table').replaceChildren();
  $('previous').disabled = true;
  $('next').disabled = true;
  $('message').textContent='正在读取完整保存表…';
  $('instance-panel').hidden=true;
  try{
    const data=await api('analysis',state.data?filters():{
    });
    if(request!==state.request)return;
    const first=!state.data;
    state.data=data;
    $('title').textContent=label(data.kind);
    $('source').textContent=source;
    $('notice').textContent=data.notice;
    $('dimensions').hidden=data.kind==='r3';
    $('curve-section').hidden=data.kind==='r3';
    $('budget-pairs').hidden=data.kind!=='r2';
    if(first&&data.kind!=='r3'){
      for(const key of ['n','d','k'])option($(key),data.options[key]);
      option($('k-a'),data.options.k);
      option($('k-b'),data.options.k,data.options.k[1]);
      const metrics=data.kind==='r2'?['failure_rate','mean_relative_gap','mean_absolute_loss','mean_ratio','ratio_of_means']:data.kind==='r4'?['certified_ratio_mean','tightening_mean']:['initial_ratio_mean','prefix_ratio_mean','dual_ratio_mean'];
      option($('curve-metric'),metrics);
      await refresh();
      return;
    }
    if(data.kind !== 'r3') {
      const budgets = data.cells.filter(row => row.n === Number($('n').value) && row.d === Number($('d').value)).map(row => row.k).sort((a, b) => a - b);
      const prior = $('k').value;
      option($('k'), budgets, prior);
      option($('k-a'), budgets, $('k-a').value);
      option($('k-b'), budgets, $('k-b').value);
      if (prior !== $('k').value) { await refresh(); return; }
    }
    $('counts').textContent=`当前 ${data.graph_count} 张原图 · ${data.record_count} 条记录；来源完整表 ${data.total_records} 条记录`;
    $('unit').textContent=data.kind==='r3'?'每原图四端点；先各方向两链平均，再 high − low。构造协议比较，不作 E0 因果解释。':'同一原图跨预算相关。分布固定 n、d、k；G < O 才表示失效，U > G 仅表示尚未认证。';
    $('primary').replaceChildren();
    if(data.primary){
      $('primary').append(node('strong','完整预定批次的保存主估计'),node('p',`原图 n=${data.primary.n}；端点=${data.primary.endpoints}；差值 ${fmt(data.primary.delta)}，保存区间 [${fmt(data.primary.lower)}, ${fmt(data.primary.upper)}]。当前筛选不改变此区间。`));
    }const old=$('distribution-metric').value;
    option($('distribution-metric'),Object.keys(data.distributions),old);
    renderDistribution();
    if(data.kind!=='r3')renderCurve();
    $('paired-summary').textContent=data.pairs.length?`${data.pairs.length} 个合法同图配对；下方预览前 20 个，完整记录见分页浏览。`:'';
    table($('pair-table'),data.pairs.slice(0,20),data.kind==='r3'?['base_graph_id','low_first_loss','high_first_loss','difference']:['base_graph_id','k','initial','prefix','dual'],row=>openInstance({
      base_graph_id:row.base_graph_id,...(data.kind==='r3'?{
      }:{
        k:row.k
      })
    }));
    state.offset=0;
    await loadRecords();
    if(request===state.request)$('message').textContent='已读取完整表；未运行研究生产或最优值重算。';
  }catch(error){
    if(request===state.request) {
      fail(error);
      for (const id of ['curve', 'distribution', 'records', 'pair-table', 'primary']) $(id).replaceChildren();
      $('counts').textContent = '当前数据不可读取。';
      $('previous').disabled = true;
      $('next').disabled = true;
    }
  }
}
async function loadRecords(){
  const request=++state.recordRequest;
  try{
    const data=await api('records',{
      ...filters(),offset:state.offset,limit:50
    });
    if(request!==state.recordRequest)return;
    state.total=data.total;
    const columns=data.kind==='r3'?['base_graph_id','direction','replica','greedy','optimum','relative_gap','first_loss']:['base_graph_id','n','d','k','greedy','optimum','relative_gap'];
    table($('records'),data.rows,columns,row=>openInstance({
      base_graph_id:row.base_graph_id,...(data.kind==='r3'?{
        direction:row.direction,replica:row.replica
      }:{
        k:row.k
      })
    }));
    $('page-count').textContent=`${data.total?state.offset+1:0}–${Math.min(state.offset+50,data.total)} / ${data.total}`;
    $('previous').disabled=state.offset===0;
    $('next').disabled=state.offset+50>=data.total;
  }catch(error){
    if(request===state.recordRequest) fail(error);
  }
}
async function openInstance(selection){
  const request=++state.instanceRequest;
  $('instance-panel').hidden=true;
  $('message').textContent='读取实际集合与保存见证…';
  try{
    const data=await api('instance',selection);
    if(request!==state.instanceRequest)return;
    state.instance=data;
    state.selection=selection;
    $('instance-panel').hidden=false;
    $('instance-title').textContent=`${data.base_graph_id} · k=${data.instance.k}${data.direction===null?' · 原图':` · ${
      data.direction===-1?'low':'high'
    } 链 ${
      data.replica
    }`}`;
    $('instance-source').textContent=data.provenance.graph_origin;
    $('export').href='/api/studies/instance-export?'+query(selection);
    $('instance-choices').replaceChildren(...data.choices.map(choice=>{
      const button=node('button',choice.label);button.addEventListener('click',()=>{
        const next={
          base_graph_id:data.base_graph_id
        };for(const key of ['k','direction','replica'])if(choice[key]!==undefined&&choice[key]!==null)next[key]=choice[key];openInstance(next);
      });return button;
    }));
    $('quality').textContent=`Greedy ${data.values.greedy} · 保存最优参考 ${data.values.optimum}${data.values.forced_optimum!==undefined?' · 强制首步最优 '+data.values.forced_optimum:''}。已核对见证覆盖与 Greedy 回放，未重新证明最优性。`;
    $('step').max=data.instance.k;
    $('step').value=0;
    renderStep();
    $('certificate-panel').hidden=!data.certificate;
    $('certificate').textContent=data.certificate?JSON.stringify(data.certificate,null,2):'';
    $('moves-panel').hidden=!data.moves.length;
    $('moves').textContent=data.moves.map(row=>row.join(', ')).join('\n');
    $('message').textContent='已核对实例身份、保存见证和确定性 Greedy 步骤。';
    $('instance-panel').scrollIntoView({
      behavior:'smooth',block:'start'
    });
  }catch(error){
    if(request===state.instanceRequest)fail(error);
  }
}
function renderStep(){
  const data=state.instance;
  if(!data)return;
  const step=data.steps[Number($('step').value)];
  $('step-count').textContent=`步骤 ${step.step} / ${data.instance.k}`;
  $('step-info').textContent=`已覆盖 ${step.coverage}；当前最大收益候选 [${step.candidates.join(', ')}]；下一选择 ${fmt(step.next_choice)}`;
  const table=node('table'),head=node('tr');
  head.append(node('th','集合'));
  for(let i=0;i<data.instance.universe_size;i++)head.append(node('th',String(i)));
  head.append(node('th','边际收益'));
  table.append(head);
  data.instance.sets.forEach((set,index)=>{
    const tr=node('tr');if(step.selected.includes(index))tr.classList.add('selected');if(index===step.next_choice)tr.classList.add('chosen');tr.append(node('th',`S${index}`));for(let i=0;i<data.instance.universe_size;i++){
      const td=node('td',set.includes(i)?'●':'');if(set.includes(i)&&step.covered.includes(i))td.classList.add('covered');tr.append(td);
    }tr.append(node('td',fmt(step.gains[index])));table.append(tr);
  });
  $('matrix').replaceChildren(table);
  $('witnesses').textContent=`Greedy 终集 [${data.values.greedy_selected.join(', ')}]；最优见证 [${data.values.optimum_selected.join(', ')}]${data.values.forced_selected?`；强制首步见证 [${
    data.values.forced_selected.join(', ')
  }]`:''}`;
  $('step-back').disabled=step.step===0;
  $('step-next').disabled=step.step===data.instance.k;
}
$('compare-pairs').addEventListener('click',async()=>{
  const request = ++state.pairRequest;
  const budget = Number($('k-b').value);
  try{
    const data=await api('pairs',{
      n:$('n').value,d:$('d').value,k_a:$('k-a').value,k_b:$('k-b').value,metric:$('pair-metric').value
    });
    if (request !== state.pairRequest) return;
    $('budget-pair-message').textContent=`${data.notice} ${data.pairs.length} 张原图；均值差 ${fmt(data.distribution.mean)}`;chart($('budget-pair-chart'),data.distribution.points.map(p=>({
      x:p.value,y:p.count
    })),{
      bars:true,title:'预算 B − A'
    });table($('budget-pair-table'),data.pairs.slice(0,20),['base_graph_id','a','b','difference'],row=>openInstance({
      base_graph_id:row.base_graph_id,k:budget
    }));
  }catch(error){
    if (request !== state.pairRequest) return;
    $('budget-pair-message').textContent=error.message;$('budget-pair-chart').replaceChildren();$('budget-pair-table').replaceChildren();
  }
});
for(const id of ['n','d','k','loss-only'])$(id).addEventListener('change',refresh);
$('curve-metric').addEventListener('change',renderCurve);
$('distribution-metric').addEventListener('change',renderDistribution);
$('previous').addEventListener('click',()=>{
  state.offset=Math.max(0,state.offset-50);loadRecords();
});
$('next').addEventListener('click',()=>{
  state.offset+=50;loadRecords();
});
$('step').addEventListener('input',renderStep);
for(const[id,delta]of [['step-back',-1],['step-next',1]])$(id).addEventListener('click',()=>{
  $('step').value=Number($('step').value)+delta;renderStep();
});
if(source)refresh();
else $('message').textContent='请从专题研究页面选择一个已有来源。';
