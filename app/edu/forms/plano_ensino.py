from datetime import date

from comum.models import Ano
from djtools import forms
from edu.models import PERIODO_LETIVO_CHOICES, Aluno, Componente, CursoCampus, ItemPlanoEstudo, PlanoEnsino
from rh.models import UnidadeOrganizacional


class PlanoEnsinoPublicForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    campus = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.campi().all(), label='Campus', widget=forms.Select(), required=False)
    curso = forms.ModelChoiceFieldPlus(CursoCampus.objects.all(), label='Curso', required=False)
    componente = forms.ModelChoiceFieldPlus(Componente.objects.all(), label='Componente', required=False)

    def processar(self):
        qs = PlanoEnsino.objects.filter(data_homologacao__isnull=False)

        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        campus = self.cleaned_data['campus']
        curso = self.cleaned_data['curso']
        componente = self.cleaned_data['componente']

        if ano_letivo:
            qs = qs.filter(diario__ano_letivo=ano_letivo)
        if periodo_letivo:
            qs = qs.filter(diario__periodo_letivo=periodo_letivo)
        if campus:
            qs = qs.filter(diario__turma__curso_campus__diretoria__setor__uo=campus)
        if curso:
            qs = qs.filter(diario__turma__curso_campus=curso)
        if componente:
            qs = qs.filter(diario__componente_curricular__componente=componente)
        return qs


class DevolverPlanoEnsino(forms.FormPlus):
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea())


class DefinirPlanoEstudoForm(forms.FormPlus):
    def __init__(self, *args, **kwargs):
        self.plano_estudo = kwargs.pop('plano_estudo')
        super().__init__(*args, **kwargs)
        aluno = self.plano_estudo.pedido_matricula.matricula_periodo.aluno
        ignorar_ids = []
        ignorar_ids.extend(aluno.get_ids_componentes_cumpridos())
        ignorar_ids.extend(aluno.get_ids_componentes_cursando())
        qs = aluno.matriz.componentecurricular_set.filter(optativo=False).exclude(componente_id__in=ignorar_ids)
        self.qs = qs.order_by('id')
        self.fieldsets = []
        anos_letivos = Ano.objects.filter(ano__gte=date.today().year, ano__lte=date.today().year + 5).order_by('ano')
        ids = []
        for cc in self.qs:
            ids.append(cc.id)
            item = self.plano_estudo.itemplanoestudo_set.filter(plano_estudo=self.plano_estudo, componente_curricular=cc).first()
            ignorar_ids.append(cc.componente_id)
            ano_letivo_field_name = f'ano_letivo-{cc.pk}'
            periodo_letivo_field_name = f'periodo_letivo-{cc.pk}'
            self.fields[ano_letivo_field_name] = forms.ModelChoiceFieldPlus(anos_letivos, label='Ano Letivo', required=False)
            self.fields[periodo_letivo_field_name] = forms.ChoiceField(
                choices=[['', ''], *PERIODO_LETIVO_CHOICES], label='Período Letivo', required=False
            )
            self.fieldsets.append((str(cc), {'fields': ((ano_letivo_field_name, periodo_letivo_field_name),)}))
            if item:
                self.initial[ano_letivo_field_name] = item.ano_letivo_id
                self.initial[periodo_letivo_field_name] = item.periodo_letivo

        componentes_curriculares_opcionais = aluno.matriz.componentecurricular_set.filter(optativo=True).exclude(componente_id__in=ignorar_ids)
        itens = self.plano_estudo.itemplanoestudo_set.filter(plano_estudo=self.plano_estudo).exclude(componente_curricular_id__in=ids)
        for i in range(10):
            componente_curricular_field_name = f'componente_curricular--{i}'
            ano_letivo_field_name = f'ano_letivo--{i}'
            periodo_letivo_field_name = f'periodo_letivo--{i}'
            self.fields[componente_curricular_field_name] = forms.ModelChoiceFieldPlus(
                componentes_curriculares_opcionais, label='Componente Curricular', required=False
            )
            self.fields[ano_letivo_field_name] = forms.ModelChoiceFieldPlus(anos_letivos, label='Ano Letivo', required=False)
            self.fields[periodo_letivo_field_name] = forms.ChoiceField(
                choices=[['', ''], *PERIODO_LETIVO_CHOICES], label='Período Letivo', required=False
            )
            self.fieldsets.append(
                (f'Disciplina Optativa {i + 1}', {'fields': (componente_curricular_field_name, (ano_letivo_field_name, periodo_letivo_field_name))})
            )
            item = itens[i] if len(itens) > i else None
            if item:
                self.initial[componente_curricular_field_name] = item.componente_curricular_id
                self.initial[ano_letivo_field_name] = item.ano_letivo_id
                self.initial[periodo_letivo_field_name] = item.periodo_letivo

    def processar(self):
        ids = []
        for cc in self.qs:
            ids.append(cc.id)
            ano_letivo_field_name = f'ano_letivo-{cc.pk}'
            periodo_letivo_field_name = f'periodo_letivo-{cc.pk}'
            item = self.plano_estudo.itemplanoestudo_set.filter(plano_estudo=self.plano_estudo, componente_curricular=cc).first()
            if item is None:
                item = ItemPlanoEstudo(plano_estudo=self.plano_estudo, componente_curricular=cc)
            ano_letivo = self.cleaned_data.get(ano_letivo_field_name)
            periodo_letivo = self.cleaned_data.get(periodo_letivo_field_name)
            if ano_letivo and periodo_letivo:
                item.ano_letivo = ano_letivo
                item.periodo_letivo = periodo_letivo
                item.save()

        for i in range(10):
            componente_curricular_field_name = f'componente_curricular--{i}'
            ano_letivo_field_name = f'ano_letivo--{i}'
            periodo_letivo_field_name = f'periodo_letivo--{i}'
            cc = self.cleaned_data.get(componente_curricular_field_name)
            item = self.plano_estudo.itemplanoestudo_set.filter(plano_estudo=self.plano_estudo, componente_curricular=cc).first()
            if item is None:
                item = ItemPlanoEstudo(plano_estudo=self.plano_estudo, componente_curricular=cc)
            ano_letivo = self.cleaned_data.get(ano_letivo_field_name)
            periodo_letivo = self.cleaned_data.get(periodo_letivo_field_name)
            if cc and ano_letivo and periodo_letivo:
                ids.append(cc.id)
                item.ano_letivo = ano_letivo
                item.periodo_letivo = periodo_letivo
                item.save()

        self.plano_estudo.itemplanoestudo_set.filter(plano_estudo=self.plano_estudo).exclude(componente_curricular__id__in=ids).delete()


