import tkinter
import tkinter.messagebox
import customtkinter
import time
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import threading
import psutil
import subprocess
import threading
import time
import json
import requests
import re
from pynput import keyboard, mouse
import time
import threading
import tkinter as tk  # Required for StringVar, IntVar, etc.
import GPUtil
import os
import sys
import winreg
import customtkinter
import tkinter as tk
import requests
import time
import os
import sys

def on_closing():
    # Terminate the command if running
    if main_thread.command_thread and main_thread.command_thread.is_running():
        main_thread.stop()

    # Exit the program
    print("Closing the application. Terminating the script.")
    sys.exit()
dir = os.path.abspath(os.path.dirname(__file__))

SRB_Miner = os.path.join(dir, "SRBMiner-MULTI.exe")
settings_dir = os.path.join(dir, "settings.json")
icon_dir = os.path.join(dir, "icon.ico")

last_activity_time = time.time()

customtkinter.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
customtkinter.set_default_color_theme("green")  # Themes: "blue" (standard), "green", "dark-blue"

class Status:
    COMPUTING = "Status: computing"
    STOPPED = "Status: stopped"
    NO_COMPUTING_KEY = "Missing computing key (settings)"
    INVALID_COMPUTING_KEY = "Invalid computing key (settings)"
    SERVER_DOWN = "The computing4charity server is down!"
    OUTDATED = "Outdated client, please install a newer version."
    INVALID_GPU = "Your GPU does not have enough VRAM"
status = Status.STOPPED

def check_gpu():
    gpus = GPUtil.getGPUs()
    for gpu in gpus:
        return gpu.memoryTotal // 1000 > 4

if not check_gpu():
    status = Status.INVALID_GPU

