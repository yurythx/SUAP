"""Roteiro navegado das tarefas do ``pesquisa`` — a fonte de ``pesquisa/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. A cadeia de estados é
deliberada: edital → projeto → pré-seleção → indicação → avaliação → distribuição de
bolsas → execução → monitoramento → conclusão — cada teste parte do estado gravado pelo
anterior (a suíte não dá flush). As asserções são as mesmas do behave e existem para a
rodada falhar alto quando a tela mudou de forma.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, adicionar_ao_filteredselect, anotar_tela, expect

from pesquisa.tests.doc.conftest import marcar_periodo

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAL = f'E2E Edital {uuid4().hex[:8]}'
PROJETO = f'E2E Projeto {uuid4().hex[:8]}'
ATIVIDADE = 'Descrição da Atividade 1'
META = 'Meta 1'
DESPESA_MEMORIA = 'Pagamento das bolsas de dois alunos'
HOJE = date.today()


def _formatar_data(dias: int) -> str:
    return (HOJE + timedelta(days=dias)).strftime('%d/%m/%Y')


def _iso_local(dias: int) -> str:
    """``YYYY-MM-DDTHH:MM`` para os ``input[type=datetime-local]`` do admin."""
    return (datetime.now() + timedelta(days=dias)).strftime('%Y-%m-%dT00:00')


def _edital():
    from pesquisa.models import Edital

    # `order_by('-id').first()` e não `.get(titulo=...)`: sob `--reruns 2` (job `gerar-doc`),
    # uma falha depois do save faz a retentativa criar um segundo edital com o mesmo título e
    # `.get` passaria a levantar `MultipleObjectsReturned` em todos os testes seguintes.
    return Edital.objects.filter(titulo=EDITAL).order_by('-id').first()


def _projeto():
    from pesquisa.models import Projeto

    return Projeto.objects.filter(titulo=PROJETO).order_by('-id').first()


# --------------------------------------------------------------------------------------
# Tarefa 1 — o Diretor de Pesquisa cadastra o edital e o configura
# --------------------------------------------------------------------------------------


def test_cadastrar_edital_e_configurar(logado_doc, capturar):
    """Tarefa 1 — edital completo: cadastro, plano de oferta, fontes, critérios e comissão."""
    from pesquisa.models import BolsaDisponivel, ComissaoEditalPesquisa, CriterioAvaliacao, Edital, Recurso

    tela = Tela(logado_doc('diretor')).ir('/admin/pesquisa/edital/')
    tela.ver_titulo('Editais')
    anotar_tela('edital-listagem', tela)
    capturar(tela.pagina, 'edital-listagem')

    tela.ver_botao('Adicionar Edital')
    tela.clicar_botao('Adicionar Edital')
    tela.ver_titulo('Adicionar Edital')
    anotar_tela('edital-formulario', tela)
    # Datas do calendário: inscrições abertas HOJE (as fases seguintes são deslocadas por
    # `marcar_periodo` no teste de cada tarefa, sem congelar o relógio).
    tela.preencher_formulario(
        [
            ('Título', 'texto', EDITAL),
            ('Descrição', 'textarea', 'Seleção de projetos de pesquisa do edital de teste.'),
            ('Tipo do Edital', 'lista', 'Pesquisa'),
            ('Formato do Edital', 'lista', 'Completo'),
            ('Forma de Seleção', 'lista', 'Campus'),
            ('Edital de Campus', 'checkbox', 'marcar'),
            ('Início das Inscrições', 'texto', _iso_local(0)),
            ('Fim das Inscrições', 'texto', _iso_local(5)),
            ('Início da Pré-Seleção', 'texto', _iso_local(10)),
            ('Fim da Pré-Seleção', 'texto', _iso_local(12)),
            ('Data Limite Para Recursos da Pré-Seleção', 'texto', _iso_local(13)),
            ('Início da Seleção', 'texto', _iso_local(15)),
            ('Fim da Seleção', 'texto', _iso_local(20)),
            ('Data Limite Para Recursos', 'texto', _iso_local(21)),
            ('Data Limite Para Avaliação dos Recursos', 'texto', _iso_local(22)),
            ('Divulgação da Seleção', 'texto', _iso_local(23)),
            ('Participação de Aluno Obrigatória', 'checkbox', 'desmarcar'),
            ('Participação de Servidor Obrigatória', 'checkbox', 'desmarcar'),
            ('Titulações dos Avaliadores', 'filteredselectmultiple', 'Doutorado'),
            ('Anos de consideração das Publicações', 'texto', '3'),
            ('Peso da Avaliação do Coordenador (%)', 'texto', '0'),
            ('Peso da Avaliação do Projeto (%)', 'texto', '100'),
            ('Ponto de Corte para Aprovação de Projeto (%)', 'texto', '50'),
            ('Carga Horária do Coordenador', 'texto', '4'),
            ('Período máximo currículo desatualizado', 'texto', '6'),
            ('Total de Servidores', 'texto', '5'),
            ('Total de Servidores Bolsistas', 'texto', '3'),
            ('Total de Alunos', 'texto', '2'),
            ('Total de Alunos Bolsistas', 'texto', '1'),
        ]
    )
    capturar(tela.pagina, 'edital-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Edital cadastrado com sucesso.')

    edital = Edital.objects.filter(titulo=EDITAL).first()
    assert edital is not None, 'a UI disse que salvou, mas não persistiu o edital'
    assert edital.publicado, 'o edital nasceu com "Publicado" desmarcado; a doc afirma que abre as inscrições direto'

    tela.ir(f'/pesquisa/edital/{edital.pk}/')
    tela.ver_titulo(EDITAL)
    anotar_tela('edital-pagina', tela)

    # Etapa 2 — plano de oferta por campus (define quantas bolsas cada campus terá).
    tela.clicar_aba('Plano de Oferta por Campus')
    tela.ver_botao('Adicionar Oferta')
    tela.clicar_botao('Adicionar Oferta')
    anotar_tela('oferta-formulario', tela)
    # O campo Campi é o `FilteredSelectMultiple` do admin; o rótulo fica fora do selector,
    # então o `_PREENCHEDORES` da `Tela` não o encontra (medido nesta rodada).
    adicionar_ao_filteredselect(tela.pagina, 'id_campi_from', 'CZN')
    tela.preencher_formulario(
        [
            ('Bolsas de Iniciação Científica', 'texto', '2'),
            ('Bolsas para Pesquisador', 'texto', '2'),
        ]
    )
    tela.clicar_botao('Enviar')
    tela.sucesso('Oferta(s) adicionada(s) com sucesso.')
    # Asserção no banco: o `form.is_valid()` do `OfertaProjetoPesquisaFormMultiplo` só garante
    # que algo foi submetido — esta checagem confirma que a oferta do campus escolhido (CZN)
    # realmente persistiu, senão a etapa 2 da doc descreveria um plano de oferta que não
    # vincula o campus.
    from rh.models import UnidadeOrganizacional

    uo_czn = UnidadeOrganizacional.objects.suap().get(sigla='CZN')
    assert BolsaDisponivel.objects.filter(edital=edital, uo=uo_czn).exists(), 'a UI disse que adicionou a oferta, mas não persistiu para o campus CZN'
    # Volta à página do edital de forma explícita (o redirect após o submit já o faz, mas
    # o estado pós-redirect das abas montadas por JS é mais confiável com navegação nova).
    tela.ir(f'/pesquisa/edital/{edital.pk}/')
    tela.ver_titulo(EDITAL)

    # Etapa 3 — fonte de recursos: o teto que cada projeto aprovado poderá gastar na rubrica.
    tela.clicar_aba('Fonte de Recursos')
    tela.clicar_botao('Adicionar Recurso')
    popup = tela.popup()
    anotar_tela('recurso-formulario', popup)
    popup.preencher_formulario(
        [
            ('Origem', 'lista', 'PROPI'),
            ('Valor disponível por projeto (R$)', 'texto', '10.000,00'),
            ('Despesa', 'autocomplete', 'Auxílio Financeiro a Estudantes'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Recurso adicionado com sucesso.')

    # Etapa 4 — critérios que os avaliadores vão pontuar.
    tela.ir(f'/pesquisa/edital/{edital.pk}/')
    tela.clicar_aba('Critérios de Avaliação da Qualificação do Projeto')
    tela.clicar_botao('Adicionar Critério de Avaliação')
    popup = tela.popup()
    anotar_tela('criterio-formulario', popup)
    popup.preencher_formulario(
        [
            ('Descrição', 'textarea', 'Adequação da proposta ao tema do edital'),
            ('Pontuação Máxima', 'texto', '10,00'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Critério de avaliação adicionado com sucesso.')
    tela.esperar()

    assert Recurso.objects.filter(edital=edital).exists(), 'fonte de recurso não persistiu'
    assert CriterioAvaliacao.objects.filter(edital=edital).exists(), 'critério não persistiu'

    # Etapa 5 — comissão de avaliação (os possíveis avaliadores do edital).
    tela.ir('/admin/pesquisa/comissaoeditalpesquisa/')
    tela.ver_titulo('Comissões de Avaliação')
    anotar_tela('comissao-listagem', tela)
    tela.ver_botao('Adicionar Comissão de Avaliação')
    tela.clicar_botao('Adicionar Comissão de Avaliação')
    tela.ver_botao('Por Indicação de Nomes')
    tela.clicar_botao('Por Indicação de Nomes')
    tela.esperar()  # o clique navega para o formulário de comissão; aguarda assentar antes de ler/capturar
    anotar_tela('comissao-formulario', tela)
    capturar(tela.pagina, 'comissao-formulario')
    tela.preencher_formulario(
        [
            ('Filtrar por Edital', 'lista', str(edital)),
            ('Campus', 'lista', 'CZN'),
            ('Membro', 'autocomplete multiplo', 'Avaliador Um Doc'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    # Edição: incluir mais um avaliador na comissão.
    tela.ir('/admin/pesquisa/comissaoeditalpesquisa/')
    tela.linha(str(edital)).clicar_icone('edição')
    anotar_tela('comissao-edicao', tela)
    tela.preencher_formulario([('Membro', 'autocomplete multiplo', 'Avaliador Dois Doc')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Atualização realizada com sucesso.')
    assert ComissaoEditalPesquisa.objects.filter(edital=edital).exists(), 'comissão não persistiu'
    capturar(tela.pagina, 'comissao-listagem')


# --------------------------------------------------------------------------------------
# Tarefa 2 — o coordenador submete o projeto de pesquisa
# --------------------------------------------------------------------------------------


def test_submeter_projeto(logado_doc, capturar):
    """Tarefa 2 — da equipe ao envio: o coordenador completa o projeto e o envia."""
    from pesquisa.models import Desembolso, Etapa, ItemMemoriaCalculo, Meta, Participacao, Projeto

    edital = _edital()
    marcar_periodo(edital, 'inscricao')

    tela = Tela(logado_doc('coord_projeto')).ir('/pesquisa/editais_abertos/')
    tela.ver_titulo('Editais de Pesquisa e de Inovação com Inscrições Abertas')
    anotar_tela('editais-abertos', tela)
    capturar(tela.pagina, 'editais-abertos')
    tela.ver_botao('Adicionar Projeto')
    tela.clicar_botao('Adicionar Projeto')
    tela.ver_titulo('Adicionar Projeto')
    anotar_tela('projeto-formulario', tela)
    tela.preencher_formulario(
        [
            ('Campus', 'autocomplete', 'CZN'),
            ('Título do projeto', 'texto', PROJETO),
            ('Início da Execução', 'data', _formatar_data(10)),
            ('Término da Execução', 'data', _formatar_data(300)),
            ('Área do Conhecimento', 'lista', 'MATEMÁTICA (CIÊNCIAS EXATAS E DA TERRA)'),
            ('Grupo de Pesquisa', 'autocomplete', 'Grupo de Pesquisa'),
            ('Palavras-Chaves', 'texto', 'palavras 1; palavras 2'),
            ('Resumo', 'texto rico', 'Resumo do projeto'),
            ('Introdução', 'texto rico', 'Introdução do projeto'),
            ('Justificativa', 'texto rico', 'Justificativa do projeto'),
            ('Fundamentação Teórica', 'texto rico', 'Fundamentação teórica do projeto'),
            ('Objetivo Geral', 'texto rico', 'Objetivo geral do projeto'),
            ('Metodologia da execução do projeto', 'texto rico', 'Metodologia do projeto'),
            ('Acompanhamento e avaliação do projeto durante a execução', 'texto rico', 'Acompanhamento do projeto'),
            ('Resultados Esperados', 'texto rico', 'Resultados esperados do projeto'),
            ('Referências Bibliográficas', 'texto rico', 'Referências do projeto'),
            ('O Coordenador Receberá Bolsa?', 'checkbox', 'marcar'),
            ('Necessita de Autorização do Comitê de Ética em Pesquisa (CEP)?', 'lista', 'Não'),
            ('Necessita de Autorização do Comitê de Ética no Uso de Animais (CEUA)?', 'lista', 'Não'),
            (
                'Necessita de Autorização do Sistema Nacional de Gestão do Patrimônio Genético e do Conhecimento Tradicional Associado (SISGEN)?',
                'lista',
                'Não',
            ),
            ('Necessita de Autorização do Sistema de Autorização e Informação em Biodiversidade (SISBIO)?', 'lista', 'Não'),
            ('É vinculado à um Laboratório Multiusuário?', 'lista', 'Não'),
        ]
    )
    capturar(tela.pagina, 'projeto-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Projeto cadastrado com sucesso.')

    projeto = Projeto.objects.filter(titulo=PROJETO).first()
    assert projeto is not None, 'a UI disse que salvou, mas não persistiu o projeto'
    assert projeto.data_conclusao_planejamento is None, 'projeto novo já nasceu enviado; a doc afirma que nasce rascunho'

    tela.ir(f'/pesquisa/projeto/{projeto.pk}/')
    tela.ver_titulo('Projeto de Pesquisa')
    anotar_tela('projeto-pagina', tela)
    capturar(tela.pagina, 'projeto-pagina')

    # Equipe: um servidor e um aluno.
    tela.clicar_aba('Equipe')
    tela.ver_botao('Adicionar Servidor')
    tela.clicar_botao('Adicionar Servidor')
    popup = tela.popup()
    anotar_tela('participante-servidor', popup)
    popup.preencher_formulario(
        [
            ('Vínculo', 'lista', 'Bolsista'),
            ('Carga Horária', 'texto', '6'),
            ('Participante', 'autocomplete', 'Servidor Projeto Doc'),
            ('Data de Entrada', 'data', _formatar_data(0)),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Participante adicionado com sucesso.')

    tela.clicar_botao('Adicionar Aluno')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Vínculo', 'lista', 'Bolsista'),
            ('Carga Horária', 'texto', '6'),
            ('Participante', 'autocomplete', 'Aluno Projeto Doc'),
            ('Data de Entrada', 'data', _formatar_data(0)),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Participante adicionado com sucesso.')
    capturar(tela.pagina, 'projeto-equipe')

    # Metas e atividades.
    tela.clicar_aba('Objetivos específicos')
    tela.ver_botao('Adicionar Meta')
    tela.clicar_botao('Adicionar Meta')
    popup = tela.popup()
    anotar_tela('meta-formulario', popup)
    popup.preencher_formulario([('Ordem', 'texto', '1'), ('Descrição', 'textarea', META)])
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Meta adicionada com sucesso.')

    tela.ver_botao('Adicionar Atividade')
    tela.clicar_botao('Adicionar Atividade')
    popup = tela.popup()
    anotar_tela('atividade-formulario', popup)
    popup.preencher_formulario(
        [
            ('Ordem', 'texto', '1'),
            ('Descrição', 'textarea', ATIVIDADE),
            ('Resultados Esperados', 'textarea', 'Resultados da atividade'),
            ('Responsável', 'lista', 'Servidor Projeto Doc'),
            ('Início da Execução', 'data', _formatar_data(30)),
            ('Fim da Execução', 'data', _formatar_data(60)),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Etapa adicionada com sucesso.')
    capturar(tela.pagina, 'projeto-objetivos')

    # Plano de aplicação: a memória de cálculo da despesa.
    tela.clicar_aba('Plano de Aplicação')
    tela.ver_botao('Adicionar Memória de Cálculo')
    tela.clicar_botao('Adicionar Memória de Cálculo')
    popup = tela.popup()
    anotar_tela('memoria-formulario', popup)
    popup.preencher_formulario(
        [
            ('Despesa', 'autocomplete', 'Auxílio Financeiro a Estudantes'),
            ('Descrição', 'textarea', DESPESA_MEMORIA),
            ('Unidade de Medida', 'texto', 'Unidade'),
            ('Quantidade', 'texto', '1'),
            ('Valor Unitário (R$)', 'texto', '10.000,00'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Item adicionado com sucesso.')

    # Plano de desembolso: quando o gasto previsto será executado.
    tela.clicar_aba('Plano de Desembolso')
    tela.ver_botao('Adicionar Item')
    tela.clicar_botao('Adicionar Item')
    popup = tela.popup()
    anotar_tela('desembolso-formulario', popup)
    item = ItemMemoriaCalculo.objects.get(projeto=projeto, descricao=DESPESA_MEMORIA)
    popup.preencher_formulario(
        [
            ('Mémoria de Cálculo', 'lista', str(item)),
            ('Ano', 'autocomplete', str(HOJE.year)),
            ('Mês', 'lista', '1'),
            ('Valor (R$)', 'texto', '1.000,00'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Desembolso adicionado com sucesso.')

    assert Participacao.objects.filter(projeto=projeto).count() >= 2, 'equipe não persistiu'
    assert Meta.objects.filter(projeto=projeto).exists(), 'metas não persistidas'
    assert Etapa.objects.filter(meta__projeto=projeto).exists(), 'atividades não persistidas'
    assert Desembolso.objects.filter(item__projeto=projeto).exists(), 'desembolso não persistiu'

    # Envio: encerra o planejamento e submete o projeto à pré-seleção.
    tela.ir(f'/pesquisa/projeto/{projeto.pk}/')
    tela.ver_botao('Enviar Projeto')
    capturar(tela.pagina, 'projeto-envio')
    tela.clicar_botao('Enviar Projeto')
    tela.sucesso('Projeto enviado com sucesso.')
    projeto.refresh_from_db()
    assert projeto.data_conclusao_planejamento is not None, 'a UI disse que enviou, mas não marcou a submissão'


# --------------------------------------------------------------------------------------
# Tarefa 3 — o Coordenador de Pesquisa faz a pré-seleção
# --------------------------------------------------------------------------------------


def test_pre_selecionar_projeto(logado_doc, capturar):
    """Tarefa 3 — a verificação inicial do projeto submetido, com justificativa."""
    projeto = _projeto()
    marcar_periodo(projeto.edital, 'pre_selecao')

    tela = Tela(logado_doc('coord_pesquisa')).ir('/pesquisa/pre_avaliacao/pesquisa/')
    tela.ver_titulo('Editais')
    capturar(tela.pagina, 'pre-avaliacao-editais')
    tela.linha(EDITAL).clicar_icone('exibição')
    tela.ver_titulo(f'Pré-Seleção de Projetos - {EDITAL}')
    anotar_tela('pre-selecao-projetos', tela)
    capturar(tela.pagina, 'pre-selecao-projetos')
    tela.linha(PROJETO).ver_botao('Pré-selecionar')
    tela.linha(PROJETO).clicar_botao('Pré-selecionar')
    tela.ver_titulo(f'Justificativa da Pré-Avaliação - {PROJETO}')
    anotar_tela('pre-avaliacao-justificativa', tela)
    tela.preencher_formulario([('Justificativa da Pré-Avaliação', 'textarea', 'Projeto atende às exigências do edital.')])
    capturar(tela.pagina, 'pre-avaliacao-justificativa')
    tela.clicar_botao('Salvar')
    tela.sucesso('Projeto pré-avaliado com sucesso.')

    projeto.refresh_from_db()
    assert projeto.pre_aprovado, 'a UI disse que pré-selecionou, mas não persistiu'
    assert projeto.vinculo_supervisor is not None, 'o pré-avaliador não virou o supervisor padrão; a doc afirma que vira'


# --------------------------------------------------------------------------------------
# Tarefa 4 — indicação dos avaliadores de cada projeto
# --------------------------------------------------------------------------------------


def test_indicar_avaliadores(logado_doc, capturar):
    """Tarefa 4 — dentre a comissão, escolher quem avaliará este projeto."""
    from pesquisa.models import AvaliadorIndicado

    projeto = _projeto()
    marcar_periodo(projeto.edital, 'selecao')

    tela = Tela(logado_doc('diretor')).ir('/pesquisa/pre_avaliacao/selecionar_avaliadores/')
    tela.ver_titulo('Editais em Avaliação')
    anotar_tela('indicar-editais', tela)
    tela.linha(EDITAL).clicar_icone('exibição')
    tela.ver_titulo(f'Selecionar avaliadores dos Projetos do {EDITAL}')
    # A lista de projetos só aparece depois de submeter o filtro (`{% if form.is_bound %}`),
    # então "Enviar" é executado antes de procurar o projeto.
    tela.ver_botao('Enviar')
    tela.clicar_botao('Enviar')
    anotar_tela('selecionar-avaliadores', tela)
    capturar(tela.pagina, 'selecionar-avaliadores')
    tela.cartao(PROJETO).ver_botao('Selecionar avaliadores')
    tela.cartao(PROJETO).clicar_botao('Selecionar avaliadores')
    tela.ver_titulo(f'Indicar Avaliadores do Projeto {PROJETO}')
    # A lista de avaliadores só aparece após submeter o filtro (`{% if form.is_valid %}`).
    tela.clicar_botao('Enviar')
    anotar_tela('indicar-avaliadores', tela)
    capturar(tela.pagina, 'indicar-avaliadores')

    tela.selecionar_item('Avaliador Um Doc')
    tela.selecionar_item('Avaliador Dois Doc')
    tela.clicar_botao('Salvar')
    tela.sucesso('Avaliadores cadastrados com sucesso.')

    indicados = AvaliadorIndicado.objects.filter(projeto=projeto)
    assert indicados.count() >= 2, 'a UI disse que indicou, mas não persistiu'
    for avaliador in indicados:
        assert avaliador.vinculo.user.groups.filter(name='Avaliador Sistêmico de Projetos de Pesquisa').exists(), (
            'a indicação deixou de conceder o acesso de avaliador; a doc afirma que concede'
        )


# --------------------------------------------------------------------------------------
# Tarefa 5 — os avaliadores pontuam o projeto
# --------------------------------------------------------------------------------------


def test_avaliar_projeto(logado_doc, capturar):
    """Tarefa 5 — os dois avaliadores indicados registram a avaliação do projeto."""
    from pesquisa.models import Avaliacao

    projeto = _projeto()
    marcar_periodo(projeto.edital, 'selecao')
    criterios = list(projeto.edital.criterioavaliacao_set.all())
    assert criterios, 'edital sem critérios; a avaliação não tem o que pontuar'

    for papel in ('avaliador1', 'avaliador2'):
        tela = Tela(logado_doc(papel)).ir('/pesquisa/avaliacao/')
        tela.ver_titulo('Editais em Avaliação')
        tela.clicar_link(EDITAL)
        tela.ver_titulo('Seleção de Projetos')
        anotar_tela(f'{papel}-selecao', tela)
        capturar(tela.pagina, 'avaliacao-selecao')
        tela.linha(PROJETO).ver_botao('Avaliar')
        tela.linha(PROJETO).clicar_botao('Avaliar')
        tela.ver_botao('Avaliar Projeto')
        tela.clicar_botao('Avaliar Projeto')
        tela.ver_titulo(f'Avaliar Projeto - {PROJETO}')
        anotar_tela('avaliar-projeto', tela)
        capturar(tela.pagina, 'avaliar-projeto')
        dados = [('Parecer', 'textarea', f'Parecer do {papel}')]
        for criterio in criterios:
            dados.append((criterio.descricao, 'lista', '10.0'))
        tela.preencher_formulario(dados)
        tela.clicar_botao('Enviar')
        tela.sucesso('Projeto avaliado com sucesso.')

    assert Avaliacao.objects.filter(projeto=projeto).count() == 2, 'as duas avaliações não persistiram'


# --------------------------------------------------------------------------------------
# Tarefa 6 — distribuição das bolsas do edital
# --------------------------------------------------------------------------------------


def test_distribuir_bolsas(logado_doc, capturar):
    """Tarefa 6 — confirmar a distribuição automática das bolsas do edital por campus."""
    projeto = _projeto()
    marcar_periodo(projeto.edital, 'distribuicao')

    tela = Tela(logado_doc('diretor')).ir('/pesquisa/distribuir_bolsas/')
    tela.ver_titulo('Distribuição de Bolsas dos Projetos de Pesquisa')
    anotar_tela('distribuicao-bolsas', tela)
    capturar(tela.pagina, 'distribuicao-bolsas')
    # Para o Diretor de Pesquisa (`uos is None`), a linha do edital de Campus mostra um link
    # com o nome da unidade (não um botão "Gerenciar Bolsas"), que leva ao gerenciamento.
    link_gerenciar = tela.pagina.locator(f'//tr[contains(normalize-space(.), "{EDITAL}")]//a[contains(@href, "gerenciar_bolsas")]').first
    expect(link_gerenciar).to_be_visible()
    link_gerenciar.click()
    tela.ver_titulo('Gerenciamento de Bolsas dos Projetos de Pesquisa')
    anotar_tela('gerenciar-bolsas', tela)
    capturar(tela.pagina, 'gerenciar-bolsas')
    tela.ver_botao('Salvar')
    tela.clicar_botao('Salvar')
    tela.sucesso('Bolsas salvas com sucesso.')

    projeto.refresh_from_db()
    assert projeto.aprovado, 'a distribuição não aprovou o projeto classificado'


# --------------------------------------------------------------------------------------
# Tarefa 7 — registro da execução do projeto
# --------------------------------------------------------------------------------------


def test_registrar_execucao(logado_doc, capturar):
    """Tarefa 7 — o coordenador registra a execução: atividades, fotos, gastos e relatório."""
    from pesquisa.models import FotoProjeto, RegistroExecucaoEtapa, RegistroGasto, RelatorioProjeto

    projeto = _projeto()
    marcar_periodo(projeto.edital, 'execucao')
    etapa = projeto.meta_set.first().etapa_set.first()

    tela = Tela(logado_doc('coord_projeto')).ir(f'/pesquisa/projeto/{projeto.pk}/')
    tela.ver_titulo('Projeto de Pesquisa')

    # Execução da atividade.
    tela.clicar_aba('Objetivos específicos')
    tela.linha(ATIVIDADE).ver_botao('Registrar Execução')
    tela.linha(ATIVIDADE).clicar_botao('Registrar Execução')
    popup = tela.popup()
    anotar_tela('registro-execucao', popup)
    popup.preencher_formulario(
        [
            ('Indicadores Qualitativos', 'lista', 'Atendido'),
            ('Início da Execução', 'data', _formatar_data(30)),
            ('Fim da Execução', 'data', _formatar_data(60)),
            ('Descrição da Atividade Realizada', 'textarea', 'Execução da atividade conforme planejado.'),
        ]
    )
    capturar(tela.pagina, 'registro-execucao')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Execução registrada com sucesso.')
    assert RegistroExecucaoEtapa.objects.filter(etapa=etapa).exists(), 'execução da atividade não persistiu'

    # Foto do projeto.
    tela.clicar_aba('Fotos')
    tela.ver_botao('Adicionar Foto')
    tela.clicar_botao('Adicionar Foto')
    anotar_tela('foto-formulario', tela)
    capturar(tela.pagina, 'foto-formulario')
    tela.preencher_formulario([('Legenda', 'textarea', 'Legenda da foto'), ('Fotos', 'arquivo', 'arquivo.png')])
    tela.clicar_botao('Enviar')
    tela.sucesso('Foto adicionada com sucesso.')
    assert FotoProjeto.objects.filter(projeto=projeto).exists(), 'foto não persistiu'

    # Gasto: para cada desembolso, o registro do que ocorreu de fato.
    tela.clicar_aba('Plano de Desembolso')
    # A descrição da memória de cálculo aparece em várias linhas do DOM (abas não visíveis);
    # restringir à aba visível para não pegar o primeiro `tr` de uma aba oculta.
    linha_desembolso = tela.aba('Plano de Desembolso').linha(DESPESA_MEMORIA)
    linha_desembolso.ver_botao('Gerenciar Gasto')
    linha_desembolso.clicar_botao('Gerenciar Gasto')
    tela.ver_titulo('Gastos Registrados')
    anotar_tela('gastos-registrados', tela)
    tela.preencher_formulario(
        [
            ('Ano', 'lista', str(HOJE.year)),
            ('Mês', 'lista', '1'),
            ('Descrição', 'textarea', 'Pagamento da bolsa do aluno'),
            ('Quantidade', 'texto', '1'),
            ('Valor Unitário (R$)', 'texto', '200,00'),
            ('Observação', 'textarea', 'Registro do gasto efetivamente realizado.'),
        ]
    )
    capturar(tela.pagina, 'gastos-registrados')
    tela.clicar_botao('Salvar')
    tela.sucesso('Gasto registrado com sucesso.')
    assert RegistroGasto.objects.filter(desembolso__item__projeto=projeto).exists(), 'gasto não persistiu'

    # Relatório parcial.
    tela.ir(f'/pesquisa/projeto/{projeto.pk}/')
    tela.clicar_aba('Relatórios')
    tela.ver_botao('Adicionar Relatório')
    tela.clicar_botao('Adicionar Relatório')
    tela.ver_titulo('Adicionar Relatório')
    anotar_tela('relatorio-formulario', tela)
    capturar(tela.pagina, 'relatorio-formulario')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', 'Relatório parcial do projeto'),
            ('Tipo do Relatório', 'lista', 'Parcial'),
            ('Arquivo', 'arquivo', 'arquivo.pdf'),
            ('Observação', 'textarea', 'Relatório do primeiro semestre.'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Relatório adicionado com sucesso.')
    assert RelatorioProjeto.objects.filter(projeto=projeto, tipo=RelatorioProjeto.PARCIAL).exists(), 'relatório não persistiu'
    capturar(tela.pagina, 'projeto-execucao')


def test_registrar_frequencia_diaria(logado_doc, capturar):
    """Tarefa 7 (frequência) — o membro da equipe registra as atividades do dia."""
    from pesquisa.models import RegistroFrequencia

    projeto = _projeto()
    marcar_periodo(projeto.edital, 'execucao')

    tela = Tela(logado_doc('aluno')).ir('/pesquisa/meus_projetos/')
    tela.ver_titulo('Meus Projetos')
    tela.linha(PROJETO).clicar_icone('exibição')
    tela.ver_titulo('Projeto de Pesquisa')
    tela.clicar_aba('Registros de Frequência/Atividade')
    tela.ver_botao('Cadastrar Frequência/Atividade')
    tela.clicar_botao('Cadastrar Frequência/Atividade')
    tela.ver_titulo('Registrar Frequência/Atividade')
    anotar_tela('frequencia-formulario', tela)
    tela.preencher_formulario([('Descrição', 'textarea', 'Atividades realizadas no dia.'), ('Data', 'data', _formatar_data(0))])
    capturar(tela.pagina, 'frequencia-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Frequência/Atividade cadastrada com sucesso.')
    assert RegistroFrequencia.objects.filter(projeto=projeto).exists(), 'frequência não persistiu'


# --------------------------------------------------------------------------------------
# Tarefa 8 — o supervisor monitora a execução
# --------------------------------------------------------------------------------------


def test_monitorar_execucao(logado_doc, capturar):
    """Tarefa 8 — o supervisor valida as execuções de atividade e os gastos registrados."""
    from pesquisa.models import RegistroExecucaoEtapa, RegistroGasto

    projeto = _projeto()
    marcar_periodo(projeto.edital, 'execucao')

    registro_atividade = RegistroExecucaoEtapa.objects.get(etapa__meta__projeto=projeto, aprovado=False)
    registro_gasto = RegistroGasto.objects.get(desembolso__item__projeto=projeto, aprovado=False)

    tela = Tela(logado_doc('coord_pesquisa')).ir('/pesquisa/projetos_em_execucao/')
    tela.ver_titulo('Monitoramento')
    anotar_tela('monitoramento-lista', tela)
    capturar(tela.pagina, 'monitoramento-lista')
    tela.linha(PROJETO).ver_botao('Acompanhar Validação')
    tela.linha(PROJETO).clicar_botao('Acompanhar Validação')
    tela.ver_titulo('Validar Execução')
    anotar_tela('monitoramento-validar', tela)

    tela.clicar_aba('Metas')
    tela.linha(ATIVIDADE).ver_botao('Aprovar')
    tela.linha(ATIVIDADE).clicar_botao('Aprovar')
    tela.sucesso('Execução de atividade validada com sucesso.')
    registro_atividade.refresh_from_db()
    assert registro_atividade.aprovado, 'a UI disse que aprovou, mas não persistiu'

    tela.clicar_aba('Gastos')
    tela.linha(registro_gasto.descricao).ver_botao('Aprovar')
    tela.linha(registro_gasto.descricao).clicar_botao('Aprovar')
    tela.sucesso('Gasto validado com sucesso.')
    registro_gasto.refresh_from_db()
    assert registro_gasto.aprovado, 'a UI disse que aprovou o gasto, mas não persistiu'
    capturar(tela.pagina, 'monitoramento-validar')


# --------------------------------------------------------------------------------------
# Tarefa 9 — conclusão e finalização do projeto
# --------------------------------------------------------------------------------------


def test_concluir_e_finalizar(logado_doc, capturar):
    """Tarefa 9 — o coordenador registra e finaliza a conclusão; o supervisor emite o parecer.

    A ordem segue o que a tela valida: ``pode_finalizar_conclusao`` exige as atividades e
    os gastos já aprovados no monitoramento (tarefa 8), e ``pode_emitir_parecer`` exige o
    projeto já finalizado (``data_finalizacao_conclusao``) — por isso o coordenador finaliza
    ANTES de o supervisor emitir o parecer.
    """
    from pesquisa.models import RegistroConclusaoProjeto

    projeto = _projeto()
    marcar_periodo(projeto.edital, 'execucao')

    # Coordenador: registra a conclusão.
    tela = Tela(logado_doc('coord_projeto')).ir(f'/pesquisa/projeto/{projeto.pk}/')
    tela.clicar_aba('Conclusão')
    tela.ver_botao('Registrar/Editar Conclusão')
    tela.clicar_botao('Registrar/Editar Conclusão')
    popup = tela.popup()
    anotar_tela('conclusao-registrar', popup)
    popup.preencher_formulario(
        [
            ('Resultados Alcançados', 'textarea', 'Os resultados previstos foram alcançados.'),
            ('Disseminação dos Resultados', 'textarea', 'Resultados divulgados em evento científico.'),
            ('Observação', 'textarea', 'Observações finais sobre a execução.'),
        ]
    )
    capturar(tela.pagina, 'conclusao-registrar')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Conclusão do projeto registrada com sucesso.')
    assert RegistroConclusaoProjeto.objects.filter(projeto=projeto).exists(), 'conclusão não persistiu'

    # Coordenador: finaliza a conclusão (desembolsos/atividades já validados na tarefa 8).
    tela.ir(f'/pesquisa/projeto/{projeto.pk}/')
    tela.clicar_aba('Conclusão')
    tela.ver_botao('Finalizar Conclusão')
    capturar(tela.pagina, 'conclusao-finalizar')
    tela.clicar_botao('Finalizar Conclusão')
    tela.sucesso('Conclusão finalizada com sucesso.')
    projeto.refresh_from_db()
    assert projeto.data_finalizacao_conclusao is not None, 'a UI disse que finalizou, mas não persistiu'

    # Supervisor: emite o parecer de aprovação da conclusão já finalizada.
    tela = Tela(logado_doc('coord_pesquisa')).ir('/pesquisa/projetos_em_execucao/')
    tela.linha(PROJETO).clicar_botao('Acompanhar Validação')
    tela.ver_titulo('Validar Execução')
    tela.clicar_aba('Conclusão do Projeto')
    tela.ver_botao('Emitir parecer')
    tela.clicar_botao('Emitir parecer')
    popup = tela.popup()
    anotar_tela('conclusao-validar', popup)
    popup.preencher_formulario([('Aprovado', 'checkbox', 'marcar'), ('Observação', 'textarea', 'Conclusão aprovada pelo supervisor.')])
    capturar(tela.pagina, 'conclusao-validar')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Conclusão do projeto registrada com sucesso.')
    registro = RegistroConclusaoProjeto.objects.get(projeto=projeto)
    assert registro.dt_avaliacao is not None, 'a UI disse que aprovou a conclusão, mas não gravou a data'
    assert registro.aprovado, 'a UI disse que aprovou a conclusão, mas não persistiu'
