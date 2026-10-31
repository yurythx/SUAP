from suap import nomenclatura
from pgd2.utils import get_pgd_sou_gov, get_datetime_now, get_servidores_setores_sou_chefe_direto
from rh.models import Servidor
from django.db.models import Q
from functools import reduce
import operator


def get_pendencia_geral_servidor_pgd(servidor, msgs_para_chefe=False, pit_especifico=None):
    from pgd2.models import (
        PlanoIndividualTrabalho,
        SolicitacaoAdesaoServidor,
    )

    # Sempre busca as pendências NA DATA DE HOJE
    dados_pgd_sou_gov = get_pgd_sou_gov(servidor.pessoa_fisica.cpf, servidor.matricula)
    if dados_pgd_sou_gov[0] != 'erro':
        dados_pgd_suap = pit_especifico or PlanoIndividualTrabalho.get_pit_na_data(servidor, get_datetime_now().date())
        if dados_pgd_suap:
            # Para casos de quem já tem ao menos 1 PIT homologado
            # Para casos de quem está iniciando agora
            em_pgd_hoje_suap = SolicitacaoAdesaoServidor.estah_no_pgd_hoje(servidor)[0] or SolicitacaoAdesaoServidor.tem_adesao_vigente(
                servidor.get_user()
            )

            msg_pit = f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2} {dados_pgd_suap.get_verbose_periodo()}'

            msg1 = 'Solicite a sua chefia a atualização dos seus dados, caso haja divergências. '
            msg2 = f'Ajuste o seu {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} do período atual ou solicite a sua chefia a atualização dos seus dados no SOU GOV, caso haja divergências.'
            msg3 = 'Realize o cadastro no SUAP ou se desligue do PGD.'
            msg4 = 'Solicite a gestão de pessoas a atualização dos seus dados no SIAPE/SUAP ou solicite a sua chefia a atualização dos seus dados no SOU GOV, caso haja divergências.'
            msg5 = 'Solicite a gestão de pessoas a atualização dos seus dados no SIAPE.'
            if msgs_para_chefe:
                msg1 = f'Atualize os dados no SOU GOV ou solicite ao servidor para ajustar o referido {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}, caso haja divergências.'
                msg2 = f'Atualize os dados no SOU GOV ou solicite ao servidor para ajustar o referido {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}, caso haja divergências.'
                msg3 = f'O servidor deve realizar o cadastro do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} no SUAP ou servidor deve ser desligado do PGD.'
                msg4 = 'Solicite a gestão de pessoas a atualização dos dados no SIAPE/SUAP ou atualize os dados no SOU GOV, caso haja divergências.'
                msg5 = 'Solicite a gestão de pessoas a atualização dos seus dados no SIAPE.'

            # Não está no PGD no SUAP
            if not em_pgd_hoje_suap and dados_pgd_sou_gov[0] == 'sim':
                return f'Considerando {msg_pit}. No SUAP, o servidor não está em PGD, porém, no SouGov, consta como estando em PGD. {msg1}'

            # Servidor em PGD no SUAP mas não está no SOU GOV
            if em_pgd_hoje_suap and dados_pgd_sou_gov[0] == 'não':
                return f'Considerando {msg_pit}. No SUAP, o servidor está em PGD, porém, no SouGov, consta como não estando em PGD. {msg1}'

            if em_pgd_hoje_suap and dados_pgd_sou_gov[0] == 'sim':
                # Se não tem PIT atual
                if not dados_pgd_suap:
                    return f'Considerando {msg_pit}. No SUAP e no SOU GOV o servidor está em PGD, porém, não existe {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} homologado para o período atual. {msg3}'

                if dados_pgd_suap:
                    # Se regime/modalidade são diferentes
                    # - No SIAPE está Exterior mas no SUAP está outra
                    if dados_pgd_sou_gov[1] == 'no exterior' and dados_pgd_suap.get_modalidade_execucao_para_api() in [1, 2, 3]:
                        return f'Considerando {msg_pit}. No SOU GOV o servidor está em PGD no exterior, porém, no SUAP aparentemente não existem dados do SIAPE específicos de PGD EXTERIOR. {msg5}'
                    # - Presencial
                    if dados_pgd_suap.get_modalidade_execucao_para_api() == 1 and not dados_pgd_sou_gov[1] == 'presencial':  # NOQA
                        return f'Considerando {msg_pit}. No SUAP e no SOU GOV o servidor está em PGD, porém, no SUAP consta na modalidade/regime PRESENCIAL e no SOU GOV consta {dados_pgd_sou_gov[1].upper()}. {msg2}'
                    # - Parcial
                    if dados_pgd_suap.get_modalidade_execucao_para_api() == 2 and not dados_pgd_sou_gov[1] == 'parcial':  # NOQA
                        return f'Considerando {msg_pit}. No SUAP e no SOU GOV o servidor está em PGD, porém, no SUAP consta na modalidade/regime PARCIAL e no SOU GOV consta {dados_pgd_sou_gov[1].upper()}. {msg2}'
                    # - Integral
                    if dados_pgd_suap.get_modalidade_execucao_para_api() == 3 and not dados_pgd_sou_gov[1] == 'integral':  # NOQA
                        return f'Considerando {msg_pit}. No SUAP e no SOU GOV o servidor está em PGD, porém, no SUAP consta na modalidade/regime INTEGRAL e no SOU GOV consta {dados_pgd_sou_gov[1].upper()}. {msg2}'
                    # - Exterior
                    if dados_pgd_suap.get_modalidade_execucao_para_api() in [4, 5] and not (
                        dados_pgd_suap.regime_execucacao == dados_pgd_suap.TRABALHO_TELETRABALHO_INTEGRAL and dados_pgd_sou_gov[1] == 'no exterior'
                    ):
                        return f'Considerando {msg_pit}. No SUAP e no SOU GOV o servidor está em PGD, porém, no SUAP consta na modalidade/regime NO EXTERIOR (conforme cadastros de afastamentos informados pela Gestão de Pessoas) e no SOU GOV consta {dados_pgd_sou_gov[1].upper()}. Para que o servidor esteja em PGD exterior no SUAP é necessário o cadastro do afastamento pela gestão de pessoas (aparentemente já existe) e o servidor deve ter informado "Teletrabalho integral". {msg4}'

    return False


