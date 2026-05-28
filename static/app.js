'use strict';

// ── State ─────────────────────────────────────
const state = {
  files: { audio: null, text: null, pptx: null },
  jobId: null,
  pollTimer: null,
};

// ── DOM refs ──────────────────────────────────
const $ = id => document.getElementById(id);
const modelSel = $('model-select');
const apiKeyInput = $('api-key');
const generateBtn = $('generate-btn');
const progressSection = $('progress-section');
const progressFill = $('progress-fill');
const progressPct = $('progress-pct');
const progressLabel = $('progress-label');
const errorBox = $('error-box');
const resultSection = $('result-section');
const resultVideo = $('result-video');
const downloadBtn = $('download-btn');
const newVideoBtn = $('new-video-btn');
const resultSlides = $('result-slides');
const resultDuration = $('result-duration');

// ── Populate model select ─────────────────────
const GROUPS = [
  { prefix: 'claude-',       label: '── Anthropic  (clé sk-ant-…)' },
  { prefix: 'gpt-',          label: '── OpenAI  (clé sk-…)' },
  { prefix: 'openai/',       label: '── OpenRouter  (clé sk-or-v1-…)' },
  { prefix: 'anthropic/',    label: null },   // merged into OpenRouter group
  { prefix: 'google/',       label: null },
  { prefix: 'meta-llama/',   label: null },
  { prefix: 'mistralai/',    label: null },
  { prefix: 'qwen/',         label: null },
  { prefix: 'deepseek/',     label: null },
];

async function loadModels() {
  try {
    const res = await fetch('/api/models');
    const data = await res.json();

    const groups = {
      anthropic: { label: '── Anthropic  (clé sk-ant-…)', models: [] },
      openai:    { label: '── OpenAI  (clé sk-…)',        models: [] },
      openrouter:{ label: '── OpenRouter  (clé sk-or-v1-…)', models: [] },
    };

    for (const m of data.models) {
      if (m.id.startsWith('claude-'))  groups.anthropic.models.push(m);
      else if (m.id.startsWith('gpt-')) groups.openai.models.push(m);
      else                              groups.openrouter.models.push(m);
    }

    modelSel.innerHTML = '';
    for (const g of Object.values(groups)) {
      if (!g.models.length) continue;
      const grp = document.createElement('optgroup');
      grp.label = g.label;
      g.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.label;
        if (m.id === 'claude-sonnet-4-6') opt.selected = true;
        grp.appendChild(opt);
      });
      modelSel.appendChild(grp);
    }
  } catch {
    // keep default options from HTML
  }
}

// ── Upload zones ──────────────────────────────
document.querySelectorAll('.upload-zone').forEach(zone => {
  const type = zone.dataset.type;
  const input = zone.querySelector('input[type="file"]');

  // Click handled by the native input (covers whole zone via absolute positioning)
  input.addEventListener('change', () => handleFile(type, input.files[0]));

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    handleFile(type, e.dataTransfer.files[0]);
  });
});

function handleFile(type, file) {
  if (!file) return;
  state.files[type] = file;
  refreshZone(type, file.name);
  refreshGenerateBtn();
}

function refreshZone(type, name) {
  const zone = document.querySelector(`.upload-zone[data-type="${type}"]`);
  const fname = zone.querySelector('.upload-filename');
  const check = zone.querySelector('.upload-check');
  fname.textContent = name;
  check.style.display = 'inline';
  zone.classList.add('filled');
}

function refreshGenerateBtn() {
  const ready = state.files.audio && state.files.text && state.files.pptx && apiKeyInput.value.trim();
  generateBtn.disabled = !ready;
}

apiKeyInput.addEventListener('input', refreshGenerateBtn);

// ── Generate ──────────────────────────────────
generateBtn.addEventListener('click', async () => {
  errorBox.classList.remove('visible');
  resultSection.classList.remove('visible');

  const fd = new FormData();
  fd.append('audio', state.files.audio);
  fd.append('text', state.files.text);
  fd.append('pptx', state.files.pptx);
  fd.append('llm_model', modelSel.value);
  fd.append('api_key', apiKeyInput.value.trim());

  generateBtn.disabled = true;
  generateBtn.textContent = 'Traitement en cours…';

  progressSection.classList.add('visible');
  setProgress(0, 'Envoi des fichiers…');
  setSteps([]);

  try {
    const res = await fetch('/api/process', { method: 'POST', body: fd });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Erreur lors de l\'envoi.');
    }

    state.jobId = data.job_id;
    startPolling();
  } catch (err) {
    showError(err.message);
    resetBtn();
  }
});

