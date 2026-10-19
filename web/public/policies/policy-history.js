(() => {
  const history = document.querySelector('[data-policy-document]');
  if (!history) return;

  const documentType = history.dataset.policyDocument;
  const fallbackVersion = history.dataset.policyVersion;

  const render = (policy) => {
    const current = policy.versions.find(
      (version) => version.version === policy.currentVersion,
    );
    const currentVersion = history.querySelector('[data-policy-current-version]');
    const list = history.querySelector('[data-policy-version-list]');
    if (!current || !currentVersion || !list) return;

    currentVersion.textContent = `${current.version} 시행`;
    list.replaceChildren();

    [...policy.versions]
      .sort((left, right) => right.version.localeCompare(left.version))
      .forEach((version) => {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = version.path;
      link.textContent = `시행일 ${version.version}`;
      if (version.version === fallbackVersion) {
        link.setAttribute('aria-current', 'page');
      }
      item.append(link);
      if (version.version === policy.currentVersion) {
        const current = document.createElement('span');
        current.className = 'policy-history__current';
        current.textContent = '현재 시행 중';
        item.append(current);
      }
      list.append(item);
      });
  };

  fetch('/policies/manifest.json', { cache: 'no-cache' })
    .then((response) => {
      if (!response.ok) throw new Error('Failed to load policy manifest.');
      return response.json();
    })
    .then((manifest) => {
      const policy = manifest.documents?.[documentType];
      if (policy?.versions?.length) render(policy);
    })
    .catch(() => {
      // The static fallback remains visible when the version index is unavailable.
    });
})();
