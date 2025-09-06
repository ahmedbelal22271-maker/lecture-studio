import gc
import json
import os
import threading
import sys
import contextlib
from datetime import datetime
from pydub import AudioSegment
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



@contextlib.contextmanager
def suppress_output():
    """Temporarily suppress stdout and stderr (for model repack messages)."""
    with open(os.devnull, "w") as devnull:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = devnull, devnull
            yield
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr



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
    resume_offset: int = 6,     # kept for API compatibility
    backtrack_sec: float = 30.0 # how many seconds to backtrack when trimming
):
    # Ensure the Lecture folder exists
    the_path_into_transcript_txt = prepare_lecture_folder(course, lecture)

    if not _transcribe_lock.acquire(blocking=False):
        raise RuntimeError("transcribe_audio already running")

    fw_model = None
    temp_audio_path = None
    base_offset_sec = 0.0  # where trimmed file starts in the original audio
    audio_trimmed = False

    try:
        device = fw_device or ("cuda" if HAS_TORCH else "cpu")
        compute_type = fw_compute_type or ("float16" if device != "cpu" else "int8")

        print("[INFO] Loading faster-whisper model...")
        with suppress_output():
            fw_model = WhisperModel(model, device=device, compute_type=compute_type)
        print("[INFO] Model loaded successfully.")

        # Load last checkpoint for this lecture/audio (lookup by original audio_path)
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
            # safety: if base_offset_sec >= duration, just start at 0
            duration_sec = len(full_audio) / 1000.0
            if base_offset_sec >= duration_sec:
                base_offset_sec = max(0.0, duration_sec - 1.0)
            start_ms = int(base_offset_sec * 1000)
            trimmed_audio = full_audio[start_ms:]
            # create unique temp file
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_audio_path = tmp.name
            tmp.close()
            trimmed_audio.export(temp_audio_path, format='wav')
            audio_path_to_use = temp_audio_path
            audio_trimmed = True

            print(f"[INFO] Audio trimmed:")
            print(f" previously saved offset {last_offset_sec:.2f}s")
        else:
            audio_path_to_use = audio_path
            audio_trimmed = False
            base_offset_sec = 0.0

        lang_map = {
            "Arabic": "ar",
            "English": "en",
            "French": "fr",
            "German": "de",
            "Auto (Detect)": None
            # extend if you expect more
        }
        lang_code = lang_map[lang_mode]  # fallback: use as-is

        # Transcribe audio (Faster-Whisper)
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
            #print(f"[DEBUG] Current all_segments:{all_segments}")
            # seg.start / seg.end are seconds relative to audio_path_to_use
            adj_start = float(seg.start) + base_offset_sec
            adj_end = float(seg.end) + base_offset_sec

            # Skip segments that end <= last saved offset (already processed)
            if checkpoint and (adj_end <= last_offset_sec + eps):
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
                extra={"segment_index": idx,
                        "text": (seg.text or "")[:300],
                        "threads":threads,
                        "chunk_token":chunk_token,
                        "model":model},
                max_age=10,
                full_text= all_segments
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




# --- Global abort flag ---
_abort_flag = False

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
