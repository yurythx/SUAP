"""Fluxo: o que cada membro da equipe dá ou recebe fora das mãos do coordenador — anuência, termo e dados bancários.

* **Anuência da chefia** — edital que a exige ("De todos os servidores"): o Coordenador de
  Extensão do campus (ou o gerente) indica o chefe imediato do membro, o chefe defere ou indefere
  em "Participações Pendentes da Sua Anuência", e o gerente pode cancelá-la. Sem anuência o membro
  não recebe certificado nem declaração.
* **Termo de compromisso** — o próprio membro aceita, com a senha.
* **Dados bancários** — o próprio membro (o bolsista) cadastra, atrás do duplo fator; na aba
  "Equipe" só o coordenador, o Coordenador de Extensão do campus, o gerente e o dono os veem.

As rotas de anuência gravam por GET (``registrar_anuencia_participacao``, ``cancelar_anuencia``):
as sondas afirmam o 403 E que nada foi gravado.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import PAPEIS, banco, clicar_em, membro, outra_uo, vinculo

if TYPE_CHECKING:
    from projetos.models import Participacao
    from rh.models import UnidadeOrganizacional


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
PENDENTES = '/projetos/participacoes_pendentes_anuencia/'
REGISTRAR_ANUENCIA = '/projetos/registrar_anuencia_participacao/{}/{}/'
CANCELAR_ANUENCIA = '/projetos/cancelar_anuencia/{}/'
ALTERAR_CHEFIA = '/projetos/alterar_chefia_imediata_participacao/{}/'
ACEITAR_TERMO = '/projetos/aceitar_termo_compromisso/{}/'
DADOS_BANCARIOS = '/projetos/cadastrar_dados_bancarios/{}/'
DUPLO_FATOR = '/djtools/two_factor_authentication/'

DEFERIR, INDEFERIR = '1', '2'
CODIGO_DE_DUPLO_FATOR = '123456'  # `TwoFactorAuthenticationCode.save` fixa o código sob teste (djtools/models.py)


@pytest.fixture
def membro_com_anuencia(projeto_em_execucao) -> Callable[..., Participacao]:
    """``(chefe='outro_coordenador', uo=None, **campos) -> Participacao`` do ``segundo_avaliador`` num edital que exige anuência.

    ``chefe`` é o papel do responsável pela anuência (``None``: ainda não indicado, como sai de
    "Adicionar Servidor" quando o SIAPE não traz chefia); ``campos`` vão para a participação.
    """
    from projetos.models import Edital

    def _novo(chefe: str | None = 'outro_coordenador', uo: UnidadeOrganizacional | None = None, **campos: object) -> Participacao:
        extra = {'uo': uo} if uo else {}
        projeto = projeto_em_execucao(**extra).projeto
        Edital.objects.filter(pk=projeto.edital_id).update(exige_anuencia=Edital.TODOS)
        responsavel = vinculo(chefe).relacionamento if chefe else None
        return membro(projeto, 'segundo_avaliador', responsavel_anuencia=responsavel, **campos)

    return _novo


def test_coordenador_de_extensao_indica_a_chefia_e_o_chefe_defere(logado_projetos, membro_com_anuencia):
    """A cadeia da anuência: sem chefe indicado → o Coordenador de Extensão indica → o chefe defere na lista de pendências."""
    participacao = membro_com_anuencia(chefe=None)
    projeto = participacao.projeto
    tela = Tela(logado_projetos('coordenador_extensao')).ir(PROJETO.format(projeto.pk)).clicar_aba('Equipe')

    tela.ver_texto('O chefe imediato não foi indicado.')
    clicar_em(tela, ALTERAR_CHEFIA.format(participacao.pk))
    tela.ver_titulo('Alterar Responsável pela Anuência do Participante')
    tela.preencher('Servidor', 'autocomplete', PAPEIS['outro_coordenador'], 'Outro Coordenador E2E').clicar_botao('Salvar')
    tela.esperar().sucesso('Chefia imediata alterada com sucesso.')
    participacao.refresh_from_db()
    assert participacao.responsavel_anuencia == vinculo('outro_coordenador').relacionamento, 'a UI disse que alterou, mas a chefia não mudou'

    chefe = Tela(logado_projetos('outro_coordenador')).ir(PENDENTES)
    chefe.ver_titulo('Participações Pendentes da Sua Anuência').linha(projeto.titulo)
    clicar_em(chefe, REGISTRAR_ANUENCIA.format(participacao.pk, DEFERIR))  # `.confirm`: o `logado` aceita
    chefe.esperar().sucesso('Anuência registrada com sucesso.')
    participacao.refresh_from_db()
    assert participacao.anuencia is True, 'a UI disse que registrou, mas a anuência não foi deferida'
    assert participacao.anuencia_registrada_em is not None
    assert chefe.loc(f'//tr[contains(normalize-space(.), "{projeto.titulo}")]').count() == 0, 'a participação deferida continua pendente'


def test_chefe_indefere_a_participacao(logado_projetos, membro_com_anuencia):
    participacao = membro_com_anuencia()
    tela = Tela(logado_projetos('outro_coordenador')).ir(PENDENTES)

    tela.linha(participacao.projeto.titulo)
    clicar_em(tela, REGISTRAR_ANUENCIA.format(participacao.pk, INDEFERIR))
    tela.esperar().sucesso('Anuência registrada com sucesso.')
    participacao.refresh_from_db()
    assert (participacao.anuencia, participacao.anuencia_registrada_em is not None) == (False, True), 'o indeferimento não foi gravado'


def test_gerente_cancela_a_anuencia_registrada(logado_projetos, membro_com_anuencia):
    """Cancelar volta a participação ao início: sem chefe, sem decisão, sem data — o SIAPE ou o coordenador indicam de novo."""
    import datetime

    participacao = membro_com_anuencia(anuencia=True, anuencia_registrada_em=datetime.datetime.now())
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(participacao.projeto_id)).clicar_aba('Equipe')

    clicar_em(tela, CANCELAR_ANUENCIA.format(participacao.pk))  # `.btn.danger.confirm`
    tela.esperar().sucesso('Anuência cancelada com sucesso.')
    participacao.refresh_from_db()
    assert (participacao.responsavel_anuencia, participacao.anuencia, participacao.anuencia_registrada_em) == (None, None, None), (
        'a UI disse que cancelou, mas a anuência continua registrada'
    )


def test_cancelar_anuencia_oferecido_ao_coordenador_de_extensao_abre(logado_projetos, membro_com_anuencia):
    import datetime

    participacao = membro_com_anuencia(anuencia=True, anuencia_registrada_em=datetime.datetime.now())
    tela = Tela(logado_projetos('coordenador_extensao')).ir(PROJETO.format(participacao.projeto_id)).clicar_aba('Equipe')

    rota = CANCELAR_ANUENCIA.format(participacao.pk)
    oferecido = tela.loc(f'//a[@href="{rota}"]').count() > 0
    status = tela.buscar(rota).status
    assert not oferecido or status in (200, 302), f'a aba oferece "Cancelar anuência" ao Coordenador de Extensão, e a rota responde {status}'


def test_cancelar_anuencia_nao_e_oferecido_fora_de_inscricao_e_execucao(logado_projetos, membro_com_anuencia):
    """#17559: a view só cancela em inscrição/execução; no projeto inativado o gerente não vê o botão e a rota recusa."""
    import datetime

    from projetos.models import Projeto

    participacao = membro_com_anuencia(anuencia=True, anuencia_registrada_em=datetime.datetime.now())
    Projeto.objects.filter(pk=participacao.projeto_id).update(inativado=True)
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(participacao.projeto_id)).clicar_aba('Equipe')

    rota = CANCELAR_ANUENCIA.format(participacao.pk)
    assert tela.loc(f'//a[@href="{rota}"]').count() == 0, 'a aba oferece "Cancelar anuência" em projeto inativado'
    assert tela.buscar(rota).status == 403
    participacao.refresh_from_db()
    assert participacao.anuencia is True, 'uma rota que respondeu 403 desfez a anuência'


