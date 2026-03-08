import tkinter as tk
from tkinter import ttk
import threading
from pynput import keyboard
import time
import sv_ttk

exit_event = None
gui_closed = False
selected_delay = 0.005
current_fps = 180
is_running = False

def on_press_c(key):
    if key == keyboard.Key.caps_lock and is_running:
        press_keys()

def on_press(key):
    if key == keyboard.Key.esc:
        pass

def press_keys():
    global selected_delay
    controller = keyboard.Controller()
    controller.press(keyboard.Key.space)
    controller.release(keyboard.Key.space)
    time.sleep(selected_delay)
    controller.press(keyboard.Key.ctrl)
    threading.Timer(0.3, controller.release, args=[keyboard.Key.ctrl]).start()

def worker():
    global exit_event, gui_closed
    k_listener = keyboard.Listener(on_press=on_press)
    k_listener_c = keyboard.Listener(on_press=on_press_c)
    k_listener.start()
    k_listener_c.start()
    while not exit_event.is_set():
        time.sleep(0.1)
        if not gui_closed and not root.winfo_exists():
            gui_closed = True
            exit_event.set()
    k_listener.stop()
    k_listener_c.stop()

def on_select(value, fps):
    global selected_delay, current_fps
    selected_delay = float(value)
    current_fps = fps
    status_label.config(text=f"Current FPS is {current_fps}")
    print(f"Delay selected: {selected_delay}")

def toggle_script():
    global is_running
    if is_running:
        is_running = False
        start_stop_button.config(text="Start")
        print("Script stopped")
    else:
        is_running = True
        start_stop_button.config(text="Stop")
        print("Script started")

def main():
    global exit_event, gui_closed, root, status_label, start_stop_button, worker_thread

    root = tk.Tk()
    root.geometry("400x250")
    root.overrideredirect(True) 
    sv_ttk.set_theme("dark")

    title_bar = ttk.Frame(root)
    title_bar.pack(fill="x")

    title_label = ttk.Label(title_bar, text="Apex tools", anchor="w")
    title_label.pack(side="left", padx=5)

    close_button = ttk.Button(title_bar, text="X", command=root.quit, width=2)
    close_button.pack(side="right", padx=5)

    content = ttk.Frame(root)
    content.pack(expand=True, fill="both", padx=10, pady=10)

    menu_frame = ttk.Frame(content)
    menu_frame.pack(fill="x")

    # Меню "Menu"
#    file_menu_btn = ttk.Menubutton(menu_frame, text="Menu")
#    file_menu_btn.pack(side="left", padx=5)
#    file_menu = tk.Menu(file_menu_btn, tearoff=0)
#    file_menu.add_command(label="Exit", command=root.quit)
#    file_menu_btn.configure(menu=file_menu)

    framerate_menu_btn = ttk.Menubutton(menu_frame, text="Game framerate ")
    framerate_menu_btn.pack(side="left", padx=5)
    framerate_menu = tk.Menu(framerate_menu_btn, tearoff=0)
    framerate_menu.add_command(label="144", command=lambda: on_select("0.007", 144))
    framerate_menu.add_command(label="180", command=lambda: on_select("0.005", 180))
    framerate_menu.add_command(label="240", command=lambda: on_select("0.0045", 240))
    framerate_menu.add_command(label="300", command=lambda: on_select("0.0038", 300))
    framerate_menu_btn.configure(menu=framerate_menu)

    status_label = ttk.Label(content, text=f"Current FPS is {current_fps}")
    status_label.pack(pady=10)

    start_stop_button = ttk.Button(content, text="Start", command=toggle_script)
    start_stop_button.pack(pady=20)

    footer_label = ttk.Label(content, text="Made by blaQarm", font=("Arial", 8))
    footer_label.pack(side="bottom", pady=10)

    def move_window(event):
        root.geometry(f'+{event.x_root}+{event.y_root}')

    title_bar.bind("<B1-Motion>", move_window)
    title_label.bind("<B1-Motion>", move_window)

    exit_event = threading.Event()
    worker_thread = threading.Thread(target=worker)
    worker_thread.start()

    def on_close():
        global exit_event, gui_closed
        exit_event.set()
        worker_thread.join()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__ == "__main__":
    main()
