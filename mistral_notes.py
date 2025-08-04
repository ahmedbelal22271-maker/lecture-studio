# mistral_notes.py

import os
from llama_cpp import Llama
from utils import (
    split_into_chunks,
    score_chunk_for_importance,
    extract_key_summary,
    prepare_contextual_prompt
)

MODEL_PATH = "mistral-7b-instruct-v0.1.Q4_K_M.gguf"
CTX_SIZE = 4096
MAX_TOKENS = 1536

llm = Llama(model_path=MODEL_PATH, n_ctx=CTX_SIZE)

def generate_notes_from_transcript(transcript_text, previous_context=None):
    chunks = split_into_chunks(transcript_text)
    notes = []
    summaries = []

    for i, chunk in enumerate(chunks):
        print(f"[MISTRAL] Processing chunk {i+1}/{len(chunks)}...")

        if i == 0:
            prompt = prepare_contextual_prompt(chunk, previous_context)
        else:
            previous_summary = summaries[-1] if summaries else None
            prompt = prepare_contextual_prompt(chunk, previous_summary)

        output = llm(prompt, max_tokens=MAX_TOKENS)
        result = output["choices"][0].get("text") or output["choices"][0].get("content", "")
        result = result.strip()

        score = score_chunk_for_importance(result)
        notes.append({"index": i+1, "content": result, "score": score})

        # Extract a small summary to feed into next chunk
        summaries.append(extract_key_summary(result))

    # Re-rank by score (highest first)
    notes_sorted = sorted(notes, key=lambda n: n["score"], reverse=True)

    final_output = "\n\n".join([f"## Chunk {n['index']}\n\n{n['content']}" for n in notes_sorted])
    return final_output