def test_so_o_chefe_indicado_registra_a_anuencia(logado_projetos, membro_com_anuencia):
    """Quem não é o chefe indicado: 403, e o GET não grava decisão nenhuma. Na lista dele, a participação nem aparece."""
    participacao = membro_com_anuencia()
    tela = Tela(logado_projetos('coordenador_projeto'))

    assert tela.buscar(REGISTRAR_ANUENCIA.format(participacao.pk, DEFERIR)).status == 403
    participacao.refresh_from_db()
    assert (participacao.anuencia, participacao.anuencia_registrada_em) == (None, None), 'uma rota que respondeu 403 gravou a anuência'
    tela.ir(PENDENTES).ver_texto('Nenhum participante foi encontrado.')


def test_opcao_invalida_nao_registra_anuencia(logado_projetos, membro_com_anuencia):
    """#17514: só ``1``/``2`` decidem; outra opção, mesmo do chefe indicado, é 404 e a participação continua pendente."""
    participacao = membro_com_anuencia()
    tela = Tela(logado_projetos('outro_coordenador'))

    assert tela.buscar(REGISTRAR_ANUENCIA.format(participacao.pk, '3')).status == 404
    participacao.refresh_from_db()
    assert (participacao.anuencia, participacao.anuencia_registrada_em) == (None, None), 'opção inválida gravou anuência sem decisão'


