from decimal import Decimal
from types import SimpleNamespace

import pytest

from rsc_tae.models import GrupoSaberCompetencia, RolSaberCompetencia, Requisito
from rsc_tae.models.anexo import taxa_por_papel, pontos_anexo, pontos_item_anexos


@pytest.mark.django_db(databases='__all__')
class TestCamposPapel:
    ATORES = ('servidor_a',)

    def test_item_aceita_papel_com_taxa_substituto(self):
        req = Requisito.objects.create(numero=99, descricao='X', descricao_curta='X', numeral_romano='X')
        grupo = GrupoSaberCompetencia.objects.create(requisito=req, numero=1, pontuacao_unidade=Decimal('9.000'), descricao='g')
        item = RolSaberCompetencia.objects.create(
            numero=1,
            grupo=grupo,
            titulo='CD-02',
            descricao='d',
            unidade_medida='ano',
            item_temporal=True,
            aceita_papel=True,
            pontuacao_unidade_substituto=Decimal('4.500'),
        )
        assert item.aceita_papel is True
        assert item.pontuacao_unidade == Decimal('9.000')  # titular vem do grupo
        assert item.pontuacao_unidade_substituto == Decimal('4.500')


class _ItemFake:
    # Espelha as constantes de papel expostas por RolSaberCompetencia (Task 1).
    PAPEL_TITULAR = 'titular'
    PAPEL_SUBSTITUTO = 'substituto'

    def __init__(self, temporal, aceita, tit, sub):
        self.item_temporal = temporal
        self.aceita_papel = aceita
        self.pontuacao_unidade = tit
        self.pontuacao_unidade_substituto = sub


def test_taxa_por_papel_usa_substituto():
    item = _ItemFake(True, True, Decimal('9'), Decimal('4.5'))
    assert taxa_por_papel(item, 'titular') == Decimal('9')
    assert taxa_por_papel(item, 'substituto') == Decimal('4.5')


def test_taxa_item_sem_papel_ignora_substituto():
    item = _ItemFake(True, False, Decimal('9'), None)
    assert taxa_por_papel(item, 'substituto') == Decimal('9')  # aceita_papel=False -> sempre titular


def test_pontos_item_soma_por_papel():
    item = _ItemFake(True, True, Decimal('9'), Decimal('4.5'))
    # 13 meses -> 1 ano pontuável (fração <=6? 13-12=1 -> 1 ano); 7 meses -> 1 ano
    anexos = [
        SimpleNamespace(pontuacao=Decimal('13'), papel='titular'),
        SimpleNamespace(pontuacao=Decimal('7'), papel='substituto'),
    ]
    # titular: 1*9=9 ; substituto: 1*4.5=4.5 ; total=13.5
    assert pontos_item_anexos(item, anexos) == Decimal('13.5')


# --------------------------------------------------------------------------- #
# Task 3 — agregação por papel nos sites de cálculo (categorias A e B)         #
# --------------------------------------------------------------------------- #


class _ItemFakeId:
    PAPEL_TITULAR = 'titular'
    PAPEL_SUBSTITUTO = 'substituto'

    def __init__(self, id, temporal, aceita, tit, sub):
        self.id = id
        self.item_temporal = temporal
        self.aceita_papel = aceita
        self.pontuacao_unidade = tit
        self.pontuacao_unidade_substituto = sub


def _anexo_fake(pontuacao, papel=None, id=1):
    return SimpleNamespace(id=id, pontuacao=Decimal(str(pontuacao)), papel=papel)


def _nivel_fake(min_pontos='0', min_itens=0):
    return SimpleNamespace(pontuacao_minima=Decimal(min_pontos), numero_minimo_itens=min_itens)


def _processo_fake(nivel, saldo='0'):
    return SimpleNamespace(saldo_pontuacao_anterior=Decimal(saldo), nivel_requisitado=nivel)


