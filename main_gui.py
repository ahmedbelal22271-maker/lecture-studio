import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
from whisper_offline import transcribe_audio, kill_whisper, set_abort_flag
from output_manager import clear_lecture_checkpoints, prepare_lecture_folder, load_last_checkpoint, save_checkpoint_offset, compute_resume_start_sec, save_transcript_chunks, BASE_DIR
from pydub import AudioSegment
import json
import collections

# Queue checkpoint file — persists the queue across restarts
QUEUE_CHECKPOINT_FILE = "queue_checkpoint.json"

def _save_queue_checkpoint(queue_items: list) -> None:
    """Save the current queue to disk so it survives a force-close."""
    import tempfile, json as _json
    tmp = QUEUE_CHECKPOINT_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(queue_items, f, indent=2, ensure_ascii=False)
        os.replace(tmp, QUEUE_CHECKPOINT_FILE)
    except Exception as e:
        print(f"[WARNING] Could not save queue checkpoint: {e}")

def _load_queue_checkpoint() -> list:
    """Load saved queue items from disk. Returns [] if nothing found."""
    import json as _json
    if not os.path.exists(QUEUE_CHECKPOINT_FILE):
        return []
    try:
        with open(QUEUE_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = _json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _clear_queue_checkpoint() -> None:
    """Delete the queue checkpoint file."""
    try:
        if os.path.exists(QUEUE_CHECKPOINT_FILE):
            os.remove(QUEUE_CHECKPOINT_FILE)
    except Exception as e:
        print(f"[WARNING] Could not clear queue checkpoint: {e}")

# Constants
CTX_SIZE = 4096
tokens_per_word = 1.3
CURRENT_LECTURE_INFO = {}

WPM_PRESETS = {
    "Casual Lecture (~120 WPM)": 120,
    "Dense Technical Lecture (~180 WPM)": 180
}

def estimate_tokens(wpm, minutes):
    return int(wpm * minutes * tokens_per_word)


# ── Course Library Browser Class ─────────────────────────────────────────────
class LibraryBrowser:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("📚 Course Library")
        self.window.geometry("900x600")
        self.window.transient(parent)
        
        # Split layout: Treeview on the left, Text viewer on the right
        self.paned = tk.PanedWindow(self.window, orient=tk.HORIZONTAL, sashwidth=4)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ── Left Pane: File Tree & Action Buttons ──
        self.tree_frame = tk.Frame(self.paned)
        
        self.tree = ttk.Treeview(self.tree_frame, selectmode="browse")
        self.tree_scroll = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scroll.set)
        
        # Action button frame at the bottom of the tree
        self.tree_btn_frame = tk.Frame(self.tree_frame)
        self.tree_btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        
        tk.Button(self.tree_btn_frame, text="🪓 Re-chunk Selected Lecture", 
                  command=self.rechunk_transcript).pack(fill=tk.X)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)

        # ── Right Pane: File Content Viewer ──
        self.view_frame = tk.Frame(self.paned)
        self.text_viewer = tk.Text(self.view_frame, wrap="word", state="disabled", font=("Segoe UI", 10))
        self.text_scroll = ttk.Scrollbar(self.view_frame, orient="vertical", command=self.text_viewer.yview)
        self.text_viewer.configure(yscrollcommand=self.text_scroll.set)
        
        self.text_viewer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.paned.add(self.tree_frame, minsize=250)
        self.paned.add(self.view_frame, minsize=400)

        self.populate_tree()

    def populate_tree(self):
        """Scan the BASE_DIR and populate the Treeview hierarchically."""
        if not os.path.exists(BASE_DIR):
            self.tree.insert("", tk.END, text="No courses found.")
            return

        # Top level node
        root_node = self.tree.insert("", tk.END, text="Courses", open=True)

        for course in sorted(os.listdir(BASE_DIR)):
            course_path = os.path.join(BASE_DIR, course)
            if os.path.isdir(course_path):
                course_node = self.tree.insert(root_node, tk.END, text=f"📘 {course}", open=False)
                
                for lecture in sorted(os.listdir(course_path)):
                    lecture_path = os.path.join(course_path, lecture)
                    if os.path.isdir(lecture_path):
                        lecture_node = self.tree.insert(course_node, tk.END, text=f"🎙 {lecture}", open=False)
                        self._add_files_to_tree(lecture_node, lecture_path)

    def _add_files_to_tree(self, parent_node, path):
        """Recursively add files and folders to the tree."""
        for item in sorted(os.listdir(path)):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                folder_node = self.tree.insert(parent_node, tk.END, text=f"📂 {item}", open=False)
                self._add_files_to_tree(folder_node, item_path)
            elif item.endswith(".txt") or item.endswith(".json") or item.endswith(".md"):
                self.tree.insert(parent_node, tk.END, text=f"📄 {item}", values=(item_path,))

    def _get_course_and_lecture_from_selection(self):
        """Traverse up the tree to figure out the course and lecture of the selected item."""
        selected = self.tree.selection()
        if not selected: 
            return None, None
            
        item = selected[0]
        course = None
        lecture = None
        
        # Walk up the tree parents to find the lecture and course labels
        while item:
            text = self.tree.item(item, "text")
            if text.startswith("🎙 "):
                lecture = text[2:] # Slice off the emoji and space
            elif text.startswith("📘 "):
                course = text[2:]
            item = self.tree.parent(item)
            
        return course, lecture

    def rechunk_transcript(self):
        """Prompts the user for chunks and splits the existing transcript."""
        course, lecture = self._get_course_and_lecture_from_selection()
        
        if not course or not lecture:
            messagebox.showinfo("Select Lecture", "Please select a lecture (or a file inside it) from the tree first.", parent=self.window)
            return
            
        transcript_path = os.path.join(BASE_DIR, course, lecture, "final_transcript.txt")
        
        if not os.path.exists(transcript_path):
            messagebox.showwarning("Not Found", f"No 'final_transcript.txt' found in:\n{course} / {lecture}\n\nYou can only re-chunk completed lectures.", parent=self.window)
            return
            
        num_chunks = simpledialog.askinteger(
            "Re-chunk Transcript", 
            f"How many chunks do you want for '{lecture}'?", 
            parent=self.window, 
            minvalue=1, 
            maxvalue=999
        )
        
        if not num_chunks:
            return  # User cancelled or closed the dialog
            
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                full_text = f.read()
                
            # Use the existing output_manager logic to chunk and save it
            save_transcript_chunks(course, lecture, full_text, fixed_chunks=num_chunks)
            
            messagebox.showinfo("Success", f"Transcript successfully split into {num_chunks} chunks!\nThey are saved in the lecture's chunk folder.", parent=self.window)
            
            # Refresh the tree visually to display the new chunk text files
            self.tree.delete(*self.tree.get_children())
            self.populate_tree()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to re-chunk the transcript:\n{str(e)}", parent=self.window)

    def on_item_select(self, event):
        """Triggered when a user clicks an item in the tree."""
        selected_item = self.tree.selection()
        if not selected_item:
            return

        item_values = self.tree.item(selected_item[0], "values")
        
        if item_values:
            file_path = item_values[0]
            self.display_file_content(file_path)
        else:
            self.text_viewer.config(state="normal")
            self.text_viewer.delete("1.0", tk.END)
            self.text_viewer.insert("1.0", "Select a text or markdown file to view its contents.")
            self.text_viewer.config(state="disabled")

    def display_file_content(self, file_path):
        """Read the file and display it in the text widget."""
        self.text_viewer.config(state="normal")
        self.text_viewer.delete("1.0", tk.END)
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.text_viewer.insert("1.0", content)
        except Exception as e:
            self.text_viewer.insert("1.0", f"Error reading file:\n{str(e)}")
            
        self.text_viewer.config(state="disabled")


