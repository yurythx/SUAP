"""Fluxo: plano de oferta do edital — por campus, em lote, por grupo e por tema.

O plano de oferta define a abrangência do edital: só servidores dos campi ofertados submetem
projetos, e as quantidades (pré-selecionados/selecionados) são as vagas que a classificação
respeita. Cada forma de seleção (``Edital.forma_selecao``) abre uma aba diferente na tela do
edital; aqui passa o ciclo de cada uma (popups de adicionar/editar, remoção por GET) e as regras
que mais importam: campus repetido é recusado, o lote ATUALIZA a oferta de um campus já ofertado
em vez de duplicá-la, área temática sem tema só tem uma oferta, e a oferta por tema é exclusiva
do gerente sistêmico. Fecha com a matriz de acesso do coordenador de extensão a edital de outro
campus — inclusive remover oferta de edital alheio pela URL (#17488).
"""

from uuid import uuid4

import pytest

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela, adicionar_ao_filteredselect
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAL = '/projetos/edital/{}/'
ABA_CAMPUS = 'Plano de Oferta por Campus'
ADICIONAR_OFERTA = '/projetos/adicionar_oferta_projeto/{}/'
EDITAR_OFERTA = '/projetos/editar_oferta_projeto/{}/{}/'
REMOVER_OFERTA = '/projetos/remover_oferta_projeto/{}/{}/'
ADICIONAR_OFERTA_EM_LOTE = '/projetos/adicionar_oferta_projeto_em_lote/{}/'
ABA_GRUPO = 'Plano de Oferta por Grupo'
ADICIONAR_OFERTA_GRUPO = '/projetos/adicionar_oferta_por_grupo/{}/'
EDITAR_OFERTA_GRUPO = '/projetos/editar_oferta_projeto_por_grupo/{}/{}/'
REMOVER_OFERTA_GRUPO = '/projetos/remover_oferta_projeto_por_grupo/{}/{}/'
ABA_TEMA = 'Plano de Oferta por Tema'
ADICIONAR_OFERTA_TEMA = '/projetos/adicionar_oferta_projeto_por_tema/{}/'
EDITAR_OFERTA_TEMA = '/projetos/editar_oferta_projeto_por_tema/{}/{}/'
REMOVER_OFERTA_TEMA = '/projetos/remover_oferta_projeto_por_tema/{}/{}/'

# `Edital.forma_selecao` e `Edital.FOMENTO_EXTERNO`, literais porque o model só é importado no corpo.
TEMA, GRUPO, EXTERNO = '2', '4', 'Externo'


def test_oferta_por_campus_ciclo_completo(logado_projetos, edital_novo, projetos_seed):
    """Adicionar (popup) → editar (popup) → remover, pelo gerente — o cenário da feature 001."""
    from projetos.models import OfertaProjeto

    edital = edital_novo()
    OfertaProjeto.objects.filter(edital=edital).delete()
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba(ABA_CAMPUS)
    clicar_em(tela, ADICIONAR_OFERTA.format(edital.pk))
    popup = popup_em(tela, ADICIONAR_OFERTA.format(edital.pk))
    popup.preencher_formulario([('Campus', 'autocomplete', 'CZN'), ('Pré-Selecionados', 'texto', '5'), ('Selecionados', 'texto', '3')])
    tela = popup.salvar_no_popup('Salvar').sucesso('Oferta adicionada com sucesso.')
    oferta = OfertaProjeto.objects.filter(edital=edital, uo=projetos_seed.uo).first()
    assert oferta is not None, 'a UI disse que salvou, mas não persistiu'
    assert (oferta.qtd_aprovados, oferta.qtd_selecionados) == (5, 3), 'quantidades gravadas erradas'

    tela.clicar_aba(ABA_CAMPUS)
    clicar_em(tela, EDITAR_OFERTA.format(oferta.pk, edital.pk))
    popup = popup_em(tela, EDITAR_OFERTA.format(oferta.pk, edital.pk)).preencher('Selecionados', 'texto', '4')
    tela = popup.salvar_no_popup('Salvar').sucesso('Oferta editada com sucesso.')
    oferta.refresh_from_db()
    assert oferta.qtd_selecionados == 4, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA_CAMPUS)
    clicar_em(tela, REMOVER_OFERTA.format(oferta.pk, edital.pk))
    tela.esperar().sucesso('Oferta removida com sucesso.')
    assert not OfertaProjeto.objects.filter(pk=oferta.pk).exists(), 'a UI disse que removeu, mas a oferta continua'


def test_campus_ja_ofertado_e_recusado(logado_projetos, edital_novo):
    """``OfertaProjetoForm.clean``: um plano por campus — o edital novo já oferta o CZN."""
    from projetos.models import OfertaProjeto

    edital = edital_novo()
    tela = Tela(logado_projetos('gerente')).ir(ADICIONAR_OFERTA.format(edital.pk))

    tela.preencher_formulario([('Campus', 'autocomplete', 'CZN'), ('Pré-Selecionados', 'texto', '1'), ('Selecionados', 'texto', '1')])
    tela.clicar_botao('Salvar')
    tela.erro('Um plano de oferta para este campus já foi cadastrado.')
    assert OfertaProjeto.objects.filter(edital=edital).count() == 1, 'o formulário recusou, mas a oferta foi duplicada'


