"""Reconcilia a etapa da demanda com a entrega pendente.

Regra nova: "Em homologação" <=> existe uma entrega ENVIADA
(docs/specs/2026-10-21-demandas-fluxo-entrega-homologacao.md). Os dados antigos
violam isso de três jeitos, corrigidos aqui:

1. Demanda "Em homologação" pelo fluxo antigo, sem entrega: ganha uma entrega pendente
   com o ambiente, a URL e a senha que estavam na demanda, cobrindo todo o escopo (era
   assim que a homologação antiga funcionava).
2. Entrega pendente com a demanda "Em desenvolvimento" (o fluxo das entregas não movia a
   etapa): a demanda vai para "Em homologação", com previsão = prazo da entrega.
3. Entrega pendente com a demanda em qualquer outra etapa, ou segunda entrega pendente da
   mesma demanda: a entrega é cancelada.

Também remove o agendamento da expiração automática de entregas, que deixou de existir.

Pode rodar de novo sem efeito. O reverso é noop: desfazer a migration não apaga as entregas
criadas aqui nem devolve as demandas à etapa anterior.
"""

from django.db import migrations
from django.utils import timezone

EM_DESENVOLVIMENTO = 'Em desenvolvimento'
EM_HOMOLOGACAO = 'Em homologação'
ENVIADA = 'ENVIADA'
CANCELADA = 'CANCELADA'
AGENDAMENTO_EXPIRACAO = '[demandas] Expirar Entregas com Prazo Vencido'


def _responsavel_pela_homologacao(demanda, historico, HistoricoSituacao):
    """Quem levou a demanda à homologação; sem isso, a equipe ou o último autor de qualquer etapa."""
    if historico and historico.usuario_id:
        return historico.usuario
    responsavel = demanda.desenvolvedores.first() or demanda.analistas.first()
    if responsavel:
        return responsavel
    ultimo = HistoricoSituacao.objects.filter(demanda=demanda, usuario__isnull=False).order_by('-data_hora').first()
    return ultimo.usuario if ultimo else None


def _criar_entregas_da_homologacao_antiga(apps):
    Demanda = apps.get_model('demandas', 'Demanda')
    Entrega = apps.get_model('demandas', 'Entrega')
    HistoricoEntrega = apps.get_model('demandas', 'HistoricoEntrega')
    HistoricoSituacao = apps.get_model('demandas', 'HistoricoSituacao')
    Especificacao = apps.get_model('demandas', 'Especificacao')

    demandas = Demanda.objects.filter(situacao=EM_HOMOLOGACAO).exclude(entregas__status=ENVIADA)
    sem_responsavel = []
    for demanda in demandas:
        historico = HistoricoSituacao.objects.filter(demanda=demanda, situacao=EM_HOMOLOGACAO).order_by('-data_hora').first()
        responsavel = _responsavel_pela_homologacao(demanda, historico, HistoricoSituacao)
        if responsavel is None:
            sem_responsavel.append(demanda.pk)
            continue
        entrega = Entrega.objects.create(
            demanda=demanda,
            titulo='Homologação registrada antes das entregas',
            descricao='Entrega criada automaticamente a partir da homologação aberta pelo fluxo antigo.',
            status=ENVIADA,
            ambiente_homologacao_id=demanda.ambiente_homologacao_id,
            url_validacao=demanda.url_validacao,
            senha_homologacao=demanda.senha_homologacao,
            prazo_feedback=historico.data_previsao if historico else None,
            branch=demanda.branch,
            conclui_demanda=True,
            cadastrada_por=responsavel,
        )
        entrega.especificacoes.set(Especificacao.objects.filter(dod__demanda=demanda))
        enviada = HistoricoEntrega.objects.create(
            entrega=entrega, usuario=responsavel, acao='Enviada', observacao='Migrada da homologação pela etapa da demanda.'
        )
        if historico:
            # `enviada_em` e `data_hora` são auto_now_add: o update retroage sem passar pelo pre_save.
            Entrega.objects.filter(pk=entrega.pk).update(enviada_em=historico.data_hora)
            HistoricoEntrega.objects.filter(pk=enviada.pk).update(data_hora=historico.data_hora)

    if sem_responsavel:
        # Sem ninguém a quem atribuir a entrega a demanda ficaria "Em homologação" sem entrega,
        # violando a regra: melhor parar o deploy e tratar à mão do que seguir calado.
        raise RuntimeError(f'Demandas "Em homologação" sem nenhum usuário para cadastrar a entrega migrada: {sem_responsavel}')


def _reconciliar_entregas_pendentes(apps):
    Entrega = apps.get_model('demandas', 'Entrega')
    HistoricoEntrega = apps.get_model('demandas', 'HistoricoEntrega')
    HistoricoSituacao = apps.get_model('demandas', 'HistoricoSituacao')

    com_pendente = set()
    for entrega in Entrega.objects.filter(status=ENVIADA).select_related('demanda').order_by('enviada_em'):
        demanda = entrega.demanda
        if demanda.pk in com_pendente:
            motivo = 'Outra entrega da demanda já aguardava validação.'
        elif demanda.situacao in (EM_DESENVOLVIMENTO, EM_HOMOLOGACAO):
            com_pendente.add(demanda.pk)
            if demanda.situacao == EM_DESENVOLVIMENTO:
                demanda.situacao = EM_HOMOLOGACAO
                demanda.save(update_fields=['situacao'])
                HistoricoSituacao.objects.create(
                    demanda=demanda, usuario=entrega.cadastrada_por, situacao=EM_HOMOLOGACAO, data_previsao=entrega.prazo_feedback
                )
            continue
        else:
            motivo = f'Demanda estava "{demanda.situacao}", fora de homologação.'

        entrega.status = CANCELADA
        entrega.cancelada_em = timezone.now()
        entrega.save(update_fields=['status', 'cancelada_em'])
        HistoricoEntrega.objects.create(entrega=entrega, usuario=None, acao='Cancelada', observacao=motivo)


def _remover_agendamento_de_expiracao(apps):
    removidos, _ = apps.get_model('django_celery_beat', 'PeriodicTask').objects.filter(name=AGENDAMENTO_EXPIRACAO).delete()
    if removidos:
        # O model histórico não dispara o sinal que avisa o Beat; sem isso, um Beat que não for
        # reiniciado continua chamando o comando removido.
        apps.get_model('django_celery_beat', 'PeriodicTasks').objects.update_or_create(ident=1, defaults={'last_update': timezone.now()})


def reconciliar(apps, schema_editor):
    _criar_entregas_da_homologacao_antiga(apps)
    _reconciliar_entregas_pendentes(apps)
    _remover_agendamento_de_expiracao(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("demandas", "0051_entrega_conclui_demanda"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(reconciliar, migrations.RunPython.noop),
    ]
