import os
import sys
import subprocess
import shutil
import PyInstaller.__main__

def build():
    build_dir = os.path.dirname(os.path.abspath(__file__))
    proj_dir = os.path.dirname(build_dir)
    frontend_dir = os.path.join(proj_dir, "frontend")
    
    print("==================================================")
    print("      Building CueGrid Pro Windows .EXE           ")
    print("==================================================")
    print(f"Project dir: {proj_dir}")
    print(f"Frontend assets dir: {frontend_dir}")
    
    # Collect soundfile DLLs / binaries if present
    import soundfile
    soundfile_dir = os.path.dirname(soundfile.__file__)
    print(f"Soundfile package dir: {soundfile_dir}")
    
    hidden_imports = [
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "librosa",
        "librosa.beat",
        "librosa.feature",
        "librosa.onset",
        "soundfile",
        "_soundfile",
        "_soundfile_data",
        "scipy",
        "scipy.signal",
        "scipy.stats",
        "scipy.special",
        "scipy.spatial.transform._rotation_groups",
        "mutagen",
        "mutagen.easyid3",
        "mutagen.id3",
        "mutagen.mp3",
        "mutagen.flac",
        "mutagen.wave",
        "mutagen.aiff",
        "mutagen.oggvorbis",
        "multipart",
        "python_multipart",
        "tkinter",
        "tkinter.filedialog",
        "backend",
        "backend.server",
        "backend.analyzer",
        "backend.rekordbox_xml",
        "app",
        "app.server",
        "app.analyzer",
        "app.rekordbox_xml"
    ]
    
    hidden_args = []
    for h in hidden_imports:
        hidden_args.extend(["--hidden-import", h])
        
    data_args = [
        "--add-data", f"{frontend_dir};frontend",
        "--add-data", f"{frontend_dir};static"
    ]
    
    # Add soundfile data/binaries if directory has _soundfile_data
    sf_data = os.path.join(soundfile_dir, "_soundfile_data")
    if os.path.exists(sf_data):
        data_args.extend(["--add-data", f"{sf_data};_soundfile_data"])
        
    # PyInstaller arguments
    icon_file = os.path.join(proj_dir, "icon.ico")
    icon_args = ["--icon", icon_file] if os.path.exists(icon_file) else []
    
    exclude_args = [
        "--exclude-module", "matplotlib",
        "--exclude-module", "IPython",
        "--exclude-module", "unittest",
        "--exclude-module", "pytest"
    ]

    start_script = os.path.join(proj_dir, "start.py")
    dist_dir = os.path.join(proj_dir, "dist")

    pyinstaller_args = [
        start_script,
        "--name=CueGridPro",
        "--onedir",             # Fast startup and reliable DLL loading for scientific packages
        f"--distpath={dist_dir}",
        "--noconfirm",
        "--clean",
        "--noconsole",          # Launches cleanly without any black Python console window
    ] + icon_args + exclude_args + hidden_args + data_args
    
    print("\nRunning PyInstaller with arguments:")
    print(" ".join(pyinstaller_args))
    
    PyInstaller.__main__.run(pyinstaller_args)
    
    exe_path = os.path.join(dist_dir, "CueGridPro", "CueGridPro.exe")
    if os.path.exists(exe_path):
        print("\n" + "="*50)
        print("[SUCCESS] Build complete!")
        print(f"Executable is ready at: {exe_path}")
        print("="*50)
    else:
        print("\n[ERROR] Executable not found after build.")

if __name__ == "__main__":
    build()
