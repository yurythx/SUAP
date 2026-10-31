import tqdm
from django.conf import settings
from django.urls import reverse

from djtools.utils import send_notification
from pgd2.models import ComissaoPGD, PlanoEntregasSetorial, SolicitacaoAdesaoServidor
from pgd2.monitoramento import (
    get_pess_aptos_para_analise_execucao,
    get_pess_aptos_para_avaliacao_execucao,
    get_pess_inconsistentes_aprovacao,
    get_servidores_adesao_vigente_sem_pit_relacionado,
    get_servidores_deveriam_mas_nao_tem_pit_homologado,
    get_servidores_deveriam_mas_nao_tem_pit_homologado_ultimos_3_periodos,
    get_servidores_em_pgd_em_estagio_probratorio,
    get_servidores_em_pgd_no_sou_gov_mas_nao_no_suap,
    get_servidores_movimentados_com_menos_de_6_meses_de_instituto,
)
from pgd2.pendencias_alertas import existe_pendencias_chefe_para_notificar, existe_pendencias_servidor_para_notificar
from rh.models import Funcao, Servidor, ServidorFuncaoHistorico, Setor
from suap import nomenclatura

# --------------------------------------------
# Notificações diárias
# --------------------------------------------


def notificar(vinculos, chefe=True):
    url = f'{settings.SITE_URL}/pgd2/pendencias_avisos_pgd/'
    titulo = '[SUAP] PGD: Pendências de chefia' if chefe else '[SUAP] PGD: Pendências do servidor'
    texto = []
    texto.append('<h1>PGD</h1>')
    if chefe:
        texto.append('<h2>Há pendências de chefia no PGD que precisam da sua análise.</h2>')
    else:
        texto.append('<h2>Há pendências no seu PGD que precisam ser resolvidas.</h2>')
    texto.append(f'<p class="more-info">Consulte os itens e veja como resolvê-los na tela <a href="{url}">Pendências no PGD</a>.</p>')
    send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos)


