(() => {
  const adminForms = document.querySelectorAll('[data-admin-submit]');
  adminForms.forEach((adminForm) => {
    adminForm.addEventListener('submit', (event) => {
      const fileInput = adminForm.querySelector('input[type="file"]');
      const error = adminForm.querySelector('[data-file-error]');
      if (fileInput && error) {
        const file = fileInput.files[0];
        const message = file && file.size > 1048576 ? error.dataset.sizeError
          : file && !file.name.toLowerCase().endsWith('.csv') ? error.dataset.typeError : '';
        error.textContent = message;
        error.hidden = !message;
        if (message) {
          event.preventDefault();
          fileInput.setAttribute('aria-invalid', 'true');
          fileInput.focus();
          return;
        }
        fileInput.removeAttribute('aria-invalid');
      }
      if (!adminForm.checkValidity()) {
        event.preventDefault();
        adminForm.reportValidity();
        return;
      }
      const button = adminForm.querySelector('[data-admin-submit-button]');
      if (button) button.disabled = true;
      adminForm.setAttribute('aria-busy', 'true');
      adminForm.querySelector('[data-admin-spinner]')?.classList.remove('d-none');
    });
  });
  window.addEventListener('pageshow', () => {
    adminForms.forEach((adminForm) => {
      adminForm.removeAttribute('aria-busy');
      const button = adminForm.querySelector('[data-admin-submit-button]');
      if (button) button.disabled = false;
      adminForm.querySelector('[data-admin-spinner]')?.classList.add('d-none');
    });
  });

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
