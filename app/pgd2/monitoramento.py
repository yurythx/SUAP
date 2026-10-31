from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Q
from django.utils import timezone

from pgd2.models import (
    ConfiguracaoPerfilServidor,
    DesligamentoPgdServidor,
    JustificativaDesligamentoPgd,
    MonitoramentoServidor,
    ParticipantePgd,
    PeriodoPitRit,
    PitSetores,
    PlanoEntregasSetorial,
    PlanoIndividualTrabalho,
    RegistroAcaoSolicitacaoAdesaoServidor,
    SetorHabilitacao,
    SolicitacaoAdesaoServidor,
)
from pgd2.utils import (
    get_ch_prevista_servidor_periodo,
    get_datetime_now,
    get_justificativa_desligamento_automatico,
    permite_habilitacao_dos_setores,
    utilizar_integracao_com_ponto,
)
from rh.models import PCA, FormaProvimentoVacancia, Servidor

# ================================================
# Consultas
# ================================================

# PESs
# ------------------------------------------------


def get_pess_inconsistentes_aprovacao(tipo=1, uos=None, setores=None, periodos_pes=None):
    # Todos os setores com PES
    # - Ainda não entregues para aprovacao
    # - OU entregues para a aprovacao mas ainda nao aprovados
    verificar = PlanoEntregasSetorial.objects.filter(situacao=PlanoEntregasSetorial.EM_CADASTRO)
    if tipo == 2:
        verificar = PlanoEntregasSetorial.objects.filter(situacao=PlanoEntregasSetorial.SOLICITADO_APROVACAO)

    # Filtros
    if uos:
        verificar = verificar.filter(setor__uo__in=uos)
    if setores:
        verificar = verificar.filter(setor__in=setores)
    if periodos_pes:
        verificar = verificar.filter(periodo_pes__in=periodos_pes)

    return verificar


def get_pess_de_setores_nao_habilitados(uos=None, setores=None, periodos_pes=None):
    # Todos os PESs de setores não habilitados no PGD

    setores_habilitados = SetorHabilitacao.get_setores_habilitados()
    verificar = PlanoEntregasSetorial.objects.all().exclude(setor__in=setores_habilitados)

    # Filtros
    if uos:
        verificar = verificar.filter(setor__uo__in=uos)
    if setores:
        verificar = verificar.filter(setor__in=setores)
    if periodos_pes:
        verificar = verificar.filter(periodo_pes__in=periodos_pes)

    return verificar


def get_pess_de_setores_habilitados(uos=None, setores=None, periodos_pes=None):
    # Todos os PESs de setores habilitados no PGD

    setores_habilitados = SetorHabilitacao.get_setores_habilitados()
    verificar = PlanoEntregasSetorial.objects.filter(setor__in=setores_habilitados)

    # Filtros
    if uos:
        verificar = verificar.filter(setor__uo__in=uos)
    if setores:
        verificar = verificar.filter(setor__in=setores)
    if periodos_pes:
        verificar = verificar.filter(periodo_pes__in=periodos_pes)

    return verificar


def get_pess_aprovados_de_setores_nao_habilitados(uos=None, setores=None, periodos_pes=None):
    # Todos os PESs de setores não habilitados no PGD

    setores_habilitados = SetorHabilitacao.get_setores_habilitados()
    verificar = PlanoEntregasSetorial.get_pess_aprovados().exclude(setor__in=setores_habilitados)

    # Filtros
    if uos:
        verificar = verificar.filter(setor__uo__in=uos)
    if setores:
        verificar = verificar.filter(setor__in=setores)
    if periodos_pes:
        verificar = verificar.filter(periodo_pes__in=periodos_pes)

    return verificar


def get_setores_habilitados_sem_pes_criado(uos=None, setores=None, periodos_pes=None):
    # Setores habilitados que não possuem PES criado

    setores_habilitados = SetorHabilitacao.get_setores_habilitados()
    pess_criados = PlanoEntregasSetorial.objects.all()

    # Filtros
    if uos:
        setores_habilitados = setores_habilitados.filter(uo__in=uos)
        pess_criados = pess_criados.filter(setor__uo__in=uos)
    if setores:
        setores_habilitados = setores_habilitados.filter(id__in=setores.values_list('id', flat=True))
        pess_criados = pess_criados.filter(setor__in=setores)
    if periodos_pes:
        pess_criados = pess_criados.filter(periodo_pes__in=periodos_pes)

    # Exclui os setores habilitados que possuem PES criado
    setores_habilitados = setores_habilitados.exclude(id__in=pess_criados.values_list('setor_id', flat=True))
    setores_habilitados = setores_habilitados.order_by('sigla')
    return setores_habilitados


def get_pess_aptos_para_analise_execucao(uos=None, setores=None, periodos_pes=None):
    # PESs aprovados para análise de execução

    pess = PlanoEntregasSetorial.get_pess_pendendentes_analise_execucao()

    # Filtros
    if uos:
        pess = pess.filter(setor__uo__in=uos)
    if setores:
        pess = pess.filter(setor__in=setores)
    if periodos_pes:
        pess = pess.filter(periodo_pes__in=periodos_pes)

    return pess