# ── Main GUI Application ─────────────────────────────────────────────────────
class LectureStudioGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Lecture Studio 2.0")
        self.root.geometry("500x740")
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        # Default settings
        self.chunk_mode = tk.StringVar(value="dynamic")
        self.wpm = tk.IntVar(value=120)
        self.chunk_minutes = tk.IntVar(value=10)
        self.tokens = estimate_tokens(120, 10)  
        self.use_fixed_chunk_count = tk.BooleanVar(value=False)
        self.desired_chunks = tk.IntVar(value=10)
        self.beam_size = tk.IntVar(value=2)
        self.whisper_model_display = tk.StringVar(value="Medium")
        self.asr_threads = tk.IntVar(value=min(4, os.cpu_count() or 4))

        # Queue state
        self._queue = collections.deque()
        self._queue_running = False

        # Emergency stop
        tk.Button(root, text="🛑 Emergency Stop", fg="white", bg="red",
                  command=self.shutdown).pack(pady=5)

        # Course / lecture / language
        tk.Label(root, text="📘 Course Name:").pack()
        self.course_entry = tk.Entry(root); self.course_entry.pack()

        tk.Label(root, text="🎙 Lecture Title:").pack()
        self.lecture_entry = tk.Entry(root); self.lecture_entry.pack()

        tk.Label(root, text="🌐 Audio Language:").pack(pady=5)
        self.lang_var = tk.StringVar(value="Arabic")
        tk.OptionMenu(root, self.lang_var, "Arabic", "English", "Auto (Detect)").pack()

        # Audio selection
        tk.Button(root, text="🎧 Choose Lecture Audio (.mp3 / .m4a)",
                  command=self.browse_audio).pack(pady=5)
        self.audio_path_label = tk.Label(root, text="No file selected", fg="gray")
        self.audio_path_label.pack()

        # Action buttons
        tk.Button(root, text="⚙️ Settings", command=self.open_settings).pack(pady=5)
        tk.Button(root, text="▶️ YouTube → Transcribe",
                  command=self.open_youtube_popup).pack(pady=2)
        tk.Button(root, text="📚 Open Lecture Library",
                  command=self.open_library).pack(pady=(2, 5))

        btn_frame = tk.Frame(root); btn_frame.pack(pady=4)
        tk.Button(btn_frame, text="➕ Add to Queue",
                  command=self.add_to_queue).pack(side="left", padx=6)
        tk.Button(btn_frame, text="🚀 Start Processing",
                  command=self.run_pipeline_threaded).pack(side="left", padx=6)

        # Queue display
        tk.Label(root, text="📋 Queue:", anchor="w").pack(fill="x", padx=10)
        queue_frame = tk.Frame(root)
        queue_frame.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        scrollbar = tk.Scrollbar(queue_frame, orient="vertical")
        self.queue_listbox = tk.Listbox(queue_frame, height=6,
                                        yscrollcommand=scrollbar.set,
                                        selectmode="single", activestyle="dotbox")
        scrollbar.config(command=self.queue_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.queue_listbox.pack(side="left", fill="both", expand=True)

        queue_btn_frame = tk.Frame(root); queue_btn_frame.pack(pady=2)
        tk.Button(queue_btn_frame, text="▶ Start Queue",
                  command=self.start_queue, bg="#1a7a1a", fg="white").pack(side="left", padx=6)
        tk.Button(queue_btn_frame, text="✏ Edit Selected",
                  command=self.edit_selected_queue_item).pack(side="left", padx=6)
        tk.Button(queue_btn_frame, text="✖ Remove Selected",
                  command=self.remove_selected_from_queue).pack(side="left", padx=6)
        tk.Button(queue_btn_frame, text="🗑 Clear Queue",
                  command=self.clear_queue).pack(side="left", padx=6)

        # Status
        self.status_label = tk.Label(root, text="Waiting for input...", fg="blue",
                                     wraplength=460)
        self.status_label.pack(pady=8)

        self.root.after(200, self.check_for_resume)
        self.root.after(400, self.check_for_queue_restore)

    def open_library(self):
        """Spawns the library browser window."""
        LibraryBrowser(self.root)

    # ── Queue methods ────────────────────────────────────────────────────────

    def add_to_queue(self):
        course     = self.course_entry.get().strip()
        lecture    = self.lecture_entry.get().strip()
        audio_path = getattr(self, "audio_path", None)
        lang       = self.lang_var.get()

        if not course or not lecture or not audio_path:
            messagebox.showwarning(
                "Missing Info",
                "Please fill in Course Name, Lecture Title, and choose an audio file "
                "before adding to the queue."
            )
            return

        self._queue.append({
            "course":       course,
            "lecture":      lecture,
            "audio_path":   audio_path,
            "lang":         lang,
            "chunk_token":  self.tokens,
            "fixed_chunks": self.desired_chunks.get() if self.use_fixed_chunk_count.get() else None,
        })
        _save_queue_checkpoint(list(self._queue))
        self._refresh_queue_listbox()

        # Clear fields for next entry
        self.course_entry.delete(0, tk.END)
        self.lecture_entry.delete(0, tk.END)
        self.audio_path = None
        self.audio_path_label.config(text="No file selected")
        self.update_status(
            f"✅ Added [{len(self._queue)}]: {course} / {lecture}", "green")

    def remove_selected_from_queue(self):
        sel = self.queue_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        lst = list(self._queue)
        removed = lst.pop(idx)
        self._queue = collections.deque(lst)
        _save_queue_checkpoint(list(self._queue))
        self._refresh_queue_listbox()
        self.update_status(
            f"Removed: {removed['course']} / {removed['lecture']}", "gray")

    def clear_queue(self):
        if not self._queue:
            return
        if messagebox.askyesno("Clear Queue", "Remove all items from the queue?"):
            self._queue.clear()
            _save_queue_checkpoint([])
            self._refresh_queue_listbox()
            self.update_status("Queue cleared.", "gray")

    def edit_selected_queue_item(self):
        """Open an edit dialog for the currently selected queue item."""
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

        # Course
        tk.Label(win, text="📘 Course Name:").grid(row=0, column=0, sticky="w", **pad)
        course_var = tk.StringVar(value=item["course"])
        tk.Entry(win, textvariable=course_var, width=36).grid(row=0, column=1, **pad)

        # Lecture
        tk.Label(win, text="🎙 Lecture Title:").grid(row=1, column=0, sticky="w", **pad)
        lecture_var = tk.StringVar(value=item["lecture"])
        tk.Entry(win, textvariable=lecture_var, width=36).grid(row=1, column=1, **pad)

        # Language
        tk.Label(win, text="🌐 Language:").grid(row=2, column=0, sticky="w", **pad)
        lang_var = tk.StringVar(value=item.get("lang", "Arabic"))
        tk.OptionMenu(win, lang_var, "Arabic", "English", "Auto (Detect)").grid(
            row=2, column=1, sticky="w", **pad)

        # Model
        tk.Label(win, text="🧠 Model:").grid(row=3, column=0, sticky="w", **pad)
        model_var = tk.StringVar(
            value=item.get("model", self.whisper_model_display.get()))
        tk.OptionMenu(win, model_var, "Medium", "Small", "Base", "Tiny").grid(
            row=3, column=1, sticky="w", **pad)

        # Beam Size
        tk.Label(win, text="🔍 Beam Size:").grid(row=4, column=0, sticky="w", **pad)
        beam_var = tk.IntVar(value=item.get("beam_size", self.beam_size.get()))
        tk.Spinbox(win, from_=1, to=5, width=6, textvariable=beam_var).grid(
            row=4, column=1, sticky="w", **pad)

        # Threads
        max_threads = max(1, os.cpu_count() or 4)
        tk.Label(win, text="⚙ Threads:").grid(row=5, column=0, sticky="w", **pad)
        threads_var = tk.IntVar(
            value=item.get("threads", self.asr_threads.get()))
        tk.Spinbox(win, from_=1, to=max_threads, width=6,
                   textvariable=threads_var).grid(row=5, column=1, sticky="w", **pad)

        is_youtube = item.get("youtube", False)
        audio_var  = tk.StringVar(value=item["audio_path"])
        url_var    = tk.StringVar(value=item.get("url", ""))

        if is_youtube:
            # ── YouTube item: show URL + re-download option ──────────────────
            tk.Label(win, text="🔗 YouTube URL:").grid(row=6, column=0, sticky="w", **pad)
            tk.Entry(win, textvariable=url_var, width=36).grid(row=6, column=1, **pad)

            tk.Label(win, text="🎧 Audio File:").grid(row=7, column=0, sticky="w", **pad)
            tk.Label(win, textvariable=audio_var, fg="gray",
                     width=34, anchor="w", wraplength=260).grid(
                row=7, column=1, sticky="w", **pad)

            redownload_status = tk.Label(win, text="", fg="blue", wraplength=280)
            redownload_status.grid(row=8, column=0, columnspan=2, **pad)

            def _redownload():
                new_url = url_var.get().strip()
                if not new_url:
                    messagebox.showwarning("No URL", "Please enter a YouTube URL first.",
                                           parent=win)
                    return
                redownload_btn.config(state="disabled", text="⏳ Downloading...")

                def _worker():
                    try:
                        from youtube_downloader import download_youtube_audio
                        new_course  = course_var.get().strip() or item["course"]
                        new_lecture = lecture_var.get().strip() or item["lecture"]

                        def _upd(msg):
                            try:
                                redownload_status.config(text=msg)
                                win.update_idletasks()
                            except Exception:
                                pass

                        path = download_youtube_audio(
                            url=new_url,
                            course=new_course,
                            lecture=new_lecture,
                            progress_callback=_upd,
                        )
                        audio_var.set(path)
                        redownload_status.config(
                            text=f"✅ Downloaded: {os.path.basename(path)}", fg="green")
                        redownload_btn.config(state="normal",
                                              text="🔄 Re-download from URL")
                    except Exception as exc:
                        redownload_status.config(text=f"❌ {exc}", fg="red")
                        redownload_btn.config(state="normal",
                                              text="🔄 Re-download from URL")

                threading.Thread(target=_worker, daemon=True).start()

            redownload_btn = tk.Button(
                win, text="🔄 Re-download from URL", command=_redownload)
            redownload_btn.grid(row=9, column=1, sticky="w", padx=12, pady=2)
            save_row = 10

        else:
            # ── Local file item: show file path + re-browse ──────────────────
            tk.Label(win, text="🎧 Audio File:").grid(row=6, column=0, sticky="w", **pad)
            tk.Label(win, textvariable=audio_var, fg="gray",
                     width=34, anchor="w", wraplength=260).grid(
                row=6, column=1, sticky="w", **pad)

            def _rebrowse():
                path = tk.filedialog.askopenfilename(filetypes=[
                    ("Audio files", "*.mp3 *.m4a"),
                    ("MP3 files",   "*.mp3"),
                    ("M4A files",   "*.m4a"),
                ])
                if path:
                    audio_var.set(path)

            tk.Button(win, text="Browse…", command=_rebrowse).grid(
                row=7, column=1, sticky="w", padx=12, pady=2)
            save_row = 8

        # Save / Cancel
        def _save():
            new_course  = course_var.get().strip()
            new_lecture = lecture_var.get().strip()
            if not new_course or not new_lecture:
                messagebox.showwarning("Invalid", "Course and Lecture cannot be empty.",
                                       parent=win)
                return
            updated = {
                **item,
                "course":     new_course,
                "lecture":    new_lecture,
                "lang":       lang_var.get(),
                "model":      model_var.get(),
                "beam_size":  beam_var.get(),
                "threads":    threads_var.get(),
                "audio_path": audio_var.get(),
            }
            if is_youtube:
                updated["url"] = url_var.get().strip()
            lst[idx] = updated
            self._queue = __import__("collections").deque(lst)
            _save_queue_checkpoint(lst)
            self._refresh_queue_listbox()
            win.destroy()
            self.update_status(f"✅ Queue item #{idx + 1} updated.", "green")

        btn_row = tk.Frame(win)
        btn_row.grid(row=save_row, column=0, columnspan=2, pady=10)
        tk.Button(btn_row, text="💾 Save", command=_save,
                  bg="#1a73e8", fg="white", width=10).pack(side="left", padx=8)
        tk.Button(btn_row, text="Cancel", command=win.destroy,
                  width=10).pack(side="left", padx=8)

        win.update_idletasks()
        win.geometry(f"{win.winfo_reqwidth() + 20}x{win.winfo_reqheight() + 10}")

    def _refresh_queue_listbox(self):
        self.queue_listbox.delete(0, tk.END)
        for i, item in enumerate(self._queue, 1):
            source = "[YT]" if item.get("youtube") else "[local]"
            self.queue_listbox.insert(
                tk.END,
                f"{i}. {source} [{item['lang']}]  {item['course']}  /  {item['lecture']}"
            )

    def start_queue(self):
        if not self._queue:
            messagebox.showinfo("Queue Empty", "Add lectures to the queue first.")
            return
        if self._queue_running:
            messagebox.showinfo("Already Running",
                                "The queue is already being processed.")
            return
        threading.Thread(target=self._queue_worker, daemon=True).start()

    def _queue_worker(self):
        """Process all queue items one by one (FIFO). Runs on a background thread."""
        self._queue_running = True
        total = len(self._queue)
        completed = 0

        while self._queue:
            item = self._queue.popleft()
            completed += 1
            remaining = len(self._queue)
            # Update checkpoint — item was popped so it won't re-run on restore
            _save_queue_checkpoint(list(self._queue))
            self.root.after(0, self._refresh_queue_listbox)
            self.root.after(
                0, lambda c=item["course"], l=item["lecture"],
                n=completed, t=total, r=remaining:
                self.update_status(
                    f"🎧 Processing {n}/{t}: {c} / {l}  "
                    f"({r} remaining after this)", "green")
            )

            try:
                self._run_single_item(item)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                keep_going = [True]

                def _ask(exc=exc, item=item, kg=keep_going):
                    ans = messagebox.askyesno(
                        "Item Failed",
                        f"Error on:\n{item['course']} / {item['lecture']}\n\n"
                        f"{exc}\n\nContinue with remaining queue?"
                    )
                    kg[0] = ans

                self.root.after(0, _ask)
                import time; time.sleep(0.5)   # let dialog appear
                if not keep_going[0]:
                    self._queue.clear()
                    self.root.after(0, self._refresh_queue_listbox)
                    break

        self._queue_running = False
        _clear_queue_checkpoint()   # all done — no need to restore anything
        self.root.after(0, self._refresh_queue_listbox)
        self.root.after(
            0, lambda c=completed:
            self.update_status(
                f"✅ Queue complete — {c} lecture(s) processed.", "black")
        )

    def _run_single_item(self, item: dict):
        """
        Transcribe one queue item. Blocks until done (called from queue worker).
        Uses per-item settings if the item was edited; falls back to global settings.
        """
        course     = item["course"]
        lecture    = item["lecture"]
        audio_path = item["audio_path"]
        lang_mode  = item["lang"]

        # Per-item overrides (set by the Edit dialog) — fall back to global settings
        model_map     = {"Medium": "medium", "Small": "small",
                         "Base": "base", "Tiny": "tiny"}
        selected_model = model_map.get(
            item.get("model", self.whisper_model_display.get()), "medium")
        beam_size = item.get("beam_size", self.beam_size.get())
        try:
            threads = max(1, int(item.get("threads", self.asr_threads.get())))
        except Exception:
            threads = 4

        lecture_dir     = prepare_lecture_folder(course, lecture)
        transcript_path = os.path.join(lecture_dir, "final_transcript.txt")

        # Use per-item chunk_token if set, else fall back to current global value
        chunk_token   = item.get("chunk_token", self.tokens)
        fixed_chunks  = item.get("fixed_chunks", None)

        ar_text, _, _ = transcribe_audio(audio_path, **{
            "lang_mode":       lang_mode,
            "model":           selected_model,
            "chunk_token":     chunk_token,
            "fixed_chunks":    fixed_chunks,
            "gui_callback":    lambda msg: self.update_status(msg, "green"),
            "fw_device":       "cpu",
            "fw_compute_type": "int8",
            "fw_beam_size":    beam_size,
            "fw_vad":          True,   # VAD skips silent sections
            "threads":         threads,
            "course":          course,
            "lecture":         lecture,
            "resume_offset":   0.0,
            "fresh_start":     True,
        })

        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(ar_text)
        clear_lecture_checkpoints(course=course, lecture=lecture)

    # ── Settings / helpers ───────────────────────────────────────────────────

    def on_chunk_slider_change(self, _):
        if hasattr(self, "_chunk_slider_update_job") and self._chunk_slider_update_job:
            self.root.after_cancel(self._chunk_slider_update_job)
        self._chunk_slider_update_job = self.root.after(100, self.update_estimate)

    def open_settings(self):
        FASTER_SPECS = {
            "tiny":   {"Params": "39M",  "RAM": "<1 GB",    "Notes": "Fastest; low accuracy on noisy Arabic"},
            "base":   {"Params": "74M",  "RAM": "1–1.5 GB", "Notes": "Fair; more substitutions"},
            "small":  {"Params": "244M", "RAM": "2–3 GB",   "Notes": "Good; some regressions on accents/noise"},
            "medium": {"Params": "769M", "RAM": "5–7 GB",   "Notes": "Most accurate in this group"},
        }

        def show_model_info(display_name, parent):
            key = (display_name or "").strip().lower()
            if key in FASTER_SPECS:
                s = FASTER_SPECS[key]
                messagebox.showinfo(
                    f"Faster-Whisper Model: {display_name}",
                    "Params: {Params}\nRAM: {RAM}\nNotes: {Notes}".format(**s),
                    parent=parent)
            else:
                messagebox.showwarning("Model Info", "Please select a valid model.",
                                       parent=parent)

        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.transient(self.root)
        win.grab_set()

        max_threads = max(1, os.cpu_count() or 4)

        tk.Label(win, text="WPM Preset:").pack(anchor="w", pady=2)
        wpm_frame = tk.Frame(win); wpm_frame.pack(anchor="w")
        wpm_cb = ttk.Combobox(wpm_frame, textvariable=self.wpm,
                              values=list(WPM_PRESETS.values()),
                              state="readonly", width=18)
        wpm_cb.pack(side="left", padx=(0, 5))
        wpm_cb.bind("<<ComboboxSelected>>", lambda e: self.update_estimate())
        tk.Button(wpm_frame, text="ℹ", width=2,
                  command=lambda: messagebox.showinfo(
                      "WPM Presets",
                      "WPM presets represent typical speaking speeds.\n"
                      "- Casual: ~120 WPM\n- Dense technical: ~180 WPM\n\n"
                      "Adjust depending on your lecture.", parent=win)
                  ).pack(side="left", padx=6)

        tk.Label(win, text="Model:").pack(anchor="w", pady=6)
        model_row = tk.Frame(win); model_row.pack(anchor="w", fill="x")
        tk.OptionMenu(model_row, self.whisper_model_display,
                      "Medium", "Small", "Base", "Tiny").pack(side="left")
        tk.Button(model_row, text="ℹ", width=2,
                  command=lambda: show_model_info(
                      self.whisper_model_display.get(), win)
                  ).pack(side="left", padx=6)

        tk.Label(win, text="ASR Threads:").pack(anchor="w", pady=(10, 2))
        th_row = tk.Frame(win); th_row.pack(anchor="w", fill="x")
        tk.Spinbox(th_row, from_=1, to=max_threads, width=6,
                   textvariable=self.asr_threads).pack(side="left")
        tk.Button(th_row, text="ℹ", width=2,
                  command=lambda: messagebox.showinfo(
                      "Threads",
                      f"Number of CPU threads to use (1–{max_threads}).\n\n"
                      "Higher = faster, but too high may cause contention on laptops.\n"
                      "A safe rule is 50–100% of your CPU cores.", parent=win)
                  ).pack(side="left", padx=6)

        tk.Label(win, text="Beam Size:").pack(anchor="w", pady=(10, 2))
        beam_row = tk.Frame(win); beam_row.pack(anchor="w", fill="x")
        tk.Spinbox(beam_row, from_=1, to=5, width=6,
                   textvariable=self.beam_size).pack(side="left")
        tk.Button(beam_row, text="ℹ", width=2,
                  command=lambda: messagebox.showinfo(
                      "Beam Size",
                      "Beam search width for decoding.\n"
                      "1 = greedy (fastest).\n"
                      "Higher = more accurate but slower.\n"
                      "Recommended: 2 for Arabic lectures.", parent=win)
                  ).pack(side="left", padx=6)

        # ── Chunking mode toggle ────────────────────────────────────────────
        sep = tk.Frame(win, height=1, bg="lightgray"); sep.pack(fill="x", pady=(10,4))
        tk.Label(win, text="Chunking Mode:", font=("", 9, "bold")).pack(anchor="w")

        mode_frame = tk.Frame(win); mode_frame.pack(anchor="w", fill="x")
        tk.Radiobutton(mode_frame, text="Auto (by minutes)",
                       variable=self.use_fixed_chunk_count, value=False,
                       command=lambda: _toggle_chunk_mode()).pack(side="left", padx=(0,12))
        tk.Radiobutton(mode_frame, text="Fixed number of chunks",
                       variable=self.use_fixed_chunk_count, value=True,
                       command=lambda: _toggle_chunk_mode()).pack(side="left")

        # ── Auto mode widgets ────────────────────────────────────────────────
        auto_frame = tk.Frame(win); auto_frame.pack(fill="x")
        self.chunk_slider = tk.Scale(
            auto_frame, from_=1, to=30, orient="horizontal",
            label="Chunk Length (minutes)",
            variable=self.chunk_minutes, command=lambda _: self.update_estimate())
        self.chunk_slider.pack(fill="x")
        self.chunk_slider.config(command=self.on_chunk_slider_change)
        self.token_label = tk.Label(auto_frame, text="~0 tokens")
        self.token_label.pack(anchor="w")
        self.warning_label = tk.Label(auto_frame, text="", fg="red")
        self.warning_label.pack(anchor="w")
        self.chunk_count_label = tk.Label(auto_frame, text="Estimated chunks: ?")
        self.chunk_count_label.pack(anchor="w", pady=2)

        # ── Fixed chunks mode widgets ────────────────────────────────────────
        fixed_frame = tk.Frame(win); fixed_frame.pack(fill="x")
        fix_row = tk.Frame(fixed_frame); fix_row.pack(anchor="w", pady=4)
        tk.Label(fix_row, text="Number of chunks:").pack(side="left")
        tk.Spinbox(fix_row, from_=1, to=999, width=6,
                   textvariable=self.desired_chunks).pack(side="left", padx=6)
        tk.Button(fix_row, text="ℹ", width=2,
                  command=lambda: messagebox.showinfo(
                      "Fixed Chunk Count",
                      "The transcript will be split into exactly this many chunks "
                      "(or fewer if the transcript is very short).\n\n"
                      "The program divides the total word count evenly across the "
                      "requested number of chunks.",
                      parent=win)
                  ).pack(side="left")
        self.fixed_chunk_info = tk.Label(fixed_frame, text="", fg="gray")
        self.fixed_chunk_info.pack(anchor="w")

        def _toggle_chunk_mode():
            if self.use_fixed_chunk_count.get():
                auto_frame.pack_forget()
                fixed_frame.pack(fill="x")
            else:
                fixed_frame.pack_forget()
                auto_frame.pack(fill="x")
            win.update_idletasks()
            win.geometry(f"{win.winfo_reqwidth()}x{win.winfo_reqheight()}")

        # Apply initial state
        if self.use_fixed_chunk_count.get():
            auto_frame.pack_forget()
            fixed_frame.pack(fill="x")
        else:
            fixed_frame.pack_forget()
            auto_frame.pack(fill="x")

        win.update_idletasks()
        needed_h = max(300, win.winfo_reqheight() + 12)
        needed_w = max(420, win.winfo_reqwidth() + 12)
        win.minsize(needed_w, needed_h)
        win.geometry(f"{needed_w}x{needed_h}")
        self.update_estimate()

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
        self.audio_path_label.config(
            text=os.path.basename(path) if path else "No file selected")
        if self.audio_path:
            audio = AudioSegment.from_file(self.audio_path)
            self.audio_duration_sec = len(audio) / 1000.0
        else:
            self.audio_duration_sec = 0

    def update_status(self, msg, color="black"):
        self.status_label.config(text=msg, fg=color)
        self.root.update_idletasks()

    def check_for_queue_restore(self):
        """On startup, check if there is a saved queue and offer to restore it."""
        saved = _load_queue_checkpoint()
        if not saved:
            return
        answer = messagebox.askyesno(
            "Restore Queue?",
            f"A saved queue was found with {len(saved)} item(s):\n\n" +
            "\n".join(
                f"  {i+1}. [{item.get('lang','?')}]  "
                f"{item.get('course','?')} / {item.get('lecture','?')}"
                for i, item in enumerate(saved[:5])
            ) +
            (f"\n  ... and {len(saved)-5} more" if len(saved) > 5 else "") +
            "\n\nWould you like to restore the queue?"
        )
        if answer:
            self._queue = collections.deque(saved)
            self._refresh_queue_listbox()
            self.update_status(
                f"✅ Queue restored — {len(saved)} item(s) ready.", "green")
        else:
            _clear_queue_checkpoint()

    def check_for_resume(self):
        checkpoint = load_last_checkpoint()
        if not checkpoint:
            return
        course      = checkpoint.get("course", "?")
        lecture     = checkpoint.get("lecture", "?")
        audio_path  = checkpoint.get("audio_path", None)
        last_offset = checkpoint.get("last_offset_sec", 0.0)

        resume = messagebox.askyesno(
            "Resume Found",
            f"Unfinished transcription detected:\n\n"
            f"📘 Course: {course}\n🎙 Lecture: {lecture}\n"
            f"⏱ Last position: {last_offset:.1f} sec\n\n"
            f"Do you want to resume from this point?"
        )
        if resume:
            self.course_entry.delete(0, tk.END)
            self.course_entry.insert(0, course)
            self.lecture_entry.delete(0, tk.END)
            self.lecture_entry.insert(0, lecture)
            self.audio_path = audio_path
            self.audio_path_label.config(
                text=os.path.basename(audio_path) if audio_path else "No file selected")
            global CURRENT_LECTURE_INFO
            CURRENT_LECTURE_INFO = {
                "course": course, "lecture": lecture, "audio_path": audio_path,
                "lang_mode": checkpoint.get("lang", self.lang_var.get()),
                "resume_offset_sec": last_offset,
            }
            threading.Thread(
                target=self.run_pipeline,
                kwargs={
                    "checkpoint":    checkpoint,
                    "course":        course,
                    "lecture":       lecture,
                    "audio_path":    audio_path,
                    "lang":          checkpoint.get("lang", self.lang_var.get()),
                    "restart":       False,
                    "resume_offset": last_offset,
                },
                daemon=True
            ).start()
        else:
            self.course_entry.delete(0, tk.END)
            self.lecture_entry.delete(0, tk.END)
            self.audio_path = None
            self.audio_path_label.config(text="No file selected")

    def resume_from_checkpoint(self, checkpoint):
        self.update_status("🔄 Resuming from checkpoint...", "green")
        try:
            self.run_pipeline()
        except Exception as e:
            messagebox.showerror("Resume Failed", str(e))

    def restart_lecture(self, course, lecture):
        from output_manager import _write_checkpoint_list, _read_checkpoint_list
        items = _read_checkpoint_list()
        items = [i for i in items if not (
            i.get("course") == course and i.get("lecture") == lecture)]
        _write_checkpoint_list(items)
        messagebox.showinfo("Restart",
                            f"Checkpoint cleared for {course}/{lecture}. Please start again.")

    def run_pipeline_threaded(self, checkpoint=None, **kwargs):
        threading.Thread(
            target=self.run_pipeline,
            kwargs=kwargs if checkpoint is None else {**kwargs, "checkpoint": checkpoint},
            daemon=True
        ).start()

    def run_pipeline(self, checkpoint=None, *, course=None, lecture=None,
                     audio_path=None, lang=None, restart=False, resume_offset=None):
        import traceback
        try:
            if checkpoint:
                course             = checkpoint.get("course", course)
                lecture            = checkpoint.get("lecture", lecture)
                audio_path         = checkpoint.get("audio_path", audio_path)
                lang_mode          = checkpoint.get("lang", lang or "Auto (Detect)")
                restart            = checkpoint.get("restart", restart)
                last_offset        = checkpoint.get("last_offset_sec", 0.0)
                threads_loaded     = checkpoint.get("threads", 4)
                
                _ckpt_chunk = checkpoint.get("chunk_token", 0)
                chunk_token_loaded = _ckpt_chunk if _ckpt_chunk > 500 else self.tokens
                beam_size_loaded   = checkpoint.get("beam_size", 2)
                resume_offset = resume_offset if resume_offset is not None else last_offset
                if not (course and lecture and audio_path):
                    messagebox.showerror("Checkpoint Error", "Missing info in checkpoint.")
                    return
                if restart:
                    self.update_status(f"🔄 Restarting {course}/{lecture}...", "green")
                else:
                    self.update_status(
                        f"▶ Resuming {course}/{lecture} from {resume_offset:.1f}s...", "green")
            else:
                course        = course or self.course_entry.get().strip()
                lecture       = lecture or self.lecture_entry.get().strip()
                audio_path    = audio_path or getattr(self, "audio_path", None)
                lang_mode     = lang or self.lang_var.get()
                resume_offset = resume_offset or 0.0
                threads_loaded = chunk_token_loaded = beam_size_loaded = None
                if not course or not lecture or not audio_path:
                    messagebox.showwarning(
                        "Missing Info",
                        "Please provide course name, lecture title, and audio file.")
                    return

            lecture_dir     = prepare_lecture_folder(course, lecture)
            transcript_path = os.path.join(lecture_dir, "final_transcript.txt")

            model_map      = {"Medium": "medium", "Small": "small",
                              "Base": "base", "Tiny": "tiny"}
            selected_model = model_map.get(self.whisper_model_display.get(), "medium")

            try:
                threads = max(1, int(self.asr_threads.get()))
            except Exception:
                threads = 4

            self.update_status(
                f"🎧 Transcribing with Faster-Whisper ({selected_model})...", "green")

            kwargs = {
                "lang_mode":       lang_mode,
                "model":           selected_model,
                "chunk_token":     chunk_token_loaded if checkpoint else self.tokens,
                "fixed_chunks":    None if (checkpoint or not self.use_fixed_chunk_count.get())
                                   else self.desired_chunks.get(),
                "gui_callback":    lambda msg: self.update_status(msg, "green"),
                "fw_device":       "cpu",
                "fw_compute_type": "int8",
                "fw_beam_size":    self.beam_size.get() if not checkpoint else beam_size_loaded,
                "fw_vad":          True,  
                "threads":         threads_loaded if checkpoint else threads,
                "course":          course,
                "lecture":         lecture,
                "resume_offset":   resume_offset,
                "fresh_start":     checkpoint is None,
            }

            if self.chunk_mode.get().lower() == "fixed":
                try:
                    kwargs["min_spacing_sec"] = max(30, int(self.chunk_minutes.get()) * 60)
                except Exception:
                    kwargs["min_spacing_sec"] = 60

            try:
                ar_text, en_text, transcript_metadata_json = transcribe_audio(
                    audio_path, **kwargs)
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Transcription Error", str(e))
                return

            self.update_status("💾 Transcription complete.", "black")
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(ar_text)
            clear_lecture_checkpoints(course=course, lecture=lecture)
            messagebox.showinfo("Done", "Lecture processed successfully.")

        except Exception as e:
            traceback.print_exc()

    def open_youtube_popup(self):
        try:
            from youtube_downloader import download_youtube_audio, YTDLP_AVAILABLE
        except ImportError:
            messagebox.showerror(
                "Module Not Found",
                "youtube_downloader.py was not found next to main_gui.py.\n\n"
                "Make sure you copied it into the same folder."
            )
            return

        course  = self.course_entry.get().strip()
        lecture = self.lecture_entry.get().strip()

        if not course or not lecture:
            messagebox.showwarning(
                "Missing Info",
                "Please fill in the Course Name and Lecture Title fields "
                "before opening the YouTube downloader.\n\n"
                "They will be used to name the output folder."
            )
            return

        if not YTDLP_AVAILABLE:
            messagebox.showerror(
                "yt-dlp Not Installed",
                "The yt-dlp library is required for YouTube downloads.\n\n"
                "Install it by running:\n    pip install yt-dlp"
            )
            return

        popup = tk.Toplevel(self.root)
        popup.title("YouTube → Transcribe")
        popup.geometry("520x340")
        popup.transient(self.root)
        popup.grab_set()
        popup.resizable(False, False)

        tk.Label(popup, text="🎬 YouTube Download & Transcribe",
                 font=("", 12, "bold")).pack(pady=(14, 4))
        tk.Label(popup,
                 text=f"Course:  {course}    |    Lecture:  {lecture}",
                 fg="gray").pack()
        tk.Label(popup,
                 text="\nPaste YouTube URL (public or unlisted):").pack(anchor="w", padx=20)

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
            except Exception:
                pass

        def _do_download_then(action):
            url = url_var.get().strip()
            if not url:
                messagebox.showwarning("No URL", "Please paste a YouTube URL first.",
                                       parent=popup)
                return
            dl_btn_start.config(state="disabled")
            dl_btn_queue.config(state="disabled")

            def _worker():
                try:
                    _update("⬇️  Connecting to YouTube...")
                    audio_path = download_youtube_audio(
                        url=url,
                        course=course,
                        lecture=lecture,
                        progress_callback=_update,
                    )
                    _update(f"✅ Audio saved.\n{audio_path}")

                    if action == "start":
                        self.audio_path = audio_path
                        self.audio_path_label.config(
                            text=f"[YouTube] {course} / {lecture}")
                        try:
                            from pydub import AudioSegment as _AS
                            self.audio_duration_sec = len(
                                _AS.from_file(audio_path)) / 1000.0
                        except Exception:
                            self.audio_duration_sec = 0
                        popup.destroy()
                        self.update_status(
                            f"🎧 Transcribing YouTube audio for {lecture}...", "green")
                        self.run_pipeline(
                            course=course,
                            lecture=lecture,
                            audio_path=audio_path,
                            lang=self.lang_var.get(),
                        )

                    else:  # action == "queue"
                        self._queue.append({
                            "course":      course,
                            "lecture":     lecture,
                            "audio_path":  audio_path,
                            "lang":        self.lang_var.get(),
                            "youtube":     True,
                            "url":         url,
                            "chunk_token": self.tokens,
                        })
                        _save_queue_checkpoint(list(self._queue))
                        self.root.after(0, self._refresh_queue_listbox)
                        popup.destroy()
                        self.update_status(
                            f"✅ Added to queue: {course} / {lecture}", "green")

                except Exception as exc:
                    _update(f"❌ Error: {exc}")
                    try:
                        dl_btn_start.config(state="normal")
                        dl_btn_queue.config(state="normal")
                    except Exception:
                        pass

            threading.Thread(target=_worker, daemon=True).start()

        btn_row = tk.Frame(popup); btn_row.pack(pady=8)
        dl_btn_start = tk.Button(
            btn_row, text="⬇️ Download & Start Now",
            bg="#1a73e8", fg="white", font=("", 10, "bold"),
            command=lambda: _do_download_then("start"))
        dl_btn_start.pack(side="left", padx=8)

        dl_btn_queue = tk.Button(
            btn_row, text="➕ Download & Add to Queue",
            bg="#1a7a1a", fg="white", font=("", 10, "bold"),
            command=lambda: _do_download_then("queue"))
        dl_btn_queue.pack(side="left", padx=8)

        tk.Label(
            popup,
            text="ℹ️  Works with public and unlisted videos.\n"
                 "Private or members-only videos cannot be downloaded.",
            fg="gray", font=("", 8), justify="center",
        ).pack(pady=(0, 10))

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