from django import forms


class FileUploadForm(forms.Form):
    title = forms.CharField(max_length=255)
    file = forms.FileField(help_text='.txt or .md')


class UrlIngestForm(forms.Form):
    title = forms.CharField(max_length=255)
    url = forms.URLField()


class TextIngestForm(forms.Form):
    title = forms.CharField(max_length=255)
    text = forms.CharField(widget=forms.Textarea(attrs={'rows': 6}))
