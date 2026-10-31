"""Fluxos F002/F003: ciclo de vida e alteração de acesso de documento textual.

O teste mantém cada cadeia no mesmo contexto, como os cenários do behave faziam. Regressões
de permissão, transição de status, assinatura, finalização e mudança de nível ficam visíveis
pela UI e pela persistência.
"""

from uuid import uuid4

import pytest

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/documento_eletronico/documentotexto/'


def _preencher_senha(tela: Tela, valor: str = SENHA_E2E) -> Tela:
    """Preenche o PasswordField, cujo label não é irmão direto do input."""
    tela.raiz.locator('input[type="password"]').first.fill(valor)
    return tela


def _criar_documento(tela: Tela) -> object:
    """Cria documento novo pela tela e devolve o objeto persistido."""
    assunto = f'E2E Documento {uuid4().hex[:8]}'
    tela.ir(LISTAGEM).clicar_botao('Adicionar Documento de Texto').preencher_formulario(
        [
            ('Tipo do Documento', 'lista', 'Ofício'),
            ('Modelo', 'lista', 'Exercício provisório para acompanhamento de cônjuge'),
            ('Nível de Acesso', 'lista', 'Público'),
            ('Setor Dono', 'lista', 'DIDE/CEN'),
            ('Assunto', 'textarea', assunto),
        ]
    ).clicar_botao('Salvar')

    from documento_eletronico.models import DocumentoTexto

    return DocumentoTexto.objects.get(assunto=assunto)


CRIAR_RELACIONADO = '/documento_eletronico/criar_documento_relacionado/{}/'


def test_cria_documento_relacionado_a_partir_do_memo(logado_documento, configuracao_de_vinculo):
    """Documento relacionado: a rota só responde com configuração de vínculo ativa (views.py:534).

    O caminho é o da tela: o gerente abre o MEMO, clica em "Criar documento relacionado", escolhe a
    configuração e o modelo da PORTARIA que revoga; o SUAP cria o documento base, grava o
    ``VinculoDocumentoTexto`` e manda editar o documento novo. Sem a configuração a view é 403 —
    era o único buraco de rota do módulo.
    """
    from documento_eletronico.models import DocumentoTexto, VinculoDocumentoTexto

    memo = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    tela = Tela(logado_documento('gerente')).ir(f'/documento_eletronico/visualizar_documento/{memo.pk}/')
    tela.clicar_botao('Criar documento relacionado')
    # `ver_titulo` espera a página nova chegar; sem essa espera a leitura dos rótulos (one-shot)
    # fotografa o documento em navegação e devolve lista vazia.
    tela.ver_titulo(f'Criar documento relacionado a {memo.identificador}')
    assert tela.pagina.url.endswith(CRIAR_RELACIONADO.format(memo.pk)), f'a tela não abriu a criação de documento relacionado: {tela.pagina.url}'
    rotulos = tela.rotulos_na_tela()
    assert any(rotulo.startswith('Documento a ser criado') for rotulo in rotulos), f'formulário sem o campo de configuração. Rótulos: {rotulos}'
    assert any(rotulo.startswith('Modelo') for rotulo in rotulos), f'formulário sem o campo de modelo. Rótulos: {rotulos}'

    tela.preencher_formulario(
        [
            ('Documento a ser criado', 'lista', str(configuracao_de_vinculo)),
            ('Modelo', 'autocomplete', 'Substituição de Chefia'),
        ]
    )
    tela.clicar_botao('Enviar')
    tela.sucesso('Documento relacionado criado.')

    vinculo = VinculoDocumentoTexto.objects.filter(configuracao=configuracao_de_vinculo, documento_texto_alvo=memo).first()
    assert vinculo is not None, 'a UI disse que criou, mas o vínculo não persistiu'
    assert vinculo.documento_texto_base.assunto == f'Revogação de {memo.identificador}', 'o documento base não recebeu o assunto do vínculo'
    assert vinculo.documento_texto_base.modelo.nome == 'Substituição de Chefia', 'o documento base não usa o modelo escolhido'


