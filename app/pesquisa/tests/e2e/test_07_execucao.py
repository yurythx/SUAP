"""Fluxo: registro da execução do projeto (modo 2).

Aprovado e com bolsas distribuídas (006), o projeto entra em execução. Esta é a maior feature
do PESQUISA em cenários depois da 002, e a única em que **dois papéis diferentes** trabalham
sobre o mesmo projeto: o coordenador registra (atividades, fotos, gastos, anexos, relatórios) e
o **aluno** da equipe lança a própria frequência.

O que este arquivo pega: a cadeia de abas do projeto (Objetivos específicos → Fotos → Plano de
Desembolso → Anexos → Relatórios → Registros de Frequência/Atividade), o ``Arquivo`` dos cinco
uploads (o tipo que o behave resolvia pelo nome do arquivo e que aqui resolve pela extensão,
``e2e_ui.py:359-362``), o ``Texto Rico`` de novo, e o acesso do aluno ao projeto — a feature 007
é a única da cadeia em que o discente age, e por isso é a que prova que o papel ``Aluno``
enxerga o projeto em que participa.

Os testes são **sequenciais**: o gasto registrado aqui é o que a feature 008 valida, e a
atividade executada aqui é a que a 008 aprova.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 007 fixa: depois da divulgação da seleção (19/01), já em execução.
DATA = '20/01/2018'

MEUS_PROJETOS = '/pesquisa/meus_projetos/'

TITULO_PROJETO = 'Título do projeto'

DESCRICAO_ATIVIDADE = 'Descrição da Atividade 1'
DESCRICAO_MEMORIA = 'Pagamento das bolsas de dois alunos, no valor de R$ 500,00 cada'
ROTULO_MEMORIA = f'339018 - Auxílio Financeiro a Estudantes - {DESCRICAO_MEMORIA}'
OBSERVACAO_GASTO = 'Obs sobre o registro do gasto'


def _projeto(tela: Tela) -> Tela:
    """Meus Projetos → ícone de exibição → o projeto aberto."""
    tela.ir(MEUS_PROJETOS)
    tela.ver_titulo('Meus Projetos')
    tela.clicar_icone('exibição')
    return tela.ver_titulo('Projeto de Pesquisa')


def test_registro_da_execucao_das_atividades(logado_pesquisa):
    """O coordenador registra a execução com o indicador qualitativo — o alvo da validação da 008.

    O botão "Registrar Execução" vive na linha da atividade, não no topo da aba: recortar a
    linha é o que garante que o registro vai para a atividade certa quando o projeto tem mais
    de uma.
    """
    from pesquisa.models import RegistroExecucaoEtapa

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Objetivos específicos')

    tela.linha(DESCRICAO_ATIVIDADE)
    tela.ver_botao('Registrar Execução')
    tela.linha(DESCRICAO_ATIVIDADE).clicar_botao('Registrar Execução')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Indicadores Qualitativos', 'Lista', 'Atendido'),
            ('Início da Execução', 'Data', '01/04/2018'),
            ('Fim da Execução', 'Data', '30/04/2018'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Execução registrada com sucesso.')
    execucao = RegistroExecucaoEtapa.objects.filter(etapa__descricao=DESCRICAO_ATIVIDADE, etapa__meta__projeto__titulo=TITULO_PROJETO).first()
    assert execucao is not None, 'a UI disse que registrou, mas não há execução para a atividade'
    # O indicador qualitativo é o campo que a feature preenche e o que o supervisor da
    # feature 008 lê para aprovar; sem ele o registro fica sem o dado do cenário.
    assert execucao.tipo_indicador_qualitativo == RegistroExecucaoEtapa.ATENDIDO, (
        f'a UI disse que registrou, mas o indicador gravou {execucao.tipo_indicador_qualitativo!r}'
    )


def test_cadastro_das_fotos(logado_pesquisa):
    """O coordenador anexa uma foto com legenda à aba "Fotos" do projeto."""
    from pesquisa.models import FotoProjeto

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Fotos')
    tela.clicar_botao('Adicionar Foto')

    tela.preencher_formulario(
        [
            ('Legenda', 'TextArea', 'Legenda da foto'),
            ('Fotos', 'Arquivo', 'foto_projeto.png'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.sucesso('Foto adicionada com sucesso.')
    foto = FotoProjeto.objects.filter(projeto__titulo=TITULO_PROJETO, legenda='Legenda da foto').first()
    assert foto is not None, 'a UI disse que salvou, mas a foto não persistiu'
    assert foto.imagem, 'a UI disse que salvou, mas o arquivo da imagem não foi anexado'


def test_registro_dos_gastos(logado_pesquisa):
    """O coordenador registra o gasto do desembolso — o que a feature 008 aprova depois.

    O botão "Gerenciar Gasto" está na linha do desembolso, e é ele que amarra o gasto à rubrica
    do plano de desembolso. O ``Observação`` é o texto que a tela de monitoramento da 008 mostra
    para o supervisor identificar o gasto, e é por isso que o teste o afirma no ORM.
    """
    from pesquisa.models import RegistroGasto

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Plano de Desembolso')

    tela.linha(ROTULO_MEMORIA)
    tela.ver_botao('Gerenciar Gasto')
    tela.linha(ROTULO_MEMORIA).clicar_botao('Gerenciar Gasto')

    tela.ver_titulo('Gastos Registrados')
    tela.preencher_formulario(
        [
            ('Ano', 'Lista', '2018'),
            ('Mês', 'Lista', '5'),
            ('Descrição', 'TextArea', OBSERVACAO_GASTO),
            ('Quantidade', 'Texto', '1'),
            ('Valor Unitário (R$)', 'Texto', '200,00'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Gasto registrado com sucesso.')
    gasto = RegistroGasto.objects.filter(descricao=OBSERVACAO_GASTO).order_by('-id').first()
    assert gasto is not None, 'a UI disse que registrou, mas não há gasto com a observação do cenário'
    # O gasto pode vir ligado ao desembolso (o caminho da tela) e sempre ao item de memória de
    # cálculo; as duas pontas provam que ele foi parar no projeto certo.
    projeto = gasto.desembolso.item.projeto if gasto.desembolso_id else gasto.item.projeto
    assert projeto.titulo == TITULO_PROJETO, f'a UI disse que registrou, mas o gasto caiu no projeto {projeto.titulo!r}'
    assert str(gasto.mes) == '5', f'a UI disse que registrou, mas o mês gravou {gasto.mes!r}'


def test_cadastro_de_anexo_do_projeto(logado_pesquisa):
    """O coordenador anexa a folha de frequência vinculada a um membro da equipe.

    O campo ``Membro da Equipe`` é obrigatório e é o que distingue este upload dos outros: o
    anexo fica amarrado a uma participação, e o rótulo da lista traz o nome com a matrícula e o
    tipo entre parênteses — o formato que o ``Lista`` do behave usa como valor.
    """
    from pesquisa.models import ProjetoAnexo

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Anexos')
    tela.clicar_botao('Adicionar Anexo')

    tela.preencher_formulario(
        [
            ('Descrição', 'Texto', 'Folha de Frequência do aluno'),
            ('Membro da Equipe', 'Lista', 'Aluno do Projeto (20191101011081) (Aluno)'),
            ('Arquivo', 'Arquivo', 'Arquivo.pdf'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Anexo cadastrado com sucesso.')
    anexo = ProjetoAnexo.objects.filter(projeto__titulo=TITULO_PROJETO, descricao='Folha de Frequência do aluno').first()
    assert anexo is not None, 'a UI disse que salvou, mas o anexo não persistiu'
    assert anexo.arquivo_id, 'a UI disse que salvou, mas o arquivo do anexo está vazio'
    assert anexo.vinculo_membro_equipe_id, 'a UI disse que salvou, mas o anexo não ficou vinculado a nenhum membro da equipe'


def test_cadastro_de_relatorio_parcial(logado_pesquisa):
    """O coordenador cadastra um relatório parcial — o documento que a conclusão exige.

    O ``Tipo do Relatório`` ``Parcial`` é o que separa este do relatório final que a finalização
    (feature 010) requer aprovado; trocar o tipo aqui quebraria aquele passo em silêncio.
    """
    from pesquisa.models import RelatorioProjeto

    tela = Tela(logado_pesquisa('coordenador_projeto'))
    _projeto(tela)
    tela.clicar_aba('Relatórios')
    tela.clicar_botao('Adicionar Relatório')

    tela.ver_titulo('Adicionar Relatório')
    tela.preencher_formulario(
        [
            ('Descrição', 'Texto', 'Relatório parcial do projeto'),
            ('Tipo do Relatório', 'Lista', 'Parcial'),
            ('Arquivo', 'Arquivo', 'relatorio_parcial.pdf'),
            ('Observação', 'TextArea', 'Exemplo de cadastro do relatório parcial'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Relatório adicionado com sucesso.')
    relatorio = RelatorioProjeto.objects.filter(projeto__titulo=TITULO_PROJETO, descricao='Relatório parcial do projeto').first()
    assert relatorio is not None, 'a UI disse que salvou, mas o relatório não persistiu'
    assert relatorio.tipo == RelatorioProjeto.PARCIAL, f'a UI disse que salvou, mas o relatório ficou como {relatorio.tipo!r}'
    assert relatorio.arquivo, 'a UI disse que salvou, mas o PDF do relatório não foi anexado'


def test_registro_da_frequencia_diaria(logado_pesquisa):
    """O **aluno** da equipe lança a própria frequência no projeto.

    É o único cenário da cadeia em que o discente age, e o único que não passa por "Meus
    Projetos": a feature vai direto da página inicial ao projeto, pelo link do título. Isso
    torna este teste o que prova que o papel ``Aluno`` enxerga o projeto em que participa —
    e é a evidência que faltaria se o resto da suíte só exercitasse servidores.
    """
    from pesquisa.models import RegistroFrequencia

    tela = Tela(logado_pesquisa('aluno')).ir('/')
    tela.clicar_link(TITULO_PROJETO)
    tela.ver_titulo('Projeto de Pesquisa')

    tela.clicar_aba('Registros de Frequência/Atividade')
    tela.clicar_botao('Cadastrar Frequência/Atividade')

    tela.ver_titulo('Registrar Frequência/Atividade')
    tela.preencher_formulario(
        [
            ('Descrição', 'TextArea', 'Descrição da atividade do dia'),
            ('Data', 'Data', '20/02/2018'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Frequência/Atividade cadastrada com sucesso.')
    assert RegistroFrequencia.objects.filter(projeto__titulo=TITULO_PROJETO, descricao='Descrição da atividade do dia').exists(), (
        'a UI disse que salvou, mas a frequência não persistiu'
    )


ENCERRAR_PARTICIPACAO = '/pesquisa/remover_participante/{}/'
ATIVAR_PARTICIPANTE = '/pesquisa/ativar_participante/{}/'


def test_coordenador_de_pesquisa_de_outro_campus_nao_gerencia_a_equipe(logado_pesquisa, papeis, projeto_do_fluxo):
    """#17555: Encerrar/Ativar participante exigem o que a aba "Equipe" exige — inclusive o campus.

    O Coordenador de Pesquisa é papel local: o do CEN leva 403 nas duas rotas do projeto do CZN, e
    ``ativar_participante``, que grava por GET, não grava. O do CZN e o Diretor (sistêmico)
    continuam abrindo o formulário de encerramento.
    """
    from comum.utils import get_uo
    from pesquisa.models import HistoricoEquipe, Participacao, Projeto
    from pesquisa.tests.e2e.conftest import PAPEIS

    projeto = projeto_do_fluxo()
    vizinho = papeis[PAPEIS['coordenador_pesquisa_outro_campus']]
    # Pré-condições: sem elas o 403 viria de outro motivo e o teste não provaria o escopo.
    uo_vizinho = get_uo(vizinho)
    assert uo_vizinho is not None, 'o coordenador vizinho deveria ter campus'
    assert uo_vizinho != projeto.uo, 'o coordenador vizinho deveria ser de outro campus'
    assert projeto.get_status() != Projeto.STATUS_EM_INSCRICAO, 'a cadeia deveria ter o projeto já fora da inscrição'
    participacao = Participacao.objects.filter(projeto=projeto, responsavel=False, ativo=True).order_by('id').first()
    assert participacao is not None, 'a feature 002 deveria ter posto um membro não responsável na equipe'
    historico = HistoricoEquipe.objects.filter(participante=participacao).count()

    tela = Tela(logado_pesquisa('coordenador_pesquisa_outro_campus'))
    respostas = {rota: tela.buscar(rota.format(participacao.pk)).status for rota in (ENCERRAR_PARTICIPACAO, ATIVAR_PARTICIPANTE)}
    assert respostas == {ENCERRAR_PARTICIPACAO: 403, ATIVAR_PARTICIPANTE: 403}, respostas
    participacao.refresh_from_db()
    assert participacao.ativo, 'uma rota que deveria barrar mexeu na participação'
    assert HistoricoEquipe.objects.filter(participante=participacao).count() == historico, 'uma rota barrada gravou no histórico'

    for papel in ('coordenador_pesquisa', 'diretor'):
        status = Tela(logado_pesquisa(papel)).buscar(ENCERRAR_PARTICIPACAO.format(participacao.pk)).status
        assert status == 200, f'{papel} perdeu o encerramento de participação ({status})'
