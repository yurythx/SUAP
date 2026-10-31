from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from comum.models import Dependente, PrestadorServico
from rh.importador_ws import ImportadorSIAPENetService
from rh.importador_ws import ImportadorWs
from rh.enums import TipoExtracao
from rh.models import CampoExcecao, ExcecaoDado, PessoaFisica, Servidor
from rh.tests.test_base import RHBase


def _make_service():
    service = ImportadorSIAPENetService.__new__(ImportadorSIAPENetService)
    service.client = MagicMock()
    service.get_headers = MagicMock(return_value={'siglaSistema': 'SIG', 'nomeSistema': 'NOM', 'senha': '123', 'codigoOrgao': '26435'})
    service._get_service_and_params = MagicMock(return_value={'consultaDadosFuncionais': 'siglaSistema,nomeSistema,senha,cpf,codOrgao'})
    return service


class ImportadorSIAPENetServiceCallServiceSiapeTest:
    @patch.object(ImportadorSIAPENetService, '_call_service_siape', autospec=True)
    def test_call_service_siape_wraps_webfault_0030_as_empty(self, mock_call):
        from suds import WebFault

        fault = MagicMock()
        fault.faultcode = '0030'
        fault.faultstring = 'Não existem dados para consulta'

        real_service = _make_service()

        def side_effect(self_ref, params):
            params.pop('consulta', None)
            params.pop('siglaSistema', None)
            params.pop('nomeSistema', None)
            params.pop('senha', None)
            params.pop('codOrgao', None)
            raise WebFault(fault, MagicMock())

        mock_call.side_effect = side_effect
        with pytest.raises(WebFault):
            mock_call(real_service, {'consulta': 'consultaDadosFuncionais'})

    def test_fault_code_0030_returns_empty(self):
        service = _make_service()
        from suds import WebFault

        fault = MagicMock()
        fault.faultcode = '0030'
        fault.faultstring = 'Não existem dados para consulta'
        webfault = WebFault(fault, MagicMock())
        service.client.service.consultaDadosFuncionais.side_effect = webfault
        result = service._call_service_siape({'consulta': 'consultaDadosFuncionais', 'cpf': '12345678901', 'codOrgao': '26435'})
        assert result == b'<empty></empty>'

    def test_fault_code_0002_returns_empty(self):
        service = _make_service()
        from suds import WebFault

        fault = MagicMock()
        fault.faultcode = '0002'
        fault.faultstring = 'Não existem dados para consulta'
        webfault = WebFault(fault, MagicMock())
        service.client.service.consultaDadosFuncionais.side_effect = webfault
        result = service._call_service_siape({'consulta': 'consultaDadosFuncionais', 'cpf': '12345678901', 'codOrgao': '26435'})
        assert result == b'<empty></empty>'

    def test_fault_code_unknown_raises_exception(self):
        service = _make_service()
        from suds import WebFault

        fault = MagicMock()
        fault.faultcode = '9999'
        fault.faultstring = 'Erro desconhecido'
        webfault = WebFault(fault, MagicMock())
        service.client.service.consultaDadosFuncionais.side_effect = webfault
        with pytest.raises(Exception) as ctx:
            service._call_service_siape({'consulta': 'consultaDadosFuncionais', 'cpf': '12345678901', 'codOrgao': '26435'})
        assert '9999' in str(ctx.value)

    def test_successful_call_returns_result(self):
        service = _make_service()
        service.client.service.consultaDadosFuncionais.return_value = '<result>ok</result>'
        result = service._call_service_siape({'consulta': 'consultaDadosFuncionais', 'cpf': '12345678901', 'codOrgao': '26435'})
        assert result == '<result>ok</result>'


