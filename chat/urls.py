from django.urls import path

from . import views

urlpatterns = [
    path('', views.chat, name='chat'),
    path('clear/', views.clear_chat, name='chat.clear'),
    path('location/', views.set_location, name='chat.location'),
]
