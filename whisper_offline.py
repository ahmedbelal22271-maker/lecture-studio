import gc
import json
import os
import threading
import sys
import contextlib
import collections
import re as _re
import tempfile
from pydub import AudioSegment

# --- Local ffmpeg setup ---
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_FFMPEG_PATH  = os.path.join(_BASE_DIR, "ffmpeg-8.0-essentials_build", "bin", "ffmpeg.exe")
_FFPROBE_PATH = os.path.join(_BASE_DIR, "ffmpeg-8.0-essentials_build", "bin", "ffprobe.exe")
if os.path.isfile(_FFMPEG_PATH):
    AudioSegment.converter = _FFMPEG_PATH
    AudioSegment.ffmpeg    = _FFMPEG_PATH
    AudioSegment.ffprobe   = _FFPROBE_PATH
else:
    print(f"[WARNING] Local ffmpeg not found at {_FFMPEG_PATH}. Falling back to system PATH.")

from output_manager import (
    prepare_lecture_folder,
    append_to_cumulative_transcript,
    save_checkpoint_offset,
    load_last_checkpoint,
    compute_resume_start_sec,
    save_transcript_chunks,
)

# --- Faster-Whisper ---
try:
    from faster_whisper import WhisperModel
    FW_AVAILABLE = True
except Exception:
    WhisperModel = None
    FW_AVAILABLE = False

# --- Torch / CUDA ---
try:
    import torch
    HAS_TORCH = torch.cuda.is_available()
except Exception:
    torch = None
    HAS_TORCH = False

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
os.environ.setdefault("HF_HOME", r"C:\whisper_models")

_transcribe_lock = threading.Lock()
CHECKPOINT_FILE  = "whisper_checkpoint.json"

# --- Global abort flag ---
_abort_flag = False


@contextlib.contextmanager
def suppress_output():
    """Suppress stdout/stderr (used only during transcription, NOT model load)."""
    with open(os.devnull, "w") as devnull:
        old_out, old_err = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = devnull, devnull
            yield
        finally:
            sys.stdout, sys.stderr = old_out, old_err


# ---------------------------------------------------------------------------
# Hallucination filter (Static checks)
# ---------------------------------------------------------------------------
_HALLUCINATION_EXACT = {
    ".", "..", "...", "\u060c", "\u060c.", "\u061f", "!", ",", "-", "\u2013", "\u2014",
    "thank you.", "thank you", "thanks.", "thanks",
    "thanks for watching.", "thanks for watching",
    "please.", "please", "subscribe.", "subscribe",
    "like and subscribe.", "like and subscribe",
    "you", "you.", "bye.", "bye", "okay.", "okay", "ok.", "ok",
    "\u0634\u0643\u0631\u0627\u064b.", "\u0634\u0643\u0631\u0627\u064b",
    "\u0634\u0643\u0631\u0627.", "\u0634\u0643\u0631\u0627",
    "\u0634\u0643\u0631\u064b\u0627", "\u0634\u0643\u0631\u064b\u0627.",
    "\u0627\u0644\u0644\u0647.", "\u0627\u0644\u0644\u0647",
    "\u0646\u0639\u0645.", "\u0646\u0639\u0645",
    "\u062d\u0633\u0646\u064b\u0627.", "\u062d\u0633\u0646\u064b\u0627",
    # Subscribe-style hallucinations
    "\u0627\u0634\u062a\u0631\u0643\u0648\u0627 \u0641\u064a \u0627\u0644\u0642\u0646\u0627\u0629",
    "\u0627\u0634\u062a\u0631\u0643\u0648\u0627 \u0641\u064a \u0627\u0644\u0642\u0646\u0627\u0629.",
    "subscribe to the channel", "subscribe to the channel.",
    "like and subscribe to the channel", "like and subscribe to the channel.",
    "don\'t forget to subscribe", "don\'t forget to subscribe.",
}

_HALLUCINATION_PATTERNS = [
    _re.compile(r"^\s*[\.\u060c\,\!\?\-\u2013\u2014\u061f]+\s*$"),
    _re.compile(r"^\s*\[.*?\]\s*$"),
    _re.compile(r"^\s*\(.*?\)\s*$"),
    _re.compile(r"^(.)\1{3,}$"),
    _re.compile(r"^(\u0622\u0622\s*){2,}$"),
    _re.compile(r"^(\u0622\s*){4,}$"),
]


def _is_arabic_filler_loop(text: str) -> bool:
    tokens = text.strip().split()
    if len(tokens) < 4:
        return False
    filler = {"\u0622", "\u0622\u0622", "\u0622\u0622\u0622"}
    count = sum(1 for t in tokens if t.strip("\u060c.\u061f! ") in filler)
    return (count / len(tokens)) >= 0.6


# Phrases that are always hallucinations regardless of surrounding text
_HALLUCINATION_SUBSTRINGS = [
    "اشتركوا في القناة",  # اشتركوا في القناة
    "subscribe to the channel",
    "don't forget to subscribe",
    "like and subscribe",
]

