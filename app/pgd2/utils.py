import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import Group
from django.db.models import Q
from django.utils.safestring import mark_safe

from comum.models import Configuracao
from comum.utils import get_setores_que_sou_chefe_hoje, get_sigla_reitoria
from djtools.utils import datas_entre, formata_segundos
from pit_rit.utils import PontoDocente
from ponto.compensacao import Contexto
from ponto.models import Frequencia, RecessoOpcaoEscolhida, RecessoPeriodoCompensacao
from rh.models import AfastamentoSiape, Funcao, ModalidadePGD, Servidor, ServidorFuncaoHistorico, Setor

# ---------------------------------
# CHEFES DE SETOR
# ---------------------------------


def setores_que_sou_chefe_hoje(servidor):
    """Retorna setores chefiados hoje por ``servidor`` incluindo descendentes (PGD 2).

    Para reitor ou chefe da reitoria, devolve toda a árvore PGD. Caso contrário,
    expande as chefias diretas via ``Setor.ids_subarvore``.

    Args:
        servidor: instância de ``Servidor`` cujas chefias serão consultadas; pode ser ``None``.

    Returns:
        QuerySet[Setor]: setores acessíveis no PGD 2; queryset vazio quando
        ``servidor`` é falsy ou sem chefias do dia.
    """
    if servidor:
        if servidor.eh_reitor():
            return get_setores_pgd()

        setores = get_setores_que_sou_chefe_hoje(servidor.get_user())

        if setores:
            if setores.filter(sigla=get_sigla_reitoria()).exists():
                return get_setores_pgd()
            ids_chefias = list(setores.values_list('id', flat=True))
            ids_setores = Setor.ids_subarvore(ids_chefias)
            return Setor.objects.suap().filter(id__in=ids_setores)
    return Setor.objects.suap_ativos().none()


def setores_que_sou_chefe_direto_hoje(servidor):
    # Retorna apenas os que eh chefe direto (SEM descentes)

    if servidor.eh_reitor():
        return get_setores_pgd()

    usuario_logado = servidor
    if usuario_logado.eh_chefe_do_setor_hoje(usuario_logado.setor):
        return Setor.objects.suap_ativos().filter(
            pk__in=usuario_logado.servidorfuncaohistorico_set.atuais()
            .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
            .values_list('setor_suap_id', flat=True)
            .distinct()
        )
    return Setor.objects.suap_ativos().none()


def setores_que_sou_fui_chefe_direto(servidor_chefe):
    # SEM descendentes

    if servidor_chefe.eh_reitor():
        return get_setores_pgd()

    qs_base = ServidorFuncaoHistorico.objects.filter(servidor=servidor_chefe, funcao__codigo__in=Funcao.get_codigos_funcao_chefia()).only(
        'setor_suap'
    )

    return Setor.objects.suap().filter(id__in=qs_base.values_list('setor_suap_id'))


def setores_que_sou_fui_chefe(servidor_chefe):
    # COM descendentes

    if servidor_chefe.eh_reitor():
        return get_setores_pgd()

    ids_setores = set()
    for setor in setores_que_sou_fui_chefe_direto(servidor_chefe):
        ids_setores.update(setor.ids_descendentes)
    return Setor.objects.suap().filter(id__in=ids_setores)


def setores_que_sou_chefe_direto_no_periodo(data_inicio, data_fim, servidor_chefe):
    # SEM descendentes

    if servidor_chefe.eh_reitor(na_data=data_inicio):
        return get_setores_pgd()

    qs_base = ServidorFuncaoHistorico.objects.filter(servidor=servidor_chefe, funcao__codigo__in=Funcao.get_codigos_funcao_chefia()).only(
        'setor_suap'
    )

    historico_funcao = qs_base.filter(
        # data de inicio da funcao dentro do período informado
        Q(data_inicio_funcao__gte=data_inicio, data_inicio_funcao__lte=data_fim)
        # data de inicio da funcao antes do período informado e data fim da função depois da data inicio do período
        | Q(data_inicio_funcao__lt=data_inicio, data_fim_funcao__gte=data_inicio)
        # data de inicio da funcao antes do período informado e sem data fim
        | Q(data_inicio_funcao__lt=data_inicio, data_fim_funcao__isnull=True)
        # data de fim da funcao deve está dentro do período informado
        | Q(data_fim_funcao__gte=data_inicio, data_fim_funcao__lte=data_fim)
    )

    return Setor.objects.suap().filter(id__in=historico_funcao.values_list('setor_suap_id'))


