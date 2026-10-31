from django.conf import settings
from django.urls import path

from erros import views

urlpatterns = [
    path('erro/<int:pk>/', views.erro),
    path('areas/', views.areas),
    path('modulo/<str:modulo_id>/', views.modulo),
    path('modulos/<str:area_id>/', views.modulos),
    path('adicionar_anexo/<int:pk>/', views.adicionar_anexo),
    path('reportar_erro_500/', views.reportar_erro_500),
    path('reportar_erro_por_chamado/<int:chamado_pk>/', views.reportar_erro_por_chamado),
    path('reportar_erro/', views.reportar_erro),
    path('alterar_situacao_erro/<int:pk>/', views.alterar_situacao_erro),
    path('alterar_url/<int:pk>/', views.alterar_url),
    path('atribuir_atendente/<int:pk>/', views.atribuir_atendente),
    path('unificar_erros/<int:pk>/', views.unificar_erros),
    path('desconsiderar_comentario/<int:pk>/', views.desconsiderar_comentario),
    path('editar_atualizacao/<int:pk>/', views.editar_atualizacao),
    path('remover_atendente/<int:pk_erro>/<int:pk_vinculo>/', views.remover_atendente),
    path('erros_informante/<int:pk>/', views.erros_informante),
]
if settings.DEBUG:
    urlpatterns += [path('exception/', views.exception), path('exception/<int:pk>/', views.exception)]
