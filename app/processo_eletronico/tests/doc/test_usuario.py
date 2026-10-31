"""Roteiros que geram as capturas do manual do Processo Eletrônico."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela
from processo_eletronico.tests.e2e.test_01_cadastros import CONFIGURACOES, DESPACHOS, TIPOS
from processo_eletronico.tests.e2e.test_02_fluxo_basico import PERMISSOES, PROCESSOS, _selecionar_tipo
from processo_eletronico.tests.e2e.test_03_fluxos_complementares import (
    ACOMPANHAR_URL,
    ADD_COMMENT_URL,
    ADD_DOCUMENTO_URL,
    ALTERAR_NIVEL_URL,
    DAR_CIENCIA_URL,
    DEFERIR_DESPACHO_URL,
    DESACOMPANHAR_URL,
    EDITAR_INTERESSADOS_URL,
    ENCAMINHAR_SEM_URL,
    ENCAMINHAR_URL,
    LISTAR_DOCUMENTOS_URL,
    NUP1,
    NUP2,
    PRIORIDADE_URL,
    RECEBER_URL,
    REMOVER_ULTIMO_URL,
    SOLICITAR_CIENCIA_URL,
    SOLICITAR_DESPACHO_URL,
    UPLOAD_URL,
    _detalhe,
    _processo,
    _selecionar_checkbox_popup,
    _senha,
)

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_captura_alteracao_nivel_acesso(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado da alteração de acesso."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(ALTERAR_NIVEL_URL.format(processo.pk))
    tela.ver_titulo(f'Alterar Nível de Acesso do Processo {NUP1}')
    capturar(tela.pagina, 'alterar-nivel-formulario-r3')
    tela.preencher_formulario(
        [
            ('Para', 'lista', 'Restrito'),
            ('Hipótese Legal', 'lista', 'Informação Pessoal (Art. 31 da Lei no 12.527/2011)'),
        ]
    )
    capturar(tela.pagina, 'alterar-nivel-preenchido-r3')
    _senha(tela).clicar_botao('Enviar').sucesso('Nível de Acesso alterado com sucesso.')
    capturar(tela.pagina, 'alterar-nivel-salvo-r3')


def test_captura_encaminhamento_sem_despacho(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado do encaminhamento sem despacho."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(ENCAMINHAR_SEM_URL.format(processo.pk))
    tela.ver_titulo(f'Encaminhar Processo {NUP1}')
    capturar(tela.pagina, 'encaminhar-sem-formulario-r3')
    tela.preencher_formulario([('Buscar setor de destino por', 'radio', 'Autocompletar'), ('Setor de Destino', 'autocomplete', 'A2')])
    capturar(tela.pagina, 'encaminhar-sem-preenchido-r3')
    tela.clicar_botao('Salvar').sucesso('Processo encaminhado com sucesso.')
    capturar(tela.pagina, 'encaminhar-sem-salvo-r3')


def test_captura_recebimento(logado_processo_eletronico: Any, processo_a_receber: Any, capturar: Any) -> None:
    """Gera tela e resultado do recebimento de processo."""
    tela = Tela(logado_processo_eletronico('operador_b')).ir(RECEBER_URL.format(processo_a_receber.pk))
    tela.sucesso('Processo recebido com sucesso.')
    capturar(tela.pagina, 'receber-salvo-r3')


def test_captura_requerimento_e_geracao_de_processo(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera as telas do fluxo completo de requerimento até a criação do processo."""
    from processo_eletronico.models import Requerimento

    tipo_processo = 'Acesso à Informação: Demanda do e-SIC'
    assunto = f'Requerimento de documentação {uuid4().hex[:8]}'
    descricao = 'Descrição do requerimento para geração do processo.'
    tela = Tela(logado_processo_eletronico('servidor')).ir('/admin/processo_eletronico/requerimento/')
    tela.ver_titulo('Requerimentos')
    capturar(tela.pagina, 'requerimento-listagem-r3')
    tela.clicar_botao('Adicionar Requerimento').ver_titulo('Adicionar Requerimento')
    capturar(tela.pagina, 'requerimento-formulario-r3')
    tela.clicar_botao('Buscar')
    tela.popup_ajax().selecionar_item(tipo_processo).clicar_botao('Confirmar')
    tela.preencher_formulario([('Assunto', 'texto', assunto), ('Descrição', 'textarea', descricao)])
    capturar(tela.pagina, 'requerimento-preenchido-r3')
    tela.clicar_botao('Salvar').sucesso('Requerimento cadastrado com sucesso.')

    requerimento = Requerimento.objects.get(assunto=assunto)
    tela.ver_titulo(f'Requerimento #{requerimento.get_numero_requerimento()}')
    capturar(tela.pagina, 'requerimento-gerenciado-r3')
    tela.clicar_botao('Gerar Processo Eletrônico').ver_titulo(f'Finalizar Requerimento {requerimento.get_numero_requerimento()}')
    capturar(tela.pagina, 'requerimento-finalizacao-formulario-r3')
    papel = requerimento.interessado.relacionamento.papeis_ativos.first()
    assert papel is not None
    tela.preencher_formulario(
        [
            ('Destino do primeiro trâmite', 'radio', 'Buscar usando o Autocompletar'),
            ('Setor de Destino', 'autocomplete', 'A1'),
            ('Perfil', 'lista', str(papel)),
        ]
    )
    capturar(tela.pagina, 'requerimento-finalizacao-preenchido-r3')
    _senha(tela).clicar_botao('Enviar').sucesso('Requerimento finalizado com sucesso.')

    requerimento.refresh_from_db()
    assert requerimento.processo_id is not None, 'a UI disse que finalizou, mas não criou o processo'
    processo = requerimento.processo
    assert processo.ultimo_tramite.destinatario_setor.sigla == 'A1', 'o processo não foi encaminhado ao setor escolhido'
    tela.ver_titulo(f'Processo {processo.numero_protocolo}')
    capturar(tela.pagina, 'requerimento-processo-criado-r3')


