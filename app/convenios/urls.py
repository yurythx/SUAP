from django.urls import path

from convenios import views

urlpatterns = [
    path('convenios/', views.convenios),
    path('conveniados/', views.conveniados),
    path('convenios_a_vencer/', views.convenios_a_vencer),
    path('convenio/<int:convenio_id>/', views.convenio),
    path('adicionar_aditivo/<int:convenio_id>/', views.adicionar_aditivo),
    path('atualizar_aditivo/<int:aditivo_id>/', views.atualizar_aditivo),
    path('excluir_aditivo/<int:aditivo_id>/', views.excluir_aditivo),
    path('adicionar_anexo/<int:convenio_id>/', views.adicionar_anexo),
    path('atualizar_anexo/<int:anexo_id>/', views.atualizar_anexo),
    path('excluir_anexo/<int:anexo_id>/', views.excluir_anexo),
    path('upload_anexo/<int:anexo_id>/', views.upload_anexo),
    path('visualizar_arquivo/<int:id_arquivo>/', views.visualizar_arquivo),
    path('estatisticas_convenios/', views.estatisticas_convenios),
    path('parceriainternacional/<int:parceriainternacional_id>/', views.parceriainternacional),
]
