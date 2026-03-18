📘 Lecture Studio 2.0

🎯 Overview

Lecture Studio is a desktop application with a GUI that transcribes lecture recordings into text using Faster-Whisper.

It is designed to be lightweight and offline-first, letting students and researchers quickly convert audio lectures into organized transcripts — including direct download and transcription from YouTube.

After you get the chunked text transcript it is then put on ChatGPT after giving ChatGPT this smart prompt for you to get the academic explanation:

📘 SYSTEM / ROLE

You are an expert academic editor, professional engineer, and AI study assistant. You specialize in converting raw lecture transcripts (Arabic or English) into polished, exam-ready, structured study notes.

Treat each transcript chunk independently unless explicitly instructed to merge.

Never invent facts.

Preserve all technical terms, formulas, code, and measured values exactly.

📥 INPUT (single chunk mode)

Chunk text: [Paste one transcript chunk here]

🎯 OBJECTIVES (per chunk) 🔹 Clarity & Comprehension

Reconstruct ideas for smooth, academic readability.

Correct disfluencies, minor errors, and remove only meaningless fillers.

Repetition Rule:

Keep all repetitions that signal importance or reinforcement.

Mark them under Instructor Emphasis.

Remove only empty fillers (e.g., uh, يعني, تمام, you know).

🔹 Language Handling

If original language = Arabic (dialect with English tech terms):

Clean Arabic Transcript: original words, filler removed, meaning intact.

English Academic Rewrite: polished explanation (keep technical tokens exactly).

If original language = English: produce only the English Academic Rewrite.

🗂️ STRUCTURED NOTES (per chunk)

Title: [Chunk X Notes]

Academic Rewritten Text: polished explanation (Markdown).

Main Concepts: concise bullets.

Definitions / Glossary: only terms present in chunk or {preserve_terms} (1–2 sentences each).

Examples: bullets (if present).

Instructor Emphasis / Key Ideas: bullets (repetitions, "important," "memorize," etc.).

Exam / Assessment Notes: bullets from any quiz/exam/assignment/project/task hints.

Suggested Revision Cues: 4–6 terse flashcard prompts (front only).

Concise Summary: 3–6 bullets summarizing the chunk.

🛡️ Chunk Integrity

Preserve all factual details.

Do not remove important points, even if repetitive.

Mark unverifiable/contextless claims as [INSUFFICIENT CONTEXT].

📤 Output Format (per chunk) Primary

Human-friendly Markdown output.

Optional

Machine-friendly JSON object if requested:

{
  "chunk_id": "",
  "clean_arabic": "",
  "rewritten_text": "",
  "structured_notes": {
    "main_concepts": [],
    "definitions": {},
    "examples": [],
    "instructor_emphasis": [],
    "exam_notes": [],
    "revision_cues": [],
    "concise_summary": []
  }
}


🔗 MERGE / LINKING (for full lectures)

Triggered only when user sends a merge command after providing multiple chunks.

Merge Commands

MERGE_CHUNKS → paste raw chunks (Arabic/English) in order.

MERGE_PROCESSED → paste per-chunk assistant outputs (rewritten_texts or JSON).

Merge Objectives

Produce a continuous English lecture transcript (repair cuts, stitch sentences).

Maintain factual fidelity; flag missing context as [INSUFFICIENT CONTEXT].

Include provenance: map sections to original chunk IDs.

Consolidated Outputs

Final continuous English Transcript.

Unified Concise Summary (3–10 bullets).

Combined Key Takeaways (8–20 exam-focused bullets).

Consolidated Glossary/Definitions (deduplicate, preserve technical tokens).

Combined Exam/Assessment Notes (clear and actionable).

Suggested Exam Questions (8–12) with answers (mix short/medium/challenging).

Suggested Revision Cues (12–25 flashcards).

Confidence Score (0–100%) for factual accuracy/completeness.

Chunk Provenance Map (which chunk contributed what).

Warnings: [INSUFFICIENT CONTEXT], ambiguous values, or smoothing notes.

Tokens Estimate: approximate token count (1 token ≈ 4 characters heuristic).

📑 Final Merge Output Format

Markdown (primary):

Final Transcript

Consolidated Notes

Appendix (chunk_map + warnings)

JSON (secondary): structured summary of above.

⚖️ Safety & Fidelity Rules

Never hallucinate facts.

Preserve technical tokens, formulas, numeric values, code blocks exactly.

Mark ambiguous/missing units explicitly.

If final merged text exceeds user's token budget, truncate only as last resort and log warning.

