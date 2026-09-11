import os
import urllib.parse
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Any


def path_to_rekordbox_url(local_path: str) -> str:
    r"""
    Converts a local Windows or Unix file path to a Rekordbox-compatible file URI.
    Example: C:\Music\Track 01.mp3 -> file://localhost/C:/Music/Track%2001.mp3
    """
    # Normalize slashes
    clean_path = local_path.replace("\\", "/")
    
    # Ensure leading slash for Windows drives (e.g. C:/ -> /C:/)
    if clean_path and clean_path[1:3] == ":/":
        clean_path = "/" + clean_path
    elif not clean_path.startswith("/"):
        clean_path = "/" + clean_path

    # Quote URL special characters (spaces, hashtags, unicode, etc.) keeping slashes and colons safe
    quoted_path = urllib.parse.quote(clean_path, safe="/:")
    return f"file://localhost{quoted_path}"


def build_rekordbox_xml(
    tracks_data: List[Dict[str, Any]],
    playlist_name: str = "Auto Cues",
    export_beatgrid: bool = True,
    export_bpm: bool = True,
    export_hot_cues: bool = True,
    export_memory_cues: bool = True
) -> str:
    """
    Builds a complete, valid Pioneer Rekordbox XML document from analyzed tracks and cues.
    
    Parameters:
    - tracks_data: List of track dicts with metadata, bpm, first_beat_offset, and cue_points.
    - playlist_name: Name of the generated playlist inside Rekordbox.
    - export_beatgrid: Whether to include <TEMPO> beatgrid elements.
    - export_bpm: Whether to include BPM values in track and tempo metadata.
    - export_hot_cues: Whether to include Hot Cue position marks (Num 0..7).
    - export_memory_cues: Whether to include Memory Cue position marks (Num -1).
    
    Returns:
    - Pretty-printed XML string encoded in UTF-8.
    """
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    
    # Product header
    ET.SubElement(root, "PRODUCT", Name="rekordbox", Version="6.0.0", Company="Pioneer DJ")
    
    # Collection node
    collection = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks_data)))
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for idx, item in enumerate(tracks_data, start=1):
        file_path = item.get("file_path", "")
        file_url = path_to_rekordbox_url(file_path)
        
        duration_sec = int(round(item.get("duration", 0)))
        bpm = item.get("bpm", 128.00)
        first_beat = item.get("first_beat_offset", 0.0)
        
        bpm_attr = f"{bpm:.2f}" if export_bpm else "0.00"
        
        # Track attributes
        track_elem = ET.SubElement(
            collection,
            "TRACK",
            TrackID=str(idx),
            Name=str(item.get("title", os.path.basename(file_path))),
            Artist=str(item.get("artist", "Unknown Artist")),
            Composer="",
            Album=str(item.get("album", "")),
            Grouping="",
            Genre=str(item.get("genre", "")),
            Kind=str(item.get("kind", "MP3 File")),
            Size=str(item.get("size", 0)),
            TotalTime=str(duration_sec),
            DiscNumber="0",
            TrackNumber="0",
            Year="0",
            AverageBpm=bpm_attr,
            DateAdded=today_str,
            BitRate=str(item.get("bitrate", 320)),
            SampleRate=str(item.get("samplerate", 44100)),
            Comments="Auto-cued by Rekordbox Auto Cue Generator",
            PlayCount="0",
            Rating="0",
            Location=file_url,
            Remixer="",
            Tonality="",
            Label="",
            Mix=""
        )
        
        # Tempo / Beatgrid definition (if enabled)
        if export_beatgrid:
            ET.SubElement(
                track_elem,
                "TEMPO",
                Inizio=f"{first_beat:.3f}",
                Bpm=bpm_attr,
                Metro="4/4",
                Battito="1"
            )
        
        # Add Cue Points (if hot cues or memory cues enabled)
        cue_points = item.get("cue_points", [])
        
        for cue in cue_points:
            color = cue.get("color", {"r": 0, "g": 229, "b": 255})
            r_str = str(color.get("r", 0))
            g_str = str(color.get("g", 229))
            b_str = str(color.get("b", 255))
            start_sec = f"{cue.get('timestamp', 0.0):.3f}"
            cue_name = str(cue.get("name", ""))
            
            # Hot Cue position mark (Num = 0..7 for Hot Cues A..H)
            if export_hot_cues and cue.get("is_hot_cue") and cue.get("hot_cue_num", -1) >= 0:
                ET.SubElement(
                    track_elem,
                    "POSITION_MARK",
                    Name=cue_name,
                    Type="0",
                    Start=start_sec,
                    Num=str(cue.get("hot_cue_num")),
                    Red=r_str,
                    Green=g_str,
                    Blue=b_str
                )
                
            # Memory Cue position mark (Num = -1 for Memory Cues)
            if export_memory_cues and cue.get("is_memory_cue"):
                ET.SubElement(
                    track_elem,
                    "POSITION_MARK",
                    Name=cue_name,
                    Type="0",
                    Start=start_sec,
                    Num="-1",
                    Red=r_str,
                    Green=g_str,
                    Blue=b_str
                )

    # Playlists structure
    playlists = ET.SubElement(root, "PLAYLISTS")
    root_node = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT")
    
    # Auto Cues playlist
    playlist_node = ET.SubElement(
        root_node,
        "NODE",
        Name=playlist_name,
        Type="1",
        KeyType="0",
        Entries=str(len(tracks_data))
    )
    
    for idx in range(1, len(tracks_data) + 1):
        ET.SubElement(playlist_node, "TRACK", Key=str(idx))

    # Convert to formatted XML string
    rough_string = ET.tostring(root, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    
    return pretty_xml


def save_rekordbox_xml(tracks_data: List[Dict[str, Any]], output_filepath: str, playlist_name: str = "Auto Cues") -> str:
    """Saves generated Rekordbox XML to target file."""
    xml_content = build_rekordbox_xml(tracks_data, playlist_name=playlist_name)
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(xml_content)
    return os.path.abspath(output_filepath)
