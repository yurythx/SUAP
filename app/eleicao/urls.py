from django.urls import path

from eleicao import views

urlpatterns = [
    path('votacao/<int:eleicao_id>/', views.votacao),
    path('votar/<int:candidato_id>/', views.votar),
    path('votar_branco_nulo/<int:eleicao_id>/<str:tipo_voto>/', views.votar_branco_nulo),
    path('voto_qrcode/<int:voto_id>/', views.voto_qrcode),
    path('validar_candidato/<int:candidato_id>/', views.validar_candidato),
    path('validar_chapa/<int:chapa_id>/', views.validar_chapa),
    path('minhas_eleicoes/', views.minhas_eleicoes),
    path('inscricao/<int:eleicao_id>/', views.inscricao),
    path('editar_inscricao/<int:candidato_id>/', views.editar_inscricao),
    path('campanha/', views.campanha),
    path('validar_votacao/<int:eleicao_id>/', views.validar_votacao),
    path('invalidar_voto/<int:voto_id>/', views.invalidar_voto),
    path('resultado/<int:eleicao_id>/', views.resultado),
    path('resultado_pdf/<int:eleicao_id>/', views.resultado_pdf),
    path('ver_publico/<int:eleicao_id>/', views.ver_publico),
    path('atualizar_publico/<int:eleicao_id>/', views.atualizar_publico),
    path('exportar_resultado/<int:edital_id>/', views.exportar_resultado),
    path('dashboard_edital/<int:edital_id>/', views.dashboard_edital),
]
