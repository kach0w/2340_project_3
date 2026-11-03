"""Ingestion + preprocessing pipeline (stories 6 & 7).

Ingestion methods:
  - ingest_file: direct file upload (.txt / .md; TODO: PDF)
  - ingest_url: web scrape
  - ingest_text: pasted text
  - TODO: ingest_api (e.g. FEMA / ReliefWeb / NWS APIs)
"""
import re
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction

from .models import Chunk, Document


# ---------- cleaning ----------

def clean_text(text):
    """Normalize whitespace and strip junk before chunking."""
    text = text.replace('\r\n', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # TODO: strip boilerplate (nav/footer text, cookie banners), dedupe, etc.
    return text.strip()


def chunk_text(text, size=None, overlap=None):
    size = size or settings.RAG_CHUNK_SIZE
    overlap = overlap or settings.RAG_CHUNK_OVERLAP
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


@transaction.atomic
def process_document(document):
    """Clean + (re)chunk a document. Safe to call again to reload it."""
    document.cleaned_text = clean_text(document.raw_text)
    document.save()
    document.chunks.all().delete()
    Chunk.objects.bulk_create([
        Chunk(document=document, chunk_index=i, content=c)
        for i, c in enumerate(chunk_text(document.cleaned_text))
    ])
    # TODO: compute embeddings for each chunk
    return document


# ---------- ingestion methods ----------

def ingest_text(title, text):
    doc = Document.objects.create(title=title, source_type=Document.SOURCE_TEXT, raw_text=text)
    return process_document(doc)


def ingest_file(title, uploaded_file):
    text = uploaded_file.read().decode('utf-8', errors='ignore')
    uploaded_file.seek(0)
    doc = Document.objects.create(
        title=title, source_type=Document.SOURCE_UPLOAD, file=uploaded_file, raw_text=text,
    )
    return process_document(doc)


class _TextExtractor(HTMLParser):
    SKIP = {'script', 'style', 'nav', 'footer', 'header'}

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def ingest_url(title, url):
    req = Request(url, headers={'User-Agent': 'DisasterBot/0.1'})
    with urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
    parser = _TextExtractor()
    parser.feed(html)
    doc = Document.objects.create(
        title=title, source_type=Document.SOURCE_URL, source_url=url, raw_text='\n'.join(parser.parts),
    )
    return process_document(doc)


# ---------- admin controls (story 11) ----------

def clear_knowledge_base():
    Document.objects.all().delete()


def reload_knowledge_base():
    for doc in Document.objects.all():
        process_document(doc)
