import { bristolLabels, tableLabels } from "./constants.js";
import { state } from "./state.js";
import { escapeHtml, formatDateTime } from "./utils.js";


export function renderSummary(summary) {
  document.querySelector("#summary-bowel").textContent = summary.bowel_events ?? 0;
  document.querySelector("#summary-bristol").textContent = summary.avg_bristol ?? "-";
  document.querySelector("#summary-meals").textContent = summary.meals ?? 0;
  document.querySelector("#summary-medications").textContent = summary.medications ?? 0;
  document.querySelector("#summary-exercise").textContent = summary.exercise_minutes ?? 0;
  document.querySelector("#summary-sleep").textContent = summary.sleep_minutes ?? 0;
}


export function renderList(table) {
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


export function populateMedicationPickers(record = null) {
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


export function populateMealLocations() {
  const datalist = document.querySelector("#meal-location-history");
  if (!datalist) return;
  datalist.innerHTML = state.mealLocations
    .map((location) => `<option value="${escapeHtml(location)}"></option>`)
    .join("");
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
  return `
    <figure class="meal-photo-frame">
      <img class="meal-photo" src="${escapeHtml(record.photo_path)}" alt="饮食照片" />
    </figure>
  `;
}
