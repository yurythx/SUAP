from django.core.exceptions import ValidationError
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from edu.models import (
    ProjetoIntegrador,
    AtividadeProjetoIntegrador,
    Diario,
    MatriculaDiario,
    AvaliacaoAtividadeProjetoIntegrador,
    AvaliacaoProjetoIntegrador,
)


class ProjetoIntegradorForm(forms.ModelFormPlus):
    participantes = forms.MultipleModelChoiceField(
        MatriculaDiario.objects,
        label='Participantes',
        widget=AutocompleteWidget(
            search_fields=MatriculaDiario.SEARCH_FIELDS,
            form_filters=[
                ('diario', 'diario'),
            ],
            multiple=True,
        ),
        required=False,
    )

    class Meta:
        model = ProjetoIntegrador
        fields = (
            'diario',
            'tema',
            'professores',
            'participantes',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk or self.request.GET.get('diario'):
            self.fields['diario'].widget = forms.HiddenInput()
        else:
            diarios = Diario.objects.filter(
                professordiario__professor__vinculo__user=self.request.user, componente_curricular__ch_projeto_integrador__gt=0
            )
            ano_letivo = diarios.order_by('ano_letivo__ano').values_list('ano_letivo', flat=True).last()
            self.fields['diario'].queryset = diarios.filter(ano_letivo=ano_letivo)

    def clean_participantes(self):
        pk = self.instance.pk if self.instance else 0
        diario = self.cleaned_data.get('diario')
        participantes = self.cleaned_data.get('participantes')
        for participante in participantes:
            pi = diario.projetointegrador_set.exclude(pk=pk).filter(participantes=participante).first()
            if pi:
                raise forms.ValidationError(
                    f'O participante {participante.matricula_periodo.aluno} já se encontra em outro projeto integrador nesse diário ({pi}).'
                )
        return participantes


class AdicionarAlunoProjetoIntegradorForm(forms.ModelFormPlus):
    participantes = forms.MultipleModelChoiceField(
        MatriculaDiario.objects,
        label='Participantes',
        widget=AutocompleteWidget(
            search_fields=MatriculaDiario.SEARCH_FIELDS,
            multiple=True,
        ),
        required=False,
    )

    class Meta:
        model = ProjetoIntegrador
        fields = ('diario',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diario'].widget = forms.HiddenInput()
        self.fields['participantes'].queryset = MatriculaDiario.objects.filter(
            diario__turma_id=self.instance.diario.turma_id,
            diario__componente_curricular_id=self.instance.diario.componente_curricular_id,
        )

    def clean_participantes(self):
        pk = self.instance.pk if self.instance else 0
        diario = self.cleaned_data.get('diario')
        participantes = self.cleaned_data.get('participantes')
        for participante in participantes:
            pi = diario.projetointegrador_set.exclude(pk=pk).filter(participantes=participante).first()
            if pi:
                raise forms.ValidationError(
                    f'O participante {participante.matricula_periodo.aluno} já se encontra em outro projeto integrador nesse diário ({pi}).'
                )
        return participantes


class ProjetoIntegradorEditForm(forms.ModelFormPlus):
    class Meta:
        model = ProjetoIntegrador
        fields = (
            'tema',
            'professores',
        )


class AvaliarAtividadeProjetoIntegradorForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadeProjetoIntegrador
        fields = ('observacao',)

    fieldsets = (
        ('Avaliação individual', {'fields': ()}),
        ('Dados complementares', {'fields': ('observacao',)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        names = []
        initial = dict(self.instance.avaliacaoatividadeprojetointegrador_set.values_list('participante', 'situacao'))
        for md in self.instance.projeto_integrador.participantes.all():
            name = str(md.id)
            self.fields[name] = forms.ChoiceField(
                label=str(md.matricula_periodo.aluno),
                choices=[*AvaliacaoAtividadeProjetoIntegrador.SITUACAO_CHOICES, [9, 'Não registrada']],
                widget=forms.RadioSelect(attrs={'disabled': md.situacao != MatriculaDiario.SITUACAO_CURSANDO}),
                initial=initial.get(md.pk, 9),
                required=False,
            )
            names.append(name)
        self.fieldsets[0][1]['fields'] = names

    def save(self, *args, **kwargs):
        for pk in self.fields:
            if pk.isdigit():
                situacao = self.cleaned_data[pk]
                if situacao:
                    if int(situacao) == 9:
                        AvaliacaoAtividadeProjetoIntegrador.objects.filter(atividade_projeto_integrador=self.instance, participante_id=pk).delete()
                    else:
                        AvaliacaoAtividadeProjetoIntegrador.objects.update_or_create(
                            atividade_projeto_integrador=self.instance, participante_id=pk, defaults={'situacao': situacao}
                        )
        return super().save(*args, **kwargs)


def AvaliarProjetoIntegradorFormFactory(*args, **kwargs):
    etapa = kwargs.pop('etapa')
    suffix = etapa if etapa > 1 else ''

    class AvaliarProjetoIntegradorForm(forms.ModelFormPlus):
        class Meta:
            model = ProjetoIntegrador
            fields = (f'data_hora_defesa{suffix}', f'presidente_banca{suffix}', f'membros_banca{suffix}', f'arquivo{suffix}', f'obs{suffix}')

        fieldsets = (
            ('Notas', {'fields': ()}),
            ('Dados da banca', {'fields': (f'data_hora_defesa{suffix}', f'presidente_banca{suffix}', f'membros_banca{suffix}')}),
            ('Arquivo digitalizado', {'fields': (f'arquivo{suffix}',)}),
            ('Dados complementares', {'fields': (f'obs{suffix}',)}),
        )

        def __init__(self, *args, **kwargs):

            super().__init__(*args, **kwargs)
            names = []
            field_name = 'nota' if etapa == 1 else f'nota{etapa}'
            initial = dict(self.instance.avaliacaoprojetointegrador_set.values_list('participante', field_name))
            for md in self.instance.participantes.all():
                name = str(md.id)
                self.fields[name] = forms.NotaField(label=str(md.matricula_periodo.aluno), initial=initial.get(md.pk), help_text='', required=False)
                if md.situacao != MatriculaDiario.SITUACAO_CURSANDO:
                    self.fields[name].widget.attrs.update(readonly='readonly')
                    self.fields[
                        name
                    ].help_text = f'Não é possível registrar a nota. O aluno está com situação {md.get_situacao_display()} no diário {md.diario.id}. Para realizar o lançamento, a situação deve estar como Cursando.'
                names.append(name)
            self.fieldsets[0][1]['fields'] = names
            self.fields[f'presidente_banca{suffix}'].queryset = self.fields[f'presidente_banca{suffix}'].queryset.filter(ativo=True)
            self.fields[f'membros_banca{suffix}'].queryset = self.fields[f'membros_banca{suffix}'].queryset.filter(ativo=True)

        def processar(self):
            field_name = 'nota' if etapa == 1 else f'nota{etapa}'
            erros = []
            for pk in self.fields:
                if pk.isdigit():
                    try:
                        avaliacao = AvaliacaoProjetoIntegrador.objects.get_or_create(projeto_integrador=self.instance, participante_id=pk)[0]
                        setattr(avaliacao, field_name, self.cleaned_data.get(pk, None))
                        avaliacao.processar_pratica_profissional(finalizar=False)
                        avaliacao.save()
                    except ValidationError as e:
                        erros.append(f'{e!s} ({avaliacao.participante.matricula_periodo.aluno.matricula}).')
            self.save()
            return erros

    return AvaliarProjetoIntegradorForm(*args, **kwargs)
