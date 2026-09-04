import { expect, test } from '@playwright/test';

const seasonCards = '[data-season-grid] .season-card';
const produceIcons = `${seasonCards} .produce-icon`;

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

  // "livestock" is a real, registered category (Issue #44 Part B) -- but it has no
  // no_official_season_registry filter button on this page (only categories with rows in this
  // month's catalog get one), so validCategories (derived from this section's own [data-filter]
  // buttons) must treat it exactly like any other invalid value: fall back to "all".
  await page.goto(
    '/season/current.html?keep=one&keep=two&q=瓜&category=livestock#season',
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

test('local decorative icons render and reflow at a 200% zoom equivalent', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  const spriteResponses = [];
  page.on('response', (response) => {
    if (new URL(response.url()).pathname.endsWith('/assets/icons/produce.svg')) {
      spriteResponses.push(response);
    }
  });

  await page.goto('/season/current.html');
  const cardCount = await page.locator(seasonCards).count();
  expect(cardCount).toBe(39);
  await expect(page.locator(produceIcons)).toHaveCount(cardCount);
  await expect.poll(() => spriteResponses.length).toBeGreaterThan(0);
  expect(spriteResponses.every((response) => response.status() === 200)).toBe(true);
  expect(
    spriteResponses.every((response) =>
      String(response.headers()['content-type'] || '').includes('image/svg+xml'),
    ),
  ).toBe(true);
  expect(await Promise.all(spriteResponses.map((response) => response.finished()))).toEqual(
    spriteResponses.map(() => null),
  );
  await expect.poll(() =>
    page.locator(`${produceIcons} use`).evaluateAll((uses) =>
      uses.every((use) => {
        const box = use.getBBox();
        return box.width > 0 && box.height > 0;
      }),
    ),
  ).toBe(true);

  const iconContract = await page.locator(produceIcons).evaluateAll((icons) =>
    icons.map((icon) => {
      const use = icon.querySelector('use');
      const box = use?.getBBox();
      return {
        ariaHidden: icon.getAttribute('aria-hidden'),
        focusable: icon.getAttribute('focusable'),
        fidelity: icon.getAttribute('data-icon-fidelity'),
        href: use?.getAttribute('href') || '',
        width: box?.width || 0,
        height: box?.height || 0,
      };
    }),
  );
  expect(iconContract.every((icon) => icon.ariaHidden === 'true')).toBe(true);
  expect(iconContract.every((icon) => icon.focusable === 'false')).toBe(true);
  // category_fallback is the documented degradation for an agency catalogue name nobody has
  // authored an icon for. Forbidding it would make a decorative gap block a publication.
  expect(iconContract.every((icon) => ['exact', 'representative', 'category_fallback'].includes(icon.fidelity))).toBe(true);
  expect(iconContract.every((icon) => icon.href.startsWith('../assets/icons/produce.svg#produce-'))).toBe(true);
  expect(iconContract.every((icon) => icon.width > 0 && icon.height > 0)).toBe(true);

  // 640 CSS px exercises the layout viewport equivalent of 1280 px at 200% zoom.
  await page.setViewportSize({ width: 640, height: 900 });
  const layoutFailures = await page.locator(seasonCards).evaluateAll((elements) =>
    elements.flatMap((element) => {
      const rect = element.getBoundingClientRect();
      const title = element.querySelector('.season-card-title');
      const titleRect = title?.getBoundingClientRect();
      const iconRect = element.querySelector('.produce-icon')?.getBoundingClientRect();
      const failures = [];
      if (rect.left < -1 || rect.right > window.innerWidth + 1) failures.push('card viewport overflow');
      if (title && title.scrollWidth > title.clientWidth + 1) failures.push('title overflow');
      if (titleRect && (titleRect.left < rect.left - 1 || titleRect.right > rect.right + 1)) failures.push('title outside card');
      if (iconRect && (iconRect.left < rect.left - 1 || iconRect.right > rect.right + 1)) failures.push('icon outside card');
      return failures;
    }),
  );
  expect(layoutFailures).toEqual([]);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1),
  ).toBe(true);
  expect(browserErrors).toEqual([]);
});

test('icons and complete catalog remain available without JavaScript', async ({ browser }, testInfo) => {
  const projectUse = testInfo.project.use;
  const contextOptions = { javaScriptEnabled: false };
  for (const key of ['viewport', 'isMobile', 'hasTouch', 'deviceScaleFactor', 'userAgent', 'locale', 'colorScheme', 'reducedMotion']) {
    if (projectUse[key] !== undefined) contextOptions[key] = projectUse[key];
  }
  if (!contextOptions.viewport) contextOptions.viewport = { width: 1280, height: 720 };
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  const requestFailures = [];
  page.on('requestfailed', (request) => requestFailures.push(request.url()));
  try {
    const spriteResponsePromise = page.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith('/assets/icons/produce.svg'),
    );
    await page.goto('http://127.0.0.1:4173/season/current.html');
    const spriteResponse = await spriteResponsePromise;
    expect(spriteResponse.status()).toBe(200);
    expect(await spriteResponse.finished()).toBeNull();
    await expect(page.locator(seasonCards)).toHaveCount(39);
    await expect(page.locator(produceIcons)).toHaveCount(39);
    await expect(page.locator(`${produceIcons} use`)).toHaveCount(39);
    expect(await page.locator(`${seasonCards}[hidden]`).count()).toBe(0);
    await expect.poll(() =>
      page.locator(`${produceIcons} use`).evaluateAll((uses) =>
        uses.every((use) => {
          const box = use.getBBox();
          return box.width > 0 && box.height > 0;
        }),
      ),
    ).toBe(true);
    expect(requestFailures).toEqual([]);
  } finally {
    await context.close();
  }
});

test('print layout keeps icons visible and hides interactive controls', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  const spriteResponsePromise = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith('/assets/icons/produce.svg'),
  );
  await page.goto('/season/current.html');
  const spriteResponse = await spriteResponsePromise;
  expect(spriteResponse.status()).toBe(200);
  expect(await spriteResponse.finished()).toBeNull();
  await page.emulateMedia({ media: 'print' });
  expect(
    await page.locator('.filter-group, .season-controls').evaluateAll((elements) =>
      elements.every((element) => getComputedStyle(element).display === 'none'),
    ),
  ).toBe(true);
  await expect.poll(() =>
    page.locator(`${produceIcons} use`).evaluateAll((uses) =>
      uses.length === 39 && uses.every((use) => {
        const box = use.getBBox();
        return box.width > 0 && box.height > 0;
      }),
    ),
  ).toBe(true);
  expect(
    await page.locator(produceIcons).evaluateAll((icons) =>
      icons.length === 39 &&
      icons.every((icon) => {
        const box = icon.getBoundingClientRect();
        const useBox = icon.querySelector('use')?.getBBox();
        const style = getComputedStyle(icon);
        return box.width > 0 && box.height > 0 && (useBox?.width || 0) > 0 && (useBox?.height || 0) > 0 && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
      }),
    ),
  ).toBe(true);
  expect(browserErrors).toEqual([]);
});
