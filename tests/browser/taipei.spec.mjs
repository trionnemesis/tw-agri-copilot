import { expect, test } from '@playwright/test';

async function taipeiPayload(request) {
  const response = await request.get('/data/taipei/current.json');
  expect(response.ok()).toBe(true);
  return response.json();
}

async function expectReadableTaipeiPage(page, payload) {
  const status = page.locator('#taipei-status');
  await expect(status).toHaveAttribute('data-taipei-as-of', payload.as_of_date);
  await expect(status).toHaveAttribute('data-taipei-requested', payload.requested_date);
  await expect(status).toHaveAttribute('data-taipei-scope-status', payload.scope_status);
  await expect(page.locator('[data-taipei-item]')).toHaveCount(payload.items.length);
  await expect(page.getByText('批發市場平均行情，非實際零售通路售價。')).toBeVisible();
  await expect(page.getByText(/不是產地/).first()).toBeVisible();
  for (const item of payload.items) {
    await expect(page.locator(`[data-taipei-item="${item.canonical_id}"]`)).toHaveAttribute(
      'data-recommendation-status',
      item.recommendation_gate.status,
    );
  }
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

test('homepage links to the Taipei scope page', async ({ page }) => {
  await page.goto('/index.html');
  await page.locator('#taipei').getByRole('link', { name: '查看臺北市描述統計 →' }).click();
  await expect(page).toHaveURL(/\/taipei\/index\.html$/);
  await expect(page.getByRole('heading', { level: 1, name: '臺北市蔬果批發行情' })).toBeVisible();
});

test('Taipei page matches its public JSON without horizontal page scroll', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const payload = await taipeiPayload(request);
  await page.goto('/taipei/index.html');
  await expectReadableTaipeiPage(page, payload);
  for (const href of ['../data/taipei/current.json', '../data/taipei/items.csv', '../data/taipei/observations.csv']) {
    const response = await request.get(new URL(href, page.url()).toString());
    expect(response.ok()).toBe(true);
  }
  expect(errors).toEqual([]);
});

test.describe('without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  test('Taipei statistics stay readable', async ({ page, request }) => {
    const payload = await taipeiPayload(request);
    await page.goto('/taipei/index.html');
    await expectReadableTaipeiPage(page, payload);
    await page.getByText(/展開 \d+ 筆臺北成交列/).click();
    await expect(page.locator('#taipei-observations tbody tr')).toHaveCount(Math.max(payload.observations.length, 1));
  });
});
