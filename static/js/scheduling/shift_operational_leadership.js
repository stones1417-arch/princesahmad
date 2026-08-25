document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-shift-leadership]");
  if (!root) return;
  const dialog = root.querySelector("[data-leadership-dialog]");
  let pendingForm = null;
  let pendingValue = null;
  let lastTrigger = null;

  const closeDialog = () => {
    if (dialog.open) dialog.close();
    if (lastTrigger) lastTrigger.focus();
  };
  root.querySelectorAll(".shift-leadership-selector").forEach((form) => {
    const select = form.querySelector("select");
    if (!select) return;
    const initial = form.dataset.currentId || "";
    const save = form.querySelector("[data-save]");
    const reset = form.querySelector("[data-reset]");
    const dirty = form.querySelector(".shift-leadership-selector__dirty");
    const sync = () => {
      const changed = select.value !== initial;
      save.disabled = !changed || !select.value;
      reset.hidden = !changed;
      dirty.textContent = changed ? "تغيير غير محفوظ" : "";
    };
    select.addEventListener("change", sync);
    reset.addEventListener("click", () => { select.value = initial; sync(); select.focus(); });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      pendingForm = form; pendingValue = select.value; lastTrigger = save;
      dialog.querySelector("[data-dialog-title]").textContent = `تغيير ${form.dataset.roleLabel}`;
      dialog.querySelector("[data-dialog-current]").textContent = form.dataset.currentName || "غير معيّن";
      dialog.querySelector("[data-dialog-next]").textContent = select.options[select.selectedIndex].text;
      dialog.querySelector("[data-dialog-copy]").textContent = "سيصبح المسؤول الجديد هو المسؤول التشغيلي لهذه الوظيفة في هذه الوردية.";
      dialog.showModal();
    });
    const remove = form.querySelector("[data-remove]");
    if (remove) remove.addEventListener("click", () => {
      pendingForm = form; pendingValue = ""; lastTrigger = remove;
      dialog.querySelector("[data-dialog-title]").textContent = `إزالة ${form.dataset.roleLabel} من الوردية؟`;
      dialog.querySelector("[data-dialog-current]").textContent = form.dataset.currentName;
      dialog.querySelector("[data-dialog-next]").textContent = "غير معيّن";
      dialog.querySelector("[data-dialog-copy]").textContent = "ستصبح هذه الوظيفة بدون مسؤول حتى يتم تعيين بديل.";
      dialog.showModal();
    });
    sync();
  });
  dialog.querySelector("[data-dialog-cancel]").addEventListener("click", closeDialog);
  dialog.querySelector(".shift-leadership-dialog__close").addEventListener("click", closeDialog);
  dialog.querySelector("[data-dialog-confirm]").addEventListener("click", (event) => {
    if (!pendingForm) return;
    const select = pendingForm.querySelector("select");
    select.value = pendingValue;
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = "جاري الحفظ...";
    pendingForm.querySelector("[data-save]").disabled = true;
    pendingForm.submit();
  });
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); closeDialog(); });
});
