/**
 * Auth setup — logs in once, saves session to .auth/state.json.
 * Subsequent tests reuse the session without re-logging.
 *
 * Usage:
 *   IMPERAL_EMAIL=alex.c@webhostmost.com IMPERAL_PASSWORD=... \
 *     npx playwright test --config=playwright.config.ts
 */
import { test as setup, expect } from '@playwright/test';
import path from 'path';

const STATE_FILE = path.join(__dirname, '.auth/state.json');

setup('authenticate', async ({ page }) => {
  const email    = process.env.IMPERAL_EMAIL    || 'alex.c@webhostmost.com';
  const password = process.env.IMPERAL_PASSWORD || '';

  if (!password) {
    throw new Error('Set IMPERAL_PASSWORD env var before running e2e tests.');
  }

  await page.goto('/');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in|log in|login/i }).click();

  // Wait until we land somewhere authenticated (not the login page)
  await expect(page).not.toHaveURL(/login|signin/, { timeout: 15_000 });

  await page.context().storageState({ path: STATE_FILE });
});
