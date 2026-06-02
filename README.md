🧠 HONEST_TUTOR

A Glass-Box AI tutoring framework for Natural Deduction proof generation, verification, repair, and educational feedback.

The system combines Large Language Models (LLMs), symbolic verification, semantic validation, automated repair mechanisms, and formal theorem proving to ensure that generated proofs satisfy logical correctness requirements before being presented to users.

⚙️ Overview

HONEST_TUTOR is designed as a multi-phase neuro-symbolic reasoning system that operates on Fitch-style Natural Deduction proofs.

The framework follows a verification-first philosophy:

1. Generate a proof using an LLM.
2. Validate structural correctness.
3. Validate scope and assumption handling.
4. Validate semantic consistency.
5. Repair detected errors.
6. Formally reconstruct proofs when necessary.
7. Present verified results through an educational frontend.

This approach enables transparent and explainable proof tutoring rather than relying solely on probabilistic AI outputs.

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

