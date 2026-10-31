"""Fluxos de inscrição e participação do AE (modo 2).

As etapas da inscrição (caracterização, grupo familiar, documentação e detalhamento) são
percorridas até a confirmação persistida, um teste por tipo de programa; a inclusão como
participante é exercitada para os quatro programas.
"""

from datetime import datetime

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def _preencher_grupo_familiar(tela: Tela) -> Tela:
    return tela.preencher_formulario(
        [
            ('Renda do Estudante', 'texto', '430,00'),
            ('Você estudou em escola particular com BOLSA DE ESTUDO INTEGRAL (ou seja, sem pagamento de mensalidade)?', 'lista', 'Não'),
            (
                'Você recebe acompanhamento pedagógico específico pelo NAPNE (Núcleo de Atendimento às Pessoas com necessidades educacionais específicas)?',
                'lista',
                'Não',
            ),
            ('Você reside ou é oriundo de comunidades tradicionais, quilombola ou indígena?', 'lista', 'Não'),
            ('Você mora ou já morou em abrigo institucional (orfanato)?', 'lista', 'Não, nunca morei'),
        ]
    ).clicar_botao('Continuar')


def _limpar_inscricoes(aluno, programa) -> None:
    from ae.models import Inscricao

    Inscricao.objects.filter(aluno=aluno, programa=programa).delete()


def _iniciar_inscricao(tela: Tela, nome_programa: str, autenticar: bool = False) -> Tela:
    tela.ir('/').clicar_link(f'Inscrever-se em: {nome_programa} (CZN)')
    if autenticar:
        tela.preencher('Código', 'texto', '123456').clicar_botao('Autenticar')
    return tela


def test_realiza_caracterizacao_socioeconomica(logado_ae, ae_fluxos):
    from ae.models import Caracterizacao

    pagina = logado_ae('aluno')
    aluno = ae_fluxos['aluno']
    tela = Tela(pagina).ir('/ae/caracterizacao/')
    tela.ver_titulo('Caracterização Social').preencher_formulario(
        [
            ('Etnia/Raça/Cor', 'autocomplete', 'Parda'),
            ('Estado Civil', 'autocomplete', 'Solteiro(a)'),
            ('Serviço de Saúde que você mais utiliza', 'autocomplete', 'Sistema Único de Saúde - SUS'),
            ('Ano de conclusão do Ensino Fundamental', 'texto', '2017'),
            ('Tipo de escola que cursou o Ensino Fundamental', 'autocomplete', 'Somente em escola pública'),
            ('Situação de Trabalho', 'autocomplete', 'Não está trabalhando'),
            ('Meio de transporte que você utiliza/utilizará para se deslocar', 'checkbox multiplo', 'Bicicleta, Moto'),
            ('Contribuintes da Renda Familiar', 'checkbox multiplo', 'Pai, Mãe, Parentes'),
            ('Principal Responsável Financeiro', 'radio', 'Pai'),
            ('Situação de Trabalho do Principal Responsável Financeiro', 'lista', 'Autônomo'),
            ('Nível de Escolaridade do Principal Responsável Financeiro', 'autocomplete', 'Ensino médio completo'),
            ('Nível de escolaridade do pai', 'autocomplete', 'Ensino médio completo'),
            ('Nível de escolaridade da mãe', 'autocomplete', 'Ensino médio completo'),
            ('Renda Bruta Familiar R$', 'texto', '2.500,00'),
            ('Companhia domiciliar', 'radio', 'Pai'),
            ('Número de pessoas no domicílio', 'texto', '1'),
            ('Tipo de Imóvel', 'autocomplete', 'Financiado'),
            ('Tipo de Área Residencial', 'autocomplete', 'Urbana'),
            ('Frequência de Acesso à Internet', 'autocomplete', 'Diariamente'),
            ('Quantidade de Computadores Desktop que possui', 'texto', '1'),
            ('Quantidade de Notebooks que possui', 'texto', '1'),
            ('Quantidade de Smartphones que possui', 'texto', '1'),
            ('Quantidade de Netbooks que possui', 'texto', '0'),
        ]
    ).clicar_botao('Salvar')
    tela.sucesso('Caracterização realizada com sucesso.')
    assert Caracterizacao.objects.filter(aluno=aluno).exists()


