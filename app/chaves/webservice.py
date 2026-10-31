import xmlrpc.client

from chaves import tasks
from chaves.models import Chave
from comum.models import User
from comum.utils import get_uo, tl
from djtools.utils import get_client_ip
from ponto.models import Maquina, MaquinaLog
from rh.models import PessoaFisica

DB_ENCODING = 'utf-8'
CLIENT_ENCODING = 'latin-1'
EXCEPTION_MAQUINA_SEM_PERMISSAO_CHAVES = 'A Máquina com ip {} não tem permissão para o módulo de chaves'
EXCEPTION_CHAVE_NAO_ENCONTRADA = 'A chave {} não foi encontrada'
MSG_USUARIO_SEM_CAMPUS = 'O usuário não está relacionado a nenhum Campus!'


def get_dados_chave(session_pk, chave_identificacao):
    """
    Retorna dados relevantes sobre a chave.

    Variáveis de retorno:
    1) ok : bool
    2) disponivel : bool
    3) pessoas_permitidas: dict
        {pessoa_id:str = [pessoa_nome:str,
                          template:xmlrpcbin, pode_registrar_sem_digital:bool]}
    4) pessoa_emprestimo : str (pessoa que está com a chave caso ela esteja emprestada)
    """
    ip = get_client_ip(tl.get_request())
    try:
        maquina = Maquina.objects.get(ip=ip, cliente_chaves=True, ativo=True)
    except Maquina.DoesNotExist:
        return {'ok': False, 'msg': EXCEPTION_MAQUINA_SEM_PERMISSAO_CHAVES.format(ip)}

    # Testando se o usuário está num Campus
    user = User.objects.get(username=session_pk)
    pessoa_emprestimo = ''
    user_uo = get_uo(user)
    if not user_uo:
        return {'ok': False, 'msg': MSG_USUARIO_SEM_CAMPUS}

    # Testando se existe chave no campus do usuário com a identificação passada
    try:
        chave = Chave.objects.get(identificacao=chave_identificacao, ativa=True, sala__predio__uo=user_uo)
        if not chave.disponivel:
            m = chave.movimentacao_set.get(data_devolucao=None)
            pessoa_emprestimo = str(m.vinculo_emprestimo.pessoa.pessoafisica)
    except Chave.DoesNotExist:
        return {'ok': False, 'msg': EXCEPTION_CHAVE_NAO_ENCONTRADA.format(chave_identificacao)}

    # Pegando dados das pessoas permitidas para a chave
    pessoas_permitidas = {}
    lista = list(chave.vinculos.values_list('pessoa_id', flat=True))
    lista.append(user.get_profile().pk)
    for pf in PessoaFisica.objects.filter(id__in=lista):
        tmpl = pf.get_template(CLIENT_ENCODING) or b''
        if isinstance(tmpl, str):
            try:
                tmpl_bytes = tmpl.encode(CLIENT_ENCODING)
            except Exception:
                tmpl_bytes = tmpl.encode('utf-8', errors='ignore')
        else:
            tmpl_bytes = tmpl or b''
        pessoas_permitidas[str(pf.pk)] = [pf.nome, xmlrpc.client.Binary(tmpl_bytes), pf.tem_digital_fraca]
    MaquinaLog.objects.create(maquina=maquina, operacao='chaves_get_dados_chave')
    return {'ok': True, 'disponivel': chave.disponivel, 'pessoas_permitidas': pessoas_permitidas, 'pessoa_emprestimo': pessoa_emprestimo}


def efetuar_emprestimo_ou_devolucao(session_pk, chave_identificacao, pessoa_emprestimo, observacao):
    ip = get_client_ip(tl.get_request())
    try:
        maquina = Maquina.objects.get(ip=ip, cliente_chaves=True, ativo=True)
    except Maquina.DoesNotExist:
        return {'ok': False, 'msg': EXCEPTION_MAQUINA_SEM_PERMISSAO_CHAVES.format(ip)}

    # Testando se o usuário está num Campus
    user = User.objects.get(username=session_pk)
    user_uo = get_uo(user)
    if not user_uo:
        return {'ok': False, 'msg': MSG_USUARIO_SEM_CAMPUS}

    # Testando se existe chave no campus do usuário com a identificação passada
    try:
        chave = Chave.objects.get(identificacao=chave_identificacao, ativa=True, sala__predio__uo=user_uo)
    except Chave.DoesNotExist:
        return {'ok': False, 'msg': EXCEPTION_CHAVE_NAO_ENCONTRADA.format(chave_identificacao)}

    pessoa_emprestimo = PessoaFisica.objects.get(pk=pessoa_emprestimo)
    vinculo = pessoa_emprestimo.get_vinculo()

    if chave.disponivel and not chave.vinculo_permitido(vinculo):
        msg = 'Pessoa não permitida'
        MaquinaLog.objects.create(maquina=maquina, operacao='chaves_efetuar_emprestimo_ou_devolucao', status=MaquinaLog.ERRO, mensagem=msg)
        return {'ok': False, 'msg': msg}

    try:
        if chave.disponivel:
            msg = 'Empréstimo realizado com sucesso'
            MaquinaLog.objects.create(maquina=maquina, operacao='chaves_efetuar_emprestimo_ou_devolucao', mensagem=msg)
            chave._efetuar_emprestimo(vinculo, user.get_vinculo(), observacao)
            return {'ok': True, 'msg': msg}
        else:
            msg = 'Devolução realizada com sucesso'
            MaquinaLog.objects.create(maquina=maquina, operacao='chaves_efetuar_emprestimo_ou_devolucao', mensagem=msg)
            chave._efetuar_devolucao(vinculo, user.get_vinculo(), observacao)
            return {'ok': True, 'msg': msg}
    except Exception as e:
        msg = str(e)
        MaquinaLog.objects.create(maquina=maquina, operacao='chaves_efetuar_emprestimo_ou_devolucao', status=MaquinaLog.ERRO, mensagem=msg)
        return {'ok': False, 'msg': msg}


def importar_emprestimos(dados):
    ip = get_client_ip(tl.get_request())
    try:
        maquina = Maquina.objects.get(ip=ip, cliente_chaves=True, ativo=True)
    except Maquina.DoesNotExist:
        return {'ok': False, 'msg': EXCEPTION_MAQUINA_SEM_PERMISSAO_CHAVES.format(ip)}

    tasks.inserir_movimentacoes(maquina, dados)
    return {'ok': True, 'erros': ''}


exposed = [
    [get_dados_chave, 'chaves/get_dados_chave'],
    [efetuar_emprestimo_ou_devolucao, 'chaves/efetuar_emprestimo_ou_devolucao'],
    [importar_emprestimos, 'importar_emprestimos'],
]
