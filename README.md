# 📘 Lecture Studio 2.0

## 🎯 Overview
Lecture Studio is a **desktop application with a GUI** that transcribes lecture recordings into text using [Faster-Whisper](https://github.com/guillaumekln/faster-whisper).

It is designed to be **lightweight and offline-first**, letting students and researchers quickly convert audio lectures into organized transcripts — including direct download and transcription from YouTube.

After you get the chunked text transcript, paste it into Claude or ChatGPT using this prompt for structured academic study notes:

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
- ✏️ **Queue item editor** — edit course name, lecture title, language, model, beam size, threads, chunk settings, and audio file for any queued item before it runs. YouTube items also support URL editing and re-downloading.
- 🔁 **Queue checkpoint & restore** — the queue is saved to disk on every change. If the program is force-closed, the queue is fully restored on next launch, including resume offsets for any interrupted transcriptions.
- 🎧 **Multiple audio formats** — supports `.mp3` and `.m4a` files.
- 📂 **Organized storage** — transcripts saved in `courses/<course>/<lecture>/`.
- 📑 **Automatic chunking** — split transcripts by time (minutes) or by a fixed number of chunks.
- ⏸ **Checkpoint & resume** — saves progress every segment. On restart, offers to resume from the exact point of interruption.
- 🆕 **Fresh start guarantee** — new runs never accidentally resume from a stale checkpoint.
- 🔢 **Smart versioning** — if a transcript already exists, automatically creates `transcript_2.txt`, `transcript_3.txt` etc. with matching `_chunks_2/`, `_chunks_3/` folders. Configurable via File Conflict Mode in Settings.
- 🔇 **Hallucination filter** — removes garbage segments: subscribe loops (`اشتركوا في القناة`), punctuation spam, Arabic filler sound loops (`آآ آآ`), `[Music]`, `Thank you.` and similar.
- 🔄 **Dynamic hallucination loop detection** — if Whisper repeats the same segment 3 times in a row, transcription automatically restarts from that offset with a blank context, bypassing the stuck point.
- 🔈 **VAD (Voice Activity Detection)** — skips silent sections so Whisper never gets stuck grinding through silence.
- 📚 **Library Browser** — browse all courses, lectures, and transcripts in a split-pane viewer. Supports re-chunking any transcript (including externally added ones) with fuzzy filename detection.
- ⚙️ **Persistent settings** — all settings saved to `settings.json` automatically on close. File is auto-generated with defaults on first run and self-repairs if keys are missing.
- 🛑 **Emergency Stop** button — halts transcription safely at the next segment boundary.
- 🌐 **Current Process indicator** — shows which lecture is actively being transcribed in the GUI.
- 💤 **Lazy YouTube download** — optionally defer YouTube downloads to run-time rather than queuing time, keeping the queue responsive.

---

## 📂 Project Structure

```
LectureStudio/
├── main_gui.py              # Tkinter GUI — all user interaction, queue, YouTube popup
├── whisper_offline.py       # Faster-Whisper transcription engine
├── output_manager.py        # File & folder handling, checkpoints, chunk saving
├── youtube_downloader.py    # YouTube audio download logic (yt-dlp + pydub)
├── library_browser.py       # Library Browser — file tree viewer and re-chunker
├── config.py                # Settings load/save, queue checkpoint helpers, constants
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

- **`main_gui.py`** → GUI entry point. Handles course/lecture input, audio selection, queue management, YouTube popup, settings window, and checkpoint resume on startup.
- **`whisper_offline.py`** → Core transcription engine. Integrates Faster-Whisper, manages checkpoints, hallucination filtering (static + dynamic loop detection), VAD, and abort handling.
- **`output_manager.py`** → Manages saving transcripts, metadata, and chunked outputs to disk. Handles smart versioning via `run_suffix`.
- **`youtube_downloader.py`** → Downloads audio from YouTube as MP3 using yt-dlp. Downloads progressive MP4 streams for guaranteed audio sync, then extracts audio via pydub + local ffmpeg. Each download gets a unique filename so multiple YouTube items can coexist in the queue.
- **`library_browser.py`** → Standalone Library Browser class. Fuzzy transcript detection via fuzzywuzzy, path-aware re-chunking using absolute paths, supports externally added transcripts.
- **`config.py`** → All settings and queue checkpoint logic extracted here. Also defines `estimate_tokens()`, `WPM_PRESETS`, and `CTX_SIZE`.

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
- `fuzzywuzzy` (optional — for fuzzy transcript detection in Library Browser)
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
3. If audio for this lecture was previously downloaded, a dialog offers to Resume, Restart, or Download New.
4. Paste the YouTube URL (public or unlisted links both work) and click **⬇️ Download & Start Now**.

> Downloaded audio is saved to `youtube_downloads/<course>/<lecture>/audio.mp3` and kept after transcription.
> The transcript is saved in the normal location: `courses/<course>/<lecture>/`.

---

### Using the Queue (multiple lectures)
1. Fill in Course Name, Lecture Title, and select an audio file (or use YouTube).
2. Click **➕ Add to Queue** — the fields clear automatically so you can enter the next lecture.
3. Repeat for all lectures you want to process.
4. Click **▶ Start Queue** — all items process one by one in FIFO order automatically.
5. You can add more items to the queue while it is already running — they will be picked up automatically.

**Queue controls:**
- **✏ Edit Selected** — opens an edit dialog for any queued item. Editable fields: course name, lecture title, language, model, beam size, threads, chunk settings, and audio file. YouTube items also support URL editing and re-downloading from within the dialog.
- **✖ Remove Selected** — removes the highlighted item.
- **🗑 Clear Queue** — clears all items after confirmation.

**Queue status icons (in the listbox):**
- `[  ]` — waiting
- `[>>]` — currently running
- `[OK]` — completed successfully
- `[XX]` — failed with error

If one item fails during a queue run, a dialog asks whether to continue with the remaining items or stop.

**YouTube + Queue:**
In the YouTube popup, use **➕ Download & Add to Queue** to download the audio and add it to the queue. If **Lazy YouTube Download** is enabled in Settings, the download is deferred until the item is actually processed by the queue worker.

**Queue restore on startup:**
If the program is force-closed while a queue is active, the queue is automatically restored on next launch. Any items that were mid-transcription will have their Whisper checkpoint offset injected automatically — they resume from where they left off when you start the queue again.

---

### Using the Library Browser
Click **📚 Open Lecture Library** to open the browser. It shows all courses and lectures in a split-pane tree view. Click any `.txt` file to view its contents on the right.

**Re-chunking a transcript:**
1. Select a lecture or a specific transcript file in the tree.
2. Click **🪓 Re-chunk Selected Lecture**.
3. Enter the number of chunks you want.
4. The transcript is split and saved into a `<filename>_chunks/` folder next to the source file.

Re-chunking works on externally added transcripts too — it uses fuzzy filename matching to detect transcript files even if they are not named `transcript.txt`.

---

### Output files
```
courses/<course>/<lecture>/transcript.txt              ← full transcript (run 1)
courses/<course>/<lecture>/transcript_2.txt            ← full transcript (run 2, if conflict)
courses/<course>/<lecture>/<course>_<lecture>_chunks/  ← chunks (run 1)
courses/<course>/<lecture>/<course>_<lecture>_chunks_2/← chunks (run 2)
youtube_downloads/<course>/<lecture>/audio.mp3         ← downloaded YouTube audio (kept)
```

---

## ⚙️ Settings

Open the **⚙️ Settings** window before starting to configure:

| Setting | Description | Recommended |
|---|---|---|
| **Model** | Whisper model size. Larger = more accurate but slower and more RAM. | Medium |
| **Beam Size** | Search width for decoding. Higher = slightly more accurate, but past 2 causes hallucinations on Arabic. | **2** |
| **ASR Threads** | Number of CPU threads to use. | 50–100% of your CPU cores |
| **WPM Preset** | Words-per-minute estimate for chunk size calculation (Auto mode only). | Casual (~120 WPM) |
| **Chunk Length** | How many minutes of audio per transcript chunk (Auto mode only). | 10 min |
| **Chunking Mode** | Auto (by minutes) or Fixed (exact number of chunks). | Fixed |
| **Number of chunks** | Exact number of chunks to split transcript into (Fixed mode only). | 5 |
| **Delay YouTube download** | Download YouTube audio at queue processing time rather than at add time. | On |
| **File Conflict Mode** | Create New (transcript_2.txt etc.) or Overwrite Existing. | Create New |

Settings are saved automatically to `settings.json` when the Settings window is closed.

---

## 📄 License

MIT License. Free for personal and academic use.

---

## 💻 Specs & Tips

- The program needs about **2 GB of RAM** for the Medium model.
- Set ASR threads to **50–100% of your CPU core count**. Going from 4 to 8 threads can cut transcription time by 30–40%.
- For the best accuracy on Arabic lectures, set **Beam Size to 2**. Higher values increase hallucinations on dialectal Arabic — especially random foreign script injection (Russian, Japanese, etc.). `beam_size=1` is ~20–30% faster with minimal accuracy loss on clean audio.
- On first run, the Whisper model will be **downloaded automatically** (~1.5 GB for Medium). This only happens once — subsequent runs load from `C:\whisper_models` instantly.
- **Model load time is 60–90 seconds** on CPU on first run per session. This is normal — the 769M parameter model takes time to load into RAM. For a queue of multiple items, the model is loaded only once and reused for all subsequent items.
- **First segment appears 20–30 seconds after model load** for a typical 30MB M4A. This is faster-whisper internally decoding the audio before emitting the first segment — not a freeze.
- The program keeps **VAD (Voice Activity Detection) on** by default. This prevents Whisper from getting stuck for minutes on silent sections of the audio. Do not disable it unless you have a specific reason.
- The **dynamic hallucination loop detector** automatically breaks out of stuck segments. If Whisper repeats the same text 3 times in a row, it restarts transcription from that offset + 0.5 seconds with a blank context, without any user intervention.
- If transcription is interrupted, the program saves a **checkpoint every segment** and will offer to resume from where it left off on the next launch.
- A fresh **Start Processing** click always starts from the beginning — it never accidentally resumes a stale checkpoint.
- YouTube downloads are saved to `youtube_downloads/` in the program folder. Keep this folder **outside OneDrive-synced paths** to avoid file lock issues during download and transcription.
- The **hallucination filter** automatically removes common garbage outputs like `اشتركوا في القناة`, `Thank you.`, `.....`, `[Music]`, and Arabic filler sound loops (`آآ آآ آآ`). These never appear in the final transcript.
- **Keep the `youtube_downloads/` and `courses/` folders outside OneDrive** if possible. OneDrive file locking causes ffprobe and ffmpeg to hang when accessing files mid-sync.
- For **large audio files** (1+ hours), expect the first segment to appear after 30–90 seconds while Whisper decodes and processes the initial audio chunks. This is normal and not a freeze.
- **5 chunks** is the recommended setting for a 65-minute lecture when using the ChatGPT/Claude prompt above — it keeps each message digestible while building a complete running summary.