def setores_que_sou_chefe_no_periodo(data_inicio, data_fim, servidor_chefe):
    # COM descendentes

    if servidor_chefe.eh_reitor(na_data=data_inicio):
        return get_setores_pgd()

    ids_setores = set()
    for setor in setores_que_sou_chefe_direto_no_periodo(data_inicio, data_fim, servidor_chefe):
        ids_setores.update(setor.ids_descendentes)
    return Setor.objects.suap().filter(id__in=ids_setores)


def servidores_que_sou_chefe_direto_hoje(servidor):
    if servidor:
        if servidor.eh_reitor():
            return Servidor.objects.vinculados()

        # Retorna os setores que eh chefe hoje (COM descendentes)
        setores_chefe = setores_que_sou_chefe_hoje(servidor)
        if setores_chefe.filter(sigla=get_sigla_reitoria()).exists():
            return Servidor.objects.vinculados()

        # Servidores que eh chefe hoje
        ids_servidores = set()
        for setor in setores_chefe:
            chefes = chefes_do_setor(setor)
            ids_servidores.update(chefes.values_list('id', flat=True))

        return Servidor.objects.vinculados().filter(id__in=ids_servidores).exclude(id=servidor.id)

    return Servidor.objects.none()


def servidores_que_sou_chefe_no_periodo(data_inicio, data_fim, servidor_chefe):
    if servidor_chefe.eh_reitor(na_data=data_inicio):
        return Servidor.objects.vinculados()

    # Setores COM descendentes
    setores_chefe = setores_que_sou_chefe_direto_no_periodo(data_inicio, data_fim, servidor_chefe)

    # Servidores
    ids_servidores = set()
    for setor in setores_chefe:
        chefes = chefes_do_setor(setor)
        ids_servidores.update(chefes.values_list('id', flat=True))

    return Servidor.objects.vinculados().filter(id__in=ids_servidores)


def chefes_do_setor(setor):
    chefes_atuais = Servidor.objects.filter(
        pk__in=ServidorFuncaoHistorico.objects.atuais()
        .filter(setor_suap=setor, funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
        .values_list('servidor', flat=True)
        .distinct()
    )
    return chefes_atuais


def get_servidores_setores_sou_chefe_direto(user):
    # Setores que é chefe direto. Exemplo: DIGPE
    setores = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
    # Chefes dos subsetores da DIGPE. Exemplo: Chefe CODEPE, Chefe CODEPE, Chefe COGCAP, Chefe COADPE e Chefe COASS
    servidores = servidores_que_sou_chefe_direto_hoje(user.get_relacionamento())
    # Todos os subsetores da DIGPE
    setores_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())

    return setores, servidores, setores_hoje


def setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(user_chefe, data_inicio, data_fim, apenas_setores=True):
    # Se fui chefe no periodo ou Se sou chefe hoje
    # - Setores
    setores_chefe_no_periodo = setores_que_sou_chefe_no_periodo(data_inicio, data_fim, user_chefe.get_relacionamento())
    setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(user_chefe.get_relacionamento())
    setores = setores_chefe_no_periodo | setores_sou_chefe_hoje

    # - Servidores
    servidores = []
    if not apenas_setores:
        servidores_chefe_no_periodo = servidores_que_sou_chefe_no_periodo(data_inicio, data_fim, user_chefe.get_relacionamento())
        servidores_sou_chefe_hoje = servidores_que_sou_chefe_direto_hoje(user_chefe.get_relacionamento())
        servidores = servidores_chefe_no_periodo | servidores_sou_chefe_hoje
        servidores = servidores.exclude(matricula=user_chefe.username)

    return setores, servidores


