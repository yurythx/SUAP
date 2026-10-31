from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from rsc_tae.models import (
    GrupoSaberCompetencia,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
)


def _pdf(nome):
    return SimpleUploadedFile(nome, b'%PDF-1.4', content_type='application/pdf')


@pytest.mark.django_db(databases='__all__')
class TestMigrarPapelRequisitoV:
    ATORES = ('servidor_a',)

    def _montar_par(self):
        req = Requisito.objects.create(numero=5, descricao='V', descricao_curta='V', numeral_romano='V')
        g_tit = GrupoSaberCompetencia.objects.create(requisito=req, numero=1, pontuacao_unidade=Decimal('9.000'), descricao='g9')
        g_sub = GrupoSaberCompetencia.objects.create(requisito=req, numero=2, pontuacao_unidade=Decimal('4.500'), descricao='g4')
        titular = RolSaberCompetencia.objects.create(
            numero=1, grupo=g_tit, titulo='Cargo CD-02 ou equivalente — titular', descricao='d', unidade_medida='ano', item_temporal=True
        )
        substituto = RolSaberCompetencia.objects.create(
            numero=2, grupo=g_sub, titulo='Cargo CD-02 ou equivalente — substituto', descricao='d', unidade_medida='ano', item_temporal=True
        )
        return titular, substituto

    def _processo(self, vinculo):
        nivel = Nivel.objects.create(nome='N', numero_minimo_itens=0, pontuacao_minima=0)
        return ProcessoRSCTae.objects.create(vinculo=vinculo, nivel_requisitado=nivel)

    def test_dry_run_nao_grava(self):
        titular, substituto = self._montar_par()
        call_command('migrar_papel_requisito_v')  # sem --commit
        titular.refresh_from_db()
        substituto.refresh_from_db()
        assert titular.aceita_papel is False  # nada gravado
        assert substituto.ativo is True

    def test_commit_funde_e_preserva(self, atores):

        titular, substituto = self._montar_par()
        processo = self._processo(self.servidor_a.get_vinculo())
        RolSaberCompetenciaAnexo.objects.create(processo=processo, rol_saber_competencia=titular, arquivo=_pdf('t.pdf'), pontuacao=Decimal('13'))
        anexo_sub = RolSaberCompetenciaAnexo.objects.create(
            processo=processo, rol_saber_competencia=substituto, arquivo=_pdf('s.pdf'), pontuacao=Decimal('13')
        )

        call_command('migrar_papel_requisito_v', '--commit')

        titular.refresh_from_db()
        substituto.refresh_from_db()
        anexo_sub.refresh_from_db()

        assert titular.aceita_papel is True
        assert titular.pontuacao_unidade_substituto == Decimal('4.500')
        assert titular.titulo == 'Cargo CD-02 ou equivalente'  # sem sufixo
        assert substituto.ativo is False  # soft-delete
        # anexo do substituto foi repontado ao titular com papel substituto
        assert anexo_sub.rol_saber_competencia_id == titular.id
        assert anexo_sub.papel == 'substituto'
        # o Requisito V passa a ter 1 item ativo (o titular canônico)
        assert RolSaberCompetencia.objects.filter(grupo__requisito__numero=5, ativo=True).count() == 1
