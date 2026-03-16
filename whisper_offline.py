import gc
import json
import os
import threading
import sys
import contextlib
from datetime import datetime
from pydub import AudioSegment

# --- Local ffmpeg setup ---
# Point pydub to the bundled ffmpeg so it works without a system-wide install.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_FFMPEG_PATH = os.path.join(_BASE_DIR, "ffmpeg-8.0-essentials_build", "bin", "ffmpeg.exe")
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
    save_transcript_chunks
)
import tempfile


# --- Faster-Whisper ---
try:
    from faster_whisper import WhisperModel
    FW_AVAILABLE = True
except Exception:
    WhisperModel = None
    FW_AVAILABLE = False

# Torch check (for CUDA detection)
try:
    import torch
    HAS_TORCH = torch.cuda.is_available()
except Exception:
    torch = None
    HAS_TORCH = False

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

_transcribe_lock = threading.Lock()


# --- Checkpoint system ---
CHECKPOINT_FILE = "whisper_checkpoint.json"


# --- Global abort flag ---
# NOTE: Must be declared before transcribe_audio so it can be reset at the top of each run.
_abort_flag = False


@contextlib.contextmanager
def suppress_output():
    """Temporarily suppress stdout and stderr (e.g. for noisy transcription internals)."""
    with open(os.devnull, "w") as devnull:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = devnull, devnull
            yield
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr


# ---------------------------------------------------------------------------
# Hallucination filter
# ---------------------------------------------------------------------------
# Whisper commonly hallucinates on silence or low-SNR audio, producing
# repetitive garbage like ".", "...", "Thank you.", "Thanks for watching.",
# single punctuation characters, or music/noise tokens like "[Music]".
# This filter drops any segment that matches these known patterns so they
# never reach the transcript.

import re as _re

_HALLUCINATION_EXACT = {
    # Punctuation-only variants (all languages)
    ".", "..", "...", "،", "،.", "؟", "!", ",", "-", "–", "—",
    # Common English hallucinations
    "thank you.", "thank you", "thanks.", "thanks",
    "thanks for watching.", "thanks for watching",
    "please.", "please", "subscribe.", "subscribe",
    "like and subscribe.", "like and subscribe",
    "you", "you.", "bye.", "bye", "okay.", "okay", "ok.", "ok",
    # Common Arabic hallucinations
    "شكراً.", "شكراً", "شكرا.", "شكرا", "شكرًا", "شكرًا.",
    "الله.", "الله", "نعم.", "نعم", "حسناً.", "حسناً",
}

_HALLUCINATION_PATTERNS = [
    _re.compile(r"^\s*[\.\،\,\!\?\-\–\—\؟]+\s*$"),          # pure punctuation
    _re.compile(r"^\s*\[.*?\]\s*$"),                           # tokens like [Music] [Noise]
    _re.compile(r"^\s*\(.*?\)\s*$"),                           # tokens like (silence)
    _re.compile(r"^(.){3,}$"),                               # same char repeated 4+ times
]

def _is_hallucination(text: str) -> bool:
    """
    Return True if the segment text looks like a Whisper hallucination.
    Only checks for known garbage patterns — no duration/length heuristics
    so legitimate long technical terms are never accidentally filtered.
    """
    t = (text or "").strip()
    if not t:
        return True
    if t.lower() in _HALLUCINATION_EXACT:
        return True
    for pat in _HALLUCINATION_PATTERNS:
        if pat.match(t):
            return True
    return False


