"""Exclusão do processo de alteração de carga horária e alteração dos horários semanais dele (#17648).

As rotas não conferiam quem pedia: qualquer usuário logado excluía o processo de outro (com os arquivos
do storage) e qualquer servidor adicionava, editava ou removia horário de processo alheio. Agora seguem
a regra dos botões e ícones na tela:

- excluir: o ícone da listagem só aparece ao próprio servidor, com o processo "Aguardando envio para o
  chefe" (``CargaHorariaReduzida.pode_ser_excluido_por``);
- adicionar, editar e remover horário: a tela do processo só abre para os coordenadores de Gestão de
  Pessoas; o RH sistêmico altera e o RH do campus, só enquanto o RH pode validar (adicionar) ou editar o
  horário (``CargaHorariaReduzida.pode_alterar_horario``).

O RH do campus abria e alterava pela URL o processo de servidor de outro campus (#17690): a listagem do admin
filtrava pelo campus, as views não. Agora a tela do processo, o deferimento da carga horária excepcional, o
deferir/indeferir e os horários seguem o critério da listagem (``CargaHorariaReduzida.filtro_escopo_rh``).

Os documentos do processo (#17695): o upload não exigia login nem conferia quem anexava, e o PDF abria para
qualquer logado com o link. Agora anexa quem vê o uploader na tela (o RH no escopo, só no afastamento
parcial), só PDF, e o documento abre para o dono e o RH no escopo. A tela deixou de dispensar o token CSRF.

O deferimento (#17696) tinha dois caminhos divergentes: o "Deferir" da carga horária excepcional não conferia o
tipo nem se o processo já estava deferido, nem gravava o validador ou notificava o servidor, e o "Atualizar
Situação" pela URL re-deferia ou revertia um processo deferido. Agora os dois passam por
``CargaHorariaReduzida.deferir_pelo_rh`` e seguem a regra dos botões da tela.

A exclusão de documento (#17705) dispensava o token CSRF, aceitava GET, dava 500 com chave inválida e só deixava o
dono excluir, em qualquer status, enquanto o ícone só aparecia ao RH. Agora só o RH no escopo exclui, por POST
com o token.

A carga horária excepcional (#17713) só era indeferida pela URL do "Atualizar Situação", que a tela esconde nela, e a
mesma URL a deferia. Agora ela tem o botão "Indeferir" ao lado do "Deferir", e a URL vale só para o afastamento
parcial; os dois indeferimentos passam por ``CargaHorariaReduzida.indeferir_pelo_rh``.

O indeferimento da carga horária excepcional é final (#17729): o "Deferir" também some, e o POST dá 403, no processo
já indeferido pelo RH.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponse
from django.test import Client

from comum.models import RegistroNotificacao, User
from rh.models import CargaHorariaReduzida, DocumentacaoExigida, HorarioSemanal
from rh.tests.factories import (
    CargaHorariaReduzidaFactory,
    DocumentacaoExigidaFactory,
    HorarioSemanalFactory,
    JornadaTrabalhoFactory,
    ServidorFactory,
    SetorFactory,
)
from rh.models import Setor

EXCLUIR = '/rh/excluir_processo_afastamento_parcial/{}/'
REMOVER_HORARIO = '/rh/remover_horario_afastamento/{}/'
ADICIONAR_HORARIO = '/rh/adicionar_horario_afastamento_parcial/{}/'
EDITAR_HORARIO = '/rh/editar_horario_afastamento/{}/'
ABRIR = '/rh/abrir_processo_afastamento_parcial/{}/'
ALTERAR_SITUACAO = '/rh/alterar_situacao_afastamento_parcial_rh/{}/{}/'
EDITAR_NO_ADMIN = '/admin/rh/cargahorariareduzida/{}/change/'
RH_SISTEMICO = 'Coordenador de Gestão de Pessoas Sistêmico'
RH_CAMPUS = 'Coordenador de Gestão de Pessoas'


def _usuario(*grupos: str, setor: Setor | None = None) -> User:
    """Servidor com os ``grupos``, lotado em ``setor`` (sem ele, num campus só seu)."""
    usuario = ServidorFactory(setor=setor or SetorFactory()).get_user()
    usuario.groups.add(*[Group.objects.get(name=grupo) for grupo in grupos])
    return usuario


def _campus_do(processo: CargaHorariaReduzida) -> Setor:
    return processo.servidor.setor


@pytest.fixture(autouse=True)
def _limpa_cache_de_perfil() -> Iterator[None]:
    """Zera ``User.PESSOAS_FISICAS``/``User.VINCULOS``: caches de classe por ``user.id``, e o banco de teste recicla ids.

    Sem isso o ``get_vinculo()`` do dono pode devolver o vínculo de um usuário de outro teste.
    """
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()
    yield
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()


@pytest.fixture
def storage_temporario(settings, tmp_path: Path) -> None:
    settings.STORAGES = {
        **settings.STORAGES,
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': str(tmp_path)}},
    }


@pytest.fixture
def processo_editavel(storage_temporario: None) -> CargaHorariaReduzida:
    """Processo "Aguardando envio para o chefe" com um documento gravado no storage."""
    processo = CargaHorariaReduzidaFactory(servidor=ServidorFactory(setor=SetorFactory()), status=CargaHorariaReduzida.STATUS_AGUARDANDO_ENVIO_CHEFE)
    documento = DocumentacaoExigidaFactory(processo=processo)
    default_storage.save(documento.diretorio, ContentFile(b'%PDF'))
    return processo


@pytest.mark.parametrize('grupos', [(), (RH_SISTEMICO,), (RH_CAMPUS,)], ids=['servidor', 'rh_sistemico', 'rh_campus'])
def test_so_o_dono_exclui_o_processo(client: Client, processo_editavel: CargaHorariaReduzida, grupos: tuple[str, ...]) -> None:
    diretorio = processo_editavel.documentos.get().diretorio
    client.force_login(_usuario(*grupos))

    assert client.get(EXCLUIR.format(processo_editavel.pk)).status_code == 403
    assert CargaHorariaReduzida.objects.filter(pk=processo_editavel.pk).exists()
    assert default_storage.exists(diretorio), 'a exclusão negada apagou o arquivo do storage'


def test_dono_exclui_o_processo_ainda_nao_enviado(
    client: Client, processo_editavel: CargaHorariaReduzida, django_capture_on_commit_callbacks
) -> None:
    diretorio = processo_editavel.documentos.get().diretorio
    client.force_login(processo_editavel.servidor.get_user())

    with django_capture_on_commit_callbacks(execute=True):
        assert client.get(EXCLUIR.format(processo_editavel.pk)).status_code == 302
    assert not CargaHorariaReduzida.objects.filter(pk=processo_editavel.pk).exists()
    assert not default_storage.exists(diretorio)


def test_admin_exclui_o_processo_e_apaga_os_arquivos(client: Client, storage_temporario: None, django_capture_on_commit_callbacks) -> None:
    """#17691: o cascade do admin só apagava as linhas e deixava os arquivos órfãos no storage."""
    processo = CargaHorariaReduzidaFactory(servidor=ServidorFactory(setor=SetorFactory()), status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH)
    diretorio = DocumentacaoExigidaFactory(processo=processo).diretorio
    default_storage.save(diretorio, ContentFile(b'%PDF'))
    admin = _usuario()
    admin.is_superuser = admin.is_staff = True
    admin.set_password('senha17691')
    admin.save()
    client.force_login(admin)

    with django_capture_on_commit_callbacks(execute=True):
        resposta = client.post(f'/admin/rh/cargahorariareduzida/{processo.pk}/delete/', {'post': 'yes', 'senha': 'senha17691'})
    assert resposta.status_code == 302
    assert not CargaHorariaReduzida.objects.filter(pk=processo.pk).exists()
    assert not default_storage.exists(diretorio)