def test_ciclo_de_vida_do_documento_textual(logado_documento, relogio):
    """Executa criação, edição, transições, assinatura e impressão de um documento."""
    from documento_eletronico.models import DocumentoTexto
    from documento_eletronico.status import DocumentoStatus

    tela = Tela(logado_documento('chefe'))
    documento = _criar_documento(tela)
    assert documento.status == DocumentoStatus.STATUS_RASCUNHO

    tela.ir(f'/documento_eletronico/visualizar_documento/{documento.pk}/').ver_titulo('Documento')
    tela.clicar_botao('Editar').clicar_botao('Texto').clicar_botao('Salvar e Visualizar').sucesso('Edição realizada com sucesso.')

    tela.clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    documento = DocumentoTexto.objects.get(pk=documento.pk)
    assert documento.status == DocumentoStatus.STATUS_CONCLUIDO

    tela.clicar_botao('Ações').clicar_botao('Retornar para rascunho').sucesso('Operação realizada com sucesso.')
    documento = DocumentoTexto.objects.get(pk=documento.pk)
    assert documento.status == DocumentoStatus.STATUS_RASCUNHO

    tela.clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    documento = DocumentoTexto.objects.get(pk=documento.pk)
    assert documento.status == DocumentoStatus.STATUS_CONCLUIDO

    tela.clicar_botao('Assinar').ver_titulo('Assinatura de Documento').clicar_botao('Definir identificador').preencher_formulario(
        [('Perfil', 'lista', 'Cargo A')]
    )
    _preencher_senha(tela).clicar_botao('Assinar Documento').sucesso('Documento assinado com sucesso.')
    documento = DocumentoTexto.objects.get(pk=documento.pk)
    assert documento.status == DocumentoStatus.STATUS_ASSINADO

    tela.clicar_botao('Finalizar').sucesso('Documento finalizado com sucesso.')
    documento = DocumentoTexto.objects.get(pk=documento.pk)
    assert documento.status == DocumentoStatus.STATUS_FINALIZADO

    tela.clicar_botao('Ações').clicar_botao('Imprimir (Retrato)').ver_titulo('Imprimir Documento em formato PDF')


def test_solicitar_assinatura_e_compartilhar_documento(logado_documento, documento_seed):
    """Solicita assinatura e grava compartilhamento no memorando seed do módulo."""
    from documento_eletronico.models import DocumentoTexto, SolicitacaoAssinatura

    tela = Tela(logado_documento('chefe'))
    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    tela.ir(f'/documento_eletronico/visualizar_documento/{documento.pk}/')
    tela.raiz.locator('ul.action-bar a:visible').filter(has_text='Solicitar').first.click()
    tela.clicar_botao('Assinatura')
    tela.preencher_formulario([('Pessoa', 'autocomplete', 'Servidor Documento Gerente S')]).clicar_botao('Enviar solicitações').sucesso(
        'Sua solicitação foi enviada com sucesso.'
    )
    assert SolicitacaoAssinatura.objects.filter(documento=documento).exists(), 'a UI disse que solicitou, mas não persistiu'

    tela.ir(f'/documento_eletronico/visualizar_documento/{documento.pk}/').clicar_botao('Compartilhar').popup().preencher_formulario(
        [('Setores que podem ler', 'autocomplete multiplo', 'DIAC/CEN')]
    ).salvar_no_popup('Enviar').sucesso('Gerenciamento salvo com sucesso.')


def test_clonar_e_vincular_documento(logado_documento, documento_seed):
    """Clona memorando e vincula o clone ao documento seed."""
    from documento_eletronico.models import DocumentoTexto, SolicitacaoAssinatura, TipoVinculoDocumento, VinculoDocumentoTexto
    from documento_eletronico.status import DocumentoStatus

    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    tela = Tela(logado_documento('chefe')).ir(f'/documento_eletronico/visualizar_documento/{documento.pk}/')
    tela.raiz.locator('ul.action-bar a:visible').filter(has_text='Solicitar').first.click()
    tela.clicar_botao('Assinatura').preencher_formulario([('Pessoa', 'autocomplete', 'Servidor Documento Gerente S')]).clicar_botao(
        'Enviar solicitações'
    ).sucesso('Sua solicitação foi enviada com sucesso.')
    assert SolicitacaoAssinatura.objects.filter(documento=documento).exists()

    tela = Tela(logado_documento('gerente'))
    tela.ir(f'/documento_eletronico/visualizar_documento/{documento.pk}/').clicar_botao('Ações').clicar_botao('Clonar').sucesso(
        'Para prosseguir com a clonagem edite as informações necessárias e informe o assunto do documento.'
    ).preencher_formulario([('Setor Dono', 'lista', 'CEN'), ('Assunto', 'textarea', f'Clone E2E {uuid4().hex[:8]}')]).clicar_botao('Salvar').sucesso(
        'Documento foi clonado com sucesso.'
    )
    clone = DocumentoTexto.objects.filter(assunto__startswith='Clone E2E').order_by('-pk').first()
    assert clone is not None, 'a UI disse que clonou, mas não persistiu'

    tela.ir(f'/documento_eletronico/visualizar_documento/{clone.pk}/').clicar_botao('Concluir').sucesso('Operação realizada com sucesso.')
    tela.clicar_botao('Assinar').clicar_botao('Definir identificador').preencher_formulario([('Perfil', 'lista', 'Cargo A')])
    _preencher_senha(tela).clicar_botao('Assinar Documento').sucesso('Documento assinado com sucesso.')
    tela.clicar_botao('Finalizar').sucesso('Documento finalizado com sucesso.')
    clone = DocumentoTexto.objects.get(pk=clone.pk)
    assert clone.status == DocumentoStatus.STATUS_FINALIZADO

    tipo_vinculo = TipoVinculoDocumento.objects.filter(descricao_voz_ativa__icontains='aditivo').first()
    if tipo_vinculo is None:
        pytest.skip('seed global não possui tipo de vínculo "aditivo"')
    DocumentoTexto.objects.filter(pk=documento.pk).update(status=DocumentoStatus.STATUS_FINALIZADO)
    tela.ir(f'/documento_eletronico/visualizar_documento/{clone.pk}/').clicar_botao('Ações').clicar_botao('Vincular documento').preencher_formulario(
        [('Tipo de Vínculo', 'lista', tipo_vinculo.descricao_voz_ativa), ('Documento Alvo', 'autocomplete', documento.identificador)]
    ).clicar_botao('Salvar').sucesso('Vínculo criado com sucesso.')
    assert VinculoDocumentoTexto.objects.filter(documento_texto_base=clone, documento_texto_alvo=documento).exists(), (
        'a UI disse que vinculou, mas não persistiu'
    )


