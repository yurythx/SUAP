from decimal import Decimal
from types import SimpleNamespace

from rsc_tae.enums import SituacaoDocumentoPreliminar
from rsc_tae.views._helpers import status_abas_preenchimento


def _resumo(total_pontos, pontos_minimos, itens_preenchidos, itens_minimos):
    return {
        'total_pontos': Decimal(total_pontos),
        'pontos_minimos': Decimal(pontos_minimos),
        'itens_preenchidos': itens_preenchidos,
        'itens_minimos': itens_minimos,
    }


def _status(processo=None, documento=None, situacao_doc=SituacaoDocumentoPreliminar.PENDENTE, resumo=None, requisito_obrigatorio=None):
    processo = processo or SimpleNamespace(declaracao_conformidade=False)
    resumo = resumo or _resumo('0.00', '0.00', 0, 0)
    requisito_obrigatorio = requisito_obrigatorio or {'aplicavel': False, 'alcancado': False, 'labels': []}
    # A função agora recebe o dict {tipo: doc} de documentos preliminares atuais; a situação de cada
    # documento é lida de doc.avaliacao.situacao (ver _documento_preliminar_situacao).
    if documento is None:
        documentos_preliminares_atuais = {1: None}
    else:
        documentos_preliminares_atuais = {1: SimpleNamespace(avaliacao=SimpleNamespace(situacao=situacao_doc))}
    return status_abas_preenchimento(processo, documentos_preliminares_atuais, resumo, requisito_obrigatorio)


class TestStatusAbasPreenchimento:
    """Unidade: indicador de 'aba concluída' (ícone de check) por aba do servidor."""

    # --- Documentos preliminares ---
    def test_documentos_ok_quando_anexado_e_nao_em_correcao(self):
        assert _status(documento=SimpleNamespace(), situacao_doc=SituacaoDocumentoPreliminar.PENDENTE)['documentos'] is True

    def test_documentos_pendente_quando_correcao_solicitada(self):
        assert _status(documento=SimpleNamespace(), situacao_doc=SituacaoDocumentoPreliminar.CORRECAO_SOLICITADA)['documentos'] is False

    def test_documentos_pendente_sem_documento(self):
        assert _status(documento=None)['documentos'] is False

    # --- Formulário ---
    def test_formulario_ok_quando_atinge_minimos(self):
        assert _status(resumo=_resumo('5.00', '3.00', 2, 1))['formulario'] is True

    def test_formulario_pendente_abaixo_dos_pontos(self):
        assert _status(resumo=_resumo('2.00', '3.00', 5, 1))['formulario'] is False

    def test_formulario_pendente_abaixo_dos_itens(self):
        assert _status(resumo=_resumo('9.00', '3.00', 0, 1))['formulario'] is False

    def test_formulario_ok_quando_nivel_sem_minimos(self):
        assert _status(resumo=_resumo('0.00', '0.00', 0, 0))['formulario'] is True

    def test_formulario_pendente_quando_requisito_obrigatorio_nao_alcancado(self):
        rn04 = {'aplicavel': True, 'alcancado': False, 'labels': ['IV - Produção técnica']}
        assert _status(resumo=_resumo('5.00', '3.00', 2, 1), requisito_obrigatorio=rn04)['formulario'] is False

    def test_formulario_ok_quando_requisito_obrigatorio_alcancado(self):
        rn04 = {'aplicavel': True, 'alcancado': True, 'labels': ['IV - Produção técnica']}
        assert _status(resumo=_resumo('5.00', '3.00', 2, 1), requisito_obrigatorio=rn04)['formulario'] is True

    # A aba Memorial/Declaração de Conformidade Legal deixou de existir — a declaração passou a ser
    # assinada no formulário de conclusão; status_abas_preenchimento retorna apenas documentos e formulario.