def test_exclusao_do_documento_nao_quebra_sem_arquivo(processo_editavel: CargaHorariaReduzida, django_capture_on_commit_callbacks) -> None:
    """Arquivo já inexistente e ``diretorio`` vazio não impedem a exclusão da linha."""
    sem_arquivo = DocumentacaoExigidaFactory(processo=processo_editavel)
    sem_diretorio = DocumentacaoExigidaFactory(processo=processo_editavel, diretorio='')

    with django_capture_on_commit_callbacks(execute=True):
        processo_editavel.delete()
    assert not DocumentacaoExigida.objects.filter(pk__in=[sem_arquivo.pk, sem_diretorio.pk]).exists()


def test_falha_do_storage_nao_impede_a_exclusao(
    processo_editavel: CargaHorariaReduzida, django_capture_on_commit_callbacks, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _falha(self, name: str) -> None:
        raise OSError('storage fora do ar')

    monkeypatch.setattr('django.core.files.storage.FileSystemStorage.delete', _falha)

    with django_capture_on_commit_callbacks(execute=True):
        processo_editavel.delete()
    assert not CargaHorariaReduzida.objects.filter(pk=processo_editavel.pk).exists()


def test_rollback_da_exclusao_preserva_o_arquivo(processo_editavel: CargaHorariaReduzida, django_capture_on_commit_callbacks) -> None:
    pk, diretorio = processo_editavel.pk, processo_editavel.documentos.get().diretorio

    def _exclui_e_desfaz() -> None:
        with transaction.atomic():
            processo_editavel.delete()
            raise RuntimeError

    with django_capture_on_commit_callbacks(execute=True), pytest.raises(RuntimeError):
        _exclui_e_desfaz()
    assert CargaHorariaReduzida.objects.filter(pk=pk).exists()
    assert default_storage.exists(diretorio)


def test_dono_nao_exclui_o_processo_ja_enviado(client: Client) -> None:
    processo = CargaHorariaReduzidaFactory(servidor=ServidorFactory(setor=SetorFactory()), status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH)
    client.force_login(processo.servidor.get_user())

    assert client.get(EXCLUIR.format(processo.pk)).status_code == 403
    assert CargaHorariaReduzida.objects.filter(pk=processo.pk).exists()


@pytest.mark.parametrize('do_dono', [False, True], ids=['alheio', 'proprio'])
def test_servidor_fora_do_rh_nao_remove_horario(client: Client, do_dono: bool) -> None:
    """A tela do processo nem abre para quem não é do RH, dono ou não."""
    horario = HorarioSemanalFactory(processo_reducao_ch__servidor=ServidorFactory(setor=SetorFactory()))
    client.force_login(horario.processo_reducao_ch.servidor.get_user() if do_dono else _usuario())

    assert client.get(REMOVER_HORARIO.format(horario.pk)).status_code == 403
    assert HorarioSemanal.objects.filter(pk=horario.pk).exists()


@pytest.mark.parametrize('grupo', [RH_SISTEMICO, RH_CAMPUS])
def test_rh_remove_horario_do_processo_em_validacao(client: Client, grupo: str) -> None:
    horario = HorarioSemanalFactory(
        processo_reducao_ch__tipo=CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL,
        processo_reducao_ch__status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH,
    )
    client.force_login(_usuario(grupo, setor=_campus_do(horario.processo_reducao_ch)))

    assert client.get(REMOVER_HORARIO.format(horario.pk)).status_code == 302
    assert not HorarioSemanal.objects.filter(pk=horario.pk).exists()
    assert CargaHorariaReduzida.objects.filter(pk=horario.processo_reducao_ch_id, status=CargaHorariaReduzida.STATUS_ALTERANDO_HORARIO).exists()


@pytest.mark.parametrize(('grupo', 'status_esperado'), [(RH_SISTEMICO, 302), (RH_CAMPUS, 403)])
def test_horario_de_processo_deferido_so_o_rh_sistemico_remove(client: Client, grupo: str, status_esperado: int) -> None:
    """No afastamento parcial deferido o RH do campus não mexe mais no horário."""
    horario = HorarioSemanalFactory(
        processo_reducao_ch__tipo=CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL,
        processo_reducao_ch__status=CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH,
    )
    client.force_login(_usuario(grupo, setor=_campus_do(horario.processo_reducao_ch)))

    assert client.get(REMOVER_HORARIO.format(horario.pk)).status_code == status_esperado
    assert HorarioSemanal.objects.filter(pk=horario.pk).exists() is (status_esperado == 403)


def _horario_em_validacao_pelo_rh() -> HorarioSemanal:
    """Horário de afastamento parcial aguardando o RH, de servidor com jornada que o formulário reconhece."""
    servidor = ServidorFactory(setor=SetorFactory(), jornada_trabalho=JornadaTrabalhoFactory(codigo='T17648', nome='40 HORAS SEMANAIS'))
    return HorarioSemanalFactory(
        processo_reducao_ch__servidor=servidor,
        processo_reducao_ch__tipo=CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL,
        processo_reducao_ch__status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH,
    )


def _horario_postado(horario: HorarioSemanal, seg: str) -> dict[str, str]:
    """30h semanais: ``seg`` mais o que falta para 30h nos outros quatro dias."""
    resto = f'{(30 - float(seg)) / 4:.1f}'
    return {
        'data_inicial_horario': horario.data_inicio.isoformat(),
        'data_fim_horario': horario.data_fim.isoformat(),
        'nova_jornada': '30.0',
        'seg': seg,
        **dict.fromkeys(('ter', 'qua', 'qui', 'sex'), resto),
    }


@pytest.mark.parametrize('acao', ['adicionar', 'editar'])
def test_servidor_fora_do_rh_nao_adiciona_nem_edita_horario_alheio(client: Client, acao: str) -> None:
    horario = HorarioSemanalFactory(processo_reducao_ch__servidor=ServidorFactory(setor=SetorFactory()))
    processo = horario.processo_reducao_ch
    client.force_login(_usuario())
    url = ADICIONAR_HORARIO.format(processo.pk) if acao == 'adicionar' else EDITAR_HORARIO.format(horario.pk)

    assert client.post(url, _horario_postado(horario, '10.0')).status_code == 403
    assert list(HorarioSemanal.objects.filter(processo_reducao_ch=processo).values_list('pk', flat=True)) == [horario.pk]
    horario.refresh_from_db()
    assert float(horario.seg) == 6


@pytest.mark.parametrize('grupo', [RH_SISTEMICO, RH_CAMPUS])
def test_rh_adiciona_e_edita_horario_do_processo_em_validacao(client: Client, grupo: str) -> None:
    horario = _horario_em_validacao_pelo_rh()
    processo = horario.processo_reducao_ch
    client.force_login(_usuario(grupo, setor=_campus_do(processo)))

    assert client.post(ADICIONAR_HORARIO.format(processo.pk), _horario_postado(horario, '10.0')).status_code == 302
    assert HorarioSemanal.objects.filter(processo_reducao_ch=processo, seg=10).exists()
    assert client.post(EDITAR_HORARIO.format(horario.pk), _horario_postado(horario, '8.0')).status_code == 302
    horario.refresh_from_db()
    assert float(horario.seg) == 8


def test_rh_do_campus_nao_edita_horario_de_afastamento_deferido(client: Client) -> None:
    horario = HorarioSemanalFactory(
        processo_reducao_ch__tipo=CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL,
        processo_reducao_ch__status=CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH,
    )
    client.force_login(_usuario(RH_CAMPUS, setor=_campus_do(horario.processo_reducao_ch)))

    assert client.post(EDITAR_HORARIO.format(horario.pk), _horario_postado(horario, '10.0')).status_code == 403
    horario.refresh_from_db()
    assert float(horario.seg) == 6


# --- Escopo de campus do RH (#17690) ---------------------------------------------------------------------------------

RH_CAMPUS_OUTRO, RH_CAMPUS_MESMO, RH_SISTEMICO_OUTRO = 'rh_campus_outro_campus', 'rh_campus_mesmo_campus', 'rh_sistemico_outro_campus'
ATORES_PERMITIDOS = [RH_CAMPUS_MESMO, RH_SISTEMICO_OUTRO]


def _ator(ator: str, processo: CargaHorariaReduzida) -> User:
    """RH do campus no campus do processo ou em outro, ou RH sistêmico de outro campus."""
    if ator == RH_CAMPUS_MESMO:
        return _usuario(RH_CAMPUS, setor=_campus_do(processo))
    return _usuario(RH_CAMPUS if ator == RH_CAMPUS_OUTRO else RH_SISTEMICO)


def _status(processo: CargaHorariaReduzida) -> int:
    return CargaHorariaReduzida.objects.values_list('status', flat=True).get(pk=processo.pk)


@pytest.mark.parametrize('ator', [RH_CAMPUS_OUTRO, *ATORES_PERMITIDOS])
def test_tela_do_processo_so_abre_no_escopo_do_rh(client: Client, ator: str) -> None:
    processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    client.force_login(_ator(ator, processo))

    assert client.get(ABRIR.format(processo.pk)).status_code == (403 if ator == RH_CAMPUS_OUTRO else 200)


@pytest.mark.parametrize('ator', [RH_CAMPUS_OUTRO, *ATORES_PERMITIDOS])
def test_deferir_carga_horaria_excepcional_so_no_escopo_do_rh(client: Client, ator: str) -> None:
    """O "Deferir" da carga horária excepcional é o POST ``salvar_ch_excepcional`` da tela do processo."""
    processo = HorarioSemanalFactory(
        processo_reducao_ch__servidor=ServidorFactory(setor=SetorFactory()),
        processo_reducao_ch__tipo=CargaHorariaReduzida.TIPO_CH_EXCEPCIONAL,
        processo_reducao_ch__status=CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO,
    ).processo_reducao_ch
    client.force_login(_ator(ator, processo))

    resposta = client.post(ABRIR.format(processo.pk), {'acao': 'salvar_ch_excepcional'})

    if ator == RH_CAMPUS_OUTRO:
        assert resposta.status_code == 403
        assert _status(processo) == CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO
    else:
        assert resposta.status_code == 302
        assert _status(processo) == CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH


@pytest.mark.parametrize('ator', [RH_CAMPUS_OUTRO, *ATORES_PERMITIDOS])
def test_deferir_afastamento_parcial_so_no_escopo_do_rh(client: Client, ator: str) -> None:
    processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    client.force_login(_ator(ator, processo))

    resposta = client.get(ALTERAR_SITUACAO.format(processo.pk, CargaHorariaReduzida.STATUS_AMIGAVEL_DEFERIDO))

    if ator == RH_CAMPUS_OUTRO:
        assert resposta.status_code == 403
        assert _status(processo) == CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH
    else:
        assert resposta.status_code == 302
        assert _status(processo) == CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH


@pytest.mark.parametrize('situacao', [CargaHorariaReduzida.STATUS_AMIGAVEL_DEFERIDO, CargaHorariaReduzida.STATUS_AMIGAVEL_INDEFERIDO])
@pytest.mark.parametrize('ator', ['servidor_do_mesmo_campus', RH_CAMPUS_OUTRO])
def test_fora_do_escopo_do_rh_nao_defere_nem_indefere(client: Client, ator: str, situacao: str) -> None:
    """O botão "Atualizar Situação" só aparece ao RH; a permissão ``change_cargahorariareduzida`` todo servidor tem."""
    processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    usuario = _ator(ator, processo) if ator == RH_CAMPUS_OUTRO else _usuario(setor=_campus_do(processo))
    client.force_login(usuario)

    resposta = client.post(ALTERAR_SITUACAO.format(processo.pk, situacao), {'motivo_indeferimento_rh': 'fora do escopo'})

    assert resposta.status_code == 403
    assert _status(processo) == CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH


@pytest.mark.parametrize('ator', [RH_CAMPUS_OUTRO, *ATORES_PERMITIDOS])
def test_horario_so_muda_no_escopo_do_rh(client: Client, ator: str) -> None:
    horario = _horario_em_validacao_pelo_rh()
    processo = horario.processo_reducao_ch
    client.force_login(_ator(ator, processo))

    respostas = [
        client.post(ADICIONAR_HORARIO.format(processo.pk), _horario_postado(horario, '10.0')).status_code,
        client.post(EDITAR_HORARIO.format(horario.pk), _horario_postado(horario, '8.0')).status_code,
    ]

    horario.refresh_from_db()
    if ator == RH_CAMPUS_OUTRO:
        assert respostas == [403, 403]
        assert list(HorarioSemanal.objects.filter(processo_reducao_ch=processo).values_list('pk', flat=True)) == [horario.pk]
        assert float(horario.seg) == 6
        assert client.get(REMOVER_HORARIO.format(horario.pk)).status_code == 403
        assert HorarioSemanal.objects.filter(pk=horario.pk).exists()
    else:
        assert respostas == [302, 302]
        assert HorarioSemanal.objects.filter(processo_reducao_ch=processo, seg=10).exists()
        assert float(horario.seg) == 8
        assert client.get(REMOVER_HORARIO.format(horario.pk)).status_code == 302
        assert not HorarioSemanal.objects.filter(pk=horario.pk).exists()


@pytest.mark.parametrize('ator', [RH_CAMPUS_OUTRO, *ATORES_PERMITIDOS])
def test_edicao_no_admin_segue_a_listagem(client: Client, ator: str) -> None:
    """O botão "Editar" da tela leva ao admin, que já busca o processo pela listagem filtrada."""
    processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    client.force_login(_ator(ator, processo))

    resposta = client.get(EDITAR_NO_ADMIN.format(processo.pk))

    if ator == RH_CAMPUS_OUTRO:
        assert (resposta.status_code, resposta.url) == (302, '/admin/'), 'o admin devia tratar o processo fora da listagem como inexistente'
    else:
        assert resposta.status_code == 200


# --- Documentos do processo (#17695) ---------------------------------------------------------------------------------

UPLOAD = '/rh/afastamento_pacial_upload/?processo={}&qqfile={}'
VISUALIZAR = '/rh/visualizar_documentacao_pdf/{}/'
PDF = b'%PDF-1.4\n%documento de teste\n'
DONO, SERVIDOR_DO_CAMPUS = 'dono', 'servidor_do_mesmo_campus'


@pytest.fixture
def midia(storage_temporario: None, settings, tmp_path: Path) -> Path:
    """O ``LocalUploadBackend`` do uploader grava sob ``MEDIA_ROOT``, não pelo ``default_storage``."""
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def _afastamento_em_validacao(tipo: int = CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL) -> CargaHorariaReduzida:
    return CargaHorariaReduzidaFactory(
        servidor=ServidorFactory(setor=SetorFactory()), tipo=tipo, status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH
    )


def _quem(ator: str, processo: CargaHorariaReduzida) -> User:
    """Além dos atores de RH (``_ator``), o dono do processo e um servidor fora do RH no campus dele."""
    if ator == DONO:
        return processo.servidor.get_user()
    if ator == SERVIDOR_DO_CAMPUS:
        return _usuario(setor=_campus_do(processo))
    return _ator(ator, processo)


def _anexar(client: Client, processo: CargaHorariaReduzida, nome: str = 'documento.pdf', conteudo: bytes = PDF) -> HttpResponse:
    """Como o uploader da tela: arquivo cru no corpo do POST ajax e o nome na querystring."""
    return client.post(
        UPLOAD.format(processo.pk, nome), data=conteudo, content_type='application/octet-stream', HTTP_X_REQUESTED_WITH='XMLHttpRequest'
    )


def _gravados(midia: Path) -> list[Path]:
    return [arquivo for arquivo in midia.rglob('*') if arquivo.is_file()]


def test_anonimo_nao_anexa_documento(client: Client, midia: Path) -> None:
    processo = _afastamento_em_validacao()

    assert _anexar(client, processo).status_code == 302
    assert not processo.documentos.exists()
    assert _gravados(midia) == []


@pytest.mark.parametrize('ator', [DONO, SERVIDOR_DO_CAMPUS, RH_CAMPUS_OUTRO])
def test_fora_do_escopo_do_rh_nao_anexa_documento(client: Client, midia: Path, ator: str) -> None:
    """O uploader só aparece na tela do processo, que só abre para o RH no escopo: nem o dono anexa."""
    processo = _afastamento_em_validacao()
    client.force_login(_quem(ator, processo))

    assert _anexar(client, processo).status_code == 403
    assert not processo.documentos.exists()
    assert _gravados(midia) == []


def test_carga_horaria_excepcional_nao_recebe_documento(client: Client, midia: Path) -> None:
    """A tela só mostra o uploader no afastamento parcial."""
    processo = _afastamento_em_validacao(tipo=CargaHorariaReduzida.TIPO_CH_EXCEPCIONAL)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    assert _anexar(client, processo).status_code == 403
    assert _gravados(midia) == []


@pytest.mark.parametrize('ator', ATORES_PERMITIDOS)
def test_rh_no_escopo_anexa_pdf(client: Client, midia: Path, ator: str) -> None:
    processo = _afastamento_em_validacao()
    client.force_login(_ator(ator, processo))

    resposta = _anexar(client, processo)

    assert resposta.status_code == 200
    assert json.loads(resposta.content)['success'] is True
    assert (midia / processo.documentos.get().diretorio).read_bytes() == PDF


@pytest.mark.parametrize(('nome', 'conteudo'), [('documento.exe', PDF), ('documento.pdf', b'MZ\x90\x00 executavel')], ids=['extensao', 'conteudo'])
def test_upload_recusa_o_que_nao_e_pdf(client: Client, midia: Path, nome: str, conteudo: bytes) -> None:
    """A tela só aceita ``.pdf`` no navegador; o servidor confere a extensão e o cabeçalho ``%PDF-``."""
    processo = _afastamento_em_validacao()
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    assert json.loads(_anexar(client, processo, nome, conteudo).content)['success'] is False
    assert not processo.documentos.exists()
    assert _gravados(midia) == []


def test_deferir_carga_horaria_excepcional_exige_token_csrf() -> None:
    """O POST ``salvar_ch_excepcional`` defere o processo: sem o token, outro site faria o RH logado deferir."""
    processo = HorarioSemanalFactory(
        processo_reducao_ch__servidor=ServidorFactory(setor=SetorFactory()),
        processo_reducao_ch__tipo=CargaHorariaReduzida.TIPO_CH_EXCEPCIONAL,
        processo_reducao_ch__status=CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO,
    ).processo_reducao_ch
    client = Client(enforce_csrf_checks=True)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    assert client.post(ABRIR.format(processo.pk), {'acao': 'salvar_ch_excepcional'}).status_code == 403
    assert _status(processo) == CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO


@pytest.mark.parametrize(
    ('ator', 'status_esperado'),
    [(SERVIDOR_DO_CAMPUS, 403), (RH_CAMPUS_OUTRO, 403), (DONO, 200), (RH_CAMPUS_MESMO, 200), (RH_SISTEMICO_OUTRO, 200)],
)
def test_so_o_dono_e_o_rh_no_escopo_visualizam_documento(client: Client, storage_temporario: None, ator: str, status_esperado: int) -> None:
    documento = DocumentacaoExigidaFactory(processo=_afastamento_em_validacao())
    client.force_login(_quem(ator, documento.processo))

    assert client.get(VISUALIZAR.format(documento.encrypted_pk)).status_code == status_esperado


def test_visualizar_documento_com_chave_invalida_da_404(client: Client) -> None:
    client.force_login(_usuario(RH_SISTEMICO))

    assert client.get(VISUALIZAR.format('chave-invalida')).status_code == 404


# --- Deferimento (#17696) --------------------------------------------------------------------------------------------


def _ch_excepcional(status: int = CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO) -> CargaHorariaReduzida:
    """Carga horária excepcional com um horário que cobre o período, como a tela exige para deferir."""
    return HorarioSemanalFactory(
        processo_reducao_ch__servidor=ServidorFactory(setor=SetorFactory()),
        processo_reducao_ch__tipo=CargaHorariaReduzida.TIPO_CH_EXCEPCIONAL,
        processo_reducao_ch__status=status,
    ).processo_reducao_ch


def _deferido_por_outro(processo: CargaHorariaReduzida) -> int:
    """Marca o ``processo`` como deferido por outro servidor do RH e devolve o id desse validador."""
    validador = ServidorFactory(setor=SetorFactory())
    CargaHorariaReduzida.objects.filter(pk=processo.pk).update(status=CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH, servidor_rh_validador=validador)
    return validador.pk


def _deferimentos_notificados(processo: CargaHorariaReduzida) -> int:
    return RegistroNotificacao.objects.filter(vinculo=processo.servidor.get_vinculo(), notificacao__mensagem__contains='deferido pelo RH').count()


def _situacao(processo: CargaHorariaReduzida) -> tuple[int, int | None]:
    return CargaHorariaReduzida.objects.values_list('status', 'servidor_rh_validador').get(pk=processo.pk)


@pytest.mark.parametrize('caminho', ['deferir_ch_excepcional', 'atualizar_situacao'])
def test_deferimento_registra_o_validador_e_notifica_o_servidor(client: Client, caminho: str) -> None:
    """O "Deferir" da carga horária excepcional não gravava o validador nem notificava, como o "Atualizar Situação"."""
    if caminho == 'deferir_ch_excepcional':
        processo = _ch_excepcional()
    else:
        processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    rh = _ator(RH_SISTEMICO_OUTRO, processo)
    client.force_login(rh)

    if caminho == 'deferir_ch_excepcional':
        resposta = client.post(ABRIR.format(processo.pk), {'acao': 'salvar_ch_excepcional'})
    else:
        resposta = client.get(ALTERAR_SITUACAO.format(processo.pk, CargaHorariaReduzida.STATUS_AMIGAVEL_DEFERIDO))

    assert resposta.status_code == 302
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH, rh.get_relacionamento().pk)
    assert _deferimentos_notificados(processo) == 1