def transcribe_audio(
    audio_path: str,
    lang_mode: str = 'Arabic',
    chunk_token: int = 500,
    gui_callback=None,
    translate: bool = False,
    model: str = "medium",
    fw_device: str = None,
    fw_compute_type: str = None,
    fw_beam_size: int = 1,
    fw_vad: bool = False,
    course: str = None,
    lecture: str = None,
    threads: int = 4,
    resume_offset: int = 6,      # kept for API compatibility
    backtrack_sec: float = 30.0, # how many seconds to backtrack when trimming
    fresh_start: bool = False,   # if True, ignore any saved checkpoint and start from 0
):
    # --- FIX 1: Check faster-whisper is actually installed before doing anything ---
    if not FW_AVAILABLE:
        raise RuntimeError(
            "faster-whisper is not installed.\n"
            "Run:  pip install faster-whisper"
        )

    # --- FIX 2: Reset abort flag at the start of every new run ---
    # Without this, any run after an Emergency Stop would be silently killed immediately.
    global _abort_flag
    _abort_flag = False

    # Ensure the Lecture folder exists
    the_path_into_transcript_txt = prepare_lecture_folder(course, lecture)

    if not _transcribe_lock.acquire(blocking=False):
        raise RuntimeError("transcribe_audio is already running.")

    fw_model = None
    temp_audio_path = None
    base_offset_sec = 0.0  # where trimmed file starts in the original audio
    audio_trimmed = False

    try:
        device = fw_device or ("cuda" if HAS_TORCH else "cpu")
        compute_type = fw_compute_type or ("float16" if device != "cpu" else "int8")

        # --- FIX 3: Do NOT suppress output during model loading ---
        # The model may need to be downloaded (~hundreds of MB to ~1.5 GB depending on size).
        # Suppressing stdout/stderr here made the app appear completely frozen with no feedback.
        print(f"[INFO] Loading faster-whisper model '{model}' on {device} ({compute_type})...")
        print("[INFO] If this is the first run, the model will be downloaded now. Please wait...")
        if gui_callback:
            try:
                gui_callback(f"⬇️ Loading model '{model}'... (may download on first run)")
            except Exception:
                pass

        fw_model = WhisperModel(model, device=device, compute_type=compute_type)
        print("[INFO] Model loaded successfully.")
        if gui_callback:
            try:
                gui_callback("✅ Model loaded. Starting transcription...")
            except Exception:
                pass

        # Load last checkpoint — skipped entirely when fresh_start=True so that
        # a new run never accidentally resumes from a leftover checkpoint.
        if fresh_start:
            checkpoint = None
            print("[INFO] fresh_start=True — ignoring any saved checkpoint.")
            if gui_callback:
                try:
                    gui_callback("🆕 Starting fresh — ignoring any previous checkpoint.")
                except Exception:
                    pass
        else:
            checkpoint = load_last_checkpoint(
                course=course,
                lecture=lecture,
                audio_path=audio_path,
                lang=lang_mode
            )
        last_offset_sec = float(checkpoint.get('last_offset_sec', 0.0)) if checkpoint else 0.0

        # Compute base_offset_sec: backtrack a bit before last saved offset
        if checkpoint and last_offset_sec > 0.0:
            base_offset_sec = compute_resume_start_sec(checkpoint, backtrack_sec)
            # Trim audio starting at base_offset_sec
            full_audio = AudioSegment.from_file(audio_path)
            # Safety: if base_offset_sec >= duration, just start at 0
            duration_sec = len(full_audio) / 1000.0
            if base_offset_sec >= duration_sec:
                base_offset_sec = max(0.0, duration_sec - 1.0)
            start_ms = int(base_offset_sec * 1000)
            trimmed_audio = full_audio[start_ms:]
            # Create unique temp file
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_audio_path = tmp.name
            tmp.close()
            trimmed_audio.export(temp_audio_path, format='wav')
            audio_path_to_use = temp_audio_path
            audio_trimmed = True

            print(f"[INFO] Audio trimmed: resuming from {base_offset_sec:.2f}s "
                  f"(previously saved offset was {last_offset_sec:.2f}s)")
        else:
            base_offset_sec = 0.0
            # Always convert non-WAV files (e.g. M4A, MP3) to WAV before passing to Whisper.
            # M4A uses AAC with a variable-bitrate container whose timestamps can drift when
            # decoded on-the-fly by faster-whisper, causing segments in the middle to be silently
            # skipped. Exporting to PCM WAV first gives Whisper clean, reliable timestamps.
            ext = os.path.splitext(audio_path)[1].lower()
            if ext != ".wav":
                if gui_callback:
                    try:
                        gui_callback("🔄 Converting audio to WAV for accurate timestamps...")
                    except Exception:
                        pass
                print(f"[INFO] Converting {ext} → WAV for reliable timestamp alignment...")
                full_audio = AudioSegment.from_file(audio_path)
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                temp_audio_path = tmp.name
                tmp.close()
                full_audio.export(temp_audio_path, format="wav")
                audio_path_to_use = temp_audio_path
                audio_trimmed = True
                print(f"[INFO] Conversion complete. Temporary WAV: {temp_audio_path}")
            else:
                audio_path_to_use = audio_path
                audio_trimmed = False

        lang_map = {
            "Arabic":       "ar",
            "English":      "en",
            "French":       "fr",
            "German":       "de",
            "Auto (Detect)": None,
        }
        # --- FIX 4: Use .get() with a safe fallback instead of a bare key lookup ---
        # A bare lang_map[lang_mode] raises KeyError for any unexpected language string.
        lang_code = lang_map.get(lang_mode, lang_mode if lang_mode else None)

        # Transcribe audio (Faster-Whisper)
        # Only suppress output here (internal CTranslate2 / ffmpeg noise), NOT during model load.
        with suppress_output():
            segments, info = fw_model.transcribe(
                audio_path_to_use,
                language=lang_code,
                beam_size=fw_beam_size,
                vad_filter=fw_vad
            )

        all_segments = checkpoint.get("full_text", []) if checkpoint else []
        transcript_metadata = []
        eps = 1e-3  # small tolerance for float compares

        for idx, seg in enumerate(segments):
            # seg.start / seg.end are seconds relative to audio_path_to_use
            adj_start = float(seg.start) + base_offset_sec
            adj_end   = float(seg.end)   + base_offset_sec

            # Skip segments that end <= last saved offset (already processed)
            if checkpoint and (adj_end <= last_offset_sec + eps):
                continue

            # Drop hallucinated segments (silence artifacts, punctuation loops, etc.)
            if _is_hallucination(seg.text):
                print(f"[FILTER] Hallucination dropped at {adj_start:.1f}s: {repr(seg.text)}")
                continue

            if should_abort():
                print("[ABORT] Transcription stopped by user.")
                break

            # Save checkpoint with absolute offset (original file seconds)
            save_checkpoint_offset(
                course=course,
                lecture=lecture,
                audio_path=audio_path,   # always store original audio path in checkpoints
                lang=lang_mode,
                last_offset_sec=adj_end,
                extra={
                    "segment_index": idx,
                    "text":          (seg.text or "")[:300],
                    "threads":       threads,
                    "chunk_token":   chunk_token,
                    "model":         model,
                    "beam_size":     fw_beam_size,
                },
                max_age=10,
                full_text=all_segments
            )

            # Output (GUI + terminal)
            output_text = f"[{adj_start:.2f}-{adj_end:.2f}s] {seg.text}"
            if gui_callback:
                try:
                    gui_callback(output_text)
                except Exception:
                    pass
            print(output_text)

            # Append only the raw segment text to cumulative transcript (one line per segment)
            append_to_cumulative_transcript(course, lecture, (seg.text or "").strip(), "a")

            # Collect for final return
            all_segments.append((seg.text or "").strip())
            transcript_metadata.append({"start": adj_start, "end": adj_end, "text": seg.text})

        # Final combined text returned to caller
        full_text = "\n".join(all_segments)
        print("\n[INFO] Full transcript:\n")
        print(full_text)
        print("\n[INFO] End of transcript\n")

        save_transcript_chunks(course, lecture, full_text, chunk_size=chunk_token)

        return full_text, full_text, json.dumps(transcript_metadata, ensure_ascii=False)

    finally:
        # Cleanup
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
    """Check if transcription should be aborted."""
    return _abort_flag


def set_abort_flag():
    """Set the abort flag to True, signaling transcription to stop."""
    global _abort_flag
    _abort_flag = True
    print("[INFO] Abort flag set. Whisper will stop at next safe point.")


def kill_whisper():
    """Alias for stopping the transcription."""
    set_abort_flag()