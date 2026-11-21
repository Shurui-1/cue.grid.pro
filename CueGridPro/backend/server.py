import os
import sys
import tempfile
import shutil
import asyncio
import subprocess
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from .analyzer import analyze_audio_track, calculate_cue_points, fast_extract_peaks_and_duration
    from .rekordbox_xml import build_rekordbox_xml, save_rekordbox_xml, parse_rekordbox_xml
except (ImportError, ModuleNotFoundError, ValueError):
    try:
        from backend.analyzer import analyze_audio_track, calculate_cue_points, fast_extract_peaks_and_duration
        from backend.rekordbox_xml import build_rekordbox_xml, save_rekordbox_xml, parse_rekordbox_xml
    except (ImportError, ModuleNotFoundError, ValueError):
        from analyzer import analyze_audio_track, calculate_cue_points, fast_extract_peaks_and_duration
        from rekordbox_xml import build_rekordbox_xml, save_rekordbox_xml, parse_rekordbox_xml

app = FastAPI(title="Rekordbox Auto Cue Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_bundle_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BUNDLE_DIR = get_bundle_dir()
STATIC_DIR = os.path.join(BUNDLE_DIR, "frontend")
if not os.path.exists(STATIC_DIR):
    STATIC_DIR = os.path.join(BUNDLE_DIR, "app", "static")
if not os.path.exists(STATIC_DIR):
    STATIC_DIR = os.path.join(BUNDLE_DIR, "static")
if not os.path.exists(STATIC_DIR):
    STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

TEMP_DIR = os.path.join(tempfile.gettempdir(), "rekordbox_auto_cues")
os.makedirs(TEMP_DIR, exist_ok=True)


class RecalculateRequest(BaseModel):
    duration: float
    bpm: float
    first_beat_offset: float = 0.0
    bar_interval: int = 16
    cue_mode: str = "both"
    naming_template: str = "{bar} Bars"
    max_hot_cues: int = 8
    max_memory_cues: int = 8
    color_scheme: str = "default"
    start_bar: int = 0


class PathAnalysisRequest(BaseModel):
    file_paths: List[str]
    bar_interval: int = 16
    cue_mode: str = "both"
    naming_template: str = "{bar} Bars"
    max_hot_cues: int = 8
    max_memory_cues: int = 8
    min_bpm: float = 60.0
    max_bpm: float = 180.0
    start_bar: int = 0
    drop_anchor_mode: bool = False


class ExportXmlRequest(BaseModel):
    tracks: List[dict]
    playlist_name: str = "Auto Cues"
    save_to_path: Optional[str] = None
    export_beatgrid: bool = True
    export_bpm: bool = True
    export_hot_cues: bool = True
    export_memory_cues: bool = True


class ImportXmlPathRequest(BaseModel):
    xml_path: str
    bar_interval: int = 16
    cue_mode: str = "both"
    naming_template: str = "{bar} Bars"
    max_hot_cues: int = 8
    max_memory_cues: int = 8
    start_bar: int = 0


def _process_imported_xml_tracks(
    parsed_tracks: List[dict],
    bar_interval: int = 16,
    cue_mode: str = "both",
    naming_template: str = "{bar} Bars",
    max_hot_cues: int = 8,
    max_memory_cues: int = 8,
    start_bar: int = 0
) -> List[dict]:
    """
    Takes tracks parsed from Rekordbox XML (with pre-analyzed BPM and Beatgrid),
    fast-loads waveform peaks if local audio exists, and places Hot Cues & Memory Cues.
    """
    results = []
    for item in parsed_tracks:
        wave_info = fast_extract_peaks_and_duration(
            file_path=item.get("file_path", ""),
            fallback_duration=item.get("duration", 0.0),
            bpm=item.get("bpm", 128.0),
            first_beat_offset=item.get("first_beat_offset", 0.0),
            num_peaks=800
        )
        duration = wave_info["duration"] if wave_info["duration"] > 0 else item.get("duration", 180.0)
        item["duration"] = duration
        item["peaks"] = wave_info["peaks"]
        item["audio_available"] = wave_info["audio_available"]

        cues = calculate_cue_points(
            duration=duration,
            bpm=item["bpm"],
            first_beat_offset=item["first_beat_offset"],
            bar_interval=bar_interval,
            cue_mode=cue_mode,
            naming_template=naming_template,
            max_hot_cues=max_hot_cues,
            max_memory_cues=max_memory_cues,
            start_bar=start_bar
        )
        item["cue_points"] = cues
        results.append(item)
    return results


def _analyze_single_track(
    file_path: str,
    min_bpm: float = 60.0,
    max_bpm: float = 180.0,
    bar_interval: int = 16,
    cue_mode: str = "both",
    naming_template: str = "{bar} Bars",
    max_hot_cues: int = 8,
    max_memory_cues: int = 8,
    start_bar: int = 0,
    drop_anchor_mode: bool = False
) -> dict:
    """Synchronous worker function to analyze a single track and calculate its cue points."""
    analysis = analyze_audio_track(
        file_path,
        min_bpm=min_bpm,
        max_bpm=max_bpm,
        drop_anchor_mode=drop_anchor_mode
    )
    cues = calculate_cue_points(
        duration=analysis["duration"],
        bpm=analysis["bpm"],
        first_beat_offset=analysis["first_beat_offset"],
        bar_interval=bar_interval,
        cue_mode=cue_mode,
        naming_template=naming_template,
        max_hot_cues=max_hot_cues,
        max_memory_cues=max_memory_cues,
        start_bar=start_bar
    )
    analysis["cue_points"] = cues
    return analysis


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Rekordbox Auto Cue Generator is running</h1>"


@app.post("/api/analyze-path")
async def analyze_paths_endpoint(req: PathAnalysisRequest):
    """Analyzes a list of local file paths without uploading, running non-blocking in a thread pool."""
    results = []
    errors = []
    
    for path in req.file_paths:
        if not os.path.exists(path):
            errors.append(f"Файл не найден: {path}")
            continue
            
        try:
            # Offload heavy CPU audio analysis to thread pool so event loop stays responsive
            analysis = await asyncio.to_thread(
                _analyze_single_track,
                path,
                req.min_bpm,
                req.max_bpm,
                req.bar_interval,
                req.cue_mode,
                req.naming_template,
                req.max_hot_cues,
                req.max_memory_cues,
                req.start_bar,
                req.drop_anchor_mode
            )
            results.append(analysis)
        except Exception as e:
            errors.append(f"Ошибка при анализе '{os.path.basename(path)}': {str(e)}")
            
    return {"tracks": results, "errors": errors}


@app.post("/api/analyze-upload")
async def analyze_upload_endpoint(
    files: List[UploadFile] = File(...),
    bar_interval: int = Form(16),
    cue_mode: str = Form("both"),
    naming_template: str = Form("{bar} Bars"),
    max_hot_cues: int = Form(8),
    max_memory_cues: int = Form(8),
    min_bpm: float = Form(60.0),
    max_bpm: float = Form(180.0),
    start_bar: int = Form(0),
    drop_anchor_mode: bool = Form(False)
):
    """Handles browser file uploads, stores stream in temp folder, and analyzes non-blocking."""
    results = []
    errors = []
    
    for file in files:
        safe_filename = file.filename or "uploaded_audio.mp3"
        temp_ext = os.path.splitext(safe_filename)[1]
        if not temp_ext:
            temp_ext = ".mp3"
            
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=temp_ext, dir=TEMP_DIR)
        temp_path = temp_file.name
        
        try:
            # Stream directly to disk to prevent huge RAM spikes
            shutil.copyfileobj(file.file, temp_file)
            temp_file.close()
            
            # Run heavy CPU-bound Librosa analysis in worker thread
            analysis = await asyncio.to_thread(
                _analyze_single_track,
                temp_path,
                min_bpm,
                max_bpm,
                bar_interval,
                cue_mode,
                naming_template,
                max_hot_cues,
                max_memory_cues,
                start_bar,
                drop_anchor_mode
            )
            
            analysis["file_name"] = safe_filename
            # Restore original track title if extracted title is missing or equals temp filename
            temp_basename = os.path.splitext(os.path.basename(temp_path))[0]
            if not analysis.get("title") or analysis.get("title") == temp_basename:
                analysis["title"] = os.path.splitext(safe_filename)[0]
                
            results.append(analysis)
        except Exception as e:
            errors.append(f"Ошибка при обработке '{safe_filename}': {str(e)}")
        finally:
            try:
                temp_file.close()
            except Exception:
                pass
            
    return {"tracks": results, "errors": errors}