def test_campi_em_lote_atualizam_a_oferta_existente(logado_projetos, edital_novo, projetos_seed):
    """O lote é upsert por campus: o CZN já ofertado (5/3) fica UM plano, com as quantidades novas."""
    from projetos.models import OfertaProjeto

    edital = edital_novo()
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba(ABA_CAMPUS)
    clicar_em(tela, ADICIONAR_OFERTA_EM_LOTE.format(edital.pk))
    tela.ver_titulo('Adicionar Oferta de Projeto')
    adicionar_ao_filteredselect(tela.pagina, 'id_campi_from', 'CZN')
    tela.preencher_formulario([('Pré-Selecionados', 'texto', '7'), ('Selecionados', 'texto', '2')]).clicar_botao('Enviar')

    tela.esperar().sucesso('Campi adicionados com sucesso.')
    ofertas = OfertaProjeto.objects.filter(edital=edital, uo=projetos_seed.uo)
    assert list(ofertas.values_list('qtd_aprovados', 'qtd_selecionados')) == [(7, 2)], 'o lote duplicou ou não atualizou a oferta do campus'


def test_edital_de_fomento_externo_oferta_so_os_campi(logado_projetos, edital_novo, projetos_seed):
    """Fomento externo não tem vagas: a mesma rota troca de formulário e grava só o campus."""
    from projetos.models import OfertaProjeto

    edital = edital_novo(tipo_fomento=EXTERNO)
    OfertaProjeto.objects.filter(edital=edital).delete()
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba(ABA_CAMPUS)
    clicar_em(tela, ADICIONAR_OFERTA.format(edital.pk))
    adicionar_ao_filteredselect(tela.pagina, 'id_campi_from', 'CZN')
    tela.clicar_botao('Enviar')

    tela.esperar().sucesso('Oferta adicionada com sucesso.')
    assert OfertaProjeto.objects.filter(edital=edital, uo=projetos_seed.uo).exists(), 'a UI disse que salvou, mas não persistiu'


def test_oferta_por_grupo_ciclo_completo(logado_projetos, edital_novo):
    """Adicionar (popup) → editar (popup) → remover, num edital de seleção por grupo."""
    from projetos.models import OfertaProjetoPorGrupo

    edital = edital_novo(forma_selecao=GRUPO)
    grupo = f'Grupo {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba(ABA_GRUPO)
    clicar_em(tela, ADICIONAR_OFERTA_GRUPO.format(edital.pk))
    popup = popup_em(tela, ADICIONAR_OFERTA_GRUPO.format(edital.pk))
    popup.preencher_formulario([('Grupo', 'texto', grupo), ('Pré-Selecionados', 'texto', '4'), ('Selecionados', 'texto', '2')])
    tela = popup.salvar_no_popup('Salvar').sucesso('Oferta adicionada com sucesso.')
    oferta = OfertaProjetoPorGrupo.objects.filter(edital=edital, grupo=grupo).first()
    assert oferta is not None, 'a UI disse que salvou, mas não persistiu'

    tela.clicar_aba(ABA_GRUPO)
    clicar_em(tela, EDITAR_OFERTA_GRUPO.format(oferta.pk, edital.pk))
    popup = popup_em(tela, EDITAR_OFERTA_GRUPO.format(oferta.pk, edital.pk)).preencher('Selecionados', 'texto', '3')
    tela = popup.salvar_no_popup('Salvar').sucesso('Oferta editada com sucesso.')
    oferta.refresh_from_db()
    assert oferta.selecionados == 3, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA_GRUPO)
    clicar_em(tela, REMOVER_OFERTA_GRUPO.format(oferta.pk, edital.pk))
    tela.esperar().sucesso('Oferta removida com sucesso.')
    assert not OfertaProjetoPorGrupo.objects.filter(pk=oferta.pk).exists(), 'a UI disse que removeu, mas a oferta continua'


