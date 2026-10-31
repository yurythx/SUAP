"""Relatório de situação dos processos de RSC docente.

Pedido da Gestão de Pessoas: os processos do ano separados por situação e, nos que estão em
análise, quantas avaliações já foram finalizadas, quantas faltam e a situação de cada avaliador.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission

from protocolo.models import Processo as Protocolo
from rsc import relatorio_situacao
from rh.tests.factories import ServidorFactory
from rsc.models import Avaliacao, ProcessoAvaliador, ProcessoRSC, TipoRsc


def _vinculo(avaliador_id, status, tipo=ProcessoAvaliador.AVALIADOR_EXTERNO, data_limite='20/09/2026'):
    """Avaliador da banca com o que o relatório lê dele, sem depender do banco."""
    rotulos_status = dict(ProcessoAvaliador.STATUS_CHOICES)
    rotulos_tipo = dict(ProcessoAvaliador.TIPO_AVALIADOR_CHOICES)
    return SimpleNamespace(
        avaliador=f'Avaliador {avaliador_id}',
        avaliador_id=avaliador_id,
        status=status,
        get_status_display=lambda: rotulos_status[status],
        get_tipo_avaliador_display=lambda: rotulos_tipo[tipo],
        data_limite=lambda: data_limite,
    )


def test_banca_informa_quantas_avaliacoes_foram_finalizadas_e_quantas_faltam():
    """Só avaliação deferida ou indeferida conta; a desistência não aproxima o processo do resultado."""
    vinculos = [
        _vinculo(1, ProcessoAvaliador.AVALIACAO_FINALIZADA, ProcessoAvaliador.AVALIADOR_INTERNO),
        _vinculo(2, ProcessoAvaliador.EM_AVALIACAO),
        _vinculo(3, ProcessoAvaliador.AGUARDANDO_ACEITE),
    ]
    avaliacoes = [
        Avaliacao(avaliador_id=1, status=Avaliacao.DEFERIDA),
        Avaliacao(avaliador_id=2, status=Avaliacao.EM_AVALIACAO),
        Avaliacao(avaliador_id=9, status=Avaliacao.DESISTENCIA),
    ]

    banca = relatorio_situacao.resumir_banca(vinculos, avaliacoes, reservas=2)

    assert (banca['finalizadas'], banca['faltam'], banca['reservas']) == (1, 2, 2)
    finalizado, em_avaliacao, aguardando_aceite = banca['avaliadores']
    assert finalizado['situacao'] == 'Avaliação finalizada (Deferida)'
    assert finalizado['tipo'] == 'Avaliador Interno'
    assert finalizado['data_limite'] is None, 'quem já finalizou não tem prazo a cumprir'
    assert em_avaliacao['data_limite'] == aguardando_aceite['data_limite'] == '20/09/2026'


def test_processos_sao_separados_pelas_situacoes_pedidas():
    """Processo fora das situações do relatório (ex.: aguardando validação) não aparece em seção nenhuma."""

    def processo(pk, status):
        return SimpleNamespace(pk=pk, status=status, processo_eletronico=None, protocolo=None)

    processos = [
        processo(1, ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES),
        processo(2, ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR),
        processo(3, ProcessoRSC.STATUS_EM_AVALIACAO),
        processo(4, ProcessoRSC.STATUS_AGUARDANDO_CIENCIA),
        processo(5, ProcessoRSC.STATUS_APROVADO),
        processo(6, ProcessoRSC.STATUS_REPROVADO),
        processo(7, ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD),
    ]
    bancas = {2: {'finalizadas': 0}, 3: {'finalizadas': 1}}

    with patch.object(relatorio_situacao, 'bancas_por_processo', return_value=bancas) as buscar_bancas:
        grupos = relatorio_situacao.agrupar_por_secao(processos)

    contagem = {grupo['secao'].chave: len(grupo['itens']) for grupo in grupos}
    assert contagem == {'validados': 1, 'em_analise': 2, 'aguardando_ciencia': 1, 'cientes': 0, 'finalizados': 2}
    assert [p.pk for p in buscar_bancas.call_args.args[0]] == [2, 3], 'a banca só é buscada para os processos em análise'


@pytest.mark.django_db(databases='__all__')
class TestProcessosDoAno:
    @pytest.fixture(autouse=True)
    def _setup(self, client, db, sync_permissions):
        self.client = client
        # O `servidor_a` é o requerente (e o usuário sem permissão); o `admin` é quem abre
        # a tela do relatório. O setor precisa de campus: o protocolo grava a `uo` dele.
        self.servidor_a = ServidorFactory()
        self.admin = ServidorFactory()
        usuario_admin = self.admin.get_user()
        usuario_admin.is_superuser = True
        usuario_admin.is_staff = True
        usuario_admin.save(update_fields=['is_superuser', 'is_staff'])
        self.tipo_rsc = TipoRsc.objects.create(nome='RSC-II', categoria='Docente')

    def _protocolo(self, numero, data_cadastro):
        """Protocolo físico sem o `save()`, que exige a configuração de numeração do órgão."""
        setor = self.servidor_a.setor
        protocolo = Protocolo.objects.bulk_create(
            [
                Protocolo(
                    vinculo_cadastro=self.servidor_a.get_vinculo(),
                    uo=setor.uo,
                    setor_origem=setor,
                    interessado_nome=str(self.servidor_a),
                    interessado_documento='000.000.000-00',
                    numero_processo=numero,
                    assunto='Requerimento RSC',
                    tipo=Protocolo.TIPO_REQUERIMENTO,
                )
            ]
        )[0]
        Protocolo.objects.filter(pk=protocolo.pk).update(data_cadastro=data_cadastro)
        return protocolo

    def _processo(self, protocolo=None):
        return ProcessoRSC.objects.create(
            servidor=self.servidor_a, tipo_rsc=self.tipo_rsc, status=ProcessoRSC.STATUS_EM_AVALIACAO, protocolo=protocolo
        )

    def test_filtra_pelo_ano_de_entrada_do_processo(self):
        do_ano = self._processo(self._protocolo('23035.000001.2026-01', datetime.datetime(2026, 3, 10, 9, 0)))
        self._processo(self._protocolo('23035.000002.2025-02', datetime.datetime(2025, 11, 5, 9, 0)))
        self._processo(protocolo=None)  # ainda não enviado à CPPD: sem data de entrada

        processos = list(relatorio_situacao.processos_do_ano(2026))

        assert processos == [do_ano]
        assert processos[0].data_entrada.year == 2026

    def test_tela_lista_e_exporta_a_planilha(self):
        self._processo(self._protocolo('23035.000003.2026-03', datetime.datetime(2026, 4, 1, 9, 0)))
        self.client.force_login(self.admin.get_user())

        tela = self.client.get('/rsc/relatorio_situacao/', {'ano': '2026'})
        planilha = self.client.get('/rsc/relatorio_situacao/', {'ano': '2026', 'xls': '1'})

        assert tela.status_code == 200
        assert '23035.000003.2026-03' in tela.content.decode()
        assert planilha.status_code == 200
        assert 'spreadsheetml' in planilha['Content-Type']

    def test_banca_de_varios_processos_nao_consulta_o_banco_por_processo(self, django_assert_num_queries):
        """Duas consultas no total (avaliadores e avaliações), quantos forem os processos em análise."""
        processos = [self._processo() for _ in range(3)]

        with django_assert_num_queries(2):
            relatorio_situacao.bancas_por_processo(processos)

    def test_tela_nega_acesso_sem_permissao(self):
        self.client.force_login(self.servidor_a.get_user())

        assert self.client.get('/rsc/relatorio_situacao/').status_code == 403

    def test_tela_abre_com_so_a_permissao_da_gestao_de_pessoas(self):
        """A permissão é "CPPD **ou** Gestão de Pessoas": quem tem só a de relatório precisa entrar."""
        usuario = self.servidor_a.get_user()
        usuario.user_permissions.add(Permission.objects.get(content_type__app_label='rsc', codename='pode_ver_relatorio_rsc'))
        self.client.force_login(usuario)

        assert self.client.get('/rsc/relatorio_situacao/').status_code == 200
