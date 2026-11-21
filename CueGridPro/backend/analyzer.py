import os
import math
import numpy as np
import mutagen
from mutagen.easyid3 import EasyID3
import soundfile as sf
import librosa
from typing import Dict, List, Optional, Any


# Standard Rekordbox Color Palette presets
HOT_CUE_COLORS = [
    {"r": 255, "g": 0, "b": 0, "name": "Red"},         # Cue A / Bar 0
    {"r": 255, "g": 128, "b": 0, "name": "Orange"},    # Cue B / Bar 16
    {"r": 255, "g": 215, "b": 0, "name": "Yellow"},    # Cue C / Bar 32
    {"r": 0, "g": 230, "b": 118, "name": "Green"},     # Cue D / Bar 48
    {"r": 0, "g": 229, "b": 255, "name": "Cyan"},      # Cue E / Bar 64
    {"r": 41, "g": 121, "b": 255, "name": "Blue"},     # Cue F / Bar 80
    {"r": 213, "g": 0, "b": 249, "name": "Purple"},    # Cue G / Bar 96
    {"r": 255, "g": 64, "b": 129, "name": "Pink"},     # Cue H / Bar 112
    {"r": 0, "g": 200, "b": 83, "name": "Emerald"},
    {"r": 255, "g": 171, "b": 0, "name": "Amber"},
    {"r": 0, "g": 176, "b": 255, "name": "Light Blue"},
    {"r": 170, "g": 0, "b": 255, "name": "Violet"},
    {"r": 255, "g": 23, "b": 68, "name": "Crimson"},
    {"r": 118, "g": 255, "b": 3, "name": "Lime"},
    {"r": 255, "g": 145, "b": 0, "name": "Deep Orange"},
    {"r": 224, "g": 64, "b": 251, "name": "Magenta"}
]

HOT_CUE_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P"]


def extract_metadata(file_path: str) -> Dict[str, Any]:
    """Extract metadata (title, artist, album, duration, bitrate, sample rate) from audio file."""
    file_name = os.path.basename(file_path)
    base_name, ext = os.path.splitext(file_name)
    
    metadata = {
        "title": base_name,
        "artist": "Unknown Artist",
        "album": "",
        "duration": 0.0,
        "bitrate": 320,
        "samplerate": 44100,
        "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        "kind": f"{ext.upper().replace('.', '')} File",
        "bpm_tag": None
    }
    
    try:
        audio = mutagen.File(file_path)
        if audio is not None:
            if hasattr(audio, 'info'):
                if hasattr(audio.info, 'length'):
                    metadata["duration"] = float(audio.info.length)
                if hasattr(audio.info, 'bitrate'):
                    metadata["bitrate"] = int(audio.info.bitrate / 1000) if audio.info.bitrate else 320
                if hasattr(audio.info, 'sample_rate'):
                    metadata["samplerate"] = int(audio.info.sample_rate)
            
            # Tags extraction
            tags = audio.tags
            if tags:
                # MP3 EasyID3 or standard tags
                if hasattr(tags, 'get'):
                    metadata["title"] = str(tags.get('title', [metadata["title"]])[0]) if isinstance(tags.get('title'), list) else str(tags.get('title', metadata["title"]))
                    metadata["artist"] = str(tags.get('artist', [metadata["artist"]])[0]) if isinstance(tags.get('artist'), list) else str(tags.get('artist', metadata["artist"]))
                    metadata["album"] = str(tags.get('album', [''])[0]) if isinstance(tags.get('album'), list) else str(tags.get('album', ''))
                    
                    # Try to find existing BPM tag
                    bpm_val = tags.get('bpm') or tags.get('TBPM') or tags.get('BPM')
                    if bpm_val:
                        try:
                            val_str = str(bpm_val[0] if isinstance(bpm_val, list) else bpm_val).strip()
                            metadata["bpm_tag"] = float(val_str)
                        except (ValueError, TypeError):
                            pass
    except Exception as e:
        print(f"Warning: Error reading metadata for {file_path}: {e}")
        
    return metadata


