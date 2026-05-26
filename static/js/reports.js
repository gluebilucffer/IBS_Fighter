import { requestJson } from "./api.js";
import { state } from "./state.js";
import { escapeHtml, formatNumber, shortDate, shortText, today } from "./utils.js";


export async function loadReport(endDate = state.date || today()) {
  const days = state.reportDays || 7;
  const payload = await requestJson(
    `/api/report?module=${encodeURIComponent(state.reportModule)}&days=${encodeURIComponent(days)}&end_date=${encodeURIComponent(endDate)}`,
  );
  state.report = payload;
  renderReport(payload);
}


function renderReport(report) {
  if (!report) return;
  updateReportShell(report);
  if (report.module === "medications") {
    renderMedicationReport(report);
    return;
  }
  renderBowelReport(report);
}


function updateReportShell(report) {
  const moduleLabel = report.module === "medications" ? "用药报表" : "排便报表";
  const rangeNote = report.range.clamped_to_tracking_start
    ? ` · 从 ${report.range.tracking_start_date} 起统计`
    : "";
  document.querySelector("#report-title").textContent = moduleLabel;
  document.querySelector("#report-range").textContent = `${report.range.start_date} 至 ${report.range.end_date}${rangeNote}`;

  document.querySelectorAll("[data-report-module]").forEach((button) => {
    button.classList.toggle("active", button.dataset.reportModule === report.module);
  });
  document.querySelectorAll("[data-report-module-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.reportModulePanel === report.module);
  });
  document.querySelectorAll("[data-report-days]").forEach((button) => {
    const requestedDays = report.range.requested_days ?? report.range.days;
    button.classList.toggle("active", Number(button.dataset.reportDays) === requestedDays);
  });
}


function renderBowelReport(report) {
  const summary = report.summary || {};

  document.querySelector("#report-total-events").textContent = summary.total_events ?? 0;
  document.querySelector("#report-avg-events-day").textContent = summary.avg_events_per_day ?? 0;
  document.querySelector("#report-avg-bristol").textContent = summary.avg_bristol ?? "-";
  document.querySelector("#report-normal-rate").textContent = `${summary.safe_rate ?? summary.normal_rate ?? 0}%`;
  document.querySelector("#report-abnormal-count").textContent = summary.abnormal_count ?? 0;
  document.querySelector("#report-urgent-count").textContent = summary.urgent_count ?? 0;

  renderBristolControlChart(
    "#report-control-chart",
    report.control_points || [],
    report.control_limits || { min: 1, max: 7, safe_min: 4, safe_max: 5 },
  );

  renderBarRows("#report-bowel-chart", report.daily || [], {
    emptyText: "这个周期还没有排便记录",
    label: (row) => shortDate(row.date),
    value: (row) => row.count,
    valueText: (row) => `${row.count} 次 · 均 ${row.avg_bristol ?? "-"}`,
    meta: (row) => dailyMetaText(row),
  });

  renderBarRows("#report-bristol-chart", report.bristol_distribution || [], {
    emptyText: "还没有布里斯托等级数据",
    label: (row) => String(row.type),
    value: (row) => row.count,
    valueText: (row) => `${row.count} 次 · ${row.rate}%`,
    meta: (row) => row.label.replace(`${row.type} `, ""),
  });

  renderBarRows("#report-quality-chart", report.quality_distribution || [], {
    emptyText: "还没有可归类的排便记录",
    label: (row) => row.label,
    value: (row) => row.count,
    valueText: (row) => `${row.count} 次`,
  });

  renderRankList("#report-color-list", report.color_distribution || [], {
    emptyText: "暂无颜色记录",
    valueText: (row) => `${row.count} 次`,
  });

  renderRankList("#report-location-list", report.location_distribution || [], {
    emptyText: "暂无地点记录",
    valueText: (row) => `${row.count} 次`,
  });

  renderNoRecordDays(report.no_record_dates || [], report.range.days);
  renderAttentionDays(report.attention_days || []);
  renderInsights(report.insights || []);
}