@app.post("/api/recalculate-cues")
async def recalculate_cues_endpoint(req: RecalculateRequest):
    """Fast recalculation of cue points when settings change."""
    cues = calculate_cue_points(
        duration=req.duration,
        bpm=req.bpm,
        first_beat_offset=req.first_beat_offset,
        bar_interval=req.bar_interval,
        cue_mode=req.cue_mode,
        naming_template=req.naming_template,
        max_hot_cues=req.max_hot_cues,
        max_memory_cues=req.max_memory_cues,
        start_bar=req.start_bar
    )
    return {"cue_points": cues}


class ReanalyzeSingleRequest(BaseModel):
    file_path: str
    bar_interval: int = 16
    cue_mode: str = "both"
    naming_template: str = "{bar} Bars"
    max_hot_cues: int = 8
    max_memory_cues: int = 8
    min_bpm: float = 60.0
    max_bpm: float = 180.0
    start_bar: int = 0
    drop_anchor_mode: bool = False


@app.post("/api/reanalyze-track")
async def reanalyze_track_endpoint(req: ReanalyzeSingleRequest):
    """Re-runs full audio analysis (standard or Deep Drop-Anchored mode) on an already loaded track."""
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail=f"Файл трека не найден: {req.file_path}")
    try:
        analysis = await asyncio.to_thread(
            _analyze_single_track,
            req.file_path,
            req.min_bpm,
            req.max_bpm,
            req.bar_interval,
            req.cue_mode,
            req.naming_template,
            req.max_hot_cues,
            req.max_memory_cues,
            req.start_bar,
            req.drop_anchor_mode
        )
        return {"track": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка переанализа: {str(e)}")


@app.post("/api/import-xml-path")
async def import_xml_path_endpoint(req: ImportXmlPathRequest):
    """Imports pre-analyzed Beatgrid and BPM from a local Rekordbox XML file and calculates cues."""
    if not os.path.exists(req.xml_path):
        raise HTTPException(status_code=404, detail=f"XML файл не найден: {req.xml_path}")
    try:
        parsed = await asyncio.to_thread(parse_rekordbox_xml, req.xml_path, True)
        if not parsed:
            return {"tracks": [], "errors": ["В выбранном XML-файле не найдено треков в <COLLECTION>."]}
        tracks = await asyncio.to_thread(
            _process_imported_xml_tracks,
            parsed,
            req.bar_interval,
            req.cue_mode,
            req.naming_template,
            req.max_hot_cues,
            req.max_memory_cues,
            req.start_bar
        )
        return {"tracks": tracks, "errors": []}
    except Exception as e:
        return {"tracks": [], "errors": [f"Ошибка чтения Rekordbox XML: {str(e)}"]}


@app.post("/api/import-xml-upload")
async def import_xml_upload_endpoint(
    file: UploadFile = File(...),
    bar_interval: int = Form(16),
    cue_mode: str = Form("both"),
    naming_template: str = Form("{bar} Bars"),
    max_hot_cues: int = Form(8),
    max_memory_cues: int = Form(8),
    start_bar: int = Form(0)
):
    """Imports pre-analyzed Beatgrid and BPM from an uploaded Rekordbox XML file and calculates cues."""
    try:
        raw_bytes = await file.read()
        xml_str = raw_bytes.decode("utf-8", errors="replace")
        parsed = await asyncio.to_thread(parse_rekordbox_xml, xml_str, False)
        if not parsed:
            return {"tracks": [], "errors": ["В загруженном XML-файле не найдено треков в <COLLECTION>."]}
        tracks = await asyncio.to_thread(
            _process_imported_xml_tracks,
            parsed,
            bar_interval,
            cue_mode,
            naming_template,
            max_hot_cues,
            max_memory_cues,
            start_bar
        )
        return {"tracks": tracks, "errors": []}
    except Exception as e:
        return {"tracks": [], "errors": [f"Ошибка импорта Rekordbox XML: {str(e)}"]}


@app.post("/api/export-xml")
async def export_xml_endpoint(req: ExportXmlRequest):
    """Generates Pioneer Rekordbox XML."""
    if not req.tracks:
        raise HTTPException(status_code=400, detail="No tracks provided for XML export")
        
    xml_content = build_rekordbox_xml(
        req.tracks,
        playlist_name=req.playlist_name,
        export_beatgrid=req.export_beatgrid,
        export_bpm=req.export_bpm,
        export_hot_cues=req.export_hot_cues,
        export_memory_cues=req.export_memory_cues
    )
    
    if req.save_to_path:
        try:
            with open(req.save_to_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
            return {"status": "saved", "path": req.save_to_path}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save XML to path: {e}")
            
    # Return as downloadable file
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=rekordbox_auto_cues.xml"
        }
    )


