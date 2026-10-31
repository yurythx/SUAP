"""Regressão da anexação encadeada de processos (X anexado a Y, Y anexado a H).

``get_todos_documentos_processo``/``get_documentos_removidos`` iteravam só
``get_anexos()`` (1 nível), então H nunca herdava os documentos de X — só os
de Y. ``get_anexacoes_recursivas`` percorre a cadeia inteira em largura, e
``anexar()`` ganhou uma guarda contra ciclos usando o mesmo método.
"""

import pytest
from django.core.exceptions import ValidationError

from djtools.middleware import threadlocals as tl
from djtools.utils import get_datetime_now
from documento_eletronico.tests.factories import DocumentoTextoFactory
from processo_eletronico.models import Anexacao, DocumentoTextoProcesso
from processo_eletronico.tests.factories import ApensamentoFactory, ApensamentoProcessoFactory, ProcessoFactory
from rh.tests.factories import ServidorFactory


class TestAnexacaoProcessos:
    @pytest.fixture(autouse=True)
    def _setup(self, sync_permissions, setor_com_siorg):
        self.setor = setor_com_siorg
        self.autor = ServidorFactory(setor=setor_com_siorg).get_user()

    def _criar_processo(self):
        return ProcessoFactory(setor_criacao=self.setor, usuario_gerador=self.autor)

    def _adicionar_documento(self, processo, *, removido=False):
        tl.context.user = self.autor
        try:
            documento = DocumentoTextoFactory(setor_dono=self.setor, usuario_criacao=self.autor)
            vinculo = DocumentoTextoProcesso.objects.create(processo=processo, documento=documento)
            if removido:
                vinculo.data_hora_remocao = get_datetime_now()
                vinculo.save()
            return vinculo
        finally:
            tl.context.user = None

    def _anexar_diretamente(self, anexador, anexado):
        tl.context.user = self.autor
        try:
            return Anexacao.objects.create(processo_anexador=anexador, processo_anexado=anexado, justificativa_criacao='Teste')
        finally:
            tl.context.user = None

    @staticmethod
    def _ids_documentos(iteravel):
        return {item.documento_id for item in iteravel if hasattr(item, 'documento_id')}

    def test_anexacao_em_cadeia_propaga_documentos_do_processo_avo(self):
        x, y, h = self._criar_processo(), self._criar_processo(), self._criar_processo()
        doc_x = self._adicionar_documento(x)
        doc_y = self._adicionar_documento(y)
        doc_h = self._adicionar_documento(h)
        self._anexar_diretamente(y, x)
        self._anexar_diretamente(h, y)

        ids = self._ids_documentos(h.get_todos_documentos_processo())

        assert {doc_x.documento_id, doc_y.documento_id, doc_h.documento_id} <= ids

    def test_anexacao_em_cadeia_propaga_documentos_removidos(self):
        x, y, h = self._criar_processo(), self._criar_processo(), self._criar_processo()
        self._adicionar_documento(x)
        doc_removido_x = self._adicionar_documento(x, removido=True)
        self._adicionar_documento(y)
        self._adicionar_documento(h)
        self._anexar_diretamente(y, x)
        self._anexar_diretamente(h, y)

        ids = self._ids_documentos(h.get_documentos_removidos())

        assert doc_removido_x.documento_id in ids

    def test_anexacao_profundidade_maior_nao_para_cedo(self):
        processos = [self._criar_processo() for _ in range(5)]
        docs = [self._adicionar_documento(p) for p in processos]
        for anexador, anexado in zip(processos[1:], processos[:-1], strict=True):
            self._anexar_diretamente(anexador, anexado)
        topo = processos[-1]

        ids = self._ids_documentos(topo.get_todos_documentos_processo())

        assert {doc.documento_id for doc in docs} <= ids

    def test_anexar_processo_que_ja_esta_na_cadeia_levanta_erro(self):
        x, y, h = self._criar_processo(), self._criar_processo(), self._criar_processo()
        self._adicionar_documento(x)
        self._adicionar_documento(y)
        self._adicionar_documento(h)
        self._anexar_diretamente(h, y)
        self._anexar_diretamente(y, x)

        with pytest.raises(ValidationError):
            x.anexar(h, self.autor, 'Tentativa de ciclo')

    def test_anexar_processo_a_si_mesmo_levanta_erro(self):
        x = self._criar_processo()

        with pytest.raises(ValidationError):
            x.anexar(x, self.autor, 'Auto-anexação')

    def test_anexacao_recursiva_numero_de_queries_e_limitado(self, django_assert_num_queries):
        processos = [self._criar_processo() for _ in range(4)]
        for anexador, anexado in zip(processos[1:], processos[:-1], strict=True):
            self._anexar_diretamente(anexador, anexado)
        topo = processos[-1]

        # 3 anexações abaixo do topo: 3 níveis com resultado + 1 nível vazio que encerra o laço = 4 queries.
        with django_assert_num_queries(4):
            topo.get_anexacoes_recursivas()

    def test_anexacao_simples_continua_funcionando(self):
        y, h = self._criar_processo(), self._criar_processo()
        doc_y = self._adicionar_documento(y)
        doc_h = self._adicionar_documento(h)
        self._anexar_diretamente(h, y)

        ids = self._ids_documentos(h.get_todos_documentos_processo())

        assert {doc_y.documento_id, doc_h.documento_id} <= ids

    def test_processo_com_apensamento_vigente_nao_pode_ser_anexado(self):
        """Anexar um processo apensado deixa o apensamento ativo e trava o encaminhamento do anexador (#17774)."""
        anexador = self._criar_processo()
        livre, apensado, par_do_apensado, desapensado = (self._criar_processo() for _ in range(4))
        apensamento = ApensamentoFactory()
        ApensamentoProcessoFactory(apensamento=apensamento, processo=apensado)
        ApensamentoProcessoFactory(apensamento=apensamento, processo=par_do_apensado)
        ApensamentoProcessoFactory(processo=desapensado, data_hora_remocao=get_datetime_now())

        candidatos = set(anexador.get_processos_podem_ser_anexados(self.autor))

        assert {livre, desapensado} <= candidatos
        assert not {apensado, par_do_apensado} & candidatos
