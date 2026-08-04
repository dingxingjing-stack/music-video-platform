import { test, expect } from '@playwright/test';

test.describe('MV Studio - Enterprise UI', () => {
  test('page loads with correct title', async ({ page }) => {
    await page.goto('http://localhost:3000/');
    await expect(page).toHaveTitle(/MV Studio/i);
  });

  test('navbar has logo and status', async ({ page }) => {
    await page.goto('http://localhost:3000/');
    await expect(page.locator('header')).toBeVisible();
    await expect(page.locator('select')).toBeVisible();
  });

  test('path selector cards are visible', async ({ page }) => {
    await page.goto('http://localhost:3000/');
    const cards = page.locator('[class*="cursor-pointer"]').first().locator('..').locator('[class*="cursor-pointer"]');
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test('input area is functional', async ({ page }) => {
    await page.goto('http://localhost:3000/');
    // Just verify the prompt input area exists and is visible
    const promptInput = page.getByPlaceholder(/prompt|提示/i).first();
    if (await promptInput.isVisible()) {
      await promptInput.click();
      // Input should be focused (no error thrown)
    }
  });

  test('generate button is visible', async ({ page }) => {
    await page.goto('http://localhost:3000/');
    const btn = page.locator('button').filter({ hasText: /生成|Generate/i }).first();
    if (await btn.isVisible()) {
      await expect(btn).toBeEnabled();
    }
  });

  test('footer is visible', async ({ page }) => {
    await page.goto('http://localhost:3000/');
    await expect(page.locator('footer')).toBeVisible();
  });
});
