from django.urls import path

from pedagogia import views

urlpatterns = [
    path('questionariomatriz/<int:pk>/', views.questionariomatriz),
    path('avaliacao_processual_curso/', views.avaliacao_processual_curso),
    path('resultado_avaliacao_cursos/', views.resultado_avaliacao_cursos),
    path('ver_respostas_insuficiente/<str:pk>/<str:campo>/', views.ver_respostas_insuficiente),
]
