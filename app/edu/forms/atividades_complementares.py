from datetime import date
from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from comum.models import Ano
from djtools import forms
from edu.models import (
    Aluno,
    AtividadeAprofundamento,
    AtividadeComplementar,
    AtividadeCurricularExtensao,
    AtividadeCurricularExtensaoExtra,
    AtividadePraticaProfissional,
    ComponenteCurricular,
    ConfiguracaoAtividadeAprofundamento,
    ConfiguracaoAtividadeComplementar,
    HorarioAtividadeExtra,
    HorarioAula,
    ItemConfiguracaoAtividadeAprofundamento,
    ItemConfiguracaoAtividadeComplementar,
    MatriculaDiario,
    MatriculaPeriodo,
    Matriz,
    SituacaoMatriculaPeriodo,
    TipoAtividadeAprofundamento,
    TipoAtividadeComplementar,
    TipoAtividadeCurricularExtensaoExtra,
    VinculacaoAtividadeExtensao,
)


class IndeferirAtividadeComplementarForm(forms.ModelFormPlus):
    razao_indeferimento = forms.CharField(widget=forms.Textarea(), required=True, label='Razão do Indeferimento')

    class Meta:
        model = AtividadeComplementar
        fields = ('razao_indeferimento',)

    def save(self, *args, **kwargs):
        self.instance.deferida = False
        super().save(*args, **kwargs)


class IndeferirAtividadeAprofundamentoForm(forms.ModelFormPlus):
    razao_indeferimento = forms.CharField(widget=forms.Textarea(), required=True, label='Razão do Indeferimento')

    class Meta:
        model = AtividadeAprofundamento
        fields = ('razao_indeferimento',)

    def save(self, *args, **kwargs):
        self.instance.deferida = False
        super().save(*args, **kwargs)