class AvaliarPlanoEstudoForm(forms.FormPlus):
    data = forms.DateFieldPlus(label='Data')
    resultado = forms.ChoiceField(label='Resultado', choices=[['', ''], ['Homologado', 'Homologado'], ['Não-Homologado', 'Não-Homologado']])
    numero_ata = forms.CharField(label='Número da Ata')
    observacao = forms.CharField(label='Observação', required=False, widget=forms.Textarea())

    def processar(self, planos_estudo):
        planos_estudo.update(
            homologado=self.cleaned_data['resultado'] == 'Homologado',
            data_homologacao=self.cleaned_data['data'],
            observacao_homologacao=self.cleaned_data['observacao'],
            numero_ata_homologacao=self.cleaned_data['numero_ata'],
        )


class AlterarCoordenadorPlanoEnsinoForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoEnsino
        fields = ('coordenador_curso',)


class PlanoEnsinoForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoEnsino
        fields = (
            'coordenador_curso',
            'ementa',
            'justificativa',
            'objetivo_geral',
            'objetivos_especificos',
            'conteudo_programatico',
            'metodologia',
            'informacoes_adicionais',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.diario.componente_curricular.ementa:
            self.initial['ementa'] = self.instance.diario.componente_curricular.ementa
            self.instance.ementa = self.instance.diario.componente_curricular.ementa
            self.fields['ementa'].initial = self.instance.diario.componente_curricular.ementa
            self.fields['ementa'].widget.attrs.update(readonly='readonly')
        self.fields['coordenador_curso'].queryset = self.fields['coordenador_curso'].queryset.filter(ativo=True)
