"""Testes do agrupamento por matrícula dos dados vindos do SIAPE.

A consulta `consultaDadosAfastamentoHistorico` devolve um bloco por
`grMatricula`. Servidores com mais de um vínculo ativo recebem um bloco por
vínculo, e as férias/afastamentos de cada um precisam ser exibidos separados,
como já acontece nas abas de dados funcionais e pessoais.
"""

from rh.utils import agrupar_por_matricula

VINCULOS = [('1103098', 'Marcilio de Oliveira Monteiro'), ('2103098', 'Marcilio de Oliveira Monteiro')]


class AgruparPorMatriculaTest:
    def test_sem_vinculos_e_sem_itens_retorna_lista_vazia(self):
        assert agrupar_por_matricula([], []) == []

    def test_distribui_itens_entre_os_vinculos(self):
        grupos = agrupar_por_matricula(VINCULOS, [('1103098', 'parcela 01'), ('1103098', 'parcela 02'), ('2103098', 'parcela 01')])

        assert [(grupo['matricula'], grupo['itens']) for grupo in grupos] == [
            ('1103098', ['parcela 01', 'parcela 02']),
            ('2103098', ['parcela 01']),
        ]

    def test_vinculo_sem_itens_continua_aparecendo(self):
        """Sem isso, um vínculo sem férias no período some da tela em vez de aparecer vazio."""
        grupos = agrupar_por_matricula(VINCULOS, [('1103098', 'parcela 01')])

        assert [grupo['matricula'] for grupo in grupos] == ['1103098', '2103098']
        assert grupos[1]['itens'] == []

    def test_rotula_o_grupo_com_o_nome_do_vinculo(self):
        grupos = agrupar_por_matricula([('1103098', 'Nome Vindo do SIAPE')], [('1103098', 'parcela 01')])

        assert grupos[0]['nome'] == 'Nome Vindo do SIAPE'

    def test_ordem_dos_grupos_segue_a_lista_de_vinculos(self):
        grupos = agrupar_por_matricula(list(reversed(VINCULOS)), [('1103098', 'a'), ('2103098', 'b')])

        assert [grupo['matricula'] for grupo in grupos] == ['2103098', '1103098']

    def test_matricula_fora_da_lista_de_vinculos_vira_grupo_no_fim(self):
        """As duas consultas ao SIAPE são independentes e podem divergir; nada pode ser descartado."""
        grupos = agrupar_por_matricula(VINCULOS, [('9999999', 'orfa'), ('1103098', 'a')])

        assert [grupo['matricula'] for grupo in grupos] == ['1103098', '2103098', '9999999']
        assert grupos[2]['itens'] == ['orfa']
        assert grupos[2]['nome'] == ''

    def test_reune_itens_nao_consecutivos_do_mesmo_vinculo(self):
        """Diferente de `{% regroup %}`, não depende da ordenação da resposta do SIAPE."""
        grupos = agrupar_por_matricula(VINCULOS, [('1103098', 'a'), ('2103098', 'b'), ('1103098', 'c')])

        assert grupos[0]['itens'] == ['a', 'c']
        assert grupos[1]['itens'] == ['b']

    def test_normaliza_matricula_numerica_para_texto(self):
        grupos = agrupar_por_matricula([(1103098, 'Nome')], [(1103098, 'a')])

        assert grupos[0]['matricula'] == '1103098'
        assert grupos[0]['itens'] == ['a']
