"""Fluxo dos complementos da demanda: anexos, notas internas, observadores e usuários.

A demanda principal da cadeia é concluída em ``test_03`` e o produto deixa de oferecer a maior
parte dos complementos numa demanda terminal. Este arquivo cria a **segunda demanda** da suíte
e a mantém em "Em negociação" — o estado em que anexos, notas internas, observadores e a troca
de usuários são oferecidos —, subindo-a para "Em análise" só no teste da data de previsão.

ACHADO DE PRODUTO (candidato a issue): em ``demandas/views.py:805`` a guarda da especificação
técnica está invertida — ``if not demanda.eh_situacao_terminal: raise PermissionDenied``. O
menu "Especificação técnica" só aparece para demanda **não terminal** (``demanda.html``) e é
justamente aí que a view nega; a tela só abre para demanda concluída/cancelada. O teste cobre o
comportamento real (a tela abre na demanda concluída) e deixa a inversão registrada.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from demandas.tests.e2e.apoio import esperar_editor_rico
from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from demandas.models import Demanda

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VISUALIZAR = '/demandas/visualizar/{}/'
ADICIONAR_ANEXO = '/demandas/adicionar_anexo/{}/'
REMOVER_ANEXO = '/demandas/remover_anexo/{}/'
ATUALIZAR_ANEXOS = '/demandas/anexos_atualizar_informacoes/{}/'
NOTA_ADD = '/demandas/notainterna/{}/add/'
NOTA_CHANGE = '/demandas/notainterna/{}/{}/change/'
NOTA_DELETE = '/demandas/notainterna/{}/{}/delete/'
ACOMPANHAR = '/demandas/acompanhar/{}/'
ADICIONAR_OBSERVADOR = '/demandas/adicionar_observador/{}/{}/'
REMOVER_OBSERVADOR = '/demandas/remover_observador/{}/{}/'
ALTERAR_USUARIO = '/demandas/alterar_usuario/{}/{}/'
ESPECIFICACAO_TECNICA = '/demandas/especificacao_tecnica/{}/'
EDITAR_PREVISAO = '/demandas/editar_data_previsao_etapa/{}/'
AREA_ADMIN = '/admin/demandas/areaatuacaodemanda/'
GERENCIAR_DEMANDANTES = '/demandas/gerenciar_demandantes/{}/'
GERENCIAR_DEMANDANTES_EDITAR = '/demandas/gerenciar_demandantes_editar/{}/{}/'
SUBSTITUIR_DEMANDANTE = '/demandas/substituir_demandante/{}/{}/'

TITULO = 'Demanda 2'
DESCRICAO = 'Segunda demanda E2E'


def demanda_complementar() -> Demanda:
    """Cria a segunda demanda da suíte e a deixa em "Em negociação" pelo domínio.

    O estado é precondição dos fluxos complementares (anexos, notas internas, observadores,
    troca de usuários); percorrer a negociação pela tela é o que ``test_01`` a ``test_03`` já
    fazem.
    """
    from comum.models import User
    from demandas.models import AreaAtuacaoDemanda, Demanda, Situacao, Tag, TipoDemanda

    area = AreaAtuacaoDemanda.objects.get(area__nome='Tecnologia da Informação')
    demanda = Demanda.objects.filter(titulo=TITULO).first()
    if demanda is None:
        demanda = Demanda.objects.create(area=area, titulo=TITULO, descricao=DESCRICAO, tipo=TipoDemanda.MELHORIA)
        demanda.demandantes.add(User.objects.get(username='105001'))
        demanda.analistas.add(User.objects.get(username='105002'))
        demanda.tags.add(Tag.objects.get(nome='Tag Especial'))
    if demanda.situacao == Situacao.ESTADO_ABERTO:
        demanda.alterar_situacao(User.objects.get(username='105002'), Situacao.ESTADO_EM_NEGOCIACAO)
    demanda.refresh_from_db()
    return demanda


def demanda_concluida() -> Demanda:
    """A demanda da cadeia, concluída por ``test_03``."""
    from demandas.models import Demanda

    demanda = Demanda.objects.filter(titulo='Demanda 1').first()
    assert demanda is not None, 'demanda ausente: a cadeia é sequencial, rode `pytest demandas/tests/e2e` inteiro'
    return demanda


def test_anexos_da_demanda(logado_demandas: Callable[[str], Page]) -> None:
    """O analista anexa um arquivo, atualiza as informações dos anexos e o remove."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import Anexos

    demanda = demanda_complementar()
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Anexos')
    tela.aba('Anexos').clicar_botao('Adicionar anexo')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ANEXO.format(demanda.pk)}$'))
    tela.preencher('Arquivo', 'Arquivo', 'arquivo.pdf')
    tela.clicar_botao('Salvar').sucesso('Anexo adicionado com sucesso.')
    anexo = Anexos.objects.get(demanda=demanda)
    assert anexo.usuario == demanda.analistas.first(), 'o anexo precisa registrar quem o enviou'

    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Anexos')
    expect(tela.aba('Anexos').botao('Atualizar informações dos anexos')).to_have_attribute('href', ATUALIZAR_ANEXOS.format(demanda.pk))
    tela.aba('Anexos').clicar_botao('Atualizar informações dos anexos')
    tela.sucesso('Anexos atualizados com sucesso.')

    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Anexos')
    expect(tela.aba('Anexos').botao('Remover')).to_have_attribute('href', REMOVER_ANEXO.format(anexo.pk))
    tela.aba('Anexos').clicar_botao('Remover')
    tela.sucesso('Anexo removido com sucesso.')
    assert not Anexos.objects.filter(pk=anexo.pk).exists(), 'a UI disse que removeu, mas o anexo permanece'


