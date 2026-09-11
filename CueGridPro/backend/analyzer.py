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


def analyze_audio_track(
    file_path: str,
    max_duration: int = 240,
    min_bpm: float = 60.0,
    max_bpm: float = 180.0
) -> Dict[str, Any]:
    """
    Analyzes an audio file to determine:
    1. Metadata (title, artist, duration, samplerate, etc.)
    2. Estimated BPM (tempo) using enhanced multi-band & Fourier analysis
    3. First beat (downbeat) offset in seconds
    4. Waveform peaks for UI visualization
    """
    meta = extract_metadata(file_path)
    
    # Load audio for analysis (22.05kHz mono is optimal for fast beat tracking)
    try:
        # Load up to max_duration seconds for fast BPM tracking
        y, sr = librosa.load(file_path, sr=22050, mono=True, duration=max_duration)
    except Exception as e:
        # Fallback to soundfile if librosa default loader fails
        try:
            y, sr = sf.read(file_path, dtype='float32')
            if y.ndim > 1:
                y = np.mean(y, axis=1)
            if sr != 22050:
                y = librosa.resample(y, orig_sr=sr, target_sr=22050)
                sr = 22050
            if len(y) > max_duration * sr:
                y = y[:max_duration * sr]
        except Exception as e2:
            raise RuntimeError(f"Could not load audio file '{file_path}': {e} | {e2}")

    # Generate waveform preview peaks
    peaks = generate_waveform_peaks(y, num_peaks=600)
    
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

    # Compute onset strength envelope and align beat grid with guided accurate BPM
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    _, beat_frames = librosa.beat.beat_track(
        y=y,
        sr=sr,
        onset_envelope=onset_env,
        bpm=bpm,
        units='time',
        tightness=100
    )

    # Determine first beat (downbeat / grid origin at track start)
    first_beat_time = 0.0
    beat_sec = 60.0 / bpm if bpm > 0 else 0.5
    bar_sec = beat_sec * 4.0

    if len(beat_frames) > 0:
        raw_first_beat = float(beat_frames[0])
        # If the first detected drum beat is after an intro (> 1 beat),
        # project the beatgrid backwards to the start of the track (0.0s)
        if raw_first_beat >= beat_sec:
            # Back-propagate in full 4-beat bars
            projected_origin = raw_first_beat % bar_sec
            # If projected origin is near the boundary of a bar, wrap to 0.0
            if projected_origin > bar_sec - 0.05 or projected_origin < 0.02:
                projected_origin = 0.0
            # Ensure origin is within the first beat interval [0.0, beat_sec)
            while projected_origin >= beat_sec:
                projected_origin -= beat_sec
            first_beat_time = max(0.0, round(projected_origin, 3))
        else:
            first_beat_time = max(0.0, round(raw_first_beat, 3))
    else:
        # Fallback to first onset transient if no beat frames were found
        onsets = librosa.onset.onset_detect(y=y, sr=sr, units='time')
        if len(onsets) > 0:
            raw_onset = float(onsets[0])
            projected_origin = raw_onset % beat_sec if raw_onset >= beat_sec else raw_onset
            first_beat_time = max(0.0, round(projected_origin, 3))

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
    start_bar: int = 1
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
    - start_bar: Starting bar index (default 1 = 1 bar after first beat / start of bar 2)
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
