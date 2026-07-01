"""Flask app for Phase 8 frontend and proof endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, request, send_from_directory
from ollama import chat

from .verified_mode import run_verified_mode

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BACKEND_DIR.parent / "Frontend"
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
ASSET_VERSION = str(int((FRONTEND_DIR / "script.js").stat().st_mtime))


def _parse_premises(payload: Dict[str, Any]) -> List[str]:
    premises = payload.get("premises", [])
    if isinstance(premises, list):
        return [str(item).strip() for item in premises if str(item).strip()]
    if isinstance(premises, str):
        return [line.strip() for line in premises.splitlines() if line.strip()]
    return []


def _parse_goal(payload: Dict[str, Any]) -> str:
    goal = payload.get("goal", "")
    return str(goal).strip()


def _build_ai_prompt(question: str) -> str:
    return (
        "You are a careful logic tutor for propositional logic and natural deduction. "
        "Answer clearly, concisely, and correctly. If the user asks for a proof idea, "
        "include rule names and a short worked example when helpful.\n\n"
        f"Question: {question.strip()}"
    )


def create_app() -> Flask:
    app = Flask(__name__)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/")
    def index() -> Any:
        html_path = FRONTEND_DIR / "index.html"
        html = html_path.read_text(encoding="utf-8")
        html = html.replace('href="styles.css"', f'href="styles.css?v={ASSET_VERSION}"')
        html = html.replace('src="script.js"', f'src="script.js?v={ASSET_VERSION}"')
        return app.response_class(html, mimetype="text/html")

    @app.get("/help")
    def help_page() -> Any:
        return send_from_directory(FRONTEND_DIR, "help.html")

    @app.get("/styles.css")
    def styles() -> Any:
        return send_from_directory(FRONTEND_DIR, "styles.css")

    @app.get("/script.js")
    def script() -> Any:
        return send_from_directory(FRONTEND_DIR, "script.js")

    @app.post("/ask_ai")
    def ask_ai() -> Any:
        payload = request.get_json(silent=True) or {}
        question = str(payload.get("question", "")).strip()
        if not question:
            return jsonify({"error": "Missing question."}), 400

        prompt = _build_ai_prompt(question)
        response = chat(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.3},
        )
        answer = response["message"]["content"]
        return jsonify({
            "mode": "ai_tutor",
            "question": question,
            "answer": answer,
            "model": DEFAULT_MODEL,
        })

    @app.post("/solve_verified")
    def solve_verified() -> Any:
        payload = request.get_json(silent=True) or {}
        premises = _parse_premises(payload)
        goal = _parse_goal(payload)

        if not premises:
            return jsonify({"error": "Missing premises."}), 400
        if not goal:
            return jsonify({"error": "Missing goal."}), 400

        try:
            proof = run_verified_mode(premises=premises, goal=goal, model=DEFAULT_MODEL)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 422
        except Exception as exc:  # pragma: no cover - route-level guard
            return jsonify({"error": str(exc)}), 500

        step_count = len(proof.get("steps", [])) if isinstance(proof, dict) else 0
        return jsonify({
            "title": "Verified Proof",
            "summary": f"Verified proof generated successfully with {step_count} steps.",
            "mode": "verified_proof",
            **proof,
        })

    return app


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
