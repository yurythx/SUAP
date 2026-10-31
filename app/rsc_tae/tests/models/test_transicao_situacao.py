"""Testes do controle rígido de transições de situação do ProcessoRSCTae.

Cobrem o método único ``ProcessoRSCTae.transicionar`` (validação + histórico +
motivo + origem, tudo atômico) e o teste-guarda que impede mudanças de situação
fora desse método (``.update(situacao=...)`` solto em views/management/admin).
"""

import re
from pathlib import Path

import pytest

import rsc_tae

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import (
    HistoricoSituacaoProcessoRSCTae,
    Nivel,
    OrigemTransicao,
    ProcessoRSCTae,
    TransicaoInvalidaError,
)

# Ancorado no pacote do app, não na profundidade deste arquivo: `parents[n]` quebra calado
# quando o teste muda de pasta — a varredura abaixo passaria a não achar arquivo nenhum.
RSC_TAE_DIR = Path(rsc_tae.__file__).resolve().parent
DIRS_PRODUCAO = ('views', 'management', 'admin')

# ProcessoRSCTae.objects.filter(...).update( ... situacao= ... )
_PADRAO_UPDATE_SITUACAO = re.compile(
    r'ProcessoRSCTae\.objects\.filter\([^\n]*\)\.update\((?:[^()]|\([^()]*\))*?situacao=',
    re.MULTILINE,
)


@pytest.mark.django_db(databases='__all__')
class TestTransicionar:
    ATORES = ('servidor_a',)
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=self.nivel)

    def test_transicao_valida_grava_historico_com_data_motivo_e_origem(self):
        vinculo = self.servidor_a.get_vinculo()
        self.processo.transicionar(
            SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
            motivo='Servidor concluiu o preenchimento.',
            por_vinculo=vinculo,
            campos_extras={'avaliador_atual': None},
        )

        # Situação atualizada em memória e no banco
        assert self.processo.situacao == SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR
        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR

        registro = HistoricoSituacaoProcessoRSCTae.objects.filter(processo=self.processo).latest('data_transicao')
        assert registro.situacao_anterior == SituacaoProcesso.AGUARDANDO_PREENCHIMENTO
        assert registro.situacao_nova == SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR
        assert registro.motivo == 'Servidor concluiu o preenchimento.'
        assert registro.origem == OrigemTransicao.MANUAL
        assert registro.data_transicao is not None
        assert registro.realizado_por_vinculo_id == vinculo.id

    def test_transicao_automatica_registra_origem_automatico(self):
        self.processo.transicionar(
            SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
            motivo='Rotina do sistema.',
            origem=OrigemTransicao.AUTOMATICO,
        )
        registro = HistoricoSituacaoProcessoRSCTae.objects.filter(processo=self.processo).latest('data_transicao')
        assert registro.origem == OrigemTransicao.AUTOMATICO

    def test_transicao_invalida_e_rejeitada_sem_efeitos(self):
        with pytest.raises(TransicaoInvalidaError):
            self.processo.transicionar(SituacaoProcesso.DEFERIDO, motivo='Tentativa inválida.')

        assert ProcessoRSCTae.objects.get(pk=self.processo.pk).situacao == SituacaoProcesso.AGUARDANDO_PREENCHIMENTO
        assert not HistoricoSituacaoProcessoRSCTae.objects.filter(processo=self.processo).exists()

    def test_motivo_vazio_e_obrigatorio(self):
        with pytest.raises(ValueError):
            self.processo.transicionar(SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR, motivo='   ')

        assert not HistoricoSituacaoProcessoRSCTae.objects.filter(processo=self.processo).exists()


class TestGuardaTransicao:
    """Teste-guarda estático: nenhuma mudança de situação fora de ``transicionar``."""

    ATORES = ('servidor_a',)

    def test_regex_detecta_violacao_simulada(self):
        """Sanidade: o padrão realmente casa um update de situação proibido."""
        trecho = 'ProcessoRSCTae.objects.filter(pk=processo.pk).update(\n    situacao=SituacaoProcesso.EM_ANALISE,\n)'
        assert _PADRAO_UPDATE_SITUACAO.search(trecho)

    def test_nenhum_update_situacao_solto_em_producao(self):
        infratores = []
        for subdir in DIRS_PRODUCAO:
            for arquivo in (RSC_TAE_DIR / subdir).rglob('*.py'):
                if _PADRAO_UPDATE_SITUACAO.search(arquivo.read_text(encoding='utf-8')):
                    infratores.append(str(arquivo.relative_to(RSC_TAE_DIR)))

        assert not infratores, (
            f'A situação do ProcessoRSCTae só pode mudar via ProcessoRSCTae.transicionar(). Encontrado .update(situacao=...) solto em: {infratores}'
        )
