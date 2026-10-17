import argparse
import hmac
import json
import socket
import threading
from pynput import keyboard, mouse

PORT = 24800
MAX_LINE = 8192

mouse_controller = mouse.Controller()
keyboard_controller = keyboard.Controller()
pressed_keys = {}
pressed_buttons = {}
state_lock = threading.Lock()


def resolve_key(value):
    if not isinstance(value, str):
        return None
    if value.startswith("Key."):
        name = value[4:]
        return getattr(keyboard.Key, name, None)
    if value.startswith("char:"):
        char = value[5:]
        return char if len(char) == 1 else None
    return None


def handle_event(event):
    kind = event.get("type")

    if kind == "move":
        dx = int(event.get("dx", 0))
        dy = int(event.get("dy", 0))
        mouse_controller.move(dx, dy)

    elif kind == "click":
        button_name = event.get("button", "left")
        button = getattr(mouse.Button, button_name, None)
        if button is not None:
            action = event.get("action")
            if action == "down":
                mouse_controller.press(button)
                pressed_buttons[button_name] = button
            elif action == "up":
                mouse_controller.release(button)
                pressed_buttons.pop(button_name, None)

    elif kind == "scroll":
        mouse_controller.scroll(int(event.get("dx", 0)), int(event.get("dy", 0)))

    elif kind in ("key_down", "key_up"):
        key_obj = resolve_key(event.get("key"))
        if key_obj is None:
            return
        if kind == "key_down":
            keyboard_controller.press(key_obj)
            pressed_keys[str(event.get("key"))] = key_obj
        else:
            keyboard_controller.release(key_obj)
            pressed_keys.pop(str(event.get("key")), None)


def release_all():
    for key_obj in list(pressed_keys.values()):
        try:
            keyboard_controller.release(key_obj)
        except Exception:
            pass
    pressed_keys.clear()

    for button in list(pressed_buttons.values()):
        try:
            mouse_controller.release(button)
        except Exception:
            pass
    pressed_buttons.clear()


def client_session(conn, expected_token):
    with conn:
        file = conn.makefile("r", encoding="utf-8", newline="\n")
        try:
            first_line = file.readline(MAX_LINE + 1)
            if not first_line or len(first_line) > MAX_LINE:
                return
            try:
                hello = json.loads(first_line)
            except json.JSONDecodeError:
                return

            supplied = str(hello.get("token", ""))
            if hello.get("type") != "hello" or not hmac.compare_digest(supplied, expected_token):
                print("Rejected client: invalid token.")
                return

            conn.sendall(b'{"type":"ok"}\n')
            print(f"Controller connected from {conn.getpeername()}")

            for line in file:
                if len(line) > MAX_LINE:
                    break
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        handle_event(event)
                except (json.JSONDecodeError, ValueError, TypeError, OSError) as exc:
                    print(f"Ignored invalid input event: {exc}")
        except (ConnectionError, OSError) as exc:
            print(f"Connection ended: {exc}")
        finally:
            release_all()
            print("Controller disconnected; released held keys/buttons.")


def main():
    parser = argparse.ArgumentParser(description="FlowSwitch input receiver")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: all network interfaces)")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--token", required=True, help="Shared secret; use a long random value")
    args = parser.parse_args()

    if len(args.token) < 16:
        parser.error("Use a token at least 16 characters long.")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(4)
    print(f"FlowSwitch receiver listening on {args.host}:{args.port}")
    print("Only use this prototype on a trusted private network.")

    try:
        while True:
            conn, address = server.accept()
            threading.Thread(target=client_session, args=(conn, args.token), daemon=True).start()
    except KeyboardInterrupt:
        print("\nStopping FlowSwitch receiver.")
    finally:
        server.close()
        release_all()


if __name__ == "__main__":
    main()
