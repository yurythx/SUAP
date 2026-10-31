"""Recebimento de trâmite pelo barramento: interessados do processo (#17659) e usuário do recebimento (#17692).

`receber_processo` é chamado direto, como `processar_recebimento_tramite_a_receber` o faz. Os metadados e os
documentos já chegaram do barramento (a fronteira externa), então não há HTTP a simular.
"""

import base64
import logging
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType

from comum.models import Configuracao, User, Vinculo
from comum.tests.factories import UserFactory
from conectagov_pen.models import MapeamentoTiposDocumento, ProcessoBarramento, TipoDocumentoPEN, TramiteBarramento
from conectagov_pen.processa_pendencias import processar_recebimento_tramite_a_receber, receber_processo
from djtools.middleware import threadlocals as tl
from documento_eletronico.tests.factories import TipoConferenciaFactory, TipoDocumentoFactory
from processo_eletronico.models import DocumentoDigitalizadoProcesso, Processo
from processo_eletronico.tests.factories import TipoProcessoFactory
from rh.models import PessoaFisica, PessoaJuridica
from rh.tests.factories import PessoaJuridicaFactory, SetorFactory, cnpj_valido

ID_ESTRUTURA = '123456'
ID_TIPO_DOC_PEN = 42
# `_criar_documento_recebido` grava o documento com `tipo_conferencia_id=3` fixo.
ID_TIPO_CONFERENCIA_RECEBIMENTO = 3


@pytest.fixture
def estrutura_recebimento(db):
    """Campus mapeado no barramento e a configuração mínima para o SUAP criar o processo recebido.

    Sem usuário no threadlocal, como na rotina agendada (Beat) e no comando de correção: `Processo.modificado_por` e
    `DocumentoProcesso.usuario_inclusao` são NOT NULL e vêm do usuário logado (tela) ou de `usuario_recebimento_pen`.
    """
    setor = SetorFactory(codigo_siorg=str(Processo.CODIGO_SIORG))
    uo = setor.uo
    uo.id_estrutura_pen = ID_ESTRUTURA
    uo.setor_recebimento_pen = setor
    uo.save()
    tipo = TipoProcessoFactory()
    _configurar('tipo_processo_recebimento_pen', tipo.pk)
    tl.context.user = None
    yield setor
    tl.context.user = None


@pytest.fixture
def usuario_logado(estrutura_recebimento) -> User:
    """Recebimento disparado pela tela (`views.processar_pendencias`)."""
    tl.context.user = UserFactory()
    return tl.context.user


def _configurar(chave: str, valor: object) -> None:
    Configuracao.objects.update_or_create(app='conectagov_pen', chave=chave, defaults={'valor': valor})
    Configuracao.clear_cache()


def _metadados(interessados: list[dict]) -> dict:
    return {
        'destinatario': {'numeroDeIdentificacaoDaEstrutura': ID_ESTRUTURA},
        'processo': {
            'protocolo': '23000.000001/2026-11',
            'nivelDeSigilo': Processo.NIVEL_ACESSO_PUBLICO,
            'descricao': 'Assunto do processo',
            'dataHoraDeProducao': '2026-10-01T10:00:00',
            'produtor': {'nome': 'suap'},
            'interessados': interessados,
        },
    }


def _tramite_pendente() -> TramiteBarramento:
    processo_barramento = ProcessoBarramento.objects.create(nre_barramento_pen='NRE1', criado_no_suap=False)
    return TramiteBarramento.objects.create(processo_barramento=processo_barramento, status=TramiteBarramento.STATUS_PENDENTE_RECEBIMENTO)


def _receber(interessados: list[dict], documentos: list[dict] | None = None) -> Processo:
    tramite_barramento = _tramite_pendente()
    return receber_processo(_metadados(interessados), documentos or [], tramite_barramento.processo_barramento, tramite_barramento)


def _interessado(codigo: str, nome: str = 'Interessado') -> dict:
    return {'nome': nome, 'documentosDeIdentificacao': [{'codigo': codigo, 'emissor': 'CPF_CNPJ', 'tipo': 'CI', 'nomeNoDocumento': nome}]}


def _vinculo_de(pessoa: PessoaJuridica) -> Vinculo:
    return Vinculo.objects.get(id_relacionamento=pessoa.pk, tipo_relacionamento=ContentType.objects.get_for_model(PessoaJuridica))


def _so_digitos(codigo: str) -> str:
    return ''.join(c for c in codigo if c.isdigit())


def test_interessado_pj_com_cnpj_formatado_vira_vinculo_da_pj(usuario_logado):
    cnpj = cnpj_valido(7)

    processo = _receber([_interessado(cnpj, 'Empresa Ltda')])

    pessoa_juridica = PessoaJuridica.objects.get(cnpj=cnpj)
    assert pessoa_juridica.nome == 'Empresa Ltda'
    assert list(processo.interessados.all()) == [_vinculo_de(pessoa_juridica)]


def test_interessado_pj_com_cnpj_so_digitos_cai_no_ramo_pj(usuario_logado):
    cnpj = cnpj_valido(8)

    processo = _receber([_interessado(_so_digitos(cnpj))])

    assert not PessoaFisica.objects.exists()
    pessoa_juridica = PessoaJuridica.objects.get(cnpj=cnpj)
    assert list(processo.interessados.all()) == [_vinculo_de(pessoa_juridica)]