class CommandThread(threading.Thread):
    def __init__(self, command):
        super().__init__()
        self.command = command
        self.process = None

    def run(self):
        global status, hashrate
        print(f"Started running command: {self.command}")
        self.process = subprocess.Popen(
            self.command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,  # Ensures output is decoded to strings
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        try:
            status = Status.COMPUTING
            for line in iter(self.process.stdout.readline, ''):
                match = re.search(r"Total:\s*([0-9]*\.[0-9]+)\s*(kH/s|MH/s)", line)

                if match:
                    hashrate = f"{float(match.group(1))} {match.group(2)}"

            stdout, stderr = self.process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            print("Process timed out.")
            self.stop_command()

    def stop_command(self):
        global status
        if self.process:
            print(f"Attempting to terminate the command (PID: {self.process.pid}).")
            self.process.terminate()
            
            try:
                status = Status.STOPPED
                stdout, stderr = self.process.communicate(timeout=5)
                if stderr:
                    print(f"Command error during termination: {stderr.decode()}")
            except subprocess.TimeoutExpired:
                print("Process did not terminate in time, attempting to force kill it.")
                self.force_kill()

    def force_kill(self):
        if self.process:
            pid = self.process.pid
            try:
                p = psutil.Process(pid)
                print(f"Attempting to kill process with PID: {pid}")
                p.terminate()
                p.wait(timeout=5)
                if p.is_running():
                    print("Process did not terminate, force killing it.")
                    p.kill()
            except psutil.NoSuchProcess:
                print(f"Process with PID {pid} already terminated.")
            except psutil.AccessDenied:
                print(f"Access denied while trying to terminate process {pid}.")
            except psutil.TimeoutExpired:
                print("Timeout expired while waiting for the process to terminate.")

    def is_running(self):
        return self.is_alive()
    
class MainThread:
    def __init__(self):
        self.command_thread = None

    def start(self, command):
        if self.command_thread is None or not self.command_thread.is_alive():
            self.command_thread = CommandThread(command)
            print("Main thread is starting.")
            self.command_thread.start()
        else:
            print("The command is already running.")

    def stop(self):
        if self.command_thread and self.command_thread.is_running():
            print("Main thread is stopping the command.")
            self.command_thread.stop_command()
        else:
            print("The command is not running.")
    
    def restart(self, command):
        self.stop()
        self.start(command)

def on_keyboard_event(key):
    global last_activity_time
    last_activity_time = time.time()

def on_mouse_event(x, y):
    global last_activity_time
    last_activity_time = time.time()

main_thread = MainThread()
settings = {}
latest_response = {}
hashrate = "Hashrate: ~"
balance = 0
class Settings:
    def load():
        global settings, settings_dir
        with open(settings_dir, "r") as f:
            settings = json.load(f)
    def save():
        global settings, settings_dir
        with open(settings_dir, 'w') as f:
            json.dump(settings, f)
Settings.load()
server = settings["server"]

def convert(input):
    factors = {
        "H/s": 1,
        "kH/s": 1_000,
        "MH/s": 1_000_000,
        "GH/s": 1_000_000_000,
    }
    match = re.match(r"([0-9]*\.?[0-9]+)\s*(\w+/s)", input)
    
    if match:
        number = float(match.group(1))
        unit = match.group(2)
        
        if unit in factors:
            return number * factors[unit]
        else:
            return None
    else:
        return None

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.title("Computing4Charity")
        self.geometry("400x400")
        self.resizable(False, False)
        self.iconbitmap(icon_dir)

        # Bind the close event to the on_closing function
        self.protocol("WM_DELETE_WINDOW", on_closing)

        # Configure main window grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Setup Tabview
        self.tabview = customtkinter.CTkTabview(self, width=250)
        self.tabview.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self._setup_tabs()

        # Initialize settings
        self.idle_computing_var = tk.IntVar(value=settings["idle_computing"])
        self.gpu_slider_var = tk.IntVar(value=settings["gpu_usage"])

        # Dashboard Page Widgets
        self._setup_dashboard_widgets()

        # Settings Page Widgets
        self._setup_settings_widgets()

        # Start live updates
        self.update_dashboard_status()
        self.server_loop()

    def _setup_tabs(self):
        self.tabview.add("Dashboard")
        self.tabview.add("Settings")
        for tab in ["Dashboard", "Settings"]:
            self.tabview.tab(tab).grid_columnconfigure(0, weight=1)

    def _setup_dashboard_widgets(self):
        dashboard_tab = self.tabview.tab("Dashboard")

        self.status = customtkinter.CTkLabel(dashboard_tab, text="Status: Idle", font=("Arial", 14))
        self.status.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="nsew")

        self.start_button = customtkinter.CTkButton(dashboard_tab, text="Start", command=self.start_event)
        self.start_button.grid(row=1, column=0, padx=20, pady=(20, 10), sticky="nsew")

        self.stop_button = customtkinter.CTkButton(dashboard_tab, text="Stop", command=self.stop_event)
        self.stop_button.grid(row=1, column=1, padx=20, pady=(20, 10), sticky="nsew")

        self.points = customtkinter.CTkLabel(dashboard_tab, text="~ points", font=("Arial", 18, "bold"))
        self.points.grid(row=2, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="nsew")

        self.hashrate = customtkinter.CTkLabel(dashboard_tab, text="Hashrate: ~", font=("Arial", 14))
        self.hashrate.grid(row=3, column=0, padx=20, pady=(10, 10), sticky="nsew")

        self.projected = customtkinter.CTkLabel(dashboard_tab, text="24 Hour: ~", font=("Arial", 14))
        self.projected.grid(row=3, column=1, padx=20, pady=(10, 10), sticky="nsew")

    def _setup_settings_widgets(self):
        settings_tab = self.tabview.tab("Settings")

        self.idle_computing_checkbox = customtkinter.CTkCheckBox(
            settings_tab,
            text="Idle Computing",
            command=self.idle_computing_event,
            variable=self.idle_computing_var
        )

        self.idle_computing_checkbox.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")

        self.gpu_label = customtkinter.CTkLabel(settings_tab, text="GPU Usage")
        self.gpu_label.grid(row=1, column=0, padx=20, pady=(10, 10), sticky="nsew")

        self.gpu_slider = customtkinter.CTkSlider(
            settings_tab, from_=0, to=100, number_of_steps=100,
            command=self.gpu_slider_event, variable=self.gpu_slider_var
        )
        self.gpu_slider.grid(row=2, column=0, padx=20, pady=(10, 10), sticky="nsew")

        self.set_computing_key_button = customtkinter.CTkButton(
            settings_tab, text="Set Computing Key", command=self.open_computing_key_dialog
        )
        self.set_computing_key_button.grid(row=3, column=0, padx=20, pady=(10, 20), sticky="nsew")

    def open_computing_key_dialog(self):
        global status
        Settings.load()
        dialog = customtkinter.CTkInputDialog(text="Enter your Computing Key", title="Set Computing Key")
        result = dialog.get_input()
        if settings["computing_key"] != result:
            settings["computing_key"] = result
            Settings.save()
            status = Status.STOPPED

    def start_event(self):
        global status, latest_response, settings, SRB_Miner
        Settings.load()
        if not settings["computing_key"]:
            status = Status.NO_COMPUTING_KEY
            return

        try:
            response = requests.get(f"{server}/mining", json={"computing_key": settings["computing_key"]}).json()
            latest_response = response
            if response["success"]:
                main_thread.start(
                    f'"{SRB_Miner}" -a {response["algorithm"]} -o {response["stratum"]}'
                    f" -u {response['address']}.{settings['computing_key']} -p x -i {int((settings['gpu_usage'] // 100) * 12)}"
                )
            else:
                status = Status.INVALID_COMPUTING_KEY
        except requests.exceptions.ConnectionError:
            status = Status.SERVER_DOWN

    def stop_event(self):
        global hashrate
        hashrate = "Hashrate: ~"
        main_thread.stop()

    def idle_computing_event(self):
        Settings.load()
        updated_status = self.idle_computing_checkbox.get()
        if settings["idle_computing"] != updated_status:
            settings["idle_computing"] = updated_status
            Settings.save()
    

    def gpu_slider_event(self, value):
        Settings.load()
        if settings["gpu_usage"] != value:
            settings["gpu_usage"] = value
            Settings.save()

    def update_dashboard_status(self):
        global status, hashrate, balance, last_activity_time
        Settings.load()
        self.status.configure(text=status)
        self.hashrate.configure(text=hashrate)
        self.points.configure(text=f"{balance} points")
        rate = convert(hashrate)
        if rate:
            self.projected.configure(text=f"24 Hour: {rate // 1_000_000 * 30} points")
        else:
            self.projected.configure(text="24 Hour: ~")

        if not settings["computing_key"]:
            status = Status.NO_COMPUTING_KEY

        idle_time = time.time() - last_activity_time
        if settings["idle_computing"]:
            if idle_time >= 60:
                self.start_event()
            else:
                self.stop_event()


        self.after(1000, self.update_dashboard_status)

    def server_loop(self):
        global status, balance
        Settings.load()
        try:
            response = requests.get(f"{server}/mining", json={"computing_key": settings["computing_key"]}).json()
            if status == Status.SERVER_DOWN:
                status = Status.STOPPED
            if response["success"]:
                balance = response["balance"]
                if response != latest_response and not latest_response == {}:
                    self.stop_event()
                    self.start_event()

                if response["version"] != settings["version"]:
                    self.stop_event()
                    status = Status.OUTDATED
            else:
                Status.INVALID_COMPUTING_KEY
        except requests.exceptions.ConnectionError:
            status = Status.SERVER_DOWN
        else:
            if status == Status.SERVER_DOWN:
                status = Status.STOPPED

        self.after(1000, self.server_loop)


if __name__ == "__main__":
    keyboard_listener = keyboard.Listener(on_press=on_keyboard_event)
    mouse_listener = mouse.Listener(on_move=on_mouse_event, on_click=lambda x, y, button, pressed: on_mouse_event(x, y))

    keyboard_listener.start()
    mouse_listener.start()
    app = App()
    app.mainloop()

    keyboard_listener.join()
    mouse_listener.join()