def get_pess_aptos_para_avaliacao_execucao(uos=None, setores=None, periodos_pes=None):
    # PESs aprovados para avaliação de execução

    pess = PlanoEntregasSetorial.get_pess_pendendentes_avaliacao()

    # Filtros
    if uos:
        pess = pess.filter(setor__uo__in=uos)
    if setores:
        pess = pess.filter(setor__in=setores)
    if periodos_pes:
        pess = pess.filter(periodo_pes__in=periodos_pes)

    return pess


def get_pess_relacionados_a_pit(tipo=1, uos=None, setores=None, periodos_pes=None):
    # Tipo 1: PESs aprovados, mas sem Plano de Trabalho relacionado.
    # Tipo 2: PESs aprovados, mas sem Plano de Trabalho homologado relacionado.

    pess = PlanoEntregasSetorial.get_pess_aprovados()
    if tipo == 1:
        pess = PlanoEntregasSetorial.get_pess_aprovados()
        ids_pess_com_pit = (
            PitSetores.objects.filter(pes__in=pess, pit__isnull=False)
            .exclude(pit__situacao=PlanoIndividualTrabalho.CANCELADO)
            .values_list('pes__id', flat=True)
            .distinct()
        )
        pess = pess.exclude(id__in=ids_pess_com_pit)
    elif tipo == 2:
        pess = PlanoEntregasSetorial.get_pess_aprovados()
        pits_homologados = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
        ids_pess_com_pit_homologado = PitSetores.objects.filter(pes__in=pess, pit__in=pits_homologados).values_list('pes__id', flat=True).distinct()
        pess = pess.exclude(id__in=ids_pess_com_pit_homologado)

    # Filtros
    if uos:
        pess = pess.filter(setor__uo__in=uos)
    if setores:
        pess = pess.filter(setor__in=setores)
    if periodos_pes:
        pess = pess.filter(periodo_pes__in=periodos_pes)

    return pess


# Servidores
# ------------------------------------------------


def get_servidores_inconsistentes_regra_de_perfil_geral_servidor(buscar_str=None, setores=None, uos=None):
    # Todos os servidores com adesão ao PGD sem desligamento
    servidores = SolicitacaoAdesaoServidor.get_servidores_em_pgd()
    servidores = servidores.order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)

    # Regra de habilitação do servidor pelo seu gerfil geral
    def estah_inconsistente_pela_regra_de_perfil_geral_servidor(servidor):
        retorno = ConfiguracaoPerfilServidor.checa_perfil_servidor(servidor, retorna_motivo=True)
        if retorno:
            return False, None
        return True, retorno

    # Verifica
    servidores_inconsistentes = []
    for servidor in servidores:
        estah_inconsistente = estah_inconsistente_pela_regra_de_perfil_geral_servidor(servidor)
        if estah_inconsistente[0]:
            servidores_inconsistentes.append((servidor, estah_inconsistente[1]))

    return servidores_inconsistentes


def get_servidores_inconsistentes_regra_habilitacao_setor(buscar_str=None, setores=None, uos=None):
    # Todos os servidores com adesão ao PGD sem desligamento
    servidores = SolicitacaoAdesaoServidor.get_servidores_em_pgd()
    servidores = servidores.order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)

    # Pela regra de habilitação do setor
    def estah_inconsistente_pela_regra_de_habilitacao_setor(servidor):
        habilitacao = SetorHabilitacao.setor_estah_habilitado(servidor.setor)

        if not habilitacao:
            return True, f'Setor {servidor.setor} não está habilitado no PGD'

        """
        servidores = habilitacao.servidores.all()
        if servidores and servidor not in servidores:
            return True, f'Servidor não habilitado na lista de Servidores do cadastro de habilitação PGD setor {habilitacao.setor}'

        cargos_emprego = habilitacao.cargos_emprego.all()
        if cargos_emprego and servidor.cargo_emprego not in cargos_emprego:
            return True, f'Servidor não habilitado na lista de Cargos Emprego do cadastro de habilitação PGD setor {habilitacao.setor}'
        """

        return False, None

    # Verifica
    servidores_inconsistentes = []
    for servidor in servidores:
        estah_inconsistente = estah_inconsistente_pela_regra_de_habilitacao_setor(servidor)
        if estah_inconsistente[0]:
            servidores_inconsistentes.append((servidor, estah_inconsistente[1]))

    return servidores_inconsistentes


