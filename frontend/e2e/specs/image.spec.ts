/**
 * ImagePage E2E Tests
 */

import { test, expect } from '@playwright/test'

test.describe('ImagePage', () => {
  test('page loads with upload area', async ({ page }) => {
    await page.goto('/image')
    await page.waitForLoadState('networkidle')

    // Should show header
    await expect(page.locator('h2')).toContainText('识图', { timeout: 5000 })

    // Upload area should be present
    const uploadZone = page.locator('input[type="file"], [class*="upload"]')
    await expect(uploadZone.first()).toBeVisible({ timeout: 5000 })
  })

  test('dark mode works on image page', async ({ page }) => {
    await page.goto('/image')
    await page.waitForLoadState('networkidle')

    await page.locator('.theme-toggle').click()

    const hasDark = await page.evaluate(() =>
      document.documentElement.classList.contains('dark')
    )
    expect(hasDark).toBe(true)
  })
})
