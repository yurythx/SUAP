import datetime
from django.core.exceptions import ValidationError

from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from edu import tasks
from edu.models import (
    Aluno,
    ComponenteCurricular,
    ConvocacaoENADE,
    CursoCampus,
    JustificativaDispensaENADE,
    Modalidade,
    ModalidadeConvocacaoENADE,
    NivelEnsino,
    PeriodoConvocacaoRegencia,
    RegistroConvocacaoENADE,
    SituacaoMatricula,
)


class ConvocacaoENADEForm(forms.ModelForm):
    class Meta:
        model = ConvocacaoENADE
        fields = (
            'tipo_convocacao',
            'ano_letivo',
            'portaria',
            'edital',
            'data_inscricao_ingressantes',
            'data_inscricao',
            'data_inicio_inscricao',
            'areas_cursos_formacao_superior',
            'modalidades_convocadas',
            'situacoes_convocadas',
        )

    class Media:
        js = ['/static/edu/js/ConvocacaoENADEForm.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'situacoes_convocadas' not in self.initial or not self.initial['situacoes_convocadas']:
            self.initial['situacoes_convocadas'] = [SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL]

        self.fields['modalidades_convocadas'].queryset = Modalidade.objects.filter(nivel_ensino_id=NivelEnsino.GRADUACAO)

    def clean(self):
        ano_letivo = self.cleaned_data.get('ano_letivo')
        tipo_convocacao = self.cleaned_data.get('tipo_convocacao')
        areas_cursos_formacao_superior = self.cleaned_data.get('areas_cursos_formacao_superior') or ()
        modalidades_convocadas = self.cleaned_data.get('modalidades_convocadas') or ()
        data_inscricao_ingressantes = self.cleaned_data.get('data_inscricao_ingressantes')
        data_inscricao = self.cleaned_data.get('data_inscricao')
        qs = ConvocacaoENADE.objects.filter(ano_letivo=ano_letivo, tipo_convocacao=tipo_convocacao).values_list('cursos', flat=True).distinct()
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        cursos = CursoCampus.objects.filter(
            modalidade_id__in=modalidades_convocadas, area_curso_formacao_superior_id__in=areas_cursos_formacao_superior
        ).distinct()

        if tipo_convocacao == ConvocacaoENADE.AVALIACAO_TEORICA and data_inscricao_ingressantes is None:
            raise forms.ValidationError(
                'O campo "Data limite para inscrição de ingressantes" é requerido quando o "Tipo de convocação" for "Avaliação teórica".'
            )
        if tipo_convocacao == ConvocacaoENADE.AVALIACAO_TEORICA and data_inscricao is None:
            raise forms.ValidationError(
                'O campo "Data limite para inscrição de concluintes" é requerido quando o "Tipo de convocação" for "Avaliação teórica".'
            )

        erros = []
        for curso in cursos:
            if curso.id in qs:
                erros.append(f'O curso {curso} foi adicionado em outra convocação do ano letivo {ano_letivo}')
        if erros:
            raise forms.ValidationError(', '.join(erros))
        return self.cleaned_data

    def save(self, commit=False):
        convocacao = super().save(commit=True)
        convocacao.cursos.clear()
        cursos = CursoCampus.objects.filter(
            exige_enade=True,
            processamento_enade=True,
            area_curso_formacao_superior__in=convocacao.areas_cursos_formacao_superior.all(),
            modalidade__in=convocacao.modalidades_convocadas.all(),
        )
        for curso in cursos:
            convocacao.cursos.add(curso)

        for mce in ModalidadeConvocacaoENADE.objects.filter(convocacao_enade_id=convocacao.id).exclude(
            modalidade__in=convocacao.modalidades_convocadas.all()
        ):
            mce.delete()

        for modalidade in convocacao.modalidades_convocadas.all():
            if not ModalidadeConvocacaoENADE.objects.filter(modalidade_id=modalidade.id, convocacao_enade_id=convocacao.id).exists():
                mce = ModalidadeConvocacaoENADE()
                mce.modalidade_id = modalidade.id
                mce.convocacao_enade_id = convocacao.id
                mce.save()

        return convocacao

    def save_m2m(self):
        pass


class ModalidadeConvocacaoENADEForm(forms.ModelForm):
    class Meta:
        model = ModalidadeConvocacaoENADE
        fields = (
            'percentual_minimo_ingressantes',
            'percentual_maximo_ingressantes',
            'percentual_minimo_concluintes',
            'percentual_maximo_concluintes',
            'data_limite_integralizacao_concluinte',
            'data_limite_conclusao',
            'data_prova',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.convocacao_enade.is_avaliacao_teorica():
            del self.fields['data_limite_conclusao']
            del self.fields['data_limite_integralizacao_concluinte']
        hoje = datetime.date.today()
        if self.instance.convocacao_enade.data_inscricao and self.instance.convocacao_enade.data_inscricao < hoje:
            del self.fields['percentual_minimo_concluintes']
            del self.fields['percentual_maximo_concluintes']
            if 'data_limite_conclusao' in self.fields:
                del self.fields['data_limite_conclusao']
            if 'data_limite_integralizacao_concluinte' in self.fields:
                del self.fields['data_limite_integralizacao_concluinte']
        if self.instance.convocacao_enade.data_inscricao_ingressantes and self.instance.convocacao_enade.data_inscricao_ingressantes < hoje:
            del self.fields['percentual_minimo_ingressantes']
            del self.fields['percentual_maximo_ingressantes']

    def clean_data_prova(self):
        data_prova = self.cleaned_data.get('data_prova')
        if self.instance.pk:
            if ModalidadeConvocacaoENADE.objects.get(id=self.instance.pk).data_prova is not None and data_prova is None:
                raise forms.ValidationError('Não é possível remover a data da prova.')
        return data_prova

    def clean(self):
        percentual_minimo_ingressantes = self.cleaned_data.get('percentual_minimo_ingressantes')
        percentual_maximo_ingressantes = self.cleaned_data.get('percentual_maximo_ingressantes')
        percentual_minimo_concluintes = self.cleaned_data.get('percentual_minimo_concluintes')
        percentual_maximo_concluintes = self.cleaned_data.get('percentual_maximo_concluintes')

        if percentual_minimo_ingressantes and percentual_maximo_ingressantes and percentual_minimo_ingressantes > percentual_maximo_ingressantes:
            raise forms.ValidationError(
                f'O percentual mínimo de ingressantes {percentual_minimo_ingressantes} não pode ser maior que o percentual máximo de ingressantes ({percentual_maximo_ingressantes}).'
            )
        if percentual_minimo_concluintes and percentual_maximo_concluintes and percentual_minimo_concluintes > percentual_maximo_concluintes:
            raise forms.ValidationError(
                f'O percentual mínimo de concluintes {percentual_minimo_concluintes} não pode ser maior que o percentual máximo de concluintes ({percentual_maximo_concluintes}).'
            )

        return self.cleaned_data


class AtualizarListaConvocadosENADEForm(forms.Form):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Atualizar Lista de Convocados'

    curso_campus = forms.ModelChoiceField(
        CursoCampus.locals,
        required=False,
        label='Curso',
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS),
        help_text='Não selecione o curso caso deseje atualizar a lista para todos os cursos cadastrados.',
    )
    periodos = forms.MultipleModelChoiceFieldPlus(PeriodoConvocacaoRegencia.objects, required=True, label='Período')

    def __init__(self, convocacao_enade, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.convocacao_enade = convocacao_enade
        if convocacao_enade.is_avaliacao_teorica():
            self.fields['curso_campus'].queryset = convocacao_enade.cursos.all()
            del self.fields['periodos']
        else:
            self.fields['periodos'].queryset = PeriodoConvocacaoRegencia.objects.filter(convocacao_enade=convocacao_enade)
            del self.fields['curso_campus']

    def processar(self, request):
        curso_campus = self.cleaned_data.get('curso_campus', None)
        cursos = [curso_campus.id] if curso_campus else list(self.convocacao_enade.cursos.all().values_list('id', flat=True))
        periodos = self.cleaned_data.get('periodos')
        return tasks.atualizar_lista_convocacao_enade(self.convocacao_enade, cursos, periodos)


class LancarSituacaoAlunoENADEForm(forms.ModelForm):
    justificativa_dispensa = forms.ModelChoiceField(
        queryset=JustificativaDispensaENADE.objects.filter(ativo=True), label='Justificativa de Dispensa', required=False
    )

    class Meta:
        model = RegistroConvocacaoENADE
        fields = ('situacao', 'justificativa_dispensa')

    class Media:
        js = ('/static/edu/js/LancarSituacaoAlunoENADEForm.js',)

    def clean_justificativa_dispensa(self):
        if self.cleaned_data.get('situacao') == RegistroConvocacaoENADE.SITUACAO_DISPENSADO:
            if not self.cleaned_data.get('justificativa_dispensa'):
                raise forms.ValidationError('O campo Justificativa de Dispensa é obrigatório.')
        elif self.cleaned_data.get('justificativa_dispensa'):
            raise forms.ValidationError('O campo Justificativa de Dispensa deve ser preenchido apenas quando a Situação for Dispensado.')
        return self.cleaned_data.get('justificativa_dispensa')

    def clean(self):
        if (
            self.instance.convocacao_enade
            and not self.instance.get_data_prova()
            and self.instance.tipo_convocacao
            in [RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE, RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE]
            and self.cleaned_data.get('situacao') != RegistroConvocacaoENADE.SITUACAO_DISPENSADO
        ):
            raise forms.ValidationError('Você precisa definir a data de realização da prova na modaliade da convocação do ENADE.')
        if not self.instance.convocacao_enade and self.cleaned_data.get('situacao') != RegistroConvocacaoENADE.SITUACAO_DISPENSADO:
            raise forms.ValidationError('A situação do aluno no ENADE deve ser "Dispensado"')
        if (
            self.instance.convocacao_enade
            and not self.instance.convocacao_enade.cursos.filter(pk=self.instance.aluno.curso_campus.pk).exists()
            and self.cleaned_data.get('situacao') != RegistroConvocacaoENADE.SITUACAO_DISPENSADO
        ):
            raise forms.ValidationError('A situação do aluno no ENADE deve ser "Dispensado"')
        return self.cleaned_data


class RegistroConvocacaoENADEForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Salvar'

    aluno = forms.ModelChoiceFieldPlus(
        Aluno.ativos, label='Aluno', widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS), help_text='Lista alunos ativos.'
    )

    class Meta:
        model = RegistroConvocacaoENADE
        exclude = ('situacao', 'percentual_ch_cumprida', 'justificativa_dispensa', 'estagio_docente')

    def __init__(self, convocacao, curso_campus, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if convocacao:
            self.fields['convocacao_enade'].initial = convocacao.pk
            self.fields['convocacao_enade'].widget = forms.HiddenInput()
            if convocacao.is_avaliacao_teorica():
                del self.fields['periodo_convocacao_regencia']
                self.fields['tipo_convocacao'].choices = (
                    ('', '---'),
                    (RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE, 'Ingressante'),
                    (RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE, 'Concluinte'),
                )
            else:
                del self.fields['possivel_concluinte']
                del self.fields['possivel_integralizado']
                del self.fields['tipo_convocacao']
                self.instance.tipo_convocacao = RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP
                self.fields['periodo_convocacao_regencia'].queryset = convocacao.periodoconvocacaoregencia_set.all()

        if curso_campus:
            self.fields['aluno'].queryset = Aluno.ativos.filter(curso_campus=curso_campus)

    def clean(self):
        aluno = self.cleaned_data.get('aluno')
        convocacao_enade = self.cleaned_data.get('convocacao_enade')
        if not aluno or not convocacao_enade:
            return self.cleaned_data

        if convocacao_enade.registroconvocacaoenade_set.filter(aluno_id=aluno.id).exists():
            raise ValidationError(f'{aluno} já está cadastrado(a) na convocação atual.')

        if not convocacao_enade.is_avaliacao_teorica():
            if (
                RegistroConvocacaoENADE.objects.convocacoes_avaliacao_pratica()
                .filter(aluno_id=aluno.id)
                .exclude(convocacao_enade_id=convocacao_enade.id)
                .exists()
            ):
                raise ValidationError(f'O aluno {aluno} já foi convocado para a avaliação prática em outra edição do ENADE.')

            periodo = self.cleaned_data.get('periodo_convocacao_regencia')
            if periodo:
                qs_estagio = aluno.get_estagios_docentes().filter(
                    matricula_diario__diario__calendario_academico__data_inicio__lte=periodo.data_fim,
                    matricula_diario__diario__calendario_academico__data_fim__gte=periodo.data_inicio,
                    matricula_diario__diario__componente_curricular__tipo_estagio_docente__in=[
                        ComponenteCurricular.ESTAGIO_DOCENTE_3,
                        ComponenteCurricular.ESTAGIO_DOCENTE_4,
                    ],
                )
                if not qs_estagio.exists():
                    raise ValidationError(f'{aluno} não possui estágio no período informado.')

        tipo_convocacao = self.cleaned_data.get('tipo_convocacao') or self.instance.tipo_convocacao
        possivel_concluinte = self.cleaned_data.get('possivel_concluinte')
        possivel_integralizado = self.cleaned_data.get('possivel_integralizado')

        if tipo_convocacao == RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE:
            if possivel_concluinte:
                raise ValidationError('Não é possível selecionar "É possível concluinte" quando o tipo da convocação for "Ingressante".')
            if possivel_integralizado:
                raise ValidationError('Não é possível selecionar "É possível integralizado" quando o tipo da convocação for "Ingressante".')

        if possivel_integralizado and possivel_concluinte:
            raise ValidationError('Selecione apenas uma das opções "É possível integralizado" ou "É possível concluinte".')

        return self.cleaned_data

    def save(self, *args, **kwargs):
        aluno = self.cleaned_data.get('aluno')
        self.instance.percentual_ch_cumprida = aluno.get_percentual_carga_horaria_cumprida()

        periodo = self.cleaned_data.get('periodo_convocacao_regencia')
        if periodo:
            qs_estagio = aluno.get_estagios_docentes().filter(
                matricula_diario__diario__calendario_academico__data_inicio__lte=periodo.data_fim,
                matricula_diario__diario__calendario_academico__data_fim__gte=periodo.data_inicio,
                matricula_diario__diario__componente_curricular__tipo_estagio_docente__in=[
                    ComponenteCurricular.ESTAGIO_DOCENTE_3,
                    ComponenteCurricular.ESTAGIO_DOCENTE_4,
                ],
            )
            # pega o ESTAGIO_DOCENTE_3, caso não encontre, busca pelo ESTAGIO_DOCENTE_4.
            estagio = next(
                (
                    e
                    for e in qs_estagio
                    if e.matricula_diario.diario.componente_curricular.tipo_estagio_docente == ComponenteCurricular.ESTAGIO_DOCENTE_3
                ),
                qs_estagio.filter(
                    matricula_diario__diario__componente_curricular__tipo_estagio_docente=ComponenteCurricular.ESTAGIO_DOCENTE_4
                ).first(),
            )
            self.instance.estagio_docente = estagio
        return super().save(*args, **kwargs)


class DispensaConvocacaoENADEForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Salvar'

    justificativa_dispensa = forms.ModelChoiceField(
        queryset=JustificativaDispensaENADE.objects.filter(ativo=True), label='Justificativa de dispensa', required=True
    )

    class Meta:
        model = RegistroConvocacaoENADE
        fields = ('tipo_convocacao', 'convocacao_enade', 'justificativa_dispensa')

    def __init__(self, aluno, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['convocacao_enade'].queryset = ConvocacaoENADE.objects.filter(tipo_convocacao=ConvocacaoENADE.AVALIACAO_TEORICA).order_by(
            '-ano_letivo__ano'
        )
        choices = []
        if aluno.get_enade_ingressante() is None:
            choices.append((RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE, 'Ingressante'))

        ultimo_ano = ConvocacaoENADE.get_ano_ultima_avaliacao_teorica()
        if (
            ultimo_ano
            and not RegistroConvocacaoENADE.objects.filter(
                aluno_id=aluno.id, convocacao_enade__ano_letivo__ano=ultimo_ano, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE
            ).exists()
        ):
            choices.append((RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE, 'Concluinte'))
        self.fields['tipo_convocacao'].choices = choices


class DispensaConvocacaoENADEEmLoteForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Salvar'

    justificativa_dispensa = forms.ModelChoiceField(
        queryset=JustificativaDispensaENADE.objects.filter(ativo=True), label='Justificativa de dispensa', required=True
    )

    class Meta:
        model = RegistroConvocacaoENADE
        fields = ('justificativa_dispensa',)

    def __init__(self, *args, **kwargs):
        selecionados = kwargs.pop('selecionados', None)
        super().__init__(*args, **kwargs)
        self.fields.update(
            {
                'selecionados': forms.CharField(label='Selecionados', widget=forms.HiddenInput()),
            }
        )
        self.fields['selecionados'].initial = selecionados


class JustificativaDispensaENADECursoCampusForm(forms.ModelFormPlus):
    class Meta:
        model = CursoCampus
        fields = ('justificativa_dispensa_ingressante',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['justificativa_dispensa_ingressante'].queryset = JustificativaDispensaENADE.objects.filter(ativo=True)


class DatasIncricaoENADEForm(forms.ModelFormPlus):
    class Meta:
        model = ConvocacaoENADE
        fields = (
            'data_inicio_inscricao',
            'data_inscricao',
            'data_inscricao_ingressantes',
        )


class PeriodoConvocacaoRegenciaForm(forms.ModelForm):
    class Meta:
        model = PeriodoConvocacaoRegencia
        fields = ('convocacao_enade', 'data_inicio', 'data_fim')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields['convocacao_enade'].initial = pk
        self.fields['convocacao_enade'].widget = forms.HiddenInput()
