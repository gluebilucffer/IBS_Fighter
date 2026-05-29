import { requestJson, setCsrfToken } from "./api.js";
import { tableLabels, trackingTables } from "./constants.js";
import {
  collectFormData,
  collectMedicationPayloads,
  fileToDataUrl,
  fillForm,
  getFormControl,
  resetForm,
  setEmptyFormDefaults,
} from "./forms.js";
import { activateRecordTab, activateTab } from "./navigation.js";
import {
  populateMealLocations,
  populateMedicationPickers,
  populateShortcuts,
  renderChecklist,
  renderList,
  renderSummary,
} from "./records.js";
import { loadReport } from "./reports.js";
import { state } from "./state.js";
import { browserTimeZone, escapeHtml, showToast, today } from "./utils.js";


const dateInput = document.querySelector("#selected-date");


async function initialize() {
  await loadAuthState();
  dateInput.value = today();
  await loadDay();
}


async function loadAuthState() {
  const payload = await requestJson("/api/auth/me");
  state.user = payload.user || null;
  state.aiMealEnabled = Boolean(payload.ai_meal_enabled);
  state.clientTimezone = browserTimeZone();
  setCsrfToken(payload.csrf_token || "");
  renderAuthState();
}


function renderAuthState() {
  const userEmail = document.querySelector("[data-user-email]");
  if (userEmail) {
    userEmail.textContent = state.user?.email || "未登录";
  }

  const timeZoneLabel = document.querySelector("[data-timezone-label]");
  if (timeZoneLabel) {
    timeZoneLabel.textContent = `时区 ${state.clientTimezone}`;
  }

  document.querySelectorAll("[data-ai-meal-panel]").forEach((panel) => {
    panel.hidden = !state.aiMealEnabled;
  });
}


async function loadDay() {
  state.date = dateInput.value || today();
  const payload = await requestJson(`/api/day?date=${encodeURIComponent(state.date)}`);
  state.records = payload.records;
  state.medicationProducts = payload.medication_products || [];
  state.mealLocations = payload.meal_locations || [];
  state.shortcuts = payload.shortcuts || {};
  state.checklist = payload.checklist || [];
  renderSummary(payload.summary);
  renderChecklist(state.checklist);
  trackingTables.forEach((table) => renderList(table));
  renderList("medication_products");
  populateMedicationPickers();
  populateMealLocations();
  populateShortcuts();
  setEmptyFormDefaults();
  await loadReport(state.date);
}


