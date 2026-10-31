from django.forms.widgets import (
    TextInput,
)
from django.utils.safestring import mark_safe

from djtools.utils import (
    render_to_string,
)


class QrCodeScanner(TextInput):
    def render(self, name, value, attrs=None, **kwargs):
        attrs.update(style='margin-left:160px;width:300px')
        widget = super().render(name, value, attrs=attrs, **kwargs)
        output = render_to_string('djtools/templates/widgets/qr_code_scanner.html', {'widget': widget, 'name': name})
        return mark_safe(output)
