import io
import time
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from knowledge.models import Document

from . import evaluation
from .models import EvaluationResult, EvaluationRun, TestQuestion


def answer(text='x', latency=12):
    return {'answer': text, 'latency_ms': latency}


class PacerTests(TestCase):
    def test_first_call_does_not_wait(self):
        start = time.monotonic()
        evaluation.Pacer(5).wait()
        self.assertLess(time.monotonic() - start, 0.1)

    def test_spaces_calls_apart(self):
        pacer = evaluation.Pacer(0.2)
        pacer.wait()
        start = time.monotonic()
        pacer.wait()
        self.assertGreaterEqual(time.monotonic() - start, 0.15)


class ParseScoresTests(TestCase):
    def test_parses_json_array(self):
        self.assertEqual(evaluation.parse_scores('[1.0, 0.5]', 2), [1.0, 0.5])

    def test_parses_array_inside_code_fence(self):
        self.assertEqual(evaluation.parse_scores('```json\n[0.9, 0]\n```', 2), [0.9, 0.0])

    def test_clamps_out_of_range(self):
        self.assertEqual(evaluation.parse_scores('[1.5, -1]', 2), [1.0, 0.0])

    def test_wrong_length_or_garbage_returns_none(self):
        self.assertIsNone(evaluation.parse_scores('[1.0]', 2))
        self.assertIsNone(evaluation.parse_scores('no idea', 1))
        self.assertIsNone(evaluation.parse_scores('["a"]', 1))


class ScoreAllTests(TestCase):
    def setUp(self):
        self.judged = TestQuestion.objects.create(
            question='How much water?', expected_answer='One gallon per person per day.',
            expected_keywords='gallon, day',
        )
        self.keywords_only = TestQuestion.objects.create(question='Earthquake?', expected_keywords='drop, cover')

    def test_one_batched_judge_call_for_questions_with_expected_answer(self):
        with patch.object(evaluation, 'generate', return_value='[0.9]') as gen:
            scores = evaluation.score_all([(self.judged, 'a'), (self.keywords_only, 'drop and cover')])
        self.assertEqual(scores, [0.9, 1.0])
        gen.assert_called_once()

    def test_falls_back_to_keywords_when_judge_fails(self):
        with patch.object(evaluation, 'generate', side_effect=RuntimeError('429')):
            scores = evaluation.score_all([(self.judged, 'a gallon')])
        self.assertEqual(scores, [0.5])

    def test_no_judge_call_when_nothing_to_judge(self):
        with patch.object(evaluation, 'generate') as gen:
            evaluation.score_all([(self.keywords_only, 'drop')])
        gen.assert_not_called()


@override_settings(EVAL_SECONDS_BETWEEN_CALLS=0, GOOGLE_API_KEY='test-key')
class RunEvaluationTests(TestCase):
    def setUp(self):
        TestQuestion.objects.create(question='q1', expected_answer='a1')
        TestQuestion.objects.create(question='q2', expected_answer='a2')

    @patch.object(evaluation, 'generate', return_value='[0.8, 0.2]')
    @patch.object(evaluation, 'answer_question', return_value=answer())
    def test_answers_all_then_grades_once(self, aq, gen):
        seen = []
        run = evaluation.run_evaluation(on_progress=seen.append)
        self.assertEqual(aq.call_count, 2)
        gen.assert_called_once()
        self.assertEqual(run.status, EvaluationRun.STATUS_DONE)
        self.assertEqual((run.passed, run.total), (1, 2))
        self.assertEqual(run.results.count(), 2)
        self.assertIn('Answering 1/2', seen)
        self.assertIn('Grading answers', seen)

    @patch.object(evaluation, 'answer_question', return_value=answer())
    def test_uses_fail_fast_client(self, aq):
        with patch.object(evaluation, 'generate', return_value='[1, 1]'):
            evaluation.run_evaluation()
        client = aq.call_args.kwargs['client']
        self.assertIs(client, evaluation.eval_client())

    @patch.object(evaluation, 'answer_question', side_effect=RuntimeError('boom'))
    def test_marks_run_failed_on_crash(self, _):
        run = evaluation.run_evaluation()
        self.assertEqual(run.status, EvaluationRun.STATUS_FAILED)
        self.assertIn('boom', run.error_message)
        self.assertIsNotNone(run.finished_at)


class CurrentRunTests(TestCase):
    def test_stale_running_run_is_marked_failed(self):
        run = EvaluationRun.objects.create()
        EvaluationRun.objects.filter(pk=run.pk).update(updated_at=timezone.now() - timedelta(minutes=10))
        self.assertIsNone(evaluation.current_run())
        run.refresh_from_db()
        self.assertEqual(run.status, EvaluationRun.STATUS_FAILED)

    def test_recent_running_run_is_returned(self):
        run = EvaluationRun.objects.create()
        self.assertEqual(evaluation.current_run(), run)


class EvaluationViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True)
        self.client.force_login(self.staff)

    def test_run_button_starts_background_thread(self):
        with patch.object(evaluation.threading, 'Thread') as thread:
            resp = self.client.post(reverse('monitoring.run_eval'))
        self.assertRedirects(resp, reverse('monitoring.evaluation'))
        thread.return_value.start.assert_called_once()
        self.assertEqual(EvaluationRun.objects.filter(status=EvaluationRun.STATUS_RUNNING).count(), 1)

    def test_second_click_does_not_start_another_run(self):
        EvaluationRun.objects.create()
        with patch.object(evaluation.threading, 'Thread') as thread:
            self.client.post(reverse('monitoring.run_eval'))
        thread.assert_not_called()
        self.assertEqual(EvaluationRun.objects.count(), 1)

    def test_page_auto_refreshes_while_running(self):
        EvaluationRun.objects.create(progress='Answering 3/9')
        resp = self.client.get(reverse('monitoring.evaluation'))
        self.assertContains(resp, 'http-equiv="refresh"')
        self.assertContains(resp, 'Answering 3/9')

    def test_page_shows_latest_finished_run(self):
        tq = TestQuestion.objects.create(question='Water?')
        run = EvaluationRun.objects.create(status=EvaluationRun.STATUS_DONE, total=1, passed=1)
        EvaluationResult.objects.create(run=run, test_question=tq, actual_answer='a gallon', score=1.0, passed=True)
        resp = self.client.get(reverse('monitoring.evaluation'))
        self.assertNotContains(resp, 'http-equiv="refresh"')
        self.assertContains(resp, '1/1')
        self.assertContains(resp, 'a gallon')

    def test_non_staff_redirected_to_login(self):
        self.client.force_login(User.objects.create_user('regular', password='pw'))
        resp = self.client.get(reverse('monitoring.evaluation'))
        self.assertEqual(resp.status_code, 302)


class CommandTests(TestCase):
    def test_seed_eval_is_idempotent(self):
        call_command('seed_eval', '--sample-doc', stdout=io.StringIO())
        call_command('seed_eval', '--sample-doc', stdout=io.StringIO())
        self.assertEqual(TestQuestion.objects.count(), 9)
        self.assertEqual(Document.objects.count(), 1)
        self.assertTrue(Document.objects.first().chunks.exists())

    @override_settings(EVAL_SECONDS_BETWEEN_CALLS=0, GOOGLE_API_KEY='test-key')
    @patch.object(evaluation, 'generate', return_value='[1.0]')
    @patch.object(evaluation, 'answer_question', return_value=answer('ok'))
    def test_run_eval_prints_summary(self, _aq, _gen):
        TestQuestion.objects.create(question='q1', expected_answer='a1')
        out = io.StringIO()
        call_command('run_eval', stdout=out)
        self.assertIn('1/1 passed', out.getvalue())


class PerformanceDashboardTests(TestCase):
    """Story 10: latency/failures against a responsiveness target."""

    def setUp(self):
        self.client.force_login(User.objects.create_user('staff2', password='pw', is_staff=True))

    def log(self, ms, ok=True):
        from .models import QueryLog
        return QueryLog.objects.create(question='q', latency_ms=ms, success=ok)

    def test_percentile(self):
        from .views import percentile
        self.assertIsNone(percentile([], 95))
        self.assertEqual(percentile(list(range(1, 101)), 95), 95)
        self.assertEqual(percentile([7], 95), 7)

    @override_settings(LATENCY_TARGET_MS=1000, LATENCY_GOAL_PERCENT=95)
    def test_stats_count_failures_against_target(self):
        from .models import QueryLog
        from .views import performance_stats
        for ms in (100, 200, 300):
            self.log(ms)
        self.log(5000)            # slow
        self.log(50, ok=False)    # failed
        s = performance_stats(QueryLog.objects.all())
        self.assertEqual(s['within_target'], 3)
        self.assertEqual(s['within_target_percent'], 60)
        self.assertFalse(s['meets_goal'])
        self.assertEqual(s['failures'], 1)

    @override_settings(LATENCY_TARGET_MS=1000)
    def test_dashboard_shows_target_and_slow_queries(self):
        self.log(200)
        self.log(4321)
        html = self.client.get(reverse('monitoring.dashboard')).content.decode()
        self.assertIn('Responsiveness target', html)
        self.assertIn('1000 ms', html)
        self.assertIn('4321 ms', html)
        self.assertIn('Below target', html)

    def test_dashboard_with_no_queries(self):
        self.assertContains(self.client.get(reverse('monitoring.dashboard')), 'No queries yet')

    @override_settings(LATENCY_TARGET_MS=1000)
    def test_logs_flag_slow_queries(self):
        self.log(4321)
        html = self.client.get(reverse('monitoring.logs')).content.decode()
        self.assertIn('text-danger', html)
        self.assertIn('1 queries total', html)
