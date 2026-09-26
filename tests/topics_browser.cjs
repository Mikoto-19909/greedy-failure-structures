/* Study navigation checks. Reads existing research; never submits an experiment.
 * Run with the same Playwright/Edge setup as dashboard_browser.cjs.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'output', 'playwright', 'topics');
fs.mkdirSync(output, { recursive: true });
const server = spawn(process.env.DASHBOARD_PYTHON || 'python', ['-u', '-c',
  "import sys; sys.path.insert(0, 'src'); from maxcover.dashboard import serve_dashboard; serve_dashboard(port=0)"],
  { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let serverLog = '', browser;
server.stderr.on('data', chunk => { serverLog += chunk; });
const ready = new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Server startup timeout: ' + serverLog)), 15000);
  server.on('error', reject);
  server.on('exit', code => { clearTimeout(timer); reject(new Error('Server exit: ' + code + serverLog)); });
  server.stdout.on('data', chunk => {
    const match = String(chunk).match(/http:\/\/127\.0\.0\.1:\d+\//);
    if (match) { clearTimeout(timer); resolve(match[0]); }
  });
});
const checks = [];
const passed = name => { checks.push(name); console.log('PASS ' + name); };
(async () => {
  const url = await ready;
  browser = await chromium.launch({ headless: process.env.DASHBOARD_HEADED !== '1',
    ...(process.env.DASHBOARD_BROWSER_CHANNEL ? { channel: process.env.DASHBOARD_BROWSER_CHANNEL } : {}) });
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [], writes = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (request.method() !== 'GET') writes.push(request.method() + ' ' + request.url()); });
  const cards = page.locator('.topic-card');
  const waitCards = count => page.waitForFunction(count => document.querySelectorAll('.topic-card').length === count, count);
  await page.goto(url); await waitCards(2);
  const topicsResponse = await page.request.get(url + 'topics.json');
  assert.match(topicsResponse.headers()['content-type'], /application\/json/);
  const topics = await topicsResponse.json();
  assert.deepEqual(await cards.locator('a').evaluateAll(items => items.map(item => item.getAttribute('href'))),
    ['/maximum-coverage', '/online-matching']);
  await page.screenshot({ path: path.join(output, 'home-desktop.png'), fullPage: true });
  passed('home exposes both working study entries from the topic list');

  await page.getByRole('button', { name: 'EN', exact: true }).click();
  assert.equal(await page.title(), 'Research Workspace');
  await cards.first().getByRole('link').click();
  await page.locator('[data-topic-nav] select').waitFor();
  assert.equal(await page.locator('[data-topic-nav] select').inputValue(), 'maximum-coverage');
  assert.equal(await page.locator('html').getAttribute('lang'), 'en');
  await page.locator('#language-zh').click();
  assert.equal(await page.locator('[data-topic-nav] option:checked').innerText(), '最大覆盖研究');
  passed('entry navigation preserves language and follows the existing language control');

  await page.locator('[data-topic-nav] select').selectOption('online-matching');
  await page.waitForURL('**/online-matching');
  await page.locator('[data-topic-nav] select').waitFor();
  assert.equal(await page.locator('[data-topic-nav] select').inputValue(), 'online-matching');
  await page.locator('#matching-content:not([hidden])').waitFor();
  await page.locator('#matching-report-body h2').first().waitFor();
  const detail = await (await page.request.get(url + 'api/online-matching/detail?run=' +
    encodeURIComponent(await page.locator('#matching-run').inputValue()))).json();
  assert.equal(detail.verification.status, 'current_artifacts_not_revalidated');
  assert.equal(detail.verification.recorded_status, 'automatic_verification_passed_user_review_pending');
  assert.match(await page.locator('#matching-verification').innerText(), /当前展示文件未重新核验/);
  passed('saved verification is displayed as history without certifying the current artifacts');
  await page.getByRole('link', { name: '← 研究首页', exact: true }).click();
  await waitCards(2);
  passed('shared switcher reaches saved matching results and returns home');

  const alias = await page.request.get(url + 'index.html');
  const canonical = await page.request.get(url + 'maximum-coverage');
  assert.equal(alias.status(), 200); assert.equal(await alias.text(), await canonical.text());
  for (const entry of ['workbench', 'research', 'experiments']) {
    await page.goto(url + entry);
    await page.locator('[data-topic-nav] select').waitFor();
    assert.equal(await page.locator('[data-topic-nav] select').inputValue(), 'maximum-coverage');
    assert.equal(await page.locator('[data-topic-nav] option').count(), 2);
  }
  passed('legacy alias and Maximum Coverage subpages keep their own entry and shared navigation');

  const third = { ...topics[0], id: 'sample-study', href: '/sample-study', mark: 'S',
    title: { zh: '第三专题示例', en: 'Third study example' } };
  await page.route('**/topics.json', route => route.fulfill({ json: [...topics, third] }));
  await page.route('**/sample-study', route => route.fulfill({ contentType: 'text/html', body:
    '<!doctype html><html lang="zh-CN"><head><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/topics.css"></head><body><nav data-topic-nav data-topic-current="sample-study"></nav><script src="/topics.js"></script></body></html>' }));
  await page.goto(url); await waitCards(3);
  await cards.last().getByRole('link').click();
  await page.waitForURL('**/sample-study');
  await page.locator('[data-topic-nav] select').waitFor();
  assert.equal(await page.locator('[data-topic-nav] option').count(), 3);
  assert.equal(await page.locator('[data-topic-nav] select').inputValue(), 'sample-study');
  passed('a third configured topic and page need no card or switcher rendering changes');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url); await waitCards(3);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await cards.last().getByRole('link').click();
  await page.locator('[data-topic-nav] select').waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  passed('three cards and the shared switcher fit a 390-pixel viewport');

  await page.unroute('**/topics.json');
  await page.route('**/topics.json', route => route.fulfill({ status: 503, body: 'unavailable' }));
  await page.goto(url); await page.locator('[data-topic-message].error').waitFor();
  assert.equal(await cards.count(), 0);
  await page.goto(url + 'maximum-coverage');
  await page.getByRole('link', { name: '← 研究首页', exact: true }).waitFor();
  assert.equal(await page.locator('#experiment-entry').count(), 1);
  passed('unavailable topic data gives a recoverable home error and preserves the existing experiment page');

  await page.unroute('**/topics.json');
  await page.route('**/topics.json', route => route.fulfill({ json: [] }));
  await page.goto(url);
  await page.getByText('暂无研究入口。', { exact: true }).waitFor();
  await page.unroute('**/topics.json');
  await page.goto(url); await waitCards(2);
  await page.screenshot({ path: path.join(output, 'home-mobile.png'), fullPage: true });
  passed('an empty topic list has an explicit state and a reload recovers the real entries');

  assert.deepEqual(errors, []); assert.deepEqual(writes, []);
  passed('all navigation remains read-only with no page errors or experiment submissions');
  fs.writeFileSync(path.join(output, 'checks.json'), JSON.stringify({ checks, pageErrors: errors, writes }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  server.kill();
});
