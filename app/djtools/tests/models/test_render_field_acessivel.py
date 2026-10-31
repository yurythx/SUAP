"""``render_field`` liga erro e ajuda ao widget (WCAG 1.3.1, 3.3.1) — DB-free."""

from types import SimpleNamespace

from django import forms

from djtools.forms.utils import render_field, render_form
from djtools.forms.widgets.select import CheckboxSelectMultiplePlus, RenderableSelectMultiple


class _Form(forms.Form):
    nome = forms.CharField(help_text='Nome completo.')
    apelido = forms.CharField(required=False, help_text='Opcional.', widget=forms.TextInput(attrs={'aria-describedby': 'dica_externa'}))
    turno = forms.ChoiceField(choices=[('m', 'Manhã'), ('t', 'Tarde')], widget=forms.RadioSelect)


def test_campo_invalido_liga_erro_e_ajuda_ao_widget() -> None:
    html = render_field(_Form(data={}), 'nome')
    assert 'aria-invalid="true"' in html
    assert 'aria-required="true"' in html
    assert 'aria-describedby="id_nome_erro id_nome_ajuda"' in html
    assert '<ul class="errorlist" id="id_nome_erro">' in html
    assert '<p class="help" id="id_nome_ajuda">Nome completo.</p>' in html


def test_campo_valido_aponta_so_para_a_ajuda() -> None:
    html = render_field(_Form(data={'nome': 'Ana', 'turno': 'm'}), 'nome')
    assert 'aria-invalid' not in html
    assert 'errorlist' not in html
    assert 'aria-describedby="id_nome_ajuda"' in html


def test_aria_describedby_existente_e_preservado() -> None:
    html = render_field(_Form(data={'nome': 'Ana', 'turno': 'm'}), 'apelido')
    assert 'aria-describedby="dica_externa id_apelido_ajuda"' in html


def test_form_sem_auto_id_nao_aponta_para_id_inexistente() -> None:
    html = render_field(_Form(data={}, auto_id=False), 'nome')
    assert 'aria-invalid="true"' in html
    assert 'aria-describedby' not in html
    assert '_erro' not in html


def test_radioselect_invalido_renderiza_com_aria_invalid() -> None:
    html = render_field(_Form(data={}), 'turno')
    assert html.count('aria-invalid="true"') == 2  # uma por opção
    assert 'aria-required' not in html  # proibido em role=radio
    assert 'id="id_turno_erro"' in html


def test_checkbox_multiplo_obrigatorio_nao_leva_aria_required_em_cada_opcao() -> None:
    class _ComCheckboxes(forms.Form):
        dias = forms.MultipleChoiceField(choices=[('s', 'Segunda'), ('t', 'Terça')], widget=CheckboxSelectMultiplePlus)

    html = render_field(_ComCheckboxes(data={}), 'dias')
    assert html.count('type="checkbox"') == 2
    assert 'aria-required' not in html  # proibido em role=checkbox (axe aria-allowed-attr)
    assert html.count('aria-invalid="true"') == 2  # uma por opção


def test_tabela_de_checkboxes_obrigatoria_nao_leva_aria_required_em_cada_opcao() -> None:
    class _ComTabela(forms.Form):
        componentes = forms.MultipleChoiceField(widget=RenderableSelectMultiple('widgets/componentes_widget.html'))

    form = _ComTabela(data={})
    # O widget lê `choices.queryset`; objetos com `pk` bastam e o teste fica sem banco.
    form.fields['componentes'].widget.choices = SimpleNamespace(queryset=[SimpleNamespace(pk=1), SimpleNamespace(pk=2)])
    html = render_field(form, 'componentes')
    assert html.count('type="checkbox"') == 3  # 2 opções + o "marcar todos" do template
    assert 'aria-required' not in html  # proibido em role=checkbox (axe aria-allowed-attr)


def test_campo_oculto_sai_sem_label_nem_ajuda() -> None:
    class _ComOculto(forms.Form):
        token = forms.CharField(widget=forms.HiddenInput, help_text='não aparece')

    html = render_field(_ComOculto(), 'token')
    assert html.startswith('<input type="hidden"')
    assert 'help' not in html


def test_fieldset_nomeado_vira_legend_com_h3() -> None:
    class _ComFieldset(forms.Form):
        nome = forms.CharField()
        fieldsets = (('Dados pessoais', {'fields': ('nome',)}),)

    html = render_form(_ComFieldset())
    assert '<legend><h3>Dados pessoais</h3></legend>' in html
    assert '<h2>' not in html
