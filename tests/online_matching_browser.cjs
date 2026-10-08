/* Focused report-image regressions. Run: node tests/online_matching_browser.cjs
 * Requires Playwright; DASHBOARD_PYTHON selects the project Python environment.
 * Fixtures and screenshots stay in the ignored output/playwright directory.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'output', 'playwright');
fs.mkdirSync(output, { recursive: true });
const fixture = fs.mkdtempSync(path.join(output, 'matching-report-'));
const study = 'independent_research/online_matching_recourse';
const archivedRun = '20260924T175731049376Z-eval';
for (const relative of ['inputs.json', '报告/研究报告.md', 'extension_20260925/报告/六分支研究结果.md',
    'extension_20260925/报告/图/01_budget_counterexample.png', 'extension_20260925/报告/图/02_ablation.png',
    `output/${archivedRun}/figures/01_budget_benefit.png`,
    ...['summary.json', 'metrics.csv', 'traces.json', 'verification.json', 'inputs.json'].map((name) => `output/${archivedRun}/${name}`)]) {
  const file = path.join(fixture, study, relative);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.copyFileSync(path.join(root, study, relative), file);
}
const server = spawn(process.env.DASHBOARD_PYTHON || 'python', ['-u', '-c',
  "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from maxcover.dashboard import serve_dashboard; serve_dashboard(port=0, project_root=Path(sys.argv[1]))", fixture],
  { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let serverLog = '', browser;
server.stderr.on('data', (data) => { serverLog += data; });
const urlReady = new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Server startup timeout: ' + serverLog)), 15000);
  server.once('error', reject);
  server.once('exit', (code) => { clearTimeout(timer); reject(new Error('Server exited: ' + code + serverLog)); });
  server.stdout.on('data', (data) => {
    const match = String(data).match(/http:\/\/127\.0\.0\.1:\d+\//);
    if (match) { clearTimeout(timer); resolve(match[0]); }
  });
});
(async () => {
  const url = await urlReady;
  browser = await chromium.launch({ headless: true,
    ...(process.env.DASHBOARD_BROWSER_CHANNEL ? { channel: process.env.DASHBOARD_BROWSER_CHANNEL } : {}) });
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(url + 'online-matching');
  const reportImages = page.locator('#matching-report-body img');
  async function loadedImages(count) {
    await page.waitForFunction((count) => document.querySelectorAll('#matching-report-body img').length === count, count);
    for (let i = 0; i < count; i++) {
      await reportImages.nth(i).scrollIntoViewIfNeeded();
      await page.waitForFunction((index) => {
        const image = document.querySelectorAll('#matching-report-body img')[index];
        return image?.complete && image.naturalWidth > 0;
      }, i);
      assert.match(await reportImages.nth(i).getAttribute('src'), /\/api\/online-matching\/report-asset\?/);
    }
  }
  await loadedImages(2);
  assert.deepEqual(await reportImages.evaluateAll((items) => items.map((image) => image.alt)),
    ['预算增加时贪心轨迹可能变差', '链长和价格的拆分结果']);
  await page.screenshot({ path: path.join(output, 'matching-report-desktop.png') });
  console.log('PASS six-branch report renders both bundled PNG figures');
  await page.locator('#matching-report').selectOption('initial'); await loadedImages(1);
  assert.equal(await reportImages.first().getAttribute('alt'), '开发与固定比较的预算收益');
  console.log('PASS initial report resolves its parent-relative archived figure');
  const unsafe = await page.evaluate(() => {
    const text = '![unlisted](private.png) ![script](script.png) ![remote](remote.png) ![data](data.png)';
    const rendered = window.MaxcoverReport.render(text, {
      'script.png': 'javascript:alert(1)', 'remote.png': 'https://example.com/private.png',
      'data.png': 'data:image/svg+xml,<svg onload="window.injected=1"/>'
    });
    return { images: rendered.querySelectorAll('img').length, text: rendered.textContent };
  });
  assert.equal(unsafe.images, 0); assert.match(unsafe.text, /!\[unlisted\]\(private.png\)/);
  assert.equal(await page.evaluate(() => window.injected), undefined);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#matching-report').selectOption('results'); await loadedImages(2);
  assert.ok(await reportImages.evaluateAll((items) => items.every((image) => image.getBoundingClientRect().right <= innerWidth)));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: path.join(output, 'matching-report-mobile.png') });
  assert.deepEqual(errors, []);
  console.log('PASS unsafe image targets stay text; report figures fit a 390px viewport');
})().catch((error) => { console.error(error); console.error(serverLog); process.exitCode = 1; })
  .finally(async () => { if (browser) await browser.close(); server.kill(); });