class AtividadeComplementarForm(forms.ModelFormPlus):
    VINCULADO_CURSO = 1
    NAO_VINCULADO_CURSO = 2
    VINCULADO_CHOICES = [[VINCULADO_CURSO, 'Curricular'], [NAO_VINCULADO_CURSO, 'Não curricular']]
    ano_letivo = forms.ModelChoiceField(Ano.objects, label='Ano Letivo')
    aluno = forms.ModelChoiceField(Aluno.objects, widget=forms.HiddenInput())
    tipo = forms.ModelChoiceField(TipoAtividadeComplementar.objects)
    vinculacao = forms.ChoiceField(label='Vinculação', choices=VINCULADO_CHOICES, widget=forms.RadioSelect(), initial=VINCULADO_CURSO, required=True)
    tem_aacc = forms.BooleanField(label='Tem AACC', widget=forms.HiddenInput(), required=False)

    motivo = forms.CharFieldPlus(
        label='Motivo',
        required=True,
        widget=forms.Textarea(),
        help_text='Informe a justificativa para a alteração da atividade complementar deferida.',
    )

    fieldsets = (
        ('Tipo e Período Letivo', {'fields': (('ano_letivo', 'periodo_letivo'), 'vinculacao', 'tipo', 'tem_aacc')}),
        (
            'Dados da Atividade',
            {
                'fields': (
                    'aluno',
                    'descricao',
                    ('data_atividade', 'data_conclusao_atividade'),
                    'carga_horaria',
                    'informacoes_complementares',
                    'documento',
                    'motivo',
                )
            },
        ),
    )

    class Meta:
        model = AtividadeComplementar
        exclude = ('deferida', 'razao_indeferimento', 'data_deferimento_atividade')

    class Media:
        js = ('/static/edu/js/AtividadeComplementarForm.js',)

    def __init__(self, *args, **kwargs):
        self.as_aluno = kwargs.pop('as_aluno', False)
        super().__init__(*args, **kwargs)

        self.aluno_obj = Aluno.objects.get(pk=self.initial['aluno'])
        self.tipos_vinculados = TipoAtividadeComplementar.objects.filter(
            itemconfiguracaoatividadecomplementar__configuracao__matriz__aluno=self.aluno_obj
        ).distinct()
        self.tipos_nao_vinculados = TipoAtividadeComplementar.objects.exclude(
            itemconfiguracaoatividadecomplementar__configuracao__matriz__aluno=self.aluno_obj
        ).distinct()
        self.fields['ano_letivo'].queryset = Ano.objects.filter(matriculaperiodo__aluno=self.aluno_obj).distinct()
        self.fields['tipo'].queryset = TipoAtividadeComplementar.objects.exclude(descricao='Atividade de Extensão')

        if self.instance.pk and self.instance.tipo in self.tipos_nao_vinculados:
            self.fields['vinculacao'].initial = self.NAO_VINCULADO_CURSO

        if self.as_aluno:
            self.fields['documento'].required = True

        self.initial['tem_aacc'] = self.tipos_vinculados.exists()

        if self.instance and not self.instance.deferida:
            del self.fields['motivo']

    def clean_tipo(self):
        tipo = self.cleaned_data.get('tipo')
        vinculacao = int(self.data.get('vinculacao'))
        if vinculacao == self.VINCULADO_CURSO and tipo not in self.tipos_vinculados:
            raise ValidationError('Selecione um tipo vinculado.')
        if vinculacao == self.NAO_VINCULADO_CURSO and tipo not in self.tipos_nao_vinculados:
            raise ValidationError('Selecione um tipo não vinculado.')
        return self.cleaned_data['tipo']

    def clean_carga_horaria(self):
        carga_horaria = self.cleaned_data.get('carga_horaria')
        if carga_horaria <= 0:
            raise ValidationError('Informe uma carga horária maior que zero.')
        return carga_horaria

    def clean(self):
        aluno = (self.cleaned_data.get('aluno'),)
        ano_letivo = (self.cleaned_data.get('ano_letivo'),)
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        qs_matricula_periodo = MatriculaPeriodo.objects.filter(aluno=aluno[0], ano_letivo=ano_letivo[0], periodo_letivo=periodo_letivo)

        if not qs_matricula_periodo.exists():
            raise ValidationError('Ano/Período Letivo inválidos')

        if qs_matricula_periodo[0].situacao.pk == SituacaoMatriculaPeriodo.EM_ABERTO:
            raise forms.ValidationError('A situação do aluno no período selecionado é "Em aberto".')

        return self.cleaned_data

    @transaction.atomic()
    def processar(self, vinculo):
        ch_anterior_atividade = None
        if self.instance.deferida:
            old = AtividadeComplementar.objects.filter(id=self.instance.id).first()
            if old and old.is_curricular():
                ch_anterior_atividade = old.carga_horaria
                tipo_anterior_atividade = old.tipo
                ch_cumprida_anterior = old.aluno.get_ch_cumprida()

        if not self.as_aluno:
            self.instance.deferida = True
            self.instance.save()
        else:
            self.instance.save()
            self.instance.enviar_email_coordenador()

        instance_is_curricular = self.instance.is_curricular()
        if ch_anterior_atividade is not None and (self.instance.carga_horaria < ch_anterior_atividade or not instance_is_curricular):
            from edu.models import ProcedimentoReducaoCH

            ch_cumprida_nova = self.instance.aluno.get_ch_cumprida()
            pr = ProcedimentoReducaoCH()
            pr.matricula_periodo = self.instance.aluno.get_matricula_periodo(
                ano_letivo=self.instance.ano_letivo, periodo_letivo=self.instance.periodo_letivo
            )
            pr.tipo_procedimento = ProcedimentoReducaoCH.ATIVIDADE_COMPLEMENTAR
            pr.motivo = self.cleaned_data.get('motivo')
            nao_curricular = 'não curricular' if not instance_is_curricular else 'curricular'
            pr.informacao_complementar = f'Alteração da atividade complementar <strong>{tipo_anterior_atividade}</strong> ({ch_anterior_atividade}h) para <strong>{self.instance.tipo}</strong> ({self.instance.carga_horaria}h - {nao_curricular}).'
            pr.vinculo = vinculo
            pr.ch_nova = ch_cumprida_nova
            pr.ch_anterior = ch_cumprida_anterior
            pr.save()


class RemoverAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Excluir'
    motivo = forms.CharFieldPlus(
        label='Motivo',
        required=True,
        widget=forms.Textarea(),
        help_text='Informe a justificativa para a exclusão da atividade.',
    )
    senha = forms.PasswordField()


class DesfazerAvaliacaoAtividadeForm(forms.FormPlus):
    motivo = forms.CharFieldPlus(
        label='Motivo',
        required=True,
        widget=forms.Textarea(),
        help_text='Informe a justificativa para desfazer a avaliação da atividade.',
    )


class AtividadeAprofundamentoForm(forms.ModelFormPlus):
    aluno = forms.ModelChoiceField(Aluno.objects, widget=forms.HiddenInput())
    motivo = forms.CharFieldPlus(
        label='Motivo',
        required=True,
        widget=forms.Textarea(),
        help_text='Informe a justificativa para a alteração da ativiade de aprofundamento deferida.',
    )

    fieldsets = (
        ('Tipo e Período Letivo', {'fields': (('ano_letivo', 'periodo_letivo'), 'tipo')}),
        (
            'Dados da Atividade',
            {'fields': ('aluno', 'descricao', ('data_atividade', 'carga_horaria'), 'informacoes_complementares', 'documento', 'motivo')},
        ),
    )

    class Meta:
        model = AtividadeAprofundamento
        exclude = ('deferida', 'razao_indeferimento')

    def __init__(self, *args, **kwargs):
        self.as_aluno = kwargs.pop('as_aluno', False)
        super().__init__(*args, **kwargs)
        self.aluno_obj = Aluno.objects.get(pk=self.initial['aluno'])
        pks = ItemConfiguracaoAtividadeAprofundamento.objects.filter(
            configuracao=self.aluno_obj.matriz.configuracao_atividade_aprofundamento_id
        ).values_list('tipo', flat=True)
        self.fields['tipo'].queryset = self.fields['tipo'].queryset.filter(pk__in=pks).exclude(descricao='Atividade de Extensão')

        if self.instance and not self.instance.deferida:
            del self.fields['motivo']

    def clean_carga_horaria(self):
        carga_horaria = self.cleaned_data.get('carga_horaria')
        tipo = self.cleaned_data.get('tipo')
        if tipo:
            item_configuracao = ItemConfiguracaoAtividadeAprofundamento.objects.get(
                configuracao=self.aluno_obj.matriz.configuracao_atividade_aprofundamento_id, tipo=tipo
            )
            if carga_horaria and tipo and item_configuracao.carga_horaria and carga_horaria > item_configuracao.carga_horaria:
                raise forms.ValidationError(f'A carga horária dessa atividade deve ser de {item_configuracao.carga_horaria} horas')
        return carga_horaria

    def clean(self):
        aluno = self.cleaned_data.get('aluno')
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        qs_matricula_periodo = MatriculaPeriodo.objects.filter(aluno=aluno, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)

        if not qs_matricula_periodo.exists():
            raise ValidationError('Ano/Período Letivo inválidos')

        if qs_matricula_periodo[0].situacao.pk == SituacaoMatriculaPeriodo.EM_ABERTO:
            raise forms.ValidationError('A situação do aluno no período selecionado é "Em aberto".')

        return self.cleaned_data

    @transaction.atomic()
    def processar(self, vinculo):
        ch_anterior_atividade = None
        if self.instance.deferida:
            old = AtividadeAprofundamento.objects.filter(id=self.instance.id).first()
            if old:
                ch_anterior_atividade = old.carga_horaria
                tipo_anterior_atividade = old.tipo
                ch_cumprida_anterior = old.aluno.get_ch_cumprida()

        if not self.as_aluno:
            self.instance.deferida = True
            self.instance.save()
        else:
            self.instance.save()
            self.instance.enviar_email_coordenador()

        if ch_anterior_atividade is not None and self.instance.carga_horaria < ch_anterior_atividade:
            from edu.models import ProcedimentoReducaoCH

            ch_cumprida_nova = self.instance.aluno.get_ch_cumprida()
            pr = ProcedimentoReducaoCH()
            pr.matricula_periodo = self.instance.aluno.get_matricula_periodo(
                ano_letivo=self.instance.ano_letivo, periodo_letivo=self.instance.periodo_letivo
            )
            pr.tipo_procedimento = ProcedimentoReducaoCH.ATIVIDADE_APROFUNDAMENTO
            pr.motivo = self.cleaned_data.get('motivo')
            pr.informacao_complementar = f'Alteração da atividade de aprofundamento <strong>{tipo_anterior_atividade}</strong> ({ch_anterior_atividade}h) para <strong>{self.instance.tipo}</strong> ({self.instance.carga_horaria}h).'
            pr.vinculo = vinculo
            pr.ch_nova = ch_cumprida_nova
            pr.ch_anterior = ch_cumprida_anterior
            pr.save()


