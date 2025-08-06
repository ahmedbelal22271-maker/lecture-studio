import json
import psutil
from datetime import datetime
import subprocess  # Allows us to run external programs like Whisper
import os           # File checking and filesystem operations
from tqdm import tqdm  # tqdm is used to display a progress bar in the terminal

# Global variable to keep track of Whisper's process
whisper_proc = None

# Global flag to interrupt long processing (Mistral later)
abort_flag = False

LANGUAGE_CODE_MAP = {
    "Arabic": "ar",
    "English": "en"
}

def transcribe_audio(audio_path, lang_mode="Arabic"):
    """
    Runs Whisper from the command line to transcribe an MP3 file in segments.

    Uses checkpoints and temp trimming to resume safely on crash/failure.

    Args:
        audio_path (str): Path to the input audio file.
        lang_mode (str): "Arabic" or "English".

    Returns:
        tuple: (transcript_text, english_placeholder, metadata_json)
    """
    global whisper_proc

    whisper_lang = LANGUAGE_CODE_MAP.get(lang_mode, "ar")

    # Checkpoint system
    checkpoint = load_whisper_checkpoint()
    if checkpoint and checkpoint["audio_path"] == audio_path:
        resume_from = checkpoint.get("last_offset_sec", 0)
        if resume_from > 0:
            audio_path = trim_audio_from_offset(audio_path, resume_from)
            print(f"[RESUME] Trimming audio from {resume_from} seconds")
    else:
        resume_from = 0

    segment_duration = 120  # seconds per chunk
    current_offset = resume_from
    part_index = 1
    combined_text = ""

    with tqdm(desc="[WHISPER] Transcription Progress", bar_format="{l_bar}{bar} {n_fmt} chunks") as pbar:
        while True:
            save_whisper_checkpoint(audio_path, lang_mode, current_offset)
            output_txt = f"transcript_part_{part_index:03}.txt"

            transcribe_cmd = [
                "whisper", audio_path,
                "--model", "medium",
                "--language", whisper_lang,
                "--task", "transcribe",
                "--output_format", "txt",
                "--output_dir", ".",
                "--fp16", "False",
                "--threads", "3"
            ]

            try:
                whisper_proc = subprocess.Popen(transcribe_cmd)
                whisper_proc.wait()
            except Exception as e:
                raise RuntimeError("Whisper failed to run") from e

            if not os.path.exists("transcript.txt"):
                raise RuntimeError("Expected Whisper output not found")

            os.rename("transcript.txt", output_txt)
            with open(output_txt, "r", encoding="utf-8") as f:
                combined_text += f.read().strip() + "\n"

            part_index += 1
            current_offset += segment_duration
            pbar.update(1)

            # TEMPORARY limit until full audio duration is implemented
            if current_offset > 600:
                break

    if os.path.exists("whisper_checkpoint.json"):
        os.remove("whisper_checkpoint.json")

    return combined_text, "", "{}"


def kill_whisper():
    """
    Stops Whisper process if it's still running. Called during emergency shutdown.
    """
    global whisper_proc
    if whisper_proc and whisper_proc.poll() is None:
        whisper_proc.terminate()

def set_abort_flag():
    """
    Signals other parts of the app (like Mistral processing) to stop early.
    """
    global abort_flag
    abort_flag = True

def should_abort():
    """
    Check whether an abort was requested. Called periodically in long loops.
    """
    return abort_flag
def save_whisper_checkpoint(audio_path, lang_mode, offset):
    checkpoint = {
        "audio_path": audio_path,
        "lang": lang_mode,
        "model": "medium",
        "last_offset_sec": offset,
        "timestamp": datetime.now().isoformat()
    }
    with open("whisper_checkpoint.json", "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)

def load_whisper_checkpoint():
    if os.path.exists("whisper_checkpoint.json"):
        with open("whisper_checkpoint.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def trim_audio_from_offset(original_path, offset_sec):
    trimmed_path = ".temp_resume_trim.mp3"
    cmd = [
        "ffmpeg", "-y", "-i", original_path,
        "-ss", str(offset_sec),
        "-acodec", "copy",
        trimmed_path
    ]
    subprocess.run(cmd, check=True)
    return trimmed_path