# ---------------------------------
# PONTO
# ---------------------------------


def obter_dados_ponto_servidor(servidor, data_ini, data_fim, visualizar_futuro=False):
    # Essa rotina tende a sair do PGD
    # - Depois que o s novos cálculos de horas (obter_dados_horas_servidor) se consolidares ela sai
    return Frequencia.relatorio_ponto_pessoa(vinculo=servidor.get_vinculo(), data_ini=data_ini, data_fim=data_fim, visualizar_futuro=True)


def obter_dados_horas_ponto_servidor(servidor, data_ini, data_fim):
    # Busca dados de horas do servidor na compensacao.py
    return Contexto(servidor=servidor, periodo_data_inicial=data_ini, periodo_data_final=data_fim, considera_valor_debito_se_dia_futuro=True)


def obter_compensacoes_especificas_compesaveis_rit(rit):
    # Seleciona compensações específicas do servidor
    compensacoes_especificas = RecessoOpcaoEscolhida.objects.filter(
        funcionario=rit.adesao.servidor, validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO
    )

    # Retira as que não sao compensáveis
    compensacoes_compensaveis = []

    # datas_rit = datas_entre(rit.get_data_inicial(), rit.get_data_final())
    data_rit_inicial, data_rit_final = rit.data_inicio, rit.data_fim

    for ce in compensacoes_especificas:
        totais_ch = ce.totais_ch(carga_horaria_pendente=True)
        total_carga_horaria_pendente = totais_ch['total_carga_horaria_pendente']
        total_carga_horaria_pendente_por_dia = totais_ch['total_carga_horaria_pendente_por_dia']
        periodos_de_compensacao = ce.recesso_opcao.periodos_de_compensacao.all()
        for pc in periodos_de_compensacao:
            """
                rit         |--------------------------------|

                pc_1   |--------------------------------------------|
                pc_2            |--------------------------------------------|
                pc_3   |------------------------------|
                pc_4             |-----------------------|
            """
            pc_1_2_3_4 = pc.data_inicial <= data_rit_final and pc.data_final >= data_rit_inicial

            if pc_1_2_3_4:
                compensacoes_compensaveis.append((ce, pc.data_final, total_carga_horaria_pendente, total_carga_horaria_pendente_por_dia))

    return compensacoes_compensaveis


def get_pendencias_ponto_servidor(pit):
    lista_pendencias_ponto = []
    if pit.deve_verificar_ponto():
        servidor = pit.adesao.servidor
        ontem = get_datetime_now().date() - relativedelta(days=1)
        # Compensacoes especificas
        # -------------------
        q_rpc = RecessoPeriodoCompensacao.objects.filter(data_inicial__lte=ontem, data_final__gte=ontem).distinct('recesso_opcao')
        recesso_servidor = RecessoOpcaoEscolhida.objects.filter(
            funcionario=servidor,
            recesso_opcao__id__in=q_rpc.values_list('recesso_opcao_id', flat=True),
            validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
        )
        for es in recesso_servidor:
            dias = es.dias_efetivos_a_compensar()
            if dias and ontem > dias[-1]:
                total = es.totais_ch(carga_horaria_pendente=True)['total_carga_horaria_pendente']
                if total:
                    total_formatado = formata_segundos(total, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)
                    lista_pendencias_ponto.append(
                        f'O recesso "{es.recesso_opcao!s}" está com débito de: {total_formatado}. Acesse "https://suap.ifrn.edu.br/admin/ponto/recessoopcaoescolhida/" para regularizar essa situação.'
                    )
        # Se o ponto anterior está ok
        # -------------------
        # Ontem
        ontem = get_datetime_now().date() - relativedelta(days=1)
        data_inicial_pit = pit.data_inicio - relativedelta(days=1)
        data_fim = min(ontem, data_inicial_pit)
        # Primeiro dia do mês passado
        mes_passado = get_datetime_now().date() - relativedelta(months=1)
        data_ini = datetime.date(mes_passado.year, mes_passado.month, 1)

        ponto = Frequencia.relatorio_ponto_pessoa_novo(
            vinculo=servidor.get_vinculo(), servidor_logado=servidor, data_ini=data_ini, data_fim=data_fim, escopo='todos'
        )

        total_debito = ponto.get('totais_compensacao').get('total_debito_pendente')
        if total_debito != '0h 0min 0seg':
            link_ponto = f'<a href="/ponto/frequencia_funcionario/?funcionario={servidor.id}&faixa_0={data_ini!s}&faixa_1={data_fim!s}">relatório de ponto aqui</a>'
            lista_pendencias_ponto.append(
                mark_safe(
                    f'O Servidor não pode ter débitos no ponto. <strong>Para conferir seu débito de "{total_debito}" acesse o {link_ponto}.</strong>'
                )
            )
    return lista_pendencias_ponto


