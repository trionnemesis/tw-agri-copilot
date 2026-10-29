import { expect, test } from '@playwright/test';

test('selection, URL history and shared scales stay synchronized', async ({page, request}) => {
  const data = await (await request.get('/data/taipei/map.json')).json();
  await page.goto('/taipei/map.html?item=cabbage&crop=LA2&market=all&window=30d&other=keep#map');
  if (data.analysis_status === 'failed') { await expect(page.getByText(/地圖分析無法使用/)).toBeVisible(); return; }
  await expect(page.locator('#item')).toBeEnabled();
  await expect(page.locator('#map-status')).toContainText(data.as_of_date);
  await expect(page.locator('#map-status')).toContainText(data.requested_date);
  const legend = await page.locator('#legend').textContent();
  await page.locator('#market').selectOption('104');
  await expect(page).toHaveURL(/market=104/);
  await expect(page.locator('#legend')).toHaveText(legend);
  await expect(page.locator('[data-market="109"]')).toHaveClass(/unfocused/);
  await page.locator('#window').selectOption('7d');
  await page.goBack();
  await expect(page.locator('#window')).toHaveValue('30d');
  await expect(page.locator('#market')).toHaveValue('104');
  expect(page.url()).toContain('other=keep'); expect(page.url()).toContain('#map');
  await page.goto('/taipei/map.html?item=cabbage&crop=invalid');
  await expect(page.locator('#control-status')).toContainText('無效');
  await expect(page.locator('#crop')).toHaveValue('LA2');
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('payload failure leaves the default static view intact', async ({page}) => {
  await page.route('**/data/taipei/map-ui.json', route=>route.fulfill({status:404,body:'missing'}));
  await page.goto('/taipei/map.html');
  if (await page.getByText(/地圖分析無法使用/).count()) return;
  await expect(page.locator('#control-status')).toContainText('載入失敗');
  await expect(page.locator('#item')).toBeDisabled();
  await expect(page.locator('#dynamic .chart')).toHaveCount(2);
  await expect(page.locator('#market-109')).toBeVisible();
});

test.describe('without JavaScript', () => {
  test.use({javaScriptEnabled:false});
  test('default map, cards, charts and comparison table remain readable', async ({page})=>{
    await page.goto('/taipei/map.html');
    if (await page.getByText(/地圖分析無法使用/).count()) return;
    await expect(page.locator('#item')).toBeDisabled();
    await expect(page.locator('#map svg')).toBeVisible();
    await expect(page.locator('#dynamic .chart')).toHaveCount(2);
    await expect(page.locator('#market-104')).toBeVisible();
    await expect(page.getByRole('heading',{name:'所有原始代碼截至日比較'})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  });
});

test('invalid hydration and a failed 90-day request preserve complete state', async ({page}) => {
  await page.route('**/data/taipei/map-ui.json', route=>route.fulfill({status:200,contentType:'application/json',body:'{"items":[],"series":[]}'}));
  await page.goto('/taipei/map.html');
  if (await page.getByText(/地圖分析無法使用/).count()) return;
  await expect(page.locator('#control-status')).toContainText('載入失敗');
  await expect(page.locator('#item')).toBeDisabled();
  await page.unroute('**/data/taipei/map-ui.json');
  await page.goto('/taipei/map.html');
  await expect(page.locator('#item')).toBeEnabled();
  const before = await page.locator('#dynamic').innerHTML();
  await page.route('**/data/taipei/map.json', route=>route.fulfill({status:404,body:'missing'}));
  await page.locator('#window').selectOption('90d');
  await expect(page.locator('#control-status')).toContainText('載入失敗');
  await expect(page.locator('#window')).toHaveValue('30d');
  expect(await page.locator('#dynamic').innerHTML()).toBe(before);
});

test('a late 90-day response cannot overwrite a newer selection', async ({page}) => {
  await page.goto('/taipei/map.html');
  if (await page.getByText(/地圖分析無法使用/).count()) return;
  await expect(page.locator('#item')).toBeEnabled();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/data/taipei/map.json', async route => { await gate; await route.continue(); });
  await page.locator('#window').selectOption('90d');
  await page.locator('#window').selectOption('7d');
  await expect(page.locator('#window')).toHaveValue('7d');
  release();
  await expect(page.locator('#control-status')).toContainText('7d');
  await expect(page.locator('#window')).toHaveValue('7d');
});

test('a superficially shaped payload missing series is rejected before hydration', async ({page}) => {
  await page.route('**/data/taipei/map-ui.json', async route => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.series = [];
    await route.fulfill({response, json:payload});
  });
  await page.goto('/taipei/map.html');
  if (await page.getByText(/地圖分析無法使用/).count()) return;
  await expect(page.locator('#control-status')).toContainText('載入失敗');
  await expect(page.locator('#item')).toBeDisabled();
  await expect(page.locator('#dynamic .chart')).toHaveCount(2);
});

test('90-day values and map marker scale match the published data without external requests', async ({page, request}) => {
  const payload=await (await request.get('/data/taipei/map.json')).json();
  const external=[];
  page.on('request', req=>{if(new URL(req.url()).origin !== 'http://127.0.0.1:4173') external.push(req.url());});
  await page.goto('/taipei/map.html');
  if (payload.analysis_status === 'failed') return;
  await expect(page.locator('#item')).toBeEnabled();
  await page.locator('#window').selectOption('90d');
  await expect(page.locator('#window')).toHaveValue('90d');
  const stat=payload.statistics.find(r=>r.market_code==='104' && r.product_code_raw==='LA2').windows['90d'];
  await expect(page.locator('#market-104')).toContainText(`有效 ${stat.coverage_days}／最低 ${stat.minimum_days} 日`);
  const observations=payload.series.filter(r=>r.product_code_raw==='LA2').flatMap(r=>r.days).filter(d=>d.observation_status==='observed');
  for (const marker of await page.locator('.map-marker').all()) {
    const code=await marker.getAttribute('data-code');
    const day=payload.series.find(r=>r.market_code===code && r.product_code_raw==='LA2').days.at(-1);
    const circle=marker.locator('.data-circle');
    if(day.observation_status==='observed') {
      const ref=Math.max(...observations.map(d=>d.volume_kg));
      expect(Number(await circle.getAttribute('r'))).toBeCloseTo(25*Math.sqrt(day.volume_kg/ref),3);
      expect(Number(await circle.getAttribute('data-price'))).toBe(day.price_twd_per_kg);
    } else await expect(circle).toHaveAttribute('data-available','false');
  }
  expect(external).toEqual([]);
});

test('200% zoom keeps the page within its viewport and district names visible', async ({page}) => {
  await page.setViewportSize({width:780,height:844});
  await page.goto('/taipei/map.html');
  if (await page.getByText(/地圖分析無法使用/).count()) return;
  await page.evaluate(()=>{document.body.style.zoom='200%';});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await expect(page.locator('.district-label')).toHaveCount(12);
  await expect(page.locator('.district-label').first()).toBeVisible();
});

test.describe('map links without JavaScript',()=>{
  test.use({javaScriptEnabled:false});
  test('verified market marker is a keyboard-operable anchor',async({page})=>{
    await page.goto('/taipei/map.html');
    if (await page.getByText(/地圖分析無法使用/).count()) return;
    const marker=page.locator('.map-marker').first();
    if (!await marker.count()) return;
    const code=await marker.getAttribute('data-code');
    await expect(marker).toHaveAttribute('href',`#market-${code}`);
    await marker.focus(); await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(`#market-${code}$`));
    await expect(page.locator(`#market-${code}`)).toBeVisible();
  });
});
