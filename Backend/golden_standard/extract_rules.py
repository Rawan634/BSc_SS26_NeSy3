"""Extract full PDF text and structured inference rules from the golden standard PDFs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PyPDF2 import PdfReader


BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "pdfs"
TEXT_DIR = BASE_DIR / "texts"
RULES_DIR = BASE_DIR / "rules"


@dataclass(frozen=True)
class RuleTemplate:
	name: str
	symbol: str
	premises: list[str]
	conclusion: str
	pattern_description: str
	keywords: tuple[str, ...]


SECTION_16_RULES: tuple[RuleTemplate, ...] = (
	RuleTemplate(
		name="Modus Ponens",
		symbol="→E",
		premises=["p → q", "p"],
		conclusion="q",
		pattern_description="From p → q and p, conclude q.",
		keywords=("modus ponens", "law of detachment"),
	),
	RuleTemplate(
		name="Modus Tollens",
		symbol="MT",
		premises=["p → q", "¬q"],
		conclusion="¬p",
		pattern_description="From p → q and ¬q, conclude ¬p.",
		keywords=("modus tollens",),
	),
	RuleTemplate(
		name="Hypothetical Syllogism",
		symbol="HS",
		premises=["p → q", "q → r"],
		conclusion="p → r",
		pattern_description="From p → q and q → r, conclude p → r.",
		keywords=("hypothetical syllogism",),
	),
	RuleTemplate(
		name="Disjunctive Syllogism",
		symbol="DS",
		premises=["p ∨ q", "¬p"],
		conclusion="q",
		pattern_description="From p ∨ q and ¬p, conclude q.",
		keywords=("disjunctive syllogism",),
	),
	RuleTemplate(
		name="Addition",
		symbol="∨I",
		premises=["p"],
		conclusion="p ∨ q",
		pattern_description="From p, conclude p ∨ q.",
		keywords=("addition",),
	),
	RuleTemplate(
		name="Simplification",
		symbol="∧E",
		premises=["p ∧ q"],
		conclusion="p",
		pattern_description="From p ∧ q, conclude p.",
		keywords=("simplification", "simplification rule"),
	),
	RuleTemplate(
		name="Conjunction",
		symbol="∧I",
		premises=["p", "q"],
		conclusion="p ∧ q",
		pattern_description="From p and q, conclude p ∧ q.",
		keywords=("conjunction",),
	),
	RuleTemplate(
		name="Resolution",
		symbol="Res",
		premises=["p ∨ q", "¬p ∨ r"],
		conclusion="q ∨ r",
		pattern_description="From p ∨ q and ¬p ∨ r, conclude q ∨ r.",
		keywords=("resolution",),
	),
)


QUANTIFIED_RULES: tuple[RuleTemplate, ...] = (
	RuleTemplate(
		name="Universal Instantiation",
		symbol="∀E",
		premises=["∀x P(x)"],
		conclusion="P(c)",
		pattern_description="From ∀x P(x), conclude P(c) for a particular element c.",
		keywords=("universal instantiation",),
	),
	RuleTemplate(
		name="Universal Generalization",
		symbol="∀I",
		premises=["P(c) for an arbitrary c"],
		conclusion="∀x P(x)",
		pattern_description="From P(c) for an arbitrary c, conclude ∀x P(x).",
		keywords=("universal generalization",),
	),
	RuleTemplate(
		name="Existential Instantiation",
		symbol="∃E",
		premises=["∃x P(x)"],
		conclusion="P(c) for some element c",
		pattern_description="From ∃x P(x), conclude P(c) for some element c.",
		keywords=("existential instantiation",),
	),
	RuleTemplate(
		name="Existential Generalization",
		symbol="∃I",
		premises=["P(c) for some element c"],
		conclusion="∃x P(x)",
		pattern_description="From P(c) for some element c, conclude ∃x P(x).",
		keywords=("existential generalization",),
	),
	RuleTemplate(
		name="Universal Modus Ponens",
		symbol="UMP",
		premises=["∀x(P(x) → Q(x))", "P(a)"],
		conclusion="Q(a)",
		pattern_description="From ∀x(P(x) → Q(x)) and P(a), conclude Q(a).",
		keywords=("universal modus ponens",),
	),
	RuleTemplate(
		name="Universal Modus Tollens",
		symbol="UMT",
		premises=["∀x(P(x) → Q(x))", "¬Q(a)"],
		conclusion="¬P(a)",
		pattern_description="From ∀x(P(x) → Q(x)) and ¬Q(a), conclude ¬P(a).",
		keywords=("universal modus tollens",),
	),
)


ASSUMPTION_BASED_RULES: tuple[RuleTemplate, ...] = (
	RuleTemplate(
		name="Implication Introduction",
		symbol="→I",
		premises=["Assume p", "derive q"],
		conclusion="p → q",
		pattern_description="Assume p and derive q; then conclude p → q (conditional proof).",
		keywords=(
			"direct proof of a conditional statement p→q",
			"first step is the assumption that p is true",
		),
	),
	RuleTemplate(
		name="Negation Introduction",
		symbol="¬I",
		premises=["Assume p", "derive contradiction (⊥)"],
		conclusion="¬p",
		pattern_description="Assume p and derive a contradiction; then conclude ¬p (proof by contradiction).",
		keywords=(
			"proofs by contradiction",
			"assuming that ¬p is true leads to a contradiction",
		),
	),
	RuleTemplate(
		name="Falsum Elimination",
		symbol="⊥E",
		premises=["⊥"],
		conclusion="any formula r",
		pattern_description="From a contradiction (⊥), infer any formula (ex falso quodlibet).",
		keywords=(
			"r∧¬r",
			"is a contradiction whenever r is a proposition",
			"both p and ¬p are true, we have a contradiction",
		),
	),
)


ASSUMPTION_RULE_FALLBACKS: dict[str, dict[str, object]] = {
	"Implication Introduction": {
		"name": "Implication Introduction",
		"symbol": "→I",
		"pattern_description": "Assume p and derive q; then conclude p → q (conditional proof).",
		"premises": ["Assume p", "derive q"],
		"conclusion": "p → q",
		"natural_language": "To prove p → q, assume p and derive q.",
		"full_explanation": (
			"Section 1.7 presents direct proof of conditional statements as starting with the assumption that "
			"p is true, then deriving q using definitions, axioms, and prior results; this establishes p→q."
		),
		"source_pdf": "Rosen_1.7_Introduction_to_Proofs.pdf",
		"page": 86,
	},
	"Negation Introduction": {
		"name": "Negation Introduction",
		"symbol": "¬I",
		"pattern_description": "Assume p and derive a contradiction; then conclude ¬p (proof by contradiction).",
		"premises": ["Assume p", "derive contradiction (⊥)"],
		"conclusion": "¬p",
		"natural_language": "If assuming p leads to contradiction, conclude ¬p.",
		"full_explanation": (
			"Section 1.7 explains proof by contradiction: if an assumption implies a contradiction, that "
			"assumption is false, yielding its negation."
		),
		"source_pdf": "Rosen_1.7_Introduction_to_Proofs.pdf",
		"page": 90,
	},
	"Falsum Elimination": {
		"name": "Falsum Elimination",
		"symbol": "⊥E",
		"pattern_description": "From contradiction (⊥), infer any formula (ex falso quodlibet).",
		"premises": ["⊥"],
		"conclusion": "any formula r",
		"natural_language": "Once contradiction is derived, any formula follows in classical logic.",
		"full_explanation": (
			"Section 1.7 formalizes contradiction via forms such as r ∧ ¬r and repeatedly uses contradiction "
			"to close assumptions; this corresponds to the classical ex falso rule."
		),
		"source_pdf": "Rosen_1.7_Introduction_to_Proofs.pdf",
		"page": 90,
	},
}


LIGATURES = {
	"\ufb00": "ff",
	"\ufb01": "fi",
	"\ufb02": "fl",
	"\ufb03": "ffi",
	"\ufb04": "ffl",
	"\ufb05": "ft",
	"\ufb06": "st",
}


def normalize_text(text: str) -> str:
	for bad, good in LIGATURES.items():
		text = text.replace(bad, good)
	text = text.replace("\u00a0", " ")
	text = text.replace("\r\n", "\n").replace("\r", "\n")
	text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
	text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
	text = re.sub(r"[ \t]+", " ", text)
	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()


def safe_stem(pdf_path: Path) -> str:
	stem = pdf_path.stem
	if stem.lower().startswith("rosen_"):
		stem = stem[6:]
	stem = stem.replace(" ", "_")
	return stem.lower()


def extract_printed_page_number(raw_text: str, pdf_page: int) -> int:
	lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
	if not lines:
		return pdf_page

	header_line = lines[0]
	end_match = re.search(r"(\d{1,4})\s*$", header_line)
	if end_match:
		return int(end_match.group(1))

	start_match = re.match(r"^\s*(\d{1,4})\b", header_line)
	if start_match:
		return int(start_match.group(1))

	for candidate_line in lines[1:4]:
		end_match = re.search(r"(\d{1,4})\s*$", candidate_line)
		if end_match:
			return int(end_match.group(1))
		start_match = re.match(r"^\s*(\d{1,4})\b", candidate_line)
		if start_match:
			return int(start_match.group(1))

	return pdf_page


def extract_pdf_pages(pdf_path: Path) -> list[dict[str, object]]:
	reader = PdfReader(str(pdf_path))
	pages: list[dict[str, object]] = []
	for index, page in enumerate(reader.pages, start=1):
		raw_text = page.extract_text() or ""
		printed_page = extract_printed_page_number(raw_text, index)
		pages.append({"pdf_page": index, "page": printed_page, "text": normalize_text(raw_text)})
	return pages


def write_full_text(pages: Iterable[dict[str, object]], output_path: Path) -> None:
	chunks = []
	for page in pages:
		page_number = int(page["page"])
		pdf_page_number = int(page["pdf_page"])
		text = str(page["text"])
		chunks.append(f"=== PDF Page {pdf_page_number} | Book Page {page_number} ===\n{text}".strip())
	output_path.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")


def compact_whitespace(text: str) -> str:
	return re.sub(r"\s+", " ", text).strip()


def is_usable_natural_language(candidate: str) -> bool:
	candidate_lower = candidate.lower()
	if len(candidate) < 30:
		return False
	if candidate_lower.startswith("table ") or " rules of inference" in candidate_lower:
		return False
	if candidate.startswith("◂") or candidate[0].isdigit():
		return False
	if candidate.count("→") > 2 or candidate.count("∴") > 0:
		return False
	return True


def natural_language_for_keywords(text: str, keywords: tuple[str, ...], fallback: str) -> str:
	cleaned = compact_whitespace(text)
	if not cleaned:
		return fallback

	parts = re.split(r"(?<=[.!?])\s+", cleaned)
	for keyword in keywords:
		keyword_lower = keyword.lower()
		for part in parts:
			candidate = part.strip()
			if keyword_lower in candidate.lower() and is_usable_natural_language(candidate):
				return candidate

	for part in parts:
		candidate = part.strip()
		if is_usable_natural_language(candidate):
			return candidate

	return fallback


def page_for_keywords(pages: list[dict[str, object]], keywords: tuple[str, ...]) -> tuple[int | None, str]:
	for page in pages:
		text = str(page["text"])
		text_lower = text.lower()
		for keyword in keywords:
			if keyword.lower() in text_lower:
				return int(page["page"]), text
	return None, ""


def context_window(text: str, keywords: tuple[str, ...], radius: int = 900) -> str:
	text_lower = text.lower()
	for keyword in keywords:
		index = text_lower.find(keyword.lower())
		if index >= 0:
			start = max(0, index - radius)
			end = min(len(text), index + radius)
			return compact_whitespace(text[start:end])
	return compact_whitespace(text[: radius * 2])


def build_rule_record(
	template: RuleTemplate,
	pages: list[dict[str, object]],
	source_pdf: str,
) -> dict[str, object] | None:
	page_number, page_text = page_for_keywords(pages, template.keywords)
	if page_number is None:
		return None

	full_explanation = context_window(page_text, template.keywords)
	if template in SECTION_16_RULES and "TABLE 1 Rules of Inference" in page_text:
		natural_language = template.pattern_description
	else:
		natural_language = natural_language_for_keywords(page_text, template.keywords, template.pattern_description)

	return {
		"name": template.name,
		"symbol": template.symbol,
		"pattern_description": template.pattern_description,
		"premises": template.premises,
		"conclusion": template.conclusion,
		"natural_language": natural_language,
		"full_explanation": full_explanation,
		"source_pdf": source_pdf,
		"page": page_number,
	}


def parse_rules_for_pdf(pdf_path: Path, pages: list[dict[str, object]]) -> list[dict[str, object]]:
	pdf_stem = pdf_path.stem.lower()
	if not any(
		marker in pdf_stem
		for marker in ("rules_of_inference", "introduction_to_proofs", "proof_methods_strategy")
	):
		return []

	rules: list[dict[str, object]] = []
	seen_names: set[str] = set()
	all_templates: tuple[RuleTemplate, ...] = tuple()

	if "rules_of_inference" in pdf_stem:
		all_templates += SECTION_16_RULES + QUANTIFIED_RULES

	if "introduction_to_proofs" in pdf_stem or "proof_methods_strategy" in pdf_stem:
		all_templates += ASSUMPTION_BASED_RULES

	for template in all_templates:
		record = build_rule_record(template, pages, pdf_path.name)
		if record and record["name"] not in seen_names:
			rules.append(record)
			seen_names.add(str(record["name"]))

	return rules


def write_rules(rules: list[dict[str, object]], output_path: Path) -> None:
	output_path.write_text(json.dumps(rules, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def merge_assumption_rules_into_section_16() -> int:
	target_path = RULES_DIR / "1.6_rules_of_inference.json"
	if not target_path.exists():
		return 0

	section_16_rules = json.loads(target_path.read_text(encoding="utf-8"))
	if not isinstance(section_16_rules, list):
		return 0

	source_paths = (
		RULES_DIR / "1.7_introduction_to_proofs.json",
		RULES_DIR / "1.8_proof_methods_strategy.json",
	)
	assumption_source_records: dict[str, dict[str, object]] = {}
	for source_path in source_paths:
		if not source_path.exists():
			continue
		source_records = json.loads(source_path.read_text(encoding="utf-8"))
		if not isinstance(source_records, list):
			continue
		for record in source_records:
			if not isinstance(record, dict):
				continue
			name = str(record.get("name", ""))
			if name in ASSUMPTION_RULE_FALLBACKS:
				assumption_source_records[name] = record

	existing_names = {str(rule.get("name", "")) for rule in section_16_rules if isinstance(rule, dict)}
	added_count = 0
	for rule_name in ASSUMPTION_RULE_FALLBACKS:
		if rule_name in existing_names:
			continue
		record = assumption_source_records.get(rule_name, ASSUMPTION_RULE_FALLBACKS[rule_name])
		section_16_rules.append(record)
		existing_names.add(rule_name)
		added_count += 1

	write_rules(section_16_rules, target_path)
	return added_count


def process_pdf(pdf_path: Path) -> dict[str, object]:
	print(f"Processing PDF: {pdf_path.name}")
	try:
		pages = extract_pdf_pages(pdf_path)
		text_output = TEXT_DIR / f"{safe_stem(pdf_path)}.txt"
		rules_output = RULES_DIR / f"{safe_stem(pdf_path)}.json"
		write_full_text(pages, text_output)
		rules = parse_rules_for_pdf(pdf_path, pages)
		write_rules(rules, rules_output)
		print(
			f"Completed {pdf_path.name}: wrote {len(pages)} pages to {text_output.name} and "
			f"{len(rules)} rules to {rules_output.name}"
		)
		return {"pdf": pdf_path.name, "pages": len(pages), "rules": len(rules), "error": None}
	except Exception as error:  # pragma: no cover - defensive script-level handling
		print(f"Failed to process {pdf_path.name}: {error}")
		return {"pdf": pdf_path.name, "pages": 0, "rules": 0, "error": str(error)}


def main() -> None:
	TEXT_DIR.mkdir(parents=True, exist_ok=True)
	RULES_DIR.mkdir(parents=True, exist_ok=True)

	pdf_paths = sorted(PDF_DIR.glob("*.pdf"))
	if not pdf_paths:
		print(f"No PDFs found in {PDF_DIR}")
		return

	results = [process_pdf(pdf_path) for pdf_path in pdf_paths]
	merged_count = merge_assumption_rules_into_section_16()
	failed = [result for result in results if result["error"]]

	total_rules = sum(int(result["rules"]) for result in results)
	print(
		f"Processed {len(results)} PDFs. Extracted {total_rules} rules in total. "
		f"Merged {merged_count} assumption-based rules into 1.6_rules_of_inference.json."
	)
	if failed:
		print("Some PDFs could not be processed:")
		for result in failed:
			print(f" - {result['pdf']}: {result['error']}")


if __name__ == "__main__":
	main()
