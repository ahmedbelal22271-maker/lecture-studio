# main_gui.py (With Midterm Revision Button)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ModuleNotFoundError:
    print("[ERROR] tkinter is not installed or not available in this environment.")
    print("This GUI cannot run without tkinter. Please install it or use a compatible environment.")
    exit(1)

import os
from revision_generator import run_revision_pipeline
from output_manager import create_output_paths

class LectureStudioGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Lecture Studio 2.0")
        self.root.geometry("500x450")

        # Course Name
        tk.Label(root, text="📘 Course Name:").pack(pady=5)
        self.course_entry = tk.Entry(root, width=40)
        self.course_entry.pack()

        # Lecture Title
        tk.Label(root, text="🎙 Lecture Title:").pack(pady=5)
        self.lecture_entry = tk.Entry(root, width=40)
        self.lecture_entry.pack()

        # MP3 File Picker
        tk.Button(root, text="🎧 Choose Lecture Audio (.mp3)", command=self.browse_audio).pack(pady=10)
        self.audio_path_label = tk.Label(root, text="No file selected", fg="gray")
        self.audio_path_label.pack()

        # Processing Options
        self.rerank_var = tk.BooleanVar(value=True)
        self.revision_var = tk.BooleanVar(value=True)

        tk.Checkbutton(root, text="🔀 Re-rank chunks by importance", variable=self.rerank_var).pack(anchor='w', padx=20)
        tk.Checkbutton(root, text="🧠 Auto-generate revision summary", variable=self.revision_var).pack(anchor='w', padx=20)

        # Start Button
        tk.Button(root, text="🚀 Start Processing", command=self.run_pipeline).pack(pady=10)

        # Midterm Revision Button
        tk.Button(root, text="📘 Generate Midterm Revision", command=self.run_revision).pack(pady=5)

        # Status
        self.status_label = tk.Label(root, text="Waiting for input...", fg="blue")
        self.status_label.pack(pady=10)

    def browse_audio(self):
        file_path = filedialog.askopenfilename(filetypes=[("MP3 files", "*.mp3")])
        if file_path:
            self.audio_path = file_path
            self.audio_path_label.config(text=file_path.split("/")[-1])
        else:
            self.audio_path = None
            self.audio_path_label.config(text="No file selected")

    def run_pipeline(self):
        # Placeholder only — real logic will be injected here
        messagebox.showinfo("Not Yet Wired", "Pipeline logic will be connected soon.")

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

if __name__ == "__main__":
    root = tk.Tk()
    app = LectureStudioGUI(root)
    root.mainloop()
