from django.urls import path

from . import views

urlpatterns = [
    path('resultado_execucao/<int:pk>/', views.resultado_execucao, name='resultado_execucao'),
]
