from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import ingestion
from .forms import FileUploadForm, TextIngestForm, UrlIngestForm
from .models import Document


@staff_member_required(login_url='loginaccount')
def documents(request):
    return render(request, 'documents.html', {
        'documents': Document.objects.all(),
        'file_form': FileUploadForm(),
        'url_form': UrlIngestForm(),
        'text_form': TextIngestForm(),
    })


@staff_member_required(login_url='loginaccount')
def document_detail(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    return render(request, 'document_detail.html', {'document': document})


@staff_member_required(login_url='loginaccount')
@require_POST
def ingest(request, method):
    try:
        if method == 'file':
            form = FileUploadForm(request.POST, request.FILES)
            if form.is_valid():
                ingestion.ingest_file(form.cleaned_data['title'], form.cleaned_data['file'])
        elif method == 'url':
            form = UrlIngestForm(request.POST)
            if form.is_valid():
                ingestion.ingest_url(form.cleaned_data['title'], form.cleaned_data['url'])
        elif method == 'text':
            form = TextIngestForm(request.POST)
            if form.is_valid():
                ingestion.ingest_text(form.cleaned_data['title'], form.cleaned_data['text'])
        else:
            messages.error(request, 'Unknown ingestion method.')
            return redirect('knowledge.documents')

        if form.is_valid():
            messages.success(request, 'Document ingested.')
        else:
            messages.error(request, f'Invalid input: {form.errors.as_text()}')
    except Exception as e:
        messages.error(request, f'Ingestion failed: {e}')
    return redirect('knowledge.documents')


@staff_member_required(login_url='loginaccount')
@require_POST
def delete_document(request, document_id):
    get_object_or_404(Document, pk=document_id).delete()
    messages.success(request, 'Document deleted.')
    return redirect('knowledge.documents')


@staff_member_required(login_url='loginaccount')
@require_POST
def clear_all(request):
    ingestion.clear_knowledge_base()
    messages.success(request, 'Knowledge base cleared.')
    return redirect('knowledge.documents')


@staff_member_required(login_url='loginaccount')
@require_POST
def reload_all(request):
    ingestion.reload_knowledge_base()
    messages.success(request, 'Knowledge base reloaded.')
    return redirect('knowledge.documents')
