"""Cadastros gerais do Documento Eletrônico (modo 2)."""

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

CLASSIFICACOES = '/admin/documento_eletronico/classificacao/'
TIPOS_INTERNOS = '/admin/documento_eletronico/tipodocumentotexto/'
TIPOS_EXTERNOS = '/admin/documento_eletronico/tipodocumento/'
TIPOS_VINCULO = '/admin/documento_eletronico/tipovinculodocumento/'
TIPOS_CONFERENCIA = '/admin/documento_eletronico/tipoconferencia/'
HIPOTESES = '/admin/documento_eletronico/hipoteselegal/'
MODELOS = '/admin/documento_eletronico/modelodocumento/'


def _sufixo() -> str:
    """Gera identificadores únicos para permitir ``--reuse-db``."""
    return uuid4().hex[:8]


def test_cadastrar_classificacao(logado_documento):
    """Cadastra uma classificação ativa e suficiente para classificar processos."""
    tela = Tela(logado_documento('gerente'))
    sufixo = _sufixo()
    codigo = f'9{sufixo[:5]}'
    descricao = f'Outros E2E {sufixo}'

    tela.ir(CLASSIFICACOES).clicar_botao('Adicionar Classificação').preencher_formulario(
        [
            ('Código', 'texto', codigo),
            ('Descrição', 'textarea', descricao),
            ('Suficiente para classificar um processo?', 'checkbox', 'marcar'),
            ('Ativo', 'checkbox', 'marcar'),
            ('Migrado', 'checkbox', 'marcar'),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    from documento_eletronico.models import Classificacao

    classificacao = Classificacao.objects.get(codigo=codigo)
    assert classificacao.descricao == descricao
    assert classificacao.ativo
    assert classificacao.migrado
    assert classificacao.suficiente_para_classificar_processo


def test_cadastrar_e_clonar_tipo_de_documento_interno(logado_documento):
    """Cadastra um tipo interno com cabeçalho rico e verifica sua clonagem."""
    tela = Tela(logado_documento('gerente'))
    sufixo = _sufixo()
    nome = f'Documento Interno E2E {sufixo}'
    sigla = f'DI{sufixo[:5].upper()}'

    tela.ir(TIPOS_INTERNOS).clicar_botao('Adicionar Tipo de Documento Interno').preencher_formulario(
        [
            ('Descrição', 'texto', nome),
            ('Sigla', 'texto', sigla),
            ('Ativo', 'checkbox', 'marcar'),
            ('Cabecalho padrao', 'texto rico', 'IFRN'),
        ]
    ).esperar().clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    from documento_eletronico.models import TipoDocumentoTexto

    tipo = TipoDocumentoTexto.objects.get(nome=nome)
    assert tipo.sigla == sigla
    assert tipo.ativo
    assert 'IFRN' in tipo.cabecalho_padrao

    linha = tela.ir(TIPOS_INTERNOS).linha(nome)
    linha.clicar_botao('Clonar')

    clone = TipoDocumentoTexto.objects.filter(nome__startswith=f'Clone de {nome}').first()
    assert clone is not None, 'a UI acionou a clonagem, mas o tipo clonado não foi persistido'
    assert clone.cabecalho_padrao == tipo.cabecalho_padrao


def test_cadastrar_tipo_de_documento_externo(logado_documento):
    """Cadastra o tipo de documento externo usado por documentos digitalizados."""
    tela = Tela(logado_documento('gerente'))
    sufixo = _sufixo()
    nome = f'Documento Externo E2E {sufixo}'
    sigla = f'DE{sufixo[:5].upper()}'

    tela.ir(TIPOS_EXTERNOS).clicar_botao('Adicionar Tipo de Documento Externo').preencher_formulario(
        [('Descrição', 'texto', nome), ('Sigla', 'texto', sigla), ('Ativo', 'checkbox', 'marcar')]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    from documento_eletronico.models import TipoDocumento

    tipo = TipoDocumento.objects.get(nome=nome)
    assert tipo.sigla == sigla
    assert tipo.ativo


def test_cadastrar_tipo_de_vinculo_de_documento(logado_documento):
    """Cadastra as frases ativa e passiva que descrevem um vínculo documental."""
    tela = Tela(logado_documento('gerente'))
    sufixo = _sufixo()
    descricao = f'Prorrogação E2E {sufixo}'
    ativa = f'prorroga o(a) {sufixo}'
    passiva = f'foi prorrogado pelo(a) {sufixo}'

    tela.ir(TIPOS_VINCULO).clicar_botao('Adicionar Tipo de Vínculo de Documento').preencher_formulario(
        [('Descrição', 'texto', descricao), ('Descrição na Voz Ativa', 'texto', ativa), ('Descrição na Voz Passiva', 'texto', passiva)]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    from documento_eletronico.models import TipoVinculoDocumento

    vinculo = TipoVinculoDocumento.objects.get(descricao=descricao)
    assert vinculo.descricao_voz_ativa == ativa.lower()
    assert vinculo.descricao_voz_passiva == passiva.lower()


def test_cadastrar_tipo_de_conferencia(logado_documento):
    """Cadastra a descrição da forma de conferência de um documento externo."""
    tela = Tela(logado_documento('gerente'))
    descricao = f'Outro E2E {_sufixo()}'

    tela.ir(TIPOS_CONFERENCIA).clicar_botao('Adicionar Tipo de Conferência').preencher_formulario([('Descrição', 'texto', descricao)]).clicar_botao(
        'Salvar'
    ).sucesso('Cadastro realizado com sucesso.')

    from documento_eletronico.models import TipoConferencia

    assert TipoConferencia.objects.filter(descricao=descricao).exists()


def test_cadastrar_hipoteses_legais(logado_documento):
    """Cadastra hipóteses legais para níveis sigiloso e restrito."""
    tela = Tela(logado_documento('gerente'))
    sufixo = _sufixo()
    sigiloso = f'Outro E2E {sufixo}'
    restrito = f'Auditoria Interna E2E {sufixo}'
    base_sigiloso = f'Art. 26 § 5º, da Lei no 10.180/2001 {sufixo}'
    base_restrito = f'Art. 15 § 4º, da Lei no 9.960/2001 {sufixo}'

    tela.ir(HIPOTESES).clicar_botao('Adicionar Hipótese Legal').preencher_formulario(
        [('Nível de Acesso', 'lista', 'Sigiloso'), ('Descrição', 'texto', sigiloso), ('Base Legal', 'texto', base_sigiloso)]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    tela.ir(HIPOTESES).clicar_botao('Adicionar Hipótese Legal').preencher_formulario(
        [('Nível de Acesso', 'lista', 'Restrito'), ('Descrição', 'texto', restrito), ('Base Legal', 'texto', base_restrito)]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    from documento_eletronico.models import HipoteseLegal, NivelAcesso

    assert HipoteseLegal.objects.filter(descricao=sigiloso, nivel_acesso=NivelAcesso.SIGILOSO.name, base_legal=base_sigiloso).exists()
    assert HipoteseLegal.objects.filter(descricao=restrito, nivel_acesso=NivelAcesso.RESTRITO.name, base_legal=base_restrito).exists()


def test_cadastrar_modelo_de_documento(logado_documento):
    """Cadastra modelo interno com os três níveis de acesso permitidos."""
    tela = Tela(logado_documento('gerente'))
    descricao = f'Outro E2E {_sufixo()}'

    tela.ir(MODELOS).clicar_botao('Adicionar Modelo de Documento').preencher_formulario(
        [
            ('Tipo do Documento', 'autocomplete', 'Ofício'),
            ('Descrição', 'texto', descricao),
            ('Sigiloso?', 'checkbox', 'marcar'),
            ('Restrito?', 'checkbox', 'marcar'),
            ('Público?', 'checkbox', 'marcar'),
            ('Nível de Acesso Padrão', 'lista', 'Público'),
            ('Ativo', 'checkbox', 'marcar'),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    from documento_eletronico.models import Documento, ModeloDocumento

    modelo = ModeloDocumento.objects.get(nome=descricao)
    assert modelo.tipo_documento_texto.nome == 'Ofício'
    assert modelo.permite_nivel_acesso_sigiloso
    assert modelo.permite_nivel_acesso_restrito
    assert modelo.permite_nivel_acesso_publico
    assert modelo.nivel_acesso_padrao == Documento.NIVEL_ACESSO_PUBLICO
    assert modelo.ativo
