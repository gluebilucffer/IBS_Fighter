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
  document.querySelector("#report-title").textContent = moduleLabel;
  document.querySelector("#report-range").textContent = `${report.range.start_date} 至 ${report.range.end_date}`;

  document.querySelectorAll("[data-report-module]").forEach((button) => {
    button.classList.toggle("active", button.dataset.reportModule === report.module);
  });
  document.querySelectorAll("[data-report-module-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.reportModulePanel === report.module);
  });
  document.querySelectorAll("[data-report-days]").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.reportDays) === report.range.days);
  });
}


function renderBowelReport(report) {
  const summary = report.summary || {};

  document.querySelector("#report-total-events").textContent = summary.total_events ?? 0;
  document.querySelector("#report-avg-events-day").textContent = summary.avg_events_per_day ?? 0;
  document.querySelector("#report-avg-bristol").textContent = summary.avg_bristol ?? "-";
  document.querySelector("#report-normal-rate").textContent = `${summary.normal_rate ?? 0}%`;
  document.querySelector("#report-abnormal-count").textContent = summary.abnormal_count ?? 0;
  document.querySelector("#report-urgent-count").textContent = summary.urgent_count ?? 0;

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
  if (row.hard_count) parts.push(`偏硬 ${row.hard_count}`);
  if (row.loose_count) parts.push(`偏稀 ${row.loose_count}`);
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
