export function activateTab(tabName) {
  document.querySelectorAll(".main-nav [data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === tabName);
  });
}


export function activateRecordTab(tabName) {
  document.querySelectorAll("[data-record-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.recordTab === tabName);
  });
  document.querySelectorAll("[data-record-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.recordPanel === tabName);
  });
}
