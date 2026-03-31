import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const GAME_URL = `${BASE_URL}/games/game-001`;

test.describe('Stage 1 - PRE_ENTRY E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to game detail page
    await page.goto(GAME_URL);
    // Wait for the page to load
    await page.waitForSelector('text=Traffic-Master', { timeout: 10000 });
  });

  // ─── 1. State Persistence ───

  test('should persist partySize across page reload', async ({ page }) => {
    // Change party size to 5
    const select = page.locator('select');
    await select.selectOption('5');

    // Verify selection
    await expect(select).toHaveValue('5');

    // Reload the page
    await page.reload();
    await page.waitForSelector('text=Traffic-Master', { timeout: 10000 });

    // Verify party size is still 5 after reload
    const selectAfter = page.locator('select');
    await expect(selectAfter).toHaveValue('5');
  });

  test('should persist recommendEnabled toggle across reload', async ({ page }) => {
    // Click recommend toggle (initially off)
    const toggle = page.getByLabel('Toggle recommend');
    await toggle.click();

    // Reload
    await page.reload();
    await page.waitForSelector('text=Traffic-Master', { timeout: 10000 });

    // Verify toggle state persisted (check classList for bg-emerald-500)
    const toggleAfter = page.getByLabel('Toggle recommend');
    await expect(toggleAfter).toHaveClass(/bg-emerald-500/);
  });

  // ─── 2. Validation Constraints ───

  test('partySize dropdown should only contain values 1-10', async ({ page }) => {
    const options = page.locator('select option');
    const count = await options.count();

    expect(count).toBe(10);

    // Verify first and last values
    await expect(options.first()).toHaveValue('1');
    await expect(options.last()).toHaveValue('10');
  });

  test('price filter should show slider when enabled', async ({ page }) => {
    // Price slider should not be visible initially
    const slider = page.locator('input[type="range"]').first();
    await expect(slider).not.toBeVisible();

    // Toggle price filter on
    const priceToggle = page.getByLabel('Toggle price filter');
    await priceToggle.click();

    // Now slider should be visible
    await expect(page.locator('input[type="range"]').first()).toBeVisible();
  });

  // ─── 3. UI Rendering ───

  test('should display game information correctly', async ({ page }) => {
    // Check that game info is rendered
    await expect(page.locator('text=경기 정보')).toBeVisible();
    await expect(page.locator('text=가격표')).toBeVisible();
    await expect(page.locator('text=VS')).toBeVisible();
  });

  test('should display price table tab content', async ({ page }) => {
    // Click on price table tab
    await page.click('text=가격표');

    // Verify price table is visible
    await expect(page.locator('text=좌석 등급')).toBeVisible();
    await expect(page.locator('text=가격')).toBeVisible();
  });

  // ─── 4. Booking Flow ───

  test('booking button should be enabled when sale status is ON_SALE', async ({ page }) => {
    const bookingButton = page.locator('#booking-button');
    await expect(bookingButton).toBeEnabled();
    await expect(bookingButton).toContainText('예매하기');
  });

  test('should create TM_SESSION_ID in localStorage on page load', async ({ page }) => {
    const sessionId = await page.evaluate(() => localStorage.getItem('TM_SESSION_ID'));
    expect(sessionId).toBeTruthy();
    // Should be a valid UUID format
    expect(sessionId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    );
  });

  test('should save preferences to TM_PREFERENCES in localStorage', async ({ page }) => {
    // Change party size
    await page.locator('select').selectOption('7');

    // Check localStorage
    const stored = await page.evaluate(() => localStorage.getItem('TM_PREFERENCES'));
    expect(stored).toBeTruthy();

    const prefs = JSON.parse(stored!);
    expect(prefs.partySize).toBe(7);
  });
});
