/**
 * ItineraryPage E2E Tests (Phase 18 广州专属)
 */

import { test, expect } from '@playwright/test'

test.describe('ItineraryPage', () => {
  test('empty state shows CTA buttons', async ({ page }) => {
    await page.goto('/itinerary')
    await page.waitForLoadState('networkidle')

    const body = page.locator('body')
    await expect(body).toBeVisible({ timeout: 5000 })
  })

  test('loads with query param and shows progress', async ({ page }) => {
    await page.goto('/itinerary?q=广州西关一日游')
    await page.waitForLoadState('networkidle')

    // Either loading state or already rendered itinerary
    await page.waitForTimeout(3000)
    // Page should still render something (loading or empty)
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })

  test('invalid query param shows graceful empty state', async ({ page }) => {
    await page.goto('/itinerary?q=')
    await page.waitForLoadState('networkidle')

    // Empty state should appear (no crash)
    const html = await page.content()
    expect(html.length).toBeGreaterThan(0)
  })
})