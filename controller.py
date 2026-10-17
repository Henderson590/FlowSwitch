import argparse
import json
import socket
import threading
import time
from pynput import keyboard, mouse

PORT = 24800
HOTKEY = "Ctrl + Alt + F12"


class FlowSwitchController:
    def __init__(self, host, port, token):
        self.host = host
        self.port = port
        self.token = token
        self.sock = None
        self.sock_lock = threading.Lock()
        self.active = False
        self.active_lock = threading.Lock()
        self.held = set()
        self.last_position = None
        self.last_toggle = 0.0

    def send(self, payload):
        with self.sock_lock:
            if self.sock is None:
                return
            try:
                data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
                self.sock.sendall(data)
            except OSError as exc:
                print(f"Connection lost: {exc}")
                self.sock = None
                with self.active_lock:
                    self.active = False

    def key_name(self, key):
        if isinstance(key, keyboard.KeyCode):
            if key.char is not None:
                return "char:" + key.char
            return None
        return str(key)

    def toggle(self):
        now = time.monotonic()
        if now - self.last_toggle < 0.35:
            return
        self.last_toggle = now
        with self.active_lock:
            self.active = not self.active
            state = self.active
        print("Remote input ON" if state else "Remote input OFF")

    def on_move(self, x, y):
        if self.last_position is None:
            self.last_position = (x, y)
            return
        old_x, old_y = self.last_position
        self.last_position = (x, y)
        with self.active_lock:
            active = self.active
        if active:
            dx, dy = int(x - old_x), int(y - old_y)
            if dx or dy:
                self.send({"type": "move", "dx": dx, "dy": dy})

    def on_click(self, x, y, button, pressed):
        with self.active_lock:
            active = self.active
        if active:
            self.send({
                "type": "click",
                "button": str(button).replace("Button.", ""),
                "action": "down" if pressed else "up",
            })

    def on_scroll(self, x, y, dx, dy):
        with self.active_lock:
            active = self.active
        if active:
            self.send({"type": "scroll", "dx": int(dx), "dy": int(dy)})

    def on_press(self, key):
        # Toggle with Ctrl + Alt + F12. Don't forward the toggle combination.
        self.held.add(key)
        ctrl = keyboard.Key.ctrl in self.held or keyboard.Key.ctrl_l in self.held or keyboard.Key.ctrl_r in self.held
        alt = keyboard.Key.alt in self.held or keyboard.Key.alt_l in self.held or keyboard.Key.alt_r in self.held
        if ctrl and alt and key == keyboard.Key.f12:
            self.toggle()
            return

        with self.active_lock:
            active = self.active
        if active:
            key_id = self.key_name(key)
            if key_id:
                self.send({"type": "key_down", "key": key_id})

    def on_release(self, key):
        self.held.discard(key)
        with self.active_lock:
            active = self.active
        if active:
            key_id = self.key_name(key)
            if key_id:
                self.send({"type": "key_up", "key": key_id})

    def run(self):
        print(f"Connecting to {self.host}:{self.port} ...")
        self.sock = socket.create_connection((self.host, self.port), timeout=8)
        self.sock.settimeout(None)
        hello = (json.dumps({"type": "hello", "token": self.token}) + "\n").encode("utf-8")
        self.sock.sendall(hello)
        response = self.sock.makefile("r", encoding="utf-8").readline()
        if not response or json.loads(response).get("type") != "ok":
            self.sock.close()
            self.sock = None
            raise RuntimeError("Receiver rejected the token.")

        print("Connected.")
        print(f"Press {HOTKEY} to toggle remote input. Keep the hotkey handy to return control locally.")

        mouse_listener = mouse.Listener(on_move=self.on_move, on_click=self.on_click, on_scroll=self.on_scroll)
        keyboard_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        mouse_listener.start()
        keyboard_listener.start()

        try:
            while mouse_listener.is_alive() and keyboard_listener.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\nStopping FlowSwitch controller.")
        finally:
            mouse_listener.stop()
            keyboard_listener.stop()
            if self.sock:
                self.sock.close()


def main():
    parser = argparse.ArgumentParser(description="FlowSwitch Windows input controller")
    parser.add_argument("--host", required=True, help="Receiver Mac's local IP address")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--token", required=True, help="Same shared secret used by the receiver")
    args = parser.parse_args()

    try:
        FlowSwitchController(args.host, args.port, args.token).run()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"FlowSwitch: {exc}")


if __name__ == "__main__":
    main()
