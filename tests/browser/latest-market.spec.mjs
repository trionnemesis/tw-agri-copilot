import { test, expect } from '@playwright/test';

test('latest observed prices stay separate from dated complete analysis', async ({ page, request }) => {
  const current = await (await request.get('/data/current.json')).json();
  const latest = await (await request.get('/data/latest-market.json')).json();
  await page.goto('/');
  const section = page.locator('#latest-market');
  await expect(section).toHaveAttribute('data-latest-as-of', latest.as_of_date || '');
  await expect(section).toContainText(`有效行情 ${latest.valid_watchlist_count}／${latest.expected_watchlist_count} 項`);
  await expect(section.locator('tbody tr')).toHaveCount(latest.expected_watchlist_count);
  for (const item of latest.items.filter(item => item.observation_status === 'missing')) {
    const row = section.locator(`[data-latest-item="${item.canonical_id}"]`);
    await expect(row).toContainText('缺資料（原因未確認）');
    await expect(row.locator('td').first()).toHaveText('—');
  }
  await expect(page.locator('#movers h2')).toContainText(current.as_of_date);
  const historical = current.as_of_date !== current.publication_status.requested_date || current.publication_status.status !== 'complete';
  if (historical) {
    await expect(page.locator('#recommendations .recommendation-card')).toHaveCount(0);
    await expect(page.locator('#advice')).toContainText('歷史採買分析');
  }
  await expect(page.getByRole('heading', { name: '今日變便宜／今日變貴' })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
