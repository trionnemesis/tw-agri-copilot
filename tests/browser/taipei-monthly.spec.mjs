import { expect, test } from '@playwright/test';

async function monthlyPayload(request) {
  const response = await request.get('/data/taipei/monthly.json');
  expect(response.ok()).toBe(true);
  return response.json();
}

async function expectReadableMonthlyPage(page, payload) {
  const status = page.locator('#taipei-monthly-status');
  await expect(status).toHaveAttribute('data-monthly-analysis-status', payload.analysis_status);
  await expect(status).toHaveAttribute('data-monthly-requested', payload.requested_date);
  await expect(page.locator('[data-monthly-retail-item]')).toHaveCount(payload.retail_items.length);
  await expect(page.locator('[data-monthly-supply-category]')).toHaveCount(payload.supply_categories.length);
  await expect(page.getByText(/不是今日報價/).first()).toBeVisible();
  for (const item of payload.retail_items) {
    await expect(page.locator(`[data-monthly-retail-item="${item.item_raw}"]`)).toHaveAttribute(
      'data-advice-status',
      item.advice.status,
    );
  }
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

test('Taipei page links to the monthly page', async ({ page }) => {
  await page.goto('/taipei/index.html');
  await page.getByRole('link', { name: '另看臺北市零售月均價與食物供銷月統計 →' }).click();
  await expect(page).toHaveURL(/\/taipei\/monthly\.html$/);
  await expect(page.getByRole('heading', { level: 1, name: '臺北市零售月均價與食物供銷' })).toBeVisible();
});

test('monthly page matches its public JSON without horizontal page scroll', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const payload = await monthlyPayload(request);
  await page.goto('/taipei/monthly.html');
  await expectReadableMonthlyPage(page, payload);
  for (const href of ['../data/taipei/monthly.json', '../data/taipei/monthly-retail.csv', '../data/taipei/monthly-supply.csv']) {
    const response = await request.get(new URL(href, page.url()).toString());
    expect(response.ok()).toBe(true);
  }
  expect(errors).toEqual([]);
});

test.describe('without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  test('monthly statistics stay readable', async ({ page, request }) => {
    const payload = await monthlyPayload(request);
    await page.goto('/taipei/monthly.html');
    await expectReadableMonthlyPage(page, payload);
    await page.getByText('展開每個月份採用的 revision').click();
    const periods = payload.sources.reduce((count, source) => count + source.periods.length, 0);
    await expect(page.locator('#taipei-monthly-lineage tbody tr')).toHaveCount(Math.max(periods, 1));
  });
});
