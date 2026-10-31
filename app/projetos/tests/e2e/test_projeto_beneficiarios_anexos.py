"""Fluxo: caracterização dos beneficiários e anexos do projeto (feature 002).

A caracterização (público-alvo e quantidade prevista) é pendência de envio e vira indicador na
execução. Os anexos são de dois tipos, na mesma aba: os "Outros Anexos" que o coordenador sobe
livremente (arquivo guardado criptografado em ``comum.Arquivo`` e servido por
``visualizar_arquivo``) e os anexos exigidos pelo edital de cada membro, que nascem pendentes
quando se abre "Gerenciar anexos" do participante. A regressão que se pega: o ciclo de cada um,
o download devolvendo o arquivo de verdade e a regra de quantidade positiva.
"""

from uuid import uuid4

import pytest

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ABA_BENEFICIARIOS = 'Caracterização dos beneficiários'
ADICIONAR_CARACTERIZACAO = '/projetos/adicionar_caracterizacao_beneficiario/{}/'
EDITAR_CARACTERIZACAO = '/projetos/editar_caracterizacao_beneficiario/{}/'
REMOVER_CARACTERIZACAO = '/projetos/remover_caracterizacao_beneficiario/{}/'
ABA_ANEXOS = 'Anexos'
ADICIONAR_ANEXO_DIVERSO = '/projetos/adicionar_anexo_diverso_projeto/{}/'
UPLOAD_OUTRO_ANEXO = '/projetos/upload_outro_anexo/{}/'
EXCLUIR_OUTRO_ANEXO = '/projetos/excluir_outro_anexo/{}/'
VISUALIZAR_ARQUIVO = '/projetos/visualizar_arquivo/{}/'
ABA_EQUIPE = 'Equipe'
ANEXOS_DO_PARTICIPANTE = '/projetos/adicionar_anexo_do_projeto/{}/'


def test_caracterizacao_dos_beneficiarios_ciclo_completo(logado_projetos, projeto_novo):
    """Adicionar (popup) → editar (popup) → remover, pelo coordenador."""
    from projetos.models import CaracterizacaoBeneficiario

    projeto = projeto_novo()
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA_BENEFICIARIOS)
    clicar_em(tela, ADICIONAR_CARACTERIZACAO.format(projeto.pk))
    popup = popup_em(tela, ADICIONAR_CARACTERIZACAO.format(projeto.pk)).preencher_formulario(
        [('Tipo de Beneficiário', 'autocomplete', 'Movimentos Sociais'), ('Quantidade Prevista de Pessoas a Atender', 'texto', '12')]
    )
    tela = popup.salvar_no_popup('Salvar').sucesso('Caracterização do beneficiário adicionada com sucesso.')
    caracterizacao = CaracterizacaoBeneficiario.objects.filter(projeto=projeto, tipo_beneficiario__descricao='Movimentos Sociais').first()
    assert caracterizacao is not None, 'a UI disse que salvou, mas não persistiu'
    assert caracterizacao.quantidade == 12, f'quantidade gravada: {caracterizacao.quantidade}'

    tela.clicar_aba(ABA_BENEFICIARIOS)
    clicar_em(tela, EDITAR_CARACTERIZACAO.format(caracterizacao.pk))
    popup = popup_em(tela, EDITAR_CARACTERIZACAO.format(caracterizacao.pk)).preencher('Quantidade Prevista de Pessoas a Atender', 'texto', '20')
    tela = popup.salvar_no_popup('Salvar').sucesso('Caracterização do beneficiário editada com sucesso.')
    caracterizacao.refresh_from_db()
    assert caracterizacao.quantidade == 20, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA_BENEFICIARIOS)
    clicar_em(tela, REMOVER_CARACTERIZACAO.format(caracterizacao.pk))
    tela.esperar().sucesso('Caracterização do Beneficiário removida com sucesso.')
    assert not CaracterizacaoBeneficiario.objects.filter(pk=caracterizacao.pk).exists(), 'a UI disse que removeu, mas continua'


