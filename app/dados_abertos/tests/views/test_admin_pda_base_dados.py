"""Testes da listagem do admin de PDA x Base de Dados."""

from django.contrib.admin.utils import label_for_field
from django.urls import reverse

from dados_abertos.admin.pda_base_dados import PDABaseDadosAdmin
from dados_abertos.enums import SituacaoLAI
from dados_abertos.models import PDABaseDados
from dados_abertos.tests.factories import PDABaseDadosFactory
from rh.tests.factories import PessoaFisicaFactory, ServidorFactory


def test_coluna_de_situacao_lai_tem_rotulo_e_status():
    """A coluna sai em português e com o status do Design System.

    Regressão: com o ``get_situacao_lai_display`` cru em ``list_display``, o Django não achava
    ``short_description`` e rotulava a coluna como "method".
    """
    admin = PDABaseDadosAdmin(PDABaseDados, None)

    assert label_for_field('situacao_lai_formatada', PDABaseDados, admin) == 'Situação LAI'

    html = admin.situacao_lai_formatada(PDABaseDados(situacao_lai=SituacaoLAI.DEVOLVIDO))
    assert html == '<span class="status status-error">Devolvido para ajustes</span>'


def test_busca_encontra_relacao_pelo_nome_do_responsavel(admin_client, sync_permissions):
    """A busca do changelist resolve todos os ``search_fields``; um caminho inválido derrubava qualquer pesquisa."""
    responsavel = ServidorFactory(pessoa_fisica=PessoaFisicaFactory(nome='Josefina Responsavel'))
    com_responsavel = PDABaseDadosFactory(responsavel_abertura=responsavel)
    sem_responsavel = PDABaseDadosFactory()

    resposta = admin_client.get(reverse('admin:dados_abertos_pdabasedados_changelist'), {'q': 'Josefina'})

    assert resposta.status_code == 200
    encontradas = list(resposta.context['cl'].result_list)
    assert com_responsavel in encontradas
    assert sem_responsavel not in encontradas
