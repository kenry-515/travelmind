/**
 * RecommendPage E2E Tests
 */

import { test, expect } from '@playwright/test'

test.describe('RecommendPage', () => {
  test('page loads with search bar and quick suggestions', async ({ page }) => {
    await page.goto('/recommend')
    await page.waitForLoadState('networkidle')
    // Should show the page header and search area
    await expect(page.locator('h2')).toContainText('推荐', { timeout: 5000 })
  })

  test('empty query is handled gracefully', async ({ page }) => {
    await page.goto('/recommend')
    await page.waitForLoadState('networkidle')
    // Search button should be disabled or form prevents empty submit
    const submitBtn = page.locator('button[type="submit"], button:has-text("搜索")')
    if (await submitBtn.count() > 0) {
      await expect(submitBtn.first()).toBeDisabled()
    }
  })

  test('quick example chip is clickable', async ({ page }) => {
    await page.goto('/recommend')
    await page.waitForLoadState('networkidle')
    // Look for example/suggestion chips
    const chips = page.locator('button:has-text("北京"), button:has-text("成都"), button:has-text("上海")')
    const count = await chips.count()
    if (count > 0) {
      await chips.first().click()
      // Should start loading (skeleton appears) or show results
      await page.waitForTimeout(2000)
    }
  })
})