@pytest.mark.parametrize(
    'quantidade',
    [
        '-3',
        '0',
    ],
)
def test_quantidade_de_beneficiarios_tem_de_ser_positiva(logado_projetos, projeto_novo, quantidade):
    """``CaracterizacaoBeneficiarioForm.clean``: quantidade prevista não positiva é recusada."""
    projeto = projeto_novo()
    tela = Tela(logado_projetos('coordenador_projeto')).ir(ADICIONAR_CARACTERIZACAO.format(projeto.pk))

    tela.preencher_formulario(
        [('Tipo de Beneficiário', 'autocomplete', 'Grupos Comunitários'), ('Quantidade Prevista de Pessoas a Atender', 'texto', quantidade)]
    )
    tela.clicar_botao('Salvar')

    tela.erro('A quantidade deve ser maior que zero.')
    assert not projeto.caracterizacaobeneficiario_set.exists(), 'o formulário recusou, mas a caracterização foi gravada'


def test_outro_anexo_ciclo_completo(logado_projetos, projeto_novo):
    """Adicionar (tela própria) → baixar → trocar o arquivo → remover, na aba "Anexos"."""
    from projetos.models import ProjetoAnexo

    projeto = projeto_novo()
    descricao = f'Plano de divulgação {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA_ANEXOS)
    clicar_em(tela, ADICIONAR_ANEXO_DIVERSO.format(projeto.pk))
    tela.ver_titulo('Adicionar Anexo ao Projeto').preencher_formulario([('Descrição', 'texto', descricao), ('Arquivo', 'arquivo', 'arquivo.pdf')])
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Anexo cadastrado com sucesso.')
    anexo = ProjetoAnexo.objects.filter(projeto=projeto, descricao=descricao).first()
    assert anexo is not None, 'a UI disse que salvou, mas o anexo não persistiu'
    assert anexo.arquivo_id is not None, 'o anexo foi gravado sem o arquivo'

    # O download é um link comum da aba: afirma que a tela o oferece e que ele devolve o PDF.
    tela.clicar_aba(ABA_ANEXOS)
    download = VISUALIZAR_ARQUIVO.format(anexo.arquivo_id)
    assert tela.loc(f'//a[@href="{download}"]').count(), f'a aba não oferece o download do anexo ({download})'
    resposta = tela.buscar(download)
    assert (resposta.status, resposta.headers.get('content-type')) == (200, 'application/pdf'), 'o download não devolveu o PDF enviado'

    clicar_em(tela, UPLOAD_OUTRO_ANEXO.format(anexo.pk))
    tela.ver_titulo('Upload de Arquivo').preencher('Arquivo', 'arquivo', 'arquivo.png').clicar_botao('Enviar')
    tela.esperar().sucesso('Anexo alterado com sucesso.')
    anexo.refresh_from_db()
    assert anexo.arquivo.nome.endswith('.png'), f'a UI disse que trocou, mas o arquivo segue {anexo.arquivo.nome}'

    tela.clicar_aba(ABA_ANEXOS)
    clicar_em(tela, EXCLUIR_OUTRO_ANEXO.format(anexo.pk))
    tela.esperar().sucesso('Anexo removido com sucesso.')
    assert not ProjetoAnexo.objects.filter(pk=anexo.pk).exists(), 'a UI disse que removeu, mas o anexo continua'


def test_gerenciar_anexos_gera_as_pendencias_do_participante(logado_projetos, projeto_novo, edital_novo):
    """ "Gerenciar anexos" do coordenador cria, pendente, o anexo que o edital exige do tipo de membro dele."""
    from projetos.models import Participacao, ProjetoAnexo
    from projetos.tests.factories import EditalAnexoFactory

    edital = edital_novo()
    exigido = EditalAnexoFactory(edital=edital, nome=f'Termo do coordenador {uuid4().hex[:8]}')  # coordenador TAE voluntário
    projeto = projeto_novo(edital=edital)
    coordenador = Participacao.objects.get(projeto=projeto, responsavel=True)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA_EQUIPE)
    clicar_em(tela, ANEXOS_DO_PARTICIPANTE.format(coordenador.pk))

    tela.ver_titulo('Anexos do Participante: Coordenador Projeto E2E').linha(exigido.nome).ver_texto('Aguardando submissão do arquivo')
    assert ProjetoAnexo.objects.filter(projeto=projeto, participacao=coordenador, anexo_edital=exigido, arquivo__isnull=True).exists(), (
        'a tela listou o anexo, mas a pendência não foi gravada'
    )
