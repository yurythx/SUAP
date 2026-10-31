from djtools.db.models.fields.integer import NotaField, IntegerFieldPlus, PositiveIntegerFieldPlus


def test_notafield_formfield_always_uses_notafield():
    field = NotaField()
    form_field = field.formfield()
    assert form_field.__class__.__name__ == 'NotaField'


def test_notafield_formfield_widget_is_notawidget():
    field = NotaField()
    form_field = field.formfield()
    assert form_field.widget.__class__.__name__ == 'NotaWidget'


def test_notafield_formfield_with_kwargs():
    field = NotaField()
    form_field = field.formfield(label='Nota', help_text='Informe a nota')
    assert form_field.label == 'Nota'


def test_integerfieldplus_extra_attrs():
    field = IntegerFieldPlus(extra_attrs={'data-mask': '000'})
    assert field.extra_attrs == {'data-mask': '000'}


def test_integerfieldplus_default_extra_attrs():
    field = IntegerFieldPlus()
    assert field.extra_attrs == {}


def test_positiveintegerfieldplus_min_value_default():
    field = PositiveIntegerFieldPlus()
    assert field.min_value == 0


def test_positiveintegerfieldplus_min_value_positive():
    field = PositiveIntegerFieldPlus(min_value=5)
    assert field.min_value == 5


def test_positiveintegerfieldplus_min_value_negative_clamped_to_zero():
    field = PositiveIntegerFieldPlus(min_value=-3)
    assert field.min_value == 0


def test_positiveintegerfieldplus_formfield_passes_min_value():
    field = PositiveIntegerFieldPlus(min_value=10)
    form_field = field.formfield()
    assert form_field.min_value == 10
