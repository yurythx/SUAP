from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import Client
from django.utils import timezone

from comum.models import Configuracao
from documento_eletronico.tests.factories import TipoDocumentoFactory
from processo_eletronico.models import ModeloDespacho, Processo, Requerimento
from processo_eletronico.tests.factories import ProcessoFactory, TipoProcessoFactory
from rh.models import Setor
from rh.tests.factories import PapelFactory

MENSAGEM_SEM_SETOR = 'Para finalizar é preciso que informe o Setor de Destino do Processo.'
MENSAGEM_JA_FINALIZADO = 'Este requerimento já foi finalizado.'


def test_modelo_despacho_ausente_informa_configuracao() -> None:
    with (
        patch.object(ModeloDespacho.objects, 'first', return_value=None),
        pytest.raises(ValidationError, match='Modelo de Despacho não está cadastrado no módulo de Processo Eletrônico'),
    ):
        ModeloDespacho.get_modelo()


def test_modelo_despacho_configurado() -> None:
    modelo = ModeloDespacho(cabecalho='Cabeçalho', rodape='Rodapé')
    with patch.object(ModeloDespacho.objects, 'first', return_value=modelo):
        assert ModeloDespacho.get_modelo() is modelo


@pytest.mark.parametrize('numero', [None, '', '0000439000000012026', '0000439.abc/2026-00', '0000439.00000001/2026-00extra'])
def test_protocolo_invalido_informa_inconsistencia(numero: str | None) -> None:
    processo = SimpleNamespace(setor_criacao=SimpleNamespace(get_codigo_siorg=lambda: '439'))
    with patch.object(Processo.objects, 'filter') as consulta:
        consulta.return_value.latest.return_value = SimpleNamespace(numero_protocolo=numero)
        with pytest.raises(ValidationError, match='inconsistência no cadastro'):
            Processo._proximo_numero_unico_protocolo.__wrapped__(processo)


def test_protocolo_valido_incrementa_sequencial() -> None:
    processo = SimpleNamespace(setor_criacao=SimpleNamespace(get_codigo_siorg=lambda: '439'))
    ano = datetime.today().year
    with patch.object(Processo.objects, 'filter') as consulta:
        consulta.return_value.latest.return_value = SimpleNamespace(numero_protocolo=f'0000439.00000001/{ano}-00')
        numero = Processo._proximo_numero_unico_protocolo.__wrapped__(processo)
    numero_base = f'000043900000002{ano}'
    digitos_verificadores = f'{98 - int(numero_base) % 97:02d}'
    assert numero == f'0000439.00000002/{ano}-{digitos_verificadores}'


def test_finalizar_requerimento_sem_setor_de_destino_acusa_erro_no_campo(client: Client, dois_servidores: SimpleNamespace) -> None:
    servidor = dois_servidores.a
    user = servidor.get_user()
    user.set_password('123')
    user.save()
    papel = PapelFactory(servidor=servidor)
    ModeloDespacho.objects.create(cabecalho='Cabeçalho', rodape='Rodapé')
    Configuracao.objects.create(app='documento_eletronico', chave='tipo_documento_requerimento', valor=TipoDocumentoFactory().pk)
    Configuracao.clear_cache()
    requerimento = Requerimento(tipo_processo=TipoProcessoFactory(), assunto='Requerimento sem destino')
    requerimento.save(request_user=user)
    processos_antes = Processo.objects.count()
    client.force_login(user)

    response = client.post(
        f'/processo_eletronico/finalizar_requerimento/{requerimento.pk}/',
        {'senha': '123', 'papel': papel.pk, 'tipo_busca_setor': 'autocompletar'},
    )

    assert response.status_code == 200
    assert response.context['form'].errors == {'destinatario_setor_autocompletar': [MENSAGEM_SEM_SETOR]}
    assert MENSAGEM_SEM_SETOR in response.content.decode()
    assert 'Entre em contato com o suporte' not in response.content.decode()
    requerimento.refresh_from_db()
    assert requerimento.situacao == Requerimento.SITUACAO_INICIADO
    assert requerimento.processo is None
    assert Processo.objects.count() == processos_antes


def test_requerimento_finalizado_sem_setor_de_destino_levanta_validation_error(dois_servidores: SimpleNamespace, setor_com_siorg: Setor) -> None:
    # Rede de segurança do model, caso a regra escape do form.
    user = dois_servidores.a.get_user()
    requerimento = Requerimento(tipo_processo=TipoProcessoFactory(), assunto='Requerimento sem destino')
    requerimento.save(request_user=user)
    requerimento.situacao = Requerimento.SITUACAO_FINALIZADO
    requerimento.processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=user)

    with pytest.raises(ValidationError, match=MENSAGEM_SEM_SETOR):
        requerimento.save(request_user=user)

    assert Requerimento.objects.get(pk=requerimento.pk).situacao == Requerimento.SITUACAO_INICIADO