🧾 Usage Examples

Per-Chunk Example:

Chunk ID: Chunk 1
Original language: ar
preserve_terms: {}
Chunk text: [Paste transcript here]


→ Assistant returns Markdown + optional JSON with all structured notes.

Merge Example — after all chunks are processed, user sends:

MERGE_CHUNKS
[Paste raw chunks in order]


OR

MERGE_PROCESSED
[Paste assistant per-chunk outputs in order]


→ Assistant returns merged lecture package with transcript, consolidated notes, glossary, exam questions, revision cues, provenance, tokens estimate, and warnings.

✨ Features

🎤 Offline transcription with Faster-Whisper (CPU or CUDA).

🖥 Simple GUI built with Tkinter — opens in under a second (all heavy imports are lazy-loaded).

📚 Course Library Browser — A built-in file explorer to seamlessly view your downloaded media, transcripts, and chunked text files all in one place.

🪓 Dynamic Re-chunking — Easily select any completed lecture in the Library Browser and re-split its transcript into a specific, custom number of chunks on the fly.

🎬 Smart YouTube download & transcribe — Paste a YouTube URL to download and transcribe automatically. Automatically detects previously downloaded videos for the same course/lecture and smartly offers to resume, restart, or overwrite to save bandwidth and time.

📋 FIFO Queue system — add multiple lectures to a queue and process them one by one automatically without supervision.

✏️ Queue item editor — edit course name, lecture title, language, model, beam size, threads, audio file, and fixed chunk quantity for any queued item before it runs.

🎧 Multiple audio formats — supports .mp3 and .m4a files.

📂 Organized storage — transcripts saved in courses/<course>/<lecture>/.

📑 Automatic & Fixed chunking of large transcripts for easier navigation.

⏸ Checkpoint & resume support — continue from the last offset if stopped mid-transcription.

🆕 Fresh start guarantee — new runs never accidentally resume from a stale checkpoint.

🔇 Hallucination filter — automatically removes garbage segments (silence artifacts, subscribe loops, punctuation spam, Arabic filler sounds like آآ).

🔈 VAD (Voice Activity Detection) — skips silent sections so Whisper never gets stuck grinding through silence.

🛑 Emergency Stop button — halts transcription safely at the next segment boundary.

📂 Project Structure

LectureStudio/
├── main_gui.py              # Tkinter GUI — all user interaction, library browser, queue, YouTube popup
├── whisper_offline.py       # Faster-Whisper transcription engine
├── output_manager.py        # File & folder handling, checkpoints, chunk saving
├── youtube_downloader.py    # YouTube audio download logic (yt-dlp + pydub)
├── requirements.txt         # Python dependencies
└── README.md                # This file


main_gui.py → GUI entry point. Handles course/lecture input, audio selection, queue management, Library Browser, YouTube popup, settings window, and checkpoint resume on startup.

whisper_offline.py → Core transcription engine. Integrates Faster-Whisper, manages checkpoints, hallucination filtering, VAD, and abort handling.

output_manager.py → Manages saving transcripts, metadata, and chunked outputs to disk.

youtube_downloader.py → Downloads audio from YouTube as MP3 using yt-dlp. Downloads progressive MP4 streams for guaranteed audio sync, then extracts audio via pydub + local ffmpeg. Each download gets a unique filename so multiple YouTube items can coexist in the queue without overwriting each other.

🚀 Installation

1. Clone the repo

git clone https://github.com/ahmedbelal22271-maker/lecture-studio.git
cd lecture-studio

2. Install Python dependencies

pip install -r requirements.txt


Minimum requirements:

Python 3.9+

faster-whisper

pydub

yt-dlp

tkinter (comes preinstalled with most Python distributions)

3. ffmpeg

✅ ffmpeg is already included in the repository as ffmpeg-8.0-essentials_build/. No setup required — the program detects and uses it automatically.

If for any reason the bundled ffmpeg is missing or you are on a non-Windows system, install it system-wide as a fallback:

winget install ffmpeg


The program will detect the system ffmpeg automatically if the local bundle is not present.

4. Model storage location

By default, Whisper models are downloaded to C:\whisper_models. This keeps them outside OneDrive-synced folders, which avoids permission errors and slow file access during download.

If you need to change this, edit the following line at the top of whisper_offline.py:

os.environ.setdefault("HF_HOME", r"C:\whisper_models")


🖥 Usage

Run the GUI

python main_gui.py


Transcribing a local audio file (single)