def test_resumo_por_pontos_par_conta_um_item_e_soma_por_papel():
    """Categoria A: uma RolSaberCompetencia (aceita_papel) com 2 anexos (titular+substituto)
    conta como 1 item e soma os pontos pelas duas taxas."""
    from rsc_tae.views._helpers import _calcular_resumo_por_pontos

    item = _ItemFakeId(1, True, True, Decimal('9'), Decimal('4.5'))
    anexos = {1: [_anexo_fake(13, 'titular', 1), _anexo_fake(13, 'substituto', 2)]}  # 13 meses -> 1 ano cada
    resumo = _calcular_resumo_por_pontos(_processo_fake(_nivel_fake()), [item], {}, anexos)
    assert resumo['itens_preenchidos'] == 1
    assert resumo['total_pontos_itens'] == Decimal('13.5')  # 1*9 + 1*4.5


def test_resumo_por_pontos_item_sem_papel_regressao():
    """Invariante: item temporal SEM papel mantém o cálculo antigo (taxa única)."""
    from rsc_tae.views._helpers import _calcular_resumo_por_pontos

    item = _ItemFakeId(2, True, False, Decimal('9'), None)
    anexos = {2: [_anexo_fake(13, None, 1), _anexo_fake(13, None, 2)]}  # 1 ano cada, taxa 9
    resumo = _calcular_resumo_por_pontos(_processo_fake(_nivel_fake()), [item], {}, anexos)
    assert resumo['itens_preenchidos'] == 1
    assert resumo['total_pontos_itens'] == Decimal('18')  # 2*9 (idêntico ao antigo)


def test_pontos_item_validados_por_papel():
    """Categoria B: pontos validados (avaliador) somam pela taxa do papel de cada anexo."""
    from rsc_tae.enums import SituacaoAvaliacaoItem
    from rsc_tae.views.processo import _pontos_item

    item = _ItemFakeId(1, True, True, Decimal('9'), Decimal('4.5'))
    linha = {'item': item, 'anexos': [_anexo_fake(13, 'titular', 10), _anexo_fake(13, 'substituto', 11)]}
    av = {
        10: SimpleNamespace(situacao=SituacaoAvaliacaoItem.DEFERIDO, pontuacao_validada=Decimal('13')),
        11: SimpleNamespace(situacao=SituacaoAvaliacaoItem.DEFERIDO, pontuacao_validada=Decimal('13')),
    }
    assert _pontos_item(linha, av) == Decimal('13.5')  # 1*9 + 1*4.5


def test_pontos_item_sem_papel_regressao():
    """Invariante categoria B: item sem papel mantém a taxa única."""
    from rsc_tae.enums import SituacaoAvaliacaoItem
    from rsc_tae.views.processo import _pontos_item

    item = _ItemFakeId(2, True, False, Decimal('9'), None)
    linha = {'item': item, 'anexos': [_anexo_fake(13, None, 10), _anexo_fake(13, None, 11)]}
    av = {
        10: SimpleNamespace(situacao=SituacaoAvaliacaoItem.DEFERIDO, pontuacao_validada=Decimal('13')),
        11: SimpleNamespace(situacao=SituacaoAvaliacaoItem.DEFERIDO, pontuacao_validada=Decimal('13')),
    }
    assert _pontos_item(linha, av) == Decimal('18')  # 2*9


def test_corrigir_pontos_temporais_por_papel():
    """A correção temporal da avaliação usa a taxa do papel de cada anexo (não anula o ajuste)."""
    from rsc_tae.views._helpers import corrigir_pontos_temporais_avaliacao

    item = _ItemFakeId(1, True, True, Decimal('9'), Decimal('4.5'))
    a_tit = SimpleNamespace(id=1, pontuacao=Decimal('13'), papel='titular', avaliacao_anexo=None, avaliacoes_todos=[])
    a_sub = SimpleNamespace(id=2, pontuacao=Decimal('13'), papel='substituto', avaliacao_anexo=None, avaliacoes_todos=[])
    ln = {'item': item, 'anexos': [a_tit, a_sub]}
    ctx = {'linhas_avaliacao': [ln]}
    corrigir_pontos_temporais_avaliacao(ctx)
    assert a_tit.pontos_requeridos == Decimal('9')  # 1 ano * 9
    assert a_sub.pontos_requeridos == Decimal('4.5')  # 1 ano * 4.5
    assert ln['total_pontos_requeridos_item'] == Decimal('13.5')