@app.get("/api/audio-stream")
async def audio_stream_endpoint(path: str = Query(...)):
    """Streams local audio file for in-browser playback."""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio file not found")
        
    ext = os.path.splitext(path)[1].lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".aiff": "audio/aiff",
        ".aif": "audio/aiff"
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media_type)


def _native_pick_files_worker() -> List[str]:
    """Runs native file selection dialog on Windows (Tkinter with PowerShell fallback)."""
    # Try Tkinter first
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.focus_force()
        
        file_paths = filedialog.askopenfilenames(
            title="Выберите аудиофайлы для Rekordbox Auto Cues",
            filetypes=[
                ("Аудиофайлы", "*.mp3 *.wav *.flac *.aiff *.aif *.m4a *.ogg"),
                ("Все файлы", "*.*")
            ]
        )
        root.destroy()
        if file_paths:
            return list(file_paths)
        return []
    except Exception as e:
        print(f"[WARN] Tkinter file dialog fallback to PowerShell: {e}")

    # Fallback to PowerShell Windows.Forms OpenFileDialog
    try:
        ps_cmd = (
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
            "$f = New-Object System.Windows.Forms.OpenFileDialog; "
            "$f.Multiselect = $true; "
            "$f.Title = 'Выберите аудиофайлы для Rekordbox Auto Cues'; "
            "$f.Filter = 'Аудиофайлы (*.mp3;*.wav;*.flac;*.aiff;*.aif;*.m4a;*.ogg)|*.mp3;*.wav;*.flac;*.aiff;*.aif;*.m4a;*.ogg|Все файлы (*.*)|*.*'; "
            "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
            "  $f.FileNames | ForEach-Object { Write-Output $_ } "
            "}"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode == 0 and res.stdout.strip():
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip() and os.path.exists(line.strip())]
            return lines
    except Exception as e2:
        print(f"[ERROR] PowerShell file dialog failed: {e2}")

    return []


