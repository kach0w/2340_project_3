"""Run the accuracy evaluation from the terminal with live progress (story 9).

Usage: python manage.py run_eval
"""
from django.core.management.base import BaseCommand

from monitoring.evaluation import current_run, run_evaluation


class Command(BaseCommand):
    help = 'Run all test questions through the chatbot and score them.'

    def handle(self, *args, **options):
        if current_run():
            self.stderr.write('An evaluation is already running (started from the website).')
            return

        run = run_evaluation(on_progress=lambda msg: self.stdout.write(msg))

        self.stdout.write('')
        for r in run.results.select_related('test_question').order_by('id'):
            status = self.style.SUCCESS('PASS') if r.passed else self.style.ERROR('FAIL')
            self.stdout.write(f'{status} {r.score:.2f}  {r.latency_ms / 1000:5.1f}s  {r.test_question.question[:60]}')
        if run.error_message:
            self.stdout.write(self.style.ERROR(run.error_message))
        self.stdout.write(self.style.SUCCESS(f'\n{run.passed}/{run.total} passed'))
