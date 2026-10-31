"""Fluxo: os bolsistas e os documentos da equipe — registros de bolsa, lista mensal, lista de equipes, certificado e declarações.

* **Registros de bolsistas** (gerente) — a bolsa de extensão que o ``ae`` guarda para cada aluno
  bolsista de projeto aprovado em execução: nasce do ``Participacao.save``
  (``gerencia_bolsa_ae``) e o gerente corrige as datas ou a exclui.
* **Lista mensal de bolsistas** — os anexos mensais ligados a desembolso de "Auxílio financeiro
  a estudantes", com os dados bancários do bolsista (é a folha de pagamento da bolsa).
* **Lista de equipes** — as equipes dos projetos aprovados, com exportação para planilha.
* **Documentos** — certificado de participação (membro que saiu, ou projeto concluído),
  declaração de participação (membro ativo em execução) e declaração de orientação (servidor
  que orienta aluno). Sob teste o ``@documento`` devolve HTML (armadilha 20).
* ``get_json_dados_empresa`` — o JSON que preenche o formulário de visita técnica pelo CNPJ.

As sondas: quem não gerencia o edital não mexe em registro de bolsa; quem não é o membro nem
gerencia o projeto não emite o documento dele — e três leituras que vazam dados pessoais
(``xfail``): a lista de equipes, com CPF e conta bancária na planilha, abre para qualquer servidor
ou aluno; a declaração de orientação sai para qualquer um.
"""

from __future__ import annotations

import datetime
import io
from typing import TYPE_CHECKING

import pytest

from djtools.e2e_ui import Tela, esperar_desfecho_do_popup, marcar_documento
from projetos.tests.e2e.conftest import banco, categoria_bolsa_extensao, clicar_em, membro

if TYPE_CHECKING:
    from ae.models import ParticipacaoBolsa
    from projetos.models import Participacao, ProjetoAnexo
    from rh.models import PessoaJuridica


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
REGISTROS_BOLSISTAS = '/projetos/registros_bolsistas/'
EDITAR_REGISTRO = '/projetos/editar_registro_bolsista/{}/'
EXCLUIR_REGISTRO = '/projetos/excluir_registro_bolsista/{}/'
LISTA_MENSAL = '/projetos/lista_mensal_bolsistas/'
LISTAR_EQUIPES = '/projetos/listar_equipes_dos_projetos/'
CERTIFICADO = '/projetos/emitir_certificado_extensao_pdf/{}/'
DECLARACAO_PARTICIPACAO = '/projetos/emitir_declaracao_participacao_pdf/{}/'
DECLARACAO_ORIENTACAO = '/projetos/emitir_declaracao_orientacao_pdf/{}/'
DADOS_EMPRESA = '/projetos/get_json_dados_empresa/'
PROGRESSO_DA_TAREFA = '/djtools/process_progress/1/{}/'  # o arquivo que a tarefa (@task) gerou

MATRICULA_DO_ALUNO = '20191101015901'
CONTA = '98765-4'
DADOS_BANCARIOS = {'numero_agencia': '3293-X', 'tipo_conta': 'Conta Corrente', 'numero_conta': CONTA}


# ------------------------------------------------------------------ registros de bolsistas


@pytest.fixture
def bolsa_de_extensao(projeto_em_execucao) -> ParticipacaoBolsa:
    """A bolsa (``ae.ParticipacaoBolsa``) que o SUAP gera para o aluno bolsista do projeto aprovado em execução.

    Não é criada à mão: é o ``save`` da participação bolsista que a gera, contanto que exista a
    categoria de bolsa de extensão (sem ela, ``gerencia_bolsa_ae`` quebra). Vai embora com a
    participação, na cascata do projeto.
    """
    from ae.models import ParticipacaoBolsa

    categoria_bolsa_extensao()
    participacao = membro(projeto_em_execucao().projeto, 'aluno', vinculo='Bolsista', bolsa_concedida=True)
    bolsa = ParticipacaoBolsa.objects.filter(aluno_participante_projeto=participacao).first()
    assert bolsa is not None, 'a participação bolsista não gerou a bolsa no ae'
    return bolsa


def _filtrar_bolsistas(tela: Tela) -> Tela:
    tela.ir(REGISTROS_BOLSISTAS).ver_titulo('Registros de Bolsistas')
    return tela.preencher('Matrícula/Nome', 'texto', MATRICULA_DO_ALUNO).clicar_botao('Enviar').esperar()


