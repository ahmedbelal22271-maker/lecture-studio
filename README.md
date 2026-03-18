# 📘 Lecture Studio 2.0

## 🎯 Overview
Lecture Studio is a **desktop application with a GUI** that transcribes lecture recordings into text using [Faster-Whisper](https://github.com/guillaumekln/faster-whisper).

It is designed to be **lightweight and offline-first**, letting students and researchers quickly convert audio lectures into organized transcripts — including direct download and transcription from YouTube.

After you get the chunked text transcript it is then put on ChatGPT after giving ChatGPT this smart prompt for you to get the academic explanation:

---

You are a transcript analyst specializing in spoken lecture transcripts. The user will paste chunks of a transcript one at a time, and finally the full transcript at the end.
LANGUAGE CONTEXT:
Chunks are spoken in Egyptian Arabic dialect with English technical terms mixed in. Spoken language contains natural noise that must be actively filtered:

Remove: filler words, false starts, repetitions, stutters, transcription artifacts, repeated phrases caused by transcription errors, meta-conversation (e.g., "can you hear me?", "does anyone have a question?", attendance remarks), and any phrase that appears more than once with identical meaning
Preserve: all technical terms exactly as stated, all conceptual content, all examples, all questions raised by students and their answers, and all named entities (people, books, processors, bus names, etc.)
Normalize: indirect or fragmented phrasing into clean, direct English statements without losing the original meaning


YOUR BEHAVIOR:
For every message the user sends, first determine what it is:

If it is a PARTIAL chunk (part of a larger transcript still being fed): process it as a chunk
If it is the FULL transcript (the complete, unabridged version): produce the final analysis

How to tell the difference:

A chunk will feel incomplete — it may start or end mid-sentence, mid-topic, or mid-conversation
The full transcript will be comprehensive, covering everything discussed across all previous chunks
If unsure, treat it as a chunk


If it is a CHUNK:
Step 1 — Clean the chunk first:
Before extracting anything, mentally strip all noise as defined above. Work only from the cleaned version.
Step 2 — Extract & Link:

Extract all important information — key points, decisions, names, action items, topics, facts, questions raised
Link it to everything processed so far — note continuations, contradictions, elaborations, or new threads
Update your internal running summary

Output format:
✅ Chunk Received — [brief 3-word topic label]
Extracted from this chunk:

[bullet points of key info — clean, direct, noise-free]

Links to previous chunks:

[how this connects to what came before — write "N/A" for the first chunk]

Running Summary so far:
[Your updated cumulative summary — complete, clean, fully linked, ready to carry full context forward]

If it is the FULL TRANSCRIPT:
Step 1 — Clean the full transcript first:
Apply the same noise removal pass across the entire transcript before doing any analysis. This cleaned version is what all sections below are based on.
You now have the complete transcript. Cross-reference it with everything accumulated across all chunks and produce an exhaustive, detail-complete analysis. Someone who has never read the transcript should come away knowing everything in it — no detail, no matter how minor, should be omitted.
Output format:
1. Executive Summary
A concise overview of the entire transcript in 3–5 sentences covering the who, what, and why.
2. Participants & Roles
List every person who speaks or is mentioned, with their role, title, or relationship if stated or inferable.
3. Full Chronological Breakdown
Go through the transcript from start to finish and document every topic, exchange, and point raised — in order. For each segment include:

What was discussed
Who said or raised it
Any responses, reactions, or follow-ups
How it connects to other parts of the transcript

This section must be exhaustive. Do not summarize away specifics. Do not skip anything. All content must be in clean, noise-free English.
4. Key Topics & Insights
Group the most important themes and ideas across the transcript. For each topic include all relevant details, nuances, and supporting points raised by any participant.
5. Decisions Made
Every conclusion, agreement, resolution, or commitment reached — with full context on how it was arrived at.
6. Action Items
Every task, follow-up, next step, or responsibility assigned or implied — including who is responsible and any deadlines or conditions mentioned.
7. Open Questions & Unresolved Threads
Everything left unanswered, deferred, or flagged for later — with full context on why it was left open.
8. Notable Quotes
Significant statements that are particularly illustrative or important — cleaned of filler but preserving the speaker's original meaning — with speaker attribution and context.
9. Contradictions & Tensions
Any disagreements, inconsistencies, or conflicting statements between participants or across different parts of the transcript.

---

## ✨ Features

- 🎤 **Offline transcription** with Faster-Whisper (CPU or CUDA).
- 🖥 **Simple GUI** built with Tkinter — opens in under a second (all heavy imports are lazy-loaded).
- 🎬 **YouTube download & transcribe** — paste any public or unlisted YouTube URL and the program downloads the audio and transcribes it automatically.
- 📋 **FIFO Queue system** — add multiple lectures to a queue and process them one by one automatically without supervision.
- ✏️ **Queue item editor** — edit course name, lecture title, language, model, beam size, threads, and audio file for any queued item before it runs. YouTube items also support URL editing and re-downloading.
- 🎧 **Multiple audio formats** — supports `.mp3` and `.m4a` files.
- 📂 **Organized storage** — transcripts saved in `courses/<course>/<lecture>/`.
- 📑 **Automatic chunking** of large transcripts for easier navigation.
- ⏸ **Checkpoint & resume** support — continue from the last offset if stopped mid-transcription.
- 🆕 **Fresh start guarantee** — new runs never accidentally resume from a stale checkpoint.
- 🔇 **Hallucination filter** — automatically removes garbage segments (silence artifacts, subscribe loops, punctuation spam, Arabic filler sounds like آآ).
- 🔈 **VAD (Voice Activity Detection)** — skips silent sections so Whisper never gets stuck grinding through silence.
- 🛑 **Emergency Stop** button — halts transcription safely at the next segment boundary.

---

## 📂 Project Structure

```
LectureStudio/
├── main_gui.py              # Tkinter GUI — all user interaction, queue, YouTube popup
├── whisper_offline.py       # Faster-Whisper transcription engine
├── output_manager.py        # File & folder handling, checkpoints, chunk saving
├── youtube_downloader.py    # YouTube audio download logic (yt-dlp + pydub)
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

- **`main_gui.py`** → GUI entry point. Handles course/lecture input, audio selection, queue management, YouTube popup, settings window, and checkpoint resume on startup.
- **`whisper_offline.py`** → Core transcription engine. Integrates Faster-Whisper, manages checkpoints, hallucination filtering, VAD, and abort handling.
- **`output_manager.py`** → Manages saving transcripts, metadata, and chunked outputs to disk.
- **`youtube_downloader.py`** → Downloads audio from YouTube as MP3 using yt-dlp. Downloads progressive MP4 streams for guaranteed audio sync, then extracts audio via pydub + local ffmpeg. Each download gets a unique filename so multiple YouTube items can coexist in the queue without overwriting each other.

---

## 🚀 Installation

### 1. Clone the repo
```bash
git clone https://github.com/ahmedbelal22271-maker/lecture-studio.git
cd lecture-studio
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

Minimum requirements:
- Python 3.9+
- `faster-whisper`
- `pydub`
- `yt-dlp`
- `tkinter` (comes preinstalled with most Python distributions)

### 3. ffmpeg

✅ **ffmpeg is already included in the repository** as `ffmpeg-8.0-essentials_build/`. No setup required — the program detects and uses it automatically.

If for any reason the bundled ffmpeg is missing or you are on a non-Windows system, install it system-wide as a fallback:
```bash
winget install ffmpeg
```
The program will detect the system ffmpeg automatically if the local bundle is not present.

### 4. Model storage location

By default, Whisper models are downloaded to `C:\whisper_models`. This keeps them outside OneDrive-synced folders, which avoids permission errors and slow file access during download.

If you need to change this, edit the following line at the top of `whisper_offline.py`:
```python
os.environ.setdefault("HF_HOME", r"C:\whisper_models")
```

---

## 🖥 Usage

### Run the GUI
```bash
python main_gui.py
```

---

### Transcribing a local audio file (single)
1. Enter **Course Name** and **Lecture Title**.
2. Select an audio file (`.mp3` or `.m4a`) using the **Choose Lecture Audio** button.
3. Choose your **Audio Language** (Arabic, English, or Auto Detect).
4. Optionally open **⚙️ Settings** to configure the model and other options.
5. Click **🚀 Start Processing**.

---

### Transcribing from YouTube (single)
1. Enter **Course Name** and **Lecture Title** first.
2. Click **▶️ YouTube → Transcribe**.
3. Paste the YouTube URL (public or unlisted links both work).
4. Click **⬇️ Download & Start Now** — the program downloads the audio and starts transcription automatically.

> Downloaded audio is saved to `youtube_downloads/<course>/<lecture>/audio.mp3` and kept after transcription.
> The transcript is saved in the normal location: `courses/<course>/<lecture>/`.

---

### Using the Queue (multiple lectures)
1. Fill in Course Name, Lecture Title, and select an audio file (or use YouTube).
2. Click **➕ Add to Queue** — the fields clear automatically so you can enter the next lecture.
3. Repeat for all lectures you want to process.
4. Click **▶ Start Queue** — all items process one by one in FIFO order automatically.

**Queue controls:**
- **✏ Edit Selected** — opens an edit dialog for any queued item where you can change course name, lecture title, language, model, beam size, threads, and audio file. For YouTube items you can also edit the URL and re-download.
- **✖ Remove Selected** — removes the highlighted item.
- **🗑 Clear Queue** — clears all items after confirmation.

If one item fails during a queue run, a dialog asks whether to continue with the remaining items or stop.

**YouTube + Queue:**
In the YouTube popup, use **➕ Download & Add to Queue** to download the audio and add it to the queue without starting transcription immediately.

---

### Output files
```
courses/<course>/<lecture>/final_transcript.txt        ← full transcript
courses/<course>/<lecture>/<course>_<lecture>_chunks/  ← chunked transcript
youtube_downloads/<course>/<lecture>/audio.mp3         ← downloaded YouTube audio (kept)
```

---

## ⚙️ Settings

Open the **⚙️ Settings** window before starting to configure:

| Setting | Description | Recommended |
|---|---|---|
| **Model** | Whisper model size. Larger = more accurate but slower and more RAM. | Medium |
| **Beam Size** | Search width for decoding. Higher = slightly more accurate, but past 2 causes hallucinations on Arabic. | **2** |
| **ASR Threads** | Number of CPU threads to use. | 50% of your CPU cores |
| **WPM Preset** | Words-per-minute estimate for chunk size calculation. | Casual (~120 WPM) |
| **Chunk Length** | How many minutes of audio per transcript chunk. | 10 min |

---

## 📄 License

MIT License. Free for personal and academic use.

---

## 💻 Specs & Tips

- The program needs about **2 GB of RAM** for the Medium model.
- Set ASR threads to **half your CPU core count** so the program can multitask alongside other applications.
- For the best accuracy on Arabic lectures, set **Beam Size to 2** in the Settings window. Higher values increase hallucinations on dialectal Arabic — especially random foreign script injection (Russian, Japanese, etc.).
- On first run, the Whisper model will be **downloaded automatically** (~1.5 GB for Medium). This only happens once — subsequent runs load from `C:\whisper_models` instantly.
- The program keeps **VAD (Voice Activity Detection) on** by default. This prevents Whisper from getting stuck for minutes on silent sections of the audio. Do not disable it unless you have a specific reason.
- If transcription is interrupted, the program saves a **checkpoint** and will offer to resume from where it left off on the next launch.
- A fresh **Start Processing** click always starts from the beginning — it never accidentally resumes a stale checkpoint.
- YouTube downloads are saved to `youtube_downloads/` in the program folder. Keep this folder outside OneDrive-synced paths to avoid file lock issues.
- The **hallucination filter** automatically removes common garbage outputs like `اشتركوا في القناة`, `Thank you.`, `.....`, `[Music]`, and Arabic filler sound loops (`آآ آآ آآ`). These never appear in the final transcript.
- For **large audio files** (1+ hours), expect the first segment to appear after 30–90 seconds while Whisper decodes and processes the initial audio chunks. This is normal.
