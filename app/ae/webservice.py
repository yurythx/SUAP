import sys
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models.query_utils import Q
from django.db.utils import IntegrityError
from sentry_sdk import capture_exception

from ae.models import DemandaAluno, DemandaAlunoAtendida
from comum.models import Vinculo, UsuarioGrupo
from comum.utils import tl
from djtools.utils import get_client_ip
from edu.models import Aluno
from ponto.models import Maquina, MaquinaLog
from rh.models import PessoaFisica

EXCEPTION_MAQUINA_SEM_PERMISSAO_REFEICOES = 'Máquina sem permissão para registro de refeições - {}'


HORA_LIMITE_CAFE = 10
HORA_LIMITE_ALMOCO = 16


def _demanda_do_horario(horario: datetime, cafe: DemandaAluno, almoco: DemandaAluno, jantar: DemandaAluno) -> int:
    if horario.hour < HORA_LIMITE_CAFE:
        return cafe.id
    if horario.hour < HORA_LIMITE_ALMOCO:
        return almoco.id
    return jantar.id


def _vinculo_do_operador(operador_id: int | str) -> Vinculo | None:
    """Vínculo do operador pelo id da tabela ``pessoa`` do terminal; em dump antigo o id é a PF."""
    vinculo = Vinculo.objects.do_terminal(operador_id)
    if vinculo:
        return vinculo
    operador = PessoaFisica.objects.get(pk=operador_id)
    return (
        Vinculo.objects.filter(
            pessoa_id=operador.id,
            user__in=UsuarioGrupo.objects.filter(group__name='Operador do Terminal do Refeitório').values_list('user', flat=True),
        ).first()
        or Vinculo.objects.filter(pessoa_id=operador.id).last()
    )


def _registrar_atendimento(aluno: Aluno, demanda: int, horario: datetime, maquina: Maquina, vinculo_do_operador: Vinculo | None) -> None:
    if DemandaAlunoAtendida.objects.filter(aluno=aluno, demanda_id=demanda, data=horario).exists():
        return
    atendimento = DemandaAlunoAtendida()
    atendimento.responsavel_vinculo = vinculo_do_operador
    atendimento.demanda_id = demanda
    atendimento.aluno = aluno
    atendimento.data = horario
    atendimento.quantidade = Decimal(1)
    atendimento.valor = Decimal(0)
    atendimento.observacao = 'Registrada pelo sistema'
    atendimento.terminal = maquina
    atendimento.campus = maquina.uo
    atendimento.cadastrado_por = vinculo_do_operador.user
    atendimento.save()


def registrar_refeicoes_offline(registros: str, operador_id: int | str) -> dict:
    usernames_erro = []
    """
    Registra a refeição de modo offline, o ``horario`` deve ser confiável.
    """
    ip = get_client_ip(tl.get_request())
    try:
        maquina = Maquina.objects.get(ip=ip, ativo=True, cliente_refeitorio=True)
    except Maquina.DoesNotExist:
        return {'ok': False, 'msg': EXCEPTION_MAQUINA_SEM_PERMISSAO_REFEICOES.format(ip)}

    FORMATO_HORARIO = '%Y-%m-%d %H:%M:%S'
    cafe = DemandaAluno.objects.get(pk=DemandaAluno.CAFE)
    almoco = DemandaAluno.objects.get(pk=DemandaAluno.ALMOCO)
    jantar = DemandaAluno.objects.get(pk=DemandaAluno.JANTAR)
    refeicoes = []
    demandas = Q()
    for registro in registros.split('|'):
        username, datahora = registro.split(';')
        try:
            horario = datetime.strptime(datahora, FORMATO_HORARIO)
        except ValueError:
            msg = 'Para o usuário {} Horário "{}" não está no formato "{}"'.format(username, datahora, FORMATO_HORARIO.replace('%', ''))
            MaquinaLog.objects.create(maquina=maquina, operacao='registrar_refeicoes_offline', status=MaquinaLog.ERRO, mensagem=msg)
            return {'ok': False, 'msg': msg}

        demanda = _demanda_do_horario(horario, cafe, almoco, jantar)
        refeicoes.append([username, horario, demanda])
        demandas |= Q(aluno__matricula=username, data=horario, demanda_id=demanda)

    refeicoes_existentes = DemandaAlunoAtendida.objects.filter(demandas).values_list('aluno__matricula', 'data', 'demanda_id')
    vinculo_do_operador = _vinculo_do_operador(operador_id)
    for refeicao in refeicoes:
        username, horario, demanda = refeicao
        if refeicao not in refeicoes_existentes:
            sid = transaction.savepoint()
            try:
                _registrar_atendimento(Aluno.objects.get(matricula=username), demanda, horario, maquina, vinculo_do_operador)
                transaction.savepoint_commit(sid)
            except IntegrityError as e:
                capture_exception(e)
                if 'ae_demandaalunoatendida_aluno_id_key' not in ''.join(e.args):
                    usernames_erro.append(username)
                transaction.savepoint_rollback(sid)
            except Exception as e:
                capture_exception(e)
                usernames_erro.append(username)
                sys.stdout.write('ERRO TERMINAL')
                sys.stdout.write(str(e))
                sys.stdout.flush()
                transaction.savepoint_rollback(sid)
    if usernames_erro:
        MaquinaLog.objects.create(
            maquina=maquina,
            operacao='registrar_refeicoes_offline',
            status=MaquinaLog.ERRO,
            mensagem='Erros nos registros: {}'.format(','.join(usernames_erro)),
        )
    else:
        MaquinaLog.objects.create(maquina=maquina, operacao='registrar_refeicoes_offline')
    return {'ok': True, 'usernames_erro': ';'.join(usernames_erro)}


exposed = [[registrar_refeicoes_offline, 'registrar_refeicoes_offline']]
