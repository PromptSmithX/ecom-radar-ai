"""Renderer for generating Markdown reports from FinalReport models using Jinja2."""

from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from src.core.config import BASE_DIR, settings
from src.core.models import FinalReport


import unicodedata

def slugify(text: str) -> str:
    """Converts string into clean ASCII slug format."""
    # Normalize unicode to remove accents (e.g. quà tặng -> qua tang)
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ASCII", "ignore").decode("utf-8")
    ascii_text = ascii_text.lower()
    clean = re.sub(r"[^\w\-_]", "_", ascii_text)
    return re.sub(r"_+", "_", clean).strip("_")


class ReportRenderer:
    def __init__(self, template_path: Path | None = None, output_dir: Path | None = None):
        tpl_path = template_path or (BASE_DIR / settings.reporting.template_path)
        self.output_dir = output_dir or (BASE_DIR / settings.reporting.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        env = Environment(loader=FileSystemLoader(str(tpl_path.parent)), autoescape=False)
        self.template = env.get_template(tpl_path.name)

    def render(self, report: FinalReport) -> str:
        """Renders the FinalReport object into a Markdown string."""
        return self.template.render(report=report)

    def save(self, report: FinalReport, filename: str | None = None) -> Path:
        """Renders and saves the report to the reports directory."""
        content = self.render(report)
        if not filename:
            date_str = datetime.now().strftime("%Y-%m-%d")
            cat_slug = slugify(report.category)
            filename = f"{date_str}_{cat_slug}.md"

        target_file = self.output_dir / filename
        target_file.write_text(content, encoding="utf-8")
        return target_file
