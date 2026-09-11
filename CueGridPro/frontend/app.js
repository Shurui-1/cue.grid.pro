/**
 * Rekordbox Auto Cue Generator (CueGrid Pro) - Frontend Application
 */

// Application State
const state = {
  tracks: [],           // Array of analyzed track objects
  activeAudio: null,    // Currently playing HTML5 Audio element
  activeTrackId: null,  // ID of currently playing track
  currentInterval: 16,  // Selected bar interval (default 16)
  cueMode: 'both',      // 'both', 'hot_cues', 'memory_cues'
  namingTemplate: '{bar} Bars',
  maxHotCues: 8,
  maxMemoryCues: 8,
  minBpm: 60,
  maxBpm: 180,
  exportBeatgrid: true,
  exportBpm: true,
  exportHotCues: true,
  exportMemoryCues: true
};

// DOM Elements
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const btnBrowseFiles = document.getElementById('btnBrowseFiles');
const btnBrowseFolder = document.getElementById('btnBrowseFolder');
const progressContainer = document.getElementById('progressContainer');
const progressBar = document.getElementById('progressBar');
const progressPercent = document.getElementById('progressPercent');
const progressStatus = document.getElementById('progressStatus');
const tracksList = document.getElementById('tracksList');
const emptyState = document.getElementById('emptyState');
const tracksCount = document.getElementById('tracksCount');
const exportCount = document.getElementById('exportCount');
const btnExportXml = document.getElementById('btnExportXml');
const btnClearAll = document.getElementById('btnClearAll');
const btnApplyAll = document.getElementById('btnApplyAll');
const customIntervalInput = document.getElementById('customIntervalInput');
const bpmRangeSelect = document.getElementById('bpmRangeSelect');
const customBpmRangeWrap = document.getElementById('customBpmRangeWrap');
const minBpmInput = document.getElementById('minBpmInput');
const maxBpmInput = document.getElementById('maxBpmInput');
const cueModeSelect = document.getElementById('cueModeSelect');
const namingTemplateSelect = document.getElementById('namingTemplateSelect');
const maxHotCuesSelect = document.getElementById('maxHotCuesSelect');
const maxMemoryCuesSelect = document.getElementById('maxMemoryCuesSelect');
const chkExportBeatgrid = document.getElementById('chkExportBeatgrid');
const chkExportBpm = document.getElementById('chkExportBpm');
const chkExportHotCues = document.getElementById('chkExportHotCues');
const chkExportMemoryCues = document.getElementById('chkExportMemoryCues');

// Modal Elements
const guideModal = document.getElementById('guideModal');
const btnGuide = document.getElementById('btnGuide');
const btnCloseModal = document.getElementById('btnCloseModal');
const btnCloseModalBtn = document.getElementById('btnCloseModalBtn');


// -------------------------------------------------------------
// Initialization & Event Listeners
// -------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  setupSettingsHandlers();
});

function setupEventListeners() {
  // Modal Handlers
  btnGuide.addEventListener('click', () => guideModal.classList.remove('hidden'));
  btnCloseModal.addEventListener('click', () => guideModal.classList.add('hidden'));
  btnCloseModalBtn.addEventListener('click', () => guideModal.classList.add('hidden'));
  guideModal.querySelector('.modal-backdrop').addEventListener('click', () => guideModal.classList.add('hidden'));

  // Drag & Drop Handlers
  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('dragover');
    });
  });

  dropZone.addEventListener('drop', handleFileDrop);

  // File Browsing (Native or HTML Input)
  btnBrowseFiles.addEventListener('click', (e) => {
    e.stopPropagation();
    openFilesDialog();
  });

  btnBrowseFolder.addEventListener('click', (e) => {
    e.stopPropagation();
    openFolderDialog();
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadAndAnalyzeFiles(Array.from(e.target.files));
    }
  });

  // Export XML
  btnExportXml.addEventListener('click', handleExportXml);

  // Clear All Tracks
  btnClearAll.addEventListener('click', () => {
    if (confirm('Очистить весь список треков?')) {
      stopActiveAudio();
      state.tracks = [];
      renderTracksList();
    }
  });

  // Apply to All Tracks
  btnApplyAll.addEventListener('click', () => {
    recalculateAllTracks();
  });
}

