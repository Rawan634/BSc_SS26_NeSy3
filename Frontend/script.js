const aiModeTab = document.getElementById('aiModeTab');
const verifiedModeTab = document.getElementById('verifiedModeTab');
const aiTutorPanel = document.getElementById('aiTutorPanel');
const verifiedProofPanel = document.getElementById('verifiedProofPanel');
const helpButton = document.getElementById('helpButton');
const askTutorButton = document.getElementById('askTutorButton');
const solveProofButton = document.getElementById('solveProofButton');
const aiQuestion = document.getElementById('aiQuestion');
const premisesInput = document.getElementById('premisesInput');
const goalInput = document.getElementById('goalInput');
const aiResponse = document.getElementById('aiResponse');
const verifiedProofOutput = document.getElementById('verifiedProofOutput');
const proofTooltip = document.getElementById('proofTooltip');
const statusText = document.getElementById('statusText');
const helpModal = document.getElementById('helpModal');
const helpCloseButton = document.getElementById('helpCloseButton');
const themeToggle = document.getElementById('themeToggle');
const API_BASE_URL = window.__AI_LOGIC_TUTOR_API__ || 'http://127.0.0.1:5000';

const RULE_NAME_MAP = {
  MT: 'Modus Tollens',
  DS: 'Disjunctive Syllogism',
  '→E': 'Modus Ponens',
  HS: 'Hypothetical Syllogism',
  premise: 'Premise',
};

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

function setStatus(message) {
  if (statusText) {
    statusText.textContent = message;
  }
}

function switchMode(mode) {
  const isAI = mode === 'ai';
  aiModeTab.classList.toggle('active', isAI);
  verifiedModeTab.classList.toggle('active', !isAI);
  aiModeTab.setAttribute('aria-pressed', String(isAI));
  verifiedModeTab.setAttribute('aria-pressed', String(!isAI));
  aiTutorPanel.classList.toggle('active', isAI);
  verifiedProofPanel.classList.toggle('active', !isAI);
  setStatus(isAI ? 'AI Tutor Mode is active.' : 'Verified Proof Mode is active.');
}

function normalizeText(text) {
  return String(text || '').replace(/\r\n/g, '\n').trim();
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeHtmlWithLineBreaks(value) {
  return escapeHtml(value).replace(/\n/g, '<br>');
}

function renderAiAnswer(data) {
  const payload = typeof data === 'string' ? { answer: data } : data || {};
  const answer = payload.answer || payload.response || payload.explanation || payload.message || JSON.stringify(payload, null, 2);
  aiResponse.innerHTML = `<div class="ai-answer">${formatRichText(answer)}</div>`;
}

function formatRichText(text) {
  const lines = normalizeText(text).split('\n');
  const blocks = [];
  let listItems = [];

  const flushList = () => {
    if (listItems.length) {
      blocks.push(`<ul>${listItems.map((item) => `<li>${item}</li>`).join('')}</ul>`);
      listItems = [];
    }
  };

  lines.forEach((line) => {
    if (!line.trim()) {
      flushList();
      return;
    }

    if (/^\s*[-*•]\s+/.test(line)) {
      const itemText = escapeHtml(line.replace(/^\s*[-*•]\s+/, '')).replace(/`([^`]+)`/g, '<span class="formula-inline">$1</span>');
      listItems.push(itemText);
      return;
    }

    flushList();
    blocks.push(`<p>${escapeHtml(line).replace(/`([^`]+)`/g, '<span class="formula-inline">$1</span>')}</p>`);
  });

  flushList();
  return blocks.join('');
}

function clearProofOutput(message) {
  verifiedProofOutput.innerHTML = `<div class="placeholder">${escapeHtml(message)}</div>`;
}

function extractProofSteps(payload) {
  if (!payload) {
    return [];
  }

  if (Array.isArray(payload.steps)) {
    return payload.steps;
  }

  if (Array.isArray(payload.proof?.steps)) {
    return payload.proof.steps;
  }

  if (Array.isArray(payload.result?.steps)) {
    return payload.result.steps;
  }

  if (Array.isArray(payload.data?.steps)) {
    return payload.data.steps;
  }

  if (Array.isArray(payload.annotated_steps)) {
    return payload.annotated_steps;
  }

  return [];
}

function getExplanation(step) {
  return step.short_explanation || step.shortExplanation || step.short || step.rule_short || '';
}

function getDetailedExplanation(step) {
  return step.detailed_explanation || step.detailedExplanation || step.detailed || '';
}

function getExamples(step) {
  const examples = step.example || step.explanation_example || step.examples || [];
  const list = Array.isArray(examples) ? examples : [examples];
  return list.filter((item) => String(item || '').trim());
}

