from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from nzassa_app import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('nzassa_app.urls')),
    path('ping/', views.ping),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

