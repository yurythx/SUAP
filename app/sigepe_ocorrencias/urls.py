from django.urls import path

from sigepe_ocorrencias import views

urlpatterns = [
    path('visualizar_pacote/<int:pacote_id>/', views.visualizar_pacote, name='visualizar_pacote'),
    path('download_arquivo_pacote_envio/<int:pacote_id>/', views.download_arquivo_pacote_envio, name='download_arquivo_pacote_envio'),
    path('upload_arquivo_pacote_envio/<int:pacote_id>/', views.upload_arquivo_pacote_envio, name='upload_arquivo_pacote_envio'),
    path('gerar_arquivo_envio/<int:pacote_id>/', views.gerar_arquivo_envio, name='gerar_arquivo_envio'),
    path('zerar_pacote/<int:pacote_id>/', views.zerar_pacote, name='zerar_pacote'),
    path('excluir_pacote/<int:pacote_id>/', views.excluir_pacote, name='excluir_pacote'),
]
