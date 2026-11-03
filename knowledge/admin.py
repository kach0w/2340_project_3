from django.contrib import admin

from .models import Chunk, Document


class ChunkInline(admin.TabularInline):
    model = Chunk
    extra = 0


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'source_type', 'is_active', 'created_at')
    list_filter = ('source_type', 'is_active')
    inlines = [ChunkInline]


admin.site.register(Chunk)