function setupSettingsHandlers() {
  // Interval Pills
  document.querySelectorAll('.btn-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      customIntervalInput.value = '';
      state.currentInterval = parseInt(btn.getAttribute('data-interval'), 10);
      recalculateAllTracks();
    });
  });

  customIntervalInput.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    if (val && val > 0) {
      document.querySelectorAll('.btn-pill').forEach(b => b.classList.remove('active'));
      state.currentInterval = val;
      recalculateAllTracks();
    }
  });

  // BPM Range Selector
  bpmRangeSelect.addEventListener('change', (e) => {
    const val = e.target.value;
    if (val === 'custom') {
      customBpmRangeWrap.classList.remove('hidden');
      state.minBpm = parseFloat(minBpmInput.value) || 60;
      state.maxBpm = parseFloat(maxBpmInput.value) || 180;
    } else {
      customBpmRangeWrap.classList.add('hidden');
      const parts = val.split('-');
      if (parts.length === 2) {
        state.minBpm = parseFloat(parts[0]);
        state.maxBpm = parseFloat(parts[1]);
        minBpmInput.value = state.minBpm;
        maxBpmInput.value = state.maxBpm;
      }
    }
    recalculateAllTracks();
  });

  const onCustomBpmChange = () => {
    const minVal = parseFloat(minBpmInput.value);
    const maxVal = parseFloat(maxBpmInput.value);
    if (minVal > 0 && maxVal >= minVal) {
      state.minBpm = minVal;
      state.maxBpm = maxVal;
      recalculateAllTracks();
    }
  };
  minBpmInput.addEventListener('change', onCustomBpmChange);
  maxBpmInput.addEventListener('change', onCustomBpmChange);

  cueModeSelect.addEventListener('change', (e) => {
    state.cueMode = e.target.value;
    recalculateAllTracks();
  });

  namingTemplateSelect.addEventListener('change', (e) => {
    state.namingTemplate = e.target.value;
    recalculateAllTracks();
  });

  maxHotCuesSelect.addEventListener('change', (e) => {
    state.maxHotCues = parseInt(e.target.value, 10);
    recalculateAllTracks();
  });

  maxMemoryCuesSelect.addEventListener('change', (e) => {
    state.maxMemoryCues = parseInt(e.target.value, 10);
    recalculateAllTracks();
  });

  // XML Export Checkboxes
  chkExportBeatgrid.addEventListener('change', (e) => {
    state.exportBeatgrid = e.target.checked;
  });

  chkExportBpm.addEventListener('change', (e) => {
    state.exportBpm = e.target.checked;
  });

  chkExportHotCues.addEventListener('change', (e) => {
    state.exportHotCues = e.target.checked;
  });

  chkExportMemoryCues.addEventListener('change', (e) => {
    state.exportMemoryCues = e.target.checked;
  });
}


// -------------------------------------------------------------
// File Selection & Analysis
// -------------------------------------------------------------

async function openFilesDialog() {
  try {
    const res = await fetch('/api/pick-files', { method: 'POST' });
    const data = await res.json();
    if (data.files && data.files.length > 0) {
      analyzeLocalPaths(data.files);
      return;
    }
  } catch (err) {
    console.log('Native file dialog fallback to HTML input', err);
  }
  fileInput.click();
}

async function openFolderDialog() {
  try {
    const res = await fetch('/api/pick-folder', { method: 'POST' });
    const data = await res.json();
    if (data.files && data.files.length > 0) {
      analyzeLocalPaths(data.files);
      return;
    } else if (data.folder && (!data.files || data.files.length === 0)) {
      alert('В выбранной папке не найдено подходящих аудиофайлов (MP3, WAV, FLAC, AIFF, M4A, OGG).');
    }
  } catch (err) {
    console.log('Folder dialog fallback', err);
    alert('Для выбора папки перетащите ее напрямую в окно программы.');
  }
}