function canonicalFormula(formula) {
  return String(formula || '')
    .replace(/->/g, '→')
    .replace(/~/g, '¬')
    .replace(/\s+/g, '');
}

function getDifficultyLabel(stepCount) {
  if (stepCount <= 3) {
    return 'Easy';
  }
  if (stepCount <= 7) {
    return 'Medium';
  }
  return 'Hard';
}

function getRuleDisplay(rule, step) {
  const ruleText = String(rule || '').trim();
  const fullName = step.rule_full_name || RULE_NAME_MAP[ruleText] || RULE_NAME_MAP[ruleText.toLowerCase()] || '';

  if (!ruleText && fullName) {
    return fullName;
  }
  if (!fullName || fullName === ruleText) {
    return ruleText || 'Unknown Rule';
  }
  return `${ruleText} (${fullName})`;
}

function getOriginalError(step) {
  if (Array.isArray(step.original_errors) && step.original_errors.length > 0) {
    return step.original_errors.join('\n');
  }
  return step.original_error || step.previous_error || '';
}

function buildOverallStrategy(steps, payload) {
  const fromPayload = normalizeText(payload?.overall_proof_strategy || '');
  if (fromPayload) {
    return fromPayload;
  }

  const derived = (steps || []).filter((step) => {
    const rule = String(step?.rule || '').toLowerCase();
    return rule && rule !== 'premise' && rule !== 'assumption';
  });

  if (!derived.length) {
    return 'The proof starts from the given premises and reaches the goal directly.';
  }

  const parts = derived.slice(0, 3).map((step, index) => {
    const prefix = index === 0 ? 'First' : (index === 1 ? 'Then' : 'Finally');
    const rule = step.rule_full_name || step.rule || 'a valid inference rule';
    const formula = step.formula || 'the next result';
    return `${prefix}, we apply ${rule} to derive ${formula}.`;
  });

  return parts.join(' ');
}

function renderProofLine(step, options = {}) {
  const line = step.line ?? '';
  const formula = step.formula ?? '';
  const rule = step.rule ?? '';
  const isGoalAchieved = Boolean(options.isGoalAchieved);
  const wasCorrected = Boolean(step.was_corrected);
  const explanation = getExplanation(step);
  const detailed = getDetailedExplanation(step);
  const exampleList = getExamples(step);
  const originalError = getOriginalError(step);
  const references = Array.isArray(step.references) ? step.references : [];
  const referencesText = references.length ? `References: ${references.join(', ')}` : 'No references';
  const correctedNote = wasCorrected ? 'Corrected line' : 'Original line';

  const ruleDisplay = getRuleDisplay(rule, step);
  const goalBadge = isGoalAchieved
    ? '<div class="goal-achieved-badge"><span class="goal-icon" aria-label="Goal achieved">🏁 Goal Achieved</span></div>'
    : '';

  return `
    <article class="proof-line ${wasCorrected ? 'corrected' : ''} ${isGoalAchieved ? 'goal-achieved' : ''}" tabindex="0" data-line="${escapeHtml(line)}" data-refs="${escapeHtml(references.join(','))}" data-short="${escapeHtml(explanation)}">
      <div class="line-number">${escapeHtml(line)}</div>
      <div class="formula">${escapeHtml(formula)}</div>
      <div class="rule-pill">${escapeHtml(ruleDisplay)}</div>
      ${goalBadge}
      <div class="proof-details">
        <div class="detail-block">
          <div class="detail-label">Status</div>
          <div class="detail-text">${escapeHtml(isGoalAchieved ? `${correctedNote} • Goal achieved` : correctedNote)}</div>
        </div>
        <div class="detail-block">
          <div class="detail-label">Explanation</div>
          <div class="detail-text">${escapeHtmlWithLineBreaks(detailed || explanation || 'No explanation available.')}</div>
        </div>
        ${exampleList.length ? `
        <div class="detail-block">
          <div class="detail-label">General Rule Pattern</div>
          <div class="detail-pattern">${exampleList.map((item) => escapeHtml(item)).join('<br>')}</div>
        </div>
        ` : ''}
        ${wasCorrected ? `
        <div class="detail-block">
          <div class="detail-label">Original Error</div>
          <div class="detail-text">${escapeHtmlWithLineBreaks(originalError || 'No original error provided.')}</div>
        </div>
        ` : ''}
        <div class="detail-block">
          <div class="detail-label">References</div>
          <div class="detail-text">${escapeHtml(referencesText)}</div>
        </div>
      </div>
    </article>
  `;
}

function clearReferenceHighlights() {
  const highlighted = verifiedProofOutput.querySelectorAll('.proof-line.ref-highlight');
  highlighted.forEach((lineEl) => lineEl.classList.remove('ref-highlight'));
}

