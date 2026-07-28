/**
 * HomePage E2E Tests
 */

import { test, expect } from '@playwright/test'

test.describe('HomePage', () => {
  test('page loads with hero and navigation', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Title should be visible
    await expect(page.locator('h1, h2').first()).toBeVisible({ timeout: 5000 })

    // Quick navigation cards should exist
    const navLinks = page.locator('a[href^="/"]')
    const count = await navLinks.count()
    expect(count).toBeGreaterThanOrEqual(4)

    // Theme toggle should exist
    await expect(page.locator('.theme-toggle')).toBeVisible()
  })

  test('example questions are shown', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Example question chips should be visible
    const examples = page.locator('button:has-text("北京"), button:has-text("成都"), button:has-text("推荐")')
    const count = await examples.count()
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('dark mode toggle works on homepage', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    await page.locator('.theme-toggle').click()

    const hasDark = await page.evaluate(() =>
      document.documentElement.classList.contains('dark')
    )
    expect(hasDark).toBe(true)
  })
})