// ── Polling ───────────────────────────────────
const STEP_MESSAGES = [
  { pct: 5,  label: 'Lecture des fichiers' },
  { pct: 10, label: 'Conversion des slides' },
  { pct: 25, label: 'Analyse LLM' },
  { pct: 55, label: 'Découpage audio' },
  { pct: 65, label: 'Génération vidéo' },
  { pct: 98, label: 'Assemblage final' },
];

function startPolling() {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(pollStatus, 800);
}

async function pollStatus() {
  if (!state.jobId) return;
  try {
    const res = await fetch(`/api/status/${state.jobId}`);
    const data = await res.json();

    setProgress(data.progress, data.message);

    const doneSteps = STEP_MESSAGES.filter(s => s.pct <= data.progress).map(s => s.label);
    const activeStep = STEP_MESSAGES.find(s => s.pct > data.progress)?.label || null;
    setSteps(doneSteps, activeStep, data.status === 'error' ? data.message : null);

    if (data.status === 'done') {
      clearInterval(state.pollTimer);
      showResult(data);
      resetBtn();
    } else if (data.status === 'error') {
      clearInterval(state.pollTimer);
      showError(data.message);
      resetBtn();
    }
  } catch {
    // network glitch — keep polling
  }
}

// ── UI helpers ────────────────────────────────
function setProgress(pct, label) {
  progressFill.style.width = `${pct}%`;
  progressPct.textContent = `${pct}%`;
  progressLabel.textContent = label;
}

function setSteps(done, active = null, errorMsg = null) {
  const list = $('step-list');
  list.innerHTML = '';

  STEP_MESSAGES.forEach(s => {
    const li = document.createElement('li');
    li.className = 'step';
    const isDone = done.includes(s.label);
    const isActive = s.label === active;
    if (isDone) li.classList.add('done');
    if (isActive) li.classList.add('active');

    li.innerHTML = `<span class="step-dot"></span><span>${s.label}${isActive ? '…' : isDone ? ' ✓' : ''}</span>`;
    list.appendChild(li);
  });

  if (errorMsg) {
    const li = document.createElement('li');
    li.className = 'step error-step';
    li.innerHTML = `<span class="step-dot"></span><span>Erreur : ${errorMsg}</span>`;
    list.appendChild(li);
  }
}

function showError(msg) {
  errorBox.textContent = `Erreur : ${msg}`;
  errorBox.classList.add('visible');
}

function showResult(data) {
  resultSection.classList.add('visible');
  resultVideo.src = `/api/download/${state.jobId}`;
  downloadBtn.href = `/api/download/${state.jobId}`;

  if (data.n_slides) resultSlides.textContent = `${data.n_slides} slides`;
  if (data.duration_total) {
    const m = Math.floor(data.duration_total / 60);
    const s = Math.round(data.duration_total % 60);
    resultDuration.textContent = m > 0 ? `${m}min ${s}s` : `${s}s`;
  }

  resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function resetBtn() {
  generateBtn.disabled = false;
  generateBtn.textContent = '▶ Générer la vidéo e-learning';
  refreshGenerateBtn();
}

newVideoBtn.addEventListener('click', () => {
  // Clean up old job
  if (state.jobId) {
    fetch(`/api/job/${state.jobId}`, { method: 'DELETE' }).catch(() => {});
    state.jobId = null;
  }
  resultSection.classList.remove('visible');
  progressSection.classList.remove('visible');
  errorBox.classList.remove('visible');
  resultVideo.src = '';

  // Reset uploads
  state.files = { audio: null, text: null, pptx: null };
  document.querySelectorAll('.upload-zone').forEach(zone => {
    zone.classList.remove('filled');
    const fname = zone.querySelector('.upload-filename');
    const check = zone.querySelector('.upload-check');
    if (fname) fname.textContent = '';
    if (check) check.style.display = 'none';
    const input = zone.querySelector('input[type="file"]');
    if (input) input.value = '';
  });

  refreshGenerateBtn();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// ── Boot ──────────────────────────────────────
loadModels();
refreshGenerateBtn();
