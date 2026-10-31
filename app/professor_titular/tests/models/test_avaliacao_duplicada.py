import contextlib
import datetime
import importlib

import pytest
from django.db import connection

from professor_titular.models import (
    Arquivo,
    Avaliacao,
    AvaliacaoItem,
    CategoriaMemorialDescritivo,
    Criterio,
    Grupo,
    Indicador,
    ProcessoTitular,
    Unidade,
)
from rh.models import Avaliador
from rh.tests.factories import ServidorFactory

migracao = importlib.import_module('professor_titular.migrations.0009_avaliacao_unica_por_avaliador')


@contextlib.contextmanager
def sem_constraint_de_unicidade():
    """Solta o unique_together de Avaliacao para reproduzir o estado legado.

    A duplicata não é mais criável depois da migração 0009 — que é justamente o ponto —,
    então provar a correção de `get_qtd_itens` exige recriar o estado que existia antes.
    O DROP vive dentro da transação do teste e volta atrás no rollback.
    """
    with connection.cursor() as cursor:
        # Descarrega os gatilhos de FK pendentes das inserções já feitas nesta transação;
        # sem isso o Postgres recusa o ALTER TABLE com "pending trigger events".
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        cursor.execute("""
            SELECT conname FROM pg_constraint
             WHERE conrelid = 'professor_titular_avaliacao'::regclass AND contype = 'u'
        """)
        nomes = [linha[0] for linha in cursor.fetchall()]
        assert nomes, 'esperava a constraint de unicidade criada pela migração 0009'
        for nome in nomes:
            cursor.execute(f'ALTER TABLE professor_titular_avaliacao DROP CONSTRAINT "{nome}"')
    yield


@pytest.fixture
def cenario(db, sync_permissions):
    """Processo com um arquivo pontuável e um avaliador.

    O teste precisa de um servidor qualquer com vínculo; antes ele garimpava um do
    substrato do `suap_data` (`filter(...).first()`, sem ordenação), agora constrói o seu.
    """
    servidor = ServidorFactory()
    vinculo = servidor.get_vinculo()

    processo = ProcessoTitular.objects.create(servidor=servidor, ano=2026, ano_envio_cppd=2026, status=ProcessoTitular.STATUS_EM_AVALIACAO)
    grupo = Grupo.objects.create(nome='Grupo A', percentual=100)
    unidade = Unidade.objects.create(nome='Unidade', sigla='UN')
    indicador = Indicador.objects.create(grupo=grupo, nome='Indicador', descricao='d')
    categoria = CategoriaMemorialDescritivo.objects.create(nome='Categoria', indice='c')
    criterio = Criterio.objects.create(
        indicador=indicador,
        artigo='Art. 1',
        nome='Critério',
        status=0,
        pontos=10,
        unidade=unidade,
        categoria_memorial_descritivo=categoria,
        num_artigo=1,
        inciso='I',
        alinea='a',
    )
    arquivo = Arquivo.objects.create(
        processo=processo,
        criterio=criterio,
        nome='doc.pdf',
        diretorio='doc.pdf',
        qtd_itens=3,
        data_referencia=datetime.date(2026, 1, 1),
        tamanho=1,
    )
    avaliador = Avaliador.objects.create(
        vinculo=vinculo,
        matricula_siape='1',
        numero_documento_identificacao='1',
        emissor_documento_identificacao='x',
        pis_pasep='1',
        numero_agencia='1',
        tipo_conta='1',
        numero_conta='1',
    )
    return processo, arquivo, avaliador


class TestCriarAvaliacaoIdempotente:
    def test_chamar_duas_vezes_nao_duplica(self, cenario):
        processo, _, avaliador = cenario
        primeira = processo.criar_avaliacao(avaliador)
        segunda = processo.criar_avaliacao(avaliador)
        assert primeira.pk == segunda.pk
        assert Avaliacao.objects.filter(processo=processo, avaliador=avaliador).count() == 1

    def test_nao_duplica_os_itens(self, cenario):
        processo, arquivo, avaliador = cenario
        avaliacao = processo.criar_avaliacao(avaliador)
        processo.criar_avaliacao(avaliador)
        assert AvaliacaoItem.objects.filter(avaliacao=avaliacao, arquivo=arquivo).count() == 1


class TestPontuacaoNaoCruzaAvaliacoes:
    """`get_qtd_itens` filtrava por avaliador, não pela avaliação.

    Com duas avaliações do mesmo avaliador, ele lia o item da avaliação errada — e como a
    queryset não tinha ordenação, qual delas era indefinido.
    """

    def test_le_a_quantidade_da_avaliacao_informada(self, cenario):
        processo, arquivo, avaliador = cenario
        avaliada = processo.criar_avaliacao(avaliador)
        AvaliacaoItem.objects.filter(avaliacao=avaliada, arquivo=arquivo).update(qtd_itens_validado=2)

        # Segunda avaliação do MESMO avaliador, intocada (o estado que a corrida produzia).
        with sem_constraint_de_unicidade():
            vazia = Avaliacao.objects.create(processo=processo, avaliador=avaliador, status=Avaliacao.EM_AVALIACAO)
        AvaliacaoItem.objects.create(avaliacao=vazia, arquivo=arquivo)

        assert arquivo.get_qtd_itens(avaliada) == 2, 'deve ler o item da avaliação preenchida'
        assert arquivo.get_qtd_itens(vazia) == arquivo.qtd_itens, 'sem quantidade validada, cai no declarado'
        assert arquivo.get_nota_pretendida(avaliada, True) == 2 * arquivo.criterio.pontos


