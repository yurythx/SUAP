from django.urls import path

from . import views

urlpatterns = [
    path('funcionarios/', views.funcionarios, name='terminal_funcionarios'),
    path('digitais/', views.digitais, name='terminal_digitais'),
    path('frequencias/', views.frequencias, name='terminal_frequencias'),
    path('frequencias/dia/<str:username>/', views.frequencias_dia, name='terminal_frequencias_dia'),
    path('ocorrencias/<str:username>/', views.ocorrencias, name='terminal_ocorrencias'),
    path('solicitar_autocadastro/<str:username>/', views.solicitar_autocadastro, name='terminal_solicitar_autocadastro'),
    path('cancelar_autocadastro/<str:username>/<str:code>/', views.cancelar_autocadastro, name='terminal_cancelar_autocadastro'),
    path('confirmar_autocadastro/<str:username>/', views.confirmar_autocadastro, name='terminal_confirmar_autocadastro'),
    path('whoami/', views.whoami, name='terminal_whoami'),
]