@pytest.mark.parametrize('so_digitos', [False, True])
def test_interessado_pj_existente_nao_duplica(usuario_logado, so_digitos):
    existente = PessoaJuridicaFactory()
    codigo = _so_digitos(existente.cnpj) if so_digitos else existente.cnpj
    total = PessoaJuridica.objects.count()

    processo = _receber([_interessado(codigo)])

    assert PessoaJuridica.objects.count() == total
    assert list(processo.interessados.all()) == [_vinculo_de(existente)]


def test_interessado_com_cnpj_invalido_e_ignorado_sem_abortar_o_recebimento(usuario_logado):
    valido = cnpj_valido(9)

    processo = _receber([_interessado('11.111.111/0001-00'), _interessado(valido)])

    assert not PessoaJuridica.objects.filter(cnpj='11.111.111/0001-00').exists()
    assert list(processo.interessados.all()) == [_vinculo_de(PessoaJuridica.objects.get(cnpj=valido))]


def test_interessado_com_cpf_invalido_e_ignorado_sem_o_cpf_no_log(usuario_logado, caplog):
    interessados = [_interessado('52998224725', 'Ana Souza'), _interessado('11111111111', 'Beto Silva'), _interessado('39053344705', 'Caio Lima')]

    with caplog.at_level(logging.WARNING, logger='conectagov_pen.processa_pendencias'):
        processo = _receber(interessados)

    assert set(processo.interessados.values_list('pessoa__pessoafisica__cpf', flat=True)) == {'529.982.247-25', '390.533.447-05'}
    assert not PessoaFisica.objects.filter(cpf__in=['11111111111', '111.111.111-11']).exists()
    assert 'Beto Silva' in caplog.text
    assert '11111111111' not in caplog.text


def _documento_pdf() -> dict:
    tipo_pen = TipoDocumentoPEN.objects.create(id_tipo_doc_pen=ID_TIPO_DOC_PEN, nome='Ofício')
    MapeamentoTiposDocumento.objects.create(tipo_doc_barramento_pen=tipo_pen, tipo_doc_suap=TipoDocumentoFactory(), tipo_para_recebimento_suap=True)
    TipoConferenciaFactory(pk=ID_TIPO_CONFERENCIA_RECEBIMENTO)
    return {
        'ordem': 1,
        'assunto': 'Ofício recebido',
        'id_tipo_doc_pen': ID_TIPO_DOC_PEN,
        'conteudo': base64.b64encode(b'%PDF-1.4 conteudo').decode(),
        'nome_arquivo': 'oficio.pdf',
        'tipo_conteudo': 'out',
        'tipo_arquivo': 'application/pdf',
        'complemento_tipo_arquivo': '',
        'nivel_acesso': 3,
        'hipoteseLegal': None,
    }


def test_rotina_agendada_recebe_em_nome_do_usuario_configurado(estrutura_recebimento):
    usuario = UserFactory()
    _configurar('usuario_recebimento_pen', usuario.pk)

    processo = _receber([], [_documento_pdf()])

    assert processo.modificado_por == usuario
    assert DocumentoDigitalizadoProcesso.objects.get(processo=processo).usuario_inclusao == usuario
    assert tl.get_user() is None


def test_recebimento_pela_tela_grava_o_usuario_logado(usuario_logado):
    _configurar('usuario_recebimento_pen', UserFactory().pk)

    processo = _receber([])

    assert processo.modificado_por == usuario_logado
    assert tl.get_user() == usuario_logado


def test_rotina_agendada_sem_usuario_configurado_deixa_o_tramite_pendente_sem_recusar(estrutura_recebimento):
    tramite_barramento = _tramite_pendente()
    metadados = _metadados([])
    metadados['remetente'] = {'identificacaoDoRepositorioDeEstruturas': 1, 'numeroDeIdentificacaoDaEstrutura': '654321'}
    metadados['destinatario']['identificacaoDoRepositorioDeEstruturas'] = 1
    metadados['processo']['documentos'] = [
        {
            'ordem': 1,
            'descricao': 'Ofício recebido',
            'especie': {'codigo': ID_TIPO_DOC_PEN, 'nomeNoProdutor': 'Ofício'},
            'nivelDeSigilo': 3,
            'hipoteseLegal': None,
            'componentesDigitais': [
                {
                    'hash': {'conteudo': 'HASH1'},
                    'nome': 'oficio.pdf',
                    'tipoDeConteudo': 'out',
                    'mimeType': 'application/pdf',
                    'dadosComplementaresDoTipoDeArquivo': '',
                }
            ],
        }
    ]
    tramite_barramento.metadados_processo = metadados
    tramite_barramento.id_tramite_barramento = 99
    tramite_barramento.componentes_digitais_a_receber = ['HASH1']
    tramite_barramento.save()

    with (
        mock.patch('conectagov_pen.processa_pendencias.receber_componente_digital', return_value={'content': b'%PDF-1.4'}) as baixar,
        mock.patch('conectagov_pen.processa_pendencias.monta_recibo', return_value={}),  # assina com o certificado do órgão
        mock.patch('conectagov_pen.processa_pendencias.get_estrutura_por_id', return_value={'nome': 'Órgão'}),
        mock.patch('conectagov_pen.processa_pendencias.recusar_tramite') as recusar,
    ):
        processar_recebimento_tramite_a_receber(tramite_barramento, [])

    recusar.assert_not_called()
    baixar.assert_not_called()
    assert not Processo.objects.exists()
    tramite_barramento.refresh_from_db()
    assert tramite_barramento.status == TramiteBarramento.STATUS_PENDENTE_RECEBIMENTO
