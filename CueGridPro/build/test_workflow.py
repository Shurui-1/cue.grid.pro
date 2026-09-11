import os
import sys
import numpy as np
import soundfile as sf
import xml.etree.ElementTree as ET

PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

try:
    from backend.analyzer import analyze_audio_track, calculate_cue_points
    from backend.rekordbox_xml import build_rekordbox_xml, path_to_rekordbox_url
except ImportError:
    from app.analyzer import analyze_audio_track, calculate_cue_points
    from app.rekordbox_xml import build_rekordbox_xml, path_to_rekordbox_url

import tempfile

def create_synthetic_beat_audio(filename="test_track_128bpm.wav", duration=16.0, bpm=128.0, sr=44100):
    """Generates a synthetic 4/4 electronic beat audio for testing."""
    filepath = os.path.join(tempfile.gettempdir(), filename)
    total_samples = int(duration * sr)
    audio = np.zeros(total_samples, dtype=np.float32)
    
    # 1 beat duration
    beat_interval = 60.0 / bpm
    beat_samples = int(beat_interval * sr)
    
    # Generate kick drums on every beat
    num_beats = int(duration / beat_interval)
    
    for b in range(num_beats):
        start_idx = b * beat_samples
        if start_idx >= total_samples:
            break
            
        # Kick sound (sine sweep)
        kick_len = min(int(0.15 * sr), total_samples - start_idx)
        t = np.linspace(0, 0.15, kick_len)
        freq_env = 150 * np.exp(-30 * t) + 40
        kick = np.sin(2 * np.pi * freq_env * t) * np.exp(-15 * t)
        
        # Make downbeats (bar 1, 5, 9...) slightly louder
        if b % 4 == 0:
            kick *= 1.2
            
        audio[start_idx:start_idx + kick_len] += kick[:kick_len]
        
    # Normalize
    audio = audio / (np.max(np.abs(audio)) + 1e-6)
    sf.write(filepath, audio, sr)
    return os.path.abspath(filepath)


