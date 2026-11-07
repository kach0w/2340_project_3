"""Seed known test questions for accuracy testing (story 9).

Usage:
    python manage.py seed_eval                # just the test questions
    python manage.py seed_eval --sample-doc   # also ingest a matching sample doc
"""
from django.core.management.base import BaseCommand

from knowledge.ingestion import ingest_text
from knowledge.models import Document
from monitoring.models import TestQuestion

SAMPLE_DOC_TITLE = 'Disaster Preparedness Basics (eval sample)'
SAMPLE_DOC = """
Emergency supply kit
Every household should build an emergency supply kit. Store at least one gallon of water per person per day, for at least three days, for drinking and sanitation. Include at least a three-day supply of non-perishable food, a manual can opener, a flashlight, a battery-powered or hand-crank radio, extra batteries, a first aid kit, and any prescription medications.

Flash floods
If a flash flood warning is issued, move immediately to higher ground. Never walk, swim, or drive through flood waters: Turn Around, Don't Drown. Just six inches of moving water can knock you down, and one foot of moving water can sweep your vehicle away.

Tornadoes
When a tornado warning is issued, go to a safe room, basement, or storm cellar. If there is no basement, go to a small interior room on the lowest floor, away from windows, doors, and outside walls. Cover your head and neck with your arms.

Earthquakes
During an earthquake, Drop, Cover, and Hold On. Drop to your hands and knees, cover your head and neck under a sturdy table or desk, and hold on until the shaking stops. Do not run outside during shaking.

Hurricanes
A hurricane watch means hurricane conditions are possible in the area, typically within 48 hours. A hurricane warning means hurricane conditions are expected, typically within 36 hours. Follow evacuation orders from local officials.

Generators and carbon monoxide
Never use a generator, grill, or camp stove inside a home, garage, or basement. Keep generators outdoors and at least 20 feet away from windows, doors, and vents to prevent carbon monoxide poisoning.

Wildfire smoke
During wildfire smoke events, stay indoors with windows and doors closed. If you must go outside, an N95 respirator offers protection from smoke particles; cloth or surgical masks do not.
"""

# (question, expected answer, comma-separated keywords)
TEST_QUESTIONS = [
    (
        'How much water should I store in my emergency kit?',
        'At least one gallon of water per person per day, for at least three days.',
        'gallon, per person, three days',
    ),
    (
        'What should I do if a flash flood warning is issued?',
        'Move to higher ground immediately and never walk or drive through flood water (Turn Around, Don\'t Drown).',
        'higher ground, turn around',
    ),
    (
        'How much moving water can sweep away a car?',
        'One foot (12 inches) of moving water can sweep a vehicle away; six inches can knock a person down.',
        'one foot',
    ),
    (
        'Where should I shelter during a tornado if I have no basement?',
        'A small interior room on the lowest floor, away from windows, doors, and outside walls.',
        'interior room, lowest floor, windows',
    ),
    (
        'What should I do during an earthquake?',
        'Drop, Cover, and Hold On: drop to hands and knees, cover head and neck under sturdy furniture, hold on until shaking stops.',
        'drop, cover, hold on',
    ),
    (
        'What is the difference between a hurricane watch and a hurricane warning?',
        'A watch means hurricane conditions are possible (about 48 hours); a warning means they are expected (about 36 hours).',
        'possible, expected, 48, 36',
    ),
    (
        'How far from my house should I keep a generator?',
        'Outdoors, at least 20 feet away from windows, doors, and vents, to avoid carbon monoxide poisoning.',
        '20 feet, carbon monoxide',
    ),
    (
        'What kind of mask protects against wildfire smoke?',
        'An N95 respirator; cloth and surgical masks do not protect against smoke particles.',
        'n95',
    ),
    (
        'What is the capital of France?',
        'The bot should say it does not know / the information is not in its knowledge base, and not answer from outside knowledge.',
        '',
    ),
]


class Command(BaseCommand):
    help = 'Seed known test questions for the accuracy evaluation page.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sample-doc', action='store_true',
            help='Also ingest a sample disaster-preparedness document the questions are based on.',
        )

    def handle(self, *args, **options):
        if options['sample_doc']:
            if Document.objects.filter(title=SAMPLE_DOC_TITLE).exists():
                self.stdout.write('Sample doc already present.')
            else:
                ingest_text(SAMPLE_DOC_TITLE, SAMPLE_DOC)
                self.stdout.write(self.style.SUCCESS('Ingested sample doc.'))

        created = 0
        for question, expected, keywords in TEST_QUESTIONS:
            _, was_created = TestQuestion.objects.get_or_create(
                question=question,
                defaults={'expected_answer': expected, 'expected_keywords': keywords},
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(
            f'{created} test questions added ({len(TEST_QUESTIONS) - created} already existed).'
        ))
