(() => {
  'use strict';

  const data = window.CYCLE_DATA;
  const target = document.getElementById('cycle-table-body');
  const count = document.getElementById('cycle-count');
  const searchInput = document.getElementById('cycle-search');
  if (!target || !Array.isArray(data?.cycles)) return;

  const exactUtc = value => String(value).replace('T', ' ').replace('+00:00', ' UTC');
  const noteFor = cycle => {
    if (cycle.Name === 'Era 6, Cycle 6') return cycle.EndStatus || 'Expected September 2026; exact UTC cutover unconfirmed.';
    return '—';
  };

  function renderRows(filterText = '') {
    target.replaceChildren();
    const query = filterText.trim().toLowerCase();
    const matches = data.cycles.filter(cycle => {
      if (!query) return true;
      const haystack = [
        cycle.Name,
        cycle.ShortName,
        cycle.StartDateTime,
        cycle.EndDateTime,
        cycle.EndStatus || '',
        noteFor(cycle)
      ].join(' ').toLowerCase();
      return haystack.includes(query);
    });

    if (!matches.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 5;
      cell.style.textAlign = 'center';
      cell.style.padding = '32px 16px';
      cell.style.color = 'var(--muted)';
      cell.textContent = `No cycles match "${filterText}".`;
      row.appendChild(cell);
      target.appendChild(row);
      if (count) count.textContent = '0 intervals';
      return;
    }

    matches.forEach(cycle => {
      const row = document.createElement('tr');
      if (cycle.EndDateTime.startsWith('9999-')) row.classList.add('cycle-current');
      const end = cycle.EndDateTime.startsWith('9999-') ? 'September 2026 · TBC' : exactUtc(cycle.EndDateTime);
      const cells = [cycle.Name, cycle.ShortName, exactUtc(cycle.StartDateTime), end, noteFor(cycle)];
      cells.forEach((value, index) => {
        const cell = document.createElement('td');
        if (index === 1) {
          const code = document.createElement('code');
          code.textContent = value;
          cell.append(code);
        } else {
          cell.textContent = value;
        }
        row.append(cell);
      });
      target.append(row);
    });

    if (count) count.textContent = `${matches.length} interval${matches.length === 1 ? '' : 's'}`;
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => renderRows(searchInput.value));
  }

  renderRows();
})();
