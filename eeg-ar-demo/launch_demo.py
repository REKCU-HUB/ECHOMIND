"""Open the native EEG monitor and the linked AR website as separate windows."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import webbrowser

from demo_engine import DemoEngine
from demo_server import create_server
from monitor_demo import DemoMonitor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true', help='Open monitor only, for local QA')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    assets = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'web' / 'dist'
    if not (assets / 'index.html').is_file():
        messagebox.showerror('EchoMind demo', 'The AR demo files are missing. Rebuild web/dist or use the packaged EXE.')
        root.destroy()
        return
    engine = DemoEngine()
    try:
        server = create_server(args.port, engine, assets)
    except OSError:
        server = create_server(0, engine, assets)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/'
    screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
    monitor_w = min(1100, max(900, int(screen_w * .46)))
    height = min(920, max(720, screen_h - 100))
    browser_w = max(900, screen_w - monitor_w - 25)
    browser_x = monitor_w + 15 if screen_w >= 1800 else 70
    candidates = [
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/Application/chrome.exe',
    ]
    browser_exe = next((p for p in candidates if p.is_file()), None)
    browser_processes = []
    profile = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'EchoMind EEG Demo' / f'browser-{server.server_port}'

    def open_ar():
        if browser_exe:
            try:
                process = subprocess.Popen([
                    str(browser_exe), f'--app={url}', f'--user-data-dir={profile}',
                    '--no-first-run', '--no-default-browser-check', '--disable-features=msEdgeSidebarV2',
                    f'--window-size={browser_w},{height}', f'--window-position={browser_x},40',
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                browser_processes.append(process)
            except OSError as error:
                messagebox.showerror('Open AR demo', f'Could not open the AR window: {error}\n\nOpen {url} in your browser.')
        else:
            webbrowser.open(url)

    closing = False
    def close():
        nonlocal closing
        if closing:
            return
        closing = True
        threading.Thread(target=server.shutdown, daemon=True).start()
        root.destroy()

    DemoMonitor(root, engine, open_ar, close)
    root.geometry(f'{monitor_w}x{height}+10+40')
    root.protocol('WM_DELETE_WINDOW', close)
    root.deiconify()
    if not args.no_browser:
        root.after(600, open_ar)
    root.mainloop()
    server.server_close()


if __name__ == '__main__':
    main()