def get_ch_prevista_servidor_periodo(servidor, data_inicial, data_final):
    tempo_previsto_calculado = 0

    if servidor.eh_docente:
        # Tempo previsto do servidor DOCENTE
        pd = PontoDocente(servidor, data_inicial, data_final)
        horas = pd.total_relogio_exigido()
        if horas:
            tempo_previsto_calculado = horas / 3600

    if servidor.eh_tecnico_administrativo:
        # Tempo previsto do servidor TAE
        ths = obter_dados_horas_ponto_servidor(servidor, data_ini=data_inicial, data_fim=data_final)
        ths = ths.get_totais()

        # Calculando para meses que já passaram, atual e pra frente
        # total_exigido_final: total prévio descontado os abonos da chefia imediata
        # ths.total_debito_externo: se o servidor tiver alguma CH de GECC (ou outros). Vai ter que pahar essa hora a mais
        tempo_previsto_calculado = ths.total_exigido_final + ths.total_debito_externo
        tempo_previsto_calculado = tempo_previsto_calculado / 3600

    return tempo_previsto_calculado


# ---------------------------------
# SETOR SERVIDOR
# ---------------------------------


def get_setor_servidor_no_periodo_incluindo_funcao(servidor, data_inicio, data_fim):
    # Procurando por função [setor_suap]
    setor_funcao = servidor.historico_funcao(data_inicio=data_inicio, data_fim=data_fim).order_by('data_inicio_funcao').last()
    if setor_funcao and setor_funcao.setor_suap:
        return setor_funcao.setor_suap

    # Procurando por setor [setor]
    setor_suap = servidor.historico_setor_suap(data_inicio=data_inicio, data_fim=data_fim).order_by('data_inicio_no_setor').last()
    if setor_suap and setor_suap.setor:
        return setor_suap.setor

    return None


def get_setor_servidor_no_periodo(servidor, data_inicio, data_fim):
    # Procurando por setor [setor]
    setor_suap = servidor.historico_setor_suap(data_inicio=data_inicio, data_fim=data_fim).order_by('data_inicio_no_setor').last()
    if setor_suap and setor_suap.setor:
        return setor_suap.setor

    return None


def get_setor_siape_lotacao_servidor_no_periodo(servidor, data_inicio, data_fim):
    # Procurando por setor [setor]
    setor = (
        servidor.historico_setor_siape(data_inicio=data_inicio, data_fim=data_fim)
        .select_related('setor_lotacao')
        .order_by('data_inicio_setor_lotacao')
        .last()
    )
    if setor and setor.setor_lotacao:
        return setor.setor_lotacao

    return None


def get_setores_servidor_no_periodo_incluindo_funcao(servidor, data_inicio, data_fim):
    # setor
    setores_suap = list(servidor.historico_setor_suap(data_inicio=data_inicio, data_fim=data_fim).values_list('setor_id', flat=True))

    # setor_suap
    setores_suap.extend(list(servidor.historico_funcao(data_inicio=data_inicio, data_fim=data_fim).values_list('setor_suap_id', flat=True)))

    return Setor.objects.suap().filter(id__in=setores_suap)


