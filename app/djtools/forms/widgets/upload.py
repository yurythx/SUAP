from django.conf import settings
from django.forms.widgets import (
    CheckboxInput,
    ClearableFileInput,
    Widget,
)
from django.template.context_processors import csrf
from django.template.defaultfilters import filesizeformat
from django.utils.safestring import mark_safe

from djtools.utils import (
    randomic,
    render_to_string,
)


class AjaxFileUploadWidget(Widget):
    class Media:
        js = ('/static/arquivo/js/fileuploader.js', '/static/arquivo/js/compatibility.js', '/static/arquivo/js/pdf.js')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params = {'csrf_name': 'csrfmiddlewaretoken', 'csrf_xname': 'X-CSRFToken'}
        self.options = {}

    def render(self, name, value=None, attrs=None, renderer=None):
        csrf_token = csrf(self.request).get('csrf_token')
        if csrf_token:
            csrf_token = csrf_token.encode().decode('utf-8')
        self.params['csrf_token'] = csrf_token

        context = {
            'id': randomic(),
            'url': self.url,
            'sizeLimit': self.sizeLimit,
            'allowedExtensions': self.allowedExtensions,
            'multiple': self.multiple,
            'params': self.params,
            'onCompleteUploadFunction': self.onCompleteUploadFunction,
        }
        context.update(self.options)
        if attrs:
            context.update(attrs)
        context['id'] = randomic()
        output = render_to_string('djtools/templates/ajaxfileupload_widget.html', context)
        return mark_safe(output)


class ClearableFileInputPlus(ClearableFileInput):
    template_name = 'widgets/clearable_file_input.html'
    max_file_size = settings.DEFAULT_FILE_UPLOAD_MAX_SIZE
    multiple = False
    extensions = None
    mimetypes = None

    def value_from_datadict(self, data, files, name):
        if self.multiple:
            if hasattr(files, 'getlist'):
                upload = files.getlist(name)
            else:
                upload = [files.get(name)]
        else:
            upload = files.get(name)
        if not self.is_required and CheckboxInput().value_from_datadict(data, files, self.clear_checkbox_name(name)):
            if upload:
                # If the user contradicts themselves (uploads a new file AND
                # checks the "clear" checkbox), we return a unique marker
                # object that FileField will turn into a ValidationError.
                return object()
            # False signals to clear any existing value, as opposed to just None
            return False

        return upload

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        checkbox_name = self.clear_checkbox_name(name)
        checkbox_id = self.clear_checkbox_id(checkbox_name)
        if self.multiple:
            attrs['multiple'] = 'multiple'
            attrs['class'] = 'multifileuploader'

        context['widget'].update(
            {
                'checkbox_name': checkbox_name,
                'checkbox_id': checkbox_id,
                'is_initial': self.is_initial(value),
                'input_text': self.input_text,
                'initial_text': self.initial_text,
                'clear_checkbox_label': self.clear_checkbox_label,
                'name': name,
                'value': value,
                'attrs': attrs,
                'max_file_size': self.max_file_size,
                'friendly_max_file_size': filesizeformat(self.max_file_size),
                'extensions': self.extensions,
                'extensions_display': self.extensions and ', '.join(self.extensions) or '',
                'mimetypes': self.mimetypes,
            }
        )
        return context


class PositionedPdfInput(ClearableFileInputPlus):
    def render(self, *args, **kwargs):
        widget = super().render(*args, **kwargs)
        html = render_to_string('djtools/templates/widgets/positioned_pdf_input.html', {'widget': widget, 'id': kwargs.get('attrs').get('id')})
        return html
