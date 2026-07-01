# 🧠 HONEST_TUTOR

A glass-box AI tutoring framework for Natural Deduction proof generation, verification, repair, and educational feedback.

The system combines large language models, symbolic validation, semantic checking, automated repair, and formal reconstruction to ensure proofs are checked before they are shown to the user.

## Overview

HONEST_TUTOR is a multi-phase neuro-symbolic reasoning system for Fitch-style Natural Deduction proofs.

The pipeline is:

1. Generate a proof with an LLM.
2. Validate structural correctness.
3. Validate scope and assumptions.
4. Validate semantic consistency.
5. Repair detected errors.
6. Reconstruct proofs formally when needed.
7. Present verified results through the frontend.

## Project Structure

```text
HONEST_TUTOR/
├── Backend/
│   ├── phase6_repair/        # Structural repair engine
│   ├── phase7/               # Lean-based semantic repair
│   ├── phase8/               # Flask backend for the frontend
│   ├── semantic_verifier/    # Semantic validation and NLI fallback
│   ├── tutor_agent/          # LLM proof generation
│   ├── validator/            # Structural and scope validation
│   └── main.py               # Batch / evaluation entry point
│
├── Frontend/
│   ├── index.html
│   ├── script.js
│   └── styles.css
│
└── README.md
```

## What You Need To Download

Before running the project, install or download these:

- Python 3.10 or newer
- Ollama
- A local Ollama model, such as `llama3`
- Optional: Lean 4, if you want the formal repair path to work fully

Optional but useful:

- VS Code
- The Python extension for VS Code

## Setup

### 1. Create and activate a virtual environment

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Python packages

```powershell
pip install flask ollama torch transformers PyPDF2
```

If you plan to work on the backend evaluation scripts, this package set is enough for the current codebase.

### 3. Install and start Ollama

Install Ollama from the official website, then pull the model used by the app:

```powershell
ollama pull llama3
```

Make sure the Ollama server is running before starting the app.

## Running The Project

### Run the web app

The frontend is served by the Flask backend, so you do not need to open `index.html` directly.

From the project root:

```powershell
cd Backend
python -m phase8.app
```

Then open:

```text
http://127.0.0.1:5000/
```

### Run the proof pipeline / evaluation entry point

If you want to run the backend proof-generation script directly:

```powershell
cd Backend
python main.py
```

## Notes

- The verified proof mode uses the backend API at `http://127.0.0.1:5000`.
- The semantic repair path can use Lean-based reconstruction when available.

## Troubleshooting

- If the app cannot reach Ollama, start the Ollama server with `ollama serve` or make sure the background service is running.
- If proof generation is slow, that is usually the model call or semantic repair step.
