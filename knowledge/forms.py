from django import forms

from .models import Document


class FileUploadForm(forms.Form):
    title = forms.CharField(max_length=255)
    file = forms.FileField(help_text='.txt or .md')


class UrlIngestForm(forms.Form):
    title = forms.CharField(max_length=255)
    url = forms.URLField()


class TextIngestForm(forms.Form):
    title = forms.CharField(max_length=255)
    text = forms.CharField(widget=forms.Textarea(attrs={'rows': 6}))


class DocumentEditForm(forms.ModelForm):
    """Story 5: update an existing document; saving re-cleans and re-chunks it."""

    class Meta:
        model = Document
        fields = ['title', 'source_url', 'raw_text', 'is_active']
        labels = {'raw_text': 'Text', 'is_active': 'Active (used to answer questions)'}
        widgets = {'raw_text': forms.Textarea(attrs={'rows': 14})}