def get_setores_servidor_no_periodo(servidor, data_inicio, data_fim):
    # setor
    setores_suap = list(servidor.historico_setor_suap(data_inicio=data_inicio, data_fim=data_fim).values_list('setor_id', flat=True))

    return Setor.objects.suap().filter(id__in=setores_suap)


# ---------------------------------
# GERAL
# ---------------------------------


def get_msg_nenhum_setor_habilitado(sigla_setor=''):
    return f"""
            O setor {sigla_setor} precisa ter cadastro de habilitação no PGD pela gestão.
            Entre em cotato com a Comissão Central/Local do PGD.
            """


def get_msg_singular_nenhum_setor_habilitado(sigla_setor):
    return f"""
           O setor relacionado precisa ter cadastro de habilitação no PGD pela gestão.
           Entre em contato com a Comissão Central/Local do PGD para verificar o cadastro de habilitação do setor {sigla_setor}.
           """


def get_msg_plural_nenhum_setor_habilitado(sigla_setores):
    return f"""
           Os setores relacionados precisam ter cadastro de habilitação no PGD pela gestão.
           Entre em contato com a Comissão Central/Local do PGD para verificar o cadastro de habilitação dos setores: {sigla_setores}.
           """


def get_setores_pgd():
    return Setor.objects.suap().suap_ativos()


def get_vbn_field(model, str_field):
    return model._meta.get_field(str_field).verbose_name


def get_datetime_now():
    try:
        from django.utils import timezone

        return timezone.now()
    except ImportError:
        from datetime import datetime

        return datetime.now()


def gv(v):
    v = v.get('v')
    if v:
        return Decimal(v)
    else:
        return Decimal(0)


def get_lista_dias_para_cadastrar(data_inicio, data_final, recorrencia_dias_semana):
    lista_dias = datas_entre(data_inicio, data_final)

    lista_dias_para_cadastrar = []

    if recorrencia_dias_semana:
        # Se tiver dias da semama para recorrencia
        # dias_recorrencia: list considerando (SEGUNDA = 0, TERCA = 1, QUARTA = 2, QUINTA = 3, SEXTA = 4, SABADO = 5, DOMINGO = 6)
        for d in lista_dias:
            if d >= data_inicio and str(d.weekday()) in recorrencia_dias_semana:
                lista_dias_para_cadastrar.append(d)
    else:
        # Se for ter recorrencia todos os dias até uma data
        lista_dias_para_cadastrar = lista_dias

    return lista_dias_para_cadastrar


def get_sigla_setor_uo(setor):
    setor_sigla = None
    uo_sigla = None
    if setor.sigla:
        setor_sigla = setor.sigla
    else:
        setor_sigla = setor.nome
    if setor.uo and setor.uo.sigla:
        uo_sigla = setor.uo.sigla

    sigla_setor_uo = f'{setor_sigla}/{uo_sigla}'
    if not uo_sigla:
        sigla_setor_uo = f'{setor_sigla}/{uo_sigla}'

    return sigla_setor_uo


def is_blank(text):
    """
    Testa se o texto está em branco ou contém somente espaços
    """
    return len(text.strip()) == 0


def pode_consultar_dados_api(user):
    # COCA
    # Sistemico PGD
    # Super user
    from pgd2.models import ComissaoPGD

    return user.is_superuser or ComissaoPGD.user_estah_em_gestao_pgd(user)


def amanha():
    # Obtém a data de hoje
    hoje = datetime.date.today()

    # Calcula a data de amanhã
    return hoje + datetime.timedelta(days=1)


# ---------------------------------
# CONFIGURAÇÕES
# ---------------------------------


def instituicao_eh_ifrn():
    return Configuracao.get_valor_por_chave('comum', 'instituicao_sigla') == 'IFRN'


def get_metodo_obter_codigo_siape_setor():
    cfg = Configuracao.get_valor_por_chave('pgd2', 'metodo_obter_codigo_siape_setor')
    if cfg:
        return int(cfg)
    return 1


def get_timeout_pgd2():
    cfg = Configuracao.get_valor_por_chave('pgd2', 'timeout')
    if cfg:
        return int(cfg)
    return 60