def test_deferir_ch_excepcional_nao_defere_afastamento_parcial(client: Client) -> None:
    """O botão "Deferir" só aparece na carga horária excepcional; o afastamento parcial é deferido pelo "Atualizar Situação"."""
    processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    assert client.post(ABRIR.format(processo.pk), {'acao': 'salvar_ch_excepcional'}).status_code == 403
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH, None)
    assert _deferimentos_notificados(processo) == 0


def test_carga_horaria_excepcional_deferida_nao_e_deferida_de_novo(client: Client) -> None:
    processo = _ch_excepcional()
    validador = _deferido_por_outro(processo)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    assert client.post(ABRIR.format(processo.pk), {'acao': 'salvar_ch_excepcional'}).status_code == 403
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH, validador)
    assert _deferimentos_notificados(processo) == 0


@pytest.mark.parametrize('situacao', [CargaHorariaReduzida.STATUS_AMIGAVEL_DEFERIDO, CargaHorariaReduzida.STATUS_AMIGAVEL_INDEFERIDO])
def test_situacao_de_processo_deferido_nao_muda_pela_url(client: Client, situacao: str) -> None:
    """O "Atualizar Situação" some no processo deferido; pela URL, o deferir trocava o validador e renotificava e o
    indeferir revertia o deferimento."""
    processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    validador = _deferido_por_outro(processo)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    resposta = client.post(ALTERAR_SITUACAO.format(processo.pk, situacao), {'motivo_indeferimento_rh': 'reverte o deferido'})

    assert resposta.status_code == 403
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH, validador)
    assert _deferimentos_notificados(processo) == 0


