"""Seed por factories do Processo Eletrônico (#17486).

A suíte do módulo não tem mais ``features/`` (modo 2, unidade de cobertura = rota). As funções
abaixo substituem os três antigos steps do behave — ``os dados básicos para o processo
eletronico``, ``os usuários do processo eletronico`` e ``os cadastros de documentos
eletronicos`` — e a árvore A0/A1/A2 que vinha do seed global legado, agora montada com os
helpers de ``djtools.e2e_fixtures``. Idempotentes, requisito do banco compartilhado e do
``--reuse-db`` do CI.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from djtools.e2e_fixtures import campus, criar_servidores, setor

if TYPE_CHECKING:
    from rh.models import Setor

# Sigla do setor -> {matrícula: (nome, grupos)}. Os nomes são digitados nos autocompletes.
SERVIDORES = {
    'A1': {
        '128001': ('Operador de Processo 1', ['Operador de Processo Eletrônico']),
        '128002': ('Chefe de Setor', ['Chefe de Setor']),
    },
    'A2': {
        '128003': ('Operador de Processo 2', ['Operador de Processo Eletrônico']),
        '128004': ('Chefe de Setor 2', ['Chefe de Setor']),
    },
    'RE': {'ServidorB': ('ServidorB', ['Servidor'])},
}


def arvore_processo() -> dict[str, Setor]:
    """Árvore RAIZ → A0 (campus) → A1/A2 e RAIZ → RE, com os códigos SIORG/protocolo do legado.

    O NUP dos processos sai do SIORG do setor de criação (A1 = 439; A2 herda 666 do A0) e do
    ``codigo_protocolo`` da UO (23001, o prefixo dos processos fixos). Tem de rodar ANTES dos
    usuários: ``User.get_vinculo`` guarda o vínculo (e o setor) em ``User.VINCULOS``, cache de
    classe que o live_server herda; um update depois deixa o setor sem SIORG lá.
    """
    setor_a0 = campus('A0', codigo_protocolo='23001', codigo_siorg='666')
    return {
        'A0': setor_a0,
        'A1': setor('A1', setor_a0, codigo_siorg='439'),
        'A2': setor('A2', setor_a0),
        'RE': campus('RE', codigo_protocolo='23001', codigo_siorg='23001'),
    }


def usuarios_processo(setores: dict[str, Setor]) -> None:
    """Cria os servidores de ``SERVIDORES``, as chefias FG de A1/A2 e o Reitor ``ServidorB`` no RE."""
    from rh.models import Atividade, Funcao, Servidor, ServidorFuncaoHistorico
    from rh.tests.factories import FuncaoFactory

    for sigla, servidores in SERVIDORES.items():
        criar_servidores(setores[sigla], servidores)

    funcao_chefe = FuncaoFactory(codigo=Funcao.CODIGO_FG, nome='Chefe de Setor')
    funcao_reitor = FuncaoFactory(codigo=Funcao.CODIGO_CD, nome='Reitor')
    atividade_reitor = Atividade.objects.get_or_create(codigo=Atividade.REITOR, defaults={'nome': 'Reitor'})[0]
    for matricula, sigla, funcao, atividade in (
        ('128002', 'A1', funcao_chefe, None),
        ('128004', 'A2', funcao_chefe, None),
        ('ServidorB', 'RE', funcao_reitor, atividade_reitor),
    ):
        ServidorFuncaoHistorico.objects.get_or_create(
            servidor=Servidor.objects.get(matricula=matricula),
            data_inicio_funcao=datetime.date(2010, 1, 1),
            funcao=funcao,
            atividade=atividade,
            setor=setores[sigla],
            setor_suap=setores[sigla],
        )
    Servidor.objects.get(matricula='128001')._definir_papel_do_servidor()


def cadastros_documento_eletronico_basicos() -> None:
    """Cria o tipo ``Termo`` e o ``Documento Teste`` concluído.

    O documento nasce assinado e finalizado pelo operador do A2 — é o pré-requisito dos fluxos
    que anexam ou originam processo a partir de documento interno. As fixtures do documento
    eletrônico já vêm do ``semear_base`` (``documento_eletronico_initial``).
    """
    from documento_eletronico.generators import montar_identificador_sigla
    from documento_eletronico.models import Documento, DocumentoTexto, ModeloDocumento, TipoDocumento, TipoDocumentoTextoHistoricoConteudo
    from rh.models import Servidor, Setor

    setor_suap = Setor.objects.suap().get(sigla='A2')
    # Operador de processo 2
    servidor = Servidor.objects.get(matricula='128003')

    user = servidor.get_user()
    modelo = ModeloDocumento.objects.last()

    # Adiciona Tipo
    tipo_termo = TipoDocumento()
    tipo_termo.nome = 'Termo'
    tipo_termo.sigla = 'Termo'
    tipo_termo.ativo = True
    tipo_termo.save()

    # Adiciona documento interno
    TipoDocumentoTextoHistoricoConteudo.objects.create(
        tipo_documento_texto=modelo.tipo_documento_texto,
        area_conteudo=TipoDocumentoTextoHistoricoConteudo.CABECALHO,
        conteudo=modelo.tipo_documento_texto.cabecalho_padrao,
        hash=modelo.tipo_documento_texto.cabecalho_hash,
    )
    TipoDocumentoTextoHistoricoConteudo.objects.create(
        tipo_documento_texto=modelo.tipo_documento_texto,
        area_conteudo=TipoDocumentoTextoHistoricoConteudo.RODAPE,
        conteudo=modelo.tipo_documento_texto.rodape_padrao,
        hash=modelo.tipo_documento_texto.rodape_hash,
    )

    documento_texto = DocumentoTexto()
    documento_texto.setor_dono = setor_suap
    documento_texto.usuario_criacao = user
    documento_texto.assunto = 'Documento Teste'
    documento_texto.data_ultima_modificacao = datetime.datetime.now()
    documento_texto.usuario_ultima_modificacao = user
    documento_texto.modelo = modelo
    documento_texto.nivel_acesso = Documento.NIVEL_ACESSO_PUBLICO

    documento_texto.save()

    servidor._definir_papel_do_servidor()

    documento_texto.concluir()
    documento_texto.atribuir_identificador_e_processar_conteudo_final(
        identificador_tipo_documento_sigla=modelo.tipo_documento_texto.sigla,
        identificador_numero=1,
        identificador_ano=2020,
        identificador_setor_sigla=montar_identificador_sigla(setor_suap),
        data_emissao=datetime.datetime.now(),
        identificador_dono_documento=None,
    )
    documento_texto.save()

    documento_texto.assinar_via_senha(user, servidor.papeis_ativos[0], documento_texto.data_criacao)
    documento_texto.finalizar_documento()
    documento_texto.save()
