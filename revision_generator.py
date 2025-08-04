# revision_generator.py

import os
from llama_cpp import Llama
from output_manager import list_all_notes

MODEL_PATH = "mistral-7b-instruct-v0.1.Q4_K_M.gguf"
CTX_SIZE = 4096
MAX_TOKENS = 1536

llm = Llama(model_path=MODEL_PATH, n_ctx=CTX_SIZE)

def load_all_notes(course_dir):
    note_paths = list_all_notes(course_dir)
    all_notes = []
    for path in note_paths:
        with open(path, "r", encoding="utf-8") as f:
            all_notes.append(f.read())
    return "\n\n".join(all_notes)

def build_revision_prompt(notes_text):
    return f"""
[INST] <<SYS>>
You are an academic assistant helping a student prepare for their midterm or final exam.
Your job is to summarize the most important concepts, topics, and alerts from all prior lecture notes.
Return your output in Markdown format, structured as follows:

### 🧠 Core Concepts to Review
- Bullet point list of the most important academic ideas.

### 📝 Composite Exam Questions
- Generate 3–5 realistic exam-style questions based on all lecture notes.

### 🔍 Instructor Emphasis
- Identify repeated emphasis, warnings, or repeated terminology from past lectures.
<</SYS>>

Here are all the lecture notes:

{notes_text}
[/INST]
"""

def generate_revision_summary(course_dir):
    notes_text = load_all_notes(course_dir)
    prompt = build_revision_prompt(notes_text)
    output = llm(prompt, max_tokens=MAX_TOKENS)
    result = output["choices"][0].get("text") or output["choices"][0].get("content", "")
    return result.strip()

def save_revision_summary(course_dir, revision_text):
    path = os.path.join(course_dir, "revision_summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(revision_text)
    return path

def run_revision_pipeline(course_dir):
    print(f"[INFO] Generating revision summary for course: {course_dir}")
    summary = generate_revision_summary(course_dir)
    path = save_revision_summary(course_dir, summary)
    print(f"[SUCCESS] Revision summary saved to: {path}")
    return path
