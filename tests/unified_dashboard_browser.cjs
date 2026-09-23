/* Integration verification, not a performance or research experiment.
 * A private copy of the real runner adds a short delay and records task IDs.
 * The server imports that copy; static assets come from the current worktree.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'output', 'playwright'); fs.mkdirSync(output, { recursive: true });
const fixture = fs.mkdtempSync(path.join(output, 'unified-'));
const python = process.env.DASHBOARD_PYTHON || 'python';
const write = (relative, content) => { const file = path.join(fixture, relative); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, content); return file; };
fs.cpSync(path.join(root, 'src', 'maxcover'), path.join(fixture, 'src', 'maxcover'), {
  recursive: true, filter: (source) => !['__pycache__', 'dashboard_ui'].includes(path.basename(source)) });
const benchmarkFile = path.join(fixture, 'src', 'maxcover', 'benchmark.py');
let benchmark = fs.readFileSync(benchmarkFile, 'utf8').replace(/\r\n/g, '\n');
assert(benchmark.includes('def _execute_task(task: _RunTask) -> _CompletedRun:\n'));
benchmark = benchmark.replace('def _execute_task(task: _RunTask) -> _CompletedRun:', 'def _execute_task_original_for_ui_test(task: _RunTask) -> _CompletedRun:');
benchmark = benchmark.replace('def _record_for_completed(completed: _CompletedRun) -> RunRecord:', [
  'def _execute_task(task: _RunTask) -> _CompletedRun:',
  '    import os',
  "    fixture_root = Path(__file__).resolve().parents[2]",
  "    markers = fixture_root / 'worker-markers'",
  '    markers.mkdir(exist_ok=True)',
  "    marker = markers / f'{os.getpid()}-{time.time_ns()}-{task.run_id}.json'",
  "    item = {'run_id': task.run_id, 'config_hash': task.config_hash, 'done': False}",
  '    marker.write_text(json.dumps(item))',
  '    try:',
  "        if (fixture_root / 'fail-on-execution').exists():",
  "            raise RuntimeError('complete checkpoint unexpectedly reran an algorithm')",
  '        time.sleep(0.12)',
  '        return _execute_task_original_for_ui_test(task)',
  '    finally:',
  "        item['done'] = True",
  '        marker.write_text(json.dumps(item))',
  '', '', 'def _record_for_completed(completed: _CompletedRun) -> RunRecord:'
].join('\n'));
fs.writeFileSync(benchmarkFile, benchmark);
const template = '{"schema_version":3,"name":"unified browser fixture","base_seed":18446744073709551615,"repetitions":40,"algorithms":[{"name":"greedy"}],"cases":[{"name":"tiny","family":"uniform","universe_size":8,"set_count":5,"k":2,"density":0.5}]}';
write('configs/template.json', template);
write('configs/legacy.json', template.replace('"repetitions":40', '"repetitions":2'));
write('experiments/saved-r1/paths.jsonl', fs.readFileSync(path.join(root, 'experiments/r1_prefix_exchange_v1/paths.jsonl')));
write('results/workbench_jobs/.fixture', '');
const env = { ...process.env, PYTHONPATH: path.join(fixture, 'src'), PYTHONIOENCODING: 'utf-8' };
const launcher = write('server.py', [
  'from pathlib import Path', 'import maxcover.dashboard as dashboard',
  `dashboard.STATIC_ROOT = Path(${JSON.stringify(path.join(root, 'src', 'maxcover', 'dashboard_ui'))})`,
  `dashboard.serve_dashboard(port=0, project_root=Path(${JSON.stringify(fixture)}))`, ''
].join('\n'));
const blockerFile = write('blocker.py', [
  'from pathlib import Path', 'import time', 'from maxcover.dashboard_jobs import _FileLock',
  "lock = _FileLock(Path('results/workbench_jobs/execution.lock'))", "print('LOCK_READY', flush=True)",
  "while not Path('release-queue').exists(): time.sleep(0.02)", 'lock.close()', ''
].join('\n'));
let server, blocker, browser, url, log = '';
const checks = [], errors = [];
const passed = (name) => { checks.push(name); console.log('PASS ' + name); };
function ready(process, matcher) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('startup timeout: ' + log)), 20000);
    process.once('error', reject);
    process.once('exit', (code) => { clearTimeout(timer); reject(new Error('early process exit ' + code + ': ' + log)); });
    process.stdout.on('data', (chunk) => { const match = String(chunk).match(matcher); if (match) { clearTimeout(timer); resolve(match[0]); } });
    process.stderr.on('data', (chunk) => { log += String(chunk); });
  });
}
async function startServer() {
  server = spawn(python, ['-u', launcher], { cwd: fixture, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  url = await ready(server, /http:\/\/127\.0\.0\.1:\d+\//);
}
async function stopServer() {
  const target = server; if (!target || target.exitCode !== null) return;
  await new Promise((resolve) => { target.once('exit', resolve); target.kill(); });
}
async function poll(read, predicate, label) {
  const deadline = Date.now() + 30000; let value;
  while (Date.now() < deadline) { value = await read(); if (predicate(value)) return value; await new Promise((resolve) => setTimeout(resolve, 40)); }
  throw new Error(label + ': ' + JSON.stringify(value));
}
function csvRows(file) {
  const result = spawnSync(python, ['-c', "import csv,json,sys; from pathlib import Path; print(json.dumps(list(csv.DictReader(Path(sys.argv[1]).open(encoding='utf-8',newline='')))))", file], { encoding: 'utf8', windowsHide: true });
  assert.equal(result.status, 0, result.stderr); return JSON.parse(result.stdout);
}
function markers() {
  const directory = path.join(fixture, 'worker-markers');
  return fs.existsSync(directory) ? fs.readdirSync(directory).map((name) => ({ name, ...JSON.parse(fs.readFileSync(path.join(directory, name), 'utf8')) })) : [];
}
(async () => {
  blocker = spawn(python, ['-u', blockerFile], { cwd: fixture, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  await ready(blocker, /LOCK_READY/); await startServer();
  browser = await chromium.launch({ headless: true, ...(process.env.DASHBOARD_BROWSER_CHANNEL ? { channel: process.env.DASHBOARD_BROWSER_CHANNEL } : {}) });
  const context = await browser.newContext({ viewport: { width: 1366, height: 960 }, acceptDownloads: true });
  const page = await context.newPage(); page.on('pageerror', (error) => errors.push(error.message)); page.on('dialog', (dialog) => dialog.accept());
  const api = (route, payload) => page.evaluate(async ({ route, payload }) => {
    const response = await fetch(route, payload === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    return { status: response.status, data: await response.json() };
  }, { route, payload });
  const job = async (id) => (await api('/api/research/jobs/' + id)).data;
  const terminal = (id) => poll(() => job(id), (item) => ['completed', 'paused', 'cancelled', 'failed', 'interrupted'].includes(item.status), 'job did not terminate');
  const configIdle = (target) => target.waitForFunction(() => !document.querySelector('#config-select').disabled);
  async function detail(id) {
    await page.locator('#refresh-jobs').click();
    const row = page.locator('#jobs-body tr').filter({ hasText: id }); await row.getByRole('button', { name: '查看任务', exact: true }).click();
    await page.waitForFunction((expected) => document.querySelector('#job-id').textContent === expected && !document.querySelector('#job-detail').hidden, id);
  }
  async function control(action) {
    const response = page.waitForResponse((response) => response.url().endsWith('/' + action) && response.request().method() === 'POST');
    await page.locator('#' + action + '-job').click(); const result = await response;
    assert.equal(result.status(), 202, await result.text()); return result.json();
  }
  await page.goto(url + 'experiments'); await configIdle(page);
  await page.locator('#config-select').selectOption('template.json'); await configIdle(page);
  await page.locator('#config-copy').click(); await configIdle(page);
  const local = await page.locator('#config-select').inputValue();
  await page.locator('#config-name').fill('unified saved copy'); await page.locator('#config-apply').click(); await configIdle(page);
  await page.locator('#config-save').click(); await configIdle(page);
  await page.locator('#config-run').click(); await page.waitForFunction(() => !document.querySelector('#submit-benchmark').disabled);
  assert.equal(await page.locator('#benchmark-config').inputValue(), local);
  assert.match(await page.locator('#benchmark-preview').innerText(), /40 个实例/);
  assert.equal(await page.locator('#mode-benchmark').getAttribute('aria-pressed'), 'true');
  assert.equal((await api('/api/research/jobs')).data.jobs.length, 0);
  await page.locator('#benchmark-output').fill('unified'); await page.locator('#benchmark-workers').fill('2');
  const submitted = page.waitForResponse((response) => response.url().endsWith('/api/research/jobs') && response.request().method() === 'POST');
  await page.locator('#submit-benchmark').click(); const first = await (await submitted).json();
  await page.locator('#view-jobs').waitFor({ state: 'visible' }); await detail(first.id);
  assert.equal((await job(first.id)).status, 'queued');
  passed('UI copies and edits a local configuration, preflights its actual scale and queues workers=2 without implicit execution');
  const editor = await context.newPage(); editor.on('dialog', (dialog) => dialog.accept());
  await editor.goto(url + 'experiments?config=' + encodeURIComponent(local)); await configIdle(editor);
  await editor.locator('#config-seed').fill('18446744073709551614'); await editor.locator('#config-repetitions').fill('55');
  await editor.locator('#config-apply').click(); await configIdle(editor); await editor.locator('#config-save').click(); await configIdle(editor); await editor.close();
  const snapshot = fs.readFileSync(path.join(fixture, 'results/workbench_jobs', first.id, 'config.json'), 'utf8');
  assert.match(snapshot, /18446744073709551615/); assert.match(snapshot, /"repetitions": 40/);
  assert.match(fs.readFileSync(path.join(fixture, 'configs', local), 'utf8'), /18446744073709551614/);
  const changed = (await api('/api/config?path=' + encodeURIComponent(local))).data;
  const duplicate = await api('/api/run', { config: local, config_hash: changed.config_hash, output: 'unified', workers: 2, force: true });
  assert.equal(duplicate.status, 409);
  const legacyConfig = (await api('/api/config?path=legacy.json')).data;
  const legacy = await api('/api/run', { config: 'legacy.json', config_hash: legacyConfig.config_hash, output: 'legacy', workers: 1 });
  assert.equal(legacy.status, 202); assert.equal(legacy.data.status, 'queued');
  assert((await api('/api/jobs')).data.jobs.some((item) => item.id === first.id));
  assert((await api('/api/research/jobs')).data.jobs.some((item) => item.id === legacy.data.id));
  passed('editing the source leaves the queued snapshot exact; old API shares reservations, queue and history');
  write('release-queue', 'release');
  await poll(() => job(first.id), (item) => item.status === 'running' && item.progress.saved_runs >= 1, 'benchmark did not publish progress');
  await detail(first.id); assert.match(await page.locator('#job-progress').innerText(), /\/ 40/);
  const readers = await Promise.all([
    api('/api/result?name=unified'), api('/api/workbench/compare?source=results%2Funified'),
    api('/api/workbench/library'), api('/api/results'), api('/api/workbench/compare?source=experiments%2Fsaved-r1'),
    api('/api/run', { config: local, config_hash: changed.config_hash, output: 'unified', workers: 2, force: true })]);
  assert.equal(readers[0].status, 409); assert.equal(readers[1].status, 409);
  assert.equal(readers[2].status, 200);
  const busySource = readers[2].data.sources.find((item) => item.source === 'results/unified');
  assert(busySource?.error); assert.equal(busySource.records, undefined);
  assert.equal(readers[3].status, 200); assert(!readers[3].data.results.some((item) => item.name === 'unified'));
  assert.equal(readers[4].status, 200); assert(readers[4].data.total > 0);
  assert.equal(readers[5].status, 409);
  await control('pause'); const paused = await terminal(first.id); assert.equal(paused.status, 'paused');
  assert(paused.progress.saved_runs > 0 && paused.progress.saved_runs < 40);
  assert(markers().filter((item) => item.config_hash === first.params.config_hash).every((item) => item.done));
  const pausedRows = csvRows(path.join(fixture, 'results/unified/raw_results.csv'));
  const pausedMarkers = new Set(markers().map((item) => item.name));
  const legacyFinished = await terminal(legacy.data.id); assert.equal(legacyFinished.status, 'completed');
  assert(paused.finished_at <= legacyFinished.started_at);
  passed('active readers return 409 while unrelated data remains browsable; UI pause saves a checkpoint and drains workers before the next task');
  await detail(first.id); const second = await control('resume');
  assert.equal(second.output_dir, first.output_dir); assert.equal(second.resume_of, first.id);
  await poll(() => job(second.id), (item) => item.status === 'running' && item.progress.saved_runs > pausedRows.length, 'resume did not progress');
  await detail(second.id); await control('cancel'); const cancelled = await terminal(second.id);
  assert.equal(cancelled.status, 'cancelled'); assert(cancelled.progress.saved_runs < 40);
  const savedIds = new Set(pausedRows.map((row) => row.run_id));
  assert(!markers().some((item) => item.config_hash === first.params.config_hash && !pausedMarkers.has(item.name) && savedIds.has(item.run_id)));
  assert(markers().filter((item) => item.config_hash === first.params.config_hash).every((item) => item.done));
  await detail(second.id); const third = await control('resume'); const completed = await terminal(third.id);
  assert.equal(completed.status, 'completed'); assert.equal(completed.progress.saved_runs, 40);
  assert.equal(completed.params.config_hash, first.params.config_hash); assert.equal(completed.output_dir, first.output_dir);
  const rows = csvRows(path.join(fixture, 'results/unified/raw_results.csv'));
  assert.equal(rows.length, 40); assert.equal(new Set(rows.map((row) => row.run_id)).size, 40);
  assert(rows.every((row) => row.config_hash === first.params.config_hash));
  for (const saved of pausedRows) assert.deepEqual(rows.find((row) => row.run_id === saved.run_id), saved);
  passed('UI resume/cancel/resume keeps the frozen input and directory, preserves saved rows and executes only missing IDs');
  await detail(third.id); await page.locator('#job-result').waitFor({ state: 'visible' });
  assert.match(await page.locator('#job-summary').innerText(), /没有自动执行独立科研验证/);
  const downloadPromise = page.waitForEvent('download'); await page.getByRole('link', { name: '下载 raw_results.csv', exact: true }).click();
  const downloaded = await downloadPromise; const downloadPath = path.join(output, 'unified-raw-results.csv'); await downloaded.saveAs(downloadPath);
  assert.deepEqual(fs.readFileSync(downloadPath), fs.readFileSync(path.join(fixture, 'results/unified/raw_results.csv')));
  const beforeMarkers = markers().length, beforeRows = fs.readFileSync(path.join(fixture, 'results/unified/raw_results.csv'));
  write('fail-on-execution', 'completed IDs must never execute again');
  const fourth = await control('resume'); const repeated = await terminal(fourth.id);
  assert.equal(repeated.status, 'completed'); assert.equal(markers().length, beforeMarkers);
  assert.deepEqual(fs.readFileSync(path.join(fixture, 'results/unified/raw_results.csv')), beforeRows);
  passed('result UI and CSV download match disk; resuming a complete checkpoint never invokes an algorithm');
  await detail(fourth.id); await page.locator('#job-result').waitFor({ state: 'visible' });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, 'unified-dashboard-desktop.png'), fullPage: true });
  await stopServer(); await startServer();
  await page.goto(url + 'research'); await page.locator('#nav-jobs').click(); await detail(fourth.id);
  assert.equal((await api('/api/research/jobs')).data.jobs.length, 5);
  assert.match(await page.locator('#job-title').innerText(), /计算完成/);
  await page.locator('#job-filter').selectOption('paused');
  assert.match(await page.locator('#jobs-body').innerText(), new RegExp(first.id));
  await page.locator('#job-filter').selectOption('cancelled');
  assert.match(await page.locator('#jobs-body').innerText(), new RegExp(second.id));
  await page.locator('#job-filter').selectOption(''); await detail(fourth.id);
  await page.locator('#job-result').waitFor({ state: 'visible' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, 'unified-dashboard-mobile.png'), fullPage: true });
  await page.locator('#job-artifacts').screenshot({ path: path.join(output, 'unified-dashboard-mobile-downloads.png') });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
  assert.deepEqual(errors, []); assert.equal(fs.readFileSync(path.join(fixture, 'configs/template.json'), 'utf8'), template);
  passed('server restart preserves paused/cancelled/completed history, filters and usable 390px result controls');
  fs.writeFileSync(path.join(output, 'unified-dashboard-checks.json'), JSON.stringify({ fixture, checks, attempts: [first.id, second.id, third.id, fourth.id], legacy: legacy.data.id, delaySeconds: 0.12, scope: 'UI correctness fixture, not performance or research evidence' }, null, 2));
  console.log(`Completed ${checks.length} unified dashboard scenarios.`);
})().catch((error) => { console.error(error); console.error(log); process.exitCode = 1; }).finally(async () => {
  write('release-queue', 'release');
  if (server && server.exitCode === null && url) {
    try {
      const response = await fetch(url + 'api/research/jobs'); const history = await response.json();
      for (const job of history.jobs.filter((item) => item.kind === 'benchmark' && ['queued', 'running'].includes(item.status))) {
        await fetch(url + `api/research/jobs/${job.id}/cancel`, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: url.slice(0, -1) }, body: '{}' });
      }
      await poll(async () => (await (await fetch(url + 'api/research/jobs')).json()).jobs,
        (items) => items.every((item) => !['queued', 'running'].includes(item.status)), 'fixture workers did not terminate');
    } catch (error) { console.error('Fixture cleanup diagnostic:', error.message); }
  }
  if (browser) await browser.close();
  await stopServer(); if (blocker && blocker.exitCode === null) blocker.kill();
});