def get_servidores_adesao_vigente_sem_pit_relacionado(regra=1, buscar_str=None, setores=None, periodo_pit_rit=None, uos=None):
    # Regras
    # 1: Servidores com adesão vigente e sem PIT relacionado (exceto cancelados)
    # 2: Servidores com adesão vigente e sem PIT homologado ao menos uma vez (exceto cancelados)
    # 3: Servidores com adesão vigente e sem PIT homologado ao menos uma vez no período atual (exceto cancelados)
    # 4: Servidores com adesão vigente e sem PIT homologado ao menos uma vez no em determinado periodo (exceto cancelados)
    #   - periodo_pit_rit: apenas para esta regra

    adesoes_vigentes = SolicitacaoAdesaoServidor.get_adesoes_vigentes()

    pits_relacionados_adesao_vigente = []
    if regra == 1:
        # PITs relacionados as adesões
        pits_relacionados_adesao_vigente = PlanoIndividualTrabalho.objects.filter(adesao__in=adesoes_vigentes)
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
    elif regra == 2:
        # PITs relacionados as adesões e que foram homologados ao menos uma vez
        pits_relacionados_adesao_vigente = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.filter(adesao__in=adesoes_vigentes)
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
    elif regra == 3:
        # PITs relacionados as adesões, relacionados ao período atual e que foram homologados ao menos uma vez
        periodo_pit_atual = PeriodoPitRit.get_periodo_pit_atual()
        pits_relacionados_adesao_vigente = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.filter(adesao__in=adesoes_vigentes)
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.filter(periodo_pit_rit=periodo_pit_atual)
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
    elif regra == 4 and periodo_pit_rit:
        # PITs relacionados as adesões, relacionados ao período passado como parâmetro e que foram homologados ao menos uma vez
        pits_relacionados_adesao_vigente = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.filter(adesao__in=adesoes_vigentes)
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.filter(periodo_pit_rit=periodo_pit_rit)
        pits_relacionados_adesao_vigente = pits_relacionados_adesao_vigente.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)

    if pits_relacionados_adesao_vigente:
        # Exclui das adesões vigentes os servidores que tem PIT relacionado a alguma adesão vigente
        adesoes_vigentes = adesoes_vigentes.exclude(servidor__in=pits_relacionados_adesao_vigente.values_list('adesao__servidor_id', flat=True))

        # Obtem os servidores
        servidores = Servidor.objects.vinculados().filter(id__in=adesoes_vigentes.values_list('servidor_id', flat=True))
        servidores = servidores.order_by('pessoa_fisica__nome')

        # Filtros
        if buscar_str:
            servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
        if setores:
            servidores = servidores.filter(setor__in=setores)
        if uos:
            servidores = servidores.filter(setor__uo__in=uos)

    else:
        return Servidor.objects.none()

    return servidores


def get_servidores_adesao_vigente_sem_pit_homologado(buscar_str=None, setores=None):
    servidores = SolicitacaoAdesaoServidor.get_servidores_com_adesao_vigente()
    servidores_em_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd()
    servidores = servidores.exclude(adesao__servidor=servidores_em_pgd)
    servidores = servidores.order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)

    return servidores


def get_servidores_em_pgd(buscar_str=None, setores=None, uos=None):
    servidores = SolicitacaoAdesaoServidor.get_servidores_em_pgd()
    servidores = servidores.order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)

    return servidores


def get_servidores_em_pgd_no_sou_gov(buscar_str=None, setores=None, uos=None):
    # Servidores em PGD no SOU GOV
    # participa_pgd é atualizado pelo WS SIAPE
    servidores = Servidor.objects.vinculados().filter(participa_pgd=True).order_by('pessoa_fisica__nome')
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)

    return servidores


def get_servidores_em_pgd_no_suap_mas_nao_no_sou_gov(buscar_str=None, setores=None, uos=None):
    # Servidores em PGD no SUAP
    servidores_pgd_suap = SolicitacaoAdesaoServidor.get_servidores_em_pgd()
    # Servidores que não estão em PGD no SOU GOV
    servidores_nao_estao_em_pgd_sou_gov = Servidor.objects.vinculados().filter(participa_pgd=False)

    # Servidores que estão em PGD no SUAP mas não estão em PGD no SOU GOV
    lista_servidores = servidores_pgd_suap.filter(id__in=servidores_nao_estao_em_pgd_sou_gov.values_list('id', flat=True))
    lista_servidores = lista_servidores.order_by('pessoa_fisica__nome')

    if buscar_str:
        lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        lista_servidores = lista_servidores.filter(setor__in=setores)
    if uos:
        lista_servidores = lista_servidores.filter(setor__uo__in=uos)

    return lista_servidores


def get_servidores_em_pgd_no_sou_gov_mas_nao_no_suap(buscar_str=None, setores=None, uos=None):
    # Servidores em PGD no SOU GOV
    servidores_pgd_sougov = Servidor.objects.vinculados().filter(participa_pgd=True)
    # Servidores em PGD no SUAP
    servidores_pgd_suap = SolicitacaoAdesaoServidor.get_servidores_em_pgd()

    # Servidores que estão em PGD no SOU GOV mas não estão em PGD no SUAP
    lista_servidores = servidores_pgd_sougov.exclude(id__in=servidores_pgd_suap.values_list('id', flat=True))
    lista_servidores = lista_servidores.order_by('pessoa_fisica__nome')

    if buscar_str:
        lista_servidores = lista_servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        lista_servidores = lista_servidores.filter(setor__in=setores)
    if uos:
        lista_servidores = lista_servidores.filter(setor__uo__in=uos)

    return lista_servidores


