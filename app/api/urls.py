from django.urls import path

from . import views

urlpatterns = [
    path('', views.index),
    # path('docs/', views.schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]
