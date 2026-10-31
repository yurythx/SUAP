"""Listagem "Documentos esperando assinatura" (``?opcao=4``) sem o join largo (#17687, incidente #17674).

O filtro fazia JOIN de ``documentotexto`` com a solicitação e semi join com a subquery das
solicitações pendentes; somado ao ``select_related`` da ``pessoafisica`` inteira do autor, o
planner montava em produção um hash paralelo do ``documentotexto`` inteiro (1M linhas). Com
até 32 resultados o admin não pagina e executa a listagem sem ``LIMIT`` — sempre o caso de
quem não tem nada a assinar, como o aluno da rajada. Agora os ids pendentes são materializados
numa consulta indexada e o documento é filtrado por literais.

As colunas da listagem (assinaturas, datas, favorito, autor) são carregadas por página, não
linha a linha (#17700).
"""

from __future__ import annotations

import re

import pytest
from django.db import connection
from django.http import HttpResponse
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import formats, timezone

from comum.models import User, Vinculo
from djtools.models import Task
from djtools.templatetags.filters import status
from djtools.utils import normalizar_nome_proprio
from documento_eletronico.admin import DashboardFilter
from documento_eletronico.models import (
    Assinatura,
    AssinaturaDocumentoTexto,
    DocumentoTexto,
    RegistroAcaoDocumentoTexto,
    SolicitacaoAssinatura,
)
from documento_eletronico.status import DocumentoStatus, SolicitacaoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory, RegistroAcaoDocumentoTextoFactory, SolicitacaoAssinaturaFactory
from edu.tests.factories import AlunoFactory
from rh.models import Papel, Pessoa, Servidor
from rh.tests.factories import PapelFactory, ServidorFactory

pytestmark = pytest.mark.django_db

URL = '/admin/documento_eletronico/documentotexto/'
TABELA_SOLICITACAO = '"documento_eletronico_solicitacaoassinatura"'
ORDEM_LISTAGEM = (
    'ORDER BY "documento_eletronico_documentotexto"."data_criacao" DESC, "documento_eletronico_documentotexto"."identificador_numero" DESC'
)


def _solicitar(
    documento: DocumentoTexto, solicitante: User, solicitado: Vinculo, status: int = SolicitacaoStatus.STATUS_ESPERANDO
) -> SolicitacaoAssinatura:
    return SolicitacaoAssinaturaFactory(documento=documento, solicitante=solicitante, solicitado=solicitado, status=status)


def _cenario() -> tuple[User, set[DocumentoTexto], DocumentoTexto]:
    """Aluno signatário com documentos em cada situação de solicitação; devolve (aluno, esperados, documento pendente)."""
    dono = ServidorFactory(pessoa_fisica__nome='Autora Documental').get_user()
    outro = ServidorFactory().get_user().get_vinculo()
    aluno = AlunoFactory().get_user()
    signatario = aluno.get_vinculo()

    sem_condicionante, condicionante_deferida, condicionante_pendente, de_outro, ja_deferida, duas_solicitacoes = (
        DocumentoTextoFactory(usuario_criacao=dono, status=DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA) for _ in range(6)
    )
    _solicitar(sem_condicionante, dono, signatario)
    deferida = _solicitar(condicionante_deferida, dono, outro, SolicitacaoStatus.STATUS_DEFERIDA)
    _solicitar(condicionante_deferida, dono, signatario).condicionantes.add(deferida)
    pendente = _solicitar(condicionante_pendente, dono, outro)
    _solicitar(condicionante_pendente, dono, signatario).condicionantes.add(pendente)
    _solicitar(de_outro, dono, outro)
    _solicitar(ja_deferida, dono, signatario, SolicitacaoStatus.STATUS_DEFERIDA)
    _solicitar(duas_solicitacoes, dono, signatario)
    _solicitar(duas_solicitacoes, dono, signatario)
    return aluno, {sem_condicionante, condicionante_deferida, duas_solicitacoes}, sem_condicionante


def test_esperando_assinatura_lista_so_as_pendentes_liberadas_filtrando_por_ids(sync_permissions: None) -> None:
    aluno, esperados, _ = _cenario()

    esperando = DocumentoTexto.objects.esperando_assinatura(aluno)

    assert set(esperando) == esperados
    # Duas solicitações pendentes para o mesmo documento não o contam duas vezes.
    assert esperando.count() == len(esperados)
    assert set(DocumentoTexto.objects.by_user(aluno)) == esperados
    # O documento é filtrado pelos ids já materializados: nem JOIN nem subquery da solicitação.
    sql = str(esperando.query)
    assert TABELA_SOLICITACAO not in sql
    filtro = re.search(r'"documento_eletronico_documentotexto"\."id" IN \(([\d, ]+)\)', sql)
    assert filtro
    assert {int(pk) for pk in filtro.group(1).split(',')} == {d.pk for d in esperados}