class ImportadorWsDependentesTestCase(RHBase):
    def test_dependente_reusa_a_pessoa_fisica_existente(self):
        importador = ImportadorWs.__new__(ImportadorWs)
        pessoa_fisica_original = self.servidor_a.pessoa_fisica
        total_inicial = PessoaFisica.objects.count()
        matricula_dependente = ''.join(filter(str.isdigit, pessoa_fisica_original.cpf))
        PrestadorServico.objects.filter(matricula=matricula_dependente).delete()

        importador._importar_dependentes(
            self.servidor_a,
            [{'cpf': pessoa_fisica_original.cpf, 'nome': 'Outro Nome', 'codCondicao': '001', 'arrayBeneficios': {}}],
        )

        prestador = PrestadorServico.objects.get(matricula=matricula_dependente)
        assert Dependente.objects.get(usuario_externo=prestador).servidor == self.servidor_a
        assert prestador.pessoa_fisica_id == pessoa_fisica_original.pk
        assert PessoaFisica.objects.count() == total_inicial
        pessoa_fisica_original.refresh_from_db()
        assert pessoa_fisica_original.nome != 'Outro Nome'  # PREENCHER não sobrescreve


@pytest.mark.django_db
def test_dependente_com_cpf_invalido_fica_de_fora_e_vai_para_o_log(sync_permissions: None, caplog: pytest.LogCaptureFixture) -> None:
    from rh.tests.factories import ServidorFactory

    servidor = ServidorFactory()
    importador = ImportadorWs.__new__(ImportadorWs)

    with caplog.at_level('WARNING', logger='rh.importador_ws'):
        importador._importar_dependentes(servidor, [{'cpf': '111.111.111-11', 'nome': 'Fulano de Tal'}])

    assert f'Dependente Fulano de Tal do servidor {servidor.matricula} não importado: CPF inválido.' in caplog.messages
    assert not Dependente.objects.filter(servidor=servidor).exists()


class ImportadorWsDocumentacaoAusenteTest:
    """Documentação vazia no SIAPE não pode abortar a importação inteira.

    Reproduzido com CPF real (SIAPE_NET): a servidora tem dados funcionais
    completos — 73 campos, órgão do IFRN, matrícula e e-mail — mas
    `consultaDadosDocumentacao` responde `<empty></empty>`. Documento de
    identidade, título e CTPS são complementares; PCA, contracheques e
    dependentes já são tolerados vazios na mesma função.
    """

    def _importador(self, documentacao):
        importador = ImportadorWs.__new__(ImportadorWs)
        importador.client = MagicMock()
        importador.get_dados_funcionais = MagicMock(return_value={'matriculaSiape': '1023394'})
        importador.get_dados_documentacao = MagicMock(return_value=documentacao)
        importador.get_dados_pessoais = MagicMock(return_value=[{'nome': 'FULANA DE TAL'}])
        importador.get_dados_endereco_residencial = MagicMock(return_value=[{'cep': '59000000'}])
        importador.get_dados_bancarios = MagicMock(return_value=[{'matricula': '1023394', 'banco': '001'}])
        importador.get_dados_escolares = MagicMock(return_value={'escolar': [{'nivel': 'X'}], 'titulacoes': []})
        importador.get_dados_contracheques = MagicMock(return_value=None)
        importador.get_dados_pca = MagicMock(return_value=None)
        importador.get_dependentes = MagicMock(return_value=None)
        return importador

    def test_documentacao_vazia_nao_aborta(self):
        importador = self._importador([])
        servidores, pessoa = importador._get_servidor_completo('79405681320')
        assert servidores, 'os dados funcionais precisam sobreviver'
        assert pessoa['nome'] == 'FULANA DE TAL'
        assert pessoa['cep'] == '59000000'

    def test_documentacao_vazia_preserva_o_cpf_consultado(self):
        # `numCPF` só vem desta consulta — não está em pessoais, endereço nem
        # escolares. Sem ele, `mask_cpf(None)` devolve '' e a PessoaFisica
        # nasceria sem CPF. O CPF consultado é a fonte de verdade: foi a chave
        # usada para achar esta pessoa.
        importador = self._importador([])
        _, pessoa = importador._get_servidor_completo('79405681320')
        assert pessoa['numCPF'] == '79405681320'

    def test_documentacao_presente_continua_sendo_aplicada(self):
        importador = self._importador([{'numCPF': '79405681320', 'numeroCarteiraIdentidade': '123'}])
        _, pessoa = importador._get_servidor_completo('79405681320')
        assert pessoa['numCPF'] == '79405681320'
        assert pessoa['numeroCarteiraIdentidade'] == '123'

    def test_documentacao_parcial_sem_numcpf_tambem_preserva_o_cpf(self):
        # Achado do code-review: a tolerância cobria só a documentação VAZIA.
        # Vindo uma resposta não vazia mas sem `numCPF` — dado parcial, comum no
        # SIAPE —, o ramo de sucesso retornava antes da garantia e a
        # PessoaFisica nascia com cpf='', a mesma corrupção por outro caminho.
        importador = self._importador([{'numeroCarteiraIdentidade': '123'}])
        _, pessoa = importador._get_servidor_completo('79405681320')
        assert pessoa['numCPF'] == '79405681320'
        assert pessoa['numeroCarteiraIdentidade'] == '123'

    def test_dados_pessoais_vazios_continuam_sendo_fatais(self):
        # A tolerância é só da documentação: sem nome e nascimento não há
        # PessoaFisica que faça sentido.
        importador = self._importador([])
        importador.get_dados_pessoais = MagicMock(return_value=[])
        with pytest.raises(Exception, match='dados pessoais'):
            importador._get_servidor_completo('79405681320')