def test_alterar_nivel_de_acesso(logado_documento, documento_seed):
    """Altera o nível de acesso de documento com hipótese legal e senha."""
    from documento_eletronico.models import DocumentoTexto, HipoteseLegal
    from documento_eletronico.status import DocumentoStatus

    tela = Tela(logado_documento('chefe'))
    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    DocumentoTexto.objects.filter(
        pk=documento.pk,
    ).update(status=DocumentoStatus.STATUS_FINALIZADO, nivel_acesso=DocumentoTexto.NIVEL_ACESSO_PUBLICO, hipotese_legal=None)
    hipotese = HipoteseLegal.objects.filter(nivel_acesso='SIGILOSO').first()
    if hipotese is None:
        pytest.skip('seed global não possui hipótese legal sigilosa')
    tela.ir(f'/documento_eletronico/visualizar_documento/{documento.pk}/').clicar_botao('Nível de acesso').clicar_botao('Editar nível de acesso')
    tela.preencher('Para', 'lista', 'Sigiloso')
    tela.raiz.locator('#id_hipotese_legal option').nth(1).wait_for(state='attached')
    tela.preencher('Hipótese Legal', 'lista', str(hipotese))
    _preencher_senha(tela).clicar_botao('Enviar').sucesso('Nível de Acesso alterado com sucesso.')
    documento = DocumentoTexto.objects.get(pk=documento.pk)
    assert documento.nivel_acesso == documento.NIVEL_ACESSO_SIGILOSO


def test_solicitar_e_autorizar_alteracao_de_nivel(logado_documento, documento_seed):
    """Executa solicitação e autorização de mudança de nível no fluxo de setor."""
    from documento_eletronico.models import DocumentoTexto, HipoteseLegal
    from documento_eletronico.status import DocumentoStatus

    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    DocumentoTexto.objects.filter(
        pk=documento.pk,
    ).update(status=DocumentoStatus.STATUS_FINALIZADO, nivel_acesso=DocumentoTexto.NIVEL_ACESSO_PUBLICO, hipotese_legal=None)
    tela = Tela(logado_documento('leitor'))
    hipotese = HipoteseLegal.objects.filter(nivel_acesso='RESTRITO').first()
    if hipotese is None:
        pytest.skip('seed global não possui hipótese legal restrita')
    tela.ir(f'/documento_eletronico/visualizar_documento/{documento.pk}/').clicar_botao('Nível de acesso').clicar_botao(
        'Solicitar alteração de nível de acesso'
    )
    tela.preencher('Para', 'lista', 'Restrito')
    tela.raiz.locator('#id_hipotese_legal option').nth(1).wait_for(state='attached')
    tela.raiz.locator('#id_hipotese_legal').select_option(index=1)
    _preencher_senha(tela).clicar_botao('Enviar').sucesso('Solicitação realizada com sucesso com sucesso.')

    tela = (
        Tela(logado_documento('chefe'))
        .ir(f'/documento_eletronico/visualizar_documento/{documento.pk}/')
        .clicar_botao('Nível de acesso')
        .clicar_botao('Analisar/Visualizar solicitações de alteração de nível de acesso')
        .ver_titulo('Solicitações de alteração de nível de acesso de documento')
        .clicar_botao('Deferir')
        .ver_titulo('Analisar solicitação de alteração de nível de acesso')
        .preencher_formulario([('Confirmar', 'checkbox', 'marcar')])
    )
    _preencher_senha(tela).clicar_botao('Enviar').sucesso('Nível de Acesso alterado com sucesso.')
    documento = DocumentoTexto.objects.get(pk=documento.pk)
    assert documento.nivel_acesso == documento.NIVEL_ACESSO_RESTRITO
