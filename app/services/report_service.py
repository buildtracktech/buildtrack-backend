from html import escape
from functools import partial
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.enums import FindingKind
from app.models import Check


FONT_NAME = "BuildTrackUnicode"
FONT_BOLD_NAME = "BuildTrackUnicodeBold"

CHECK_STATUS_LABELS = {
    "created": "создана",
    "processing": "выполняется",
    "completed": "завершена",
    "failed": "ошибка",
}
CHECK_VERDICT_LABELS = {
    "valid": "соответствует",
    "invalid": "есть несоответствия",
    "manual_review": "требуется ручная проверка",
}
RULE_TYPE_LABELS = {
    "required_phrase": "обязательная фраза",
    "forbidden_phrase": "запрещённая фраза",
    "manual_review": "ручная проверка",
}
FINDING_KIND_LABELS = {
    "non_compliance": "несоответствие",
    "manual_review": "ручная проверка",
}
SEVERITY_LABELS = {
    "info": "информация",
    "minor": "незначительное",
    "major": "существенное",
    "critical": "критическое",
}
FINDING_STATUS_LABELS = {
    "open": "открыто",
    "confirmed": "подтверждено",
    "dismissed": "отклонено",
    "resolved": "устранено",
}


FONT_CANDIDATES = (
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
    (
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ),
    (
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ),
    (
        Path("/Library/Fonts/Arial.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    ),
)


def _register_fonts() -> None:
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    for regular_path, bold_path in FONT_CANDIDATES:
        if regular_path.is_file() and bold_path.is_file():
            pdfmetrics.registerFont(TTFont(FONT_NAME, regular_path))
            pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, bold_path))
            return
    raise RuntimeError(
        "A Unicode report font is required. Install DejaVu Sans or Arial."
    )


def _text(value: object | None) -> str:
    if value is None:
        return "-"
    return escape(str(value))


def _label(labels: dict[str, str], value: object | None) -> str:
    if value is None:
        return "-"
    return labels.get(str(value), str(value))


def _page_footer(canvas, document, *, report_label: str) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(18 * mm, 12 * mm, report_label)
    canvas.drawRightString(
        A4[0] - 18 * mm,
        12 * mm,
        f"Страница {document.page}",
    )
    canvas.restoreState()