def get_servidores_em_pgd_com_dados_diferentes_entre_sougov_suap(buscar_str=None, setores=None, uos=None):
    """
    PGD (ParticipantePgd)
    1 - Total de participantes registrados no Siape em regime presencial
    2 - Total de participantes registrados no Siape em regime teletrabalho parcial
    3 - Total de participantes registrados no Siape em regime teletrabalho integral
    4 - Total de participantes registrados no Siape em regime teletrabalho no exterior (art. 12, VIII)
    5 - Total de participantes registrados no Siape em regime teletrabalho no exterior (art. 12, §7°)

    SOU GOV
    - presencial
    - parcial
    - integral
    - no exterior
    """
    servidores_pgd_suap = (
        ParticipantePgd.objects.filter(situacao=1)
        .select_related('servidor', 'servidor__setor', 'servidor__cargo_emprego', 'servidor__modalidade_pgd')
        .order_by('servidor__pessoa_fisica__nome')
    )
    if buscar_str:
        servidores_pgd_suap = servidores_pgd_suap.filter(
            Q(servidor__pessoa_fisica__nome__icontains=buscar_str) | Q(servidor__matricula__icontains=buscar_str)
        )
    if setores:
        servidores_pgd_suap = servidores_pgd_suap.filter(servidor__setor__in=setores)
    if uos:
        servidores_pgd_suap = servidores_pgd_suap.filter(servidor__setor__uo__in=uos)
    lista_servidores_diferenca_modalidade = []
    for servidor_pgd_suap in servidores_pgd_suap:
        modalidade_sougov = servidor_pgd_suap.servidor.modalidade_pgd.nome.upper() if servidor_pgd_suap.servidor.modalidade_pgd else '-'
        modalidade_sougov_exibir = servidor_pgd_suap.servidor.modalidade_pgd.nome.capitalize() if servidor_pgd_suap.servidor.modalidade_pgd else '-'

        modalidade_suap_exibir = servidor_pgd_suap.get_modalidade_execucao_display()

        if (
            servidor_pgd_suap.situacao == 1
            and not servidor_pgd_suap.servidor.participa_pgd
            or servidor_pgd_suap.situacao == 0
            and servidor_pgd_suap.servidor.participa_pgd
        ):
            lista_servidores_diferenca_modalidade.append((servidor_pgd_suap, modalidade_suap_exibir, modalidade_sougov_exibir))
        else:
            if servidor_pgd_suap.modalidade_execucao == 1 and modalidade_sougov != 'PRESENCIAL':
                lista_servidores_diferenca_modalidade.append((servidor_pgd_suap, modalidade_suap_exibir, modalidade_sougov_exibir))
            if servidor_pgd_suap.modalidade_execucao == 2 and modalidade_sougov != 'PARCIAL':
                lista_servidores_diferenca_modalidade.append((servidor_pgd_suap, modalidade_suap_exibir, modalidade_sougov_exibir))
            if servidor_pgd_suap.modalidade_execucao == 3 and modalidade_sougov != 'INTEGRAL':
                lista_servidores_diferenca_modalidade.append((servidor_pgd_suap, modalidade_suap_exibir, modalidade_sougov_exibir))
            if servidor_pgd_suap.modalidade_execucao in [4, 5] and modalidade_sougov != 'NO EXTERIOR':
                lista_servidores_diferenca_modalidade.append((servidor_pgd_suap, modalidade_suap_exibir, modalidade_sougov_exibir))

    return lista_servidores_diferenca_modalidade


def get_servidores_inativos_em_pgd(buscar_str=None, setores=None, uos=None):
    # servidores = SolicitacaoAdesaoServidor.get_servidores_inativos_em_pgd()
    servidores = SolicitacaoAdesaoServidor.get_servidores_inativos_com_adesao_vigente()
    servidores = servidores.order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)

    return servidores


def get_servidores_desligados(buscar_str=None, setores=None, uos=None):
    servidores = SolicitacaoAdesaoServidor.get_servidores_desligados()
    servidores = servidores.filter(id__in=Servidor.objects.vinculados().values_list('id', flat=True))
    servidores = servidores.select_related('setor', 'cargo_emprego')
    servidores = servidores.order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)

    return servidores


# Comentado por em tese não fazser mais sentigo. verificar depois
"""
def get_servidores_em_pgd_sem_pit_homologado(buscar_str=None, setores=None, considerar_apenas_periodo_pit_atual=True):
    # Servidores em PGD e sem PIT homologado ao menos uma vez
    # EXCETO PITs CANCELADOS ATUALMENTE

    servidores = SolicitacaoAdesaoServidor.get_servidores_em_pgd()

    ids_servidores_com_pit_homologado = []
    if considerar_apenas_periodo_pit_atual:
        # Periodo atual (hoje ou ultimo cadastrado)
        periodo_pit_atual = PeriodoPitRit.objects.filter(
            cancelado=False, data_inicio__lte=get_datetime_now().date(), data_fim__gte=get_datetime_now().date()
        )
        if periodo_pit_atual:
            periodo_pit_atual = periodo_pit_atual.first()
        else:
            periodo_pit_atual = PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio').first()
        print('Periodo atual ', periodo_pit_atual)
        ids_servidores_com_pit_homologado = (
            PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
            .filter(periodo_pit_rit=periodo_pit_atual)
            .exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
            .distinct('adesao__servidor_id')
            .values_list('adesao__servidor_id', flat=True)
        )
    else:
        ids_servidores_com_pit_homologado = (
            PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
            .exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
            .distinct('adesao__servidor_id')
            .values_list('adesao__servidor_id', flat=True)
        )

    servidores = servidores.exclude(id__in=ids_servidores_com_pit_homologado)
    servidores = servidores.order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)

    return servidores
"""


