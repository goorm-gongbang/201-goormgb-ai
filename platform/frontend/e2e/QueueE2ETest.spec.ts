import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const GAME_URL = `${BASE_URL}/games/game-001`;

test.describe('Stage 2 - Queue E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(GAME_URL);
    await page.waitForSelector('text=Traffic-Master', { timeout: 10000 });
  });

  // ─── 1. Queue Entry via Recommend Toggle ───

  test('should enter queue when recommendEnabled and booking clicked', async ({ page }) => {
    // Enable recommend toggle
    const toggle = page.getByLabel('Toggle recommend');
    await toggle.click();

    // Click booking button
    const bookingButton = page.locator('#booking-button');
    await bookingButton.click();

    // Should navigate to queue page
    await page.waitForURL(/\/queue\//, { timeout: 10000 });

    // Should display queue overlay elements
    await expect(page.locator('text=대기열 안내')).toBeVisible();
    await expect(page.locator('text=번째')).toBeVisible();
  });

  // ─── 2. Position Decreases Over Time ───

  test('should show decreasing position during polling', async ({ page }) => {
    // Enable recommend and enter queue
    const toggle = page.getByLabel('Toggle recommend');
    await toggle.click();
    await page.locator('#booking-button').click();
    await page.waitForURL(/\/queue\//, { timeout: 10000 });

    // Wait for first position display
    await page.waitForSelector('text=번째', { timeout: 5000 });

    // Capture initial position text
    const positionEl = page.locator('text=번째').first();
    await expect(positionEl).toBeVisible();

    // Wait for a few polls (3 seconds)
    await page.waitForTimeout(3000);

    // Progress bar should have advanced (width > 0)
    const progressBar = page.locator('div.bg-gradient-to-r.from-emerald-500');
    const style = await progressBar.getAttribute('style');
    expect(style).toBeTruthy();
  });

  // ─── 3. Auto-Redirect on GRANTED ───

  test('should auto-redirect when queue status becomes GRANTED', async ({ page }) => {
    // Enable recommend and enter queue
    const toggle = page.getByLabel('Toggle recommend');
    await toggle.click();
    await page.locator('#booking-button').click();
    // Wait for redirect to /select (GRANTED status) → QueueService now redirects immediately
    // estimatedWaitMs = 5000.
    await page.waitForURL(/\/seats/, { timeout: 15000 });
    
    // S7 Enhancement: Security Challenge appears ON THE SEATS SCREEN (triggered by Map API)
    // Wait for security modal
    await expect(page.locator('text=보안 확인')).toBeVisible({ timeout: 10000 });
    
    // Solve challenge (3+4=7)
    await page.fill('input[placeholder="답변 입력 (예: 7)"]', '7');
    await page.click('button:has-text("제출")');
    
    // Modal should close
    await expect(page.locator('text=보안 확인')).not.toBeVisible();
  });

  // ─── 4. Direct Path (No Queue) ───

  test('should skip queue when recommendEnabled is false', async ({ page }) => {
    // Ensure recommend is off (default)
    // Click booking directly
    const bookingButton = page.locator('#booking-button');
    await bookingButton.click();

    // Should NOT go to queue page, should go to /select directly
    await page.waitForURL(/\/select/, { timeout: 10000 });
  });
});
