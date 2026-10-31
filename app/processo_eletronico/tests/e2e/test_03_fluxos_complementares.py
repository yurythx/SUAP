"""Fluxos complementares do Processo Eletrônico (modo 2)."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.utils.timezone import now
from playwright.sync_api import expect

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

NUP1 = '23001.000001.2019-68'
NUP2 = '23001.000002.2019-11'
PROCESSO_URL = '/processo_eletronico/processo/{}/'
ALTERAR_NIVEL_URL = '/processo_eletronico/alterar_nivel_acesso_processo/{}/'
ENCAMINHAR_SEM_URL = '/processo_eletronico/processo/encaminhar_sem_despacho/{}/'
ENCAMINHAR_URL = '/processo_eletronico/processo/encaminhar/{}/'
RECEBER_URL = '/processo_eletronico/processo/receber/{}/'
EDITAR_INTERESSADOS_URL = '/processo_eletronico/processo/editar_interessados/{}/'
REMOVER_ULTIMO_URL = '/processo_eletronico/processo/remover_ultimo_tramite/{}/'
PRIORIDADE_URL = '/processo_eletronico/adicionar_prioridade/{}/'
ADD_COMMENT_URL = '/processo_eletronico/adicionar_comentario/{}/'
LISTAR_DOCUMENTOS_URL = '/processo_eletronico/listar_documentos_adicionar/{}/'
ADD_DOCUMENTO_URL = '/processo_eletronico/adicionar_documento/{}/{}/'
UPLOAD_URL = '/processo_eletronico/documento_upload/{}/'
SOLICITAR_CIENCIA_URL = '/processo_eletronico/solicitar_ciencia/{}/'
DAR_CIENCIA_URL = '/processo_eletronico/dar_ciencia/{}/'
SOLICITAR_DESPACHO_URL = '/processo_eletronico/solicitar_despacho/{}/'
DEFERIR_DESPACHO_URL = '/processo_eletronico/solicitar_despacho/deferir/{}/'
ACOMPANHAR_URL = '/processo_eletronico/processo/acompanhar/{}/'
DESACOMPANHAR_URL = '/processo_eletronico/processo/desacompanhar/{}/'


def _processo(numero: str) -> Any:
    from processo_eletronico.models import Processo

    return Processo.objects.get(numero_protocolo=numero)


def _usuario(matricula: str) -> Any:
    from rh.models import Servidor

    return Servidor.objects.get(matricula=matricula).get_user()


def _vinculo(matricula: str) -> Any:
    return _usuario(matricula).get_vinculo()


def _detalhe(tela: Tela, numero: str) -> Tela:
    processo = _processo(numero)
    return tela.ir(PROCESSO_URL.format(processo.pk)).ver_titulo(f'Processo {numero}')


def _senha(tela: Tela) -> Tela:
    campo = tela.loc('//input[@type="password"]').first
    expect(campo).to_be_visible()
    campo.fill(SENHA_E2E)
    return tela


def _selecionar_checkbox_popup(tela: Tela, campo: str, valor: str) -> Tela:
    seletor = (
        '//input[contains(@class, "popup_multiple_choice_field") and '
        f'ancestor::div[preceding-sibling::label[contains(normalize-space(text()), "{campo}")]]]'
    )
    item = tela.loc(seletor).first
    expect(item).to_be_visible()
    item.click()
    popup = tela.popup_ajax()
    opcao = popup.loc(f'//input[contains(@title, "{valor}")]').first
    expect(opcao).to_be_visible()
    opcao.click()
    popup.clicar_botao('Confirmar')
    return tela


@pytest.fixture(autouse=True)
def limpar_fluxos_complementares(estado_processo: None) -> None:
    """Remove efeitos persistentes dos fluxos complementares entre testes."""
    from processo_eletronico.models import (
        ComentarioProcesso,
        DocumentoDigitalizadoProcesso,
        DocumentoTextoProcesso,
        PrioridadeTramite,
        Processo,
        SolicitacaoCiencia,
        SolicitacaoDespacho,
    )

    processos = Processo.objects.filter(numero_protocolo__in=[NUP1, NUP2])
    ComentarioProcesso.objects.filter(processo__in=processos).delete()
    DocumentoDigitalizadoProcesso.objects.filter(processo__in=processos).delete()
    DocumentoTextoProcesso.objects.filter(processo__in=processos).delete()
    PrioridadeTramite.objects.filter(tramite__processo__in=processos).delete()
    SolicitacaoCiencia.objects.filter(processo__in=processos).delete()
    SolicitacaoDespacho.objects.filter(processo__in=processos).delete()
    for processo in processos:
        processo.acompanhantes_processo.clear()


@pytest.fixture
def solicitacao_despacho_local(processo_seed: bool) -> Any:
    """Cria uma solicitação pendente para o operador A1 deferir pela UI."""
    from processo_eletronico.models import SolicitacaoDespacho
    from rh.models import Setor

    processo = _processo(NUP1)
    return SolicitacaoDespacho.objects.create(
        processo=processo,
        despacho_corpo='Despacho criado pela massa e2e.',
        remetente_setor=Setor.objects.suap().get(sigla='A1'),
        remetente_vinculo=_vinculo('128002'),
        solicitado=_vinculo('128001'),
        destinatario_setor_tramite=Setor.objects.suap().get(sigla='A2'),
    )


@pytest.fixture
def solicitacao_ciencia_local(processo_seed: bool) -> Any:
    """Cria uma solicitação de ciência pendente para o operador A2."""
    from processo_eletronico.models import SolicitacaoCiencia

    processo = _processo(NUP1)
    return SolicitacaoCiencia.objects.create(
        processo=processo,
        tramite=processo.ultimo_tramite,
        solicitante=_usuario('128002'),
        solicitado=_vinculo('128003'),
        data_limite_ciencia=now() + timedelta(days=30),
        motivo='Solicitação criada pela massa e2e.',
        tipo=SolicitacaoCiencia.TIPO_NOTIFICACAO,
    )


@pytest.fixture
def interesse_chefe_b(processo_seed: bool) -> Any:
    """Adiciona previamente o interesse do chefe B ao processo sem trâmite."""
    processo = _processo(NUP2)
    processo.acompanhantes_processo.add(_vinculo('128004'))
    return processo


def test_alterar_nivel_de_acesso(logado_processo_eletronico: Any) -> None:
    """Altera o nível do processo e informa a hipótese legal obrigatória."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(ALTERAR_NIVEL_URL.format(processo.pk))
    tela.ver_titulo(f'Alterar Nível de Acesso do Processo {NUP1}').preencher_formulario(
        [
            ('Para', 'lista', 'Restrito'),
            ('Hipótese Legal', 'lista', 'Informação Pessoal (Art. 31 da Lei no 12.527/2011)'),
        ]
    )
    _senha(tela).clicar_botao('Enviar').sucesso('Nível de Acesso alterado com sucesso.')

    from processo_eletronico.models import Processo

    processo = Processo.objects.get(pk=processo.pk)
    assert processo.nivel_acesso == Processo.NIVEL_ACESSO_RESTRITO
    assert str(processo.hipotese_legal) == 'Informação Pessoal (Art. 31 da Lei no 12.527/2011)'


