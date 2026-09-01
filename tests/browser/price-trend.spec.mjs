import { expect, test } from '@playwright/test';


test('produce page exposes a readable quantitative price trend', async ({ page }) => {
  await page.goto('/produce/banana.html');

  await expect(page.getByRole('heading', { name: '價格量化摘要' })).toBeVisible();
  await expect(page.getByText('7D 波動度 CV', { exact: true })).toBeVisible();
  await expect(page.getByText('30D 有效日', { exact: true })).toBeVisible();

  const trendSection = page.locator('.trend-quant-chart');
  await expect(trendSection.getByRole('heading')).toContainText(
    /最多 120 日價格趨勢 · 實際 \d+ 個有效交易日/,
  );

  const chart = page.locator("[data-trend-chart='v1']");
  await expect(chart).toBeVisible();
  await expect(chart.locator('.chart-line')).toHaveCount(1);
  await expect(chart.locator('.chart-ref-7d')).toHaveCount(1);
  await expect(chart.locator('.chart-ref-30d')).toHaveCount(1);
  await expect(chart.locator('.chart-point-latest')).toHaveCount(1);
  await expect(chart.locator('.chart-point-high')).toHaveCount(1);
  await expect(chart.locator('.chart-point-low')).toHaveCount(1);
  await expect(chart.locator('.chart-tick').filter({ hasText: 'NT$' }).first()).toBeVisible();

  const annotations = chart.locator('[data-chart-label]');
  await expect(annotations).toHaveCount(5);
  const annotationBoxes = await annotations.evaluateAll((nodes) =>
    nodes.map((node) => {
      const box = node.getBoundingClientRect();
      return {
        key: node.getAttribute('data-chart-label'),
        top: box.top,
        bottom: box.bottom,
      };
    }),
  );
  for (let leftIndex = 0; leftIndex < annotationBoxes.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < annotationBoxes.length; rightIndex += 1) {
      const leftBox = annotationBoxes[leftIndex];
      const rightBox = annotationBoxes[rightIndex];
      const overlap = Math.min(leftBox.bottom, rightBox.bottom) - Math.max(leftBox.top, rightBox.top);
      expect(overlap, `${leftBox.key} overlaps ${rightBox.key}`).toBeLessThanOrEqual(0.5);
    }
  }

  const accessibleSummary = await chart.getAttribute('aria-label');
  expect(accessibleSummary).toContain('有效交易日');
  expect(accessibleSummary).toContain('7D 均價');
  expect(accessibleSummary).toContain('30D 均價');

  await expect(page.getByText(/休市與缺資料不補 0/)).toBeVisible();
  await expect(page.locator("style[data-trend-quant-style='v1']")).toHaveCount(1);

  const pageOverflows = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(pageOverflows).toBe(false);
});
