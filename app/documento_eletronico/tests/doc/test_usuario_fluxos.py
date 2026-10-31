"""Fluxos documentais que geram as capturas do manual de usuário."""

from __future__ import annotations

from uuid import uuid4

import pytest

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DOCUMENTOS = '/admin/documento_eletronico/documentotexto/'
PERMISSOES = '/processo_eletronico/permissoes/'
MEMO = 'MEMO 1/2020 - DIDE/CEN/RAIZ'


def _sufixo() -> str:
    return uuid4().hex[:8]


def _capturar(tela: Tela, capturar, slug: str) -> None:
    anotar_tela(slug, tela)
    capturar(tela.pagina, slug)


def _senha(tela: Tela) -> Tela:
    tela.raiz.locator('input[type="password"]').first.fill(SENHA_E2E)
    return tela


def _selecionar_autocomplete(tela: Tela, campo: str, valor: str) -> None:
    """Seleciona uma pessoa no select2 da tela transversal de permissões."""
    widget = tela.pagina.locator(f'select[name="{campo}"] + span.select2 .select2-selection').first
    busca = widget.locator('input.select2-search__field')
    busca.click(force=True)
    tela.pagina.locator('span.select2-container--open').first.wait_for(state='visible')
    busca.fill(valor)
    tela.pagina.locator('.select2-results__option.loading-results').wait_for(state='detached')
    tela.pagina.locator('span.select2-container--open li.select2-results__option', has_text=valor).first.click()


