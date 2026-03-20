import os
import threading
import tkinter as tk
import time
import json
import collections
import traceback
from tkinter import filedialog, messagebox, ttk

from pydub import AudioSegment

# --- Internal Module Imports ---
from whisper_offline import transcribe_audio, kill_whisper, set_abort_flag
from output_manager import (
    clear_lecture_checkpoints, 
    prepare_lecture_folder, 
    load_last_checkpoint, 
    compute_resume_start_sec, 
    BASE_DIR, 
    sanitize_filename
)

from config import (
    load_settings, save_settings,
    load_queue_checkpoint, save_queue_checkpoint, clear_queue_checkpoint,
    estimate_tokens, WPM_PRESETS, CTX_SIZE
)
from library_browser import LibraryBrowser

def _get_run_suffix(course: str, lecture: str, overwrite: bool) -> str:
    """Calculates the suffix for duplicate transcript filenames (e.g. '_2', '_3')"""
    lecture_dir = os.path.join(BASE_DIR, sanitize_filename(course), sanitize_filename(lecture))
    if overwrite or not os.path.exists(os.path.join(lecture_dir, "transcript.txt")):
        return ""
    
    i = 2
    while os.path.exists(os.path.join(lecture_dir, f"transcript_{i}.txt")):
        i += 1
    return f"_{i}"

