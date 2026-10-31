"""Listagem padrão do admin de documentos (sem ``?opcao=``): só os documentos que o usuário pode ler (#17699).

Antes, qualquer usuário logado — aluno inclusive — via setor, tipo, identificador, nível de acesso e
autor de todos os documentos de setor, e a contagem total. Agora a visão geral aplica a regra de
``pode_ler`` (``DocumentoTexto.objects.legiveis_por``), na listagem, na contagem e no total.

As checagens de permissão de cada linha (assunto, assinaturas, ícones) leem os dados carregados
por página, não consultam o banco linha a linha (#17710).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.html import conditional_escape

from comum.models import Configuracao, User, Vinculo
from djtools.middleware import threadlocals as tl
from documento_eletronico.admin import DashboardFilter
from documento_eletronico.models import (
    Assinatura,
    AssinaturaDocumentoTexto,
    CompartilhamentoDocumentoPessoa,
    Documento,
    DocumentoTexto,
    DocumentoTextoInteressado,
    ModeloDocumento,
    NivelPermissao,
    SolicitacaoAssinatura,
    SolicitacaoRevisao,
)
from documento_eletronico.status import DocumentoStatus, SolicitacaoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory, ModeloDocumentoFactory, SolicitacaoAssinaturaFactory
from documento_eletronico.tests.models.test_documentos_legiveis import _juntada_pendente, _no_processo, _processo
from edu.tests.factories import AlunoFactory
from processo_eletronico.models import Processo
from processo_eletronico.tests.factories import CompartilhamentoPoderChefeFactory, ProcessoFactory
from rh.models import Papel, Servidor, Setor
from rh.tests.factories import PapelFactory, ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db

URL = '/admin/documento_eletronico/documentotexto/'
FINALIZADO = DocumentoStatus.STATUS_FINALIZADO


def _documentos_de_outro_setor(setor: Setor) -> dict[str, DocumentoTexto]:
    autor = ServidorFactory(setor=setor).get_user()

    def doc(nivel: int, status: int = FINALIZADO) -> DocumentoTexto:
        return DocumentoTextoFactory(usuario_criacao=autor, setor_dono=setor, nivel_acesso=nivel, status=status)

    return {
        'publico': doc(Documento.NIVEL_ACESSO_PUBLICO),
        'publico_rascunho': doc(Documento.NIVEL_ACESSO_PUBLICO, DocumentoStatus.STATUS_RASCUNHO),
        'restrito': doc(Documento.NIVEL_ACESSO_RESTRITO),
        'sigiloso': doc(Documento.NIVEL_ACESSO_SIGILOSO),
        'sigiloso_compartilhado': doc(Documento.NIVEL_ACESSO_SIGILOSO),
        'restrito_concluido': doc(Documento.NIVEL_ACESSO_RESTRITO, DocumentoStatus.STATUS_CONCLUIDO),
    }


@pytest.mark.parametrize('papel', ['aluno', 'servidor'])
def test_listagem_padrao_so_mostra_e_conta_os_documentos_legiveis(client: Client, sync_permissions: None, papel: str) -> None:
    docs = _documentos_de_outro_setor(SetorFactory())
    user = AlunoFactory().get_user() if papel == 'aluno' else ServidorFactory().get_user()
    tl.context.user = user
    CompartilhamentoDocumentoPessoa.objects.create(documento=docs['sigiloso_compartilhado'], vinculo_permitido=user.get_vinculo())
    tl.context.user = None
    client.force_login(user)

    resposta = client.get(URL)

    assert resposta.status_code == 200
    cl = resposta.context['cl']
    esperados = {d for d in docs.values() if d.pode_ler(user)}
    assert set(cl.result_list) == esperados
    assert cl.result_count == cl.full_result_count == len(esperados)
    # Lê o público finalizado e o sigiloso compartilhado com ele; restrito e sigiloso de outro setor, não.
    assert esperados == {docs['publico'], docs['sigiloso_compartilhado']}
    html = resposta.content.decode()
    for nome in ('restrito', 'sigiloso', 'publico_rascunho', 'restrito_concluido'):
        assert f'/gerenciar_favoritos/{docs[nome].pk}/' not in html


def test_busca_e_exportacao_da_listagem_padrao_seguem_o_filtro(client: Client, sync_permissions: None) -> None:
    """A busca (inclusive no corpo, que soma um OR ao resultado) e a exportação partem da mesma raiz filtrada."""
    docs = _documentos_de_outro_setor(SetorFactory())
    restrito = docs['restrito']
    tipo = restrito.modelo.tipo_documento_texto
    tipo.permite_busca_corpo_conteudo = True
    tipo.save()
    DocumentoTexto.objects.filter(pk=restrito.pk).update(corpo_indexado='segredo do restrito')
    servidor = ServidorFactory().get_user()
    client.force_login(servidor)

    buscas = ({'q': restrito.assunto}, {'q': 'segredo', 'tipo': tipo.pk}, {'q': str(restrito.pk)})
    for busca in buscas:
        resposta = client.get(URL, busca)
        assert resposta.status_code == 200
        assert restrito not in resposta.context['cl'].result_list, busca
    # As mesmas buscas acham o documento para quem pode lê-lo: o que some acima é o filtro, não a busca.
    client.force_login(restrito.usuario_criacao)
    for busca in buscas:
        assert restrito in client.get(URL, busca).context['cl'].result_list, busca
    client.force_login(servidor)

    # A exportação CSV/XLS sai de get_current_queryset, sobre a mesma ChangeList.
    requisicao = RequestFactory().get(URL)
    requisicao.user = servidor
    exportados = admin.site._registry[DocumentoTexto].get_current_queryset(requisicao)
    assert set(exportados) == {docs['publico']}


def test_contagem_da_listagem_padrao_filtra_sem_join(client: Client, sync_permissions: None) -> None:
    """O COUNT roda para todo usuário sobre o documentotexto inteiro (incidente #17674): só a própria tabela."""
    docs = _documentos_de_outro_setor(SetorFactory())
    servidor = ServidorFactory().get_user()
    client.force_login(servidor)
    # Sem os caches por processo do perfil, que mascarariam consultas.
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()

    with CaptureQueriesContext(connection) as consultas:
        resposta = client.get(URL)

    assert set(resposta.context['cl'].result_list) == {docs['publico']}
    contagens = [q['sql'] for q in consultas.captured_queries if q['sql'].startswith('SELECT COUNT(*)') and 'documentotexto' in q['sql']]
    assert contagens
    for sql in contagens:
        assert ' JOIN ' not in sql, sql
        assert sql.count('SELECT') == 1, sql


def test_agrupamento_continua_mostrando_o_que_o_usuario_revisa_sem_poder_ler(client: Client, sync_permissions: None) -> None:
    """As opções do agrupamento já filtram pelo usuário e ficam como estavam: o revisor não lê, mas revisa."""
    docs = _documentos_de_outro_setor(SetorFactory())
    revisor = ServidorFactory().get_user()
    em_revisao = docs['restrito_concluido']
    tl.context.user = em_revisao.usuario_criacao
    SolicitacaoRevisao.objects.create(documento=em_revisao, revisor=revisor.get_vinculo())
    tl.context.user = None
    client.force_login(revisor)
    assert not em_revisao.pode_ler(revisor)

    resposta = client.get(URL, {'opcao': DashboardFilter.DOCUMENTOS_ESPERANDO_REVISAO})

    assert resposta.status_code == 200
    assert list(resposta.context['cl'].result_list) == [em_revisao]
    assert em_revisao not in client.get(URL).context['cl'].result_list


RESTRITO = Documento.NIVEL_ACESSO_RESTRITO
# Restritos que o usuário lê, finalizados e não finalizados: cada situação passa por um ramo diferente do get_assunto.
SITUACOES = (FINALIZADO, DocumentoStatus.STATUS_CONCLUIDO, DocumentoStatus.STATUS_ASSINADO)


def _consultas(client: Client, opcao: str) -> tuple[list[DocumentoTexto], int]:
    # Sem os caches por processo do perfil, que mascarariam consultas linha a linha.
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()
    with CaptureQueriesContext(connection) as consultas:
        resposta = client.get(URL, {'opcao': opcao} if opcao else {})
    assert resposta.status_code == 200
    return list(resposta.context['cl'].result_list), len(consultas.captured_queries)


@pytest.mark.parametrize('opcao', ['', DashboardFilter.COMPARTILHADOS_COMIGO])
@pytest.mark.parametrize('papel', ['servidor', 'chefe'])
def test_listagem_nao_checa_permissao_linha_a_linha(client: Client, sync_permissions: None, papel: str, opcao: str) -> None:
    """Restritos legíveis — compartilhados com o servidor, ou do setor que o chefe chefia — não custam consultas por linha."""
    meu_setor = SetorFactory()
    setor_dos_documentos = meu_setor if papel == 'chefe' else SetorFactory()
    autor = ServidorFactory(setor=setor_dos_documentos).get_user()
    user = ServidorFactory(setor=meu_setor).get_user()
    tl.context.user = autor  # CurrentUserField dos compartilhamentos.
    if papel == 'chefe':
        CompartilhamentoPoderChefeFactory(setor_dono=meu_setor, vinculo_permitido=user.get_vinculo())
    tl.context.user = None
    client.force_login(user)

    def criar(quantidade: int) -> None:
        tl.context.user = autor
        for i in range(quantidade):
            documento = DocumentoTextoFactory(
                usuario_criacao=autor, setor_dono=setor_dos_documentos, nivel_acesso=RESTRITO, status=SITUACOES[i % len(SITUACOES)]
            )
            if papel == 'servidor':
                CompartilhamentoDocumentoPessoa.objects.create(documento=documento, vinculo_permitido=user.get_vinculo())
        tl.context.user = None

    # A 1ª requisição paga custos únicos da sessão (grupos, preferências, notificações): fica fora da comparação.
    _consultas(client, opcao)
    criar(2)
    documentos, com_dois = _consultas(client, opcao)
    assert len(documentos) == 2
    criar(4)
    documentos, com_seis = _consultas(client, opcao)
    assert len(documentos) == 6
    # Instâncias novas, fora da página: a regra consultada no banco, não o cache da listagem.
    assert all(documento.pode_ler(user) for documento in DocumentoTexto.objects.filter(pk__in=[d.pk for d in documentos]))

    assert com_seis - com_dois <= 2, f'{com_dois} consultas com 2 documentos, {com_seis} com 6'


def _celula(linha: str, campo: str) -> str:
    # A 1ª coluna (os ícones) sai em <th>.
    return re.search(rf'<t([dh]) class="field-{campo}[^"]*">(.*?)</t\1>', linha, re.DOTALL).group(2)


def _linhas_conferidas(client: Client, user: User, opcoes: tuple[str, ...]) -> list[tuple[DocumentoTexto, str, bool, bool]]:
    """Confere, linha a linha, o assunto e os ícones de cada listagem com as permissões consultadas fora dela; devolve
    ``(documento, assunto, pode_ler, pode_editar)`` de cada linha."""
    model_admin = admin.site._registry[DocumentoTexto]
    linhas = []
    for opcao in opcoes:
        resposta = client.get(URL, {'opcao': opcao} if opcao else {})
        html = resposta.content.decode()
        for documento in resposta.context['cl'].result_list:
            linha = re.search(rf'<tr[^>]*>(?:(?!</tr>).)*/gerenciar_favoritos/{documento.pk}/(?:(?!</tr>).)*</tr>', html, re.DOTALL).group(0)
            # Instância nova, fora da página: as permissões consultam o banco, como em qualquer outra tela.
            avulso = DocumentoTexto.objects.get(pk=documento.pk)
            tl.context.user = user
            assunto, pode_ler, pode_editar = model_admin.get_assunto(avulso), avulso.pode_ler(user), avulso.pode_editar(user)
            tl.context.user = None
            assert _celula(linha, 'get_assunto') == conditional_escape(assunto), (opcao, documento.assunto)
            icones = _celula(linha, 'show_list_display_icons')
            assert ('icon-view' in icones, 'icon-edit' in icones) == (pode_ler, pode_editar), (opcao, documento.assunto)
            linhas.append((documento, assunto, pode_ler, pode_editar))
    return linhas


def test_colunas_da_listagem_seguem_as_permissoes_de_cada_documento(client: Client, sync_permissions: None) -> None:
    """Caracterização: o assunto e os ícones de cada linha são os que as permissões dão consultadas fora da listagem."""
    servidor = ServidorFactory()
    papel = PapelFactory(servidor=servidor)
    user = servidor.get_user()
    vinculo = user.get_vinculo()
    autor = ServidorFactory().get_user()
    setor = autor.get_relacionamento().setor
    tl.context.user = autor

    def doc(status: int, compartilhamento: int | None = None) -> DocumentoTexto:
        documento = DocumentoTextoFactory(usuario_criacao=autor, setor_dono=setor, nivel_acesso=RESTRITO, status=status)
        if compartilhamento:
            CompartilhamentoDocumentoPessoa.objects.create(documento=documento, vinculo_permitido=vinculo, nivel_permissao=compartilhamento)
        return documento

    ler, editar = NivelPermissao.LER, NivelPermissao.EDITAR
    doc(FINALIZADO, ler)  # lê: assunto e visualizar
    doc(DocumentoStatus.STATUS_CONCLUIDO, ler)  # lê, mas o assunto fica restrito até a finalização
    doc(DocumentoStatus.STATUS_RASCUNHO, editar)  # edita o rascunho: ícone de editar
    doc(DocumentoStatus.STATUS_CONCLUIDO, editar)  # edita, mas só o rascunho tem ícone de editar
    aguardando = doc(DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA, ler)  # assina e edita pela solicitação balizadora
    SolicitacaoAssinaturaFactory(documento=aguardando, solicitante=autor, solicitado=vinculo)
    ja_assinou = doc(DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA, ler)  # já assinou: não assina de novo, mas edita
    SolicitacaoAssinaturaFactory(documento=ja_assinou, solicitante=autor, solicitado=vinculo)
    assinatura = Assinatura.objects.create(
        vinculo=vinculo, cpf=servidor.pessoa_fisica.cpf, nome_papel=papel.detalhamento, papel=papel, hmac=f'hmac-{ja_assinou.pk}'
    )
    AssinaturaDocumentoTexto.objects.create(documento=ja_assinou, assinatura=assinatura)
    # A assinatura defere a solicitação e avança o documento: volta ao "aguardando", com a solicitação ainda pendente.
    SolicitacaoAssinatura.objects.filter(documento=ja_assinou).update(status=SolicitacaoStatus.STATUS_ESPERANDO)
    DocumentoTexto.objects.filter(pk=ja_assinou.pk).update(status=DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA)
    de_outro = doc(DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA, ler)  # a solicitação é de outro: nem assina nem edita
    SolicitacaoAssinaturaFactory(documento=de_outro, solicitante=autor, solicitado=ServidorFactory().get_user().get_vinculo())
    # Revisor que não lê: em revisão, edita sem visualizar; revisado e depois finalizado, nem assunto nem ícones.
    SolicitacaoRevisao.objects.create(documento=doc(DocumentoStatus.STATUS_CONCLUIDO), revisor=vinculo)
    revisado = doc(DocumentoStatus.STATUS_CONCLUIDO)
    SolicitacaoRevisao.objects.create(documento=revisado, revisor=vinculo)
    SolicitacaoRevisao.objects.filter(documento=revisado).update(data_resposta=timezone.now(), status=SolicitacaoStatus.STATUS_DEFERIDA)
    DocumentoTexto.objects.filter(pk=revisado.pk).update(status=FINALIZADO)
    tl.context.user = None
    client.force_login(user)

    vistos = set()
    opcoes = ('', DashboardFilter.DOCUMENTOS_ESPERANDO_ASSINATURA, DashboardFilter.DOCUMENTOS_ESPERANDO_REVISAO, DashboardFilter.DOCUMENTOS_REVISADOS)
    for documento, assunto, pode_ler, pode_editar in _linhas_conferidas(client, user, opcoes):
        vistos.add((assunto == documento.assunto, pode_ler, pode_editar))
        vistos.add(assunto)

    # Cada coluna aparece nos dois sentidos: o cenário exercita os ramos, não só o caso feliz.
    assert {'Assunto Restrito', 'Assunto restrito até a finalização do documento.'} <= vistos
    assert {(True, True, False), (False, True, False), (True, True, True), (False, True, True), (False, False, True), (False, False, False)} <= vistos


def _opcoes_do_filtro(client: Client, html: str, filtro: str) -> set[int]:
    """Ids que o autocomplete do filtro lateral oferece, pelo caminho do navegador: a consulta assinada que a página
    entrega (``control``) vai, com a busca vazia, para o endpoint JSON do autocomplete."""
    script = re.search(rf'id="{filtro}_select".*?url: "([^"]+)".*?control: \'([^\']+)\'', html, re.DOTALL)
    assert script, f'filtro {filtro} sem autocomplete'
    url, control = script.groups()
    resposta = client.post(url, {'q': '', 'control': control})
    assert resposta.status_code == 200
    return {int(item['id']) for item in resposta.json()['items']}


@pytest.mark.parametrize('opcao', ['', DashboardFilter.COMPARTILHADOS_COMIGO])
@pytest.mark.parametrize('papel', ['aluno', 'servidor'])
def test_filtros_de_autor_e_interessado_so_oferecem_os_documentos_da_listagem(client: Client, sync_permissions: None, papel: str, opcao: str) -> None:
    """O autocomplete dos filtros laterais não revela autor nem interessado de documento que a listagem esconde (#17718)."""
    setor = SetorFactory()
    autor_restrito, autor_publico = ServidorFactory(setor=setor).get_user(), ServidorFactory(setor=setor).get_user()
    interessado_restrito, interessado_publico = ServidorFactory().get_user().get_vinculo(), ServidorFactory().get_user().get_vinculo()
    restrito = DocumentoTextoFactory(usuario_criacao=autor_restrito, setor_dono=setor, nivel_acesso=RESTRITO, status=FINALIZADO)
    publico = DocumentoTextoFactory(usuario_criacao=autor_publico, setor_dono=setor, nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO, status=FINALIZADO)
    DocumentoTextoInteressado.objects.create(documentotexto=restrito, vinculo=interessado_restrito)
    DocumentoTextoInteressado.objects.create(documentotexto=publico, vinculo=interessado_publico)
    user = AlunoFactory().get_user() if papel == 'aluno' else ServidorFactory().get_user()
    tl.context.user = autor_publico
    CompartilhamentoDocumentoPessoa.objects.create(documento=publico, vinculo_permitido=user.get_vinculo())
    tl.context.user = None
    client.force_login(user)

    resposta = client.get(URL, {'opcao': opcao} if opcao else {})

    assert list(resposta.context['cl'].result_list) == [publico]
    html = resposta.content.decode()
    autores = _opcoes_do_filtro(client, html, 'usuario_criacao')
    assert autor_publico.pk in autores
    assert autor_restrito.pk not in autores
    interessados = _opcoes_do_filtro(client, html, 'interessados')
    assert interessado_publico.pk in interessados
    assert interessado_restrito.pk not in interessados


# Demais perfis (#17722): leitura via processo, juntada pendente, leitura sistêmica, cargo, revisão, assinatura pendente
# e documentos pessoais.
Criar = Callable[[int], None]
Caso = Callable[[Servidor], tuple[str, Criar]]
PUBLICO = Documento.NIVEL_ACESSO_PUBLICO
CANCELADO, CONCLUIDO = DocumentoStatus.STATUS_CANCELADO, DocumentoStatus.STATUS_CONCLUIDO
AGUARDANDO = DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA
GRUPO_SISTEMICO = 'Sistêmico de Leitura'


def _setor_siorg() -> Setor:
    # O NUP do processo sai do código SIORG do setor.
    return SetorFactory(codigo_siorg=str(Processo.CODIGO_SIORG))


def _setor_e_autor() -> tuple[Setor, User]:
    setor = _setor_siorg()
    return setor, ServidorFactory(setor=setor).get_user()


def _entrar_em(user: User, *grupos: str) -> None:
    for grupo in grupos:
        Group.objects.get_or_create(name=grupo)[0].user_set.add(user)


def _configurar(modelo_sistemico: ModeloDocumento, procuradoria: Setor) -> None:
    Configuracao.objects.create(app='rh', chave='setor_procuradoria', valor=str(procuradoria.pk))
    Configuracao.objects.create(
        app='documento_eletronico',
        chave='grupossistemicos_com_perm_leitura_de_modelosdoc',
        valor=json.dumps({GRUPO_SISTEMICO: [modelo_sistemico.pk]}),
    )


def _assinar(servidor: Servidor, papel: Papel, documento: DocumentoTexto) -> None:
    assinatura = Assinatura.objects.create(
        vinculo=servidor.get_user().get_vinculo(),
        cpf=servidor.pessoa_fisica.cpf,
        nome_papel=papel.detalhamento,
        papel=papel,
        hmac=f'hmac-{documento.pk}',
    )
    AssinaturaDocumentoTexto.objects.create(documento=documento, assinatura=assinatura)


def _criador(autor: User, documento: Callable[[int], object]) -> Criar:
    def criar(quantidade: int) -> None:
        tl.context.user = autor  # CurrentUserField dos vínculos com processo, revisões e compartilhamentos.
        for i in range(quantidade):
            documento(i)
        tl.context.user = None

    return criar


def _caso_interessado_no_processo(servidor: Servidor) -> tuple[str, Criar]:
    """Restritos de outro setor que o servidor lê só por ser interessado no processo em que estão."""
    setor, autor = _setor_e_autor()
    processo = _processo(setor, autor, interessado=servidor.get_user())

    def documento(i: int) -> None:
        doc = DocumentoTextoFactory(usuario_criacao=autor, setor_dono=setor, nivel_acesso=RESTRITO, status=SITUACOES[i % len(SITUACOES)])
        _no_processo(processo, doc)

    return '', _criador(autor, documento)


def _caso_cargo(grupo: str) -> Caso:
    def caso(servidor: Servidor) -> tuple[str, Criar]:
        """Restritos de outro setor que o auditor ou o procurador leem pelo cargo."""
        _entrar_em(servidor.get_user(), grupo)
        setor, autor = _setor_e_autor()
        situacoes = (FINALIZADO, DocumentoStatus.STATUS_ASSINADO, CANCELADO)

        def documento(i: int) -> None:
            DocumentoTextoFactory(usuario_criacao=autor, setor_dono=setor, nivel_acesso=RESTRITO, status=situacoes[i % len(situacoes)])

        return '', _criador(autor, documento)

    return caso


def _caso_revisor(servidor: Servidor) -> tuple[str, Criar]:
    """Restritos de outro setor em revisão pelo servidor, que não os lê."""
    setor, autor = _setor_e_autor()

    def documento(i: int) -> None:
        doc = DocumentoTextoFactory(usuario_criacao=autor, setor_dono=setor, nivel_acesso=RESTRITO, status=CONCLUIDO)
        SolicitacaoRevisao.objects.create(documento=doc, revisor=servidor.get_user().get_vinculo())

    return DashboardFilter.DOCUMENTOS_ESPERANDO_REVISAO, _criador(autor, documento)


def _caso_solicitado(pessoal: bool) -> Caso:
    def caso(servidor: Servidor) -> tuple[str, Criar]:
        """Documentos esperando a assinatura do servidor, que tem papel ativo: restritos de outro setor, ou pessoais de outro."""
        PapelFactory(servidor=servidor)
        setor, autor = _setor_e_autor()

        def documento(i: int) -> None:
            doc = DocumentoTextoFactory(usuario_criacao=autor, setor_dono=None if pessoal else setor, nivel_acesso=RESTRITO, status=AGUARDANDO)
            SolicitacaoAssinaturaFactory(documento=doc, solicitante=autor, solicitado=servidor.get_user().get_vinculo())

        return DashboardFilter.DOCUMENTOS_ESPERANDO_ASSINATURA, _criador(autor, documento)

    return caso


def _caso_pessoal_assinado(servidor: Servidor) -> tuple[str, Criar]:
    """Documentos pessoais de outro, assinados pelo servidor."""
    papel = PapelFactory(servidor=servidor)
    _, autor = _setor_e_autor()

    def documento(i: int) -> None:
        _assinar(servidor, papel, DocumentoTextoFactory(usuario_criacao=autor, status=FINALIZADO))

    return DashboardFilter.DOCUMENTOS_ASSINADOS_POR_MIM, _criador(autor, documento)


def _caso_pessoal_solicitante(servidor: Servidor) -> tuple[str, Criar]:
    """Documentos pessoais do servidor, com a assinatura que ele solicitou a outro."""
    user = servidor.get_user()
    outro = ServidorFactory().get_user().get_vinculo()

    def documento(i: int) -> None:
        doc = DocumentoTextoFactory(usuario_criacao=user, status=AGUARDANDO)
        SolicitacaoAssinaturaFactory(documento=doc, solicitante=user, solicitado=outro)

    return DashboardFilter.SOLICITACOES_ASSINATURA, _criador(user, documento)


CASOS: dict[str, Caso] = {
    'interessado_no_processo': _caso_interessado_no_processo,
    'auditor': _caso_cargo('Auditor'),
    'procurador': _caso_cargo('Procurador'),
    'revisor': _caso_revisor,
    'solicitado': _caso_solicitado(pessoal=False),
    'pessoal_solicitado': _caso_solicitado(pessoal=True),
    'pessoal_assinado': _caso_pessoal_assinado,
    'pessoal_solicitante': _caso_pessoal_solicitante,
}


@pytest.mark.parametrize('caso', CASOS)
def test_listagem_nao_checa_permissao_linha_a_linha_nos_demais_perfis(client: Client, sync_permissions: None, caso: str) -> None:
    """Via processo, por cargo, em revisão, esperando assinatura e pessoais: nenhuma consulta por linha (#17722)."""
    # Chefe de um setor com processos, que tem lá uma juntada pendente, com a procuradoria e a leitura sistêmica
    # configuradas: nas linhas que ele não lê de outro jeito, todas as checagens via processo e por cargo rodam.
    servidor = ServidorFactory(setor=_setor_siorg())
    user = servidor.get_user()
    _, autor = _setor_e_autor()
    tl.context.user = autor
    CompartilhamentoPoderChefeFactory(setor_dono=servidor.setor, vinculo_permitido=user.get_vinculo())
    # O anexo da juntada é pessoal: fica fora de todas as listagens, mas cada linha percorre a juntada.
    anexo = DocumentoTextoFactory(usuario_criacao=autor, nivel_acesso=RESTRITO, status=FINALIZADO)
    _juntada_pendente(_processo(servidor.setor, autor), anexo, autor)
    tl.context.user = None
    _configurar(ModeloDocumentoFactory(), _setor_siorg())
    opcao, criar = CASOS[caso](servidor)
    # Setores de trâmite e configurações ficam em cache.
    cache.clear()
    client.force_login(user)

    criar(2)
    # A 1ª requisição paga custos únicos da sessão (grupos, preferências, notificações) e, já com linhas, os setores de
    # trâmite do usuário, guardados em cache na 1ª checagem via processo: fica fora da comparação.
    _consultas(client, opcao)
    documentos, com_dois = _consultas(client, opcao)
    assert len(documentos) == 2
    criar(4)
    documentos, com_seis = _consultas(client, opcao)
    assert len(documentos) == 6

    assert com_seis - com_dois <= 2, f'{com_dois} consultas com 2 documentos, {com_seis} com 6'


# Por perfil, documentos que ele lê e que não lê: as âncoras de que cada ramo é exercitado.
ANCORAS = {
    'interessado': (
        {'no processo que autoriza', 'público cancelado removido do processo que autoriza', 'no processo privado'},
        {'removido do processo que autoriza', 'no processo que não autoriza', 'público cancelado no processo privado', 'com juntada pendente'},
    ),
    'chefe': (
        {'no processo que autoriza', 'com juntada pendente', 'do meu setor', 'no processo privado'},
        {'removido do processo que autoriza', 'no processo que não autoriza', 'público cancelado no processo privado'},
    ),
    'auditor': (
        {'removido do processo que autoriza', 'no processo que não autoriza', 'da procuradoria', 'público cancelado no processo privado'},
        {'do meu setor', 'rascunho', 'em revisão', 'esperando minha assinatura'},
    ),
    'procurador': ({'do meu setor', 'no processo que não autoriza', 'público cancelado no processo privado'}, {'da procuradoria', 'rascunho'}),
    'sistemico': ({'sistêmico', 'no processo privado'}, {'no processo que não autoriza', 'com juntada pendente'}),
}


@pytest.mark.parametrize('perfil', ANCORAS)
def test_colunas_da_listagem_seguem_as_permissoes_nos_demais_perfis(client: Client, sync_permissions: None, perfil: str) -> None:
    """Caracterização (#17722): o assunto e os ícones de cada linha são os que as permissões dão consultadas fora da
    listagem. A opção 10 (vinculados a mim) lista inclusive os documentos de setor que o perfil não lê; as opções 4, 5, 6
    e 8, os em revisão, os esperando assinatura e os pessoais."""
    meu_setor, outro_setor, procuradoria = _setor_siorg(), _setor_siorg(), _setor_siorg()
    servidor = ServidorFactory(setor=meu_setor)
    papel = PapelFactory(servidor=servidor)
    user = servidor.get_user()
    vinculo = user.get_vinculo()
    autor = ServidorFactory(setor=outro_setor).get_user()
    outro = ServidorFactory().get_user().get_vinculo()
    modelo_sistemico = ModeloDocumentoFactory()
    _configurar(modelo_sistemico, procuradoria)
    _entrar_em(user, *{'auditor': ['Auditor'], 'procurador': ['Procurador'], 'sistemico': [GRUPO_SISTEMICO]}.get(perfil, []))
    tl.context.user = autor
    if perfil == 'chefe':
        CompartilhamentoPoderChefeFactory(setor_dono=meu_setor, vinculo_permitido=vinculo)
    # O processo que autoriza: o servidor é interessado nele ou, se chefe, ele está no setor dele.
    autoriza = _processo(meu_setor if perfil == 'chefe' else outro_setor, autor, interessado=user if perfil == 'interessado' else None)
    nao_autoriza = _processo(outro_setor, autor)
    privado = _processo(outro_setor, user, interessado=autor, nivel=Processo.NIVEL_ACESSO_PRIVADO)

    def doc(assunto: str, status: int = FINALIZADO, setor: Setor | None = outro_setor, nivel: int = RESTRITO, **kwargs: object) -> DocumentoTexto:
        documento = DocumentoTextoFactory(usuario_criacao=autor, setor_dono=setor, nivel_acesso=nivel, status=status, assunto=assunto, **kwargs)
        if setor:
            documento.interessados.add(vinculo)  # opção 10; ser interessado no documento não dá leitura
        return documento

    def solicitar(documento: DocumentoTexto, solicitado: Vinculo = vinculo, **kwargs: object) -> SolicitacaoAssinatura:
        return SolicitacaoAssinaturaFactory(documento=documento, solicitante=documento.usuario_criacao, solicitado=solicitado, **kwargs)

    def compartilhar(documento: DocumentoTexto, nivel: int) -> None:
        CompartilhamentoDocumentoPessoa.objects.create(documento=documento, vinculo_permitido=vinculo, nivel_permissao=nivel)

    _no_processo(autoriza, doc('no processo que autoriza'))
    _no_processo(autoriza, doc('removido do processo que autoriza'), removido=True)
    _no_processo(autoriza, doc('público cancelado removido do processo que autoriza', CANCELADO, nivel=PUBLICO), removido=True)
    _no_processo(nao_autoriza, doc('no processo que não autoriza'))
    _no_processo(privado, doc('no processo privado'))
    _no_processo(privado, doc('público cancelado no processo privado', CANCELADO, nivel=PUBLICO))
    doc('do meu setor', setor=meu_setor)
    doc('da procuradoria', setor=procuradoria)
    doc('rascunho', DocumentoStatus.STATUS_RASCUNHO)
    doc('sistêmico', modelo=modelo_sistemico)
    _juntada_pendente(_processo(meu_setor, autor), doc('com juntada pendente'), autor)
    SolicitacaoRevisao.objects.create(documento=doc('em revisão', CONCLUIDO), revisor=vinculo)
    solicitar(doc('esperando minha assinatura', AGUARDANDO))
    # Pendente de mim, mas condicionada a uma deferida e a uma pendente de outro: não assino ainda (opção 4).
    condicionada = doc('esperando outra assinatura', AGUARDANDO)
    solicitar(condicionada).condicionantes.add(
        solicitar(condicionada, outro, status=SolicitacaoStatus.STATUS_DEFERIDA), solicitar(condicionada, outro)
    )
    # Pessoais (opções 4, 5 e 8).
    for nivel, assunto in ((NivelPermissao.EDITAR, 'pessoal compartilhado para edição'), (NivelPermissao.LER, 'pessoal compartilhado para leitura')):
        pessoal = doc(assunto, AGUARDANDO, setor=None)
        solicitar(pessoal)
        compartilhar(pessoal, nivel)
    _assinar(servidor, papel, doc('pessoal assinado por mim', setor=None))
    assinado_compartilhado = doc('pessoal assinado e compartilhado', setor=None)
    _assinar(servidor, papel, assinado_compartilhado)
    compartilhar(assinado_compartilhado, NivelPermissao.LER)
    meu = DocumentoTextoFactory(usuario_criacao=user, nivel_acesso=RESTRITO, status=AGUARDANDO, assunto='meu pessoal')
    solicitar(meu, outro)
    tl.context.user = None
    # Setores de trâmite e configurações ficam em cache; aqui o cenário já está completo.
    cache.clear()
    client.force_login(user)

    opcoes = (
        '',
        DashboardFilter.DOCUMENTOS_ESPERANDO_ASSINATURA,
        DashboardFilter.DOCUMENTOS_ASSINADOS_POR_MIM,
        DashboardFilter.DOCUMENTOS_ESPERANDO_REVISAO,
        DashboardFilter.SOLICITACOES_ASSINATURA,
        DashboardFilter.VINCULADOS_A_MIM,
    )
    linhas = _linhas_conferidas(client, user, opcoes)

    # Todo documento do cenário aparece em alguma listagem, e cada coluna nos dois sentidos.
    assert {documento.assunto for documento, *_ in linhas} >= {*ANCORAS['interessado'][0], *ANCORAS['auditor'][0], 'meu pessoal'}
    assert {pode_ler for *_, pode_ler, _ in linhas} == {True, False}
    assert {pode_editar for *_, pode_editar in linhas} == {True, False}
    lidos = {documento.assunto for documento, _, pode_ler, _ in linhas if pode_ler}
    le, nao_le = ANCORAS[perfil]
    assert le <= lidos, le - lidos
    assert not nao_le & lidos, nao_le & lidos
