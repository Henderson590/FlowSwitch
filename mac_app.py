"""FlowSwitch Mac GUI receiver.

Run on macOS with Python 3.11+, tkinter and pynput.
Optional drag-and-drop support requires tkinterdnd2.
"""

import queue
import socket
import threading
import tkinter as tk
from pathlib import Path
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
    """Find the Mac's local network IP address."""
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
        self.root.title("FlowSwitch")
        self.root.geometry("520x850")
        self.root.minsize(460, 760)

        self.dark_mode = tk.BooleanVar(value=False)
        self.messages = queue.Queue()
        self.stop_event = None
        self.worker = None

        self.download_dir = str(Path.home() / "Downloads")
        self._animation_phase = 0
        self._theme_transition = False

        self._configure_style()

        # Main window
        self.outer = ttk.Frame(
            root,
            style="App.TFrame",
            padding=(30, 22, 30, 20),
        )
        self.outer.pack(fill="both", expand=True)

        # Header
        self.top = ttk.Frame(
            self.outer,
            style="App.TFrame",
        )
        self.top.pack(fill="x")

        self.connection_badge = ttk.Label(
            self.top,
            text="●  DISCONNECTED",
            style="Disconnected.TLabel",
        )
        self.connection_badge.pack(side="left")

        # Keep the existing theme button sizing and placement.
        self.theme_button = ttk.Button(
            self.top,
            text="☼",
            command=self.toggle_theme,
            style="Theme.TButton",
        )
        self.theme_button.pack(side="right")

        # Main branding
        self.brand = ttk.Label(
            self.outer,
            text="FlowSwitch",
            style="Title.TLabel",
            anchor="center",
        )
        self.brand.pack(fill="x", pady=(8, 0))

        self.platform = ttk.Label(
            self.outer,
            text="MacOS",
            style="Platform.TLabel",
            anchor="center",
        )
        self.platform.pack(fill="x", pady=(0, 8))

        # Monitor illustration
        self.monitor = tk.Canvas(
            self.outer,
            height=126,
            highlightthickness=0,
            bd=0,
        )
        self.monitor.pack(fill="x", pady=(0, 20))
        self._draw_monitor()

        # Connection card
        self.connection_card = ttk.Frame(
            self.outer,
            style="Card.TFrame",
            padding=(18, 16, 18, 16),
        )
        self.connection_card.pack(fill="x", pady=(0, 14))

        ttk.Label(
            self.connection_card,
            text="CONNECTION",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        ttk.Label(
            self.connection_card,
            text="Mac IP Address",
            style="Field.TLabel",
        ).pack(anchor="w")

        self.ip = tk.StringVar(value=local_ip())

        self.ip_row = ttk.Frame(
            self.connection_card,
            style="Card.TFrame",
        )
        self.ip_row.pack(fill="x", pady=(5, 12))

        self.ip_entry = ttk.Entry(
            self.ip_row,
            textvariable=self.ip,
            state="readonly",
            style="Rounded.TEntry",
        )
        self.ip_entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=5,
        )

        self.refresh_button = ttk.Button(
            self.ip_row,
            text="↻",
            command=self.refresh_ip,
            style="Secondary.TButton",
        )
        self.refresh_button.pack(side="left", padx=(8, 0))

        ttk.Label(
            self.connection_card,
            text="Custom Connection Token",
            style="Field.TLabel",
        ).pack(anchor="w")

        self.token = ttk.Entry(
            self.connection_card,
            show="•",
            style="Rounded.TEntry",
        )
        self.token.pack(fill="x", pady=(5, 14), ipady=5)

        self.connection_buttons = ttk.Frame(
            self.connection_card,
            style="Card.TFrame",
        )
        self.connection_buttons.pack(fill="x")

        self.start_button = ttk.Button(
            self.connection_buttons,
            text="Start Receiver",
            command=self.start,
            style="Accent.TButton",
        )
        self.start_button.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 5),
        )

        self.stop_button = ttk.Button(
            self.connection_buttons,
            text="Stop Receiver",
            command=self.stop,
            style="Danger.TButton",
            state="disabled",
        )
        self.stop_button.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(5, 0),
        )

        # File transfer card
        self.files_card = ttk.Frame(
            self.outer,
            style="Card.TFrame",
            padding=(18, 16, 18, 16),
        )
        self.files_card.pack(fill="x")

        ttk.Label(
            self.files_card,
            text="FILE TRANSFER",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(
            self.files_card,
            text="Incoming Files Save To",
            style="Field.TLabel",
        ).pack(anchor="w")

        self.download_dir_var = tk.StringVar(
            value=self.download_dir
        )

        self.folder_row = ttk.Frame(
            self.files_card,
            style="Card.TFrame",
        )
        self.folder_row.pack(fill="x", pady=(5, 12))

        # Editable path field, matching the Windows version.
        self.folder_entry = ttk.Entry(
            self.folder_row,
            textvariable=self.download_dir_var,
            style="Rounded.TEntry",
        )
        self.folder_entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=5,
        )

        self.browse_button = ttk.Button(
            self.folder_row,
            text="Browse",
            command=self.choose_download_dir,
            style="Secondary.TButton",
        )
        self.browse_button.pack(side="left", padx=(8, 0))

        self.file_buttons = ttk.Frame(
            self.files_card,
            style="Card.TFrame",
        )
        self.file_buttons.pack(fill="x", pady=(0, 10))

        self.send_button = ttk.Button(
            self.file_buttons,
            text="Send Files",
            command=self.send_files,
            style="Accent.TButton",
        )
        self.send_button.pack(fill="x")

        # Drag-and-drop area
        drop_text = (
            "↓\nDrop files here to send to Windows"
            if DND_AVAILABLE
            else "↓\nUse Send Files to choose files"
        )

        self.drop_zone = tk.Label(
            self.files_card,
            text=drop_text,
            font=("Helvetica Neue", 10),
            padx=12,
            pady=14,
            cursor="hand2",
            relief="flat",
            bd=0,
        )
        self.drop_zone.pack(fill="x", pady=(0, 2))
        self._style_drop_zone()

        if DND_AVAILABLE:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind(
                "<<Drop>>",
                self.on_files_dropped,
            )

        # Status at the bottom
        self.status = tk.StringVar(value="Ready to connect")

        self.status_bar = ttk.Frame(
            self.outer,
            style="App.TFrame",
        )
        self.status_bar.pack(
            side="bottom",
            fill="x",
            pady=(12, 0),
        )

        self.status_indicator = tk.Canvas(
            self.status_bar,
            width=10,
            height=10,
            highlightthickness=0,
            bd=0,
        )
        self.status_indicator.pack(
            side="left",
            padx=(2, 8),
        )

        self.status_label = ttk.Label(
            self.status_bar,
            textvariable=self.status,
            style="Status.TLabel",
            anchor="w",
        )
        self.status_label.pack(
            side="left",
            fill="x",
            expand=True,
        )

        self._update_status_indicator()
        self._bind_hover_effects()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(150, self.poll_messages)
        self.root.after(180, self._animate_ui)

    # ---------------------------------------------------------
    # Theme and appearance
    # ---------------------------------------------------------

    def _configure_style(self):
        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        dark = self.dark_mode.get()

        if dark:
            self.colors = {
                "bg": "#17181C",
                "card": "#22242A",
                "field": "#2B2D34",
                "text": "#F5F5F7",
                "muted": "#A9ABB5",
                "accent": "#F1F1F4",
                "border": "#383B44",
                "drop": "#292C34",
                "monitor": "#F5F5F7",
                "button": "#F1F1F4",
                "button_text": "#17181C",
                "status_text": "#B9BBC5",
                "hover": "#D9DAE0",
            }
        else:
            self.colors = {
                "bg": "#F5F6F8",
                "card": "#FFFFFF",
                "field": "#FFFFFF",
                "text": "#202127",
                "muted": "#737681",
                "accent": "#272932",
                "border": "#E0E2E8",
                "drop": "#F1F3F7",
                "monitor": "#272932",
                "button": "#272932",
                "button_text": "#FFFFFF",
                "status_text": "#656875",
                "hover": "#454854",
            }

        c = self.colors
        self.root.configure(bg=c["bg"])

        style.configure(
            ".",
            font=("Helvetica Neue", 10),
            background=c["bg"],
            foreground=c["text"],
        )

        style.configure(
            "App.TFrame",
            background=c["bg"],
        )

        style.configure(
            "Card.TFrame",
            background=c["card"],
            borderwidth=1,
            relief="flat",
        )

        style.configure(
            "Title.TLabel",
            font=("Helvetica Neue", 32, "bold"),
            background=c["bg"],
            foreground=c["text"],
        )

        style.configure(
            "Platform.TLabel",
            font=("Helvetica Neue", 15),
            background=c["bg"],
            foreground=c["muted"],
        )

        style.configure(
            "Section.TLabel",
            font=("Helvetica Neue", 9, "bold"),
            background=c["card"],
            foreground=c["muted"],
        )

        style.configure(
            "Field.TLabel",
            font=("Helvetica Neue", 9),
            background=c["card"],
            foreground=c["muted"],
        )

        style.configure(
            "Rounded.TEntry",
            fieldbackground=c["field"],
            foreground=c["text"],
            insertcolor=c["text"],
            padding=(10, 8),
            bordercolor=c["border"],
            lightcolor=c["border"],
            darkcolor=c["border"],
        )

        style.map(
            "Rounded.TEntry",
            bordercolor=[
                ("focus", c["muted"]),
                ("!focus", c["border"]),
            ],
        )

        style.configure(
            "TButton",
            font=("Helvetica Neue", 9, "bold"),
            padding=(14, 9),
            borderwidth=0,
            relief="flat",
            background=c["card"],
            foreground=c["text"],
        )

        style.map(
            "TButton",
            background=[
                ("disabled", c["card"]),
                ("pressed", c["border"]),
                ("active", c["border"]),
            ],
            foreground=[
                ("disabled", c["muted"]),
            ],
        )

        style.configure(
            "Accent.TButton",
            background=c["button"],
            foreground=c["button_text"],
            padding=(14, 10),
        )

        style.map(
            "Accent.TButton",
            background=[
                ("disabled", c["border"]),
                ("pressed", c["hover"]),
                ("active", c["hover"]),
            ],
            foreground=[
                ("disabled", c["muted"]),
                ("active", c["button_text"]),
            ],
        )

        style.configure(
            "Secondary.TButton",
            background=c["field"],
            foreground=c["text"],
            padding=(12, 8),
        )

        style.map(
            "Secondary.TButton",
            background=[
                ("pressed", c["border"]),
                ("active", c["border"]),
            ],
        )

        style.configure(
            "Danger.TButton",
            background="#D93645",
            foreground="#FFFFFF",
            padding=(14, 10),
        )

        style.map(
            "Danger.TButton",
            background=[
                ("disabled", c["border"]),
                ("pressed", "#B82A37"),
                ("active", "#E34A57"),
            ],
        )

        # IMPORTANT:
        # The theme button's existing padding and placement are unchanged.
        style.configure(
            "Theme.TButton",
            background=c["bg"],
            foreground=c["text"],
            width = 2,
            padx = 2,
            font=("Apple Color Emoji", 15),
            borderwidth=0,
        )

        style.map(
            "Theme.TButton",
            background=[
                ("pressed", c["border"]),
                ("active", c["border"]),
            ],
        )

        style.configure(
            "Drop.TLabel",
            background=c["drop"],
            foreground=c["text"],
            font=("Helvetica Neue", 10, "bold"),
        )

        style.configure(
            "Status.TLabel",
            background=c["bg"],
            foreground=c["status_text"],
            font=("Helvetica Neue", 9),
        )

        style.configure(
            "Connected.TLabel",
            background=c["bg"],
            foreground="#27C982",
            font=("Helvetica Neue", 9, "bold"),
        )

        style.configure(
            "Disconnected.TLabel",
            background=c["bg"],
            foreground="#F06464",
            font=("Helvetica Neue", 9, "bold"),
        )

        if hasattr(self, "monitor"):
            self._draw_monitor()

        if hasattr(self, "drop_zone"):
            self._style_drop_zone()

        if hasattr(self, "theme_button"):
            self.theme_button.configure(
                text="☾" if dark else "☼"
            )

        if hasattr(self, "status_indicator"):
            self._update_status_indicator()

    def _style_drop_zone(self):
        c = self.colors

        self.drop_zone.configure(
            bg=c["drop"],
            fg=c["muted"],
            activebackground=c["border"],
            activeforeground=c["text"],
        )

    def toggle_theme(self):
        self.dark_mode.set(not self.dark_mode.get())
        self._configure_style()

        self._theme_transition = True
        self.theme_button.configure(
            text="☾" if self.dark_mode.get() else "☼"
        )

        self.root.after(180, self._finish_theme_transition)

    def _finish_theme_transition(self):
        self._theme_transition = False

    # ---------------------------------------------------------
    # Monitor illustration and subtle animation
    # ---------------------------------------------------------

    def _draw_monitor(self):
        c = self.colors
        self.monitor.configure(bg=c["bg"])
        self.monitor.delete("all")

        width = max(self.monitor.winfo_width(), 300)
        cx = width / 2

        pulse = 2 if self._animation_phase % 24 < 12 else 3

        self.monitor.create_rectangle(
            cx - 76,
            7,
            cx + 76,
            91,
            outline=c["monitor"],
            width=pulse,
        )

        self.monitor.create_line(
            cx,
            91,
            cx,
            109,
            fill=c["monitor"],
            width=3,
        )

        self.monitor.create_line(
            cx - 31,
            110,
            cx + 31,
            110,
            fill=c["monitor"],
            width=3,
            capstyle="round",
        )

        self.monitor.create_oval(
            cx - 10,
            34,
            cx + 10,
            54,
            outline=c["monitor"],
            width=2,
        )

        self.monitor.create_line(
            cx - 23,
            64,
            cx + 23,
            64,
            fill=c["monitor"],
            width=2,
        )

    def _animate_ui(self):
        try:
            if not self.root.winfo_exists():
                return

            self._animation_phase += 1
            self._draw_monitor()

        except tk.TclError:
            return

        self.root.after(240, self._animate_ui)

    def _bind_hover_effects(self):
        self.drop_zone.bind(
            "<Enter>",
            self._drop_hover_enter,
        )
        self.drop_zone.bind(
            "<Leave>",
            self._drop_hover_leave,
        )

    def _drop_hover_enter(self, _event):
        self.drop_zone.configure(
            bg=self.colors["border"],
            fg=self.colors["text"],
        )

    def _drop_hover_leave(self, _event):
        self._style_drop_zone()

    # ---------------------------------------------------------
    # Network information
    # ---------------------------------------------------------

    def refresh_ip(self):
        self.ip.set(local_ip())
        self.status.set("IP address refreshed")

    # ---------------------------------------------------------
    # Receiver lifecycle
    # ---------------------------------------------------------

    def start(self):
        token = self.token.get()

        if len(token) < 16:
            messagebox.showerror(
                "Token too short",
                "Use a token at least 16 characters long.",
                parent=self.root,
            )
            return

        if self.worker and self.worker.is_alive():
            return

        self.stop_event = threading.Event()

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("Starting receiver…")

        save_path = self.download_dir_var.get().strip()

        if not save_path:
            save_path = str(Path.home() / "Downloads")

        self.download_dir = save_path

        self.worker = threading.Thread(
            target=self.run_server,
            args=(token, self.stop_event, save_path),
            daemon=True,
        )
        self.worker.start()

    def run_server(self, token, stop_event, download_dir):
        try:
            size = (
                self.root.winfo_screenwidth(),
                self.root.winfo_screenheight(),
            )

            run_receiver(
                token=token,
                stop_event=stop_event,
                status_callback=self.messages.put,
                screen_size=size,
                download_dir=download_dir,
            )
        except Exception:
            # Keep detailed exception information out of the main UI.
            self.messages.put("Connection lost")
        finally:
            self.messages.put("Receiver stopped")

    def stop(self):
        if self.stop_event:
            self.status.set("Stopping receiver…")
            self.stop_event.set()

    # ---------------------------------------------------------
    # Incoming file save location
    # ---------------------------------------------------------

    def choose_download_dir(self):
        current = self.download_dir_var.get().strip()

        initial = (
            current
            if current and Path(current).is_dir()
            else str(Path.home())
        )

        folder = filedialog.askdirectory(
            title="Choose where incoming files are saved",
            parent=self.root,
            initialdir=initial,
        )

        if folder:
            self.download_dir = folder
            self.download_dir_var.set(folder)
            self.status.set("Save location updated")

    # ---------------------------------------------------------
    # File transfer and drag-and-drop
    # ---------------------------------------------------------

    def on_files_dropped(self, event):
        try:
            paths = [
                str(Path(p))
                for p in self.root.tk.splitlist(event.data)
            ]
        except Exception:
            self.status.set("Unable to read dropped files")
            return "break"

        if not paths:
            return "break"

        files = [
            path for path in paths
            if Path(path).is_file()
        ]

        if not files:
            self.status.set("Drop files, not folders")
            return "break"

        if not send_files_to_controller(files):
            self.status.set(
                "Start the receiver and connect from Windows first"
            )
            return "break"

        self.status.set(
            f"Queued {len(files)} file(s) for transfer"
        )
        return "copy"

    def send_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose files to send",
            parent=self.root,
        )

        if not paths:
            return

        if not send_files_to_controller(paths):
            messagebox.showwarning(
                "Not connected",
                "Start the receiver and connect from Windows "
                "before sending files.",
                parent=self.root,
            )
            return

        self.status.set(
            f"Queued {len(paths)} file(s) for transfer"
        )

    # ---------------------------------------------------------
    # Status and lifecycle
    # ---------------------------------------------------------

    def _update_status_indicator(self):
        if not hasattr(self, "status_indicator"):
            return

        c = self.colors
        self.status_indicator.configure(bg=c["bg"])
        self.status_indicator.delete("all")

        connected = (
            self.worker is not None
            and self.worker.is_alive()
            and self.stop_event is not None
            and not self.stop_event.is_set()
        )

        color = "#27C982" if connected else "#9295A0"

        self.status_indicator.create_oval(
            1,
            1,
            9,
            9,
            fill=color,
            outline=color,
        )

    def poll_messages(self):
        try:
            while True:
                message = str(self.messages.get_nowait())
                low = message.lower()

                if (
                    "connected" in low
                    and not any(
                        word in low
                        for word in (
                            "disconnected",
                            "connection lost",
                            "not connected",
                            "receiver stopped",
                        )
                    )
                ):
                    self.connection_badge.configure(
                        text="●  CONNECTED",
                        style="Connected.TLabel",
                    )
                    self.status.set("Connected")

                elif any(
                    word in low
                    for word in (
                        "disconnected",
                        "connection lost",
                        "receiver stopped",
                        "stopped",
                    )
                ):
                    self.connection_badge.configure(
                        text="●  DISCONNECTED",
                        style="Disconnected.TLabel",
                    )
                    self.status.set("Ready to connect")

                elif any(
                    word in low
                    for word in (
                        "queued",
                        "saved",
                        "transfer",
                        "error",
                        "failed",
                        "couldn't",
                        "choose",
                        "sending",
                        "unable",
                    )
                ):
                    self.status.set(message)

        except queue.Empty:
            pass

        if not (self.worker and self.worker.is_alive()):
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

            self.connection_badge.configure(
                text="●  DISCONNECTED",
                style="Disconnected.TLabel",
            )

        self._update_status_indicator()
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
    # tkinterdnd2's native extension may require a compatible Tcl/Tk 8.6.
    # Fall back to standard Tk if the native extension cannot start.
    if DND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
        except Exception as exc:
            DND_AVAILABLE = False
            print(
                "FlowSwitch: native drag-and-drop unavailable:",
                exc,
            )
            print(
                "Use a compatible Python/Tcl-Tk 8.6 build "
                "to enable drag-and-drop."
            )
            root = tk.Tk()
    else:
        root = tk.Tk()

    MacApp(root)
    root.mainloop()