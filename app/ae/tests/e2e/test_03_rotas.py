"""Smoke das rotas do AE que os fluxos não declaram (modo 2).

O gate ``bin/scripts/paridade_e2e.py ae --rotas`` lê **literais**: as rotas que os fluxos alcançam
por clique não aparecem para ele. Aqui cada uma entra como URL com o literal presente e a
asserção é o **status do contrato** — ``200`` para a tela que renderiza, ``302`` para a view
que redireciona ou delega a uma task, ``403`` para a barreira de permissão/estado e ``404``
para o ``get_object_or_404`` de um id inexistente. A mensagem de falha carrega o motivo, então
quando a rota quebra o relatório diz qual fronteira caiu.

Os ids vêm da fixture ``alvos``, que cria (idempotente) uma participação, um documento, um
comprovante, uma solicitação de auxílio e os registros administrativos que as telas exigem.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

_2FA = '/djtools/two_factor_authentication/?next='


def _participacao(ae_fluxos, django_db_blocker):
    """Garante uma inscrição e uma participação abertas no programa de alimentação."""
    from ae.models import Inscricao, Participacao

    with django_db_blocker.unblock():
        aluno = ae_fluxos['aluno']
        programa = ae_fluxos['programas']['ALM']
        participacao = Participacao.objects.filter(aluno=aluno, programa=programa).first()
        if participacao is not None:
            return participacao
        inscricao = Inscricao.objects.filter(aluno=aluno, programa=programa).order_by('-pk').first()
        if inscricao is None:
            inscricao = Inscricao.objects.create(
                aluno=aluno,
                programa=programa,
                periodo_inscricao=ae_fluxos['periodos']['ALM'],
                data_cadastro=datetime(2024, 6, 3),
                motivo='E2E rota',
                ativa=True,
            )
        return Participacao.objects.create(
            programa=programa, aluno=aluno, inscricao=inscricao, data_inicio=date(2024, 6, 3), motivo_entrada='E2E rota'
        )


def _documento(aluno, django_db_blocker):
    from ae.models import DocumentoInscricaoAluno

    with django_db_blocker.unblock():
        documento = DocumentoInscricaoAluno.objects.filter(aluno=aluno, tipo_arquivo='Comprovante de Residência').first()
        if documento is None:
            documento = DocumentoInscricaoAluno.objects.create(
                aluno=aluno, tipo_arquivo='Comprovante de Residência', arquivo='ae/inscricao/documentos/e2e-rota.pdf'
            )
        return documento


def _comprovante(aluno, campus, programa, participacao, django_db_blocker):
    from ae.models import ComprovanteParticipacao

    with django_db_blocker.unblock():
        comprovante = ComprovanteParticipacao.objects.filter(aluno=aluno, participacao=participacao, ano=2024).first()
        if comprovante is None:
            comprovante = ComprovanteParticipacao.objects.create(
                aluno=aluno,
                campus=campus,
                programa=programa,
                participacao=participacao,
                tipo='Folha de Frequência',
                mes='Junho',
                ano=2024,
                pendente=True,
                arquivo='ae/participacoes/comprovantes/e2e-rota.pdf',
            )
        return comprovante


def _auxilio(aluno, campus, django_db_blocker):
    from ae.models import SolicitacaoAuxilioAluno, TipoAuxilioEventual

    with django_db_blocker.unblock():
        tipo_auxilio, _ = TipoAuxilioEventual.objects.get_or_create(
            nome='E2E Auxílio Eventual', defaults={'descricao': 'Auxílio do smoke de rotas', 'ativo': True}
        )
        tipo_auxilio.campi_que_ofertam.add(campus)
        solicitacao = SolicitacaoAuxilioAluno.objects.filter(aluno=aluno, tipo_auxilio=tipo_auxilio).first()
        if solicitacao is None:
            solicitacao = SolicitacaoAuxilioAluno.objects.create(aluno=aluno, tipo_auxilio=tipo_auxilio, motivo_solicitacao='E2E rota')
        return tipo_auxilio, solicitacao


def _registros(aluno, campus, programa, django_db_blocker):
    """Cria os registros administrativos das telas de detalhe (atividade, ação, atendimento)."""
    from ae.models import AcaoEducativa, AtividadeDiversa, DemandaAlunoAtendida, TipoAtividadeDiversa

    with django_db_blocker.unblock():
        tipo_atividade, _ = TipoAtividadeDiversa.objects.get_or_create(nome='E2E Atividade Diversa')
        atividade = AtividadeDiversa.objects.filter(tipo=tipo_atividade).first()
        if atividade is None:
            atividade = AtividadeDiversa.objects.create(
                tipo=tipo_atividade, campus=campus, data_inicio=datetime(2024, 6, 3, 8, 0), observacao='E2E rota'
            )
        acao = AcaoEducativa.objects.filter(titulo='E2E Ação Educativa').first()
        if acao is None:
            acao = AcaoEducativa.objects.create(
                titulo='E2E Ação Educativa', campus=campus, data_inicio=datetime(2024, 6, 3, 8, 0), descricao='E2E rota'
            )
        atendimento = DemandaAlunoAtendida.objects.filter(aluno=aluno, programa=programa, observacao='E2E rota').first()
        if atendimento is None:
            atendimento = DemandaAlunoAtendida.objects.create(
                demanda_id=1, programa=programa, aluno=aluno, data=datetime(2024, 6, 3, 8, 0), campus=campus, observacao='E2E rota'
            )
        return atividade, acao, atendimento


def _bolsa(aluno, django_db_blocker):
    from ae.models import CategoriaBolsa, ParticipacaoBolsa

    with django_db_blocker.unblock():
        categoria, _ = CategoriaBolsa.objects.get_or_create(nome='E2E Categoria de Bolsa', defaults={'descricao': 'E2E rota', 'ativa': True})
        bolsa = ParticipacaoBolsa.objects.filter(aluno=aluno).first()
        if bolsa is None:
            bolsa = ParticipacaoBolsa.objects.create(aluno=aluno, categoria=categoria, data_inicio=date(2024, 6, 3))
        return bolsa


@pytest.fixture(scope='session')
def alvos(ae_fluxos, django_db_blocker):
    """Ids reais para o smoke: participação, documento, comprovante, auxílio e registros do seed."""
    from ae.tests.e2e import seed as seed_ae
    from rh.models import UnidadeOrganizacional

    campus = UnidadeOrganizacional.objects.uo().get(sigla='CZN')
    aluno = ae_fluxos['aluno']
    programa = ae_fluxos['programas']['ALM']
    with django_db_blocker.unblock():
        seed_ae.criar_caracterizacao(aluno)
        from ae.models import Caracterizacao

        caracterizacao_id = Caracterizacao.objects.filter(aluno=aluno).values_list('pk', flat=True).first()
    participacao = _participacao(ae_fluxos, django_db_blocker)
    tipo_auxilio, solicitacao_auxilio = _auxilio(aluno, campus, django_db_blocker)
    atividade, acao, atendimento = _registros(aluno, campus, programa, django_db_blocker)
    participacao_alimentacao = participacao.sub_instance()
    if participacao_alimentacao.pk is None:
        with django_db_blocker.unblock():
            participacao_alimentacao.save()
    edital = ae_fluxos['periodos']['ALM'].edital
    return {
        'aluno': str(aluno.pk),
        'matricula': str(aluno.matricula),
        'programa': str(programa.pk),
        'periodo': str(ae_fluxos['periodos']['ALM'].pk),
        'inscricao': str(participacao.inscricao_id),
        'edital': str(edital.pk),
        'tipo_programa': str(edital.tipo_programa.first().pk),
        'pessoafisica': str(aluno.pessoa_fisica.pk),
        'participacao': str(participacao.pk),
        'documento': str(_documento(aluno, django_db_blocker).pk),
        'comprovante': str(_comprovante(aluno, campus, programa, participacao, django_db_blocker).pk),
        'tipo_auxilio': str(tipo_auxilio.pk),
        'solicitacao_auxilio': str(solicitacao_auxilio.pk),
        'atividade_diversa': str(atividade.pk),
        'acao_educativa': str(acao.pk),
        'atendimento': str(atendimento.pk),
        'caracterizacao': str(caracterizacao_id),
        'participacao_bolsa': str(_bolsa(aluno, django_db_blocker).pk),
        'participacao_alimentacao': str(participacao_alimentacao.pk),
    }


# (papel, rota, status esperado, motivo do status). A rota entra como literal com os
# placeholders das chaves de ``alvos``; o motivo fica na mensagem de falha.
#
# Cobertura: 200 = a tela renderiza com o estado das fixtures; 302 = redirecionamento,
# delegação a task ou exigência de segundo fator; 403 = barreira de permissão ou de estado;
# 404/500 só aparecem quando o contrato é esse (não há nenhum 500 aqui de propósito).
CASOS: list[tuple[str, str, int, str]] = [
    # Caracterização
    ('coordenador', '/ae/caracterizacao/{aluno}/', 200, 'tela de caracterização do aluno do seed'),
    ('coordenador', '/ae/caracterizacao/{aluno}/1/', 200, 'variante de renovação de matrícula'),
    ('aluno', '/ae/caracterizacao/', 200, 'sem id, a view resolve a caracterização do próprio usuário'),
    ('coordenador', '/ae/estatisticas_caracterizacao_dados_pessoais/', 200, 'gráfico de estatística responde 200'),
    ('coordenador', '/ae/estatisticas_caracterizacao_dados_educacionais/', 200, 'gráfico de estatística responde 200'),
    ('coordenador', '/ae/estatisticas_caracterizacao_dados_familiares/', 200, 'gráfico de estatística responde 200'),
    ('coordenador', '/ae/estatisticas_caracterizacao_dados_tic/', 200, 'gráfico de estatística responde 200'),
    # Inscrição
    ('assistente_social', '/ae/inscricao_identificacao/', 200, 'tela de identificação da inscrição'),
    (
        'coordenador',
        '/ae/inscricao_caracterizacao/{aluno}/{periodo}/{programa}/',
        302,
        f'exige segundo fator de autenticação: redireciona para ``{_2FA}``',
    ),
    (
        'coordenador',
        '/ae/inscricao_caracterizacao/{aluno}/{periodo}/{programa}/202406031200/',
        302,
        'variante com data de cadastro na URL; mesma exigência de segundo fator',
    ),
    (
        'coordenador',
        '/ae/inscricao_grupo_familiar/{aluno}/{periodo}/{programa}/202406031200/',
        403,
        'o aluno já é participante do programa: ``impede_se_inscrever_sendo_participante`` bloqueia a etapa',
    ),
    (
        'coordenador',
        '/ae/inscricao_documentacao/{aluno}/{periodo}/{programa}/202406031200/',
        403,
        'o aluno já é participante do programa: a etapa de documentação é bloqueada',
    ),
    (
        'coordenador',
        '/ae/inscricao_detalhamento/{aluno}/{periodo}/{programa}/202406031200/',
        403,
        'o aluno já é participante do programa: a etapa de detalhamento é bloqueada',
    ),
    ('coordenador', '/ae/inscricao_confirmacao/ALM/{inscricao}/', 200, 'tela de confirmação da inscrição'),
    ('coordenador', '/ae/estatisticas/', 200, 'panorama de estatísticas responde 200'),
    ('coordenador', '/ae/comprovante_inscricao/{inscricao}/', 200, 'comprovante da inscrição do aluno'),
    ('coordenador', '/ae/inscricao/{inscricao}/', 200, 'detalhe da inscrição'),
    ('coordenador', '/ae/parecer_inscricao/{inscricao}/', 200, 'tela de parecer da inscrição'),
    (
        'assistente_social',
        '/ae/adicionar_pendencia/{inscricao}/',
        403,
        'exige inscrição em ``PENDENTE_DOCUMENTACAO``; a do seed está em outro estado',
    ),
    ('coordenador', '/ae/ver_historico_documento/{documento}/', 200, 'histórico do documento de inscrição'),
    # Programa e participação
    ('coordenador', '/ae/programa/{programa}/', 200, 'detalhe do programa do seed'),
    ('coordenador', '/ae/registrar_atendimento/{inscricao}/', 200, 'formulário de atendimento da inscrição'),
    ('coordenador', '/ae/gerenciar_participacao/{programa}/', 200, 'tela de gestão de participações do programa'),
    ('coordenador', '/ae/editar_participacao/{participacao}/', 200, 'formulário de edição da participação aberta'),
    (
        'coordenador',
        '/ae/adicionar_participacao/{programa}/{inscricao}/',
        302,
        'o aluno do seed já tem participação aberta: a view redireciona de volta com a mensagem de erro',
    ),
    ('coordenador', '/ae/revogar_participacao/{participacao}/', 200, 'formulário de finalização da participação'),
    ('coordenador', '/ae/corrigir_participacao/{participacao}/', 200, 'formulário de correção da participação'),
    # Refeições e exportações de terminal
    (
        'coordenador',
        '/ae/remover_agendamento_refeicao/',
        302,
        'sem ``id`` na query string nada é cancelado: a view redireciona para a listagem do admin',
    ),
    ('coordenador', '/ae/get_pessoas/', 403, 'exportação de terminal exige máquina cadastrada (``PermissionDenied``)'),
    ('coordenador', '/ae/get_pessoas/v2/', 403, 'variante versionada da exportação de terminal, mesma exigência'),
    ('coordenador', '/ae/get_config_refeicao/', 403, 'o dump do refeitório não existe no ambiente de teste e a view nega'),
    ('coordenador', '/ae/get_config_refeicao/v2/', 403, 'variante versionada do dump do refeitório, mesma exigência'),
    ('coordenador', '/ae/relatorio_semanal_refeitorio/{programa}/', 200, 'relatório semanal do programa de alimentação'),
    ('coordenador', '/ae/folha_pagamento/{programa}/', 200, 'folha de pagamento do programa'),
    ('coordenador', '/ae/alunos_ativos_sem_caracterizacao/', 200, 'relatório de alunos sem caracterização'),
    ('coordenador', '/ae/relatorio_gestao/', 200, 'relatório de gestão responde 200'),
    ('coordenador', '/ae/grafico_atendimentos/', 200, 'gráfico de atendimentos responde 200'),
    ('coordenador', '/ae/relatorio_financeiro/', 200, 'relatório financeiro responde 200'),
    ('coordenador', '/ae/dashboard/', 200, 'painel do módulo responde 200'),
    ('coordenador', '/ae/relatorio_financeiro_refeicoes/', 200, 'recorte de refeições do relatório financeiro'),
    ('coordenador', '/ae/relatorio_financeiro_auxilio_transporte/', 200, 'recorte de transporte do relatório financeiro'),
    ('coordenador', '/ae/relatorio_financeiro_bolsas/', 200, 'recorte de bolsas do relatório financeiro'),
    ('coordenador', '/ae/participacoes_bolsas/', 200, 'tela de participações em bolsas'),
    ('coordenador', '/ae/participacoes_bolsas_salvar/', 200, 'formulário de cadastro de participação em bolsa'),
    ('coordenador', '/ae/participacoes_bolsas_salvar/{participacao_bolsa}/', 200, 'formulário de edição da participação em bolsa (id existente)'),
    ('coordenador', '/ae/lista_participantes_bolsas/', 200, 'relatório de participantes em bolsas'),
    ('coordenador', '/ae/lista_participantes_programas/', 200, 'relatório de participantes por programa'),
    ('coordenador', '/ae/lista_atendidos_auxilios/', 200, 'relatório de atendidos por auxílios'),
    ('coordenador', '/ae/aluno/buscar/', 200, 'autocomplete de aluno'),
    ('coordenador', '/ae/relatorio_erro_participacoes/', 200, 'relatório de inconsistências das participações'),
    ('coordenador', '/ae/atendimento/{atendimento}/', 200, 'detalhe do atendimento registrado'),
    ('aluno', '/ae/solicitar_refeicao/{programa}/', 302, 'o programa do seed tem ``impedir_solicitacao_beneficio``: redireciona com erro'),
    ('coordenador', '/ae/avaliar_solicitacao_refeicao/{programa}/', 200, 'tela de avaliação das solicitações de refeição'),
    ('aluno', '/ae/busca_tipo_refeicao/', 200, 'endpoint de tipos de refeição responde para o aluno'),
    ('coordenador', '/ae/liberar_participacao_alimentacao/{programa}/', 200, 'tela de liberação de participações suspensas'),
    ('aluno', '/ae/justificar_falta/{aluno}/{programa}/', 200, 'com participação aberta, o formulário de justificativa de falta renderiza'),
    ('coordenador', '/ae/lista_alunodemandaatendida/', 302, 'atalho: redireciona para a listagem do admin com o mês corrente'),
    ('coordenador', '/ae/lista_alunodemandaatendida_alimentos/', 302, 'atalho: redireciona para a listagem filtrada por kit alimentação'),
    ('coordenador', '/ae/lista_historicosuspensoesalimentacao/', 302, 'atalho: redireciona para a listagem do admin de suspensões'),
    ('aluno', '/ae/redireciona_minhas_inscricoes/', 302, 'redireciona para as atividades estudantis do aluno no edu'),
    ('coordenador', '/ae/relatorio_alunos_aptos/', 200, 'relatório de alunos aptos responde 200'),
    ('coordenador', '/ae/atividadediversa/{atividade_diversa}/', 200, 'detalhe da atividade diversa'),
    ('coordenador', '/ae/acaoeducativa/{acao_educativa}/', 200, 'detalhe da ação educativa'),
    ('coordenador', '/ae/informar_data_entrega_documentacao/', 200, 'formulário de data de entrega da documentação'),
    ('coordenador', '/ae/relatorio_atendimentos_pnaes/', 200, 'relatório de atendimentos PNAES'),
    ('coordenador', '/ae/relatorio_planejamento/', 200, 'relatório de planejamento responde 200'),
    ('coordenador', '/ae/indeferir_solicitacoes/{programa}/', 302, 'sem solicitações pendentes, redireciona para a tela de avaliação'),
    ('coordenador', '/ae/agendar_desbloqueio_alimentacao/{participacao_alimentacao}/{programa}/', 200, 'formulário de agendamento do desbloqueio'),
    (
        'assistente_social',
        '/ae/atualizar_documentacao_aluno/{documento}/',
        200,
        'tela de atualização da documentação (exige permissão do serviço social)',
    ),
    ('assistente_social', '/ae/adicionar_documentacao_aluno/{matricula}/', 200, 'cadastro de documentação avulsa do aluno'),
    ('coordenador', '/ae/redireciona_relatorio_semanal/', 302, 'atalho: redireciona para o relatório semanal do programa corrente'),
    ('coordenador', '/ae/imprimir_lista_diaria/{programa}/Segunda/', 302, 'sem horário de refeição cadastrado, a impressão redireciona para a raiz'),
    ('coordenador', '/ae/redireciona_relatorio_diario/', 200, 'atalho do relatório diário renderiza a seleção'),
    ('coordenador', '/ae/relatorio_diario_refeitorio/{programa}/', 200, 'relatório diário do refeitório'),
    ('coordenador', '/ae/relatorio_aluno_rendimento_frequencia/', 200, 'relatório de rendimento e frequência'),
    ('coordenador', '/ae/verifica_tipo_programa/', 200, 'endpoint que classifica o tipo do programa'),
    ('coordenador', '/ae/redireciona_folha_pagamento/', 200, 'atalho da folha de pagamento renderiza a seleção'),
    ('coordenador', '/ae/redireciona_avaliar_solicitacao_refeicao/', 200, 'atalho da avaliação de refeições renderiza a seleção'),
    ('coordenador', '/ae/lista_atendimentos_refeicoes/', 200, 'relatório de atendimentos em refeições'),
    ('coordenador', '/ae/importar_caracterizacao_edital_ano/', 200, 'tela de importação da caracterização por edital/ano'),
    ('assistente_social', '/ae/avaliar_solicitacao_auxilio/{solicitacao_auxilio}/', 200, 'formulário de avaliação da solicitação de auxílio'),
    ('coordenador', '/ae/historico_caracterizacao/{caracterizacao}/', 200, 'histórico da caracterização do aluno'),
    ('coordenador', '/ae/relatorio_demanda_reprimida/', 200, 'relatório de demanda reprimida responde 200'),
    ('coordenador', '/ae/adicionar_dado_bancario/{aluno}/', 302, f'editar dado bancário exige segundo fator: redireciona para ``{_2FA}``'),
    ('coordenador', '/ae/adicionar_dado_bancario/{aluno}/1/', 302, 'variante de atualização do dado bancário; mesma exigência de segundo fator'),
    ('coordenador', '/ae/documentacao_pendente/{aluno}/{inscricao}/', 200, 'tela de documentação pendente da inscrição'),
    (
        'assistente_social',
        '/ae/registrar_pendencia_documento/{documento}/{inscricao}/',
        403,
        'documento sem inscrição com pendência: a view nega antes de renderizar',
    ),
    ('assistente_social', '/ae/corrigir_documento/{documento}/{inscricao}/', 403, 'documento sem pendência editável (``pode_editar()`` falso)'),
    ('coordenador', '/ae/historico_parecer/{inscricao}/', 200, 'histórico de pareceres da inscrição'),
    ('coordenador', '/ae/historico_termo_compromisso/{inscricao}/', 200, 'histórico do termo de compromisso da inscrição'),
    ('aluno', '/ae/assinar_termo_compromisso_inscricao/{inscricao}/', 403, 'inscrição sem ``pendente_assinatura``: a view nega a assinatura'),
    ('coordenador', '/ae/validar_termo_compromisso/{inscricao}/', 200, 'formulário de validação do termo de compromisso'),
    ('coordenador', '/ae/participacoes_pendentes_ciencia/', 200, 'lista de participações pendentes de ciência'),
    ('coordenador', '/ae/tabela_disponibilidade/{programa}/', 200, 'tabela de disponibilidade do programa'),
    ('aluno', '/ae/listar_comprovantes_mensais_pendentes/{aluno}/', 200, 'lista de comprovantes mensais pendentes do aluno'),
    ('aluno', '/ae/cadastrar_comprovante_mensal/{comprovante}/', 200, 'formulário de envio do comprovante mensal pendente'),
    ('assistente_social', '/ae/invalidar_comprovante_mensal/{comprovante}/', 200, 'formulário de invalidação do comprovante (serviço social)'),
    ('aluno', '/ae/meus_comprovantes_mensais/', 302, 'redireciona para a lista de comprovantes do próprio aluno'),
    ('aluno', '/ae/solicitar_alteracao_alimentacao/{participacao}/', 403, 'programa fora da fase de alteração (``em_fase_alteracao()`` falso)'),
    (
        'aluno',
        '/ae/adicionar_comprovante_solicitacao_auxilio/{solicitacao_auxilio}/',
        403,
        'solicitação sem ``comprovacao_pendente``: a view nega o envio',
    ),
    (
        'assistente_social',
        '/ae/avaliar_comprovante_utilizacao_auxilio/{solicitacao_auxilio}/',
        200,
        'formulário de avaliação do comprovante do auxílio',
    ),
    (
        'coordenador',
        '/ae/gerenciar_oferta_auxilio_eventual/{tipo_auxilio}/',
        302,
        'redireciona para o tipo de auxílio ofertado pelo campus (id da oferta)',
    ),
    # Análise de inscrições
    ('assistente_social', '/ae/analise_inscricoes/', 200, 'tela de análise das inscrições (serviço social)'),
    (
        'assistente_social',
        '/ae/gerar_analise_inscricoes/{edital}/{programa}/nota/',
        302,
        'gera as análises (o aluno do smoke tem caracterização e sem matrícula corrente não derruba mais a task) e redireciona para a página de processamento',
    ),
    ('coordenador', '/ae/adicionar_criterio_selecao_programa/', 200, 'formulário de critério de seleção'),
    ('assistente_social', '/ae/adicionar_parametro_selecao_programa/', 200, 'formulário de parâmetro de seleção'),
    ('coordenador', '/ae/pontuacao_especificidade/1/', 403, 'exige ``ae.add_auxilioeventual``, que o papel do smoke não tem'),
    ('coordenador', '/ae/ver_avaliacao_especificidade/1/', 403, 'exige ``ae.add_auxilioeventual``'),
    ('coordenador', '/ae/atualizar_caracterizacao/1/', 403, 'exige ``ae.add_auxilioeventual``'),
    ('coordenador', '/ae/cadastrar_simulacao_resultado/1/', 403, 'exige ``ae.add_auxilioeventual``'),
    ('coordenador', '/ae/cadastrar_obs_analise/1/', 403, 'exige ``ae.add_auxilioeventual``'),
    ('coordenador', '/ae/editar_valor_gasto_mensal/1/', 403, 'exige ``ae.add_auxilioeventual``'),
    (
        'assistente_social',
        '/ae/exportar_analises_deferidas_pdf/{edital}/{programa}/{tipo_programa}/',
        302,
        'exportação delegada a task: redireciona para a própria página de processamento',
    ),
    ('coordenador', '/ae/relatorio_refeicoes/', 200, 'relatório de refeições responde 200'),
    ('coordenador', '/ae/relatorio_densidade_pontuacao/', 200, 'relatório de densidade de pontuação'),
    ('coordenador', '/ae/relatorio_estatistica_pareceres/', 200, 'relatório de estatística de pareceres'),
    ('coordenador', '/ae/relatorio_alunos_com_pendencias/', 200, 'relatório de alunos com pendências'),
    ('coordenador', '/ae/relatorio_quantidade_refeicoes_deferidas/', 200, 'relatório de refeições deferidas'),
    ('coordenador', '/ae/editar_turno_disponibilidade/1/', 403, 'exige ``ae.add_auxilioeventual``'),
    ('coordenador', '/ae/relatorio_beneficiarios_sispnaes/', 200, 'relatório de beneficiários SISPNAES'),
    ('coordenador', '/ae/gerar_pendencia_comprovantes_mensais/{programa}/', 200, 'geração de pendências de comprovantes mensais'),
    ('coordenador', '/ae/cadastrar_simulacao_resultado_texto/1/', 403, 'exige ``ae.add_auxilioeventual``'),
    ('coordenador', '/ae/recalcular_sugestao_resultado/1/', 403, 'exige ``ae.add_auxilioeventual``'),
    (
        'assistente_social',
        '/ae/importar_cadunico/{pessoafisica}/',
        302,
        'importação delegada a task: redireciona para a própria página de processamento',
    ),
    ('coordenador', '/ae/ver_descricao_pontuacao_analise/1/', 403, 'exige ``ae.pode_abrir_inscricao_do_campus``'),
]


@pytest.mark.parametrize(('papel', 'rota', 'status_esperado', 'motivo'), CASOS, ids=[caso[1] for caso in CASOS])
def test_rota_responde_como_esperado(logado_ae, alvos: dict[str, str], papel, rota, status_esperado, motivo):
    """Cada rota responde o status do contrato, com o papel de maior alcance para ela."""
    resposta = Tela(logado_ae(papel)).buscar(rota.format(**alvos))
    assert resposta.status == status_esperado, f'{rota} respondeu HTTP {resposta.status} (esperado {status_esperado}: {motivo})'
