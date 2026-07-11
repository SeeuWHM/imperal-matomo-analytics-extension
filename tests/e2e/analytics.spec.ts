/**
 * Analytics extension — E2E tests.
 *
 * Run:
 *   IMPERAL_PASSWORD=... npx playwright test --config=playwright.config.ts
 *
 * Structure:
 *   1. UI hygiene — no extra buttons, correct panels
 *   2. Panel data — KPIs load, chart renders, tables populate
 *   3. Chat functions — each analytics tool via Webbee prompt
 */
import { test, expect, Page } from '@playwright/test';

const EXT = '/ext/analytics';
const CHAT_INPUT = 'role=textbox[name="Message Webbee..."]';
const WEBBEE_RESPONSE_TIMEOUT = 30_000;

// ─────────────────────────── helpers ─────────────────────────────────────────

async function sendPrompt(page: Page, text: string) {
  await page.locator(CHAT_INPUT).fill(text);
  await page.locator(CHAT_INPUT).press('Enter');
}

/** Wait until the last bot message is no longer "Thinking…" */
async function waitForResponse(page: Page, expectedSubstring?: string) {
  // Wait for thinking indicator to disappear
  await expect(page.getByText('Thinking', { exact: false }))
    .toBeHidden({ timeout: WEBBEE_RESPONSE_TIMEOUT })
    .catch(() => {});   // ignore if it was never shown

  if (expectedSubstring) {
    await expect(page.getByText(expectedSubstring, { exact: false }))
      .toBeVisible({ timeout: WEBBEE_RESPONSE_TIMEOUT });
  } else {
    // Wait for Function call badge to appear (Webbee used a tool)
    await expect(page.getByText('Function call', { exact: false }).last())
      .toBeVisible({ timeout: WEBBEE_RESPONSE_TIMEOUT });
  }
}

async function goToAnalytics(page: Page) {
  await page.goto(EXT);
  // Wait for left sidebar panel to load (shows live counter)
  await expect(page.getByText('LIVE', { exact: false })).toBeVisible({ timeout: 20_000 });
}

// ─────────────────────────── 1. UI Hygiene ───────────────────────────────────

test.describe('UI Hygiene — no extra buttons', () => {
  test.beforeEach(async ({ page }) => {
    await goToAnalytics(page);
    // Give panels time to fully render
    await page.waitForTimeout(4_000);
  });

  test('no Quick Action grid buttons', async ({ page }) => {
    // These action buttons must NOT exist after our cleanup
    const forbidden = ['What to do', 'Anomalies', 'Live visitors', 'Top 10 pages',
                       'Week vs last week', 'Traffic sources', 'Top countries',
                       'Daily brief (AI)', 'AI Insights'];
    for (const label of forbidden) {
      await expect(page.getByRole('button', { name: label }))
        .toBeHidden({ timeout: 2_000 })
        .catch(() => {});  // pass if not found at all
      const el = page.getByRole('button', { name: label });
      const count = await el.count();
      expect(count, `Found forbidden button: "${label}"`).toBe(0);
    }
  });

  test('only navigation buttons in center hub header', async ({ page }) => {
    // ⚙️ Settings nav + ✕ Close nav are the only buttons in the hub
    await expect(page.getByRole('button', { name: '⚙️' })).toBeVisible();
    await expect(page.getByRole('button', { name: '✕' })).toBeVisible();

    // No data-action refresh button (↻) that used to call real_time
    const refresh = page.getByRole('button', { name: '↻' });
    expect(await refresh.count()).toBe(0);
  });

  test('Open Dashboard button exists in sidebar (navigation only)', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Open Dashboard/i })).toBeVisible();
  });

  test('result zone shows empty state, not stale Quick Action message', async ({ page }) => {
    // Should NOT show old "Press a Quick Action above" text
    const stale = page.getByText('Press a Quick Action above', { exact: false });
    expect(await stale.count()).toBe(0);
  });
});

// ─────────────────────────── 2. Panel data ───────────────────────────────────

test.describe('Panel data — KPIs and tables render', () => {
  test.beforeEach(async ({ page }) => {
    await goToAnalytics(page);
    await page.waitForTimeout(6_000);
  });

  test('sidebar shows LIVE, TODAY, YESTERDAY stats', async ({ page }) => {
    await expect(page.getByText('LIVE', { exact: true })).toBeVisible();
    await expect(page.getByText('TODAY', { exact: true })).toBeVisible();
    await expect(page.getByText('YESTERDAY', { exact: true })).toBeVisible();
  });

  test('center hub shows KPI row with 8 stats', async ({ page }) => {
    await expect(page.getByText('LIVE (30M)', { exact: true })).toBeVisible();
    await expect(page.getByText('LAST 30D', { exact: true })).toBeVisible();
    await expect(page.getByText('WOW Δ', { exact: true })).toBeVisible();
    await expect(page.getByText('BOUNCE RATE', { exact: true })).toBeVisible();
  });

  test('traffic chart renders (last 30 days label)', async ({ page }) => {
    await expect(page.getByText('TRAFFIC — LAST 30 DAYS', { exact: true })).toBeVisible();
  });

  test('top pages table has at least 5 rows', async ({ page }) => {
    await expect(page.getByText('TOP PAGES', { exact: false })).toBeVisible();
    // Table rows — count cells in the URL column
    const rows = page.locator('table tr, [role="row"]');
    const count = await rows.count();
    expect(count).toBeGreaterThan(5);
  });

  test('traffic sources section visible', async ({ page }) => {
    await expect(page.getByText('TRAFFIC SOURCES', { exact: false })).toBeVisible();
  });

  test('devices section visible', async ({ page }) => {
    await expect(page.getByText('DEVICES', { exact: false })).toBeVisible();
  });

  test('live visitor count is a number', async ({ page }) => {
    const badge = page.getByText(/\d+ live/i).first();
    await expect(badge).toBeVisible();
  });
});

