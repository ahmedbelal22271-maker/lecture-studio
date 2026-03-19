# output_manager.py (Updated with Lecture Metadata & Course Memory Handling)

import os
import json
from datetime import datetime
from typing import List, Dict, Optional

BASE_DIR = "courses"  # Base folder for storing course data
CHECKPOINT_FILE = "whisper_checkpoint.json"


def _safe_name(x: str, fallback: str) -> str:
    """Normalize names for filesystem use."""
    if not x:
        return fallback
    x = str(x).strip().replace(os.sep, "_")
    return x or fallback


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe as a folder/file name."""
    if not name:
        return "untitled"
    return "_".join(str(name).strip().lower().split())


def ensure_course_lecture_dirs(course: str, lecture: str):
    """Ensure that directories for a course and lecture exist."""
    course_dir = os.path.join(BASE_DIR, sanitize_filename(course))
    lecture_dir = os.path.join(course_dir, sanitize_filename(lecture))
    os.makedirs(lecture_dir, exist_ok=True)
    return course_dir, lecture_dir


def save_notes_markdown(notes_list, course, lecture):
    """Save a list of notes to notes.md for a specific lecture."""
    _, lecture_dir = ensure_course_lecture_dirs(course, lecture)
    file_path = os.path.join(lecture_dir, "notes.md")
    with open(file_path, "w", encoding="utf-8") as f:
        for _, content in notes_list:
            f.write(content + "\n\n")


def save_lecture_metadata(course, lecture, lecture_metadata):
    """Save chunk metadata for a lecture as JSON."""
    _, lecture_dir = ensure_course_lecture_dirs(course, lecture)
    file_path = os.path.join(lecture_dir, "lecture_metadata.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(lecture_metadata, f, indent=2, ensure_ascii=False)


def load_lecture_metadata(course, lecture):
    """Load chunk metadata for a lecture; return empty list if not found."""
    _, lecture_dir = ensure_course_lecture_dirs(course, lecture)
    file_path = os.path.join(lecture_dir, "lecture_metadata.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_course_memory(course, course_memory):
    """Save aggregated course memory for inter-lecture linking."""
    course_dir = os.path.join(BASE_DIR, sanitize_filename(course))
    os.makedirs(course_dir, exist_ok=True)
    file_path = os.path.join(course_dir, "course_memory.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(course_memory, f, indent=2, ensure_ascii=False)


def load_course_memory(course):
    """Load course-level memory; return empty dict if not found."""
    course_dir = os.path.join(BASE_DIR, sanitize_filename(course))
    file_path = os.path.join(course_dir, "course_memory.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------- folders ----------
def prepare_lecture_folder(course_name: str, lecture_name: str) -> str:
    """Create and return the path to courses/<course>/<lecture>."""
    if not course_name or not lecture_name:
        raise ValueError("[ERROR] Both course_name and lecture_name must be provided")
    course_dir = os.path.join(BASE_DIR, sanitize_filename(course_name))
    lecture_dir = os.path.join(course_dir, sanitize_filename(lecture_name))
    os.makedirs(lecture_dir, exist_ok=True)
    return lecture_dir


def append_to_cumulative_transcript(course_name: str, lecture_name: str, text: str, mode: str = "a", run_suffix: str = "") -> str:
    """Append a single segment (one line) to the rolling transcript file for the lecture.
    run_suffix allows versioning: '' -> transcript.txt, '_2' -> transcript_2.txt, etc.
    """
    if mode == "a":
        base_dir = prepare_lecture_folder(course_name, lecture_name)
        transcript_path = os.path.join(base_dir, f"transcript{run_suffix}.txt")
        with open(transcript_path, "a", encoding="utf-8") as f:
            f.write((text or "").rstrip() + "\n")
        return transcript_path

# ---------- checkpoints (offset-only primary) ----------
def _read_checkpoint_list() -> List[Dict]:
    if not os.path.exists(CHECKPOINT_FILE):
        return []
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else [data]
    except Exception:
        return []


def _write_checkpoint_list(items: List[Dict], max_age: int = 2000) -> None:
    """Write checkpoint list atomically (temp file + replace) and keep bounded history."""
    items = items[-max_age:]  # keep it bounded
    tmp_path = CHECKPOINT_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            # os.fsync may not be available on all platforms; ignore if so
            pass
    os.replace(tmp_path, CHECKPOINT_FILE)


def save_checkpoint_offset(
    *,
    course: str,
    lecture: str,
    audio_path: str,
    lang: str,
    last_offset_sec: float,
    extra: dict | None = None,
    max_age: int = 10,
    full_text: list = []
) -> dict:
    """
    Append a checkpoint record focused on absolute time offset.
    Optional `extra` can hold secondary info (segment_index, text snippet, etc.).
    """
    entry = {
        "course": course,
        "lecture": lecture,
        "audio_path": audio_path,
        "lang": lang,
        "last_offset_sec": float(last_offset_sec),
        "timestamp": datetime.now().isoformat(),
        "full_text": full_text
    }
    if isinstance(extra, dict):
        entry.update(extra)

    items = _read_checkpoint_list()
    items.append(entry)
    _write_checkpoint_list(items, max_age=max_age)
    return entry


def load_last_checkpoint(
    *,
    course: str | None = None,
    lecture: str | None = None,
    audio_path: str | None = None,
    lang: str | None = None
) -> Optional[dict]:
    """
    Return the latest checkpoint that matches the provided filters (if any).
    If nothing matches, returns None.
    """
    items = _read_checkpoint_list()
    if not items:
        return None

    # Apply filters progressively (course/lecture/audio_path/lang)
    def ok(e: dict) -> bool:
        if course and e.get("course") != course:
            return False
        if lecture and e.get("lecture") != lecture:
            return False
        if audio_path and e.get("audio_path") != audio_path:
            return False
        if lang and e.get("lang") != lang:
            return False
        return True

    filtered = [e for e in items if ok(e)]
    return filtered[-1] if filtered else None


def compute_resume_start_sec(checkpoint: dict | None, backtrack_sec: float = 5.0) -> float:
    """
    From a checkpoint, compute the resume start in SECONDS (not milliseconds).
    Backtracks `backtrack_sec` seconds to give overlap.
    Returns a float (seconds).
    """
    if not checkpoint:
        return 0.0
    last_off = float(checkpoint.get("last_offset_sec", 0.0))
    resume_sec = max(0.0, last_off - float(backtrack_sec))
    return float(resume_sec)

# ---------- chunk saving ----------

def save_transcript_chunks(course, lecture, full_text, chunk_size=500, fixed_chunks=None, run_suffix=""):
    """
    Split transcript into word-based chunks and save each chunk.

    Args:
        course (str):        Course name
        lecture (str):       Lecture name
        full_text (str):     Final transcript text
        chunk_size (int):    Number of words per chunk (used when fixed_chunks is None)
        fixed_chunks (int):  If provided, split into exactly this many equal chunks
                             instead of using chunk_size.
        run_suffix (str):    Version suffix that mirrors the transcript filename.
                             e.g. '' -> _chunks folder, '_2' -> _chunks_2 folder.
                             This ensures transcript_2.txt gets its own _chunks_2 folder.
    """
    words = full_text.split()
    if not words:
        print("[INFO] Transcript is empty — no chunks to save.")
        return

    if fixed_chunks and fixed_chunks > 0:
        # Divide evenly into exactly fixed_chunks pieces
        chunk_size = max(1, -(-len(words) // fixed_chunks))  # ceiling division
        print(f"[INFO] Fixed chunk mode: {fixed_chunks} chunks requested, "
              f"{chunk_size} words/chunk ({len(words)} total words)")

    chunks = [
        " ".join(words[i:i+chunk_size])
        for i in range(0, len(words), chunk_size)
    ]

    # Folder name mirrors the transcript version:
    #   transcript.txt   -> {course}_{lecture}_chunks
    #   transcript_2.txt -> {course}_{lecture}_chunks_2
    folder_name = f"{sanitize_filename(course)}_{sanitize_filename(lecture)}_chunks{run_suffix}"
    path_to_chunks_folder = os.path.join(
        BASE_DIR, sanitize_filename(course), sanitize_filename(lecture), folder_name
    )
    os.makedirs(path_to_chunks_folder, exist_ok=True)

    for idx, chunk in enumerate(chunks, start=1):
        file_path = os.path.join(path_to_chunks_folder, f"chunk_{idx}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(chunk)

    print(f"[INFO] Saved {len(chunks)} chunk(s) into {folder_name}")

def clear_lecture_checkpoints(course: str, lecture: str, run_suffix: str = ""):
    """Delete Whisper checkpoints for a given course/lecture (and optionally a specific run suffix)."""
    items = _read_checkpoint_list()
    def _should_remove(i):
        if i.get("course") != course or i.get("lecture") != lecture:
            return False
        # If run_suffix is specified, only remove checkpoints for that specific run
        if run_suffix:
            return i.get("run_suffix", "") == run_suffix
        return True
    filtered = [i for i in items if not _should_remove(i)]
    _write_checkpoint_list(filtered)