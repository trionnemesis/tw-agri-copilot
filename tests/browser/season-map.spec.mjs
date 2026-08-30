import { expect, test } from '@playwright/test';

const countySections = '[data-county-section]';
const countyLinks = '[data-county-link]';
const countySelect = '[data-county-select]';

const counties = [
  ['taipei-city', '臺北市'],
  ['new-taipei-city', '新北市'],
  ['keelung-city', '基隆市'],
  ['taoyuan-city', '桃園市'],
  ['hsinchu-city', '新竹市'],
  ['hsinchu-county', '新竹縣'],
  ['miaoli-county', '苗栗縣'],
  ['taichung-city', '臺中市'],
  ['changhua-county', '彰化縣'],
  ['nantou-county', '南投縣'],
  ['yunlin-county', '雲林縣'],
  ['chiayi-city', '嘉義市'],
  ['chiayi-county', '嘉義縣'],
  ['tainan-city', '臺南市'],
  ['kaohsiung-city', '高雄市'],
  ['pingtung-county', '屏東縣'],
  ['yilan-county', '宜蘭縣'],
  ['hualien-county', '花蓮縣'],
  ['taitung-county', '臺東縣'],
  ['penghu-county', '澎湖縣'],
  ['kinmen-county', '金門縣'],
  ['lienchiang-county', '連江縣'],
];

function collectBrowserErrors(page) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return errors;
}

function urlState(page) {
  const url = new URL(page.url());
  return {
    county: url.searchParams.get('county'),
    keep: url.searchParams.getAll('keep'),
    hash: url.hash,
  };
}

async function visibleCountySlugs(page) {
  return page.locator(countySections).evaluateAll((sections) =>
    sections
      .filter((section) => !section.hidden)
      .map((section) => section.dataset.countySection),
  );
}

async function expectSelectedCounty(page, slug, displayName) {
  await expect(page.locator(countySelect)).toHaveValue(slug);
  await expect(page.locator(`${countyLinks}[aria-current="true"]`)).toHaveAttribute(
    'data-county-link',
    slug,
  );
  await expect.poll(() => visibleCountySlugs(page)).toEqual([slug]);
  await expect(page.locator(`[data-county-section="${slug}"]`)).toBeVisible();
  await expect(page.locator('[data-county-live]')).toContainText(`已選取${displayName}`);
}

test('renders the exact 22-county map and hydrates safe URL state', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);

  await page.goto(
    '/season/map.html?keep=one&county=taipei-city&keep=two#county-taipei-city',
  );

  await expect(page.locator(countySections)).toHaveCount(22);
  await expect(page.locator(countyLinks)).toHaveCount(22);
  await expect(page.locator(`${countyLinks} [data-county-path]`)).toHaveCount(22);
  await expect(page.locator(`${countySelect} option`)).toHaveCount(23);

  expect(
    await page.locator(countySections).evaluateAll((sections) =>
      sections.map((section) => [
        section.dataset.countySection,
        section.dataset.countyName,
      ]),
    ),
  ).toEqual(counties);
  expect(
    await page.locator(countyLinks).evaluateAll((links) =>
      links.map((link) => [link.dataset.countyLink, link.getAttribute('aria-label')]),
    ),
  ).toEqual(counties);
  await expectSelectedCounty(page, 'taipei-city', '臺北市');
  expect(urlState(page)).toEqual({
    county: 'taipei-city',
    keep: ['one', 'two'],
    hash: '#county-taipei-city',
  });

  await page.goto('/season/map.html?keep=one&county=not-a-county&keep=two#safe');
  await expect(page.locator(countySelect)).toHaveValue('');
  await expect(page.locator(`${countyLinks}[aria-current="true"]`)).toHaveCount(0);
  await expect.poll(() => visibleCountySlugs(page)).toEqual([]);
  await expect(page.locator('[data-county-unselected]')).toBeVisible();
  expect(urlState(page)).toEqual({
    county: 'not-a-county',
    keep: ['one', 'two'],
    hash: '#safe',
  });
  expect(browserErrors).toEqual([]);
});

