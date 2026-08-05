(() => {
  const form = document.querySelector('.announcement-enterprise-form');
  if (!form) return;
  const title = form.querySelector('#id_title');
  const content = form.querySelector('#id_content');
  const file = form.querySelector('#id_attachment');
  const zone = form.querySelector('[data-upload-zone]');
  const selected = form.querySelector('[data-selected-file]');
  const save = form.querySelector('[data-save-button]');
  const status = form.querySelector('[data-form-status]');

  const updateCount = (field, suffix, max) => {
    const counter = form.querySelector(`[data-count="${field?.id}"]`);
    if (counter && field) counter.textContent = max ? `${field.value.length} / ${max}` : `${field.value.length} ${suffix}`;
  };
  const update = () => {
    const titleReady = (title?.value.trim().length || 0) >= 5;
    const contentReady = (content?.value.trim().length || 0) >= 10;
    const ready = titleReady && contentReady;
    title?.closest('.form-field')?.classList.toggle('has-error', Boolean(title?.value) && !titleReady);
    content?.closest('.form-field')?.classList.toggle('has-error', Boolean(content?.value) && !contentReady);
    if (save) save.disabled = !ready;
    if (status) status.textContent = ready ? 'البيانات مكتملة وجاهزة للحفظ.' : (!titleReady ? 'أدخل عنوانًا لا يقل عن 5 أحرف.' : 'أدخل محتوى لا يقل عن 10 أحرف.');
    updateCount(title, '', 200); updateCount(content, 'حرف');
  };
  const showFile = () => {
    const item = file?.files?.[0];
    if (!selected) return;
    selected.hidden = !item;
    if (item) selected.textContent = `${item.name} · ${(item.size / 1024 / 1024).toFixed(2)} MB`;
  };
  zone?.addEventListener('click', () => file?.click());
  ['dragenter','dragover'].forEach(name => zone?.addEventListener(name, e => { e.preventDefault(); zone.classList.add('is-dragging'); }));
  ['dragleave','drop'].forEach(name => zone?.addEventListener(name, e => { e.preventDefault(); zone.classList.remove('is-dragging'); }));
  zone?.addEventListener('drop', e => { if (file && e.dataTransfer.files.length) { file.files = e.dataTransfer.files; showFile(); } });
  file?.addEventListener('change', showFile);
  [title, content].forEach(el => el?.addEventListener('input', update));
  form.addEventListener('submit', () => { if (save) { save.disabled = true; save.textContent = 'جارٍ الحفظ...'; } });
  update(); showFile();
})();
