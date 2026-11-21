import os
import sys
import numpy as np
import soundfile as sf
import xml.etree.ElementTree as ET

PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

try:
    from backend.analyzer import analyze_audio_track, calculate_cue_points, fast_extract_peaks_and_duration
    from backend.rekordbox_xml import build_rekordbox_xml, path_to_rekordbox_url, parse_rekordbox_xml, rekordbox_url_to_path
except ImportError:
    from app.analyzer import analyze_audio_track, calculate_cue_points, fast_extract_peaks_and_duration
    from app.rekordbox_xml import build_rekordbox_xml, path_to_rekordbox_url, parse_rekordbox_xml, rekordbox_url_to_path

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
    assert len(analysis['peaks']) in [600, 800], f"Peaks check failed: {len(analysis['peaks'])}"
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
        max_memory_cues=8,
        start_bar=0
    )
    print(f"Total cues generated for 6-minute track with max 8 hot / 8 memory: {len(cues_limited)}")
    hot_cues_count = sum(1 for c in cues_limited if c.get("is_hot_cue"))
    memory_cues_count = sum(1 for c in cues_limited if c.get("is_memory_cue"))
    print(f" - Hot Cues: {hot_cues_count} (max 8)")
    print(f" - Memory Cues: {memory_cues_count} (max 8)")
    
    assert len(cues_limited) == 8, f"Expected exactly 8 cues, got {len(cues_limited)}"
    assert cues_limited[0]["bar_index"] == 0, f"Expected Cue 0 at Bar 0 (Bar 1, Beat 1), got {cues_limited[0]['bar_index']}"
    assert cues_limited[0]["timestamp"] == 0.0, f"Expected Cue 0 at 0.0s, got {cues_limited[0]['timestamp']}"
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
    assert collection is not None, "COLLECTION missing"
    assert len(collection) == 1, "Expected 1 TRACK"
    
    track_node = collection[0]
    assert track_node.attrib["Name"] == "test_track_128bpm"
    assert track_node.attrib["AverageBpm"] == f"{analysis['bpm']:.2f}"
    
    marks = track_node.findall("POSITION_MARK")
    # 8 hot cues + 8 memory cues = 16 position marks
    assert len(marks) == 16, f"Expected 16 marks, got {len(marks)}"
    print("[XML Export] Validated XML structure with 16 position marks (8 Hot Cues + 8 Memory Cues).")
    
    # Test individual export options
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
    
    print("\n=== 6b. Testing Deep Drop-Anchored Grid Mode (drop_anchor_mode=True) ===")
    # Create a track with a 15.35s drumless/offbeat intro where the First Drop starts at 15.35s (128 BPM)
    # 8 bars at 128 BPM = 15.0s -> back-propagated first beat offset should be ~0.35s!
    drop_test_wav = os.path.join(tempfile.gettempdir(), "test_track_drop_anchor.wav")
    sr = 22050
    total_samples = 45 * sr
    audio_drop = np.zeros(total_samples, dtype=np.float32)
    t = np.linspace(0, 45.0, total_samples)
    # Atmospheric intro pad starting at 0.0s (which would trick a simple threshold detector into snapping to 0.000s)
    audio_drop[:int(15.35 * sr)] += (np.sin(2 * np.pi * 240 * t[:int(15.35 * sr)]) * 0.18)
    
    # Heavy Drop at 15.35s (8 bars + 0.35s offset, 128 BPM -> beat = 0.46875s, bar = 1.875s)
    drop_start_sec = 15.35
    beat_sec = 60.0 / 128.0
    for b in range(60):
        b_time = drop_start_sec + b * beat_sec
        s = int(b_time * sr)
        if s < total_samples:
            # Heavy sub-bass kick on every beat (strongest on Beat 1 of each bar)
            k_len = min(int(0.22 * sr), total_samples - s)
            t_k = np.linspace(0, 0.22, k_len)
            amp = 0.95 if (b % 4 == 0) else 0.75
            audio_drop[s:s + k_len] += amp * np.sin(2 * np.pi * (140 * np.exp(-25 * t_k) + 45) * t_k) * np.exp(-10 * t_k)
            # Snare on Beats 2 and 4
            if b % 4 in [1, 3]:
                sn_len = min(int(0.12 * sr), total_samples - s)
                t_sn = np.linspace(0, 0.12, sn_len)
                audio_drop[s:s + sn_len] += 0.45 * np.sin(2 * np.pi * 900 * t_sn) * np.exp(-20 * t_sn)

    sf.write(drop_test_wav, audio_drop, sr)

    # Analyze with drop_anchor_mode=True
    drop_analysis = analyze_audio_track(drop_test_wav, min_bpm=100.0, max_bpm=160.0, drop_anchor_mode=True)
    print(f"Drop-Anchored BPM: {drop_analysis['bpm']} (Expected: 128.0)")
    print(f"Detected Drop Time: {drop_analysis['drop_time']}s (Expected: ~15.35s)")
    print(f"Back-propagated First Beat Offset: {drop_analysis['first_beat_offset']}s (Expected: ~0.35s)")

    assert 127.5 <= drop_analysis['bpm'] <= 128.5, f"Expected 128 BPM, got {drop_analysis['bpm']}"
    assert drop_analysis['drop_time'] is not None, "drop_time should be populated in drop_anchor_mode"
    assert abs(drop_analysis['drop_time'] - 15.35) < 0.08, f"Expected drop around 15.35s, got {drop_analysis['drop_time']}s"
    assert abs(drop_analysis['first_beat_offset'] - 0.35) < 0.08, f"Expected back-propagated offset ~0.35s, got {drop_analysis['first_beat_offset']}s"

    # Verify that an 8-bar cue point lands squarely on the drop!
    drop_cues = calculate_cue_points(
        duration=drop_analysis['duration'],
        bpm=drop_analysis['bpm'],
        first_beat_offset=drop_analysis['first_beat_offset'],
        bar_interval=8,
        start_bar=0
    )
    cue_8bar = drop_cues[1]  # Bar 8 (second cue)
    print(f"8-Bar Cue Timestamp: {cue_8bar['timestamp']}s (Drop is at 15.35s)")
    assert abs(cue_8bar['timestamp'] - 15.35) < 0.08, f"8-bar cue {cue_8bar['timestamp']}s did not land on drop 15.35s!"

    if os.path.exists(drop_test_wav):
        os.remove(drop_test_wav)

    print("\n=== 6c. Testing Rekordbox XML Pre-Analyzed Beatgrid Import (Cue-Only Workflow) ===")
    sample_rb_xml = """<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="6.8.0" Company="AlphaTheta"/>
  <COLLECTION Entries="1">
    <TRACK TrackID="101" Name="My Analyzed DJ Track" Artist="DJ Tester" TotalTime="240"
           AverageBpm="174.00" BitRate="320" SampleRate="44100" Kind="MP3 File" Size="9600000"
           Location="file://localhost/D:/Music/DnB/My%20Analyzed%20DJ%20Track.mp3">
      <TEMPO Inizio="0.125" Bpm="174.00" Metro="4/4" Battito="1"/>
    </TRACK>
  </COLLECTION>
</DJ_PLAYLISTS>"""

    imported_tracks = parse_rekordbox_xml(sample_rb_xml, is_file_path=False)
    assert len(imported_tracks) == 1, f"Expected 1 imported track, got {len(imported_tracks)}"
    imp_t = imported_tracks[0]
    print(f"Imported Track: '{imp_t['title']}' | BPM: {imp_t['bpm']} | Inizio: {imp_t['first_beat_offset']}s | Path: {imp_t['file_path']}")
    assert imp_t["bpm"] == 174.0, f"Expected 174.0 BPM, got {imp_t['bpm']}"
    assert imp_t["first_beat_offset"] == 0.125, f"Expected 0.125s Inizio, got {imp_t['first_beat_offset']}"
    assert imp_t["from_rekordbox_xml"] is True

    # Place Hot & Memory Cues every 16 bars directly on the imported Rekordbox Beatgrid
    imp_cues = calculate_cue_points(
        duration=imp_t["duration"],
        bpm=imp_t["bpm"],
        first_beat_offset=imp_t["first_beat_offset"],
        bar_interval=16,
        cue_mode="both",
        max_hot_cues=8,
        max_memory_cues=8,
        start_bar=0
    )
    assert len(imp_cues) == 8
    assert imp_cues[0]["timestamp"] == 0.125, f"Cue 0 must start right on Rekordbox Inizio 0.125s, got {imp_cues[0]['timestamp']}s"
    print(f"Placed {len(imp_cues)} Hot/Memory Cues onto Rekordbox grid (Cue 0 at {imp_cues[0]['timestamp']}s, Cue 1 at {imp_cues[1]['timestamp']}s).")

    if os.path.exists(intro_wav):
        os.remove(intro_wav)
    
    # Cleanup test wav
    if os.path.exists(test_wav):
        os.remove(test_wav)

    # 7. Testing Real User Tracks (if present)
    import glob
    real_tracks = glob.glob(r"D:\музыка\электро\DnB\ыаыуа\*.mp3")
    if real_tracks:
        print(f"\n=== 7. Testing Real User Tracks ({len(real_tracks)} files) ===")
        for r_path in real_tracks[:4]:
            r_res = analyze_audio_track(r_path, min_bpm=140, max_bpm=190)
            r_cues = calculate_cue_points(r_res['duration'], r_res['bpm'], r_res['first_beat_offset'], bar_interval=16, start_bar=0)
            print(f"Real Track: {os.path.basename(r_path)}")
            print(f"  BPM: {r_res['bpm']} | FirstBeat: {r_res['first_beat_offset']}s")
            print(f"  Cue 0: {r_cues[0]['name']} at {r_cues[0]['timestamp']}s (Bar {r_cues[0]['bar_number']})")
            print(f"  Cue 1: {r_cues[1]['name']} at {r_cues[1]['timestamp']}s (Bar {r_cues[1]['bar_number']})")
            assert r_res['first_beat_offset'] < 0.05, f"Expected downbeat < 0.05s, got {r_res['first_beat_offset']}s"
            assert r_cues[0]['bar_index'] == 0, "Cue 0 must be Bar 0"
        print("[Real Tracks] Verified downbeat and Cue 0 alignment for real tracks successfully.")
        
    print("\n[SUCCESS] All unit, BPM range, Memory Cue limits, Intro Beatgrid, and XML tests passed perfectly!")

if __name__ == "__main__":
    run_tests()
