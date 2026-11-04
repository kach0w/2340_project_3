from django.test import TestCase

from .ingestion import chunk_text, clean_text, ingest_text
from .models import Document


class CleanTextTests(TestCase):
    def test_removes_boilerplate_lines(self):
        raw = 'Skip to content\nAccept all cookies\nEvacuate via Highway 101.\nSubscribe now\nPrivacy Policy'
        self.assertEqual(clean_text(raw), 'Evacuate via Highway 101.')

    def test_removes_duplicate_lines(self):
        raw = 'Shelters open at Lincoln High School.\nshelters open at lincoln high school!\nBring ID.'
        self.assertEqual(clean_text(raw).count('Lincoln'), 1)

    def test_normalizes_whitespace_and_hidden_chars(self):
        raw = 'Stay\u200b   calm.\r\n\r\n\r\n\r\nCall   911.'
        self.assertEqual(clean_text(raw), 'Stay calm.\n\nCall 911.')

    def test_decodes_entities_and_strips_tags(self):
        self.assertEqual(clean_text('Fire &amp; smoke <b>warning</b>'), 'Fire & smoke warning')

    def test_rejoins_hyphenated_breaks(self):
        self.assertEqual(clean_text('Begin evacu-\nation now.'), 'Begin evacuation now.')

    def test_empty_input(self):
        self.assertEqual(clean_text(''), '')
        self.assertEqual(clean_text(None), '')


class ChunkTextTests(TestCase):
    def test_short_text_single_chunk(self):
        self.assertEqual(chunk_text('Move to higher ground immediately.', size=200, overlap=20),
                         ['Move to higher ground immediately.'])

    def test_respects_size_and_never_cuts_mid_word(self):
        text = ' '.join(f'Sentence number {i} tells you to stay safe.' for i in range(60))
        chunks = chunk_text(text, size=200, overlap=50)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 200)
            self.assertTrue(c.endswith('.'), c)         # ends on a sentence boundary

    def test_overlap_repeats_trailing_sentence(self):
        text = ' '.join(f'Step {i} is to check the shelter list carefully.' for i in range(20))
        chunks = chunk_text(text, size=150, overlap=60)
        last_sentence_of_first = chunks[0].split('. ')[-1]
        self.assertIn(last_sentence_of_first.rstrip('.'), chunks[1])

    def test_oversized_sentence_is_split_on_spaces(self):
        chunks = chunk_text('word ' * 100, size=60, overlap=0)
        self.assertTrue(all(len(c) <= 60 for c in chunks))

    def test_drops_tiny_fragments(self):
        text = 'A long enough sentence about flood safety procedures.\n\nOK.'
        self.assertNotIn('OK.', chunk_text(text, size=60, overlap=0))


class IngestPipelineTests(TestCase):
    def test_ingest_text_cleans_then_chunks(self):
        doc = ingest_text('Test', 'Skip to content\n\nFlood warning in effect.\nFlood warning in effect.\n')
        doc.refresh_from_db()
        self.assertEqual(doc.cleaned_text, 'Flood warning in effect.')
        self.assertEqual(doc.chunks.count(), 1)
        self.assertEqual(doc.raw_text.count('Skip to content'), 1)   # raw text preserved

    def test_reload_rebuilds_chunks_without_duplicates(self):
        from .ingestion import reload_knowledge_base
        ingest_text('Test', 'Evacuation routes are posted at every shelter entrance.')
        reload_knowledge_base()
        self.assertEqual(Document.objects.get().chunks.count(), 1)
# Create your tests here.