# --- Exclusão de documento (#17705) ----------------------------------------------------------------------------------

EXCLUIR_DOCUMENTO = '/rh/excluir_documentacao_pdf/{}/'


@pytest.fixture
def documento(storage_temporario: None) -> DocumentacaoExigida:
    """Documento de afastamento parcial aguardando o RH, gravado no storage."""
    documento = DocumentacaoExigidaFactory(processo=_afastamento_em_validacao())
    default_storage.save(documento.diretorio, ContentFile(PDF))
    return documento


def _excluir(client: Client, documento: DocumentacaoExigida) -> HttpResponse:
    """Como o ícone da tela: POST ajax (o ``Client`` padrão dispensa o token CSRF, conferido à parte)."""
    return client.post(EXCLUIR_DOCUMENTO.format(documento.encrypted_pk), data='{}', content_type='application/json')


def _intacto(documento: DocumentacaoExigida) -> bool:
    return DocumentacaoExigida.objects.filter(pk=documento.pk).exists() and default_storage.exists(documento.diretorio)


@pytest.mark.parametrize('ator', ATORES_PERMITIDOS)
def test_rh_no_escopo_ve_e_exclui_documento(documento: DocumentacaoExigida, ator: str, django_capture_on_commit_callbacks) -> None:
    """O ícone de excluir aparecia só ao dono, que nem abre a tela; o RH que a abre recebia "sem permissão".

    Como o JS da tela: o token do form vai no cabeçalho ``X-CSRFToken`` (o cookie é HttpOnly).
    """
    client = Client(enforce_csrf_checks=True)
    client.force_login(_ator(ator, documento.processo))
    tela = client.get(ABRIR.format(documento.processo_id)).content.decode()
    assert EXCLUIR_DOCUMENTO.format(documento.encrypted_pk) in tela
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', tela).group(1)

    with django_capture_on_commit_callbacks(execute=True):
        resposta = client.post(EXCLUIR_DOCUMENTO.format(documento.encrypted_pk), data='{}', content_type='application/json', HTTP_X_CSRFTOKEN=token)

    assert json.loads(resposta.content)['ok'] is True
    assert not DocumentacaoExigida.objects.filter(pk=documento.pk).exists()
    assert not default_storage.exists(documento.diretorio)


