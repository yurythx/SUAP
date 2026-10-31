"""Cadastros básicos do Processo Eletrônico (modo 2)."""

from uuid import uuid4
from typing import Any

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

TIPOS = '/admin/processo_eletronico/tipoprocesso/'
DESPACHOS = '/admin/processo_eletronico/modelodespacho/'
CONFIGURACOES = '/admin/processo_eletronico/configuracaotramiteprocesso/'
HIPOTESES = '/admin/documento_eletronico/hipoteselegal/'


def _sufixo() -> str:
    """Gera valores únicos para execuções com ``--reuse-db``."""
    return uuid4().hex[:8]


def test_adicionar_tipo_e_configuracao_de_tramite(logado_processo_eletronico: Any) -> None:
    """Cadastra um tipo e usa-o na configuração do primeiro trâmite."""
    tela = Tela(logado_processo_eletronico('admin'))
    sufixo = _sufixo()
    nome = f'Tipo de Processo X E2E {sufixo}'

    tela.ir(TIPOS).clicar_botao('Adicionar Tipo de Processo').preencher_formulario(
        [
            ('Nome', 'texto', nome),
            ('Nível de Acesso Padrão', 'lista', 'Público'),
            ('Permite Gerar Processo via Requerimento?', 'checkbox', 'marcar'),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')

    tela.ir(CONFIGURACOES).clicar_botao('Adicionar Configuração do Trâmite do Processo').clicar_botao('Buscar').selecionar_item(nome).clicar_botao(
        'Confirmar'
    ).preencher_formulario(
        [
            ('Origem do interessado', 'autocomplete', 'A0'),
            ('Destino do primeiro trâmite', 'radio', 'Buscar usando o Autocompletar'),
            ('Setor de Destino', 'autocomplete', 'A0'),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')

    from processo_eletronico.models import ConfiguracaoTramiteProcesso, TipoProcesso

    tipo = TipoProcesso.objects.get(nome=nome)
    assert tipo.nivel_acesso_default == 1
    assert tipo.permite_gerar_processo_via_requerimento
    assert ConfiguracaoTramiteProcesso.objects.filter(tipo_processo=tipo, setor_destino_primeiro_tramite__sigla='A0').exists()


def test_adicionar_modelo_de_despacho(logado_processo_eletronico: Any) -> None:
    """Cadastra um modelo de despacho com cabeçalho e rodapé."""
    tela = Tela(logado_processo_eletronico('admin'))
    sufixo = _sufixo()
    cabecalho = f'Cabeçalho Modelo de Despacho E2E {sufixo}'
    rodape = f'Rodapé Modelo de Despacho E2E {sufixo}'

    tela.ir(DESPACHOS).clicar_botao('Adicionar Modelo de Despacho').preencher_formulario(
        [('Cabeçalho', 'textarea', cabecalho), ('Rodapé', 'textarea', rodape)]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')

    from processo_eletronico.models import ModeloDespacho

    modelo = ModeloDespacho.objects.get(cabecalho=cabecalho)
    assert modelo.rodape == rodape


def test_adicionar_hipotese_legal(logado_processo_eletronico: Any) -> None:
    """Cadastra uma hipótese legal restrita para uso nos processos."""
    tela = Tela(logado_processo_eletronico('admin'))
    sufixo = _sufixo()
    descricao = f'Informação Restrita E2E {sufixo}'
    base_legal = f'Base Legal E2E {sufixo}'

    tela.ir(HIPOTESES).clicar_botao('Adicionar Hipótese Legal').preencher_formulario(
        [('Nível de Acesso', 'lista', 'Restrito'), ('Descrição', 'texto', descricao), ('Base Legal', 'texto', base_legal)]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')

    from documento_eletronico.models import HipoteseLegal

    hipotese = HipoteseLegal.objects.get(descricao=descricao)
    assert hipotese.nivel_acesso == 'RESTRITO'
    assert hipotese.base_legal == base_legal
