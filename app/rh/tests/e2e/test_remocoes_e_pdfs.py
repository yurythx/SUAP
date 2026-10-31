# ruff: noqa: UP032
"""Ações por GET do RH: validar foto, remoções, crachá/carteira e os dados do organograma.

São rotas sem formulário próprio — um link numa tela que a suíte já abre dispara a gravação. Cada teste
cria o objeto que vai consumir (a suíte não dá flush) e afirma a mensagem e o banco. Crachá e carteira
afirmam o tipo do documento devolvido: uma view de PDF ainda pode responder 500, ou um 302 de "dados
insuficientes" que um smoke por status não distinguiria de sucesso.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from uuid import uuid4

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela
from rh.tests.factories import (
    AgendaAtendimentoHorarioFactory,
    CargaHorariaReduzidaFactory,
    DocumentacaoExigidaFactory,
    HorarioSemanalFactory,
    ServidorFactory,
    SetorFactory,
    SetorJornadaHistoricoFactory,
    SituacaoFactory,
    SolicitacaoAlteracaoFotoFactory,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DETALHE_FOTO = '/rh/detalhe_solicitacao_alteracao_foto/{}/'
VALIDAR_FOTO = '/rh/validaralteracaofoto/{}/'
ADICIONAR_HORARIO = '/rh/adicionar_horario/{}/'
REMOVER_HORARIO = '/rh/remover_horario/{}/'
JORNADAS_DO_SETOR = '/rh/setor_jornada_historico/{}/'
REMOVER_JORNADA = '/rh/setor_jornada_historico_remover/{}/'
PROCESSO = '/rh/abrir_processo_afastamento_parcial/{}/'
REMOVER_HORARIO_AFASTAMENTO = '/rh/remover_horario_afastamento/{}/'
EXCLUIR_PROCESSO = '/rh/excluir_processo_afastamento_parcial/{}/'
CRACHA_PESSOA = '/rh/cracha_pessoa/{}/'
CRACHA_SETOR = '/rh/cracha_setor/{}/'
CARTEIRA = '/rh/carteira_funcional/{}/'
CARTEIRA_DA_SESSAO = '/rh/carteira_funcional/'
CARTEIRAS_DO_SETOR = '/rh/carteira_funcional_setor/{}/all/'
CARTEIRA_MODELO_2016 = '/rh/imprimir_carteira_funcional_pdf/'
ORGANOGRAMA_DADOS = '/rh/organograma/data/'


def _servidor(setor: object, **campos: object) -> object:
    return ServidorFactory(matricula=str(int(uuid4().hex[:8], 16)), setor=setor, pessoa_fisica__nome='Servidor E2E ' + uuid4().hex[:10], **campos)


def _com_foto(servidor: object) -> None:
    """Grava uma foto real no vínculo: crachá e carteira desenham a imagem e a miniatura 150x200."""
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image

    imagem = BytesIO()
    Image.new('RGB', (150, 200), 'gray').save(imagem, 'JPEG')
    servidor.get_vinculo().foto.save('{}.jpg'.format(servidor.matricula), ContentFile(imagem.getvalue()))


@pytest.fixture
def tipos_de_documento() -> Iterator[None]:
    """Crachá e carteira exigem um ``DocumentoControleTipo`` por identificador, com a situação do servidor na abrangência.

    O seed não traz nenhum, e é configuração global do banco reusado: cria só o que falta e apaga no fim,
    para não mudar o que as outras suítes (``comum/tests/e2e``) medem. Model do ``comum`` sem factory:
    segue o precedente de ``comum/tests/e2e/conftest.py``.
    """
    from comum.models import DocumentoControleTipo

    criados = []
    for identificador in (DocumentoControleTipo.CRACHA, DocumentoControleTipo.CARTEIRA_FUNCIONAL):
        tipo = DocumentoControleTipo.objects.filter(identificador=identificador).first()
        if tipo is None:
            tipo = DocumentoControleTipo.objects.create(identificador=identificador)
            criados.append(tipo.pk)
        tipo.abrangencia.add(SituacaoFactory())
    yield
    DocumentoControleTipo.objects.filter(pk__in=criados).delete()


def test_validar_foto(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """O caminho feliz da troca de foto: a imagem enviada vira a foto do vínculo do solicitante."""
    tela = Tela(logado_rh('sistemico'))
    from comum.models import Vinculo
    from rh.models import SolicitacaoAlteracaoFoto

    solicitante = _servidor(rh_seed['setor'])
    solicitacao = SolicitacaoAlteracaoFotoFactory(solicitante=solicitante)
    validar = VALIDAR_FOTO.format(solicitacao.pk)
    tela.ir(DETALHE_FOTO.format(solicitacao.pk)).ver_titulo('Solicitação de Alteração de Foto')
    assert tela.loc('//a[@href="{}"]'.format(validar)).count() == 1
    tela.clicar_botao('Validar')
    tela.sucesso('Solicitação validada com sucesso.')
    assert SolicitacaoAlteracaoFoto.objects.filter(
        pk=solicitacao.pk, situacao=SolicitacaoAlteracaoFoto.VALIDADA, responsavel_interacao=rh_seed['sistemico']
    ).exists(), 'a UI disse que validou, mas a solicitação não mudou'
    assert Vinculo.objects.get(pk=solicitante.get_vinculo().pk).foto, 'validou, mas a foto não chegou ao vínculo do solicitante'


def test_servidor_nao_valida_foto_de_outro(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('servidor'))
    from rh.models import SolicitacaoAlteracaoFoto

    solicitacao = SolicitacaoAlteracaoFotoFactory(solicitante=_servidor(rh_seed['setor']))
    resposta = tela.buscar(VALIDAR_FOTO.format(solicitacao.pk))
    situacao = SolicitacaoAlteracaoFoto.objects.get(pk=solicitacao.pk).get_situacao_display()
    assert resposta.status == 403, f'servidor comum validou a foto de outro: HTTP {resposta.status}, situação {situacao!r}'


def test_remover_horario_de_atendimento(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('saude'))
    from rh.models import AgendaAtendimentoHorario

    horario = AgendaAtendimentoHorarioFactory(profissional=rh_seed['saude'])
    tela.ir(ADICIONAR_HORARIO.format(horario.acao_saude_id))
    assert tela.loc('//a[@href="{}"]'.format(REMOVER_HORARIO.format(horario.pk))).count() == 1
    tela.clicar_botao('Remover')
    tela.sucesso('Horário removido com sucesso.')
    assert not AgendaAtendimentoHorario.objects.filter(pk=horario.pk).exists(), 'a UI disse que removeu, mas o horário ficou'


def test_remover_jornada_do_setor(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import SetorJornadaHistorico

    setor = SetorFactory(sigla='JR' + uuid4().hex[:8], superior=rh_seed['setor'], campus=False)
    jornada = SetorJornadaHistoricoFactory(setor=setor)
    tela.ir(JORNADAS_DO_SETOR.format(setor.pk))
    assert tela.loc('//a[@href="{}"]'.format(REMOVER_JORNADA.format(jornada.pk))).count() == 1
    tela.clicar_icone('remoção')
    tela.sucesso('Histórico removido com sucesso.')
    assert not SetorJornadaHistorico.objects.filter(pk=jornada.pk).exists(), 'a UI disse que removeu, mas o histórico ficou'


def test_remover_horario_de_afastamento(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """Remover o horário devolve o processo para "Alterando horário" — é o que reabre a edição."""
    tela = Tela(logado_rh('sistemico'))
    from rh.models import CargaHorariaReduzida, HorarioSemanal

    # Jornada do seed: com a da factory ('40h'), `get_carga_horaria_disponivel_choice` faz None * 5 e a tela dá 500.
    servidor = _servidor(rh_seed['setor'], jornada_trabalho=rh_seed['servidor'].jornada_trabalho)
    processo = CargaHorariaReduzidaFactory(servidor=servidor)
    horario = HorarioSemanalFactory(processo_reducao_ch=processo)
    tela.ir(PROCESSO.format(processo.pk))
    tela.loc('//a[@href="{}"]'.format(REMOVER_HORARIO_AFASTAMENTO.format(horario.pk))).click()
    tela.sucesso('Horário removido com sucesso.')
    assert not HorarioSemanal.objects.filter(pk=horario.pk).exists(), 'a UI disse que removeu, mas o horário ficou'
    assert CargaHorariaReduzida.objects.filter(pk=processo.pk, status=CargaHorariaReduzida.STATUS_ALTERANDO_HORARIO).exists()


def test_servidor_nao_remove_horario_de_outro(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('servidor'))
    from rh.models import HorarioSemanal

    processo = CargaHorariaReduzidaFactory(servidor=_servidor(rh_seed['setor']))
    horario = HorarioSemanalFactory(processo_reducao_ch=processo)
    resposta = tela.buscar(REMOVER_HORARIO_AFASTAMENTO.format(horario.pk))
    existe = HorarioSemanal.objects.filter(pk=horario.pk).exists()
    assert resposta.status == 403, f'servidor comum removeu o horário do processo de outro: HTTP {resposta.status}, horário ainda existe: {existe}'


def test_processo_de_servidor_com_jornada_fora_da_lista(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """``JornadaTrabalho.get_jornada_trabalho_diaria`` devolve ``None`` fora dos 5 nomes fixos, e o ``or 40.0`` nunca roda."""
    tela = Tela(logado_rh('sistemico'))
    from rh.tests.factories import JornadaTrabalhoFactory

    jornada = JornadaTrabalhoFactory(codigo='E2ERHX', nome='JORNADA E2E FORA DA LISTA')
    processo = CargaHorariaReduzidaFactory(servidor=_servidor(rh_seed['setor'], jornada_trabalho=jornada))
    resposta = tela.buscar(PROCESSO.format(processo.pk))
    assert resposta.status == 200, f'tela do processo respondeu HTTP {resposta.status}'


def test_excluir_processo_proprio(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """Entra pela URL: nenhuma tela alcança o link.

    O único link (``opcoes`` de ``CargaHorariaReduzidaAdmin``) só aparece para o dono de um processo
    "Aguardando envio para o chefe", e a listagem do admin filtra justamente esse status para o RH e
    nega a tela a quem não é RH. O dono aqui é do RH sistêmico para a mensagem aparecer na volta.
    """
    tela = Tela(logado_rh('sistemico'))
    from rh.models import CargaHorariaReduzida

    processo = CargaHorariaReduzidaFactory(servidor=rh_seed['sistemico'], status=CargaHorariaReduzida.STATUS_AGUARDANDO_ENVIO_CHEFE)
    tela.ir(EXCLUIR_PROCESSO.format(processo.pk))
    tela.sucesso('Processo excluído com sucesso.')
    assert not CargaHorariaReduzida.objects.filter(pk=processo.pk).exists(), 'a UI disse que excluiu, mas o processo ficou'


@pytest.mark.parametrize(
    ('resposta', 'esperado'),
    [
        ({'status': 200, 'body': '{"ok": false, "msg": "Recusado pelo servidor."}'}, 'Recusado pelo servidor.'),
        ({'status': 404, 'body': '<h1>Não encontrado</h1>', 'content_type': 'text/html'}, 'Não foi possível excluir o arquivo.'),
        ({'status': 403, 'body': '{"ok": false, "msg": "Sem permissão."}'}, 'Sem permissão.'),
    ],
    ids=['ok_false', 'http_sem_json', 'http_com_json'],
)
def test_exclusao_de_documento_recusada_mostra_a_mensagem(logado_rh: Callable[[str], Page], rh_seed: dict, resposta: dict, esperado: str) -> None:
    """A recusa chega ao usuário como texto, não como "undefined" nem como erro de JS.

    O ícone só aparece a quem pode excluir, então a recusa da view é simulada na rota do ajax; o que se
    afirma é o alerta do template e que o documento continua na tela.
    """
    pagina = logado_rh('sistemico')
    tela = Tela(pagina)
    from rh.models import CargaHorariaReduzida

    processo = CargaHorariaReduzidaFactory(servidor=rh_seed['servidor'], tipo=CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL)
    documento = DocumentacaoExigidaFactory(processo=processo, diretorio='cargahoraria/{}.pdf'.format(uuid4().hex))
    pagina.route('**/rh/excluir_documentacao_pdf/**', lambda rota: rota.fulfill(**{'content_type': 'application/json', **resposta}))
    alertas: list[str] = []

    def _dialogo(dialogo: object) -> None:
        if dialogo.type == 'alert':
            alertas.append(dialogo.message)
        dialogo.accept()

    pagina.on('dialog', _dialogo)
    tela.ir(PROCESSO.format(processo.pk))
    linha = '//tr[@id="linha-{}"]'.format(documento.encrypted_pk)
    pagina.locator(linha + '//a[contains(@class, "icon-delete")]').click()
    pagina.wait_for_function('() => jQuery.active === 0')
    assert alertas == [esperado], f'alerta mostrado: {alertas!r}'
    assert pagina.locator(linha).is_visible()


def test_servidor_nao_exclui_processo_de_outro(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('servidor'))
    from rh.models import CargaHorariaReduzida

    processo = CargaHorariaReduzidaFactory(servidor=_servidor(rh_seed['setor']))
    resposta = tela.buscar(EXCLUIR_PROCESSO.format(processo.pk))
    existe = CargaHorariaReduzida.objects.filter(pk=processo.pk).exists()
    assert resposta.status == 403, f'servidor comum excluiu o processo de outro: HTTP {resposta.status}, processo ainda existe: {existe}'


def test_cracha_e_carteira_funcional(logado_rh: Callable[[str], Page], rh_seed: dict, tipos_de_documento: None) -> None:
    """Servidor elegível num setor só dele: crachá e carteira saem em PDF, individual e por setor.

    A carteira modelo 2016 é ``@documento``: sob teste ele devolve o HTML do documento em vez do PDF
    (``running_tests``), e é esse HTML que se afirma. Ela e a carteira sem servidor na URL leem os ids
    da sessão, gravados pela carteira individual.
    """
    tela = Tela(logado_rh('sistemico'))
    from comum.tests.factories import MunicipioFactory

    # Sigla que ordena DEPOIS de E2ERH: `test_setor_equivalencia_e_bases_legais` pega a primeira linha da listagem
    # de setores que contém "E2ERH", e todo filho do campus traz "RAIZ → E2ERH → ..." no caminho.
    setor = SetorFactory(sigla='RHCR' + uuid4().hex[:6], superior=rh_seed['setor'], campus=False)
    servidor = _servidor(
        setor,
        pessoa_fisica__nome_mae='Mãe E2E',
        pessoa_fisica__rg='1234567',
        pessoa_fisica__rg_orgao='SSP',
        pessoa_fisica__rg_uf='RN',
        pessoa_fisica__nascimento_data=date(1980, 5, 17),
        pessoa_fisica__nascimento_municipio=MunicipioFactory(),
        pessoa_fisica__grupo_sanguineo='O',
        pessoa_fisica__fator_rh='+',
    )
    _com_foto(servidor)
    assert servidor.pode_gerar_cracha(), 'servidor do teste não é elegível ao crachá'
    assert servidor.pode_gerar_carteira_funcional(), 'servidor do teste não é elegível à carteira'
    for url in (
        CRACHA_PESSOA.format(servidor.pessoa_fisica_id),
        CRACHA_SETOR.format(setor.pk),
        CARTEIRA.format(servidor.pk),
        CARTEIRA_DA_SESSAO,
        CARTEIRAS_DO_SETOR.format(setor.pk),
    ):
        resposta = tela.buscar(url)
        assert resposta.status == 200, f'{url}: HTTP {resposta.status} {resposta.headers.get("location", "")}'
        assert resposta.headers['content-type'] == 'application/pdf', f'{url}: {resposta.headers["content-type"]}'
        assert resposta.body().startswith(b'%PDF'), f'{url}: corpo não é PDF'
    resposta = tela.buscar(CARTEIRA_MODELO_2016)
    assert resposta.status == 200, resposta.text()[:1000]
    assert servidor.pessoa_fisica.nome.upper() in resposta.text()
    assert servidor.matricula in resposta.text()


def test_dados_do_organograma(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    """O JSON que o Highcharts da tela de organograma consome: o setor filho pendurado no campus."""
    tela = Tela(logado_rh('sistemico'))
    campus = rh_seed['setor']
    filho = SetorFactory(sigla='OG' + uuid4().hex[:8], superior=campus, campus=False)
    resposta = tela.buscar(ORGANOGRAMA_DADOS + '?setor_raiz={}'.format(campus.pk))
    assert resposta.status == 200, resposta.text()[:1000]
    assert resposta.headers['content-type'] == 'application/json'
    serie = resposta.json()['series'][0]
    assert [campus.sigla, filho.sigla] in serie['data'], f'ligação campus→filho ausente: {serie["data"]}'
    assert filho.sigla in [no['id'] for no in serie['nodes']]