def test_sem_pendencias_nao_consulta_documentos_e_by_user_mantem_os_demais_ramos(sync_permissions: None) -> None:
    servidor = ServidorFactory().get_user()
    proprio = DocumentoTextoFactory(usuario_criacao=servidor)

    with CaptureQueriesContext(connection) as consultas:
        assert list(DocumentoTexto.objects.esperando_assinatura(servidor)) == []
        assert DocumentoTexto.objects.esperando_assinatura(servidor).count() == 0
    # Só a consulta indexada das solicitações; a lista vazia não chega a consultar documentos.
    assert consultas.captured_queries
    assert not [q for q in consultas.captured_queries if 'FROM "documento_eletronico_documentotexto"' in q['sql']]
    # No OR do by_user o ramo vazio cai sem anular os outros: o documento próprio continua visível.
    assert proprio in DocumentoTexto.objects.by_user(servidor)


def test_listagem_do_aluno_nao_monta_o_join_largo(client: Client, sync_permissions: None) -> None:
    aluno, _, pendente = _cenario()
    client.force_login(aluno)

    with CaptureQueriesContext(connection) as sem_filtro:
        resposta = client.get(URL)
    # Sem ``?opcao=`` a tela não redireciona nem consulta as solicitações.
    assert resposta.status_code == 200
    assert not resposta.has_header('Location')
    assert not [q for q in sem_filtro.captured_queries if TABELA_SOLICITACAO in q['sql']]

    # Cache por processo do perfil (User.get_profile) esconderia a carga do nome do autor linha a linha.
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()
    with CaptureQueriesContext(connection) as com_filtro:
        resposta = client.get(URL, {'opcao': '4'})
    assert resposta.status_code == 200
    assert pendente in resposta.context['cl'].result_list
    assert 'Autora Documental' in resposta.content.decode()
    documentos = [q['sql'] for q in com_filtro.captured_queries if 'FROM "documento_eletronico_documentotexto"' in q['sql']]
    assert not [sql for sql in documentos if TABELA_SOLICITACAO in sql]
    listagem = [sql for sql in documentos if sql.endswith(ORDEM_LISTAGEM)]
    assert listagem
    # Só os campos do autor exibidos; nada de pessoa_fisica inteira (template de digital, senha do ponto...).
    assert not [sql for sql in listagem if '"pessoa_fisica"."template"' in sql]
    # ...mas o nome do autor vem na própria listagem: nada de carga adiada do nome, autor a autor.
    assert not [q for q in com_filtro.captured_queries if q['sql'].startswith('SELECT "pessoa"."nome_usual"')]


def test_listagem_do_aluno_sem_pendencias_nao_consulta_documentos(client: Client, sync_permissions: None) -> None:
    client.force_login(AlunoFactory().get_user())

    with CaptureQueriesContext(connection) as consultas:
        resposta = client.get(URL, {'opcao': '4'})

    assert resposta.status_code == 200
    assert list(resposta.context['cl'].result_list) == []
    documentos = [q['sql'] for q in consultas.captured_queries if 'FROM "documento_eletronico_documentotexto"' in q['sql']]
    # Nem a listagem sem LIMIT, nem COUNT/date_hierarchy filtrados: a lista vazia de ids encerra o filtro antes do banco.
    assert not [sql for sql in documentos if sql.endswith(ORDEM_LISTAGEM) or '"documento_eletronico_documentotexto"."id" IN' in sql]


def _documentos_assinados(servidor: Servidor, papel: Papel, quantidade: int) -> list[DocumentoTexto]:
    """Documentos públicos do setor do ``servidor``, de autores distintos, assinados, finalizados e favoritados por ele."""
    user = servidor.get_user()
    vinculo = user.get_vinculo()
    documentos = []
    for _ in range(quantidade):
        autor = ServidorFactory().get_user()
        documento = DocumentoTextoFactory(usuario_criacao=autor, setor_dono=servidor.setor, status=DocumentoStatus.STATUS_FINALIZADO)
        assinatura = Assinatura.objects.create(
            vinculo=vinculo, cpf=servidor.pessoa_fisica.cpf, nome_papel=papel.detalhamento, papel=papel, hmac=f'hmac-{documento.pk}'
        )
        documento.assinatura_balizadora = AssinaturaDocumentoTexto.objects.create(documento=documento, assinatura=assinatura)
        documento.save()
        RegistroAcaoDocumentoTextoFactory(documento=documento, user=autor, tipo=RegistroAcaoDocumentoTexto.TIPO_FINALIZACAO)
        documento.usuarios_marcadores_favoritos.add(user)
        documentos.append(documento)
    return documentos


def _listar(client: Client, opcao: str) -> tuple[HttpResponse, int]:
    """GET na listagem; devolve a resposta e o nº de consultas."""
    # Sem os caches por processo do perfil, que mascarariam a carga do autor linha a linha.
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()
    with CaptureQueriesContext(connection) as consultas:
        resposta = client.get(URL, {'opcao': opcao})
    assert resposta.status_code == 200
    # A solicitação balizadora do ícone de edição (pode_editar) também vem por página (#17710): nada é descontado.
    return resposta, len(consultas.captured_queries)


