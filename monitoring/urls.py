from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='monitoring.dashboard'),
    path('logs/', views.logs, name='monitoring.logs'),
    path('evaluation/', views.evaluation, name='monitoring.evaluation'),
    path('evaluation/run/', views.run_eval, name='monitoring.run_eval'),
]