@pytest.mark.parametrize(
    ('papel', 'outro_campus', 'status'),
    [
        ('coordenador_extensao', False, 200),
        ('gerente', True, 200),
        # Papel LOCAL (decisão 42) e a view compara o campus: o Coordenador de Extensão de outro campus não indica chefia.
        ('coordenador_extensao', True, 403),
        # Sem `projetos.pode_pre_avaliar_projeto`: nem o coordenador do projeto troca quem dá a anuência dele.
        ('coordenador_projeto', False, 403),
    ],
)
def test_alterar_chefia_por_papel(logado_projetos, membro_com_anuencia, papel, outro_campus, status):
    participacao = membro_com_anuencia(uo=outra_uo() if outro_campus else None)
    assert Tela(logado_projetos(papel)).buscar(ALTERAR_CHEFIA.format(participacao.pk)).status == status


def test_anuencia_registrada_nao_troca_de_chefia_nem_e_cancelada_por_quem_nao_gerencia(logado_projetos, membro_com_anuencia):
    """Depois da decisão, "alterar chefia" fecha até para o Coordenador de Extensão; cancelar é do gerente — o coordenador do projeto leva 403."""
    import datetime

    participacao = membro_com_anuencia(anuencia=False, anuencia_registrada_em=datetime.datetime.now())

    assert Tela(logado_projetos('coordenador_extensao')).buscar(ALTERAR_CHEFIA.format(participacao.pk)).status == 403
    assert Tela(logado_projetos('coordenador_projeto')).buscar(CANCELAR_ANUENCIA.format(participacao.pk)).status == 403
    participacao.refresh_from_db()
    assert participacao.anuencia is False, 'uma rota que respondeu 403 desfez a anuência'


# -------------------------------------------------------------------- termo de compromisso


@pytest.fixture
def membro_com_termo(projeto_em_execucao) -> Participacao:
    """Participação do ``avaliador`` (que loga) num edital com termo de compromisso do servidor, ainda não aceito."""
    from projetos.models import Edital

    projeto = projeto_em_execucao().projeto
    Edital.objects.filter(pk=projeto.edital_id).update(termo_compromisso_servidor='<p>Comprometo-me com as atividades do projeto.</p>')
    return membro(projeto, 'avaliador')


def test_membro_aceita_o_termo_de_compromisso(logado_projetos, membro_com_termo):
    """O próprio membro aceita na aba "Equipe", confirmando com a senha; a senha errada é recusada antes."""
    participacao = membro_com_termo
    tela = Tela(logado_projetos('avaliador')).ir(PROJETO.format(participacao.projeto_id)).clicar_aba('Equipe')

    tela.ver_texto('Termo de Compromisso não assinado')
    clicar_em(tela, ACEITAR_TERMO.format(participacao.pk))
    tela.ver_titulo('Aceitar Termo de Compromisso').ver_texto('Comprometo-me com as atividades do projeto.')
    tela.preencher('Aceito o Termo de Compromisso', 'checkbox', 'marcar').preencher('Senha para confirmação', 'senha', 'senha-errada')
    tela.clicar_botao('Enviar')
    tela.esperar().erro('A senha não confere com a do usuário logado.')
    participacao.refresh_from_db()
    assert participacao.termo_aceito_em is None, 'o termo foi aceito com a senha errada'

    tela.preencher('Aceito o Termo de Compromisso', 'checkbox', 'marcar').preencher('Senha para confirmação', 'senha', SENHA_E2E)
    tela.clicar_botao('Enviar')
    tela.esperar().sucesso('Termo de compromisso aceito com sucesso.')
    participacao.refresh_from_db()
    assert participacao.termo_aceito_em is not None, 'a UI disse que aceitou, mas o aceite não foi gravado'


def test_so_o_proprio_membro_aceita_o_termo(logado_projetos, membro_com_termo):
    """Nem o coordenador aceita pelo membro: o aceite é pessoal."""
    assert Tela(logado_projetos('coordenador_projeto')).buscar(ACEITAR_TERMO.format(membro_com_termo.pk)).status == 403


# ------------------------------------------------------------------------ dados bancários

NUMERO_DA_CONTA = '98765-4'


@pytest.fixture
def bolsista_da_equipe(projeto_em_execucao) -> Participacao:
    """Participação do ``aluno`` (voluntário: com bolsa, ``gerencia_bolsa_ae`` gravaria no ``ae``) num projeto em execução."""
    return membro(projeto_em_execucao().projeto, 'aluno')


def _passar_pelo_duplo_fator(tela: Tela, rota: str) -> Tela:
    """Zera a marca de duplo fator da sessão e passa por ele de novo, com o código fixo dos testes.

    O ``logado`` reusa a sessão do papel entre os testes: sem zerar, quem passou pelo duplo fator
    num teste pula a tela no seguinte, e o fluxo dependeria da ordem. O GET na tela do duplo fator
    é o que apaga a marca (``djtools/views.py``, ``two_factor_authentication``).
    """
    tela.buscar(DUPLO_FATOR)
    tela.ir(rota).ver_titulo('Autenticação via E-mail')
    tela.preencher('Código', 'número', CODIGO_DE_DUPLO_FATOR).clicar_botao('Autenticar')
    return tela.esperar().sucesso('Código de autenticação validado com sucesso.')


