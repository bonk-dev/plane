# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): PDF version of the project time report (estimate vs. logged time).
# Strings are intentionally hardcoded in Polish.

# Python imports
import io
import logging
import os
from datetime import datetime
from xml.sax.saxutils import escape

# Third Party imports
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger("plane.api")

# DejaVu has the Polish characters (ą, ę, ł, ś, ż…) that the built-in Helvetica lacks.
# Docker images install it with `apk add font-dejavu`.
FONT_CANDIDATES = (
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),  # Alpine
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),  # Arch
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),  # Debian/Ubuntu
)
ESTIMATE_COLOR = colors.HexColor("#9AA5B1")
LOGGED_COLOR = colors.HexColor("#3F76FF")
OVER_COLOR = colors.HexColor("#C0392B")
UNDER_COLOR = colors.HexColor("#1E8449")
HEADER_BG = colors.HexColor("#EEF1F5")
STRIPE_BG = colors.HexColor("#F8F9FB")
GRID_COLOR = colors.HexColor("#C9CED6")

_fonts = None


def _register_fonts():
    """(regular, bold) font names; falls back to Helvetica when DejaVu is not installed."""
    global _fonts
    if _fonts is None:
        for regular, bold in FONT_CANDIDATES:
            if os.path.exists(regular) and os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("ReportSans", regular))
                pdfmetrics.registerFont(TTFont("ReportSans-Bold", bold))
                pdfmetrics.registerFontFamily("ReportSans", normal="ReportSans", bold="ReportSans-Bold")
                _fonts = ("ReportSans", "ReportSans-Bold")
                break
        else:
            logger.warning("DejaVu fonts not found, time report PDF falls back to Helvetica (no Polish characters)")
            _fonts = ("Helvetica", "Helvetica-Bold")
    return _fonts


def _num(value, signed=False):
    """1.5 -> "1,50" (Polish decimal comma); None stays empty."""
    if value is None or isinstance(value, str):
        return value or ""
    text = f"{value:+.2f}" if signed else f"{value:.2f}"
    return text.replace(".", ",")


def _date(value):
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d")


def _short(text, limit=22):
    return text if len(text) <= limit else text[: limit - 1] + "…"


class _Styles:
    def __init__(self):
        self.font, self.bold = _register_fonts()
        self.title = ParagraphStyle("title", fontName=self.bold, fontSize=16, leading=20, spaceAfter=2)
        self.subtitle = ParagraphStyle(
            "subtitle", fontName=self.font, fontSize=9, leading=12, textColor=colors.HexColor("#555555")
        )
        self.heading = ParagraphStyle(
            "heading", fontName=self.bold, fontSize=12, leading=15, spaceBefore=10, spaceAfter=6
        )
        self.cell = ParagraphStyle("cell", fontName=self.font, fontSize=7.5, leading=9)
        self.head = ParagraphStyle("head", fontName=self.bold, fontSize=7.5, leading=9)
        self.note = ParagraphStyle(
            "note", fontName=self.font, fontSize=8, leading=10, spaceBefore=4, textColor=colors.HexColor("#555555")
        )

    def table(self, header, rows, col_widths, numeric_from=None, extra=()):
        # Paragraph headers wrap instead of overflowing narrow columns
        data = [[Paragraph(escape(text), self.head) for text in header], *rows]
        table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        style = [
            ("FONTNAME", (0, 0), (-1, -1), self.font),
            ("FONTNAME", (0, 0), (-1, 0), self.bold),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("LEADING", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE_BG]),
            ("GRID", (0, 0), (-1, -1), 0.25, GRID_COLOR),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if numeric_from is not None:
            style.append(("ALIGN", (numeric_from, 1), (-1, -1), "RIGHT"))
        style.extend(extra)
        table.setStyle(TableStyle(style))
        return table


def _issue_table(report, styles, width):
    header = [
        "ID",
        "Nazwa",
        "Wykonawca",
        "Estymata [h]",
        "Wykonanie [h]",
        "Różnica [h]",
        "Start",
        "Plan. zakończenie",
        "Fakt. zakończenie",
    ]
    data = []
    extra = []
    for i, row in enumerate(report["people"], start=1):
        data.append(
            [
                row["identifier"],
                Paragraph(escape(row["name"]), styles.cell),
                Paragraph(escape(row["display_name"] or "(nieprzypisane)"), styles.cell),
                _num(row["estimate"]),
                _num(row["logged_hours"]),
                _num(row["difference_h"], signed=True),
                _date(row["start_date"]),
                _date(row["target_date"]),
                _date(row["completed_at"]),
            ]
        )
        if row["difference_h"] is not None and row["difference_h"] != 0:
            extra.append(("TEXTCOLOR", (5, i), (5, i), OVER_COLOR if row["difference_h"] > 0 else UNDER_COLOR))
        if row["delay_days"] is not None and row["delay_days"] > 0:
            extra.append(("TEXTCOLOR", (8, i), (8, i), OVER_COLOR))
    widths = [width * f for f in (0.075, 0.27, 0.12, 0.075, 0.08, 0.075, 0.095, 0.105, 0.105)]
    # Long project identifiers ("APACHESEC-12") must not run into the name column; the name wraps instead
    id_width = max(pdfmetrics.stringWidth(row["identifier"], styles.font, 7.5) for row in report["people"]) + 14
    if id_width > widths[0]:
        widths[1] -= id_width - widths[0]
        widths[0] = id_width
    return styles.table(header, data, widths, extra=[("ALIGN", (3, 1), (5, -1), "RIGHT"), *extra])