def generate_check_report_pdf(check: Check) -> bytes:
    _register_fonts()
    uses_training_rules = any(
        snapshot.is_demo for snapshot in check.normative_snapshots
    )
    has_unvalidated_rules = any(
        not snapshot.expert_validated for snapshot in check.normative_snapshots
    )
    report_label = (
        "BuildTrack - приёмочный отчёт"
        if uses_training_rules
        else "BuildTrack - отчёт проверки"
    )
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"Отчёт проверки BuildTrack №{check.id}",
        author="BuildTrack",
    )
    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BuildTrackTitle",
        parent=base_styles["Title"],
        fontName=FONT_BOLD_NAME,
        fontSize=19,
        leading=23,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#123B5D"),
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "BuildTrackHeading",
        parent=base_styles["Heading2"],
        fontName=FONT_BOLD_NAME,
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#123B5D"),
        spaceBefore=10,
        spaceAfter=7,
    )
    body_style = ParagraphStyle(
        "BuildTrackBody",
        parent=base_styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=5,
    )
    small_style = ParagraphStyle(
        "BuildTrackSmall",
        parent=body_style,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#475569"),
    )
    label_style = ParagraphStyle(
        "BuildTrackLabel",
        parent=small_style,
        fontName=FONT_BOLD_NAME,
        textColor=colors.HexColor("#1F2937"),
    )

    story = [
        Paragraph("BuildTrack", title_style),
        Paragraph("Отчет проверки проектной документации", heading_style),
    ]
    raw_info_rows = [
        ["Проверка", f"#{check.id}"],
        ["Проект", f"#{check.project_id} - {check.project.name}"],
        ["Этап", f"#{check.stage_id} - {check.stage.name}"],
        ["Документ", f"#{check.document_id} - {check.document.title}"],
        ["Версия документа", check.document.version],
        ["Статус", _label(CHECK_STATUS_LABELS, check.status)],
        ["Результат", _label(CHECK_VERDICT_LABELS, check.verdict)],
        ["Алгоритм", check.engine_code],
        ["Страниц", check.pages_count],
        ["SHA-256 документа", check.document_hash_snapshot],
    ]
    info_rows = [
        [Paragraph(_text(label), label_style), Paragraph(_text(value), small_style)]
        for label, value in raw_info_rows
    ]
    info_table = Table(info_rows, colWidths=[46 * mm, 118 * mm], repeatRows=0)
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), FONT_BOLD_NAME),
                ("FONTNAME", (1, 0), (1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1F2937")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF1F6")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([info_table, Spacer(1, 6 * mm)])

    non_compliance_count = sum(
        finding.kind == FindingKind.NON_COMPLIANCE.value
        for finding in check.findings
    )
    manual_count = sum(
        finding.kind == FindingKind.MANUAL_REVIEW.value
        for finding in check.findings
    )
    summary_table = Table(
        [
            ["Нормативов", "Несоответствий", "Ручная проверка", "Всего замечаний"],
            [
                str(len(check.normative_snapshots)),
                str(non_compliance_count),
                str(manual_count),
                str(len(check.findings)),
            ],
        ],
        colWidths=[41 * mm] * 4,
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD_NAME),
                ("FONTNAME", (0, 1), (-1, 1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123B5D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            Paragraph("Сводка", heading_style),
            summary_table,
            Paragraph("Использованные нормативы", heading_style),
        ]
    )

    normative_rows = [["Код", "Версия", "Раздел", "Тип правила", "Проверено экспертом"]]
    normative_rows.extend(
        [
            snapshot.document_code,
            snapshot.version,
            snapshot.section or "-",
            _label(RULE_TYPE_LABELS, snapshot.rule_type),
            "Да" if snapshot.expert_validated else "Нет",
        ]
        for snapshot in check.normative_snapshots
    )
    normative_table = Table(
        normative_rows,
        colWidths=[36 * mm, 20 * mm, 33 * mm, 43 * mm, 32 * mm],
        repeatRows=1,
    )
    normative_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD_NAME),
                ("FONTNAME", (0, 1), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1F6")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([normative_table, Paragraph("Замечания", heading_style)])

    if not check.findings:
        story.append(Paragraph("Автоматические замечания не сформированы.", body_style))
    for index, finding in enumerate(check.findings, start=1):
        details = [
            Paragraph(f"{index}. {_text(finding.title)}", heading_style),
            Paragraph(
                f"Тип: {_text(_label(FINDING_KIND_LABELS, finding.kind))} | "
                f"Важность: {_text(_label(SEVERITY_LABELS, finding.severity))} | "
                f"Статус: {_text(_label(FINDING_STATUS_LABELS, finding.status))} | "
                f"Страница: {_text(finding.page_number)}",
                small_style,
            ),
            Paragraph(f"Описание: {_text(finding.description)}", body_style),
        ]
        if finding.evidence_text:
            details.append(
                Paragraph(f"Основание: {_text(finding.evidence_text)}", body_style)
            )
        if finding.recommendation:
            details.append(
                Paragraph(f"Рекомендация: {_text(finding.recommendation)}", body_style)
            )
        story.append(KeepTogether(details))

    story.extend(
        [
            PageBreak(),
            Paragraph("Ограничения результата", heading_style),
            Paragraph(
                (
                    "Результат приёмочного сценария. Документ не является заключением строительной "
                    "экспертизы, юридическим актом приёмки или разрешением на выполнение "
                    "строительных работ."
                    if uses_training_rules
                    else "Автоматизированный результат не заменяет заключение строительной "
                    "экспертизы, юридический акт приёмки или разрешение на выполнение "
                    "строительных работ."
                )
                + (
                    " Правила без экспертного подтверждения требуют рассмотрения "
                    "квалифицированным специалистом."
                    if has_unvalidated_rules
                    else ""
                ),
                body_style,
            ),
            Paragraph(
                f"Хеш извлеченного текста: {_text(check.extracted_text_hash)}",
                small_style,
            ),
            Paragraph(
                f"Сформировано: {_text(check.completed_at or check.created_at)}",
                small_style,
            ),
        ]
    )
    footer = partial(_page_footer, report_label=report_label)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
