from django.urls import path

from . import views

urlpatterns = [
    path('', views.documents, name='knowledge.documents'),
    path('<int:document_id>/', views.document_detail, name='knowledge.document_detail'),
    path('<int:document_id>/delete/', views.delete_document, name='knowledge.delete'),
    path('ingest/<str:method>/', views.ingest, name='knowledge.ingest'),
    path('clear/', views.clear_all, name='knowledge.clear'),
    path('reload/', views.reload_all, name='knowledge.reload'),
]
