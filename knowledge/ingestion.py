"""Ingestion + preprocessing pipeline (stories 6 & 7).

Ingestion methods:
  - ingest_file: direct file upload (.txt / .md; TODO: PDF)
  - ingest_url: web scrape
  - ingest_text: pasted text
  - TODO: ingest_api (e.g. FEMA / ReliefWeb / NWS APIs)
"""
from html import unescape
import re
import unicodedata
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction

from .models import Chunk, Document


# ---------- cleaning ----------

# Lines that are web/page boilerplate rather than content (matched on the whole line).
BOILERPLATE_PATTERNS = [
    r'skip to (main )?content',
    r'(accept|reject|manage)( all)?( cookies?| preferences)?',
    r'we use cookies.*',
    r'this (site|website) uses cookies.*',
    r'(subscribe|sign up|log ?in|sign ?in|register)( now| today| for .*)?',
    r'(share|tweet|print|email|follow us)( this)?( page| article)?( on .*)?',
    r'(click|read|learn) more',
    r'(privacy policy|terms( of (use|service))?|cookie policy|all rights reserved.*|copyright .*)',
    r'advertisement',
    r'back to top',
    r'(home|menu|search)',
]
_BOILERPLATE = re.compile(r'^(?:' + '|'.join(BOILERPLATE_PATTERNS) + r')[\s.:!|>\u00bb-]*$', re.I)

_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200d\u2060\ufeff]')
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(\[])')
MIN_CHUNK_CHARS = 30


def clean_text(text):
    """Normalize and strip junk before chunking (story 7).

    - unicode normalization, control / zero-width characters removed
    - HTML entities decoded, leftover tags removed
    - boilerplate lines (cookie banners, nav, share buttons, ...) dropped
    - repeated lines / paragraphs removed (case-insensitive)
    - hyphenated line breaks re-joined, whitespace collapsed
    """
    text = unicodedata.normalize('NFKC', unescape(text or ''))
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _CONTROL_CHARS.sub('', text)
    text = re.sub(r'<[^>]+>', ' ', text)            # stray HTML tags
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)     # "evacu-\nation" -> "evacuation"
    text = re.sub(r'[ \t]+', ' ', text)

    seen, kept = set(), []
    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            kept.append('')                          # keep paragraph breaks
            continue
        if _BOILERPLATE.match(line):
            continue
        key = re.sub(r'\W+', ' ', line.lower()).strip()
        if len(key) > 20:                            # only dedupe substantial lines
            if key in seen:
                continue
            seen.add(key)
        kept.append(line)

    text = '\n'.join(kept)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _split_sentences(paragraph):
    return [s.strip() for s in _SENTENCE_END.split(paragraph) if s.strip()]


def _hard_split(piece, size):
    """Last resort for a single 'sentence' longer than size: split on spaces."""
    words, out, cur = piece.split(' '), [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > size:
            out.append(cur)
            cur = w
        else:
            cur = f'{cur} {w}'.strip()
    if cur:
        out.append(cur)
    return out


def chunk_text(text, size=None, overlap=None):
    """Split text into ~size-character chunks on sentence boundaries.

    Never cuts mid-word; consecutive chunks share up to `overlap` characters
    of trailing sentences so context isn't lost at the boundary. Tiny
    fragments are dropped.
    """
    size = size or settings.RAG_CHUNK_SIZE
    overlap = settings.RAG_CHUNK_OVERLAP if overlap is None else overlap

    units = []
    for para in re.split(r'\n\s*\n', text):
        para = ' '.join(para.split())
        for sentence in _split_sentences(para):
            units.extend([sentence] if len(sentence) <= size else _hard_split(sentence, size))

    chunks, current = [], []
    length = 0
    for unit in units:
        added = len(unit) + (1 if current else 0)
        if current and length + added > size:
            chunks.append(' '.join(current))
            # carry trailing sentences forward as overlap
            carry, carried = [], 0
            for prev in reversed(current):
                if carried + len(prev) + 1 > overlap:
                    break
                carry.insert(0, prev)
                carried += len(prev) + 1
            current, length = carry, sum(len(u) + 1 for u in carry) - (1 if carry else 0)
            added = len(unit) + (1 if current else 0)
        current.append(unit)
        length += added
    if current:
        chunks.append(' '.join(current))

    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS or len(chunks) == 1]


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

def ingest_text(title, text, alert_areas=''):
    doc = Document.objects.create(
        title=title, source_type=Document.SOURCE_TEXT, raw_text=text, alert_areas=alert_areas,
    )
    return process_document(doc)


def ingest_file(title, uploaded_file, alert_areas=''):
    text = uploaded_file.read().decode('utf-8', errors='ignore')
    uploaded_file.seek(0)
    doc = Document.objects.create(
        title=title, source_type=Document.SOURCE_UPLOAD, file=uploaded_file, raw_text=text,
        alert_areas=alert_areas,
    )
    return process_document(doc)


class _TextExtractor(HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'svg', 'nav', 'footer', 'header', 'aside', 'form', 'button'}

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


def ingest_url(title, url, alert_areas=''):
    req = Request(url, headers={'User-Agent': 'DisasterBot/0.1'})
    with urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
    parser = _TextExtractor()
    parser.feed(html)
    doc = Document.objects.create(
        title=title, source_type=Document.SOURCE_URL, source_url=url, raw_text='\n'.join(parser.parts),
        alert_areas=alert_areas,
    )
    return process_document(doc)


# ---------- admin controls (story 11) ----------

def clear_knowledge_base():
    Document.objects.all().delete()


def reload_knowledge_base():
    for doc in Document.objects.all():
        process_document(doc)