@pytest.mark.parametrize('ator', [DONO, SERVIDOR_DO_CAMPUS, RH_CAMPUS_OUTRO])
def test_fora_do_escopo_do_rh_nao_exclui_documento(client: Client, documento: DocumentacaoExigida, ator: str) -> None:
    """Só o RH no escopo exclui (decisão na #17705). O dono excluía em qualquer status: ``servidor_pode_editar`` sem parênteses."""
    client.force_login(_quem(ator, documento.processo))

    assert json.loads(_excluir(client, documento).content)['ok'] is False
    assert _intacto(documento)


def test_excluir_documento_com_chave_invalida_da_404(client: Client) -> None:
    client.force_login(_usuario(RH_SISTEMICO))

    assert client.post(EXCLUIR_DOCUMENTO.format('chave-invalida')).status_code == 404


def test_excluir_documento_exige_post_com_token_csrf(documento: DocumentacaoExigida) -> None:
    """Sem o token, outro site faria o RH logado excluir: por POST forjado ou por um GET (``<img src>``), que o Django
    não confere."""
    client = Client(enforce_csrf_checks=True)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, documento.processo))

    assert client.post(EXCLUIR_DOCUMENTO.format(documento.encrypted_pk)).status_code == 403
    assert client.get(EXCLUIR_DOCUMENTO.format(documento.encrypted_pk)).status_code == 405
    assert _intacto(documento)