def _criar_documento(tela: Tela, assunto: str) -> int:
    tela.ir(DOCUMENTOS).clicar_botao('Adicionar Documento de Texto').preencher_formulario(
        [
            ('Tipo do Documento', 'lista', 'Ofício'),
            ('Modelo', 'lista', 'Exercício provisório para acompanhamento de cônjuge'),
            ('Nível de Acesso', 'lista', 'Público'),
            ('Setor Dono', 'lista', 'DIDE/CEN'),
            ('Assunto', 'textarea', assunto),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    from documento_eletronico.models import DocumentoTexto

    return DocumentoTexto.objects.get(assunto=assunto).pk


def _abrir_documento(tela: Tela, documento_id: int) -> Tela:
    return tela.ir(f'/documento_eletronico/visualizar_documento/{documento_id}/').ver_titulo('Documento')


def _assinar(tela: Tela) -> Tela:
    return (
        tela.clicar_botao('Assinar')
        .ver_titulo('Assinatura de Documento')
        .clicar_botao('Definir identificador')
        .preencher_formulario([('Perfil', 'lista', 'Cargo A')])
    )


def _concluir_e_assinar(tela: Tela) -> Tela:
    return _senha(_assinar(tela)).clicar_botao('Assinar Documento').sucesso('Documento assinado com sucesso.')


def _finalizar_documento(tela: Tela) -> Tela:
    return tela.clicar_botao('Finalizar').sucesso('Documento finalizado com sucesso.')


def _abrir_para_clonagem(logado_documento, documento_id: int) -> Tela:
    """Concede ao gerente a assinatura pendente e abre o documento para clonagem."""
    tela = _abrir_documento(Tela(logado_documento('chefe')), documento_id)
    tela.raiz.locator('ul.action-bar a:visible').filter(has_text='Solicitar').first.click()
    tela.clicar_botao('Assinatura').preencher_formulario([('Pessoa', 'autocomplete', 'Servidor Documento Gerente S')]).clicar_botao(
        'Enviar solicitações'
    ).sucesso('Sua solicitação foi enviada com sucesso.')
    return _abrir_documento(Tela(logado_documento('gerente')), documento_id)


def test_definir_permissoes(logado_documento, capturar) -> None:
    """Configura, pela aba do módulo, quem pode operar e ler documentos do setor."""
    tela = Tela(logado_documento('chefe')).ir(PERMISSOES)
    tela.raiz.locator('a.nav-link', has_text='Documentos Eletrônicos').click()
    tela.esperar().ver_titulo('Permissões para Documentos e Processos Eletrônicos')
    _capturar(tela, capturar, 'permissoes-formulario')
    _selecionar_autocomplete(tela, 'pessoas_permitidas_podem_escrever', 'Servidor Documento Operador')
    _selecionar_autocomplete(tela, 'pessoas_permitidas_podem_ler', 'Servidor Documento Leitor')
    tela.clicar_botao('Enviar').sucesso('Operação realizada com sucesso.')
    _capturar(tela, capturar, 'permissoes-salvo')


def test_cadastrar_documento(logado_documento, capturar) -> None:
    """Cadastra um documento textual e captura a tela de consulta."""
    tela = Tela(logado_documento('chefe')).ir(DOCUMENTOS)
    _capturar(tela, capturar, 'cadastrar-documento-lista')
    tela.clicar_botao('Adicionar Documento de Texto').ver_titulo('Adicionar Documento de Texto')
    _capturar(tela, capturar, 'cadastrar-documento-formulario')
    documento_id = _criar_documento(tela, f'Documento doc {_sufixo()}')
    _capturar(_abrir_documento(tela, documento_id), capturar, 'cadastrar-documento-salvo')


def test_editar_conteudo(logado_documento, capturar) -> None:
    """Abre o editor textual, salva o conteúdo e captura cada tela do fluxo."""
    tela = Tela(logado_documento('chefe'))
    documento_id = _criar_documento(tela, f'Conteúdo doc {_sufixo()}')
    _capturar(_abrir_documento(tela, documento_id), capturar, 'editar-conteudo-documento')
    tela.clicar_botao('Editar').clicar_botao('Texto').ver_titulo('Editar Documento')
    _capturar(tela, capturar, 'editar-conteudo-formulario')
    tela.clicar_botao('Salvar e Visualizar').sucesso('Edição realizada com sucesso.')
    _capturar(tela, capturar, 'editar-conteudo-salvo')


def test_concluir_documento(logado_documento, capturar) -> None:
    """Conclui um documento em rascunho."""
    tela = Tela(logado_documento('chefe'))
    documento_id = _criar_documento(tela, f'Conclusão doc {_sufixo()}')
    _capturar(_abrir_documento(tela, documento_id), capturar, 'concluir-documento-rascunho')
    tela.clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    _capturar(tela, capturar, 'concluir-documento-concluido')


def test_retornar_para_rascunho(logado_documento, capturar) -> None:
    """Retorna um documento concluído para edição e o conclui novamente."""
    tela = Tela(logado_documento('chefe'))
    documento_id = _criar_documento(tela, f'Rascunho doc {_sufixo()}')
    _abrir_documento(tela, documento_id).clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    _capturar(tela, capturar, 'retornar-rascunho-concluido')
    tela.clicar_botao('Ações').clicar_botao('Retornar para rascunho').sucesso('Operação realizada com sucesso.')
    _capturar(tela, capturar, 'retornar-rascunho-rascunho')
    tela.clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    _capturar(tela, capturar, 'retornar-rascunho-reconcluido')


def test_assinar_documento(logado_documento, capturar) -> None:
    """Assina um documento concluído usando o identificador e a senha."""
    tela = Tela(logado_documento('chefe'))
    documento_id = _criar_documento(tela, f'Assinatura doc {_sufixo()}')
    _abrir_documento(tela, documento_id).clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    _capturar(tela, capturar, 'assinar-documento-concluido')
    _assinar(tela)
    _capturar(tela, capturar, 'assinar-documento-formulario')
    _senha(tela).clicar_botao('Assinar Documento').sucesso('Documento assinado com sucesso.')
    _capturar(tela, capturar, 'assinar-documento-assinado')


def test_solicitar_assinatura(logado_documento, capturar, documento_seed) -> None:
    """Solicita e executa a assinatura de um documento por outro servidor."""
    from documento_eletronico.models import DocumentoTexto, SolicitacaoAssinatura

    documento = DocumentoTexto.objects.get(identificador=MEMO)
    tela = _abrir_documento(Tela(logado_documento('chefe')), documento.pk)
    _capturar(tela, capturar, 'solicitar-assinatura-documento')
    tela.raiz.locator('ul.action-bar a:visible').filter(has_text='Solicitar').first.click()
    tela.clicar_botao('Assinatura').ver_titulo('Solicitações de Assinaturas')
    _capturar(tela, capturar, 'solicitar-assinatura-formulario')
    tela.preencher_formulario([('Pessoa', 'autocomplete', 'Servidor Documento Gerente S')]).clicar_botao('Enviar solicitações').sucesso(
        'Sua solicitação foi enviada com sucesso.'
    )
    assert SolicitacaoAssinatura.objects.filter(documento=documento).exists()
    _capturar(tela, capturar, 'solicitar-assinatura-salvo')
    destinatario = _abrir_documento(Tela(logado_documento('gerente')), documento.pk)
    _capturar(destinatario, capturar, 'solicitar-assinatura-destinatario')
    destinatario.clicar_botao('Assinar').ver_titulo('Assinatura de Documento').preencher_formulario([('Perfil', 'lista', 'Cargo A')])
    _capturar(destinatario, capturar, 'solicitar-assinatura-assinatura-formulario')
    _senha(destinatario).clicar_botao('Assinar Documento').sucesso('Documento assinado com sucesso.')
    _capturar(destinatario, capturar, 'solicitar-assinatura-assinado')


def test_finalizar_documento(logado_documento, capturar, documento_seed) -> None:
    """Finaliza um documento depois de sua assinatura."""
    tela = Tela(logado_documento('chefe'))
    documento_id = _criar_documento(tela, f'Finalização doc {_sufixo()}')
    _abrir_documento(tela, documento_id).clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    _assinar(tela)
    _senha(tela).clicar_botao('Assinar Documento').sucesso('Documento assinado com sucesso.')
    _capturar(tela, capturar, 'finalizar-documento-assinado')
    _finalizar_documento(tela)
    _capturar(tela, capturar, 'finalizar-documento-finalizado')


def test_imprimir_documento(logado_documento, capturar, documento_seed) -> None:
    """Abre as versões retrato e paisagem da impressão."""
    tela = Tela(logado_documento('chefe'))
    documento_id = _criar_documento(tela, f'Impressão doc {_sufixo()}')
    _abrir_documento(tela, documento_id).clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    _assinar(tela)
    _senha(tela).clicar_botao('Assinar Documento').sucesso('Documento assinado com sucesso.')
    _finalizar_documento(tela)
    tela.clicar_botao('Ações').clicar_botao('Imprimir (Retrato)').ver_titulo('Imprimir Documento em formato PDF')
    _capturar(tela, capturar, 'imprimir-documento-retrato')
    tela.ir(f'/documento_eletronico/visualizar_documento/{documento_id}/')
    tela.clicar_botao('Ações').clicar_botao('Imprimir (Paisagem)').ver_titulo('Imprimir Documento em formato PDF')
    _capturar(tela, capturar, 'imprimir-documento-paisagem')


def test_compartilhar_documento(logado_documento, capturar, documento_seed) -> None:
    """Compartilha um documento com outro setor pelo popup de gerenciamento."""
    from documento_eletronico.models import DocumentoTexto

    documento = DocumentoTexto.objects.get(identificador=MEMO)
    tela = _abrir_documento(Tela(logado_documento('chefe')), documento.pk).clicar_botao('Compartilhar').popup()
    tela.ver_titulo('Gerenciamento de Compartilhamento de Documento')
    _capturar(tela, capturar, 'compartilhar-documento-formulario')
    tela.preencher_formulario([('Setores que podem ler', 'autocomplete multiplo', 'DIAC/CEN')]).salvar_no_popup('Enviar').sucesso(
        'Gerenciamento salvo com sucesso.'
    )
    _capturar(tela, capturar, 'compartilhar-documento-salvo')


def test_clonar_documento(logado_documento, capturar, documento_seed) -> None:
    """Clona o documento seed e informa novo assunto."""
    from documento_eletronico.models import DocumentoTexto

    documento = DocumentoTexto.objects.get(identificador=MEMO)
    tela = _abrir_para_clonagem(logado_documento, documento.pk)
    tela.clicar_botao('Ações').clicar_botao('Clonar').sucesso(
        'Para prosseguir com a clonagem edite as informações necessárias e informe o assunto do documento.'
    )
    _capturar(tela, capturar, 'clonar-documento-formulario')
    tela.preencher_formulario([('Setor Dono', 'lista', 'CEN'), ('Assunto', 'textarea', f'Clone doc {_sufixo()}')]).clicar_botao('Salvar').sucesso(
        'Documento foi clonado com sucesso.'
    )
    _capturar(tela, capturar, 'clonar-documento-salvo')


def test_vincular_documento(logado_documento, capturar, documento_seed) -> None:
    """Finaliza um documento clonado e cria o vínculo com o documento seed."""
    from documento_eletronico.models import DocumentoTexto, TipoVinculoDocumento, VinculoDocumentoTexto
    from documento_eletronico.status import DocumentoStatus

    alvo = DocumentoTexto.objects.get(identificador=MEMO)
    tela = _abrir_para_clonagem(logado_documento, alvo.pk)
    tela.clicar_botao('Ações').clicar_botao('Clonar').preencher_formulario(
        [('Setor Dono', 'lista', 'CEN'), ('Assunto', 'textarea', f'Vínculo doc {_sufixo()}')]
    ).clicar_botao('Salvar').sucesso('Documento foi clonado com sucesso.')
    base = DocumentoTexto.objects.filter(assunto__startswith='Vínculo doc').order_by('-pk').first()
    assert base is not None
    _abrir_documento(tela, base.pk).clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    _concluir_e_assinar(tela)
    _finalizar_documento(tela)
    DocumentoTexto.objects.filter(pk=alvo.pk).update(status=DocumentoStatus.STATUS_FINALIZADO)
    tipo_vinculo = TipoVinculoDocumento.objects.filter(descricao_voz_ativa__icontains='aditivo').first()
    assert tipo_vinculo is not None, 'seed sem tipo de vínculo "aditivo" para executar a tarefa'
    _abrir_documento(tela, base.pk).clicar_botao('Ações').clicar_botao('Vincular documento')
    _capturar(tela, capturar, 'vincular-documento-formulario')
    tela.preencher_formulario(
        [('Tipo de Vínculo', 'lista', tipo_vinculo.descricao_voz_ativa), ('Documento Alvo', 'autocomplete', MEMO)]
    ).clicar_botao('Salvar').sucesso('Vínculo criado com sucesso.')
    assert VinculoDocumentoTexto.objects.filter(documento_texto_base=base, documento_texto_alvo=alvo).exists()
    _capturar(tela, capturar, 'vincular-documento-salvo')
