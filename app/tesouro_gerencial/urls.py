from django.urls import path

from tesouro_gerencial import views

urlpatterns = [
    path('variaveis/', views.variaveis),
    path('importacao/', views.importacao),
    path('campi/', views.campi),
]
