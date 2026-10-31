from django.urls import path

from arquivo import views

urlpatterns = [
    path('arquivos_pendentes/', views.arquivos_pendentes, name='arquivos_pendentes'),
    # (r'^arquivos_pendentes_identificacao/', views.arquivos_pendentes_identificacao),
    # (r'^arquivos_pendentes_validacao/', views.arquivos_pendentes_validacao),
    path('arquivos_rejeitados/', views.arquivos_rejeitados, name='arquivos_rejeitados'),
    path('arquivos_rejeitados_servidor/<int:servidor_matricula>/', views.arquivos_rejeitados_servidor, name='arquivos_rejeitados_servidor'),
    path('arquivos_pendentes_servidor/<str:servidor_matricula>/', views.arquivos_pendentes_servidor, name='arquivos_pendentes_servidor'),
    path(
        'arquivos_pendentes_servidor/<str:servidor_matricula>/<str:arquivo_id>/identificar/',
        views.arquivos_pendentes_servidor_identificar,
        name='arquivos_pendentes_servidor_identificar',
    ),
    path(
        'arquivos_pendentes_servidor/<str:servidor_matricula>/<str:arquivo_id>/validar/',
        views.arquivos_pendentes_servidor_validar,
        name='arquivos_pendentes_servidor_validar',
    ),
    path(
        'arquivos_pendentes_servidor/<str:servidor_matricula>/<str:arquivo_id>/excluir/',
        views.arquivos_pendentes_servidor_excluir,
        name='arquivos_pendentes_servidor_excluir',
    ),
    path('arquivos_servidor/<int:servidor_matricula>/', views.arquivos_servidor, name='arquivos_servidor'),
    path('visualizar_arquivo_pdf/<str:arquivo_id>/', views.visualizar_arquivo_pdf),
    path('arquivos_upload/', views.selecionar_servidor, name='selecionar_servidor'),
    path('arquivos_upload/<int:servidor_matricula>/', views.arquivos_upload, name='arquivos_upload'),
    path('arquivos_upload/upload/', views.upload_handler, name='upload_handler'),
    path('tipos_arquivos/', views.tipos_arquivos, name='tipos_arquivos'),
    path('protocolar_arquivo/<str:arquivo_id>/', views.protocolar_arquivo),
]
