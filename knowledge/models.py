from django.db import models


class Document(models.Model):
    """A source in the curated dataset (story 5)."""

    SOURCE_UPLOAD = 'upload'
    SOURCE_URL = 'url'
    SOURCE_TEXT = 'text'
    SOURCE_API = 'api'
    SOURCE_CHOICES = [
        (SOURCE_UPLOAD, 'File upload'),
        (SOURCE_URL, 'Web scrape'),
        (SOURCE_TEXT, 'Direct text'),
        (SOURCE_API, 'API'),
    ]

    title = models.CharField(max_length=255)
    source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    source_url = models.URLField(blank=True)
    file = models.FileField(upload_to='documents/', blank=True)
    raw_text = models.TextField(blank=True)
    cleaned_text = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Chunk(models.Model):
    """A retrievable piece of a Document."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    # TODO: store a real embedding vector (or move to a vector DB)
    embedding = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['document', 'chunk_index']

    def __str__(self):
        return f'{self.document.title} #{self.chunk_index}'