function highlightReferencedLines(refValues) {
  clearReferenceHighlights();
  if (!Array.isArray(refValues) || !refValues.length) {
    return;
  }

  refValues.forEach((ref) => {
    const refLine = String(ref).trim();
    if (!refLine) {
      return;
    }
    const target = verifiedProofOutput.querySelector(`.proof-line[data-line="${refLine}"]`);
    if (target) {
      target.classList.add('ref-highlight');
    }
  });
}

function attachProofInteractions() {
  const proofLines = verifiedProofOutput.querySelectorAll('.proof-line');
  proofLines.forEach((lineEl) => {
    const shortText = lineEl.getAttribute('data-short') || 'No explanation available.';
    const refs = String(lineEl.getAttribute('data-refs') || '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);

    lineEl.addEventListener('mouseenter', (event) => {
      highlightReferencedLines(refs);
      if (lineEl.classList.contains('expanded')) {
        return;
      }
      showTooltip(shortText, event.clientX, event.clientY);
    });

    lineEl.addEventListener('mousemove', (event) => {
      if (lineEl.classList.contains('expanded')) {
        return;
      }
      moveTooltip(event.clientX, event.clientY);
    });

    lineEl.addEventListener('mouseleave', () => {
      hideTooltip();
      clearReferenceHighlights();
    });

    lineEl.addEventListener('click', () => {
      lineEl.classList.toggle('expanded');
      if (lineEl.classList.contains('expanded')) {
        hideTooltip();
      }
    });

    lineEl.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        lineEl.classList.toggle('expanded');
        if (lineEl.classList.contains('expanded')) {
          hideTooltip();
        }
      }
    });
  });
}

function showTooltip(text, x, y) {
  if (!text) {
    return;
  }
  proofTooltip.innerHTML = escapeHtml(text);
  proofTooltip.classList.add('visible');
  proofTooltip.setAttribute('aria-hidden', 'false');
  moveTooltip(x, y);
}

function moveTooltip(x, y) {
  if (!proofTooltip.classList.contains('visible')) {
    return;
  }
  const offset = 18;
  proofTooltip.style.left = `${Math.min(window.innerWidth - 24, x + offset)}px`;
  proofTooltip.style.top = `${Math.min(window.innerHeight - 24, y + offset)}px`;
}

function hideTooltip() {
  proofTooltip.classList.remove('visible');
  proofTooltip.setAttribute('aria-hidden', 'true');
  clearReferenceHighlights();
}

function openHelpModal() {
  if (!helpModal) {
    return;
  }
  helpModal.classList.add('open');
  helpModal.setAttribute('aria-hidden', 'false');
  helpButton.setAttribute('aria-expanded', 'true');
  const panel = helpModal.querySelector('.help-modal-panel');
  if (panel) {
    panel.focus();
  }
}

function closeHelpModal() {
  if (!helpModal) {
    return;
  }
  helpModal.classList.remove('open');
  helpModal.setAttribute('aria-hidden', 'true');
  helpButton.setAttribute('aria-expanded', 'false');
}

// When modal opens, hide page content to avoid overlap and interaction
const MODAL_OPEN_CLASS = 'help-open';
const appShell = document.querySelector('.app-shell');

const origOpen = openHelpModal;
openHelpModal = function() {
  document.documentElement.classList.add(MODAL_OPEN_CLASS);
  if (appShell) appShell.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = 'hidden';
  origOpen();
};

const origClose = closeHelpModal;
closeHelpModal = function() {
  document.documentElement.classList.remove(MODAL_OPEN_CLASS);
  if (appShell) appShell.removeAttribute('aria-hidden');
  document.body.style.overflow = '';
  origClose();
};

async function askTutor() {
  const question = normalizeText(aiQuestion.value);
  if (!question) {
    aiResponse.innerHTML = '<div class="placeholder">Enter a question before asking the tutor.</div>';
    return;
  }

  setStatus('Sending question to the tutor...');
  askTutorButton.disabled = true;

  try {
    const response = await fetch(apiUrl('/ask_ai'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question }),
    });

    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error((data && (data.error || data.message)) || 'Tutor request failed.');
    }

    renderAiAnswer(data);
    setStatus('Tutor response loaded.');
  } catch (error) {
    aiResponse.innerHTML = `<div class="placeholder">${escapeHtml(error.message)}</div>`;
    setStatus('Tutor request failed.');
  } finally {
    askTutorButton.disabled = false;
  }
}

function buildProofRequestPayload() {
  const premises = normalizeText(premisesInput.value)
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  const goal = normalizeText(goalInput.value);

  return {
    premises,
    goal,
  };
}

