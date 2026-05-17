import { requestJson } from "./api.js";
import { tableLabels, trackingTables } from "./constants.js";
import {
  collectFormData,
  collectMedicationPayloads,
  fillForm,
  resetForm,
  setEmptyFormDefaults,
} from "./forms.js";
import { activateRecordTab, activateTab } from "./navigation.js";
import {
  populateMealLocations,
  populateMedicationPickers,
  renderList,
  renderSummary,
} from "./records.js";
import { loadReport } from "./reports.js";
import { state } from "./state.js";
import { showToast, today } from "./utils.js";


const dateInput = document.querySelector("#selected-date");


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
  const reportModuleButton = event.target.closest("[data-report-module]");
  const reportRangeButton = event.target.closest("[data-report-days]");

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

  if (reportModuleButton) {
    state.reportModule = reportModuleButton.dataset.reportModule || "bowel";
    loadReport(state.date || dateInput.value || today()).catch((error) => showToast(error.message));
  }

  if (reportRangeButton) {
    state.reportDays = Number(reportRangeButton.dataset.reportDays) || 7;
    loadReport(state.date || dateInput.value || today()).catch((error) => showToast(error.message));
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


dateInput.value = today();
loadDay().catch((error) => showToast(error.message));