class ImportadorWsConsultarComRetentativaTest:
    """O laço de retentativa, agora compartilhado pelas nove consultas.

    Testado direto porque a semântica dele é sutil e valia para todas: são três
    tentativas (não quatro), o esgotamento devolve `None` em vez de propagar, e
    só quem passa `propagar_em_debug` relança sob DEBUG — assimetria herdada do
    código original, onde apenas a consulta funcional fazia isso.
    """

    def _importador(self):
        return ImportadorWs.__new__(ImportadorWs)

    def test_devolve_no_primeiro_sucesso_sem_repetir(self):
        consulta = MagicMock(return_value=['ok'])
        assert self._importador()._consultar_com_retentativa(consulta) == ['ok']
        assert consulta.call_count == 1

    def test_tenta_exatamente_tres_vezes_e_desiste(self):
        consulta = MagicMock(side_effect=Exception('fora do ar'))
        assert self._importador()._consultar_com_retentativa(consulta) is None
        assert consulta.call_count == 3

    def test_sucesso_na_ultima_tentativa_ainda_conta(self):
        consulta = MagicMock(side_effect=[Exception('1'), Exception('2'), ['ok']])
        assert self._importador()._consultar_com_retentativa(consulta) == ['ok']
        assert consulta.call_count == 3

    def test_sob_debug_so_propaga_quem_pediu(self):
        consulta = MagicMock(side_effect=ValueError('boom'))
        importador = self._importador()
        with override_settings(DEBUG=True):
            with pytest.raises(ValueError):
                importador._consultar_com_retentativa(consulta, propagar_em_debug=True)
            consulta.reset_mock()
            assert importador._consultar_com_retentativa(consulta) is None
            assert consulta.call_count == 3