def test_bolsista_cadastra_os_dados_bancarios_pelo_duplo_fator(logado_projetos, bolsista_da_equipe, email_pessoal_de):
    """ "Dados bancários" na aba "Equipe" leva ao duplo fator e, dele, ao formulário; o coordenador passa a ver a conta."""
    participacao = bolsista_da_equipe
    email_pessoal_de('aluno')
    banco()
    tela = Tela(logado_projetos('aluno')).ir(PROJETO.format(participacao.projeto_id)).clicar_aba('Equipe')

    assert tela.loc(f'//a[@href="{DADOS_BANCARIOS.format(participacao.pk)}"]').count() == 1, 'a aba não oferece "Dados bancários" ao próprio membro'
    _passar_pelo_duplo_fator(tela, DADOS_BANCARIOS.format(participacao.pk))
    tela.ver_titulo('Cadastrar/Atualizar Dados Bancários').preencher_formulario(
        [
            ('Banco', 'autocomplete', 'Banco do Brasil'),  # ForeignKeyPlus: select2 (armadilha 23)
            ('Número da Agência', 'texto', '3293-X'),
            ('Tipo da Conta', 'lista', 'Conta Corrente'),
            ('Número da Conta', 'texto', NUMERO_DA_CONTA),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Dados bancários atualizados com sucesso.')
    participacao.refresh_from_db()
    assert (participacao.instituicao, participacao.numero_conta, participacao.tipo_conta) == (banco(), NUMERO_DA_CONTA, 'Conta Corrente'), (
        'a UI disse que atualizou, mas os dados bancários não persistiram'
    )


def test_so_o_proprio_membro_altera_os_dados_bancarios(logado_projetos, bolsista_da_equipe, email_pessoal_de):
    """O coordenador VÊ a conta do bolsista, mas não a altera: passado o duplo fator, a rota lhe dá 403."""
    participacao = bolsista_da_equipe
    email_pessoal_de('coordenador_projeto')
    tela = Tela(logado_projetos('coordenador_projeto'))

    tela.buscar(DUPLO_FATOR)
    tela.ir(DADOS_BANCARIOS.format(participacao.pk)).preencher('Código', 'número', CODIGO_DE_DUPLO_FATOR).clicar_botao('Autenticar')
    tela.esperar()
    assert tela.buscar(DADOS_BANCARIOS.format(participacao.pk)).status == 403


@pytest.mark.parametrize(
    ('papel', 've'),
    [
        ('coordenador_projeto', True),
        ('coordenador_extensao', True),
        ('gerente', True),
        # Membro da equipe, mas não é o dono da conta nem gerencia o projeto.
        ('avaliador', False),
    ],
)
def test_quem_ve_os_dados_bancarios_na_equipe(logado_projetos, projeto_em_execucao, papel, ve):
    projeto = projeto_em_execucao().projeto
    membro(projeto, 'aluno', instituicao=banco(), numero_agencia='3293-X', tipo_conta='Conta Corrente', numero_conta=NUMERO_DA_CONTA)
    membro(projeto, 'avaliador')

    resposta = Tela(logado_projetos(papel)).buscar(PROJETO.format(projeto.pk))
    assert resposta.status == 200
    assert (NUMERO_DA_CONTA in resposta.text()) is ve, f'{papel} {"não " if ve else ""}vê a conta do bolsista na aba "Equipe"'


@pytest.mark.parametrize('papel', ['aluno', 'coordenador_extensao'])
def test_fora_do_projeto_ninguem_ve_os_dados_bancarios(logado_projetos, projeto_em_execucao, papel):
    """O aluno de fora (vai para a consulta pública) e o Coordenador de Extensão de OUTRO campus não veem a conta.

    Afirma só a conta, não o acesso à página: se o Coordenador de Extensão de outro campus abre o
    projeto é decisão pendente (ver relatório da fatia 4). ``pode_ver_dados_bancarios`` compara o
    campus explicitamente (``projetos/views.py:1197``).
    """
    projeto = projeto_em_execucao(uo=outra_uo()).projeto
    membro(projeto, 'avaliador', instituicao=banco(), numero_agencia='3293-X', tipo_conta='Conta Corrente', numero_conta=NUMERO_DA_CONTA)

    tela = Tela(logado_projetos(papel))
    for url in (PROJETO.format(projeto.pk), f'/projetos/consulta_projeto/{projeto.pk}/'):
        assert NUMERO_DA_CONTA not in tela.buscar(url).text(), f'{papel} de fora vê a conta do membro em {url}'
