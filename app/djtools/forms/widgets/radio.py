from django.forms import widgets


class RadioInput(widgets.Input):
    input_type = 'radio'
    template_name = 'django/forms/widgets/input.html'


class RadioSelect(widgets.RadioSelect):
    template_name = 'widgets/radio.html'

    def __init__(self, uncheck=False, attrs=None, choices=()):
        super().__init__(attrs, choices)
        self.uncheck = uncheck

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['enable_uncheck'] = self.uncheck
        return context


class RenderableRadioSelect(RadioSelect):
    def __init__(self, template_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.template_name = template_name

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        objects = []
        for object in self.choices.queryset.all():
            widget = RadioInput(attrs.copy())
            if str(value) == str(object.id):
                object.checked_ = True
                widget.attrs.update(checked='checked')
            object.widget = widget.render(name, object.id, attrs.copy())
            objects.append(object)
        context['objects'] = objects
        for option in context['widget']['optgroups']:
            if option[1][0]['value'] != '':
                option[1][0]['object'] = self.choices.queryset.filter(pk=option[1][0]['value'].value)[0]
        return context