# --- Indeferimento da carga horária excepcional (#17713) -------------------------------------------------------------


def _indeferir_ch_excepcional(client: Client, processo: CargaHorariaReduzida, motivo: str = 'Jornada incompatível.') -> HttpResponse:
    """O botão "Indeferir" da carga horária excepcional: POST ``indeferir_ch_excepcional`` da tela, com o motivo."""
    return client.post(ABRIR.format(processo.pk), {'acao': 'indeferir_ch_excepcional', 'motivo_indeferimento_rh': motivo})


def _indeferimentos_notificados(processo: CargaHorariaReduzida) -> int:
    return RegistroNotificacao.objects.filter(vinculo=processo.servidor.get_vinculo(), notificacao__mensagem__contains='indeferido pelo RH').count()


def _motivo(processo: CargaHorariaReduzida) -> str | None:
    return CargaHorariaReduzida.objects.values_list('motivo_indeferimento_rh', flat=True).get(pk=processo.pk)


@pytest.mark.parametrize('ator', [RH_CAMPUS_OUTRO, *ATORES_PERMITIDOS])
def test_indeferir_carga_horaria_excepcional_pelo_botao_so_no_escopo_do_rh(client: Client, ator: str) -> None:
    """A carga horária excepcional só era indeferida pela URL do "Atualizar Situação", que a tela não oferece."""
    processo = _ch_excepcional()
    rh = _ator(ator, processo)
    client.force_login(rh)

    resposta = _indeferir_ch_excepcional(client, processo)

    if ator == RH_CAMPUS_OUTRO:
        assert resposta.status_code == 403
        assert _situacao(processo) == (CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO, None)
        assert _indeferimentos_notificados(processo) == 0
    else:
        assert resposta.status_code == 302
        assert _situacao(processo) == (CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH, rh.get_relacionamento().pk)
        assert _motivo(processo) == 'Jornada incompatível.'
        assert _indeferimentos_notificados(processo) == 1


