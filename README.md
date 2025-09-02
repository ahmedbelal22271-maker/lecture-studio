
# 📘 Lecture Studio

## 🎯 Overview
Lecture Studio is a **desktop application with a GUI** that transcribes lecture recordings into text using [Faster-Whisper](https://github.com/guillaumekln/faster-whisper).  

It is designed to be **lightweight and offline-first**, letting students and researchers quickly convert audio lectures into organized transcripts.

---

## ✨ Features
- 🎤 **Offline transcription** with Faster-Whisper (CPU or CUDA).
- 🖥 **Simple GUI** built with Tkinter — pick a course, lecture title, and audio, then start.
- 📂 **Organized storage**: transcripts saved in `courses/<course>/<lecture>/`.
- 📑 **Automatic chunking** of large transcripts for easier navigation.
- ⏸ **Checkpoint & resume** support — continue from the last offset if stopped.
- 🛑 **Emergency Stop** button to halt transcription safely.

---

## 📂 Project Structure



LectureStudio/
├── main_gui.py # Tkinter GUI for user interaction
├── whisper_offline.py # Faster-Whisper transcription logic
├── output_manager.py # File & folder handling, checkpoints, chunk saving
├── requirements.txt # Python dependencies
└── README.md # Project documentation


- **`main_gui.py`** → GUI entry point (course input, audio selection, start/stop transcription).  
- **`whisper_offline.py`** → Core transcription engine (Faster-Whisper integration, checkpoints, abort handling).  
- **`output_manager.py`** → Manages saving transcripts, metadata, and chunked outputs.  

---

## 🚀 Installation

1. Clone the repo:
   ```bash
   git clone https://github.com/ahmedbelal22271-maker/lecture-studio.git
   cd LectureStudio


Install dependencies:

pip install -r requirements.txt


Minimum requirements:

Python 3.9+

faster-whisper

pydub

tkinter (comes preinstalled with most Python distributions)

## 🖥 Usage

Run the GUI:

python main_gui.py


In the app:

Enter Course Name and Lecture Title.

Select an Audio File (.mp3).

Choose Model Size (Tiny, Base, Small, Medium).

Adjust Threads and Chunk Length (minutes).

Click 🚀 Start Processing.

Output is saved automatically:

##Transcript:

courses/<course>/<lecture>/final_transcript.txt


## Chunks:

courses/<course>/<lecture>/<course>_<lecture>_chunks/

## 📄 License

MIT License. Free for personal and academic use.
