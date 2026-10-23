import ctypes
import json
import queue
import sys
import threading
import time
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import simpledialog, ttk

import sv_ttk
from pynput import keyboard

FPS_PRESETS = (60, 120, 144, 165, 180, 240, 300)
FINE_TUNE_LIMIT_MS = 10.0
JUMP_HOLD_S = 0.02
KEY_FIELDS = ("activation", "jump", "crouch")

DEFAULT_CONFIG = {
    "fps": 180,
    "fine_tune_ms": 0.0,
    "activation": {"type": "special", "name": "caps_lock"},
    "jump": {"type": "special", "name": "space"},
    "crouch": {"type": "special", "name": "ctrl"},
    "crouch_hold_ms": 300,
    "cooldown_ms": 500,
}


def config_path():
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    return base / "config.json"


CONFIG_PATH = config_path()


def key_to_data(key):
    if isinstance(key, keyboard.Key):
        return {"type": "special", "name": key.name}
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return {"type": "char", "char": key.char}
        if key.vk is not None:
            return {"type": "vk", "vk": int(key.vk)}
    return {"type": "special", "name": "space"}


def data_to_key(data):
    if not isinstance(data, dict):
        return keyboard.Key.space
    kind = data.get("type")
    if kind == "special":
        return getattr(keyboard.Key, str(data.get("name", "space")), keyboard.Key.space)
    if kind == "char":
        char = data.get("char")
        if isinstance(char, str) and char:
            return keyboard.KeyCode.from_char(char)
        return keyboard.Key.space
    if kind == "vk":
        try:
            return keyboard.KeyCode.from_vk(int(data["vk"]))
        except (KeyError, TypeError, ValueError):
            return keyboard.Key.space
    return keyboard.Key.space


def key_signature(key):
    return json.dumps(key_to_data(key), sort_keys=True)


def get_key_name(key):
    if isinstance(key, keyboard.Key):
        return key.name.replace("_", " ").title()
    if isinstance(key, keyboard.KeyCode):
        if key.char == " ":
            return "Space"
        if key.char == "\t":
            return "Tab"
        if key.char is not None and key.char.isprintable():
            return key.char.upper()
        if key.vk is not None:
            for special in keyboard.Key:
                if getattr(special.value, "vk", None) == key.vk:
                    return special.name.replace("_", " ").title()
            return f"VK {key.vk}"
    return "Unknown"


