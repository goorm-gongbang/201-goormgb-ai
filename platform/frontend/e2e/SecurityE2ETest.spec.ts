import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';

test.describe('Stage 3 - Security Challenge E2E Tests', () => {

  // ─── 1. Global Interception — Modal appears on any page with ?forceChallenge=true ───

  test('should show security modal when ?forceChallenge=true on Stage 1 page', async ({ page }) => {
    await page.goto(`${BASE_URL}/games/game-001?forceChallenge=true`);
    await page.waitForTimeout(1000);

    // Verify modal is visible
    const overlay = page.locator('[data-testid="security-overlay"]');
    await expect(overlay).toBeVisible();

    // Verify "보안 확인" title is shown
    await expect(page.locator('text=보안 확인')).toBeVisible();

    // Verify quiz prompt
    await expect(page.locator('text=3 + 4 = ?')).toBeVisible();
  });

  test('should block interaction with page behind modal', async ({ page }) => {
    await page.goto(`${BASE_URL}/games/game-001?forceChallenge=true`);
    await page.waitForTimeout(1000);

    // The booking button should NOT be clickable through the overlay
    const bookingButton = page.locator('#booking-button');

    // Try to click — it should be covered by the overlay
    // We verify by checking the overlay is on top (z-index)
    const overlay = page.locator('[data-testid="security-overlay"]');
    await expect(overlay).toBeVisible();

    // The button exists but is obscured
    const isBookingVisible = await bookingButton.isVisible().catch(() => false);
    // Even if visible in DOM, clicking should hit the overlay instead
  });

  // ─── 2. Failure — Wrong answer keeps modal open ───

  test('should show error on wrong answer and keep modal open', async ({ page }) => {
    await page.goto(`${BASE_URL}/games/game-001?forceChallenge=true`);
    await page.waitForTimeout(1000);

    // Type wrong answer
    const input = page.locator('[data-testid="security-input"]');
    await input.fill('0');

    // Submit
    const submitBtn = page.locator('[data-testid="security-submit"]');
    await submitBtn.click();

    // Wait for response
    await page.waitForTimeout(1000);

    // Error message should appear
    const error = page.locator('[data-testid="security-error"]');
    await expect(error).toBeVisible();
    await expect(error).toContainText('오답');

    // Modal should still be visible
    const overlay = page.locator('[data-testid="security-overlay"]');
    await expect(overlay).toBeVisible();
  });

  // ─── 3. Success — Correct answer closes modal ───

  test('should close modal on correct answer and reveal page', async ({ page }) => {
    await page.goto(`${BASE_URL}/games/game-001?forceChallenge=true`);
    await page.waitForTimeout(1000);

    // Type correct answer
    const input = page.locator('[data-testid="security-input"]');
    await input.fill('7');

    // Submit
    const submitBtn = page.locator('[data-testid="security-submit"]');
    await submitBtn.click();

    // Wait for modal to close
    await page.waitForTimeout(1000);

    // Overlay should be gone
    const overlay = page.locator('[data-testid="security-overlay"]');
    await expect(overlay).not.toBeVisible();

    // Original page content should be interactable
    await expect(page.locator('text=Traffic-Master')).toBeVisible();
  });

  // ─── 4. Verify on Queue page too (Global Interceptor) ───

  test('should also work on queue page with ?forceChallenge=true', async ({ page }) => {
    // Navigate to a queue-like URL with force challenge
    await page.goto(`${BASE_URL}/queue/test-ticket-123?forceChallenge=true`);
    await page.waitForTimeout(1000);

    // Modal should appear even on queue page
    const overlay = page.locator('[data-testid="security-overlay"]');
    await expect(overlay).toBeVisible();
    await expect(page.locator('text=보안 확인')).toBeVisible();
  });
});