def _preparar_finalizacao(servidor: object) -> SimpleNamespace:
    """Requerimento INICIADO do servidor, com o que o form de finalizar exige (senha, papel, modelo de despacho)."""
    user = servidor.get_user()
    user.set_password('123')
    user.save()
    papel = PapelFactory(servidor=servidor)
    ModeloDespacho.objects.create(cabecalho='Cabeçalho', rodape='Rodapé')
    Configuracao.objects.create(app='documento_eletronico', chave='tipo_documento_requerimento', valor=TipoDocumentoFactory().pk)
    Configuracao.clear_cache()
    requerimento = Requerimento(tipo_processo=TipoProcessoFactory(), assunto='Requerimento enviado duas vezes')
    requerimento.save(request_user=user)
    return SimpleNamespace(user=user, papel=papel, requerimento=requerimento)


def _finalizar_no_banco(requerimento: Requerimento, processo: Processo) -> None:
    """Estado deixado pelo primeiro envio: requerimento finalizado e ligado ao processo gerado."""
    Requerimento.objects.filter(pk=requerimento.pk).update(
        situacao=Requerimento.SITUACAO_FINALIZADO, processo=processo, data_hora_finalizado=timezone.now()
    )


def _assert_redireciona_ao_processo_ja_finalizado(response: HttpResponse, processo: Processo) -> None:
    assert response.status_code == 302
    assert response.url == f'/processo_eletronico/processo/{processo.pk}/'
    mensagens = [str(m) for m in get_messages(response.wsgi_request)]
    assert mensagens == [MENSAGEM_JA_FINALIZADO]


def test_reenviar_finalizacao_de_requerimento_ja_finalizado_redireciona_ao_processo(
    client: Client, dois_servidores: SimpleNamespace, setor_com_siorg: Setor
) -> None:
    dados = _preparar_finalizacao(dois_servidores.a)
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=dados.user)
    _finalizar_no_banco(dados.requerimento, processo)
    processos_antes = Processo.objects.count()
    client.force_login(dados.user)

    response = client.post(
        f'/processo_eletronico/finalizar_requerimento/{dados.requerimento.pk}/',
        {'senha': '123', 'papel': dados.papel.pk, 'tipo_busca_setor': 'autocompletar', 'destinatario_setor_autocompletar': setor_com_siorg.pk},
    )

    _assert_redireciona_ao_processo_ja_finalizado(response, processo)
    dados.requerimento.refresh_from_db()
    assert dados.requerimento.situacao == Requerimento.SITUACAO_FINALIZADO
    assert dados.requerimento.processo == processo
    assert Processo.objects.count() == processos_antes


def test_envio_concorrente_finalizado_por_outra_requisicao_redireciona_ao_processo(
    client: Client, dois_servidores: SimpleNamespace, setor_com_siorg: Setor
) -> None:
    # Duplo clique (SUAP-WQZ): o segundo POST lê o requerimento ainda INICIADO no topo da view, e o
    # primeiro POST finaliza e comita antes que o segundo chegue ao `save`.
    dados = _preparar_finalizacao(dois_servidores.a)
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=dados.user)
    processos_antes = Processo.objects.count()
    buscar_requerimento = Requerimento.get_requerimento_by_user

    def buscar_e_outra_requisicao_finaliza(request_user: object, requerimento_id: int) -> Requerimento | None:
        requerimento = buscar_requerimento(request_user=request_user, requerimento_id=requerimento_id)
        _finalizar_no_banco(dados.requerimento, processo)
        return requerimento

    client.force_login(dados.user)
    with patch.object(Requerimento, 'get_requerimento_by_user', side_effect=buscar_e_outra_requisicao_finaliza):
        response = client.post(
            f'/processo_eletronico/finalizar_requerimento/{dados.requerimento.pk}/',
            {'senha': '123', 'papel': dados.papel.pk, 'tipo_busca_setor': 'autocompletar', 'destinatario_setor_autocompletar': setor_com_siorg.pk},
        )

    _assert_redireciona_ao_processo_ja_finalizado(response, processo)
    dados.requerimento.refresh_from_db()
    assert dados.requerimento.situacao == Requerimento.SITUACAO_FINALIZADO
    assert dados.requerimento.processo == processo
    assert dados.requerimento.destinatario_setor is None
    assert Processo.objects.count() == processos_antes
