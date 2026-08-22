(() => {
  'use strict';

  const data = window.CYCLE_DATA;
  const target = document.getElementById('cycle-table-body');
  const count = document.getElementById('cycle-count');
  if (!target || !Array.isArray(data?.cycles)) return;

  const exactUtc = value => String(value).replace('T', ' ').replace('+00:00', ' UTC');
  const noteFor = cycle => {
    if (cycle.Name === 'Era 6, Cycle 2') return 'Ends one second before the confirmed noon UTC cutover.';
    if (cycle.Name === 'Era 6, Cycle 3') return 'Starts at the confirmed noon UTC cutover.';
    if (cycle.Name === 'Era 6, Cycle 5') return 'Ends one second before the confirmed noon UTC cutover.';
    if (cycle.Name === 'Era 6, Cycle 6') return 'Open-ended. Supplied short name repeats e6c5.';
    return '—';
  };

  data.cycles.forEach(cycle => {
    const row = document.createElement('tr');
    if (cycle.EndDateTime.startsWith('9999-')) row.classList.add('cycle-current');
    const cells = [cycle.Name, cycle.ShortName, exactUtc(cycle.StartDateTime), exactUtc(cycle.EndDateTime), noteFor(cycle)];
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

  if (count) count.textContent = `${data.cycles.length} intervals`;
})();
