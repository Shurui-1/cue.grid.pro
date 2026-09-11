import os
import sys
import time
import socket
import urllib.request
import webbrowser
import threading
import multiprocessing
import subprocess
import tempfile
import shutil

# Force UTF-8 encoding on Windows console
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def get_base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


SCRIPT_DIR = get_base_dir()
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def is_port_available(port: int) -> bool:
    """Checks if a local port is free to bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def find_free_port(start_port: int = 8765, max_attempts: int = 20) -> int:
    """Finds an available port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        if is_port_available(p):
            return p
    return start_port


def get_app_window_runner():
    """Finds an available browser executable that supports --app standalone window mode."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Edge\Application\msedge.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        shutil.which("msedge"),
        shutil.which("chrome"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def launch_desktop_window(url: str, max_wait: float = 15.0):
    """
    Waits for the local server to be ready, then opens the UI as a standalone native desktop app window.
    """
    start_time = time.time()
    server_ready = False
    
    while time.time() - start_time < max_wait:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.25)
            
    if not server_ready:
        time.sleep(0.5)

    runner = get_app_window_runner()
    if runner:
        profile_dir = os.path.join(tempfile.gettempdir(), "CueGridPro_Profile")
        os.makedirs(profile_dir, exist_ok=True)
        
        cmd = [
            runner,
            f"--app={url}",
            f"--user-data-dir={profile_dir}",
            "--window-size=1320,880",
            "--window-position=center",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
        ]
        try:
            subprocess.Popen(cmd)
            return
        except Exception as e:
            print(f"[WARN] Could not launch app window: {e}")

    # Fallback to default browser if no app runner found
    try:
        webbrowser.open(url)
    except Exception:
        if sys.platform == "win32":
            os.system(f"start {url}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    try:
        import uvicorn
        try:
            from backend.server import app
        except ImportError:
            from app.server import app
        
        port = find_free_port(8765)
        app_url = f"http://127.0.0.1:{port}"

        print("=====================================================")
        print("       Rekordbox Auto Cue Generator (CueGrid Pro)    ")
        print("=====================================================")
        print(f" Сервер запущен: {app_url}")
        print(" Открытие окна программы...")
        print(f" Прямой адрес в сети: {app_url}")
        print(" Для выхода закройте окно программы или нажмите Ctrl + C.")
        print("=====================================================\n")
        
        # Start opener in background thread
        opener_thread = threading.Thread(target=launch_desktop_window, args=(app_url,), daemon=True)
        opener_thread.start()
        
        # Run uvicorn server on main thread to keep application alive and responsive
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    except KeyboardInterrupt:
        print("\nЗавершение работы программы...")
        os._exit(0)
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        try:
            input("\nНажмите Enter для выхода...")
        except Exception:
            time.sleep(10)


