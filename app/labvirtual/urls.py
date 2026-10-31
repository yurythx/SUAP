from django.urls import path

from .views import (
    adicionar_membro_view,
    agendamento_labvirtual_detail_view,
    agendamento_shutdown_view,
    agendamento_sync_view,
    cancelar_solicitacao_agendamento_view,
    deferir_solicitacao_agendamento_view,
    desktop_pool_detail_view,
    indeferir_solicitacao_agendamento_view,
    procurar_usuario_view,
    remover_membro_view,
    # Solicitacao e agendamento
    solicitacao_agendamento_detail_view,
    solicitar_agendamento_view,
    sync_desktop_pools_view,
)

app_name = 'labvirtual'

urlpatterns = [
    # Desktop Pools
    path('labvirtual/sync_desktop_pools/', view=sync_desktop_pools_view, name='sync_desktop_pools'),
    path('labvirtual/<int:pk>/', view=desktop_pool_detail_view, name='desktop_pool_detail'),
    # Solicitação
    path('solicitar_agendamento/<int:pk>', view=solicitar_agendamento_view, name='solicitar_agendamento'),
    path('solicitacao_agendamento/<int:pk>', view=solicitacao_agendamento_detail_view, name='solicitacao_agendamento'),
    path('solicitacao_agendamento/deferir/<int:pk>', view=deferir_solicitacao_agendamento_view, name='deferir_solicitacao'),
    path('solicitacao_agendamento/indeferir/<int:pk>', view=indeferir_solicitacao_agendamento_view, name='indeferir_solicitacao'),
    path('solicitacao_agendamento/cancelar/<int:pk>', view=cancelar_solicitacao_agendamento_view, name='cancelar_solicitacao'),
    # Agendamento
    path('agendamento/laboratoriovirtual/<int:pk>/', view=agendamento_labvirtual_detail_view, name='agendamento_labvirtual'),
    path('agendamento/sync/<int:pk>/', view=agendamento_sync_view, name='liberar_agendamento'),
    path('agendamento/shutdown/<int:pk>/', view=agendamento_shutdown_view, name='encerrar_agendamento'),
    # Gerenciamento dos grupos
    path('solicicao_agendamento/procurar_usuario/<int:solicitacao_pk>', procurar_usuario_view, name='procurar_usuario'),
    path('solicitacao_agendamento/adicionar_membro/<int:pk>/<int:membro_pk>', adicionar_membro_view, name='adicionar_membro'),
    path('solicitacao_agendamento/remover_member/<int:pk>/<int:membro_pk>', remover_membro_view, name='remover_membro'),
]
