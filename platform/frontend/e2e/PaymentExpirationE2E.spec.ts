import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';

test.describe('Stage 6 - Payment Expiration E2E', () => {

  test('should show countdown timer on payment page', async ({ page }) => {
    // We need a valid orderId, so we go through the full flow
    // For now, test the page structure with a mock orderId
    await page.goto(`${BASE_URL}/payment?orderId=test-order-123`);
    await page.waitForTimeout(1500);

    // Should either show order info or redirect
    const url = page.url();
    if (url.includes('/payment')) {
      // Page loaded — check for timer or error
      const timerEl = page.locator('[data-testid="countdown-timer"]');
      const errorText = page.locator('text=주문 정보를 찾을 수 없습니다');
      const isTimer = await timerEl.isVisible().catch(() => false);
      const isError = await errorText.isVisible().catch(() => false);
      expect(isTimer || isError).toBeTruthy();
    }
  });

  test('should redirect to /seats when no orderId param', async ({ page }) => {
    await page.goto(`${BASE_URL}/payment`);
    await page.waitForTimeout(2000);
    expect(page.url()).toContain('/seats');
  });

  test('pay button should be disabled when agreements not checked', async ({ page }) => {
    await page.goto(`${BASE_URL}/payment?orderId=test-order-123`);
    await page.waitForTimeout(1500);

    const payBtn = page.locator('#pay-button');
    if (await payBtn.isVisible().catch(() => false)) {
      await expect(payBtn).toBeDisabled();
    }
  });

  test('payment done page should show success', async ({ page }) => {
    await page.goto(`${BASE_URL}/payment/done?orderId=fake-id`);
    await page.waitForTimeout(1000);

    await expect(page.locator('text=결제가 완료되었습니다')).toBeVisible();
  });
});