def _native_pick_folder_worker() -> str:
    """Runs native folder selection dialog on Windows (Tkinter with PowerShell fallback)."""
    # Try Tkinter first
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.focus_force()
        
        folder = filedialog.askdirectory(title="Выберите папку с музыкальными треками")
        root.destroy()
        if folder:
            return folder
        return ""
    except Exception as e:
        print(f"[WARN] Tkinter folder dialog fallback to PowerShell: {e}")

    # Fallback to PowerShell FolderBrowserDialog
    try:
        ps_cmd = (
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$d.Description = 'Выберите папку с музыкальными треками'; "
            "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
            "  Write-Output $d.SelectedPath "
            "}"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode == 0 and res.stdout.strip():
            selected = res.stdout.strip()
            if os.path.exists(selected):
                return selected
    except Exception as e2:
        print(f"[ERROR] PowerShell folder dialog failed: {e2}")

    return ""


@app.post("/api/pick-files")
async def pick_files_dialog():
    """Opens native Windows file dialog in non-blocking thread to select audio tracks."""
    try:
        file_paths = await asyncio.to_thread(_native_pick_files_worker)
        # If user explicitly pressed Cancel or closed dialog, indicate canceled: True
        return {"files": file_paths, "canceled": len(file_paths) == 0}
    except Exception as e:
        return {"files": [], "error": str(e), "canceled": False}


def _native_pick_xml_worker() -> str:
    """Runs native file selection dialog on Windows to select a Rekordbox .xml file."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.focus_force()

        xml_path = filedialog.askopenfilename(
            title="Выберите экспортированный файл Rekordbox XML с готовой сеткой треков",
            filetypes=[
                ("Rekordbox XML", "*.xml"),
                ("Все файлы", "*.*")
            ]
        )
        root.destroy()
        if xml_path:
            return str(xml_path)
        return ""
    except Exception as e:
        print(f"[WARN] Tkinter XML dialog fallback to PowerShell: {e}")

    try:
        ps_cmd = (
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
            "$f = New-Object System.Windows.Forms.OpenFileDialog; "
            "$f.Multiselect = $false; "
            "$f.Title = 'Выберите файл Rekordbox XML с готовой сеткой треков'; "
            "$f.Filter = 'Rekordbox XML (*.xml)|*.xml|Все файлы (*.*)|*.*'; "
            "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
            "  Write-Output $f.FileName "
            "}"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode == 0 and res.stdout.strip():
            selected = res.stdout.strip()
            if os.path.exists(selected):
                return selected
    except Exception as e2:
        print(f"[ERROR] PowerShell XML dialog failed: {e2}")

    return ""


@app.post("/api/pick-xml")
async def pick_xml_dialog():
    """Opens native Windows file dialog to pick a Rekordbox XML file."""
    try:
        xml_path = await asyncio.to_thread(_native_pick_xml_worker)
        return {"xml_path": xml_path, "canceled": len(xml_path) == 0}
    except Exception as e:
        return {"xml_path": "", "error": str(e), "canceled": False}


@app.post("/api/pick-folder")
async def pick_folder_dialog():
    """Opens native Windows folder dialog in non-blocking thread to select audio tracks folder."""
    try:
        folder = await asyncio.to_thread(_native_pick_folder_worker)
        if not folder:
            return {"files": [], "folder": "", "canceled": True}
            
        supported_exts = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}
        found_files = []
        
        for root_dir, _, filenames in os.walk(folder):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in supported_exts:
                    found_files.append(os.path.join(root_dir, filename))
                    
        return {"files": found_files, "folder": folder, "canceled": False}
    except Exception as e:
        return {"files": [], "folder": "", "error": str(e), "canceled": False}


@app.get("/api/heartbeat")
async def heartbeat():
    return {"status": "ok", "app": "CueGridPro"}


@app.post("/api/shutdown")
async def shutdown(confirm: bool = Query(False)):
    """Cleanly exits the application only when explicitly confirmed."""
    if confirm:
        def _delayed_exit():
            import time
            time.sleep(0.5)
            os._exit(0)
        import threading
        threading.Thread(target=_delayed_exit, daemon=True).start()
        return {"status": "shutting down"}
    return {"status": "ignored", "message": "Confirmation required for shutdown"}


# Mount static assets
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