async function handleFileDrop(e) {
  const dt = e.dataTransfer;
  const files = Array.from(dt.files);
  if (files.length > 0) {
    uploadAndAnalyzeFiles(files);
  }
}

async function uploadAndAnalyzeFiles(files) {
  const audioFiles = files.filter(f => /\.(mp3|wav|flac|aiff|aif|m4a|ogg)$/i.test(f.name));
  if (audioFiles.length === 0) {
    alert('Пожалуйста, выберите аудиофайлы (MP3, WAV, FLAC, AIFF, M4A, OGG).');
    return;
  }

  showProgress('Загрузка и анализ треков...', 10);

  const formData = new FormData();
  audioFiles.forEach(file => formData.append('files', file));
  formData.append('bar_interval', state.currentInterval);
  formData.append('cue_mode', state.cueMode);
  formData.append('naming_template', state.namingTemplate);
  formData.append('max_hot_cues', state.maxHotCues);
  formData.append('max_memory_cues', state.maxMemoryCues);
  formData.append('min_bpm', state.minBpm);
  formData.append('max_bpm', state.maxBpm);

  try {
    showProgress('Выполняется глубокий аудио-анализ (BPM, Beatgrid)...', 45);
    const res = await fetch('/api/analyze-upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (data.tracks && data.tracks.length > 0) {
      appendTracks(data.tracks);
    }
    if (data.errors && data.errors.length > 0) {
      console.warn('Analysis warnings/errors:', data.errors);
    }
    showProgress('Готово!', 100);
    setTimeout(hideProgress, 600);
  } catch (err) {
    hideProgress();
    alert('Ошибка при анализе файлов: ' + err.message);
  }
}

async function analyzeLocalPaths(filePaths) {
  showProgress('Анализ локальных треков...', 20);

  try {
    const res = await fetch('/api/analyze-path', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_paths: filePaths,
        bar_interval: state.currentInterval,
        cue_mode: state.cueMode,
        naming_template: state.namingTemplate,
        max_hot_cues: state.maxHotCues,
        max_memory_cues: state.maxMemoryCues,
        min_bpm: state.minBpm,
        max_bpm: state.maxBpm
      })
    });
    const data = await res.json();

    if (data.tracks && data.tracks.length > 0) {
      appendTracks(data.tracks);
    }
    if (data.errors && data.errors.length > 0) {
      console.warn('Analysis warnings/errors:', data.errors);
    }
    showProgress('Готово!', 100);
    setTimeout(hideProgress, 600);
  } catch (err) {
    hideProgress();
    alert('Ошибка анализа: ' + err.message);
  }
}

function appendTracks(newTracks) {
  newTracks.forEach(t => {
    t.id = 'track_' + Math.random().toString(36).substr(2, 9);
    state.tracks.push(t);
  });
  renderTracksList();
}


// -------------------------------------------------------------
// Progress Helper
// -------------------------------------------------------------

function showProgress(status, percent) {
  progressContainer.classList.remove('hidden');
  progressStatus.textContent = status;
  progressBar.style.width = percent + '%';
  progressPercent.textContent = percent + '%';
}

function hideProgress() {
  progressContainer.classList.add('hidden');
}


// -------------------------------------------------------------
// Recalculation Engine
// -------------------------------------------------------------

