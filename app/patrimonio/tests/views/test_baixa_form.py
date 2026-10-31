"""Testes da fábrica de formulários de baixa (``BaixaFormFactory``)."""

from unittest.mock import Mock

from patrimonio.forms import BaixaFormFactory


class TestBaixaFormFactory:
    """A fábrica é usada apenas pela edição, mas aceita ``instance=None`` na assinatura."""

    def test_sem_instancia_nao_estoura(self):
        """Sem instância, os campos não podem desreferenciar ``None`` (AttributeError do Sentry)."""
        campus = Mock(id=7)

        form = BaixaFormFactory(campus)()

        assert form.fields['tipo'].initial is None
        assert form.fields['uo'].initial == 7
        assert form.fields['unidade'].widget.attrs['value'] is campus

    def test_sem_instancia_e_sem_unidade_nao_estoura(self):
        """Usuário sem lotação (``get_uo`` retorna ``None``) também não pode estourar."""
        form = BaixaFormFactory(None)()

        assert form.fields['uo'].initial is None
        assert form.fields['unidade'].widget.attrs['value'] == ''

    def test_com_instancia_preenche_iniciais(self):
        """Na edição, os campos vêm da baixa e não da unidade do usuário logado."""
        baixa = Mock(tipo_id=3, uo_id=11, uo='Campus Natal', numero='123/2026', observacao='Baixa de teste')

        form = BaixaFormFactory(Mock(id=99), instance=baixa)()

        assert form.fields['tipo'].initial == 3
        assert form.fields['uo'].initial == 11
        assert form.fields['unidade'].widget.attrs['value'] == 'Campus Natal'
        assert form.fields['numero'].initial == '123/2026'
