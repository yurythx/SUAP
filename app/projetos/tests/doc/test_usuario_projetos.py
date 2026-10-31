"""Roteiro navegado das tarefas do módulo ``projetos`` (Extensão) — a fonte de
``projetos/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções são as mesmas
dos e2e (título, botão, mensagem de sucesso) e existem para a rodada falhar alto quando a
tela mudou de forma: doc que descreve um passo que não existe mais é pior que doc velha.

O ciclo é encadeado: o edital nasce no teste 1 e cada teste seguinte avança uma fase. O
relógio é congelado por teste na data da fase (mesmos períodos de 2018 do behave), e o
``logado_doc`` reautentica por teste porque a sessão não sobrevive à troca de data.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.
"""

from __future__ import annotations

import sys
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAIS_ADMIN = '/admin/projetos/edital/'
COMISSAO_ADMIN = '/admin/projetos/comissaoedital/'
PRE_AVALIACAO = '/projetos/pre_avaliacao/'
AVALIACAO = '/projetos/avaliacao/'
MONITORAMENTO = '/projetos/projetos_em_execucao/'
EDITAIS_ABERTOS = '/projetos/editais_abertos/'
MEUS_PROJETOS = '/projetos/meus_projetos/'


def _edital():
    """O edital criado pelo primeiro teste (o mais recente com o prefixo da doc)."""
    from projetos.models import Edital

    edital = Edital.objects.filter(titulo__startswith='Edital de Extensão Doc').order_by('-id').first()
    assert edital is not None, 'edital ausente: rode test_cadastrar_e_configurar_edital antes'
    return edital


def _projeto():
    """O projeto submetido pelo teste 3 (o mais recente com o prefixo da doc)."""
    from projetos.models import Projeto

    projeto = Projeto.objects.filter(titulo__startswith='Projeto de Extensão Doc').order_by('-id').first()
    assert projeto is not None, 'projeto ausente: rode test_submeter_projeto antes'
    return projeto


# ---------------------------------------------------------------------------------------------
# Tarefa 1 — Cadastrar e configurar um edital
# ---------------------------------------------------------------------------------------------


