(() => {
  const form = document.querySelector('.wizard-form');
  if (!form) return;
  const type = form.querySelector('#id_report_type');
  const shift = form.querySelector('#id_shift_plan');
  const summary = form.querySelector('#id_summary');
  const recommendations = form.querySelector('#id_recommendations');
  const manualSections = form.querySelectorAll('.manual-fields');
  const operationalSection = form.querySelector('.operational-info');
  const submit = form.querySelector('[data-submit-button]');
  const status = form.querySelector('[data-submit-status]');
  const steps = Object.fromEntries([...form.querySelectorAll('[data-step]')].map(el => [el.dataset.step, el]));
  const progress = form.querySelector('[data-progress-bar]');

  const textPresent = () => Boolean(summary?.value.trim() || recommendations?.value.trim());
  const setStep = (name, state) => {
    const el = steps[name]; if (!el) return;
    el.classList.toggle('active', state === 'active');
    el.classList.toggle('complete', state === 'complete');
  };
  const updateCounter = (field) => {
    if (!field) return;
    const counter = form.querySelector(`[data-counter="${field.id}"]`);
    if (counter) counter.textContent = `${field.value.length} / 2000`;
  };
  const update = () => {
    const manual = type?.value === 'manual';
    manualSections.forEach(el => el.hidden = !manual);
    if (operationalSection) operationalSection.hidden = manual;
    if (shift) { shift.disabled = manual; shift.required = !manual; }
    const shiftReady = manual || Boolean(shift?.value);
    const contentReady = manual ? textPresent() : shiftReady;
    const ready = Boolean(type?.value && shiftReady && contentReady);
    setStep('type', type?.value ? 'complete' : 'active');
    setStep('shift', shiftReady ? 'complete' : (type?.value ? 'active' : ''));
    setStep('content', contentReady ? 'complete' : (shiftReady ? 'active' : ''));
    setStep('save', ready ? 'active' : '');
    const completed = [Boolean(type?.value), shiftReady, contentReady, ready].filter(Boolean).length;
    if (progress) progress.style.width = `${Math.max(25, completed * 25)}%`;
    if (submit) submit.disabled = !ready;
    if (status) status.textContent = ready ? 'اكتملت البيانات الأساسية. سيتم إنشاء التقرير كمسودة موثقة باسمك.' : (manual ? 'أدخل ملخصًا تنفيذيًا أو توصية واحدة على الأقل.' : 'اختر وردية منتهية ومتاحة لإكمال التقرير التشغيلي.');
    updateCounter(summary); updateCounter(recommendations);
  };
  [type, shift, summary, recommendations].forEach(el => { el?.addEventListener('change', update); el?.addEventListener('input', update); });
  form.addEventListener('submit', () => { if (submit) { submit.disabled = true; submit.querySelector('span').textContent = 'جارٍ إنشاء التقرير...'; } });
  update();
})();