def get_max_workers():
    cfg = Configuracao.get_valor_por_chave('pgd2', 'max_workers')
    if cfg:
        return int(cfg)
    return 10


def permite_habilitacao_dos_setores():
    permite = Configuracao.get_valor_por_chave('pgd2', 'permite_habilitacao_dos_setores')
    return bool(permite)


# AUDITORIA
# ---------------------------------


"""
def servidor_eh_auditor(servidor):
    cargo_emprego = servidor.cargo_emprego.codigo if servidor.cargo_emprego else None
    return cargo_emprego in get_codigos_cargo_emprego_auditor()

def get_codigos_cargo_emprego_auditor():
    return ['701009']

"""


def get_servidores_auditoria():
    return Servidor.objects.ativos().filter(vinculos__user__groups=Group.objects.get(name='Auditor'), vinculos__user__is_superuser=False)


def servidor_eh_auditor(servidor):
    return get_servidores_auditoria().filter(id=servidor.id).exists()


def get_setor_auditoria_centralizada():
    setor_audge = Configuracao.get_valor_por_chave('pgd2', 'auditoria_centralizada_setor_audge')
    return Setor.objects.suap().filter(sigla=setor_audge).first()


def permite_auditoria_centralizada():
    permite = Configuracao.get_valor_por_chave('pgd2', 'permite_auditoria_centralizada')
    return bool(permite)


def setor_eh_auditoria_centralizada(setor):
    setor_audge = get_setor_auditoria_centralizada()
    if not setor_audge:
        return False
    return setor.sigla == setor_audge.sigla


def considerar_auditoria_centralizada():
    return bool(get_setor_auditoria_centralizada() and permite_auditoria_centralizada())


# PONTO
# ---------------------------------


def utilizar_integracao_com_ponto():
    return bool(Configuracao.get_valor_por_chave('pgd2', 'permite_integracao_com_ponto'))


def validar_ponto_antes_primeiro_pit_adesao():
    config = Configuracao.get_valor_por_chave('pgd2', 'permite_integracao_com_ponto_valida_ponto')
    return bool(config) and utilizar_integracao_com_ponto()


# PLAN ESTRAT
# ---------------------------------


def utilizar_integracao_com_plan_estrategico():
    return bool(Configuracao.get_valor_por_chave('pgd2', 'permite_integracao_com_plan_estrategico'))


# PDE
# ---------------------------------


def utilizar_integracao_com_pde():
    return bool(Configuracao.get_valor_por_chave('pgd2', 'permite_integracao_com_pde'))


# AFASTAMENTO EXTERIOR
# ---------------------------------


def get_afastamentos_exterior():
    afastamentos_pgd_exterior = Configuracao.get_valor_por_chave('pgd2', 'afastamentos_pgd_exterior')
    if afastamentos_pgd_exterior:
        afastamentos_pgd_exterior = [int(afastamento) for afastamento in afastamentos_pgd_exterior.split(',')]
        return AfastamentoSiape.objects.filter(id__in=afastamentos_pgd_exterior)
    return AfastamentoSiape.objects.none()


def get_pit_model():
    from pgd2.models import PlanoIndividualTrabalho

    return PlanoIndividualTrabalho


def get_html_diff_json(json1, json2, label_json1, label_json2):
    import difflib
    import json
    from html import escape

    # Converter JSONs para strings formatadas
    json_str1 = json.dumps(json1, indent=4, sort_keys=True).splitlines()
    json_str2 = json.dumps(json2, indent=4, sort_keys=True).splitlines()

    # Criar comparação de linha a linha
    differ = difflib.ndiff(json_str1, json_str2)

    # Criar estrutura para armazenar as colunas
    rows = []
    for line in differ:
        tag = line[:2]  # Pegamos os primeiros caracteres para identificar mudanças
        content = escape(line[2:])  # Escapamos HTML para segurança

        if tag == '  ':  # Linha igual
            rows.append(f'<tr><td>{content}</td><td>{content}</td><td></td></tr>')
        elif tag == '- ':  # Linha removida do JSON1
            rows.append(f'<tr class="error"><td>{content}</td><td></td><td><strong>REMOVIDO</strong></td></tr>')
        elif tag == '+ ':  # Linha adicionada no JSON2
            rows.append(f'<tr class="highlight"><td></td><td>{content}</td><td><strong>ADICIONADO</strong></td></tr>')
        elif tag == '? ':  # Indicação de mudança específica
            continue  # Ignoramos as linhas de "?" do difflib.ndiff

    # Criar estrutura da tabela
    html_table = f"""
    <table class="table-responsive">
        <thead>
            <tr>
                <th>{label_json1}</th>
                <th>{label_json2}</th>
                <th>Diferença</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """

    return html_table


