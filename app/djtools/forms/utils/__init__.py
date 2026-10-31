from collections.abc import Mapping, Sequence

from django import forms
from django.forms.utils import flatatt
from django.utils.encoding import force_str, smart_str
from django.utils.html import conditional_escape
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

from djtools.forms.widgets.select import CheckboxSelectMultiplePlus, RenderableSelectMultiple
from djtools.templatetags.filters import format_


class BoundField:
    "A Field plus data"

    @staticmethod
    def _pretty_name(name):
        "Converts 'first_name' to 'First name'"
        name = name[0].upper() + name[1:]
        return name.replace('_', ' ')

    def __init__(self, form, field, name):
        self.form = form
        self.field = field
        self.name = name
        self.html_name = form.add_prefix(name)
        self.html_initial_name = form.add_initial_prefix(name)
        if self.field.label is None:
            self.label = self._pretty_name(name)
        else:
            self.label = self.field.label
        self.help_text = field.help_text or ''

    def __str__(self):
        """Renders this field as an HTML widget."""
        if self.field.show_hidden_initial:
            return self.as_widget() + self.as_hidden(only_initial=True)
        return self.as_widget()

    def _errors(self):
        """
        Returns an ErrorList for this field. Returns an empty ErrorList
        if there are none.
        """
        return self.form.errors.get(self.name, self.form.error_class())

    errors = property(_errors)

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        """
        Renders the field by rendering the passed widget, adding any HTML
        attributes passed as attrs.  If no widget is specified, then the
        field's default widget will be used.
        """
        if not widget:
            widget = self.field.widget
        attrs = attrs or {}
        auto_id = self.auto_id
        if auto_id and 'id' not in attrs and 'id' not in widget.attrs:
            attrs['id'] = auto_id
        if not self.form.is_bound or (hasattr(self.form, 'is_wizard') and self.name not in self.form.data):
            data = self.form.initial.get(self.name, self.field.initial)
            if callable(data):
                data = data()
        else:
            if isinstance(self.field, forms.FileField) and self.data is None:
                data = self.form.initial.get(self.name, self.field.initial)
            else:
                data = self.data
        if not only_initial:
            name = self.html_name
        else:
            name = self.html_initial_name
        return widget.render(name, data, attrs=attrs)

    def as_text(self, attrs=None, **kwargs):
        """
        Returns a string of HTML for representing this as an <input type="text">.
        """
        return self.as_widget(forms.TextInput(), attrs, **kwargs)

    def as_textarea(self, attrs=None, **kwargs):
        "Returns a string of HTML for representing this as a <textarea>."
        return self.as_widget(forms.Textarea(), attrs, **kwargs)

    def as_hidden(self, attrs=None, **kwargs):
        """
        Returns a string of HTML for representing this as an <input type="hidden">.
        """
        return self.as_widget(self.field.hidden_widget(), attrs, **kwargs)

    def _data(self):
        """
        Returns the data for this BoundField, or None if it wasn't given.
        """
        return self.field.widget.value_from_datadict(self.form.data, self.form.files, self.html_name)

    data = property(_data)

    def label_tag(self, contents=None, attrs=None):
        """
        Wraps the given contents in a <label>, if the field has an ID attribute.
        Does not HTML-escape the contents. If contents aren't given, uses the
        field's HTML-escaped label.

        If attrs are given, they're used as HTML attributes on the <label> tag.
        """
        contents = contents or conditional_escape(self.label)
        widget = self.field.widget
        id_ = widget.attrs.get('id') or self.auto_id
        if id_:
            attrs = attrs and flatatt(attrs) or ''
            contents = f'<label for="{widget.id_for_label(id_)}"{attrs}>{contents!s}</label>'
        return mark_safe(contents)

    def _is_hidden(self):
        "Returns True if this BoundField's widget is hidden."
        return self.field.widget.is_hidden

    is_hidden = property(_is_hidden)

    def _auto_id(self):
        """
        Calculates and returns the ID attribute for this BoundField, if the
        associated Form has specified auto_id. Returns an empty string otherwise.
        """
        auto_id = self.form.auto_id
        if auto_id and '%s' in smart_str(auto_id):
            return smart_str(auto_id) % self.html_name
        elif auto_id:
            return self.html_name
        return ''

    auto_id = property(_auto_id)


def _label_do_campo(form: forms.BaseForm, bf: BoundField) -> str:
    if not bf.label:
        return ''
    label = conditional_escape(force_str(bf.label))
    # Só acrescenta o sufixo se o label não terminar em pontuação.
    if form.label_suffix and label[-1] not in ':?.!':
        label += form.label_suffix
    return bf.label_tag(label) or ''


