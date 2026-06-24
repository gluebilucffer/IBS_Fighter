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
  if (report.module === "weight") {
    renderWeightReport(report);
    return;
  }
  if (report.module === "medications") {
    renderMedicationReport(report);
    return;
  }
  renderBowelReport(report);
}


function updateReportShell(report) {
  const moduleLabels = {
    bowel: "排便报表",
    medications: "用药报表",
    weight: "体重报表",
  };
  const moduleLabel = moduleLabels[report.module] || "排便报表";
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
  renderSafetyPChart("#report-safety-p-chart", report.safety_p_chart || {});
  renderUnsafeIntervalChart("#report-unsafe-interval-chart", report.unsafe_interval_g_chart || {});

  renderVerticalBarChart("#report-bristol-chart", report.bristol_distribution || [], {
    emptyText: "还没有布里斯托等级数据",
    label: (row) => String(row.type),
    value: (row) => row.count,
    valueText: (row) => `${row.count} 次`,
    meta: (row) => `${row.rate}%`,
    isSafe: (row) => row.type === 4 || row.type === 5,
  });

  renderQualitySummary(report.quality_distribution || [], summary);

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


function renderSafetyPChart(selector, chart) {
  const container = document.querySelector(selector);
  if (!container) return;

  const points = chart.points || [];
  const dataPoints = points.filter((point) => point.safe_rate !== null && point.safe_rate !== undefined);
  if (!dataPoints.length) {
    container.innerHTML = '<div class="empty">这个周期还没有可计算安全率的排便记录</div>';
    return;
  }

  const width = 720;
  const height = 290;
  const padding = { top: 22, right: 30, bottom: 36, left: 48 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const xFor = (index) => {
    if (points.length <= 1) return padding.left + chartWidth / 2;
    return padding.left + (index / (points.length - 1)) * chartWidth;
  };
  const yFor = (value) => {
    const bounded = Math.min(100, Math.max(0, Number(value) || 0));
    return padding.top + ((100 - bounded) / 100) * chartHeight;
  };
  const plottedPoints = points
    .map((point, index) => ({
      ...point,
      x: xFor(index),
      y: point.safe_rate === null || point.safe_rate === undefined ? null : yFor(point.safe_rate),
    }))
    .filter((point) => point.y !== null);
  const path = plottedPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(" ");
  const centerline = Number(chart.overall_safe_rate) || 0;
  const yCenter = yFor(centerline);
  const ticks = [100, 75, 50, 25, 0];
  const flaggedPoints = plottedPoints.filter((point) => point.status !== "stable");
  const recentPoints = plottedPoints.slice(-10);

  const svg = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="安全率 p-chart">
      ${ticks.map((tick) => {
        const y = yFor(tick);
        return `
          <line class="spc-grid-line" x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line>
          <text class="control-axis-label" x="${padding.left - 12}" y="${y + 4}" text-anchor="end">${tick}%</text>
        `;
      }).join("")}
      <line class="control-axis-line" x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}"></line>
      <line class="control-axis-line" x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}"></line>
      <line class="spc-centerline" x1="${padding.left}" y1="${yCenter}" x2="${width - padding.right}" y2="${yCenter}"></line>
      <text class="spc-center-label" x="${width - padding.right - 8}" y="${yCenter - 8}" text-anchor="end">中心线 ${escapeHtml(formatNumber(centerline))}%</text>
      ${plottedPoints.map((point) => {
        if (point.lcl === null || point.ucl === null || point.lcl === undefined || point.ucl === undefined) {
          return "";
        }
        return `
          <line class="spc-control-range" x1="${point.x}" y1="${yFor(point.ucl)}" x2="${point.x}" y2="${yFor(point.lcl)}"></line>
        `;
      }).join("")}
      <path class="spc-value-line" d="${path}"></path>
      ${plottedPoints.map((point) => {
        const isFlagged = point.status !== "stable";
        const statusText = point.status === "special_cause"
          ? "超出控制线"
          : point.status === "has_unsafe"
            ? "含非安全值"
            : "稳定";
        return `
          <g class="spc-point ${isFlagged ? "unsafe" : "safe"}">
            <circle cx="${point.x}" cy="${point.y}" r="${isFlagged ? 7 : 5.5}"></circle>
            <title>${escapeHtml(`${point.date} · 安全率 ${point.safe_rate}% · ${statusText}`)}</title>
          </g>
        `;
      }).join("")}
      <text class="control-axis-caption" x="${padding.left}" y="${height - 10}">${escapeHtml(shortDate(points[0].date))}</text>
      <text class="control-axis-caption" x="${width - padding.right}" y="${height - 10}" text-anchor="end">${escapeHtml(shortDate(points[points.length - 1].date))}</text>
    </svg>
  `;

  container.innerHTML = `
    <div class="spc-legend">
      <span><i class="legend-safe"></i>整体安全率 ${escapeHtml(formatNumber(chart.overall_safe_rate))}%</span>
      <span>${escapeHtml(String(chart.safe_count || 0))}/${escapeHtml(String(chart.total_events || 0))} 次在 4-5</span>
      <strong>异常点 ${flaggedPoints.length} 天</strong>
    </div>
    ${svg}
    <div class="spc-point-list">
      ${recentPoints.map((point) => `
        <span class="spc-point-chip ${point.status === "stable" ? "safe" : "unsafe"}">
          <b>${escapeHtml(shortDate(point.date))}</b>
          ${escapeHtml(formatNumber(point.safe_rate))}%
          <small>${escapeHtml(String(point.count))} 次</small>
        </span>
      `).join("")}
    </div>
  `;
}


function renderUnsafeIntervalChart(selector, chart) {
  const container = document.querySelector(selector);
  if (!container) return;

  const totalEvents = Number(chart.total_events) || 0;
  if (!totalEvents) {
    container.innerHTML = '<div class="empty">这个周期还没有排便记录</div>';
    return;
  }

  const points = chart.points || [];
  const intervalRows = points.filter((point) => point.safe_events_since_previous_unsafe !== null && point.safe_events_since_previous_unsafe !== undefined);
  const currentSafeEvents = chart.current_safe_events_after_last_unsafe;
  const currentDays = chart.current_days_after_last_unsafe;
  const longestInterval = chart.longest_safe_events_between_unsafe;
  const maxValue = Math.max(
    ...intervalRows.map((point) => Number(point.safe_events_since_previous_unsafe) || 0),
    Number(currentSafeEvents) || 0,
    1,
  );

  const intervalList = intervalRows.length
    ? intervalRows.slice(-10).map((point) => {
      const safeEvents = Number(point.safe_events_since_previous_unsafe) || 0;
      const bowelEvents = point.bowel_events_since_previous_unsafe ?? 0;
      const days = point.days_since_previous_unsafe ?? "-";
      const width = safeEvents > 0 ? Math.max(5, Math.round((safeEvents / maxValue) * 100)) : 2;
      return `
        <div class="interval-row">
          <div class="interval-label">
            <strong>${escapeHtml(shortDate(point.date))} · Bristol ${escapeHtml(String(point.bristol_type ?? "-"))}</strong>
            <span>${escapeHtml(String(days))} 天 / 间隔 ${escapeHtml(String(bowelEvents))} 次排便</span>
          </div>
          <div class="interval-track" aria-hidden="true">
            <span class="interval-fill" style="width: ${width}%"></span>
          </div>
          <div class="interval-value">${escapeHtml(String(safeEvents))} 次安全</div>
        </div>
      `;
    }).join("")
    : `<div class="empty">${points.length ? "这个周期只有 1 次非安全排便，还不能形成间隔" : "这个周期没有非安全排便"}</div>`;

  const currentText = currentSafeEvents === null || currentSafeEvents === undefined
    ? "未形成"
    : `${currentSafeEvents} 次`;
  const daysText = currentDays === null || currentDays === undefined
    ? ""
    : ` · ${currentDays} 天`;
  const longestText = longestInterval === null || longestInterval === undefined
    ? "未形成"
    : `${longestInterval} 次`;

  container.innerHTML = `
    <div class="interval-summary">
      <span>
        <b>${escapeHtml(String(chart.unsafe_count || 0))}</b>
        非安全排便
      </span>
      <span>
        <b>${escapeHtml(currentText)}</b>
        当前连续安全${escapeHtml(daysText)}
      </span>
      <span>
        <b>${escapeHtml(longestText)}</b>
        最长异常间隔
      </span>
    </div>
    <div class="interval-list">
      ${intervalList}
    </div>
  `;
}


function renderVerticalBarChart(selector, rows, options) {
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
      const height = value > 0 ? Math.max(6, Math.round((value / maxValue) * 100)) : 0;
      const safeClass = options.isSafe?.(row) ? " safe" : "";
      return `
        <div class="vertical-bar${safeClass}">
          <div class="vertical-bar-value">${escapeHtml(String(options.valueText(row)))}</div>
          <div class="vertical-bar-track" aria-hidden="true">
            <span class="vertical-bar-fill" style="height: ${height}%"></span>
          </div>
          <div class="vertical-bar-label">
            <strong>${escapeHtml(String(options.label(row)))}</strong>
            <span>${escapeHtml(String(options.meta?.(row) || ""))}</span>
          </div>
        </div>
      `;
    })
    .join("");
}


function renderQualitySummary(rows, summary) {
  const container = document.querySelector("#report-quality-summary");
  if (!container) return;
  const total = Number(summary.total_events) || rows.reduce((sum, row) => sum + (Number(row.count) || 0), 0);
  if (!total) {
    container.innerHTML = '<div class="empty">还没有可归类的排便记录</div>';
    return;
  }

  const safeCount = Number(summary.safe_count) || 0;
  const abnormalCount = Number(summary.abnormal_count) || 0;
  const safeRate = summary.safe_rate ?? 0;
  const detailRows = rows.filter((row) => Number(row.count) > 0);
  const detailText = detailRows
    .map((row) => {
      const count = Number(row.count) || 0;
      const rate = Math.round((count / total) * 1000) / 10;
      return `${row.label} ${count} 次（${rate}%）`;
    })
    .join("；");

  container.innerHTML = `
    <p>
      这个周期共 ${escapeHtml(String(total))} 次排便，安全区 4-5 有
      <b>${escapeHtml(String(safeCount))}</b> 次，占
      <b>${escapeHtml(String(safeRate))}%</b>；非安全值
      <b>${escapeHtml(String(abnormalCount))}</b> 次。
    </p>
    <small>${escapeHtml(detailText || "暂无形态分布细节")}</small>
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


function renderWeightReport(report) {
  const summary = report.summary || {};

  document.querySelector("#weight-report-latest").textContent = formatWeight(summary.latest_weight_kg);
  document.querySelector("#weight-report-latest-date").textContent = summary.latest_date || "周期内最近一次";
  document.querySelector("#weight-report-change").textContent = formatSignedWeight(summary.change_kg);
  document.querySelector("#weight-report-coverage").textContent = `${summary.coverage_rate ?? 0}%`;
  document.querySelector("#weight-report-record-days").textContent = `${summary.days_with_records ?? 0} 天有记录`;
  document.querySelector("#weight-report-average").textContent = formatWeight(summary.avg_weight_kg);
  document.querySelector("#weight-report-min").textContent = formatWeight(summary.min_weight_kg);
  document.querySelector("#weight-report-min-date").textContent = summary.min_weight_date || "-";
  document.querySelector("#weight-report-max").textContent = formatWeight(summary.max_weight_kg);
  document.querySelector("#weight-report-max-date").textContent = summary.max_weight_date || "-";

  renderWeightTrendChart("#weight-report-trend-chart", report.trend_points || []);
  renderDateChips(
    "#weight-report-no-record-days",
    report.no_record_dates || [],
    report.range.days,
    "这个周期每天都有体重记录",
    "天没有体重记录",
  );
  renderWeightAttentionDays(report.attention_days || []);
  renderInsightsFor("#weight-report-insights", report.insights || [], "记录还不够，暂时没有体重监控建议");
}


function renderWeightTrendChart(selector, points) {
  const container = document.querySelector(selector);
  if (!container) return;

  if (!points.length) {
    container.innerHTML = '<div class="empty">这个周期还没有体重数据</div>';
    return;
  }

  const width = 720;
  const height = 300;
  const padding = { top: 24, right: 30, bottom: 36, left: 56 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const weights = points.map((point) => Number(point.weight_kg)).filter((value) => Number.isFinite(value));
  const rawMin = Math.min(...weights);
  const rawMax = Math.max(...weights);
  const span = Math.max(rawMax - rawMin, 1);
  const minValue = Math.floor((rawMin - span * 0.15) * 10) / 10;
  const maxValue = Math.ceil((rawMax + span * 0.15) * 10) / 10;
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
    y: yFor(point.weight_kg),
  }));
  const path = pointCoords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(" ");
  const yTicks = [maxValue, (maxValue + minValue) / 2, minValue];
  const change = points.length > 1
    ? Number(points[points.length - 1].weight_kg) - Number(points[0].weight_kg)
    : null;

  const svg = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="体重趋势图">
      ${yTicks.map((tick) => {
        const y = yFor(tick);
        return `
          <line class="control-grid-line" x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line>
          <text class="control-axis-label" x="${padding.left - 12}" y="${y + 4}" text-anchor="end">${escapeHtml(formatNumber(tick))}</text>
        `;
      }).join("")}
      <line class="control-axis-line" x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}"></line>
      <line class="control-axis-line" x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}"></line>
      <path class="control-value-line" d="${path}"></path>
      ${pointCoords.map((point) => {
        const context = point.measurement_context ? ` · ${point.measurement_context}` : "";
        const changeText = point.change_from_previous_kg === null || point.change_from_previous_kg === undefined
          ? ""
          : ` · 较上次 ${formatSignedWeight(point.change_from_previous_kg)}`;
        return `
          <g class="control-point safe">
            <circle cx="${point.x}" cy="${point.y}" r="6"></circle>
            <title>${escapeHtml(`${point.date} · ${formatWeight(point.weight_kg)}${context}${changeText}`)}</title>
          </g>
        `;
      }).join("")}
      <text class="control-axis-caption" x="${padding.left}" y="${height - 10}">${escapeHtml(shortDate(points[0].date))}</text>
      <text class="control-axis-caption" x="${width - padding.right}" y="${height - 10}" text-anchor="end">${escapeHtml(shortDate(points[points.length - 1].date))}</text>
    </svg>
  `;

  container.innerHTML = `
    <div class="control-legend">
      <span><i class="legend-safe"></i>记录点 ${points.length} 天</span>
      <span>范围 ${escapeHtml(formatWeight(rawMin))} - ${escapeHtml(formatWeight(rawMax))}</span>
      <strong>周期变化 ${escapeHtml(formatSignedWeight(change))}</strong>
    </div>
    ${svg}
  `;
}


function renderWeightAttentionDays(rows) {
  const container = document.querySelector("#weight-report-attention-days");
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = '<div class="empty">这个周期没有较上次记录变化 1kg 以上的日期</div>';
    return;
  }

  container.innerHTML = rows
    .map((row) => {
      const meta = [row.measurement_context, ...(row.reasons || [])].filter(Boolean);
      return `
        <div class="attention-item">
          <strong>${escapeHtml(row.date)}</strong>
          <span>${escapeHtml(meta.join(" · "))}</span>
          <b>${escapeHtml(formatWeight(row.weight_kg))}</b>
        </div>
      `;
    })
    .join("");
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


function formatWeight(value) {
  if (value === null || value === undefined || value === "") return "-";
  return `${formatNumber(value)}kg`;
}


function formatSignedWeight(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number > 0 ? "+" : ""}${formatNumber(number)}kg`;
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
