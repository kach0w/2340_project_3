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


class LocationFilterTests(TestCase):
    """Custom story 2: alerts are filtered by the user's ZIP code."""

    def setUp(self):
        self.atlanta = make_doc('Atlanta flood warning')
        self.atlanta.alert_areas = '30332, 30318'
        self.atlanta.save()
        make_chunk(self.atlanta, 0, 'Flood warning: evacuate low-lying areas near the river now.')

        self.metro = make_doc('Metro Atlanta flood watch')
        self.metro.alert_areas = '303'
        self.metro.save()
        make_chunk(self.metro, 0, 'Flood watch: move valuables upstairs and monitor river levels.')

        self.miami = make_doc('Miami flood warning')
        self.miami.alert_areas = '33101'
        self.miami.save()
        make_chunk(self.miami, 0, 'Flood warning: evacuate Miami Beach zones A and B now.')

        self.general = make_doc('General flood safety')
        make_chunk(self.general, 0, 'Flood safety: never drive through flood water.')

    def titles(self, chunks):
        return {c.document.title for c in chunks}

    def test_zip_keeps_local_and_general_alerts_and_drops_distant_ones(self):
        from .rag import retrieve
        titles = self.titles(retrieve('flood warning evacuate', top_k=10, zip_code='30332'))
        self.assertEqual(titles, {'Atlanta flood warning', 'Metro Atlanta flood watch', 'General flood safety'})

    def test_zip_prefix_area_matches_any_zip_in_it(self):
        from .rag import retrieve
        titles = self.titles(retrieve('flood', top_k=10, zip_code='30309'))
        self.assertIn('Metro Atlanta flood watch', titles)
        self.assertNotIn('Atlanta flood warning', titles)  # 30309 isn't one of its ZIPs
        self.assertNotIn('Miami flood warning', titles)

    def test_other_location_gets_its_own_alerts(self):
        from .rag import retrieve
        titles = self.titles(retrieve('flood warning evacuate', top_k=10, zip_code='33101'))
        self.assertEqual(titles, {'Miami flood warning', 'General flood safety'})

    def test_no_location_means_no_filtering(self):
        from .rag import retrieve
        self.assertEqual(len(self.titles(retrieve('flood', top_k=10))), 4)

    def test_prompt_mentions_location_only_when_set(self):
        _, _, with_zip = build_prompt('what about floods', [], zip_code='30332')
        _, _, without = build_prompt('what about floods', [])
        self.assertIn('ZIP code 30332', with_zip)
        self.assertNotIn('ZIP code', without)

    @patch('chat.rag.generate', return_value='Evacuate now [1].')
    def test_answer_sources_show_local_alert_areas(self, _):
        result = answer_question('miami flood warning evacuate', zip_code='30332')
        titles = [g['title'] for g in result['sources']]
        self.assertNotIn('Miami flood warning', titles)
        atl = next(g for g in result['sources'] if g['title'] == 'Atlanta flood warning')
        self.assertEqual(atl['areas'], ['30332', '30318'])

    def test_set_and_clear_location_for_guest(self):
        self.client.post('/chat/location/', {'location': '30332-1234'})
        self.assertEqual(self.client.session['zip_code'], '30332')
        self.assertContains(self.client.get('/chat/'), 'ZIP 30332')
        self.client.post('/chat/location/', {'clear': '1'})
        self.assertNotIn('zip_code', self.client.session)
        self.assertContains(self.client.get('/chat/'), 'No location set')

    def test_address_is_accepted_and_shown_back(self):
        # Wireflow #2: the user types an address; the page shows it back.
        address = '266 Ferst Dr NW, Atlanta, GA 30332'
        self.client.post('/chat/location/', {'location': address})
        self.assertEqual(self.client.session['zip_code'], '30332')
        html = self.client.get('/chat/').content.decode()
        self.assertIn('Ask now for information about emergencies at:', html)
        self.assertIn(address, html)
        self.assertIn('Change address', html)

    def test_change_address_shows_the_form_prefilled(self):
        self.client.post('/chat/location/', {'location': '30332'})
        html = self.client.get('/chat/?change=location').content.decode()
        self.assertIn('id="location-form"', html)
        self.assertIn('value="30332"', html)

    def test_zip_from_location(self):
        from knowledge.location import zip_from_location
        self.assertEqual(zip_from_location('30332'), '30332')
        self.assertEqual(zip_from_location('12345 Main St, Miami, FL 33101-2000'), '33101')
        self.assertIsNone(zip_from_location('Atlanta, GA'))
        self.assertIsNone(zip_from_location('123456'))

    def test_location_without_zip_is_rejected(self):
        response = self.client.post('/chat/location/', {'location': 'Atlanta, GA'}, follow=True)
        self.assertNotIn('zip_code', self.client.session)
        self.assertContains(response, 'Enter a 5-digit ZIP code')

    def test_logged_in_users_zip_is_saved_on_profile_and_persists(self):
        from django.contrib.auth.models import User
        from accounts.models import Profile
        user = User.objects.create_user('aiden', password='pw12345!')
        self.client.force_login(user)
        self.client.post('/chat/location/', {'location': 'North Ave, Atlanta, GA 30332'})
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.zip_code, '30332')
        self.assertEqual(profile.location, 'North Ave, Atlanta, GA 30332')
        # New session (e.g. another device): location is still applied.
        self.client.logout()
        self.client.force_login(user)
        self.assertContains(self.client.get('/chat/'), 'ZIP 30332')

    @patch('chat.rag.generate', return_value='Evacuate now [1].')
    def test_chat_uses_saved_zip(self, _):
        self.client.post('/chat/location/', {'location': '30332'})
        self.client.post('/chat/', {'question': 'miami flood warning evacuate'})
        html = self.client.get('/chat/').content.decode()
        self.assertNotIn('Miami flood warning', html)
        self.assertIn('Local alert: 30332, 30318', html)