def get_pendencias_chefe_sou_gov(user):
    from pgd2.models import SolicitacaoAdesaoServidor, PlanoIndividualTrabalho, PlanoIndividualTrabalhoCopia

    lista_pendencias = []

    if user.eh_servidor:
        setores, servidores, setores_hoje = get_servidores_setores_sou_chefe_direto(user)

        if setores:
            lista_servidores = Servidor.objects.vinculados().filter(id__in=SolicitacaoAdesaoServidor.objects.all().values('servidor_id'))
            querys = []
            querys.append(Q(setor__in=setores))
            if servidores and setores_hoje:
                querys.append(Q(id__in=servidores.values('id')) & Q(setor__in=setores_hoje))
            lista_servidores = lista_servidores.filter(reduce(operator.or_, querys))

            for serv in lista_servidores:
                pit_atual = PlanoIndividualTrabalho.get_pit_na_data(serv, get_datetime_now().date(), permite_pit_aguardando_parecer=True)
                if pit_atual:
                    pit_copia = PlanoIndividualTrabalhoCopia.objects.filter(original=pit_atual).first()
                    pit_teste = pit_atual
                    if pit_copia:
                        pit_teste.regime_execucacao = pit_copia.regime_execucacao
                        pit_teste.percentual_teletrabalho = pit_copia.percentual_teletrabalho
                    pendencia_geral = get_pendencia_geral_servidor_pgd(serv, msgs_para_chefe=True, pit_especifico=pit_teste)
                    if pendencia_geral:
                        pend_dict = {}
                        pend_dict['msg'] = f'Para o(a) servidor(a) {serv}. {pendencia_geral}'
                        pend_dict['url'] = '#'
                        lista_pendencias.append(pend_dict)

    return lista_pendencias


