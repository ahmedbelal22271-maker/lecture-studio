# whisper_offline.py

import subprocess
import os

def transcribe_audio(audio_path):
    """Run Whisper offline and return Arabic + English transcript and JSON"""

    # Arabic Transcription
    ar_txt = "transcript_ar.txt"
    ar_json = "transcript_ar.json"

    transcribe_cmd = [
        "whisper", audio_path,
        "--model", "medium",
        "--language", "Arabic",
        "--task", "transcribe",
        "--output_format", "txt,json",
        "--output_dir", ".",
        "--fp16", "False"
    ]

    subprocess.run(transcribe_cmd, check=True)

    # English Translation
    en_txt = "transcript_en.txt"

    translate_cmd = [
        "whisper", audio_path,
        "--model", "medium",
        "--language", "Arabic",
        "--task", "translate",
        "--output_format", "txt",
        "--output_dir", ".",
        "--fp16", "False"
    ]

    subprocess.run(translate_cmd, check=True)

    # Load results
    with open(ar_txt, "r", encoding="utf-8") as f:
        transcript_ar = f.read()

    with open(ar_json, "r", encoding="utf-8") as f:
        transcript_json = f.read()

    with open(en_txt, "r", encoding="utf-8") as f:
        transcript_en = f.read()

    return transcript_ar, transcript_en, transcript_json