class SemanticRetrievalTests(TestCase):
    def chunk(self, title, content, vector, areas='', active=True):
        doc = make_doc(title, is_active=active)
        doc.alert_areas = areas
        doc.save()
        return Chunk.objects.create(document=doc, chunk_index=0, content=content, embedding=vector)

    @patch('chat.rag.embed_text', return_value=[1, 0])
    def test_semantic_order_top_k_and_no_threshold(self, embed):
        from .rag import retrieve
        weak = self.chunk('Weak', 'flood flood', [0, 1])
        best = self.chunk('Best', 'Rising water requires immediate relocation.', [1, 0])
        opposite = self.chunk('Opposite', 'Other guidance', [-1, 0])
        self.assertEqual(retrieve('flood', top_k=1), [best])
        self.assertEqual(retrieve('flood', top_k=10), [best, weak, opposite])
        embed.assert_called_with('flood', 'RETRIEVAL_QUERY')

    @patch('chat.rag.embed_text', return_value=[1, 0])
    def test_missing_and_incompatible_embeddings_do_not_disable_semantics(self, _):
        from .rag import retrieve
        best = self.chunk('Semantic', 'Seek higher terrain.', [1, 0])
        self.chunk('Missing', 'flood', None)
        self.chunk('Wrong dimensions', 'flood', [1, 0, 0])
        self.assertEqual(retrieve('flood'), [best])

    @patch('chat.rag.embed_text', return_value=[1, 0])
    def test_zip_and_active_filtering_before_semantic_ranking(self, _):
        from .rag import retrieve
        local = self.chunk('Local', 'Local guidance', [1, 0], '30332')
        metro = self.chunk('Metro', 'Metro guidance', [0.9, 0.1], '303')
        general = self.chunk('General', 'General guidance', [0.8, 0.2])
        distant = self.chunk('Distant', 'Distant guidance', [1, 0], '33101')
        self.chunk('Inactive', 'Inactive guidance', [1, 0], active=False)
        self.assertEqual(retrieve('evacuate', top_k=10, zip_code='30332'), [local, metro, general])
        self.assertEqual(set(retrieve('evacuate', top_k=10, zip_code='30309')), {metro, general})
        self.assertEqual(set(retrieve('evacuate', top_k=10)), {local, metro, general, distant})

    @patch('chat.rag.embed_text')
    def test_no_embeddings_or_no_eligible_chunks_skips_api(self, embed):
        from .rag import retrieve
        self.assertEqual(retrieve('flood'), [])
        chunk = self.chunk('Legacy', 'flood warning', None)
        self.assertEqual(retrieve('flood'), [chunk])
        embed.assert_not_called()

    @patch('chat.rag.embed_text')
    def test_query_failure_missing_key_and_incompatible_vectors_use_keywords(self, embed):
        from .rag import retrieve
        chunk = self.chunk('Guide', 'flood warning', [1, 0])
        embed.side_effect = RuntimeError('API unavailable')
        with self.assertLogs('chat.rag', level='ERROR'):
            self.assertEqual(retrieve('flood'), [chunk])
        embed.side_effect = None
        for vector in (None, [1, 0, 0]):
            embed.return_value = vector
            self.assertEqual(retrieve('flood'), [chunk])
            self.assertEqual(retrieve('unrelated'), [])