def _is_hallucination(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t.lower() in _HALLUCINATION_EXACT:
        return True
    for pat in _HALLUCINATION_PATTERNS:
        if pat.match(t):
            return True
    if _is_arabic_filler_loop(t):
        return True
    # Check for known hallucination substrings (handles punctuation variants)
    t_lower = t.lower()
    for sub in _HALLUCINATION_SUBSTRINGS:
        if sub.lower() in t_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Main transcription function
# ---------------------------------------------------------------------------
def transcribe_audio(
    audio_path: str,
    lang_mode: str = "Arabic",
    chunk_token: int = 500,
    gui_callback=None,
    translate: bool = False,
    model: str = "medium",
    fw_device: str = None,
    fw_compute_type: str = None,
    fw_beam_size: int = 2,
    fw_vad: bool = False,
    course: str = None,
    lecture: str = None,
    threads: int = 4,
    resume_offset: int = 6,       # kept for API compatibility
    backtrack_sec: float = 30.0,  # seconds to backtrack when resuming
    fresh_start: bool = False,    # True = ignore saved checkpoint, always start from 0
    fixed_chunks: int = None,     # if set, split into exactly this many chunks instead of chunk_token
    run_suffix: str = "",         # version suffix for transcript file (e.g. '_2' for transcript_2.txt)
):
    # Guard: faster-whisper must be installed
    if not FW_AVAILABLE:
        raise RuntimeError(
            "faster-whisper is not installed.\n"
            "Run:  pip install faster-whisper"
        )

    # Reset abort flag at the start of every run.
    # Without this, any run after Emergency Stop is silently killed immediately.
    global _abort_flag
    _abort_flag = False

    prepare_lecture_folder(course, lecture)

    if not _transcribe_lock.acquire(blocking=False):
        raise RuntimeError("transcribe_audio is already running.")

    fw_model       = None
    temp_audio_path = None
    base_offset_sec = 0.0

    try:
        device       = fw_device       or ("cuda" if HAS_TORCH else "cpu")
        compute_type = fw_compute_type or ("float16" if device != "cpu" else "int8")

        print(f"[INFO] Loading faster-whisper model \'{model}\' on {device} ({compute_type})...")
        print("[INFO] If this is the first run, the model will be downloaded. Please wait...")
        if gui_callback:
            try:
                gui_callback(f"\u2b07\ufe0f Loading model \'{model}\'... (may download on first run)")
            except Exception:
                pass

        # Do NOT suppress output during model load — download progress must be visible
        fw_model = WhisperModel(model, device=device, compute_type=compute_type)
        print("[INFO] Model loaded successfully.")
        if gui_callback:
            try:
                gui_callback("\u2705 Model loaded. Starting transcription...")
            except Exception:
                pass

        # Checkpoint handling
        if fresh_start:
            checkpoint = None
            print("[INFO] fresh_start=True — ignoring any saved checkpoint.")
        else:
            checkpoint = load_last_checkpoint(
                course=course, lecture=lecture,
                audio_path=audio_path, lang=lang_mode,
            )
        last_offset_sec = float(checkpoint.get("last_offset_sec", 0.0)) if checkpoint else 0.0

        if checkpoint and last_offset_sec > 0.0:
            base_offset_sec = compute_resume_start_sec(checkpoint, backtrack_sec)
            print(f"[INFO] Resuming from {base_offset_sec:.2f}s (was at {last_offset_sec:.2f}s)")
        else:
            base_offset_sec = 0.0

        # Load the audio into memory ONCE to efficiently slice it across iterations
        print(f"[INFO] Preparing audio file to calculate duration and trim...")
        full_audio = AudioSegment.from_file(audio_path)
        total_duration_sec = len(full_audio) / 1000.0

        # Language mapping — use .get() to avoid KeyError on unexpected strings
        lang_map = {
            "Arabic":        "ar",
            "English":       "en",
            "French":        "fr",
            "German":        "de",
            "Auto (Detect)": None,
        }
        lang_code = lang_map.get(lang_mode, lang_mode if lang_mode else None)

        print(f"[INFO] beam_size={fw_beam_size}, lang={lang_code}")

        all_segments = checkpoint.get("full_text", []) if checkpoint else []
        transcript_metadata = []
        eps = 1e-3

        # We wrap the transcription process in a while loop so it can automatically
        # "restart" itself with a new offset if a hallucination loop is detected.
        loop_detected = True
        
        while loop_detected:
            loop_detected = False

            if base_offset_sec >= total_duration_sec:
                break

            # If we are offsetting, we create a temporary sliced audio file 
            # to feed Whisper a completely blank slate context.
            if base_offset_sec > 0.0:
                print(f"[INFO] Extracting audio slice from {base_offset_sec:.2f}s...")
                trimmed_audio = full_audio[int(base_offset_sec * 1000):]
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                temp_audio_path = tmp.name
                tmp.close()
                trimmed_audio.export(temp_audio_path, format="wav")
                audio_path_to_use = temp_audio_path
            else:
                audio_path_to_use = audio_path
                temp_audio_path = None

            if gui_callback:
                try:
                    gui_callback(f"🎧 Transcribing... (starting from {base_offset_sec:.1f}s)")
                except Exception:
                    pass

            # Transcribe — suppress only the CTranslate2 / ffmpeg internal noise
            with suppress_output():
                segments, info = fw_model.transcribe(
                    audio_path_to_use,
                    language=lang_code,
                    beam_size=fw_beam_size,
                    vad_filter=fw_vad,
                )

            # 🧠 RUNNING MEMORY: keeps track of the last 3 printed segments
            running_memory = collections.deque(maxlen=3)

            for idx, seg in enumerate(segments):
                # Because the audio might be a sliced temp file, we must shift the 
                # local segment times by our base_offset_sec to get absolute global times.
                adj_start = float(seg.start) + base_offset_sec
                adj_end   = float(seg.end)   + base_offset_sec

                # Skip already-processed segments (used during normal Resume)
                if checkpoint and (adj_end <= last_offset_sec + eps):
                    continue

                # 1. Static pattern drops (garbage text)
                if _is_hallucination(seg.text):
                    print(f"[FILTER] Dropped at {adj_start:.1f}s: {repr(seg.text)}")
                    continue

                if should_abort():
                    print("[ABORT] Transcription stopped by user.")
                    break

                # 2. 🛑 STRICT DYNAMIC HALLUCINATION REGULATION 🛑
                clean_text = seg.text.strip().lower()
                
                # Check if the running memory is full (3 items) AND the current segment matches all 3 of them
                if len(running_memory) == 3 and all(prev == clean_text for prev in running_memory):
                    print(f"\n[HALLUCINATION LOOP DETECTED] at {adj_end:.2f}s! Repeated segment: {repr(seg.text)}")
                    if gui_callback:
                        try: gui_callback(f"⚠️ Hallucination Loop at {adj_end:.1f}s! Breaking loop to restart...")
                        except Exception: pass
                    
                    # Force restart the transcription engine from slightly after this corrupted segment
                    # This clears Whisper's context and forces it to look at the next part with a blank slate
                    base_offset_sec = adj_end + 0.5 
                    loop_detected = True
                    break # Breaks the segment for-loop, concluding this transcribe() call to start fresh

                # Append to running memory for the next check
                running_memory.append(clean_text)

                # Append segment FIRST so the checkpoint's full_text is always complete
                seg_text = (seg.text or "").strip()
                all_segments.append(seg_text)
                transcript_metadata.append({"start": adj_start, "end": adj_end, "text": seg.text})
                append_to_cumulative_transcript(course, lecture, seg_text, "a", run_suffix=run_suffix)

                # Save checkpoint with the updated all_segments (now includes current segment)
                save_checkpoint_offset(
                    course=course, lecture=lecture,
                    audio_path=audio_path, lang=lang_mode,
                    last_offset_sec=adj_end,
                    extra={
                        "segment_index": idx,
                        "text":          seg_text[:300],
                        "threads":       threads,
                        "chunk_token":   chunk_token,
                        "model":         model,
                        "beam_size":     fw_beam_size,
                        "run_suffix":    run_suffix,
                    },
                    max_age=10,
                    full_text=all_segments,
                )
                
                # Update last_offset_sec manually so subsequent iterations in this run don't trigger the skip block
                last_offset_sec = adj_end

                output_text = f"[{adj_start:.2f}-{adj_end:.2f}s] {seg.text}"
                if gui_callback:
                    try:
                        if total_duration_sec > 0:
                            pct = min(100.0, (adj_end / total_duration_sec) * 100)
                            gui_callback(
                                f"🎧 {pct:.0f}%  [{adj_start:.0f}s → {adj_end:.0f}s]  {seg.text[:60]}"
                            )
                        else:
                            gui_callback(output_text)
                    except Exception:
                        pass
                print(output_text)

            # Cleanup the temporary sliced audio file before the next while loop iteration begins
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except Exception:
                    pass

            if should_abort():
                break

        full_text = "\n".join(all_segments)
        print("\n[INFO] Full transcript:\n")
        print(full_text)
        print("\n[INFO] End of transcript\n")

        save_transcript_chunks(
            course, lecture, full_text,
            chunk_size=chunk_token,
            fixed_chunks=fixed_chunks,
            run_suffix=run_suffix,
        )
        return full_text, full_text, json.dumps(transcript_metadata, ensure_ascii=False)

    finally:
        if fw_model:
            del fw_model
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except Exception:
                pass
        gc.collect()
        if _transcribe_lock.locked():
            _transcribe_lock.release()


def should_abort() -> bool:
    return _abort_flag


def set_abort_flag():
    global _abort_flag
    _abort_flag = True
    print("[INFO] Abort flag set. Whisper will stop at next safe point.")


def kill_whisper():
    set_abort_flag()