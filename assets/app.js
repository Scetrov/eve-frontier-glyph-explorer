(() => {
  'use strict';

  const data = window.GLYPH_DATA;
  if (!data || !Array.isArray(data.glyphs)) {
    document.body.innerHTML = '<main class="empty-state">Catalogue data could not be loaded.</main>';
    return;
  }

  const glyphs = data.glyphs;
  const repositoryUrl = 'https://github.com/Scetrov/eve-frontier-glyph-explorer';
  const evidence = Array.isArray(window.GLYPH_EVIDENCE) ? window.GLYPH_EVIDENCE : [];
  const hybridGeometryReview = Array.isArray(window.MANUAL_HYBRID_GEOMETRY_REVIEW?.records)
    ? window.MANUAL_HYBRID_GEOMETRY_REVIEW.records
    : [];
  const officialArtifactIndex = window.OFFICIAL_ARTIFACT_INDEX && typeof window.OFFICIAL_ARTIFACT_INDEX === 'object'
    ? window.OFFICIAL_ARTIFACT_INDEX
    : {};
  const cellAudits = Array.isArray(window.GLYPH_CELL_AUDIT?.audits) ? window.GLYPH_CELL_AUDIT.audits : [];
  const evidenceByGlyph = new Map();
  evidence.forEach(item => {
    const glyphId = Number(item.glyph_id);
    if (!evidenceByGlyph.has(glyphId)) evidenceByGlyph.set(glyphId, []);
    evidenceByGlyph.get(glyphId).push(item);
  });
  const hybridGeometryByEvidence = new Map();
  hybridGeometryReview.forEach(item => {
    hybridGeometryByEvidence.set(`${item.recording}|${item.ordinal}|${item.frame}|${item.source_video}`, item);
  });
  const byId = new Map(glyphs.map(glyph => [Number(glyph.id), glyph]));
  const sequences = data.sequences.map(row => ({
    ...row,
    ids: String(row.glyph_ids).trim().split(/\s+/).filter(Boolean).map(Number)
  }));
  const sequenceByRecording = new Map(sequences.map(row => [row.recording, row]));
  const carrierCells = new Set([
    4, 12, 13, 14, 20, 21, 23, 24, 28, 29, 33, 34, 36, 37,
    43, 44, 46, 47, 51, 52, 56, 57, 59, 60, 66, 67, 68, 76
  ]);
  const auditedCarrierCells = new Set([24, 47]);
  const svgNamespace = 'http://www.w3.org/2000/svg';

  const rootStyle = getComputedStyle(document.documentElement);
  const palette = {
    background: rootStyle.getPropertyValue('--void-soft').trim() || '#151514',
    inactive: rootStyle.getPropertyValue('--line').trim() || '#40403b',
    active: rootStyle.getPropertyValue('--signal').trim() || '#ff4700',
    activeBright: rootStyle.getPropertyValue('--signal-bright').trim() || '#fe6b2e',
    cold: rootStyle.getPropertyValue('--cold').trim() || '#fafae5',
    frame: rootStyle.getPropertyValue('--line-bright').trim() || '#6f6f66',
    text: rootStyle.getPropertyValue('--text').trim() || '#fafae5'
  };

  const elements = {
    grid: document.getElementById('glyph-grid'),
    resultCount: document.getElementById('result-count'),
    search: document.getElementById('search'),
    filter: document.getElementById('filter'),
    sort: document.getElementById('sort'),
    carrier: document.getElementById('carrier-toggle'),
    title: document.getElementById('inspector-title'),
    quality: document.getElementById('quality-tag'),
    selectedCanvas: document.getElementById('selected-canvas'),
    selectedStats: document.getElementById('selected-stats'),
    recordingList: document.getElementById('recording-list'),
    evidenceCount: document.getElementById('evidence-count'),
    evidenceList: document.getElementById('evidence-list'),
    contextList: document.getElementById('context-list'),
    nearList: document.getElementById('near-list'),
    copyFingerprint: document.getElementById('copy-fingerprint'),
    copyStatus: document.getElementById('copy-status'),
    permalink: document.getElementById('permalink'),
    reportGlyph: document.getElementById('report-glyph'),
    compareLeft: document.getElementById('compare-left'),
    compareRight: document.getElementById('compare-right'),
    compareLeftCanvas: document.getElementById('compare-left-canvas'),
    compareRightCanvas: document.getElementById('compare-right-canvas'),
    compareDiffCanvas: document.getElementById('compare-diff-canvas'),
    compareLeftTitle: document.getElementById('compare-left-title'),
    compareRightTitle: document.getElementById('compare-right-title'),
    compareSummary: document.getElementById('compare-summary'),
    recordingSelect: document.getElementById('recording-select'),
    sequenceMeta: document.getElementById('sequence-meta'),
    sequenceStrip: document.getElementById('sequence-strip'),
    analysisMetrics: document.getElementById('analysis-metrics'),
    repeatedBlocks: document.getElementById('repeated-blocks'),
    heatmap: document.getElementById('cell-heatmap'),
    cellReview: document.getElementById('cell-review'),
    cellReviewTitle: document.getElementById('cell-review-title'),
    cellReviewSummary: document.getElementById('cell-review-summary'),
    cellPatternCount: document.getElementById('cell-pattern-count'),
    cellPatternList: document.getElementById('cell-pattern-list'),
    cellEvidenceCount: document.getElementById('cell-evidence-count'),
    cellEvidenceList: document.getElementById('cell-evidence-list'),
    cellEvidenceMore: document.getElementById('cell-evidence-more'),
    reportCell: document.getElementById('report-cell'),
    evidenceDialog: document.getElementById('evidence-dialog'),
    evidenceDialogClose: document.getElementById('evidence-dialog-close'),
    evidenceDialogImage: document.getElementById('evidence-dialog-image'),
    evidenceDialogOverlay: document.getElementById('evidence-dialog-overlay'),
    evidenceDialogSourceCaption: document.getElementById('evidence-dialog-source-caption'),
    evidenceDialogCanonical: document.getElementById('evidence-dialog-canonical'),
    evidenceDialogTitle: document.getElementById('evidence-dialog-title'),
    evidenceDialogAssessment: document.getElementById('evidence-dialog-assessment'),
    evidenceDialogMeta: document.getElementById('evidence-dialog-meta'),
    reportEvidence: document.getElementById('report-evidence')
  };

  const state = {
    selectedId: initialGlyphId(),
    compareLeftId: 40,
    compareRightId: 131,
    carrier: false,
    selectedCell: null,
    cellEvidenceLimit: 48
  };

  function initialGlyphId() {
    const requested = Number(new URLSearchParams(location.search).get('glyph'));
    return byId.has(requested) ? requested : 40;
  }

  function issueUrl(template, title, label, body) {
    const params = new URLSearchParams({ template, title, labels: label, body });
    return `${repositoryUrl}/issues/new?${params.toString()}`;
  }

  function explorerUrl(fragment) {
    return `${location.origin}${location.pathname}${location.search}${fragment}`;
  }

  function setReportLink(element, template, title, label, body) {
    if (!element) return;
    element.href = issueUrl(template, title, label, body);
  }

  function officialArtifactFor(record) {
    return officialArtifactIndex[record.broadcast] || null;
  }

  function officialArtifactMeta(record) {
    const artifact = officialArtifactFor(record);
    if (!artifact) return [];
    const id = escapeText(record.broadcast);
    const url = escapeAttribute(artifact.url);
    return [
      ['Official artifact', `<a href="${url}" target="_blank" rel="noopener">${id} ↗</a>`],
      ['Artifact API record', `${escapeText(artifact.createdAt)} · record time, not broadcast time`]
    ];
  }

  function glyphIssueBody(glyph) {
    return `## What needs review?\n<!-- Describe the suspected pattern, assignment, or provenance issue. -->\n\n## Explorer context\n- Glyph: #${glyph.id}\n- Canonical fingerprint: \`${glyph.fingerprint}\`\n- Active cells: ${glyph.cells || 'none'}\n- Occurrences: ${glyph.occurrences}\n- Verification: ${glyph.verification_status}\n- Explorer URL: ${location.origin}${location.pathname}?glyph=${glyph.id}#atlas`;
  }

  function frameIssueBody(record) {
    const changed = record.difference_cells.length ? record.difference_cells.join(' ') : 'none';
    return `## What appears wrong?\n<!-- Describe the visual discrepancy. Please do not upload source media unless you have permission. -->\n\n## Frame context\n- Matched glyph: #${record.glyph_id}\n- Source video: ${record.source_video}\n- Recording: ${record.recording}\n- Decoded frame: ${record.frame}\n- Timestamp: ${Number(record.time_s).toFixed(4)} seconds\n- Glyph position: ${record.ordinal}\n- Assignment: ${record.assignment_basis}\n- Differing cells: ${changed}\n- Evidence image: ${new URL(record.image, location.href).href}`;
  }

  function cellIssueBody(row, column, matches, auditRows) {
    return `## What needs review?\n<!-- Describe why this cell may be misclassified, active, or carrier-only. -->\n\n## Cell context\n- Grid coordinate: (${row},${column})\n- Active canonical glyphs: ${matches.length ? matches.map(glyph => `#${glyph.id}`).join(', ') : 'none'}\n- Audited corrections: ${auditRows.length ? auditRows.map(audit => `#${audit.glyph_id} (${audit.verdict})`).join(', ') : 'none'}\n- Explorer URL: ${explorerUrl('#analysis')}`;
  }

  function setupCanvas(canvas, logicalSize) {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(logicalSize * ratio);
    canvas.height = Math.round(logicalSize * ratio);
    const context = canvas.getContext('2d');
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.imageSmoothingEnabled = false;
    return context;
  }

  function svgNode(name, attributes = {}) {
    const node = document.createElementNS(svgNamespace, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  function overlayGeometry(record) {
    const centerX = Number(record.overlay_center_x);
    const centerY = Number(record.overlay_center_y);
    const pitch = Number(record.overlay_pitch);
    if (Number.isFinite(centerX) && Number.isFinite(centerY) && Number.isFinite(pitch) && pitch > 0) {
      return { centerX, centerY, pitch, registration: record.overlay_registration || 'unlabelled registration' };
    }
    return null;
  }

  function geometryAssessmentFor(record) {
    return hybridGeometryByEvidence.get(`${record.recording}|${record.ordinal}|${record.frame}|${record.source_video}`) || null;
  }

  function geometryAssessmentKind(assessment) {
    if (!assessment) return 'unavailable';
    if (assessment.operational_consensus) return 'candidate';
    if (String(assessment.operational_status || '').startsWith('rejected:')) return 'rejected';
    if (String(assessment.operational_status || '').startsWith('reviewed reference seed')) return 'seed';
    return 'awaiting';
  }

  function geometryAssessmentLabel(assessment) {
    const labels = {
      candidate: 'GEOMETRY / CANDIDATE',
      rejected: 'GEOMETRY / REJECTED',
      seed: 'GEOMETRY / REFERENCE SEED',
      awaiting: 'GEOMETRY / AWAITING REFERENCE',
      unavailable: 'GEOMETRY / NOT ASSESSED'
    };
    return labels[geometryAssessmentKind(assessment)];
  }

  function measured(value, digits = 4, suffix = '') {
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(digits)}${suffix}` : 'not available';
  }

  function checkSummary(check) {
    if (!check) return 'not evaluated';
    if (!check.usable) return check.reason || 'not usable';
    const residual = measured(check.rms_residual_px, 2, ' px RMS');
    if (Number.isFinite(Number(check.supported_sides_6px))) return `${residual} · ${check.supported_sides_6px}/4 sides supported`;
    if (Number.isFinite(Number(check.weak_boundaries))) return `${residual} · ${check.weak_boundaries} weak boundaries`;
    return residual;
  }

  function renderGeometryAssessment(record) {
    const assessment = geometryAssessmentFor(record);
    const kind = geometryAssessmentKind(assessment);
    if (!assessment) {
      elements.evidenceDialogAssessment.innerHTML = [
        '<div class="assessment-heading"><span>GEOMETRY ASSESSMENT / READ ONLY</span><strong class="assessment-chip assessment-unavailable">NOT ASSESSED</strong></div>',
        '<p>No hybrid geometry assessment is available for this record. The observed-state QA overlay, if present, remains independent of this research ledger.</p>'
      ].join('');
      return;
    }
    const details = [
      ['Assessment', assessment.operational_status || 'not available'],
      ['Decision type', 'deterministic threshold gate · not a probability'],
      ['Review / overlay', `${assessment.review_status || 'pending'} · overlay disabled`],
      ['Reference geometry', assessment.reference_frame === null ? 'awaiting reviewed reference' : `frame ${assessment.reference_frame} · ${assessment.reference_geometry_provenance || 'recorded source seed'}`],
      ['Selected proposal', assessment.proposal_selected || 'none retained'],
      ['Direct / temporal spread', Number.isFinite(Number(assessment.consensus_disagreement_cells)) ? `${measured(assessment.consensus_disagreement_cells, 4, ' cells')} · ${measured(assessment.consensus_disagreement_px, 2, ' px')}` : 'not evaluated'],
      ['Temporal support', Number.isFinite(Number(assessment.minimum_temporal_step_inliers)) ? `${assessment.minimum_temporal_step_inliers} minimum inliers · ${measured(Number(assessment.minimum_temporal_step_inlier_ratio) * 100, 1, '%')}` : 'not evaluated'],
      ['Lattice support', assessment.direct_lattice ? `direct: ${checkSummary(assessment.direct_lattice)} · temporal: ${checkSummary(assessment.temporal_lattice)}` : 'not evaluated'],
      ['Diamond support', assessment.direct_diamond ? `direct: ${checkSummary(assessment.direct_diamond)} · temporal: ${checkSummary(assessment.temporal_diamond)}` : 'not evaluated'],
      ['Verified source', assessment.source_sha256 ? `SHA-256 ${assessment.source_sha256}` : 'not available']
    ];
    elements.evidenceDialogAssessment.innerHTML = [
      `<div class="assessment-heading"><span>GEOMETRY ASSESSMENT / READ ONLY</span><strong class="assessment-chip assessment-${kind}">${escapeText(geometryAssessmentLabel(assessment).replace('GEOMETRY / ', ''))}</strong></div>`,
      '<p>Experimental registration evidence only. It neither changes the corpus tag nor draws a proposed geometry overlay.</p>',
      `<div class="assessment-grid">${details.map(([label, value]) => `<div><span>${escapeText(label)}</span><strong>${escapeText(value)}</strong></div>`).join('')}</div>`
    ].join('');
  }

  function drawEvidenceOverlay(svg, record) {
    if (!svg) return;
    const observed = String(record.observed_fingerprint || '');
    const canonical = String(record.canonical_fingerprint || '');
    const geometry = overlayGeometry(record);
    if (!geometry) {
      svg.replaceChildren();
      svg.setAttribute('aria-label', 'QA cell overlay unavailable: this record has no image registration.');
      return;
    }
    const { centerX, centerY, pitch, registration } = geometry;
    const square = pitch * 0.8;
    let positiveCount = 0;
    let negativeCount = 0;
    let differenceCount = 0;
    const fragment = document.createDocumentFragment();

    for (let index = 0; index < 81; index += 1) {
      const row = Math.floor(index / 9);
      const column = index % 9;
      const excluded = carrierCells.has(index);
      const positive = observed[index] === '1';
      const differs = observed[index] !== canonical[index];
      const x = centerX + (column - 4) * pitch - square / 2;
      const y = centerY + (row - 4) * pitch - square / 2;
      const classes = ['evidence-overlay-cell'];
      if (excluded) classes.push('evidence-overlay-excluded');
      else if (positive) {
        classes.push('evidence-overlay-positive');
        positiveCount += 1;
      } else {
        classes.push('evidence-overlay-negative');
        negativeCount += 1;
      }
      if (differs && !excluded) {
        classes.push('evidence-overlay-difference');
        differenceCount += 1;
      }
      fragment.appendChild(svgNode('rect', {
        x: x.toFixed(2), y: y.toFixed(2), width: square.toFixed(2), height: square.toFixed(2),
        class: classes.join(' '), 'data-cell': `(${row},${column})`
      }));
    }
    svg.replaceChildren(fragment);
    svg.setAttribute('aria-label', `${positiveCount} observed positive payload cells, ${negativeCount} observed negative payload cells, ${differenceCount} differing payload cells; ${registration}.`);
  }

  function createEvidenceImageStage(record) {
    const stage = document.createElement('span');
    stage.className = 'evidence-image-stage';
    const image = document.createElement('img');
    image.src = record.image;
    image.loading = 'lazy';
    image.alt = `Actual frame ${record.frame} from ${record.source_video}`;
    const overlay = svgNode('svg', {
      class: 'evidence-overlay', viewBox: '0 0 480 480', preserveAspectRatio: 'none', 'aria-hidden': 'true'
    });
    drawEvidenceOverlay(overlay, record);
    stage.append(image, overlay);
    return stage;
  }

  function drawGlyph(canvas, glyph, options = {}) {
    const size = options.size || 240;
    const context = setupCanvas(canvas, size);
    const active = new Set(glyph.cell_indices);
    const margin = size * 0.055;
    const usable = size - margin * 2;
    const pitch = usable / 9;
    const square = pitch * 0.68;
    const inset = (pitch - square) / 2;

    context.clearRect(0, 0, size, size);
    if (options.surface !== false) {
      context.fillStyle = palette.background;
      context.fillRect(0, 0, size, size);
    }

    for (let index = 0; index < 81; index += 1) {
      const row = Math.floor(index / 9);
      const column = index % 9;
      const x = margin + column * pitch + inset;
      const y = margin + row * pitch + inset;
      context.fillStyle = active.has(index) ? palette.active : palette.inactive;
      context.fillRect(Math.round(x), Math.round(y), Math.max(1, Math.round(square)), Math.max(1, Math.round(square)));
    }

    if (options.carrier) drawCarrierMask(context, size, margin, usable);
  }

  function drawCarrierMask(context, size, margin, usable) {
    context.save();
    const pitch = usable / 9;
    carrierCells.forEach(index => {
      const row = Math.floor(index / 9);
      const column = index % 9;
      const x = margin + column * pitch;
      const y = margin + row * pitch;
      context.fillStyle = palette.cold;
      context.globalAlpha = auditedCarrierCells.has(index) ? 0.22 : 0.12;
      context.fillRect(x, y, pitch, pitch);
      context.strokeStyle = auditedCarrierCells.has(index) ? palette.active : palette.frame;
      context.globalAlpha = auditedCarrierCells.has(index) ? 0.8 : 0.35;
      context.lineWidth = Math.max(1, size / 240);
      context.strokeRect(x + 0.5, y + 0.5, pitch - 1, pitch - 1);
    });
    context.restore();
  }

  function drawDifference(canvas, leftGlyph, rightGlyph, options = {}) {
    const size = options.size || 240;
    const context = setupCanvas(canvas, size);
    const left = new Set(leftGlyph.cell_indices);
    const right = new Set(rightGlyph.cell_indices);
    const margin = size * 0.055;
    const usable = size - margin * 2;
    const pitch = usable / 9;
    const square = pitch * 0.68;
    const inset = (pitch - square) / 2;
    context.clearRect(0, 0, size, size);
    context.fillStyle = palette.background;
    context.fillRect(0, 0, size, size);

    for (let index = 0; index < 81; index += 1) {
      const row = Math.floor(index / 9);
      const column = index % 9;
      const x = margin + column * pitch + inset;
      const y = margin + row * pitch + inset;
      const inLeft = left.has(index);
      const inRight = right.has(index);
      if (inLeft && inRight) context.fillStyle = palette.frame;
      else if (inLeft) context.fillStyle = palette.cold;
      else if (inRight) context.fillStyle = palette.activeBright;
      else context.fillStyle = palette.inactive;
      context.fillRect(Math.round(x), Math.round(y), Math.max(1, Math.round(square)), Math.max(1, Math.round(square)));
    }
    if (options.carrier) drawCarrierMask(context, size, margin, usable);
  }

  function renderStats() {
    document.getElementById('stat-glyphs').textContent = data.stats.canonical_glyphs;
    document.getElementById('stat-recordings').textContent = data.stats.recordings;
    document.getElementById('stat-occurrences').textContent = data.stats.occurrences.toLocaleString();
    document.getElementById('stat-cells').textContent = `${data.stats.used_grid_cells} / 81`;
  }

  function filteredGlyphs() {
    const query = elements.search.value.trim().toLowerCase().replace(/^#/, '');
    const filter = elements.filter.value;
    const sort = elements.sort.value;
    const rows = glyphs.filter(glyph => {
      const searchText = [
        glyph.id,
        glyph.recordings.join(' '),
        glyph.broadcasts.join(' '),
        glyph.cycles.join(' '),
        glyph.phrases.join(' '),
        glyph.phrase_roles.join(' '),
        glyph.cells
      ].join(' ').toLowerCase();
      if (query && !searchText.includes(query)) return false;
      if (filter === 'repeated' && glyph.occurrences < 2) return false;
      if (filter === 'singletons' && glyph.occurrences !== 1) return false;
      if (filter === 'near' && !glyph.near_twins.some(item => item.distance === 1)) return false;
      if (filter === 'cluster' && glyph.phrases.length === 0) return false;
      if (filter === 'provisional' && glyph.provisional_occurrences === 0) return false;
      return true;
    });
    rows.sort((left, right) => {
      if (sort === 'frequency') return right.occurrences - left.occurrences || left.id - right.id;
      if (sort === 'cells') return right.n_cells - left.n_cells || left.id - right.id;
      if (sort === 'family') return right.family_size - left.family_size || left.family_id - right.family_id || left.id - right.id;
      return left.id - right.id;
    });
    return rows;
  }

  function renderGrid() {
    const rows = filteredGlyphs();
    const fragment = document.createDocumentFragment();
    elements.grid.replaceChildren();
    elements.resultCount.textContent = `${rows.length} glyph${rows.length === 1 ? '' : 's'}`;

    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'No glyphs match the current signal filters.';
      elements.grid.appendChild(empty);
      return;
    }

    rows.forEach(glyph => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'glyph-tile';
      button.dataset.glyphId = glyph.id;
      button.setAttribute('aria-pressed', String(glyph.id === state.selectedId));
      button.setAttribute('aria-label', `Glyph ${glyph.id}, ${glyph.occurrences} occurrences, ${glyph.n_cells} active cells`);
      const canvas = document.createElement('canvas');
      canvas.width = 180;
      canvas.height = 180;
      canvas.setAttribute('aria-hidden', 'true');
      const meta = document.createElement('span');
      meta.className = 'tile-meta';
      meta.innerHTML = `<span class="tile-id">#${glyph.id}</span><span class="tile-count">N=${glyph.occurrences}</span>`;
      button.append(canvas, meta);
      button.addEventListener('click', () => selectGlyph(glyph.id, true));
      drawGlyph(canvas, glyph, { size: 112, carrier: state.carrier });
      fragment.appendChild(button);
    });
    elements.grid.appendChild(fragment);
  }

  function selectGlyph(id, updateAddress = false) {
    const glyph = byId.get(Number(id));
    if (!glyph) return;
    state.selectedId = glyph.id;
    elements.title.textContent = `Glyph #${glyph.id}`;
    elements.quality.textContent = glyph.verification_status.includes('unverified')
      ? 'CORPUS TAG / UNVERIFIED'
      : glyph.provisional_occurrences ? 'CANONICAL + NEW READS' : 'CANONICAL';
    drawGlyph(elements.selectedCanvas, glyph, { size: 330, carrier: state.carrier });
    elements.selectedCanvas.setAttribute('aria-label', `Glyph ${glyph.id}, ${glyph.n_cells} active cells`);

    elements.selectedStats.innerHTML = [
      [glyph.n_cells, 'Active cells'],
      [glyph.occurrences, 'Occurrences'],
      [glyph.recording_count, 'Recordings'],
      [glyph.phrases.length ? glyph.phrases.join(', ') : '—', 'Phrase cluster'],
      [glyph.nearest_neighbour_distance, 'Nearest distance'],
      [`${glyph.family_id} / ${glyph.family_size}`, 'Family / size']
    ].map(([value, label]) => `<div><strong>${value}</strong><span>${label}</span></div>`).join('');

    elements.recordingList.replaceChildren();
    glyph.recordings.forEach(recording => {
      const item = document.createElement('span');
      item.textContent = recording;
      elements.recordingList.appendChild(item);
    });
    if (!glyph.recordings.length) elements.recordingList.textContent = 'No occurrence record';

    renderContexts(glyph);
    renderEvidence(glyph);
    renderNearTwins(glyph);
    elements.permalink.href = `${location.pathname}?glyph=${glyph.id}#atlas`;
    elements.permalink.textContent = `Link to #${glyph.id}`;
    setReportLink(elements.reportGlyph, 'glyph-report.md', `[Glyph] Review #${glyph.id}`, 'report: glyph', glyphIssueBody(glyph));
    state.compareLeftId = glyph.id;
    elements.compareLeft.value = String(glyph.id);
    updateComparison();
    document.querySelectorAll('.glyph-tile').forEach(tile => {
      tile.setAttribute('aria-pressed', String(Number(tile.dataset.glyphId) === glyph.id));
    });

    if (updateAddress) {
      const url = new URL(location.href);
      url.searchParams.set('glyph', glyph.id);
      history.replaceState(null, '', `${url.pathname}${url.search}#atlas`);
    }
  }

  function renderEvidence(glyph) {
    const records = evidenceByGlyph.get(glyph.id) || [];
    elements.evidenceCount.textContent = `${records.length} frame${records.length === 1 ? '' : 's'}`;
    elements.evidenceList.replaceChildren();
    if (!records.length) {
      elements.evidenceList.textContent = 'No source-frame evidence packaged.';
      return;
    }
    const fragment = document.createDocumentFragment();
    records.forEach(record => fragment.appendChild(createEvidenceCard(record, glyph)));
    elements.evidenceList.appendChild(fragment);
  }

  function createEvidenceCard(record, glyph) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `evidence-card${record.assigned_hamming ? ' evidence-card-difference' : ''}`;
    button.setAttribute('aria-label', `${record.source_video}, frame ${record.frame}, matched to glyph ${glyph.id}`);
    const meta = document.createElement('span');
    meta.className = 'evidence-card-meta';
    const source = document.createElement('strong');
    source.textContent = `#${glyph.id} · ${record.source_video}`;
    const reference = document.createElement('span');
    reference.textContent = `FRAME ${String(record.frame).padStart(6, '0')} · T+${Number(record.time_s).toFixed(4)}S`;
    const status = document.createElement('span');
    status.className = 'evidence-card-status';
    status.textContent = record.assigned_hamming
      ? `${record.assigned_hamming} CELL${record.assigned_hamming === 1 ? '' : 'S'} FROM ASSIGNED GLYPH`
      : record.verification_status || 'MATCHES CORPUS TAG';
    const assessment = geometryAssessmentFor(record);
    const geometry = document.createElement('span');
    geometry.className = `evidence-card-assessment assessment-${geometryAssessmentKind(assessment)}`;
    geometry.textContent = geometryAssessmentLabel(assessment);
    meta.append(source, reference, status, geometry);
    button.append(createEvidenceImageStage(record), meta);
    button.addEventListener('click', () => openEvidence(record));
    return button;
  }

  function createAuditEvidenceCard(audit, source) {
    const link = document.createElement('a');
    link.className = 'evidence-card';
    link.href = source.median_image;
    link.target = '_blank';
    link.rel = 'noopener';
    link.setAttribute('aria-label', `${audit.cell} audit median from ${source.source_video}`);
    const image = document.createElement('img');
    image.src = source.median_image;
    image.loading = 'lazy';
    image.alt = `Seven-frame median for ${audit.cell} from ${source.source_video}`;
    const meta = document.createElement('span');
    meta.className = 'evidence-card-meta';
    meta.innerHTML = `<strong>#${audit.glyph_id} · ${escapeText(source.source_video)}</strong><span>FRAMES ${source.frames[0]}–${source.frames.at(-1)} · SHA256 ${source.sha256.slice(0, 12)}…</span><span class="evidence-card-status">${escapeText(audit.verdict)} · SCORE ${Number(source.median_contrast).toFixed(4)}</span>`;
    link.append(image, meta);
    return link;
  }

  function openEvidence(record) {
    const glyph = byId.get(Number(record.glyph_id));
    elements.evidenceDialogTitle.textContent = `${record.source_video} / frame ${record.frame}`;
    elements.evidenceDialogImage.src = record.image;
    elements.evidenceDialogImage.alt = `Actual frame ${record.frame} from ${record.source_video}`;
    drawEvidenceOverlay(elements.evidenceDialogOverlay, record);
    const confidence = record.confidence === null || record.confidence === '' ? Number.NaN : Number(record.confidence);
    const registration = overlayGeometry(record)?.registration === 'detector-ring-fit'
      ? 'detector-ring registration'
      : 'no independently verified image registration';
    elements.evidenceDialogSourceCaption.textContent = Number.isFinite(confidence)
      ? `Observed-state QA overlay · orange: positive · pale dashed: negative · hatched: excluded carrier · detector separation score ${confidence.toFixed(4)} (not a probability) · ${registration}`
      : `Observed-state QA overlay · orange: positive · pale dashed: negative · hatched: excluded carrier · manual tag: no detector score · ${registration}`;
    renderGeometryAssessment(record);
    setReportLink(elements.reportEvidence, 'frame-report.md', `[Frame] ${record.source_video} / frame ${record.frame}`, 'report: frame', frameIssueBody(record));
    drawGlyph(elements.evidenceDialogCanonical, glyph, { size: 440, carrier: true });
    const changed = record.difference_cells.length ? record.difference_cells.join(' ') : 'none';
    const details = [
      ['Matched glyph', `#${record.glyph_id}`],
      ['Source recording', record.recording],
      ['Source file', record.source_video],
      ['Frame reference', `frame ${record.frame} · glyph position ${record.ordinal}`],
      ['Timestamp', `${Number(record.time_s).toFixed(4)} seconds`],
      ['Assignment', record.assignment_basis],
      ['Verification', record.verification_status || 'not independently verified'],
      ['Assigned Hamming', `${record.assigned_hamming} changed cells`],
      ['Differing cells', changed],
      ['Evidence class', record.provisional ? 'provisional automatic read' : 'corpus manual tag']
    ];
    const artifactDetails = officialArtifactMeta(record);
    elements.evidenceDialogMeta.innerHTML = [
      ...details.map(([label, value]) => `<div><span>${escapeText(label)}</span><strong>${escapeText(value)}</strong></div>`),
      ...artifactDetails.map(([label, value]) => `<div><span>${escapeText(label)}</span><strong>${value}</strong></div>`)
    ].join('');
    if (typeof elements.evidenceDialog.showModal === 'function') elements.evidenceDialog.showModal();
    else window.open(record.image, '_blank', 'noopener');
  }

  function renderContexts(glyph) {
    elements.contextList.replaceChildren();
    let rendered = 0;
    for (const sequence of sequences) {
      sequence.ids.forEach((id, index) => {
        if (id !== glyph.id || rendered >= 8) return;
        const row = document.createElement('div');
        row.className = 'context-row';
        const label = document.createElement('span');
        label.textContent = sequence.recording;
        label.title = sequence.recording;
        const tokens = document.createElement('div');
        tokens.className = 'context-tokens';
        const start = Math.max(0, index - 3);
        const end = Math.min(sequence.ids.length, index + 4);
        sequence.ids.slice(start, end).forEach((tokenId, offset) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = `#${tokenId}`;
          if (start + offset === index) button.className = 'current';
          button.addEventListener('click', () => selectGlyph(tokenId, true));
          tokens.appendChild(button);
        });
        row.append(label, tokens);
        elements.contextList.appendChild(row);
        rendered += 1;
      });
      if (rendered >= 8) break;
    }
    if (!rendered) elements.contextList.textContent = 'No sequence context catalogued.';
  }

  function renderNearTwins(glyph) {
    elements.nearList.replaceChildren();
    if (!glyph.near_twins.length) {
      elements.nearList.textContent = 'No glyph within two cells.';
      return;
    }
    glyph.near_twins.forEach(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'near-button';
      button.textContent = `#${item.id} / ${item.distance} cell${item.distance === 1 ? '' : 's'}`;
      button.addEventListener('click', () => selectGlyph(item.id, true));
      elements.nearList.appendChild(button);
    });
  }

  async function copyFingerprint() {
    const glyph = byId.get(state.selectedId);
    try {
      await navigator.clipboard.writeText(glyph.fingerprint);
      elements.copyStatus.textContent = 'Fingerprint copied to clipboard.';
    } catch {
      const temporary = document.createElement('textarea');
      temporary.value = glyph.fingerprint;
      temporary.style.position = 'fixed';
      temporary.style.opacity = '0';
      document.body.appendChild(temporary);
      temporary.select();
      document.execCommand('copy');
      temporary.remove();
      elements.copyStatus.textContent = 'Fingerprint copied to clipboard.';
    }
    window.setTimeout(() => { elements.copyStatus.textContent = ''; }, 2200);
  }

  function populateComparators() {
    const options = glyphs.map(glyph => `<option value="${glyph.id}">#${glyph.id} · ${glyph.n_cells} cells · N=${glyph.occurrences}</option>`).join('');
    elements.compareLeft.innerHTML = options;
    elements.compareRight.innerHTML = options;
    elements.compareLeft.value = String(state.compareLeftId);
    elements.compareRight.value = String(state.compareRightId);
  }

  function updateComparison() {
    state.compareLeftId = Number(elements.compareLeft.value);
    state.compareRightId = Number(elements.compareRight.value);
    const left = byId.get(state.compareLeftId);
    const right = byId.get(state.compareRightId);
    if (!left || !right) return;
    elements.compareLeftTitle.textContent = `#${left.id}`;
    elements.compareRightTitle.textContent = `#${right.id}`;
    drawGlyph(elements.compareLeftCanvas, left, { size: 280, carrier: state.carrier });
    drawGlyph(elements.compareRightCanvas, right, { size: 280, carrier: state.carrier });
    drawDifference(elements.compareDiffCanvas, left, right, { size: 280, carrier: state.carrier });
    const leftCells = new Set(left.cell_indices);
    const rightCells = new Set(right.cell_indices);
    const onlyLeft = [...leftCells].filter(cell => !rightCells.has(cell));
    const onlyRight = [...rightCells].filter(cell => !leftCells.has(cell));
    const distance = onlyLeft.length + onlyRight.length;
    const format = cells => cells.length ? cells.map(cell => `(${Math.floor(cell / 9)},${cell % 9})`).join(' ') : 'none';
    elements.compareSummary.textContent = `${distance} changed cell${distance === 1 ? '' : 's'} · only #${left.id}: ${format(onlyLeft)} · only #${right.id}: ${format(onlyRight)}`;
  }

  function populateSequences() {
    const sorted = [...sequences].sort((left, right) => left.recording.localeCompare(right.recording, undefined, { numeric: true }));
    elements.recordingSelect.innerHTML = sorted.map(row => `<option value="${escapeAttribute(row.recording)}">${escapeText(row.recording)}</option>`).join('');
    const preferred = sequenceByRecording.has('E6C6-21') ? 'E6C6-21' : sorted[0].recording;
    elements.recordingSelect.value = preferred;
    renderSequence(preferred);
  }

  function renderSequence(recording) {
    const sequence = sequenceByRecording.get(recording);
    if (!sequence) return;
    const artifact = officialArtifactFor(sequence);
    elements.sequenceMeta.innerHTML = [
      `<span><strong>${sequence.n_glyphs}</strong> glyphs</span>`,
      `<span><strong>${escapeText(sequence.cycle)}</strong> cycle</span>`,
      `<span><strong>${escapeText(sequence.track)}</strong> track</span>`,
      `<span><strong>${escapeText(sequence.source)}</strong></span>`,
      artifact ? `<span><a href="${escapeAttribute(artifact.url)}" target="_blank" rel="noopener">Official artifact ${escapeText(sequence.broadcast)} ↗</a></span>` : '',
      sequence.uncertain_gt2 ? `<span><strong>${sequence.uncertain_gt2}</strong> reads &gt;2 cells away</span>` : ''
    ].join('');
    const fragment = document.createDocumentFragment();
    sequence.ids.forEach((id, index) => {
      const glyph = byId.get(id);
      if (!glyph) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `sequence-token${String(sequence.source).startsWith('provisional') ? ' provisional' : ''}`;
      button.setAttribute('aria-label', `Position ${index + 1}, glyph ${id}`);
      const canvas = document.createElement('canvas');
      const label = document.createElement('span');
      label.textContent = `${String(index + 1).padStart(2, '0')} / #${id}`;
      button.append(canvas, label);
      button.addEventListener('click', () => {
        selectGlyph(id, true);
        document.getElementById('inspector').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      drawGlyph(canvas, glyph, { size: 72, carrier: state.carrier });
      fragment.appendChild(button);
    });
    elements.sequenceStrip.replaceChildren(fragment);
  }

  function renderAnalysis() {
    const metrics = [
      [data.stats.token_entropy_bits.toFixed(2), 'Bits per token', `${(data.stats.normalised_entropy * 100).toFixed(1)}% of maximum`],
      [data.stats.index_of_coincidence.toFixed(4), 'Index of coincidence', 'Low for plaintext substitution'],
      [data.stats.distance_one_pairs, 'One-cell pairs', 'Potential selector variants'],
      [data.stats.adjacent_mean_hamming.toFixed(2), 'Adjacent Hamming distance', `Random pairs: ${data.stats.all_pair_mean_hamming.toFixed(2)}`]
    ];
    elements.analysisMetrics.innerHTML = metrics.map(([value, label, note]) => `<article><strong>${value}</strong><span>${label}</span><small>${note}</small></article>`).join('');

    const fragment = document.createDocumentFragment();
    data.repeated_blocks.slice(0, 8).forEach((block, index) => {
      const row = document.createElement('div');
      row.className = 'block-row';
      const rank = document.createElement('div');
      rank.className = 'block-rank';
      rank.textContent = `${String(index + 1).padStart(2, '0')} / L${block.length} / N${block.n_broadcasts}`;
      const tokens = document.createElement('div');
      tokens.className = 'block-tokens';
      block.glyph_ids.forEach(id => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = `#${id}`;
        button.addEventListener('click', () => selectGlyph(id, true));
        tokens.appendChild(button);
      });
      const videos = document.createElement('div');
      videos.className = 'block-videos';
      videos.textContent = block.broadcasts.join(' · ');
      row.append(rank, tokens, videos);
      fragment.appendChild(row);
    });
    elements.repeatedBlocks.replaceChildren(fragment);
    renderCellHeatmap();
  }

  function renderCellHeatmap() {
    const usage = data.cell_usage;
    const maximum = Math.max(...usage);
    const fragment = document.createDocumentFragment();
    elements.heatmap.replaceChildren();
    for (let index = 0; index < 81; index += 1) {
      const row = Math.floor(index / 9);
      const column = index % 9;
      const value = usage[index];
      const strength = maximum ? value / maximum : 0;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'heatmap-cell';
      button.dataset.cellIndex = index;
      button.setAttribute('role', 'gridcell');
      button.setAttribute('aria-label', `Cell row ${row}, column ${column}: active in ${value} canonical glyph${value === 1 ? '' : 's'}`);
      button.setAttribute('aria-selected', String(index === state.selectedCell));
      button.title = `(${row},${column}) · ${value} canonical glyph${value === 1 ? '' : 's'}`;
      button.style.setProperty('--cell-strength', value ? String(0.13 + strength * 0.87) : '0');
      button.classList.toggle('heatmap-cell-empty', value === 0);
      button.classList.toggle('heatmap-cell-carrier', carrierCells.has(index));
      button.classList.toggle('heatmap-cell-audited', auditedCarrierCells.has(index));
      const count = document.createElement('strong');
      count.textContent = value;
      const coordinate = document.createElement('span');
      coordinate.textContent = `${row},${column}`;
      button.append(count, coordinate);
      button.addEventListener('click', () => selectCell(index));
      fragment.appendChild(button);
    }
    elements.heatmap.appendChild(fragment);
  }

  function selectCell(index, resetLimit = true) {
    state.selectedCell = index;
    if (resetLimit) state.cellEvidenceLimit = 48;
    elements.heatmap.querySelectorAll('.heatmap-cell').forEach(button => {
      button.setAttribute('aria-selected', String(Number(button.dataset.cellIndex) === index));
    });
    renderCellReview();
  }

  function renderCellReview() {
    const index = state.selectedCell;
    if (!Number.isInteger(index)) return;
    const row = Math.floor(index / 9);
    const column = index % 9;
    const matches = glyphs.filter(glyph => glyph.cell_indices.includes(index));
    const auditRows = cellAudits.filter(audit => audit.cell === `(${row},${column})`);
    const auditSources = auditRows.flatMap(audit => audit.sources.map(source => ({ audit, source })));
    const matchIds = new Set(matches.map(glyph => glyph.id));
    const records = evidence
      .filter(record => matchIds.has(Number(record.glyph_id)))
      .sort((left, right) => Number(left.glyph_id) - Number(right.glyph_id)
        || left.recording.localeCompare(right.recording, undefined, { numeric: true })
        || Number(left.ordinal) - Number(right.ordinal));

    elements.cellReview.hidden = false;
    elements.cellReviewTitle.textContent = `Cell (${row},${column})`;
    elements.cellReviewSummary.textContent = `${matches.length} active pattern${matches.length === 1 ? '' : 's'} · ${records.length} occurrence frame${records.length === 1 ? '' : 's'} · ${auditSources.length} audit median${auditSources.length === 1 ? '' : 's'}`;
    elements.cellPatternCount.textContent = `${matches.length} active · ${auditRows.length} corrected`;
    elements.cellEvidenceCount.textContent = `${records.length} frames · ${auditSources.length} medians`;
    setReportLink(elements.reportCell, 'cell-report.md', `[Cell] Review (${row},${column})`, 'report: cell', cellIssueBody(row, column, matches, auditRows));

    const patternFragment = document.createDocumentFragment();
    matches.forEach(glyph => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cell-pattern';
      button.setAttribute('aria-label', `Inspect glyph ${glyph.id}, active at cell ${row}, ${column}`);
      const canvas = document.createElement('canvas');
      canvas.setAttribute('aria-hidden', 'true');
      const label = document.createElement('span');
      label.innerHTML = `<strong>#${glyph.id}</strong><small>${glyph.occurrences} occurrence${glyph.occurrences === 1 ? '' : 's'}</small>`;
      button.append(canvas, label);
      button.addEventListener('click', () => {
        selectGlyph(glyph.id, true);
        document.getElementById('inspector').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      drawGlyph(canvas, glyph, { size: 90, carrier: state.carrier });
      patternFragment.appendChild(button);
    });
    auditRows.forEach(audit => {
      const glyph = byId.get(Number(audit.glyph_id));
      if (!glyph) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cell-pattern';
      const canvas = document.createElement('canvas');
      canvas.setAttribute('aria-hidden', 'true');
      const label = document.createElement('span');
      label.innerHTML = `<strong>#${glyph.id}</strong><small>${escapeText(audit.verdict)} · corrected tag</small>`;
      button.append(canvas, label);
      button.addEventListener('click', () => selectGlyph(glyph.id, true));
      drawGlyph(canvas, glyph, { size: 90, carrier: true });
      patternFragment.appendChild(button);
    });
    elements.cellPatternList.replaceChildren(patternFragment);
    if (!matches.length && !auditRows.length) {
      const empty = document.createElement('p');
      empty.className = 'cell-review-empty';
      empty.textContent = 'No canonical glyph activates this position. Review the carrier-mask hypothesis against source imagery before assigning payload meaning.';
      elements.cellPatternList.appendChild(empty);
    }

    const evidenceFragment = document.createDocumentFragment();
    records.slice(0, state.cellEvidenceLimit).forEach(record => {
      evidenceFragment.appendChild(createEvidenceCard(record, byId.get(Number(record.glyph_id))));
    });
    auditSources.forEach(({ audit, source }) => evidenceFragment.appendChild(createAuditEvidenceCard(audit, source)));
    elements.cellEvidenceList.replaceChildren(evidenceFragment);
    if (!records.length && !auditSources.length) {
      const empty = document.createElement('p');
      empty.className = 'cell-review-empty';
      empty.textContent = 'No frame evidence is associated with canonical patterns at this position.';
      elements.cellEvidenceList.appendChild(empty);
    }
    const remaining = records.length - state.cellEvidenceLimit;
    elements.cellEvidenceMore.hidden = remaining <= 0;
    elements.cellEvidenceMore.textContent = remaining > 0 ? `Load ${Math.min(48, remaining)} more of ${remaining}` : 'All evidence loaded';
  }

  function escapeText(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function escapeAttribute(value) {
    return escapeText(value);
  }

  function redrawAllCanvases() {
    renderGrid();
    selectGlyph(state.selectedId, false);
    updateComparison();
    renderSequence(elements.recordingSelect.value);
    renderCellHeatmap();
    if (Number.isInteger(state.selectedCell)) renderCellReview();
  }

  elements.search.addEventListener('input', renderGrid);
  elements.filter.addEventListener('change', renderGrid);
  elements.sort.addEventListener('change', renderGrid);
  elements.carrier.addEventListener('change', () => {
    state.carrier = elements.carrier.checked;
    redrawAllCanvases();
  });
  elements.copyFingerprint.addEventListener('click', copyFingerprint);
  elements.compareLeft.addEventListener('change', updateComparison);
  elements.compareRight.addEventListener('change', updateComparison);
  elements.recordingSelect.addEventListener('change', event => renderSequence(event.target.value));
  elements.cellEvidenceMore.addEventListener('click', () => {
    state.cellEvidenceLimit += 48;
    renderCellReview();
  });
  elements.evidenceDialogClose.addEventListener('click', () => elements.evidenceDialog.close());
  elements.evidenceDialog.addEventListener('click', event => {
    if (event.target === elements.evidenceDialog) elements.evidenceDialog.close();
  });

  window.addEventListener('keydown', event => {
    if (event.target.matches('input, select, button, textarea')) return;
    if (event.key === '[' || event.key === ']') {
      const delta = event.key === '[' ? -1 : 1;
      const next = Math.min(glyphs.length, Math.max(1, state.selectedId + delta));
      selectGlyph(next, true);
    }
  });

  renderStats();
  populateComparators();
  populateSequences();
  renderAnalysis();
  renderGrid();
  selectGlyph(state.selectedId, false);
})();
