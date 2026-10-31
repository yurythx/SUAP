"""Testes da tela /rh/importar_servidor/ (consulta ao SIAPE antes de importar).

Servidores com mais de um vínculo ativo aparecem no SIAPE como blocos separados
por `grMatricula`, cada um com suas próprias férias e afastamentos. A tela
precisa exibir esses conjuntos separados por matrícula, como já faz nas abas de
dados funcionais e pessoais.
"""

from datetime import date
from unittest.mock import patch

from bs4 import BeautifulSoup

from comum.models import Ano
from ferias.models import Ferias
from rh.models import AfastamentoSiape, Servidor
from rh.tests.test_base import RHBase

MATRICULA_VINCULO_1 = '1103098'
MATRICULA_VINCULO_2 = '2103098'
MATRICULA_SEM_MOVIMENTACAO = '3103098'
NOME_NO_SIAPE = 'Nome Como Vem do Siape'


class ImportadorFalso:
    """Dublê do `ImportadorWs`: devolve o que o SIAPE devolveria, sem rede."""

    eh_conectagov = False

    def __init__(self, dados_atualizar, ferias, afastamentos, historico_pca=None):
        self._dados_atualizar = dados_atualizar
        self._ferias = ferias
        self._afastamentos = afastamentos
        self._historico_pca = historico_pca or {'consultas': [], 'provimentos': []}

    def get_historico_pca(self, *args, **kwargs):
        return self._historico_pca

    def importacao_servidor(self, *args, **kwargs):
        return self._dados_atualizar

    def get_afastamento_historico(self, *args, **kwargs):
        return {'ferias': self._ferias, 'afastamentos': self._afastamentos}

    def get_dependentes(self, *args, **kwargs):
        return []


def grupos_da_aba(html, data_tab):
    """Devolve `{matrícula do cabeçalho: texto do bloco}` de uma aba da tela."""
    aba = BeautifulSoup(html, 'html.parser').find('div', attrs={'data-tab': data_tab})
    grupos = {}
    for titulo in aba.find_all('h2'):
        corpo = [str(titulo)]
        for irmao in titulo.next_siblings:
            if getattr(irmao, 'name', None) == 'h2':
                break
            corpo.append(str(irmao))
        grupos[titulo.get_text(strip=True)] = ' '.join(corpo)
    return grupos


def cabecalho_de(grupos, matricula):
    return next(cabecalho for cabecalho in grupos if matricula in cabecalho)


class ImportarServidorPorMatriculaTest(RHBase):
    def _monta_cenario(self):
        pessoa = self.servidor_a.pessoa_fisica
        ano_2026 = Ano(ano=2026)
        vinculo_1 = Servidor(matricula=MATRICULA_VINCULO_1, pessoa_fisica=pessoa)
        vinculo_2 = Servidor(matricula=MATRICULA_VINCULO_2, pessoa_fisica=pessoa)
        afastamento = AfastamentoSiape(codigo='0434', nome='AFAST. PÓS-GRADUAÇÃO STRICTO SENSU')

        def parcela(vinculo, numero, inicio, fim):
            return {
                'ferias': Ferias(ano=ano_2026, servidor=vinculo),
                'numero_parcela': numero,
                'data_inicio': inicio,
                'data_fim': fim,
                'adiantamento_gratificacao_natalina': False,
            }

        ferias = [
            parcela(vinculo_1, '01', date(2026, 1, 14), date(2026, 1, 16)),
            # parcela que o SIAPE só devolve no vínculo 1
            parcela(vinculo_1, '02', date(2026, 7, 27), date(2026, 8, 11)),
            parcela(vinculo_2, '01', date(2026, 1, 14), date(2026, 1, 16)),
        ]
        afastamentos = [
            {
                'afastamento': afastamento,
                'servidor': vinculo_1,
                'data_inicio': date(2026, 3, 12),
                'data_termino': date(2026, 7, 22),
            }
        ]
        # o terceiro vínculo existe no SIAPE mas não teve férias nem afastamentos no período
        dados_atualizar = [
            {'matricula': matricula, 'nome_apresentacao': NOME_NO_SIAPE, 'pessoa_fisica': pessoa}
            for matricula in (MATRICULA_VINCULO_1, MATRICULA_VINCULO_2, MATRICULA_SEM_MOVIMENTACAO)
        ]
        return ImportadorFalso(dados_atualizar, ferias, afastamentos)

    def _consulta(self, client):
        client.login(username=self.servidor_a.get_user().username, password='123')
        importador = self._monta_cenario()
        with patch('rh.views.ImportadorWs', return_value=importador):
            resposta = client.post('/rh/importar_servidor/', {'cpf': self.servidor_a.pessoa_fisica.cpf})
        assert resposta.status_code == 200
        return resposta.content.decode()

    def test_aba_ferias_tem_um_bloco_por_matricula(self, client):
        grupos = grupos_da_aba(self._consulta(client), 'dados_ferias')

        assert len(grupos) == 3
        for matricula in (MATRICULA_VINCULO_1, MATRICULA_VINCULO_2, MATRICULA_SEM_MOVIMENTACAO):
            assert cabecalho_de(grupos, matricula)

    def test_aba_ferias_mantem_a_parcela_exclusiva_no_bloco_do_vinculo_certo(self, client):
        grupos = grupos_da_aba(self._consulta(client), 'dados_ferias')

        assert '27/07/2026' in grupos[cabecalho_de(grupos, MATRICULA_VINCULO_1)]
        assert '27/07/2026' not in grupos[cabecalho_de(grupos, MATRICULA_VINCULO_2)]

    def test_aba_ferias_avisa_que_o_vinculo_nao_tem_parcelas(self, client):
        """Vínculo sem férias no período precisa aparecer vazio, não sumir da tela."""
        grupos = grupos_da_aba(self._consulta(client), 'dados_ferias')

        bloco = grupos[cabecalho_de(grupos, MATRICULA_SEM_MOVIMENTACAO)]
        assert 'Não foram encontradas férias cadastradas.' in bloco

    def test_cabecalho_usa_o_nome_de_apresentacao_do_siape(self, client):
        """As abas vizinhas usam `nome_apresentacao`; divergir mostraria dois nomes na mesma tela."""
        grupos = grupos_da_aba(self._consulta(client), 'dados_ferias')

        assert cabecalho_de(grupos, MATRICULA_VINCULO_1).startswith(NOME_NO_SIAPE)

    def test_aba_afastamentos_tem_um_bloco_por_matricula(self, client):
        grupos = grupos_da_aba(self._consulta(client), 'dados_afastamentos')

        assert len(grupos) == 3
        assert 'AFAST. PÓS-GRADUAÇÃO' in grupos[cabecalho_de(grupos, MATRICULA_VINCULO_1)]
        assert 'Nenhum afastamento encontrado.' in grupos[cabecalho_de(grupos, MATRICULA_VINCULO_2)]


