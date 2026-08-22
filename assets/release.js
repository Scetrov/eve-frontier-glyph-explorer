(() => {
  'use strict';

  const releaseCommit = document.getElementById('release-commit');
  if (!releaseCommit) return;

  const repositoryUrl = 'https://github.com/Scetrov/eve-frontier-glyph-explorer';
  fetch('data/release.json', { cache: 'no-store' })
    .then(response => response.ok ? response.json() : null)
    .then(release => {
      if (!release || !/^[0-9a-f]{40}$/i.test(release.commit || '')) return;
      const shortCommit = /^[0-9a-f]{7,40}$/i.test(release.short_commit || '')
        ? release.short_commit.slice(0, 7)
        : release.commit.slice(0, 7);
      releaseCommit.textContent = shortCommit;
      releaseCommit.href = `${repositoryUrl}/commit/${release.commit}`;
      releaseCommit.title = release.commit;
    })
    .catch(() => {});
})();
