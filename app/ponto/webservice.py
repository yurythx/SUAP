from datetime import datetime

from django.db import transaction
from django.db.models import Q

from comum.models import Vinculo
from comum.utils import tl
from djtools.utils import get_client_ip
from ponto.models import Frequencia, Maquina, MaquinaLog

EXCEPTION_MAQUINA_SEM_PERMISSAO_PONTO = 'Máquina com ip {} não tem permissão para registro de frequências'


def registrar_frequencias(maquina, registros):
    usernames_erro = []
    """
    Registra a frequência de modo offline, o ``horario`` deve ser confiável.
    """
    FORMATO_HORARIO = '%Y-%m-%d %H:%M:%S'

    frequencias = []
    for registro in registros.split('|'):
        username, datahora = registro.split(';')
        horario = ''
        try:
            horario = datetime.strptime(datahora, FORMATO_HORARIO)
        except ValueError:
            msg = 'Para o usuário {} Horário "{}" não está no formato "{}"'.format(username, horario, FORMATO_HORARIO.replace('%', ''))
            MaquinaLog.objects.create(maquina=maquina, operacao='registrar_frequencias', status=MaquinaLog.ERRO, mensagem=msg)
            return {'ok': False, 'msg': msg}

        frequencias.append((username, horario))

    q = Q()
    for username, horario in frequencias:
        q |= Q(vinculo__user__username=username, horario=horario)
    frequencias_existentes = Frequencia.objects.filter(q).values_list('vinculo__user__username', 'horario')

    for frequencia in frequencias:
        username, horario = frequencia
        if frequencia not in frequencias_existentes:
            sid = transaction.savepoint()
            try:
                vinculo = Vinculo.objects.get(user__username=username)
                Frequencia.insere_frequencia(vinculo, maquina, horario, online=False)
                transaction.savepoint_commit(sid)
            except Exception:
                usernames_erro.append(username)
                transaction.savepoint_rollback(sid)
    return usernames_erro


def registrar_frequencias_offline(registros):
    ip = get_client_ip(tl.get_request())
    try:
        maquina = Maquina.objects.get(ip=ip, cliente_ponto=True, ativo=True)
    except Maquina.DoesNotExist:
        return {'ok': False, 'msg': EXCEPTION_MAQUINA_SEM_PERMISSAO_PONTO.format(ip)}

    usernames_erro = registrar_frequencias(maquina, registros)
    if usernames_erro:
        msg = 'Erros nos usuários: {}'.format(','.join(usernames_erro))
        MaquinaLog.objects.create(maquina=maquina, operacao='registrar_frequencias_offline', status=MaquinaLog.ERRO, mensagem=msg)
    else:
        MaquinaLog.objects.create(maquina=maquina, operacao='ponto_registrar_frequencias_offline')

    return {'ok': True, 'usernames_erro': ';'.join(usernames_erro)}


exposed = [[registrar_frequencias_offline, 'registrar_frequencias_offline']]
