"""Testa que o campo de descrição do Projeto usa o widget TinyMCE."""

from __future__ import annotations

import pytest
from tinymce.widgets import TinyMCE

from gerenciador_projetos.forms import ProjetoForm
from gerenciador_projetos.models import Projeto


class TestProjetoFormTextoRico:
    def test_campo_descricao_usa_tinymce(self):
        form = ProjetoForm()
        assert isinstance(form.fields['descricao'].widget, TinyMCE)

    def test_campos_situacao_e_visibilidade_usam_radiobutton(self):
        from django import forms as django_forms

        form = ProjetoForm(instance=Projeto(pk=1))  # instance com pk simula edição, onde 'situacao' fica visível
        assert isinstance(form.fields['situacao'].widget, django_forms.RadioSelect)
        assert isinstance(form.fields['visibilidade'].widget, django_forms.RadioSelect)
