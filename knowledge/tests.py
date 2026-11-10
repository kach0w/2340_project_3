from django.test import SimpleTestCase, TestCase, TransactionTestCase

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


class DocumentManagementTests(TestCase):
    """Story 5: define and update the dataset from the website."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_user('staff', password='pw', is_staff=True))
        self.doc = ingest_text('Floods', 'Move to higher ground during a flash flood warning.')

    def test_edit_updates_text_and_rechunks(self):
        from django.urls import reverse
        resp = self.client.post(reverse('knowledge.edit', args=[self.doc.id]), {
            'title': 'Floods (updated)', 'source_url': '',
            'raw_text': 'Never drive through flood water. Turn around, do not drown.', 'is_active': 'on',
        })
        self.assertRedirects(resp, reverse('knowledge.document_detail', args=[self.doc.id]))
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.title, 'Floods (updated)')
        chunks = ' '.join(self.doc.chunks.values_list('content', flat=True))
        self.assertIn('Turn around', chunks)
        self.assertNotIn('higher ground', chunks)

    def test_edit_page_loads(self):
        from django.urls import reverse
        self.assertContains(self.client.get(reverse('knowledge.edit', args=[self.doc.id])), 'Edit document')

    def test_toggle_deactivates_and_reactivates(self):
        from django.urls import reverse
        url = reverse('knowledge.toggle', args=[self.doc.id])
        self.client.post(url)
        self.doc.refresh_from_db()
        self.assertFalse(self.doc.is_active)
        self.client.post(url)
        self.doc.refresh_from_db()
        self.assertTrue(self.doc.is_active)

    def test_inactive_document_not_retrieved(self):
        from chat.rag import retrieve
        self.assertTrue(retrieve('flash flood warning'))
        Document.objects.filter(pk=self.doc.pk).update(is_active=False)
        self.assertEqual(retrieve('flash flood warning'), [])

    def test_list_shows_status_and_actions(self):
        from django.urls import reverse
        html = self.client.get(reverse('knowledge.documents')).content.decode()
        for text in ('active', 'Edit', 'Deactivate'):
            self.assertIn(text, html)

    def test_non_staff_cannot_edit(self):
        from django.contrib.auth.models import User
        from django.urls import reverse
        self.client.force_login(User.objects.create_user('regular', password='pw'))
        self.assertEqual(self.client.post(reverse('knowledge.toggle', args=[self.doc.id])).status_code, 302)
        self.doc.refresh_from_db()
        self.assertTrue(self.doc.is_active)


class AlertAreaTests(TestCase):
    """Custom story 2: staff tag alerts with the areas they apply to."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.staff = User.objects.create_user('admin', password='pw12345!', is_staff=True)
        self.client.force_login(self.staff)

    def test_parse_areas_normalizes_and_rejects_bad_values(self):
        from .location import parse_areas
        self.assertEqual(parse_areas('30332, 303  30332-0001,30318'), ['30332', '303', '30318'])
        self.assertEqual(parse_areas(''), [])
        with self.assertRaises(ValueError):
            parse_areas('30332, atlanta, 1234')

    def test_applies_to(self):
        doc = Document(title='x', source_type=Document.SOURCE_TEXT, alert_areas='30332, 331')
        self.assertTrue(doc.applies_to('30332'))
        self.assertTrue(doc.applies_to('33139'))
        self.assertFalse(doc.applies_to('30309'))
        self.assertTrue(doc.applies_to(None))
        general = Document(title='y', source_type=Document.SOURCE_TEXT)
        self.assertTrue(general.applies_to('99999'))
        self.assertFalse(general.is_local)

    def test_ingest_text_with_alert_areas(self):
        self.client.post('/knowledge/ingest/text/', {
            'title': 'Tornado warning', 'text': 'Take shelter in an interior room now.',
            'alert_areas': '30332 30318',
        })
        self.assertEqual(Document.objects.get(title='Tornado warning').alert_areas, '30332, 30318')

    def test_invalid_alert_areas_are_rejected_on_ingest(self):
        self.client.post('/knowledge/ingest/text/', {
            'title': 'Bad', 'text': 'Take shelter in an interior room now.', 'alert_areas': 'Atlanta',
        })
        self.assertFalse(Document.objects.filter(title='Bad').exists())

    def test_edit_alert_areas(self):
        doc = ingest_text('Heat advisory', 'Stay hydrated and avoid outdoor work this afternoon.')
        self.client.post(f'/knowledge/{doc.id}/edit/', {
            'title': doc.title, 'source_url': '', 'alert_areas': '303',
            'raw_text': doc.raw_text, 'is_active': 'on',
        })
        doc.refresh_from_db()
        self.assertEqual(doc.alert_areas, '303')

    def test_list_shows_alert_area(self):
        ingest_text('Local alert', 'Boil water notice for the neighborhood.', alert_areas='30332')
        ingest_text('Everywhere', 'Keep a three day supply of water.')
        html = self.client.get('/knowledge/').content.decode()
        self.assertIn('30332', html)
        self.assertIn('All areas', html)


