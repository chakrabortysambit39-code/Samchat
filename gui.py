"""
gui.py
customtkinter desktop UI for Jarvis, wired to the real Assistant
(commands.py + ai.py + memory.py + speech.py). Includes a mic button,
an optional always-listening mode, reminder pop-ups, and a small
settings panel — all driven by the same Assistant used from the CLI.
"""
import threading
import time
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

import memory
import reminders
import screen
import settings
import speech
import voice
import webcam
from assistant import Assistant


class JarvisGUI:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.assistant_name = settings.get("assistant_name", "Jarvis")
        self.assistant = Assistant(speak_replies=settings.get("voice_enabled", True))

        self._always_listening = False
        self._listen_stop_event = threading.Event()

        self.root = ctk.CTk()
        self.root.title(f"{self.assistant_name} AI")
        self.root.geometry("1000x700")
        self.root.minsize(760, 520)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_layout()

        # Any reminder that fires — including ones re-armed from a
        # previous session — shows up in chat and gets spoken.
        reminders.set_notify_callback(self._on_reminder_fired)
        reminders.rearm_pending()

        self._greet()
        self._tick_clock()

    # ------------------------------------------------------------ layout
    def _build_layout(self):
        top = ctk.CTkFrame(self.root)
        top.pack(fill="x", padx=10, pady=(10, 0))

        ctk.CTkLabel(top, text=self.assistant_name, font=("Helvetica", 18, "bold")).pack(side="left", padx=5)
        self.clock_label = ctk.CTkLabel(top, text="", font=("Helvetica", 12), text_color="gray70")
        self.clock_label.pack(side="left", padx=10)

        ctk.CTkButton(top, text="⚙ Settings", width=90, command=self._open_settings).pack(side="right", padx=5)
        ctk.CTkButton(top, text="Help", width=60, command=lambda: self._run_async("help")).pack(side="right", padx=5)
        ctk.CTkButton(top, text="Clear", width=60, command=self._clear_chat).pack(side="right", padx=5)

        self.voice_toggle = ctk.CTkSwitch(top, text="Voice replies", command=self._toggle_voice)
        if settings.get("voice_enabled", True):
            self.voice_toggle.select()
        self.voice_toggle.pack(side="right", padx=10)

        self.chat = ctk.CTkTextbox(self.root, wrap="word", font=("Helvetica", 13))
        self.chat.pack(fill="both", expand=True, padx=10, pady=10)
        self.chat.configure(state="disabled")

        bottom = ctk.CTkFrame(self.root)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self.entry = ctk.CTkEntry(bottom, placeholder_text="Type a message, e.g. 'weather in Pune', or 'help'")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry.bind("<Return>", lambda e: self.send())

        ctk.CTkButton(bottom, text="Send", width=80, command=self.send).pack(side="left", padx=(0, 5))

        self.mic_button = ctk.CTkButton(bottom, text="🎤", width=44, command=self._listen_once)
        self.mic_button.pack(side="left", padx=(0, 5))

        self.always_listen_toggle = ctk.CTkSwitch(bottom, text="Always listening", command=self._toggle_always_listen)
        self.always_listen_toggle.pack(side="left", padx=(0, 5))

        self.webcam_button = ctk.CTkButton(bottom, text="📷", width=44, command=self._use_webcam)
        self.webcam_button.pack(side="left", padx=(0, 5))
        if not webcam.is_available():
            self.webcam_button.configure(state="disabled")

        self.screen_button = ctk.CTkButton(bottom, text="🖥", width=44, command=self._use_screen)
        self.screen_button.pack(side="left", padx=(0, 5))
        if not screen.is_available():
            self.screen_button.configure(state="disabled")

        self.upload_button = ctk.CTkButton(bottom, text="📎", width=44, command=self._upload_image)
        self.upload_button.pack(side="left")

        if not voice.is_available():
            self.mic_button.configure(state="disabled")
            self.always_listen_toggle.configure(state="disabled")
        if not speech.is_available():
            self.voice_toggle.configure(state="disabled")

    # ------------------------------------------------------------ helpers
    def _append(self, speaker: str, text: str):
        stamp = datetime.now().strftime("%H:%M")
        self.chat.configure(state="normal")
        self.chat.insert("end", f"[{stamp}] {speaker}: {text}\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _greet(self):
        name = settings.get("user_name", "there")
        self._append(self.assistant_name, f"Hi {name}, I'm online. Type 'help' to see everything "
                                            f"I can do, or just ask me something.")

    def _tick_clock(self):
        self.clock_label.configure(text=datetime.now().strftime("%A, %d %b · %H:%M"))
        self.root.after(1000, self._tick_clock)

    def _clear_chat(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        memory.clear_history()
        self._greet()

    def _toggle_voice(self):
        enabled = bool(self.voice_toggle.get())
        settings.set("voice_enabled", enabled)
        self.assistant.speak_replies = enabled

    # -------------------------------------------------------- reminders
    def _on_reminder_fired(self, reminder: dict):
        """Called from a background timer thread — must hop back onto the
        GUI thread via root.after before touching any widget."""
        def show():
            message = f"⏰ Reminder: {reminder['text']}"
            self._append(self.assistant_name, message)
            speech.say(message)
            messagebox.showinfo(self.assistant_name, message)
        self.root.after(0, show)

    # -------------------------------------------------------- settings
    def _open_settings(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Settings")
        win.geometry("360x260")
        win.transient(self.root)

        cfg = settings.get_all()

        ctk.CTkLabel(win, text="Your name").pack(anchor="w", padx=15, pady=(15, 0))
        name_entry = ctk.CTkEntry(win)
        name_entry.insert(0, cfg.get("user_name", ""))
        name_entry.pack(fill="x", padx=15)

        ctk.CTkLabel(win, text="Default city").pack(anchor="w", padx=15, pady=(10, 0))
        city_entry = ctk.CTkEntry(win)
        city_entry.insert(0, cfg.get("city", ""))
        city_entry.pack(fill="x", padx=15)

        ctk.CTkLabel(win, text="Assistant name").pack(anchor="w", padx=15, pady=(10, 0))
        assistant_entry = ctk.CTkEntry(win)
        assistant_entry.insert(0, cfg.get("assistant_name", "Jarvis"))
        assistant_entry.pack(fill="x", padx=15)

        def save_and_close():
            settings.set_many(
                user_name=name_entry.get().strip() or "there",
                city=city_entry.get().strip() or "Pune",
                assistant_name=assistant_entry.get().strip() or "Jarvis",
            )
            win.destroy()

        ctk.CTkButton(win, text="Save", command=save_and_close).pack(pady=20)

    # -------------------------------------------------------------- text
    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._append("You", text)
        self._run_async(text)

    def _run_async(self, text: str):
        def worker():
            response = self.assistant.process(text)
            self.root.after(0, lambda: self._append(self.assistant_name, response))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------- voice
    def _listen_once(self):
        self.mic_button.configure(state="disabled", text="…")

        def worker():
            heard = voice.listen()
            self.root.after(0, self._after_listen, heard)

        threading.Thread(target=worker, daemon=True).start()

    def _after_listen(self, heard: str):
        self.mic_button.configure(state="normal", text="🎤")
        if heard:
            self._append("You", heard)
            self._run_async(heard)
        else:
            self._append(self.assistant_name, "I didn't catch that.")

    # ------------------------------------------------------------ vision
    def _use_webcam(self):
        self._append("You", "[webcam snapshot]")
        self.webcam_button.configure(state="disabled")

        def worker():
            frame = webcam.capture_frame()
            if frame is None:
                response = "I couldn't get a frame from the webcam (no camera, or it's in use elsewhere)."
                memory.add_turn("assistant", response)
            else:
                response = self.assistant.process_image(frame, source="webcam snapshot")
            self.root.after(0, lambda: self._append(self.assistant_name, response))
            self.root.after(0, lambda: self.webcam_button.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _use_screen(self):
        self._append("You", "[screenshot]")
        self.screen_button.configure(state="disabled")

        def worker():
            frame = screen.capture_screen()
            if frame is None:
                response = "I couldn't capture the screen on this machine."
                memory.add_turn("assistant", response)
            else:
                response = self.assistant.process_image(frame, source="screenshot")
            self.root.after(0, lambda: self._append(self.assistant_name, response))
            self.root.after(0, lambda: self.screen_button.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _upload_image(self):
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.gif *.webp"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            self._append(self.assistant_name, f"I couldn't read that file: {e}")
            return

        self._append("You", f"[uploaded {path.split('/')[-1].split(chr(92))[-1]}]")
        self.upload_button.configure(state="disabled")

        def worker():
            response = self.assistant.process_image(image_bytes, source="uploaded image")
            self.root.after(0, lambda: self._append(self.assistant_name, response))
            self.root.after(0, lambda: self.upload_button.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_always_listen(self):
        self._always_listening = bool(self.always_listen_toggle.get())
        if self._always_listening:
            self._listen_stop_event.clear()
            self.mic_button.configure(state="disabled")
            threading.Thread(target=self._always_listen_loop, daemon=True).start()
        else:
            self._listen_stop_event.set()
            self.mic_button.configure(state="normal")

    def _always_listen_loop(self):
        """Keeps calling voice.listen() with short timeouts until toggled
        off, so it can react to the stop event promptly instead of
        blocking on a single long listen() call."""
        while not self._listen_stop_event.is_set():
            heard = voice.listen(timeout=3, phrase_time_limit=8)
            if heard and not self._listen_stop_event.is_set():
                self.root.after(0, self._append, "You", heard)
                self.root.after(0, lambda h=heard: self._run_async(h))
            time.sleep(0.2)

    # --------------------------------------------------------------- run
    def _on_close(self):
        self._listen_stop_event.set()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