function renderBristolControlChart(selector, points, limits) {
  const container = document.querySelector(selector);
  if (!container) return;

  if (!points.length) {
    container.innerHTML = '<div class="empty">这个周期还没有布里斯托等级数据</div>';
    return;
  }

  const width = 720;
  const height = 300;
  const padding = { top: 22, right: 28, bottom: 34, left: 46 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const minValue = Number(limits.min) || 1;
  const maxValue = Number(limits.max) || 7;
  const safeMin = Number(limits.safe_min) || 4;
  const safeMax = Number(limits.safe_max) || 5;
  const xFor = (index) => {
    if (points.length === 1) return padding.left + chartWidth / 2;
    return padding.left + (index / (points.length - 1)) * chartWidth;
  };
  const yFor = (value) => {
    const bounded = Math.min(maxValue, Math.max(minValue, Number(value) || minValue));
    return padding.top + ((maxValue - bounded) / (maxValue - minValue)) * chartHeight;
  };
  const pointCoords = points.map((point, index) => ({
    ...point,
    x: xFor(index),
    y: yFor(point.bristol_type),
  }));
  const path = pointCoords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(" ");
  const safeTop = yFor(safeMax);
  const safeBottom = yFor(safeMin);
  const unsafePoints = pointCoords.filter((point) => !point.is_safe);
  const safeRate = Math.round(((points.length - unsafePoints.length) / points.length) * 1000) / 10;
  const yTicks = [7, 6, 5, 4, 3, 2, 1];

  const svg = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="布里斯托控制图，安全区为 4 到 5">
      <rect class="control-safe-band" x="${padding.left}" y="${safeTop}" width="${chartWidth}" height="${safeBottom - safeTop}"></rect>
      ${yTicks.map((tick) => {
        const y = yFor(tick);
        const isLimit = tick === safeMin || tick === safeMax;
        return `
          <line class="${isLimit ? "control-limit-line" : "control-grid-line"}" x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line>
          <text class="control-axis-label" x="${padding.left - 12}" y="${y + 4}" text-anchor="end">${tick}</text>
        `;
      }).join("")}
      <line class="control-axis-line" x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}"></line>
      <line class="control-axis-line" x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}"></line>
      <text class="control-safe-label" x="${width - padding.right - 8}" y="${safeTop + 18}" text-anchor="end">安全 4-5</text>
      <path class="control-value-line" d="${path}"></path>
      ${pointCoords.map((point) => `
        <g class="control-point ${point.is_safe ? "safe" : "unsafe"}">
          <circle cx="${point.x}" cy="${point.y}" r="${point.is_safe ? 6 : 8}"></circle>
          ${point.is_safe ? "" : `<text x="${point.x}" y="${point.y - 13}" text-anchor="middle">${point.bristol_type}</text>`}
          <title>${escapeHtml(`${point.date} · Bristol ${point.bristol_type} · ${point.is_safe ? "安全" : "非安全"}`)}</title>
        </g>
      `).join("")}
      <text class="control-axis-caption" x="${padding.left}" y="${height - 10}">${escapeHtml(shortDate(points[0].date))}</text>
      <text class="control-axis-caption" x="${width - padding.right}" y="${height - 10}" text-anchor="end">${escapeHtml(shortDate(points[points.length - 1].date))}</text>
    </svg>
  `;

  const outlierList = unsafePoints.length
    ? `
      <div class="control-outliers">
        ${unsafePoints.slice(0, 8).map((point) => `
          <span class="control-outlier">
            <b>${escapeHtml(shortDate(point.date))}</b>
            Bristol ${escapeHtml(String(point.bristol_type))}
          </span>
        `).join("")}
        ${unsafePoints.length > 8 ? `<span class="control-outlier muted">+${unsafePoints.length - 8}</span>` : ""}
      </div>
    `
    : '<div class="control-outliers"><span class="control-outlier safe">全部在安全区</span></div>';

  container.innerHTML = `
    <div class="control-legend">
      <span><i class="legend-safe"></i>安全区 4-5</span>
      <span><i class="legend-unsafe"></i>非安全值 ${unsafePoints.length} 次</span>
      <strong>安全率 ${safeRate}%</strong>
    </div>
    ${svg}
    ${outlierList}
  `;
}


function renderMedicationReport(report) {
  const summary = report.summary || {};
  const topProduct = summary.top_product;
  const topTiming = summary.top_timing_relation;

  document.querySelector("#med-report-total-records").textContent = summary.total_records ?? 0;
  document.querySelector("#med-report-active-days").textContent = `${summary.days_with_records ?? 0}`;
  document.querySelector("#med-report-products").textContent = summary.active_products ?? 0;
  document.querySelector("#med-report-avg-day").textContent = summary.avg_records_per_day ?? 0;
  document.querySelector("#med-report-top-product").textContent = topProduct
    ? shortText(topProduct.label, 8)
    : "-";
  document.querySelector("#med-report-top-product-meta").textContent = topProduct
    ? `${topProduct.count} 次`
    : "按记录次数";
  document.querySelector("#med-report-top-timing").textContent = topTiming
    ? shortText(topTiming.label, 8)
    : "-";
  document.querySelector("#med-report-top-timing-meta").textContent = topTiming
    ? `${topTiming.count} 次`
    : "最常见";

  renderBarRows("#med-report-daily-chart", report.daily || [], {
    emptyText: "这个周期还没有用药记录",
    label: (row) => shortDate(row.date),
    value: (row) => row.count,
    valueText: (row) => `${row.count} 条`,
    meta: (row) => medicationDailyMeta(row),
  });

  renderMedicationProductList(report.product_usage || []);

  renderBarRows("#med-report-type-chart", report.type_distribution || [], {
    emptyText: "暂无类型分布",
    label: (row) => row.label,
    value: (row) => row.count,
    valueText: (row) => `${row.count} 次`,
  });

  renderBarRows("#med-report-timing-chart", report.timing_distribution || [], {
    emptyText: "暂无时间关系记录",
    label: (row) => row.label,
    value: (row) => row.count,
    valueText: (row) => `${row.count} 次`,
  });

  renderDateChips(
    "#med-report-no-record-days",
    report.no_record_dates || [],
    report.range.days,
    "这个周期每天都有用药记录",
    "天没有用药记录",
  );
  renderMedicationHighLoadDays(report.high_load_days || []);
  renderInsightsFor("#med-report-insights", report.insights || [], "记录还不够，暂时没有用药解读");
}


function renderBarRows(selector, rows, options) {
  const container = document.querySelector(selector);
  if (!container) return;
  const values = rows.map((row) => Number(options.value(row)) || 0);
  const maxValue = Math.max(...values, 1);
  const hasData = values.some((value) => value > 0);
  if (!hasData) {
    container.innerHTML = `<div class="empty">${escapeHtml(options.emptyText || "暂无数据")}</div>`;
    return;
  }

  container.innerHTML = rows
    .map((row) => {
      const value = Number(options.value(row)) || 0;
      const width = value > 0 ? Math.max(3, Math.round((value / maxValue) * 100)) : 0;
      const meta = options.meta?.(row);
      return `
        <div class="bar-row">
          <div class="bar-label">
            <strong>${escapeHtml(String(options.label(row)))}</strong>
            ${meta ? `<span>${escapeHtml(String(meta))}</span>` : ""}
          </div>
          <div class="bar-track" aria-hidden="true">
            <span class="bar-fill" style="width: ${width}%"></span>
          </div>
          <div class="bar-value">${escapeHtml(String(options.valueText(row)))}</div>
        </div>
      `;
    })
    .join("");
}


function renderMedicationProductList(rows) {
  const container = document.querySelector("#med-report-product-list");
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = '<div class="empty">暂无药物使用排行</div>';
    return;
  }

  container.innerHTML = rows
    .slice(0, 10)
    .map((row) => {
      const quantity = row.quantity ? ` · ${formatNumber(row.quantity)}${row.unit || ""}` : "";
      return `
        <div class="rank-item">
          <span>
            <b>${escapeHtml(String(row.label || "未命名药物"))}</b>
            <small>${escapeHtml([row.type, `${row.active_days} 天`].filter(Boolean).join(" · "))}</small>
          </span>
          <strong>${escapeHtml(`${row.count} 次${quantity}`)}</strong>
        </div>
      `;
    })
    .join("");
}


function renderRankList(selector, rows, options) {
  const container = document.querySelector(selector);
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = `<div class="empty">${escapeHtml(options.emptyText || "暂无数据")}</div>`;
    return;
  }

  const title = options.title ? `<div class="rank-caption">${escapeHtml(options.title)}</div>` : "";
  container.innerHTML =
    title +
    rows
      .slice(0, 8)
      .map((row) => {
        const meta = options.meta?.(row);
        return `
          <div class="rank-item">
            <span>
              <b>${escapeHtml(String(row.label || "未命名"))}</b>
              ${meta ? `<small>${escapeHtml(String(meta))}</small>` : ""}
            </span>
            <strong>${escapeHtml(String(options.valueText(row)))}</strong>
          </div>
        `;
      })
      .join("");
}


function renderAttentionDays(rows) {
  const container = document.querySelector("#report-attention-days");
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = '<div class="empty">这个周期没有明显需要留意的排便日期</div>';
    return;
  }

  container.innerHTML = rows
    .map((row) => {
      return `
        <div class="attention-item">
          <strong>${escapeHtml(row.date)}</strong>
          <span>${escapeHtml(row.reasons.join(" · "))}</span>
          <b>${row.count} 次</b>
        </div>
      `;
    })
    .join("");
}


function renderNoRecordDays(rows, totalDays) {
  renderDateChips(
    "#report-no-record-days",
    rows,
    totalDays,
    "这个周期每天都有排便记录",
    "天没有记录",
  );
}


function renderDateChips(selector, rows, totalDays, emptyText, summarySuffix) {
  const container = document.querySelector(selector);
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }

  const visibleRows = rows.slice(0, 12);
  const hiddenCount = rows.length - visibleRows.length;
  container.innerHTML = `
    <div class="date-chip-summary">${rows.length} / ${totalDays} ${escapeHtml(summarySuffix)}</div>
    ${visibleRows.map((dateValue) => `<span class="date-chip">${escapeHtml(shortDate(dateValue))}</span>`).join("")}
    ${hiddenCount > 0 ? `<span class="date-chip muted">+${hiddenCount}</span>` : ""}
  `;
}


function renderInsights(rows) {
  renderInsightsFor("#report-insights", rows, "记录还不够，暂时没有趋势解读");
}


function renderInsightsFor(selector, rows, emptyText) {
  const container = document.querySelector(selector);
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }

  container.innerHTML = rows
    .map((text) => `<div class="insight-item">${escapeHtml(text)}</div>`)
    .join("");
}


function renderMedicationHighLoadDays(rows) {
  const container = document.querySelector("#med-report-high-load-days");
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = '<div class="empty">这个周期没有一天记录 4 条及以上用药</div>';
    return;
  }

  container.innerHTML = rows
    .map((row) => {
      const meta = [
        row.dominant_timing_relation,
        row.dominant_type,
        row.dominant_product,
      ].filter(Boolean);
      return `
        <div class="attention-item">
          <strong>${escapeHtml(row.date)}</strong>
          <span>${escapeHtml(meta.join(" · "))}</span>
          <b>${row.count} 条</b>
        </div>
      `;
    })
    .join("");
}


function dailyMetaText(row) {
  const parts = [];
  if (row.below_count) parts.push(`低于安全区 ${row.below_count}`);
  if (row.above_count) parts.push(`高于安全区 ${row.above_count}`);
  if (row.urgent_count) parts.push(`急迫 ${row.urgent_count}`);
  if (row.count >= 3) parts.push("一天多次");
  if (!parts.length && row.dominant_color) parts.push(row.dominant_color);
  return parts.join(" · ");
}


function medicationDailyMeta(row) {
  return [row.dominant_timing_relation, row.dominant_type, row.dominant_product]
    .filter(Boolean)
    .join(" · ");
}
