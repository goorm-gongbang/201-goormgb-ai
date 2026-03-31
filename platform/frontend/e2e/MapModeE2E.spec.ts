import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';

test.describe('Stage 5 - MAP Mode E2E Tests', () => {

  test('should render MAP mode layout when mode=MAP', async ({ page }) => {
    await page.goto(`${BASE_URL}/seats?mode=MAP`);
    await page.waitForTimeout(1500);

    await expect(page.locator('text=맵 모드')).toBeVisible();
    await expect(page.locator('text=구역 선택')).toBeVisible();
    await expect(page.locator('text=좌측에서 구역을 선택해주세요')).toBeVisible();
  });

  test('should load zones with accordion groups', async ({ page }) => {
    await page.goto(`${BASE_URL}/seats?mode=MAP`);
    await page.waitForTimeout(1500);

    // Floor groups should be visible
    await expect(page.locator('text=1층')).toBeVisible();

    // Zone items should be visible under expanded group
    const zoneItems = page.locator('button:has-text("구역")');
    const count = await zoneItems.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should show seat grid when zone is selected', async ({ page }) => {
    await page.goto(`${BASE_URL}/seats?mode=MAP`);
    await page.waitForTimeout(1500);

    // Click first available zone (not disabled)
    const availableZone = page.locator('button:has-text("구역"):not([disabled])').first();
    await availableZone.click();
    await page.waitForTimeout(1000);

    // Grid should appear
    await expect(page.locator('text=좌석 배치도')).toBeVisible();
    await expect(page.locator('text=FIELD')).toBeVisible();
  });

  test('should prevent selecting more seats than partySize', async ({ page }) => {
    await page.goto(`${BASE_URL}/seats?mode=MAP`);
    await page.waitForTimeout(1500);

    // Select a zone
    const availableZone = page.locator('button:has-text("구역"):not([disabled])').first();
    await availableZone.click();
    await page.waitForTimeout(1000);

    // Party size is default 2 — click 3 available seats (○)
    const availableSeats = page.locator('button:has-text("○")');
    const total = await availableSeats.count();
    expect(total).toBeGreaterThan(2);

    // Click first 3 seats
    await availableSeats.nth(0).click();
    await availableSeats.nth(1).click();
    await availableSeats.nth(2).click();
    await page.waitForTimeout(500);

    // Only 2 should be selected (partySize limit)
    const selectedCount = page.locator('text=선택한 좌석 (2/2)');
    await expect(selectedCount).toBeVisible();
  });

  test('should not allow clicking held/unavailable seats', async ({ page }) => {
    await page.goto(`${BASE_URL}/seats?mode=MAP`);
    await page.waitForTimeout(1500);

    // Select a zone
    const availableZone = page.locator('button:has-text("구역"):not([disabled])').first();
    await availableZone.click();
    await page.waitForTimeout(1000);

    // Held seats (×) and unavailable seats (·) should be disabled
    const heldSeat = page.locator('button:has-text("×")').first();
    if (await heldSeat.count() > 0) {
      await expect(heldSeat).toBeDisabled();
    }

    const unavailSeat = page.locator('button:has-text("·")').first();
    if (await unavailSeat.count() > 0) {
      await expect(unavailSeat).toBeDisabled();
    }
  });

  test('booking button disabled until partySize seats selected', async ({ page }) => {
    await page.goto(`${BASE_URL}/seats?mode=MAP`);
    await page.waitForTimeout(1500);

    // Booking button should be disabled initially
    const bookBtn = page.locator('#booking-button-map');
    await expect(bookBtn).toBeDisabled();

    // Select a zone and seats
    const availableZone = page.locator('button:has-text("구역"):not([disabled])').first();
    await availableZone.click();
    await page.waitForTimeout(1000);

    // Select 2 seats
    const availableSeats = page.locator('button:has-text("○")');
    await availableSeats.nth(0).click();
    await availableSeats.nth(1).click();
    await page.waitForTimeout(500);

    // Now button should be enabled
    await expect(bookBtn).toBeEnabled();
  });
});
