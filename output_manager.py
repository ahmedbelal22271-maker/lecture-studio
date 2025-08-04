# output_manager.py

import os
from datetime import datetime

def sanitize_filename(name):
    return "_".join(name.strip().lower().split())

def create_output_paths(base_dir, course_name, lecture_title):
    course_dir = os.path.join(base_dir, sanitize_filename(course_name))
    lecture_dir = os.path.join(course_dir, sanitize_filename(lecture_title))

    os.makedirs(lecture_dir, exist_ok=True)
    return lecture_dir

def save_transcript(transcript_text, lecture_dir, lang="en"):
    filename = f"transcript_{lang}.txt"
    path = os.path.join(lecture_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(transcript_text)
    return path

def save_notes_markdown(notes_text, lecture_dir):
    path = os.path.join(lecture_dir, "notes.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(notes_text)
    return path

def save_log(message, lecture_dir):
    log_path = os.path.join(lecture_dir, "processing_log.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

def list_all_notes(course_dir):
    """Return paths to all notes.md under a given course folder."""
    notes = []
    for root, _, files in os.walk(course_dir):
        for f in files:
            if f == "notes.md":
                notes.append(os.path.join(root, f))
    return sorted(notes)
