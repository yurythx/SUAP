"""Guarda de ``Processo.get_processos_por_vinculo`` (aba "Documentos e Processos" do aluno).

A consulta foi reescrita de um ``OR`` atravessando JOINs (interessados, acompanhantes e
``user -> vinculo -> pessoa``) para um ``UNION`` de consultas indexadas: o ``OR`` com JOIN
obrigava o Postgres a varrer ``processo_eletronico_processo`` e ``comum_vinculo`` inteiras.
Este teste tranca o conjunto de resultados das duas variantes (por vínculo e por CPF).
"""

import pytest

from processo_eletronico.models import Processo, TipoProcesso


class TestProcessosPorVinculo:
    @pytest.fixture(autouse=True)
    def _setup(self, setor_com_siorg, dois_servidores):
        self.setor = setor_com_siorg
        self.tipo = TipoProcesso.objects.create(nome='Tipo PPV', nivel_acesso_default=Processo.NIVEL_ACESSO_PUBLICO)
        self.vinculo = dois_servidores.a.get_vinculo()
        self.outro_vinculo = dois_servidores.b.get_vinculo()

    def _criar_processo(self, gerador=None, modificado_por=None, usuario_finalizacao=None):
        outro_user = self.outro_vinculo.user
        return Processo.objects.create(
            tipo_processo=self.tipo,
            nivel_acesso=Processo.NIVEL_ACESSO_PUBLICO,
            setor_criacao=self.setor,
            usuario_gerador=gerador or outro_user,
            modificado_por=modificado_por or outro_user,
            usuario_finalizacao=usuario_finalizacao,
        )

    def _processos_esperados(self):
        """Um processo por relação coberta pela busca, mais um alheio ao vínculo."""
        user = self.vinculo.user
        interessado = self._criar_processo()
        interessado.interessados.add(self.vinculo)
        acompanhado = self._criar_processo()
        acompanhado.acompanhantes_processo.add(self.vinculo)
        esperados = {
            interessado.id,
            acompanhado.id,
            self._criar_processo(gerador=user).id,
            self._criar_processo(modificado_por=user).id,
            self._criar_processo(usuario_finalizacao=user).id,
        }
        self._criar_processo()  # ruído: nenhuma relação com o vínculo
        return esperados

    def test_cobre_as_cinco_relacoes_e_ignora_processos_alheios(self):
        esperados = self._processos_esperados()
        assert set(Processo.get_processos_por_vinculo(self.vinculo).values_list('id', flat=True)) == esperados

    def test_filtrando_por_cpf_retorna_o_mesmo_conjunto(self):
        esperados = self._processos_esperados()
        encontrados = Processo.get_processos_por_vinculo(self.vinculo, filtrar_pessoa_por_tipo_vinculo=True)
        assert set(encontrados.values_list('id', flat=True)) == esperados