def notificar_chefes():
    # Setores PGD
    ids_setores_pes_aprovado = PlanoEntregasSetorial.objects.filter(situacao=PlanoEntregasSetorial.APROVADO).values('setor_id')
    setores_pgd = Setor.objects.suap_ativos().filter(id__in=ids_setores_pes_aprovado)
    for setor in tqdm.tqdm(setores_pgd):
        chefes_atuais = Servidor.objects.ativos().filter(
            pk__in=ServidorFuncaoHistorico.objects.atuais()
            .filter(setor_suap=setor, funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
            .values_list('servidor', flat=True)
            .distinct()
        )
        primeiro_chefe = chefes_atuais.first()
        if primeiro_chefe:
            if existe_pendencias_chefe_para_notificar(primeiro_chefe.get_user()):
                vinculos_chefe = [chefe.get_vinculo() for chefe in chefes_atuais]
                notificar(vinculos_chefe, chefe=True)


def notificar_servidores():
    adesoes_vigentes = SolicitacaoAdesaoServidor.get_adesoes_vigentes()
    servidores_pgd = Servidor.objects.vinculados().filter(id__in=adesoes_vigentes.values('servidor_id'))
    for servidor in tqdm.tqdm(servidores_pgd):
        if existe_pendencias_servidor_para_notificar(servidor.get_user()):
            notificar([servidor.get_vinculo()], chefe=False)


def notificar_gestao_pgd():
    def notificar_gestao(notificacoes):
        if notificacoes:
            titulo = '[SUAP] PGD: Pendências de análise pela Gestão PGD'
            texto = []
            texto.append('<h1>PGD: Pendências de análise pela Gestão PGD</h1>')
            texto.append('<h2>Situações pendentes de análise pela Gestão do PGD</h2>')
            texto.append('<ul>')
            for notificacao in notificacoes:
                texto.append(
                    f'<li>{notificacao["titulo"]}. Acesse: <a href="{settings.SITE_URL}{notificacao["url"]}">{settings.SITE_URL}{notificacao["url"]}</a></li>'
                )
            texto.append('</ul>')

            membros = ComissaoPGD.get_vigentes().filter(eh_sistemica=True).first().membros.all()

            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, membros)

    # ----------------------------------
    # Notifica as seguintes regras da view pgd2/monitoramento_servidores/
    # ----------------------------------

    notificacoes = []

    # AGRUPAMENTO_SERVIDORES_EM_PGD_NO_SOUGOV_MAS_NAO_NO_SUAP = 4
    lista_servidores = get_servidores_em_pgd_no_sou_gov_mas_nao_no_suap()
    if lista_servidores:
        notificacao = {'titulo': 'Servidores em PGD no SOUGOV mas não no SUAP', 'url': f'{reverse("monitoramento_servidores")}?regra=4'}
        notificacoes.append(notificacao)

    # AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_RELACIONADO = 6
    lista_servidores = get_servidores_adesao_vigente_sem_pit_relacionado(regra=1)
    if lista_servidores:
        notificacao = {
            'titulo': f'Servidores com adesão vigente e sem qualquer {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionado (exceto cancelados)',
            'url': f'{reverse("monitoramento_servidores")}?regra=6',
        }
        notificacoes.append(notificacao)

    # AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_HOMOLOGADO = 7
    lista_servidores = get_servidores_adesao_vigente_sem_pit_relacionado(regra=2)
    if lista_servidores:
        notificacao = {
            'titulo': f'Servidores com adesão vigente e sem {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionado homologado ao menos uma vez (exceto cancelados)',
            'url': f'{reverse("monitoramento_servidores")}?regra=7',
        }
        notificacoes.append(notificacao)

    # AGRUPAMENTO_SERVIDORES_COM_ADESAO_VIGENTE_SEM_PIT_HOMOLOGADO_PERIODO_ATUAL = 8
    lista_servidores = get_servidores_adesao_vigente_sem_pit_relacionado(regra=3)
    if lista_servidores:
        notificacao = {
            'titulo': f'Servidores com adesão vigente e sem {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionado homologado ao menos uma vez no período atual (exceto cancelados)',
            'url': f'{reverse("monitoramento_servidores")}?regra=8',
        }
        notificacoes.append(notificacao)

    # REGRA_SERVIDOR_DEVERIA_TER_PIT = 9
    lista_servidores = get_servidores_deveriam_mas_nao_tem_pit_homologado()
    if lista_servidores:
        notificacao = {
            'titulo': 'Servidores com adesão vigente que deveriam ter plano de trabalho (exceto cancelados) homologado no período atual, mas não possuem',
            'url': f'{reverse("monitoramento_servidores")}?regra=9',
        }
        notificacoes.append(notificacao)

    # REGRA_SERVIDOR_DEVERIA_TER_PIT_ULTIMOS_3_PERIODOS = 10
    lista_servidores = get_servidores_deveriam_mas_nao_tem_pit_homologado_ultimos_3_periodos()
    if lista_servidores:
        notificacao = {
            'titulo': 'Servidores com adesão vigente que deveriam ter plano de trabalho homologado em cada um dos últimos 3 períodos (incluindo o período atual), mas não possuem',
            'url': f'{reverse("monitoramento_servidores")}?regra=10',
        }
        notificacoes.append(notificacao)

    # REGRA_SERVIDORES_NO_PRIMEIRO_ANO_ESTAGIO_PROBATORIO = 11
    lista_servidores = get_servidores_em_pgd_em_estagio_probratorio(ano_estagio_probratorio=1)
    if lista_servidores:
        notificacao = {
            'titulo': 'Servidores em PGD que estão cumprindo o primeiro ano de estágio probatório',
            'url': f'{reverse("monitoramento_servidores")}?regra=11',
        }
        notificacoes.append(notificacao)

    # REGRA_SERVIDORES_NO_PRIMEIRO_SEGUNDO_ESTAGIO_PROBATORIO = 12
    lista_servidores = get_servidores_em_pgd_em_estagio_probratorio(ano_estagio_probratorio=2)
    if lista_servidores:
        notificacao = {
            'titulo': 'Servidores em PGD que estão cumprindo o segundo ano de estágio probatório',
            'url': f'{reverse("monitoramento_servidores")}?regra=12',
        }
        notificacoes.append(notificacao)

    # REGRA_SERVIDORES_NO_PRIMEIRO_TERCEIRO_ESTAGIO_PROBATORIO = 13
    lista_servidores = get_servidores_em_pgd_em_estagio_probratorio(ano_estagio_probratorio=3)
    if lista_servidores:
        notificacao = {
            'titulo': 'Servidores em PGD que estão cumprindo o terceiro ano de estágio probatório',
            'url': f'{reverse("monitoramento_servidores")}?regra=13',
        }
        notificacoes.append(notificacao)

    # REGRA_SERVIDORES_MOVIMENTADOS_COM_MENOS_DE_6_MESES_DE_INSTITUTO = 14
    lista_servidores = get_servidores_movimentados_com_menos_de_6_meses_de_instituto()
    if lista_servidores:
        notificacao = {
            'titulo': 'Servidores movimentados com menos de 6 meses de instituto',
            'url': f'{reverse("monitoramento_servidores")}?regra=14',
        }
        notificacoes.append(notificacao)

    # ----------------------------------
    # Notifica as seguintes regras da view pgd2/monitoramento_pes/
    # ----------------------------------
    # REGRA_INCONSISTENCIA_ENVIO_APROVACAO = 1
    lista_pess = get_pess_inconsistentes_aprovacao(tipo=1)
    if lista_pess:
        notificacao = {
            'titulo': 'PESs cadastrados, mas que ainda não foram enviados para aprovação',
            'url': f'{reverse("monitoramento_pes")}?regra=1',
        }
        notificacoes.append(notificacao)

    # REGRA_INCONSISTENCIA_APROVACAO = 2
    lista_pess = get_pess_inconsistentes_aprovacao(tipo=2)
    if lista_pess:
        notificacao = {
            'titulo': 'PESs cadastrados, enviados para aprovação, mas que ainda não foram aprovados',
            'url': f'{reverse("monitoramento_pes")}?regra=2',
        }
        notificacoes.append(notificacao)

    # REGRA_INCONSISTENCIA_ANALISE_EXECUCAO = 3
    lista_pess = get_pess_aptos_para_analise_execucao()
    if lista_pess:
        notificacao = {
            'titulo': 'PESs aptos para análise da execução, mas que ainda não foram analisados',
            'url': f'{reverse("monitoramento_pes")}?regra=3',
        }
        notificacoes.append(notificacao)

    # REGRA_INCONSISTENCIA_AVALIACAO_EXCUCAO = 4
    lista_pess = get_pess_aptos_para_avaliacao_execucao()
    if lista_pess:
        notificacao = {
            'titulo': 'PESs aptos para avaliação da execução, mas que ainda não foram avaliados',
            'url': f'{reverse("monitoramento_pes")}?regra=4',
        }
        notificacoes.append(notificacao)

    # Prepara o envio
    notificar_gestao(notificacoes)


