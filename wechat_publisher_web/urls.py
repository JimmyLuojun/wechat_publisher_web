"""
URL configuration for wechat_publisher_web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.urls import path, include # Add include
from django.conf import settings # Add this
from django.conf.urls.static import static # Add this

urlpatterns = [
    path('admin/', admin.site.urls),
    path('publisher/', include('publisher.urls')), # Example: Include publisher app URLs under /publisher/
    # Add other paths as needed
]

# Add this block to serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Optionally add static files serving if needed, though runserver usually handles this
    # urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
