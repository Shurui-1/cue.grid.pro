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


def rekordbox_url_to_path(file_url: str) -> str:
    r"""
    Converts a Rekordbox XML Location URI back into a local OS file path.
    Example: file://localhost/C:/Music/Track%2001.mp3 -> C:\Music\Track 01.mp3
    """
    if not file_url:
        return ""
    raw = file_url.strip()
    if raw.lower().startswith("file://localhost"):
        raw = raw[len("file://localhost"):]
    elif raw.lower().startswith("file://"):
        raw = raw[len("file://"):]

    unquoted = urllib.parse.unquote(raw)
    # Remove leading slash before Windows drive letter (e.g. /C:/Music -> C:/Music)
    if len(unquoted) >= 3 and unquoted[0] == "/" and unquoted[2] == ":":
        unquoted = unquoted[1:]

    return os.path.normpath(unquoted)


def parse_rekordbox_xml(xml_content_or_path: str, is_file_path: bool = True) -> List[Dict[str, Any]]:
    """
    Parses an exported Pioneer Rekordbox XML file (or XML string) and extracts tracks
    with their pre-analyzed Rekordbox Beatgrid (<TEMPO> Inizio, Bpm, Battito) and metadata.
    """
    if is_file_path:
        if not os.path.exists(xml_content_or_path):
            raise FileNotFoundError(f"XML file not found: {xml_content_or_path}")
        tree = ET.parse(xml_content_or_path)
        root = tree.getroot()
    else:
        root = ET.fromstring(xml_content_or_path)

    collection = root.find("COLLECTION")
    if collection is None:
        return []

    parsed_tracks = []
    for track_elem in collection.findall("TRACK"):
        attrib = track_elem.attrib
        loc = attrib.get("Location", "")
        local_path = rekordbox_url_to_path(loc)

        try:
            duration = float(attrib.get("TotalTime", "0") or 0.0)
        except ValueError:
            duration = 0.0

        try:
            avg_bpm = float(attrib.get("AverageBpm", "128.0") or 128.0)
        except ValueError:
            avg_bpm = 128.0

        try:
            bitrate = int(attrib.get("BitRate", "320") or 320)
        except ValueError:
            bitrate = 320

        try:
            samplerate = int(attrib.get("SampleRate", "44100") or 44100)
        except ValueError:
            samplerate = 44100

        try:
            size = int(attrib.get("Size", "0") or 0)
        except ValueError:
            size = 0

        # Extract TEMPO nodes (Rekordbox Beatgrid)
        tempo_nodes = []
        first_beat_offset = 0.0
        grid_bpm = avg_bpm

        tempos = track_elem.findall("TEMPO")
        if tempos:
            for t_idx, t_node in enumerate(tempos):
                t_attr = t_node.attrib
                try:
                    inizio = float(t_attr.get("Inizio", "0.0") or 0.0)
                except ValueError:
                    inizio = 0.0
                try:
                    t_bpm = float(t_attr.get("Bpm", str(avg_bpm)) or avg_bpm)
                except ValueError:
                    t_bpm = avg_bpm
                try:
                    battito = int(t_attr.get("Battito", "1") or 1)
                except ValueError:
                    battito = 1
                metro = t_attr.get("Metro", "4/4")

                tempo_nodes.append({
                    "inizio": inizio,
                    "bpm": t_bpm,
                    "metro": metro,
                    "battito": battito
                })

                if t_idx == 0:
                    if t_bpm > 0:
                        grid_bpm = t_bpm
                    beat_sec = 60.0 / grid_bpm if grid_bpm > 0 else 0.46875
                    bar_sec = 4.0 * beat_sec
                    # Calculate exact Bar 1, Beat 1 downbeat from Inizio and Battito (1..4)
                    if battito in [2, 3, 4]:
                        downbeat_t = inizio - (battito - 1) * beat_sec
                        if downbeat_t < 0:
                            downbeat_t += bar_sec
                        first_beat_offset = round(downbeat_t, 3)
                    else:
                        first_beat_offset = round(inizio, 3)

        file_name = os.path.basename(local_path) if local_path else attrib.get("Name", "Track")
        title = attrib.get("Name") or os.path.splitext(file_name)[0]

        parsed_tracks.append({
            "file_path": local_path,
            "location_url": loc,
            "file_name": file_name,
            "title": title,
            "artist": attrib.get("Artist", "Unknown Artist"),
            "album": attrib.get("Album", ""),
            "genre": attrib.get("Genre", ""),
            "kind": attrib.get("Kind", "MP3 File"),
            "size": size,
            "duration": round(duration, 2),
            "bitrate": bitrate,
            "samplerate": samplerate,
            "bpm": round(grid_bpm, 2),
            "first_beat_offset": first_beat_offset,
            "tempo_nodes": tempo_nodes,
            "from_rekordbox_xml": True
        })

    return parsed_tracks


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
        if file_path:
            file_url = path_to_rekordbox_url(file_path)
        else:
            file_url = item.get("location_url", "")
        
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
            tempo_nodes = item.get("tempo_nodes")
            if tempo_nodes and len(tempo_nodes) > 1:
                for t_idx, tn in enumerate(tempo_nodes):
                    t_inizio = f"{first_beat:.3f}" if t_idx == 0 else f"{float(tn.get('inizio', 0.0)):.3f}"
                    t_bpm = bpm_attr if t_idx == 0 else (f"{float(tn.get('bpm', bpm)):.2f}" if export_bpm else "0.00")
                    ET.SubElement(
                        track_elem,
                        "TEMPO",
                        Inizio=t_inizio,
                        Bpm=t_bpm,
                        Metro=str(tn.get("metro", "4/4")),
                        Battito=str(tn.get("battito", 1))
                    )
            else:
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
