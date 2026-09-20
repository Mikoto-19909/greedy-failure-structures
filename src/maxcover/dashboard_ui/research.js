/* Saved study readers and bounded research jobs; computations stay in Python. */
'use strict';
const $ = (id) => document.getElementById(id);
const state = { view: 'studies', epoch: 0, studies: [], jobs: [], archivedJobs: {}, archiveAvailable: false, source: null, job: null,
  studyRequest: 0, libraryRequest: 0, jobRequest: 0, jobsRequest: 0, resultKey: null, timer: null };
const labels = {
  r2: 'R2 · 预算扫描', r3: 'R3 · 配对差异', r4: 'R4 · 上界校准', r4_dual: 'R4 · 上界对照',
  mine: '反例挖掘', refute: '猜想检验', queued: '排队中', running: '运行中', completed: '计算完成',
  failed: '失败', interrupted: '中断', counterexample_found: '找到反例', domain_exhausted: '指定有限域已穷尽',
  no_counterexample_in_input: '本次已评估输入中未找到反例',
  budget_exhausted: '预算耗尽', deletion_minimal: '已完成单步删减检查',
  n: 'n', endpoints: '端点数', delta: 'high − low 首步不可恢复率差值', lower: '区间下界', upper: '区间上界',
  confidence: '置信水平', direction: '比较方向', low_first_loss: 'low 端点首步损失', high_first_loss: 'high 端点首步损失',
  low_failure: 'low 端点失效', high_failure: 'high 端点失效', low_relative_gap: 'low 端点相对损失', high_relative_gap: 'high 端点相对损失',
  low_exposure: 'low 端点暴露量', high_exposure: 'high 端点暴露量', graphs_without_exposure_separation: '暴露量未分离的原图数',
  run_status: '运行记录', verification: '独立验证记录', summary_verification: '汇总验证记录', analysis_status: '分析记录',
  status: '状态', validated: '本任务独立验证', counts: '计数', input_count: '输入实例数', selected: '入选数',
  evaluated: '已评估', eligible: '满足前提', visited: '已访问候选', examined: '已检查候选',
  counterexamples: '反例数', failures: '反例数', scanned: '已访问候选', rejected: '未满足前提', candidate_space: '候选空间', max_instances: '候选预算', combinations: '组合数',
  exact: '精确评估', combination_limit: '组合超限', passed: '记录中的通过状态', skipped: '跳过数',
  universe_size: '全集大小', set_count: '集合数', k: '选择预算 k', coverage: '覆盖数', greedy_coverage: 'Greedy 覆盖',
  optimal_coverage: '最优覆盖', optimum: '最优值', relative_gap: '相对损失', greedy: 'Greedy', optimal: '最优解',
  selected_indices: '选择索引', selection: '选择顺序', marginal_gains: '逐步新增覆盖', tie_candidates: '平局候选',
  greedy_selected: 'Greedy 选择顺序', optimum_selected: '最优选择见证', trace: '逐步轨迹', gap: '相对损失',
  source: '来源', population: '样本标签', case: '案例', rank: '排名', input: '输入文件', top: '选取数量',
  max_combinations: '每实例最优组合上限', max_evaluations: '每案例删减评估上限', timeout_seconds: '任务时限（秒）',
  set_size: '每集合大小', unique_sets: '禁止重复集合', max_frequency: '元素最大频数', min_ratio: '最低覆盖比例 [p,q]',
  budget: '候选枚举上限', output_dir: '输出目录', retry_of: '重新运行来源', error: '错误',
};
const label = (value) => labels[value] || String(value);
const el = (tag, text, className) => {
  const node = document.createElement(tag); if (text !== undefined) node.textContent = text;
  if (className) node.className = className; return node;
};
function message(text = '', error = false) { $('research-message').textContent = text; $('research-message').classList.toggle('error', error); }
async function api(url, body) {
  const response = await fetch(url, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  let data;
  try { data = await response.json(); } catch (_) { throw new Error(`服务器响应无法读取（HTTP ${response.status}）`); }
  if (!response.ok) throw new Error(data.error || `请求失败（HTTP ${response.status}）`);
  return data;
}
function link(text, url) { const node = el('a', text, 'button button-secondary'); node.href = url; node.download = ''; return node; }
function statusBadge(status) { return el('span', label(status || '未知'), `research-state ${String(status).replace(/[^a-z_]/g, '')}`); }
function scalar(value) {
  if (value === null || value === undefined) return '未提供';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (value === 'passed') return '通过（历史记录）';
  return label(value);
}
// Stored summaries retain their original fields. Long arrays are explicitly previewed.
function values(data, depth = 0, context = '') {
  const wrapper = el('div');
  if (data === null || typeof data !== 'object') { wrapper.textContent = scalar(data); return wrapper; }
  if (Array.isArray(data) && data.every((item) => item === null || typeof item !== 'object')) {
    wrapper.textContent = data.length ? data.map(scalar).join('、') : '空列表'; return wrapper;
  }
  const entries = Object.entries(data), simple = el('dl', undefined, 'research-values');
  for (const [key, value] of entries.slice(0, 50)) {
    if (value !== null && typeof value === 'object' && !Array.isArray(value) && depth < 5) {
      wrapper.append(el('h4', label(key), 'research-subfield'), values(value, depth + 1));
    } else if (Array.isArray(value) && value.some((item) => item !== null && typeof item === 'object') && depth < 5) {
      const details = el('details'); details.append(el('summary', `${label(key)}（${value.length} 项）`));
      value.slice(0, 30).forEach((item, index) => { details.append(el('h4', `#${index + 1}`), values(item, depth + 1)); });
      if (value.length > 30) details.append(el('p', `预览前 30 / ${value.length} 项，完整内容请下载原始文件。`, 'help-text'));
      wrapper.append(details);
    } else {
      const name = context === 'r3_primary' && key === 'n' ? '原图数量 n' : context === 'params' && key === 'n' ? '全集大小 n' : context === 'params' && key === 'm' ? '集合数 m' : key === 'input' && typeof value === 'number' ? '输入实例数' : label(key);
      simple.append(el('dt', name), el('dd', Array.isArray(value) ? value.map(scalar).join('、') : typeof value === 'object' && value !== null ? JSON.stringify(value) : scalar(value)));
    }
  }
  wrapper.prepend(simple);
  if (entries.length > 50) wrapper.append(el('p', `预览前 50 / ${entries.length} 个字段，完整内容请下载原始文件。`, 'help-text'));
  return wrapper;
}
function showView(view) {
  state.view = view; state.epoch++; clearTimeout(state.timer); message();
  for (const name of ['studies', 'experiments', 'jobs']) {
    $(`view-${name}`).hidden = name !== view;
    if (name === view) $(`nav-${name}`).setAttribute('aria-current', 'page'); else $(`nav-${name}`).removeAttribute('aria-current');
  }
  $(`${view}-title`).focus();
  if (view === 'jobs') loadJobs();
}

function renderLibrary() {
  const query = $('study-search').value.trim().toLowerCase(), kind = $('study-kind').value;
  const sources = state.studies.filter((source) => (!kind || source.kind === kind) && `${source.label} ${source.source} ${source.kind}`.toLowerCase().includes(query));
  $('study-library').replaceChildren(); $('study-count').textContent = `${sources.length} / ${state.studies.length} 份已有专题产物`;
  if (!sources.length) $('study-library').append(el('p', state.studies.length ? '当前筛选没有匹配来源。' : '项目 experiments/ 与 results/ 中尚未找到 R2–R4 产物。将已有专题目录放入这些位置后刷新；正式证据可以按项目文档从已发布快照恢复。', 'research-empty'));
  for (const source of sources) {
    const card = el('article', undefined, `research-card${state.source === source.source ? ' active' : ''}`);
    card.append(el('p', label(source.kind), 'research-kind'), el('h3', source.label), el('p', source.source, 'help-text'), el('p', source.statistical_unit));
    if (source.error) card.append(el('p', source.error, 'research-error'));
    const button = el('button', '查看保存产物', 'button button-secondary'); button.addEventListener('click', () => loadStudy(source.source));
    card.append(button); $('study-library').append(card);
  }
}
async function loadLibrary() {
  const request = ++state.libraryRequest, epoch = state.epoch; message('正在读取专题库…');
  try {
    const data = await api('/api/studies/library'); if (request !== state.libraryRequest) return;
    state.studies = data.sources; $('study-notice').textContent = data.notice || ''; renderLibrary();
    if (epoch === state.epoch) message();
  } catch (error) { if (request === state.libraryRequest && epoch === state.epoch) message(error.message, true); }
}
const studyArtifact = (source, file) => '/api/studies/artifact?' + new URLSearchParams({ source, file });
async function loadStudy(source) {
  const request = ++state.studyRequest, epoch = state.epoch; state.source = source;
  $('study-detail').hidden = true; renderLibrary(); message('正在读取专题数据…');
  try {
    const data = await api('/api/studies/detail?' + new URLSearchParams({ source }));
    if (request !== state.studyRequest || epoch !== state.epoch) return;
    $('study-title').textContent = data.title || data.label; $('study-source').textContent = data.source;
    $('study-unit').textContent = `统计单位：${data.statistical_unit}`; $('study-statuses').replaceChildren();
    for (const [key, record] of Object.entries(data.statuses || {})) {
      const card = el('div', undefined, 'research-card'); card.append(el('h4', label(key)));
      card.append(el('p', !record.present ? '未保存此记录' : record.error ? record.error : '已保存历史记录；本次读取未重新验证', record.error ? 'research-error' : 'help-text'));
      if (record.data) card.append(values(record.data));
      if (record.omitted_fields?.length) card.append(el('p', `逐图字段 ${record.omitted_fields.join('、')} 请从完整文件查看。`, 'help-text'));
      $('study-statuses').append(card);
    }
    $('study-notes').replaceChildren(...[...(data.notes || []), ...((data.errors || []).map((item) => `${item.file}：${item.error}`))].map((note) => el('p', note, 'wb-note')));
    $('study-documents').replaceChildren();
    for (const document of data.documents || []) {
      const section = el('section', undefined, 'research-table'); section.append(el('h4', document.name));
      if (document.error) section.append(el('p', document.error, 'research-error')); else section.append(values(document.data, 0, data.kind === 'r3' && document.name === 'primary_summary.json' ? 'r3_primary' : ''));
      if (document.omitted_fields?.length) section.append(el('p', `字段 ${document.omitted_fields.join('、')} 未内联展示，请下载原始 JSON。`, 'help-text'));
      if ((data.source_files || []).includes(document.name)) section.append(link('下载原始 JSON', studyArtifact(source, document.name)));
      $('study-documents').append(section);
    }
    $('study-tables').replaceChildren();
    for (const table of data.tables || []) {
      const section = el('section', undefined, 'research-table'), heading = el('div', undefined, 'wb-heading');
      heading.append(el('h4', table.name));
      if ((data.source_files || []).includes(table.name)) heading.append(link('下载完整 CSV', studyArtifact(source, table.name)));
      section.append(heading, el('p', table.total === null ? '文件读取失败，记录总数未知。' : `显示 ${table.shown} / ${table.total} 条保存记录${table.truncated ? `；仅预览前 ${table.limit} 条，请下载完整 CSV。` : '。'} 字段与数值按原文件显示。`, 'help-text'));
      if (table.error) section.append(el('p', table.error, 'research-error'));
      const wrap = el('div', undefined, 'wb-table-wrap'), grid = el('table', undefined, 'wb-table'), head = el('thead'), header = el('tr'), body = el('tbody');
      for (const column of table.columns) { const th = el('th', column); th.scope = 'col'; header.append(th); }
      head.append(header);
      for (const row of table.rows) { const tr = el('tr'); for (const column of table.columns) tr.append(el('td', row[column] ?? '')); body.append(tr); }
      grid.append(head, body); wrap.append(grid); section.append(wrap); $('study-tables').append(section);
    }
    const downloads = el('div', undefined, 'wb-actions');
    for (const file of data.source_files || []) downloads.append(link(`下载 ${file}`, studyArtifact(source, file)));
    $('study-tables').append(downloads); $('study-detail').hidden = false; message(); $('study-title').focus();
  } catch (error) { if (request === state.studyRequest && epoch === state.epoch) message(error.message, true); }
}

async function loadMineSources() {
  try {
    const data = await api('/api/workbench/library');
    for (const source of data.sources || []) {
      if (source.kind !== 'r1' || source.error) continue;
      const option = el('option', source.label || source.source); option.value = `${source.source}/paths.jsonl`; $('mine-source').append(option);
    }
  } catch (_) { /* A manual project-relative input remains available. */ }
}
const integer = (id) => Number($(id).value);
const optionalInteger = (id) => $(id).value === '' ? null : integer(id);
function previewClaim() {
  $('claim-preview').textContent = `本次问题：在 n=${$('refute-n').value}、m=${$('refute-m').value}、k=${$('refute-k').value} 的指定域内，满足条件的每个实例是否都有 G/O ≥ ${$('refute-p').value}/${$('refute-q').value}？O=0 时覆盖要求成立。`;
}
async function submit(kind, event) {
  event.preventDefault(); const button = $(`submit-${kind}`); if (button.disabled) return;
  const epoch = state.epoch;
  let params;
  if (kind === 'mine') {
    params = { kind, input: $('mine-input').value.trim(), population: $('mine-population').value.trim(), top: integer('mine-top'), max_combinations: integer('mine-combinations'), max_evaluations: integer('mine-evaluations'), timeout_seconds: integer('mine-timeout') };
  } else {
    params = { kind, n: integer('refute-n'), m: integer('refute-m'), k: integer('refute-k'), set_size: optionalInteger('refute-size'), unique_sets: $('refute-unique').checked, max_frequency: optionalInteger('refute-frequency'), min_ratio: [integer('refute-p'), integer('refute-q')], budget: integer('refute-budget'), max_combinations: integer('refute-combinations'), timeout_seconds: integer('refute-timeout') };
    if (params.k > params.m || (params.set_size !== null && params.set_size > params.n) || (params.max_frequency !== null && params.max_frequency > params.m) || params.min_ratio[0] > params.min_ratio[1]) {
      message('请检查条件：k ≤ m，集合大小 ≤ n，最大频数 ≤ m，比例分子 ≤ 分母。', true); return;
    }
  }
  button.disabled = true; message('正在保存输入与参数并提交任务…');
  try {
    const job = await api('/api/research/jobs', params);
    if (epoch !== state.epoch) return;
    state.job = job.id; state.resultKey = null; $('job-detail').hidden = true; showView('jobs');
  } catch (error) { if (epoch === state.epoch) message(error.message, true); }
  finally { button.disabled = false; }
}

function renderJobs() {
  const filter = $('job-filter').value, jobs = state.jobs.filter((job) => (!filter || job.status === filter)
    && ($('show-archived-jobs').checked || !state.archivedJobs[job.id]?.archived)); $('jobs-body').replaceChildren();
  if (!jobs.length) { const row = el('tr'), td = el('td', '暂无匹配任务。提交一项反例挖掘或猜想检验后，记录会保留在这里。'); td.colSpan = 5; row.append(td); $('jobs-body').append(row); }
  for (const job of jobs) {
    const row = el('tr'), id = el('td', label(job.kind)); id.append(el('small', job.id));
    if (state.archivedJobs[job.id]?.archived) id.append(el('small', '已归档'));
    const status = el('td'); status.append(statusBadge(job.status));
    const summary = el('td', job.summary?.status ? label(job.summary.status) : job.error || '等待结果');
    if (job.summary?.validated !== undefined) summary.append(el('small', `独立验证：${job.summary.validated ? '通过' : '未通过'}`));
    const action = el('td'), button = el('button', '查看任务', 'button button-secondary');
    button.addEventListener('click', () => { state.job = job.id; state.resultKey = null; $('job-detail').hidden = true; loadJob(job.id); });
    action.append(button);
    if (state.archiveAvailable && !job.corrupt_record && ['completed', 'failed', 'interrupted'].includes(job.status)) {
      const archived = Boolean(state.archivedJobs[job.id]?.archived);
      const archive = el('button', archived ? '还原' : '归档', 'button button-secondary');
      archive.setAttribute('aria-label', `${archived ? '还原' : '归档'}任务 ${job.id}`);
      archive.addEventListener('click', async () => {
        archive.disabled = true; const epoch = state.epoch;
        try {
          await api('/api/local/archive', { kind: 'job', id: job.id, archived: !archived });
          if (epoch === state.epoch) await loadJobs();
        } catch (error) { if (epoch === state.epoch) message(error.message, true); }
        finally { archive.disabled = false; }
      });
      action.append(archive);
    }
    row.append(id, status, el('td', job.created_at), summary, action); $('jobs-body').append(row);
  }
}
async function loadJobs() {
  clearTimeout(state.timer); const request = ++state.jobsRequest, epoch = state.epoch;
  try {
    const archiveRequest = api('/api/local/archive?kind=job').catch((error) => ({ entries: {}, unavailable: true,
      warnings: [`归档状态不可用，暂时显示全部原任务并停用归档操作：${error.message}`] }));
    const [data, archives] = await Promise.all([api('/api/research/jobs'), archiveRequest]);
    if (request !== state.jobsRequest || epoch !== state.epoch) return;
    state.jobs = data.jobs; state.archivedJobs = archives.entries; state.archiveAvailable = !archives.unavailable; renderJobs();
    const running = data.jobs.filter((job) => job.status === 'running').length, queued = data.jobs.filter((job) => job.status === 'queued').length;
    $('queue-state').textContent = `${data.queue_state === 'recovering' ? '正在恢复任务记录' : '队列可用'} · ${running} 项运行中 · ${queued} 项排队 · ${data.jobs.length} 项历史记录。页面每 2 秒刷新；离开此页不影响已提交任务。`;
    if (state.job && state.archivedJobs[state.job]?.archived && !$('show-archived-jobs').checked) {
      state.job = null; ++state.jobRequest; state.resultKey = null; $('job-detail').hidden = true;
    }
    message((archives.warnings || []).join(' '), Boolean(archives.unavailable)); if (state.job) await loadJob(state.job, false);
  } catch (error) { if (request === state.jobsRequest && epoch === state.epoch) message(error.message, true); }
  finally { if (request === state.jobsRequest && epoch === state.epoch && state.view === 'jobs') state.timer = setTimeout(loadJobs, 2000); }
}
async function loadJob(id, focus = true) {
  const request = ++state.jobRequest, epoch = state.epoch;
  try {
    const job = await api(`/api/research/jobs/${encodeURIComponent(id)}`);
    if (request !== state.jobRequest || epoch !== state.epoch || state.job !== id) return;
    $('job-id').textContent = job.id; $('job-title').textContent = `${label(job.kind)} · ${label(job.status)}`;
    $('job-metadata').replaceChildren();
    for (const [key, value] of [['创建时间', job.created_at], ['开始时间', job.started_at], ['结束时间', job.finished_at], ['输出目录', job.output_dir], ['重新运行来源', job.retry_of]]) {
      $('job-metadata').append(el('dt', key), el('dd', value || '—'));
    }
    $('retry-job').hidden = Boolean(job.corrupt_record) || !['failed', 'interrupted'].includes(job.status); $('job-error').hidden = !job.error; $('job-error').textContent = job.error || '';
    $('job-params').replaceChildren(values(job.params, 0, 'params')); $('job-log').textContent = Array.isArray(job.log_tail) ? job.log_tail.join('\n') : job.log_tail || '暂无日志。';
    if (state.resultKey !== `${id}:${job.finished_at}`) $('job-result').hidden = true;
    $('job-detail').hidden = false; if (focus) $('job-title').focus();
    if (job.status !== 'completed') { $('job-result').hidden = true; state.resultKey = null; }
    else if (state.resultKey !== `${id}:${job.finished_at}`) {
      const result = await api(`/api/research/jobs/${encodeURIComponent(id)}/result`);
      if (request !== state.jobRequest || epoch !== state.epoch || state.job !== id) return;
      renderResult(id, result); state.resultKey = `${id}:${job.finished_at}`;
    }
  } catch (error) { if (request === state.jobRequest && epoch === state.epoch) { $('job-detail').hidden = true; message(error.message, true); } }
}
function casePanel(title, data) {
  const panel = el('div', undefined, 'research-panel'); panel.append(el('h4', title));
  if (!data) { panel.append(el('p', '无此阶段记录。', 'help-text')); return panel; }
  if (data.status) panel.append(el('p', label(data.status), 'help-text'));
  const instance = data.instance || {};
  panel.append(values({ universe_size: instance.universe_size, set_count: instance.sets?.length, k: instance.k }));
  if (Array.isArray(instance.sets)) instance.sets.forEach((set, index) => panel.append(el('p', `S${index} = {${Array.isArray(set) ? set.join(', ') : set}}`, 'research-set')));
  if (data.evaluation) panel.append(values(data.evaluation));
  return panel;
}
function renderResult(id, result) {
  const summary = result.summary || {}, { cases = [], ...overview } = summary; $('job-summary').replaceChildren(values(overview));
  const interpretation = result.job?.kind === 'mine' ? '挖掘结果来自筛选后的输入；案例数量与缩小结果不用于估计总体失效率。' : summary.status === 'domain_exhausted' ? '搜索已覆盖本次指定的有限域。请同时检查满足前提的实例数；结论不推广到其他域。' : summary.status === 'budget_exhausted' ? '预算用完，搜索未完成。未找到反例不能确认该有限域内猜想成立。' : summary.status === 'counterexample_found' ? '已找到满足本次结构条件、违反覆盖要求的反例。请阅读实际集合与最优见证。' : '请结合本次输入、停止状态和可用精确参考读取结果。';
  $('job-summary').append(el('p', interpretation, 'wb-note'));
  $('job-artifacts').replaceChildren();
  for (const artifact of result.artifacts || []) $('job-artifacts').append(link(`下载 ${artifact.name}`, `/api/research/jobs/${encodeURIComponent(id)}/files/${encodeURIComponent(artifact.name)}`));
  $('job-cases').replaceChildren();
  for (const [index, item] of cases.entries()) {
    const section = el('section', undefined, 'research-case'); section.append(el('h3', `案例 ${item.rank || index + 1}`));
    if (item.source) section.append(values({ source: item.source }));
    const grid = el('div', undefined, 'research-case-grid'); grid.append(casePanel('原始实例', item.original));
    if (item.reduced) grid.append(casePanel('缩小后的实例', item.reduced)); section.append(grid);
    if (item.reduced) section.append(el('p', '缩小只保持 k 与 G < O；若用于结构猜想，必须重新核对前提。单步删减完成不表示全局最小。', 'help-text'));
    $('job-cases').append(section);
  }
  if (!cases.length) $('job-cases').append(el('p', '本次没有可展示的反例案例，请结合停止状态和计数读取结果。', 'help-text'));
  $('job-document').replaceChildren(values(result.document)); $('job-result').hidden = false;
}
async function retryJob() {
  const id = state.job, epoch = state.epoch; $('retry-job').disabled = true;
  try {
    const job = await api(`/api/research/jobs/${encodeURIComponent(id)}/retry`, {});
    if (epoch !== state.epoch || id !== state.job) return;
    state.job = job.id; state.resultKey = null; $('job-detail').hidden = true; await loadJobs();
  } catch (error) { if (epoch === state.epoch) message(error.message, true); }
  finally { $('retry-job').disabled = false; }
}
for (const view of ['studies', 'experiments', 'jobs']) $(`nav-${view}`).addEventListener('click', () => showView(view));
$('refresh-studies').addEventListener('click', loadLibrary);
$('study-search').addEventListener('input', renderLibrary); $('study-kind').addEventListener('change', renderLibrary);
$('refresh-jobs').addEventListener('click', loadJobs); $('job-filter').addEventListener('change', renderJobs); $('retry-job').addEventListener('click', retryJob);
$('show-archived-jobs').addEventListener('change', () => loadJobs());
for (const kind of ['mine', 'refute']) {
  $(`mode-${kind}`).addEventListener('click', () => {
    for (const mode of ['mine', 'refute']) { $(`${mode}-form`).hidden = mode !== kind; $(`mode-${mode}`).className = `button button-${mode === kind ? 'primary' : 'secondary'}`; $(`mode-${mode}`).setAttribute('aria-pressed', String(mode === kind)); }
    message();
  });
  $(`${kind}-form`).addEventListener('submit', (event) => submit(kind, event));
}
$('mine-source').addEventListener('change', () => { if ($('mine-source').value) $('mine-input').value = $('mine-source').value; });
$('mine-input').addEventListener('input', () => { if ($('mine-source').value !== $('mine-input').value) $('mine-source').value = ''; });
$('refute-form').addEventListener('input', previewClaim);
previewClaim(); loadLibrary(); loadMineSources();
