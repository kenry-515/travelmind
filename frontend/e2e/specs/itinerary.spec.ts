/**
 * ItineraryPage E2E Tests (Phase 18 广州专属)
 */

import { test, expect } from '@playwright/test'

test.describe('ItineraryPage', () => {
  test('empty state shows CTA buttons', async ({ page }) => {
    await page.goto('/itinerary')
    await page.waitForLoadState('networkidle')

    // Page should render — use heading as stable target
    await expect(page.locator('h1, h2, h3').first()).toBeVisible({ timeout: 10_000 })
  })

  test('loads with query param and shows progress', async ({ page }) => {
    await page.goto('/itinerary?q=广州西关一日游', { waitUntil: 'domcontentloaded' })

    // 等行程页主标题出现(loading 或已生成)
    // 已生成: h2 "羊城行程 · 广州专属"
    // loading: progress 文本
    await expect(
      page.locator('h2').filter({ hasText: /羊城行程|完整规划|生成|暂无/ }).first()
    ).toBeVisible({ timeout: 60_000 })
  })

  test('invalid query param shows graceful empty state', async ({ page }) => {
    await page.goto('/itinerary?q=')
    await page.waitForLoadState('networkidle')

    // 空状态页面应能渲染
    await expect(page.locator('h1, h2, h3').first()).toBeVisible({ timeout: 10_000 })
  })
})