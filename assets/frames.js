(() => {
  'use strict';

  const svgNamespace = 'http://www.w3.org/2000/svg';
  const carrierCells = new Set([
    4, 12, 13, 14, 20, 21, 23, 24, 28, 29, 33, 34, 36, 37,
    43, 44, 46, 47, 51, 52, 56, 57, 59, 60, 66, 67, 68, 76
  ]);

  const PROVENANCE_INFO = {
    'archive-invest-manual': {
      label: 'ArchiveInvest manual tag',
      tagClass: 'tag-archive-invest',
      description: 'Human-annotated pattern tag from community ArchiveInvest corpus CSVs'
    },
    'pytorch-loftr-consensus': {
      label: 'PyTorch LoFTR neural consensus',
      tagClass: 'tag-pytorch',
      description: 'Verified through PyTorch LoFTR direct & temporal correspondence consensus'
    },
    'detector-ring-fit': {
      label: 'Classical detector ring fit',
      tagClass: 'tag-detector',
      description: 'Subpixel ring-intensity thresholding from automatic video extraction'
    },
    'audited-correction': {
      label: 'Audited multi-frame correction',
      tagClass: 'tag-audited',
      description: 'Multi-frame/multi-source carrier median audit correction'
    },
    'carrier-diamond': {
      label: 'Carrier diamond structure',
      tagClass: 'tag-carrier',
      description: 'Structural carrier registration graphic excluded from 9×9 payload'
    },
    'sequence-consensus': {
      label: 'Sequence-consensus derived',
      tagClass: 'tag-sequence',
      description: 'Unambiguous sequence consensus alignment across multiple captures'
    }
  };

  const palette = {
    crude: '#0b0b0b',
    neutral: '#fafae5',
    signal: '#ff4700',
    signalDim: '#b33300',
    background: '#141413',
    cellActive: '#ff4700',
    cellInactive: '#262624',
    cellExcluded: '#181816',
    border: '#2e2e2a'
  };

  const elements = {
    statFrames: document.getElementById('stat-frames'),
    statRecordings: document.getElementById('stat-recordings'),
    statManual: document.getElementById('stat-manual'),
    statProvisional: document.getElementById('stat-provisional'),
    search: document.getElementById('frames-search'),
    recording: document.getElementById('frames-recording'),
    sourceType: document.getElementById('frames-source-type'),
    glyphId: document.getElementById('frames-glyph-id'),
    sort: document.getElementById('frames-sort'),
    status: document.getElementById('frames-status'),
    grid: document.getElementById('frames-grid'),
    modeQa: document.getElementById('mode-qa'),
    modeProvenance: document.getElementById('mode-provenance'),
    modeClean: document.getElementById('mode-clean'),
    opacitySlider: document.getElementById('frames-overlay-opacity'),
    opacityValue: document.getElementById('frames-overlay-opacity-val'),
    // Modal elements
    dialog: document.getElementById('evidence-dialog'),
    dialogTitle: document.getElementById('evidence-dialog-title'),
    dialogClose: document.getElementById('evidence-dialog-close'),
    dialogImage: document.getElementById('evidence-dialog-image'),
    dialogOverlay: document.getElementById('evidence-dialog-overlay'),
    dialogSourceCaption: document.getElementById('evidence-dialog-source-caption'),
    dialogCanonical: document.getElementById('evidence-dialog-canonical'),
    dialogAssessment: document.getElementById('evidence-dialog-assessment'),
    dialogMeta: document.getElementById('evidence-dialog-meta'),
    dialogCellInspector: document.getElementById('evidence-dialog-cell-inspector'),
    dialogModeQa: document.getElementById('evidence-mode-qa'),
    dialogModeProvenance: document.getElementById('evidence-mode-provenance'),
    dialogOpacitySlider: document.getElementById('dialog-overlay-opacity-frames'),
    dialogOpacityValue: document.getElementById('dialog-overlay-opacity-frames-val'),
    reportEvidence: document.getElementById('report-evidence')
  };

  const evidenceRecords = Array.isArray(window.GLYPH_EVIDENCE) ? window.GLYPH_EVIDENCE : [];
  const glyphData = window.GLYPH_DATA || { glyphs: [] };
  const glyphMap = new Map((glyphData.glyphs || []).map(g => [g.id, g]));
  const officialArtifacts = window.OFFICIAL_ARTIFACTS || {};
  const hybridGeometry = Array.isArray(window.MANUAL_HYBRID_GEOMETRY_REVIEW) ? window.MANUAL_HYBRID_GEOMETRY_REVIEW : [];
  const hybridMap = new Map(hybridGeometry.map(h => [`${h.recording}|${h.ordinal}|${h.frame}|${h.source_video}`, h]));

  const state = {
    search: '',
    recording: 'all',
    sourceType: 'all',
    glyphId: 'all',
    sort: 'chronological',
    overlayMode: 'qa', // 'qa' | 'provenance' | 'clean'
    dialogMode: 'qa',
    activeRecord: null,
    inspectedCellIndex: null
  };

  function escapeText(str) {
    return String(str || '').replace(/[&<>"']/g, match => {
      const entities = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
      return entities[match] || match;
    });
  }

  function svgNode(name, attributes = {}) {
    const node = document.createElementNS(svgNamespace, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  function setupCanvas(canvas, size = 480) {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    const context = canvas.getContext('2d');
    context.resetTransform();
    context.scale(dpr, dpr);
    return context;
  }

  function drawGlyph(canvas, glyph, options = {}) {
    const size = options.size || 480;
    const context = setupCanvas(canvas, size);
    const active = new Set(glyph ? glyph.cell_indices : []);
    const margin = size * 0.055;
    const usable = size - margin * 2;
    const pitch = usable / 9;
    const square = pitch * 0.72;
    const inset = (pitch - square) / 2;

    context.clearRect(0, 0, size, size);
    context.fillStyle = palette.crude;
    context.fillRect(0, 0, size, size);

    for (let row = 0; row < 9; row += 1) {
      for (let col = 0; col < 9; col += 1) {
        const index = row * 9 + col;
        const x = margin + col * pitch + inset;
        const y = margin + row * pitch + inset;

        if (carrierCells.has(index)) {
          context.fillStyle = palette.cellExcluded;
          context.fillRect(x, y, square, square);
          context.strokeStyle = palette.border;
          context.lineWidth = 1;
          context.strokeRect(x + 0.5, y + 0.5, square - 1, square - 1);
        } else if (active.has(index)) {
          context.fillStyle = palette.cellActive;
          context.fillRect(x, y, square, square);
        } else {
          context.fillStyle = palette.cellInactive;
          context.fillRect(x, y, square, square);
        }
      }
    }
  }

  function overlayGeometry(record) {
    const centerX = Number(record.overlay_center_x);
    const centerY = Number(record.overlay_center_y);
    const pitch = Number(record.overlay_pitch);
    if (Number.isFinite(centerX) && Number.isFinite(centerY) && Number.isFinite(pitch) && pitch > 0) {
      return { centerX, centerY, pitch, registration: record.overlay_registration || 'subpixel-lattice-fit' };
    }
    return null;
  }

  function inspectEvidenceCell(rect, record, index, isClick = false) {
    if (!elements.dialogCellInspector) return;
    const row = Math.floor(index / 9);
    const col = index % 9;
    const observed = String(record.observed_fingerprint || '');
    const canonical = String(record.canonical_fingerprint || '');
    const observedBit = observed[index] === '1';
    const canonicalBit = canonical[index] === '1';
    const differs = observed[index] !== canonical[index];
    const excluded = carrierCells.has(index);
    const provKey = (record.cell_provenance && record.cell_provenance[index]) || (excluded ? 'carrier-diamond' : (record.provisional ? 'detector-ring-fit' : 'archive-invest-manual'));
    const info = PROVENANCE_INFO[provKey] || { label: provKey, tagClass: 'tag-archive-invest', description: 'Observed cell record' };

    state.inspectedCellIndex = index;
    if (elements.dialogOverlay) {
      elements.dialogOverlay.querySelectorAll('.evidence-overlay-cell').forEach(cell => {
        cell.classList.remove('is-inspected');
      });
      if (rect) rect.classList.add('is-inspected');
    }

    elements.dialogCellInspector.innerHTML = [
      '<div class="inspector-cell-badge">',
      `<strong>Cell (${row},${col})</strong>`,
      `<span>Observed: <em>${observedBit ? 'Active (1)' : 'Inactive (0)'}</em></span>`,
      differs ? '<span class="status-tag" style="background:rgba(255,71,0,0.2);color:var(--signal);border:1px solid var(--signal)">Differs from canonical</span>' : '<span class="status-tag">Matches canonical</span>',
      `<span class="inspector-tag ${info.tagClass}">${escapeText(info.label)}</span>`,
      `<span style="color:var(--muted)">${escapeText(info.description)}</span>`,
      '</div>'
    ].join('');
  }

  function uninspectEvidenceCell(rect) {
    if (state.inspectedCellIndex !== null) return;
    if (rect) rect.classList.remove('is-inspected');
    if (elements.dialogCellInspector) {
      elements.dialogCellInspector.innerHTML = '<span class="inspector-prompt">Hover or tap any cell in the overlay to inspect its exact provenance and alignment.</span>';
    }
  }

  function drawEvidenceOverlay(svg, record, options = {}) {
    if (!svg) return;
    const mode = options.mode || state.overlayMode || 'qa';
    const interactive = Boolean(options.interactive);
    const observed = String(record.observed_fingerprint || '');
    const canonical = String(record.canonical_fingerprint || '');
    const geometry = overlayGeometry(record);
    if (!geometry || mode === 'clean') {
      svg.replaceChildren();
      svg.setAttribute('aria-label', mode === 'clean' ? 'Clean frame: overlay hidden.' : 'Overlay unavailable: uncalibrated.');
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
      const provKey = (record.cell_provenance && record.cell_provenance[index]) || (excluded ? 'carrier-diamond' : (record.provisional ? 'detector-ring-fit' : 'archive-invest-manual'));
      const x = centerX + (column - 4) * pitch - square / 2;
      const y = centerY + (row - 4) * pitch - square / 2;
      const classes = ['evidence-overlay-cell'];

      if (mode === 'provenance') {
        classes.push(`cell-prov-${provKey}`);
        if (differs && !excluded) classes.push('evidence-overlay-difference');
      } else {
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
      }

      if (interactive && state.inspectedCellIndex === index) {
        classes.push('is-inspected');
      }

      const rect = svgNode('rect', {
        x: x.toFixed(2), y: y.toFixed(2), width: square.toFixed(2), height: square.toFixed(2),
        class: classes.join(' '),
        'data-cell': `(${row},${column})`,
        'data-row': String(row),
        'data-col': String(column),
        'data-index': String(index),
        'data-provenance': provKey,
        tabindex: interactive ? '0' : '-1',
        role: interactive ? 'button' : 'presentation',
        'aria-label': `Cell (${row},${column}): ${positive ? '1' : '0'}, ${PROVENANCE_INFO[provKey]?.label || provKey}`
      });

      if (interactive) {
        rect.addEventListener('mouseenter', () => inspectEvidenceCell(rect, record, index, false));
        rect.addEventListener('focus', () => inspectEvidenceCell(rect, record, index, false));
        rect.addEventListener('mouseleave', () => uninspectEvidenceCell(rect));
        rect.addEventListener('blur', () => uninspectEvidenceCell(rect));
        rect.addEventListener('click', (e) => {
          e.stopPropagation();
          inspectEvidenceCell(rect, record, index, true);
        });
      }

      fragment.appendChild(rect);
    }
    svg.replaceChildren(fragment);
    svg.setAttribute('aria-label', `${positiveCount} active cells, ${negativeCount} inactive cells; ${registration}.`);
  }

  function createEvidenceCard(record) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'evidence-card';
    card.setAttribute('aria-label', `Frame ${record.frame} of glyph #${record.glyph_id} in ${record.recording}`);
    
    if (record.difference_cells && record.difference_cells.length > 0) {
      card.classList.add('evidence-card-difference');
    }

    const stage = document.createElement('span');
    stage.className = 'evidence-image-stage';
    const image = document.createElement('img');
    image.src = record.image;
    image.loading = 'lazy';
    image.alt = `Frame ${record.frame} from ${record.source_video}`;

    const overlay = svgNode('svg', {
      class: 'evidence-overlay', viewBox: '0 0 480 480', preserveAspectRatio: 'none', 'aria-hidden': 'true'
    });
    if (state.overlayMode !== 'clean') {
      drawEvidenceOverlay(overlay, record, { mode: state.overlayMode });
    }

    stage.append(image, overlay);

    const meta = document.createElement('span');
    meta.className = 'evidence-card-meta';

    const title = document.createElement('strong');
    title.textContent = `#${record.glyph_id} · ${record.recording}`;

    const sub = document.createElement('span');
    const paddedFrame = String(record.frame).padStart(6, '0');
    const timeStr = Number.isFinite(Number(record.time_s)) ? ` · T+${Number(record.time_s).toFixed(1)}s` : '';
    sub.textContent = `FRAME ${paddedFrame}${timeStr}`;

    const status = document.createElement('span');
    status.className = 'evidence-card-status';
    if (record.provisional) {
      status.textContent = 'PROVISIONAL CAPTURE';
    } else if (record.assigned_hamming === 0) {
      status.textContent = 'MATCHES CORPUS';
    } else {
      status.textContent = `DISTANCE d=${record.assigned_hamming}`;
    }

    meta.append(title, sub, status);
    card.append(stage, meta);

    card.addEventListener('click', () => openEvidenceDialog(record));
    return card;
  }

  function renderGeometryAssessment(record) {
    if (!elements.dialogAssessment) return;
    const assessment = hybridMap.get(`${record.recording}|${record.ordinal}|${record.frame}|${record.source_video}`);
    if (!assessment) {
      elements.dialogAssessment.innerHTML = [
        '<div class="assessment-heading"><span>GEOMETRY ASSESSMENT / READ ONLY</span><strong class="assessment-chip assessment-unavailable">NOT ASSESSED</strong></div>',
        '<p>No hybrid geometry assessment is available for this record. The observed-state QA overlay remains independent of this research ledger.</p>'
      ].join('');
      return;
    }
    const details = [
      ['Assessment', assessment.operational_status || 'not available'],
      ['Decision type', 'deterministic threshold gate · not a probability'],
      ['Review / overlay', `${assessment.review_status || 'pending'} · overlay disabled`],
      ['Selected proposal', assessment.proposal_selected || 'none retained'],
      ['Verified source', assessment.source_sha256 ? `SHA-256 ${assessment.source_sha256}` : 'not available']
    ];
    elements.dialogAssessment.innerHTML = [
      `<div class="assessment-heading"><span>GEOMETRY ASSESSMENT / READ ONLY</span><strong class="assessment-chip assessment-candidate">REVIEW PENDING</strong></div>`,
      '<p>Experimental registration evidence only. It neither changes the corpus tag nor draws a proposed geometry overlay.</p>',
      `<div class="assessment-grid">${details.map(([l, v]) => `<div><span>${escapeText(l)}</span><strong>${escapeText(v)}</strong></div>`).join('')}</div>`
    ].join('');
  }

  function openEvidenceDialog(record) {
    state.activeRecord = record;
    state.inspectedCellIndex = null;
    if (!elements.dialog) return;

    elements.dialogTitle.textContent = `${record.source_video} / FRAME ${record.frame}`;
    elements.dialogImage.src = record.image;
    elements.dialogImage.alt = `Actual frame ${record.frame} from ${record.source_video}`;

    if (elements.dialogSourceCaption) {
      const modeLabel = state.dialogMode === 'provenance' ? 'cell provenance' : 'observed-state QA';
      const dev = record.overlay_deviation_px ? ` · deviation ${Number(record.overlay_deviation_px).toFixed(3)}px RMS` : '';
      elements.dialogSourceCaption.textContent = `${modeLabel.toUpperCase()} OVERLAY${dev} · ${record.overlay_registration || 'subpixel lattice fit'}`.toUpperCase();
    }

    drawEvidenceOverlay(elements.dialogOverlay, record, { interactive: true, mode: state.dialogMode });

    const glyph = glyphMap.get(record.glyph_id);
    if (elements.dialogCanonical) {
      drawGlyph(elements.dialogCanonical, glyph, { size: 480 });
    }

    if (elements.dialogCellInspector) {
      elements.dialogCellInspector.innerHTML = '<span class="inspector-prompt">Hover or tap any cell in the overlay to inspect its exact provenance and alignment.</span>';
    }

    renderGeometryAssessment(record);

    if (elements.dialogMeta) {
      const artifact = officialArtifacts[record.broadcast];
      const items = [
        ['Assigned Glyph', `#${record.glyph_id}`],
        ['Recording', record.recording],
        ['Logical broadcast', record.broadcast],
        ['Decoded frame', `Frame ${record.frame}`],
        ['Source video', record.source_video],
        ['Provenance type', record.provisional ? 'Provisional automated detector' : 'ArchiveInvest manual tag'],
        ['Assigned Hamming', `d = ${record.assigned_hamming || 0}`],
        ['Official artifact', artifact ? `${artifact.id} · ${artifact.type}` : 'None recorded for broadcast label']
      ];
      elements.dialogMeta.innerHTML = items.map(([k, v]) => `<div><span>${escapeText(k)}</span><strong>${escapeText(v)}</strong></div>`).join('');
    }

    if (elements.reportEvidence) {
      const issueTitle = encodeURIComponent(`Frame evidence audit: ${record.source_video} frame ${record.frame}`);
      const issueBody = encodeURIComponent(`Recording: ${record.recording}
Frame: ${record.frame}
Glyph ID: #${record.glyph_id}
Source video: ${record.source_video}
Image path: ${record.image}
Observed: ${record.observed_fingerprint}

Describe the evidence dispute or geometry correction here:`);
      elements.reportEvidence.href = `https://github.com/Scetrov/eve-frontier-glyph-explorer/issues/new?title=${issueTitle}&body=${issueBody}`;
    }

    elements.dialog.showModal();
  }

  function closeEvidenceDialog() {
    state.activeRecord = null;
    state.inspectedCellIndex = null;
    if (elements.dialog && elements.dialog.open) {
      elements.dialog.close();
    }
  }

  function populateDropdowns() {
    // Unique recordings with counts
    const recCounts = new Map();
    evidenceRecords.forEach(e => {
      recCounts.set(e.recording, (recCounts.get(e.recording) || 0) + 1);
    });

    const sortedRecs = Array.from(recCounts.keys()).sort((a, b) => a.localeCompare(b));
    elements.recording.innerHTML = `<option value="all">All recordings (${sortedRecs.length})</option>` +
      sortedRecs.map(rec => `<option value="${escapeText(rec)}">${escapeText(rec)} (${recCounts.get(rec)})</option>`).join('');

    // Unique glyph IDs
    const glyphIds = Array.from(new Set(evidenceRecords.map(e => e.glyph_id))).sort((a, b) => a - b);
    elements.glyphId.innerHTML = `<option value="all">All glyphs (${glyphIds.length})</option>` +
      glyphIds.map(id => `<option value="${id}">Glyph #${id}</option>`).join('');
  }

  function filterAndSortRecords() {
    const q = state.search.trim().toLowerCase();
    const cleanQ = q.replace(/^#/, '');

    let filtered = evidenceRecords.filter(r => {
      // Recording filter
      if (state.recording !== 'all' && r.recording !== state.recording) return false;
      // Source type filter
      if (state.sourceType === 'manual' && r.provisional) return false;
      if (state.sourceType === 'provisional' && !r.provisional) return false;
      // Glyph filter
      if (state.glyphId !== 'all' && r.glyph_id !== Number(state.glyphId)) return false;

      // Text search
      if (q) {
        const frameStr = String(r.frame);
        const paddedFrame = frameStr.padStart(6, '0');
        const glyphStr = String(r.glyph_id);
        const recStr = String(r.recording).toLowerCase();
        const videoStr = String(r.source_video).toLowerCase();
        const broadcastStr = String(r.broadcast).toLowerCase();

        const matches = frameStr === cleanQ ||
          paddedFrame.includes(cleanQ) ||
          glyphStr === cleanQ ||
          recStr.includes(q) ||
          videoStr.includes(q) ||
          broadcastStr.includes(q);

        if (!matches) return false;
      }
      return true;
    });

    // Sorting
    filtered.sort((a, b) => {
      if (state.sort === 'frame') return a.frame - b.frame;
      if (state.sort === 'glyph') return a.glyph_id - b.glyph_id || a.frame - b.frame;
      if (state.sort === 'hamming') return (b.assigned_hamming || 0) - (a.assigned_hamming || 0) || a.glyph_id - b.glyph_id;
      // Default: chronological
      if (a.recording !== b.recording) return a.recording.localeCompare(b.recording);
      return a.ordinal - b.ordinal || a.frame - b.frame;
    });

    return filtered;
  }

  function renderGallery() {
    const records = filterAndSortRecords();

    if (elements.status) {
      elements.status.innerHTML = `Showing <strong>${records.length}</strong> of <strong>${evidenceRecords.length}</strong> frames`;
    }

    if (records.length === 0) {
      elements.grid.innerHTML = '<div class="frames-empty"><p>No frame observations match your current filter criteria.</p></div>';
      return;
    }

    const fragment = document.createDocumentFragment();
    records.forEach(record => {
      fragment.appendChild(createEvidenceCard(record));
    });

    elements.grid.replaceChildren(fragment);
  }

  function setOverlayMode(mode) {
    state.overlayMode = mode;
    [elements.modeQa, elements.modeProvenance, elements.modeClean].forEach(btn => {
      if (!btn) return;
      const isActive = (btn === elements.modeQa && mode === 'qa') ||
                       (btn === elements.modeProvenance && mode === 'provenance') ||
                       (btn === elements.modeClean && mode === 'clean');
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', String(isActive));
    });

    // Re-render gallery cards with new overlay mode
    renderGallery();
  }

  function setDialogOverlayMode(mode) {
    state.dialogMode = mode;
    [elements.dialogModeQa, elements.dialogModeProvenance].forEach(btn => {
      if (!btn) return;
      const isActive = (btn === elements.dialogModeQa && mode === 'qa') ||
                       (btn === elements.dialogModeProvenance && mode === 'provenance');
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', String(isActive));
    });

    if (state.activeRecord && elements.dialogOverlay) {
      drawEvidenceOverlay(elements.dialogOverlay, state.activeRecord, { interactive: true, mode });
      if (elements.dialogSourceCaption) {
        const modeLabel = mode === 'provenance' ? 'cell provenance' : 'observed-state QA';
        const dev = state.activeRecord.overlay_deviation_px ? ` · deviation ${Number(state.activeRecord.overlay_deviation_px).toFixed(3)}px RMS` : '';
        elements.dialogSourceCaption.textContent = `${modeLabel.toUpperCase()} OVERLAY${dev} · ${state.activeRecord.overlay_registration || 'subpixel lattice fit'}`.toUpperCase();
      }
    }
  }

  const STORAGE_KEY_OPACITY = 'eve_frontier_overlay_opacity';

  function getStoredOpacity() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_OPACITY);
      if (stored !== null) {
        const parsed = parseInt(stored, 10);
        if (!isNaN(parsed) && parsed >= 0 && parsed <= 100) {
          return parsed;
        }
      }
    } catch (e) {}
    return 100;
  }

  function setOverlayOpacity(percent, save = true) {
    const val = Math.max(0, Math.min(100, Math.round(Number(percent))));
    document.documentElement.style.setProperty('--overlay-opacity', (val / 100).toFixed(2));

    if (elements.opacitySlider) elements.opacitySlider.value = String(val);
    if (elements.opacityValue) elements.opacityValue.textContent = `${val}%`;
    if (elements.dialogOpacitySlider) elements.dialogOpacitySlider.value = String(val);
    if (elements.dialogOpacityValue) elements.dialogOpacityValue.textContent = `${val}%`;

    if (save) {
      try {
        localStorage.setItem(STORAGE_KEY_OPACITY, String(val));
      } catch (e) {}
    }
  }

  function init() {
    populateDropdowns();

    // Initialize stored opacity
    setOverlayOpacity(getStoredOpacity(), false);

    // Event listeners
    if (elements.search) {
      elements.search.addEventListener('input', () => {
        state.search = elements.search.value;
        renderGallery();
      });
    }

    if (elements.recording) {
      elements.recording.addEventListener('change', () => {
        state.recording = elements.recording.value;
        renderGallery();
      });
    }

    if (elements.sourceType) {
      elements.sourceType.addEventListener('change', () => {
        state.sourceType = elements.sourceType.value;
        renderGallery();
      });
    }

    if (elements.glyphId) {
      elements.glyphId.addEventListener('change', () => {
        state.glyphId = elements.glyphId.value;
        renderGallery();
      });
    }

    if (elements.sort) {
      elements.sort.addEventListener('change', () => {
        state.sort = elements.sort.value;
        renderGallery();
      });
    }

    if (elements.modeQa) elements.modeQa.addEventListener('click', () => setOverlayMode('qa'));
    if (elements.modeProvenance) elements.modeProvenance.addEventListener('click', () => setOverlayMode('provenance'));
    if (elements.modeClean) elements.modeClean.addEventListener('click', () => setOverlayMode('clean'));

    if (elements.opacitySlider) {
      elements.opacitySlider.addEventListener('input', (e) => {
        setOverlayOpacity(e.target.value, true);
      });
    }

    if (elements.dialogOpacitySlider) {
      elements.dialogOpacitySlider.addEventListener('input', (e) => {
        setOverlayOpacity(e.target.value, true);
      });
    }

    if (elements.dialogModeQa) elements.dialogModeQa.addEventListener('click', () => setDialogOverlayMode('qa'));
    if (elements.dialogModeProvenance) elements.dialogModeProvenance.addEventListener('click', () => setDialogOverlayMode('provenance'));

    if (elements.dialogClose) elements.dialogClose.addEventListener('click', closeEvidenceDialog);
    if (elements.dialog) {
      elements.dialog.addEventListener('click', (e) => {
        const rect = elements.dialog.getBoundingClientRect();
        if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
          closeEvidenceDialog();
        }
      });
    }

    // URL parameter parsing for initial filters
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('recording')) {
      const rec = urlParams.get('recording');
      state.recording = rec;
      if (elements.recording) elements.recording.value = rec;
    }
    if (urlParams.has('glyph')) {
      const g = urlParams.get('glyph');
      state.glyphId = g;
      if (elements.glyphId) elements.glyphId.value = g;
    }
    if (urlParams.has('frame')) {
      const f = urlParams.get('frame');
      state.search = f;
      if (elements.search) elements.search.value = f;
    }

    renderGallery();
  }

  window.addEventListener('DOMContentLoaded', init);
})();