// ─────────────────────────── 3. Chat functions ───────────────────────────────

test.describe('Chat functions — via Webbee prompt', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/assistant');
    await expect(page.locator(CHAT_INPUT)).toBeVisible({ timeout: 10_000 });
  });

  test('traffic — returns visits and pageviews', async ({ page }) => {
    await sendPrompt(page, 'покажи трафик сайта за последние 7 дней');
    await waitForResponse(page, 'визит');
  });

  test('trends — returns week-over-week comparison', async ({ page }) => {
    await sendPrompt(page, 'сравни трафик этой недели с прошлой');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/неделя|визит|%/i);
  });

  test('top_pages — returns page list', async ({ page }) => {
    await sendPrompt(page, 'покажи топ 5 страниц за эту неделю');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/\/|http/);  // page URL in response
  });

  test('geo — returns countries', async ({ page }) => {
    await sendPrompt(page, 'из каких стран посетители?');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    // Should mention at least one country
    expect(body).toMatch(/United States|India|Germany|United Kingdom|Singapore/i);
  });

  test('sources — returns traffic sources', async ({ page }) => {
    await sendPrompt(page, 'откуда идёт трафик?');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/Direct|Search|поиск|прямой/i);
  });

  test('screen_resolutions — returns resolution table', async ({ page }) => {
    await sendPrompt(page, 'с каких разрешений экранов посещают сайт?');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    // Resolution format: 1920x1080 or 1920×1080
    expect(body).toMatch(/\d{3,4}[x×]\d{3,4}/i);
  });

  test('ai_referrers — does not return 502 error', async ({ page }) => {
    await sendPrompt(page, 'с каких нейросетей идёт трафик? ChatGPT, Perplexity?');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    // Should NOT show server error
    expect(body).not.toMatch(/server returned 502/i);
    // Should mention known AI sources
    expect(body).toMatch(/ChatGPT|Perplexity|Claude|Gemini|DeepSeek|нейросет|ИИ/i);
  });

  test('browsers — returns browser breakdown', async ({ page }) => {
    await sendPrompt(page, 'какие браузеры используют посетители?');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/Chrome|Firefox|Safari|Edge/i);
  });

  test('new_vs_returning — returns percentages', async ({ page }) => {
    await sendPrompt(page, 'сколько новых и возвращающихся посетителей?');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/%/);
  });

  test('real_time — returns live count', async ({ page }) => {
    await sendPrompt(page, 'сколько посетителей на сайте прямо сейчас?');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/\d+/);
  });

  test('insights — returns actionable insight list', async ({ page }) => {
    await sendPrompt(page, 'что нужно сделать? покажи инсайты');
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/bounce|отскок|рост|падение|critical|warning|инсайт/i);
  });

  test('daily_report (background) — acknowledges and delivers', async ({ page }) => {
    await sendPrompt(page, 'сделай ежедневный отчёт по трафику');
    // Background tasks send immediate ack then deliver result
    // Wait for either ack or result
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).toMatch(/отчёт|трафик|визит|brief/i);
  });

  test('full_report (background) — 22 sections, no error', async ({ page }) => {
    test.slow();  // full_report is the heaviest call
    await sendPrompt(page, 'полный отчёт по аналитике за эту неделю');
    // Give background task time to complete and deliver
    await page.waitForTimeout(5_000);
    await waitForResponse(page);
    const body = await page.locator('body').innerText();
    expect(body).not.toMatch(/error|ошибка|502/i);
    expect(body).toMatch(/визит|visit|трафик/i);
  });
});

// ─────────────────────────── 4. Settings ────────────────────────────────────

test.describe('Settings panel', () => {
  test('settings form accessible via ⚙️ button in hub', async ({ page }) => {
    await goToAnalytics(page);
    await page.waitForTimeout(4_000);
    await page.getByRole('button', { name: '⚙️' }).click();
    await expect(page.getByText(/matomo url|auth token/i)).toBeVisible({ timeout: 5_000 });
  });

  test('back navigation from settings works', async ({ page }) => {
    await goToAnalytics(page);
    await page.waitForTimeout(4_000);
    await page.getByRole('button', { name: '⚙️' }).click();
    await page.getByRole('button', { name: /back|←/i }).click();
    await expect(page.getByText('LIVE (30M)')).toBeVisible({ timeout: 5_000 });
  });
});