def generate_waveform_peaks(y: np.ndarray, num_peaks: int = 800) -> List[float]:
    """Generate normalized amplitude peaks for fast UI waveform rendering."""
    if len(y) == 0:
        return [0.0] * num_peaks
    
    # Absolute amplitude
    y_abs = np.abs(y)
    samples_per_peak = max(1, len(y_abs) // num_peaks)
    peaks = []
    
    for i in range(num_peaks):
        start = i * samples_per_peak
        end = min(len(y_abs), start + samples_per_peak)
        if start < len(y_abs):
            chunk_max = float(np.max(y_abs[start:end])) if start < end else 0.0
            peaks.append(round(chunk_max, 4))
        else:
            peaks.append(0.0)
            
    # Normalize to 0.0 - 1.0 range
    max_val = max(peaks) if peaks and max(peaks) > 0 else 1.0
    normalized_peaks = [round(p / max_val, 3) for p in peaks]
    return normalized_peaks


def generate_synthetic_peaks_for_grid(duration: float, bpm: float, first_beat_offset: float, num_peaks: int = 800) -> List[float]:
    """
    Generates a clean rhythmic visual envelope when only Rekordbox XML metadata is loaded
    and the raw audio file is not scanned or not on the current drive.
    """
    if duration <= 0 or bpm <= 0:
        return [0.35] * num_peaks
    beat_sec = 60.0 / bpm
    bar_sec = 4.0 * beat_sec
    peaks = []
    for i in range(num_peaks):
        t = (i / num_peaks) * duration
        if t < first_beat_offset:
            peaks.append(0.2)
            continue
        rel_t = t - first_beat_offset
        beat_phase = (rel_t % beat_sec) / beat_sec
        bar_phase = (rel_t % bar_sec) / bar_sec
        pulse = math.exp(-6.0 * beat_phase) * 0.55 + (0.25 if bar_phase < 0.25 else 0.1)
        peaks.append(round(min(1.0, max(0.15, pulse)), 3))
    return peaks


def fast_extract_peaks_and_duration(file_path: str, fallback_duration: float, bpm: float, first_beat_offset: float, num_peaks: int = 800) -> Dict[str, Any]:
    """
    Fast extraction of waveform peaks (without running heavy BPM / Beatgrid DSP)
    for tracks whose Beatgrid & BPM are already imported from Rekordbox XML.
    """
    if file_path and os.path.exists(file_path):
        try:
            y, sr = librosa.load(file_path, sr=8000, mono=True)
            dur = len(y) / sr if sr > 0 else fallback_duration
            peaks = generate_waveform_peaks(y, num_peaks=num_peaks)
            return {"duration": round(float(dur), 2), "peaks": peaks, "audio_available": True}
        except Exception:
            pass
    return {
        "duration": round(float(fallback_duration), 2),
        "peaks": generate_synthetic_peaks_for_grid(fallback_duration, bpm, first_beat_offset, num_peaks=num_peaks),
        "audio_available": False
    }


import scipy.signal


def estimate_accurate_bpm(
    y: np.ndarray,
    sr: int,
    min_bpm: float = 60.0,
    max_bpm: float = 180.0,
    bpm_tag: Optional[float] = None
) -> float:
    """
    Robust, DJ-grade BPM estimation:
    1. Multi-band onset envelopes (Kick transients <= 250Hz + Mid percussions + Full spectrum flux)
    2. Fourier Tempogram peak detection (eliminates lag-15 / 172.26 BPM quantization artifacts)
    3. Multi-harmonic Comb filter autocorrelation scoring
    4. Beat-phase pulse consistency cross-correlation
    5. Target range normalization and harmonic selection
    """
    hop_length = 512
    frame_rate = sr / hop_length

    # 1. Multi-band Mel-Spectrogram
    S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=8000, hop_length=hop_length)
    S_db = librosa.power_to_db(S, ref=np.max)

    # Full-band onset strength
    onset_full = librosa.onset.onset_strength(S=S_db, sr=sr, hop_length=hop_length)

    # Low-band kick drum onset strength (bottom 16 mel bins ~= up to ~250-300 Hz)
    S_low = S_db[:16, :]
    onset_low = librosa.onset.onset_strength(S=S_low, sr=sr, hop_length=hop_length)

    # Mid-band snare/clap onset strength (bins 16 to 48 ~= 300Hz - 2kHz)
    S_mid = S_db[16:48, :]
    onset_mid = librosa.onset.onset_strength(S=S_mid, sr=sr, hop_length=hop_length)

    # Combined onset envelope (emphasizing kick downbeats)
    onset_comb = 0.55 * onset_low + 0.30 * onset_mid + 0.15 * onset_full
    onset_comb = (onset_comb - np.mean(onset_comb)) / (np.std(onset_comb) + 1e-6)
    onset_comb = np.maximum(0, onset_comb)

    # 2. Fourier Tempogram (frequency domain tempo energy)
    ft = librosa.feature.fourier_tempogram(onset_envelope=onset_comb, sr=sr, hop_length=hop_length, win_length=384)
    ft_mag = np.mean(np.abs(ft), axis=1)
    ft_freqs = librosa.fourier_tempo_frequencies(sr=sr, hop_length=hop_length, win_length=384)

    # 3. Autocorrelation of onset envelope
    max_lag = int(frame_rate * 60.0 / 40.0)  # down to 40 BPM
    min_lag = int(frame_rate * 60.0 / 260.0) # up to 260 BPM
    ac = np.correlate(onset_comb, onset_comb, mode='full')
    ac = ac[len(onset_comb) - 1 :]
    if len(ac) > max_lag:
        ac = ac[:max_lag]
    ac = (ac - np.min(ac)) / (np.max(ac) - np.min(ac) + 1e-6)

    # 4. Candidate Generation from Fourier peaks & ACF peaks
    candidate_bpms = set()

    # A) Fourier tempogram peaks with parabolic interpolation
    ft_valid = (ft_freqs >= 45) & (ft_freqs <= 250)
    ft_sub_freqs = ft_freqs[ft_valid]
    ft_sub_mag = ft_mag[ft_valid]
    peaks_ft, _ = scipy.signal.find_peaks(ft_sub_mag, distance=3, prominence=0.04 * np.max(ft_sub_mag))
    for p in peaks_ft:
        if 0 < p < len(ft_sub_freqs) - 1:
            alpha, beta, gamma = ft_sub_mag[p - 1], ft_sub_mag[p], ft_sub_mag[p + 1]
            denom = alpha - 2 * beta + gamma
            if abs(denom) > 1e-6:
                delta = np.clip(0.5 * (alpha - gamma) / denom, -0.5, 0.5)
                f_interp = np.interp(p + delta, np.arange(len(ft_sub_freqs)), ft_sub_freqs)
                candidate_bpms.add(f_interp)
        candidate_bpms.add(ft_sub_freqs[p])

    # B) Autocorrelation peaks with parabolic interpolation
    peaks_ac, _ = scipy.signal.find_peaks(ac, distance=max(2, min_lag), prominence=0.03)
    for p in peaks_ac:
        if min_lag <= p <= max_lag:
            lag = float(p)
            if 0 < p < len(ac) - 1:
                alpha, beta, gamma = ac[p - 1], ac[p], ac[p + 1]
                denom = alpha - 2 * beta + gamma
                if abs(denom) > 1e-6:
                    delta = np.clip(0.5 * (alpha - gamma) / denom, -0.5, 0.5)
                    lag = p + delta
            bpm_val = (frame_rate * 60.0) / lag
            if 45.0 <= bpm_val <= 250.0:
                candidate_bpms.add(bpm_val)

    # If ID3 BPM tag is available, include it and its harmonics
    if bpm_tag and bpm_tag > 0:
        candidate_bpms.add(float(bpm_tag))
        candidate_bpms.add(float(bpm_tag * 2.0))
        candidate_bpms.add(float(bpm_tag / 2.0))

    # Add harmonic ratios (octaves get full weight 1.0, fractional ratios get 0.82 weight)
    all_candidates = set()
    for c in candidate_bpms:
        for factor in [0.5, 1.0, 2.0, 4.0, 0.25]:
            b = c * factor
            if 40.0 <= b <= 320.0:
                all_candidates.add((b, 1.0))
                all_candidates.add((float(round(b)), 1.0))
        for factor in [0.75, 1.33333, 1.5, 0.66667]:
            b = c * factor
            if 40.0 <= b <= 320.0:
                all_candidates.add((b, 0.82))
                all_candidates.add((float(round(b)), 0.82))

    range_center = (min_bpm + max_bpm) / 2.0 if min_bpm > 0 and max_bpm >= min_bpm else 125.0

    # 5. Candidate scoring function
    def score_bpm(bpm_cand: float, ratio_weight: float = 1.0) -> float:
        if bpm_cand <= 0:
            return 0.0
        lag = frame_rate * 60.0 / bpm_cand

        # Harmonic comb sum on autocorrelation
        comb_score = 0.0
        weights = [1.0, 0.75, 0.4, 0.25]
        for idx, w in enumerate(weights, start=1):
            h_lag = int(round(lag * idx))
            if h_lag < len(ac):
                comb_score += w * ac[h_lag]

        # Fourier energy score
        ft_idx = np.argmin(np.abs(ft_freqs - bpm_cand))
        fourier_score = ft_mag[ft_idx] if ft_idx < len(ft_mag) else 0.0

        # Beat alignment score across onset_comb (pulse train consistency)
        step = lag
        num_test_beats = min(64, int(len(onset_comb) / max(1, step)))
        if num_test_beats > 4:
            phase_scores = []
            for phase_ratio in np.linspace(0, 1, 16, endpoint=False):
                phase = phase_ratio * step
                beat_indices = (phase + np.arange(num_test_beats) * step).astype(int)
                beat_indices = beat_indices[beat_indices < len(onset_comb)]
                if len(beat_indices) > 0:
                    phase_scores.append(np.mean(onset_comb[beat_indices]))
            beat_pulse_score = max(phase_scores) if phase_scores else 0.0
        else:
            beat_pulse_score = 0.0

        # Target range prior
        if min_bpm <= bpm_cand <= max_bpm:
            range_multiplier = 1.25
        else:
            dist = min(abs(bpm_cand - min_bpm), abs(bpm_cand - max_bpm))
            range_multiplier = np.exp(-0.5 * (dist / 30.0)**2)

        # ID3 tag bonus if matching
        tag_bonus = 1.0
        if bpm_tag and (abs(bpm_cand - bpm_tag) < 0.5 or abs(bpm_cand - bpm_tag * 2) < 0.5 or abs(bpm_cand - bpm_tag / 2) < 0.5):
            tag_bonus = 1.2

        total_score = (comb_score * 0.45 + (fourier_score / (np.max(ft_mag) + 1e-6)) * 0.35 + beat_pulse_score * 0.20) * range_multiplier * tag_bonus * ratio_weight
        return float(total_score)

    best_bpm = range_center
    best_score = -1.0

    for cand, r_weight in all_candidates:
        s = score_bpm(cand, r_weight)
        if s > best_score:
            best_score = s
            best_bpm = cand

    # Fine-tune in ±1.0 range around best_bpm
    local_grid = np.linspace(best_bpm - 1.0, best_bpm + 1.0, 21)
    for cand in local_grid:
        s = score_bpm(cand, 1.0)
        if s > best_score:
            best_score = s
            best_bpm = cand

    # Normalize strictly into [min_bpm, max_bpm]
    while best_bpm < min_bpm:
        best_bpm *= 2.0
    while best_bpm > max_bpm:
        best_bpm /= 2.0

    return float(round(best_bpm))