def load_config():
    config = deepcopy(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return config
    if not isinstance(raw, dict):
        return config

    try:
        config["fps"] = max(1, min(1000, int(raw.get("fps", config["fps"]))))
    except (TypeError, ValueError):
        pass

    try:
        fine_tune = float(raw.get("fine_tune_ms", config["fine_tune_ms"]))
        config["fine_tune_ms"] = max(-FINE_TUNE_LIMIT_MS, min(FINE_TUNE_LIMIT_MS, fine_tune))
    except (TypeError, ValueError):
        pass

    for field in ("crouch_hold_ms", "cooldown_ms"):
        try:
            value = int(raw.get(field, config[field]))
        except (TypeError, ValueError):
            continue
        config[field] = max(0, min(5000, value))

    for field in KEY_FIELDS:
        config[field] = key_to_data(data_to_key(raw.get(field, config[field])))

    signatures = {key_signature(data_to_key(config[field])) for field in KEY_FIELDS}
    if len(signatures) < len(KEY_FIELDS):
        for field in KEY_FIELDS:
            config[field] = deepcopy(DEFAULT_CONFIG[field])

    return config


class SuperglideApp:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.fps = int(self.config["fps"])
        self.fine_tune_ms = float(self.config["fine_tune_ms"])
        self.crouch_hold_s = int(self.config["crouch_hold_ms"]) / 1000.0
        self.cooldown_s = int(self.config["cooldown_ms"]) / 1000.0
        self.keys = {field: data_to_key(self.config[field]) for field in KEY_FIELDS}
        self.delay = 1.0 / self.fps

        self.state_lock = threading.Lock()
        self.save_lock = threading.Lock()
        self.injected_lock = threading.Lock()

        self.capture_target = None
        self.is_running = False
        self.held = set()
        self.injected_held = {}
        self.last_trigger = 0.0
        self.closing = False
        self.sequence_thread = None
        self.timer_period_set = False
        self.message_serial = 0

        self.controller = keyboard.Controller()
        self.ui_queue = queue.Queue()
        self.listener = None

        self._recompute_delay()
        self._start_timer_resolution()
        self._build_ui()
        self._start_listener()
        self._refresh_key_labels()
        self._refresh_status()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self._drain_ui_queue)

    def _start_timer_resolution(self):
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
            self.timer_period_set = True
        except Exception:
            pass

    def _recompute_delay(self):
        delay_ms = 1000.0 / max(1, self.fps) + self.fine_tune_ms
        self.delay = max(0.0005, delay_ms / 1000.0)

    def _build_ui(self):
        self.root.title("Superglide")
        self.root.geometry("460x380")
        self.root.minsize(440, 340)
        sv_ttk.set_theme("dark")

        content = ttk.Frame(self.root)
        content.pack(expand=True, fill="both", padx=12, pady=12)

        settings = ttk.Frame(content)
        settings.pack(fill="x")

        self.fps_menu_btn = ttk.Menubutton(settings, text=f"FPS: {self.fps}")
        self.fps_menu_btn.pack(side="left")
        fps_menu = tk.Menu(self.fps_menu_btn, tearoff=0)
        for value in FPS_PRESETS:
            fps_menu.add_command(label=f"{value} FPS", command=lambda v=value: self.set_fps(v))
        fps_menu.add_separator()
        fps_menu.add_command(label="Custom...", command=self._ask_custom_fps)
        self.fps_menu_btn.configure(menu=fps_menu)

        ttk.Label(settings, text="Fine-tune (ms):").pack(side="left", padx=(16, 4))
        self.fine_tune_var = tk.StringVar(value=f"{self.fine_tune_ms:.1f}")
        self.fine_tune_spin = ttk.Spinbox(
            settings,
            from_=-FINE_TUNE_LIMIT_MS,
            to=FINE_TUNE_LIMIT_MS,
            increment=0.1,
            width=6,
            textvariable=self.fine_tune_var,
            command=self._apply_fine_tune,
        )
        self.fine_tune_spin.pack(side="left")
        self.fine_tune_spin.bind("<Return>", self._apply_fine_tune)
        self.fine_tune_spin.bind("<FocusOut>", self._apply_fine_tune)

        self.status_var = tk.StringVar()
        ttk.Label(content, textvariable=self.status_var, anchor="center").pack(fill="x", pady=(12, 2))

        self.message_var = tk.StringVar()
        ttk.Label(content, textvariable=self.message_var, anchor="center").pack(fill="x", pady=(0, 8))

        key_frame = ttk.LabelFrame(content, text="Keybinds")
        key_frame.pack(fill="x", pady=4)

        self.key_vars = {}
        for field, title in (("activation", "Activation"), ("jump", "Jump"), ("crouch", "Crouch")):
            row = ttk.Frame(key_frame)
            row.pack(fill="x", padx=4, pady=2)
            ttk.Label(row, text=title, width=10).pack(side="left")
            var = tk.StringVar()
            self.key_vars[field] = var
            ttk.Label(row, textvariable=var, width=20).pack(side="left")
            ttk.Button(
                row,
                text="Set",
                width=6,
                command=lambda f=field: self.start_capture(f),
            ).pack(side="right")

        self.start_stop_button = ttk.Button(content, text="Start", command=self.toggle_script)
        self.start_stop_button.pack(pady=(14, 4))
        ttk.Label(content, text="Made by blaQarm", font=("Arial", 8)).pack(side="bottom", pady=(4, 0))

    def _start_listener(self):
        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.start()

    def _on_press(self, key, injected=False):
        if injected or key is None:
            return

        signature = key_signature(key)
        if signature in self.held:
            return
        self.held.add(signature)

        with self.state_lock:
            target = self.capture_target
            activation_signature = key_signature(self.keys["activation"])

        if target is not None:
            self._bind_key(key, target)
            return

        if not self.is_running or signature != activation_signature:
            return

        now = time.perf_counter()
        if now - self.last_trigger < self.cooldown_s:
            return
        self.last_trigger = now

        self.sequence_thread = threading.Thread(target=self._run_sequence, daemon=True)
        self.sequence_thread.start()

    def _on_release(self, key, injected=False):
        if injected or key is None:
            return
        self.held.discard(key_signature(key))

    def _bind_key(self, key, target):
        signature = key_signature(key)
        conflict = None
        with self.state_lock:
            for field, existing in self.keys.items():
                if field != target and key_signature(existing) == signature:
                    conflict = field
                    break
            if conflict is None:
                self.keys[target] = key
                self.capture_target = None

        if conflict is not None:
            self.ui_queue.put(
                ("message", f"That key is already used for {conflict.title()}. Press another key.")
            )
            return

        self.save_config()
        self.ui_queue.put(("message", f"{target.title()} set to {get_key_name(key)}"))
        self.ui_queue.put(("refresh", None))

    def start_capture(self, target):
        with self.state_lock:
            self.capture_target = target
        self._refresh_status()
        self._show_message(f"Press a key for {target.title()}.")

    def _refresh_key_labels(self):
        with self.state_lock:
            values = {field: get_key_name(self.keys[field]) for field in KEY_FIELDS}
        for field, var in self.key_vars.items():
            var.set(values[field])

    def _refresh_status(self):
        with self.state_lock:
            target = self.capture_target
            activation = get_key_name(self.keys["activation"])

        if target is not None:
            text = f"Press a key for {target.title()}..."
        else:
            mode = "RUNNING" if self.is_running else "STOPPED"
            text = (
                f"{mode} | {self.fps} FPS | {self.delay * 1000:.2f} ms"
                f" | Activation: {activation}"
            )
        self.status_var.set(text)

    def _show_message(self, text, timeout_ms=2500):
        self.message_serial += 1
        serial = self.message_serial
        self.message_var.set(text)
        self.root.after(
            timeout_ms,
            lambda: self.message_var.set("") if self.message_serial == serial else None,
        )

    def _drain_ui_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "message":
                    self._show_message(payload)
                elif kind == "timing":
                    self._show_message(payload, 1500)
                elif kind == "refresh":
                    self._refresh_key_labels()
                    self._refresh_status()
        except queue.Empty:
            pass

        if not self.closing:
            self.root.after(50, self._drain_ui_queue)

    def set_fps(self, fps):
        self.fps = max(1, min(1000, int(fps)))
        self.fps_menu_btn.configure(text=f"FPS: {self.fps}")
        self._recompute_delay()
        self._refresh_status()
        self.save_config()

    def _ask_custom_fps(self):
        value = simpledialog.askinteger(
            "Custom FPS",
            "In-game FPS cap:",
            parent=self.root,
            minvalue=30,
            maxvalue=1000,
        )
        if value is not None:
            self.set_fps(value)

    def _apply_fine_tune(self, event=None):
        try:
            value = float(self.fine_tune_var.get())
        except ValueError:
            value = self.fine_tune_ms
        value = max(-FINE_TUNE_LIMIT_MS, min(FINE_TUNE_LIMIT_MS, value))
        self.fine_tune_ms = value
        self.fine_tune_var.set(f"{value:.1f}")
        self._recompute_delay()
        self._refresh_status()
        self.save_config()
        return None

    def toggle_script(self):
        self.is_running = not self.is_running
        self.start_stop_button.configure(text="Stop" if self.is_running else "Start")
        self._refresh_status()

    def _precise_wait(self, seconds):
        if seconds <= 0:
            return
        end = time.perf_counter() + seconds
        while not self.closing:
            remaining = end - time.perf_counter()
            if remaining <= 0:
                return
            if remaining > 0.0015:
                time.sleep(remaining - 0.001)

    def _inject_press(self, key):
        self.controller.press(key)
        with self.injected_lock:
            self.injected_held[key_signature(key)] = key

    def _inject_release(self, key):
        try:
            self.controller.release(key)
        finally:
            with self.injected_lock:
                self.injected_held.pop(key_signature(key), None)

    def _release_injected(self):
        with self.injected_lock:
            keys = list(self.injected_held.values())
            self.injected_held.clear()
        for key in keys:
            try:
                self.controller.release(key)
            except Exception:
                pass

    def _run_sequence(self):
        with self.state_lock:
            jump = self.keys["jump"]
            crouch = self.keys["crouch"]

        jump_down = False
        crouch_down = False
        try:
            self._inject_press(jump)
            jump_down = True
            wait_start = time.perf_counter()
            self._precise_wait(self.delay)
            measured = time.perf_counter() - wait_start
            self._inject_press(crouch)
            crouch_down = True
            self._precise_wait(JUMP_HOLD_S)
            self._inject_release(jump)
            jump_down = False
            remaining = self.crouch_hold_s - JUMP_HOLD_S
            if remaining > 0:
                self._precise_wait(remaining)
            self.ui_queue.put(("timing", f"Jump to Crouch: {measured * 1000:.2f} ms"))
        except Exception as exc:
            self.ui_queue.put(("message", f"Input error: {exc}"))
        finally:
            if crouch_down:
                try:
                    self._inject_release(crouch)
                except Exception:
                    pass
            if jump_down:
                try:
                    self._inject_release(jump)
                except Exception:
                    pass

    def save_config(self):
        with self.state_lock:
            data = {
                "fps": self.fps,
                "fine_tune_ms": round(self.fine_tune_ms, 2),
                "activation": key_to_data(self.keys["activation"]),
                "jump": key_to_data(self.keys["jump"]),
                "crouch": key_to_data(self.keys["crouch"]),
                "crouch_hold_ms": int(round(self.crouch_hold_s * 1000)),
                "cooldown_ms": int(round(self.cooldown_s * 1000)),
            }
        with self.save_lock:
            try:
                CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError as exc:
                self.ui_queue.put(("message", f"Could not save config: {exc}"))

    def on_close(self):
        if self.closing:
            return
        self.closing = True
        self.is_running = False

        thread = self.sequence_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass

        self._release_injected()
        self.save_config()

        if self.timer_period_set:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

        self.root.destroy()


def main():
    root = tk.Tk()
    SuperglideApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