class ImportadorWsIngressoServicoPublicoTest:
    """Consolidação da data de ingresso no serviço público entre os vínculos do CPF.

    `dataOcorrIngressoServPublico` (consultaDadosFuncionais) é a data de uma
    ocorrência da MATRÍCULA, não da pessoa: o SIAPE só a preenche no vínculo em que
    o ingresso aconteceu e devolve a tag vazia nos demais. Foi o caso do CPF
    034.710.844-01 — `20082004` na matrícula 1466156 (inativa) e
    `<dataOcorrIngressoServPublico></dataOcorrIngressoServPublico>` na 2466156
    (ativa) —, que deixava o vínculo ativo sem a data e fazia a licença capacitação
    calcular pelo início de exercício na instituição (2010) em vez de 2004.

    Ingresso no serviço público é atributo da pessoa e não retrocede: vale sempre a
    data mais antiga entre os vínculos devolvidos para o CPF.
    """

    def _importador(self):
        return ImportadorWs.__new__(ImportadorWs)

    def test_vinculo_sem_a_data_herda_a_do_outro_vinculo(self):
        servidores = [
            {'matriculaSiape': '1466156', 'dataOcorrIngressoServPublico': '20082004'},
            {'matriculaSiape': '2466156', 'dataOcorrIngressoServPublico': ''},
        ]
        assert self._importador()._data_ingresso_servico_publico(servidores) == date(2004, 8, 20)

    def test_tag_ausente_e_tratada_como_vazia(self):
        # O SIAPE devolve a tag vazia; o parser (etree_to_dict) pode entregar None.
        servidores = [
            {'matriculaSiape': '1466156', 'dataOcorrIngressoServPublico': '20082004'},
            {'matriculaSiape': '2466156'},
        ]
        assert self._importador()._data_ingresso_servico_publico(servidores) == date(2004, 8, 20)

    def test_vale_sempre_a_mais_antiga_mesmo_com_data_propria(self):
        # A ordem dos vínculos na resposta do SIAPE não é garantida, e um vínculo
        # posterior pode trazer a data da própria posse em vez do primeiro ingresso.
        servidores = [
            {'matriculaSiape': '2466156', 'dataOcorrIngressoServPublico': '01012010'},
            {'matriculaSiape': '1466156', 'dataOcorrIngressoServPublico': '20082004'},
        ]
        assert self._importador()._data_ingresso_servico_publico(servidores) == date(2004, 8, 20)

    def test_vinculo_unico_mantem_a_propria_data(self):
        servidores = [{'matriculaSiape': '1466156', 'dataOcorrIngressoServPublico': '20082004'}]
        assert self._importador()._data_ingresso_servico_publico(servidores) == date(2004, 8, 20)

    def test_sem_data_em_nenhum_vinculo_devolve_none(self):
        servidores = [
            {'matriculaSiape': '1466156', 'dataOcorrIngressoServPublico': ''},
            {'matriculaSiape': '2466156'},
        ]
        assert self._importador()._data_ingresso_servico_publico(servidores) is None