def test_encaminhar_sem_despacho(logado_processo_eletronico: Any) -> None:
    """Encaminha o processo recebido para o setor A2 sem despacho."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(ENCAMINHAR_SEM_URL.format(processo.pk))
    tela.ver_titulo(f'Encaminhar Processo {NUP1}').preencher_formulario(
        [('Buscar setor de destino por', 'radio', 'Autocompletar'), ('Setor de Destino', 'autocomplete', 'A2')]
    )
    tela.clicar_botao('Salvar').sucesso('Processo encaminhado com sucesso.')

    processo = _processo(NUP1)
    assert processo.ultimo_tramite.destinatario_setor.sigla == 'A2'
    assert processo.ultimo_tramite.despacho_corpo is None


def test_receber_processo(logado_processo_eletronico: Any, processo_a_receber: Any) -> None:
    """Recebe no setor A2 o trâmite pendente do processo."""
    processo = processo_a_receber
    tela = Tela(logado_processo_eletronico('operador_b')).ir(RECEBER_URL.format(processo.pk))
    tela.sucesso('Processo recebido com sucesso.')

    tramite = processo.tramites.order_by('-pk').first()
    assert tramite.recebido_por == _vinculo('128003')
    assert tramite.data_hora_recebimento is not None


def test_editar_interessados(logado_processo_eletronico: Any) -> None:
    """Inclui o operador A2 nos interessados com justificativa e senha."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(EDITAR_INTERESSADOS_URL.format(processo.pk))
    tela.ver_titulo(f'Editar Interessados do Processo {NUP1}').preencher_formulario(
        [
            ('Interessados', 'autocomplete multiplo', 'Operador de Processo 2'),
            ('Justificativa', 'textarea', 'Alteração de interessados e2e'),
        ]
    )
    _senha(tela).clicar_botao('Enviar').sucesso('Os interessados do processo foram alterados com sucesso.')

    assert processo.interessados.filter(pessoa__nome='Operador de Processo 2').exists()


