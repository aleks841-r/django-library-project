"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# УДАЛИЛИ прямой импорт index_view отсюда

urlpatterns = [
    path('admin/', admin.site.urls),

    # ОСТАВИЛИ ТОЛЬКО ЭТУ СТРОКУ для обработки главной страницы и всех остальных путей приложения
    path('', include('library.urls')),

    # Эндпоинт генерации сырой схемы в формате YAML/JSON
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),

    # Интерактивная панель Swagger UI
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Интерфейс Redoc (необязательно, по желанию)
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

]
