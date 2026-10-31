from django.db import models


def servico_atualizar_estatisticas(**kwargs: object) -> None:
    """Marca as estatísticas como pendentes; o recálculo do serviço é manual (ação "Atualização das
    estatísticas", em background, ou o comando `centralservicos_atualizar_estatisticas_servicos`)."""
    hist_chamado = kwargs['instance']
    chamado = hist_chamado.chamado
    servico = chamado.servico

    chamado.anular_estatisticas()
    if servico and chamado.estah_fechado():
        servico.anular_estatisticas()


def signals_estatisticas():
    from centralservicos.models import HistoricoStatus

    models.signals.post_save.connect(sender=HistoricoStatus, receiver=servico_atualizar_estatisticas)
