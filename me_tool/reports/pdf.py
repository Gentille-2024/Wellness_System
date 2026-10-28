"""The monthly report as a PDF (an HTML template printed by WeasyPrint)."""

from django.conf import settings
from django.template.loader import render_to_string


def build_pdf(data, report):
    # Imported here: WeasyPrint needs system libraries (Pango) that the Docker
    # image has, so the rest of the tool also runs where they are missing
    from weasyprint import HTML

    html = render_to_string("reports/report_pdf.html", {**data, "report": report})
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