def test_inscreve_aluno_no_programa_de_trabalho(logado_ae, ae_fluxos, caracterizacao_pronta):
    from ae.models import Inscricao

    pagina = logado_ae('aluno')
    programa = ae_fluxos['programas']['TRB']
    _limpar_inscricoes(ae_fluxos['aluno'], programa)
    tela = _iniciar_inscricao(Tela(pagina), 'Apoio à Formação Estudantil', autenticar=True)
    tela.ver_titulo('Inscrição para Apoio à Formação Estudantil (CZN): Caracterização Socioeconômica').clicar_botao('Continuar')
    _preencher_grupo_familiar(tela).ver_titulo('Inscrição para Apoio à Formação Estudantil (CZN): Documentação')
    tela.preencher('Comprovante de Residência', 'arquivo', 'comprovante.png').clicar_botao('Continuar')
    tela.sucesso('Infome o setor de sua preferência, o turno que deseja trabalhar e suas habilidades.')
    tela.ver_titulo('Inscrição para Apoio à Formação Estudantil (CZN): Detalhamento').preencher_formulario(
        [('Turno de disponibilidade', 'lista', 'Tarde'), ('Motivo da solicitação', 'textarea', 'Descrição do motivo da solicitação')]
    ).clicar_botao('Continuar')
    tela.sucesso('Inscrição realizada com sucesso.')
    assert Inscricao.objects.filter(aluno=ae_fluxos['aluno'], programa=programa, ativa=True).exists()


def test_inscreve_aluno_no_programa_de_transporte(logado_ae, ae_fluxos, caracterizacao_pronta):
    from ae.models import Inscricao

    pagina = logado_ae('aluno')
    programa = ae_fluxos['programas']['PAS']
    _limpar_inscricoes(ae_fluxos['aluno'], programa)
    tela = _iniciar_inscricao(Tela(pagina), 'Auxílio Transporte')
    tela.ver_titulo('Inscrição para Auxílio Transporte (CZN): Caracterização Socioeconômica').clicar_botao('Continuar')
    _preencher_grupo_familiar(tela).ver_titulo('Inscrição para Auxílio Transporte (CZN): Documentação')
    tela.preencher('Comprovante de Residência', 'arquivo', 'comprovante.png').clicar_botao('Continuar')
    tela.sucesso('Infome o tipo do passe estudantil desejado.')
    tela.ver_titulo('Inscrição para Auxílio Transporte (CZN): Detalhamento').preencher_formulario(
        [
            ('Tipo de Passe', 'lista', 'Intermunicipal'),
            ('Motivo da solicitação', 'textarea', 'Descrição do motivo da solicitação'),
            ('Valor gasto com transporte por dia', 'texto', '10'),
            ('Descreva o trajeto que você realiza CASA/IFRN/CASA', 'textarea', 'descrição do trajeto percorrido pelo aluno'),
            ('A prefeitura do seu município oferta o transporte escolar gratuito?', 'lista', 'Não'),
            ('Declaração da prefeitura', 'arquivo', 'declaracao.pdf'),
        ]
    ).clicar_botao('Continuar')
    tela.sucesso('Inscrição realizada com sucesso.')
    assert Inscricao.objects.filter(aluno=ae_fluxos['aluno'], programa=programa, ativa=True).exists()


