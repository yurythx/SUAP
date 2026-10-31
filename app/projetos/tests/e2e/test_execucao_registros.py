"""Fluxo: os registros da execução — fotos, lições aprendidas, beneficiários atendidos, comprovantes de parceria, ocorrências e visitas técnicas.

O coordenador documenta a execução: sobe fotos, registra lições aprendidas, informa quantas
pessoas cada público-alvo de fato atendeu (feature 006) e anexa os comprovantes de parceria/adesão.
O Coordenador de Extensão do campus (ou o Gerente Sistêmico) registra ocorrências no projeto, e só
quem registrou a edita ou exclui. A visita técnica é do campus, lida pelo Coordenador de Extensão
e pelo gerente. As sondas de acesso cobrem quem não coordena o projeto — e o id do filho na
QUERYSTRING (``?deletar_licao``/``?editar_licao``), a forma vulnerável de #17490.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, outra_uo, vinculo

if TYPE_CHECKING:
    from projetos.models import VisitaTecnica

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ADICIONAR_FOTO = '/projetos/adicionar_foto/{}/'
REMOVER_FOTO = '/projetos/remover_foto/{}/'
LICAO = '/projetos/adicionar_licao_aprendida/{}/'
BENEFICIARIO_ATENDIDO = '/projetos/registro_beneficiario_atendido/{}/'
ADICIONAR_TERMO = '/projetos/adicionar_termo/{}/'
EDITAR_TERMO = '/projetos/editar_termo/{}/'
EXCLUIR_TERMO = '/projetos/excluir_termo/{}/'
REGISTRAR_OCORRENCIA = '/projetos/registrar_ocorrencia/{}/'
EDITAR_OCORRENCIA = '/projetos/editar_ocorrencia/{}/'
EXCLUIR_OCORRENCIA = '/projetos/excluir_ocorrencia/{}/'
VISITAS = '/admin/projetos/visitatecnica/'
VISUALIZAR_VISITA = '/projetos/visualizar_visita_tecnica/{}/'


def test_fotos_adicionar_e_remover(logado_projetos, projeto_em_execucao):
    from projetos.models import FotoProjeto

    projeto = projeto_em_execucao().projeto
    legenda = f'Oficina com a comunidade {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Fotos')
    clicar_em(tela, ADICIONAR_FOTO.format(projeto.pk))
    tela.ver_titulo('Adicionar Foto').preencher_formulario([('Legenda', 'textarea', legenda), ('Imagem', 'arquivo', 'foto.png')])
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Foto adicionada com sucesso.')
    foto = FotoProjeto.objects.filter(projeto=projeto, legenda=legenda).first()
    assert foto is not None, 'a UI disse que adicionou, mas a foto não persistiu'
    assert foto.imagem.name.endswith('.png'), f'a foto foi gravada sem a imagem: {foto.imagem.name!r}'

    tela.ir(PROJETO.format(projeto.pk)).clicar_aba('Fotos')  # `httprr('..')` não volta ao projeto
    clicar_em(tela, REMOVER_FOTO.format(foto.pk))  # `.btn.danger`: o `logado` aceita o confirm
    tela.esperar().sucesso('Foto removida com sucesso.')
    assert not FotoProjeto.objects.filter(pk=foto.pk).exists(), 'a UI disse que removeu, mas a foto continua'


def test_licoes_aprendidas_ciclo_completo(logado_projetos, projeto_em_execucao):
    """Adicionar → editar (``?editar_licao``) → excluir (``?deletar_licao``), todos na mesma rota."""
    from projetos.models import LicaoAprendida

    projeto = projeto_em_execucao().projeto
    descricao = f'Envolver a comunidade desde o planejamento {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Lições aprendidas')
    clicar_em(tela, LICAO.format(projeto.pk))
    tela.ver_titulo('Adicionar Lição Aprendida').preencher_formulario(
        [('Área', 'autocomplete', 'GERENCIAMENTO DOS RISCOS'), ('Descrição', 'textarea', descricao)]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Lição adicionada com sucesso.')
    licao = LicaoAprendida.objects.filter(projeto=projeto, descricao=descricao).first()
    assert licao is not None, 'a UI disse que adicionou, mas a lição não persistiu'
    assert licao.area_licao_aprendida.descricao == 'GERENCIAMENTO DOS RISCOS'

    tela.ir(PROJETO.format(projeto.pk)).clicar_aba('Lições aprendidas')  # `httprr('..')` não volta ao projeto
    clicar_em(tela, f'{LICAO.format(projeto.pk)}?editar_licao={licao.pk}')
    tela.preencher('Descrição', 'textarea', f'{descricao} (revista)').clicar_botao('Salvar')
    tela.esperar().sucesso('Lição adicionada com sucesso.')
    licao.refresh_from_db()
    assert licao.descricao.endswith('(revista)'), 'a UI disse que editou, mas não persistiu'

    tela.ir(PROJETO.format(projeto.pk)).clicar_aba('Lições aprendidas')
    clicar_em(tela, f'{LICAO.format(projeto.pk)}?deletar_licao={licao.pk}')  # `.icon-delete`
    tela.esperar().sucesso('Lição excluída com sucesso.')
    assert not LicaoAprendida.objects.filter(pk=licao.pk).exists(), 'a UI disse que excluiu, mas a lição continua'


def test_registrar_beneficiarios_atendidos(logado_projetos, projeto_em_execucao):
    """ "Registrar" na caracterização do projeto aprovado (popup): quantidade atendida e descrição do público."""
    execucao = projeto_em_execucao()
    caracterizacao = execucao.caracterizacao
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(execucao.projeto.pk))

    tela.clicar_aba('Caracterização dos beneficiários')
    clicar_em(tela, BENEFICIARIO_ATENDIDO.format(caracterizacao.pk))
    popup = popup_em(tela, BENEFICIARIO_ATENDIDO.format(caracterizacao.pk)).preencher_formulario(
        [('Quantidade Atendida', 'texto', '12'), ('Descreva os Beneficiários do Público-Alvo', 'textarea', 'Estudantes do ensino médio.')]
    )
    popup.salvar_no_popup('Salvar').sucesso('Caracterização registrada com sucesso.')
    caracterizacao.refresh_from_db()
    assert (caracterizacao.quantidade_atendida, caracterizacao.descricao_beneficiario) == (12, 'Estudantes do ensino médio.'), (
        'a UI disse que registrou, mas não persistiu'
    )


def test_comprovantes_de_parceria_ciclo_completo(logado_projetos, projeto_em_execucao):
    """Adicionar (popup) → editar (popup) → excluir, no quadro "Comprovantes de Parceria/Adesão" da aba "Dados do projeto"."""
    from projetos.models import TermoParceriaAdesao

    projeto = projeto_em_execucao().projeto
    descricao = f'Ofício da escola parceira {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, ADICIONAR_TERMO.format(projeto.pk))
    popup = popup_em(tela, ADICIONAR_TERMO.format(projeto.pk)).preencher_formulario(
        [('Descrição', 'texto', descricao), ('Comprovante de Parceria/Adesão', 'arquivo', 'oficio.pdf')]
    )
    tela = popup.salvar_no_popup('Salvar').sucesso('Comprovante de Parceria/Adesão cadastrado com sucesso.')
    termo = TermoParceriaAdesao.objects.filter(projeto=projeto, descricao=descricao).first()
    assert termo is not None, 'a UI disse que cadastrou, mas o comprovante não persistiu'

    clicar_em(tela, EDITAR_TERMO.format(termo.pk))
    popup = popup_em(tela, EDITAR_TERMO.format(termo.pk)).preencher('Descrição', 'texto', f'{descricao} (assinado)')
    tela = popup.salvar_no_popup('Salvar').sucesso('Comprovante de Parceria/Adesão editado com sucesso.')
    termo.refresh_from_db()
    assert termo.descricao.endswith('(assinado)'), 'a UI disse que editou, mas não persistiu'

    clicar_em(tela, EXCLUIR_TERMO.format(termo.pk))  # `.icon-delete`
    tela.esperar().sucesso('Comprovante de Parceria/Adesão excluído com sucesso.')
    assert not TermoParceriaAdesao.objects.filter(pk=termo.pk).exists(), 'a UI disse que excluiu, mas o comprovante continua'


def test_estranho_nao_mexe_nos_registros_da_execucao(logado_projetos, projeto_em_execucao):
    """Coordenador de OUTRO projeto: todas as rotas de registro da execução dão 403, e nada é apagado pelas remoções por GET.

    ``registro_beneficiario_atendido`` não chama ``tem_permissao``: quem barra é
    ``Projeto.pode_registrar_execucao``, que pergunta se o usuário da thread gerencia o projeto.
    """
    from projetos.tests.factories import FotoProjetoFactory, LicaoAprendidaFactory, TermoParceriaAdesaoFactory

    execucao = projeto_em_execucao()
    projeto = execucao.projeto
    foto, licao, termo = FotoProjetoFactory(projeto=projeto), LicaoAprendidaFactory(projeto=projeto), TermoParceriaAdesaoFactory(projeto=projeto)
    rotas = [
        ADICIONAR_FOTO.format(projeto.pk),
        REMOVER_FOTO.format(foto.pk),
        LICAO.format(projeto.pk),
        f'{LICAO.format(projeto.pk)}?deletar_licao={licao.pk}',
        BENEFICIARIO_ATENDIDO.format(execucao.caracterizacao.pk),
        ADICIONAR_TERMO.format(projeto.pk),
        EDITAR_TERMO.format(termo.pk),
        EXCLUIR_TERMO.format(termo.pk),
    ]
    tela = Tela(logado_projetos('outro_coordenador'))

    respostas = {rota: tela.buscar(rota).status for rota in rotas}
    assert respostas == dict.fromkeys(rotas, 403), f'rotas que não barraram o estranho: { {r: s for r, s in respostas.items() if s != 403} }'
    for objeto in (foto, licao, termo):
        assert type(objeto).objects.filter(pk=objeto.pk).exists(), f'{type(objeto).__name__} apagado por uma rota que respondeu 403'


def test_coordenador_nao_apaga_nem_toma_licao_de_projeto_alheio(logado_projetos, projeto_em_execucao):
    from projetos.models import LicaoAprendida
    from projetos.tests.factories import LicaoAprendidaFactory

    proprio = projeto_em_execucao(sufixo='proprio').projeto
    alheio = projeto_em_execucao(coordenador='outro_coordenador', sufixo='alheio').projeto
    apagada, tomada = LicaoAprendidaFactory(projeto=alheio), LicaoAprendidaFactory(projeto=alheio)
    tela = Tela(logado_projetos('coordenador_projeto'))

    tela.buscar(f'{LICAO.format(proprio.pk)}?deletar_licao={apagada.pk}')
    edicao = f'{LICAO.format(proprio.pk)}?editar_licao={tomada.pk}'
    if tela.buscar(edicao).status == 200:  # o defeito: a lição alheia abre, preenchida
        tela.ir(edicao).clicar_botao('Salvar')
        tela.esperar()
    restantes = dict(LicaoAprendida.objects.filter(pk__in=[apagada.pk, tomada.pk]).values_list('pk', 'projeto'))
    assert restantes == {apagada.pk: alheio.pk, tomada.pk: alheio.pk}, f'lições do projeto alheio apagadas ou transferidas: {restantes}'


# -------------------------------------------------------------------------- ocorrências


def test_ocorrencias_ciclo_completo(logado_projetos, projeto_em_execucao):
    """O Coordenador de Extensão do campus registra, edita e exclui uma ocorrência (aba "Ocorrências")."""
    from projetos.models import OcorrenciaProjeto

    projeto = projeto_em_execucao().projeto
    # Sem acento nem travessão: o TinyMCE grava entidades (``&ccedil;``), e a busca no ORM é pelo texto.
    texto = f'Bolsista afastado por licenca medica {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_extensao')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Ocorrências')
    clicar_em(tela, REGISTRAR_OCORRENCIA.format(projeto.pk))
    tela.ver_titulo(f'Registrar Ocorrência - Projeto: {projeto.titulo}').preencher('Ocorrência', 'texto rico', texto).clicar_botao('Salvar')
    tela.esperar().sucesso('Ocorrência registrada com sucesso.')
    ocorrencia = OcorrenciaProjeto.objects.filter(projeto=projeto, ocorrencia__contains=texto).first()
    assert ocorrencia is not None, 'a UI disse que registrou, mas a ocorrência não persistiu'
    assert ocorrencia.cadastrada_por == vinculo('coordenador_extensao')

    tela.clicar_aba('Ocorrências')
    clicar_em(tela, EDITAR_OCORRENCIA.format(ocorrencia.pk))
    tela.preencher('Ocorrência', 'texto rico', f'{texto} - retornou').clicar_botao('Salvar')
    tela.esperar().sucesso('Ocorrência editada com sucesso.')
    ocorrencia.refresh_from_db()
    assert 'retornou' in ocorrencia.ocorrencia, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba('Ocorrências')
    clicar_em(tela, EXCLUIR_OCORRENCIA.format(ocorrencia.pk))  # `.icon-delete`
    tela.esperar().sucesso('Ocorrência excluída com sucesso.')
    assert not OcorrenciaProjeto.objects.filter(pk=ocorrencia.pk).exists(), 'a UI disse que excluiu, mas a ocorrência continua'


@pytest.mark.parametrize(
    ('papel', 'outro_campus', 'status'),
    [
        ('coordenador_extensao', False, 200),
        ('gerente', True, 200),
        # Papel LOCAL (decisão 42): o Coordenador de Extensão só registra ocorrência no próprio campus.
        ('coordenador_extensao', True, 403),
        ('coordenador_projeto', False, 403),
    ],
)
def test_registrar_ocorrencia_por_papel(logado_projetos, projeto_em_execucao, papel, outro_campus, status):
    projeto = projeto_em_execucao(uo=outra_uo() if outro_campus else None).projeto
    assert Tela(logado_projetos(papel)).buscar(REGISTRAR_OCORRENCIA.format(projeto.pk)).status == status


def test_so_quem_registrou_edita_ou_exclui_a_ocorrencia(logado_projetos, projeto_em_execucao):
    from projetos.models import OcorrenciaProjeto
    from projetos.tests.factories import OcorrenciaProjetoFactory

    ocorrencia = OcorrenciaProjetoFactory(projeto=projeto_em_execucao().projeto, cadastrada_por=vinculo('coordenador_extensao'))
    tela = Tela(logado_projetos('gerente'))

    assert (tela.buscar(EDITAR_OCORRENCIA.format(ocorrencia.pk)).status, tela.buscar(EXCLUIR_OCORRENCIA.format(ocorrencia.pk)).status) == (403, 403)
    assert OcorrenciaProjeto.objects.filter(pk=ocorrencia.pk).exists(), 'a ocorrência foi apagada por uma rota que respondeu 403'


def test_icones_de_ocorrencia_oferecidos_abrem(logado_projetos, projeto_em_execucao):
    from projetos.tests.factories import OcorrenciaProjetoFactory

    projeto = projeto_em_execucao().projeto
    ocorrencia = OcorrenciaProjetoFactory(projeto=projeto, cadastrada_por=vinculo('coordenador_extensao'))
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Ocorrências').linha(ocorrencia.ocorrencia.removeprefix('<p>').removesuffix('</p>'))
    rota = EDITAR_OCORRENCIA.format(ocorrencia.pk)
    oferecido = tela.loc(f'//a[@href="{rota}"]').count() > 0
    status = tela.buscar(rota).status
    assert not oferecido or status == 200, f'a aba oferece a edição da ocorrência de outro autor, e a rota responde {status}'


# ----------------------------------------------------------------------- visita técnica


@pytest.fixture
def visita_tecnica(projetos_seed) -> Iterator[VisitaTecnica]:
    """Visita técnica do campus CZN; apagada no fim (não é filha de edital, a cascata não a leva)."""
    from projetos.tests.factories import ObjetivoVisitaTecnicaFactory, VisitaTecnicaFactory

    visita = VisitaTecnicaFactory(
        campus=projetos_seed.uo,
        instituicao_visitada=f'Escola parceira {uuid4().hex[:8]}',
        objetivos=[ObjetivoVisitaTecnicaFactory(descricao='Prospectar parceria E2E')],
    )
    yield visita
    visita.delete()


def test_gerente_visualiza_a_visita_tecnica(logado_projetos, visita_tecnica):
    """Da lista de visitas técnicas (admin), o ícone de visualizar abre a ficha da visita."""
    tela = Tela(logado_projetos('gerente')).ir(VISITAS)

    clicar_em(tela, VISUALIZAR_VISITA.format(visita_tecnica.pk))
    tela.ver_titulo(str(visita_tecnica)).ver_texto('Prospectar parceria E2E').ver_texto(visita_tecnica.nome_contato)


@pytest.mark.parametrize(('papel', 'status'), [('coordenador_extensao', 200), ('gerente', 200), ('coordenador_projeto', 403)])
def test_visita_tecnica_por_papel(logado_projetos, visita_tecnica, papel, status):
    assert Tela(logado_projetos(papel)).buscar(VISUALIZAR_VISITA.format(visita_tecnica.pk)).status == status


def test_lista_de_visitas_oferece_a_visualizacao(logado_projetos, visita_tecnica):
    """O Coordenador de Extensão também chega à ficha pela lista (a coluna "Ações" do admin)."""
    tela = Tela(logado_projetos('coordenador_extensao')).ir(VISITAS)
    expect(tela.loc(f'//a[@href="{VISUALIZAR_VISITA.format(visita_tecnica.pk)}"]')).to_have_count(1)
