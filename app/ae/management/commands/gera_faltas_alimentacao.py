import calendar
import datetime
from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Q

from ae.models import (
    AgendamentoRefeicao,
    DatasLiberadasFaltasAlimentacao,
    DatasRecessoFerias,
    DemandaAluno,
    DemandaAlunoAtendida,
    HistoricoFaltasAlimentacao,
    HistoricoSuspensoesAlimentacao,
    Inscricao,
    Programa,
    TipoRefeicao,
)
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification
from edu.models import Aluno


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        programas = Programa.objects.filter(tipo_programa__sigla=Programa.TIPO_ALIMENTACAO)
        if datetime.datetime.now().hour >= 23:
            hoje = date.today()
            data_para_desbloqueio = date.today() + relativedelta(days=1)
        else:
            hoje = date.today() - relativedelta(days=1)
            # fazendo controle do dia de verificação já que a rotina é executada depois da meia-noite
            data_para_desbloqueio = date.today()

        intervalo_mes = calendar.monthrange(hoje.year, hoje.month)
        inicio_mes = datetime.date(hoje.year, hoje.month, 1)
        fim_mes = datetime.date(hoje.year, hoje.month, intervalo_mes[1])

        for programa in programas:
            registrar_falta_hoje = True
            datas_liberadas = DatasLiberadasFaltasAlimentacao.objects.filter(campus=programa.instituicao)
            if (
                datas_liberadas.filter(data=hoje).exists()
                or datas_liberadas.filter(recorrente=True, data__day=hoje.day, data__month=hoje.month).exists()
            ):
                registrar_falta_hoje = False
            if not DemandaAlunoAtendida.objects.filter(
                campus=programa.instituicao, data__startswith=hoje, demanda__in=[DemandaAluno.ALMOCO, DemandaAluno.JANTAR, DemandaAluno.CAFE]
            ).exists():
                registrar_falta_hoje = False

            datas_liberadas_recesso = DatasRecessoFerias.objects.filter(campus=programa.instituicao)
            if datas_liberadas_recesso.filter(data=hoje).exists():
                registrar_falta_hoje = False

            registra_falta_e_eh_dia_util = registrar_falta_hoje and hoje.weekday() not in (5, 6)  # verifica se hoje eh dia util:

            # código que gera os registros de falta dos alunos agendados
            if registra_falta_e_eh_dia_util:
                for registro in AgendamentoRefeicao.objects.filter(cancelado=False, data=hoje, programa=programa):
                    aluno = registro.aluno
                    tipo_refeicao = refeicao = None
                    if registro.tipo_refeicao == AgendamentoRefeicao.TIPO_CAFE:
                        tipo_refeicao = DemandaAluno.CAFE
                        refeicao = TipoRefeicao.TIPO_CAFE
                    elif registro.tipo_refeicao == AgendamentoRefeicao.TIPO_ALMOCO:
                        tipo_refeicao = DemandaAluno.ALMOCO
                        refeicao = TipoRefeicao.TIPO_ALMOCO
                    elif registro.tipo_refeicao == AgendamentoRefeicao.TIPO_JANTAR:
                        tipo_refeicao = DemandaAluno.JANTAR
                        refeicao = TipoRefeicao.TIPO_JANTAR

                    if tipo_refeicao and not programa.get_atendimento(aluno, tipo_refeicao, hoje):
                        if not HistoricoFaltasAlimentacao.objects.filter(
                            aluno=aluno, participacao__isnull=True, tipo_refeicao=refeicao, data=hoje, cancelada=False
                        ).exists():
                            nova_falta = HistoricoFaltasAlimentacao()
                            nova_falta.aluno = aluno
                            nova_falta.programa = programa
                            nova_falta.tipo_refeicao = refeicao
                            nova_falta.data = hoje
                            nova_falta.save()
            # ---------------------------------------------------

            # Define queryset de alunos participantes
            alunos = Aluno.objects.filter(
                Q(participacao__programa=programa), Q(participacao__data_termino__isnull=True) | Q(participacao__data_termino__gte=hoje)
            ).only('pessoa_fisica')
            alunos = alunos.distinct().order_by('pessoa_fisica__nome')

            for aluno in alunos:
                try:
                    inscricao = aluno.inscricao_set.get(programa=programa).sub_instance()
                except Inscricao.DoesNotExist:
                    inscricao = None
                    solicitacao_atendida = None
                except Exception:
                    # Ainda existem alunos com inscrições duplicadas (ver https://projetos.ifrn.edu.br/issues/3889)
                    # Existem alunos com participações que não tem os dados dos atendimentos (ex: 2009153050335)
                    inscricoes = aluno.inscricao_set.filter(
                        programa=programa, participacao__isnull=False, participacao__data_termino__isnull=True
                    ).distinct()
                    if inscricoes.exists():
                        inscricao = inscricoes[0].sub_instance()
                    else:
                        inscricao = None

                participacao = None
                if inscricao:
                    try:
                        participacao = inscricao.get_participacao_aberta()
                    except Exception:
                        pass
                    if participacao:
                        participacao.sub_instance().qtd_faltas_alimentacao = 0
                        participacao.sub_instance().save()
                    if (
                        participacao
                        and participacao.sub_instance().suspensa
                        and participacao.sub_instance().liberar_em
                        and participacao.sub_instance().liberar_em <= data_para_desbloqueio
                    ):
                        novo_historico = HistoricoSuspensoesAlimentacao()
                        novo_historico.participacao = participacao
                        novo_historico.data_inicio = participacao.sub_instance().suspensa_em
                        novo_historico.data_termino = data_para_desbloqueio
                        novo_historico.liberado_por_vinculo = participacao.sub_instance().liberado_por_vinculo
                        novo_historico.save()
                        participacao.sub_instance().suspensa = False
                        participacao.sub_instance().suspensa_em = None
                        participacao.sub_instance().liberar_em = None
                        participacao.sub_instance().liberado_por_vinculo = None
                        participacao.sub_instance().save()
                        titulo = '[SUAP] Desbloqueio Automático de Participação em Programa de Alimentação'
                        texto = (
                            '<h1>Serviço Social</h1>'
                            '<h2>Desbloqueio Automático de Participação em Programa de Alimentação</h2>'
                            '<p>Sua participação no Programa de Alimentação Escolar foi desbloqueada.</p>'
                            '<p>Procure o setor de Serviço Social do seu campus para mais informações.</p>'
                        )
                        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participacao.aluno.get_vinculo()])

                # código que gera os registros de falta dos alunos participantes
                if registra_falta_e_eh_dia_util:
                    for tipo_refeicao in (DemandaAluno.ALMOCO, DemandaAluno.JANTAR, DemandaAluno.CAFE):
                        if participacao:
                            if tipo_refeicao == DemandaAluno.ALMOCO:
                                solicitacao_atendida = participacao.sub_instance().solicitacao_atendida_almoco
                            elif tipo_refeicao == DemandaAluno.JANTAR:
                                solicitacao_atendida = participacao.sub_instance().solicitacao_atendida_janta
                            elif tipo_refeicao == DemandaAluno.CAFE:
                                solicitacao_atendida = participacao.sub_instance().solicitacao_atendida_cafe
                        else:
                            solicitacao_atendida = None

                        # Se o aluno não tiver demandaalunoatendida e for participante
                        if not programa.get_atendimento(aluno, tipo_refeicao, hoje):
                            if solicitacao_atendida:
                                if hoje.weekday() == 0:
                                    dia_solicitacao = solicitacao_atendida.seg
                                elif hoje.weekday() == 1:
                                    dia_solicitacao = solicitacao_atendida.ter
                                elif hoje.weekday() == 2:
                                    dia_solicitacao = solicitacao_atendida.qua
                                elif hoje.weekday() == 3:
                                    dia_solicitacao = solicitacao_atendida.qui
                                elif hoje.weekday() == 4:
                                    dia_solicitacao = solicitacao_atendida.sex

                            if solicitacao_atendida and solicitacao_atendida.valida() and dia_solicitacao:
                                # Se o aluno ainda é participante até a data ref
                                if participacao:
                                    if tipo_refeicao == DemandaAluno.ALMOCO:
                                        refeicao = TipoRefeicao.TIPO_ALMOCO
                                    elif tipo_refeicao == DemandaAluno.CAFE:
                                        refeicao = TipoRefeicao.TIPO_CAFE
                                    elif tipo_refeicao == DemandaAluno.JANTAR:
                                        refeicao = TipoRefeicao.TIPO_JANTAR

                                    if not HistoricoFaltasAlimentacao.objects.filter(
                                        aluno=aluno, participacao=participacao, programa=programa, tipo_refeicao=refeicao, data=hoje, cancelada=False
                                    ).exists():
                                        nova_falta = HistoricoFaltasAlimentacao()
                                        nova_falta.aluno = aluno
                                        nova_falta.participacao = participacao
                                        nova_falta.programa = programa
                                        nova_falta.tipo_refeicao = refeicao
                                        nova_falta.data = hoje
                                        nova_falta.save()

                                    faltas_no_mes = HistoricoFaltasAlimentacao.objects.filter(
                                        justificativa__isnull=True,
                                        aluno=aluno,
                                        participacao=participacao,
                                        data__gte=inicio_mes,
                                        data__lte=fim_mes,
                                        cancelada=False,
                                    )
                                    total_faltas_no_mes = faltas_no_mes.count()
                                    participacao.sub_instance().qtd_faltas_alimentacao = total_faltas_no_mes
                                    participacao.sub_instance().save()
                                    if total_faltas_no_mes >= programa.qtd_faltas_bloqueio_alimentacao:
                                        suspender = False
                                        suspensoes = HistoricoSuspensoesAlimentacao.objects.filter(participacao=participacao)
                                        if suspensoes.exists():
                                            ultima_liberacao = suspensoes.order_by('-data_termino')[0].data_termino
                                            total_apos_suspensao = faltas_no_mes.filter(data__gte=ultima_liberacao).count()
                                            participacao.sub_instance().qtd_faltas_alimentacao = total_apos_suspensao
                                            participacao.sub_instance().save()
                                            if total_apos_suspensao >= programa.qtd_faltas_bloqueio_alimentacao:
                                                suspender = True
                                        else:
                                            suspender = True
                                        if suspender:
                                            if not participacao.sub_instance().suspensa:
                                                participacao.sub_instance().suspensa = True
                                                participacao.sub_instance().suspensa_em = datetime.datetime.now()
                                                participacao.sub_instance().save()

                                                titulo = '[SUAP] Suspensão de Participação em Programa de Alimentação'
                                                texto = (
                                                    '<h1>Serviço Social</h1>'
                                                    '<h2>Suspensão de Participação em Programa de Alimentação</h2>'
                                                    '<p>Sua participação no Programa de Alimentação Escolar foi suspensa por faltas não justificadas.</p>'
                                                    '<p>Procure o setor de Serviço Social do seu campus para mais informações.</p>'
                                                )
                                                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participacao.aluno.get_vinculo()])