async function recalculateAllTracks() {
  for (const track of state.tracks) {
    // If BPM is outside target range, adjust it
    if (state.minBpm > 0 && state.maxBpm >= state.minBpm) {
      while (track.bpm < state.minBpm && (track.bpm * 2 <= state.maxBpm * 1.05 || track.bpm * 2 <= state.minBpm + (state.maxBpm - state.minBpm) * 0.5)) {
        track.bpm = Math.round(track.bpm * 2 * 100) / 100;
      }
      while (track.bpm > state.maxBpm && (track.bpm / 2 >= state.minBpm * 0.95 || track.bpm / 2 >= state.minBpm)) {
        track.bpm = Math.round((track.bpm / 2) * 100) / 100;
      }
    }
    await recalculateTrackCues(track);
  }
  renderTracksList();
}

async function recalculateTrackCues(track) {
  try {
    const res = await fetch('/api/recalculate-cues', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        duration: track.duration,
        bpm: track.bpm,
        first_beat_offset: track.first_beat_offset,
        bar_interval: state.currentInterval,
        cue_mode: state.cueMode,
        naming_template: state.namingTemplate,
        max_hot_cues: state.maxHotCues,
        max_memory_cues: state.maxMemoryCues
      })
    });
    const data = await res.json();
    if (data.cue_points) {
      track.cue_points = data.cue_points;
    }
  } catch (e) {
    console.error('Error recalculating cues:', e);
  }
}


// -------------------------------------------------------------
// Rendering Tracks List
// -------------------------------------------------------------

function renderTracksList() {
  tracksCount.textContent = state.tracks.length;
  exportCount.textContent = state.tracks.length;
  btnExportXml.disabled = state.tracks.length === 0;
  btnClearAll.style.display = state.tracks.length > 0 ? 'inline-flex' : 'none';

  if (state.tracks.length === 0) {
    tracksList.innerHTML = `
      <div class="empty-state" id="emptyState">
        <p>Треки еще не добавлены. Закиньте аудиофайлы в область выше, чтобы начать анализ.</p>
      </div>
    `;
    return;
  }

  tracksList.innerHTML = '';
  state.tracks.forEach(track => {
    const card = createTrackCard(track);
    tracksList.appendChild(card);
    drawWaveform(track);
  });
}