def detect_accurate_first_beat(y: np.ndarray, sr: int, bpm: float) -> float:
    """
    Finds the exact timestamp of Bar 1, Beat 1 (Downbeat / First Bar Origin).
    
    1. Detects earliest audible audio in the first 1.5s (MP3 encoder delay / track start).
       If audio starts immediately (< 0.03s), snaps to 0.000s matching Rekordbox 1.1 grid marker.
    2. Uses Butterworth bandpass filters for Sub-bass Kick (35-140 Hz) and Snare (300-3000 Hz).
    3. Searches for the 4-beat bar phase offset phi in [0, bar_sec) that maximizes kick energy
       on Beat 1 & 3 and snare energy on Beat 2 & 4, while heavily penalizing snare energy on Beat 1.
       This prevents locking onto Beat 2 (snare = +1 beat offset) or offbeat hi-hats (+1.5 beats).
    4. Projects the downbeat phase back to the beginning of the track [0.0, bar_sec).
    """
    if bpm <= 0 or len(y) == 0:
        return 0.0

    beat_sec = 60.0 / bpm
    bar_sec = 4.0 * beat_sec
    hop_length = 512

    # Check earliest audible sound in first 1.5 seconds
    init_samples = int(min(1.5 * sr, len(y)))
    y_init = y[:init_samples]
    peak_val = float(np.max(np.abs(y_init))) if len(y_init) > 0 else 0.0
    thresh = 0.02 * peak_val if peak_val > 0 else 0.001
    audible_indices = np.where(np.abs(y_init) > thresh)[0]
    first_audible_time = float(audible_indices[0]) / sr if len(audible_indices) > 0 else 0.0

    # If the track starts immediately with audio (standard for DJ tracks, MP3 delay < 0.03s), snap to 0.000s
    if first_audible_time < 0.03:
        return 0.0

    # If the track has an intro or delayed start, find true kick/snare downbeat phase
    nyq = sr / 2.0
    test_len = int(min(45.0 * sr, len(y)))
    y_chunk = y[:test_len]

    try:
        # Sub-bass kick filter: 35 - 140 Hz
        b_kick, a_kick = scipy.signal.butter(2, [35.0 / nyq, 140.0 / nyq], btype='bandpass')
        y_kick = scipy.signal.filtfilt(b_kick, a_kick, y_chunk)
        kick_env = librosa.onset.onset_strength(y=y_kick, sr=sr, hop_length=hop_length)

        # Snare / Clap filter: 300 - 3000 Hz
        b_snare, a_snare = scipy.signal.butter(2, [300.0 / nyq, 3000.0 / nyq], btype='bandpass')
        y_snare = scipy.signal.filtfilt(b_snare, a_snare, y_chunk)
        snare_env = librosa.onset.onset_strength(y=y_snare, sr=sr, hop_length=hop_length)

        env_times = librosa.frames_to_time(np.arange(len(kick_env)), sr=sr, hop_length=hop_length)

        # Grid search candidates in [0, bar_sec) with 5ms resolution
        candidates = np.arange(0.0, bar_sec, 0.005)
        best_score = -1e9
        best_phase = 0.0
        num_bars = int(min(30.0, len(y_chunk) / sr) // bar_sec)

        for t0 in candidates:
            score = 0.0
            for k in range(num_bars):
                bar_start = t0 + k * bar_sec
                b1 = bar_start
                b2 = bar_start + beat_sec
                b3 = bar_start + 2.0 * beat_sec
                b4 = bar_start + 3.0 * beat_sec

                k1 = np.interp(b1, env_times, kick_env)
                k3 = np.interp(b3, env_times, kick_env)
                s1 = np.interp(b1, env_times, snare_env)
                s2 = np.interp(b2, env_times, snare_env)
                s4 = np.interp(b4, env_times, snare_env)

                # Reward kick on Beat 1 & 3, snare on Beat 2 & 4. Penalize snare on Beat 1!
                score += (2.0 * k1 + 1.0 * k3 + 1.5 * s2 + 1.5 * s4 - 2.0 * s1)

            if score > best_score:
                best_score = score
                best_phase = t0

        origin = best_phase % bar_sec
        while origin >= bar_sec:
            origin -= bar_sec
        while origin < 0:
            origin += bar_sec

        # If origin is within 40ms of the earliest audible onset, snap to it
        if abs(origin - first_audible_time) < 0.04:
            origin = first_audible_time
        if origin < 0.03:
            origin = 0.0

        return round(float(origin), 3)
    except Exception:
        # Fallback to earliest audible time or onset
        onsets = librosa.onset.onset_detect(y=y_init, sr=sr, units='time')
        if len(onsets) > 0 and onsets[0] < 0.1:
            return round(float(onsets[0]), 3)
        return round(first_audible_time, 3)


def analyze_drop_anchored_grid(
    y: np.ndarray,
    sr: int,
    initial_bpm: float,
    min_bpm: float = 60.0,
    max_bpm: float = 180.0
) -> Dict[str, float]:
    """
    Deep Drop-Anchored Beatgrid & BPM Analyzer:
    1. Filters the track into Sub-Bass / Kick band (30 - 150 Hz) and Mid-High Percussion (250 - 4000 Hz).
    2. Detects the First Drop by analyzing the macro-structural jump in sub-bass RMS energy
       and percussive density (comparing a 4-bar post-window against a 4-bar pre-window).
    3. Refines the BPM specifically inside the high-energy post-drop section (16-32 bars after the drop)
       with 0.01 BPM precision, where drums are crystal clear and rock-solid.
    4. Finds the exact downbeat timestamp of the First Drop (`drop_time`) and locks the 4/4 bar phase
       to the drop impact transient + 16-bar post-drop kick/snare pattern.
    5. Back-propagates the beatgrid from `drop_time` back to the start of the track:
       `first_beat_offset = drop_time - N * bar_sec`, ensuring the grid and phrase cues (every 8/16/32 bars)
       hit the First Drop with 100% precision even if the track has an ambient/drumless or off-beat intro.
    """
    duration = len(y) / sr if sr > 0 else 0.0
    if duration < 8.0 or initial_bpm <= 0:
        fb = detect_accurate_first_beat(y, sr, initial_bpm)
        return {"bpm": initial_bpm, "first_beat_offset": fb, "drop_time": fb}

    nyq = sr / 2.0
    hop_length = 256  # Higher time resolution (~11.6ms at 22050Hz) for precise drop transient locking

    # 1. Bandpass filters for Sub-Bass (30-150 Hz) and Snare/Percussion (300-3500 Hz)
    try:
        b_sub, a_sub = scipy.signal.butter(2, [30.0 / nyq, 150.0 / nyq], btype='bandpass')
        y_sub = scipy.signal.filtfilt(b_sub, a_sub, y)

        b_mid, a_mid = scipy.signal.butter(2, [300.0 / nyq, 3500.0 / nyq], btype='bandpass')
        y_mid = scipy.signal.filtfilt(b_mid, a_mid, y)
    except Exception:
        y_sub = y
        y_mid = y

    # Compute RMS energy envelopes and onset envelopes
    rms_sub = librosa.feature.rms(y=y_sub, frame_length=1024, hop_length=hop_length)[0]
    rms_full = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop_length)[0]
    kick_env = librosa.onset.onset_strength(y=y_sub, sr=sr, hop_length=hop_length)
    snare_env = librosa.onset.onset_strength(y=y_mid, sr=sr, hop_length=hop_length)
    env_times = librosa.frames_to_time(np.arange(len(kick_env)), sr=sr, hop_length=hop_length)

    # Normalize envelopes
    rms_sub_norm = rms_sub / (np.percentile(rms_sub, 98) + 1e-6)
    rms_full_norm = rms_full / (np.percentile(rms_full, 98) + 1e-6)
    kick_env_norm = kick_env / (np.percentile(kick_env, 98) + 1e-6)
    snare_env_norm = snare_env / (np.percentile(snare_env, 98) + 1e-6)

    beat_sec_init = 60.0 / initial_bpm
    bar_sec_init = 4.0 * beat_sec_init
    frames_per_bar = max(4, int(round(bar_sec_init * sr / hop_length)))

    # 2. Macro-structural First Drop Detection
    # Search window: typically between 4 bars (or 10% of track) up to 65% of track duration
    min_drop_sec = min(max(bar_sec_init * 2.0, 6.0), duration * 0.25)
    max_drop_sec = max(min_drop_sec + bar_sec_init * 4.0, min(duration * 0.70, 150.0))

    min_frame = int(min_drop_sec * sr / hop_length)
    max_frame = min(len(rms_sub_norm) - frames_per_bar * 2, int(max_drop_sec * sr / hop_length))

    win_pre = frames_per_bar * 4   # 4 bars before drop (build-up / riser / silence)
    win_post = frames_per_bar * 8  # 8 bars after drop (full bass & drums)

    drop_frame = 0
    best_drop_novelty = -1.0

    # Global high-bass threshold: a real drop has sustained sub-bass energy near the track's top levels
    high_sub_thresh = 0.52 * np.percentile(rms_sub_norm, 95)

    if max_frame > min_frame + 4:
        novelty_curve = np.zeros(len(rms_sub_norm), dtype=np.float32)
        for f in range(min_frame, max_frame):
            p_start = max(0, f - win_pre)
            n_end = min(len(rms_sub_norm), f + win_post)

            pre_sub = float(np.mean(rms_sub_norm[p_start:f])) if f > p_start else 0.0
            post_sub = float(np.mean(rms_sub_norm[f:n_end])) if n_end > f else 0.0
            post_full = float(np.mean(rms_full_norm[f:n_end])) if n_end > f else 0.0
            post_kick = float(np.mean(kick_env_norm[f:n_end])) if n_end > f else 0.0

            # Contrast jump from pre-drop to post-drop + sustained heavy bass energy
            sub_jump = max(0.0, post_sub - 0.75 * pre_sub)
            novelty_curve[f] = (sub_jump * 1.6 + post_sub * 0.8 + post_full * 0.4 + post_kick * 0.5)

        # Find major peaks in drop novelty curve separated by at least 4 bars
        peaks, _ = scipy.signal.find_peaks(
            novelty_curve[min_frame:max_frame],
            distance=frames_per_bar * 4,
            prominence=0.12 * np.max(novelty_curve[min_frame:max_frame] + 1e-6)
        )

        # Pick the FIRST prominent peak that reaches sustained drop bass energy (First Drop!)
        max_nov = float(np.max(novelty_curve[min_frame:max_frame])) if max_frame > min_frame else 0.0
        selected_peak = None
        for p in peaks:
            f_idx = min_frame + p
            n_end = min(len(rms_sub_norm), f_idx + win_post)
            post_sub = float(np.mean(rms_sub_norm[f_idx:n_end]))
            if post_sub >= high_sub_thresh and novelty_curve[f_idx] >= 0.62 * max_nov:
                selected_peak = f_idx
                break

        if selected_peak is not None:
            drop_frame = selected_peak
        else:
            drop_frame = int(min_frame + np.argmax(novelty_curve[min_frame:max_frame]))

    coarse_drop_time = float(env_times[drop_frame]) if drop_frame < len(env_times) else 0.0

    # If the track starts right away with full bass from 0.0s and has no stronger drop contrast later
    init_bars_end = min(len(rms_sub_norm), frames_per_bar * 4)
    init_sub_energy = float(np.mean(rms_sub_norm[:init_bars_end])) if init_bars_end > 0 else 0.0
    drop_sub_energy = float(np.mean(rms_sub_norm[drop_frame:min(len(rms_sub_norm), drop_frame + win_post)]))
    if init_sub_energy > 0.85 * drop_sub_energy and coarse_drop_time < bar_sec_init * 4:
        coarse_drop_time = 0.0

    # 3. High-Precision BPM Refinement inside the Drop section
    # Extract 32 bars starting from coarse_drop_time (where the groove is strongest)
    drop_sample_start = int(max(0.0, coarse_drop_time) * sr)
    drop_sample_end = int(min(len(y), drop_sample_start + int(max(45.0, bar_sec_init * 32) * sr)))
    if drop_sample_end - drop_sample_start < int(12.0 * sr):
        drop_sample_start = 0
        drop_sample_end = len(y)

    y_drop_section = y[drop_sample_start:drop_sample_end]
    kick_drop_env = kick_env_norm[drop_frame:min(len(kick_env_norm), int(drop_sample_end / hop_length))]
    snare_drop_env = snare_env_norm[drop_frame:min(len(snare_env_norm), int(drop_sample_end / hop_length))]
    comb_drop_env = 0.65 * kick_drop_env + 0.35 * snare_drop_env

    refined_bpm = float(initial_bpm)
    if len(comb_drop_env) > frames_per_bar * 4:
        frame_rate = sr / hop_length
        # Search around initial_bpm (±1.5 BPM with 0.02 BPM precision, plus exact integer BPMs)
        bpm_candidates = np.unique(np.concatenate([
            np.linspace(initial_bpm - 1.5, initial_bpm + 1.5, 151),
            np.array([round(initial_bpm - 1), round(initial_bpm), round(initial_bpm + 1)], dtype=float)
        ]))
        bpm_candidates = bpm_candidates[(bpm_candidates >= min_bpm) & (bpm_candidates <= max_bpm)]

        ac_drop = np.correlate(comb_drop_env - np.mean(comb_drop_env), comb_drop_env - np.mean(comb_drop_env), mode='full')
        ac_drop = ac_drop[len(comb_drop_env) - 1:]
        ac_drop = ac_drop / (ac_drop[0] + 1e-6)

        best_bpm_score = -1e9
        for cand_bpm in bpm_candidates:
            beat_lag = frame_rate * 60.0 / cand_bpm
            comb_sum = 0.0
            # Evaluate correlation at 1, 2, 4, 8, 16 beats (up to 4 bars)
            for mult, weight in [(1, 1.0), (2, 0.8), (4, 1.2), (8, 1.0), (16, 0.9)]:
                idx_float = beat_lag * mult
                if idx_float < len(ac_drop) - 1:
                    i0 = int(idx_float)
                    frac = idx_float - i0
                    val = (1.0 - frac) * ac_drop[i0] + frac * ac_drop[i0 + 1]
                    comb_sum += weight * val

            # Slight preference for clean integer or 0.5 BPMs (99% of modern DJ tracks)
            is_clean_int = abs(cand_bpm - round(cand_bpm)) < 0.015
            int_bonus = 1.04 if is_clean_int else 1.0

            score = comb_sum * int_bonus
            if score > best_bpm_score:
                best_bpm_score = score
                refined_bpm = float(round(cand_bpm, 2))

        # Snap to integer if within 0.08 BPM
        if abs(refined_bpm - round(refined_bpm)) <= 0.08:
            refined_bpm = float(round(refined_bpm))

    beat_sec = 60.0 / refined_bpm
    bar_sec = 4.0 * beat_sec

    # 4. Lock Exact Downbeat of the First Drop (`drop_time`)
    # Search in window [coarse_drop_time - 1.5*bar_sec, coarse_drop_time + 1.5*bar_sec]
    search_start = max(0.0, coarse_drop_time - 1.25 * bar_sec)
    search_end = min(duration - bar_sec, coarse_drop_time + 1.25 * bar_sec)

    if search_end <= search_start:
        search_start = 0.0
        search_end = min(duration, bar_sec * 2.0)

    # First, find the bar phase [0, bar_sec) inside the post-drop section that best aligns with
    # Kick on Beat 1 & 3 and Snare on Beat 2 & 4 over 16 bars after the drop
    phase_candidates = np.arange(0.0, bar_sec, 0.004)  # 4ms resolution
    best_phase_score = -1e9
    best_bar_phase = 0.0
    num_eval_bars = int(min(16, max(4, (duration - coarse_drop_time) // bar_sec)))

    for phi in phase_candidates:
        # Anchor candidate bar start near coarse_drop_time
        base_bar_t = coarse_drop_time - (coarse_drop_time % bar_sec) + phi
        if base_bar_t < coarse_drop_time - 0.5 * bar_sec:
            base_bar_t += bar_sec

        score = 0.0
        for k in range(num_eval_bars):
            b_start = base_bar_t + k * bar_sec
            b1 = b_start
            b2 = b_start + beat_sec
            b3 = b_start + 2.0 * beat_sec
            b4 = b_start + 3.0 * beat_sec

            k1 = np.interp(b1, env_times, kick_env_norm)
            k3 = np.interp(b3, env_times, kick_env_norm)
            s1 = np.interp(b1, env_times, snare_env_norm)
            s2 = np.interp(b2, env_times, snare_env_norm)
            s4 = np.interp(b4, env_times, snare_env_norm)

            # Weight the first 4 bars of the drop extra heavily
            bar_w = 1.5 if k < 4 else 1.0
            score += bar_w * (2.4 * k1 + 1.0 * k3 + 1.6 * s2 + 1.6 * s4 - 2.2 * s1)

        if score > best_phase_score:
            best_phase_score = score
            best_bar_phase = phi

    # Snap exact drop timestamp to the bar downbeat closest to the drop impact transient
    best_drop_time = best_bar_phase
    min_k = int(math.floor((search_start - best_bar_phase) / bar_sec))
    max_k = int(math.ceil((search_end - best_bar_phase) / bar_sec))

    best_transient_score = -1e9
    for k in range(min_k, max_k + 1):
        cand_drop_t = best_bar_phase + k * bar_sec
        if cand_drop_t < 0.0 or cand_drop_t >= duration - beat_sec:
            continue

        # Check kick transient right on cand_drop_t and sustained sub-bass immediately after vs before
        k_hit = float(np.interp(cand_drop_t, env_times, kick_env_norm))
        f_idx = int(round(cand_drop_t * sr / hop_length))
        pre_f = max(0, f_idx - frames_per_bar * 2)
        post_f = min(len(rms_sub_norm), f_idx + frames_per_bar * 4)

        sub_before = float(np.mean(rms_sub_norm[pre_f:f_idx])) if f_idx > pre_f else 0.0
        sub_after = float(np.mean(rms_sub_norm[f_idx:post_f])) if post_f > f_idx else 0.0
        prox_weight = np.exp(-0.5 * ((cand_drop_t - coarse_drop_time) / (bar_sec * 1.5)) ** 2)

        t_score = (k_hit * 1.5 + max(0.0, sub_after - 0.7 * sub_before) * 2.5 + sub_after) * prox_weight
        if t_score > best_transient_score:
            best_transient_score = t_score
            best_drop_time = cand_drop_t

    # 5. Back-propagate the Beatgrid from `best_drop_time` to the beginning of the track
    # Prefer phrasing multiples (16, 8, or 4 bars before the drop) if they align near the track's start
    first_beat_offset = best_drop_time % bar_sec
    while first_beat_offset >= bar_sec:
        first_beat_offset -= bar_sec
    while first_beat_offset < 0.0:
        first_beat_offset += bar_sec

    # Check earliest audible sound in the first 1.5s
    init_samples = int(min(1.5 * sr, len(y)))
    y_init = y[:init_samples]
    peak_val = float(np.max(np.abs(y_init))) if len(y_init) > 0 else 0.0
    thresh = 0.02 * peak_val if peak_val > 0 else 0.001
    audible_indices = np.where(np.abs(y_init) > thresh)[0]
    first_audible_time = float(audible_indices[0]) / sr if len(audible_indices) > 0 else 0.0

    # If the back-propagated grid lands within 45ms of 0.0s or `first_audible_time`, snap cleanly
    if first_beat_offset < 0.045 or (bar_sec - first_beat_offset) < 0.045:
        first_beat_offset = 0.0
    elif abs(first_beat_offset - first_audible_time) < 0.045:
        first_beat_offset = first_audible_time

    return {
        "bpm": round(float(refined_bpm), 2),
        "first_beat_offset": round(float(first_beat_offset), 3),
        "drop_time": round(float(best_drop_time), 3)
    }


def analyze_audio_track(
    file_path: str,
    min_bpm: float = 60.0,
    max_bpm: float = 180.0,
    drop_anchor_mode: bool = False
) -> Dict[str, Any]:
    """
    Complete analysis of a single audio file:
    - Metadata extraction
    - Waveform peak generation for visual preview
    - Accurate BPM estimation
    - First beat / downbeat offset detection (standard or Deep Drop-Anchored mode)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    # Extract metadata tags
    meta = extract_metadata(file_path)

    # Load audio using librosa (mono, sr=22050 is fast and optimal for tempo/beat)
    y, sr = librosa.load(file_path, sr=22050)

    # Generate waveform peaks (800 points for canvas rendering)
    peaks = generate_waveform_peaks(y, num_peaks=800)

    # If duration wasn't found from metadata, calculate from audio
    if meta["duration"] <= 0.0:
        meta["duration"] = len(y) / sr

    # High-precision multi-band & Fourier/Comb BPM detection
    bpm = estimate_accurate_bpm(
        y=y,
        sr=sr,
        min_bpm=min_bpm,
        max_bpm=max_bpm,
        bpm_tag=meta.get("bpm_tag")
    )

    drop_time = None
    if drop_anchor_mode:
        # Deep Drop-Anchored analysis: detects first drop, refines BPM & locks grid to the drop
        drop_res = analyze_drop_anchored_grid(
            y=y,
            sr=sr,
            initial_bpm=bpm,
            min_bpm=min_bpm,
            max_bpm=max_bpm
        )
        bpm = drop_res["bpm"]
        first_beat_time = drop_res["first_beat_offset"]
        drop_time = drop_res["drop_time"]
    else:
        # Standard fast first downbeat detection (Bar 1, Beat 1)
        first_beat_time = detect_accurate_first_beat(y=y, sr=sr, bpm=bpm)

    return {
        "file_path": os.path.abspath(file_path),
        "file_name": os.path.basename(file_path),
        "title": meta["title"],
        "artist": meta["artist"],
        "album": meta["album"],
        "duration": round(meta["duration"], 2),
        "bitrate": meta["bitrate"],
        "samplerate": meta["samplerate"],
        "size": meta["size"],
        "kind": meta["kind"],
        "bpm": bpm,
        "first_beat_offset": first_beat_time,
        "drop_time": drop_time,
        "drop_anchor_mode": drop_anchor_mode,
        "peaks": peaks
    }


def calculate_cue_points(
    duration: float,
    bpm: float,
    first_beat_offset: float = 0.0,
    bar_interval: int = 16,
    cue_mode: str = "both",  # "hot_cues", "memory_cues", "both"
    naming_template: str = "{bar} Bars",
    max_hot_cues: int = 8,
    max_memory_cues: int = 8,
    color_scheme: str = "default",
    start_bar: int = 0
) -> List[Dict[str, Any]]:
    """
    Calculates cue points positioned every `bar_interval` bars.
    
    Parameters:
    - duration: Total length of track in seconds
    - bpm: Tempo in Beats Per Minute
    - first_beat_offset: First downbeat timestamp in seconds
    - bar_interval: Step size in musical bars (e.g. 8, 16, 32, 64)
    - cue_mode: "hot_cues", "memory_cues", or "both"
    - naming_template: Format string with {bar}, {bar_num}, {cue_letter}, {time}
    - max_hot_cues: Maximum number of Hot Cues to assign (usually 8 for Pioneer A-H, 0 for unlimited)
    - max_memory_cues: Maximum number of Memory Cues to assign (usually 8, 0 for unlimited)
    - color_scheme: "default", "rainbow", "energy", "single"
    - start_bar: Starting bar index (default 0 = start at first beat / Bar 1, Beat 1)
    """
    if bpm <= 0 or duration <= 0 or bar_interval <= 0:
        return []

    # In 4/4 time signature:
    seconds_per_beat = 60.0 / bpm
    seconds_per_bar = 4.0 * seconds_per_beat
    seconds_per_interval = bar_interval * seconds_per_bar

    cue_points = []
    current_bar_index = start_bar
    cue_index = 0

    while True:
        timestamp = first_beat_offset + (current_bar_index * seconds_per_bar)
        
        # Don't place cue beyond the track duration
        if timestamp >= duration - 0.5:
            break

        # Calculate musical bar number (1-based, e.g. Bar 1, Bar 17, Bar 33, ...)
        musical_bar_num = current_bar_index + 1
        
        # Decide types for this point
        is_hot_cue = (cue_mode in ["hot_cues", "both"]) and (max_hot_cues <= 0 or cue_index < max_hot_cues)
        is_memory_cue = (cue_mode in ["memory_cues", "both"]) and (max_memory_cues <= 0 or cue_index < max_memory_cues)

        # Stop if no more cues are allowed for either type (and limits are finite)
        if not is_hot_cue and not is_memory_cue:
            if max_hot_cues > 0 or max_memory_cues > 0:
                break

        # Hot cue letter
        hot_cue_letter = HOT_CUE_LETTERS[cue_index] if (is_hot_cue and cue_index < len(HOT_CUE_LETTERS)) else ""
        hot_cue_num = cue_index if is_hot_cue else -1
        
        # Determine cue name
        minutes = int(timestamp // 60)
        seconds = int(timestamp % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"
        
        if "{bar}" in naming_template or "{bar_num}" in naming_template or "{cue_letter}" in naming_template:
            cue_name = naming_template.format(
                bar=current_bar_index,
                bar_num=musical_bar_num,
                cue_letter=hot_cue_letter,
                time=time_str
            )
        elif naming_template == "structure":
            # Smart structure names
            if cue_index == 0:
                cue_name = "Intro"
            elif cue_index == 1:
                cue_name = f"{bar_interval}b Build"
            elif cue_index == 2:
                cue_name = f"{bar_interval * 2}b Drop"
            elif cue_index == 3:
                cue_name = f"{bar_interval * 3}b Break"
            else:
                cue_name = f"Bar {musical_bar_num}"
        else:
            cue_name = f"{current_bar_index} Bars" if current_bar_index > 0 else "Intro"

        # Color determination
        color = HOT_CUE_COLORS[cue_index % len(HOT_CUE_COLORS)]

        cue_item = {
            "index": cue_index,
            "timestamp": round(timestamp, 3),
            "time_formatted": time_str,
            "bar_index": current_bar_index,
            "bar_number": musical_bar_num,
            "name": cue_name,
            "hot_cue_letter": hot_cue_letter if is_hot_cue else None,
            "hot_cue_num": hot_cue_num,
            "is_hot_cue": is_hot_cue,
            "is_memory_cue": is_memory_cue,
            "color": color
        }
        
        cue_points.append(cue_item)
        
        current_bar_index += bar_interval
        cue_index += 1

    return cue_points
