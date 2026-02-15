import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import shutil
import threading
import time
import json
import os
import re
import pyautogui
import pydirectinput
import keyboard
import ctypes
import pytesseract
import requests
import random
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- DPI Awareness for high resolution screens ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

CONFIG_FILE = "scgm_config.json"
POS_FILE = "scgm_positions.json"

# --- Tesseract OCR Configuration ---
# Check bundled path first, then local folder
bundled_tess_path = resource_path(r"Tesseract-OCR\tesseract.exe")
local_tess_path = os.path.abspath(r"Tesseract-OCR\tesseract.exe")

if os.path.exists(bundled_tess_path):
    pytesseract.pytesseract.tesseract_cmd = bundled_tess_path
elif os.path.exists(local_tess_path):
    pytesseract.pytesseract.tesseract_cmd = local_tess_path

class SelectionOverlay:
    """Semi-transparent overlay for selecting a region on screen."""
    def __init__(self, callback):
        self.callback = callback
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0.5)
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.config(cursor="cross")
        self.canvas = tk.Canvas(self.root, cursor="cross", bg="grey")
        self.canvas.pack(fill="both", expand=True)
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.root.bind("<ButtonPress-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline='#00FF00', width=3)

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        end_x, end_y = event.x, event.y
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        width = abs(self.start_x - end_x)
        height = abs(self.start_y - end_y)
        self.root.destroy()
        if width > 5 and height > 5:
            self.callback((left, top, width, height))

class SCGMreconnect(tk.Tk):
    """Main application class for SCGMreconnect macro."""
    def __init__(self):
        super().__init__()
        self.title("GPO auto-reconnect")
        self.geometry("480x850")
        
        # Internal State Management
        self.reconnect_active = False
        self.joiner_active = False
        self.ocr_nav_active = False
        self.needs_calibration = False
        self._coord_history = [] 
        self._move_history = []

        # Default Configuration Parameters
        self.config = {
            "server_code": "ex2zKt6dSX",
            "reconnect_interval": 10,
            "wait_after_reconnect": 30,
            "reconnect_image": "reconnect_button.png",
            "confidence": 0.8,
            "always_on_top": True,
            "ocr_region": [0, 0, 100, 50],
            "target_x": 0.0,
            "target_y": 0.0,
            "target_z": 0.0,
            "nav_threshold": 0.7,
            "nav_mapping": {
                "w": "z-", 
                "d": "x+",
                "space": "y+"
            },
            "discord_webhook": "",
            "macro_hotkey": "f1"
        }
        self.load_config()
        self.attributes("-topmost", self.config.get("always_on_top", True))
        self.create_widgets()
        
        # Start background processing loop
        threading.Thread(target=self.main_loop, daemon=True).start()

    def load_config(self):
        """Loads settings from JSON file."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config.update(json.load(f))
            except Exception as e:
                print(f"Config Load Error: {e}")

    def save_config(self):
        """Saves current UI settings to JSON file."""
        try:
            self.config["server_code"] = self.entry_server_code.get()
            self.config["reconnect_interval"] = int(self.entry_interval.get())
            self.config["wait_after_reconnect"] = int(self.entry_wait_time.get())
            self.config["always_on_top"] = self.var_topmost.get()
            self.config["target_x"] = self.safe_get_float(self.entry_target_x)
            self.config["target_y"] = self.safe_get_float(self.entry_target_y)
            self.config["target_z"] = self.safe_get_float(self.entry_target_z)
            self.config["discord_webhook"] = self.entry_discord.get().strip()
            self.config["macro_hotkey"] = self.entry_macro_key.get().strip().lower()
            
            # Save Mapping from UI
            if hasattr(self, 'combo_w_map'):
                self.config["nav_mapping"]["w"] = self.combo_w_map.get()
                self.config["nav_mapping"]["d"] = self.combo_d_map.get()
            
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Config Save Error: {e}")

    def manual_save(self):
        self.save_config()
        self.log("Settings saved to config.")

    def safe_get_float(self, entry):
        """Robustly extracts a float value from a text entry."""
        try:
            val = entry.get().strip()
            if not val: return 0.0
            clean_val = "".join(c for c in val if c.isdigit() or c in ".-")
            match = re.search(r'[-+]?\d*\.?\d+', clean_val)
            return float(match.group()) if match else 0.0
        except:
            return 0.0

    def create_widgets(self):
        """Builds the tabbed localized UI with shared activity logs."""
        # 1. Main Container (Notebook)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Tabs
        self.tab_setup = ttk.Frame(self.notebook, padding="10")
        self.tab_reconnect = ttk.Frame(self.notebook, padding="10")
        self.tab_joiner = ttk.Frame(self.notebook, padding="10")
        self.tab_coord = ttk.Frame(self.notebook, padding="10")

        self.notebook.add(self.tab_setup, text="[1] Setup & Settings")
        self.notebook.add(self.tab_reconnect, text="[2] Auto Reconnect")
        self.notebook.add(self.tab_joiner, text="[3] Server Joiner")
        self.notebook.add(self.tab_coord, text="[4] Coord Nav")

        # --- TAB 1: SETUP & GLOBAL ---
        s_main = self.tab_setup
        ttk.Label(s_main, text="Button Positions Setup", font=("Segoe UI", 12, "bold")).pack(pady=(0, 5))
        
        setup_frame = ttk.LabelFrame(s_main, text="Step-by-Step Position Setup", padding=10)
        setup_frame.pack(fill="x", pady=5)
        
        self.setup_buttons = {}
        steps = [
            "1. Server Menu Button",
            "2. TextBox Input Area",
            "3. Fish Hub Button",
            "4. Running Man Button",
            "Game Window Focus Point"
        ]
        for step in steps:
            btn = ttk.Button(setup_frame, text=step, command=lambda s=step: self.start_single_setup(s))
            btn.pack(fill="x", pady=2)
            self.setup_buttons[step] = btn

        # Global Settings Frame
        global_frame = ttk.LabelFrame(s_main, text="Settings & Notifications", padding=10)
        global_frame.pack(fill="x", pady=10)

        self.var_topmost = tk.BooleanVar(value=self.config.get("always_on_top", True))
        ttk.Checkbutton(global_frame, text="Window Always on Top", variable=self.var_topmost, command=self.toggle_topmost).pack(anchor="w", pady=2)

        ttk.Label(global_frame, text="Discord Webhook:").pack(anchor="w")
        self.entry_discord = ttk.Entry(global_frame, show="*")
        self.entry_discord.insert(0, self.config.get("discord_webhook", ""))
        self.entry_discord.pack(fill="x", pady=2)

        ttk.Label(global_frame, text="Macro Toggle Key (F1):").pack(anchor="w")
        self.entry_macro_key = ttk.Entry(global_frame)
        self.entry_macro_key.insert(0, self.config.get("macro_hotkey", "f1"))
        self.entry_macro_key.pack(fill="x", pady=2)

        ttk.Button(s_main, text="SAVE ALL SETTINGS", command=self.manual_save).pack(fill="x", pady=10)

        # --- TAB 2: AUTO RECONNECT ---
        r_main = self.tab_reconnect
        ttk.Label(r_main, text="Auto Reconnect Monitor", font=("Segoe UI", 12, "bold")).pack(pady=(0, 5))

        # Status
        status_rec = ttk.Frame(r_main)
        status_rec.pack(fill="x", pady=5)
        ttk.Label(status_rec, text="Status: ").pack(side="left")
        self.lbl_status_rec = ttk.Label(status_rec, text="Inactive", foreground="red", font=("Segoe UI", 9, "bold"))
        self.lbl_status_rec.pack(side="left")

        # Config
        ttk.Label(r_main, text="Scan Interval (seconds):").pack(anchor="w")
        self.entry_interval = ttk.Entry(r_main)
        self.entry_interval.insert(0, str(self.config["reconnect_interval"]))
        self.entry_interval.pack(fill="x", pady=5)

        # Image Selection
        img_frame = ttk.LabelFrame(r_main, text="Recognition Image", padding=5)
        img_frame.pack(fill="x", pady=5)
        
        self.lbl_img_path = ttk.Label(img_frame, text=f"File: {os.path.basename(self.config['reconnect_image'])}", font=("Segoe UI", 8, "italic"))
        self.lbl_img_path.pack(side="left", padx=5)
        ttk.Button(img_frame, text="Select", command=self.select_reconnect_image, width=10).pack(side="right")
        
        # Controls
        self.btn_rec_toggle = ttk.Button(r_main, text="START MONITORING", command=self.toggle_reconnect)
        self.btn_rec_toggle.pack(fill="x", pady=10)
        ttk.Button(r_main, text="DEBUG: Test Image Detection", command=self.debug_test_detection).pack(fill="x")

        # --- TAB 3: SERVER JOINER ---
        j_main = self.tab_joiner
        ttk.Label(j_main, text="Private Server Auto-Joiner", font=("Segoe UI", 12, "bold")).pack(pady=(0, 5))

        status_join = ttk.Frame(j_main)
        status_join.pack(fill="x", pady=5)
        ttk.Label(status_join, text="Status: ").pack(side="left")
        self.lbl_status_join = ttk.Label(status_join, text="Inactive", foreground="red", font=("Segoe UI", 9, "bold"))
        self.lbl_status_join.pack(side="left")

        ttk.Label(j_main, text="Private Server Code:").pack(anchor="w")
        self.entry_server_code = ttk.Entry(j_main)
        self.entry_server_code.insert(0, self.config["server_code"])
        self.entry_server_code.pack(fill="x", pady=5)

        ttk.Label(j_main, text="Wait After Reconnect (s):").pack(anchor="w")
        self.entry_wait_time = ttk.Entry(j_main)
        self.entry_wait_time.insert(0, str(self.config["wait_after_reconnect"]))
        self.entry_wait_time.pack(fill="x", pady=5)

        self.btn_join_toggle = ttk.Button(j_main, text="START AUTO JOINER", command=self.toggle_joiner)
        self.btn_join_toggle.pack(fill="x", pady=10)
        ttk.Button(j_main, text="TEST JOIN NOW (F8)", command=self.test_join_manual).pack(fill="x")

        # --- TAB 4: COORDINATE NAVIGATION ---
        c_main = self.tab_coord
        ttk.Label(c_main, text="Coordinate Navigation (OCR)", font=("Segoe UI", 12, "bold")).pack(pady=(0, 5))

        status_ocr = ttk.Frame(c_main)
        status_ocr.pack(fill="x", pady=5)
        ttk.Label(status_ocr, text="Status: ").pack(side="left")
        self.lbl_status_ocr = ttk.Label(status_ocr, text="Inactive", foreground="red", font=("Segoe UI", 9, "bold"))
        self.lbl_status_ocr.pack(side="left")

        # Axis Config
        input_frame = ttk.Frame(c_main)
        input_frame.pack(fill="x", pady=5)
        for i, axis in enumerate(["X", "Y", "Z"]):
            ttk.Label(input_frame, text=f"{axis}:").grid(row=0, column=i*2, sticky="w")
            entry = ttk.Entry(input_frame, width=8)
            entry.insert(0, str(self.config.get(f"target_{axis.lower()}", 0.0)))
            entry.grid(row=0, column=i*2+1, padx=2)
            setattr(self, f"entry_target_{axis.lower()}", entry)

        ttk.Button(c_main, text="Select Screen Region", command=self.select_ocr_region).pack(fill="x", pady=2)
        ttk.Button(c_main, text="Test OCR Reading", command=self.test_ocr).pack(fill="x", pady=2)
        ttk.Button(c_main, text="Set Current Coords as Target", command=self.set_current_as_target).pack(fill="x", pady=2)
        
        self.btn_ocr_toggle = ttk.Button(c_main, text="START NAVIGATION", command=self.toggle_ocr_nav)
        self.btn_ocr_toggle.pack(fill="x", pady=(5, 10))

        # Direction Mapping (Sub-Frame)
        map_frame = ttk.LabelFrame(c_main, text="Direction Mapping Controls", padding=5)
        map_frame.pack(fill="x", pady=5)
        map_inner = ttk.Frame(map_frame)
        map_inner.pack(fill="x")

        ttk.Label(map_inner, text="W:").grid(row=0, column=0, padx=2)
        self.combo_w_map = ttk.Combobox(map_inner, values=["x+", "x-", "z+", "z-"], width=5, state="readonly")
        self.combo_w_map.set(self.config["nav_mapping"].get("w", "z-"))
        self.combo_w_map.grid(row=0, column=1, padx=5)

        ttk.Label(map_inner, text="D:").grid(row=0, column=2, padx=2)
        self.combo_d_map = ttk.Combobox(map_inner, values=["x+", "x-", "z+", "z-"], width=5, state="readonly")
        self.combo_d_map.set(self.config["nav_mapping"].get("d", "x+"))
        self.combo_d_map.grid(row=0, column=3, padx=5)

        ttk.Button(map_frame, text="Set GPO Defaults", command=self.set_gpo_defaults).pack(fill="x", pady=5)

        # --- SHARED ACTIVITY LOGS (BOTTOM AREA) ---
        log_frame = ttk.LabelFrame(self, text="Shared Activity Logs (Sync Across All Tabs)", padding=10)
        log_frame.pack(fill="both", side="bottom", expand=True, padx=5, pady=5)

        self.log_text = tk.Text(log_frame, height=8, state='disabled', font=("Consolas", 9))
        self.log_text.pack(side="left", fill="both", expand=True)
        ttk.Scrollbar(log_frame, command=self.log_text.yview).pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=lambda *args: None)

        self.log("GPO auto-reconnect Initialized (Sync Logs Active).")

        self.log("GPO auto-reconnect Initialized.")

    def log(self, message):
        """Append a timestamped message to the UI log."""
        timestamp = time.strftime("[%H:%M:%S]")
        full_msg = f"{timestamp} {message}\n"
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, full_msg)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        print(full_msg, end='')

    def send_discord(self, message):
        """Sends an asynchronous Discord webhook notification."""
        webhook = self.config.get("discord_webhook")
        if not webhook: return
        def _send():
            try: requests.post(webhook, json={"content": f"**[GPO auto-reconnect]** {message}"}, timeout=5)
            except: pass
        threading.Thread(target=_send, daemon=True).start()

    def toggle_topmost(self):
        self.attributes("-topmost", self.var_topmost.get())
        self.save_config()

    def toggle_reconnect(self):
        self.reconnect_active = not self.reconnect_active
        if self.reconnect_active:
            self.save_config()
            self.btn_rec_toggle.config(text="STOP RECONNECT")
            self.lbl_status_rec.config(text="Active", foreground="green")
            self.log("Auto Reconnect: ENABLED")
        else:
            self.btn_rec_toggle.config(text="START RECONNECT")
            self.lbl_status_rec.config(text="Inactive", foreground="red")
            self.log("Auto Reconnect: DISABLED")

    def select_reconnect_image(self):
        """Allows user to browse and select a reconnect button image."""
        file_path = filedialog.askopenfilename(
            title="Select Reconnect Button Image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp")]
        )
        if file_path:
            # Optionally copy to local directory to keep it organized
            filename = os.path.basename(file_path)
            local_path = os.path.join(os.getcwd(), filename)
            
            try:
                if os.path.abspath(file_path) != os.path.abspath(local_path):
                    shutil.copy2(file_path, local_path)
                
                self.config["reconnect_image"] = filename
                self.lbl_img_path.config(text=f"Image: {filename}")
                self.save_config()
                self.log(f"New reconnect image set: {filename}")
            except Exception as e:
                self.log(f"Error saving image: {e}")
                messagebox.showerror("Error", f"Could not copy image: {e}")

    def debug_test_detection(self):
        """Manually trigger a scan and report findings."""
        img_path = self.config.get("reconnect_image", "reconnect_button.png")
        if not os.path.exists(img_path):
            self.log(f"Debug: Image '{img_path}' not found!")
            return
            
        conf = float(self.config.get("confidence", 0.7))
        self.log(f"Debug: Scanning for '{img_path}' (conf: {conf})...")
        
        try:
            # Try once with standard
            loc = pyautogui.locateOnScreen(img_path, confidence=conf)
            if loc:
                self.log(f"Debug: SUCCESS! Pattern found at {loc}")
                # Visual feedback
                center = pyautogui.center(loc)
                pyautogui.moveTo(center.x, center.y)
            else:
                self.log("Debug: Failed to detect. Try lowering Confidence or taking a cleaner screenshot.")
                # Fallback check - can it even see the screen?
                try:
                    pyautogui.screenshot("debug_view.png")
                    self.log("Debug: Screenshot saved as 'debug_view.png' - check if it's black/weird.")
                except: pass
        except Exception as e:
            self.log(f"Debug Error: {e}")

    def toggle_joiner(self):
        self.joiner_active = not self.joiner_active
        if self.joiner_active:
            self.save_config()
            self.btn_join_toggle.config(text="STOP AUTO JOIN")
            self.lbl_status_join.config(text="Waiting for reconnect", foreground="green")
            self.log("Auto Joiner: ENABLED")
        else:
            self.btn_join_toggle.config(text="START AUTO JOIN")
            self.lbl_status_join.config(text="Inactive", foreground="red")
            self.log("Auto Joiner: DISABLED")

    def test_join_manual(self):
        self.log("Manual Join Test Triggered...")
        threading.Thread(target=self.run_join_sequence, daemon=True).start()

    def toggle_ocr_nav(self):
        self.ocr_nav_active = not self.ocr_nav_active
        if self.ocr_nav_active:
            self.save_config()
            self.btn_ocr_toggle.config(text="STOP NAVIGATION")
            self.lbl_status_ocr.config(text="Calibrating...", foreground="orange")
            self.log("Navigation: ENABLED (Auto-Calibration in progress...)")
            self.needs_calibration = True
        else:
            self.btn_ocr_toggle.config(text="START NAVIGATION")
            self.lbl_status_ocr.config(text="Inactive", foreground="red")
            self.log("Navigation: DISABLED")
            self.needs_calibration = False
            for key in ['w', 's', 'a', 'd', 'space']: pydirectinput.keyUp(key)

    def select_ocr_region(self):
        SelectionOverlay(self.set_ocr_region_callback)

    def set_ocr_region_callback(self, region):
        self.config["ocr_region"] = region
        self.save_config()
        self.log(f"OCR Region locked: {region}")

    def get_current_coords(self):
        """Reads and parses coordinates from the defined screen region."""
        try:
            region = self.config.get("ocr_region")
            if not region: return None, None, None
            
            # Capture and preprocess
            screenshot = pyautogui.screenshot(region=region).convert('L')
            text = pytesseract.image_to_string(screenshot).lower()
            
            float_pattern = r'(-?\d+\.\d+|-?\d+)'
            x_m = re.search(r'x\s*[:\s]*[:\s]+' + float_pattern, text)
            y_m = re.search(r'y\s*[:\s]*[:\s]+' + float_pattern, text)
            z_m = re.search(r'z\s*[:\s]*[:\s]+' + float_pattern, text)
            
            if x_m and y_m and z_m:
                val = (float(x_m.group(1)), float(y_m.group(1)), float(z_m.group(1)))
            else:
                nums = re.findall(float_pattern, text)
                if len(nums) >= 3: val = (float(nums[0]), float(nums[1]), float(nums[2]))
                else: return None, None, None

            # Moving average smoothing
            self._coord_history.append(val)
            if len(self._coord_history) > 3: self._coord_history.pop(0)
            avg = [sum(axis)/len(self._coord_history) for axis in zip(*self._coord_history)]
            return avg[0], avg[1], avg[2]
        except:
            return None, None, None

    def test_ocr(self):
        x, y, z = self.get_current_coords()
        if x is not None:
            self.log(f"OCR Success: X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
        else:
            self.log("OCR Failed: Coordinate format not found.")

    def set_current_as_target(self):
        x, y, z = self.get_current_coords()
        if x is not None:
            for axis, val in zip(['x', 'y', 'z'], [x, y, z]):
                entry = getattr(self, f"entry_target_{axis}")
                entry.delete(0, tk.END)
                entry.insert(0, f"{val:.2f}")
            self.log(f"New Target Locked: X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
        else:
            self.log("Set Target Failed: Could not read coordinates.")

    def set_gpo_defaults(self):
        """Forces mapping to the most common GPO configuration."""
        self.combo_w_map.set("z-")
        self.combo_d_map.set("x+")
        self.config["nav_mapping"] = {"w": "z-", "d": "x+", "space": "y+"}
        self.save_config()
        self.log("Navigation mapping set to GPO Defaults: W=z-, D=x+")

    def calibration_thread(self):
        """Learns key mappings with double-verification for maximum accuracy."""
        time.sleep(3)
        if not self.config.get("ocr_region"):
            self.log("Calibration Failed: Select OCR region first.")
            return False

        def get_stable():
            samples = []
            for _ in range(5):
                c = self.get_current_coords()
                if c[0] is not None: samples.append(c)
                time.sleep(0.3)
            if not samples: return [None, None, None]
            return [round(sorted(axis)[len(axis)//2], 2) for axis in zip(*samples)]

        def get_direction(p1, p2):
            if p1[0] is None or p2[0] is None: return None
            dx, dz = p2[0] - p1[0], p2[2] - p1[2]
            if abs(dx) > abs(dz) and abs(dx) > 0.1: return f"x{'+' if dx > 0 else '-'}"
            if abs(dz) > abs(dx) and abs(dz) > 0.1: return f"z{'+' if dz > 0 else '-'}"
            return None

        mapping = {"space": "y+"}
        cal_pulse = 0.1
        
        # --- Verified Test for W ---
        while True:
            self.log("Calibration: Testing 'W' - Round 1...")
            p_start = get_stable()
            pydirectinput.keyDown('w'); time.sleep(cal_pulse); pydirectinput.keyUp('w')
            time.sleep(1.0)
            p_mid = get_stable()
            dir1 = get_direction(p_start, p_mid)
            
            self.log(f"Round 1 -> {dir1 if dir1 else 'No Movement'}")
            
            self.log("Calibration: Testing 'W' - Round 2...")
            pydirectinput.keyDown('w'); time.sleep(cal_pulse); pydirectinput.keyUp('w')
            time.sleep(1.0)
            p_final = get_stable()
            dir2 = get_direction(p_mid, p_final)
            
            self.log(f"Round 2 -> {dir2 if dir2 else 'No Movement'}")

            if dir1 and dir1 == dir2:
                mapping["w"] = dir1
                self.after(0, lambda d=dir1: self.combo_w_map.set(d))
                self.log(f"-> Verified W mapping: {dir1}")
                break
            self.log("Calibration Warning: 'W' inconsistent or no movement. Retrying in 2s...")
            time.sleep(2)

        # --- Verified Test for D ---
        while True:
            self.log("Calibration: Testing 'D' - Round 1...")
            p_start = get_stable()
            pydirectinput.keyDown('d'); time.sleep(cal_pulse); pydirectinput.keyUp('d')
            time.sleep(1.0)
            p_mid = get_stable()
            dir1 = get_direction(p_start, p_mid)
            
            self.log(f"Round 1 -> {dir1 if dir1 else 'No Movement'}")
            
            self.log("Calibration: Testing 'D' - Round 2...")
            pydirectinput.keyDown('d'); time.sleep(cal_pulse); pydirectinput.keyUp('d')
            time.sleep(1.0)
            p_final = get_stable()
            dir2 = get_direction(p_mid, p_final)
            
            self.log(f"Round 2 -> {dir2 if dir2 else 'No Movement'}")

            if dir1 and dir1 == dir2:
                # Basic conflict resolution: if D tries to map to the same axis as W with the same dir
                if dir1 == mapping.get("w"):
                    self.log(f"Conflict: D wants {dir1} but W is already {mapping['w']}. Adjusting...")
                    # This logic is simpler handled after verification
                
                mapping["d"] = dir1
                self.after(0, lambda d=dir1: self.combo_d_map.set(d))
                self.log(f"-> Verified D mapping: {dir1}")
                break
            self.log("Calibration Warning: 'D' inconsistent or no movement. Retrying in 2s...")
            time.sleep(2)

        # Final check for mapping logic (X/Z should be different)
        if mapping.get("w") and mapping.get("d"):
            if mapping["w"][0] == mapping["d"][0]:
                self.log("Mapping conflict (Both mapped to same axis). Resetting to fallback logic.")
                if mapping["w"][0] == 'z': mapping["d"] = "x+"
                else: mapping["d"] = "z-"
                self.after(0, lambda: self.combo_d_map.set(mapping["d"]))

        self.config["nav_mapping"] = mapping
        self.save_config()
        self.log(f"Calibration SUCCESS! Mapping: {mapping}")
        return True

    def start_single_setup(self, step_name):
        self.setup_buttons[step_name].config(text=f"PRESS 'S' AT CURSOR")
        threading.Thread(target=self.single_setup_thread, args=(step_name,), daemon=True).start()

    def single_setup_thread(self, step_name):
        while True:
            if keyboard.is_pressed('s'):
                pos = pyautogui.position()
                saved_pos = {}
                if os.path.exists(POS_FILE):
                    try: 
                        with open(POS_FILE, "r") as f: saved_pos = json.load(f)
                    except: pass
                saved_pos[step_name] = {"x": pos[0], "y": pos[1]}
                with open(POS_FILE, "w") as f: json.dump(saved_pos, f)
                
                self.log(f"Position Saved: {step_name}")
                self.after(0, lambda: self.setup_buttons[step_name].config(text="[ ✓ SAVED ]"))
                time.sleep(2)
                self.after(0, lambda: self.setup_buttons[step_name].config(text=step_name))
                break
            time.sleep(0.05)

    def run_join_sequence(self):
        """Automated sequence to join a private server."""
        if not os.path.exists(POS_FILE):
             messagebox.showwarning("Incomplete Setup", "Please set button positions first!")
             return
             
        try:
            with open(POS_FILE, "r") as f: pos = json.load(f)
            req = ["1. Server Menu Button", "2. TextBox Input Area", "3. Fish Hub Button", "4. Running Man Button"]
            for r in req:
                if r not in pos:
                    self.log(f"Error: {r} position missing.")
                    return

            self.log("Started Joining Sequence...")
            pydirectinput.PAUSE = 0.1
            
            # 1. Click Menu
            m = pos["1. Server Menu Button"]
            pydirectinput.moveTo(int(m['x']), int(m['y']))
            time.sleep(1)
            pydirectinput.moveRel(2, 2); pydirectinput.moveRel(-2, -2)
            for _ in range(3):
                pydirectinput.click()
                time.sleep(0.3)
            self.log("Clicked Menu (3x). Waiting 8s...")
            time.sleep(8)
            
            # 2. Focus TextBox
            b = pos["2. TextBox Input Area"]
            pydirectinput.moveTo(int(b['x']), int(b['y']))
            time.sleep(1)
            pydirectinput.moveRel(2, 2); pydirectinput.moveRel(-2, -2)
            for _ in range(3):
                pydirectinput.click()
                time.sleep(0.3)
            self.log("Focused TextBox (3x). Waiting 8s...")
            time.sleep(8)
            
            # 3. Enter Server Code
            server_code = self.entry_server_code.get()
            self.log(f"Entering Code: {server_code}...")
            
            # Clear textbox first (Ctrl+A + Backspace)
            pydirectinput.click() # One more click to be sure
            pydirectinput.keyDown('ctrl')
            pydirectinput.press('a')
            pydirectinput.keyUp('ctrl')
            pydirectinput.press('backspace')
            time.sleep(0.5)

            # Type with delay
            for char in server_code:
                pyautogui.write(char)
                time.sleep(0.1)
                
            time.sleep(1)
            pydirectinput.press('enter')
            self.log("Code submitted. Waiting 8s...")
            time.sleep(8)
            
            # 4. Click Fish Hub
            fh = pos["3. Fish Hub Button"]
            pydirectinput.moveTo(int(fh['x']), int(fh['y']))
            time.sleep(1)
            pydirectinput.moveRel(2, 2); pydirectinput.moveRel(-2, -2)
            for _ in range(3):
                pydirectinput.click()
                time.sleep(0.3)
            
            self.log("Join Sequence complete. Loading map (45s)...")
            time.sleep(45) # Wait for world load

            # 5. Pre-Navigation Adjustments
            if "4. Running Man Button" in pos:
                rm = pos["4. Running Man Button"]
                self.log("Activating Running Man (3x)...")
                pydirectinput.moveTo(int(rm['x']), int(rm['y']))
                time.sleep(1)
                pydirectinput.moveRel(2, 2); pydirectinput.moveRel(-2, -2)
                for _ in range(3):
                    pydirectinput.click()
                    time.sleep(0.3)
                time.sleep(2)

            self.log("Running Post-Join Key Sequence...")
            pydirectinput.keyDown('shift')
            time.sleep(1)
            pydirectinput.press('f3'); time.sleep(8)
            for i in range(4):
                pydirectinput.press('1'); time.sleep(2)
            pydirectinput.keyUp('shift')
            
            self.log("Re-activating Navigation Module...")
            if not self.ocr_nav_active: self.after(0, self.toggle_ocr_nav)

        except Exception as e:
            self.log(f"Join Sequence Failed: {e}")

    def main_loop(self):
        """Global monitoring loop for Reconnect and Navigation logic."""
        time.sleep(2)
        last_rec_check = 0
        while True:
            if not hasattr(self, 'reconnect_active'):
                time.sleep(0.5); continue
            
            now = time.time()
            # 1. Reconnect Logic
            interval = int(self.entry_interval.get() if self.entry_interval.get().isdigit() else 10)
            if self.reconnect_active and (now - last_rec_check >= interval):
                last_rec_check = now
                img_path = self.config.get("reconnect_image", "reconnect_button.png")
                
                if not os.path.exists(img_path):
                    self.log(f"Scanner Warning: Image file '{img_path}' NOT FOUND in folder!")
                    continue
                
                try:
                    # self.log(f"Scanning for {img_path}...") # Debug log
                    conf = float(self.config.get("confidence", 0.7))
                    loc = pyautogui.locateOnScreen(img_path, confidence=conf)
                    if loc:
                            # Stop current macro and Alert
                            m_key = self.config.get("macro_hotkey", "f1")
                            pydirectinput.press(m_key)
                            self.log(f"DISCONNECT DETECTED! Stopping external macro via {m_key.upper()} and notifying Discord.")
                            self.send_discord("⚠️ **Detected Disconnection!** Stopping external macro and attempting to reconnect...")
                            
                            center = pyautogui.center(loc)
                            pydirectinput.moveTo(int(center.x), int(center.y))
                            time.sleep(0.5)
                            pydirectinput.moveRel(2, 2); pydirectinput.moveRel(-2, -2)
                            for _ in range(2):
                                pydirectinput.click()
                                time.sleep(0.3)
                            self.log("Reconnect button clicked (2x).")
                            
                            if self.joiner_active:
                                wait = int(self.entry_wait_time.get())
                                self.log(f"Waiting {wait}s to trigger Join Sequence...")
                                time.sleep(wait)
                                # Focus window
                                fx, fy = -1, -1
                                if os.path.exists(POS_FILE):
                                    with open(POS_FILE, "r") as f:
                                        p = json.load(f).get("Game Window Focus Point", {})
                                        fx, fy = p.get('x', -1), p.get('y', -1)
                                if fx != -1: pydirectinput.moveTo(fx, fy)
                                else: pydirectinput.moveTo(pyautogui.size()[0]//2, pyautogui.size()[1]//2)
                                pydirectinput.mouseDown(); time.sleep(5); pydirectinput.mouseUp()
                                self.run_join_sequence()
                except: pass

            # 2. Navigation Logic
            if self.ocr_nav_active:
                if self.needs_calibration:
                    success = self.calibration_thread()
                    self.needs_calibration = False
                    if not success:
                        self.log("Navigation Error: Calibration failed. Stopping Navigation.")
                        self.after(0, self.toggle_ocr_nav)
                        continue
                    if self.ocr_nav_active:
                        self.lbl_status_ocr.config(text="Active", foreground="green")
                        self.log("Navigation: Map learning complete. Heading to Target.")
                    continue

                cx, cy, cz = self.get_current_coords()
                if cx is not None:
                    # Stability Check
                    if len(self._coord_history) >= 3:
                        last = self._coord_history[-1]
                        if abs(last[0] - cx) > 0.2 or abs(last[2] - cz) > 0.2:
                            time.sleep(0.2); continue

                    tx, ty, tz = self.safe_get_float(self.entry_target_x), self.safe_get_float(self.entry_target_y), self.safe_get_float(self.entry_target_z)
                    thres, pulse = 0.7, 0.015
                    mapping = self.config.get("nav_mapping", {"w": "z-", "d": "x+", "space": "y+"})
                    
                    # Movement Logic based on Learned Mapping
                    # Find which keys move Z and X
                    z_key, z_dir = None, None
                    x_key, x_dir = None, None
                    
                    for k, m in mapping.items():
                        if m.startswith('z'):
                            z_key, z_dir = k, m[1:]
                        elif m.startswith('x'):
                            x_key, x_dir = k, m[1:]
                    
                    # Determine Z action
                    z_act = None
                    if z_key and abs(cz - tz) > thres:
                        # if mapping is z-, it means pressing z_key decreases Z
                        # so if current Z > target Z, we need to decrease Z -> press z_key
                        if z_dir == '-': z_act = z_key if cz > tz else ('s' if z_key == 'w' else 'w')
                        else: z_act = z_key if cz < tz else ('s' if z_key == 'w' else 'w')
                        
                    # Determine X action
                    x_act = None
                    if x_key and abs(cx - tx) > thres:
                        if x_dir == '-': x_act = x_key if cx > tx else ('a' if x_key == 'd' else 'd')
                        else: x_act = x_key if cx < tx else ('a' if x_key == 'd' else 'd')

                    # Anti-Drown
                    if cy < 0:
                        keys = ['space']
                        if abs(cz-tz) > thres: keys.append(z_act)
                        if abs(cx-tx) > thres: keys.append(x_act)
                        for k in keys: pydirectinput.keyDown(k)
                        time.sleep(0.3)
                        for k in keys: pydirectinput.keyUp(k)
                        continue

                    # Y Navigation (Ascend only)
                    need_up = (cy < ty and mapping.get("space") == "y+") or (cy > ty and mapping.get("space") == "y-")
                    if abs(cy - ty) > 0.7 and need_up:
                        pydirectinput.press('space')
                    # Normal Navigation
                    elif z_act or x_act:
                        act = z_act or x_act
                        
                        # Anti-Oscillation Logic
                        self._move_history.append(act)
                        if len(self._move_history) > 6: self._move_history.pop(0)
                        
                        if len(self._move_history) >= 4:
                            h = self._move_history
                            # Check for W-S or A-D alternating pattern
                            is_ws = all(h[i] in ['w', 's'] for i in range(-4, 0)) and h[-1] != h[-2] and h[-2] != h[-3]
                            is_ad = all(h[i] in ['a', 'd'] for i in range(-4, 0)) and h[-1] != h[-2] and h[-2] != h[-3]
                            
                            if is_ws or is_ad:
                                self.log("Stuck detected (Oscillation)! Nudging...")
                                nudge_key = random.choice(['w', 'a', 's', 'd'])
                                pydirectinput.keyDown(nudge_key)
                                time.sleep(0.4)
                                pydirectinput.keyUp(nudge_key)
                                self._move_history = [] # Reset history
                                continue

                        pydirectinput.keyDown(act); time.sleep(pulse); pydirectinput.keyUp(act)
                    else:
                        self.log(f"Destination Reached: X={cx:.2f}, Z={cz:.2f}")
                        m_key = self.config.get("macro_hotkey", "f1")
                        pydirectinput.press(m_key)
                        self.log(f"Restarting external macro via {m_key.upper()}.")
                        self.send_discord(f"✅ **Destination Reached!** (X:{cx:.2f}, Z:{cz:.2f}). External macro started.")
                        self.toggle_ocr_nav()

            if keyboard.is_pressed('f8'):
                self.run_join_sequence()
                time.sleep(2)
            time.sleep(0.1)

if __name__ == "__main__":
    app = SCGMreconnect()
    app.mainloop()