def test_alterar_nivel_de_prioridade(logado_processo_eletronico: Any) -> None:
    """Define a prioridade baixa no último trâmite do processo."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(PRIORIDADE_URL.format(processo.pk))
    tela.ver_titulo(f'Nível de prioridade do processo {NUP1}').preencher_formulario(
        [('Prioridade', 'radio', 'Baixa'), ('Justificativa', 'textarea', 'Prioridade definida no e2e')]
    ).clicar_botao('Salvar').sucesso('O nível de prioridade foi atualizado com sucesso.')

    from processo_eletronico.models import PrioridadeTramite

    prioridade = PrioridadeTramite.objects.get(tramite=processo.ultimo_tramite)
    assert prioridade.prioridade == PrioridadeTramite.BAIXA_PRIORIDADE


def test_adicionar_documentos(logado_processo_eletronico: Any) -> None:
    """Adiciona documento interno e upload externo assinado ao processo."""
    from documento_eletronico.models import DocumentoTexto, DocumentoDigitalizado
    from processo_eletronico.models import DocumentoDigitalizadoProcesso, DocumentoTextoProcesso

    processo = _processo(NUP1)
    documento = DocumentoTexto.objects.get(assunto='Documento Teste')
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(LISTAR_DOCUMENTOS_URL.format(processo.pk))
    tela.ver_titulo(f'Documentos que podem ser adicionados ao processo {processo}').ir(ADD_DOCUMENTO_URL.format(processo.pk, documento.pk)).sucesso(
        'Documento adicionado com sucesso.'
    )
    assert DocumentoTextoProcesso.objects.filter(processo=processo, documento=documento).exists()

    assunto = f'Documento externo e2e {uuid4().hex[:8]}'
    tela.ir(UPLOAD_URL.format(processo.pk)).ver_titulo('Upload de Documento Externo').preencher_formulario(
        [
            ('Tipo', 'autocomplete', 'Ofício'),
            ('Arquivo', 'arquivo', 'arquivo.pdf'),
            ('Tipo de Conferência', 'lista', 'Cópia Simples'),
            ('Assunto', 'texto', assunto),
            ('Nível de Acesso', 'lista', 'Público'),
        ]
    ).clicar_botao('Salvar')
    tela.ver_titulo('Upload de Documento Externo').preencher('Perfil', 'lista', 'Cargo A')
    _senha(tela).clicar_botao('Assinar Documento').sucesso('Documento anexado com sucesso.')

    assert DocumentoDigitalizadoProcesso.objects.filter(processo=processo, documento__assunto=assunto).exists()
    assert DocumentoDigitalizado.objects.filter(assunto=assunto).exists()


def test_adicionar_comentario(logado_processo_eletronico: Any) -> None:
    """Registra comentário no processo pela tela própria de comentário."""
    from processo_eletronico.models import ComentarioProcesso

    processo = _processo(NUP1)
    comentario = f'Comentário e2e {uuid4().hex[:8]}'
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(ADD_COMMENT_URL.format(processo.pk))
    tela.ver_titulo('Adicionar Comentário').preencher('Comentário', 'textarea', comentario).clicar_botao('Salvar')

    assert ComentarioProcesso.objects.filter(processo=processo, comentario=comentario).exists()


def test_solicitar_despacho(logado_processo_eletronico: Any) -> None:
    """Solicita assinatura de despacho ao operador A1 com destino A1."""
    from processo_eletronico.models import SolicitacaoDespacho

    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(SOLICITAR_DESPACHO_URL.format(processo.pk))
    tela.ver_titulo(f'Solicitação de despacho do {NUP1}').preencher_formulario(
        [
            ('Corpo', 'textarea', 'Autorizo encaminhar para A1.'),
            ('Solicitar Assinatura a', 'autocomplete', 'Operador de Processo 1'),
            ('Setor de Destino do Trâmite (Buscar por)', 'radio', 'Autocompletar'),
            ('Especificar Setor', 'autocomplete', 'A1'),
        ]
    )
    _senha(tela).clicar_botao('Salvar').sucesso('A solicitação de despacho foi efetuada com sucesso.')

    solicitacao = SolicitacaoDespacho.objects.get(processo=processo)
    assert solicitacao.em_espera()
    assert solicitacao.solicitado == _vinculo('128001')
    assert solicitacao.destinatario_setor_tramite.sigla == 'A1'


def test_deferir_despacho(logado_processo_eletronico: Any, solicitacao_despacho_local: Any) -> None:
    """Deferir a solicitação pendente cria o trâmite assinado para A2."""
    tela = Tela(logado_processo_eletronico('operador_a')).ir(DEFERIR_DESPACHO_URL.format(solicitacao_despacho_local.pk))
    tela.ver_titulo(f'Solicitação de Despacho do Processo {NUP1}').preencher('Perfil', 'lista', 'Cargo A')
    _senha(tela).clicar_botao('Deferir e Encaminhar').sucesso('Processo encaminhado com sucesso.')

    from processo_eletronico.models import SolicitacaoDespacho

    solicitacao_despacho_local = SolicitacaoDespacho.objects.get(pk=solicitacao_despacho_local.pk)
    assert solicitacao_despacho_local.deferida()
    assert solicitacao_despacho_local.tramite_gerado.destinatario_setor.sigla == 'A2'


def test_solicitar_ciencia(logado_processo_eletronico: Any) -> None:
    """Solicita ciência ao operador A2 com prazo futuro e notificação."""
    from processo_eletronico.models import SolicitacaoCiencia

    processo = _processo(NUP1)
    processo.interessados.add(_vinculo('128003'))
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(SOLICITAR_CIENCIA_URL.format(processo.pk))
    _selecionar_checkbox_popup(tela, 'Interessados', 'Operador de Processo 2')
    tela.preencher_formulario(
        [
            ('Data Limite da Ciência', 'data', '31/12/2099'),
            ('Justificativa da Solicitação', 'textarea', 'Solicitando ciência no e2e'),
            ('Tipo da Ciência', 'radio', 'Notificação'),
        ]
    ).clicar_botao('Enviar').sucesso('Solicitações de ciência adicionadas com sucesso.')

    solicitacao = SolicitacaoCiencia.objects.get(processo=processo, solicitado=_vinculo('128003'))
    assert solicitacao.esta_esperando()
    assert solicitacao.data_limite_ciencia.year == 2099


def test_dar_ciencia(logado_processo_eletronico: Any, solicitacao_ciencia_local: Any) -> None:
    """Registra a ciência do operador A2 e gera o termo correspondente."""
    tela = Tela(logado_processo_eletronico('operador_b')).ir(DAR_CIENCIA_URL.format(solicitacao_ciencia_local.processo.pk))
    tela.ver_titulo(f'Dar Ciência ao Processo {NUP1}').preencher('Perfil', 'lista', 'Cargo A')
    tela.preencher('Declaro-me ciente', 'checkbox', 'marcar')
    _senha(tela).clicar_botao('Assinar').sucesso('Ciência do processo')

    from processo_eletronico.models import SolicitacaoCiencia

    solicitacao_ciencia_local = SolicitacaoCiencia.objects.get(pk=solicitacao_ciencia_local.pk)
    assert solicitacao_ciencia_local.estah_ciente()
    assert solicitacao_ciencia_local.data_ciencia is not None


def test_encaminhar_com_despacho(logado_processo_eletronico: Any) -> None:
    """Encaminha processo com despacho assinado e destino A2."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(ENCAMINHAR_URL.format(processo.pk))
    tela.ver_titulo(f'Encaminhar Processo {NUP1}').preencher_formulario(
        [
            ('Despacho', 'textarea', 'Esse é um despacho de teste e2e.'),
            ('Buscar setor de destino por', 'radio', 'Autocompletar'),
            ('Setor de Destino', 'autocomplete', 'A2'),
            ('Perfil', 'lista', 'Cargo A'),
        ]
    )
    _senha(tela).clicar_botao('Salvar').sucesso('Processo encaminhado com sucesso.')

    processo = _processo(NUP1)
    assert processo.ultimo_tramite.destinatario_setor.sigla == 'A2'
    assert processo.ultimo_tramite.despacho_corpo == 'Esse é um despacho de teste e2e.'


