from django.contrib.contenttypes.models import ContentType

from djtools import forms

from ..models import Comentario


class ComentarioForm(forms.ModelFormPlus):
    texto = forms.CharField(label='Texto', widget=forms.Textarea())

    class Meta:
        model = Comentario
        fields = ('texto',)

    def __init__(self, *args, **kwargs):
        self.object = kwargs.pop('object')
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance: Comentario = super().save(commit=False)
        instance.object_id = self.object.id
        instance.content_type = ContentType.objects.get_for_model(self.object)
        return super().save(commit)