def run_tests():
    print("=== 1. Testing Synthetic Audio Generation ===")
    test_wav = create_synthetic_beat_audio(duration=16.0, bpm=128.0)
    print(f"Created: {test_wav}")
    
    print("\n=== 2. Testing Audio Analyzer with Default BPM Range (60-180) ===")
    analysis = analyze_audio_track(test_wav, min_bpm=60.0, max_bpm=180.0)
    print(f"Detected BPM: {analysis['bpm']} (Expected: ~128.0)")
    print(f"Duration: {analysis['duration']}s")
    print(f"First beat offset: {analysis['first_beat_offset']}s")
    print(f"Waveform peaks count: {len(analysis['peaks'])}")
    
    assert analysis['duration'] > 15.0, "Duration check failed"
    assert len(analysis['peaks']) == 600, "Peaks check failed"
    assert 120.0 <= analysis['bpm'] <= 135.0, f"Expected ~128 BPM, got {analysis['bpm']}"

    print("\n=== 3. Testing BPM Range Enforcement (Halftime / Double-time) ===")
    # Force detection into 60-90 BPM range -> should halve to 64 BPM
    analysis_half = analyze_audio_track(test_wav, min_bpm=50.0, max_bpm=90.0)
    print(f"Detected BPM in 50-90 range: {analysis_half['bpm']} (Expected: ~64.0)")
    assert 55.0 <= analysis_half['bpm'] <= 70.0, f"Expected ~64 BPM, got {analysis_half['bpm']}"

    # Force detection into 170-260 BPM range -> should double to 256 BPM
    analysis_double = analyze_audio_track(test_wav, min_bpm=170.0, max_bpm=260.0)
    print(f"Detected BPM in 170-260 range: {analysis_double['bpm']} (Expected: ~256.0)")
    assert 240.0 <= analysis_double['bpm'] <= 270.0, f"Expected ~256 BPM, got {analysis_double['bpm']}"
    
    print("\n=== 4. Testing Cue Points Calculation with 8 Memory Cue Limit ===")
    # 360s track with 8-bar intervals would normally create ~23 cues
    cues_limited = calculate_cue_points(
        duration=360.0,
        bpm=128.0,
        first_beat_offset=0.0,
        bar_interval=8,
        cue_mode="both",
        naming_template="{bar} Bars",
        max_hot_cues=8,
        max_memory_cues=8
    )
    print(f"Total cues generated for 6-minute track with max 8 hot / 8 memory: {len(cues_limited)}")
    hot_cues_count = sum(1 for c in cues_limited if c.get("is_hot_cue"))
    memory_cues_count = sum(1 for c in cues_limited if c.get("is_memory_cue"))
    print(f" - Hot Cues: {hot_cues_count} (max 8)")
    print(f" - Memory Cues: {memory_cues_count} (max 8)")
    
    assert len(cues_limited) == 8, f"Expected exactly 8 cues, got {len(cues_limited)}"
    assert hot_cues_count == 8, f"Expected 8 hot cues, got {hot_cues_count}"
    assert memory_cues_count == 8, f"Expected 8 memory cues, got {memory_cues_count}"

    print("\n=== 5. Testing Rekordbox XML Generation ===")
    track_item = dict(analysis)
    track_item["cue_points"] = cues_limited
    
    xml_content = build_rekordbox_xml([track_item], playlist_name="Auto Cues")
    
    # Validate XML structure
    root = ET.fromstring(xml_content)
    assert root.tag == "DJ_PLAYLISTS", "Root tag mismatch"
    
    collection = root.find("COLLECTION")
    assert collection is not None, "Collection node missing"
    assert collection.attrib["Entries"] == "1"
    
    track_node = collection.find("TRACK")
    assert track_node is not None, "Track node missing"
    assert track_node.attrib["AverageBpm"] == f"{analysis['bpm']:.2f}"
    
    marks = track_node.findall("POSITION_MARK")
    hot_marks = [m for m in marks if int(m.attrib.get("Num", -1)) >= 0]
    mem_marks = [m for m in marks if int(m.attrib.get("Num", -1)) == -1]
    print(f"Generated {len(marks)} total POSITION_MARK entries in XML ({len(hot_marks)} Hot Cues, {len(mem_marks)} Memory Cues).")
    
    assert len(hot_marks) == 8, f"Expected 8 Hot Cue POSITION_MARKs in XML, got {len(hot_marks)}"
    assert len(mem_marks) == 8, f"Expected 8 Memory Cue POSITION_MARKs in XML, got {len(mem_marks)}"
    
    # Test partial export options
    # A) Only Hot Cues without Beatgrid
    xml_hot_only = build_rekordbox_xml(
        [track_item],
        playlist_name="Hot Cues Only",
        export_beatgrid=False,
        export_bpm=False,
        export_hot_cues=True,
        export_memory_cues=False
    )
    root_hot = ET.fromstring(xml_hot_hot := xml_hot_only)
    tr_hot = root_hot.find("COLLECTION/TRACK")
    assert tr_hot.attrib["AverageBpm"] == "0.00", "BPM should be 0.00 when export_bpm=False"
    assert tr_hot.find("TEMPO") is None, "TEMPO beatgrid should be omitted when export_beatgrid=False"
    marks_hot = tr_hot.findall("POSITION_MARK")
    assert len(marks_hot) == 8, f"Expected 8 hot cues, got {len(marks_hot)}"
    assert all(int(m.attrib["Num"]) >= 0 for m in marks_hot), "All marks should be Hot Cues (Num >= 0)"
    
    # B) Only Memory Cues with Beatgrid
    xml_mem_only = build_rekordbox_xml(
        [track_item],
        playlist_name="Mem Cues Only",
        export_beatgrid=True,
        export_bpm=True,
        export_hot_cues=False,
        export_memory_cues=True
    )
    root_mem = ET.fromstring(xml_mem_only)
    tr_mem = root_mem.find("COLLECTION/TRACK")
    assert tr_mem.attrib["AverageBpm"] == f"{analysis['bpm']:.2f}"
    assert tr_mem.find("TEMPO") is not None, "TEMPO beatgrid should be present"
    marks_mem = tr_mem.findall("POSITION_MARK")
    assert len(marks_mem) == 8, f"Expected 8 memory cues, got {len(marks_mem)}"
    assert all(int(m.attrib["Num"]) == -1 for m in marks_mem), "All marks should be Memory Cues (Num == -1)"
    print("[XML Export Options] Tested customizable export flags (Beatgrid, BPM, Hot Cues, Memory Cues) successfully.")
    
    print("\n=== 6. Testing Drumless Intro Beatgrid Back-Propagation ===")
    intro_wav = os.path.join(tempfile.gettempdir(), "test_track_ambient_intro.wav")
    sr = 22050
    # 15 seconds ambient pad followed by 15 seconds 128 BPM drums
    total_samples = 30 * sr
    audio_intro = np.zeros(total_samples, dtype=np.float32)
    t = np.linspace(0, 30.0, total_samples)
    audio_intro += (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 330 * t)) * 0.15
    # Drums start at 15.0s (128 BPM -> 0.46875s beat interval)
    beat_samples = int(0.46875 * sr)
    for b in range(32):
        s = int((15.0 + b * 0.46875) * sr)
        if s < total_samples:
            k_len = min(int(0.2 * sr), total_samples - s)
            t_k = np.linspace(0, 0.2, k_len)
            audio_intro[s:s + k_len] += np.sin(2 * np.pi * (150 * np.exp(-30 * t_k) + 50) * t_k) * np.exp(-15 * t_k)
    sf.write(intro_wav, audio_intro, sr)
    
    intro_analysis = analyze_audio_track(intro_wav)
    print(f"Intro track BPM: {intro_analysis['bpm']} (Expected: ~128.0)")
    print(f"Intro track first_beat_offset: {intro_analysis['first_beat_offset']:.3f}s (Expected: near 0.0s, NOT at 15.0s)")
    
    assert intro_analysis['first_beat_offset'] < 0.5, f"Expected first beat near track start, got {intro_analysis['first_beat_offset']}s"
    assert 127.0 <= intro_analysis['bpm'] <= 129.0, f"Expected ~128 BPM, got {intro_analysis['bpm']}"
    
    if os.path.exists(intro_wav):
        os.remove(intro_wav)
    
    # Cleanup test wav
    if os.path.exists(test_wav):
        os.remove(test_wav)
        
    print("\n[SUCCESS] All unit, BPM range, Memory Cue limits, Intro Beatgrid, and XML tests passed perfectly!")

if __name__ == "__main__":
    run_tests()
