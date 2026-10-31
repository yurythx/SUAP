from django.urls import path

from cpa import views

urlpatterns = [
    path('adicionar_pergunta/<int:questionario_id>/<int:categoria_id>/', views.adicionar_pergunta),
    path('editar_pergunta/<int:pk>/', views.editar_pergunta),
    path('identificacao/<int:tipo>/', views.identificacao),
    path('questionario/<int:pk>/', views.questionario),
    path('resultado/', views.resultado),
    path('resultado_agrupados/', views.resultado_agrupados),
    path('resultado_por_curso/', views.resultado_por_curso),
    path('responder_questionario/<int:pk>/', views.responder_questionario),
    path('respostas_subjetivas/<int:pergunta_id>/', views.respostas_subjetivas),
    path('get_cursos/', views.get_cursos),
    path('clonar_questionario/<int:questionario_id>/', views.clonar_questionario),
]