def _bloco(tag: str, classe: str, id_: str, conteudo: str) -> str:
    """Monta ``<tag class=... [id=...]>conteudo</tag>``; o ``id`` só sai quando o campo tem id."""
    return f'<{tag} class="{classe}"{flatatt({"id": id_} if id_ else {})}>{conteudo}</{tag}>'


def _widget_acessivel(bf: BoundField, erros: list[str], ajuda: str) -> tuple[str, str, str]:
    """Devolve ``(erros_html, widget_html, ajuda_html)`` com o widget apontando, via
    ``aria-describedby``, para os ids do erro e da ajuda — só quando o campo tem id."""
    widget = bf.field.widget
    id_ = widget.attrs.get('id') or bf.auto_id
    id_erro = f'{id_}_erro' if id_ and erros else ''
    id_ajuda = f'{id_}_ajuda' if id_ and ajuda else ''
    attrs: dict[str, str] = {}
    descritores = ' '.join(filter(None, [widget.attrs.get('aria-describedby'), id_erro, id_ajuda]))
    if descritores:
        attrs['aria-describedby'] = descritores
    # Sem o atributo `required` nativo: ele dispararia a validação do browser antes da do servidor.
    # Radio/checkbox múltiplo ficam de fora: aria-required não é permitido em role=radio/checkbox (axe aria-allowed-attr).
    # O CheckboxSelectMultiple do Django herda de RadioSelect; os dois do djtools, de SelectMultiple.
    if bf.field.required and not isinstance(widget, (forms.RadioSelect, CheckboxSelectMultiplePlus, RenderableSelectMultiple)):
        attrs['aria-required'] = 'true'
    if erros:
        attrs['aria-invalid'] = 'true'
    erros_html = _bloco('ul', 'errorlist', id_erro, ''.join(f'<li>{erro}</li>' for erro in erros)) if erros else ''
    ajuda_html = _bloco('p', 'help', id_ajuda, ajuda) if ajuda else ''
    widget_html = bf.as_widget(attrs=attrs)
    if bf.field.show_hidden_initial:
        widget_html += bf.as_hidden(only_initial=True)
    return erros_html, widget_html, ajuda_html


def render_field(form: forms.BaseForm, field_name: str) -> SafeString:
    """Renderiza erros, label, widget e ajuda de um campo, ligados por ``aria-describedby``."""
    field = form.fields[field_name]
    if hasattr(field, 'reload'):
        field.reload()
    bf = BoundField(form, field, field_name)
    if bf.is_hidden:
        return mark_safe(str(bf))
    erros = [conditional_escape(erro) for erro in bf.errors]
    ajuda = force_str(field.help_text) if field.help_text else ''
    erros_html, widget_html, ajuda_html = _widget_acessivel(bf, erros, ajuda)
    return mark_safe(f'{erros_html}{_label_do_campo(form, bf)}{widget_html}{ajuda_html}')


def _campos_visiveis(form: forms.BaseForm) -> list[str]:
    """Campos do form sem ``fieldsets``: respeita ``Meta.fields``/``Meta.exclude`` para campos de model."""
    meta = getattr(form, '_meta', None)
    include_fields = meta.fields if meta and meta.fields else None
    exclude_fields = meta.exclude if meta and meta.exclude else None
    model = getattr(meta, 'model', None)
    model_fields = [model_field.name for model_field in model._meta.fields] if hasattr(model, '_meta') else None
    campos = []
    for nome_campo in list(form.fields.keys()):
        if model_fields and nome_campo in model_fields:
            if include_fields and nome_campo not in include_fields or exclude_fields and nome_campo in exclude_fields:
                continue
        campos.append(nome_campo)
    return campos


def _avisos(form: forms.BaseForm) -> list[str]:
    """Avisos fixos do form (``INFO``/``ALERT``/``CRITICAL``) e erros gerais, antes dos fieldsets."""
    out = []
    if hasattr(form, 'INFO'):
        out.append(f'<div class="alert alert-info"><strong>Atenção: </strong>{form.INFO}</div>')
    if hasattr(form, 'ALERT'):
        out.append(f'<div class="alert alert-warning"><strong>Atenção: </strong>{form.ALERT}</div>')
    if hasattr(form, 'CRITICAL'):
        out.append(f'<div class="alert alert-danger"><strong>Atenção: </strong>{form.CRITICAL}</div>')
    if form.non_field_errors():
        out.append('<ul class="errorlist">')
        out.extend(f'<li>{error}</li>' for error in form.non_field_errors())
        out.append('</ul>')
    return out


