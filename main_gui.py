#no mistral integrated and no parallelization checkboxes
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from whisper_offline import transcribe_audio, kill_whisper, set_abort_flag
from output_manager import clear_lecture_checkpoints, prepare_lecture_folder,load_last_checkpoint,save_checkpoint_offset,compute_resume_start_sec
from pydub import AudioSegment
import json



# Constants
CTX_SIZE = 4096
tokens_per_word = 1.3
# Store info about the current lecture/audio for popup continuation
CURRENT_LECTURE_INFO = {}


WPM_PRESETS = {
    "Casual Lecture (~120 WPM)": 120,
    "Dense Technical Lecture (~180 WPM)": 180
}

def estimate_tokens(wpm, minutes):
    return int(wpm * minutes * tokens_per_word)

class LectureStudioGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Lecture Studio 2.0")
        self.root.geometry("500x600")
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        # Default settings
        self.tokens = 500
        self.chunk_mode = tk.StringVar(value="dynamic")
        self.wpm = tk.IntVar(value=120)
        self.chunk_minutes = tk.IntVar(value=10)

        # Whisper/Faster-Whisper model selection (display names)
        self.whisper_model_display = tk.StringVar(value="Medium")

        # Emergency stop
        tk.Button(root, text="🛑 Emergency Stop", fg="white", bg="red", command=self.shutdown).pack(pady=5)

        # Course and lecture input
        tk.Label(root, text="📘 Course Name:").pack()
        self.course_entry = tk.Entry(root)
        self.course_entry.pack()

        tk.Label(root, text="🎙 Lecture Title:").pack()
        self.lecture_entry = tk.Entry(root)
        self.lecture_entry.pack()

        # Language selection
        tk.Label(root, text="🌐 Audio Language:").pack(pady=5)
        self.lang_var = tk.StringVar(value="Arabic")
        tk.OptionMenu(root, self.lang_var, "Arabic", "English", "Auto (Detect)").pack()

        # Audio selection
        tk.Button(root, text="🎧 Choose Lecture Audio (.mp3)", command=self.browse_audio).pack(pady=5)
        self.audio_path_label = tk.Label(root, text="No file selected", fg="gray")
        self.audio_path_label.pack()

        # Buttons
        tk.Button(root, text="⚙️ Settings", command=self.open_settings).pack(pady=5)
        tk.Button(root, text="🚀 Start Processing", command=self.run_pipeline_threaded).pack(pady=10)

        self.status_label = tk.Label(root, text="Waiting for input...", fg="blue")
        self.status_label.pack(pady=10)

        self.root.after(200,self.check_for_resume)

    def on_chunk_slider_change(self, _):
        # If a previous update is waiting, cancel it
        if hasattr(self, "_chunk_slider_update_job") and self._chunk_slider_update_job:
            self.root.after_cancel(self._chunk_slider_update_job)

        # Schedule a new update to happen after 100 ms
        self._chunk_slider_update_job = self.root.after(100, self.update_estimate)


    def open_settings(self):
        import tkinter as tk
        from tkinter import ttk, messagebox

        # --- specs for Faster-Whisper models (display names) ---
        FASTER_SPECS = {
            "tiny":   {"Params": "39M",  "RAM": "<1 GB",     "Notes": "Fastest; low accuracy on noisy Arabic"},
            "base":   {"Params": "74M",  "RAM": "1–1.5 GB",  "Notes": "Fair; more substitutions"},
            "small":  {"Params": "244M", "RAM": "2–3 GB",    "Notes": "Good; some regressions on accents/noise"},
            "medium": {"Params": "769M", "RAM": "5–7 GB",    "Notes": "Most accurate in this group"},
        }

        def show_model_info(display_name: str, parent):
            key = (display_name or "").strip().lower()
            if key in FASTER_SPECS:
                s = FASTER_SPECS[key]
                messagebox.showinfo(
                    f"Faster-Whisper Model: {display_name}",
                    "Params: {Params}\nRAM: {RAM}\nNotes: {Notes}".format(**s),
                    parent=parent
                )
            else:
                messagebox.showwarning("Model Info", "Please select a valid model.", parent=parent)

        # Settings UI
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.transient(self.root)
        win.grab_set()  # modal

        max_threads = max(1, os.cpu_count() or 4)
        if not hasattr(self, "asr_threads"):
            self.asr_threads = tk.IntVar(value=min(4, max_threads))


        # WPM Preset
        tk.Label(win, text="WPM Preset:").pack(anchor='w', pady=2)
        wpm_frame = tk.Frame(win); wpm_frame.pack(anchor='w')
        wpm_cb = ttk.Combobox(wpm_frame, textvariable=self.wpm,
                            values=list(WPM_PRESETS.values()), state="readonly", width=18)
        wpm_cb.pack(side="left", padx=(0, 5))
        wpm_cb.bind("<<ComboboxSelected>>", lambda e: self.update_estimate())

        tk.Button(
            wpm_frame, text="ℹ", width=2,
            command=lambda: messagebox.showinfo(
                "WPM Presets",
                "WPM presets represent typical speaking speeds.\n"
                "- Casual: ~120 WPM\n- Dense technical: ~180 WPM\n\n"
                "Adjust depending on your lecture.",
                parent=win
            )
        ).pack(side="left", padx=6)

        # Model selection
        tk.Label(win, text="Model:").pack(anchor='w', pady=6)
        model_row = tk.Frame(win); model_row.pack(anchor='w', fill='x')
        model_menu = tk.OptionMenu(model_row, self.whisper_model_display, "Medium", "Small", "Base", "Tiny")
        model_menu.pack(side="left")
        tk.Button(model_row, text="ℹ", width=2,
                command=lambda: show_model_info(self.whisper_model_display.get(), win)
                ).pack(side="left", padx=6)

        # Threads
        tk.Label(win, text="ASR Threads:").pack(anchor='w', pady=(10, 2))
        th_row = tk.Frame(win); th_row.pack(anchor='w', fill='x')
        tk.Spinbox(th_row, from_=1, to=max_threads, width=6, textvariable=self.asr_threads).pack(side="left")
        tk.Button(
            th_row, text="ℹ", width=2,
            command=lambda: messagebox.showinfo(
                "Threads",
                f"Number of CPU threads to use (1–{max_threads}).\n\n"
                "Higher = faster, but too high may cause contention on laptops.\n"
                "A safe rule is 50–100% of your CPU cores.",
                parent=win
            )
        ).pack(side="left", padx=6)

        # Chunk Slider
        self.chunk_slider = tk.Scale(
            win, from_=1, to=30, orient="horizontal", label="Chunk Length (minutes)",
            variable=self.chunk_minutes, command=lambda _: self.update_estimate()
        )
        self.chunk_slider.pack(fill="x")
        self.chunk_slider.config(command=self.on_chunk_slider_change)



        # Token Estimate + Warnings
        self.token_label = tk.Label(win, text="~0 tokens"); self.token_label.pack(anchor='w')
        self.warning_label = tk.Label(win, text="", fg="red"); self.warning_label.pack(anchor='w')
        self.chunk_count_label = tk.Label(win, text="Estimated chunks: ?")
        self.chunk_count_label.pack(anchor='w', pady=2)

        win.update_idletasks()
        needed_h = max(300, win.winfo_reqheight() + 12)
        needed_w = max(420, win.winfo_reqwidth() + 12)
        win.minsize(needed_w, needed_h)
        win.geometry(f"{needed_w}x{needed_h}")

        self.update_estimate()

    def update_estimate(self, *args):
        self.tokens = estimate_tokens(self.wpm.get(), self.chunk_minutes.get())

        # Number of chunks = ceil(total duration / chunk length)
        if hasattr(self, "audio_duration_sec") and self.audio_duration_sec > 0:
            chunk_length_sec = self.chunk_minutes.get() * 60
            num_chunks = -(-self.audio_duration_sec // chunk_length_sec)  # ceiling division
        else:
            num_chunks = 0

        # Update labels
        self.token_label.config(text=f"~{self.tokens} tokens")
        self.chunk_count_label.config(text=f"≈ {int(num_chunks)} chunks")  # new label

        if self.tokens > CTX_SIZE:
            self.token_label.config(fg="red")
            self.warning_label.config(text="⚠️ Chunk may be truncated!", fg="red")
        else:
            self.token_label.config(fg="black")
            self.warning_label.config(text="", fg="black")


    def browse_audio(self):
        path = filedialog.askopenfilename(filetypes=[("MP3 files", "*.mp3")])
        self.audio_path = path if path else None
        self.audio_path_label.config(text=os.path.basename(path) if path else "No file selected")

        if self.audio_path:
            # Read duration ONCE, store in instance variable
            audio = AudioSegment.from_file(self.audio_path)
            self.audio_duration_sec = len(audio) / 1000.0
        else:
            self.audio_duration_sec = 0

    def update_status(self, msg, color="black"):
        self.status_label.config(text=msg, fg=color)
        self.root.update_idletasks()

    def check_for_resume(self):
        """Scan checkpoint file on startup and prompt user if unfinished work is found."""
        checkpoint = load_last_checkpoint()
        if not checkpoint:
            return  # nothing to resume

        course = checkpoint.get("course", "?")
        lecture = checkpoint.get("lecture", "?")
        audio_path = checkpoint.get("audio_path", None)
        last_offset = checkpoint.get("last_offset_sec", 0.0)

        resume = messagebox.askyesno(
            "Resume Found",
            f"Unfinished transcription detected:\n\n"
            f"📘 Course: {course}\n🎙 Lecture: {lecture}\n"
            f"⏱ Last position: {last_offset:.1f} sec\n\n"
            f"Do you want to resume from this point?"
        )

        if resume:
            # --- 1. Forcefully populate GUI fields ---
            self.course_entry.delete(0, tk.END)
            self.course_entry.insert(0, course)

            self.lecture_entry.delete(0, tk.END)
            self.lecture_entry.insert(0, lecture)

            self.audio_path = audio_path
            self.audio_path_label.config(text=os.path.basename(audio_path) if audio_path else "No file selected")

            # --- 2. Save CURRENT_LECTURE_INFO globally ---
            global CURRENT_LECTURE_INFO
            CURRENT_LECTURE_INFO = {
                "course": course,
                "lecture": lecture,
                "audio_path": audio_path,
                "lang_mode": checkpoint.get("lang", self.lang_var.get()),
                "resume_offset_sec": last_offset,
            }

            # --- 3. Directly launch pipeline from checkpoint ---
            # Launch in a separate thread to avoid freezing GUI
            threading.Thread(
                target=self.run_pipeline,
                kwargs={
                    "checkpoint": checkpoint,
                    "course": course,
                    "lecture": lecture,
                    "audio_path": audio_path,
                    "lang": checkpoint.get("lang", self.lang_var.get()),
                    "restart": False,
                    "resume_offset": last_offset
                },
                daemon=True  # ensures the thread exits if GUI is closed
            ).start()



        else:
            # User chose not to resume; optionally clear GUI for fresh entry
            self.course_entry.delete(0, tk.END)
            self.lecture_entry.delete(0, tk.END)
            self.audio_path = None
            self.audio_path_label.config(text="No file selected")


    def resume_from_checkpoint(self, checkpoint):
        """Resume transcription from last checkpoint."""
        self.update_status("🔄 Resuming from checkpoint...", "green")
        try:
            # Call transcribe_audio again with same params
            self.run_pipeline()
        except Exception as e:
            messagebox.showerror("Resume Failed", str(e))

    def restart_lecture(self, course, lecture):
        """Clear checkpoint for given lecture and restart from beginning."""
        from output_manager import _write_checkpoint_list, _read_checkpoint_list
        items = _read_checkpoint_list()
        items = [i for i in items if not (i.get("course") == course and i.get("lecture") == lecture)]
        _write_checkpoint_list(items)  # overwrite with filtered list
        messagebox.showinfo("Restart", f"Checkpoint cleared for {course}/{lecture}. Please start again.")




    def run_pipeline_threaded(self, checkpoint=None, **kwargs):
        threading.Thread(
            target=self.run_pipeline,
            kwargs=kwargs if checkpoint is None else {**kwargs, "checkpoint": checkpoint},
            daemon=True
        ).start()


    def run_pipeline(self, checkpoint=None, *, course=None, lecture=None, audio_path=None, lang=None, restart=False, resume_offset=None):
        import traceback
        try:
            # --- 1. Decide between normal / resume / restart ---
            if checkpoint:
                # Override parameters from checkpoint if not explicitly given
                course = checkpoint.get("course", course)
                lecture = checkpoint.get("lecture", lecture)
                audio_path = checkpoint.get("audio_path", audio_path)
                lang_mode = checkpoint.get("lang", lang or "Auto (Detect)")
                restart = checkpoint.get("restart", restart)
                last_offset = checkpoint.get("last_offset_sec", 0.0)
                threads_loaded = checkpoint.get("threads",4)
                chunk_token_loaded = checkpoint.get("chunk_token",500)
                
                # If resume_offset was not passed, use checkpoint
                resume_offset = resume_offset if resume_offset is not None else last_offset

                if not (course and lecture and audio_path):
                    messagebox.showerror("Checkpoint Error", "Missing info in checkpoint.")
                    return

                if restart:
                    self.update_status(f"🔄 Restarting {course}/{lecture} from scratch...", "green")
                else:
                    self.update_status(f"▶ Resuming {course}/{lecture} from {resume_offset:.1f}s...", "green")

            else:  # Normal new lecture mode
                course = course or self.course_entry.get().strip()
                lecture = lecture or self.lecture_entry.get().strip()
                audio_path = audio_path or getattr(self, "audio_path", None)
                lang_mode = lang or self.lang_var.get()
                resume_offset = resume_offset or 0.0

                if not course or not lecture or not audio_path:
                    messagebox.showwarning(
                        "Missing Info",
                        "Please provide course name, lecture title, and audio file."
                    )
                    return

            # --- 2. Prepare lecture folder ---
            lecture_dir = prepare_lecture_folder(course, lecture)
            transcript_path = os.path.join(lecture_dir, "final_transcript.txt")

            # --- 3. Configure Whisper model ---
            model_map = {"Medium": "medium", "Small": "small", "Base": "base", "Tiny": "tiny"}
            selected_display = self.whisper_model_display.get()
            selected_model = model_map.get(selected_display, "medium")

            try:
                threads = max(1, int(self.asr_threads.get()))
            except Exception:
                threads = 1

            self.update_status(f"🎧 Transcribing audio with Faster-Whisper ({selected_model})...", "green")

            kwargs = {
                "lang_mode": lang_mode,
                "model": selected_model,
                "chunk_token": chunk_token_loaded if checkpoint else self.tokens,
                "gui_callback": lambda msg: self.update_status(msg, "green"),
                "fw_device": "cpu",
                "fw_compute_type": "int8",
                "fw_beam_size": 1,
                "fw_vad": False,
                "threads": threads_loaded if checkpoint else threads,
                "course": course,
                "lecture": lecture,
                "resume_offset": resume_offset  # <-- Pass the offset to Whisper
            }

            if self.chunk_mode.get().lower() == "fixed":
                try:
                    kwargs["min_spacing_sec"] = max(30, int(self.chunk_minutes.get()) * 60)
                except Exception:
                    kwargs["min_spacing_sec"] = 60

            # --- 4. Run transcription ---
            try:
                ar_text, en_text, transcript_metadata_json = transcribe_audio(audio_path, **kwargs)
            except Exception as e:
                if getattr(self, "debug_mode_var", tk.BooleanVar(value=False)).get():
                    traceback.print_exc()
                messagebox.showerror("Transcription Error", str(e))
                return

            self.update_status("💾 Transcription complete.", "black")

            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(ar_text)

            clear_lecture_checkpoints(course=course,lecture=lecture)

            messagebox.showinfo("Done", "Lecture processed successfully.")

        except Exception as e:
            traceback.print_exc()


    def shutdown(self):
        print("[SHUTDOWN] User requested shutdown.")
        try:
            set_abort_flag()
            kill_whisper()
            with open("shutdown_log.txt", "a", encoding="utf-8") as log:
                log.write("[SHUTDOWN] Triggered by user. All processes terminated.\n")
            os._exit(0)
        except Exception as e:
            print("[ERROR] During forced shutdown:", e)
            self.root.quit()


if __name__ == "__main__":
    root = tk.Tk()
    app = LectureStudioGUI(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.shutdown()
