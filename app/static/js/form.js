(() => {
  const form = document.querySelector('[data-recommendation-form]');
  if (!form) return;
  // Copy the live draft at submission time; hidden fields contain only the last render.
  document.querySelectorAll('[data-locale-form]').forEach((localeForm) => {
    localeForm.addEventListener('submit', () => {
      new FormData(form).forEach((value, name) => {
        if (name === 'locale') return;
        const hidden = localeForm.elements.namedItem(name);
        if (hidden) hidden.value = value;
      });
    });
  });
  const controls = form.querySelectorAll('input, select');
  const syncValidity = (control) => {
    if (control.checkValidity()) control.removeAttribute('aria-invalid');
    else control.setAttribute('aria-invalid', 'true');
  };

  controls.forEach((control) => {
    control.addEventListener('invalid', () => syncValidity(control));
    control.addEventListener('input', () => syncValidity(control));
    control.addEventListener('change', () => syncValidity(control));
  });

  form.addEventListener('submit', (event) => {
    if (!form.checkValidity()) {
      event.preventDefault();
      event.stopPropagation();
      form.querySelector(':invalid')?.focus();
    }
    form.classList.add('was-validated');
  });

  const result = document.querySelector('[data-result-kind]');
  if (result && result.dataset.resultKind !== 'idle') {
    document.querySelector('#results-title')?.focus({ preventScroll: false });
  }
})();
