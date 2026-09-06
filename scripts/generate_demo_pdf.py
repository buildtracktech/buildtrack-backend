"""Создать приёмочный PDF по фундаменту для проверки BuildTrack Backend."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


DEFAULT_OUTPUT = Path("output/pdf/buildtrack-primer-fundament.pdf")
FONT_NAME = "BuildTrackExample"
FONT_BOLD_NAME = "BuildTrackExampleBold"
FONT_CANDIDATES = (
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
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
    raise RuntimeError("Для PDF требуется шрифт DejaVu Sans или Arial")


def generate_demo_pdf(output_path: Path) -> Path:
    """Создать приёмочный PDF с одним намеренно пропущенным полем."""

    _register_fonts()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    pdf.setTitle("BuildTrack - приёмочная документация по фундаменту")
    pdf.setAuthor("BuildTrack")
    pdf.setFillColor(colors.HexColor("#123B5D"))
    pdf.setFont(FONT_BOLD_NAME, 16)
    pdf.drawString(20 * mm, height - 24 * mm, "BUILDTRACK")

    pdf.setFillColor(colors.HexColor("#B42318"))
    pdf.setFont(FONT_BOLD_NAME, 11)
    pdf.drawString(
        20 * mm,
        height - 34 * mm,
        "ПРИЁМОЧНЫЙ ПРИМЕР - НЕ ДЛЯ СТРОИТЕЛЬСТВА",
    )

    pdf.setFillColor(colors.HexColor("#1F2937"))
    pdf.setFont(FONT_BOLD_NAME, 13)
    pdf.drawString(20 * mm, height - 46 * mm, "Документация этапа «Фундамент»")

    rows = [
        ("Проект", "Приёмка BuildTrack Backend"),
        ("Этап", "Фундамент"),
        ("Код документа", "BT-PD-TEST-002"),
        ("Редакция", "1.0"),
        ("Назначение", "Проверка работы BuildTrack Backend"),
    ]
    y = height - 62 * mm
    for label, value in rows:
        pdf.setFillColor(colors.HexColor("#EAF1F6"))
        pdf.rect(18 * mm, y - 2.4 * mm, width - 36 * mm, 8 * mm, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#1F2937"))
        pdf.setFont(FONT_BOLD_NAME, 10)
        pdf.drawString(20 * mm, y, label)
        pdf.setFont(FONT_NAME, 10)
        pdf.drawString(62 * mm, y, value)
        y -= 10 * mm

    pdf.setFont(FONT_BOLD_NAME, 11)
    pdf.drawString(20 * mm, y - 4 * mm, "Назначение документа")
    pdf.setFont(FONT_NAME, 9)
    text = pdf.beginText(20 * mm, y - 12 * mm)
    text.setLeading(5 * mm)
    for line in (
        "Этот приёмочный файл проверяет загрузку PDF и расчёт контрольной суммы,",
        "версионирование, нормативные правила, замечания и формирование отчёта.",
        "Файл не содержит утверждённых проектных решений или реальных нормативов.",
        "Одна обязательная строка намеренно отсутствует для проверки замечания.",
    ):
        text.textLine(line)
    pdf.drawText(text)

    pdf.setFillColor(colors.HexColor("#B42318"))
    pdf.setFont(FONT_BOLD_NAME, 9)
    pdf.drawString(
        20 * mm,
        18 * mm,
        "Контрольные данные. Не использовать для строительства или юридической приёмки.",
    )
    pdf.setFillColor(colors.black)
    pdf.showPage()
    pdf.save()
    return output_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output PDF path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    print(generate_demo_pdf(args.output))


if __name__ == "__main__":
    main()
