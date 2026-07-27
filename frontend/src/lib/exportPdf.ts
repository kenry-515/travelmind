/**
 * TravelMind Agent — PDF Export (Phase 10)
 *
 * Converts a TravelItinerary to a downloadable PDF using html2canvas + jspdf.
 * Pure frontend — no backend API needed.
 */

import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import type { TravelItinerary, WeatherForecast } from './api'

/** Escape text for safe interpolation into inline HTML. */
function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** Render the itinerary as a styled HTML string suitable for html2canvas. */
function renderItineraryHtml(
  itinerary: TravelItinerary,
  weather: WeatherForecast | null
): string {
  const { trip, days, budget, checklist, tips } = itinerary

  const statsHtml = trip.stats
    .map(
      (s) =>
        `<div style="text-align:center;padding:8px 12px;background:#f8fafc;border-radius:8px;min-width:80px">
          <p style="font-size:16px;font-weight:bold;color:#1e293b;margin:0">${esc(s.value)}</p>
          <p style="font-size:10px;color:#94a3b8;margin:2px 0 0">${esc(s.label)}</p>
        </div>`
    )
    .join('')

  const weatherHtml = weather
    ? `<div style="margin-top:12px;padding:10px;background:#eff6ff;border-radius:8px">
        <p style="font-size:12px;font-weight:600;color:#1e40af;margin:0 0 8px">
          🌤️ 天气参考 (${esc(weather.city)})
        </p>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          ${weather.daily
            .slice(0, 5)
            .map(
              (d) =>
                `<div style="padding:6px 10px;background:#fff;border-radius:6px;text-align:center;font-size:10px">
                  <p style="font-weight:600;color:#334155;margin:0">${d.date.slice(5)}</p>
                  <p style="color:#64748b;margin:2px 0 0">${esc(d.weather_desc)}</p>
                  <p style="color:#94a3b8;margin:1px 0 0">${d.temp_min.toFixed(0)}~${d.temp_max.toFixed(0)}°C</p>
                </div>`
            )
            .join('')}
        </div>
      </div>`
    : ''

  const daysHtml = days
    .map(
      (day) =>
        `<div style="margin-bottom:16px;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:12px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #f1f5f9">
            <span style="display:flex;align-items:center;justify-content:center;width:36px;height:36px;background:#dbeafe;border-radius:50%;font-size:16px;font-weight:bold;color:#2563eb">${day.day}</span>
            <div>
              <p style="font-size:14px;font-weight:600;color:#1e293b;margin:0">${esc(day.title)}</p>
              <p style="font-size:11px;color:#94a3b8;margin:2px 0 0">${esc(day.theme)}</p>
            </div>
          </div>
          ${day.items
            .map(
              (item) =>
                `<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;padding:10px;background:#f8fafc;border-radius:8px">
                  <p style="font-size:11px;font-weight:600;color:#2563eb;margin:0;min-width:40px">${esc(item.time)}</p>
                  <div>
                    <p style="font-size:13px;font-weight:500;color:#1e293b;margin:0">${esc(item.poi)}</p>
                    <p style="font-size:11px;color:#64748b;margin:4px 0 0;line-height:1.4">${esc(item.note)}</p>
                  </div>
                </div>`
            )
            .join('')}
          <p style="font-size:11px;color:#d97706;margin:8px 0 0;padding-top:8px;border-top:1px solid #fef3c7">
            🍜 每日一味：${esc(day.eat)}
          </p>
        </div>`
    )
    .join('')

  const budgetHtml =
    budget.length > 0
      ? `<div style="margin-top:16px;padding:12px;background:#f0fdf4;border-radius:8px">
          <p style="font-size:12px;font-weight:600;color:#166534;margin:0 0 8px">💳 预算分配（人均）</p>
          ${budget
            .map(
              (b) =>
                `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                  <span style="font-size:11px;font-weight:500;color:#334155">${esc(b.label)}</span>
                  <span style="font-size:11px;color:#64748b">¥${b.amount} · ${b.percent}%</span>
                </div>
                <div style="height:6px;background:#e2e8f0;border-radius:3px;margin-bottom:8px">
                  <div style="height:6px;width:${Math.min(b.percent, 100)}%;background:#22c55e;border-radius:3px"></div>
                </div>`
            )
            .join('')}
        </div>`
      : ''

  const checklistHtml =
    checklist.length > 0
      ? `<div style="margin-top:16px;padding:12px;background:#eff6ff;border-radius:8px">
          <p style="font-size:12px;font-weight:600;color:#1e40af;margin:0 0 8px">✅ 行前清单</p>
          ${checklist
            .map(
              (item, i) =>
                `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:11px;color:#334155">
                  <span style="display:flex;align-items:center;justify-content:center;width:18px;height:18px;border:1px solid #cbd5e1;border-radius:4px;font-size:10px">${i + 1}</span>
                  ${esc(item.text)}
                </div>`
            )
            .join('')}
        </div>`
      : ''

  const tipsHtml =
    tips.length > 0
      ? `<div style="margin-top:16px;padding:12px;background:#fffbeb;border-radius:8px">
          <p style="font-size:12px;font-weight:600;color:#92400e;margin:0 0 8px">💡 实用提示</p>
          ${tips
            .map(
              (tip) =>
                `<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 10px;background:#fff;border-radius:20px;font-size:10px;color:#92400e">${esc(tip)}</span>`
            )
            .join('')}
        </div>`
      : ''

  return `
    <div style="width:720px;padding:24px;font-family:'Microsoft YaHei','PingFang SC',sans-serif;background:#f8fafc;color:#1e293b">
      <!-- Header -->
      <div style="text-align:center;margin-bottom:20px">
        <h1 style="font-size:22px;font-weight:bold;color:#0f172a;margin:0">${esc(trip.title)}</h1>
        <p style="font-size:12px;color:#64748b;margin:6px 0 0">
          ${esc(trip.city)} · ${esc(trip.dateStart)} — ${esc(trip.dateEnd)} · ${trip.daysCount} 天行程
        </p>
      </div>

      <!-- Stats -->
      <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:16px">
        ${statsHtml}
      </div>

      ${weatherHtml}

      <!-- Days -->
      <div style="margin-top:16px">
        ${daysHtml}
      </div>

      ${budgetHtml}
      ${checklistHtml}
      ${tipsHtml}

      <!-- Footer -->
      <p style="text-align:center;font-size:10px;color:#cbd5e1;margin-top:24px">
        TravelMind Agent 生成 · ${new Date().toLocaleDateString('zh-CN')}
      </p>
    </div>
  `
}

/** Export the given itinerary to a PDF file and trigger download. */
export async function exportItineraryPdf(
  itinerary: TravelItinerary,
  weather: WeatherForecast | null
): Promise<void> {
  // Defensive check: ensure required arrays exist
  if (!Array.isArray(itinerary?.trip?.stats) || !Array.isArray(itinerary?.days)) {
    throw new Error('Invalid itinerary structure: missing trip.stats or days')
  }

  const html = renderItineraryHtml(itinerary, weather)

  // Create off-screen div, render html, capture to canvas
  const container = document.createElement('div')
  container.style.position = 'absolute'
  container.style.left = '-9999px'
  container.style.top = '0'
  container.style.width = '720px'
  container.innerHTML = html
  document.body.appendChild(container)

  try {
    const element = container.firstChild as HTMLElement | null
    if (!element) throw new Error('Failed to render itinerary HTML')
    const canvas = await html2canvas(element, {
      scale: 2, // retina quality
      useCORS: true,
      backgroundColor: '#f8fafc',
    })

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF('p', 'mm', 'a4')
    // jsPDF v4: pageSize exposes .width/.height as direct properties
    // (getWidth()/getHeight() were removed in v4)
    const pageWidth: number =
      typeof pdf.internal.pageSize.width === 'number'
        ? pdf.internal.pageSize.width
        : (pdf.internal.pageSize as unknown as { getWidth(): number }).getWidth()
    const pageHeight: number =
      typeof pdf.internal.pageSize.height === 'number'
        ? pdf.internal.pageSize.height
        : (pdf.internal.pageSize as unknown as { getHeight(): number }).getHeight()
    const imgWidth = pageWidth - 16 // 8mm margins
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    let heightLeft = imgHeight
    let position = 8 // top margin

    // Add first page
    pdf.addImage(imgData, 'PNG', 8, position, imgWidth, imgHeight)
    heightLeft -= pageHeight - 16

    // Add additional pages if content overflows
    while (heightLeft > 0) {
      position = 8 - (imgHeight - heightLeft)
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 8, position, imgWidth, imgHeight)
      heightLeft -= pageHeight - 16
    }

    const fileName = `${itinerary.trip.city}_${itinerary.trip.daysCount}天行程.pdf`
    pdf.save(fileName)
  } finally {
    document.body.removeChild(container)
  }
}
