from dataclasses import dataclass
from pathlib import Path
from typing import List

@dataclass
class IngestedPage:
    page_number: int
    text: str
    images: List[bytes]

@dataclass
class IngestedDocument:
    pages: List[IngestedPage]

def ingest_document(pdf_path: Path) -> IngestedDocument:
    """Simulate Docling ingestion. In real code, use Docling API."""
    # Stub: read PDF and extract text
    import fitz  # PyMuPDF
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages.append(IngestedPage(page_number=i+1, text=text, images=[]))
    return IngestedDocument(pages=pages)