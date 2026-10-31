"""Fluxo: documentos de empenho específicos — os dois cadastros do menu e a regra que eles ligam.

Há empenhos que o Tesouro não deixa distinguir pelos próprios atributos — a folha de pagamento lançada
como custeio, por exemplo. O gestor os marca à mão: cadastra um **tipo** (com ou sem
"Aplicar a regra sobre o cálculo das variáveis financeiras") e associa o empenho a ele. Um tipo com a
regra tira o empenho de seis variáveis (LOA_EXEC, 20RL_LOA, GTO_LOA, fGTO, fGOC, fGCO — via
``DocumentoEmpenhoEspecifico.get_documento_folha_pagamento_ids``); um tipo sem a regra é só registro.

O que se afirma aqui é o ciclo de vida dos dois cadastros (adicionar → editar → remover, com a
confirmação por senha que o ``ModelAdminPlus`` exige para remover) e, sobretudo, o **efeito** da marcação
no relatório de variáveis: o empenho sai de LOA_EXEC quando marcado com um tipo que aplica a regra e
volta quando o tipo é trocado por um que não aplica. Regressão que pega: a regra deixar de excluir (o
campus aparece gastando a folha como custeio) ou passar a excluir independentemente do tipo.
"""

import datetime
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela
from djtools.templatetags.filters import format_money
from tesouro_gerencial.tests.e2e.conftest import TIPO_COM_REGRA, TIPO_SEM_REGRA

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

TIPOS = '/admin/tesouro_gerencial/tipodocumentoempenhoespecifico/'
DOCUMENTOS = '/admin/tesouro_gerencial/documentoempenhoespecifico/'
DOCUMENTO_ADD = '/admin/tesouro_gerencial/documentoempenhoespecifico/add/'
DOCUMENTO_CHANGE = '/admin/tesouro_gerencial/documentoempenhoespecifico/{}/change/'
VARIAVEIS_DO_CAMPUS = '/tesouro_gerencial/variaveis/?campus={}&ano={}'

REGRA = 'Aplicar a regra sobre o cálculo das variáveis financeiras'


def _remover_pela_tela(tela: Tela) -> Tela:
    """Remover no ``ModelAdminPlus``: botão da tela de edição e confirmação com a senha do próprio usuário."""
    tela.clicar_botao('Remover')
    tela.preencher('Senha para confirmação', 'senha', SENHA_E2E)
    return tela.clicar_botao('Sim, remova')


def _aba_loa_exec(tela: Tela, uo) -> Tela:
    """A aba LOA_EXEC do relatório de variáveis do campus no ano corrente, com o total conferido no ORM.

    O total é espelhado do ``Variavel.get_LOA_EXEC`` e não fixado: o ano corrente é o mesmo que a
    importação grava, e o que importa aqui é o empenho do teste entrar ou sair da lista.
    """
    from tesouro_gerencial.models import Variavel

    ano = datetime.date.today().year
    tela.ir(VARIAVEIS_DO_CAMPUS.format(uo.pk, ano)).clicar_aba('LOA_EXEC')
    aba = tela.aba('LOA_EXEC')
    aba.ver_texto(f'R$ {format_money(Variavel.get_LOA_EXEC(uo, ano))}')
    return aba


def test_ciclo_do_tipo_de_documento_especifico(logado_tesouro):
    """Adicionar com a regra, editar tirando a regra, remover."""
    from tesouro_gerencial.models import TipoDocumentoEmpenhoEspecifico

    descricao = f'E2E Tipo {uuid4().hex[:8]}'
    tela = Tela(logado_tesouro('gestor')).ir(TIPOS)
    tela.ver_titulo('Tipos de Documentos de Empenho Específicos')
    tela.clicar_botao('Adicionar Tipo de Documento de Empenho Específico')
    tela.preencher_formulario(
        [
            ('Descrição', 'texto', descricao),
            (REGRA, 'checkbox', 'marcar'),
            ('Observação', 'textarea', 'Folha de pagamento empenhada como custeio.'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    tipo = TipoDocumentoEmpenhoEspecifico.objects.filter(descricao=descricao).first()
    assert tipo is not None, 'a UI disse que salvou, mas o tipo não persistiu'
    assert tipo.aplicar_calculo, 'o tipo foi salvo sem a regra marcada na tela'

    tela.linha(descricao).clicar_icone('edição')
    tela.preencher('Descrição', 'texto', f'{descricao} (registro)').preencher(REGRA, 'checkbox', 'desmarcar')
    tela.clicar_botao('Salvar')

    tela.sucesso('Atualização realizada com sucesso.')
    tipo.refresh_from_db()
    assert (tipo.descricao, tipo.aplicar_calculo) == (f'{descricao} (registro)', False), 'a UI disse que editou, mas não persistiu'

    tela.linha(tipo.descricao).clicar_icone('edição')
    _remover_pela_tela(tela)

    tela.sucesso(f'Tipo de Documento de Empenho Específico "{tipo.descricao}": excluído com sucesso.')
    assert not TipoDocumentoEmpenhoEspecifico.objects.filter(pk=tipo.pk).exists(), 'a UI disse que removeu, mas o tipo continua no banco'


def test_tipo_com_regra_tira_o_empenho_das_variaveis_e_sem_regra_devolve(logado_tesouro, tesouro_seed, empenho_do_ano):
    """Marca o empenho com o tipo que aplica a regra, troca para o que não aplica, remove a marcação."""
    from tesouro_gerencial.models import DocumentoEmpenhoEspecifico

    numero = empenho_do_ano.numero
    tela = Tela(logado_tesouro('gestor'))
    _aba_loa_exec(tela, tesouro_seed).linha(numero).ver_texto('3.210,00')

    tela.ir(DOCUMENTOS).clicar_botao('Adicionar Documento de Empenho Específico')
    tela.preencher_formulario(
        [
            ('Documento empenho', 'autocomplete', numero),
            ('Tipo', 'autocomplete', TIPO_COM_REGRA),
            ('Observação', 'textarea', 'Empenho da folha de pagamento lançado como custeio.'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    especifico = DocumentoEmpenhoEspecifico.objects.filter(documento_empenho=empenho_do_ano, tipo__descricao=TIPO_COM_REGRA).first()
    assert especifico is not None, 'a UI disse que salvou, mas o documento específico não persistiu'

    aba = _aba_loa_exec(tela, tesouro_seed)
    expect(aba.loc(f'//tr[contains(normalize-space(.), "{numero}")]')).to_have_count(0)

    tela.ir(DOCUMENTO_CHANGE.format(especifico.pk)).preencher('Tipo', 'autocomplete', TIPO_SEM_REGRA).clicar_botao('Salvar')
    tela.sucesso('Atualização realizada com sucesso.')
    especifico.refresh_from_db()
    assert especifico.tipo.descricao == TIPO_SEM_REGRA, 'a UI disse que editou, mas o tipo do documento não mudou'
    _aba_loa_exec(tela, tesouro_seed).linha(numero).ver_texto('3.210,00')

    tela.ir(DOCUMENTO_CHANGE.format(especifico.pk))
    _remover_pela_tela(tela)
    tela.sucesso('excluído com sucesso.')
    assert not DocumentoEmpenhoEspecifico.objects.filter(pk=especifico.pk).exists(), 'a UI disse que removeu, mas a marcação continua'
