"""FlowSwitch Mac GUI receiver. Run on macOS with Python 3.11+, tkinter and pynput."""
import queue
from pathlib import Path
import socket
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False

from receiver import PORT, run_receiver, send_files_to_controller


def local_ip():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    finally:
        probe.close()
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "Unavailable — check network settings"


class MacApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FlowSwitch — Mac Receiver")
        self.root.geometry("480x610")
        self.root.minsize(440, 570)
        self.messages = queue.Queue()
        self.stop_event = None
        self.worker = None

        frame = ttk.Frame(root, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="FlowSwitch", font=("Helvetica", 20, "bold")).pack(anchor="w")
        ttk.Label(frame, text="This Mac's local IP address").pack(anchor="w", pady=(18, 4))
        iprow = ttk.Frame(frame)
        iprow.pack(fill="x")
        self.ip = tk.StringVar(value=local_ip())
        ttk.Entry(iprow, textvariable=self.ip, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(iprow, text="Refresh", command=lambda: self.ip.set(local_ip())).pack(side="left", padx=(8, 0))

        ttk.Label(frame, text="Shared token (same token entered on Windows)").pack(anchor="w", pady=(14, 4))
        self.token = ttk.Entry(frame, show="•")
        self.token.pack(fill="x")

        self.start_button = ttk.Button(frame, text="Start Receiver", command=self.start)
        self.start_button.pack(fill="x", pady=(16, 0))
        self.stop_button = ttk.Button(frame, text="Stop Receiver", command=self.stop, state="disabled")
        self.stop_button.pack(fill="x", pady=(7, 0))
        self.download_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        ttk.Label(frame, text="Incoming files save to").pack(anchor="w", pady=(14, 4))
        folder_row = ttk.Frame(frame)
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=self.download_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="Browse…", command=self.choose_download_dir).pack(side="left", padx=(8, 0))
        self.drop_zone = ttk.Label(
            frame,
            text=("Drop files here to send to Windows" if DND_AVAILABLE else
                  "Drag-and-drop unavailable — install requirements-mac.txt"),
            anchor="center", justify="center", padding=14, relief="groove",
        )
        self.drop_zone.pack(fill="x", pady=(12, 0))
        if DND_AVAILABLE:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self.on_files_dropped)
        ttk.Button(frame, text="Send File(s)…", command=self.send_files).pack(fill="x", pady=(8, 0))

        self.status = tk.StringVar(value="Receiver stopped")
        ttk.Label(frame, textvariable=self.status, wraplength=420).pack(anchor="w", pady=(12, 0))

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(150, self.poll_messages)

    def start(self):
        token = self.token.get()
        if len(token) < 16:
            messagebox.showerror("Token too short", "Use a token at least 16 characters long.", parent=self.root)
            return
        if self.worker and self.worker.is_alive():
            return
        self.stop_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("Starting receiver…")
        self.worker = threading.Thread(
            target=self.run_server,
            args=(token, self.stop_event, self.download_dir.get().strip()),
            daemon=True,
        )
        self.worker.start()

    def run_server(self, token, stop_event, download_dir):
        try:
            size = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
            run_receiver(token=token, stop_event=stop_event, status_callback=self.messages.put,
                         screen_size=size, download_dir=download_dir)
        except Exception as exc:
            self.messages.put(f"Receiver error: {exc}")
        finally:
            self.messages.put("Receiver stopped")

    def choose_download_dir(self):
        folder = filedialog.askdirectory(title="Choose where incoming files are saved", parent=self.root)
        if folder:
            self.download_dir.set(folder)

    def on_files_dropped(self, event):
        try:
            paths = [str(Path(p)) for p in self.root.tk.splitlist(event.data)]
        except Exception as exc:
            self.status.set(f"Couldn't read dropped files: {exc}")
            return "break"
        if not paths:
            return "break"
        files = [p for p in paths if Path(p).is_file()]
        if not files:
            self.status.set("Drop files, not folders, to transfer them.")
            return "break"
        if not send_files_to_controller(files):
            self.status.set("Start the receiver and connect from Windows before sending files.")
            return "break"
        self.status.set(f"Queued {len(files)} file(s) for transfer to Windows…")
        return "copy"

    def send_files(self):
        paths = filedialog.askopenfilenames(title="Choose files to send", parent=self.root)
        if not paths:
            return
        if not send_files_to_controller(paths):
            messagebox.showwarning("Not connected", "Start the receiver and connect from Windows before sending files.", parent=self.root)

    def stop(self):
        if self.stop_event:
            self.status.set("Stopping safely…")
            self.stop_event.set()

    def poll_messages(self):
        try:
            while True:
                self.status.set(self.messages.get_nowait())
        except queue.Empty:
            pass
        if not (self.worker and self.worker.is_alive()):
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
        self.root.after(150, self.poll_messages)

    def close(self):
        if self.stop_event and self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.root.after(250, self.finish_close)
        else:
            self.root.destroy()

    def finish_close(self):
        if self.worker and self.worker.is_alive():
            self.root.after(200, self.finish_close)
        else:
            self.root.destroy()


if __name__ == "__main__":
    # tkinterdnd2 bundles a native TkDND extension built for Tcl/Tk 8.x.
    # Some Python builds (notably some Python 3.14 macOS builds) use a newer
    # Tcl/Tk runtime, which can make TkinterDnD.Tk() fail during startup.
    # Fall back to standard Tk so the app and file-picker transfer still work.
    if DND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
        except Exception as exc:
            DND_AVAILABLE = False
            print(f"FlowSwitch: native drag-and-drop unavailable: {exc}")
            print("Use Python 3.12/3.13 with a compatible Tcl/Tk 8.6 build to enable drag-and-drop.")
            root = tk.Tk()
    else:
        root = tk.Tk()
    MacApp(root)
    root.mainloop()