def get_pendencias_chefe(user, verifica_sou_gov=True, apenas_verificar_existe_pendencias=False):
    """
    Alertas de views.index_atribuidos_a_mim

    Chefe
    - Se tem SOL ADESÃO PGD pra deferir
    - Se tem SOL ADESÃO PES pra deferir
    - Se tem RIT pra homologar/aprovar
    - Se tem PIT pra homologar/aprovar
    - Se tem PES para aprovar
    - Se tem PES para analisar execução
    - Se tem PES para avaliar execução
    """

    from pgd2.models import (
        PlanoEntregasSetorial,
        PlanoIndividualTrabalho,
        RelatorioIndividualTrabalhoQuestionario,
        SolicitacaoAdesaoPesServidor,
        SolicitacaoAdesaoServidor,
    )

    lista_pendencias = []

    if verifica_sou_gov:
        lista_pendencias_sou_gov = get_pendencias_chefe_sou_gov(user)
        if lista_pendencias_sou_gov:
            if apenas_verificar_existe_pendencias:
                return True
            for lp in lista_pendencias_sou_gov:
                pend_dict = {}
                pend_dict['msg'] = lp.get('msg')
                pend_dict['url'] = '#'
                lista_pendencias.append(pend_dict)

    if SolicitacaoAdesaoServidor.get_solicitacoes_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=True).exists():
        if apenas_verificar_existe_pendencias:
            return True
        pend_dict = {}
        pend_dict['msg'] = 'Solicitação(ões) de adesão ao PGD'
        pend_dict['url'] = '/admin/pgd2/solicitacaoadesaoservidor/'
        lista_pendencias.append(pend_dict)

    if SolicitacaoAdesaoPesServidor.get_solicitacoes_pendendentes_avaliacao_chefe(user).exists():
        if apenas_verificar_existe_pendencias:
            return True
        pend_dict = {}
        pend_dict['msg'] = 'Solicitação(ões) de adesão a PES'
        pend_dict['url'] = '/admin/pgd2/solicitacaoadesaopesservidor/'
        lista_pendencias.append(pend_dict)

    listapes_aprova = PlanoEntregasSetorial.get_pess_pendendentes_aprovacao(user)
    if listapes_aprova.exists():
        if apenas_verificar_existe_pendencias:
            return True
        pend_dict = {}
        pend_dict['msg'] = 'Aprovação de PESs'
        pend_dict['url'] = '/admin/pgd2/planoentregassetorialaprovacao/'
        lista_pendencias.append(pend_dict)

    # pendente de análise da execução do PES
    listapes_analise_execucacao_pes = PlanoEntregasSetorial.get_pess_pendendentes_analise_execucao(user=user, apenas_chefe_direto=True)
    if listapes_analise_execucacao_pes.exists():
        if apenas_verificar_existe_pendencias:
            return True
        pend_dict = {}
        pend_dict['msg'] = 'Análise da Execução de PESs'
        pend_dict['url'] = '/pgd2/listar_pes_chefe_deve_analisar/'
        lista_pendencias.append(pend_dict)

    # pendente de avaliação da execução do PES
    listapes_avaliacao_execucacao_pes = PlanoEntregasSetorial.get_pess_pendendentes_avaliacao(user=user)
    if listapes_avaliacao_execucacao_pes.exists():
        if apenas_verificar_existe_pendencias:
            return True
        pend_dict = {}
        pend_dict['msg'] = 'Avaliação da Execução de PESs'
        pend_dict['url'] = '/pgd2/listar_pes_chefe_deve_avaliar/'
        lista_pendencias.append(pend_dict)

    lista_pits_aprova, lista_pits_homologacao = PlanoIndividualTrabalho.get_pits_pendendentes_avaliacao_chefe_direto(user)
    if lista_pits_aprova.exists() or lista_pits_homologacao.exists():
        if apenas_verificar_existe_pendencias:
            return True
        pend_dict = {}
        pend_dict['msg'] = f'Análise de {nomenclatura.plano_individual_de_trabalho_sigla_plural_pgd2}'
        pend_dict['url'] = '/pgd2/listar_pits_chefe_deve_pode_aprova_homologa/'
        lista_pendencias.append(pend_dict)

    lista_pits_aprova, lista_pits_homologacao = PlanoIndividualTrabalho.get_rits_pendendentes_avaliacao_chefe_direto(user)
    if lista_pits_aprova.exists() or lista_pits_homologacao.exists():
        if apenas_verificar_existe_pendencias:
            return True
        pend_dict = {}
        pend_dict['msg'] = f'Análise de {nomenclatura.relatorio_individual_de_trabalho_sigla_plural_pgd2}'
        pend_dict['url'] = '/pgd2/listar_rits_chefe_deve_pode_aprova_homologa/'
        lista_pendencias.append(pend_dict)

    lista_setor_periodo_a_preencher, _ = RelatorioIndividualTrabalhoQuestionario.questionarios_a_responder_como_chefe(user.get_relacionamento())
    if lista_setor_periodo_a_preencher:
        if apenas_verificar_existe_pendencias:
            return True
        pend_dict = {}
        pend_dict['msg'] = 'Questionários de pesquisa de PGD que devem ser preenchidos'
        pend_dict['url'] = '/pgd2/listar_questionarios_chefe_deve_responder/'
        lista_pendencias.append(pend_dict)

    if apenas_verificar_existe_pendencias and not lista_pendencias:
        return False
    return lista_pendencias


