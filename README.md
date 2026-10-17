# FlowSwitch — prototype 0.1

A small cross-platform proof of concept for sharing mouse and keyboard input between two computers while each computer keeps using its own display.

**Current milestone:** Windows controller → macOS receiver, with a hotkey to enable/disable forwarding. This is the input/network foundation; edge-of-screen handoff comes next.

## Requirements

- Python 3.10 or newer on both computers
- Both computers on the same trusted local network
- Do not expose port `24800` to the public internet
- macOS: grant Accessibility/Input Monitoring permissions to the terminal or Python app if macOS requests them

## 1. Install dependencies on both computers

Open a terminal in this project folder:

```bash
python -m pip install -r requirements.txt
```

On some systems, the command may be `python3` instead of `python`.

## 2. Start the receiver on the Mac

Find the Mac's local IP address in System Settings → Network, then run:

```bash
python receiver.py --token "replace-this-with-a-long-random-secret"
```

If macOS asks, allow the required input permissions. Allow incoming connections for Python if the firewall asks.

## 3. Start the controller on Windows

In PowerShell, from the project folder:

```powershell
python controller.py --host 192.168.1.50 --token "replace-this-with-a-long-random-secret"
```

Replace `192.168.1.50` with the Mac's actual local IP. The token must match the receiver's token.

## 4. Use the prototype

- Press **Ctrl + Alt + F12** to toggle remote input forwarding on/off.
- While enabled, mouse movement, clicks, scrolling, and keyboard events are sent to the Mac.
- Press the hotkey again before typing locally on Windows.

## Important limitations in this first prototype

- This is **not remote desktop**: it does not transmit or display the Mac's screen.
- It does not yet automatically switch when the cursor reaches a screen edge. That is the next milestone after verifying network input works.
- The initial prototype is Windows-controller → Mac-receiver only.
- Network input is not encrypted in this prototype. Use only on a trusted private LAN, use a unique token, and never port-forward the receiver.
- This is a prototype, not a polished or security-audited product.