def get_servidores_deveriam_mas_nao_tem_pit_homologado(buscar_str=None, setores=None, uos=None):
    servidores = MonitoramentoServidor.objects.filter(regra=MonitoramentoServidor.DEVERIAM_TER_PIT_ATUAL).values_list('servidor_id', flat=True)
    servidores = Servidor.objects.filter(id__in=servidores).order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)

    return servidores


def get_servidores_deveriam_mas_nao_tem_pit_homologado_ultimos_3_periodos(buscar_str=None, setores=None, uos=None):
    servidores = MonitoramentoServidor.objects.filter(regra=MonitoramentoServidor.DEVERIAM_TER_PIT_NOS_ULTIMOS_3_MESES).values_list(
        'servidor_id', flat=True
    )
    servidores = Servidor.objects.filter(id__in=servidores).order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)

    return servidores


def get_servidores_em_pgd_em_estagio_probratorio(ano_estagio_probratorio=1, buscar_str=None, setores=None, uos=None):
    """
    Sabendo quais servidores estão no primeiro/segundo ano de estágio probatório
    Retorna queryset de servidores que estão no ano (1 ou 2 ou 3) indicado de estágio probatório.
    """
    servidores_em_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd()

    # Filtros
    if buscar_str:
        servidores_em_pgd = servidores_em_pgd.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores_em_pgd = servidores_em_pgd.filter(setor__in=setores)
    if uos:
        servidores_em_pgd = servidores_em_pgd.filter(setor__uo__in=uos)
    ids_ultimo_pca_por_servidor = (
        PCA.objects.filter(servidor__in=servidores_em_pgd, forma_vacancia_pca__isnull=True)
        .order_by('servidor_id', '-id')
        .distinct('servidor_id')
        .values_list('id', flat=True)
    )

    pcas = (
        PCA.objects.filter(id__in=ids_ultimo_pca_por_servidor)
        .annotate(
            qtd_progressoes=Count(
                'posicionamentopca__id',
                filter=Q(posicionamentopca__forma_entrada__codigo=FormaProvimentoVacancia.CODIGO_PROGRESSAO),
            )
        )
        .filter(qtd_progressoes=ano_estagio_probratorio - 1)
        .select_related('servidor', 'forma_entrada_pca')
    )

    servidores = []
    for pca in pcas:
        servidores.append((pca.servidor, pca.forma_entrada_pca.codigo == FormaProvimentoVacancia.CODIGO_REDISTRIBUICAO))
    return sorted(servidores, key=lambda item: item[0].pessoa_fisica.nome)


def get_servidores_movimentados_com_menos_de_6_meses_de_instituto(buscar_str=None, setores=None, uos=None):
    # Sabendo quais servidores em PGD que foram movimentados tem menos de 6 meses de IFRN

    servidores_em_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd()

    # Filtros
    if buscar_str:
        servidores_em_pgd = servidores_em_pgd.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores_em_pgd = servidores_em_pgd.filter(setor__in=setores)
    if uos:
        servidores_em_pgd = servidores_em_pgd.filter(setor__uo__in=uos)

    ultimo_pca_por_servidor = (
        PCA.objects.filter(servidor__in=servidores_em_pgd, forma_vacancia_pca__isnull=True)
        .order_by('servidor_id', '-id')
        .distinct('servidor_id')
        .values_list('id', flat=True)
    )

    pcas_movimentacao = PCA.objects.filter(id__in=ultimo_pca_por_servidor).filter(
        forma_entrada_pca__codigo=FormaProvimentoVacancia.CODIGO_REDISTRIBUICAO,
        data_entrada_pca__gte=timezone.now().date() - relativedelta(months=6),
    )

    servidores = []
    for pca in pcas_movimentacao:
        servidores.append((pca.servidor, pca.data_entrada_pca))
    return sorted(servidores, key=lambda item: item[0].pessoa_fisica.nome)


def get_servidores_deveriam_mas_nao_tem_rit_homologado_nos_2_periodos_anteriores(buscar_str=None, setores=None, uos=None):
    servidores = MonitoramentoServidor.objects.filter(regra=MonitoramentoServidor.DEVERIAM_TER_RIT_NOS_2_PERIODOS_ANTERIORES).values_list(
        'servidor_id', flat=True
    )
    servidores = Servidor.objects.filter(id__in=servidores).order_by('pessoa_fisica__nome')

    # Filtros
    if buscar_str:
        servidores = servidores.filter(Q(pessoa_fisica__nome__icontains=buscar_str) | Q(matricula__icontains=buscar_str))
    if setores:
        servidores = servidores.filter(setor__in=setores)
    if uos:
        servidores = servidores.filter(setor__uo__in=uos)
    return servidores


# =================================================
# Gerar/alterar dados de monitoramento
# ================================================


