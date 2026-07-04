"""Extract raw text from HSK reading exam PDFs."""
import pdfplumber
from pathlib import Path

from etl.logging_config import get_logger

logger = get_logger(__name__)


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_all_pdfs(input_dir: str | Path) -> dict[str, str]:
    """Return mapping of filename -> extracted text for all PDFs in dir."""
    results = {}
    for pdf_file in Path(input_dir).glob("**/*.pdf"):
        try:
            results[pdf_file.name] = extract_text_from_pdf(pdf_file)
            logger.info("Extracted %s", pdf_file.name)
        except Exception:
            logger.exception("Failed to extract %s", pdf_file.name)
    return results
