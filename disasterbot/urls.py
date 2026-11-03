from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from chat import views as chatViews

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', chatViews.home, name='home'),
    path('about/', chatViews.about, name='about'),
    path('chat/', include('chat.urls')),
    path('knowledge/', include('knowledge.urls')),
    path('monitoring/', include('monitoring.urls')),
    path('accounts/', include('accounts.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