def test_gerente_corrige_e_exclui_o_registro_de_bolsa(logado_projetos, bolsa_de_extensao):
    """ "Registros de Bolsistas": filtra o aluno → "Editar Registro" (popup, data de saída) → "Excluir Registro" (popup que exclui ao abrir)."""
    from ae.models import ParticipacaoBolsa

    projeto = bolsa_de_extensao.aluno_participante_projeto.projeto
    saida = datetime.date.today() + datetime.timedelta(days=60)
    tela = _filtrar_bolsistas(Tela(logado_projetos('gerente')))

    tela.cartao(projeto.titulo)
    clicar_em(tela, EDITAR_REGISTRO.format(bolsa_de_extensao.pk))
    popup = tela.popup().preencher('Data de Saída', 'data', saida.strftime('%d/%m/%Y'))
    popup.salvar_no_popup('Salvar').sucesso('Registro editado com sucesso.')
    bolsa_de_extensao.refresh_from_db()
    assert bolsa_de_extensao.data_termino == saida, 'a UI disse que editou, mas a data de saída da bolsa não mudou'

    tela = _filtrar_bolsistas(tela)
    marcar_documento(tela.pagina)
    clicar_em(tela, EXCLUIR_REGISTRO.format(bolsa_de_extensao.pk))  # `.btn.danger`: o `logado` aceita o confirm
    esperar_desfecho_do_popup(tela.pagina)
    Tela(tela.pagina).esperar().sucesso('Registro excluído com sucesso.')
    assert not ParticipacaoBolsa.objects.filter(pk=bolsa_de_extensao.pk).exists(), 'a UI disse que excluiu, mas a bolsa continua'


def test_registro_de_bolsa_e_so_do_gerente(logado_projetos, bolsa_de_extensao):
    """O Coordenador de Extensão (e o coordenador do projeto) não abre a lista nem mexe no registro — e a exclusão por GET não exclui."""
    from ae.models import ParticipacaoBolsa

    rotas = [REGISTROS_BOLSISTAS, EDITAR_REGISTRO.format(bolsa_de_extensao.pk), EXCLUIR_REGISTRO.format(bolsa_de_extensao.pk)]
    for papel in ('coordenador_extensao', 'coordenador_projeto'):
        tela = Tela(logado_projetos(papel))
        respostas = {rota: tela.buscar(rota).status for rota in rotas}
        assert respostas == dict.fromkeys(rotas, 403), f'{papel}: rotas que não barraram { {r: s for r, s in respostas.items() if s != 403} }'
    assert ParticipacaoBolsa.objects.filter(pk=bolsa_de_extensao.pk).exists(), 'uma rota que respondeu 403 excluiu a bolsa'


# ------------------------------------------------------------------ lista mensal de bolsistas


@pytest.fixture
def anexo_mensal_do_bolsista(projeto_em_execucao) -> ProjetoAnexo:
    """O anexo mensal do bolsista, ligado ao desembolso de "Auxílio Financeiro a Estudantes" (339018) do projeto."""
    from comum.tests.factories import AnoFactory
    from projetos.tests.factories import ProjetoAnexoFactory

    execucao = projeto_em_execucao()
    participacao = membro(execucao.projeto, 'aluno', instituicao=banco(), **DADOS_BANCARIOS)
    hoje = datetime.date.today()
    return ProjetoAnexoFactory(
        projeto=execucao.projeto,
        participacao=participacao,
        vinculo_membro_equipe=participacao.vinculo_pessoa,
        desembolso=execucao.desembolso,
        ano=AnoFactory(ano=hoje.year),
        mes=hoje.month,
    )


MESES = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')


def test_lista_mensal_traz_o_bolsista_com_os_dados_bancarios(logado_projetos, anexo_mensal_do_bolsista):
    hoje = datetime.date.today()
    tela = Tela(logado_projetos('gerente')).ir(LISTA_MENSAL)

    tela.ver_titulo('Lista Mensal de Bolsistas').ver_texto('Selecione o mês e o ano para exibir a lista de bolsistas.')
    tela.preencher_formulario([('Informe o Ano', 'lista', str(hoje.year)), ('Informe o Mês', 'lista', MESES[hoje.month - 1])])
    tela.clicar_botao('Enviar')
    tela.esperar().linha(anexo_mensal_do_bolsista.projeto.titulo).ver_texto('Aluno Extensão E2E').ver_texto(CONTA)


def test_lista_mensal_e_de_quem_ve_editais(logado_projetos, anexo_mensal_do_bolsista):
    """``projetos.view_edital``: o coordenador do projeto (Servidor) não abre a folha de bolsistas."""
    assert Tela(logado_projetos('coordenador_projeto')).buscar(LISTA_MENSAL).status == 403


# ------------------------------------------------------------------------ lista de equipes


