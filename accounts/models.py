from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    """Per-user settings. Custom story 2: the ZIP code used to filter alerts."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    zip_code = models.CharField(max_length=5, blank=True)
    # What the user typed (an address or just the ZIP), shown back to them.
    location = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f'{self.user.username} ({self.location or self.zip_code or "no location"})'