def test_aplicar_notas_consolidadas_por_papel():
    """A nota consolidada da CRSC é exibida na taxa do papel de cada anexo."""
    from rsc_tae.views._helpers import aplicar_notas_consolidadas_crsc

    item = _ItemFakeId(1, True, True, Decimal('9'), Decimal('4.5'))
    a_tit = SimpleNamespace(id=1, papel='titular')
    a_sub = SimpleNamespace(id=2, papel='substituto')
    ctx = {'linhas_avaliacao': [{'item': item, 'anexos': [a_tit, a_sub]}]}
    divergencias = [
        {'anexo': SimpleNamespace(id=1), 'status_deliberacao': {'fechado': True, 'nota_consolidada': Decimal('1')}},
        {'anexo': SimpleNamespace(id=2), 'status_deliberacao': {'fechado': True, 'nota_consolidada': Decimal('1')}},
    ]
    aplicar_notas_consolidadas_crsc(ctx, divergencias)
    assert a_tit.pontos_validados == Decimal('9')  # 1 * 9
    assert a_sub.pontos_validados == Decimal('4.5')  # 1 * 4.5


def test_enriquecer_anexos_memorial_por_papel():
    """Os pontos por-anexo do Memorial Descritivo (PDF oficial) usam a taxa do papel."""
    from rsc_tae.views._helpers import _enriquecer_anexos_memorial

    item = _ItemFakeId(1, True, True, Decimal('9'), Decimal('4.5'))
    a_tit = SimpleNamespace(pontuacao=Decimal('13'), papel='titular')
    a_sub = SimpleNamespace(pontuacao=Decimal('13'), papel='substituto')
    grupos = [{'linhas': [{'item': item, 'anexos': [a_tit, a_sub]}]}]
    _enriquecer_anexos_memorial(grupos)
    assert a_tit.pontos_no_item == Decimal('9')  # 1 ano * 9
    assert a_sub.pontos_no_item == Decimal('4.5')  # 1 ano * 4,5


@pytest.mark.django_db(databases='__all__')
class TestPontosFinaisPorItem:
    """Cobre _pontos_finais_por_item (decide deferido/indeferido e alimenta os documentos oficiais)."""

    ATORES = ('servidor_a',)

    def test_pontos_finais_por_item_por_papel(self, atores):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from rsc_tae.models import Nivel, ProcessoRSCTae, RolSaberCompetenciaAnexo
        from rsc_tae.views._helpers import _pontos_finais_por_item

        req = Requisito.objects.create(numero=95, descricao='V', descricao_curta='V', numeral_romano='V')
        grupo = GrupoSaberCompetencia.objects.create(requisito=req, numero=1, pontuacao_unidade=Decimal('9.000'), descricao='g')
        item = RolSaberCompetencia.objects.create(
            numero=1,
            grupo=grupo,
            titulo='CD-02',
            descricao='d',
            unidade_medida='ano',
            item_temporal=True,
            aceita_papel=True,
            pontuacao_unidade_substituto=Decimal('4.500'),
        )
        nivel = Nivel.objects.create(nome='N', numero_minimo_itens=0, pontuacao_minima=0)
        processo = ProcessoRSCTae.objects.create(vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=nivel)
        RolSaberCompetenciaAnexo.objects.create(
            processo=processo,
            rol_saber_competencia=item,
            arquivo=SimpleUploadedFile('t.pdf', b'%PDF-1.4', content_type='application/pdf'),
            pontuacao=Decimal('13'),
            papel='titular',
        )
        RolSaberCompetenciaAnexo.objects.create(
            processo=processo,
            rol_saber_competencia=item,
            arquivo=SimpleUploadedFile('t2.pdf', b'%PDF-1.4', content_type='application/pdf'),
            pontuacao=Decimal('13'),
            papel='substituto',
        )
        pontos = _pontos_finais_por_item(processo, {})
        assert pontos[item.id] == Decimal('13.5')  # 1 ano * 9 (titular) + 1 ano * 4,5 (substituto)


