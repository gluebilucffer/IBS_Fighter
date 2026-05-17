const tableLabels = {
  bowel_movements: "排便",
  meals: "饮食",
  medications: "用药",
  medication_products: "药物",
  exercises: "运动",
  sleep_entries: "睡眠",
};

const trackingTables = ["bowel_movements", "meals", "medications", "exercises", "sleep_entries"];

const tableFields = {
  bowel_movements: [
    "id",
    "occurred_at",
    "bristol_type",
    "location",
    "urgency",
    "color",
    "notes",
  ],
  meals: [
    "id",
    "eaten_at",
    "meal_type",
    "location",
    "foods",
    "photo_path",
    "photo_filename",
    "symptoms_after",
    "notes",
  ],
  medications: [
    "id",
    "taken_at",
    "product_id",
    "quantity_value",
    "quantity_unit",
    "timing_relation",
    "notes",
  ],
  medication_products: ["id", "product_name", "ingredients", "product_type", "default_unit"],
  exercises: [
    "id",
    "started_at",
    "activity_type",
    "duration_minutes",
    "intensity",
    "notes",
  ],
  sleep_entries: [
    "id",
    "sleep_date",
    "source",
    "started_at",
    "ended_at",
    "duration_minutes",
    "quality",
    "notes",
  ],
};

const numericFields = new Set([
  "bristol_type",
  "urgency",
  "product_id",
  "quantity_value",
  "duration_minutes",
]);

const bristolLabels = {
  1: "1 硬球状",
  2: "2 结块香肠状",
  3: "3 表面裂纹",
  4: "4 光滑柔软",
  5: "5 软块",
  6: "6 糊状",
  7: "7 水样",
};

const state = {
  date: "",
  records: {},
  medicationProducts: [],
  mealLocations: [],
  reportDays: 7,
  reportModule: "bowel",
  report: null,
};

const dateInput = document.querySelector("#selected-date");
const toast = document.querySelector("#toast");

function today() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultDateTime() {
  const now = new Date();
  const datePart = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  const time = now.toTimeString().slice(0, 5);
  return `${datePart}T${time}`;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2200);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "请求失败");
  }
  return payload;
}

async function loadDay() {
  state.date = dateInput.value || today();
  const payload = await requestJson(`/api/day?date=${encodeURIComponent(state.date)}`);
  state.records = payload.records;
  state.medicationProducts = payload.medication_products || [];
  state.mealLocations = payload.meal_locations || [];
  renderSummary(payload.summary);
  trackingTables.forEach((table) => renderList(table));
  renderList("medication_products");
  populateMedicationPickers();
  populateMealLocations();
  setEmptyFormDefaults();
  await loadReport();
}

function renderSummary(summary) {
  document.querySelector("#summary-bowel").textContent = summary.bowel_events ?? 0;
  document.querySelector("#summary-bristol").textContent = summary.avg_bristol ?? "-";
  document.querySelector("#summary-meals").textContent = summary.meals ?? 0;
  document.querySelector("#summary-medications").textContent = summary.medications ?? 0;
  document.querySelector("#summary-exercise").textContent = summary.exercise_minutes ?? 0;
  document.querySelector("#summary-sleep").textContent = summary.sleep_minutes ?? 0;
}