class ImportadorWsIngressoServicoPublicoArgsTestCase(RHBase):
    """A consolidação chegando no `args` — que alimenta tanto a gravação quanto a
    tela de pré-visualização da importação (`rh/templates/importar_servidor.html`).
    """

    PESSOA = {
        'numCPF': '03471084401',
        'nome': 'FULANO DE TAL',
        'codSexo': 'M',
        'dataNascimento': '01011980',
        'codCor': '01',
        'nomeCor': 'BRANCA',
        'codEstadoCivil': '1',
        'codNacionalidade': '1',
    }

    def _vinculo(self, matricula, data_ingresso):
        return {
            'matriculaSiape': matricula,
            'emailServidor': 'fulano@ifrn.edu.br',
            'codSitFuncional': '01',
            'siglaRegimeJuridico': 'EST',
            'dataOcorrIngressoServPublico': data_ingresso,
            'dataExercicioNoOrgao': '01012010',
        }

    def _args_por_matricula(self, vinculos, cpf=None):
        pessoa = dict(self.PESSOA)
        if cpf:
            pessoa['numCPF'] = cpf
        importador = ImportadorWs.__new__(ImportadorWs)
        importador.client = MagicMock()
        importador._get_servidor_completo = MagicMock(return_value=(vinculos, pessoa))
        dados = importador.importacao_servidor(pessoa['numCPF'], ver_dados_apenas=True)
        return {a['matricula']: a for a in dados}

    def _cpf_em_digitos(self, servidor):
        return servidor.pessoa_fisica.cpf.replace('.', '').replace('-', '')

    def test_vinculo_ativo_sem_a_data_recebe_a_do_vinculo_antigo(self):
        args = self._args_por_matricula([self._vinculo('1466156', '20082004'), self._vinculo('2466156', '')])
        assert args['1466156']['data_inicio_servico_publico'] == date(2004, 8, 20)
        assert args['2466156']['data_inicio_servico_publico'] == date(2004, 8, 20)

    def test_sem_data_em_nenhum_vinculo_nao_sobrescreve_o_que_ja_esta_cadastrado(self):
        # A chave precisa sair do `args`: ela vira `defaults` do update_or_create em
        # Servidor.update_or_create, e um None ali apaga o valor já gravado (inclusive
        # correção feita à mão no admin).
        args = self._args_por_matricula([self._vinculo('1466156', ''), self._vinculo('2466156', '')])
        assert 'data_inicio_servico_publico' not in args['1466156']
        assert 'data_inicio_servico_publico' not in args['2466156']

    def test_data_ja_gravada_prevalece_quando_e_mais_antiga_que_a_do_siape(self):
        # Achado do code-review: com a consolidação vindo só da resposta, um ciclo em que
        # o vínculo detentor do primeiro ingresso não voltasse do SIAPE moveria a data para
        # frente — a mesma perda que este MR corrige, no sentido inverso.
        Servidor.objects.filter(pk=self.servidor_a.pk).update(data_inicio_servico_publico=date(2000, 1, 1))
        cpf = self._cpf_em_digitos(self.servidor_a)

        args = self._args_por_matricula([self._vinculo(self.servidor_a.matricula, '01012010')], cpf=cpf)

        assert args[self.servidor_a.matricula]['data_inicio_servico_publico'] == date(2000, 1, 1)

    def test_data_do_siape_prevalece_quando_e_mais_antiga_que_a_gravada(self):
        Servidor.objects.filter(pk=self.servidor_a.pk).update(data_inicio_servico_publico=date(2010, 1, 1))
        cpf = self._cpf_em_digitos(self.servidor_a)

        args = self._args_por_matricula([self._vinculo(self.servidor_a.matricula, '20082004')], cpf=cpf)

        assert args[self.servidor_a.matricula]['data_inicio_servico_publico'] == date(2004, 8, 20)

    def test_excecao_de_atualizacao_continua_alcancando_o_campo_consolidado(self):
        # Achado do code-review: a consolidação escreve no `args` antes do bloco de
        # ExcecaoDado, então o mecanismo de exceção precisa continuar enxergando o campo.
        excecao = ExcecaoDado.objects.create(servidor=self.servidor_a, tipo_extracao=TipoExtracao.TIPO_WEBSERVICE)
        excecao.campos.add(CampoExcecao.objects.create(campo='data_inicio_servico_publico'))

        args = self._args_por_matricula([self._vinculo(self.servidor_a.matricula, '20082004')])

        assert 'Não será atualizado' in str(args[self.servidor_a.matricula]['data_inicio_servico_publico'])