function createTrackCard(track) {
  const card = document.createElement('div');
  card.className = 'track-card';
  card.id = `card_${track.id}`;

  const formatMinSec = (sec) => {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  card.innerHTML = `
    <div class="track-top-bar">
      <div class="track-info">
        <h4 class="track-title">${escapeHtml(track.title || track.file_name)}</h4>
        <div class="track-meta">
          <span>${escapeHtml(track.artist || 'Unknown Artist')}</span>
          <span class="badge-tag">${track.kind || 'MP3'}</span>
          <span>${track.bitrate} kbps</span>
          <span>${track.samplerate} Hz</span>
          <span>⏱ ${formatMinSec(track.duration)}</span>
        </div>
      </div>
      <button class="track-btn-remove" title="Удалить трек" onclick="removeTrack('${track.id}')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="icon-sm">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>

    <!-- Waveform with Markers -->
    <div class="waveform-container">
      <div class="waveform-canvas-wrapper" id="canvas_wrap_${track.id}">
        <canvas class="waveform-canvas" id="canvas_${track.id}"></canvas>
        <div class="playhead" id="playhead_${track.id}"></div>
      </div>
      <div class="waveform-controls">
        <div class="playback-controls">
          <button class="btn-play" id="btn_play_${track.id}" onclick="togglePlayTrack('${track.id}')">
            <svg viewBox="0 0 24 24" fill="currentColor" class="icon-sm" id="icon_play_${track.id}">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
          </button>
          <div class="time-display" id="time_${track.id}">
            0:00 / ${formatMinSec(track.duration)}
          </div>
        </div>
        <div class="track-meta">
          <span style="color: var(--accent-cyan)">Точек: <strong>${track.cue_points ? track.cue_points.length : 0}</strong></span>
          <span>Шаг: <strong>${state.currentInterval} бар.</strong></span>
        </div>
      </div>
    </div>

    <!-- Fine Tuning Parameters -->
    <div class="track-fine-tune">
      <div class="fine-tune-field">
        <label class="fine-tune-label">Темп (BPM)</label>
        <div class="input-group">
          <input type="number" step="0.01" class="input-num" value="${track.bpm}" 
                 onchange="updateTrackBpm('${track.id}', this.value)">
          <button class="btn-nudge" title="Вдвое меньше" onclick="adjustBpm('${track.id}', 0.5)">/2</button>
          <button class="btn-nudge" title="Вдвое больше" onclick="adjustBpm('${track.id}', 2.0)">x2</button>
        </div>
      </div>

      <div class="fine-tune-field">
        <label class="fine-tune-label">Смещение 1-го удара (мс)</label>
        <div class="input-group">
          <input type="number" step="1" class="input-num" value="${Math.round(track.first_beat_offset * 1000)}" 
                 onchange="updateTrackOffset('${track.id}', this.value / 1000)">
          <button class="btn-nudge" onclick="nudgeOffset('${track.id}', -0.010)">-10ms</button>
          <button class="btn-nudge" onclick="nudgeOffset('${track.id}', +0.010)">+10ms</button>
          <button class="btn-nudge" onclick="nudgeOffset('${track.id}', -0.050)">-50ms</button>
          <button class="btn-nudge" onclick="nudgeOffset('${track.id}', +0.050)">+50ms</button>
        </div>
      </div>
    </div>

    <!-- Cue Points Chips List -->
    <div class="cue-chips-container">
      <div class="cue-chips-title">Расставленные точки (нажмите на точку для перехода):</div>
      <div class="cue-chips-list">
        ${renderCueChips(track)}
      </div>
    </div>
  `;

  // Canvas Click Seeking
  setTimeout(() => {
    const wrap = card.querySelector(`#canvas_wrap_${track.id}`);
    if (wrap) {
      wrap.addEventListener('click', (e) => {
        const rect = wrap.getBoundingClientRect();
        const clickRatio = (e.clientX - rect.left) / rect.width;
        seekTrackPosition(track.id, clickRatio * track.duration);
      });
    }
  }, 50);

  return card;
}

function renderCueChips(track) {
  if (!track.cue_points || track.cue_points.length === 0) {
    return `<span style="font-size:0.75rem; color:var(--text-dim)">Нет точек</span>`;
  }

  return track.cue_points.map(cue => {
    const rgb = cue.color ? `rgb(${cue.color.r}, ${cue.color.g}, ${cue.color.b})` : '#00bcd4';
    let badges = '';
    if (cue.is_hot_cue && cue.hot_cue_letter) {
      badges += `<span class="cue-chip-hot">[Hot ${cue.hot_cue_letter}]</span>`;
    }
    if (cue.is_memory_cue) {
      badges += `<span class="cue-chip-mem" style="font-size:0.7rem; color:var(--accent-orange); margin-right:4px;">[Mem]</span>`;
    }
    return `
      <div class="cue-chip" onclick="seekTrackPosition('${track.id}', ${cue.timestamp})" title="Перейти к ${cue.time_formatted}">
        <span class="cue-color-dot" style="background: ${rgb}; box-shadow: 0 0 6px ${rgb}"></span>
        ${badges}
        <span class="cue-chip-name">${escapeHtml(cue.name)}</span>
        <span class="cue-chip-time">${cue.time_formatted}</span>
      </div>
    `;
  }).join('');
}


// -------------------------------------------------------------
// Waveform Drawing Engine
// -------------------------------------------------------------

function drawWaveform(track) {
  const canvas = document.getElementById(`canvas_${track.id}`);
  if (!canvas) return;

  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = rect.width || 800;
  const height = rect.height || 90;

  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  ctx.clearRect(0, 0, width, height);

  // 1. Draw Waveform Peaks
  const peaks = track.peaks || [];
  const numPeaks = peaks.length;
  const centerY = height / 2;

  const gradient = ctx.createLinearGradient(0, 0, width, 0);
  gradient.addColorStop(0, '#00d2ff');
  gradient.addColorStop(0.5, '#0088ff');
  gradient.addColorStop(1, '#00e676');

  ctx.fillStyle = gradient;

  if (numPeaks > 0) {
    const barWidth = Math.max(1, width / numPeaks);
    for (let i = 0; i < numPeaks; i++) {
      const peakVal = peaks[i];
      const barHeight = Math.max(2, peakVal * (height * 0.88));
      const x = i * (width / numPeaks);
      const y = centerY - barHeight / 2;
      ctx.fillRect(x, y, Math.max(1, barWidth - 0.5), barHeight);
    }
  }

  // 2. Draw Cue Markers
  const cues = track.cue_points || [];
  cues.forEach(cue => {
    if (track.duration <= 0) return;
    const xRatio = cue.timestamp / track.duration;
    if (xRatio < 0 || xRatio > 1) return;

    const x = xRatio * width;
    const rgb = cue.color ? `rgb(${cue.color.r}, ${cue.color.g}, ${cue.color.b})` : '#ff9100';

    // Vertical line
    ctx.strokeStyle = rgb;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 2]);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
    ctx.setLineDash([]);

    // Cue Badge Tag at top
    ctx.fillStyle = rgb;
    let tagText = '◆';
    if (cue.is_hot_cue && cue.hot_cue_letter) {
      tagText = cue.hot_cue_letter;
    } else if (cue.is_memory_cue) {
      tagText = 'M';
    }
    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    const textWidth = ctx.measureText(tagText).width;
    
    ctx.beginPath();
    ctx.roundRect(x - (textWidth + 6) / 2, 2, textWidth + 6, 14, 3);
    ctx.fill();

    ctx.fillStyle = '#000000';
    ctx.fillText(tagText, x - textWidth / 2, 12);
  });
}