Enter Course Name and Lecture Title.

Select an audio file (.mp3 or .m4a) using the Choose Lecture Audio button.

Choose your Audio Language (Arabic, English, or Auto Detect).

Optionally open ⚙️ Settings to configure the model and other options.

Click 🚀 Start Processing.

Transcribing from YouTube (single)

Enter Course Name and Lecture Title first.

Click ▶️ YouTube → Transcribe.

Smart Detection: If you previously downloaded a YouTube video for this Course and Lecture, the program will instantly alert you and ask if you want to Resume, Restart, or Download a New Video.

Otherwise, paste the YouTube URL (public or unlisted links both work).

Click ⬇️ Download & Start Now — the program downloads the audio and starts transcription automatically.

Downloaded audio is saved to youtube_downloads/<course>/<lecture>/audio.mp3 and kept after transcription. The transcript is saved in the normal location: courses/<course>/<lecture>/.

Browsing and Re-chunking Lectures

Click 📚 Open Lecture Library to launch the built-in file system explorer.

Browse through your Courses and YouTube Downloads folders to view your audio files and read .txt or .md transcripts right inside the app.

Need a different chunk layout? Select a completed lecture from the tree and click 🪓 Re-chunk Selected Lecture. You will be prompted to enter a new fixed number of chunks, and the program will automatically re-split and organize the transcript.txt into a brand new set of files!

Using the Queue (multiple lectures)

Fill in Course Name, Lecture Title, and select an audio file (or use YouTube).

Click ➕ Add to Queue — the fields clear automatically so you can enter the next lecture.

Repeat for all lectures you want to process.

Click ▶ Start Queue — all items process one by one in FIFO order automatically.

Queue controls:

✏ Edit Selected — opens an edit dialog for any queued item where you can change course name, lecture title, language, model, beam size, threads, audio file, and specify fixed vs. auto chunk lengths. For YouTube items you can also edit the URL and re-download.

✖ Remove Selected — removes the highlighted item.

🗑 Clear Queue — clears all items after confirmation.

If one item fails during a queue run, a dialog asks whether to continue with the remaining items or stop.

YouTube + Queue: In the YouTube popup, use ➕ Download & Add to Queue to download the audio and add it to the queue without starting transcription immediately.

Output files

courses/<course>/<lecture>/transcript.txt              ← full transcript
courses/<course>/<lecture>/<course>_<lecture>_chunks/  ← chunked transcript
youtube_downloads/<course>/<lecture>/audio.mp3         ← downloaded YouTube audio (kept)


⚙️ Settings

Open the ⚙️ Settings window before starting to configure:

Setting

Description

Recommended

Model

Whisper model size. Larger = more accurate but slower and more RAM.

Medium

Beam Size

Search width for decoding. Higher = slightly more accurate, but past 2 causes hallucinations on Arabic.

2

ASR Threads

Number of CPU threads to use.

50% of your CPU cores

WPM Preset

Words-per-minute estimate for auto-chunk size calculation.

Casual (~120 WPM)

Chunking Mode

Switch between "Auto (by minutes)" and "Fixed number of chunks".

Auto

📄 License

MIT License. Free for personal and academic use.

💻 Specs & Tips

The program needs about 2 GB of RAM for the Medium model.

Set ASR threads to half your CPU core count so the program can multitask alongside other applications.

For the best accuracy on Arabic lectures, set Beam Size to 2 in the Settings window. Higher values increase hallucinations on dialectal Arabic — especially random foreign script injection (Russian, Japanese, etc.).

On first run, the Whisper model will be downloaded automatically (~1.5 GB for Medium). This only happens once — subsequent runs load from C:\whisper_models instantly.

The program keeps VAD (Voice Activity Detection) on by default. This prevents Whisper from getting stuck for minutes on silent sections of the audio. Do not disable it unless you have a specific reason.

If transcription is interrupted, the program saves a checkpoint and will offer to resume from where it left off on the next launch.

A fresh Start Processing click always starts from the beginning — it never accidentally resumes a stale checkpoint.

YouTube downloads are saved to youtube_downloads/ in the program folder. Keep this folder outside OneDrive-synced paths to avoid file lock issues.

The hallucination filter automatically removes common garbage outputs like اشتركوا في القناة, Thank you., ....., [Music], and Arabic filler sound loops (آآ آآ آآ). These never appear in the final transcript.

For large audio files (1+ hours), expect the first segment to appear after 30–90 seconds while Whisper decodes and processes the initial audio chunks. This is normal.