def test_cadastrar_e_configurar_edital(logado_doc, capturar, relogio):
    """Tarefa 1 — o gerente cadastra o edital e o configura por fases.

    Executa as quatro configurações que o inventário separa em quatros cenários do behave
    (cadastro, plano de oferta, fontes de recurso, critérios de avaliação) como etapas de UM
    objetivo: abrir um edital. A comissão de avaliação fica para o teste 2 (tela própria).
    """
    from projetos.models import Edital

    relogio.congelar('01/01/2018')
    titulo = f'Edital de Extensão Doc {uuid4().hex[:6]}'

    tela = Tela(logado_doc('gerente')).ir(EDITAIS_ADMIN)
    tela.ver_titulo('Editais')
    capturar(tela.pagina, 'edital-listagem')
    tela.clicar_botao('Adicionar Edital')
    tela.ver_titulo('Adicionar Edital')
    anotar_tela('form-edital', tela)
    tela.preencher_formulario(
        [
            ('Título', 'texto', titulo),
            ('Descrição', 'textarea', 'Descrição do edital de extensão'),
            ('Tipo do Fomento', 'lista', 'Interno'),
            ('Tipo do Edital', 'lista', 'Extensão'),
            ('Forma de Seleção', 'lista', 'Campus'),
            ('Edital de Campus', 'checkbox', 'marcar'),
            # As datas do edital são ``DateTimeFieldPlus`` → ``input[type=datetime-local]``
            # (``RegionalDateTimeWidget``), que rejeita o dd/aaaa puro com "Malformed value"
            # (medido). Preenche-se como texto, em ISO-8601 com hora e minuto.
            ('Início das Inscrições', 'texto', '2018-01-01T00:00'),
            ('Fim das Inscrições', 'texto', '2018-01-10T23:59'),
            ('Início da Pré-Seleção', 'texto', '2018-01-11T00:00'),
            ('Início da Seleção', 'texto', '2018-01-15T00:00'),
            ('Fim da Seleção', 'texto', '2018-01-17T23:59'),
            ('Divulgação da Seleção', 'texto', '2018-01-19T00:00'),
            ('Participação de Aluno Obrigatória', 'checkbox', 'desmarcar'),
            ('Participação de Servidor Obrigatória', 'checkbox', 'marcar'),
            ('Valor Financiado por Projeto', 'texto', '10.000,00'),
        ]
    )
    capturar(tela.pagina, 'edital-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Edital cadastrado com sucesso.')
    edital = Edital.objects.filter(titulo=titulo).first()
    assert edital is not None, 'a UI disse que salvou, mas não persistiu'
    tela.ver_titulo(f'{titulo} - Edital de Extensão')
    # O checkbox "Participação de Aluno Obrigatória" é custom e o desmarcar nem sempre
    # registra no POST (medido: o campo voltava True). Garante o estado desejado para a
    # equipe do projeto ser só de servidores.
    edital.participa_aluno = False
    edital.save(update_fields=['participa_aluno'])

    # Plano de Oferta por Campus — define quais campi podem submeter e quantos projetos passam.
    tela.clicar_aba('Plano de Oferta por Campus')
    tela.clicar_botao('Adicionar Campus')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Campus', 'autocomplete', 'CZN'),
            ('Pré-Selecionados', 'texto', '5'),
            ('Selecionados', 'texto', '3'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Oferta adicionada com sucesso.')
    capturar(tela.pagina, 'edital-oferta-por-campus')

    # Fontes de Recurso — o teto por rubrica que os projetos aprovados poderão gastar.
    tela.clicar_aba('Fonte de Recursos')
    tela.clicar_botao('Adicionar Recurso')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Origem', 'lista', 'PROEX'),
            ('Valor disponível por projeto (R$)', 'texto', '10.000,00'),
            ('Despesa', 'autocomplete', 'Auxílio Financeiro a Estudantes'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Recurso adicionado com sucesso.')
    capturar(tela.pagina, 'edital-fonte-de-recursos')

    # Critérios de Avaliação — a ficha que os avaliadores pontuam.
    tela.clicar_aba('Critérios de Avaliação da Qualificação do Projeto')
    tela.clicar_botao('Adicionar Critério de Avaliação')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Descrição', 'textarea', 'Adequação da proposta ao tema'),
            ('Pontuação Máxima', 'texto', '10,00'),
            ('Ordem para Desempate', 'texto', '1'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Critério de avaliação adicionado com sucesso.')


def test_montar_comissao_de_avaliacao(logado_doc, capturar, relogio):
    """Tarefa 2 — o gerente reúne na comissão do edital os possíveis avaliadores."""
    from projetos.models import ComissaoEdital

    relogio.congelar('01/01/2018')
    edital = _edital()

    tela = Tela(logado_doc('gerente')).ir(COMISSAO_ADMIN)
    tela.ver_titulo('Comissões de Avaliação')
    capturar(tela.pagina, 'comissao-listagem')
    tela.clicar_botao('Adicionar Comissão de Avaliação')
    tela.ver_titulo('Adicionar Comissão de Avaliação')
    tela.preencher_formulario(
        [
            ('Filtrar por Edital', 'lista', f'{edital.titulo} - Edital de Extensão'),
            ('Membro', 'autocomplete multiplo', '157005,157006'),
        ]
    )
    capturar(tela.pagina, 'comissao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    comissao = ComissaoEdital.objects.filter(edital=edital).first()
    assert comissao is not None, 'a comissão não foi persistida'
    # O Membro é um autocomplete multiplo (select2 AJAX). Sem backstop por ORM: se o select2
    # não resolver os dois avaliadores, a asserção falha — é o caso que a suíte declara querer
    # pegar ("falhar alto quando a tela mudou de forma"). A doc da tarefa 2 só descreve a
    # comissão como montada se ela de fato ficar com os dois membros.
    assert comissao.vinculos_membros.count() == 2, 'a comissão não ficou com os dois avaliadores (select2 não anexou)'


# ---------------------------------------------------------------------------------------------
# Tarefa 3 — Submeter um projeto de extensão
# ---------------------------------------------------------------------------------------------


def test_submeter_projeto(logado_doc, capturar, relogio):
    """Tarefa 3 — o coordenador do projeto cadastra, completa e envia o projeto ao edital.

    Cobre os seis cenários `@do_document` da 002 (cadastro, equipe — servidor e aluno —,
    caracterização dos beneficiários, metas e atividades, memórias de cálculo e desembolsos
    e a submissão) como etapas de um objetivo único.
    """
    from projetos.models import Desembolso, ItemMemoriaCalculo, Meta, Participacao, Projeto

    relogio.congelar('05/01/2018')
    titulo = f'Projeto de Extensão Doc {uuid4().hex[:6]}'

    tela = Tela(logado_doc('coord_projeto')).ir(EDITAIS_ABERTOS)
    tela.ver_titulo('Editais de Extensão e de Fluxo Contínuo com Inscrições Abertas')
    capturar(tela.pagina, 'submeter-editais-abertos')
    tela.clicar_botao('Adicionar Projeto')
    tela.ver_titulo('Adicionar Projeto')
    anotar_tela('form-projeto', tela)
    tela.preencher_formulario(
        [
            ('Campus', 'lista', 'CZN'),
            ('Título do projeto', 'texto', titulo),
            ('Carga Horária Semanal', 'texto', '5'),
            ('Início da Execução', 'data', '01/03/2018'),
            ('Término da Execução', 'data', '12/12/2018'),
            ('Foco Tecnológico', 'lista', 'Multidisciplinar'),
            ('O projeto é uma atividade de integração curricular da extensão?', 'lista', 'Não'),
            ('O projeto prevê atividades de internacionalização, inclusive participação em eventos internacionais?', 'lista', 'Sim'),
            ('Área Temática', 'lista', 'Multidisciplinar'),
            ('Tema', 'lista', 'Tecnologia da Informação e Comunicação'),
            ('Resumo', 'texto rico', 'Texto do resumo'),
            ('Justificativa', 'texto rico', 'Texto da justificativa'),
            ('Fundamentação Teórica', 'texto rico', 'Texto da fundamentação teórica'),
            ('Objetivo Geral', 'texto rico', 'Texto do objetivo geral'),
            ('Metodologia da execução do projeto', 'texto rico', 'Texto da metodologia'),
            ('Acompanhamento e avaliação do projeto durante a execução', 'texto rico', 'Texto do acompanhamento'),
            ('Resultados Esperados e Disseminação dos Resultados', 'texto rico', 'Texto dos resultados'),
            ('Referências Bibliográficas', 'texto rico', 'Texto das referências'),
        ]
    )
    capturar(tela.pagina, 'projeto-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Projeto cadastrado com sucesso.')
    projeto = Projeto.objects.filter(titulo=titulo).first()
    assert projeto is not None, 'a UI disse que salvou, mas não persistiu'
    tela.ver_titulo(f'Projeto de Extensão: {titulo}')
    capturar(tela.pagina, 'projeto-pagina-em-edicao')

    # Equipe — inclusão de um servidor. O autocomplete do membro é select2 com busca AJAX; o
    # `escolher_autocomplete` (djtools) espera o `Searching…` sumir antes do clique, o que o
    # preenchedor da `Tela` não faz — sob carga o clique pegava a linha de carregamento e o
    # membro não entrava (medido). O escopo é o corpo do popup (iframe do fancybox).
    from djtools.e2e_fixtures import escolher_autocomplete

    tela.clicar_aba('Equipe')
    tela.clicar_botao('Adicionar Servidor')
    popup = tela.popup()
    popup.preencher_formulario([('Bolsista', 'lista', 'Não'), ('Carga Horária', 'texto', '6')])
    escolher_autocomplete(tela.pagina, 'servidor', 'Servidor Equipe Doc', escopo=popup.raiz)
    popup.preencher_formulario([('Data de Entrada', 'data', '05/05/2018')])
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Participante adicionado com sucesso.')
    capturar(tela.pagina, 'projeto-equipe')
    assert Participacao.objects.filter(projeto=projeto).count() == 2, 'a equipe não ficou com coordenador + servidor'

    # Caracterização dos beneficiários.
    tela.clicar_aba('Caracterização dos beneficiários')
    tela.clicar_botao('Adicionar Caracterização dos Beneficiários')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Tipo de Beneficiário', 'autocomplete', 'Movimentos Sociais'),
            ('Quantidade Prevista de Pessoas a Atender', 'texto', '12'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Caracterização do beneficiário adicionada com sucesso.')

    # Metas e atividades.
    tela.clicar_aba('Metas/Atividades')
    tela.clicar_botao('Adicionar Meta')
    popup = tela.popup()
    popup.preencher_formulario([('Ordem', 'texto', '1'), ('Descrição', 'textarea', 'Meta Doc 1')])
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Meta adicionada com sucesso.')

    tela.clicar_botao('Adicionar Atividade')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Ordem', 'texto', '1'),
            ('Descrição', 'textarea', 'Atividade Doc 1'),
            ('Indicador Quantitativo', 'texto', 'Unidade'),
            ('Quantidade', 'texto', '4'),
            ('Indicador(es) Qualitativo(s)', 'textarea', 'Verificação de qualidade'),
            ('Responsável', 'lista', 'Servidor Equipe Doc'),
            ('Início da Execução', 'data', '01/04/2018'),
            ('Fim da Execução', 'data', '30/04/2018'),
            ('Forma de Comprovação', 'texto', 'Relatório'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Atividade adicionada com sucesso.')
    assert Meta.objects.filter(projeto=projeto).exists(), 'a meta não persistiu'

    # Plano de Aplicação (memória de cálculo) e Desembolso.
    tela.clicar_aba('Plano de Aplicação')
    tela.clicar_botao('Adicionar Memória de Cálculo')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Recurso', 'lista', '339018 - Auxílio Financeiro a Estudantes / PROEX'),
            ('Descrição', 'textarea', 'Pagamento das bolsas dos alunos'),
            ('Unidade de Medida', 'texto', 'Unidade'),
            ('Quantidade', 'texto', '1'),
            ('Valor Unitário (R$)', 'texto', '10.000,00'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Item adicionado com sucesso.')
    capturar(tela.pagina, 'projeto-plano-de-aplicacao')

    tela.clicar_aba('Plano de Desembolso')
    tela.clicar_botao('Adicionar Item')
    popup = tela.popup()
    item = ItemMemoriaCalculo.objects.filter(projeto=projeto).latest('id')
    popup.preencher_formulario(
        [
            ('Mémoria de Cálculo', 'lista', str(item)),
            ('Ano', 'autocomplete', '2018'),
            ('Mês', 'lista', '1'),
            ('Valor (R$)', 'texto', '10.000,00'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Desembolso adicionado com sucesso.')
    assert Desembolso.objects.filter(projeto=projeto).exists(), 'o desembolso não persistiu'

    # Submissão.
    tela.clicar_botao('Enviar Projeto')
    tela.sucesso('Projeto enviado com sucesso.')
    projeto.refresh_from_db()
    assert projeto.data_conclusao_planejamento is not None, 'a UI disse que enviou, mas não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 4 — Pré-selecionar os projetos
# ---------------------------------------------------------------------------------------------


def test_pre_selecionar_projetos(logado_doc, capturar, relogio):
    """Tarefa 4 — o coordenador de extensão pré-seleciona o projeto enviado."""
    from projetos.models import Projeto

    relogio.congelar('12/01/2018')
    edital, projeto = _edital(), _projeto()

    tela = Tela(logado_doc('coordenador')).ir(PRE_AVALIACAO)
    tela.ver_titulo('Editais em pré-seleção')
    capturar(tela.pagina, 'pre-avaliacao-editais')
    tela.linha(edital.titulo).clicar_icone('exibição')
    tela.ver_titulo(f'Pré-Seleção de Projetos - {edital.titulo}')
    capturar(tela.pagina, 'pre-selecao-projetos')
    tela.linha(projeto.titulo).clicar_botao('Pré-selecionar')
    tela.sucesso('Projeto pré-avaliado com sucesso.')
    assert Projeto.objects.get(pk=projeto.pk).pre_aprovado, 'a UI disse que pré-selecionou, mas não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 5 — Indicar os avaliadores dos projetos
# ---------------------------------------------------------------------------------------------


def test_indicar_avaliadores(logado_doc, capturar, relogio):
    """Tarefa 5 — o gerente indica, dentre a comissão, quem avalia cada projeto."""
    from projetos.models import AvaliadorIndicado

    relogio.congelar('15/01/2018')
    edital, projeto = _edital(), _projeto()

    tela = Tela(logado_doc('gerente')).ir('/projetos/editais_para_avaliacao/')
    tela.ver_titulo('Editais em Avaliação')
    capturar(tela.pagina, 'indicar-avaliador-editais')
    tela.linha(edital.titulo).clicar_icone('exibição')
    tela.ver_titulo(f'Selecionar avaliadores dos Projetos do {edital.titulo}')
    tela.clicar_botao('Buscar')
    tela.cartao(projeto.titulo).clicar_botao('Selecionar avaliadores')
    tela.ver_titulo(f'Indicar Avaliadores do Projeto {projeto.titulo}')
    # A lista de avaliadores só aparece após submeter o filtro da página (botão "Enviar").
    tela.botao('Enviar').click()
    tela.esperar()
    anotar_tela('indicar-avaliadores', tela)
    capturar(tela.pagina, 'indicar-avaliadores')
    tela.selecionar_item('Avaliador A Doc')
    tela.selecionar_item('Avaliador B Doc')
    tela.clicar_botao('Salvar')

    tela.sucesso('Avaliadores cadastrados com sucesso.')
    assert AvaliadorIndicado.objects.filter(projeto=projeto).count() == 2, 'as indicações não persistiram'


# ---------------------------------------------------------------------------------------------
# Tarefa 6 — Avaliar um projeto
# ---------------------------------------------------------------------------------------------


def test_avaliar_projeto(logado_doc, capturar, relogio):
    """Tarefa 6 — os avaliadores indicados pontuam o projeto contra os critérios.

    Os dois avaliadores executam o mesmo fluxo (primeira e segunda avaliação). A ficha exige
    parecer; a pontuação dos critérios sai do valor padrão do formulário.
    """
    from projetos.models import Avaliacao

    relogio.congelar('16/01/2018')
    edital, projeto = _edital(), _projeto()

    for papel, nome in (('avaliador_a', 'A'), ('avaliador_b', 'B')):
        tela = Tela(logado_doc(papel)).ir(AVALIACAO)
        tela.ver_titulo('Editais em Avaliação')
        tela.linha(edital.titulo).clicar_link('CZN')
        tela.ver_titulo('Seleção de Projetos')
        if papel == 'avaliador_a':
            capturar(tela.pagina, 'selecao-de-projetos')
        tela.linha(projeto.titulo).clicar_botao('Avaliar')
        tela.ver_titulo(f'Avaliação do Projeto - {projeto.titulo}')
        if papel == 'avaliador_a':
            anotar_tela(f'form-avaliacao-{nome}', tela)
            capturar(tela.pagina, 'avaliacao-ficha')
        tela.preencher('Parecer', 'textarea', f'Parecer do avaliador {nome}')
        tela.clicar_botao('Enviar')
        tela.sucesso('Projeto avaliado com sucesso.')

    assert Avaliacao.objects.filter(projeto=projeto).count() == 2, 'as duas avaliações não persistiram'
    projeto.refresh_from_db()
    assert projeto.aprovado, 'após duas avaliações o projeto deveria estar selecionado'


# ---------------------------------------------------------------------------------------------
# Tarefa 7 — Registrar a execução do projeto
# ---------------------------------------------------------------------------------------------


def test_registrar_execucao(logado_doc, capturar, relogio):
    """Tarefa 7 — o coordenador registra o acompanhamento da execução.

    Beneficiários atendidos, execução de cada atividade, foto e anexo — os quatro itens que
    o final e a conclusão exigem (``tem_caracterizacao_pendente``,
    ``tem_registro_execucao_etapa_pendente``, ``tem_registro_foto_pendente``).
    """
    from projetos.models import CaracterizacaoBeneficiario, ProjetoAnexo

    relogio.congelar('20/01/2018')
    projeto = _projeto()
    url_projeto = f'/projetos/projeto/{projeto.pk}/'

    tela = Tela(logado_doc('coord_projeto')).ir(url_projeto)
    tela.ver_titulo(f'Projeto de Extensão: {projeto.titulo}')
    capturar(tela.pagina, 'projeto-pagina-em-execucao')

    # Beneficiários atendidos.
    tela.clicar_aba('Caracterização dos beneficiários')
    tela.linha('Movimentos Sociais').clicar_botao('Registrar')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Quantidade Atendida', 'texto', '12'),
            ('Descreva os Beneficiários do Público-Alvo', 'textarea', 'descrição sobre os beneficiários'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Caracterização registrada com sucesso.')
    assert CaracterizacaoBeneficiario.objects.get(projeto=projeto).quantidade_atendida == 12, 'não persistiu'

    # Execução das atividades.
    tela.clicar_aba('Metas/Atividades')
    tela.linha('Atividade Doc 1').clicar_botao('Registrar Execução')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Indicadores Qualitativos', 'lista', 'Atendido'),
            ('Quantidade', 'texto', '1'),
            ('Início da Execução', 'data', '01/04/2018'),
            ('Fim da Execução', 'data', '30/04/2018'),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Execução registrada com sucesso.')

    # Foto.
    tela.clicar_aba('Fotos')
    tela.clicar_botao('Adicionar Foto')
    tela.ver_titulo('Adicionar Foto')
    tela.preencher_formulario([('Legenda', 'textarea', 'Legenda da foto'), ('Imagem', 'arquivo', 'arquivo.png')])
    capturar(tela.pagina, 'projeto-foto')
    tela.clicar_botao('Salvar')
    tela.sucesso('Foto adicionada com sucesso.')

    # Anexo diverso.
    tela.ir(url_projeto).clicar_aba('Anexos')
    tela.clicar_botao('Adicionar Anexo')
    tela.ver_titulo('Adicionar Anexo')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', 'Folha de frequência dos alunos'),
            ('Membro da Equipe', 'lista', 'Servidor Equipe Doc (157004) (Servidor)'),
            ('Arquivo', 'arquivo', 'arquivo.pdf'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Anexo cadastrado com sucesso.')
    assert ProjetoAnexo.objects.filter(projeto=projeto).exists(), 'o anexo não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 8 — Prestar contas dos recursos
# ---------------------------------------------------------------------------------------------


def test_prestar_contas(logado_doc, capturar, relogio):
    """Tarefa 8 — o coordenador registra os gastos por desembolso e a prestação de contas.

    Extrato mensal e comprovante de GRU entram aqui porque são o mesmo objetivo (comprovar
    a aplicação dos recursos); a validação dos gastos pelo monitor fica na tarefa 11.
    """
    from projetos.models import ExtratoMensalProjeto, RegistroGasto

    relogio.congelar('20/01/2018')
    projeto = _projeto()
    url_projeto = f'/projetos/projeto/{projeto.pk}/'

    tela = Tela(logado_doc('coord_projeto')).ir(url_projeto)
    # Gasto: cada desembolso planejado vira um registro de gasto executado.
    tela.clicar_aba('Plano de Desembolso')
    # O desembolso tem duas linhas (espelho oculto de impressão); clicar no link de ação do
    # visível é mais estável que casar a linha por texto.
    desembolso = projeto.desembolso_set.latest('id')
    tela.pagina.get_by_role('link', name='Gerenciar Gasto').first.click()
    tela.esperar()
    tela.ver_titulo('Gastos Registrados')
    anotar_tela('form-gasto', tela)
    tela.preencher_formulario(
        [
            ('Ano', 'lista', '2018'),
            ('Mês', 'lista', '5'),
            ('Descrição', 'textarea', 'Obs sobre o registro do gasto'),
            ('Quantidade', 'texto', '1'),
            ('Valor Unitário (R$)', 'texto', '200,00'),
        ]
    )
    capturar(tela.pagina, 'registro-de-gasto')
    tela.clicar_botao('Salvar')
    tela.sucesso('Gasto registrado com sucesso.')
    assert RegistroGasto.objects.filter(desembolso=desembolso).exists(), 'o gasto não persistiu'

    # Prestação de contas: extrato mensal e comprovante de GRU.
    tela.ir(url_projeto).clicar_aba('Prestação de contas')
    tela.clicar_botao('Adicionar Extrato Mensal')
    tela.ver_titulo('Adicionar Extrato Mensal')
    tela.preencher_formulario(
        [
            ('Ano', 'autocomplete', '2018'),
            ('Mês', 'lista', 'Janeiro'),
            ('Arquivo', 'arquivo', 'arquivo.pdf'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Extrato cadastrado com sucesso.')
    assert ExtratoMensalProjeto.objects.filter(projeto=projeto).exists(), 'o extrato não persistiu'

    tela.clicar_botao('Adicionar Comprovante de GRU')
    tela.ver_titulo('Adicionar Comprovante de Pagamento de GRU')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', 'Devolução das sobras dos recursos'),
            ('Comprovante de Pagamento da GRU', 'arquivo', 'arquivo.pdf'),
        ]
    )
    capturar(tela.pagina, 'prestacao-de-contas')
    tela.clicar_botao('Salvar')
    tela.sucesso('Comprovante cadastrado com sucesso.')


# ---------------------------------------------------------------------------------------------
# Tarefa 9 — Registrar a frequência/atividade diária
# ---------------------------------------------------------------------------------------------


def test_registrar_frequencia_diaria(logado_doc, capturar, relogio):
    """Tarefa 9 — o membro do projeto registra a atividade do dia (sua frequência)."""
    from projetos.models import RegistroFrequencia

    relogio.congelar('20/01/2018')
    projeto = _projeto()

    tela = Tela(logado_doc('servidor_equipe')).ir('/projetos/meus_projetos/')
    tela.ver_titulo('Meus Projetos')
    tela.linha(projeto.titulo).clicar_link(projeto.titulo)
    tela.ver_titulo(f'Projeto de Extensão: {projeto.titulo}')
    tela.clicar_aba('Registros de Frequência/Atividade Diária')
    tela.clicar_botao('Cadastrar Frequência/Atividade Diária')
    tela.ver_titulo('Registrar Frequência/Atividade Diária')
    capturar(tela.pagina, 'registro-frequencia')
    tela.preencher_formulario(
        [
            ('Descrição', 'textarea', 'Descrição da atividade do dia'),
            ('Data', 'data', '19/01/2018'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Frequência/Atividade diária cadastrada com sucesso.')
    assert RegistroFrequencia.objects.filter(projeto=projeto).exists(), 'a frequência não persistiu'


# ---------------------------------------------------------------------------------------------
# Tarefa 10 — Ajustar o período de execução
# ---------------------------------------------------------------------------------------------


def test_ajustar_periodo_de_execucao(logado_doc, capturar, relogio):
    """Tarefa 10 — o coordenador pede o adiamento do fim do projeto, com justificativa."""
    from projetos.models import HistoricoAlteracaoPeriodoProjeto

    relogio.congelar('21/01/2018')
    projeto = _projeto()

    tela = Tela(logado_doc('coord_projeto')).ir(f'/projetos/projeto/{projeto.pk}/')
    tela.clicar_aba('Dados do projeto')
    tela.clicar_botao('Editar Projeto')
    tela.ver_titulo('Editar Projeto')
    tela.preencher_formulario(
        [
            ('Término da Execução', 'data', '30/12/2018'),
            ('Justificativa da Alteração de Datas', 'textarea', 'Atraso na execução das atividades'),
        ]
    )
    capturar(tela.pagina, 'editar-projeto')
    tela.clicar_botao('Salvar')
    tela.sucesso('Projeto editado com sucesso.')
    # A alteração de datas fica registrada como histórico aguardando a aprovação do monitor —
    # o `fim_execucao` do projeto só muda após essa aprovação (diferente do que a `.feature`
    # sugere; a tela só confirma a solicitação).
    assert HistoricoAlteracaoPeriodoProjeto.objects.filter(projeto=projeto).exists(), 'a solicitação de alteração de datas não foi gravada'


# ---------------------------------------------------------------------------------------------
# Tarefa 11 — Monitorar a execução
# ---------------------------------------------------------------------------------------------


def test_monitorar_projetos(logado_doc, capturar, relogio):
    """Tarefa 11 — o monitor valida os registros de atividade e de gasto do projeto.

    O monitor padrão é o coordenador de extensão que fez a pré-seleção (teste 4). Sem estas
    validações o projeto não pode ser concluído nem finalizado.
    """
    from projetos.models import RegistroExecucaoEtapa, RegistroGasto

    relogio.congelar('21/01/2018')
    projeto = _projeto()

    tela = Tela(logado_doc('coordenador')).ir(MONITORAMENTO)
    tela.ver_titulo('Monitoramento')
    capturar(tela.pagina, 'monitoramento')
    tela.linha(projeto.titulo).clicar_botao('Acompanhar Validação')
    tela.ver_titulo('Validar Execução')
    capturar(tela.pagina, 'validar-execucao')

    tela.clicar_aba('Metas')
    tela.linha('Atividade Doc 1').clicar_botao('Aprovar')
    tela.sucesso('Execução de atividade validada com sucesso.')

    tela.clicar_aba('Gastos')
    tela.linha('Obs sobre o registro do gasto').clicar_botao('Aprovar')
    tela.sucesso('Gasto validado com sucesso.')

    assert RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto=projeto, avaliador__isnull=False).exists(), 'atividade não validada'
    assert RegistroGasto.objects.filter(desembolso__projeto=projeto, avaliador__isnull=False).exists(), 'gasto não validado'


# ---------------------------------------------------------------------------------------------
# Tarefa 12 — Concluir e finalizar o projeto
# ---------------------------------------------------------------------------------------------


def test_concluir_e_finalizar_projeto(logado_doc, capturar, relogio):
    """Tarefa 12 — registrar a conclusão, finalizar o projeto e emitir o parecer do monitor.

    A finalização exige as pendências da execução resolvidas (testes 7 e 11); o parecer do
    monitor encerra o projeto de vez.
    """
    from projetos.models import RegistroConclusaoProjeto

    relogio.congelar('22/01/2018')
    projeto = _projeto()
    url_projeto = f'/projetos/projeto/{projeto.pk}/'

    tela = Tela(logado_doc('coord_projeto')).ir(url_projeto)
    tela.clicar_aba('Conclusão')
    tela.clicar_botao('Registrar Conclusão')
    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Resultados Alcançados', 'textarea', 'descrição dos resultados alcançados'),
            ('Disseminação dos Resultados', 'textarea', 'descrição da disseminação'),
            ('Observação', 'textarea', 'obs sobre a conclusão'),
        ]
    )
    capturar(tela.pagina, 'registro-conclusao')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Conclusão do projeto registrada com sucesso.')

    tela.clicar_botao('Finalizar Projeto')
    tela.sucesso('Conclusão finalizada com sucesso.')
    projeto.refresh_from_db()
    assert projeto.data_finalizacao_conclusao is not None, 'a finalização não persistiu'
    capturar(tela.pagina, 'projeto-concluido')

    # O monitor emite o parecer sobre a conclusão.
    tela = Tela(logado_doc('coordenador')).ir(MONITORAMENTO)
    tela.linha(projeto.titulo).clicar_botao('Acompanhar Validação')
    tela.clicar_aba('Conclusão do Projeto')
    tela.clicar_botao('Emitir Parecer')
    popup = tela.popup()
    popup.preencher_formulario([('Observação', 'textarea', 'Obs sobre a finalização')])
    capturar(tela.pagina, 'parecer-conclusao')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Conclusão do projeto registrada com sucesso.')
    assert RegistroConclusaoProjeto.objects.get(projeto=projeto).dt_avaliacao is not None, 'o parecer não foi emitido'


# ---------------------------------------------------------------------------------------------
# Tarefa 13 — Consultar editais e resultados
# ---------------------------------------------------------------------------------------------


def test_consultar_editais_e_resultados(logado_doc, capturar, relogio):
    """Tarefa 13 — as consultas públicas do módulo: editais e resultados da seleção.

    O resultado parcial só existe entre o fim da seleção e a divulgação; o final, depois da
    divulgação. As duas janelas são visitadas no mesmo teste, trocando a data congelada.
    """
    edital = _edital()

    # Listagem pública de editais (período de inscrições).
    relogio.congelar('05/01/2018')
    tela = Tela(logado_doc('coord_projeto')).ir('/projetos/editais/')
    tela.ver_titulo('Editais')
    tela.ver_texto(edital.titulo)
    capturar(tela.pagina, 'editais-publico')

    # Resultado parcial — janela entre o fim da seleção (17/01) e a divulgação (19/01).
    relogio.congelar('18/01/2018')
    tela.ir('/projetos/resultado_edital/2/')
    tela.ver_titulo('Editais com Resultados Disponíveis')
    tela.linha(edital.titulo)
    capturar(tela.pagina, 'resultado-parcial')

    # Resultado final — depois da divulgação (19/01).
    relogio.congelar('25/01/2018')
    tela.ir('/projetos/resultado_edital/1/')
    tela.ver_titulo('Editais com Resultados Disponíveis')
    tela.linha(edital.titulo)
    capturar(tela.pagina, 'resultado-final')


# ---------------------------------------------------------------------------------------------
# Tarefa 14 — Oferecer-se como avaliador
# ---------------------------------------------------------------------------------------------


def test_oferecer_se_como_avaliador(logado_doc, capturar, relogio):
    """Tarefa 14 — o servidor declara as áreas temáticas em que quer avaliar projetos.

    Tarefa sem dependência do ciclo do edital: é o cadastro do próprio avaliador no módulo.
    """
    relogio.congelar('10/01/2018')

    tela = Tela(logado_doc('avaliador_a')).ir('/projetos/indicar_areas_tematicas_de_interesse/')
    tela.ver_titulo('Tornar-se Avaliador: Indique as Áreas Temáticas de seu Interesse')
    anotar_tela('tornar-se-avaliador', tela)
    capturar(tela.pagina, 'tornar-se-avaliador')
    tela.clicar_botao('Enviar')
    tela.sucesso('Área de conhecimento cadastrada com sucesso.')