def _planilha(tela: Tela) -> list[tuple]:
    """As linhas da planilha que a tarefa de exportação gerou (a tela cai em ``/djtools/process/<uuid>/``)."""
    import openpyxl

    uuid = tela.pagina.url.rstrip('/').rsplit('/', 1)[-1]
    resposta = tela.buscar(PROGRESSO_DA_TAREFA.format(uuid))
    assert resposta.status == 200, f'o arquivo da exportação não veio: {resposta.status}'
    return list(openpyxl.load_workbook(io.BytesIO(resposta.body())).active.iter_rows(values_only=True))


def test_coordenador_de_extensao_lista_e_exporta_as_equipes(logado_projetos, projeto_em_execucao):
    """Filtra pelo edital, vê a equipe e exporta a planilha — que traz CPF e dados bancários de cada membro."""
    projeto = projeto_em_execucao().projeto
    membro(projeto, 'segundo_avaliador', instituicao=banco(), **DADOS_BANCARIOS)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(LISTAR_EQUIPES)

    tela.ver_titulo('Lista de Equipes dos Projetos').ver_texto('Selecione as opções para a buscar as equipes dos projetos.')
    tela.preencher('Filtrar por Edital', 'lista', str(projeto.edital)).clicar_botao('Enviar')
    tela.esperar().ver_texto('1 projetos e 2 participantes encontrados').ver_texto(projeto.titulo).ver_texto('Segundo Avaliador E2E')

    tela.clicar_botao('Exportar para XLS')
    tela.esperar()
    linhas = _planilha(tela)
    assert (linhas[0][4], linhas[0][5], linhas[0][12], linhas[0][14]) == ('Nome', 'CPF', 'Banco', 'Conta')
    membro_na_planilha = [linha for linha in linhas if str(linha[4]).startswith('Segundo Avaliador E2E')]
    assert membro_na_planilha, f'o membro não saiu na planilha: {linhas}'
    assert membro_na_planilha[0][14] == CONTA


@pytest.mark.parametrize('papel', ['aluno', 'outro_coordenador'])
def test_lista_de_equipes_nao_abre_sem_permissao_de_relatorio(logado_projetos, projeto_em_execucao, papel):
    projeto = projeto_em_execucao().projeto
    resposta = Tela(logado_projetos(papel)).buscar(f'{LISTAR_EQUIPES}?edital={projeto.edital_id}&situacao=2&tipo_de_exibicao=1')

    assert resposta.status == 403, f'{papel} abriu a lista de equipes (status {resposta.status})'


# -------------------------------------------------------------------------- documentos


@pytest.fixture
def membro_que_saiu(projeto_em_execucao) -> Participacao:
    """O ``avaliador`` (que loga) que entrou no início da execução e saiu 10 dias depois — tem direito a certificado."""
    from projetos.models import HistoricoEquipe
    from projetos.tests.factories import HistoricoEquipeFactory

    projeto = projeto_em_execucao().projeto
    saida = projeto.inicio_execucao + datetime.timedelta(days=10)
    participacao = membro(projeto, 'avaliador', ativo=False, data_inativacao=saida)
    HistoricoEquipe.objects.filter(participante=participacao).update(data_movimentacao_saida=saida)
    HistoricoEquipeFactory(participante=participacao, tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, data_movimentacao=saida)
    return participacao


def test_membro_que_saiu_emite_o_proprio_certificado(logado_projetos, membro_que_saiu):
    projeto = membro_que_saiu.projeto
    tela = Tela(logado_projetos('avaliador')).ir(PROJETO.format(projeto.pk)).clicar_aba('Equipe')

    clicar_em(tela, CERTIFICADO.format(membro_que_saiu.pk))
    tela.ver_texto('CERTIFICADO DE PARTICIPAÇÃO EM PROJETO DE EXTENSÃO').ver_texto('Avaliador Extensão E2E').ver_texto(projeto.titulo)


@pytest.mark.parametrize('caso', ['estranho', 'sem anuência'])
def test_certificado_negado(logado_projetos, membro_que_saiu, caso):
    """Quem não é o membro nem gerencia o projeto, ou edital que exige anuência não dada: a view manda para o início com o aviso."""
    from projetos.models import Edital

    papel = 'outro_coordenador'
    if caso == 'sem anuência':
        Edital.objects.filter(pk=membro_que_saiu.projeto.edital_id).update(exige_anuencia=Edital.TODOS)
        papel = 'avaliador'
    tela = Tela(logado_projetos(papel))

    assert tela.buscar(CERTIFICADO.format(membro_que_saiu.pk)).status == 302
    tela.ir(CERTIFICADO.format(membro_que_saiu.pk)).erro('Você não tem permissão para este acesso.')


