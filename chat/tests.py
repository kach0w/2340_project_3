from unittest.mock import patch

from django.test import TestCase

from knowledge.models import Chunk, Document

from .prompts import build_prompt
from .rag import _cited_numbers, answer_question, build_sources, group_sources


def make_doc(title, url='', is_active=True):
    return Document.objects.create(
        title=title, source_type=Document.SOURCE_TEXT, source_url=url, is_active=is_active,
    )


def make_chunk(doc, index, content):
    return Chunk.objects.create(document=doc, chunk_index=index, content=content)


class SourceNumberingTests(TestCase):
    def test_source_numbers_match_prompt_context_order(self):
        a = make_doc('Doc A')
        b = make_doc('Doc B')
        chunks = [make_chunk(a, 0, 'Alpha text about floods.'), make_chunk(b, 0, 'Beta text about fires.')]
        _, _, prompt = build_prompt('what about floods', chunks)
        for src in build_sources(chunks):
            self.assertIn(f"[{src['number']}] " + src['excerpt'], prompt)

    def test_excerpt_is_shortened_on_a_word_boundary(self):
        doc = make_doc('Long')
        chunk = make_chunk(doc, 0, 'word ' * 200)
        excerpt = build_sources([chunk])[0]['excerpt']
        self.assertLessEqual(len(excerpt), 222)
        self.assertTrue(excerpt.endswith('word\u2026'))

    def test_chunks_from_same_document_are_grouped_but_keep_numbers(self):
        a, b = make_doc('Doc A'), make_doc('Doc B')
        chunks = [make_chunk(a, 0, 'one'), make_chunk(b, 0, 'two'), make_chunk(a, 1, 'three')]
        groups = group_sources(build_sources(chunks))
        self.assertEqual([g['title'] for g in groups], ['Doc A', 'Doc B'])
        self.assertEqual([p['number'] for p in groups[0]['passages']], [1, 3])
        self.assertEqual([p['number'] for p in groups[1]['passages']], [2])


class CitationDetectionTests(TestCase):
    def test_single_multiple_and_comma_citations(self):
        self.assertEqual(_cited_numbers('Go now [2]. Also see [1, 3] and [4][5].'), {1, 2, 3, 4, 5})

    def test_no_citations(self):
        self.assertEqual(_cited_numbers('Stay calm.'), set())
        self.assertEqual(_cited_numbers(None), set())

    def test_cited_flag_set_only_on_cited_passages(self):
        doc = make_doc('Doc')
        chunks = [make_chunk(doc, 0, 'first'), make_chunk(doc, 1, 'second')]
        flags = [p['cited'] for p in build_sources(chunks, 'Do this [2].')]
        self.assertEqual(flags, [False, True])


class AnswerQuestionSourcesTests(TestCase):
    def setUp(self):
        self.doc = make_doc('FEMA Guide', url='https://example.com/fema')
        make_chunk(self.doc, 0, 'Evacuate immediately when a hurricane warning is issued.')

    @patch('chat.rag.generate', return_value='Evacuate immediately [1].')
    def test_sources_returned_with_citations(self, _):
        result = answer_question('when to evacuate hurricane')
        self.assertTrue(result['has_citations'])
        group = result['sources'][0]
        self.assertEqual(group['title'], 'FEMA Guide')
        self.assertEqual(group['url'], 'https://example.com/fema')
        self.assertTrue(group['passages'][0]['cited'])

    @patch('chat.rag.generate', return_value='Evacuate immediately.')
    def test_uncited_answer_has_sources_but_no_citation_flag(self, _):
        result = answer_question('when to evacuate hurricane')
        self.assertFalse(result['has_citations'])
        self.assertEqual(len(result['sources']), 1)

    @patch('chat.rag.generate')
    def test_no_matching_chunks_means_no_sources_and_no_llm_call(self, mock_generate):
        result = answer_question('zzzz qqqq')
        self.assertEqual(result['sources'], [])
        mock_generate.assert_not_called()

    @patch('chat.rag.generate', side_effect=RuntimeError('boom'))
    def test_failed_answer_shows_no_sources(self, _):
        result = answer_question('when to evacuate hurricane')
        self.assertFalse(result['success'])
        self.assertEqual(result['sources'], [])

    @patch('chat.rag.generate', return_value='Evacuate immediately [1].')
    def test_inactive_documents_are_not_sources(self, _):
        self.doc.is_active = False
        self.doc.save()
        self.assertEqual(answer_question('when to evacuate hurricane')['sources'], [])


class ChatPageSourcesTests(TestCase):
    @patch('chat.rag.generate', return_value='Evacuate immediately [1].')
    def test_chat_page_renders_sources_with_excerpt(self, _):
        doc = make_doc('FEMA Guide', url='https://example.com/fema')
        make_chunk(doc, 0, 'Evacuate immediately when a hurricane warning is issued.')
        self.client.post('/chat/', {'question': 'when to evacuate hurricane'})
        html = self.client.get('/chat/').content.decode()
        self.assertIn('FEMA Guide', html)
        self.assertIn('https://example.com/fema', html)
        self.assertIn('Evacuate immediately when a hurricane warning is issued.', html)
        self.assertIn('[1]', html)
        self.assertIn('cited', html)

    def test_old_format_history_still_renders(self):
        session = self.client.session
        session['chat_history'] = [{
            'question': 'old question', 'answer': 'old answer', 'intent': 'factual',
            'sources': [{'id': 1, 'title': 'Old Doc', 'url': ''}],
        }]
        session.save()
        response = self.client.get('/chat/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Old Doc')


class IntentClassificationTests(TestCase):
    """Story 8: the prompt template is chosen at runtime from the question."""

    def test_intents(self):
        from .prompts import build_prompt, classify_intent
        cases = {
            'What should I do in a flood?': 'procedural',
            'How do I prepare an emergency kit?': 'procedural',
            'Why do hurricanes form?': 'explanation',
            'How do tornadoes form?': 'explanation',
            'How does storm surge work?': 'explanation',
            'Explain a hurricane watch': 'explanation',
            'Write an evacuation plan for my family': 'creative',
            'What is FEMA?': 'factual',
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(classify_intent(question), expected)

    def test_different_intents_build_different_prompts(self):
        from .prompts import build_prompt
        _, _, steps = build_prompt('How do I prepare?', [])
        _, _, why = build_prompt('Why do floods happen?', [])
        self.assertIn('step-by-step', steps)
        self.assertIn('Explain', why)
