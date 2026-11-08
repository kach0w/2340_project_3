from django import forms

from .location import parse_areas
from .models import Document

AREA_HELP = Document._meta.get_field('alert_areas').help_text


class AlertAreasMixin:
    """Custom story 2: validate + normalize the alert areas field."""

    def clean_alert_areas(self):
        try:
            return ', '.join(parse_areas(self.cleaned_data.get('alert_areas', '')))
        except ValueError as e:
            raise forms.ValidationError(str(e))


def alert_areas_field():
    return forms.CharField(label='Alert areas (optional)', max_length=500, required=False, help_text=AREA_HELP)


class FileUploadForm(AlertAreasMixin, forms.Form):
    title = forms.CharField(max_length=255)
    file = forms.FileField(help_text='.txt or .md')
    alert_areas = alert_areas_field()


class UrlIngestForm(AlertAreasMixin, forms.Form):
    title = forms.CharField(max_length=255)
    url = forms.URLField()
    alert_areas = alert_areas_field()


class TextIngestForm(AlertAreasMixin, forms.Form):
    title = forms.CharField(max_length=255)
    text = forms.CharField(widget=forms.Textarea(attrs={'rows': 6}))
    alert_areas = alert_areas_field()


class DocumentEditForm(AlertAreasMixin, forms.ModelForm):
    """Story 5: update an existing document; saving re-cleans and re-chunks it."""

    class Meta:
        model = Document
        fields = ['title', 'source_url', 'alert_areas', 'raw_text', 'is_active']
        labels = {'raw_text': 'Text', 'is_active': 'Active (used to answer questions)'}
        widgets = {'raw_text': forms.Textarea(attrs={'rows': 14})}