async function loadReport() {
  const days = state.reportDays || 7;
  const endDate = state.date || dateInput.value || today();
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

function shortDate(value) {
  if (!value) return "";
  return value.slice(5).replace("-", "/");
}

function shortText(value, maxLength) {
  if (!value) return "";
  const text = String(value);
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return Number.isInteger(number) ? String(number) : number.toFixed(1);
}

function renderList(table) {
  const list = document.querySelector(`[data-list="${table}"]`);
  if (!list) return;
  const records =
    table === "medication_products" ? state.medicationProducts : state.records[table] || [];
  list.innerHTML = "";

  if (!records.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = `暂无${tableLabels[table]}记录`;
    list.append(empty);
    return;
  }

  records.forEach((record) => {
    const item = document.createElement("article");
    item.className = "record";
    item.innerHTML = `
      <div class="record-header">
        <div>
          <h3 class="record-title">${escapeHtml(recordTitle(table, record))}</h3>
          <div class="record-time">${escapeHtml(recordTime(table, record))}</div>
        </div>
        <div class="record-actions">
          <button class="ghost" type="button" data-edit="${table}" data-id="${record.id}">编辑</button>
          <button class="danger" type="button" data-delete="${table}" data-id="${record.id}">删除</button>
        </div>
      </div>
      ${recordPhoto(table, record)}
      <div class="record-body">${recordDetails(table, record)}</div>
    `;
    list.append(item);
  });
}

function recordTitle(table, record) {
  if (table === "bowel_movements") {
    return bristolLabels[record.bristol_type] || record.bristol_type;
  }
  if (table === "meals") {
    return record.meal_type || "饮食";
  }
  if (table === "medications") {
    return [record.product_type, record.product_name].filter(Boolean).join(" / ");
  }
  if (table === "medication_products") {
    return record.product_name;
  }
  if (table === "exercises") {
    return record.activity_type;
  }
  if (table === "sleep_entries") {
    const duration = record.duration_minutes ? `${record.duration_minutes} 分钟` : "睡眠";
    return record.quality ? `${duration} / ${record.quality}` : duration;
  }
  return "";
}

function recordTime(table, record) {
  const key = {
    bowel_movements: "occurred_at",
    meals: "eaten_at",
    medications: "taken_at",
    exercises: "started_at",
    sleep_entries: "started_at",
  }[table];
  return key && record[key] ? formatDateTime(record[key]) : record.sleep_date || "";
}

function recordDetails(table, record) {
  const rows = [];
  const add = (label, value) => {
    if (value !== undefined && value !== null && value !== "") {
      rows.push(`<div><b>${escapeHtml(label)}</b> ${escapeHtml(String(value))}</div>`);
    }
  };

  if (table === "bowel_movements") {
    add("地点", record.location);
    add("急迫感", record.urgency);
    add("颜色", record.color);
    add("备注", record.notes);
  }

  if (table === "meals") {
    add("地点", record.location);
    add("描述", record.foods);
    add("饭后", record.symptoms_after);
    add("备注", record.notes);
  }

  if (table === "medications") {
    const quantity = [record.quantity_value, record.quantity_unit].filter(Boolean).join(" ");
    add("药物", record.product_name);
    add("类型", record.product_type);
    add("数量", quantity);
    add("关系", record.timing_relation);
    add("备注", record.notes);
  }

  if (table === "medication_products") {
    add("类型", record.product_type);
    add("单位", record.default_unit);
    add("成分", record.ingredients);
  }

  if (table === "exercises") {
    const duration = record.duration_minutes ? `${record.duration_minutes} 分钟` : "";
    add("时长", duration);
    add("强度", record.intensity);
    add("活动", record.activity_type);
    add("备注", record.notes);
  }

  if (table === "sleep_entries") {
    const duration = record.duration_minutes ? `${record.duration_minutes} 分钟` : "";
    add("日期", record.sleep_date);
    add("入睡", formatDateTime(record.started_at));
    add("醒来", formatDateTime(record.ended_at));
    add("时长", duration);
    add("质量", record.quality);
    add("备注", record.notes);
  }

  return rows.join("") || "<div>无备注</div>";
}

function recordPhoto(table, record) {
  if (table !== "meals" || !record.photo_path) return "";
  return `<img class="meal-photo" src="${escapeHtml(record.photo_path)}" alt="饮食照片" />`;
}

function populateMedicationPickers(record = null) {
  document.querySelectorAll("[data-medication-picker]").forEach((picker) => {
    if (!state.medicationProducts.length) {
      picker.innerHTML = '<div class="empty">先登记药物</div>';
      return;
    }

    picker.innerHTML = state.medicationProducts
      .map((product) => {
        const isSelected = record && Number(record.product_id) === Number(product.id);
        const quantity = isSelected && record.quantity_value !== null ? record.quantity_value : "";
        const unit = product.default_unit || (isSelected && record.quantity_unit) || "";
        return `
          <label class="medication-option">
            <input type="checkbox" name="product_ids" value="${product.id}" ${
          isSelected ? "checked" : ""
        } />
            <span class="medication-name">
              <strong>${escapeHtml(product.product_name)}</strong>
              <span>${escapeHtml(product.product_type)}</span>
            </span>
            <input name="quantity_value_${product.id}" type="number" min="0" step="0.01" placeholder="数量" value="${escapeHtml(String(quantity))}" />
            <span class="fixed-unit">${escapeHtml(unit || "未设单位")}</span>
          </label>
        `;
      })
      .join("");
  });
}

function populateMealLocations() {
  const datalist = document.querySelector("#meal-location-history");
  if (!datalist) return;
  datalist.innerHTML = state.mealLocations
    .map((location) => `<option value="${escapeHtml(location)}"></option>`)
    .join("");
}

async function collectFormData(form) {
  const formData = new FormData(form);
  const payload = {};
  formData.forEach((value, key) => {
    if (key === "id" || key === "photo") return;
    const trimmed = typeof value === "string" ? value.trim() : value;
    if (trimmed === "") {
      payload[key] = null;
    } else if (numericFields.has(key)) {
      payload[key] = Number(trimmed);
    } else {
      payload[key] = trimmed;
    }
  });

  const photoInput = form.elements.photo;
  if (photoInput?.files?.[0]) {
    payload.photo_filename = photoInput.files[0].name;
    payload.photo_data_url = await fileToDataUrl(photoInput.files[0]);
  }

  return payload;
}

function collectMedicationPayloads(form) {
  const checkedProducts = [...form.querySelectorAll('input[name="product_ids"]:checked')];
  if (!checkedProducts.length) {
    throw new Error("请至少选择一种药物");
  }

  return checkedProducts.map((checkbox) => {
    const productId = Number(checkbox.value);
    const product = state.medicationProducts.find((item) => Number(item.id) === productId);
    const quantityValue = form.elements[`quantity_value_${productId}`]?.value.trim();
    return {
      taken_at: form.elements.taken_at.value,
      product_id: productId,
      quantity_value: quantityValue === "" ? null : Number(quantityValue),
      quantity_unit: product?.default_unit || null,
      timing_relation: form.elements.timing_relation.value || null,
      notes: form.elements.notes.value.trim() || null,
    };
  });
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("照片读取失败"));
    reader.readAsDataURL(file);
  });
}