def test_adicionar_interesse(logado_processo_eletronico: Any) -> None:
    """Adiciona o chefe B à lista de interesses do processo público."""
    processo = _processo(NUP2)
    tela = _detalhe(Tela(logado_processo_eletronico('chefe_b')), NUP2)
    tela.ir(ACOMPANHAR_URL.format(processo.pk)).sucesso('Processo adicionado na lista de interesses.')

    assert processo.acompanhantes_processo.filter(pk=_vinculo('128004').pk).exists()


def test_remover_interesse(logado_processo_eletronico: Any, interesse_chefe_b: Any) -> None:
    """Remove o chefe B da lista de interesses do processo."""
    tela = _detalhe(Tela(logado_processo_eletronico('chefe_b')), NUP2)
    tela.ir(DESACOMPANHAR_URL.format(interesse_chefe_b.pk)).sucesso('Processo removido da lista de interesses.')

    assert not interesse_chefe_b.acompanhantes_processo.filter(pk=_vinculo('128004').pk).exists()


def test_remover_ultimo_tramite(logado_processo_eletronico: Any) -> None:
    """Cria e desfaz o último trâmite do processo sem tramitação."""
    processo = _processo(NUP2)
    tela = Tela(logado_processo_eletronico('chefe_b')).ir(ENCAMINHAR_SEM_URL.format(processo.pk))
    tela.ver_titulo(f'Encaminhar Processo {NUP2}').preencher_formulario(
        [('Buscar setor de destino por', 'radio', 'Autocompletar'), ('Setor de Destino', 'autocomplete', 'A1')]
    ).clicar_botao('Salvar').sucesso('Processo encaminhado com sucesso.')
    tela.ir(REMOVER_ULTIMO_URL.format(processo.pk)).sucesso('Último trâmite removido com sucesso.')

    processo = _processo(NUP2)
    assert processo.ultimo_tramite_id is None
    assert not processo.tramites.exists()
