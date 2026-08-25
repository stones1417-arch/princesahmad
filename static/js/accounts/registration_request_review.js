(function () {
  "use strict";
  const root = document.querySelector("[data-account-review]");
  if (!root) return;
  let activeDialog = null;
  let returnFocus = null;
  const approvalButton = root.querySelector('[data-open-dialog="approval-dialog"]');
  const sections = Array.from(root.querySelectorAll('input[name="operational_section"]'));
  const roles = Array.from(root.querySelectorAll('input[name="role_code"]'));
  const verificationPasses = root.dataset.verificationPasses === "true";

  function selected(items) { return items.find((item) => item.checked); }
  function updateSummary() {
    const section = selected(sections);
    const role = selected(roles);
    const sectionText = section ? section.nextElementSibling.querySelector("b").textContent.trim() : "لم يحدد بعد";
    const roleText = role ? role.dataset.roleName : "لم يحدد بعد";
    root.querySelectorAll("[data-summary-section],[data-dialog-section]").forEach((node) => { node.textContent = sectionText; });
    root.querySelectorAll("[data-summary-role],[data-dialog-role]").forEach((node) => { node.textContent = roleText; });
    if (approvalButton) approvalButton.disabled = !(verificationPasses && section && role);
  }
  function closeDialog() {
    if (!activeDialog) return;
    activeDialog.hidden = true;
    document.body.classList.remove("account-review-dialog-open");
    activeDialog = null;
    if (returnFocus) returnFocus.focus();
  }
  root.querySelectorAll("[data-open-dialog]").forEach((button) => button.addEventListener("click", () => {
    const dialog = document.getElementById(button.dataset.openDialog);
    if (!dialog || button.disabled) return;
    returnFocus = button; activeDialog = dialog; dialog.hidden = false;
    document.body.classList.add("account-review-dialog-open");
    const focusTarget = dialog.querySelector("textarea, button");
    if (focusTarget) focusTarget.focus();
  }));
  root.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", closeDialog));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDialog(); });
  sections.concat(roles).forEach((input) => input.addEventListener("change", updateSummary));
  root.querySelectorAll("form").forEach((form) => form.addEventListener("submit", (event) => {
    const button = event.submitter || form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    button.disabled = true;
    if (button.dataset.submitLabel) button.textContent = button.dataset.submitLabel;
  }));
  updateSummary();
}());