// -------------------------------------------------------------
// Audio Playback & Scrubber Controls
// -------------------------------------------------------------

function togglePlayTrack(trackId) {
  const track = state.tracks.find(t => t.id === trackId);
  if (!track) return;

  // If already playing this track, pause it
  if (state.activeTrackId === trackId && state.activeAudio) {
    if (state.activeAudio.paused) {
      state.activeAudio.play();
      updatePlayButton(trackId, true);
    } else {
      state.activeAudio.pause();
      updatePlayButton(trackId, false);
    }
    return;
  }

  // Stop previous track if any
  stopActiveAudio();

  // Create new Audio
  const audioUrl = `/api/audio-stream?path=${encodeURIComponent(track.file_path)}`;
  const audio = new Audio(audioUrl);
  state.activeAudio = audio;
  state.activeTrackId = trackId;

  audio.addEventListener('timeupdate', () => {
    updatePlaybackProgress(trackId, audio.currentTime, track.duration);
  });

  audio.addEventListener('ended', () => {
    updatePlayButton(trackId, false);
    resetPlayhead(trackId);
  });

  audio.play().then(() => {
    updatePlayButton(trackId, true);
  }).catch(err => {
    console.error('Audio playback error:', err);
  });
}

function stopActiveAudio() {
  if (state.activeAudio) {
    state.activeAudio.pause();
    state.activeAudio = null;
  }
  if (state.activeTrackId) {
    updatePlayButton(state.activeTrackId, false);
    state.activeTrackId = null;
  }
}

function seekTrackPosition(trackId, targetSeconds) {
  const track = state.tracks.find(t => t.id === trackId);
  if (!track) return;

  targetSeconds = Math.max(0, Math.min(track.duration, targetSeconds));

  if (state.activeTrackId === trackId && state.activeAudio) {
    state.activeAudio.currentTime = targetSeconds;
  } else {
    // If not already playing, start playing from this point
    togglePlayTrack(trackId);
    if (state.activeAudio) {
      state.activeAudio.currentTime = targetSeconds;
    }
  }

  updatePlaybackProgress(trackId, targetSeconds, track.duration);
}