def test_coordenador_emite_a_declaracao_de_participacao_do_membro_ativo(logado_projetos, projeto_em_execucao):
    projeto = projeto_em_execucao().projeto
    participacao = membro(projeto, 'segundo_avaliador')
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk)).clicar_aba('Equipe')

    clicar_em(tela, DECLARACAO_PARTICIPACAO.format(participacao.pk))
    tela.ver_texto('DECLARAÇÃO').ver_texto('Segundo Avaliador E2E').ver_texto(projeto.titulo)


def test_estranho_nao_emite_declaracao_de_participacao(logado_projetos, projeto_em_execucao):
    participacao = membro(projeto_em_execucao().projeto, 'segundo_avaliador')
    tela = Tela(logado_projetos('outro_coordenador'))

    assert tela.buscar(DECLARACAO_PARTICIPACAO.format(participacao.pk)).status == 302
    tela.ir(DECLARACAO_PARTICIPACAO.format(participacao.pk)).erro('Você não tem permissão para ver isso.')


def test_membro_de_projeto_concluido_emite_declaracao_de_participacao(logado_projetos, projeto_em_execucao):
    from projetos.tests.factories import RegistroConclusaoProjetoFactory

    projeto = projeto_em_execucao().projeto
    participacao = membro(projeto, 'segundo_avaliador')
    RegistroConclusaoProjetoFactory(projeto=projeto)

    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(DECLARACAO_PARTICIPACAO.format(participacao.pk))
    assert resposta.status == 200, f'o coordenador do projeto concluído não emitiu a declaração do membro (status {resposta.status})'


@pytest.fixture
def orientador_de_aluno(projeto_em_execucao) -> Participacao:
    """O ``segundo_avaliador`` orientando o ``aluno`` desde o início da execução (orientação em aberto)."""
    from projetos.models import Participacao
    from projetos.tests.factories import HistoricoOrientacaoProjetoFactory

    projeto = projeto_em_execucao().projeto
    orientador = membro(projeto, 'segundo_avaliador')
    aluno = membro(projeto, 'aluno')
    Participacao.objects.filter(pk=aluno.pk).update(orientador=orientador)
    HistoricoOrientacaoProjetoFactory(orientado=aluno, orientador=orientador)
    return orientador


def test_coordenador_emite_a_declaracao_de_orientacao(logado_projetos, orientador_de_aluno):
    """O botão aparece no servidor que orienta; a declaração traz o orientador, o aluno e o projeto."""
    projeto = orientador_de_aluno.projeto
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk)).clicar_aba('Equipe')

    clicar_em(tela, DECLARACAO_ORIENTACAO.format(orientador_de_aluno.pk))
    tela.ver_texto('DECLARAÇÃO DE ORIENTAÇÃO').ver_texto('Segundo Avaliador E2E').ver_texto('Aluno Extensão E2E').ver_texto(projeto.titulo)


def test_estranho_nao_emite_declaracao_de_orientacao(logado_projetos, orientador_de_aluno):
    resposta = Tela(logado_projetos('outro_coordenador')).buscar(DECLARACAO_ORIENTACAO.format(orientador_de_aluno.pk))

    assert 'DECLARAÇÃO DE ORIENTAÇÃO' not in resposta.text(), 'estranho ao projeto emitiu a declaração de orientação de um membro'
    assert resposta.status in (302, 403), f'estranho ao projeto recebeu {resposta.status} na declaração de orientação'


# ----------------------------------------------------------------- JSON da visita técnica


@pytest.fixture
def empresa_visitada(projetos_seed) -> PessoaJuridica:
    from rh.tests.factories import PessoaJuridicaFactory

    return PessoaJuridicaFactory(nome='Escola Parceira de Extensão E2E')


@pytest.mark.parametrize('papel', ['gerente', 'coordenador_extensao'])
def test_json_dos_dados_da_empresa_pelo_cnpj(logado_projetos, empresa_visitada, papel):
    """O formulário de visita técnica busca a instituição pelo CNPJ (``VisitaTecnicaForm.js``) nesta rota."""
    resposta = Tela(logado_projetos(papel)).buscar(f'{DADOS_EMPRESA}?cnpj={empresa_visitada.cnpj}')

    assert resposta.status == 200
    assert resposta.json()['nome'] == empresa_visitada.nome, f'o JSON não trouxe a empresa do CNPJ: {resposta.json()}'


def test_json_da_empresa_so_para_quem_cadastra_visita(logado_projetos, empresa_visitada):
    """``projetos.add_visitatecnica``: o coordenador de projeto (Servidor) não consulta."""
    assert Tela(logado_projetos('coordenador_projeto')).buscar(f'{DADOS_EMPRESA}?cnpj={empresa_visitada.cnpj}').status == 403