class AplicarCodigoOrgaoTest:
    """Nome do parâmetro de órgão decidido pelo WSDL, não pelo que veio em `params`.

    `consultaHistoricoPCA` é a única operação que chama o parâmetro de `codigoOrgao`;
    o resto do serviço usa `codOrgao`. Decidir pelo que por acaso estava em `params`
    fazia a tela de consulta manual estourar `KeyError: 'codigoOrgao'` e impedia
    consultar o PCA em outro órgão, porque o valor do chamador era sobrescrito.
    """

    def test_usa_codigo_orgao_quando_a_operacao_declara_esse_nome(self):
        from rh.importador_ws import aplicar_codigo_orgao

        params = {'cpf': '123'}
        aplicar_codigo_orgao(params, ['siglaSistema', 'cpf', 'codigoOrgao'], '26435')
        assert params['codigoOrgao'] == '26435'
        assert 'codOrgao' not in params

    def test_usa_cod_orgao_nas_demais_operacoes(self):
        from rh.importador_ws import aplicar_codigo_orgao

        params = {'cpf': '123'}
        aplicar_codigo_orgao(params, ['siglaSistema', 'cpf', 'codOrgao'], '26435')
        assert params['codOrgao'] == '26435'

    def test_orgao_do_chamador_tem_precedencia_sobre_o_do_cadastro(self):
        from rh.importador_ws import aplicar_codigo_orgao

        params = {'cpf': '123', 'codigoOrgao': '26430'}
        aplicar_codigo_orgao(params, ['cpf', 'codigoOrgao'], '26435')
        assert params['codigoOrgao'] == '26430'


class ImportadorWsAcrescentarPcaTest:
    """Indexação do PCA por vínculo, consultando também o órgão de origem.

    O PCA pertence ao órgão dono do cargo: para cedidos, requisitados e em exercício
    provisório ele só existe no órgão de origem, e volta de lá com a matrícula
    daquele órgão. Medido em 98 servidores: consultar só o IFRN devolvia vazio para
    94 deles, e 74 de 141 vínculos não casavam pela matrícula inteira.
    """

    def _importador(self, respostas):
        """Dublê que devolve `respostas[codigo_orgao]` em vez de chamar o SIAPE."""
        importador = ImportadorWs.__new__(ImportadorWs)
        importador.client = MagicMock()
        importador.client.get_headers = MagicMock(return_value={'codigoOrgao': '26435'})
        importador.get_dados_pca = lambda cpf, codigo_orgao=None: respostas.get(codigo_orgao, [{}])
        return importador

    def test_consulta_o_orgao_de_origem_e_casa_pela_base_da_matricula(self):
        servidores = [{'matriculaSiape': '2475472', 'codigoOrgaoOrigem': '42201'}]
        provimento = {'matriculaSiape': '1475472', 'situacaoPca': 'VIGENTE', 'dataInicio': '2014-04-01'}
        importador = self._importador({'26435': [{}], '42201': [{'CargoPca': provimento}]})

        pessoa = {}
        importador._acrescentar_pca(pessoa, '12345678901', servidores)

        assert pessoa['dados_pca']['2475472'] == provimento

    def test_provimento_encerrado_nao_e_mais_descartado(self):
        """Aposentado e substituto com contrato findo só têm `ENCERRADO`."""
        servidores = [{'matriculaSiape': '1000892', 'codigoOrgaoOrigem': '00000'}]
        antigo = {'matriculaSiape': '1000892', 'situacaoPca': 'ENCERRADO', 'dataInicio': '2010-01-01'}
        recente = {'matriculaSiape': '1000892', 'situacaoPca': 'ENCERRADO', 'dataInicio': '2013-03-01'}
        importador = self._importador({'26435': [{'CargoPca': [antigo, recente]}]})

        pessoa = {}
        importador._acrescentar_pca(pessoa, '12345678901', servidores)

        assert pessoa['dados_pca']['1000892'] == recente

    def test_vigente_vence_provimento_de_inicio_mais_recente(self):
        servidores = [{'matriculaSiape': '1994116', 'codigoOrgaoOrigem': '00000'}]
        vigente = {'matriculaSiape': '1994116', 'situacaoPca': 'VIGENTE', 'dataInicio': '2019-12-02'}
        encerrado = {'matriculaSiape': '1994116', 'situacaoPca': 'ENCERRADO', 'dataInicio': '2023-01-28'}
        importador = self._importador({'26435': [{'CargoPca': [vigente, encerrado]}]})

        pessoa = {}
        importador._acrescentar_pca(pessoa, '12345678901', servidores)

        assert pessoa['dados_pca']['1994116'] == vigente

    def test_sem_provimento_a_chave_fica_vazia_e_nao_quebra(self):
        """Estagiário e colaborador não ocupam cargo efetivo: ausência é o esperado."""
        servidores = [{'matriculaSiape': '1010893', 'codigoOrgaoOrigem': '00000'}]
        importador = self._importador({'26435': [{}]})

        pessoa = {}
        importador._acrescentar_pca(pessoa, '12345678901', servidores)

        assert pessoa['dados_pca'] == {}

    def test_dois_vinculos_na_mesma_base_nao_recebem_o_mesmo_provimento(self):
        """A base de 6 dígitos identifica a pessoa; quem tem dois vínculos colide nela.

        Caso real: substituto encerrado no IFRN (2375512) e efetivo vigente na UFOB
        (1375512). Sem a precedência da matrícula exata, os dois vínculos ficavam com
        o provimento da UFOB.
        """
        servidores = [
            {'matriculaSiape': '2375512', 'codigoOrgaoOrigem': '00000'},
            {'matriculaSiape': '1375512', 'codigoOrgaoOrigem': '26447'},
        ]
        substituto = {'matriculaSiape': '2375512', 'situacaoPca': 'ENCERRADO', 'dataInicio': '2017-03-13', 'codigoOrgao': '26435'}
        efetivo = {'matriculaSiape': '1375512', 'situacaoPca': 'VIGENTE', 'dataInicio': '2018-03-06', 'codigoOrgao': '26447'}
        importador = self._importador({'26435': [{'CargoPca': substituto}], '26447': [{'CargoPca': efetivo}]})

        pessoa = {}
        importador._acrescentar_pca(pessoa, '12345678901', servidores)

        assert pessoa['dados_pca']['2375512'] == substituto
        assert pessoa['dados_pca']['1375512'] == efetivo


