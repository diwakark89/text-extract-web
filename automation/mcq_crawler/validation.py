from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


@dataclass
class ValidationReport:
    valid: bool
    quality_score: float
    errors: list[str]
    warnings: list[str]
    fingerprint: str
    normalized_answers: list[str]


def compute_record_fingerprint(question: str, options: dict[str, str]) -> str:
    question_part = _normalize_text(question).lower()
    option_parts = []
    for key in sorted(options.keys()):
        option_parts.append(f"{key}:{_normalize_text(options[key]).lower()}")
    payload = f"{question_part}|{'|'.join(option_parts)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def validate_record_payload(
    *,
    question: str,
    options: dict[str, str],
    answers: list[str],
    confidence: float,
    require_answers: bool,
    min_quality_score: float,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    normalized_question = _normalize_text(question)
    if len(normalized_question) < 12:
        errors.append("question_too_short")

    cleaned_options: dict[str, str] = {}
    for key, value in options.items():
        clean_key = (key or "").strip().upper()
        clean_value = _normalize_text(value)
        if clean_key and clean_value:
            cleaned_options[clean_key] = clean_value

    if len(cleaned_options) < 2:
        errors.append("insufficient_options")

    value_set = {value.lower() for value in cleaned_options.values()}
    if len(value_set) != len(cleaned_options):
        warnings.append("duplicate_option_values")

    cleaned_answers: list[str] = []
    for answer in answers:
        clean_answer = (answer or "").strip().upper()
        if clean_answer and clean_answer not in cleaned_answers:
            cleaned_answers.append(clean_answer)

    valid_answer_keys = set(cleaned_options.keys())
    consistent_answers = [ans for ans in cleaned_answers if ans in valid_answer_keys]

    if cleaned_answers and not consistent_answers:
        errors.append("answers_not_in_options")
    elif cleaned_answers and len(consistent_answers) < len(cleaned_answers):
        warnings.append("partial_answer_mismatch")

    if require_answers and not consistent_answers:
        errors.append("answers_required")

    answer_consistency = 1.0
    if cleaned_answers:
        answer_consistency = len(consistent_answers) / len(cleaned_answers)
    elif require_answers:
        answer_consistency = 0.0

    option_quality = 1.0 if len(cleaned_options) >= 4 else 0.75 if len(cleaned_options) >= 2 else 0.0
    confidence_value = max(0.0, min(1.0, float(confidence or 0.0)))

    quality_score = round(
        (0.6 * confidence_value) + (0.25 * answer_consistency) + (0.15 * option_quality),
        3,
    )

    if quality_score < min_quality_score:
        errors.append("quality_below_threshold")

    fingerprint = compute_record_fingerprint(normalized_question, cleaned_options)

    return ValidationReport(
        valid=len(errors) == 0,
        quality_score=quality_score,
        errors=errors,
        warnings=warnings,
        fingerprint=fingerprint,
        normalized_answers=consistent_answers,
    )
