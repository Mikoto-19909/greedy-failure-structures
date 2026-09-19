/* End-to-end research workbench checks using the repository's Playwright setup.
 * node tests/workbench_browser.cjs; DASHBOARD_PYTHON and DASHBOARD_BROWSER_CHANNEL
 * work as in dashboard_browser.cjs. All writes stay in an isolated fixture.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'output', 'playwright');
fs.mkdirSync(output, { recursive: true });
const fixture = fs.mkdtempSync(path.join(output, 'workbench-'));
const write = (name, content) => {
  const file = path.join(fixture, name); fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content); return file;
};
write('experiments/r1/paths.jsonl', fs.readFileSync(path.join(root, 'experiments/r1_prefix_exchange_v1/paths.jsonl')));
write('results/pilot/raw_results.csv', fs.readFileSync(path.join(root, 'experiments/core_rq/overlap_pilot_v1/raw_results.csv')));
write('results/broken/paths.jsonl', '{bad');
const python = process.env.DASHBOARD_PYTHON || 'python';
const server = spawn(python, ['-u', '-c',
  "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from maxcover.dashboard import serve_dashboard; serve_dashboard(port=0, project_root=Path(sys.argv[1]))", fixture],
  { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let log = '';
server.stderr.on('data', (chunk) => { log += chunk; });
const ready = new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Server startup timeout: ' + log)), 20000);
  server.on('error', reject);
  server.on('exit', (code) => { clearTimeout(timer); reject(new Error('Server exited: ' + code + log)); });
  server.stdout.on('data', (chunk) => {
    const match = String(chunk).match(/http:\/\/127\.0\.0\.1:\d+\//);
    if (match) { clearTimeout(timer); resolve(match[0]); }
  });
});
let browser;
const checks = [];
const passed = (name) => { checks.push(name); console.log('PASS ' + name); };
(async () => {
  const url = await ready;
  browser = await chromium.launch({ headless: process.env.DASHBOARD_HEADED !== '1',
    ...(process.env.DASHBOARD_BROWSER_CHANNEL ? { channel: process.env.DASHBOARD_BROWSER_CHANNEL } : {}) });
  const context = await browser.newContext({ viewport: { width: 1366, height: 960 } });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(url + 'workbench');
  await page.getByLabel('选择 experiments/r1', { exact: true }).waitFor();
  assert.equal(await page.getByLabel('选择 results/broken', { exact: true }).isDisabled(), true);
  assert.match(await page.locator('#library-count').innerText(), /3 \/ 3/);
  await page.getByLabel('选择 experiments/r1', { exact: true }).check();
  await page.locator('#library-search').fill('pilot');
  await page.getByLabel('选择 results/pilot', { exact: true }).check();
  assert.match(await page.locator('#compare-selected').innerText(), /（2）/);
  await page.locator('#library-search').fill('');
  await page.screenshot({ path: path.join(output, 'workbench-library.png'), fullPage: true });
  passed('library discovers saved data, isolates a damaged source and retains filtered selections');
  await page.reload();
  await page.waitForFunction(() => document.querySelector('#compare-selected').textContent.includes('（2）'));
  assert.equal(await page.getByLabel('选择 experiments/r1', { exact: true }).isChecked(), true);
  passed('source selection survives refresh');
  await page.locator('#compare-selected').click();
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('汇总 180 / 输入 186'));
  assert.equal(await page.locator('#summary-body tr').count(), 6);
  await page.locator('#compare-algorithm').selectOption('greedy');
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('汇总 120 / 输入 186'));
  await page.locator('#compare-outcome').selectOption('loss');
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('明细 44 条'));
  assert.equal(await page.locator('#summary-body tr').count(), 4);
  assert.match(await page.locator('#records-body tr').first().innerText(), /\d{17,20}/);
  await page.screenshot({ path: path.join(output, 'workbench-compare.png'), fullPage: true });
  passed('complete-data comparison keeps study populations separate and loss filtering preserves denominators');
  await page.locator('#records-body button').first().click();
  await page.locator('#trace-view').waitFor();
  assert.match(await page.locator('#trace-message').innerText(), /experiments\/r1/);
  assert.equal(await page.locator('#step-label').innerText(), '0 / 4');
  assert.equal(await page.locator('#instance-matrix circle').count() > 0, true);
  await page.locator('#step-next').click();
  assert.equal(await page.locator('#step-label').innerText(), '1 / 4');
  assert.match(await page.locator('#step-summary').innerText(), /本步新增/);
  await page.locator('#step-prev').click();
  await page.locator('#step-play').click();
  await page.waitForFunction(() => document.querySelector('#step-label').textContent === '4 / 4');
  assert.equal(await page.locator('#step-play').innerText(), '播放');
  await page.locator('#step-reset').click();
  await page.locator('#step-range').fill('2');
  assert.equal(await page.locator('#step-label').innerText(), '2 / 4');
  await page.screenshot({ path: path.join(output, 'workbench-instance.png'), fullPage: true });
  passed('R1 matrix, gains, witnesses, next/previous/reset/slider and autoplay show the saved trajectory');
  const downloadReady = page.waitForEvent('download');
  await page.locator('#export-case').click();
  const download = await downloadReady;
  const exportedPath = path.join(fixture, 'exported-case.json'); await download.saveAs(exportedPath);
  const exported = JSON.parse(fs.readFileSync(exportedPath, 'utf8'));
  assert.equal(exported.replay.algorithm, 'greedy');
  const replay = spawnSync(python, ['-c',
    "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from maxcover.benchmark import replay_instance_file; solution, matched = replay_instance_file(Path(sys.argv[1])); assert matched; print(solution.coverage)", exportedPath],
    { cwd: root, windowsHide: true, encoding: 'utf8' });
  assert.equal(replay.status, 0, replay.stderr);
  passed('downloaded case replays with the existing engine and matches recorded coverage and selection');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(output, 'workbench-mobile-instance.png'), fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true);
  await page.locator('#back-compare').click();
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('明细 44 条'));
  assert.equal(await page.locator('#compare-outcome').inputValue(), 'loss');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true);
  passed('390px layout contains its tables and matrix; returning preserves comparison filters');
  await page.setViewportSize({ width: 1366, height: 960 });
  await page.locator('#compare-outcome').selectOption('all');
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('明细 120 条'));
  await page.locator('#page-next').click();
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('第 2 / 3 页'));
  await page.locator('#page-prev').click();
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('第 1 / 3 页'));
  passed('detail pagination traverses the complete filtered set');
  await page.locator('#compare-population').selectOption('fixture');
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('明细 6 条'));
  await page.locator('#compare-case').selectOption('zero_objective');
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('明细 1 条'));
  await page.locator('#records-body button').click();
  await page.locator('#trace-view').waitFor();
  await page.locator('#step-next').click();
  assert.match(await page.locator('#step-summary').innerText(), /已覆盖 0/);
  await page.locator('#back-compare').click();
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('明细 1 条'));
  await page.locator('#compare-population').selectOption('research');
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('明细 0 条'));
  assert.equal(await page.locator('#records-body button').count(), 0);
  passed('fixture-only scope, zero-objective trace and empty filter remain explicit and usable');
  await page.route('**/api/workbench/compare?**', (route) => route.fulfill({ status: 400, json: { error: 'unreadable source' } }));
  await page.locator('#compare-case').selectOption('');
  await page.locator('#wb-message.error').waitFor();
  assert.equal(await page.locator('#records-body button').count(), 0);
  await page.unroute('**/api/workbench/compare?**');
  await page.locator('#compare-outcome').selectOption('loss');
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.includes('明细 44 条'));
  assert.equal(await page.locator('#wb-message').innerText(), '');
  passed('failed comparison clears old rows and a successful retry clears the error');
  let release, seen;
  const held = new Promise((resolve) => { release = resolve; });
  const started = new Promise((resolve) => { seen = resolve; });
  await page.route('**/api/workbench/detail?**', async (route) => { seen(); await held; await route.continue(); });
  await page.locator('#records-body button').first().click(); await started;
  await page.locator('#nav-library').click(); release();
  await page.waitForTimeout(300);
  assert.equal(await page.locator('#view-library').isVisible(), true);
  assert.equal(await page.locator('#export-case').isVisible(), false);
  await page.unroute('**/api/workbench/detail?**');
  passed('a late detail response cannot replace a newer navigation or expose the previous export');
  const noStorage = await context.newPage();
  await noStorage.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new Error('storage disabled'); };
    Storage.prototype.setItem = () => { throw new Error('storage disabled'); };
  });
  await noStorage.goto(url + 'workbench');
  await noStorage.getByLabel('选择 experiments/r1', { exact: true }).check();
  assert.equal(await noStorage.locator('#compare-selected').isEnabled(), true);
  await noStorage.close();
  assert.deepEqual(errors, []);
  passed('disabled browser storage remains usable; no browser runtime errors');
  fs.writeFileSync(path.join(output, 'workbench-browser-checks.json'), JSON.stringify({ checks, fixture, errors }, null, 2));
  console.log(`Completed ${checks.length} browser checks.`);
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close(); server.kill();
});
