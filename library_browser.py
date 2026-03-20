import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import traceback

from output_manager import BASE_DIR, sanitize_filename, save_transcript_chunks

try:
    from fuzzywuzzy import fuzz
except ImportError:
    fuzz = None


class LibraryBrowser:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("📚 Course Library")
        self.window.geometry("900x600")
        self.window.transient(parent)
        
        self.paned = tk.PanedWindow(self.window, orient=tk.HORIZONTAL, sashwidth=4)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left Pane: File Tree
        self.tree_frame = tk.Frame(self.paned)
        self.tree = ttk.Treeview(self.tree_frame, selectmode="browse")
        self.tree_scroll = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scroll.set)
        
        self.tree_btn_frame = tk.Frame(self.tree_frame)
        self.tree_btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        tk.Button(self.tree_btn_frame, text="🪓 Re-chunk Selected Lecture", command=self.rechunk_transcript).pack(fill=tk.X)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)

        # Right Pane: Content Viewer
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
        """Scans the BASE_DIR and youtube_downloads to populate the Treeview."""
        # 1. Courses Directory
        if not os.path.exists(BASE_DIR):
            self.tree.insert("", tk.END, text="No courses found.")
        else:
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

        # 2. YouTube Downloads Directory
        yt_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_downloads")
        if os.path.exists(yt_dir):
            yt_root = self.tree.insert("", tk.END, text="YouTube Downloads", open=True)
            for course in sorted(os.listdir(yt_dir)):
                course_path = os.path.join(yt_dir, course)
                if os.path.isdir(course_path):
                    course_node = self.tree.insert(yt_root, tk.END, text=f"📘 {course}", open=False)
                    for lecture in sorted(os.listdir(course_path)):
                        lecture_path = os.path.join(course_path, lecture)
                        if os.path.isdir(lecture_path):
                            lecture_node = self.tree.insert(course_node, tk.END, text=f"🎙 {lecture}", open=False)
                            self._add_files_to_tree(lecture_node, lecture_path)

    def _is_transcript_like(self, filename: str) -> bool:
        """Checks if a filename is likely a transcript based on patterns or fuzzy matching."""
        name_lower = filename.lower()
        if not name_lower.endswith(".txt"):
            return False
            
        if "transcript" in name_lower:
            return True
        
        if fuzz:
            pure_name = os.path.splitext(name_lower)[0]
            if fuzz.partial_ratio("transcript", pure_name) >= 80:
                return True
        return False

    def rechunk_transcript(self):
        """Prompts user to re-chunk a transcript file, handling external files cleanly."""
        course, lecture = self._get_course_and_lecture_from_selection()
        
        if not course or not lecture:
            messagebox.showinfo("Select Lecture", "Please select a lecture (or a file inside it) from the tree first.", parent=self.window)
            return

        selected = self.tree.selection()[0]
        item_values = self.tree.item(selected, "values")
        
        lecture_path = os.path.join(BASE_DIR, sanitize_filename(course), sanitize_filename(lecture))
        if not os.path.exists(lecture_path):
            yt_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_downloads")
            lecture_path = os.path.join(yt_dir, sanitize_filename(course), sanitize_filename(lecture))

        target_file_path = None

        if item_values:
            potential_path = item_values[0]
            if self._is_transcript_like(os.path.basename(potential_path)):
                target_file_path = potential_path
        
        if not target_file_path and os.path.exists(lecture_path):
            files = [f for f in os.listdir(lecture_path) if os.path.isfile(os.path.join(lecture_path, f))]
            for f in sorted(files):
                if self._is_transcript_like(f):
                    target_file_path = os.path.join(lecture_path, f)
                    break

        if not target_file_path or not os.path.exists(target_file_path):
            messagebox.showwarning("Not Found", f"No transcript found in:\n{course} / {lecture}\n\nYou can only re-chunk available transcript files.", parent=self.window)
            return

        num_chunks = simpledialog.askinteger(
            "Re-chunk Transcript", 
            f"How many chunks do you want for '{os.path.basename(target_file_path)}'?", 
            parent=self.window, minvalue=1, maxvalue=999
        )
        
        if not num_chunks:
            return 
            
        try:
            with open(target_file_path, "r", encoding="utf-8") as f:
                full_text = f.read()
                
            fname_no_ext = os.path.splitext(os.path.basename(target_file_path))[0]
            chunks_folder_name = f"{fname_no_ext}_chunks"
            chunks_folder_path = os.path.join(os.path.dirname(target_file_path), chunks_folder_name)
            
            os.makedirs(chunks_folder_path, exist_ok=True)
            
            words = full_text.split()
            if words:
                chunk_size = max(1, -(-len(words) // num_chunks))
                chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
                
                for idx, chunk in enumerate(chunks, start=1):
                    file_path = os.path.join(chunks_folder_path, f"chunk_{idx}.txt")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(chunk)
                        
                messagebox.showinfo("Success", f"Transcript split into {len(chunks)} chunks!\nSaved in the '{chunks_folder_name}' folder.", parent=self.window)
            else:
                messagebox.showinfo("Warning", "The transcript is empty. No chunks were created.", parent=self.window)
            
            self.tree.delete(*self.tree.get_children())
            self.populate_tree()
            
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to re-chunk the transcript:\n{str(e)}", parent=self.window)

    def _add_files_to_tree(self, parent_node, path):
        """Recursively add files and folders to the tree."""
        for item in sorted(os.listdir(path)):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                folder_node = self.tree.insert(parent_node, tk.END, text=f"📂 {item}", open=False)
                self._add_files_to_tree(folder_node, item_path)
            elif item.endswith((".txt", ".json", ".md")):
                self.tree.insert(parent_node, tk.END, text=f"📄 {item}", values=(item_path,))
            elif item.endswith((".mp3", ".m4a", ".wav", ".webm", ".mp4")):
                self.tree.insert(parent_node, tk.END, text=f"🎵 {item}", values=(item_path,))

    def _get_course_and_lecture_from_selection(self):
        """Traverse up the tree to figure out the course and lecture of the selected item."""
        selected = self.tree.selection()
        if not selected: 
            return None, None
            
        item = selected[0]
        course = lecture = None
        
        while item:
            text = self.tree.item(item, "text")
            if text.startswith("🎙 "):
                lecture = text[2:]
            elif text.startswith("📘 "):
                course = text[2:]
            item = self.tree.parent(item)
            
        return course, lecture

    def on_item_select(self, event):
        """Triggered when a user clicks an item in the tree."""
        selected_item = self.tree.selection()
        if not selected_item:
            return

        item_values = self.tree.item(selected_item[0], "values")
        if item_values:
            self.display_file_content(item_values[0])
        else:
            self.text_viewer.config(state="normal")
            self.text_viewer.delete("1.0", tk.END)
            self.text_viewer.insert("1.0", "Select a text or markdown file to view its contents.")
            self.text_viewer.config(state="disabled")

    def display_file_content(self, file_path):
        """Read the file and display it in the text widget."""
        self.text_viewer.config(state="normal")
        self.text_viewer.delete("1.0", tk.END)
        
        if file_path.endswith((".mp3", ".m4a", ".wav", ".webm", ".mp4")):
            self.text_viewer.insert("1.0", f"🎵 Audio File: {os.path.basename(file_path)}\n\n(This is a media file and cannot be viewed as text.)")
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.text_viewer.insert("1.0", f.read())
            except Exception as e:
                self.text_viewer.insert("1.0", f"Error reading file:\n{str(e)}")
            
        self.text_viewer.config(state="disabled")