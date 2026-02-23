from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('verification_system.urls')),  # корневой URL ведет в дашборд
]