function renderProof(payload) {
  // If backend signalled a repair failure, show a student-facing message instead of an invalid proof.
  if (payload && payload.repair_failed) {
    const msg = payload.goal_error || 'Automatic repair failed. We could not produce a valid proof.';
    clearProofOutput(msg);
    setStatus('Repair failed — no valid proof available.');
    return;
  }

  const steps = extractProofSteps(payload);
  if (!steps.length) {
    verifiedProofOutput.innerHTML = '<div class="placeholder">No proof steps were returned.</div>';
    return;
  }

  const title = payload.title || payload.mode || 'Verified Proof';
  const summary = payload.summary || payload.message || '';
  const stepCount = steps.length;
  const difficulty = getDifficultyLabel(stepCount);
  const goalFormula = canonicalFormula(payload.requested_goal_formula || payload.goal || '');
  const overallStrategy = buildOverallStrategy(steps, payload);

  let goalLineNumber = null;
  if (goalFormula && stepCount > 0) {
    const lastStep = steps[stepCount - 1] || {};
    if (canonicalFormula(lastStep.formula) === goalFormula) {
      goalLineNumber = lastStep.line;
    }
  }

  const markup = [
    `<div class="output-title">${escapeHtml(title)}</div>`,
    `<div class="proof-meta"><span class="difficulty-pill">Difficulty: ${escapeHtml(difficulty)}</span></div>`,
    summary ? `<div class="placeholder">${escapeHtml(summary)}</div>` : '',
    steps.map((step) => renderProofLine(step, { isGoalAchieved: goalLineNumber !== null && String(step.line) === String(goalLineNumber) })).join(''),
    `<div class="proof-strategy"><div class="detail-label">Overall Proof Strategy</div><div class="detail-text">${escapeHtmlWithLineBreaks(overallStrategy)}</div></div>`,
  ].join('');

  verifiedProofOutput.innerHTML = markup;
  attachProofInteractions();
}

async function solveVerifiedProof() {
  const payload = buildProofRequestPayload();
  if (!payload.premises.length || !payload.goal) {
    clearProofOutput('Enter premises and a goal before solving the verified proof.');
    return;
  }

  setStatus('Submitting proof to the verified pipeline...');
  solveProofButton.disabled = true;

  try {
    const response = await fetch(apiUrl('/solve_verified'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error((data && (data.error || data.message)) || 'Verified proof request failed.');
    }

    renderProof(data);
    setStatus('Verified proof loaded. Hover or click a line for details.');
  } catch (error) {
    clearProofOutput(error.message);
    setStatus('Verified proof request failed.');
  } finally {
    solveProofButton.disabled = false;
  }
}

aiModeTab.addEventListener('click', () => switchMode('ai'));
verifiedModeTab.addEventListener('click', () => switchMode('verified'));
helpButton.addEventListener('click', openHelpModal);
if (helpCloseButton) {
  helpCloseButton.addEventListener('click', closeHelpModal);
}
if (helpModal) {
  helpModal.addEventListener('click', (event) => {
    if (event.target instanceof HTMLElement && event.target.dataset.helpClose === 'backdrop') {
      closeHelpModal();
    }
  });
}
askTutorButton.addEventListener('click', askTutor);
solveProofButton.addEventListener('click', solveVerifiedProof);

aiQuestion.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    askTutor();
  }
});

premisesInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    solveVerifiedProof();
  }
});

goalInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    solveVerifiedProof();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    if (helpModal && helpModal.classList.contains('open')) {
      closeHelpModal();
      return;
    }
    hideTooltip();
  }
});

switchMode('ai');
clearProofOutput('Formatted Fitch-style proof will appear here.');

// Theme handling: default to light, allow toggle, persist in localStorage
function applyTheme(theme) {
  const isDark = theme === 'dark';
  document.documentElement.classList.toggle('theme-dark', isDark);
  if (themeToggle) {
    themeToggle.setAttribute('aria-pressed', String(isDark));
  }
  localStorage.setItem('ai_logic_tutor_theme', theme);
}

function initTheme() {
  const saved = localStorage.getItem('ai_logic_tutor_theme');
  const theme = saved === 'dark' ? 'dark' : 'light';
  applyTheme(theme);
}

if (themeToggle) {
  themeToggle.addEventListener('click', () => {
    const current = document.documentElement.classList.contains('theme-dark') ? 'dark' : 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
  });
}

initTheme();

// Add a small visual pulse when toggling for feedback
if (themeToggle) {
  themeToggle.addEventListener('click', () => {
    themeToggle.animate([
      { transform: 'scale(1)' },
      { transform: 'scale(1.06)' },
      { transform: 'scale(1)' }
    ], { duration: 220, easing: 'ease-out' });
  });
}