function fillForm(table, record) {
  const form = document.querySelector(`[data-form="${table}"]`);
  if (table === "medications") {
    form.elements.id.value = record.id ?? "";
    form.elements.taken_at.value = record.taken_at ?? "";
    form.elements.timing_relation.value = record.timing_relation ?? "";
    form.elements.notes.value = record.notes ?? "";
    populateMedicationPickers(record);
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }

  tableFields[table].forEach((field) => {
    const input = form.elements[field];
    if (!input) return;
    input.value = record[field] ?? "";
  });
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetForm(table) {
  const form = document.querySelector(`[data-form="${table}"]`);
  form.reset();
  form.elements.id.value = "";
  setFormDefaultDateTime(form);
  if (table === "bowel_movements") {
    form.elements.bristol_type.value = "4";
  }
  if (table === "medications" || table === "medication_products") {
    populateMedicationPickers();
  }
}

function setEmptyFormDefaults() {
  document.querySelectorAll("form").forEach((form) => {
    if (!form.elements.id.value) setFormDefaultDateTime(form);
  });
}

function setFormDefaultDateTime(form) {
  form.querySelectorAll('input[type="datetime-local"]').forEach((input) => {
    input.value = defaultDateTime();
  });
  form.querySelectorAll('input[type="date"]').forEach((input) => {
    input.value = state.date || today();
  });
}

function formatDateTime(value) {
  if (!value) return "";
  return value.replace("T", " ").slice(0, 16);
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => {
    const map = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return map[char];
  });
}

document.querySelectorAll("form[data-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const table = form.dataset.form;
    const id = form.elements.id.value;

    try {
      if (table === "medications") {
        const payloads = collectMedicationPayloads(form);
        if (id && payloads.length > 1) {
          throw new Error("编辑单条用药记录时只能选择一种药物");
        }

        if (id) {
          await requestJson(`/api/${table}/${id}`, {
            method: "PUT",
            body: JSON.stringify(payloads[0]),
          });
        } else {
          await Promise.all(
            payloads.map((payload) =>
              requestJson(`/api/${table}`, {
                method: "POST",
                body: JSON.stringify(payload),
              }),
            ),
          );
        }

        resetForm(table);
        await loadDay();
        showToast(`已保存 ${payloads.length} 条用药记录`);
        return;
      }

      const payload = await collectFormData(form);
      const method = id ? "PUT" : "POST";
      const url = id ? `/api/${table}/${id}` : `/api/${table}`;
      await requestJson(url, {
        method,
        body: JSON.stringify(payload),
      });
      resetForm(table);
      await loadDay();
      showToast(`${tableLabels[table]}已保存`);
    } catch (error) {
      showToast(error.message);
    }
  });
});

document.addEventListener("click", async (event) => {
  const editButton = event.target.closest("[data-edit]");
  const deleteButton = event.target.closest("[data-delete]");
  const resetButton = event.target.closest("[data-reset]");
  const tabButton = event.target.closest("[data-tab]");
  const reportModuleButton = event.target.closest("[data-report-module]");
  const reportRangeButton = event.target.closest("[data-report-days]");

  if (tabButton) {
    activateTab(tabButton.dataset.tab);
  }

  if (reportModuleButton) {
    state.reportModule = reportModuleButton.dataset.reportModule || "bowel";
    loadReport().catch((error) => showToast(error.message));
  }

  if (reportRangeButton) {
    state.reportDays = Number(reportRangeButton.dataset.reportDays) || 7;
    loadReport().catch((error) => showToast(error.message));
  }

  if (editButton) {
    const table = editButton.dataset.edit;
    const id = Number(editButton.dataset.id);
    const source =
      table === "medication_products" ? state.medicationProducts : state.records[table] || [];
    const record = source.find((item) => item.id === id);
    if (record) fillForm(table, record);
  }

  if (deleteButton) {
    const table = deleteButton.dataset.delete;
    const id = Number(deleteButton.dataset.id);
    try {
      await requestJson(`/api/${table}/${id}`, { method: "DELETE" });
      await loadDay();
      showToast(`${tableLabels[table]}已删除`);
    } catch (error) {
      showToast(error.message);
    }
  }

  if (resetButton) {
    resetForm(resetButton.dataset.reset);
  }
});

function activateTab(tabName) {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === tabName);
  });
}

dateInput.addEventListener("change", () => {
  loadDay().catch((error) => showToast(error.message));
});

dateInput.value = today();
loadDay().catch((error) => showToast(error.message));