def test_inscreve_aluno_no_curso_de_idiomas(logado_ae, ae_fluxos, caracterizacao_pronta):
    from ae.models import Inscricao

    pagina = logado_ae('aluno')
    programa = ae_fluxos['programas']['IDM']
    _limpar_inscricoes(ae_fluxos['aluno'], programa)
    tela = _iniciar_inscricao(Tela(pagina), 'Curso de Idiomas')
    tela.ver_titulo('Inscrição para Curso de Idiomas (CZN): Caracterização Socioeconômica').clicar_botao('Continuar')
    _preencher_grupo_familiar(tela).ver_titulo('Inscrição para Curso de Idiomas (CZN): Documentação')
    tela.preencher('Comprovante de Residência', 'arquivo', 'comprovante.png').clicar_botao('Continuar')
    tela.sucesso('Selecione o(s) idioma(s) que você deseja aprender.')
    tela.ver_titulo('Inscrição para Curso de Idiomas (CZN): Detalhamento').preencher_formulario(
        [
            ('Primeira Opção', 'autocomplete', '01'),
            ('Segunda Opção', 'autocomplete', '02'),
            ('Motivo da solicitação', 'textarea', 'Descrição do motivo'),
        ]
    ).clicar_botao('Continuar')
    tela.sucesso('Inscrição realizada com sucesso.')
    assert Inscricao.objects.filter(aluno=ae_fluxos['aluno'], programa=programa, ativa=True).exists()


def test_inscreve_aluno_no_programa_de_alimentacao(logado_ae, ae_fluxos, caracterizacao_pronta):
    from ae.models import Inscricao

    pagina = logado_ae('aluno')
    programa = ae_fluxos['programas']['ALM']
    _limpar_inscricoes(ae_fluxos['aluno'], programa)
    tela = _iniciar_inscricao(Tela(pagina), 'Alimentação Estudantil')
    tela.ver_titulo('Inscrição para Alimentação Estudantil (CZN): Caracterização Socioeconômica').clicar_botao('Continuar')
    _preencher_grupo_familiar(tela).ver_titulo('Inscrição para Alimentação Estudantil (CZN): Documentação')
    tela.preencher('Comprovante de Residência', 'arquivo', 'comprovante.png').clicar_botao('Continuar')
    tela.sucesso('Informe as refeições que você deseja obter.')
    tela.ver_titulo('Inscrição para Alimentação Estudantil (CZN): Detalhamento').preencher_formulario(
        [('Motivo da inscrição', 'autocomplete', 'Aula no turno inverso'), ('Segunda', 'checkbox', 'marcar')]
    ).clicar_botao('Continuar')
    tela.sucesso('Inscrição realizada com sucesso.')
    assert Inscricao.objects.filter(aluno=ae_fluxos['aluno'], programa=programa, ativa=True).exists()


def test_registra_entrega_da_documentacao(logado_ae, ae_fluxos, django_db_blocker):
    from ae.models import Inscricao

    aluno = ae_fluxos['aluno']
    programas = ae_fluxos['programas']
    with django_db_blocker.unblock():
        Inscricao.objects.filter(aluno=aluno, programa__in=programas.values()).delete()
        inscricoes = []
        for programa in programas.values():
            inscricoes.append(
                Inscricao.objects.create(
                    aluno=aluno,
                    programa=programa,
                    periodo_inscricao=ae_fluxos['periodos'][programa.tipo_programa.sigla],
                    data_cadastro=datetime(2024, 6, 3),
                    motivo='E2E documentação',
                    ativa=True,
                    situacao_parecer=Inscricao.SEM_PARECER,
                )
            )

    pagina = logado_ae('coordenador')
    tela = Tela(pagina)
    for _inscricao in inscricoes:
        tela.ir('/admin/ae/inscricao/')
        tela.selecionar_item('20191101011031')
        tela.preencher('Ação', 'lista', 'Validar documentação').clicar_acao('Aplicar')
        tela.ver_titulo('Validar documentação').preencher('Data', 'data', '03/06/2024').clicar_botao('Enviar')
        tela.sucesso('Documentação(ões) validada(s) com sucesso.').clicar_botao('Adicionar Parecer')
        tela.ver_texto('Parecer da Inscrição').preencher_formulario(
            [('Situação do Parecer', 'lista', 'Deferido'), ('Parecer da Inscrição', 'textarea', 'Descrição do parecer favorável')]
        ).clicar_botao('Salvar')
        tela.sucesso('Parecer cadastrado com sucesso.')

    assert Inscricao.objects.filter(pk__in=[inscricao.pk for inscricao in inscricoes], situacao_parecer=Inscricao.DEFERIDO).count() == 4


