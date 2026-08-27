import { expect, test } from '@playwright/test';

const seasonCards = '[data-season-grid] .season-card';

async function cards(page) {
  return page.locator(seasonCards).evaluateAll((elements) =>
    elements.map((element) => ({
      name: element.dataset.searchName || '',
      category: element.dataset.category,
      hidden: element.hidden,
    })),
  );
}

async function visibleCards(page) {
  return (await cards(page))
    .filter((card) => !card.hidden)
    .map(({ name, category }) => ({ name, category }));
}

function collectBrowserErrors(page) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return errors;
}

test('name search and category use an AND intersection', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);

  await page.goto('/season/current.html');
  const initial = await cards(page);
  expect(initial.length).toBeGreaterThan(0);
  expect(initial.every((card) => !card.hidden)).toBe(true);

  const search = page.getByRole('searchbox', { name: '搜尋蔬果名稱' });
  const resultCount = page.locator('[data-season-result-count]');
  await search.fill('　瓜　');

  const nameMatches = initial
    .filter((card) => card.name.includes('瓜'))
    .map(({ name, category }) => ({ name, category }));
  expect(nameMatches.length).toBeGreaterThan(0);
  await expect.poll(() => visibleCards(page)).toEqual(nameMatches);
  await expect(resultCount).toHaveText(`顯示 ${nameMatches.length} 項`);

  const vegetable = page.getByRole('button', { name: '蔬菜', exact: true });
  await vegetable.click();
  const intersection = nameMatches.filter(
    (card) => card.category === 'vegetable',
  );
  expect(intersection.length).toBeGreaterThan(0);
  await expect.poll(() => visibleCards(page)).toEqual(intersection);
  await expect(resultCount).toHaveText(`顯示 ${intersection.length} 項`);
  await expect(vegetable).toHaveAttribute('aria-pressed', 'true');

  await search.fill('');
  const vegetables = initial
    .filter((card) => card.category === 'vegetable')
    .map(({ name, category }) => ({ name, category }));
  await expect.poll(() => visibleCards(page)).toEqual(vegetables);
  await expect(resultCount).toHaveText(`顯示 ${vegetables.length} 項`);
  await expect(vegetable).toHaveAttribute('aria-pressed', 'true');
  expect(browserErrors).toEqual([]);
});

test('zero results recover and the homepage filter remains compatible', async ({
  page,
}) => {
  const browserErrors = collectBrowserErrors(page);

  await page.goto('/season/current.html');
  const initialCount = await page.locator(seasonCards).count();
  expect(initialCount).toBeGreaterThan(0);

  const search = page.getByRole('searchbox', { name: '搜尋蔬果名稱' });
  const resultCount = page.locator('[data-season-result-count]');
  const emptyState = page.locator('[data-season-empty]');
  await search.fill('不存在的蔬果名稱');
  await expect.poll(() => visibleCards(page)).toEqual([]);
  await expect(resultCount).toHaveText('顯示 0 項');
  await expect(emptyState).toBeVisible();

  await search.fill('');
  await expect.poll(() => visibleCards(page)).toHaveLength(initialCount);
  await expect(emptyState).toBeHidden();

  await page.goto('/index.html');
  await expect(page.locator('[data-season-search]')).toHaveCount(0);
  const homepageCards = await cards(page);
  expect(homepageCards.length).toBeGreaterThan(0);
  const vegetable = page.getByRole('button', { name: '蔬菜', exact: true });
  await vegetable.click();
  const visibleHomepageCards = await visibleCards(page);
  expect(visibleHomepageCards.length).toBeGreaterThan(0);
  expect(
    visibleHomepageCards.every((card) => card.category === 'vegetable'),
  ).toBe(true);
  await expect(vegetable).toHaveAttribute('aria-pressed', 'true');
  expect(browserErrors).toEqual([]);
});