class VincularConfiguracaoAtividadeComplementarForm(forms.Form):
    matrizes = forms.MultipleModelChoiceFieldPlus(Matriz.objects)


class VincularConfiguracaoAtividadeAprofundamentoForm(forms.Form):
    matrizes = forms.MultipleModelChoiceFieldPlus(Matriz.objects)


class ItemConfiguracaoAtividadeComplementarForm(forms.ModelForm):
    tipo = forms.ModelChoiceField(TipoAtividadeComplementar.objects, widget=forms.Select(attrs={'style': 'width:600px'}))

    def __init__(self, *args, **kwargs):
        configuracao_pk = kwargs.pop('configuracao_pk')
        super(self.__class__, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['tipo'].widget = forms.HiddenInput()
        else:
            self.fields['tipo'].queryset = TipoAtividadeComplementar.objects.exclude(
                itemconfiguracaoatividadecomplementar__configuracao__pk=configuracao_pk
            )

    class Meta:
        model = ItemConfiguracaoAtividadeComplementar
        exclude = ('configuracao', 'ch_max_periodo', 'ch_max_curso', 'ch_min_curso', 'ch_por_evento')


class ItemConfiguracaoAtividadeAprofundamentoForm(forms.ModelForm):
    tipo = forms.ModelChoiceField(TipoAtividadeAprofundamento.objects, widget=forms.Select(attrs={'style': 'width:600px'}))

    def __init__(self, *args, **kwargs):
        configuracao_pk = kwargs.pop('configuracao_pk')
        super(self.__class__, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['tipo'].widget = forms.HiddenInput()
        else:
            self.fields['tipo'].queryset = TipoAtividadeAprofundamento.objects.exclude(
                itemconfiguracaoatividadeaprofundamento__configuracao__pk=configuracao_pk
            )

    class Meta:
        model = ItemConfiguracaoAtividadeAprofundamento
        exclude = ('configuracao',)


class ReplicarConfiguracaoAACCForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoAtividadeComplementar
        exclude = ()

    def processar(self, configuracao):
        return configuracao.replicar(self.cleaned_data['descricao'])


class ReplicarConfiguracaoATPAForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoAtividadeAprofundamento
        exclude = ()

    def processar(self, configuracao):
        return configuracao.replicar(self.cleaned_data['descricao'])


class HorarioAtividadeExtraForm(forms.ModelFormPlus):
    class Meta:
        model = HorarioAtividadeExtra
        fields = ('descricao_atividade', 'tipo_atividade')

    def __init__(self, *args, **kwargs):
        self.matricula_periodo = kwargs.pop('matricula_periodo')
        super().__init__(*args, **kwargs)

    def clean(self):
        if not dict(self.request.POST).get('horario'):
            raise forms.ValidationError('É necessário informar pelo menos um horário.')
        return self.cleaned_data

    def save(self, horarios, *args, **kwargs):
        descricao_atividade = self.cleaned_data.get('descricao_atividade')
        tipo_atividade = self.cleaned_data.get('tipo_atividade')
        HorarioAtividadeExtra.objects.filter(
            descricao_atividade=descricao_atividade, tipo_atividade=tipo_atividade, matricula_periodo=self.matricula_periodo
        ).delete()
        if horarios:
            for horario in horarios:
                horario_split = horario.split(';')
                horario_aula = HorarioAula.objects.get(pk=horario_split[0])
                dia_semana = horario_split[1]
                HorarioAtividadeExtra.objects.create(
                    descricao_atividade=descricao_atividade,
                    tipo_atividade=tipo_atividade,
                    matricula_periodo=self.matricula_periodo,
                    dia_semana=dia_semana,
                    horario_aula=horario_aula,
                )
        else:
            raise ValidationError('É necessário informar pelo menos um horário.')


class EditarHorarioAtividadeExtraForm(forms.ModelFormPlus):
    atividade_tipo = forms.CharField(label='Tipo de Atividade', widget=forms.TextInput(attrs={'readonly': 'readonly'}), required=False)

    class Meta:
        model = HorarioAtividadeExtra
        fields = ('descricao_atividade', 'atividade_tipo')

    def __init__(self, *args, **kwargs):
        self.matricula_periodo = kwargs.pop('matricula_periodo')
        super().__init__(*args, **kwargs)
        self.fields['descricao_atividade'].widget = forms.TextInput(attrs={'readonly': 'readonly'})
        self.fields['atividade_tipo'].initial = self.instance.get_tipo_atividade_display()

    def save(self, horarios, *args, **kwargs):
        HorarioAtividadeExtra.objects.filter(
            descricao_atividade=self.instance.descricao_atividade,
            tipo_atividade=self.instance.tipo_atividade,
            matricula_periodo=self.matricula_periodo,
        ).delete()
        if horarios:
            for horario in horarios:
                horario_split = horario.split(';')
                horario_aula = HorarioAula.objects.get(pk=horario_split[0])
                dia_semana = horario_split[1]
                HorarioAtividadeExtra.objects.create(
                    descricao_atividade=self.instance.descricao_atividade,
                    tipo_atividade=self.instance.tipo_atividade,
                    matricula_periodo=self.matricula_periodo,
                    dia_semana=dia_semana,
                    horario_aula=horario_aula,
                )


class AtividadeCurricularExtensaoExtraForm(forms.ModelForm):
    fieldsets = (('', {'fields': ('matricula_periodo', 'tipo_atividade', 'carga_horaria', 'descricao', 'documento')}),)

    class Meta:
        model = AtividadeCurricularExtensaoExtra
        exclude = ()

    def __init__(self, *args, **kwargs):
        aluno_pk = kwargs.pop('aluno_pk', None)
        super().__init__(*args, **kwargs)
        if aluno_pk is None:
            aluno_pk = self.instance.matricula_periodo.aluno_id
        self.fields['matricula_periodo'].queryset = MatriculaPeriodo.objects.filter(aluno_id=aluno_pk)
        self.fields['tipo_atividade'].queryset = TipoAtividadeCurricularExtensaoExtra.objects.filter(ativo=True)
        if self.instance.pk and settings.COMPONENTE_CH_DECIMAL:
            self.initial['carga_horaria'] = int(self.instance.carga_horaria / 100)

    def clean_carga_horaria(self):
        carga_horaria = self.cleaned_data.get('carga_horaria')
        if self.instance.id:
            atividade = AtividadeCurricularExtensao.objects.get(
                id_referencia=self.instance.id, tipo_referencia__model='atividadecurricularextensaoextra'
            )
            if atividade.get_carga_horaria_vinculada() > carga_horaria:
                raise forms.ValidationError(
                    f'Esta atividade já possui {atividade.get_carga_horaria_vinculada()}h distribuídas. Informe um valor igual ou maior.'
                )

        return carga_horaria

    def processar(self):
        self.instance.processar()


class VincularAtividadeExtensaoForm(forms.FormPlus):
    ch_aacc = forms.IntegerField(label='Atividade Complementar', required=False)
    ch_atpa = forms.IntegerField(label='Atividade de Aprofundamento', required=False)

    @staticmethod
    def _get_help_text_matricula_diario(md: MatriculaDiario) -> str:
        cc = md.diario.componente_curricular
        cc_associado = cc.componente_curricular_associado
        ch_total = cc.get_ch_extensao_exigida()
        msg_associado = ''
        if cc_associado and cc_associado.tipo != ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO and cc_associado.ch_extensao > 0:
            msg_associado = format_html(
                '<br>{} - {}: {} horas.<br>{} - {}: {} horas.',
                cc.componente.sigla,
                cc.componente.descricao_historico,
                cc.get_ch_extensao(),
                cc_associado.componente.sigla,
                cc_associado.componente.descricao_historico,
                cc_associado.get_ch_extensao(),
            )
        return format_html('Este componente exige <strong>{} horas</strong> de atividades de extensão.{}', ch_total, msg_associado)

    def __init__(self, atividade_extensao, *args, **kwargs):
        self.atividade_extensao = atividade_extensao
        self.vinculacoes = {
            obj.matricula_diario_id: {'carga_horaria': obj.carga_horaria, 'homologada': obj.homologada}
            for obj in self.atividade_extensao.vinculacaoatividadeextensao_set.all()
        }
        super().__init__(*args, **kwargs)
        qs_md = (
            MatriculaDiario.objects.filter(
                matricula_periodo__aluno_id=self.atividade_extensao.matricula_periodo.aluno_id,
            )
            .filter(ComponenteCurricular.get_filtro_com_extensao('diario__componente_curricular'))
            .select_related(
                'diario__ano_letivo',
                'diario__componente_curricular__componente',
                'diario__componente_curricular__componente_curricular_associado__componente',
            )
        )
        self.matriculas_diario = {}
        for md in qs_md:
            if md.pk in self.vinculacoes:
                initial = self.vinculacoes.get(md.pk).get('carga_horaria')
                readonly = self.vinculacoes.get(md.pk).get('homologada') or md.situacao != MatriculaDiario.SITUACAO_CURSANDO
            else:
                self.vinculacoes[md.pk] = {'carga_horaria': 0, 'homologada': False}
                initial = None
                readonly = md.situacao != MatriculaDiario.SITUACAO_CURSANDO

            if readonly and initial is None:
                # não cria campo se não possui CH distribuída e não pode ser editada
                continue

            self.matriculas_diario[f'{md.pk}'] = md
            self.fields[f'{md.pk}'] = forms.IntegerField(
                label=f'{md.diario.componente_curricular.componente.sigla} - {md.diario.componente_curricular.componente.descricao_historico} ({md.diario.ano_letivo.ano}.{md.diario.periodo_letivo})',
                required=False,
                initial=initial,
                help_text=self._get_help_text_matricula_diario(md),
            )
            if readonly:
                self.fields[f'{md.pk}'].widget.attrs.update(readonly=readonly)

        if not self.atividade_extensao.matriz_tem_extensao_aacc():
            self.fields['ch_aacc'].widget = forms.HiddenInput()
        elif self.atividade_extensao.aacc:
            self.fields['ch_aacc'].initial = self.atividade_extensao.aacc.carga_horaria
            if self.atividade_extensao.aacc.deferida:
                self.fields['ch_aacc'].widget.attrs.update(readonly=readonly)

        if not self.atividade_extensao.matriz_tem_extensao_atpa():
            self.fields['ch_atpa'].widget = forms.HiddenInput()
        elif self.atividade_extensao.atpa:
            self.fields['ch_atpa'].initial = self.atividade_extensao.atpa.carga_horaria
            if self.atividade_extensao.atpa.deferida:
                self.fields['ch_atpa'].widget.attrs.update(readonly=readonly)

        ch_nao_vinculada = self.atividade_extensao.get_ch_nao_vinculada()
        self.INFO = ''
        if ch_nao_vinculada:
            self.INFO += f'{self.atividade_extensao.get_ch_nao_vinculada()} hora(s) não distribuída(s).'
        else:
            self.INFO += 'Carga horária total já distribuída.'
        for vinculacao in self.atividade_extensao.vinculacaoatividadeextensao_set.all():
            self.INFO += f'</br>{vinculacao.carga_horaria} hora(s) para o diário "{vinculacao.matricula_diario.diario}".'
        if self.atividade_extensao.aacc_id:
            self.INFO += f'</br>{self.atividade_extensao.aacc.carga_horaria} hora(s) para a AACC "{self.atividade_extensao.aacc}".'
        if self.atividade_extensao.atpa_id:
            self.INFO += f'</br>{self.atividade_extensao.atpa.carga_horaria} hora(s) para a ATPA "{self.atividade_extensao.atpa}".'

    def _validar_limite_componente(self, field_name: str, md: MatriculaDiario, ch_campo: int, ch_outras: int) -> None:
        if ch_campo <= 0 or self.fields[field_name].widget.attrs.get('readonly'):
            return
        ch_requerida = md.diario.componente_curricular.get_ch_extensao_exigida() or 0
        if ch_requerida <= 0:
            return
        if ch_outras + ch_campo > ch_requerida:
            self.add_error(
                field_name,
                f'A carga horária distribuída para este componente ({ch_outras + ch_campo}h) '
                f'não pode exceder a carga horária exigida pela disciplina ({ch_requerida}h).',
            )

    def clean(self):
        ch = 0
        matriculas_diario = getattr(self, 'matriculas_diario', {})
        md_ids = [md.pk for k, md in matriculas_diario.items() if (self.cleaned_data.get(k) or 0) > 0]
        totais_outras = (
            VinculacaoAtividadeExtensao.get_totais_ch_por_matricula_diario(
                md_ids,
                excluir_atividade=self.atividade_extensao,
                incluir_pendentes=False,
            )
            if md_ids
            else {}
        )
        for k in self.fields:
            ch_campo = self.cleaned_data.get(k) or 0
            ch += ch_campo
            if k in matriculas_diario:
                ch_outras = totais_outras.get(matriculas_diario[k].pk, 0)
                self._validar_limite_componente(k, matriculas_diario[k], ch_campo, ch_outras)
        if ch > self.atividade_extensao.get_carga_horaria():
            raise forms.ValidationError(f'A carga horária distribuída não pode exceder {self.atividade_extensao.get_carga_horaria()} horas.')
        return self.cleaned_data

    def processar(self):
        ch_aacc = self.cleaned_data.get('ch_aacc')
        if ch_aacc:
            if self.atividade_extensao.aacc:
                self.atividade_extensao.aacc.carga_horaria = ch_aacc
                self.atividade_extensao.aacc.save()
            else:
                self.atividade_extensao.aacc = AtividadeComplementar.objects.create(
                    aluno=self.atividade_extensao.matricula_periodo.aluno,
                    carga_horaria=ch_aacc,
                    tipo=TipoAtividadeComplementar.objects.get_or_create(descricao='Atividade de Extensão')[0],
                    ano_letivo=self.atividade_extensao.matricula_periodo.ano_letivo,
                    periodo_letivo=self.atividade_extensao.matricula_periodo.periodo_letivo,
                    data_atividade=date.today(),
                    data_conclusao_atividade=date.today(),
                    descricao=f'{self.atividade_extensao} ({self.atividade_extensao.get_tipo()})',
                )
        else:
            if self.atividade_extensao.aacc:
                aacc = self.atividade_extensao.aacc
                self.atividade_extensao.aacc = None
                self.atividade_extensao.save()
                aacc.delete()

        ch_atpa = self.cleaned_data.get('ch_atpa')
        if ch_atpa:
            if self.atividade_extensao.atpa:
                self.atividade_extensao.atpa.carga_horaria = ch_atpa
                self.atividade_extensao.atpa.save()
            else:
                self.atividade_extensao.atpa = AtividadeAprofundamento.objects.create(
                    aluno=self.atividade_extensao.matricula_periodo.aluno,
                    carga_horaria=ch_atpa,
                    tipo=TipoAtividadeAprofundamento.objects.get_or_create(descricao='Atividade de Extensão')[0],
                    ano_letivo=self.atividade_extensao.matricula_periodo.ano_letivo,
                    periodo_letivo=self.atividade_extensao.matricula_periodo.periodo_letivo,
                    data_atividade=date.today(),
                    descricao=f'{self.atividade_extensao} ({self.atividade_extensao.get_tipo()})',
                )
        else:
            if self.atividade_extensao.atpa:
                atpa = self.atividade_extensao.atpa
                self.atividade_extensao.atpa = None
                self.atividade_extensao.save()
                atpa.delete()

        for pk in self.vinculacoes:
            carga_horaria = self.cleaned_data.get(f'{pk}')
            if carga_horaria:
                vinculacao = (
                    VinculacaoAtividadeExtensao.objects.filter(atividade_extensao=self.atividade_extensao, matricula_diario_id=pk).first()
                    or VinculacaoAtividadeExtensao()
                )
                vinculacao.matricula_diario_id = pk
                vinculacao.carga_horaria = carga_horaria
                vinculacao.atividade_extensao = self.atividade_extensao
                vinculacao.save()
            else:
                self.atividade_extensao.vinculacaoatividadeextensao_set.filter(matricula_diario_id=pk).exclude(homologada=True).delete()

        self.atividade_extensao.recalcular_carga_horaria_vinculada()


class AtividadePraticaProfissionalForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadePraticaProfissional
        fields = ('descricao', 'documento_inscricao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('edu.change_atividadepraticaprofissional'):
            self.fields['documento_inscricao'].required = True

    def processar(self, user, matricula_periodo_id, modalidade):
        self.instance.matricula_periodo_id = matricula_periodo_id
        self.instance.modalidade_pratica_profissional_id = modalidade
        self.save()
        if self.instance.pode_iniciar(user):
            self.instance.iniciar()


class ConcluirAtividadePraticaProfissionalForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadePraticaProfissional
        fields = ('carga_horaria', 'nota', 'documento_conclusao')

    def processar(self):
        self.instance.concluir()


class EditarAtividadePraticaProfissionalForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadePraticaProfissional
        fields = ('descricao', 'documento_inscricao', 'carga_horaria', 'nota', 'documento_conclusao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.situacao in [AtividadePraticaProfissional.SOLICITADA, AtividadePraticaProfissional.EM_ANDAMENTO]:
            del self.fields['carga_horaria']
            del self.fields['nota']
            del self.fields['documento_conclusao']
        if self.instance.situacao in [AtividadePraticaProfissional.CONCLUIDA, AtividadePraticaProfissional.INSUFICIENTE]:
            del self.fields['descricao']
            del self.fields['documento_inscricao']
            if self.instance.nota_editavel:
                del self.fields['carga_horaria']
                del self.fields['documento_conclusao']

    def processar(self):
        if self.instance.situacao in [AtividadePraticaProfissional.CONCLUIDA, AtividadePraticaProfissional.INSUFICIENTE]:
            self.instance.concluir()
        else:
            self.save()


class AvaliarAtividadePraticaProfissionalForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadePraticaProfissional
        fields = ('nota',)

    def processar(self):
        self.instance.concluir()