def _inclui_participante(tela: Tela, programa, inscricao, campos: list[tuple[str, ...]]) -> Tela:
    tela.ir(f'/ae/programa/{programa.pk}/').ver_titulo(f'Programa: {programa.titulo}').clicar_botao('Gerenciar Participações')
    tela.ver_titulo('Gerenciar Participações').cartao('20191101011031').clicar_link('Adicionar Participação')
    popup = tela.popup().ver_titulo('Adicionar Participação')
    popup.preencher_formulario(campos)
    return popup.salvar_no_popup('Salvar')


def test_inclui_participante_de_alimentacao(logado_ae, ae_fluxos, inscricao_deferida):
    from ae.models import Participacao

    pagina = logado_ae('assistente_social')
    programa = ae_fluxos['programas']['ALM']
    inscricao = inscricao_deferida(programa)
    tela = _inclui_participante(
        Tela(pagina),
        programa,
        inscricao,
        [
            ('Data de Entrada', 'data', '03/06/2024'),
            ('Motivo de Entrada', 'textarea', 'motivo da entrada da participação'),
            ('Almoço', 'checkbox multiplo', 'Segunda, Terça'),
            ('Categoria', 'autocomplete', 'AS'),
            ('Motivo do Atendimento', 'autocomplete', 'Aula no turno inverso'),
        ],
    )
    tela.sucesso('Participação adicionada com sucesso.')
    assert Participacao.objects.filter(inscricao=inscricao).exists()


def test_inclui_participante_de_idiomas(logado_ae, ae_fluxos, inscricao_deferida):
    from ae.models import Participacao

    pagina = logado_ae('assistente_social')
    programa = ae_fluxos['programas']['IDM']
    inscricao = inscricao_deferida(programa)
    tela = _inclui_participante(
        Tela(pagina),
        programa,
        inscricao,
        [
            ('Data de Entrada', 'data', '03/06/2024'),
            ('Motivo de Entrada', 'textarea', 'motivo da entrada da participação'),
            ('Idioma', 'autocomplete', 'Inglês'),
        ],
    )
    tela.sucesso('Participação adicionada com sucesso.')
    assert Participacao.objects.filter(inscricao=inscricao).exists()


def test_inclui_participante_de_trabalho(logado_ae, ae_fluxos, inscricao_deferida):
    from ae.models import Participacao

    pagina = logado_ae('assistente_social')
    programa = ae_fluxos['programas']['TRB']
    inscricao = inscricao_deferida(programa)
    tela = _inclui_participante(
        Tela(pagina),
        programa,
        inscricao,
        [
            ('Data de Entrada', 'data', '03/06/2024'),
            ('Motivo de Entrada', 'textarea', 'motivo da entrada da participação'),
            ('Bolsa Concedida', 'autocomplete', 'CZN'),
        ],
    )
    tela.sucesso('Participação adicionada com sucesso.')
    assert Participacao.objects.filter(inscricao=inscricao).exists()


def test_inclui_participante_de_transporte(logado_ae, ae_fluxos, inscricao_deferida):
    from ae.models import Participacao

    pagina = logado_ae('assistente_social')
    programa = ae_fluxos['programas']['PAS']
    inscricao = inscricao_deferida(programa)
    tela = _inclui_participante(
        Tela(pagina),
        programa,
        inscricao,
        [
            ('Data de Entrada', 'data', '03/06/2024'),
            ('Motivo de Entrada', 'textarea', 'motivo da entrada da participação'),
            ('Valor Concedido (R$)', 'texto', '100'),
            ('Tipo de Passe Concedido', 'lista', 'Intermunicipal'),
        ],
    )
    tela.sucesso('Participação adicionada com sucesso.')
    assert Participacao.objects.filter(inscricao=inscricao).exists()
