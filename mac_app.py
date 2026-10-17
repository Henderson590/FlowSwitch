"""FlowSwitch Mac GUI receiver. Run on macOS with Python 3.11+, tkinter and pynput."""
import queue
import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from receiver import PORT, run_receiver


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
        self.root.geometry("440x320")
        self.root.minsize(420, 300)
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
        self.status = tk.StringVar(value="Receiver stopped")
        ttk.Label(frame, textvariable=self.status, wraplength=390).pack(anchor="w", pady=(12, 0))

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
            args=(token, self.stop_event),
            daemon=True,
        )
        self.worker.start()

    def run_server(self, token, stop_event):
        try:
            size = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
            run_receiver(token=token, stop_event=stop_event, status_callback=self.messages.put, screen_size=size)
        except Exception as exc:
            self.messages.put(f"Receiver error: {exc}")
        finally:
            self.messages.put("Receiver stopped")

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
    root = tk.Tk()
    MacApp(root)
    root.mainloop()