# ─── Main GUI Application ─────────────────────────────────────────────────────
class LectureStudioGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Lecture Studio 2.0")
        self.root.geometry("500x770")
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        # --- Load Settings ---
        config = load_settings()
        self.wpm = tk.IntVar(value=config["wpm"])
        self.chunk_minutes = tk.IntVar(value=config["chunk_minutes"])
        self.tokens = estimate_tokens(self.wpm.get(), self.chunk_minutes.get())  
        self.is_fixed_chunk_mode = tk.BooleanVar(value=config.get("is_fixed_chunk_mode", True))
        self.desired_chunks = tk.IntVar(value=config["desired_chunks"])
        self.beam_size = tk.IntVar(value=config["beam_size"])
        self.whisper_model_display = tk.StringVar(value=config["whisper_model_display"])
        self.asr_threads = tk.IntVar(value=config["asr_threads"])
        self.lazy_youtube_download = tk.BooleanVar(value=config["lazy_youtube_download"])
        self.overwrite_transcripts = tk.BooleanVar(value=config["overwrite_transcripts"])
        self.use_gpu = tk.BooleanVar(value=config.get("use_gpu", False))
        self.audio_duration_sec = 0.0

        # --- Queue State ---
        self._queue = collections.deque()
        self._queue_running = False

        self._build_ui()

        # Startup Check: Ask for Queue Restore FIRST
        # The Queue logic now checks for any single-item resumes dynamically
        self.root.after(200, self.check_for_queue_restore)

    def _build_ui(self):
        """Constructs the main interface components."""
        tk.Button(self.root, text="🛑 Emergency Stop", fg="white", bg="red", command=self.shutdown).pack(pady=5)

        tk.Label(self.root, text="📘 Course Name:").pack()
        self.course_entry = tk.Entry(self.root)
        self.course_entry.pack()

        tk.Label(self.root, text="🎙 Lecture Title:").pack()
        self.lecture_entry = tk.Entry(self.root)
        self.lecture_entry.pack()

        tk.Label(self.root, text="🌐 Audio Language:").pack(pady=5)
        self.lang_var = tk.StringVar(value="Arabic")
        tk.OptionMenu(self.root, self.lang_var, "Arabic", "English", "Auto (Detect)").pack()

        tk.Button(self.root, text="🎧 Choose Lecture Audio (.mp3 / .m4a)", command=self.browse_audio).pack(pady=5)
        self.audio_path_label = tk.Label(self.root, text="No file selected", fg="gray")
        self.audio_path_label.pack()

        tk.Button(self.root, text="⚙️ Settings", command=self.open_settings).pack(pady=5)
        tk.Button(self.root, text="▶️ YouTube → Transcribe", command=self.open_youtube_popup).pack(pady=2)
        tk.Button(self.root, text="📚 Open Lecture Library", command=self.open_library).pack(pady=(2, 5))

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=4)
        tk.Button(btn_frame, text="➕ Add to Queue", command=self.add_to_queue).pack(side="left", padx=6)
        tk.Button(btn_frame, text="🚀 Start Processing", command=self.run_pipeline_threaded).pack(side="left", padx=6)

        self.current_process_var = tk.StringVar(value="Current Process: None")
        tk.Label(self.root, textvariable=self.current_process_var, fg="#b30000", font=("", 10, "bold")).pack(pady=(5, 0))

        tk.Label(self.root, text="📋 Queue:", anchor="w").pack(fill="x", padx=10)
        queue_frame = tk.Frame(self.root)
        queue_frame.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        
        scrollbar = tk.Scrollbar(queue_frame, orient="vertical")
        self.queue_listbox = tk.Listbox(queue_frame, height=6, yscrollcommand=scrollbar.set, selectmode="single", activestyle="dotbox")
        scrollbar.config(command=self.queue_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.queue_listbox.pack(side="left", fill="both", expand=True)

        queue_btn_frame = tk.Frame(self.root)
        queue_btn_frame.pack(pady=2)
        tk.Button(queue_btn_frame, text="▶ Start Queue", command=self.start_queue, bg="#1a7a1a", fg="white").pack(side="left", padx=6)
        tk.Button(queue_btn_frame, text="✏ Edit Selected", command=self.edit_selected_queue_item).pack(side="left", padx=6)
        tk.Button(queue_btn_frame, text="✖ Remove Selected", command=self.remove_selected_from_queue).pack(side="left", padx=6)
        tk.Button(queue_btn_frame, text="🗑 Clear Queue", command=self.clear_queue).pack(side="left", padx=6)

        self.status_label = tk.Label(self.root, text="Waiting for input...", fg="blue", wraplength=460)
        self.status_label.pack(pady=8)

    # ─── UI Updaters ──────────────────────────────────────────────────────────
    def open_library(self):
        LibraryBrowser(self.root)
        
    def update_current_process(self, process_name: str):
        self.root.after(0, lambda: self.current_process_var.set(f"Current Process: {process_name}"))

    def update_status(self, msg: str, color: str = "black"):
        def _safe_update():
            self.status_label.config(text=msg, fg=color)
            self.root.update_idletasks()
        self.root.after(0, _safe_update)

    # ─── Queue Management ─────────────────────────────────────────────────────
    def add_to_queue(self):
        course = self.course_entry.get().strip()
        lecture = self.lecture_entry.get().strip()
        audio_path = getattr(self, "audio_path", None)

        if not course or not lecture or not audio_path:
            messagebox.showwarning("Missing Info", "Please fill in Course Name, Lecture Title, and choose an audio file.")
            return

        self._queue.append({
            "course": course,
            "lecture": lecture,
            "audio_path": audio_path,
            "lang": self.lang_var.get(),
            "chunk_token": self.tokens,
            "fixed_chunks": self.desired_chunks.get() if self.is_fixed_chunk_mode.get() else None,
            "lazy_download": False,
            "status": "waiting"
        })
        save_queue_checkpoint(list(self._queue))
        self._refresh_queue_listbox()

        self.course_entry.delete(0, tk.END)
        self.lecture_entry.delete(0, tk.END)
        self.audio_path = None
        self.audio_path_label.config(text="No file selected")
        self.update_status(f"✅ Added [{len(self._queue)}]: {course} / {lecture}", "green")

    def remove_selected_from_queue(self):
        sel = self.queue_listbox.curselection()
        if not sel:
            return
        lst = list(self._queue)
        removed = lst.pop(sel[0])
        self._queue = collections.deque(lst)
        save_queue_checkpoint(list(self._queue))
        self._refresh_queue_listbox()
        self.update_status(f"Removed: {removed['course']} / {removed['lecture']}", "gray")

    def clear_queue(self):
        if not self._queue:
            return
        if messagebox.askyesno("Clear Queue", "Remove all items from the queue?"):
            self._queue.clear()
            save_queue_checkpoint([])
            self._refresh_queue_listbox()
            self.update_status("Queue cleared.", "gray")

    def edit_selected_queue_item(self):
        sel = self.queue_listbox.curselection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a queue item to edit.")
            return
            
        idx = sel[0]
        lst = list(self._queue)
        item = lst[idx]

        win = tk.Toplevel(self.root)
        win.title(f"Edit Queue Item #{idx + 1}")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        pad = {"padx": 12, "pady": 4}

        tk.Label(win, text="📘 Course Name:").grid(row=0, column=0, sticky="w", **pad)
        course_var = tk.StringVar(value=item["course"])
        tk.Entry(win, textvariable=course_var, width=36).grid(row=0, column=1, **pad)

        tk.Label(win, text="🎙 Lecture Title:").grid(row=1, column=0, sticky="w", **pad)
        lecture_var = tk.StringVar(value=item["lecture"])
        tk.Entry(win, textvariable=lecture_var, width=36).grid(row=1, column=1, **pad)

        tk.Label(win, text="🌐 Language:").grid(row=2, column=0, sticky="w", **pad)
        lang_var = tk.StringVar(value=item.get("lang", "Arabic"))
        tk.OptionMenu(win, lang_var, "Arabic", "English", "Auto (Detect)").grid(row=2, column=1, sticky="w", **pad)

        tk.Label(win, text="🧠 Model:").grid(row=3, column=0, sticky="w", **pad)
        model_var = tk.StringVar(value=item.get("model", self.whisper_model_display.get()))
        tk.OptionMenu(win, model_var, "Medium", "Small", "Base", "Tiny").grid(row=3, column=1, sticky="w", **pad)

        tk.Label(win, text="🔍 Beam Size:").grid(row=4, column=0, sticky="w", **pad)
        beam_var = tk.IntVar(value=item.get("beam_size", self.beam_size.get()))
        tk.Spinbox(win, from_=1, to=5, width=6, textvariable=beam_var).grid(row=4, column=1, sticky="w", **pad)

        max_threads = max(1, os.cpu_count() or 4)
        tk.Label(win, text="⚙ Threads:").grid(row=5, column=0, sticky="w", **pad)
        threads_var = tk.IntVar(value=item.get("threads", self.asr_threads.get()))
        tk.Spinbox(win, from_=1, to=max_threads, width=6, textvariable=threads_var).grid(row=5, column=1, sticky="w", **pad)

        tk.Label(win, text="🪓 Chunks:").grid(row=6, column=0, sticky="w", **pad)
        chunk_frame = tk.Frame(win)
        chunk_frame.grid(row=6, column=1, sticky="w", **pad)
        
        use_fixed_var = tk.BooleanVar(value=(item.get("fixed_chunks") is not None))
        chunks_var = tk.IntVar(value=item.get("fixed_chunks") or self.desired_chunks.get() or 10)
        
        def _toggle_chunks():
            chunks_spinbox.config(state="normal" if use_fixed_var.get() else "disabled")
                
        tk.Checkbutton(chunk_frame, text="Fixed", variable=use_fixed_var, command=_toggle_chunks).pack(side="left")
        chunks_spinbox = tk.Spinbox(chunk_frame, from_=1, to=999, width=5, textvariable=chunks_var)
        chunks_spinbox.pack(side="left", padx=(4, 0))
        tk.Label(chunk_frame, text="(uncheck for Auto)", fg="gray", font=("", 8)).pack(side="left", padx=4)
        _toggle_chunks()

        is_youtube = item.get("youtube", False)
        audio_var  = tk.StringVar(value=item.get("audio_path", ""))
        url_var    = tk.StringVar(value=item.get("url", ""))

        if is_youtube:
            tk.Label(win, text="🔗 YouTube URL:").grid(row=7, column=0, sticky="w", **pad)
            tk.Entry(win, textvariable=url_var, width=36).grid(row=7, column=1, **pad)
            tk.Label(win, text="🎧 Audio File:").grid(row=8, column=0, sticky="w", **pad)
            tk.Label(win, textvariable=audio_var, fg="gray", width=34, anchor="w", wraplength=260).grid(row=8, column=1, sticky="w", **pad)

            redownload_status = tk.Label(win, text="", fg="blue", wraplength=280)
            redownload_status.grid(row=9, column=0, columnspan=2, **pad)

            def _redownload():
                new_url = url_var.get().strip()
                if not new_url: return
                redownload_btn.config(state="disabled", text="⏳ Downloading...")

                def _worker():
                    try:
                        from youtube_downloader import download_youtube_audio
                        path = download_youtube_audio(
                            url=new_url,
                            course=course_var.get().strip() or item["course"],
                            lecture=lecture_var.get().strip() or item["lecture"],
                            progress_callback=lambda msg: redownload_status.config(text=msg)
                        )
                        audio_var.set(path)
                        redownload_status.config(text=f"✅ Downloaded: {os.path.basename(path)}", fg="green")
                    except Exception as exc:
                        redownload_status.config(text=f"❌ {exc}", fg="red")
                    finally:
                        redownload_btn.config(state="normal", text="🔄 Re-download from URL")

                threading.Thread(target=_worker, daemon=True).start()

            redownload_btn = tk.Button(win, text="🔄 Re-download from URL", command=_redownload)
            redownload_btn.grid(row=10, column=1, sticky="w", padx=12, pady=2)
            save_row = 11

        else:
            tk.Label(win, text="🎧 Audio File:").grid(row=7, column=0, sticky="w", **pad)
            tk.Label(win, textvariable=audio_var, fg="gray", width=34, anchor="w", wraplength=260).grid(row=7, column=1, sticky="w", **pad)

            def _rebrowse():
                path = tk.filedialog.askopenfilename(filetypes=[("Audio files", "*.mp3 *.m4a"), ("MP3 files", "*.mp3"), ("M4A files", "*.m4a")])
                if path: audio_var.set(path)

            tk.Button(win, text="Browse…", command=_rebrowse).grid(row=8, column=1, sticky="w", padx=12, pady=2)
            save_row = 9

        def _save():
            new_course = course_var.get().strip()
            new_lecture = lecture_var.get().strip()
            if not new_course or not new_lecture:
                messagebox.showwarning("Invalid", "Course and Lecture cannot be empty.", parent=win)
                return
                
            updated = {
                **item,
                "course": new_course,
                "lecture": new_lecture,
                "lang": lang_var.get(),
                "model": model_var.get(),
                "beam_size": beam_var.get(),
                "threads": threads_var.get(),
                "audio_path": audio_var.get(),
                "fixed_chunks": chunks_var.get() if use_fixed_var.get() else None,
                "lazy_download": item.get("lazy_download", False),
                "status": item.get("status", "waiting")
            }
            if is_youtube:
                updated["url"] = url_var.get().strip()
                if audio_var.get() != "Pending Download...":
                    updated["lazy_download"] = False
            
            lst[idx] = updated
            self._queue = collections.deque(lst)
            save_queue_checkpoint(lst)
            self._refresh_queue_listbox()
            win.destroy()
            self.update_status(f"✅ Queue item #{idx + 1} updated.", "green")

        btn_row = tk.Frame(win)
        btn_row.grid(row=save_row, column=0, columnspan=2, pady=10)
        tk.Button(btn_row, text="💾 Save", command=_save, bg="#1a73e8", fg="white", width=10).pack(side="left", padx=8)
        tk.Button(btn_row, text="Cancel", command=win.destroy, width=10).pack(side="left", padx=8)

    def _refresh_queue_listbox(self):
        """Updates the visual queue list. 
        Uses completely safe ASCII characters to prevent rendering crashes on Windows listboxes."""
        self.queue_listbox.delete(0, tk.END)
        for i, item in enumerate(self._queue, 1):
            source = "[YT]" if item.get("youtube") else "[local]"
            status = item.get("status", "waiting")
            
            # 100% Safe text icons
            if status == "running":
                icon = "[>>]" 
            elif status == "done":
                icon = "[OK]"
            elif status == "error":
                icon = "[XX]"
            else:
                icon = "[  ]" # Empty bracket means waiting
                
            self.queue_listbox.insert(tk.END, f"{icon} {i}. {source} [{item['lang']}]  {item['course']}  /  {item['lecture']}")

    # ─── Queue Processing Execution ───────────────────────────────────────────
    def start_queue(self):
        if not self._queue:
            messagebox.showinfo("Queue Empty", "Add lectures to the queue first.")
            return
        if self._queue_running:
            messagebox.showinfo("Already Running", "The queue is already being processed.")
            return
        threading.Thread(target=self._queue_worker, daemon=True).start()

    def _queue_worker(self):
        self._queue_running = True
        total = len(self._queue)
        completed = 0

        while self._queue:
            item = self._queue[0]
            item["status"] = "running"
            completed += 1
            remaining = len(self._queue) - 1
            
            save_queue_checkpoint(list(self._queue))
            self.root.after(0, self._refresh_queue_listbox)
            
            run_suffix = _get_run_suffix(item["course"], item["lecture"], self.overwrite_transcripts.get())
            display_name = f"{item['course']} / {item['lecture']}" + (f" (Run {run_suffix.replace('_', '')})" if run_suffix else "")
            
            self.update_current_process(display_name)
            self.update_status(f"🎧 Processing {completed}/{total}: {item['course']} / {item['lecture']}  ({remaining} remaining)", "green")

            try:
                self._run_single_item(item, run_suffix)
                item["status"] = "done"
                self.root.after(0, self._refresh_queue_listbox)
                time.sleep(1.5)
                keep_going = [True]
            except Exception as exc:
                item["status"] = "error"
                self.root.after(0, self._refresh_queue_listbox)
                traceback.print_exc()
                
                keep_going = [True]
                dialog_done = threading.Event()
                def _ask():
                    keep_going[0] = messagebox.askyesno("Item Failed", f"Error on:\n{item['course']} / {item['lecture']}\n\n{exc}\n\nContinue with remaining queue?", parent=self.root)
                    dialog_done.set()
                self.root.after(0, _ask)
                dialog_done.wait()

            if not keep_going[0]:
                self._queue.clear()
                self.root.after(0, self._refresh_queue_listbox)
                break
            else:
                if self._queue:
                    self._queue.popleft()
                    save_queue_checkpoint(list(self._queue))
                    self.root.after(0, self._refresh_queue_listbox)

        self._queue_running = False
        clear_queue_checkpoint()
        self.root.after(0, self._refresh_queue_listbox)
        self.update_current_process("None")
        self.update_status(f"✅ Queue complete — {completed} lecture(s) processed.", "black")

    def _run_single_item(self, item: dict, run_suffix: str):
        """Transcribes a single queue item. Blocking."""
        course = item["course"]
        lecture = item["lecture"]
        lang_mode = item["lang"]

        if item.get("lazy_download") and item.get("youtube"):
            self.update_status(f"⬇️ Downloading YouTube video for {lecture}...", "blue")
            try:
                from youtube_downloader import download_youtube_audio
                audio_path = download_youtube_audio(
                    url=item["url"],
                    course=course,
                    lecture=lecture,
                    progress_callback=lambda msg: self.update_status(msg, "blue")
                )
                item["audio_path"] = audio_path
                item["lazy_download"] = False
            except Exception as exc:
                raise RuntimeError(f"YouTube Download Failed: {exc}")
        else:
            audio_path = item.get("audio_path")

        model_map = {"Medium": "medium", "Small": "small", "Base": "base", "Tiny": "tiny"}
        selected_model = model_map.get(item.get("model", self.whisper_model_display.get()), "medium")
        beam_size = item.get("beam_size", self.beam_size.get())
        threads = max(1, int(item.get("threads", self.asr_threads.get())))

        lecture_dir = prepare_lecture_folder(course, lecture)
        transcript_path = os.path.join(lecture_dir, f"transcript{run_suffix}.txt")

        chunk_token = item.get("chunk_token", self.tokens)
        fixed_chunks = item.get("fixed_chunks", None)
        
        # Reads the dynamic resume offset injected at startup
        resume_offset = item.get("resume_offset", 0.0)
        fresh_start = (resume_offset == 0.0)

        ar_text, _, _ = transcribe_audio(
            audio_path,
            lang_mode=lang_mode,
            model=selected_model,
            chunk_token=chunk_token,
            fixed_chunks=fixed_chunks,
            gui_callback=lambda msg: self.update_status(msg, "green"),
            fw_device=self._get_device_and_compute()[0],
            fw_compute_type=self._get_device_and_compute()[1],
            fw_beam_size=beam_size,
            fw_vad=True,
            threads=threads,
            course=course,
            lecture=lecture,
            resume_offset=resume_offset,
            fresh_start=fresh_start,
            run_suffix=run_suffix
        )

        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(ar_text)
        clear_lecture_checkpoints(course=course, lecture=lecture, run_suffix=run_suffix)


    # ─── Settings, Browse, & Restores ─────────────────────────────────────────
    def on_chunk_slider_change(self, _):
        if hasattr(self, "_chunk_slider_update_job") and self._chunk_slider_update_job:
            self.root.after_cancel(self._chunk_slider_update_job)
        self._chunk_slider_update_job = self.root.after(100, self.update_estimate)

    def open_settings(self):
        FASTER_SPECS = {
            "tiny": {"Params": "39M", "RAM": "<1 GB", "Notes": "Fastest; low accuracy on noisy Arabic"},
            "base": {"Params": "74M", "RAM": "1–1.5 GB", "Notes": "Fair; more substitutions"},
            "small": {"Params": "244M", "RAM": "2–3 GB", "Notes": "Good; some regressions on accents/noise"},
            "medium": {"Params": "769M", "RAM": "5–7 GB", "Notes": "Most accurate in this group"},
        }

        def show_model_info(display_name, parent):
            key = (display_name or "").strip().lower()
            if key in FASTER_SPECS:
                s = FASTER_SPECS[key]
                messagebox.showinfo(f"Model: {display_name}", "Params: {Params}\nRAM: {RAM}\nNotes: {Notes}".format(**s), parent=parent)
            else:
                messagebox.showwarning("Model Info", "Please select a valid model.", parent=parent)

        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.transient(self.root)
        win.grab_set()

        max_threads = max(1, os.cpu_count() or 4)

        tk.Label(win, text="WPM Preset:").pack(anchor="w", pady=2)
        wpm_frame = tk.Frame(win); wpm_frame.pack(anchor="w")
        wpm_cb = ttk.Combobox(wpm_frame, textvariable=self.wpm, values=list(WPM_PRESETS.values()), state="readonly", width=18)
        wpm_cb.pack(side="left", padx=(0, 5))
        wpm_cb.bind("<<ComboboxSelected>>", lambda e: self.update_estimate())
        tk.Button(wpm_frame, text="ℹ", width=2, command=lambda: messagebox.showinfo("WPM Presets", "Casual: ~120 WPM\nDense technical: ~180 WPM", parent=win)).pack(side="left", padx=6)

        tk.Label(win, text="Model:").pack(anchor="w", pady=6)
        model_row = tk.Frame(win); model_row.pack(anchor="w", fill="x")
        tk.OptionMenu(model_row, self.whisper_model_display, "Medium", "Small", "Base", "Tiny").pack(side="left")
        tk.Button(model_row, text="ℹ", width=2, command=lambda: show_model_info(self.whisper_model_display.get(), win)).pack(side="left", padx=6)

        tk.Label(win, text="ASR Threads:").pack(anchor="w", pady=(10, 2))
        th_row = tk.Frame(win); th_row.pack(anchor="w", fill="x")
        tk.Spinbox(th_row, from_=1, to=max_threads, width=6, textvariable=self.asr_threads).pack(side="left")
        tk.Button(th_row, text="ℹ", width=2, command=lambda: messagebox.showinfo("Threads", f"Number of CPU threads to use (1–{max_threads}).\nA safe rule is 50–100% of your CPU cores.", parent=win)).pack(side="left", padx=6)

        tk.Label(win, text="Beam Size:").pack(anchor="w", pady=(10, 2))
        beam_row = tk.Frame(win); beam_row.pack(anchor="w", fill="x")
        tk.Spinbox(beam_row, from_=1, to=5, width=6, textvariable=self.beam_size).pack(side="left")
        tk.Button(beam_row, text="ℹ", width=2, command=lambda: messagebox.showinfo("Beam Size", "Beam search width for decoding.\n1 = greedy (fastest).\nHigher = more accurate but slower.\nRecommended: 2 for Arabic lectures.", parent=win)).pack(side="left", padx=6)

        sep = tk.Frame(win, height=1, bg="lightgray"); sep.pack(fill="x", pady=(10,4))
        tk.Label(win, text="Chunking Mode:", font=("", 9, "bold")).pack(anchor="w")

        mode_frame = tk.Frame(win); mode_frame.pack(anchor="w", fill="x")
        tk.Radiobutton(mode_frame, text="Fixed number of chunks", variable=self.is_fixed_chunk_mode, value=True, command=lambda: _toggle_chunk_mode()).pack(side="left", padx=(0,12))
        tk.Radiobutton(mode_frame, text="Auto (by minutes)", variable=self.is_fixed_chunk_mode, value=False, command=lambda: _toggle_chunk_mode()).pack(side="left")

        auto_frame = tk.Frame(win)
        self.chunk_slider = tk.Scale(auto_frame, from_=1, to=30, orient="horizontal", label="Chunk Length (minutes)", variable=self.chunk_minutes, command=lambda _: self.update_estimate())
        self.chunk_slider.pack(fill="x")
        self.chunk_slider.config(command=self.on_chunk_slider_change)
        self.token_label = tk.Label(auto_frame, text="~0 tokens")
        self.token_label.pack(anchor="w")
        self.warning_label = tk.Label(auto_frame, text="", fg="red")
        self.warning_label.pack(anchor="w")
        self.chunk_count_label = tk.Label(auto_frame, text="Estimated chunks: ?")
        self.chunk_count_label.pack(anchor="w", pady=2)

        fixed_frame = tk.Frame(win)
        fix_row = tk.Frame(fixed_frame); fix_row.pack(anchor="w", pady=4)
        tk.Label(fix_row, text="Number of chunks:").pack(side="left")
        tk.Spinbox(fix_row, from_=1, to=999, width=6, textvariable=self.desired_chunks).pack(side="left", padx=6)
        tk.Button(fix_row, text="ℹ", width=2, command=lambda: messagebox.showinfo("Fixed Chunk Count", "The transcript will be split into exactly this many chunks.", parent=win)).pack(side="left")
        self.fixed_chunk_info = tk.Label(fixed_frame, text="", fg="gray")
        self.fixed_chunk_info.pack(anchor="w")
        
        sep2 = tk.Frame(win, height=1, bg="lightgray"); sep2.pack(fill="x", pady=(10,4))
        tk.Label(win, text="YouTube Settings:", font=("", 9, "bold")).pack(anchor="w")
        tk.Checkbutton(win, text="Delay YouTube download until processed in Queue", variable=self.lazy_youtube_download).pack(anchor="w", padx=12)

        sep3 = tk.Frame(win, height=1, bg="lightgray"); sep3.pack(fill="x", pady=(10,4))
        tk.Label(win, text="File Conflict Mode:", font=("", 9, "bold")).pack(anchor="w")
        
        mode_frame2 = tk.Frame(win); mode_frame2.pack(anchor="w", fill="x")
        tk.Radiobutton(mode_frame2, text="Create New (transcript_2, etc.)", variable=self.overwrite_transcripts, value=False).pack(side="left", padx=(0,12))
        tk.Radiobutton(mode_frame2, text="Overwrite Existing", variable=self.overwrite_transcripts, value=True).pack(side="left")

        # ── GPU / Device Settings ────────────────────────────────────────
        sep4 = tk.Frame(win, height=1, bg="lightgray"); sep4.pack(fill="x", pady=(10,4))
        tk.Label(win, text="Processing Device:", font=("", 9, "bold")).pack(anchor="w")

        try:
            import torch as _torch
            cuda_available = _torch.cuda.is_available()
            gpu_name = _torch.cuda.get_device_name(0) if cuda_available else None
        except Exception:
            cuda_available = False
            gpu_name = None

        gpu_row = tk.Frame(win); gpu_row.pack(anchor="w", fill="x", padx=12)
        gpu_cb = tk.Checkbutton(
            gpu_row, text="Use GPU (CUDA)",
            variable=self.use_gpu,
            state="normal" if cuda_available else "disabled"
        )
        gpu_cb.pack(side="left")
        tk.Button(gpu_row, text="ℹ", width=2,
                  command=lambda: messagebox.showinfo(
                      "GPU Mode",
                      "Enables CUDA acceleration via your NVIDIA GPU.\n\n"
                      "GPU mode uses float16 compute type for maximum speed.\n"
                      "CPU mode uses int8 compute type.\n\n"
                      "Requires: CUDA-enabled PyTorch + nvidia-cublas-cu12 + nvidia-cudnn-cu12\n\n"
                      f"GPU detected: {'✅ ' + gpu_name if cuda_available else '❌ No CUDA-capable GPU found'}",
                      parent=win)
                  ).pack(side="left", padx=6)

        if not cuda_available:
            tk.Label(gpu_row, text="(No CUDA GPU detected)", fg="gray", font=("", 8)).pack(side="left", padx=4)
        else:
            tk.Label(gpu_row, text=f"({gpu_name})", fg="green", font=("", 8)).pack(side="left", padx=4)

        def _toggle_chunk_mode():
            if self.is_fixed_chunk_mode.get():
                auto_frame.pack_forget()
                fixed_frame.pack(fill="x")
            else:
                fixed_frame.pack_forget()
                auto_frame.pack(fill="x")
            win.update_idletasks()
            win.geometry(f"{win.winfo_reqwidth()}x{win.winfo_reqheight()}")

        def _on_close():
            try:
                save_settings({
                    "wpm": self.wpm.get(),
                    "chunk_minutes": self.chunk_minutes.get(),
                    "is_fixed_chunk_mode": self.is_fixed_chunk_mode.get(),
                    "desired_chunks": self.desired_chunks.get(),
                    "beam_size": self.beam_size.get(),
                    "whisper_model_display": self.whisper_model_display.get(),
                    "asr_threads": self.asr_threads.get(),
                    "lazy_youtube_download": self.lazy_youtube_download.get(),
                    "overwrite_transcripts": self.overwrite_transcripts.get(),
                    "use_gpu": self.use_gpu.get()
                })
            except Exception as e:
                print(f"[WARNING] Error saving settings on close: {e}")
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)
        _toggle_chunk_mode()

        win.update_idletasks()
        needed_h = max(390, win.winfo_reqheight() + 12)
        needed_w = max(430, win.winfo_reqwidth() + 12)
        win.minsize(needed_w, needed_h)
        win.geometry(f"{needed_w}x{needed_h}")
        self.update_estimate()

    def _get_device_and_compute(self):
        """Returns (fw_device, fw_compute_type) based on GPU toggle and availability."""
        if self.use_gpu.get():
            try:
                import torch as _torch
                if _torch.cuda.is_available():
                    return "cuda", "float16"
            except Exception:
                pass
        return "cpu", "int8"

    def update_estimate(self, *args):
        self.tokens = estimate_tokens(self.wpm.get(), self.chunk_minutes.get())
        if hasattr(self, "audio_duration_sec") and self.audio_duration_sec > 0:
            chunk_length_sec = self.chunk_minutes.get() * 60
            num_chunks = -(-self.audio_duration_sec // chunk_length_sec)
        else:
            num_chunks = 0
        self.token_label.config(text=f"~{self.tokens} tokens")
        self.chunk_count_label.config(text=f"≈ {int(num_chunks)} chunks")
        if self.tokens > CTX_SIZE:
            self.token_label.config(fg="red")
            self.warning_label.config(text="⚠️ Chunk may be truncated!", fg="red")
        else:
            self.token_label.config(fg="black")
            self.warning_label.config(text="", fg="black")

    def browse_audio(self):
        path = filedialog.askopenfilename(filetypes=[
            ("Audio files", "*.mp3 *.m4a"),
            ("MP3 files",   "*.mp3"),
            ("M4A files",   "*.m4a"),
        ])
        self.audio_path = path if path else None
        self.audio_path_label.config(text=os.path.basename(path) if path else "No file selected")
        if self.audio_path:
            audio = AudioSegment.from_file(self.audio_path)
            self.audio_duration_sec = len(audio) / 1000.0
        else:
            self.audio_duration_sec = 0

    def check_for_queue_restore(self):
        """On startup, load the queue and inject unfinished checkpoint states directly into it."""
        saved = load_queue_checkpoint()
        if not saved:
            self.check_for_resume()  # Fallback to single-item resume check if no queue
            return
            
        has_resumes = False
        
        # Process and inject the whisper checkpoint offsets into the queue memory
        for item in saved:
            item["status"] = "waiting" # Guarantee reset to waiting status
            
            ckpt = load_last_checkpoint(course=item.get("course"), lecture=item.get("lecture"))
            if ckpt and float(ckpt.get("last_offset_sec", 0.0)) > 0:
                item["resume_offset"] = float(ckpt.get("last_offset_sec"))
                has_resumes = True
            else:
                item["resume_offset"] = 0.0

        msg = (
            f"A saved queue was found with {len(saved)} item(s):\n\n" +
            "\n".join(f"  {i+1}. [{item.get('lang','?')}]  {item.get('course','?')} / {item.get('lecture','?')}" for i, item in enumerate(saved[:5])) +
            (f"\n  ... and {len(saved)-5} more" if len(saved) > 5 else "")
        )
        
        if has_resumes:
            msg += "\n\nUnfinished transcriptions were detected within this queue. They will automatically resume from their last position when started."
            
        msg += "\n\nWould you like to restore the queue?"

        if messagebox.askyesno("Restore Queue?", msg):
            self._queue = collections.deque(saved)
            self._refresh_queue_listbox()
            self.update_status(f"✅ Queue restored — {len(saved)} item(s) ready.", "green")
        else:
            clear_queue_checkpoint()
            self.check_for_resume() # Check for a single-item standalone resume if user rejected the queue

    def check_for_resume(self):
        """Checks for a standalone resume (for manually started transcriptions not in the queue)"""
        checkpoint = load_last_checkpoint()
        if not checkpoint: return
        
        course = checkpoint.get("course", "?")
        lecture = checkpoint.get("lecture", "?")
        audio_path = checkpoint.get("audio_path", None)
        last_offset = checkpoint.get("last_offset_sec", 0.0)

        # Do not prompt if this item is ALREADY loaded into the queue system
        if any(item.get("course") == course and item.get("lecture") == lecture for item in self._queue):
            return

        resume = messagebox.askyesno(
            "Resume Found",
            f"Unfinished transcription detected:\n\n📘 Course: {course}\n🎙 Lecture: {lecture}\n⏱ Last position: {last_offset:.1f} sec\n\nDo you want to resume from this point?"
        )
        
        if resume:
            self.course_entry.delete(0, tk.END)
            self.course_entry.insert(0, course)
            self.lecture_entry.delete(0, tk.END)
            self.lecture_entry.insert(0, lecture)
            self.audio_path = audio_path
            self.audio_path_label.config(text=os.path.basename(audio_path) if audio_path else "No file selected")
            
            global CURRENT_LECTURE_INFO
            CURRENT_LECTURE_INFO = {
                "course": course, "lecture": lecture, "audio_path": audio_path,
                "lang_mode": checkpoint.get("lang", self.lang_var.get()),
                "resume_offset_sec": last_offset,
            }
            
            self.run_pipeline_threaded(
                checkpoint=checkpoint,
                course=course,
                lecture=lecture,
                audio_path=audio_path,
                lang=checkpoint.get("lang", self.lang_var.get()),
                restart=False,
                resume_offset=last_offset
            )
        else:
            self.course_entry.delete(0, tk.END)
            self.lecture_entry.delete(0, tk.END)
            self.audio_path = None
            self.audio_path_label.config(text="No file selected")

    # ─── Individual / Manual Transcription Execution ──────────────────────────
    def run_pipeline_threaded(self, checkpoint=None, **kwargs):
        threading.Thread(target=self.run_pipeline, kwargs=kwargs if checkpoint is None else {**kwargs, "checkpoint": checkpoint}, daemon=True).start()

    def run_pipeline(self, checkpoint=None, *, course=None, lecture=None, audio_path=None, lang=None, restart=False, resume_offset=None):
        try:
            if checkpoint:
                course = checkpoint.get("course", course)
                lecture = checkpoint.get("lecture", lecture)
                audio_path = checkpoint.get("audio_path", audio_path)
                lang_mode = checkpoint.get("lang", lang or "Auto (Detect)")
                restart = checkpoint.get("restart", restart)
                last_offset = checkpoint.get("last_offset_sec", 0.0)
                threads_loaded = checkpoint.get("threads", 4)
                
                _ckpt_chunk = checkpoint.get("chunk_token", 0)
                chunk_token_loaded = _ckpt_chunk if _ckpt_chunk > 500 else self.tokens
                beam_size_loaded = checkpoint.get("beam_size", 2)
                resume_offset = resume_offset if resume_offset is not None else last_offset
                run_suffix = checkpoint.get("run_suffix", "")
                
                if not (course and lecture and audio_path):
                    messagebox.showerror("Checkpoint Error", "Missing info in checkpoint.")
                    return
                
                display_name = f"{course} / {lecture}" + (f" (Run {run_suffix.replace('_', '')})" if run_suffix else "")
                self.update_current_process(display_name)
                
                if restart:
                    self.update_status(f"🔄 Restarting {course}/{lecture}...", "green")
                else:
                    self.update_status(f"▶ Resuming {course}/{lecture} from {resume_offset:.1f}s...", "green")
            else:
                course = course or self.course_entry.get().strip()
                lecture = lecture or self.lecture_entry.get().strip()
                audio_path = audio_path or getattr(self, "audio_path", None)
                lang_mode = lang or self.lang_var.get()
                resume_offset = resume_offset or 0.0
                threads_loaded = chunk_token_loaded = beam_size_loaded = None
                
                run_suffix = _get_run_suffix(course, lecture, self.overwrite_transcripts.get())
                
                if not course or not lecture or not audio_path:
                    messagebox.showwarning("Missing Info", "Please provide course name, lecture title, and audio file.")
                    return
                    
                display_name = f"{course} / {lecture}" + (f" (Run {run_suffix.replace('_', '')})" if run_suffix else "")
                self.update_current_process(display_name)

            lecture_dir = prepare_lecture_folder(course, lecture)
            transcript_path = os.path.join(lecture_dir, f"transcript{run_suffix}.txt")

            model_map = {"Medium": "medium", "Small": "small", "Base": "base", "Tiny": "tiny"}
            selected_model = model_map.get(self.whisper_model_display.get(), "medium")

            try:
                threads = max(1, int(self.asr_threads.get()))
            except Exception:
                threads = 4

            self.update_status(f"🎧 Transcribing with Faster-Whisper ({selected_model})...", "green")

            kwargs = {
                "lang_mode": lang_mode,
                "model": selected_model,
                "chunk_token": chunk_token_loaded if checkpoint else self.tokens,
                "fixed_chunks": None if (checkpoint or not self.is_fixed_chunk_mode.get()) else self.desired_chunks.get(),
                "gui_callback": lambda msg: self.update_status(msg, "green"),
                "fw_device": self._get_device_and_compute()[0],
                "fw_compute_type": self._get_device_and_compute()[1],
                "fw_beam_size": self.beam_size.get() if not checkpoint else beam_size_loaded,
                "fw_vad": True,  
                "threads": threads_loaded if checkpoint else threads,
                "course": course,
                "lecture": lecture,
                "resume_offset": resume_offset,
                "fresh_start": checkpoint is None,
                "run_suffix": run_suffix
            }

            ar_text, en_text, transcript_metadata_json = transcribe_audio(audio_path, **kwargs)

            self.update_status("💾 Transcription complete.", "black")
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(ar_text)
            clear_lecture_checkpoints(course=course, lecture=lecture, run_suffix=run_suffix)
            self.update_current_process("None")
            messagebox.showinfo("Done", "Lecture processed successfully.")

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Transcription Error", str(e))
            self.update_current_process("None")

    # ─── YouTube Popup & Logic ────────────────────────────────────────────────
    def open_youtube_popup(self):
        try:
            from youtube_downloader import download_youtube_audio, YTDLP_AVAILABLE
        except ImportError:
            messagebox.showerror("Module Not Found", "youtube_downloader.py was not found.")
            return

        course = self.course_entry.get().strip()
        lecture = self.lecture_entry.get().strip()

        if not course or not lecture:
            messagebox.showwarning("Missing Info", "Please fill in the Course Name and Lecture Title fields.")
            return

        if not YTDLP_AVAILABLE:
            messagebox.showerror("yt-dlp Not Installed", "Install it by running:\n    pip install yt-dlp")
            return

        yt_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_downloads", sanitize_filename(course), sanitize_filename(lecture))
        existing_audio = None
        if os.path.exists(yt_dir):
            for f in os.listdir(yt_dir):
                if f.startswith("audio.") and f.endswith((".mp3", ".m4a", ".webm", ".mp4", ".wav")):
                    existing_audio = os.path.join(yt_dir, f)
                    break

        if existing_audio:
            ans_dict = {"choice": None}
            dlg = tk.Toplevel(self.root)
            dlg.title("Existing Audio Found")
            dlg.geometry("450x260")
            dlg.transient(self.root)
            dlg.grab_set()
            dlg.resizable(False, False)
            
            tk.Label(dlg, text=f"A downloaded audio file already exists for:\n{course} / {lecture}", font=("", 10, "bold")).pack(pady=10)
            tk.Label(dlg, text="What would you like to do?").pack(pady=5)
            
            def check_checkpoint_exists():
                ckpt_file = "whisper_checkpoint.json"
                if not os.path.exists(ckpt_file): return False
                try:
                    with open(ckpt_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            return any(i.get("course") == course and i.get("lecture") == lecture for i in data)
                        elif isinstance(data, dict):
                            return data.get("course") == course and data.get("lecture") == lecture
                except Exception:
                    pass
                return False

            def set_choice(c):
                if c == "resume" and not check_checkpoint_exists():
                    messagebox.showinfo("Cannot Resume", f"No unfinished transcription found for '{lecture}'.", parent=dlg)
                    return 
                ans_dict["choice"] = c
                dlg.destroy()
                
            tk.Button(dlg, text="▶️ Resume Transcription (If interrupted)", command=lambda: set_choice("resume"), bg="#1a73e8", fg="white", font=("", 10, "bold")).pack(fill="x", padx=40, pady=5)
            tk.Button(dlg, text="🔄 Restart Transcription (From the beginning)", command=lambda: set_choice("restart")).pack(fill="x", padx=40, pady=5)
            tk.Button(dlg, text="⬇️ Download New Video (Overwrite existing)", command=lambda: set_choice("new")).pack(fill="x", padx=40, pady=5)
            
            self.root.wait_window(dlg)
            choice = ans_dict["choice"]
            
            if not choice: return

            if choice in ["resume", "restart"]:
                self.audio_path = existing_audio
                self.audio_path_label.config(text=f"[YouTube] {course} / {lecture}")
                try:
                    self.audio_duration_sec = len(AudioSegment.from_file(existing_audio)) / 1000.0
                except Exception:
                    self.audio_duration_sec = 0
                    
                if choice == "resume":
                    ckpt = load_last_checkpoint(course=course, lecture=lecture)
                    resume_sec = compute_resume_start_sec(ckpt) if ckpt else 0.0
                    dummy_ckpt = {"course": course, "lecture": lecture, "audio_path": existing_audio, "lang": self.lang_var.get(), "last_offset_sec": resume_sec, "restart": False}
                    self.update_status(f"▶ Resuming YouTube audio for {lecture}...", "green")
                    self.run_pipeline_threaded(checkpoint=dummy_ckpt)
                else:
                    self.update_status(f"🎧 Transcribing YouTube audio for {lecture}...", "green")
                    self.run_pipeline_threaded(course=course, lecture=lecture, audio_path=existing_audio, lang=self.lang_var.get(), restart=True)
                return

        # Show standard popup if no existing file or user chose 'new'
        popup = tk.Toplevel(self.root)
        popup.title("YouTube → Transcribe")
        popup.geometry("520x340")
        popup.transient(self.root)
        popup.grab_set()
        popup.resizable(False, False)

        tk.Label(popup, text="🎬 YouTube Download & Transcribe", font=("", 12, "bold")).pack(pady=(14, 4))
        tk.Label(popup, text=f"Course:  {course}    |    Lecture:  {lecture}", fg="gray").pack()
        tk.Label(popup, text="\nPaste YouTube URL (public or unlisted):").pack(anchor="w", padx=20)

        url_var = tk.StringVar()
        url_entry = tk.Entry(popup, textvariable=url_var, width=58)
        url_entry.pack(padx=20, pady=(2, 10))
        url_entry.focus_set()

        popup_status = tk.Label(popup, text="Ready.", fg="blue", wraplength=480)
        popup_status.pack(pady=4, padx=20)

        def _update(msg):
            try:
                popup_status.config(text=msg)
                popup.update_idletasks()
            except Exception: pass

        def _do_download_then(action):
            url = url_var.get().strip()
            if not url:
                messagebox.showwarning("No URL", "Please paste a YouTube URL first.", parent=popup)
                return

            if action == "queue" and self.lazy_youtube_download.get():
                self._queue.append({
                    "course": course, "lecture": lecture, "audio_path": "Pending Download...",
                    "lang": self.lang_var.get(), "youtube": True, "url": url,
                    "chunk_token": self.tokens, "fixed_chunks": self.desired_chunks.get() if self.is_fixed_chunk_mode.get() else None,
                    "lazy_download": True, "status": "waiting"
                })
                save_queue_checkpoint(list(self._queue))
                self._refresh_queue_listbox()
                popup.destroy()
                self.update_status(f"✅ Added to queue (delayed download): {course} / {lecture}", "green")
                return

            def _handle_success(final_audio_path):
                if action == "start":
                    self.audio_path = final_audio_path
                    self.audio_path_label.config(text=f"[YouTube] {course} / {lecture}")
                    try:
                        self.audio_duration_sec = len(AudioSegment.from_file(final_audio_path)) / 1000.0
                    except Exception:
                        self.audio_duration_sec = 0
                    popup.destroy()
                    self.update_status(f"🎧 Transcribing YouTube audio for {lecture}...", "green")
                    self.run_pipeline_threaded(course=course, lecture=lecture, audio_path=final_audio_path, lang=self.lang_var.get())
                else: 
                    self._queue.append({
                        "course": course, "lecture": lecture, "audio_path": final_audio_path,
                        "lang": self.lang_var.get(), "youtube": True, "url": url,
                        "chunk_token": self.tokens, "fixed_chunks": self.desired_chunks.get() if self.is_fixed_chunk_mode.get() else None,
                        "lazy_download": False, "status": "waiting"
                    })
                    save_queue_checkpoint(list(self._queue))
                    self._refresh_queue_listbox()
                    popup.destroy()
                    self.update_status(f"✅ Added to queue: {course} / {lecture}", "green")

            dl_btn_start.config(state="disabled")
            dl_btn_queue.config(state="disabled")

            def _worker():
                try:
                    _update("⬇️  Connecting to YouTube...")
                    from youtube_downloader import download_youtube_audio
                    audio_path = download_youtube_audio(url=url, course=course, lecture=lecture, progress_callback=_update)
                    _update(f"✅ Audio saved.\n{audio_path}")
                    self.root.after(0, lambda: _handle_success(audio_path))
                except Exception as exc:
                    _update(f"❌ Error: {exc}")
                    try:
                        dl_btn_start.config(state="normal")
                        dl_btn_queue.config(state="normal")
                    except Exception: pass

            threading.Thread(target=_worker, daemon=True).start()

        btn_row = tk.Frame(popup); btn_row.pack(pady=8)
        dl_btn_start = tk.Button(btn_row, text="⬇️ Download & Start Now", bg="#1a73e8", fg="white", font=("", 10, "bold"), command=lambda: _do_download_then("start"))
        dl_btn_start.pack(side="left", padx=8)

        dl_btn_queue = tk.Button(btn_row, text="➕ Download & Add to Queue", bg="#1a7a1a", fg="white", font=("", 10, "bold"), command=lambda: _do_download_then("queue"))
        dl_btn_queue.pack(side="left", padx=8)

        tk.Label(popup, text="ℹ️  Works with public and unlisted videos.\nPrivate or members-only videos cannot be downloaded.", fg="gray", font=("", 8), justify="center").pack(pady=(0, 10))

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