def executar_desligamento_automatico_servidores():
    justificativa = get_justificativa_desligamento_automatico()
    if not justificativa:
        return False

    def cadastrar_desligamento(adesao, data_desligamento_efeitos_a_partir_de, observacao):
        if adesao.tem_desligamento_cadastrado:
            return
        justificativa = get_justificativa_desligamento_automatico()
        justificativa = JustificativaDesligamentoPgd.objects.get(id=justificativa)

        d = DesligamentoPgdServidor()
        d.adesao = adesao
        d.justificativa = justificativa
        d.observacao = f'Cadastrado automaticamente: {observacao}'
        d.data_desligamento_efeitos_a_partir_de = data_desligamento_efeitos_a_partir_de
        d.data_cadastro = get_datetime_now()
        d.save()

        # Se tem punicao de dias na justificativa
        if d.justificativa.qtd_dias_punicao > 0:
            carencia_nova_adesao_ate = d.data_desligamento_efeitos_a_partir_de + relativedelta(days=d.justificativa.qtd_dias_punicao)
            d.data_pode_solicitar_nova_adesao = carencia_nova_adesao_ate
            d.save()
            adesao.data_pode_solicitar_nova_adesao = d.data_pode_solicitar_nova_adesao

        # Cadastra deligamento no PIT
        adesao.data_desligamento_efeitos_a_partir_de = d.data_desligamento_efeitos_a_partir_de
        adesao.data_desligamento_carencia_ate = d.data_desligamento_efeitos_a_partir_de + relativedelta(
            days=PlanoIndividualTrabalho.CARENCIA_PARA_EDICAO_PIT_SEM_ADESAO_VIGENTE
        )
        adesao.save()

        # Calcula os PITs/RITs da adesao
        # Calcula os PITs não cancelados e sem RIT homologado
        pits_calcular = adesao.get_pits_todos().exclude(
            Q(situacao=PlanoIndividualTrabalho.CANCELADO) | Q(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT)
        )
        for pit in pits_calcular:
            pit.calcular_pit()

        ip = '127.0.0.1'
        ra_obs = f'O Desligamento do PGD da {adesao.__str__()} foi cadastrado automaticamente mediante seguinte justificativa "{justificativa}".'
        RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
            tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DESLIGAMENTO, solicitacao=adesao, ip=ip, observacao=ra_obs
        )

    def desligar_servidores_excluidos():
        # ======================================================
        # Selecão dos servidores para desligamento automático
        # ======================================================

        # Servidores que serão desligados por estarem excluidos como Servidor
        # - Servidores que estão em PGD
        ids_servidores_para_excluir_1 = list(get_servidores_inativos_em_pgd().values_list('id', flat=True))
        # - Servidores tem adesão mas não estão em PGD
        ids_servidores_para_excluir_2 = list(SolicitacaoAdesaoServidor.objects.filter(servidor__ativo=False).values_list('servidor_id', flat=True))
        ids_servidores = list(set(ids_servidores_para_excluir_1 + ids_servidores_para_excluir_2))

        # ======================================================

        """
        Para cada um dos servidores
        - Calcula a data de efeitos
        - Se tem algum PIT/RIT
            - A data será um dia após o fim deste PIT/RIT
        - Se não tem PIT
            - Será a data de hoje
        -Calcula a adesão que será desligada
        - Executa o desligamento
        """
        pits_homologados = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez().filter(situacao=PlanoIndividualTrabalho.CANCELADO)
        for id_servidor in ids_servidores:
            servidor = Servidor.objects.get(id=id_servidor)

            data_de_efeitos = None

            adesao = None
            ultimo_pit_homologado_do_servidor = pits_homologados.filter(adesao__servidor=servidor).order_by('-data_inicio').first()
            if ultimo_pit_homologado_do_servidor:
                adesao = ultimo_pit_homologado_do_servidor.adesao
                data_de_efeitos = ultimo_pit_homologado_do_servidor.data_fim + timedelta(1)
            else:
                adesao = SolicitacaoAdesaoServidor.objects.filter(servidor=servidor, situacao=SolicitacaoAdesaoServidor.DEFERIDO).first()
                data_de_efeitos = adesao.data_inicio + timedelta(1)

            cadastrar_desligamento(adesao, data_de_efeitos, 'servidor inativo no SUAP')

    def desligar_servidores_por_falta_de_interacao():
        qtd_dias = 90  # ultimos 3 periodos.

        # Lista os servidores que
        # - Tem adesão vigente a mais de qtd_dias
        # - Excluindo servidores que estão em PGD
        # - Que nao possuem pit cadcastrado (exceto cancelado)
        data_limite = get_datetime_now().date() - relativedelta(days=qtd_dias)
        servidores_em_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd()
        adesoes = SolicitacaoAdesaoServidor.get_adesoes_vigentes()
        adesoes = adesoes.filter(data_inicio__lt=data_limite)
        adesoes = adesoes.exclude(servidor__in=servidores_em_pgd)
        for adesao in adesoes:
            if adesao.get_pits().count() == 0:
                data_de_efeitos = adesao.data_inicio + timedelta(1)
                cadastrar_desligamento(adesao, data_de_efeitos, 'servidor com adesão vigente a mais de 90 dias e sem plano de trabalho cadastrado')

    def desligar_servidores_por_setor_desabilitado():
        if permite_habilitacao_dos_setores():
            servidores_em_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd()
            setores_habilitados = SetorHabilitacao.get_setores_habilitados()
            qtd_dias = 90  # ultimos 3 periodos. Antes de alterar observe a função monitoramento_servidores_deveriam_mas_nao_tem_pit_homologado_nos_ultimos_3_periodos

            # Lista os servidores que
            # - Tem adesão vigente a mais de qtd_dias
            # - São de setores não habilitados
            # - Excluindo servidores que estão PGD
            data_limite = get_datetime_now().date() - relativedelta(days=qtd_dias)
            adesoes = SolicitacaoAdesaoServidor.get_adesoes_vigentes()
            adesoes = adesoes.filter(data_inicio__lt=data_limite)
            adesoes = adesoes.exclude(servidor__setor__in=setores_habilitados)
            adesoes = adesoes.exclude(servidor__in=servidores_em_pgd)
            for adesao in adesoes:
                data_de_efeitos = adesao.data_inicio + timedelta(1)
                cadastrar_desligamento(adesao, data_de_efeitos, 'setor sem registro de habilitação no PGD')

    desligar_servidores_excluidos()
    desligar_servidores_por_falta_de_interacao()
    desligar_servidores_por_setor_desabilitado()


