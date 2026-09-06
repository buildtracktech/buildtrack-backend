import hashlib
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.enums import FindingKind, FindingSeverity, NormativeRuleType
from app.models import CheckNormativeSnapshot


class CheckExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class FindingCandidate:
    normative_snapshot_id: int | None
    kind: FindingKind
    severity: FindingSeverity
    title: str
    description: str
    recommendation: str | None
    page_number: int | None
    evidence_text: str | None


def extract_pdf_pages(path: Path) -> list[str]:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise CheckExecutionError("Зашифрованные PDF-документы не поддерживаются")
        return [(page.extract_text() or "") for page in reader.pages]
    except CheckExecutionError:
        raise
    except (OSError, PdfReadError, ValueError) as exc:
        raise CheckExecutionError("Не удалось извлечь текст из PDF-документа") from exc


def extracted_text_hash(pages: list[str]) -> str:
    return hashlib.sha256("\f".join(pages).encode("utf-8")).hexdigest()


def _configured_phrase(snapshot: CheckNormativeSnapshot) -> str | None:
    config = snapshot.rule_config or {}
    phrase = config.get("phrase")
    if not isinstance(phrase, str) or not phrase.strip():
        return None
    return phrase.strip()


def _find_phrase(pages: list[str], phrase: str) -> tuple[int, str] | None:
    wanted = phrase.casefold()
    for page_number, page_text in enumerate(pages, start=1):
        normalized = " ".join(page_text.split())
        index = normalized.casefold().find(wanted)
        if index >= 0:
            start = max(0, index - 80)
            end = min(len(normalized), index + len(phrase) + 80)
            return page_number, normalized[start:end]
    return None


def evaluate_rule(
    snapshot: CheckNormativeSnapshot,
    pages: list[str],
) -> FindingCandidate | None:
    rule_type = NormativeRuleType(snapshot.rule_type)
    if rule_type == NormativeRuleType.MANUAL_REVIEW:
        return FindingCandidate(
            normative_snapshot_id=snapshot.id,
            kind=FindingKind.MANUAL_REVIEW,
            severity=FindingSeverity.INFO,
            title=f"Требуется ручная проверка: {snapshot.document_code}",
            description=snapshot.requirement_text,
            recommendation=snapshot.recommendation,
            page_number=None,
            evidence_text=None,
        )

    phrase = _configured_phrase(snapshot)
    if phrase is None:
        return FindingCandidate(
            normative_snapshot_id=snapshot.id,
            kind=FindingKind.MANUAL_REVIEW,
            severity=FindingSeverity.INFO,
            title=f"Требуется проверить настройку правила: {snapshot.document_code}",
            description="В автоматическом правиле не задана непустая настройка 'phrase'.",
            recommendation="Настроить правило и повторить проверку.",
            page_number=None,
            evidence_text=None,
        )

    match = _find_phrase(pages, phrase)
    if rule_type == NormativeRuleType.REQUIRED_PHRASE and match is None:
        return FindingCandidate(
            normative_snapshot_id=snapshot.id,
            kind=FindingKind.NON_COMPLIANCE,
            severity=FindingSeverity(snapshot.severity),
            title=f"Не найдена обязательная информация: {snapshot.document_code}",
            description=snapshot.requirement_text,
            recommendation=snapshot.recommendation,
            page_number=None,
            evidence_text=f"Не найдена обязательная фраза: {phrase}",
        )
    if rule_type == NormativeRuleType.FORBIDDEN_PHRASE and match is not None:
        page_number, evidence = match
        return FindingCandidate(
            normative_snapshot_id=snapshot.id,
            kind=FindingKind.NON_COMPLIANCE,
            severity=FindingSeverity(snapshot.severity),
            title=f"Обнаружено запрещённое содержимое: {snapshot.document_code}",
            description=snapshot.requirement_text,
            recommendation=snapshot.recommendation,
            page_number=page_number,
            evidence_text=evidence,
        )
    return None
