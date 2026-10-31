"""Testa que o campo de descrição da Tarefa usa o widget TinyMCE."""

from __future__ import annotations

import pytest
from tinymce.widgets import TinyMCE

from gerenciador_projetos.enums import VisibilidadeProjeto
from gerenciador_projetos.forms import TarefaFormFactory
from gerenciador_projetos.models import Projeto
from rh.models import UnidadeOrganizacional


class TestTarefaFormTextoRico:
    def test_campo_descricao_usa_tinymce(self):
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        FormClass = TarefaFormFactory(request=None, projeto=projeto)
        form = FormClass()
        assert isinstance(form.fields['descricao'].widget, TinyMCE)

    def test_campos_situacao_e_prioridade_usam_radiobutton(self):
        from django import forms as django_forms

        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        FormClass = TarefaFormFactory(request=None, projeto=projeto)
        form = FormClass()
        assert isinstance(form.fields['situacao'].widget, django_forms.RadioSelect)
        assert isinstance(form.fields['prioridade'].widget, django_forms.RadioSelect)


class TestQuerysetObservadores:
    def _projeto(self, visibilidade: str) -> Projeto:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        return Projeto.objects.create(
            titulo='Projeto',
            descricao='desc',
            uo=uo,
            criado_por=self.user_admin,
            visibilidade=visibilidade,
        )

    def test_projeto_privado_permite_somente_membros(self) -> None:
        projeto = self._projeto(VisibilidadeProjeto.PRIVADO)
        projeto.membros.add(self.user_admin)

        FormClass = TarefaFormFactory(request=None, projeto=projeto)
        form = FormClass()

        assert list(form.fields['observadores'].queryset) == [self.user_admin]

    def test_projeto_publico_permite_servidor_nao_membro(self) -> None:
        projeto = self._projeto(VisibilidadeProjeto.PUBLICO)

        FormClass = TarefaFormFactory(request=None, projeto=projeto)
        form = FormClass()

        assert self.user_admin in form.fields['observadores'].queryset
