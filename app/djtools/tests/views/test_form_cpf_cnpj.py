"""CPF/CNPJ com todos os dígitos iguais nos formulários (#17410).

A sequência repetida (000.000.000-00, 00.000.000/0000-00...) é recusada quando o valor é
digitado ou alterado. Registro legado que já tem esse valor salva normalmente se o usuário
não mexeu no campo — senão ninguém consegue editar os ~9 mil cadastros que já estão assim.
"""

from __future__ import annotations

import pytest
from django import forms

from djtools.forms.fields import BrCnpjField, BrCpfCnpjField, BrCpfField
from eventos.models import Participante


class _FormCpf(forms.Form):
    cpf = BrCpfField()


class _FormCnpj(forms.Form):
    cnpj = BrCnpjField()


class _FormDocumento(forms.Form):
    documento = BrCpfCnpjField()


def _valido(form_class: type[forms.Form], campo: str, valor: str, inicial: str | None = None) -> bool:
    initial = {campo: inicial} if inicial is not None else None
    return form_class(data={campo: valor}, initial=initial).is_valid()


@pytest.mark.parametrize(
    ('form_class', 'campo', 'repetido', 'outro_repetido', 'valido'),
    [
        (_FormCpf, 'cpf', '000.000.000-00', '111.111.111-11', '123.456.789-09'),
        (_FormCnpj, 'cnpj', '00.000.000/0000-00', '11.111.111/1111-11', '11.444.444/0001-32'),
        (_FormDocumento, 'documento', '00000000000', '11111111111', '12345678909'),
        (_FormDocumento, 'documento', '00000000000000', '11111111111111', '11444444000132'),
    ],
)
class TestSequenciaRepetidaNoForm:
    def test_cadastro_novo_com_sequencia_e_recusado(
        self, form_class: type[forms.Form], campo: str, repetido: str, outro_repetido: str, valido: str
    ) -> None:
        assert not _valido(form_class, campo, repetido)

    def test_legado_sem_alterar_o_campo_salva(
        self, form_class: type[forms.Form], campo: str, repetido: str, outro_repetido: str, valido: str
    ) -> None:
        assert _valido(form_class, campo, repetido, inicial=repetido)

    def test_alterar_para_outra_sequencia_e_recusado(
        self, form_class: type[forms.Form], campo: str, repetido: str, outro_repetido: str, valido: str
    ) -> None:
        assert not _valido(form_class, campo, outro_repetido, inicial=repetido)

    def test_valor_valido_passa(self, form_class: type[forms.Form], campo: str, repetido: str, outro_repetido: str, valido: str) -> None:
        assert _valido(form_class, campo, valido, inicial=repetido)


class _ParticipanteForm(forms.ModelForm):
    class Meta:
        model = Participante
        fields = ['cpf']


@pytest.mark.django_db
class TestModelFormComCpfLegado:
    """ModelForm (o caminho do admin): o inicial vem da instância."""

    def test_editar_sem_mexer_no_cpf_legado_salva(self) -> None:
        form = _ParticipanteForm(data={'cpf': '000.000.000-00'}, instance=Participante(cpf='000.000.000-00'))
        assert form.is_valid(), form.errors
        assert form.cleaned_data['cpf'] == '000.000.000-00'

    def test_trocar_para_outra_sequencia_e_recusado(self) -> None:
        form = _ParticipanteForm(data={'cpf': '111.111.111-11'}, instance=Participante(cpf='000.000.000-00'))
        assert not form.is_valid()
        assert form.errors['cpf'] == ['Favor, informar um CPF válido.']

    def test_cadastro_novo_com_sequencia_e_recusado(self) -> None:
        assert not _ParticipanteForm(data={'cpf': '000.000.000-00'}).is_valid()

    def test_cpf_valido_passa(self) -> None:
        form = _ParticipanteForm(data={'cpf': '12345678909'}, instance=Participante(cpf='000.000.000-00'))
        assert form.is_valid(), form.errors
        assert form.cleaned_data['cpf'] == '123.456.789-09'