def _summary_table(rows, label_key, label, styles, width):
    header = [label, "Estymata [h]", "Wykonanie [h]", "Zadania", "Zamknięte"]
    data = []
    for row in rows:
        data.append(
            [
                Paragraph(escape(row[label_key] or "(nieprzypisane)"), styles.cell),
                _num(row["estimate_h"]),
                _num(row["logged_h"]),
                row["issues"],
                row["closed_issues"],
            ]
        )
    fractions = (0.4, 0.15, 0.15, 0.15, 0.15)
    return styles.table(header, data, [width * 0.6 * f for f in fractions], numeric_from=1)


def _bar_chart(title, rows, label_key, styles, width):
    """Grouped bars: estimate vs. logged hours per person."""
    height = 230
    drawing = Drawing(width, height)
    estimates = [row["estimate_h"] for row in rows]  # None = no estimate, no bar (not a zero)
    logged = [row["logged_h"] for row in rows]
    top = max([value for value in estimates + logged if value is not None] + [1])

    chart = VerticalBarChart()
    chart.x, chart.y = 40, 55
    chart.width, chart.height = width - 180, height - 90
    chart.data = [estimates, logged]
    chart.categoryAxis.categoryNames = [_short(row[label_key] or "(nieprzypisane)") for row in rows]
    chart.categoryAxis.labels.fontName = styles.font
    chart.categoryAxis.labels.fontSize = 7
    if len(rows) > 5:
        chart.categoryAxis.labels.angle = 30
        chart.categoryAxis.labels.boxAnchor = "ne"
        chart.categoryAxis.labels.dy = -2
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = top * 1.15
    chart.valueAxis.labels.fontName = styles.font
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labelTextFormat = lambda value: _num(value).rstrip("0").rstrip(",")
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.gridStrokeColor = GRID_COLOR
    chart.valueAxis.gridStrokeWidth = 0.25
    chart.bars.strokeColor = None
    chart.bars[0].fillColor = ESTIMATE_COLOR
    chart.bars[1].fillColor = LOGGED_COLOR
    chart.barSpacing = 1
    chart.groupSpacing = 8
    if len(rows) <= 12:
        chart.barLabelFormat = lambda value: _num(value)
        chart.barLabels.fontName = styles.font
        chart.barLabels.fontSize = 6
        chart.barLabels.nudge = 6

    legend = Legend()
    legend.x, legend.y = width - 120, height - 40
    legend.fontName = styles.font
    legend.fontSize = 8
    legend.alignment = "right"
    legend.colorNamePairs = [(ESTIMATE_COLOR, "Estymata [h]"), (LOGGED_COLOR, "Wykonanie [h]")]

    drawing.add(String(0, height - 14, title, fontName=styles.bold, fontSize=10))
    drawing.add(chart)
    drawing.add(legend)
    return drawing


def _group_section(title, label, rows, label_key, styles, width):
    """Heading, summary table and chart kept on one page when they fit."""
    flowables = [Paragraph(title, styles.heading)]
    if not rows:
        return [KeepTogether(flowables + [Paragraph("Brak danych.", styles.note)])]
    flowables.append(_summary_table(rows, label_key, label, styles, width))
    flowables.append(Spacer(1, 4 * mm))
    flowables.append(_bar_chart("Estymata vs. wykonanie [h]", rows, label_key, styles, width))
    return [KeepTogether(flowables)]


def time_report_pdf(project, report, tz):
    """PDF bytes: header, work item table, summary per person with a bar chart."""
    styles = _Styles()
    generated_at = datetime.now(tz)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Raport czasu — {project.name}",
        author="Plane",
    )
    width = doc.width

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont(styles.font, 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(doc_.leftMargin, 8 * mm, f"{project.name} ({project.identifier}) — raport czasu")
        canvas.drawRightString(doc_.leftMargin + doc_.width, 8 * mm, f"Strona {doc_.page}")
        canvas.restoreState()

    total = report["summary"]["total"]
    story = [
        Paragraph(f"Raport czasu: {escape(project.name)}", styles.title),
        Paragraph(
            f"Projekt {escape(project.identifier)} · wygenerowano {generated_at:%Y-%m-%d %H:%M} ({escape(str(tz))})",
            styles.subtitle,
        ),
        Paragraph(
            f"Suma estymat: <b>{_num(total['estimate_h']) or '—'} h</b> · "
            f"suma wykonania: <b>{_num(total['logged_h'])} h</b> · "
            f"zadań: <b>{total['issues']}</b> · zamkniętych: <b>{total['closed_issues']}</b>",
            styles.subtitle,
        ),
        Spacer(1, 4 * mm),
        Paragraph("Zadania", styles.heading),
    ]
    if report["people"]:
        story.append(_issue_table(report, styles, width))
        story.append(
            Paragraph(
                "Wykonanie i różnica dotyczą czasu zalogowanego przez daną osobę; estymata dotyczy całego zadania. "
                "Różnica = wykonanie − estymata (czerwona: przekroczenie). "
                "Fakt. zakończenie na czerwono: po planowanym terminie.",
                styles.note,
            )
        )
    else:
        story.append(Paragraph("Brak zadań z estymatą lub zalogowanym czasem.", styles.note))

    summary = report["summary"]
    story += _group_section("Podsumowanie per osoba", "Osoba", summary["people"], "display_name", styles, width)

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