def test_tela_da_carga_horaria_excepcional_oferece_indeferir(client: Client) -> None:
    processo = _ch_excepcional()
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    html = client.get(ABRIR.format(processo.pk)).content.decode()

    assert 'value="Indeferir"' in html
    motivo = re.search(r'<textarea[^>]*name="motivo_indeferimento_rh"[^>]*>', html)
    # o motivo divide o formulário com o "Deferir": com o required do HTML, o navegador barraria o deferimento
    # (o aria-required só anuncia a obrigatoriedade ao leitor de tela, não bloqueia o envio)
    assert motivo
    assert not re.search(r'(?<![-\w])required\b', motivo.group())


def test_indeferir_carga_horaria_excepcional_exige_motivo(client: Client) -> None:
    processo = _ch_excepcional()
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    _indeferir_ch_excepcional(client, processo, motivo='')

    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO, None)
    assert _indeferimentos_notificados(processo) == 0


@pytest.mark.parametrize('status', [CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH, CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH])
def test_carga_horaria_excepcional_decidida_nao_e_indeferida(client: Client, status: int) -> None:
    """Deferida, o indeferimento reverteria a decisão; indeferida, trocaria o validador e o motivo e renotificaria."""
    processo = _ch_excepcional(status=status)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    assert _indeferir_ch_excepcional(client, processo).status_code == 403
    assert _situacao(processo) == (status, None)
    assert _indeferimentos_notificados(processo) == 0