def gerar_dados_monitoramento_servidores():

    def monitoramento_servidores_deveriam_mas_nao_tem_pit_homologado_periodo_atual():
        # Servidores sem PIT homologado no período atual
        servidores_sem_pit_periodo_atual = get_servidores_adesao_vigente_sem_pit_relacionado(regra=3)

        # Verifica quais desses servidores efetivamente precisariam ter PIT homologado
        periodo_pit_atual = PeriodoPitRit.get_periodo_pit_atual()
        if periodo_pit_atual and utilizar_integracao_com_ponto():
            ids_servidores_com_ch_prevista_no_periodo_atual = []
            for serv in servidores_sem_pit_periodo_atual:
                if get_ch_prevista_servidor_periodo(serv, periodo_pit_atual.data_inicio, periodo_pit_atual.data_fim) > 0:
                    ids_servidores_com_ch_prevista_no_periodo_atual.append(serv.id)

            # inclui apenas os que não poderiam ficar sem PIT
            if ids_servidores_com_ch_prevista_no_periodo_atual:
                servidores_sem_pit_periodo_atual = servidores_sem_pit_periodo_atual.filter(id__in=ids_servidores_com_ch_prevista_no_periodo_atual)
            else:
                servidores_sem_pit_periodo_atual = Servidor.objects.none()

        # Salva dados
        MonitoramentoServidor.objects.filter(regra=MonitoramentoServidor.DEVERIAM_TER_PIT_ATUAL).delete()
        if servidores_sem_pit_periodo_atual:
            for servidor in servidores_sem_pit_periodo_atual:
                mon = MonitoramentoServidor()
                mon.servidor = servidor
                mon.regra = MonitoramentoServidor.DEVERIAM_TER_PIT_ATUAL
                mon.save()

    def monitoramento_servidores_deveriam_mas_nao_tem_pit_homologado_nos_ultimos_3_periodos2():
        # Monitoramento de servidores que deveriam ter PIT homologado em todos os ultimos 3 periodos

        # Seleciona os servidores que deveriam ter PIT homologado no período atual mas nao tem PIT homologado no período atual
        servidores_sem_pit_homologado = MonitoramentoServidor.objects.filter(regra=MonitoramentoServidor.DEVERIAM_TER_PIT_ATUAL)
        servidores_sem_pit_homologado = SolicitacaoAdesaoServidor.get_servidores_com_adesao_vigente().filter(
            id__in=servidores_sem_pit_homologado.values_list('servidor_id', flat=True)
        )

        periodos = PeriodoPitRit.get_periodo_pit_atual_e_periodos_anteriores(qtd_periodos_anteriores=2)
        if len(periodos) == 3:
            # Períodos a verificar
            periodo_anterior_1 = periodos[1]
            periodo_anterior_2 = periodos[2]

            # Parte do princípio que já deveria ter PIT homologado no período atual, então já está filtrado para os que não tem PIT homologado no período atual
            # Agora vamos saber se precisaria ter PIT homologado para cada um dos períodos anteriores, ou seja, se tem CH prevista para os períodos anteriores
            # Verifica se todos os servidores sem PIT homologado deveriam ter PIT homologado para cada um dos períodos anteriores

            ids_servidores_sem_ch_prevista = []

            # Verifica periodo_anterior_1
            servidores_sem_pit_homologado = servidores_sem_pit_homologado.exclude(
                id__in=(
                    PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
                    .filter(periodo_pit_rit=periodo_anterior_1)
                    .values_list('adesao__servidor_id', flat=True)
                )
            )
            if servidores_sem_pit_homologado and utilizar_integracao_com_ponto():
                for servidor in servidores_sem_pit_homologado:
                    if get_ch_prevista_servidor_periodo(servidor, periodo_anterior_1.data_inicio, periodo_anterior_1.data_fim) == 0:
                        ids_servidores_sem_ch_prevista.append(servidor.id)
                servidores_sem_pit_homologado = servidores_sem_pit_homologado.exclude(id__in=ids_servidores_sem_ch_prevista)

            # Verifica periodo_anterior_2
            servidores_sem_pit_homologado = servidores_sem_pit_homologado.exclude(
                id__in=(
                    PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
                    .filter(periodo_pit_rit=periodo_anterior_2)
                    .values_list('adesao__servidor_id', flat=True)
                )
            )
            if servidores_sem_pit_homologado and utilizar_integracao_com_ponto():
                for servidor in servidores_sem_pit_homologado:
                    if get_ch_prevista_servidor_periodo(servidor, periodo_anterior_2.data_inicio, periodo_anterior_2.data_fim) == 0:
                        ids_servidores_sem_ch_prevista.append(servidor.id)
                servidores_sem_pit_homologado = servidores_sem_pit_homologado.exclude(id__in=ids_servidores_sem_ch_prevista)

            # Salva os dados
            MonitoramentoServidor.objects.filter(regra=MonitoramentoServidor.DEVERIAM_TER_PIT_NOS_ULTIMOS_3_MESES).delete()
            if servidores_sem_pit_homologado:
                for servidor in servidores_sem_pit_homologado:
                    mon = MonitoramentoServidor()
                    mon.servidor = servidor
                    mon.regra = MonitoramentoServidor.DEVERIAM_TER_PIT_NOS_ULTIMOS_3_MESES
                    mon.save()

    def monitoramento_servidores_deveriam_mas_nao_tem_rit_homologado_nos_2_periodos_anteriores():
        # ------------------------------------
        # Sevidores que deveriam ter RIT homologado para os dois períodos anteriores, mas não tem RIT homologado
        # ------------------------------------

        # Se tiver PIT homologado OU
        # Se precisava ter PIT homologado mas não tem
        def servidor_precisa_ter_rit_homologado_no_periodo(servidor, periodo):
            if (
                PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
                .filter(periodo_pit_rit=periodo, adesao__servidor=servidor)
                .exists()
            ):
                return True
            return get_ch_prevista_servidor_periodo(servidor, periodo.data_inicio, periodo.data_fim) > 0

        # Se tem RIT homologado
        def servidor_tem_rit_homologado_no_periodo(adesao, periodo):
            return PlanoIndividualTrabalho.get_rits_homologados(adesao=adesao).filter(periodo_pit_rit=periodo).exists()

        adesoes_vigentes = SolicitacaoAdesaoServidor.get_adesoes_vigentes()

        # Sobre a necessidade de RIT no período
        # Precisa ter RIT se:
        # - Se tiver PIT homologado OU
        # - Se precisava ter PIT homologado mas não tem

        periodo_anterior_1 = None
        periodo_anterior_2 = None
        periodos = PeriodoPitRit.get_periodo_pit_atual_e_periodos_anteriores(qtd_periodos_anteriores=2)
        if len(periodos) == 3:
            periodo_anterior_1 = periodos[1]
            periodo_anterior_2 = periodos[2]

        if periodo_anterior_1 and periodo_anterior_2:
            # Verifica periodo_anterior_1
            ids_adesoes_sem_rit_homologado_no_periodo1 = []
            for adesao in adesoes_vigentes:
                if servidor_precisa_ter_rit_homologado_no_periodo(adesao.servidor, periodo_anterior_1):
                    if not servidor_tem_rit_homologado_no_periodo(adesao, periodo_anterior_1):
                        ids_adesoes_sem_rit_homologado_no_periodo1.append(adesao.id)
            adesoes_vigentes = adesoes_vigentes.filter(id__in=ids_adesoes_sem_rit_homologado_no_periodo1)

            # Verifica periodo_anterior_1
            ids_adesoes_sem_rit_homologado_no_periodo2 = []
            for adesao in adesoes_vigentes:
                if servidor_precisa_ter_rit_homologado_no_periodo(adesao.servidor, periodo_anterior_2):
                    if not servidor_tem_rit_homologado_no_periodo(adesao, periodo_anterior_2):
                        ids_adesoes_sem_rit_homologado_no_periodo2.append(adesao.id)
            adesoes_vigentes = adesoes_vigentes.filter(id__in=ids_adesoes_sem_rit_homologado_no_periodo2)

        # Salva dados
        MonitoramentoServidor.objects.filter(regra=MonitoramentoServidor.DEVERIAM_TER_RIT_NOS_2_PERIODOS_ANTERIORES).delete()
        if adesoes_vigentes:
            for adesao in adesoes_vigentes:
                mon = MonitoramentoServidor()
                mon.servidor = adesao.servidor
                mon.regra = MonitoramentoServidor.DEVERIAM_TER_RIT_NOS_2_PERIODOS_ANTERIORES
                mon.save()

    monitoramento_servidores_deveriam_mas_nao_tem_pit_homologado_periodo_atual()
    monitoramento_servidores_deveriam_mas_nao_tem_pit_homologado_nos_ultimos_3_periodos2()
    monitoramento_servidores_deveriam_mas_nao_tem_rit_homologado_nos_2_periodos_anteriores()


def executar_monitoramento():
    executar_desligamento_automatico_servidores()
    gerar_dados_monitoramento_servidores()