function updatePlaybackProgress(trackId, currentSec, totalSec) {
  const playhead = document.getElementById(`playhead_${trackId}`);
  const timeDisplay = document.getElementById(`time_${trackId}`);
  
  if (playhead && totalSec > 0) {
    const ratio = (currentSec / totalSec) * 100;
    playhead.style.left = `${ratio}%`;
  }

  if (timeDisplay) {
    const formatMinSec = (sec) => {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return `${m}:${s < 10 ? '0' : ''}${s}`;
    };
    timeDisplay.textContent = `${formatMinSec(currentSec)} / ${formatMinSec(totalSec)}`;
  }
}

function resetPlayhead(trackId) {
  const playhead = document.getElementById(`playhead_${trackId}`);
  if (playhead) playhead.style.left = '0%';
}

function updatePlayButton(trackId, isPlaying) {
  const btn = document.getElementById(`btn_play_${trackId}`);
  if (!btn) return;

  if (isPlaying) {
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="currentColor" class="icon-sm">
        <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
      </svg>
    `;
  } else {
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="currentColor" class="icon-sm">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
    `;
  }
}


// -------------------------------------------------------------
// Track Adjustments (BPM & Offset Nudge)
// -------------------------------------------------------------

async function updateTrackBpm(trackId, newBpm) {
  const track = state.tracks.find(t => t.id === trackId);
  if (!track) return;
  const bpmVal = parseFloat(newBpm);
  if (bpmVal > 20 && bpmVal < 400) {
    track.bpm = bpmVal;
    await recalculateTrackCues(track);
    renderTracksList();
  }
}

async function adjustBpm(trackId, factor) {
  const track = state.tracks.find(t => t.id === trackId);
  if (!track) return;
  track.bpm = Math.round((track.bpm * factor) * 100) / 100;
  await recalculateTrackCues(track);
  renderTracksList();
}

async function updateTrackOffset(trackId, newOffsetSec) {
  const track = state.tracks.find(t => t.id === trackId);
  if (!track) return;
  track.first_beat_offset = Math.max(0, parseFloat(newOffsetSec));
  await recalculateTrackCues(track);
  renderTracksList();
}

async function nudgeOffset(trackId, deltaSec) {
  const track = state.tracks.find(t => t.id === trackId);
  if (!track) return;
  track.first_beat_offset = Math.max(0, Math.round((track.first_beat_offset + deltaSec) * 1000) / 1000);
  await recalculateTrackCues(track);
  renderTracksList();
}

function removeTrack(trackId) {
  if (state.activeTrackId === trackId) {
    stopActiveAudio();
  }
  state.tracks = state.tracks.filter(t => t.id !== trackId);
  renderTracksList();
}


// -------------------------------------------------------------
// Rekordbox XML Export
// -------------------------------------------------------------

async function handleExportXml() {
  if (state.tracks.length === 0) {
    alert('Сначала добавьте хотя бы один трек.');
    return;
  }

  if (!state.exportBeatgrid && !state.exportBpm && !state.exportHotCues && !state.exportMemoryCues) {
    alert('Пожалуйста, выберите хотя бы один параметр для экспорта в XML (сетка, BPM, Hot Cues или Memory Cues).');
    return;
  }

  try {
    const res = await fetch('/api/export-xml', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tracks: state.tracks,
        playlist_name: 'Auto Cues',
        export_beatgrid: state.exportBeatgrid,
        export_bpm: state.exportBpm,
        export_hot_cues: state.exportHotCues,
        export_memory_cues: state.exportMemoryCues
      })
    });

    if (!res.ok) {
      throw new Error('Export failed');
    }

    // Trigger file download
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'rekordbox_auto_cues.xml';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    // Open Guide modal to remind user how to import
    guideModal.classList.remove('hidden');
  } catch (err) {
    alert('Ошибка при экспорте XML: ' + err.message);
  }
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Clean shutdown when window is closed
window.addEventListener('beforeunload', () => {
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/shutdown');
    }
  } catch (e) {}
});