class EmbeddingTests(SimpleTestCase):
    def test_embedding_request_and_vector(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from django.test import override_settings
        from .embeddings import EMBEDDING_MODEL, embed_text
        with override_settings(GOOGLE_API_KEY='test-key'), patch('knowledge.embeddings._client') as client:
            client.return_value.models.embed_content.return_value = SimpleNamespace(
                embeddings=[SimpleNamespace(values=[1.0, 2.0])])
            self.assertEqual(embed_text('Shelter guidance', 'RETRIEVAL_DOCUMENT'), [1.0, 2.0])
            args = client.return_value.models.embed_content.call_args.kwargs
            self.assertEqual(args['model'], EMBEDDING_MODEL)
            self.assertEqual(args['contents'], 'Shelter guidance')
            self.assertEqual(args['config'].task_type, 'RETRIEVAL_DOCUMENT')

    def test_empty_input_or_missing_key_skips_api(self):
        from unittest.mock import patch
        from django.test import override_settings
        from .embeddings import embed_text
        with patch('knowledge.embeddings._client') as client:
            with override_settings(GOOGLE_API_KEY=''):
                self.assertIsNone(embed_text('text', 'RETRIEVAL_QUERY'))
            with override_settings(GOOGLE_API_KEY='test-key'):
                self.assertIsNone(embed_text('', 'RETRIEVAL_QUERY'))
            client.assert_not_called()

    def test_empty_response_and_api_failure(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from django.test import override_settings
        from .embeddings import embed_text
        with override_settings(GOOGLE_API_KEY='test-key'), patch('knowledge.embeddings._client') as client:
            for embeddings in ([], [SimpleNamespace(values=[])]):
                client.return_value.models.embed_content.return_value = SimpleNamespace(embeddings=embeddings)
                with self.assertRaises(ValueError):
                    embed_text('text', 'RETRIEVAL_QUERY')
            client.return_value.models.embed_content.side_effect = RuntimeError('API unavailable')
            with self.assertRaises(RuntimeError):
                embed_text('text', 'RETRIEVAL_QUERY')

    def test_cosine_similarity(self):
        from .embeddings import cosine_similarity
        for a, b, expected in [([1, 2], [2, 4], 1), ([1, 0], [0, 1], 0),
                               ([1, 0], [-1, 0], -1), ([0, 0], [1, 0], 0),
                               ([], [1], 0), (None, [1], 0), ([1], [1, 2], 0)]:
            with self.subTest(a=a, b=b):
                self.assertAlmostEqual(cosine_similarity(a, b), expected)


class EmbeddingIngestionTests(TransactionTestCase):
    def test_embeddings_prepared_outside_transaction_and_reload_replaces(self):
        from unittest.mock import patch
        from django.db import connection
        from .ingestion import process_document
        doc = Document.objects.create(title='Test', source_type='text', raw_text='Move to higher ground during a flood warning.')
        def embed(content, task):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(content, doc.raw_text)
            self.assertEqual(task, 'RETRIEVAL_DOCUMENT')
            return [1.0, 0.0]
        with patch('knowledge.ingestion.embed_text', side_effect=embed):
            process_document(doc)
            process_document(doc)
        self.assertEqual(doc.chunks.count(), 1)
        self.assertEqual(doc.chunks.get().embedding, [1.0, 0.0])

    def test_api_failure_preserves_chunk_without_embedding(self):
        from unittest.mock import patch
        with patch('knowledge.ingestion.embed_text', side_effect=RuntimeError('API unavailable')):
            with self.assertLogs('knowledge.ingestion', level='ERROR'):
                doc = ingest_text('Test', 'Move to higher ground during a flood warning.')
        self.assertIsNone(doc.chunks.get().embedding)

    def test_missing_key_result_preserves_chunk(self):
        from unittest.mock import patch
        with patch('knowledge.ingestion.embed_text', return_value=None):
            doc = ingest_text('Test', 'Move to higher ground during a flood warning.')
        self.assertIsNone(doc.chunks.get().embedding)

    def test_replacement_failure_rolls_back_old_chunks_and_cleaned_text(self):
        from unittest.mock import patch
        from .ingestion import process_document
        with patch('knowledge.ingestion.embed_text', return_value=[1, 0]):
            doc = ingest_text('Test', 'Original flood safety guidance for every household.')
        old_pk = doc.chunks.get().pk
        old_cleaned = doc.cleaned_text
        doc.raw_text = 'Updated guidance about evacuation routes and shelters.'
        with patch('knowledge.ingestion.embed_text', return_value=[0, 1]), patch('knowledge.ingestion.Chunk.objects.bulk_create', side_effect=RuntimeError('write failed')):
            with self.assertRaises(RuntimeError):
                process_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.cleaned_text, old_cleaned)
        self.assertEqual(doc.chunks.get().pk, old_pk)
