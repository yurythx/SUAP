"""Gera, no build, as capturas usadas em ``documento_eletronico/docs/usuario.md``."""

from __future__ import annotations

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

CLASSIFICACOES = '/admin/documento_eletronico/classificacao/'
TIPOS_INTERNOS = '/admin/documento_eletronico/tipodocumentotexto/'
TIPOS_EXTERNOS = '/admin/documento_eletronico/tipodocumento/'
TIPOS_VINCULO = '/admin/documento_eletronico/tipovinculodocumento/'
TIPOS_CONFERENCIA = '/admin/documento_eletronico/tipoconferencia/'
HIPOTESES = '/admin/documento_eletronico/hipoteselegal/'
MODELOS = '/admin/documento_eletronico/modelodocumento/'


def _sufixo() -> str:
    """Evita colisão quando o banco do job é reutilizado."""
    return uuid4().hex[:8]


def test_dashboard_documentos(logado_documento, capturar) -> None:
    """Captura o painel inicial do módulo."""
    tela = Tela(logado_documento('gerente')).ir('/documento_eletronico/dashboard/')
    tela.ver_titulo('Dashboard: Documentos Eletrônicos')
    anotar_tela('dashboard', tela)
    capturar(tela.pagina, 'smoke-dashboard')


def test_cadastro_classificacao(logado_documento, capturar) -> None:
    """Captura lista, formulário e resultado de classificação."""
    sufixo = _sufixo()
    codigo, descricao = f'9{sufixo[:5]}', f'Outros doc {sufixo}'
    tela = Tela(logado_documento('gerente')).ir(CLASSIFICACOES)
    tela.ver_botao('Adicionar Classificação')
    anotar_tela('classificacao-lista', tela)
    capturar(tela.pagina, 'classificacao-lista')
    tela.clicar_botao('Adicionar Classificação').ver_titulo('Adicionar Classificação')
    anotar_tela('classificacao-formulario', tela)
    capturar(tela.pagina, 'classificacao-formulario')
    tela.preencher_formulario(
        [
            ('Código', 'texto', codigo),
            ('Descrição', 'textarea', descricao),
            ('Suficiente para classificar um processo?', 'checkbox', 'marcar'),
            ('Ativo', 'checkbox', 'marcar'),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    anotar_tela('classificacao-salvo', tela)
    capturar(tela.pagina, 'classificacao-salvo')


def test_cadastro_tipo_interno(logado_documento, capturar) -> None:
    """Captura o cadastro de tipo de documento interno."""
    sufixo = _sufixo()
    nome, sigla = f'Documento Interno doc {sufixo}', f'DI{sufixo[:5].upper()}'
    tela = Tela(logado_documento('gerente')).ir(TIPOS_INTERNOS)
    tela.ver_botao('Adicionar Tipo de Documento Interno')
    anotar_tela('tipo-interno-lista', tela)
    capturar(tela.pagina, 'tipo-interno-lista')
    tela.clicar_botao('Adicionar Tipo de Documento Interno').ver_titulo('Adicionar Tipo de Documento Interno')
    anotar_tela('tipo-interno-formulario', tela)
    capturar(tela.pagina, 'tipo-interno-formulario')
    tela.preencher_formulario(
        [('Descrição', 'texto', nome), ('Sigla', 'texto', sigla), ('Ativo', 'checkbox', 'marcar'), ('Cabecalho padrao', 'texto rico', 'IFRN')]
    ).esperar().clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    anotar_tela('tipo-interno-salvo', tela)
    capturar(tela.pagina, 'tipo-interno-salvo')


def test_clonar_tipo_interno(logado_documento, capturar, documento_seed) -> None:
    """Clona um tipo interno a partir da ação disponível na listagem."""
    tela = Tela(logado_documento('gerente')).ir(TIPOS_INTERNOS)
    tela.linha('Memorando').clicar_botao('Clonar')
    tela.sucesso('Tipo de Documento clonado com sucesso.')
    anotar_tela('tipo-interno-clonado', tela)
    capturar(tela.pagina, 'tipo-interno-clonado')


def test_cadastro_tipo_externo(logado_documento, capturar) -> None:
    """Captura o cadastro de tipo de documento externo."""
    sufixo = _sufixo()
    nome, sigla = f'Documento Externo doc {sufixo}', f'DE{sufixo[:5].upper()}'
    tela = Tela(logado_documento('gerente')).ir(TIPOS_EXTERNOS)
    tela.ver_botao('Adicionar Tipo de Documento Externo')
    anotar_tela('tipo-externo-lista', tela)
    capturar(tela.pagina, 'tipo-externo-lista')
    tela.clicar_botao('Adicionar Tipo de Documento Externo').ver_titulo('Adicionar Tipo de Documento Externo')
    anotar_tela('tipo-externo-formulario', tela)
    capturar(tela.pagina, 'tipo-externo-formulario')
    tela.preencher_formulario([('Descrição', 'texto', nome), ('Sigla', 'texto', sigla), ('Ativo', 'checkbox', 'marcar')]).clicar_botao(
        'Salvar'
    ).sucesso('Cadastro realizado com sucesso.')
    anotar_tela('tipo-externo-salvo', tela)
    capturar(tela.pagina, 'tipo-externo-salvo')


def test_cadastro_tipo_vinculo(logado_documento, capturar) -> None:
    """Captura o cadastro de tipo de vínculo documental."""
    sufixo = _sufixo()
    tela = Tela(logado_documento('gerente')).ir(TIPOS_VINCULO)
    tela.ver_botao('Adicionar Tipo de Vínculo de Documento')
    anotar_tela('tipo-vinculo-lista', tela)
    capturar(tela.pagina, 'tipo-vinculo-lista')
    tela.clicar_botao('Adicionar Tipo de Vínculo de Documento').ver_titulo('Adicionar Tipo de Vínculo de Documento')
    anotar_tela('tipo-vinculo-formulario', tela)
    capturar(tela.pagina, 'tipo-vinculo-formulario')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', f'Prorrogação doc {sufixo}'),
            ('Descrição na Voz Ativa', 'texto', f'prorroga o(a) {sufixo}'),
            ('Descrição na Voz Passiva', 'texto', f'foi prorrogado pelo(a) {sufixo}'),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    anotar_tela('tipo-vinculo-salvo', tela)
    capturar(tela.pagina, 'tipo-vinculo-salvo')


def test_cadastro_tipo_conferencia(logado_documento, capturar) -> None:
    """Captura o cadastro da forma de conferência."""
    tela = Tela(logado_documento('gerente')).ir(TIPOS_CONFERENCIA)
    tela.ver_botao('Adicionar Tipo de Conferência')
    anotar_tela('tipo-conferencia-lista', tela)
    capturar(tela.pagina, 'tipo-conferencia-lista')
    tela.clicar_botao('Adicionar Tipo de Conferência').ver_titulo('Adicionar Tipo de Conferência')
    anotar_tela('tipo-conferencia-formulario', tela)
    capturar(tela.pagina, 'tipo-conferencia-formulario')
    tela.preencher_formulario([('Descrição', 'texto', f'Outra conferência doc {_sufixo()}')]).clicar_botao('Salvar').sucesso(
        'Cadastro realizado com sucesso.'
    )
    anotar_tela('tipo-conferencia-salvo', tela)
    capturar(tela.pagina, 'tipo-conferencia-salvo')


def test_cadastro_hipotese_legal(logado_documento, capturar) -> None:
    """Captura hipótese legal sigilosa e sua repetição para acesso restrito."""
    sufixo = _sufixo()
    tela = Tela(logado_documento('gerente')).ir(HIPOTESES)
    tela.ver_botao('Adicionar Hipótese Legal')
    anotar_tela('hipotese-legal-lista', tela)
    capturar(tela.pagina, 'hipotese-legal-lista')
    tela.clicar_botao('Adicionar Hipótese Legal').ver_titulo('Adicionar Hipótese Legal')
    anotar_tela('hipotese-legal-formulario', tela)
    capturar(tela.pagina, 'hipotese-legal-formulario')
    tela.preencher_formulario(
        [('Nível de Acesso', 'lista', 'Sigiloso'), ('Descrição', 'texto', f'Outra hipótese doc {sufixo}'), ('Base Legal', 'texto', 'Art. 26 da Lei')]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    anotar_tela('hipotese-legal-salvo', tela)
    capturar(tela.pagina, 'hipotese-legal-salvo')


def test_cadastro_modelo_documento(logado_documento, capturar) -> None:
    """Captura modelo interno com permissões de acesso configuráveis."""
    tela = Tela(logado_documento('gerente')).ir(MODELOS)
    tela.ver_botao('Adicionar Modelo de Documento')
    anotar_tela('modelo-lista', tela)
    capturar(tela.pagina, 'modelo-lista')
    tela.clicar_botao('Adicionar Modelo de Documento').ver_titulo('Adicionar Modelo de Documento')
    anotar_tela('modelo-formulario', tela)
    capturar(tela.pagina, 'modelo-formulario')
    tela.preencher_formulario(
        [
            ('Tipo do Documento', 'autocomplete', 'Ofício'),
            ('Descrição', 'texto', f'Outro modelo doc {_sufixo()}'),
            ('Sigiloso?', 'checkbox', 'marcar'),
            ('Restrito?', 'checkbox', 'marcar'),
            ('Público?', 'checkbox', 'marcar'),
            ('Nível de Acesso Padrão', 'lista', 'Público'),
            ('Ativo', 'checkbox', 'marcar'),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    anotar_tela('modelo-salvo', tela)
    capturar(tela.pagina, 'modelo-salvo')