test('select, pointer click, and keyboard activation update selection and preserve URL data', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  await page.goto('/season/map.html?keep=one&keep=two#map-state');

  await page.locator(countySelect).selectOption('new-taipei-city');
  await expectSelectedCounty(page, 'new-taipei-city', '新北市');
  expect(urlState(page)).toEqual({
    county: 'new-taipei-city',
    keep: ['one', 'two'],
    hash: '#map-state',
  });
  await expect(page.locator('[data-county-heading]:focus')).toHaveText('新北市');

  await page.locator(`${countyLinks}[data-county-link="taichung-city"]`).click();
  await expectSelectedCounty(page, 'taichung-city', '臺中市');
  expect(urlState(page)).toEqual({
    county: 'taichung-city',
    keep: ['one', 'two'],
    hash: '#map-state',
  });

  const taipeiLink = page.locator(`${countyLinks}[data-county-link="taipei-city"]`);
  await taipeiLink.focus();
  await expect(taipeiLink).toBeFocused();
  await taipeiLink.press('Enter');
  await expectSelectedCounty(page, 'taipei-city', '臺北市');
  expect(urlState(page)).toEqual({
    county: 'taipei-city',
    keep: ['one', 'two'],
    hash: '#map-state',
  });
  expect(browserErrors).toEqual([]);
});

test('tap selects a county on a touch viewport', async ({ page }, testInfo) => {
  test.skip(!testInfo.project.use.hasTouch, 'touch interaction is covered by the mobile project');
  const browserErrors = collectBrowserErrors(page);
  await page.goto('/season/map.html?keep=touch#map');

  await page.locator(`${countyLinks}[data-county-link="penghu-county"]`).tap();
  await expectSelectedCounty(page, 'penghu-county', '澎湖縣');
  expect(urlState(page)).toEqual({
    county: 'penghu-county',
    keep: ['touch'],
    hash: '#map',
  });
  expect(browserErrors).toEqual([]);
});

test('history back and forward restore complete county state', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  await page.goto('/season/map.html?keep=one&keep=two#history');
  const initialHistoryLength = await page.evaluate(() => window.history.length);

  await page.locator(countySelect).selectOption('taipei-city');
  await expectSelectedCounty(page, 'taipei-city', '臺北市');
  expect(await page.evaluate(() => window.history.length)).toBe(initialHistoryLength + 1);

  await page.locator(countySelect).selectOption('hualien-county');
  await expectSelectedCounty(page, 'hualien-county', '花蓮縣');
  expect(await page.evaluate(() => window.history.length)).toBe(initialHistoryLength + 2);

  await page.goBack();
  await expectSelectedCounty(page, 'taipei-city', '臺北市');
  expect(urlState(page)).toEqual({
    county: 'taipei-city',
    keep: ['one', 'two'],
    hash: '#history',
  });

  await page.goBack();
  await expect(page.locator(countySelect)).toHaveValue('');
  await expect.poll(() => visibleCountySlugs(page)).toEqual([]);
  expect(urlState(page)).toEqual({
    county: null,
    keep: ['one', 'two'],
    hash: '#history',
  });

  await page.goForward();
  await expectSelectedCounty(page, 'taipei-city', '臺北市');
  await page.goForward();
  await expectSelectedCounty(page, 'hualien-county', '花蓮縣');
  expect(browserErrors).toEqual([]);
});

test('Taipei keeps official markets separate from the official produce empty state', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  await page.goto('/season/map.html?county=taipei-city');
  const taipei = page.locator('[data-county-section="taipei-city"]');

  await expect(taipei.locator('.official-market-card')).toHaveCount(2);
  await expect(taipei).toContainText('市場代號 104');
  await expect(taipei).toContainText('臺北二');
  await expect(taipei).toContainText('第二果菜批發市場');
  await expect(taipei).toContainText('市場代號 109');
  await expect(taipei).toContainText('臺北一');
  await expect(taipei).toContainText('第一果菜批發市場');
  await expect(taipei.locator('[data-produce-empty]')).toHaveText(
    '農糧署本月產期資料未列出臺北市的水果／蔬菜。',
  );
  await expect(taipei.locator('.season-map-produce-card')).toHaveCount(0);
  await expect(taipei.locator('.semantic-warning')).toHaveText(
    '「產地產期」與「批發市場成交」是不同資料語意。市場位於該縣市，不代表成交品項產自該縣市。',
  );
  expect(browserErrors).toEqual([]);
});