def _linha(resposta: HttpResponse, documento: DocumentoTexto) -> str:
    html = resposta.content.decode()
    return re.search(rf'<tr[^>]*>(?:(?!</tr>).)*/gerenciar_favoritos/{documento.pk}/(?:(?!</tr>).)*</tr>', html, re.DOTALL).group(0)


def _perfil(pessoa: Pessoa, nome: str) -> str:
    return f'data-profile-id="{pessoa.uuid}">{nome}</a>'


def test_listagem_nao_consulta_o_banco_linha_a_linha(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory(pessoa_fisica__nome='Assinante Documental')
    papel = PapelFactory(servidor=servidor)
    client.force_login(servidor.get_user())
    # A 1ª requisição paga custos únicos da sessão (grupos, preferências, notificações): fica fora da comparação.
    _listar(client, DashboardFilter.DOCUMENTOS_ASSINADOS_POR_MIM)

    documentos = _documentos_assinados(servidor, papel, 2)
    resposta, com_dois = _listar(client, DashboardFilter.DOCUMENTOS_ASSINADOS_POR_MIM)
    assert len(resposta.context['cl'].result_list) == 2

    documentos += _documentos_assinados(servidor, papel, 4)
    resposta, com_seis = _listar(client, DashboardFilter.DOCUMENTOS_ASSINADOS_POR_MIM)
    assert len(resposta.context['cl'].result_list) == 6

    assert com_seis - com_dois <= 2, f'{com_dois} consultas com 2 documentos, {com_seis} com 6'

    # O conteúdo das colunas segue o mesmo.
    documento = documentos[-1]
    linha = _linha(resposta, documento)
    autor = documento.usuario_criacao.get_profile()
    assert _perfil(autor, normalizar_nome_proprio(autor.nome_usual or autor.nome)) in linha
    assert _perfil(servidor.pessoa_fisica, 'Assinante Documental') in linha
    assert f'<td class="field-setor_dono nowrap">{servidor.setor}</td>' in linha
    assert f'/gerenciar_favoritos/{documento.pk}/remove/' in linha
    assert 'fa-star warning' in linha
    assert formats.localize(timezone.template_localtime(documento.assinatura_balizadora.assinatura.data_assinatura)) in linha
    finalizacao = RegistroAcaoDocumentoTexto.objects.get(documento=documento, tipo=RegistroAcaoDocumentoTexto.TIPO_FINALIZACAO).data
    assert formats.localize(timezone.template_localtime(finalizacao)) in linha


def test_listagem_mostra_as_solicitacoes_do_documento_aguardando_assinatura(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory(pessoa_fisica__nome='Signatario Pendente')
    autor = ServidorFactory().get_user()
    documento = DocumentoTextoFactory(usuario_criacao=autor, setor_dono=servidor.setor, status=DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA)
    solicitacao = _solicitar(documento, autor, servidor.get_vinculo())
    client.force_login(servidor.get_user())

    resposta, _ = _listar(client, DashboardFilter.DOCUMENTOS_ESPERANDO_ASSINATURA)

    linha = _linha(resposta, documento)
    assert _perfil(servidor.pessoa_fisica, 'Signatario Pendente') in linha
    assert f'</div>{status(solicitacao.get_status_display())}</li>' in linha
    assert f'/gerenciar_favoritos/{documento.pk}/add/' in linha
    assert 'fa-star disabled' in linha
    assert '<td class="field-get_data_primeira_assinatura">-</td><td class="field-get_data_finalizacao">-</td>' in linha


def test_exportacao_csv_renderiza_o_favorito_sem_o_prefetch_da_pagina(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory()
    user = servidor.get_user()
    documento = DocumentoTextoFactory(usuario_criacao=user, setor_dono=servidor.setor, status=DocumentoStatus.STATUS_FINALIZADO)
    documento.usuarios_marcadores_favoritos.add(user)
    client.force_login(user)

    # A exportação percorre o queryset do admin, não o resultado paginado do DocumentoTextoChangeList: sem o cache da
    # página, a coluna de favorito estourava AttributeError dentro da tarefa.
    resposta = client.get(URL, {'opcao': DashboardFilter.FAVORITOS, 'export_to_csv': '1'}, follow=True)

    assert resposta.status_code == 200
    assert 'Exportar para XLS/CSV Admin' in resposta.content.decode()


def test_exportacao_csv_traz_o_nome_de_quem_assinou_o_documento(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory(pessoa_fisica__nome='Assinante Exportado')
    papel = PapelFactory(servidor=servidor)
    _documentos_assinados(servidor, papel, 1)
    client.force_login(servidor.get_user())

    # ``get_assinaturas`` do model (e não a do admin) resolve a coluna: antes, ``AssinaturaDocumentoTexto.pessoa`` não existia.
    resposta = client.get(URL, {'opcao': DashboardFilter.DOCUMENTOS_ASSINADOS_POR_MIM, 'export_to_csv': '1'}, follow=True)

    assert resposta.status_code == 200
    tarefa = Task.objects.get(type='Exportar para XLS/CSV Admin')
    assert not tarefa.error
    with open(tarefa.file, encoding='utf-8-sig') as arquivo:
        assert 'Assinante Exportado' in arquivo.read()
