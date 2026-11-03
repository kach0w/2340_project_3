from django.contrib.auth.models import User
from django.db import models

from knowledge.models import Document


class QueryLog(models.Model):
    """One chatbot request: usage log + performance metrics (stories 10 & 12)."""

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    question = models.TextField()
    answer = models.TextField(blank=True)
    intent = models.CharField(max_length=30, blank=True)
    sources = models.ManyToManyField(Document, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.created_at:%Y-%m-%d %H:%M}] {self.question[:50]}'


class TestQuestion(models.Model):
    """Known question with expected answer, for accuracy testing (story 9)."""

    question = models.TextField()
    expected_answer = models.TextField(blank=True)
    expected_keywords = models.CharField(
        max_length=500, blank=True, help_text='Comma-separated keywords that should appear in the answer',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def keyword_list(self):
        return [k.strip().lower() for k in self.expected_keywords.split(',') if k.strip()]

    def __str__(self):
        return self.question[:80]


class EvaluationResult(models.Model):
    test_question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE, related_name='results')
    actual_answer = models.TextField()
    score = models.FloatField(help_text='0.0 - 1.0')
    passed = models.BooleanField(default=False)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
