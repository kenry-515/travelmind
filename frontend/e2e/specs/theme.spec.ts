/**
 * Dark Mode & Theme Tests
 *
 * Verifies dark mode toggle works on every page,
 * and that .glass elements are NOT white in dark mode.
 * This catches the exact bug from Phase 12.29 post-commit.
 */

import { test, expect } from '@playwright/test'

const PAGES = [
  { name: 'Home', path: '/' },
  { name: 'Chat', path: '/chat' },
  { name: 'Recommend', path: '/recommend' },
  { name: 'Itinerary', path: '/itinerary' },
  { name: 'Image', path: '/image' },
  { name: 'History', path: '/history' },
] as const

test.describe('Dark Mode', () => {
  test.beforeEach(async ({ page }) => {
    // Start in light mode
    await page.evaluate(() => localStorage.setItem('travelmind-theme', 'light'))
  })

  for (const { name, path } of PAGES) {
    test(`${name} page — toggle dark mode`, async ({ page }) => {
      await page.goto(path)
      await page.waitForLoadState('networkidle')

      // Initially light mode — .dark should NOT be present
      const hasDarkBefore = await page.evaluate(() =>
        document.documentElement.classList.contains('dark')
      )
      expect(hasDarkBefore).toBe(false)

      // Click the theme toggle button
      const toggle = page.locator('.theme-toggle')
      await expect(toggle).toBeVisible({ timeout: 5000 })
      await toggle.click()

      // Verify .dark class is applied
      const hasDarkAfter = await page.evaluate(() =>
        document.documentElement.classList.contains('dark')
      )
      expect(hasDarkAfter).toBe(true)

      // Verify localStorage was updated
      const stored = await page.evaluate(() =>
        localStorage.getItem('travelmind-theme')
      )
      expect(stored).toBe('dark')

      // Check .glass elements are NOT white in dark mode
      const glassBg = await page.evaluate(() => {
        const el = document.querySelector('.glass')
        if (!el) return 'no-glass-element'
        return window.getComputedStyle(el).backgroundColor
      })
      // Should NOT be white (rgb(255, 255, 255) or rgba(255, 255, 255, ...))
      expect(glassBg).not.toMatch(/^rgba?\(255,\s*255,\s*255/)
      // Should contain a dark color (slate-800 equivalent)
      expect(glassBg).toMatch(/\d+/)
    })
  }

  test('persists dark mode across page reload', async ({ page }) => {
    await page.goto('/')
    await page.locator('.theme-toggle').click()
    await page.reload()
    await page.waitForLoadState('networkidle')
    const hasDark = await page.evaluate(() =>
      document.documentElement.classList.contains('dark')
    )
    expect(hasDark).toBe(true)
  })

  test('toggle back to light mode', async ({ page }) => {
    await page.goto('/')
    // Toggle to dark
    await page.locator('.theme-toggle').click()
    // Toggle back to light
    await page.locator('.theme-toggle').click()
    const hasDark = await page.evaluate(() =>
      document.documentElement.classList.contains('dark')
    )
    expect(hasDark).toBe(false)
    const stored = await page.evaluate(() =>
      localStorage.getItem('travelmind-theme')
    )
    expect(stored).toBe('light')
  })
})
