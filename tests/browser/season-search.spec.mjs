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

async function expectCardState(page, expected) {
  await expect.poll(() => visibleCards(page)).toEqual(expected);
  await expect(page.locator('[data-season-result-count]')).toHaveText(
    `顯示 ${expected.length} 項`,
  );
  if (expected.length === 0) {
    await expect(page.locator('[data-season-empty]')).toBeVisible();
  } else {
    await expect(page.locator('[data-season-empty]')).toBeHidden();
  }
}

function filtered(cardsToFilter, query = '', category = 'all') {
  return cardsToFilter
    .filter(
      (card) =>
        (!query || card.name.includes(query)) &&
        (category === 'all' || card.category === category),
    )
    .map(({ name, category: cardCategory }) => ({
      name,
      category: cardCategory,
    }));
}

function urlState(page) {
  const url = new URL(page.url());
  return {
    q: url.searchParams.get('q'),
    category: url.searchParams.get('category'),
    keep: url.searchParams.getAll('keep'),
    hash: url.hash,
  };
}

function collectBrowserErrors(page) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return errors;
}

test('hydrates valid, invalid, and blank URL state', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);

  await page.goto(
    '/season/current.html?keep=one&keep=two&q=瓜&category=vegetable#season',
  );
  const initial = await cards(page);
  expect(initial.length).toBeGreaterThan(0);

  const search = page.getByRole('searchbox', { name: '搜尋蔬果名稱' });
  const vegetable = page.getByRole('button', { name: '蔬菜', exact: true });
  const intersection = filtered(initial, '瓜', 'vegetable');
  expect(intersection.length).toBeGreaterThan(0);
  await expect(search).toHaveValue('瓜');
  await expect(vegetable).toHaveAttribute('aria-pressed', 'true');
  await expectCardState(page, intersection);
  expect(urlState(page)).toEqual({
    q: '瓜',
    category: 'vegetable',
    keep: ['one', 'two'],
    hash: '#season',
  });

  await page.goto(
    '/season/current.html?keep=one&keep=two&q=瓜&category=invalid#season',
  );
  await expect(search).toHaveValue('瓜');
  await expect(
    page.getByRole('button', { name: '全部', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expectCardState(page, filtered(await cards(page), '瓜'));
  expect(urlState(page)).toEqual({
    q: '瓜',
    category: null,
    keep: ['one', 'two'],
    hash: '#season',
  });

  await page.goto(
    '/season/current.html?keep=one&keep=two&q=%20%E3%80%80%20&category=all#season',
  );
  const blankInitial = await cards(page);
  await expect(search).toHaveValue('');
  await expect(
    page.getByRole('button', { name: '全部', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expectCardState(page, filtered(blankInitial));
  expect(urlState(page)).toEqual({
    q: null,
    category: null,
    keep: ['one', 'two'],
    hash: '#season',
  });
  expect(browserErrors).toEqual([]);
});

test('replace, push, and popstate restore the complete state', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);

  await page.goto('/season/current.html?keep=one&keep=two#season');
  const initial = await cards(page);
  expect(initial.length).toBeGreaterThan(0);
  const initialHistoryLength = await page.evaluate(() => window.history.length);

  const search = page.getByRole('searchbox', { name: '搜尋蔬果名稱' });
  const all = page.getByRole('button', { name: '全部', exact: true });
  const vegetable = page.getByRole('button', { name: '蔬菜', exact: true });

  await search.fill('　瓜　');
  expect(urlState(page)).toEqual({
    q: '瓜',
    category: null,
    keep: ['one', 'two'],
    hash: '#season',
  });
  expect(await page.evaluate(() => window.history.length)).toBe(
    initialHistoryLength,
  );
  await expectCardState(page, filtered(initial, '瓜'));

  await vegetable.click();
  expect(urlState(page)).toEqual({
    q: '瓜',
    category: 'vegetable',
    keep: ['one', 'two'],
    hash: '#season',
  });
  expect(await page.evaluate(() => window.history.length)).toBe(
    initialHistoryLength + 1,
  );
  await expectCardState(page, filtered(initial, '瓜', 'vegetable'));

  await vegetable.click();
  expect(await page.evaluate(() => window.history.length)).toBe(
    initialHistoryLength + 1,
  );

  await search.fill('');
  expect(urlState(page)).toEqual({
    q: null,
    category: 'vegetable',
    keep: ['one', 'two'],
    hash: '#season',
  });
  expect(await page.evaluate(() => window.history.length)).toBe(
    initialHistoryLength + 1,
  );
  await expectCardState(page, filtered(initial, '', 'vegetable'));

  await search.fill('不存在的蔬果名稱');
  await expectCardState(page, []);
  expect(await page.evaluate(() => window.history.length)).toBe(
    initialHistoryLength + 1,
  );

  await all.click();
  expect(urlState(page)).toEqual({
    q: '不存在的蔬果名稱',
    category: null,
    keep: ['one', 'two'],
    hash: '#season',
  });
  expect(await page.evaluate(() => window.history.length)).toBe(
    initialHistoryLength + 2,
  );
  await expectCardState(page, []);

  await page.goBack();
  await expect(search).toHaveValue('不存在的蔬果名稱');
  await expect(vegetable).toHaveAttribute('aria-pressed', 'true');
  await expectCardState(page, []);
  expect(urlState(page).category).toBe('vegetable');

  await page.goBack();
  await expect(search).toHaveValue('瓜');
  await expect(all).toHaveAttribute('aria-pressed', 'true');
  await expectCardState(page, filtered(initial, '瓜'));
  expect(urlState(page)).toEqual({
    q: '瓜',
    category: null,
    keep: ['one', 'two'],
    hash: '#season',
  });

  await page.goForward();
  await expect(search).toHaveValue('不存在的蔬果名稱');
  await expect(vegetable).toHaveAttribute('aria-pressed', 'true');
  await expectCardState(page, []);
  expect(urlState(page).category).toBe('vegetable');
  expect(browserErrors).toEqual([]);
});

test('homepage ignores URL state and keeps its URL unchanged', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);

  await page.goto(
    '/index.html?keep=one&keep=two&q=瓜&category=fruit#recommendations',
  );
  const initialUrl = page.url();
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
  expect(page.url()).toBe(initialUrl);
  expect(browserErrors).toEqual([]);
});
