🧠 HONEST_TUTOR

A web-based system for generating, verifying, and repairing Natural Deduction proofs using LLM generation + symbolic validation.

📁 Project Structure (Simplified)
```
HONEST_TUTOR/
├── Backend/
│   ├── golden_standard/      # Extracted inference rules
│   ├── phase6_repair/        # Structural repair engine
│   ├── phase7/               # Lean-based semantic repair
│   ├── phase8/               # Flask backend
│   ├── semantic_verifier/    # NLI verification
│   ├── tutor_agent/          # LLM proof generation
│   ├── validator/            # Structural & scope validation
│   └── main.py               # Entry point
│
├── Frontend/
│   ├── index.html
│   ├── script.js
│   └── styles.css
│
└── .gitignore
```
⚙️ What it does

🔍 Generates Natural Deduction proofs using an LLM  
✅ Validates proof structure and rule usage  
📦 Checks scope and assumption correctness  
🧠 Performs semantic verification (NLI)  
🔧 Repairs invalid proofs automatically  
🌐 Provides a simple web interface

🚀 Running the project

Backend

```bash
python Backend/main.py
```

Frontend

Open Frontend/index.html in a browser.

🛠️ Tech Stack

- Python / Flask  
- JavaScript / HTML / CSS  
- LLM: Llama 3 (via Ollama)  
- Lean Theorem Prover (semantic repair)

📚 Dependencies (quick setup)

```bash
pip install flask flask-cors requests pdfplumber transformers torch
```

> Requires Python 3.10+, Ollama (with Llama 3), and optionally Lean 4.

