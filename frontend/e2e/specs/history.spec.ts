/**
 * HistoryPage E2E Tests
 */

import { test, expect } from '@playwright/test'

test.describe('HistoryPage', () => {
  test('page loads and shows header', async ({ page }) => {
    await page.goto('/history')
    await page.waitForLoadState('networkidle')

    // Should show the page header
    await expect(page.locator('h2')).toContainText('行程', { timeout: 5000 })
  })

  test('dark mode works on history page', async ({ page }) => {
    await page.goto('/history')
    await page.waitForLoadState('networkidle')

    await page.locator('.theme-toggle').click()

    const hasDark = await page.evaluate(() =>
      document.documentElement.classList.contains('dark')
    )
    expect(hasDark).toBe(true)
  })
})
