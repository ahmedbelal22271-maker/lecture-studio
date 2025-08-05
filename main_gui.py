# main_gui.py (Revised with Language Selector for Whisper + Mistral Shutdown Awareness)

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from whisper_offline import transcribe_audio, kill_whisper, set_abort_flag
from mistral_notes import generate_notes_from_transcript
from revision_generator import run_revision_pipeline
from output_manager import save_transcript

class LectureStudioGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Lecture Studio 2.0")
        self.root.geometry("500x550")
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.exit_button = tk.Button(root, text="🛑 Emergency Stop", fg="white", bg="red", command=self.shutdown)
        self.exit_button.pack(pady=5)

        tk.Label(root, text="📘 Course Name:").pack()
        self.course_entry = tk.Entry(root)
        self.course_entry.pack()

        tk.Label(root, text="🎙 Lecture Title:").pack()
        self.lecture_entry = tk.Entry(root)
        self.lecture_entry.pack()

        tk.Label(root, text="🌐 Audio Language:").pack(pady=5)
        self.lang_var = tk.StringVar(value="Arabic")
        self.lang_menu = tk.OptionMenu(root, self.lang_var, "Arabic", "English")
        self.lang_menu.pack()

        tk.Button(root, text="🎧 Choose Lecture Audio (.mp3)", command=self.browse_audio).pack(pady=5)
        self.audio_path_label = tk.Label(root, text="No file selected", fg="gray")
        self.audio_path_label.pack()

        self.rerank_var = tk.BooleanVar(value=True)
        self.revision_var = tk.BooleanVar(value=True)
        self.exam_notes_var = tk.BooleanVar(value=True)
        self.debug_mode_var = tk.BooleanVar(value=False)

        tk.Checkbutton(root, text="🔀 Re-rank chunks by importance", variable=self.rerank_var).pack(anchor='w', padx=20)
        tk.Checkbutton(root, text="🧠 Auto-generate revision summary", variable=self.revision_var).pack(anchor='w', padx=20)
        tk.Checkbutton(root, text="🎯 Include Exam Notes", variable=self.exam_notes_var).pack(anchor='w', padx=20)
        tk.Checkbutton(root, text="🧪 Enable Debugging Mode", variable=self.debug_mode_var).pack(anchor='w', padx=20)

        tk.Button(root, text="🚀 Start Processing", command=self.run_pipeline_threaded).pack(pady=10)
        tk.Button(root, text="📘 Generate Midterm Revision", command=self.run_revision).pack(pady=5)

        self.status_label = tk.Label(root, text="Waiting for input...", fg="blue")
        self.status_label.pack(pady=10)

    def browse_audio(self):
        file_path = filedialog.askopenfilename(filetypes=[("MP3 files", "*.mp3")])
        if file_path:
            self.audio_path = file_path
            self.audio_path_label.config(text=os.path.basename(file_path))
        else:
            self.audio_path = None
            self.audio_path_label.config(text="No file selected")

    def update_status(self, msg, color="black"):
        self.status_label.config(text=msg, fg=color)
        self.root.update_idletasks()

    def run_pipeline_threaded(self):
        thread = threading.Thread(target=self.run_pipeline)
        thread.start()

    def run_pipeline(self):
        course = self.course_entry.get().strip()
        lecture = self.lecture_entry.get().strip()
        lang_mode = self.lang_var.get()

        if not course or not lecture or not getattr(self, "audio_path", None):
            messagebox.showwarning("Missing Info", "Please provide course name, lecture title, and audio file.")
            return

        try:
            self.update_status("🎧 Transcribing audio with Whisper...", "green")
            ar_text, en_text, _ = transcribe_audio(self.audio_path, lang_mode)

            self.update_status("💾 Saving transcripts...", "black")
            save_transcript(ar_text, os.path.join("Lecture_Outputs", course.replace(" ", "_")))

            self.update_status("🧠 Generating notes with Mistral...", "purple")
            generate_notes_from_transcript(
                ar_text,
                course,
                lecture,
                rerank=self.rerank_var.get(),
                include_exam=self.exam_notes_var.get(),
                gui_callback=self.update_status,
                debug=self.debug_mode_var.get()
            )

            if self.revision_var.get():
                self.update_status("📘 Creating revision summary...", "blue")
                run_revision_pipeline(os.path.join("Lecture_Outputs", course.replace(" ", "_")))

            self.update_status("✅ All done!", "green")
            messagebox.showinfo("Done", "Lecture processed and notes saved successfully.")
        except Exception as e:
            self.update_status("❌ Error during processing", "red")
            messagebox.showerror("Error", str(e))

    def run_revision(self):
        course_name = self.course_entry.get().strip()
        if not course_name:
            messagebox.showwarning("Missing Course", "Please enter a course name to generate revision.")
            return

        course_dir = os.path.join("Lecture_Outputs", course_name.replace(" ", "_").lower())
        if not os.path.exists(course_dir) or not os.listdir(course_dir):
            messagebox.showinfo("No Data", f"There are no lecture notes yet for '{course_name}'.\nMidterm revision cannot be generated.")
            return

        try:
            revision_path = run_revision_pipeline(course_dir)
            messagebox.showinfo("Revision Complete", f"Midterm revision generated:\n{revision_path}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while generating revision:\n{str(e)}")

    def shutdown(self):
        print("[SHUTDOWN] User requested shutdown.")
        try:
            set_abort_flag()      # Signal Mistral to exit
            kill_whisper()        # Stop Whisper if it's still running
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