def test_indeferir_ch_excepcional_nao_indefere_afastamento_parcial(client: Client) -> None:
    """O afastamento parcial é indeferido pelo "Atualizar Situação"."""
    processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    assert _indeferir_ch_excepcional(client, processo).status_code == 403
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH, None)


@pytest.mark.parametrize('situacao', [CargaHorariaReduzida.STATUS_AMIGAVEL_DEFERIDO, CargaHorariaReduzida.STATUS_AMIGAVEL_INDEFERIDO])
def test_situacao_da_carga_horaria_excepcional_nao_muda_pela_url(client: Client, situacao: str) -> None:
    """O "Atualizar Situação" só aparece no afastamento parcial; a carga horária excepcional tem "Deferir" e "Indeferir"."""
    processo = _ch_excepcional(status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    resposta = client.post(ALTERAR_SITUACAO.format(processo.pk, situacao), {'motivo_indeferimento_rh': 'pela URL'})

    assert resposta.status_code == 403
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH, None)


def test_rh_indefere_afastamento_parcial_pela_url(client: Client) -> None:
    processo = _horario_em_validacao_pelo_rh().processo_reducao_ch
    rh = _ator(RH_SISTEMICO_OUTRO, processo)
    client.force_login(rh)

    resposta = client.post(
        ALTERAR_SITUACAO.format(processo.pk, CargaHorariaReduzida.STATUS_AMIGAVEL_INDEFERIDO), {'motivo_indeferimento_rh': 'Sem documentação.'}
    )

    assert resposta.status_code == 302
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH, rh.get_relacionamento().pk)
    assert _motivo(processo) == 'Sem documentação.'
    assert _indeferimentos_notificados(processo) == 1


# --- O indeferimento da carga horária excepcional é final (#17729) ---------------------------------------------------


def test_carga_horaria_excepcional_indeferida_nao_e_deferida(client: Client) -> None:
    processo = _ch_excepcional(status=CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    assert client.post(ABRIR.format(processo.pk), {'acao': 'salvar_ch_excepcional'}).status_code == 403
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH, None)
    assert _deferimentos_notificados(processo) == 0


def test_tela_da_carga_horaria_excepcional_indeferida_nao_oferece_deferir_nem_indeferir(client: Client) -> None:
    processo = _ch_excepcional(status=CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH)
    client.force_login(_ator(RH_SISTEMICO_OUTRO, processo))

    html = client.get(ABRIR.format(processo.pk)).content.decode()

    assert 'value="Deferir"' not in html
    assert 'value="Indeferir"' not in html


def test_carga_horaria_excepcional_nao_decidida_continua_sendo_deferida(client: Client) -> None:
    processo = _ch_excepcional()
    rh = _ator(RH_SISTEMICO_OUTRO, processo)
    client.force_login(rh)

    assert 'value="Deferir"' in client.get(ABRIR.format(processo.pk)).content.decode()
    assert client.post(ABRIR.format(processo.pk), {'acao': 'salvar_ch_excepcional'}).status_code == 302
    assert _situacao(processo) == (CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH, rh.get_relacionamento().pk)


@pytest.mark.parametrize(
    'status', [valor for nome, valor in vars(CargaHorariaReduzida).items() if re.fullmatch(r'STATUS_[A-Z_]+', nome) and isinstance(valor, int)]
)
def test_so_o_status_indeferido_pelo_rh_e_indeferido_pelo_rh(status: int) -> None:
    processo = CargaHorariaReduzida(status=status)

    assert processo.status_processo_indeferido_pelo_rh() is (status == CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH)