document.querySelectorAll("form[data-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const table = form.dataset.form;
    const id = form.elements.namedItem("id").value;

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
  const recordTabButton = event.target.closest("[data-record-tab]");
  const quickActionButton = event.target.closest("[data-quick-action]");
  const shortcutButton = event.target.closest("[data-shortcut-table]");
  const aiMealAnalyzeButton = event.target.closest("[data-ai-meal-analyze]");
  const aiMealApplyButton = event.target.closest("[data-ai-meal-apply]");
  const reportModuleButton = event.target.closest("[data-report-module]");
  const reportRangeButton = event.target.closest("[data-report-days]");
  const driveBackupButton = event.target.closest("[data-drive-backup]");

  if (tabButton) {
    activateTab(tabButton.dataset.tab);
  }

  if (recordTabButton) {
    activateRecordTab(recordTabButton.dataset.recordTab);
  }

  if (quickActionButton) {
    const target = quickActionButton.dataset.quickAction;
    activateTab("records");
    activateRecordTab(target);
    document.querySelector(`[data-form="${target}"]`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  if (shortcutButton) {
    const form = document.querySelector(`[data-form="${shortcutButton.dataset.shortcutTable}"]`);
    const field = shortcutButton.dataset.shortcutField;
    const control = form?.elements.namedItem(field);
    if (control) {
      control.value = shortcutButton.dataset.shortcutValue || "";
      control.focus();
    }
  }

  if (aiMealAnalyzeButton) {
    analyzeMeal(aiMealAnalyzeButton).catch((error) => showToast(error.message));
  }

  if (aiMealApplyButton) {
    applyMealAnalysis(aiMealApplyButton);
  }

  if (reportModuleButton) {
    state.reportModule = reportModuleButton.dataset.reportModule || "bowel";
    loadReport(state.date || dateInput.value || today()).catch((error) => showToast(error.message));
  }

  if (reportRangeButton) {
    state.reportDays = Number(reportRangeButton.dataset.reportDays) || 7;
    loadReport(state.date || dateInput.value || today()).catch((error) => showToast(error.message));
  }

  if (driveBackupButton) {
    triggerDriveBackup(driveBackupButton).catch((error) => showToast(error.message));
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
    const confirmed = window.confirm(`确定删除这条${tableLabels[table]}记录吗？`);
    if (!confirmed) return;
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


dateInput.addEventListener("change", () => {
  loadDay().catch((error) => showToast(error.message));
});


initialize().catch((error) => showToast(error.message));


async function analyzeMeal(button) {
  const form = document.querySelector('[data-form="meals"]');
  const resultBox = document.querySelector("[data-ai-meal-result]");
  if (!form || !resultBox) return;

  const foodsControl = getFormControl(form, "foods");
  const photoInput = getFormControl(form, "photo");
  const text = foodsControl?.value.trim() || "";
  const photoFile = photoInput?.files?.[0];
  if (!text && !photoFile) {
    throw new Error("请先上传照片或填写文字描述");
  }

  button.disabled = true;
  button.textContent = "识别中...";
  resultBox.hidden = false;
  resultBox.innerHTML = '<div class="empty">正在调用 OpenAI 识别饮食...</div>';

  try {
    const payload = { text };
    if (photoFile) {
      payload.photo_filename = photoFile.name;
      payload.photo_data_url = await fileToDataUrl(photoFile);
    }

    const response = await requestJson("/api/ai/meals/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderMealAnalysis(response.analysis || {});
    showToast("饮食识别完成，请检查后应用");
  } finally {
    button.disabled = false;
    button.textContent = "AI 识别饮食";
  }
}


async function triggerDriveBackup(button) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "备份中...";
  try {
    const payload = await requestJson("/api/admin/backups/drive", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const backup = payload.backup || {};
    showToast(`已备份到 Drive：${backup.file_name || "完成"}`);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}


function renderMealAnalysis(analysis) {
  const resultBox = document.querySelector("[data-ai-meal-result]");
  if (!resultBox) return;
  const visibleFoods = analysis.visible_foods || [];
  const possibleIngredients = analysis.possible_ingredients || [];
  const foodsText = analysis.foods_text || "";
  resultBox.hidden = false;
  resultBox.innerHTML = `
    <div class="ai-meal-card">
      <div>
        <span>识别结果</span>
        <strong>${escapeHtml(foodsText || "未识别到明确食物")}</strong>
      </div>
      <dl>
        <div><dt>可见食物</dt><dd>${escapeHtml(visibleFoods.join("、") || "暂无")}</dd></div>
        <div><dt>可能配料</dt><dd>${escapeHtml(possibleIngredients.join("、") || "暂无")}</dd></div>
        <div><dt>餐别猜测</dt><dd>${escapeHtml(analysis.meal_type_guess || "不确定")}</dd></div>
        <div><dt>置信度</dt><dd>${escapeHtml(analysis.confidence || "-")}</dd></div>
        <div><dt>检查提示</dt><dd>${escapeHtml(analysis.review_notes || "请人工确认。")}</dd></div>
      </dl>
      <button type="button" data-ai-meal-apply data-foods="${escapeHtml(foodsText)}" data-meal-type="${escapeHtml(analysis.meal_type_guess || "")}">
        应用到文字描述
      </button>
    </div>
  `;
}


function applyMealAnalysis(button) {
  const form = document.querySelector('[data-form="meals"]');
  if (!form) return;
  const foods = button.dataset.foods || "";
  const mealType = button.dataset.mealType || "";
  const foodsControl = getFormControl(form, "foods");
  if (foodsControl && foods) {
    foodsControl.value = foods;
  }
  if (mealType && mealType !== "不确定") {
    const mealTypeControl = [...form.querySelectorAll('[name="meal_type"]')].find(
      (control) => control.value === mealType,
    );
    if (mealTypeControl) mealTypeControl.checked = true;
  }
  showToast("已应用识别结果，请检查后保存");
}
