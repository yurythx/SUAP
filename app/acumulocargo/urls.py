from django.urls import path

from acumulocargo import views

urlpatterns = [path('ver_declaracao/<int:pk>/', views.ver_declaracao), path('imprimir_declaracoes/<int:pk>/', views.imprimir_declaracoes)]
