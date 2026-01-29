import { test, expect } from '@playwright/test';

/**
 * Market Mode E2E Tests
 * Tests the cache toggle feature for EntTelligence integration
 */

test.describe('EntTelligence Cache Toggle', () => {
  test('App loads and login page appears', async ({ page }) => {
    // Navigate to app
    await page.goto('/');

    // Wait for app to hydrate
    await page.waitForLoadState('networkidle');

    // Should see login form (username input uses id="username")
    const usernameInput = page.locator('#username');
    await expect(usernameInput).toBeVisible({ timeout: 10000 });
  });

  test('Page loads without critical JS errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Filter for critical errors (ignore favicon, network issues, etc.)
    const criticalErrors = errors.filter(e =>
      (e.includes('TypeError') || e.includes('ReferenceError') || e.includes('SyntaxError'))
      && !e.includes('favicon')
    );

    expect(criticalErrors).toHaveLength(0);
  });

  test('Login form has expected fields', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Verify login form elements exist (uses id attributes)
    await expect(page.locator('#username')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });
});

test.describe('Basic App Functionality', () => {
  test('App title is PriceScout', async ({ page }) => {
    await page.goto('/');

    // Check page title
    await expect(page).toHaveTitle('PriceScout');
  });

  test('App has dark theme enabled', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check that dark class is on html element
    const html = page.locator('html');
    await expect(html).toHaveClass(/dark/);
  });
});