def test_notas_internas_da_demanda(logado_demandas: Callable[[str], Page]) -> None:
    """O analista cria, edita e exclui a nota interna — que só existe para a equipe."""
    tela = Tela(logado_demandas('analista'))

    from demandas.models import NotaInterna

    demanda = demanda_complementar()
    # O formulário abre em popup; o desfecho é o recarregamento da página de trás.
    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Notas internas')
    tela.aba('Notas internas').clicar_botao('Nota Interna')
    popup = tela.popup()
    popup.preencher('Nota', 'TextArea', 'Nota interna E2E')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('A nota interna foi adicionada.')
    nota = NotaInterna.objects.get(demanda=demanda)
    assert nota.nota == 'Nota interna E2E', 'a UI disse que salvou, mas o texto da nota não persistiu'

    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Notas internas')
    expect(tela.aba('Notas internas').botao('Editar')).to_have_attribute('href', NOTA_CHANGE.format(demanda.pk, nota.pk))
    tela.aba('Notas internas').clicar_botao('Editar')
    popup = tela.popup()
    popup.preencher('Nota', 'TextArea', 'Nota interna E2E revisada')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('A nota interna foi atualizada.')
    nota.refresh_from_db()
    assert nota.nota == 'Nota interna E2E revisada', 'a UI disse que editou, mas o texto da nota não mudou'

    tela.ir(VISUALIZAR.format(demanda.pk)).clicar_aba('Notas internas')
    expect(tela.aba('Notas internas').botao('Remover')).to_have_attribute('href', NOTA_DELETE.format(demanda.pk, nota.pk))
    tela.aba('Notas internas').clicar_botao('Remover')
    tela.sucesso('A nota interna foi removida com sucesso.')
    assert not NotaInterna.objects.filter(pk=nota.pk).exists(), 'a UI disse que removeu, mas a nota permanece'


