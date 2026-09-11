import os
import sys
import tempfile
import shutil
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from .analyzer import analyze_audio_track, calculate_cue_points
    from .rekordbox_xml import build_rekordbox_xml, save_rekordbox_xml
except (ImportError, ModuleNotFoundError, ValueError):
    try:
        from backend.analyzer import analyze_audio_track, calculate_cue_points
        from backend.rekordbox_xml import build_rekordbox_xml, save_rekordbox_xml
    except (ImportError, ModuleNotFoundError, ValueError):
        from analyzer import analyze_audio_track, calculate_cue_points
        from rekordbox_xml import build_rekordbox_xml, save_rekordbox_xml

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
    start_bar: int = 1


class PathAnalysisRequest(BaseModel):
    file_paths: List[str]
    bar_interval: int = 16
    cue_mode: str = "both"
    naming_template: str = "{bar} Bars"
    max_hot_cues: int = 8
    max_memory_cues: int = 8
    min_bpm: float = 60.0
    max_bpm: float = 180.0
    start_bar: int = 1


class ExportXmlRequest(BaseModel):
    tracks: List[dict]
    playlist_name: str = "Auto Cues"
    save_to_path: Optional[str] = None
    export_beatgrid: bool = True
    export_bpm: bool = True
    export_hot_cues: bool = True
    export_memory_cues: bool = True


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Rekordbox Auto Cue Generator is running</h1>"


@app.post("/api/analyze-path")
async def analyze_paths_endpoint(req: PathAnalysisRequest):
    """Analyzes a list of local file paths without uploading."""
    results = []
    errors = []
    
    for path in req.file_paths:
        if not os.path.exists(path):
            errors.append(f"File not found: {path}")
            continue
            
        try:
            analysis = analyze_audio_track(
                path,
                min_bpm=req.min_bpm,
                max_bpm=req.max_bpm
            )
            cues = calculate_cue_points(
                duration=analysis["duration"],
                bpm=analysis["bpm"],
                first_beat_offset=analysis["first_beat_offset"],
                bar_interval=req.bar_interval,
                cue_mode=req.cue_mode,
                naming_template=req.naming_template,
                max_hot_cues=req.max_hot_cues,
                max_memory_cues=req.max_memory_cues,
                start_bar=req.start_bar
            )
            analysis["cue_points"] = cues
            results.append(analysis)
        except Exception as e:
            errors.append(f"Failed to analyze '{os.path.basename(path)}': {str(e)}")
            
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
    start_bar: int = Form(1)
):
    """Handles browser file uploads, stores in temp folder, and analyzes."""
    results = []
    errors = []
    
    for file in files:
        # Create temp file
        temp_ext = os.path.splitext(file.filename)[1]
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=temp_ext)
        temp_path = temp_file.name
        
        try:
            content = await file.read()
            temp_file.write(content)
            temp_file.close()
            
            analysis = analyze_audio_track(
                temp_path,
                min_bpm=min_bpm,
                max_bpm=max_bpm
            )
            analysis["file_name"] = file.filename
            analysis["file_path"] = temp_path  # Note: local path for XML
            
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
            results.append(analysis)
        except Exception as e:
            errors.append(f"Failed to process '{file.filename}': {str(e)}")
            
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


@app.post("/api/pick-files")
async def pick_files_dialog():
    """Opens native Windows file dialog to select audio tracks."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        
        file_paths = filedialog.askopenfilenames(
            title="Select Audio Tracks for Rekordbox Auto Cues",
            filetypes=[
                ("Audio Files", "*.mp3 *.wav *.flac *.aiff *.aif *.m4a *.ogg"),
                ("All Files", "*.*")
            ]
        )
        root.destroy()
        return {"files": list(file_paths)}
    except Exception as e:
        return {"files": [], "error": str(e)}


@app.post("/api/pick-folder")
async def pick_folder_dialog():
    """Opens native Windows folder dialog to select audio tracks folder."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        
        folder = filedialog.askdirectory(title="Select Folder with Music Tracks")
        root.destroy()
        
        if not folder:
            return {"files": [], "folder": ""}
            
        supported_exts = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}
        found_files = []
        
        for root_dir, _, filenames in os.walk(folder):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in supported_exts:
                    found_files.append(os.path.join(root_dir, filename))
                    
        return {"files": found_files, "folder": folder}
    except Exception as e:
        return {"files": [], "folder": "", "error": str(e)}


@app.get("/api/heartbeat")
async def heartbeat():
    return {"status": "ok"}


@app.post("/api/shutdown")
async def shutdown():
    """Cleanly exits the application when the user closes the window."""
    def _delayed_exit():
        import time
        time.sleep(1.0)
        os._exit(0)
    import threading
    threading.Thread(target=_delayed_exit, daemon=True).start()
    return {"status": "shutting down"}


# Mount static assets
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

