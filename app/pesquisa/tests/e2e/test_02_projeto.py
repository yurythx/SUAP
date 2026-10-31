"""Fluxo: submissão do projeto de pesquisa (modo 2).

A feature 002 é a mais longa da cadeia: ela constrói o projeto inteiro — dados básicos,
equipe, metas, atividades, plano de aplicação, desembolso — e só no último passo o submete.
É a única funcionalidade que o **coordenador do projeto** (não o diretor) opera, e é onde o
projeto deixa de ser rascunho.

O que este arquivo pega: o editor rico dos 9 campos de texto longo (o `Tipo` "Texto Rico",
que era lacuna até #16983 e é o que faz este ser o módulo mais afetado por ela), o
`FilteredSelectMultiple`/autocomplete do formulário de submissão, a cadeia
equipe → meta → atividade → memória → desembolso sem a qual o envio é recusado, e o próprio
envio. Se qualquer elo sumir, ``concluir_planejamento`` passa a recusar em silêncio e as
features 003→011 não têm sobre o que agir.

Os testes são **sequenciais e na ordem da feature**: o projeto nasce em ``test_cadastro_do_projeto``
e cada teste seguinte acrescenta um pedaço que o envio exige.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 002 fixa: dentro das inscrições (01/01→10/01/2018) do edital da 001.
DATA = '08/01/2018'

EDITAIS_ABERTOS = '/pesquisa/editais_abertos/'
MEUS_PROJETOS = '/pesquisa/meus_projetos/'

TITULO_PROJETO = 'Título do projeto'


def _projeto(tela: Tela) -> Tela:
    """Meus Projetos → ícone de exibição → o projeto aberto.

    O ícone é o primeiro do DOM, e é por isso que ``pesquisa/tests/e2e/seed.py`` limpa a
    cadeia da execução anterior: com dois projetos acumulados, o ícone da linha 1 apontaria
    para o da run passada.
    """
    tela.ir(MEUS_PROJETOS)
    tela.ver_titulo('Meus Projetos')
    tela.clicar_icone('exibição')
    return tela.ver_titulo('Projeto de Pesquisa')


def test_cadastro_do_projeto(logado_pesquisa):
    """O coordenador abre o projeto no edital aberto e grava os dados básicos.

    Os nove campos de texto longo são **Texto Rico** — editor TinyMCE em ``iframe`` — e é o
    caminho que a ``Tela._preencher_texto_rico`` cobre copiando o conteúdo do editor de volta
    para o ``textarea`` antes do submit. Sem essa cópia o formulário salva com os campos
    vazios e a falha só apareceria no envio do projeto, longe da causa.

    O projeto nasce em rascunho ("em edição") de propósito: a feature 002 só o submete no
    último cenário, depois de equipe, metas e plano de aplicação.
    """
    from pesquisa.models import Projeto

    tela = Tela(logado_pesquisa('coordenador_projeto')).ir(EDITAIS_ABERTOS)
    tela.ver_titulo('Editais de Pesquisa e de Inovação com Inscrições Abertas')
    tela.clicar_botao('Adicionar Projeto')
    tela.ver_titulo('Adicionar Projeto')

    tela.preencher_formulario(
        [
            ('Campus', 'Autocomplete', 'CZN'),
            ('Título do projeto', 'Texto', TITULO_PROJETO),
            ('Início da Execução', 'Data', '01/03/2018'),
            ('Término da Execução', 'Data', '12/12/2018'),
            ('Área do Conhecimento', 'Lista', 'MATEMÁTICA (CIÊNCIAS EXATAS E DA TERRA)'),
            ('Grupo de Pesquisa', 'Autocomplete', 'Grupo de Pesquisa'),
            ('Palavras-Chaves', 'Texto', 'teste da palavra;'),
            ('Resumo', 'Texto Rico', 'Texto do Resumo'),
            ('Introdução', 'Texto Rico', 'Texto da Introdução'),
            ('Justificativa', 'Texto Rico', 'Texto da Justificativa'),
            ('Fundamentação Teórica', 'Texto Rico', 'Texto da Fundamentação Teórica'),
            ('Objetivo Geral', 'Texto Rico', 'Texto do objetivo Geral'),
            ('Metodologia da execução do projeto', 'Texto Rico', 'Texto da metodologia'),
            ('Acompanhamento e avaliação do projeto durante a execução', 'Texto Rico', 'Texto do acompanhamento'),
            ('Resultados Esperados', 'Texto Rico', 'Texto dos resultados'),
            ('Referências Bibliográficas', 'Texto Rico', 'Texto das referências'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Projeto cadastrado com sucesso.')
    projeto = Projeto.objects.filter(titulo=TITULO_PROJETO).first()
    assert projeto is not None, 'a UI disse que salvou, mas o projeto não persistiu'
    # O texto rico é a asserção que a mensagem de sucesso não dá: o editor grava no textarea
    # por JS, e um `fill` que não sincroniza deixa o campo vazio com a mensagem verde.
    assert 'Texto do Resumo' in projeto.resumo, f'a UI disse que salvou, mas o texto rico não chegou ao campo (resumo={projeto.resumo!r})'


def test_inclusao_de_servidor_na_equipe(logado_pesquisa):
    """O coordenador inclui o servidor na equipe, pelo popup da aba "Equipe"."""
    from pesquisa.models import Participacao

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Equipe')
    tela.clicar_botao('Adicionar Servidor')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Vínculo', 'Lista', 'Bolsista'),
            ('Carga Horária', 'Texto', '6'),
            ('Participante', 'Autocomplete', 'Servidor Projeto'),
            ('Data de Entrada', 'Data', '01/03/2018'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Participante adicionado com sucesso.')
    assert Participacao.objects.filter(projeto__titulo=TITULO_PROJETO, vinculo_pessoa__pessoa__nome='Servidor Projeto').exists(), (
        'a UI disse que salvou, mas o servidor não entrou na equipe'
    )


def test_inclusao_de_aluno_na_equipe(logado_pesquisa):
    """O coordenador inclui o aluno na equipe — o mesmo formulário, outro papel.

    Irmão de ``test_inclusao_de_servidor_na_equipe``: a feature 002 tem os dois cenários
    porque o botão e o campo ``Participante`` mudam de domínio (servidor x aluno), e é essa
    diferença que se afirma — não o fluxo, que é idêntico.
    """
    from pesquisa.models import Participacao

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Equipe')
    tela.clicar_botao('Adicionar Aluno')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Vínculo', 'Lista', 'Bolsista'),
            ('Carga Horária', 'Texto', '6'),
            ('Participante', 'Autocomplete', 'Aluno do Projeto'),
            ('Data de Entrada', 'Data', '01/03/2018'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Participante adicionado com sucesso.')
    assert Participacao.objects.filter(projeto__titulo=TITULO_PROJETO, vinculo_pessoa__pessoa__nome='Aluno do Projeto').exists(), (
        'a UI disse que salvou, mas o aluno não entrou na equipe'
    )


ALTERAR_COORDENADOR = '/pesquisa/alterar_coordenador/{}/'


def test_alterar_coordenador_em_inscricao_so_para_quem_a_tela_oferece(logado_pesquisa, projeto_do_fluxo):
    """#17573: em inscrição, trocar o coordenador não é para qualquer usuário.

    ``pode_editar_equipe_propi`` é verdadeiro para todos em inscrição, e era só ele que a view
    olhava: um servidor sem relação com o projeto abria (e enviava) a troca. Agora só o
    coordenador do projeto, o Coordenador de Pesquisa do campus e o Diretor; o Coordenador de
    Pesquisa de outro campus também leva 403 (papel local).
    """
    from pesquisa.models import Projeto

    projeto = projeto_do_fluxo()
    assert projeto.get_status() == Projeto.STATUS_EM_INSCRICAO, 'o projeto deveria estar em inscrição antes do envio'
    url = ALTERAR_COORDENADOR.format(projeto.pk)
    papeis = ('avaliador_1', 'coordenador_pesquisa_outro_campus', 'coordenador_projeto', 'coordenador_pesquisa', 'diretor')
    respostas = {papel: Tela(logado_pesquisa(papel)).buscar(url).status for papel in papeis}
    assert respostas == {
        'avaliador_1': 403,
        'coordenador_pesquisa_outro_campus': 403,
        'coordenador_projeto': 200,
        'coordenador_pesquisa': 200,
        'diretor': 200,
    }, respostas

    # O botão segue o mesmo predicado da view: quem leva 403 não o vê. O de outro campus nem abre o projeto (#17571).
    assert Tela(logado_pesquisa('coordenador_pesquisa_outro_campus')).buscar(f'/pesquisa/projeto/{projeto.pk}/').status == 403
    tela = Tela(logado_pesquisa('coordenador_pesquisa')).ir(f'/pesquisa/projeto/{projeto.pk}/')
    tela.ver_titulo('Projeto de Pesquisa')
    assert tela.loc(f'//a[@href="{url}" and normalize-space(.)="Substituir Coordenador"]').count() == 1


def test_cadastro_das_metas(logado_pesquisa):
    """O coordenador cadastra a primeira meta na aba "Objetivos específicos".

    A meta é o contêiner das atividades: a feature 007 (execução) só consegue registrar
    execução porque existe atividade dentro de meta.
    """
    from pesquisa.models import Meta

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Objetivos específicos')
    tela.clicar_botao('Adicionar Meta')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Ordem', 'Texto', '1'),
            ('Descrição', 'TextArea', 'Descrição da Meta 1'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Meta adicionada com sucesso.')
    assert Meta.objects.filter(projeto__titulo=TITULO_PROJETO, descricao='Descrição da Meta 1').exists(), (
        'a UI disse que salvou, mas a meta não persistiu'
    )


def test_cadastro_das_atividades(logado_pesquisa):
    """O coordenador cadastra a atividade dentro da meta — o alvo da execução da feature 007.

    O campo ``Responsável`` é uma lista de **participantes**, não de servidores: sem a equipe
    do teste anterior esta lista vem vazia e o popup não fecha. É a razão de a ordem da
    feature importar.
    """
    from pesquisa.models import Etapa

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Objetivos específicos')
    tela.clicar_botao('Adicionar Atividade')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Ordem', 'Texto', '1'),
            ('Descrição', 'TextArea', 'Descrição da Atividade 1'),
            ('Resultados Esperados', 'TextArea', 'Verificação de qualidade'),
            ('Responsável', 'Lista', 'Servidor Projeto'),
            ('Início da Execução', 'Data', '01/04/2018'),
            ('Fim da Execução', 'Data', '30/04/2018'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Etapa adicionada com sucesso.')
    assert Etapa.objects.filter(meta__projeto__titulo=TITULO_PROJETO, descricao='Descrição da Atividade 1').exists(), (
        'a UI disse que salvou, mas a atividade não persistiu'
    )


# O rótulo como o SUAP monta a linha de memória de cálculo na lista de desembolso:
# ``<código da natureza> - <nome da natureza> - <descrição da memória>``.
DESCRICAO_MEMORIA = 'Pagamento das bolsas de dois alunos, no valor de R$ 500,00 cada'
ROTULO_MEMORIA = f'339018 - Auxílio Financeiro a Estudantes - {DESCRICAO_MEMORIA}'


def test_cadastro_das_memorias_de_calculo(logado_pesquisa):
    """O coordenador detalha o gasto por rubrica no Plano de Aplicação.

    A memória de cálculo é o que dá origem ao desembolso seguinte e o teto que a execução da
    feature 007 não pode ultrapassar. O valor unitário sai como ``10.000,00`` — com ponto de
    milhar e vírgula decimal, o formato que o SUAP aceita em campo monetário — e é o que prova
    que o campo foi parseado em vez de gravado como texto.
    """
    from pesquisa.models import ItemMemoriaCalculo

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Plano de Aplicação')
    tela.clicar_botao('Adicionar Memória de Cálculo')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Despesa', 'Autocomplete', 'Auxílio Financeiro a Estudantes'),
            ('Descrição', 'TextArea', DESCRICAO_MEMORIA),
            ('Unidade de Medida', 'Texto', 'Unidade'),
            ('Quantidade', 'Texto', '1'),
            ('Valor Unitário (R$)', 'Texto', '10.000,00'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Item adicionado com sucesso.')
    memoria = ItemMemoriaCalculo.objects.filter(projeto__titulo=TITULO_PROJETO, descricao=DESCRICAO_MEMORIA).first()
    assert memoria is not None, 'a UI disse que salvou, mas a memória de cálculo não persistiu'
    assert str(memoria.valor_unitario).startswith('10000'), f'a UI disse que salvou, mas o valor gravou {memoria.valor_unitario}'


def test_cadastro_dos_desembolsos(logado_pesquisa):
    """O coordenador agenda quando pretende gastar, referenciando a memória de cálculo.

    A lista ``Mémoria de Cálculo`` (grafia da feature, com o acento trocado) só tem a memória
    do teste anterior — é ela que amarra o desembolso à rubrica, e é o que a feature 007 lê
    para oferecer o botão "Gerenciar Gasto".
    """
    from pesquisa.models import Desembolso

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Plano de Desembolso')
    tela.clicar_botao('Adicionar Item')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Mémoria de Cálculo', 'Lista', ROTULO_MEMORIA),
            ('Ano', 'Autocomplete', '2018'),
            ('Mês', 'Lista', '1'),
            ('Valor (R$)', 'Texto', '1.000,00'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Desembolso adicionado com sucesso.')
    assert Desembolso.objects.filter(item__projeto__titulo=TITULO_PROJETO).exists(), 'a UI disse que salvou, mas o desembolso não persistiu'


def test_submissao_do_projeto(logado_pesquisa):
    """O coordenador envia o projeto — o fim do rascunho e o começo de toda a cadeia seguinte.

    É o teste que fecha a feature 002, e vale pelo que ele reprova: ``concluir_planejamento``
    recusa quando falta meta, atividade, memória ou desembolso, e a recusa chega como erro na
    tela — não como projeto enviado. Por isso a asserção de situação no ORM vem depois da
    mensagem: ela é o que garante que as features 003→011 têm sobre o que agir.
    """
    from pesquisa.models import Projeto

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.ver_botao('Enviar Projeto')
    tela.clicar_botao('Enviar Projeto')

    tela.sucesso('Projeto enviado com sucesso.')
    projeto = Projeto.objects.get(titulo=TITULO_PROJETO)
    # ``Projeto`` não guarda a situação: ela é derivada por ``get_status()``. O que o envio
    # grava é a data de conclusão do planejamento, e é ela que tira o projeto de "Em edição".
    assert projeto.data_conclusao_planejamento is not None, 'a UI disse que enviou, mas o projeto continua em edição'
    assert projeto.meta_set.exists(), 'o projeto foi enviado sem meta'
    assert projeto.participacao_set.exists(), 'o projeto foi enviado sem equipe'