# --------------------------------------------------------------------------- #
# Task 4 — captura/validação de ``papel`` no upload/edição do anexo (API)      #
# --------------------------------------------------------------------------- #

_PDF = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'


def _arquivo_pdf(nome='doc.pdf'):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(nome, _PDF, content_type='application/pdf')


@pytest.mark.django_db(databases='__all__')
class TestPapelUploadEdicaoAPI:
    """Requisito V: o papel (titular/substituto) é capturado e validado no upload/edição do anexo."""

    ATORES = ('servidor_a',)

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        from rsc_tae.models import Nivel, ProcessoRSCTae, RolSaberCompetenciaAnexo

        self.RolSaberCompetenciaAnexo = RolSaberCompetenciaAnexo

        req = Requisito.objects.create(numero=95, descricao='V', descricao_curta='V', numeral_romano='V')
        grupo = GrupoSaberCompetencia.objects.create(requisito=req, numero=1, pontuacao_unidade=Decimal('9.000'), descricao='g')
        self.item = RolSaberCompetencia.objects.create(
            numero=1,
            grupo=grupo,
            titulo='CD-02',
            descricao='d',
            unidade_medida='ano',
            item_temporal=True,
            aceita_papel=True,
            pontuacao_unidade_substituto=Decimal('4.500'),
        )
        self.item_sem_papel = RolSaberCompetencia.objects.create(
            numero=2,
            grupo=grupo,
            titulo='outro',
            descricao='d',
            unidade_medida='ano',
            item_temporal=True,
            aceita_papel=False,
        )
        nivel = Nivel.objects.create(nome='N', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=nivel)
        self.client.login(user=self.servidor_a.get_user())

    def _upload_url(self, item):
        return f'/rsc_tae/processo/{self.processo.id}/item/{item.id}/anexos/upload/'

    def _salvar_url(self, anexo):
        return f'/rsc_tae/processo/{self.processo.id}/anexo/{anexo.id}/salvar_pontuacao/'

    def _criar_anexo(self, papel=None):
        return self.RolSaberCompetenciaAnexo.objects.create(
            processo=self.processo,
            rol_saber_competencia=self.item,
            arquivo=_arquivo_pdf(),
            pontuacao=Decimal('13'),
            data_inicio='2020-01-01',
            data_fim='2021-01-31',
            papel=papel,
        )

    # ---- upload -----------------------------------------------------------

    def test_upload_sem_papel_salva_none(self):
        resp = self.client.post(
            self._upload_url(self.item),
            data={'arquivo': _arquivo_pdf(), 'data_inicio': '2020-01-01', 'data_fim': '2021-01-31'},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body['ok'] is True
        assert body['anexo']['papel'] == ''  # serializa papel quando aceita_papel
        anexo = self.RolSaberCompetenciaAnexo.objects.get(pk=body['anexo']['id'])
        assert anexo.papel is None

    def test_upload_papel_substituto(self):
        resp = self.client.post(
            self._upload_url(self.item),
            data={'arquivo': _arquivo_pdf(), 'papel': 'substituto', 'data_inicio': '2020-01-01', 'data_fim': '2021-01-31'},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body['anexo']['papel'] == 'substituto'
        anexo = self.RolSaberCompetenciaAnexo.objects.get(pk=body['anexo']['id'])
        assert anexo.papel == 'substituto'
        # 13 meses -> 1 ano pontuável; taxa substituto 4,5
        assert body['pontuacao_total_item'] == '4.500'

    def test_upload_papel_invalido_retorna_400(self):
        resp = self.client.post(
            self._upload_url(self.item),
            data={'arquivo': _arquivo_pdf(), 'papel': 'chefe'},
        )
        assert resp.status_code == 400
        assert resp.json()['msg'] == 'Papel inválido.'
        assert not self.RolSaberCompetenciaAnexo.objects.filter(rol_saber_competencia=self.item).exists()

    def test_upload_item_sem_papel_forca_none(self):
        resp = self.client.post(
            self._upload_url(self.item_sem_papel),
            data={'arquivo': _arquivo_pdf(), 'papel': 'titular', 'data_inicio': '2020-01-01', 'data_fim': '2021-01-31'},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert 'papel' not in body['anexo']  # item sem papel não serializa o campo
        anexo = self.RolSaberCompetenciaAnexo.objects.get(pk=body['anexo']['id'])
        assert anexo.papel is None

    # ---- edição (salvar_pontuacao) ---------------------------------------

    def test_edicao_define_papel(self):
        anexo = self._criar_anexo(papel=None)
        resp = self.client.post(
            self._salvar_url(anexo),
            data={'papel': 'titular', 'data_inicio': '2020-01-01', 'data_fim': '2021-01-31'},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body['papel'] == 'titular'
        anexo.refresh_from_db()
        assert anexo.papel == 'titular'

    def test_edicao_papel_invalido_retorna_400(self):
        anexo = self._criar_anexo(papel='titular')
        resp = self.client.post(
            self._salvar_url(anexo),
            data={'papel': 'gerente', 'data_inicio': '2020-01-01', 'data_fim': '2021-01-31'},
        )
        assert resp.status_code == 400
        assert resp.json()['msg'] == 'Papel inválido.'
        anexo.refresh_from_db()
        assert anexo.papel == 'titular'  # não altera em erro

    def test_edicao_sem_campo_papel_preserva(self):
        anexo = self._criar_anexo(papel='substituto')
        resp = self.client.post(
            self._salvar_url(anexo),
            data={'data_inicio': '2020-01-01', 'data_fim': '2021-01-31'},
        )
        assert resp.status_code == 200
        anexo.refresh_from_db()
        assert anexo.papel == 'substituto'  # ausência do campo não apaga o papel


def test_conclusao_exige_papel_no_requisito_v():
    """Item aceita_papel com anexo sem papel bloqueia a conclusão do preenchimento."""
    from rsc_tae.views.processo import _erro_conclusao_anexos

    item = _ItemFakeId(1, True, True, Decimal('9'), Decimal('4.5'))
    anexo = SimpleNamespace(id=1, pontuacao=Decimal('5'), descricao='doc', papel=None, rol_saber_competencia=item)
    erro = _erro_conclusao_anexos([item], {}, {1: [anexo]})
    assert erro is not None
    assert 'papel' in erro.lower()


def test_conclusao_com_papel_preenchido_ok():
    from rsc_tae.views.processo import _erro_conclusao_anexos

    item = _ItemFakeId(1, True, True, Decimal('9'), Decimal('4.5'))
    anexo = SimpleNamespace(id=1, pontuacao=Decimal('5'), descricao='doc', papel='titular', rol_saber_competencia=item)
    assert _erro_conclusao_anexos([item], {}, {1: [anexo]}) is None


def test_conclusao_item_sem_papel_nao_exige():
    """Item que não aceita papel não é bloqueado por papel ausente."""
    from rsc_tae.views.processo import _erro_conclusao_anexos

    item = _ItemFakeId(2, False, False, Decimal('2'), None)
    anexo = SimpleNamespace(id=1, pontuacao=Decimal('5'), descricao='doc', papel=None, rol_saber_competencia=item)
    assert _erro_conclusao_anexos([item], {}, {1: [anexo]}) is None