def test_acompanhar_e_validar_observador(logado_demandas: Callable[[str], Page]) -> None:
    """Um servidor pede para acompanhar a demanda e o demandante aceita e depois remove."""
    servidor = Tela(logado_demandas('servidor'))
    demandante = Tela(logado_demandas('demandante'))

    demanda = demanda_complementar()
    servidor.ir(VISUALIZAR.format(demanda.pk)).ver_botao('Acompanhar')
    expect(servidor.botao('Acompanhar')).to_have_attribute('href', ACOMPANHAR.format(demanda.pk))
    servidor.clicar_botao('Acompanhar')
    servidor.sucesso('Você solicitou sua inclusão como Observador desta demanda. Aguarde validação pelos demandantes.')
    demanda.refresh_from_db()
    servidor_user = demanda.observadores_pendentes.get(username='105004')

    demandante.ir(VISUALIZAR.format(demanda.pk))
    expect(demandante.botao('Aceitar')).to_have_attribute('href', ADICIONAR_OBSERVADOR.format(demanda.pk, servidor_user.pk))
    demandante.clicar_botao('Aceitar')
    demandante.sucesso('foi adicionado como Observador desta demanda.')
    demanda.refresh_from_db()
    assert demanda.observadores.filter(username='105004').exists(), 'a UI disse que aceitou, mas o observador não foi vinculado'
    assert not demanda.observadores_pendentes.filter(username='105004').exists(), 'o pedido precisa sair da lista de pendentes'

    # O segundo servidor pede para acompanhar e o demandante nega.
    outro = Tela(logado_demandas('servidor2'))
    outro.ir(VISUALIZAR.format(demanda.pk)).clicar_botao('Acompanhar')
    outro.sucesso('Você solicitou sua inclusão como Observador desta demanda. Aguarde validação pelos demandantes.')
    demanda.refresh_from_db()
    negado = demanda.observadores_pendentes.get(username='105005')
    demandante.ir(VISUALIZAR.format(demanda.pk))
    expect(demandante.botao('Negar')).to_have_attribute('href', REMOVER_OBSERVADOR.format(demanda.pk, negado.pk))
    demandante.clicar_botao('Negar')
    demandante.sucesso('foi removido com sucesso da lista de Observadores Pendentes desta demanda.')
    demanda.refresh_from_db()
    assert not demanda.observadores_pendentes.filter(username='105005').exists(), 'a UI disse que negou, mas o pedido permanece'


def test_alterar_usuarios_da_demanda(logado_demandas: Callable[[str], Page]) -> None:
    """O demandante troca os demandantes da demanda pela tela de alteração de usuários.

    A tela é a mesma para os quatro papéis; ela é oferecida a quem é demandante (ou demandante
    responsável) da demanda, e o campo só oferece quem já é demandante da área de atuação.
    """
    tela = Tela(logado_demandas('demandante'))

    from comum.models import User
    from demandas.models import AreaAtuacaoDemanda

    demanda = demanda_complementar()
    area = AreaAtuacaoDemanda.objects.get(area__nome='Tecnologia da Informação')
    area.demandantes.add(User.objects.get(username='105005'))

    tela.ir(VISUALIZAR.format(demanda.pk))
    expect(tela.loc(f'//a[@href="{ALTERAR_USUARIO.format("demandantes", demanda.pk)}"]').first).to_be_visible()
    tela.loc(f'//a[@href="{ALTERAR_USUARIO.format("demandantes", demanda.pk)}"]').first.click()
    tela.ver_titulo('Alterar Demandantes da Demanda')
    tela.preencher('Demandantes', 'Autocomplete Multiplo', '105005')
    tela.clicar_botao('Salvar').sucesso('Usuários alterados com sucesso.')
    demanda.refresh_from_db()
    assert demanda.demandantes.filter(username='105005').exists(), 'a UI disse que alterou, mas o novo demandante não foi vinculado'


def test_especificacao_tecnica_da_demanda_concluida(logado_demandas: Callable[[str], Page]) -> None:
    """A especificação técnica só abre na demanda concluída (a guarda da view está invertida)."""
    tela = Tela(logado_demandas('analista'))

    demanda = demanda_concluida()
    tela.ir(ESPECIFICACAO_TECNICA.format(demanda.pk)).ver_titulo('Especificação Técnica')
    esperar_editor_rico(tela, 'id_especificacao_tecnica')
    # Texto sem acento de propósito: o campo rico grava o HTML com as entidades escapadas.
    tela.preencher('Especificação Técnica', 'Texto rico', 'Especificacao tecnica E2E')
    tela.clicar_botao('Salvar').sucesso('A Especificação Técnica foi atualizada.')
    demanda.refresh_from_db()
    assert 'Especificacao tecnica E2E' in demanda.especificacao_tecnica, 'a UI disse que salvou, mas a especificação técnica não persistiu'