def test_captura_interessados(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado da edição de interessados."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(EDITAR_INTERESSADOS_URL.format(processo.pk))
    tela.ver_titulo(f'Editar Interessados do Processo {NUP1}')
    capturar(tela.pagina, 'interessados-formulario-r3')
    tela.preencher_formulario(
        [
            ('Interessados', 'autocomplete multiplo', 'Operador de Processo 2'),
            ('Justificativa', 'textarea', 'Alteração de interessados na documentação'),
        ]
    )
    capturar(tela.pagina, 'interessados-preenchido-r3')
    _senha(tela).clicar_botao('Enviar').sucesso('Os interessados do processo foram alterados com sucesso.')
    capturar(tela.pagina, 'interessados-salvo-r3')


def test_captura_prioridade(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado da prioridade do processo."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(PRIORIDADE_URL.format(processo.pk))
    tela.ver_titulo(f'Nível de prioridade do processo {NUP1}')
    capturar(tela.pagina, 'prioridade-formulario-r3')
    tela.preencher_formulario([('Prioridade', 'radio', 'Baixa'), ('Justificativa', 'textarea', 'Prioridade da documentação')])
    capturar(tela.pagina, 'prioridade-preenchido-r3')
    tela.clicar_botao('Salvar').sucesso('O nível de prioridade foi atualizado com sucesso.')
    capturar(tela.pagina, 'prioridade-salvo-r3')


def test_captura_documentos(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera as telas de inclusão de documento interno e upload externo."""
    from documento_eletronico.models import DocumentoTexto

    processo = _processo(NUP1)
    documento = DocumentoTexto.objects.get(assunto='Documento Teste')
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(LISTAR_DOCUMENTOS_URL.format(processo.pk))
    tela.ver_titulo(f'Documentos que podem ser adicionados ao processo {processo}')
    capturar(tela.pagina, 'documentos-lista-r3')
    tela.ir(ADD_DOCUMENTO_URL.format(processo.pk, documento.pk)).sucesso('Documento adicionado com sucesso.')
    capturar(tela.pagina, 'documento-interno-salvo-r3')

    assunto = f'Documento externo documentação {uuid4().hex[:8]}'
    tela.ir(UPLOAD_URL.format(processo.pk)).ver_titulo('Upload de Documento Externo')
    capturar(tela.pagina, 'documento-externo-formulario-r3')
    tela.preencher_formulario(
        [
            ('Tipo', 'autocomplete', 'Ofício'),
            ('Arquivo', 'arquivo', 'arquivo.pdf'),
            ('Tipo de Conferência', 'lista', 'Cópia Simples'),
            ('Assunto', 'texto', assunto),
            ('Nível de Acesso', 'lista', 'Público'),
        ]
    )
    tela.clicar_botao('Salvar').ver_titulo('Upload de Documento Externo')
    tela.preencher('Perfil', 'lista', 'Cargo A')
    capturar(tela.pagina, 'documento-externo-assinatura-r3')
    _senha(tela).clicar_botao('Assinar Documento').sucesso('Documento anexado com sucesso.')
    capturar(tela.pagina, 'documento-externo-salvo-r3')


def test_captura_comentario(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário e resultado da inclusão de comentário."""
    processo = _processo(NUP1)
    comentario = f'Comentário documentação {uuid4().hex[:8]}'
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(ADD_COMMENT_URL.format(processo.pk))
    tela.ver_titulo('Adicionar Comentário')
    capturar(tela.pagina, 'comentario-formulario-r3')
    tela.preencher('Comentário', 'textarea', comentario).clicar_botao('Salvar')
    capturar(tela.pagina, 'comentario-salvo-r3')


def test_captura_solicitacao_despacho(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado da solicitação de despacho."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(SOLICITAR_DESPACHO_URL.format(processo.pk))
    tela.ver_titulo(f'Solicitação de despacho do {NUP1}')
    capturar(tela.pagina, 'solicitar-despacho-formulario-r3')
    tela.preencher_formulario(
        [
            ('Corpo', 'textarea', 'Autorizo encaminhar para A1.'),
            ('Solicitar Assinatura a', 'autocomplete', 'Operador de Processo 1'),
            ('Setor de Destino do Trâmite (Buscar por)', 'radio', 'Autocompletar'),
            ('Especificar Setor', 'autocomplete', 'A1'),
        ]
    )
    capturar(tela.pagina, 'solicitar-despacho-preenchido-r3')
    _senha(tela).clicar_botao('Salvar').sucesso('A solicitação de despacho foi efetuada com sucesso.')
    capturar(tela.pagina, 'solicitar-despacho-salvo-r3')


def test_captura_deferimento_despacho(logado_processo_eletronico: Any, solicitacao_despacho_documentacao: Any, capturar: Any) -> None:
    """Gera formulário e resultado do deferimento de despacho."""
    tela = Tela(logado_processo_eletronico('operador_a')).ir(DEFERIR_DESPACHO_URL.format(solicitacao_despacho_documentacao.pk))
    tela.ver_titulo(f'Solicitação de Despacho do Processo {NUP1}')
    capturar(tela.pagina, 'deferir-despacho-formulario-r3')
    tela.preencher('Perfil', 'lista', 'Cargo A')
    _senha(tela).clicar_botao('Deferir e Encaminhar').sucesso('Processo encaminhado com sucesso.')
    capturar(tela.pagina, 'deferir-despacho-salvo-r3')


def test_captura_solicitacao_ciencia(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado da solicitação de ciência."""
    processo = _processo(NUP1)
    processo.interessados.add(_vinculo_doc('128003'))
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(SOLICITAR_CIENCIA_URL.format(processo.pk))
    tela.ver_titulo(f'Solicitar Ciência - Processo: {NUP1}')
    capturar(tela.pagina, 'solicitar-ciencia-formulario-r3')
    _selecionar_checkbox_popup(tela, 'Interessados', 'Operador de Processo 2')
    tela.preencher_formulario(
        [
            ('Data Limite da Ciência', 'data', '31/12/2099'),
            ('Justificativa da Solicitação', 'textarea', 'Solicitando ciência na documentação'),
            ('Tipo da Ciência', 'radio', 'Notificação'),
        ]
    )
    capturar(tela.pagina, 'solicitar-ciencia-preenchido-r3')
    tela.clicar_botao('Enviar').sucesso('Solicitações de ciência adicionadas com sucesso.')
    capturar(tela.pagina, 'solicitar-ciencia-salvo-r3')


def test_captura_dar_ciencia(logado_processo_eletronico: Any, solicitacao_ciencia_documentacao: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado do atendimento da ciência."""
    tela = Tela(logado_processo_eletronico('operador_b')).ir(DAR_CIENCIA_URL.format(solicitacao_ciencia_documentacao.processo.pk))
    tela.ver_titulo(f'Dar Ciência ao Processo {NUP1}')
    capturar(tela.pagina, 'dar-ciencia-formulario-r3')
    tela.preencher('Perfil', 'lista', 'Cargo A')
    tela.preencher('Declaro-me ciente', 'checkbox', 'marcar')
    capturar(tela.pagina, 'dar-ciencia-preenchido-r3')
    _senha(tela).clicar_botao('Assinar').sucesso('Ciência do processo')
    capturar(tela.pagina, 'dar-ciencia-salvo-r3')


def test_captura_encaminhamento_com_despacho(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado do encaminhamento com despacho."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(ENCAMINHAR_URL.format(processo.pk))
    tela.ver_titulo(f'Encaminhar Processo {NUP1}')
    capturar(tela.pagina, 'encaminhar-com-formulario-r3')
    tela.preencher_formulario(
        [
            ('Despacho', 'textarea', 'Esse é um despacho de documentação.'),
            ('Buscar setor de destino por', 'radio', 'Autocompletar'),
            ('Setor de Destino', 'autocomplete', 'A2'),
            ('Perfil', 'lista', 'Cargo A'),
        ]
    )
    capturar(tela.pagina, 'encaminhar-com-preenchido-r3')
    _senha(tela).clicar_botao('Salvar').sucesso('Processo encaminhado com sucesso.')
    capturar(tela.pagina, 'encaminhar-com-salvo-r3')


def _vinculo_doc(matricula: str) -> Any:
    """Retorna vínculo de servidor usado pelo roteiro de documentação."""
    from rh.models import Servidor

    return Servidor.objects.get(matricula=matricula).get_vinculo()


def test_captura_adicionar_interesse(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera detalhe e resultado da inclusão de interesse."""
    processo = _processo(NUP2)
    tela = _detalhe(Tela(logado_processo_eletronico('chefe_b')), NUP2)
    capturar(tela.pagina, 'interesse-detalhe-r3')
    tela.ir(ACOMPANHAR_URL.format(processo.pk)).sucesso('Processo adicionado na lista de interesses.')
    capturar(tela.pagina, 'interesse-adicionado-r3')


def test_captura_remover_interesse(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera detalhe e resultado da remoção de interesse."""
    processo = _processo(NUP2)
    processo.acompanhantes_processo.add(_vinculo_doc('128004'))
    tela = _detalhe(Tela(logado_processo_eletronico('chefe_b')), NUP2)
    capturar(tela.pagina, 'interesse-remover-detalhe-r3')
    tela.ir(DESACOMPANHAR_URL.format(processo.pk)).sucesso('Processo removido da lista de interesses.')
    capturar(tela.pagina, 'interesse-removido-r3')


def test_captura_remover_ultimo_tramite(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, trâmite criado e resultado da remoção do último trâmite."""
    processo = _processo(NUP2)
    tela = Tela(logado_processo_eletronico('chefe_b')).ir(ENCAMINHAR_SEM_URL.format(processo.pk))
    tela.ver_titulo(f'Encaminhar Processo {NUP2}')
    tela.preencher_formulario([('Buscar setor de destino por', 'radio', 'Autocompletar'), ('Setor de Destino', 'autocomplete', 'A1')])
    tela.clicar_botao('Salvar').sucesso('Processo encaminhado com sucesso.')
    capturar(tela.pagina, 'remover-tramite-criado-r3')
    tela.ir(REMOVER_ULTIMO_URL.format(processo.pk)).sucesso('Último trâmite removido com sucesso.')
    capturar(tela.pagina, 'remover-tramite-salvo-r3')


TIPO_PADRAO = 'Acesso à Informação: Demanda do e-SIC'
PROCESSO_URL = '/processo_eletronico/processo/{}/'
INDEFERIR_DESPACHO_URL = '/processo_eletronico/solicitar_despacho/indeferir/{}/'
EDITAR_ASSUNTO_URL = '/processo_eletronico/processo_editar_assunto/{}/'
JUNTADA_URL = '/processo_eletronico/enviar_pedido_juntada/{}/'
FINALIZAR_URL = '/processo_eletronico/processo/finalizar/{}/'
DESFINALIZAR_URL = '/processo_eletronico/processo/desfinalizar/{}/'
APENSAR_URL = '/processo_eletronico/apensar_processos/{}/'
NUP_FINALIZAR = '23001.000003.2019-54'
NUP_APENSADOR = '23001.000004.2019-07'
NUP_APENSADO = '23001.000005.2019-41'


def test_captura_tipo_de_processo(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera listagem, formulário e resultado do cadastro de tipo de processo."""
    from processo_eletronico.models import TipoProcesso

    nome = f'Tipo de Processo documentação {uuid4().hex[:8]}'
    tela = Tela(logado_processo_eletronico('admin')).ir(TIPOS).ver_botao('Adicionar Tipo de Processo')
    capturar(tela.pagina, 'tipo-processo-listagem-r3')
    tela.clicar_botao('Adicionar Tipo de Processo').preencher_formulario(
        [
            ('Nome', 'texto', nome),
            ('Nível de Acesso Padrão', 'lista', 'Público'),
            ('Permite Gerar Processo via Requerimento?', 'checkbox', 'marcar'),
        ]
    )
    capturar(tela.pagina, 'tipo-processo-formulario-r3')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')
    capturar(tela.pagina, 'tipo-processo-salvo-r3')
    assert TipoProcesso.objects.filter(nome=nome, permite_gerar_processo_via_requerimento=True).exists()


@pytest.mark.parametrize(
    ('listagem', 'botao', 'slug'),
    [(DESPACHOS, 'Adicionar Modelo de Despacho', 'modelo-despacho')],
)
def test_captura_modelos(logado_processo_eletronico: Any, capturar: Any, listagem: str, botao: str, slug: str) -> None:
    """Gera formulário e resultado do cadastro de modelo de despacho."""
    sufixo = uuid4().hex[:8]
    tela = Tela(logado_processo_eletronico('admin')).ir(listagem).clicar_botao(botao)
    tela.preencher_formulario(
        [('Cabeçalho', 'textarea', f'Cabeçalho documentação {sufixo}'), ('Rodapé', 'textarea', f'Rodapé documentação {sufixo}')]
    )
    capturar(tela.pagina, f'{slug}-formulario-r3')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')
    capturar(tela.pagina, f'{slug}-salvo-r3')


def test_captura_configuracao_do_tramite(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário e resultado da configuração do primeiro trâmite de um tipo."""
    from processo_eletronico.models import ConfiguracaoTramiteProcesso, Processo, TipoProcesso

    tipo = TipoProcesso.objects.create(
        nome=f'Tipo com trâmite documentação {uuid4().hex[:8]}', nivel_acesso_default=Processo.NIVEL_ACESSO_PUBLICO, ativo=True
    )
    tela = Tela(logado_processo_eletronico('admin')).ir(CONFIGURACOES).clicar_botao('Adicionar Configuração do Trâmite do Processo')
    _selecionar_tipo(tela, tipo.nome)
    tela.preencher_formulario(
        [
            ('Origem do interessado', 'autocomplete', 'A0'),
            ('Destino do primeiro trâmite', 'radio', 'Buscar usando o Autocompletar'),
            ('Setor de Destino', 'autocomplete', 'A0'),
        ]
    )
    capturar(tela.pagina, 'configuracao-tramite-formulario-r3')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')
    capturar(tela.pagina, 'configuracao-tramite-salvo-r3')
    assert ConfiguracaoTramiteProcesso.objects.filter(tipo_processo=tipo).exists()


def test_captura_permissoes_da_caixa(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera tela, preenchimento e resultado da permissão de operar a caixa do setor."""
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(PERMISSOES).ver_titulo('Permissões para Documentos e Processos Eletrônicos')
    tela.clicar_aba('Processos Eletrônicos')
    capturar(tela.pagina, 'permissoes-formulario-r3')
    tela.preencher(
        'Servidores/Prestadores de Serviço que podem adicionar e operar processos eletrônicos do(a) A1',
        'autocomplete multiplo',
        'Operador de Processo 1',
    )
    capturar(tela.pagina, 'permissoes-preenchido-r3')
    tela.clicar_botao('Enviar').sucesso('Operação realizada com sucesso')
    capturar(tela.pagina, 'permissoes-salvo-r3')


def test_captura_criar_processo(logado_processo_eletronico: Any, operador_a_habilitado: Any, capturar: Any) -> None:
    """Gera listagem, formulário e resultado da abertura de processo."""
    from processo_eletronico.models import Processo

    assunto = f'Processo da documentação {uuid4().hex[:8]}'
    tela = Tela(logado_processo_eletronico('operador_a')).ir(PROCESSOS).ver_titulo('Processos Eletrônicos')
    capturar(tela.pagina, 'processo-listagem-r3')
    tela.clicar_botao('Adicionar Processo Eletrônico')
    _selecionar_tipo(tela, TIPO_PADRAO)
    tela.preencher_formulario(
        [
            ('Interessados', 'autocomplete multiplo', 'Operador de Processo 1'),
            ('Assunto', 'textarea', assunto),
            ('Nível de Acesso', 'lista', 'Público'),
            ('Setor de Criação', 'lista', 'A1'),
        ]
    )
    capturar(tela.pagina, 'processo-formulario-r3')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')
    capturar(tela.pagina, 'processo-criado-r3')
    assert Processo.objects.filter(assunto=assunto, setor_criacao__sigla='A1').exists()


def test_captura_indeferir_despacho(logado_processo_eletronico: Any, solicitacao_despacho_documentacao: Any, capturar: Any) -> None:
    """Gera o quadro da solicitação pendente, o formulário e o resultado do indeferimento."""
    tela = Tela(logado_processo_eletronico('operador_a')).ir(PROCESSO_URL.format(_processo(NUP1).pk) + '?tab=solicitacoes')
    tela.ver_botao('Analisar')
    capturar(tela.pagina, 'despacho-pendente-r3')
    tela.ir(INDEFERIR_DESPACHO_URL.format(solicitacao_despacho_documentacao.pk))
    tela.ver_titulo(f'Indeferir Solicitação de Despacho do Processo {NUP1}')
    capturar(tela.pagina, 'indeferir-despacho-formulario-r3')
    tela.preencher('Justificativa da Rejeição', 'textarea', 'O despacho precisa ser revisto antes do encaminhamento.')
    tela.clicar_botao('Salvar').sucesso('Despacho indeferido com sucesso.')
    capturar(tela.pagina, 'indeferir-despacho-salvo-r3')
    # `refresh_from_db` esbarra no `status` protegido do django-fsm; relê pelo pk.
    solicitacao = type(solicitacao_despacho_documentacao).objects.get(pk=solicitacao_despacho_documentacao.pk)
    assert solicitacao.justificativa_rejeicao


def test_captura_editar_assunto(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário e resultado da alteração de assunto."""
    processo = _processo(NUP1)
    assunto = f'Assunto revisado na documentação {uuid4().hex[:8]}'
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(EDITAR_ASSUNTO_URL.format(processo.pk))
    tela.ver_titulo(f'Editar Assunto do Processo {NUP1}')
    tela.preencher_formulario([('Assunto', 'textarea', assunto), ('Justificativa da alteração', 'textarea', 'Assunto mais específico.')])
    capturar(tela.pagina, 'editar-assunto-formulario-r3')
    tela.clicar_botao('Salvar').sucesso('O assunto do processo foi alterado com sucesso.')
    capturar(tela.pagina, 'editar-assunto-salvo-r3')
    assert _processo(NUP1).assunto == assunto


def test_captura_solicitar_documento(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado da solicitação de juntada de documentos."""
    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(JUNTADA_URL.format(processo.pk))
    tela.ver_titulo('Adicionar Solicitação de Juntada de Documentos')
    capturar(tela.pagina, 'juntada-formulario-r3')
    _selecionar_checkbox_popup(tela, 'Solicitados', 'Operador de Processo 1')
    tela.preencher_formulario([('Motivação', 'textarea', 'Envie o comprovante citado no requerimento.'), ('Data Limite', 'data', '31/12/2099')])
    capturar(tela.pagina, 'juntada-preenchido-r3')
    tela.clicar_botao('Enviar').sucesso('Solicitações de Juntada de Documentos adicionadas com sucesso.')
    capturar(tela.pagina, 'juntada-salvo-r3')


def test_captura_finalizar_e_reabrir(logado_processo_eletronico: Any, processo_documentacao: Any, capturar: Any) -> None:
    """Gera formulário e resultado da finalização e da remoção da finalização."""
    processo = processo_documentacao(NUP_FINALIZAR)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(FINALIZAR_URL.format(processo.pk)).ver_titulo(f'Finalizar Processo {processo}')
    tela.preencher_formulario(
        [('Perfil', 'lista', 'Cargo A'), ('Justificativa', 'textarea', 'Demanda atendida.'), ('Nível de acesso', 'lista', 'Público')]
    )
    capturar(tela.pagina, 'finalizar-formulario-r3')
    _senha(tela).clicar_botao('Assinar').sucesso('Processo finalizado com sucesso.')
    capturar(tela.pagina, 'finalizar-salvo-r3')
    assert _processo(NUP_FINALIZAR).esta_finalizado()

    tela.ir(DESFINALIZAR_URL.format(processo.pk)).ver_titulo(f'Remover finalização do Processo {processo}')
    tela.preencher_formulario(
        [('Perfil', 'lista', 'Cargo A'), ('Justificativa', 'textarea', 'Nova demanda no mesmo assunto.'), ('Nível de acesso', 'lista', 'Público')]
    )
    capturar(tela.pagina, 'reabrir-formulario-r3')
    _senha(tela).clicar_botao('Assinar').sucesso('Processo reaberto com sucesso.')
    capturar(tela.pagina, 'reabrir-salvo-r3')


def test_captura_apensar(logado_processo_eletronico: Any, processo_documentacao: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado do apensamento."""
    from processo_eletronico.models import ApensamentoProcesso

    apensador = processo_documentacao(NUP_APENSADOR)
    apensado = processo_documentacao(NUP_APENSADO)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(APENSAR_URL.format(apensador.pk)).ver_titulo('Apensar Processos')
    capturar(tela.pagina, 'apensar-formulario-r3')
    tela.preencher_formulario([('Processos a Apensar', 'autocomplete multiplo', NUP_APENSADO), ('Justificativa', 'textarea', 'Mesmo assunto.')])
    capturar(tela.pagina, 'apensar-preenchido-r3')
    tela.clicar_botao('Enviar').sucesso('Processo(s) apensado(s) com sucesso.')
    tela.ir(PROCESSO_URL.format(apensador.pk) + '?tab=relacionados')
    capturar(tela.pagina, 'apensar-salvo-r3')
    assert ApensamentoProcesso.objects.filter(processo=apensado, data_hora_remocao__isnull=True).exists()


SOLICITAR_NIVEL_URL = '/processo_eletronico/solicita_alteracao_nivel_acesso/processo/{}/'


def test_captura_solicitar_alteracao_de_nivel(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera formulário, preenchimento e resultado do pedido de alteração de nível de quem não pode alterar."""
    from processo_eletronico.models import SolicitacaoAlteracaoNivelAcesso

    processo = _processo(NUP1)
    tela = Tela(logado_processo_eletronico('servidor')).ir(SOLICITAR_NIVEL_URL.format(processo.pk))
    tela.ver_titulo(f'Solicitar Alteração de Nível de Acesso do Processo: {processo}')
    capturar(tela.pagina, 'solicitar-nivel-formulario-r3')
    tela.preencher_formulario(
        [
            ('Para', 'lista', 'Restrito'),
            ('Hipótese Legal', 'lista', 'Informação Pessoal (Art. 31 da Lei no 12.527/2011)'),
            ('Justificativa', 'textarea', 'O processo contém dados pessoais do interessado.'),
        ]
    )
    capturar(tela.pagina, 'solicitar-nivel-preenchido-r3')
    _senha(tela).clicar_botao('Enviar').sucesso('Solicitação realizada com sucesso')
    capturar(tela.pagina, 'solicitar-nivel-salvo-r3')
    assert SolicitacaoAlteracaoNivelAcesso.objects.filter(processo=processo).exists()


RELACIONAR_URL = '/processo_eletronico/listar_processos_relacionado/{}/?pesquisa={}'


def test_captura_relacionar_processos(logado_processo_eletronico: Any, capturar: Any) -> None:
    """Gera a busca de processos relacionáveis e o resultado do relacionamento."""
    from processo_eletronico.models import ProcessosRelacionados

    principal, relacionado = _processo(NUP1), _processo(NUP2)
    tela = Tela(logado_processo_eletronico('chefe_a')).ir(RELACIONAR_URL.format(principal.pk, NUP2))
    tela.ver_titulo(f'Processos que podem ser relacionados ao processo {principal}')
    capturar(tela.pagina, 'relacionar-lista-r3')
    tela.clicar_botao('Relacionar ao Processo').sucesso('Relacionamento criado com sucesso.')
    capturar(tela.pagina, 'relacionar-salvo-r3')
    assert ProcessosRelacionados.objects.filter(processo_origem=principal, processo_alvo=relacionado).exists()