def _caixa_do_campo(form: forms.BaseForm, linha: Sequence[str], field_name: str) -> str:
    """``div`` de um campo dentro da linha, com as classes de posição e obrigatoriedade."""
    if field_name not in form.fields:
        raise KeyError(f'Field "{field_name}" not in form.')
    field_classes = []
    if len(linha) > 1:
        field_classes.append('field-box')
    field_classes.append('field-box-first' if field_name is linha[0] else 'field-box-later')
    if form.fields[field_name].required:
        field_classes.append('required')
    return f'<div class="{" ".join(field_classes)}">{render_field(form, field_name)}</div>'


def _linha(form: forms.BaseForm, line: str | Sequence[str]) -> str:
    """``div.form-row`` de uma linha do fieldset; campo oculto sai sem ``div`` e campo inexistente (string) é pulado."""
    if isinstance(line, str):
        field = form.fields.get(line)
        if field is None:
            return ''
        if isinstance(field.widget, forms.HiddenInput):
            # Hidden field has no div.form-row
            return render_field(form, line)
        line = [line]
    error_class = ''
    for field_name in line:
        try:
            if form.errors.get(field_name, form.error_class()):
                error_class = 'errors'
        except Exception:
            pass
    caixas = ''.join(_caixa_do_campo(form, line, field_name) for field_name in line)
    return f'<div class="form-row {" ".join(line)} {error_class}">{caixas}</div>'


def _fieldset(form: forms.BaseForm, fieldset_name: str | None, options: Mapping) -> str:
    """``fieldset`` com título (``legend > h3``), descrição e linhas."""
    classes = ' '.join(options.get('classes', ()))
    out = [f'<fieldset class="module aligned {classes}">']
    if fieldset_name:
        out.append(f'<legend><h3>{fieldset_name}</h3></legend>')
    fieldset_description = options.get('description', None)
    if fieldset_description:
        out.append(f'<div class="description">{fieldset_description}</div>')
    out.extend(_linha(form, line) for line in options['fields'])
    out.append('</fieldset>')
    return ''.join(out)


def render_form(form: forms.BaseForm) -> SafeString:
    """
     form.fieldsets = (
        (None, {
            'fields': ('url', 'title', 'content', 'sites')
        }),
        ('Advanced options', {
            'fields': (('enable_comments', 'registration_required'), ('template_name',))
        }),
        ('Name...', {
             'description': 'Description...',
             'classes': ('class1', 'class2', ...)
             'fields': (('field1', 'field2'), ('field3'), ...)
        }),
    )
    """
    fieldsets = form.fieldsets if hasattr(form, 'fieldsets') else [(None, {'fields': _campos_visiveis(form)})]
    out = _avisos(form)
    out.extend(_fieldset(form, nome, options) for nome, options in fieldsets)
    return mark_safe(''.join(out))


def show_form_data(form, data=None):
    data = data or form.data
    fieldsets = hasattr(form, 'fieldsets') and form.fieldsets or [(None, {'fields': list(form.fields.keys())})]

    out = []
    for fieldset_name, options in fieldsets:
        lines = options['fields']
        classes = ' '.join(options.get('classes', ()))
        fieldset_description = options.get('description', None)

        # Fieldset
        out.append(f'<fieldset class="module aligned {classes}">')
        if fieldset_name:
            out.append(f'<h2>{fieldset_name}</h2>')
        if fieldset_description:
            out.append(f'<div class="description">{fieldset_description}</div>')

        for line in lines:
            if isinstance(line, str):
                if isinstance(form.fields[line].widget, forms.HiddenInput):
                    continue
                else:
                    line = [line]

            out.append('<div class="form-row {line_classes} ">'.format(line_classes=' '.join(line)))

            for field_name in line:
                field_classes = []
                if len(line) > 1:
                    field_classes.append('field-box')
                if field_name is line[0]:
                    field_classes.append('field-box-first')
                else:
                    field_classes.append('field-box-later')
                if form.fields[field_name].required:
                    field_classes.append('required')
                out.append('<div class="{field_classes}">'.format(field_classes=' '.join(field_classes)))

                template = '<label style="padding-top: 0">%(label)s</label><span>%(value)s</span>'

                field = form.fields[field_name]

                if field.label:
                    label = field.label
                else:
                    label = ' '.join(field_name.split('_')).capitalize()

                if isinstance(field, forms.BooleanField):
                    value = form.cleaned_data.get(field_name) and _('Yes') or _('No')
                else:
                    value = format_(form.cleaned_data[field_name]) or '<em class="scarletred1">Não Informado</em>'
                if hasattr(field, 'choices'):
                    for c_id, c_val in field.choices:
                        if c_id == form.data[field_name]:
                            value = c_val
                out.append(template % {'label': label, 'value': value})

                out.append('</div>')

            out.append('</div>')

        out.append('</fieldset>')

    out = ''.join(out)
    return mark_safe(out)