class ImportadorWsReaproveitamentoConsultaTest:
    """A tela de importação percorre o mesmo CPF duas vezes; o SIAPE não pode ir junto.

    `importacao_servidor` já coleta o PCA de cada órgão e, logo depois, a aba chama
    `get_historico_pca`. Sem reaproveitar a última coleta, cada carregamento da tela
    dobrava as idas ao serviço — que são uma por órgão, num serviço lento e com erro
    intermitente. A memória é de uma entrada só, para não inchar a importação em massa.
    """

    PROVIMENTO = {'matriculaSiape': '3010803', 'situacaoPca': 'VIGENTE', 'dataInicio': '2018-01-17'}
    SERVIDORES = [{'matriculaSiape': '1010803', 'codigoOrgaoOrigem': '26430'}]

    def _importador(self):
        importador = ImportadorWs.__new__(ImportadorWs)
        importador.client = MagicMock()
        importador.client.get_headers = MagicMock(return_value={'codigoOrgao': '26435'})
        importador._ultimo_pca = None
        return importador

    def test_segunda_coleta_do_mesmo_cpf_nao_vai_ao_siape(self):
        consulta = MagicMock(return_value=[{'CargoPca': self.PROVIMENTO}])
        importador = self._importador()
        importador.get_dados_pca = consulta

        primeira = importador.coletar_pca_por_orgao('12345678901', self.SERVIDORES)
        segunda = importador.coletar_pca_por_orgao('12345678901', self.SERVIDORES)

        assert segunda == primeira
        # uma chamada por órgão (26435 e 26430), e não duas
        assert consulta.call_count == 2

    def test_cpf_diferente_consulta_de_novo(self):
        consulta = MagicMock(return_value=[{'CargoPca': self.PROVIMENTO}])
        importador = self._importador()
        importador.get_dados_pca = consulta

        importador.coletar_pca_por_orgao('12345678901', self.SERVIDORES)
        importador.coletar_pca_por_orgao('98765432100', self.SERVIDORES)

        assert consulta.call_count == 4