def existe_pendencias_chefe_para_notificar(user):
    return get_pendencias_chefe(user, verifica_sou_gov=False, apenas_verificar_existe_pendencias=True)


def get_pendencias_servidor(user, verifica_sou_gov=True, apenas_lista_separada=True, apenas_verificar_existe_pendencias=False):
    """
    Alertas de views.index_atribuidos_a_mim

    Servidor
    - Entrega do PIT pelo servidor para avaliação
    - Entrega do RIT pelo servidor para avaliação

    apenas_lista_separada
    - se True retorna apenas uma lista sem os links

    """
    from pgd2.models import PlanoIndividualTrabalho, PlanoIndividualTrabalhoCopia

    lista_pendencias = []
    lista_pendencias_pit = []
    lista_pendencias_rit = []

    if verifica_sou_gov:
        pit_atual = PlanoIndividualTrabalho.get_pit_na_data(user.get_relacionamento(), get_datetime_now().date(), permite_pit_aguardando_parecer=True)
        pit_copia = PlanoIndividualTrabalhoCopia.objects.filter(original=pit_atual).first()
        pit_teste = pit_atual
        if pit_copia:
            pit_teste.regime_execucacao = pit_copia.regime_execucacao
            pit_teste.percentual_teletrabalho = pit_copia.percentual_teletrabalho
        pendencia_geral = get_pendencia_geral_servidor_pgd(user.get_relacionamento(), msgs_para_chefe=False, pit_especifico=pit_teste)
        if pendencia_geral:
            if apenas_verificar_existe_pendencias:
                return True
            if not apenas_lista_separada:
                pend_dict = {}
                pend_dict['msg'] = pendencia_geral
                pend_dict['url'] = '#'
                lista_pendencias.append(pend_dict)

    pits_pendentes = PlanoIndividualTrabalho.get_pits_periodos_pendendentes_criacao_ou_envio(user)
    if pits_pendentes:
        if apenas_verificar_existe_pendencias:
            return True
        if not apenas_lista_separada:
            lista_pits_pendentes = []
            for pp in pits_pendentes:
                lista_pits_pendentes.append(f'[{pp.get_verbose_simples()}]')
            pits_pendentes = ', '.join(lista_pits_pendentes)
            pend_dict = {}
            pend_dict['msg'] = (
                f'Criação ou Solicitação de Aprovação/Homologação dos seguintes {nomenclatura.plano_individual_de_trabalho_sigla_plural_pgd2}: {pits_pendentes}. Observe os {nomenclatura.plano_individual_de_trabalho_sigla_plural_pgd2} relacionados às suas adesões vigentes para identificar e resolver essas pendências.'
            )
            pend_dict['url'] = '/pgd2/meu_pgd/'
            lista_pendencias.append(pend_dict)
        else:
            for pp in pits_pendentes:
                lista_pendencias_pit.append(pp.get_verbose_simples())

    rits_pendentes = PlanoIndividualTrabalho.get_rits_pendente_envio(user)
    if rits_pendentes:
        if apenas_verificar_existe_pendencias:
            return True
        if not apenas_lista_separada:
            lista_rits_pendentes = []
            for pp in rits_pendentes:
                lista_rits_pendentes.append(f'[{pp.get_verbose_periodo()}]')
            rits_pendentes = ', '.join(lista_rits_pendentes)
            pend_dict = {}
            pend_dict['msg'] = (
                f'Envio (solicitar aprovação/homologação) dos seguintes {nomenclatura.relatorio_individual_de_trabalho_sigla_plural_pgd2}: {rits_pendentes}. Observe os {nomenclatura.relatorio_individual_de_trabalho_sigla_plural_pgd2} relacionados às suas adesões vigentes para identificar e resolver essas pendências.'
            )
            pend_dict['url'] = '/pgd2/meu_pgd/'
            lista_pendencias.append(pend_dict)
        else:
            for pp in rits_pendentes:
                lista_pendencias_rit.append(pp.get_verbose_periodo())

    if apenas_verificar_existe_pendencias:
        return False

    if apenas_lista_separada:
        return lista_pendencias_pit, lista_pendencias_rit, pendencia_geral

    return lista_pendencias


def existe_pendencias_servidor_para_notificar(user):
    return get_pendencias_servidor(user, verifica_sou_gov=False, apenas_lista_separada=False, apenas_verificar_existe_pendencias=True)
