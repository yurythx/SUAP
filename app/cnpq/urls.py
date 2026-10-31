from django.urls import path

from cnpq import views

urlpatterns = [
    # relatorios graficos
    path('', views.index),
    # exibição de dados do curriculo
    path('curriculo/<int:servidor_pk>/', views.curriculo),
    path('relatorio_importacao/', views.relatorio_importacao),
    path('relatorio_importacoes_lattes/', views.relatorio_importacoes_lattes),
    path('importar_lista_completa/', views.importar_lista_completa),
    path('atualiza_grupos_pesquisa/<int:curriculo_id>/', views.atualiza_grupos_pesquisa),
    path('cadastrar_periodico/', views.cadastrar_periodico),
    path('editar_periodico/<int:periodico_id>/', views.editar_periodico),
    path('producao_por_servidor/', views.producao_por_servidor),
    path('producao_por_campus/', views.producao_por_campus),
    path('busca_por_titulacao/', views.busca_por_titulacao),
    path('atualizar_curriculo/<int:matricula>/<int:servidor_id>/', views.atualizar_curriculo),
    path('download_xml_curriculos/', views.download_xml_curriculos),
]
