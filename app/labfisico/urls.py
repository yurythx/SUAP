from django.urls import path

from .views import (
    adicionar_membro_view,
    agendamento_labfisico_detail_view,
    agendamento_shutdown_view,
    agendamento_sync_view,
    cancelar_solicitacao_agendamento_view,
    deferir_solicitacao_agendamento_view,
    guacamole_connection_add_view,
    # Servidores Guacamole
    guacamole_connection_group_detail_view,
    guacamole_connection_group_kill_sessions_view,
    guacamole_connection_kill_sessions_view,
    indeferir_solicitacao_agendamento_view,
    procurar_usuario_view,
    remover_membro_view,
    solicitacao_agendamento_detail_view,
    # Solicitacao e agendamento
    solicitar_agendamento_view,
)

app_name = 'labfisico'

urlpatterns = [
    # Servidores Guacamole
    path('labfisico/<int:pk>/', view=guacamole_connection_group_detail_view, name='guacamole_connection_group_detail'),
    path('labfisico/adicionar_cliente/<int:pk>/', view=guacamole_connection_add_view, name='adicionar_cliente_guacamole'),
    path('labfisico/shutdown/<int:pk>/', view=guacamole_connection_group_kill_sessions_view, name='guacamole_connection_group_kill_sessions'),
    path('client/shutdown/<int:pk>/', view=guacamole_connection_kill_sessions_view, name='guacamole_connection_kill_sessions'),
    # Solicitação
    path('solicitar_agendamento/<int:pk>', view=solicitar_agendamento_view, name='solicitar_agendamento'),
    path('solicitacao_agendamento/<int:pk>', view=solicitacao_agendamento_detail_view, name='solicitacao_agendamento'),
    path('solicitacao_agendamento/deferir/<int:pk>', view=deferir_solicitacao_agendamento_view, name='deferir_solicitacao'),
    path('solicitacao_agendamento/indeferir/<int:pk>', view=indeferir_solicitacao_agendamento_view, name='indeferir_solicitacao'),
    path('solicitacao_agendamento/cancelar/<int:pk>', view=cancelar_solicitacao_agendamento_view, name='cancelar_solicitacao'),
    # Agendamento
    path('agendamento/laboratoriofisico/<int:pk>/', view=agendamento_labfisico_detail_view, name='agendamento_labfisico'),
    path('agendamento/sync/<int:pk>/', view=agendamento_sync_view, name='liberar_agendamento'),
    path('agendamento/shutdown/<int:pk>/', view=agendamento_shutdown_view, name='encerrar_agendamento'),
    # Gerenciamento dos grupos
    path('solicicao_agendamento/procurar_usuario/<int:pk>', procurar_usuario_view, name='procurar_usuario'),
    path('solicitacao_agendamento/adicionar_membro/<int:pk>/<int:uid>', adicionar_membro_view, name='adicionar_membro'),
    path('solicitacao_agendamento/remover_membro/<int:pk>/<int:id>', remover_membro_view, name='remover_membro'),
]