def test_data_de_previsao_da_etapa(logado_demandas: Callable[[str], Page]) -> None:
    """O analista edita a data de previsão da etapa pela própria tela da demanda."""
    tela = Tela(logado_demandas('analista'))

    from comum.models import User
    from demandas.models import Demanda, DoD, Especificacao, HistoricoSituacao, Situacao

    demanda = demanda_complementar()
    if demanda.situacao == Situacao.ESTADO_EM_NEGOCIACAO:
        DoD.objects.get_or_create(demanda=demanda, defaults={'descricao': 'Consolidação da Demanda 2'})
        dod = DoD.objects.get(demanda=demanda)
        Especificacao.objects.get_or_create(dod=dod, nome='Especificação 1', defaults={'atividades': 'Atividade', 'ordem': 1})
        demanda.alterar_situacao(User.objects.get(username='105002'), Situacao.ESTADO_EM_ANALISE, data_previsao=date(2019, 2, 1))
    demanda.refresh_from_db()
    assert demanda.situacao == Situacao.ESTADO_EM_ANALISE, 'a cadeia deste teste exige a demanda em análise'

    tela.ir(VISUALIZAR.format(demanda.pk))
    tela.clicar_botao('Outras opções')
    expect(tela.loc(f'//a[@href="{EDITAR_PREVISAO.format(demanda.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{EDITAR_PREVISAO.format(demanda.pk)}"]').click()
    popup = tela.popup()
    popup.ver_texto('Alterar Previsão de Conclusão da Etapa')
    popup.preencher_formulario([('Previsão', 'Data', '01/03/2019'), ('Comentário', 'TextArea', 'Nova previsão E2E')])
    popup.salvar_no_popup('Enviar')
    tela.sucesso(f'A data da previsão da etapa {Situacao.ESTADO_EM_ANALISE} foi alterada.')
    historico = HistoricoSituacao.objects.filter(demanda=demanda, situacao=Situacao.ESTADO_EM_ANALISE).latest('id')
    assert historico.data_previsao == date(2019, 3, 1), 'a UI disse que alterou, mas a previsão do histórico não mudou'
    assert Demanda.objects.get(pk=demanda.pk).situacao == Situacao.ESTADO_EM_ANALISE, 'a edição da previsão não muda a etapa'


def test_gerenciar_e_substituir_demandantes_da_area(logado_demandas: Callable[[str], Page]) -> None:
    """O coordenador de TI gerencia os demandantes da área, por módulo e por pessoa."""
    tela = Tela(logado_demandas('coordenador_ti'))

    from comum.models import User
    from demandas.models import AreaAtuacaoDemanda, Tag, TagDemandantes

    area = AreaAtuacaoDemanda.objects.get(area__nome='Tecnologia da Informação')
    tag = Tag.objects.get(nome='Tag Especial')
    tela.ir(AREA_ADMIN).ver_texto('Tecnologia da Informação')
    expect(tela.linha('Tecnologia da Informação').botao('Gerenciar demandantes')).to_have_attribute('href', GERENCIAR_DEMANDANTES.format(area.pk))
    tela.linha('Tecnologia da Informação').clicar_botao('Gerenciar demandantes')
    tela.ver_titulo('Gerenciar demandantes').ver_texto('Demandante')

    expect(tela.loc(f'//a[@href="{GERENCIAR_DEMANDANTES_EDITAR.format(area.pk, tag.pk)}"]')).to_be_visible()
    tela.loc(f'//a[@href="{GERENCIAR_DEMANDANTES_EDITAR.format(area.pk, tag.pk)}"]').click()
    popup = tela.popup()
    popup.ver_texto('Editar demandantes do módulo')
    popup.preencher('Demandantes', 'Autocomplete Multiplo', '105005')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Demandantes salvos com sucesso.')
    assert TagDemandantes.get_demandantes(tag).filter(username='105005').exists(), 'a UI disse que salvou, mas o demandante do módulo não persistiu'

    # O "Atualizar ou substituir" transfere as demandas ativas do demandante para outro.
    demandante = User.objects.get(username='105001')
    expect(tela.loc(f'//a[@href="{SUBSTITUIR_DEMANDANTE.format(area.pk, demandante.pk)}"]').first).to_be_visible()
    tela.loc(f'//a[@href="{SUBSTITUIR_DEMANDANTE.format(area.pk, demandante.pk)}"]').first.click()
    popup = tela.popup()
    popup.ver_texto('Atualizar/substituir demandante')
    popup.preencher('Demandantes', 'Autocomplete Multiplo', '105005')
    popup.salvar_no_popup('Enviar')
    tela.sucesso('Demandante atualizado/substituído com sucesso.')
    assert AreaAtuacaoDemanda.objects.get(pk=area.pk).demandantes.filter(username='105005').exists(), (
        'a UI disse que substituiu, mas o novo demandante não entrou na área'
    )