# --------------------------------------------
# Notificações de operações
# --------------------------------------------


def notificar_operacao_pgd(vinculo, assunto, texto):
    assunto = f'[SUAP] PGD - {assunto}'
    send_notification(assunto, texto, settings.DEFAULT_FROM_EMAIL, [vinculo])


def notificar_homologacao_pit(pit):
    vinculo = pit.adesao.servidor.get_vinculo()
    assunto = f'Homologação de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'
    url = reverse('visualizar_pit_pgd2', args=[pit.id])
    texto = f"""
            <h1>Homologação de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}</h1>
            <p>{pit.get_verbose_pit_notificacao()} foi homologado.</p>
            <p class="more-info">Para mais informações, acesse: <a href="{url}">{pit.get_verbose_pit_notificacao()}</a>.</p>
    """
    notificar_operacao_pgd(vinculo, assunto, texto)


def notificar_nao_homologacao_pit(pit):
    vinculo = pit.adesao.servidor.get_vinculo()
    assunto = f'Não homologação de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'
    url = reverse('visualizar_pit_pgd2', args=[pit.id])
    texto = f"""
            <h1>Não homologação de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}</h1>
            <p>{pit.get_verbose_pit_notificacao()} não foi homologado.</p>
            <p class="more-info">Para mais informações, acesse: <a href="{url}">{pit.get_verbose_pit_notificacao()}</a>.</p>
    """
    notificar_operacao_pgd(vinculo, assunto, texto)


def notificar_homologacao_rit(pit):
    vinculo = pit.adesao.servidor.get_vinculo()
    assunto = f'Homologação de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
    url = reverse('visualizar_rit_pgd2', args=[pit.id])
    texto = f"""
            <h1>Homologação de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}</h1>
            <p>{pit.get_verbose_pit_notificacao()} foi homologado.</p>
            <p class="more-info">Para mais informações, acesse: <a href="{url}">{pit.get_verbose_pit_notificacao()}</a>.</p>
    """
    notificar_operacao_pgd(vinculo, assunto, texto)


def notificar_nao_homologacao_rit(pit):
    vinculo = pit.adesao.servidor.get_vinculo()
    assunto = f'Não homologação de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
    url = reverse('visualizar_rit_pgd2', args=[pit.id])
    texto = f"""
            <h1>Não homologação de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}</h1>
            <p>{pit.get_verbose_pit_notificacao()} não foi homologado.</p>
            <p class="more-info">Para mais informações, acesse: <a href="{url}">{pit.get_verbose_pit_notificacao()}</a>.</p>
    """
    notificar_operacao_pgd(vinculo, assunto, texto)


def notificar_reabrir_rit(pit):
    vinculo = pit.adesao.servidor.get_vinculo()
    assunto = f'Reabertura de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
    url = reverse('visualizar_rit_pgd2', args=[pit.id])
    texto = f"""
            <h1>Reabertura de {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}</h1>
            <p>{pit.get_verbose_pit_notificacao()} foi reaberto.</p>
            <p class="more-info">Para mais informações, acesse: <a href="{url}">{pit.get_verbose_pit_notificacao()}</a>.</p>
    """
    notificar_operacao_pgd(vinculo, assunto, texto)


# --------------------------------------------
# Envio das notificacoes
# --------------------------------------------


def enviar_notificacoes_pgd():
    notificar_chefes()
    notificar_servidores()
    notificar_gestao_pgd()