class AbaProvimentosDeCargoTestCase(RHBase):
    """Aba de PCA: precisa mostrar o provimento e DE QUAL órgão ele veio.

    Para cedidos e em exercício provisório o cargo pertence ao órgão de origem, e é
    lá que o provimento existe. A tela tem de deixar isso explícito, inclusive os
    órgãos em que se consultou e nada se achou.
    """

    def _consulta(self, client, historico_pca):
        client.login(username=self.servidor_a.get_user().username, password='123')
        dados = [{'matricula': MATRICULA_VINCULO_1, 'nome_apresentacao': NOME_NO_SIAPE, 'pessoa_fisica': {}}]
        importador = ImportadorFalso(dados, [], [], historico_pca)
        with patch('rh.views.ImportadorWs', return_value=importador):
            resposta = client.post('/rh/importar_servidor/', {'cpf': self.servidor_a.pessoa_fisica.cpf})
        assert resposta.status_code == 200
        return BeautifulSoup(resposta.content.decode(), 'html.parser').find('div', attrs={'data-tab': 'dados_pca'})

    def test_exibe_o_provimento_do_orgao_de_origem(self, client):
        historico = {
            'consultas': [
                {'codigo_orgao': '26435', 'sigla_orgao': 'IFRN', 'quantidade': 0},
                {'codigo_orgao': '26430', 'sigla_orgao': 'IFSERTPE', 'quantidade': 1},
            ],
            'provimentos': [
                {
                    'matricula_siape': '3010803',
                    'situacao': 'VIGENTE',
                    'cargo': 'PROFESSOR ENS BASICO TECN TECNOLOGICO',
                    'codigo_vaga': '948096',
                    'orgao': 'INSTITUTO FEDERAL DO SERTAO PERNAMBUCANO',
                    'codigo_orgao': '26430',
                    'data_inicio': date(2018, 1, 17),
                    'data_fim': None,
                    'forma_provimento': 'POSSE DE NOMEADO PARA CARGO EFETIVO',
                    'forma_vacancia': None,
                    'documento_provimento': 'PORTARIA 000870/2017',
                    'documento_vacancia': '',
                }
            ],
        }
        aba = self._consulta(client, historico).get_text(' ', strip=True)

        assert '3010803' in aba
        assert 'PROFESSOR ENS BASICO TECN TECNOLOGICO' in aba
        assert '17/01/2018' in aba
        assert 'Vigente' in aba
        # os dois órgãos consultados aparecem, inclusive aquele em que nada foi achado
        assert '26435' in aba
        assert 'IFSERTPE' in aba

    def test_sem_provimento_explica_que_isso_e_esperado(self, client):
        aba = self._consulta(client, {'consultas': [], 'provimentos': []}).get_text(' ', strip=True)

        assert 'Nenhum provimento de cargo encontrado' in aba
