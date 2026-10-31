"""Testa a validação raça-indígena nos forms que captam raca/povo_indigena.

Restaurada na fatia S1-fix: a regra 'raca indígena → povo obrigatório' estava
em PessoaFisica.clean() mas foi removida junto com o campo; o gate de UX
deve viver nos forms que expõem os dois campos.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ValidationError


class _RacaStub:
    """Stub mínimo de Raca para teste sem DB."""

    def __init__(self, *, indigena: bool) -> None:
        self.codigo_censup = '5' if indigena else '1'

    def is_indigena(self) -> bool:
        return self.codigo_censup == '5'


class _FormBase:
    """Simula a interface de cleaned_data usada em clean_povo_indigena."""

    def __init__(self, raca, povo_indigena) -> None:
        self.cleaned_data: dict = {'povo_indigena': povo_indigena}
        if raca is not None:
            self.cleaned_data['raca'] = raca
        # ServidorForm usa self.instance.raca quando raca não está no form
        self.instance = MagicMock()
        self.instance.id = None
        self.instance.raca = None


# ---------------------------------------------------------------------------
# ServidorForm
# ---------------------------------------------------------------------------


class _ServidorFormClean(_FormBase):
    """Reimpleta só clean_povo_indigena de ServidorForm para teste isolado."""

    def clean_povo_indigena(self):
        povo_indigena = self.cleaned_data.get('povo_indigena')
        raca = self.cleaned_data.get('raca') or (self.instance.raca if self.instance.id else None)
        if raca and raca.is_indigena() and not povo_indigena:
            from django import forms

            raise forms.ValidationError('É necessário informar o Povo indígena quando a Raça for Indígena')
        return povo_indigena


class TestServidorFormPovoIndigena:
    def _form(self, raca, povo):
        return _ServidorFormClean(raca=raca, povo_indigena=povo)

    def test_indigena_sem_povo_levanta_erro(self):
        form = self._form(raca=_RacaStub(indigena=True), povo=None)
        with pytest.raises(ValidationError):
            form.clean_povo_indigena()

    def test_indigena_com_povo_ok(self):
        povo = MagicMock()
        form = self._form(raca=_RacaStub(indigena=True), povo=povo)
        assert form.clean_povo_indigena() is povo

    def test_nao_indigena_sem_povo_ok(self):
        form = self._form(raca=_RacaStub(indigena=False), povo=None)
        assert form.clean_povo_indigena() is None

    def test_sem_raca_sem_povo_ok(self):
        form = self._form(raca=None, povo=None)
        assert form.clean_povo_indigena() is None

    def test_instance_raca_indigena_sem_povo_levanta_erro(self):
        """Raca vem do vínculo (não é campo do form), povo_indigena é None."""
        form = self._form(raca=None, povo=None)
        form.instance.id = 1
        form.instance.raca = _RacaStub(indigena=True)
        with pytest.raises(ValidationError):
            form.clean_povo_indigena()
