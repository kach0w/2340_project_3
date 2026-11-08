from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import ingestion
from .forms import DocumentEditForm, FileUploadForm, TextIngestForm, UrlIngestForm
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
                ingestion.ingest_file(
                    form.cleaned_data['title'], form.cleaned_data['file'],
                    alert_areas=form.cleaned_data['alert_areas'],
                )
        elif method == 'url':
            form = UrlIngestForm(request.POST)
            if form.is_valid():
                ingestion.ingest_url(
                    form.cleaned_data['title'], form.cleaned_data['url'],
                    alert_areas=form.cleaned_data['alert_areas'],
                )
        elif method == 'text':
            form = TextIngestForm(request.POST)
            if form.is_valid():
                ingestion.ingest_text(
                    form.cleaned_data['title'], form.cleaned_data['text'],
                    alert_areas=form.cleaned_data['alert_areas'],
                )
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
def edit_document(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    form = DocumentEditForm(request.POST or None, instance=document)
    if request.method == 'POST' and form.is_valid():
        ingestion.process_document(form.save())
        messages.success(request, 'Document updated and re-processed.')
        return redirect('knowledge.document_detail', document_id=document.id)
    return render(request, 'document_edit.html', {'document': document, 'form': form})


@staff_member_required(login_url='loginaccount')
@require_POST
def toggle_document(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    document.is_active = not document.is_active
    document.save(update_fields=['is_active', 'updated_at'])
    state = 'activated' if document.is_active else 'deactivated (no longer used for answers)'
    messages.success(request, f'"{document.title}" {state}.')
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