def get_pgd_sou_gov(cpf, matricula_vinculo, atualizar_suap_com_sou_gov=True):
    """
    Modalidades no SOU GOV:
    - presencial
    - parcial
    - integral
    - no exterior

    Se o servidor não estiver em PGD no Sou GOV
    - Retorna (None, None)
    """

    retorno = ('erro', 'erro')

    from comum.models import APIExterna

    siape_conecta = APIExterna.SIAPE_CONECTA
    siape_net = APIExterna.SIAPE_NET
    api_externa_habilitada = (siape_conecta and siape_conecta.ativo and siape_conecta.url_base) or (
        siape_net and siape_net.ativo and siape_net.url_base
    )

    # Só consulta serviço externo se houver API ativa e minimamente configurada.
    if api_externa_habilitada:
        try:
            from rh.importador_ws import ImportadorWs

            importador = ImportadorWs()
            cpf = cpf.replace('.', '').replace('-', '')
            dados_funcionais = importador.get_dados_funcionais(cpf, todos_os_vinculos=True)
            if type(dados_funcionais) is not list:
                retorno = (dados_funcionais.get('participaPGD'), dados_funcionais.get('modalidadePGD'))
            if retorno[0] == 'erro':
                for dado_funcional in dados_funcionais:
                    if dado_funcional.get('matriculaSiape') == matricula_vinculo:
                        retorno = (dado_funcional.get('participaPGD'), dado_funcional.get('modalidadePGD'))
                        break
            if retorno[0] != 'erro' and atualizar_suap_com_sou_gov:
                atualizar_dados_pgd_suap(matricula_vinculo, retorno[0], retorno[1])
        except Exception:
            pass

    # Consulta dados no SUAP em caso de erro na consulta do serviço externo
    # ou se o serviço externo não estiver configurado (api_externa_habilitada = False)
    if not api_externa_habilitada or retorno[0] == 'erro':
        servidor = Servidor.objects.vinculados().filter(matricula=matricula_vinculo).first()
        if servidor:
            participaPGD = 'sim' if servidor.participa_pgd else 'não'
            modalidadePGD = servidor.modalidade_pgd.nome if servidor.modalidade_pgd else None
            retorno = (participaPGD, modalidadePGD)

    return retorno


def atualizar_dados_pgd_suap(matricula_vinculo, participaPGD, modalidadePGD):
    # atualiza dados PGD suap com base no SOU GOV
    if modalidadePGD and modalidadePGD != '':
        modalidadePGD = ModalidadePGD.get_or_create(nome=modalidadePGD)[0]
    participaPGD = participaPGD == 'sim'
    servidor = Servidor.objects.vinculados().filter(matricula=matricula_vinculo)
    servidor.update(modalidade_pgd=modalidadePGD, participa_pgd=participaPGD)


def get_justificativa_desligamento_automatico():
    # Retorna a justificativa para desligamento automático do servidor do PGD, caso haja uma configurada. Caso contrário, retorna None.
    cfg = Configuracao.get_valor_por_chave('pgd2', 'justificativa_desligamento_automatico')
    if cfg:
        return cfg
    return None


def setor_possui_relacao_siape_suap(setor):
    from pgd2.api_pgd2_v2 import ApiPgd2V2

    api_gd_v2 = ApiPgd2V2()
    return api_gd_v2.get_codigo_siape_setor(setor)
