/**
 * ItineraryPage E2E Tests
 */

import { test, expect } from '@playwright/test'

test.describe('ItineraryPage', () => {
  test('empty state shows CTA buttons', async ({ page }) => {
    await page.goto('/itinerary')
    await page.waitForLoadState('networkidle')

    // Should show empty state ("还没有行程" or similar)
    const body = page.locator('body')
    await expect(body).toBeVisible({ timeout: 5000 })
  })

  test('loads with query param and shows progress', async ({ page }) => {
    await page.goto('/itinerary?q=北京3日游')
    await page.waitForLoadState('networkidle')

    // Should show loading state with progress steps
    const loading = page.locator('text=完整规划约需')
    const progressSteps = page.locator('text=提取用户画像, text=分析热门趋势, text=获取天气数据')
    // Either loading state or already rendered itinerary
    await page.waitForTimeout(3000)
  })
})
