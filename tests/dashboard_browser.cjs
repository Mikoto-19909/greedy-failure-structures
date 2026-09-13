/* Focused browser regressions. Requires Playwright and a project Python environment.
 * Run from the repository: node tests/dashboard_browser.cjs
 * DASHBOARD_PYTHON selects Python; DASHBOARD_HEADED=1 shows the browser.
 * Fixtures and screenshots remain under output/playwright/ for inspection.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'output', 'playwright');
fs.mkdirSync(output, { recursive: true });
const fixture = fs.mkdtempSync(path.join(output, 'fixture-'));
const write = (name, value) => {
  const file = path.join(fixture, name);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, value);
  return file;
};
write('configs/quick.json', fs.readFileSync(path.join(root, 'configs/quick.json')));
const csv = (name, gap) => `case,family,algorithm,runs,mean_coverage,mean_optimality_gap,mean_runtime_seconds,timeouts\n${name},adversarial,greedy,1,2,${gap},0.001,0\n`;
const report = '# Results: browser fixture\n\n## Headline checks\n\n- **Observed** gap, not a general conclusion.\n- Preserve this limitation.\n\n## Data\n\n| Case | Value |\n|---|---:|\n| `a` | 2 |\n\n```text\n<script>window.injected = 1</script>\n```\n\n<img src=x onerror="window.injected=1">\n\n[bad](javascript:alert(1))\n';
const replay = { instance: { schema_version: 1, universe_size: 3, sets: [[0, 1], [2]], k: 1, encoding: 'elements' },
  run_id: 'tiny', replay: { algorithm: 'greedy', expected: { coverage: 2, selected: [0] } } };
for (const [name, gap, time] of [['a', .25, 1000], ['b', .5, 2000]]) {
  const file = write(`results/${name}/summary.csv`, csv(name, gap));
  fs.utimesSync(file, time, time);
  write(`results/${name}/results_summary.md`, report);
  write(`results/${name}/gap_by_case.svg`, '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100"><text x="10" y="50">Example</text></svg>');
  write(`results/${name}/failures/valid.json`, JSON.stringify(replay));
}
write('results/orphan/failures/valid.json', JSON.stringify(replay));
write('results/orphan/failures/bad.json', JSON.stringify({ replay: { algorithm: 'greedy' } }));
write('results/empty/log.txt', 'not an experiment');
const raw = write('results/raw-only/raw_results.csv', 'case,algorithm,coverage\nraw,greedy,2\n');
fs.utimesSync(raw, 500, 500);
const server = spawn(process.env.DASHBOARD_PYTHON || 'python', ['-u', '-c',
  "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from maxcover.dashboard import serve_dashboard; serve_dashboard(port=0, project_root=Path(sys.argv[1]))", fixture],
  { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let serverLog = '';
server.stderr.on('data', (data) => { serverLog += data; });
const urlReady = new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error('Server startup timeout: ' + serverLog)), 15000);
  server.on('error', reject);
  server.on('exit', (code) => { clearTimeout(timeout); reject(new Error('Server exited: ' + code + serverLog)); });
  server.stdout.on('data', (data) => {
    const match = String(data).match(/http:\/\/127\.0\.0\.1:\d+\//);
    if (match) { clearTimeout(timeout); resolve(match[0]); }
  });
});
let browser;
const checks = [];
const passed = (name) => { checks.push(name); console.log('PASS ' + name); };
(async () => {
  const url = await urlReady;
  browser = await chromium.launch({ headless: process.env.DASHBOARD_HEADED !== '1',
    ...(process.env.DASHBOARD_BROWSER_CHANNEL ? { channel: process.env.DASHBOARD_BROWSER_CHANNEL } : {}) });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(url);
  const loaded = async (name) => {
    await page.waitForFunction((name) => document.querySelector('#spectrum-source').textContent === name, name);
    assert.equal(await page.locator('#result-select').inputValue(), name);
  };
  const choose = async (name) => { await page.locator('#result-select').selectOption(name); await loaded(name); };
  await loaded('b');
  assert.deepEqual(await page.locator('#result-select option').evaluateAll((items) => items.map((x) => x.value)), ['b', 'a', 'raw-only']);
  passed('fresh session selects latest CSV result and excludes non-result folders');
  await choose('a'); await page.reload(); await loaded('a');
  passed('successful result selection survives page reload');

  await page.route('**/api/result?name=b', (route) => route.fulfill({ status: 400, json: { error: 'fixture unreadable' } }));
  await page.locator('#result-select').selectOption('b');
  await page.locator('#result-message.error').waitFor();
  assert.equal(await page.locator('#gallery-grid img').count(), 0);
  assert.equal(await page.locator('#summary-table tbody tr td').count(), 1);
  assert.notEqual(await page.locator('#spectrum-source').innerText(), 'a');
  await choose('a'); assert.equal(await page.locator('#result-message').isVisible(), false);
  await page.unroute('**/api/result?name=b');
  passed('invalid selection clears prior result; successful recovery clears error');

  let release;
  const delayed = new Promise((resolve) => { release = resolve; });
  await page.route('**/api/result?name=b', async (route) => { await delayed; await route.continue(); });
  await page.locator('#result-select').selectOption('b');
  await choose('a'); release(); await page.waitForTimeout(150);
  await loaded('a'); await page.unroute('**/api/result?name=b');
  passed('out-of-order result responses cannot overwrite the current choice');
  let releaseRefresh;
  const delayedRefresh = new Promise((resolve) => { releaseRefresh = resolve; });
  await page.route('**/api/results', async (route) => { await delayedRefresh; await route.continue(); });
  await page.locator('#refresh-results').click(); await choose('b'); releaseRefresh();
  await page.waitForTimeout(250); await loaded('b'); await page.unroute('**/api/results');
  passed('selection changed during refresh remains selected');

  await choose('a');
  const completedJob = { id: 'completed-refresh', status: 'completed', config: 'quick.json', output: 'a', result_name: 'a' };
  let finishRefresh, refreshStarted;
  const completionGate = new Promise((resolve) => { finishRefresh = resolve; });
  const completionSeen = new Promise((resolve) => { refreshStarted = resolve; });
  await page.route('**/api/run', (route) => route.fulfill({ json: { id: completedJob.id } }));
  await page.route('**/api/jobs/completed-refresh', (route) => route.fulfill({ json: completedJob }));
  await page.route('**/api/jobs', (route) => route.fulfill({ json: { jobs: [completedJob] } }));
  await page.route('**/api/results', async (route) => { refreshStarted(); await completionGate; await route.continue(); });
  await page.locator('#output-name').fill('a'); await page.locator('#run-button').click(); await completionSeen;
  await choose('b');
  const afterCompletion = page.waitForResponse((response) => response.url().endsWith('/api/result?name=b'));
  finishRefresh(); await (await afterCompletion).finished(); await loaded('b');
  for (const pattern of ['**/api/run', '**/api/jobs/completed-refresh', '**/api/jobs', '**/api/results']) await page.unroute(pattern);
  passed('user selection also wins over a delayed job-completion refresh');

  let finishPoll, pollStarted, polls = 0;
  const pollGate = new Promise((resolve) => { finishPoll = resolve; });
  const pollSeen = new Promise((resolve) => { pollStarted = resolve; });
  const polledJob = { ...completedJob, id: 'serial-poll' };
  await page.route('**/api/run', (route) => route.fulfill({ json: { id: polledJob.id } }));
  await page.route('**/api/jobs', (route) => route.fulfill({ json: { jobs: polls >= 3 ? [polledJob] : [] } }));
  await page.route('**/api/jobs/serial-poll', async (route) => {
    const count = ++polls;
    if (count === 2) { pollStarted(); await pollGate; }
    await route.fulfill({ json: { ...polledJob, status: count < 3 ? 'running' : 'completed' } });
  });
  await page.locator('#run-button').click(); await pollSeen;
  await page.waitForTimeout(1200); assert.equal(polls, 2);
  finishPoll(); await page.waitForFunction(() => document.querySelector('#job-line').textContent.includes('已完成'));
  await loaded('a'); await page.waitForTimeout(1200);
  assert.match(await page.locator('#job-line').innerText(), /已完成/); assert.equal(polls, 3);
  for (const pattern of ['**/api/run', '**/api/jobs/serial-poll', '**/api/jobs']) await page.unroute(pattern);
  passed('job polling stays serial and a completed job cannot regress to running');

  let posts = 0;
  page.on('request', (request) => { if (request.url().endsWith('/api/run')) posts++; });
  for (const value of ['我的第一次实验', '', ' ', '.bad', 'a'.repeat(82)]) {
    await page.locator('#output-name').fill(value); await page.locator('#run-button').click();
    assert.equal(await page.locator('#output-name').getAttribute('aria-invalid'), 'true');
    assert.equal(await page.locator('#output-error').isVisible(), true);
  }
  assert.equal(posts, 0);
  await page.locator('#output-name').fill('browser-new-run');
  assert.equal(await page.locator('#output-error').isVisible(), false);
  await page.locator('#run-button').click(); await loaded('browser-new-run');
  assert.equal(posts, 1);
  passed('invalid names never submit; corrected input completes a real small benchmark');
  await page.getByRole('button', { name: '阅读完整报告', exact: true }).click();
  await page.locator('#report-content table').first().waitFor();
  assert.ok(await page.locator('#report-content table').count() > 10);
  assert.match(await page.locator('#report-content').innerText(), /not general theoretical conclusions/);
  await page.screenshot({ path: path.join(output, 'report-real-benchmark.png') });
  await page.locator('#report-close').click();
  await page.getByRole('button', { name: 'EN', exact: true }).click(); await loaded('browser-new-run');
  assert.equal(await page.getByRole('button', { name: 'Optimal-reference coverage by case · Click to enlarge' }).count(), 1);
  await page.getByRole('button', { name: '中文', exact: true }).click(); await loaded('browser-new-run');
  assert.equal(await page.getByRole('button', { name: '各案例最优参考覆盖情况 · 点击放大' }).count(), 1);
  passed('full generated benchmark report renders its tables and original limitations');
  assert.equal(await page.locator('#replay-button').isDisabled(), true);
  assert.equal(await page.locator('#replay-algorithm').isDisabled(), true);
  await page.locator('#replay-scope').selectOption('others');
  await page.locator('#replay-select').selectOption('orphan/failures/valid.json');
  await page.locator('#replay-button').click();
  await page.locator('#replay-output .result-status').waitFor();
  assert.match(await page.locator('#replay-output').innerText(), /一致|Match/);
  await page.locator('#replay-select').selectOption('orphan/failures/bad.json');
  assert.equal(await page.locator('#replay-output .result-status').count(), 0);
  await page.locator('#replay-button').click(); await page.locator('#replay-message.error').waitFor();
  await page.locator('#replay-scope').selectOption('current');
  assert.equal(await page.locator('#replay-button').isDisabled(), true);
  passed('empty replay state, orphan-file replay, bad-file feedback and output reset');
  await choose('a');
  assert.doesNotMatch(await page.locator('#replay-output').innerText(), /此范围没有案例文件/);
  assert.deepEqual(await page.locator('#replay-select option').evaluateAll((items) => items.map((x) => x.value)), ['a/failures/valid.json']);
  await choose('b');
  assert.deepEqual(await page.locator('#replay-select option').evaluateAll((items) => items.map((x) => x.value)), ['b/failures/valid.json']);
  passed('replay cases are scoped to the displayed result');

  let releaseReplay;
  const delayedReplay = new Promise((resolve) => { releaseReplay = resolve; });
  await page.route('**/api/replay', async (route) => { await delayedReplay; await route.continue(); });
  await page.locator('#replay-button').click();
  const replayResponse = page.waitForResponse((response) => response.url().endsWith('/api/replay'));
  await choose('a'); releaseReplay(); await (await replayResponse).finished();
  await page.waitForFunction(() => !document.querySelector('#replay-button').disabled);
  assert.equal(await page.locator('#replay-output .result-status').count(), 0);
  await page.unroute('**/api/replay');
  passed('late replay response cannot appear under a different result');

  await page.route('**/api/artifact?result=a&file=results_summary.md',
    (route) => route.fulfill({ status: 404, body: 'missing report' }));
  await page.getByRole('button', { name: '阅读完整报告', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#report-content').textContent.includes('报告无法读取'));
  await page.locator('#report-close').click();
  await page.unroute('**/api/artifact?result=a&file=results_summary.md');
  passed('missing report produces a recoverable reading error');
  let releaseReport;
  const delayedReport = new Promise((resolve) => { releaseReport = resolve; });
  await page.route('**/api/artifact?result=a&file=results_summary.md', async (route) => {
    await delayedReport; await route.fulfill({ body: '# STALE REPORT', contentType: 'text/markdown' });
  });
  await page.getByRole('button', { name: '阅读完整报告', exact: true }).click();
  const reportResponse = page.waitForResponse((response) => response.url().includes('result=a&file=results_summary.md'));
  await page.locator('#report-close').click(); await choose('b');
  await page.getByRole('button', { name: '阅读完整报告', exact: true }).click();
  await page.locator('#report-content table').waitFor();
  releaseReport(); await (await reportResponse).finished();
  assert.doesNotMatch(await page.locator('#report-content').innerText(), /STALE REPORT/);
  assert.match(await page.locator('#report-title').innerText(), /^b/);
  await page.locator('#report-close').click();
  await page.unroute('**/api/artifact?result=a&file=results_summary.md');
  passed('late report response cannot replace a newly opened result report');

  await page.getByRole('button', { name: '阅读完整报告', exact: true }).click();
  await page.locator('#report-content table').waitFor();
  assert.equal(await page.locator('#report-content table tbody tr').count(), 1);
  assert.match(await page.locator('#report-content').innerText(), /Preserve this limitation/);
  assert.equal(await page.locator('#report-content script, #report-content img, #report-content a').count(), 0);
  assert.equal(await page.evaluate(() => window.injected), undefined);
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#report-source').click(); const download = await downloadPromise;
  assert.equal(fs.readFileSync(await download.path(), 'utf8'), report);
  await page.screenshot({ path: path.join(output, 'report-readable.png') });
  await page.locator('#report-close').click();
  assert.equal(await page.locator('#report-dialog').isVisible(), false);
  passed('readable report preserves content; inert HTML/unsafe links; original download');

  const chart = page.getByRole('button', { name: /按案例查看覆盖差距 ·/ });
  await chart.click(); await page.keyboard.press('Escape');
  assert.equal(await page.locator('.lightbox').isVisible(), false);
  assert.equal(await chart.evaluate((node) => node === document.activeElement), true);
  await page.locator('.result-nav a[href="#replay-section"]').click();
  assert.equal(await page.locator('#replay-section').evaluate((node) => node === document.activeElement), true);
  await page.getByRole('button', { name: 'EN', exact: true }).click(); await loaded('b');
  assert.equal(await page.locator('html').getAttribute('lang'), 'en');
  await page.getByRole('button', { name: '中文', exact: true }).click(); await loaded('b');
  passed('chart close restores focus; direct replay navigation; language round trip');
  for (const [width, height] of [[1366, 900], [932, 919], [390, 844]]) {
    await page.setViewportSize({ width, height });
    await page.mouse.move(20, 200); await page.mouse.wheel(0, -20000);
    await page.waitForFunction(() => scrollY === 0);
    await page.screenshot({ path: path.join(output, `home-${width}.png`) });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('#view-results').click();
    assert.ok(await page.locator('#result-select').evaluate((node) => node.getBoundingClientRect().right <= innerWidth));
    await page.screenshot({ path: path.join(output, `results-${width}.png`) });
  }
  passed('three viewport widths fit; result picker is reachable from the first screen');
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.evaluate(() => localStorage.setItem('maxcover-result', 'missing'));
  await page.reload(); await loaded('browser-new-run'); await page.locator('#result-notice').waitFor();
  passed('missing saved choice falls back with an explanation');
  await page.evaluate(() => localStorage.setItem('maxcover-result', 'b'));
  await page.route('**/api/result?name=b', (route) => route.fulfill({ status: 400, json: { error: 'bad CSV' } }));
  await page.reload(); await loaded('browser-new-run'); await page.locator('#result-notice').waitFor();
  await page.unroute('**/api/result?name=b');
  passed('unreadable saved choice falls back with an explanation');
  await choose('raw-only');
  assert.match(await page.locator('#summary-table tbody').innerText(), /没有汇总/);
  passed('raw-only result stays accessible without a fabricated summary');
  const storageContext = await browser.newContext();
  await storageContext.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new Error('Storage disabled'); } });
  });
  const storagePage = await storageContext.newPage(); await storagePage.goto(url);
  await storagePage.waitForFunction(() => document.querySelector('#spectrum-source').textContent === 'browser-new-run');
  await storageContext.close(); passed('disabled local storage does not prevent loading');
  await page.route('**/api/result?name=*', (route) => route.fulfill({ status: 400, json: { error: 'bad CSV' } }));
  await page.reload();
  await page.waitForFunction(() => document.querySelector('#result-message').textContent.includes('无法读取 a'));
  assert.equal(await page.locator('#gallery-grid img').count(), 0);
  assert.equal(await page.locator('#replay-button').isDisabled(), true);
  await page.unroute('**/api/result?name=*');
  passed('all result loads failing terminate without stale data or enabled current replay');
  await page.route('**/api/results', (route) => route.fulfill({ json: { results: [] } }));
  await page.route('**/api/replay-files', (route) => route.fulfill({ json: { replays: [] } }));
  await page.reload(); await page.waitForFunction(() => document.querySelector('#api-status').textContent.includes('已连接'));
  assert.equal(await page.locator('#replay-button').isDisabled(), true);
  assert.equal(await page.locator('#result-select').isDisabled(), true);
  passed('empty index has an explained, non-actionable replay state');
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output, 'browser-checks.json'), JSON.stringify({ checks, fixture, pageErrors: errors }, null, 2));
  console.log(`Completed ${checks.length} browser scenarios. Fixtures: ${fixture}`);
})().catch((error) => { console.error(error); console.error(serverLog); process.exitCode = 1; })
  .finally(async () => { if (browser) await browser.close(); server.kill(); });