test('the interactive map loads only checked-in local resources', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  const requests = [];
  page.on('request', (request) => {
    requests.push({ url: request.url(), resourceType: request.resourceType() });
  });

  await page.goto('/season/map.html?county=tainan-city');
  await expectSelectedCounty(page, 'tainan-city', '臺南市');
  await page.locator(countySelect).selectOption('kaohsiung-city');
  await expectSelectedCounty(page, 'kaohsiung-city', '高雄市');

  expect(requests.length).toBeGreaterThan(1);
  expect(
    requests.every(({ url }) => new URL(url).origin === 'http://127.0.0.1:4173'),
  ).toBe(true);
  expect(
    requests.filter(({ resourceType }) => ['fetch', 'xhr'].includes(resourceType)),
  ).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test('all county details and map anchors remain readable without JavaScript', async ({ browser }, testInfo) => {
  const projectUse = testInfo.project.use;
  const contextOptions = { javaScriptEnabled: false };
  for (const key of [
    'viewport',
    'isMobile',
    'hasTouch',
    'deviceScaleFactor',
    'userAgent',
    'locale',
    'colorScheme',
    'reducedMotion',
  ]) {
    if (projectUse[key] !== undefined) contextOptions[key] = projectUse[key];
  }
  if (!contextOptions.viewport) contextOptions.viewport = { width: 1280, height: 720 };
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  const requestFailures = [];
  page.on('requestfailed', (request) => requestFailures.push(request.url()));

  try {
    await page.goto('http://127.0.0.1:4173/season/map.html?county=taipei-city');
    await expect(page.locator(countySections)).toHaveCount(22);
    await expect(page.locator(countyLinks)).toHaveCount(22);
    expect(await page.locator(`${countySections}[hidden]`).count()).toBe(0);
    expect(
      await page.locator(countySections).evaluateAll((sections) =>
        sections.every((section) => {
          const style = getComputedStyle(section);
          const heading = section.querySelector('[data-county-heading]');
          return style.display !== 'none' && style.visibility !== 'hidden' && Boolean(heading?.textContent.trim());
        }),
      ),
    ).toBe(true);
    expect(
      await page.locator(countyLinks).evaluateAll((links) =>
        links.every((link) =>
          link.getAttribute('href') === `#county-${link.dataset.countyLink}`
        ),
      ),
    ).toBe(true);
    await page.locator(`${countyLinks}[data-county-link="hualien-county"]`).click();
    await expect(page).toHaveURL(/#county-hualien-county$/);
    await expect(page.locator(':target')).toHaveAttribute(
      'data-county-section',
      'hualien-county',
    );
    await expect(page.locator('[data-county-section="taipei-city"] .official-market-card')).toHaveCount(2);
    await expect(page.locator('[data-county-section="taipei-city"] [data-produce-empty]')).toBeVisible();
    expect(requestFailures).toEqual([]);
  } finally {
    await context.close();
  }
});

test('mobile and 200% equivalent layouts avoid horizontal overflow', async ({ page }, testInfo) => {
  const browserErrors = collectBrowserErrors(page);
  await page.goto('/season/map.html?county=lienchiang-county');

  if (testInfo.project.use.isMobile) {
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
      ),
    ).toBe(true);
  }

  // 640 CSS px exercises the layout viewport equivalent of 1280 px at 200% zoom.
  await page.setViewportSize({ width: 640, height: 900 });
  const overflow = await page
    .locator('[data-season-map-root], [data-county-map], [data-county-section="lienchiang-county"]')
    .evaluateAll((elements) =>
      elements.flatMap((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left < -1 || rect.right > window.innerWidth + 1
          ? [element.getAttribute('data-county-section') || element.className || element.tagName]
          : [];
      }),
    );
  expect(overflow).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    ),
  ).toBe(true);
  expect(browserErrors).toEqual([]);
});

test('print and reduced-motion modes retain readable results with minimal motion', async ({ page }) => {
  const browserErrors = collectBrowserErrors(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function scrollIntoView(options) {
      window.__seasonMapScrollOptions = options;
      return original.call(this, options);
    };
  });
  await page.goto('/season/map.html');

  await page.locator(countySelect).selectOption('taipei-city');
  await expectSelectedCounty(page, 'taipei-city', '臺北市');
  expect(await page.evaluate(() => window.__seasonMapScrollOptions?.behavior)).toBe('auto');
  expect(
    await page
      .locator('[data-county-path="taipei-city"]')
      .evaluate((path) => getComputedStyle(path).transitionDuration),
  ).toMatch(/^(0s)(, 0s)*$/);

  await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
  expect(
    await page.locator('.season-map-map-panel').evaluate((panel) => getComputedStyle(panel).display),
  ).toBe('none');
  await expect(page.locator('[data-county-section="taipei-city"]')).toBeVisible();
  await expect(page.locator(countySections)).toHaveCount(22);
  expect(await page.locator(`${countySections}:visible`).count()).toBe(22);
  const officialLink = page.locator(
    '[data-county-section="taipei-city"] .official-market-card a[href^="https://"]',
  ).first();
  expect(
    await officialLink.evaluate((link) => getComputedStyle(link, '::after').content),
  ).toContain('https://www.tapmc.com.tw/');
  expect(browserErrors).toEqual([]);
});