class TestPredicadoDaMigracao:
    def test_avaliacao_intocada_e_descartavel(self, cenario):
        processo, arquivo, avaliador = cenario
        vazia = Avaliacao.objects.create(processo=processo, avaliador=avaliador, status=Avaliacao.EM_AVALIACAO)
        AvaliacaoItem.objects.create(avaliacao=vazia, arquivo=arquivo)
        assert migracao._eh_descartavel(AvaliacaoItem, vazia) is True

    @pytest.mark.parametrize(
        'campos_item',
        [{'qtd_itens_validado': 0}, {'qtd_itens_validado': 3}, {'data_referencia': datetime.date(2026, 1, 1)}, {'justificativa': 'texto'}],
    )
    def test_item_tocado_impede_descarte(self, cenario, campos_item):
        processo, arquivo, avaliador = cenario
        avaliacao = Avaliacao.objects.create(processo=processo, avaliador=avaliador, status=Avaliacao.EM_AVALIACAO)
        AvaliacaoItem.objects.create(avaliacao=avaliacao, arquivo=arquivo, **campos_item)
        assert migracao._eh_descartavel(AvaliacaoItem, avaliacao) is False

    @pytest.mark.parametrize(
        'campos_avaliacao',
        [
            {'status': Avaliacao.FINALIZADA},
            {'status': Avaliacao.DESISTENCIA},
            {'pontuacao_final_individual': 10},
            {'data_finalizacao': datetime.datetime(2026, 1, 1)},
            {'avaliacao_paga': True},
            {'tipo_desistencia': Avaliacao.OUTROS},
            {'motivo_desistencia': 'motivo'},
            {'motivo_indeferimento': 'motivo'},
        ],
    )
    def test_avaliacao_com_conteudo_impede_descarte(self, cenario, campos_avaliacao):
        processo, arquivo, avaliador = cenario
        campos = {'status': Avaliacao.EM_AVALIACAO} | campos_avaliacao
        avaliacao = Avaliacao.objects.create(processo=processo, avaliador=avaliador, **campos)
        AvaliacaoItem.objects.create(avaliacao=avaliacao, arquivo=arquivo)
        assert migracao._eh_descartavel(AvaliacaoItem, avaliacao) is False


class _AppsFalso:
    """Substitui o registry histórico da migração pelos models atuais."""

    _mapa = {'avaliacao': Avaliacao, 'avaliacaoitem': AvaliacaoItem}

    def get_model(self, app_label, model_name):
        return self._mapa[model_name.lower()]


class TestLimpezaDaMigracao:
    def _duplicar(self, processo, arquivo, avaliador, **campos):
        with sem_constraint_de_unicidade():
            avaliacao = Avaliacao.objects.create(processo=processo, avaliador=avaliador, **campos)
        AvaliacaoItem.objects.create(avaliacao=avaliacao, arquivo=arquivo)
        return avaliacao

    def test_remove_a_vazia_e_preserva_a_que_tem_trabalho(self, cenario):
        processo, arquivo, avaliador = cenario
        boa = processo.criar_avaliacao(avaliador)
        AvaliacaoItem.objects.filter(avaliacao=boa).update(qtd_itens_validado=2)
        boa.status = Avaliacao.FINALIZADA
        boa.pontuacao_final_individual = 20
        boa.save()
        vazia = self._duplicar(processo, arquivo, avaliador, status=Avaliacao.EM_AVALIACAO)

        migracao.remover_avaliacoes_duplicadas(_AppsFalso(), None)

        assert Avaliacao.objects.filter(pk=boa.pk).exists()
        assert not Avaliacao.objects.filter(pk=vazia.pk).exists()
        assert not AvaliacaoItem.objects.filter(avaliacao_id=vazia.pk).exists()

    def test_preserva_desistencia_e_remove_a_intocada(self, cenario):
        """Caso real do processo 493: a linha a manter não é a finalizada, é a desistência."""
        processo, arquivo, avaliador = cenario
        intocada = processo.criar_avaliacao(avaliador)
        desistencia = self._duplicar(
            processo, arquivo, avaliador, status=Avaliacao.DESISTENCIA, tipo_desistencia=Avaliacao.OUTROS, motivo_desistencia='motivo'
        )

        migracao.remover_avaliacoes_duplicadas(_AppsFalso(), None)

        assert Avaliacao.objects.filter(pk=desistencia.pk).exists()
        assert not Avaliacao.objects.filter(pk=intocada.pk).exists()

    def test_aborta_quando_as_duas_linhas_tem_trabalho(self, cenario):
        processo, arquivo, avaliador = cenario
        uma = processo.criar_avaliacao(avaliador)
        AvaliacaoItem.objects.filter(avaliacao=uma).update(qtd_itens_validado=1)
        outra = self._duplicar(processo, arquivo, avaliador, status=Avaliacao.FINALIZADA, pontuacao_final_individual=10)

        with pytest.raises(RuntimeError, match='não pode ser automática'):
            migracao.remover_avaliacoes_duplicadas(_AppsFalso(), None)

        assert Avaliacao.objects.filter(pk__in=[uma.pk, outra.pk]).count() == 2, 'nada pode ser removido quando aborta'

    def test_nao_toca_em_processo_sem_duplicata(self, cenario):
        processo, _, avaliador = cenario
        avaliacao = processo.criar_avaliacao(avaliador)
        migracao.remover_avaliacoes_duplicadas(_AppsFalso(), None)
        assert Avaliacao.objects.filter(pk=avaliacao.pk).exists()
