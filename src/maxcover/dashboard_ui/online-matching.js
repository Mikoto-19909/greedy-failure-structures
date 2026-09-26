/* The matching page keeps distance costs and recourse separate from coverage. */
'use strict';
const $ = id => document.getElementById(id);
const state = {detail: null, trace: null, detailVersion: 0, traceVersion: 0, reportVersion: 0};
const names = {nearest: '最近空位', single: '单次腾位', priced_chain: '预算定价链', prefix_optimum: '当前前缀精确参照'};
const families = {all: '全部布局', uniform: '均匀布局', clustered: '局部聚集', near_far: '远近布局', paired: '分离点对', budget_trap: '预算例子', nested: '嵌套布局'};
const colors = {nearest: 'var(--muted)', single: 'var(--accent)', priced_chain: 'var(--amber)', prefix_optimum: 'var(--green)'};
const make = (tag, text) => {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n;};
const number = x => x === null || x === undefined ? '—' : Number(x).toLocaleString('zh-CN', {maximumFractionDigits: 3});
function runTime(name) {
  const iso=name.slice(0,4)+'-'+name.slice(4,6)+'-'+name.slice(6,8)+'T'+name.slice(9,11)+':'+name.slice(11,13)+':'+name.slice(13,15)+'Z';
  return new Date(iso).toLocaleString('zh-CN',{hour12:false});
}
function message(text='', error=false) { $('matching-message').textContent=text; $('matching-message').classList.toggle('error',error); }
async function api(path, body) {
  const response = await fetch('/api/online-matching/' + path, body === undefined ? {} : {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '读取失败');
  return data;
}
function options(select, rows) {
  select.replaceChildren();
  for (const [value,label] of rows) {const option=make('option',label); option.value=value; select.append(option);}
}
function svgNode(tag, attrs={}, text) {
  const n=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for (const [key,value] of Object.entries(attrs)) n.setAttribute(key,String(value));
  if (text !== undefined) n.textContent=text;
  return n;
}
function lineChart(target,title,xs,series,xLabel,yLabel) {
  const w=940,h=300,left=90,right=35,top=66,bottom=66;
  const svg=svgNode('svg',{viewBox:'0 0 '+w+' '+h,role:'img','aria-label':title});
  svg.append(svgNode('title',{},title),svgNode('text',{x:25,y:29,class:'chart-title'},title));
  const max=Math.max(1,...series.flatMap(s=>s.values));
  const scaleX=i=>left+(Number(xs[i])-Number(xs[0]))*(w-left-right)/Math.max(1,Number(xs.at(-1))-Number(xs[0]));
  const scaleY=v=>h-bottom-v/max*(h-top-bottom);
  for(let i=0;i<=4;i++) {
    const v=max*i/4,y=scaleY(v);
    svg.append(svgNode('line',{x1:left,y1:y,x2:w-right,y2:y,class:'axis'}));
    svg.append(svgNode('text',{x:left-12,y:y+5,'text-anchor':'end'},number(v)));
  }
  xs.forEach((x,i)=>svg.append(svgNode('text',{x:scaleX(i),y:h-bottom+23,'text-anchor':'middle'},x)));
  series.forEach((s,index)=>{
    const style='stroke:'+s.color+(s.dashed?';stroke-dasharray:6 5':'');
    svg.append(svgNode('polyline',{points:s.values.map((v,i)=>scaleX(i)+','+scaleY(v)).join(' '),class:'series',style}));
    s.values.forEach((v,i)=>svg.append(svgNode('circle',{cx:scaleX(i),cy:scaleY(v),r:4,class:'point',style:'fill:'+s.color})));
    const x=95+index*210;
    svg.append(svgNode('line',{x1:x,y1:48,x2:x+22,y2:48,class:'series',style}));
    svg.append(svgNode('text',{x:x+29,y:52},s.label));
  });
  svg.append(svgNode('text',{x:w/2,y:h-12,'text-anchor':'middle'},xLabel));
  svg.append(svgNode('text',{x:20,y:h/2,transform:'rotate(-90 20 '+h/2+')','text-anchor':'middle'},yLabel));
  $(target).replaceChildren(svg);
}
function renderComparison() {
  const family=$('matching-family').value;
  const rows=state.detail.summary.aggregates.filter(r=>r.family===family);
  const series=['nearest','single','priced_chain','prefix_optimum'].map(policy=>{
    const selected=rows.filter(r=>r.policy===policy);
    return {label:names[policy],color:colors[policy],dashed:policy==='prefix_optimum',
      values:[1,2,4].map(b=>(selected.find(r=>r.budget===b)||selected[0]).prefix_sum)};
  });
  lineChart('budget-chart','改派预算与阶段成本和',[1,2,4],series,'每个请求允许的改派次数','阶段成本和（坐标单位）');
  const table=make('table'),head=make('thead'),body=make('tbody'),header=make('tr');
  ['策略','改派上限 / 请求','阶段成本和','最终成本合计','总改派次数','单请求实际最大改派'].forEach(x=>header.append(make('th',x)));
  head.append(header);
  rows.forEach(r=>{
    const tr=make('tr');
    [names[r.policy],number(r.budget),number(r.prefix_sum),number(r.final_cost),number(r.total_recourse),number(r.max_request_recourse)]
      .forEach(x=>tr.append(make('td',x)));
    body.append(tr);
  });
  table.append(head,body); $('matching-summary').replaceChildren(table);
}
async function loadDetail(id) {
  const version=++state.detailVersion;
  ++state.traceVersion; state.trace=null;
  $('matching-content').hidden=true;
  message('正在读取已保存结果…');
  try {
    const data=await api('detail?run='+encodeURIComponent(id));
    if(version!==state.detailVersion) return;
    state.detail=data;
    options($('matching-family'),[...new Set(data.summary.aggregates.map(r=>r.family))].map(x=>[x,families[x]||x]));
    options($('matching-case'),data.cases.map(c=>[c.id,c.id+' · '+(families[c.family]||c.family)]));
    if(data.cases.some(c=>c.id==='dev_uniform')) $('matching-case').value='dev_uniform';
    const split=data.summary.split==='eval'?'固定比较':'开发例子';
    $('matching-source').textContent=split+' · '+data.cases.length+' 条序列 · '+runTime(id.split('/')[1]);
    const passed=data.verification?.status==='automatic_verification_passed_user_review_pending';
    $('matching-verification').textContent=passed?'该批次的独立核验记录：通过。':'该批次尚无通过的独立核验记录。';
    const links=['metrics.csv','summary.json','traces.json','inputs.json'];
    if(data.verification) links.push('verification.json');
    $('matching-downloads').replaceChildren(...links.map(file=>{
      const label={'metrics.csv':'下载逐序列结果','summary.json':'下载汇总','traces.json':'下载完整轨迹','inputs.json':'下载固定输入','verification.json':'下载核验记录'};
      const a=make('a',label[file]); a.href='/api/online-matching/artifact?run='+encodeURIComponent(id)+'&file='+file; a.download=file; return a;
    }));
    renderComparison(); $('matching-content').hidden=false; message();
    await loadTrace();
  } catch(error) { if(version===state.detailVersion) message(error.message,true); }
}
async function refresh(preferred) {
  try {
    const data=await api('library');
    if(!data.available) throw new Error('当前工作区没有在线匹配研究，请先迁入独立研究目录。');
    const previous=preferred||$('matching-run').value;
    options($('matching-run'),data.runs.map(r=>[r.id,r.origin+' · '+(r.split==='eval'?'固定比较':'开发例子')+' · '+runTime(r.name)]));
    $('matching-start').disabled=false;
    if(data.runs.some(r=>r.id===previous)) $('matching-run').value=previous;
    else {
      const choice=data.runs.find(r=>r.split==='eval');
      if(choice) $('matching-run').value=choice.id;
    }
    if(!$('matching-report').options.length) {
      options($('matching-report'),data.reports.map(r=>[r.id,r.title])); loadReport();
    }
    if(data.runs.length) await loadDetail($('matching-run').value);
    else message('可以运行固定实验生成第一批结果。');
  } catch(error) {message(error.message,true);}
}
async function loadTrace() {
  if(!state.detail) return;
  const version=++state.traceVersion, policy=$('matching-policy').value;
  $('matching-budget').disabled=policy==='nearest';
  const budget=policy==='nearest'?0:Number($('matching-budget').value);
  const query=new URLSearchParams({run:state.detail.id,case:$('matching-case').value,policy,budget});
  try {
    const data=await api('trace?'+query);
    if(version!==state.traceVersion) return;
    state.trace=data; $('matching-step').max=data.trace.history.length; $('matching-step').value=1; renderStep();
  } catch(error) {if(version===state.traceVersion) message(error.message,true);}
}
function renderStep() {
  if(!state.trace) return;
  const {case:c,trace}=state.trace, index=Number($('matching-step').value)-1, row=trace.history[index];
  const requests=c.order.map(i=>c.requests[i]), current=requests.slice(0,index+1), s=c.servers;
  const w=940,h=235,left=100,right=45,lo=Math.min(...s,...requests),hi=Math.max(...s,...requests);
  const x=v=>left+(v-lo)/(hi-lo||1)*(w-left-right);
  const svg=svgNode('svg',{viewBox:'0 0 '+w+' '+h,role:'img','aria-label':'第 '+(index+1)+' 步的请求与服务点分配'});
  svg.append(svgNode('title',{},'连线表示当前匹配，橙线表示本步发生改派的旧请求'));
  svg.append(svgNode('text',{x:20,y:65},'服务点'),svgNode('text',{x:20,y:155},'已到请求'));
  [60,150].forEach(y=>svg.append(svgNode('line',{x1:left,y1:y,x2:w-right,y2:y,class:'axis'})));
  current.forEach((v,i)=>{
    const moved=row.moves.includes(i),color=moved?'var(--amber)':'var(--accent)';
    svg.append(svgNode('line',{x1:x(v),y1:145,x2:x(s[row.assignment[i]]),y2:65,style:'stroke:'+color+';stroke-width:'+(moved?3:1.5)}));
  });
  s.forEach((v,j)=>{
    const occupied=row.assignment.includes(j);
    svg.append(svgNode('circle',{cx:x(v),cy:60,r:7,style:'fill:'+(occupied?'var(--ink)':'var(--panel)')+';stroke:var(--muted);stroke-width:2'}));
    svg.append(svgNode('text',{x:x(v),y:37,'text-anchor':'middle',class:'node-label'},v));
  });
  current.forEach((v,i)=>{
    svg.append(svgNode('circle',{cx:x(v),cy:150,r:6,style:'fill:'+(i===index?'var(--amber)':'var(--accent)')}));
    svg.append(svgNode('text',{x:x(v),y:176+(i%2)*19,'text-anchor':'middle',class:'node-label'},'请求 '+(i+1)+'：'+v));
  });
  svg.append(svgNode('text',{x:w/2,y:224,'text-anchor':'middle'},'一维坐标 · 橙线为本步改派，橙点为新请求'));
  $('assignment-chart').replaceChildren(svg);
  $('matching-step-label').textContent='第 '+(index+1)+' / '+trace.history.length+' 步 · 新请求 '+requests[index]+' · 当前距离 '+row.cost+' · 本步改派 '+row.moves.length+' 次';
  $('matching-prev').disabled=index===0; $('matching-next').disabled=index===trace.history.length-1;
  const moves=make('div');
  if(!row.moves.length) moves.textContent='本步保留已有分配，将新请求放入服务点 '+s[row.assignment[index]]+'。';
  else for(const i of row.moves) {
    const before=trace.history[index-1].assignment[i];
    moves.append(make('div','请求 '+(i+1)+'：服务点 '+s[before]+' → '+s[row.assignment[i]]+'；累计改派 '+row.counts[i]+' / '+trace.budget+' 次。'));
  }
  $('matching-moves').replaceChildren(moves);
  lineChart('cost-chart','各到达阶段的匹配距离',trace.history.map(r=>r.t),[
    {label:names[trace.policy],color:colors[trace.policy],values:trace.history.map(r=>r.cost)},
    {label:'当前前缀精确参照',color:colors.prefix_optimum,values:trace.oracle_costs,dashed:true}
  ],'请求到达次数','匹配距离（坐标单位）');
}
async function loadReport() {
  const version=++state.reportVersion;
  try {
    const data=await api('report?key='+encodeURIComponent($('matching-report').value));
    if(version!==state.reportVersion) return;
    $('matching-report-body').replaceChildren(window.MaxcoverReport.render(data.text));
  } catch(error) {if(version===state.reportVersion) message(error.message,true);}
}
$('matching-start').addEventListener('click',async()=>{
  const button=$('matching-start'); if(button.disabled) return;
  button.disabled=true; $('matching-refresh').disabled=true;
  message('正在运行固定实验，并核验本次结果…');
  try {const data=await api('run',{split:$('matching-split').value}); await refresh(data.id); message('本次计算与独立核验已完成。');}
  catch(error) {message(error.message,true);}
  finally {button.disabled=false; $('matching-refresh').disabled=false;}
});
$('matching-refresh').addEventListener('click',()=>refresh());
$('matching-run').addEventListener('change',()=>loadDetail($('matching-run').value));
$('matching-family').addEventListener('change',renderComparison);
['matching-case','matching-policy','matching-budget'].forEach(id=>$(id).addEventListener('change',loadTrace));
$('matching-step').addEventListener('input',renderStep);
$('matching-prev').addEventListener('click',()=>{$('matching-step').value=Number($('matching-step').value)-1;renderStep();});
$('matching-next').addEventListener('click',()=>{$('matching-step').value=Number($('matching-step').value)+1;renderStep();});
$('matching-report').addEventListener('change',loadReport);
refresh();