def test_oferta_por_tema_ciclo_completo(logado_projetos, edital_novo, catalogo_do_edital):
    """Adicionar (popup, tema encadeado à área) → editar (popup) → remover, num edital de seleção por tema."""
    from projetos.models import OfertaProjetoPorTema

    edital = edital_novo(forma_selecao=TEMA)
    tema = catalogo_do_edital.temas[0]
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba(ABA_TEMA)
    clicar_em(tela, ADICIONAR_OFERTA_TEMA.format(edital.pk))
    popup = popup_em(tela, ADICIONAR_OFERTA_TEMA.format(edital.pk))
    popup.preencher_formulario([('Área Temática', 'lista', 'Cultura'), ('Tema', 'lista', tema.descricao), ('Selecionados', 'texto', '2')])
    tela = popup.salvar_no_popup('Salvar').sucesso('Oferta por tema adicionada com sucesso.')
    oferta = OfertaProjetoPorTema.objects.filter(edital=edital, tema=tema).first()
    assert oferta is not None, 'a UI disse que salvou, mas não persistiu'

    tela.clicar_aba(ABA_TEMA)
    clicar_em(tela, EDITAR_OFERTA_TEMA.format(oferta.pk, edital.pk))
    popup = popup_em(tela, EDITAR_OFERTA_TEMA.format(oferta.pk, edital.pk)).preencher('Selecionados', 'texto', '3')
    tela = popup.salvar_no_popup('Salvar').sucesso('Oferta editada com sucesso.')
    oferta.refresh_from_db()
    assert oferta.selecionados == 3, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA_TEMA)
    clicar_em(tela, REMOVER_OFERTA_TEMA.format(oferta.pk, edital.pk))
    tela.esperar().sucesso('Oferta removida com sucesso.')
    assert not OfertaProjetoPorTema.objects.filter(pk=oferta.pk).exists(), 'a UI disse que removeu, mas a oferta continua'


def test_area_tematica_sem_tema_tem_uma_so_oferta(logado_projetos, edital_novo):
    from projetos.models import OfertaProjetoPorTema
    from projetos.tests.factories import OfertaProjetoPorTemaFactory

    edital = edital_novo(forma_selecao=TEMA)
    OfertaProjetoPorTemaFactory(edital=edital)  # área "Cultura", sem tema
    tela = Tela(logado_projetos('gerente')).ir(ADICIONAR_OFERTA_TEMA.format(edital.pk))

    tela.preencher_formulario([('Área Temática', 'lista', 'Cultura'), ('Selecionados', 'texto', '1')]).clicar_botao('Salvar')
    tela.erro('Já existe uma oferta para esta área temática.')
    assert OfertaProjetoPorTema.objects.filter(edital=edital).count() == 1, 'a UI recusou, mas a oferta foi duplicada'


@pytest.mark.parametrize(
    ('papel', 'status'),
    [
        ('gerente', 200),
        # `adicionar_oferta_projeto_por_tema` exige `pode_gerenciar_edital`, que o coordenador de extensão não tem.
        ('coordenador_extensao', 403),
    ],
)
def test_oferta_por_tema_e_do_gerente_sistemico(logado_projetos, edital_novo, papel, status):
    edital = edital_novo(forma_selecao=TEMA)
    assert Tela(logado_projetos(papel)).buscar(ADICIONAR_OFERTA_TEMA.format(edital.pk)).status == status


def test_coordenador_de_extensao_nao_configura_edital_de_outro_campus(logado_projetos, edital_de_outro_campus):
    """O controle das rotas que ``tem_permissao_acesso_edital`` protege — e a prova de que o edital é alheio."""
    from projetos.models import OfertaProjeto

    edital = edital_de_outro_campus
    oferta = OfertaProjeto.objects.get(edital=edital)
    tela = Tela(logado_projetos('coordenador_extensao'))

    assert tela.buscar(ADICIONAR_OFERTA_GRUPO.format(edital.pk)).status == 403
    assert tela.buscar(REMOVER_OFERTA.format(oferta.pk, edital.pk)).status == 403
    assert OfertaProjeto.objects.filter(pk=oferta.pk).exists(), 'o 403 veio, mas a oferta foi removida'


def test_coordenador_de_extensao_nao_remove_oferta_por_grupo_de_outro_campus(logado_projetos, edital_de_outro_campus):
    from projetos.models import OfertaProjetoPorGrupo

    edital = edital_de_outro_campus
    oferta = OfertaProjetoPorGrupo.objects.get(edital=edital)

    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(REMOVER_OFERTA_GRUPO.format(oferta.pk, edital.pk))
    assert (resposta.status, OfertaProjetoPorGrupo.objects.filter(pk=oferta.pk).exists()) == (403, True), 'removeu a oferta de edital alheio'


def test_coordenador_de_extensao_nao_remove_oferta_alheia_pela_url_do_proprio_edital(logado_projetos, edital_novo, edital_de_outro_campus):
    from projetos.models import OfertaProjeto

    proprio = edital_novo()  # cadastrado pelo gerente do CZN: o coordenador acessa
    oferta_alheia = OfertaProjeto.objects.get(edital=edital_de_outro_campus)

    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(REMOVER_OFERTA.format(oferta_alheia.pk, proprio.pk))
    # 403 ou 404: a correção natural é buscar a oferta DENTRO do edital (`get_object_or_404(..., edital=edital)`).
    assert resposta.status in (403, 404), f'respondeu {resposta.status} a um pedido para remover oferta de edital alheio'
    assert OfertaProjeto.objects.filter(pk=oferta_alheia.pk).exists(), 'removeu a oferta de edital alheio'
