import datetime
import os
from datetime import timedelta
from xml.dom import minidom

from django.apps.registry import apps
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.safestring import mark_safe

from comum.models import Ano, Sala, Vinculo
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
    RenderableSelectMultiple,
    TextareaCloneWidget,
)
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import format_, in_group
from djtools.utils import somar_dias
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    Aula,
    Componente,
    ConfiguracaoAvaliacao,
    CursoCampus,
    Diario,
    Diretoria,
    EntregaTrabalho,
    FrequenciaPraticaProfissional,
    HorarioAulaDiario,
    HorarioCampus,
    ItemConfiguracaoAvaliacao,
    MaterialAula,
    MaterialDiario,
    MatriculaDiario,
    MatriculaPeriodo,
    Matriz,
    NotaAvaliacao,
    ObservacaoDiario,
    OcorrenciaDiario,
    PeriodoLetivoAtual,
    Professor,
    ProfessorDiario,
    RespostaDiscussao,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    SolicitacaoProrrogacaoEtapa,
    SolicitacaoRelancamentoEtapa,
    SuspensaoDiario,
    TipoProfessorDiario,
    TopicoDiscussao,
    Trabalho,
)
from edu.models.professores import ConfiguracaoDadosDocentes
from rh.models import Servidor

from .utils import RedirectForm


class ProfessorDiarioForm(forms.ModelFormPlus):
    diario = forms.ModelChoiceField(queryset=Diario.objects, widget=forms.HiddenInput())
    vinculo = forms.ModelChoiceField(
        queryset=Vinculo.objects, label='Professor', required=True, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )
    periodo_letivo_ch = forms.ChoiceField(
        label='Período letivo da carga horária',
        required=False,
        help_text='Informar caso o percentual da carga horária ministrada se refira a apenas um período letivo.',
        choices=[[None, 'Todos'], *PERIODO_LETIVO_CHOICES],
    )

    fieldsets = (('', {'fields': ('diario',)}),)

    class Meta:
        model = ProfessorDiario
        exclude = ('professor',)

    def __init__(self, diario, *args, **kwargs):
        super().__init__(*args, **kwargs)

        qs_prestadores = Vinculo.objects.prestadores().filter(ativo=True, professor__isnull=False)
        qs_docentes = Vinculo.objects.servidores().filter(id_relacionamento__in=Servidor.objects.filter(eh_docente=True).values_list('id', flat=True))
        qs_tecnicos = Vinculo.objects.servidores().filter(
            id_relacionamento__in=Servidor.objects.filter(eh_tecnico_administrativo=True).values_list('id', flat=True)
        )
        if self.instance.pk:
            qs_docentes = qs_docentes.filter(ativo=True) | qs_docentes.filter(
                ativo=False, pk__in=self.instance.diario.professordiario_set.values_list('professor__vinculo__id', flat=True)
            )
            qs_tecnicos = qs_tecnicos.filter(ativo=True) | qs_tecnicos.filter(
                ativo=False, pk__in=self.instance.diario.professordiario_set.values_list('professor__vinculo__id', flat=True)
            )
        else:
            qs_docentes = qs_docentes.filter(ativo=True)
            qs_tecnicos = qs_tecnicos.filter(ativo=True)
        self.fields['vinculo'].queryset = (qs_docentes | qs_tecnicos | qs_prestadores).distinct()
        self.fields['diario'].queryset = Diario.locals.all()

        if self.instance.pk:
            self.fields['vinculo'].initial = self.instance.professor.vinculo.pk

        is_administrador = in_group(self.request.user, 'Administrador Acadêmico')
        if not is_administrador:
            self.fields['ativo'].widget = forms.HiddenInput()

        self.diario = diario
        self.fields['diario'].initial = self.diario.pk
        self._configurar_periodo_letivo_ch()

        self.rit_publicado = self.instance and self.instance.pk and self.instance.is_rit_publicado()

        if self.rit_publicado:
            self.fields.pop('tipo')
            self.fields.pop('vinculo')
            self.fields.pop('ativo')
            self.fields.pop('financiamento_externo')
            self.fields.pop('percentual_ch')
            self.fields.pop('periodo_letivo_ch')
        else:
            self.fieldsets += (('Vínculo', {'fields': ('vinculo', ('tipo', 'ativo'), 'financiamento_externo')}),)
            self.fieldsets += (('Carga Horária', {'fields': (('percentual_ch', 'periodo_letivo_ch'),)}),)

        self._configurar_fieldsets_etapas()
        for field_name in self.fields:
            if 'data_' in field_name:
                self.fields[field_name].help_text = ''

    def _configurar_periodo_letivo_ch(self) -> None:
        if self.diario.is_semestral_em_calendario_anual():
            periodo = 2 if self.diario.segundo_semestre else 1
            self.fields['periodo_letivo_ch'].choices = [
                [periodo, periodo],
            ]
            self.initial['periodo_letivo_ch'] = periodo
            self.fields['periodo_letivo_ch'].help_text = ''
        elif not self.diario.is_anual():
            self.fields['periodo_letivo_ch'].choices = [
                [self.diario.periodo_letivo, self.diario.periodo_letivo],
            ]
            self.initial['periodo_letivo_ch'] = self.diario.periodo_letivo
            self.fields['periodo_letivo_ch'].help_text = ''

    def _configurar_fieldsets_etapas(self) -> None:
        if not self.diario.componente_curricular:
            return

        qtd_avaliacoes = self.diario.componente_curricular.qtd_avaliacoes
        descricao_etapa_1 = 'Terceira Etapa' if self.diario.is_semestral_segundo_semestre() else 'Primeira Etapa'
        self.fieldsets += ((descricao_etapa_1, {'fields': (('data_inicio_etapa_1', 'data_fim_etapa_1'),)}),)
        self.fields['data_inicio_etapa_1'].initial = self.diario.get_inicio_etapa_1()
        self.fields['data_fim_etapa_1'].initial = self.flexibilizar_data(self.diario.get_fim_etapa_1())

        if qtd_avaliacoes >= 2:
            descricao_etapa_2 = 'Quarta Etapa' if self.diario.is_semestral_segundo_semestre() else 'Segunda Etapa'
            self.fieldsets += ((descricao_etapa_2, {'fields': (('data_inicio_etapa_2', 'data_fim_etapa_2'),)}),)
            self.fields['data_inicio_etapa_2'].initial = self.diario.get_inicio_etapa_2()
            self.fields['data_fim_etapa_2'].initial = self.flexibilizar_data(self.diario.get_fim_etapa_2())

        if qtd_avaliacoes >= 3:
            self.fieldsets += (('Terceira Etapa', {'fields': (('data_inicio_etapa_3', 'data_fim_etapa_3'),)}),)
            self.fields['data_inicio_etapa_3'].initial = self.diario.get_inicio_etapa_3()
            self.fields['data_fim_etapa_3'].initial = self.flexibilizar_data(self.diario.get_fim_etapa_3())

        if qtd_avaliacoes >= 4:
            self.fieldsets += (('Quarta Etapa', {'fields': (('data_inicio_etapa_4', 'data_fim_etapa_4'),)}),)
            self.fields['data_inicio_etapa_4'].initial = self.diario.get_inicio_etapa_4()
            self.fields['data_fim_etapa_4'].initial = self.flexibilizar_data(self.diario.get_fim_etapa_4())

        if qtd_avaliacoes > 0:
            self.fieldsets += (('Etapa Final', {'fields': (('data_inicio_etapa_final', 'data_fim_etapa_final'),)}),)
            self.fields['data_inicio_etapa_final'].initial = self.diario.get_inicio_etapa_final()
            self.fields['data_fim_etapa_final'].initial = self.flexibilizar_data(self.diario.get_fim_etapa_final())

    def flexibilizar_data(self, data):
        if not data:
            return None
        return somar_dias(data, 7)

    def save(self, *args, **kwargs):
        if self.instance.pk:
            super().save()
        else:
            vinculo = self.cleaned_data['vinculo']
            obj = super().save(False)
            qs = Professor.objects.filter(vinculo__id=vinculo.pk)
            if qs.exists():
                obj.professor = qs[0]
            else:
                professor = Professor()
                professor.vinculo = vinculo
                professor.save()
                obj.professor = professor
                Group.objects.get(name='Professor').user_set.add(professor.vinculo.user)
            obj.save()

    def clean_percentual_ch(self):
        if self.cleaned_data.get('percentual_ch') > 100:
            raise forms.ValidationError('O percentual de CH ministrada não pode ser maior que 100%.')
        return self.cleaned_data.get('percentual_ch')

    def clean_vinculo(self):
        qs = self.diario.professordiario_set
        if self.instance.id:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists() and self.cleaned_data.get('vinculo').id in qs.values_list('professor__vinculo__id', flat=True):
            raise forms.ValidationError('Professor já cadastrado neste diário.')
        return self.cleaned_data.get('vinculo')

    def clean_periodo_letivo_ch(self):
        return self.cleaned_data.get('periodo_letivo_ch') or None

    def _validar_datas_etapa(self, nome_etapa: str, rotulo: str) -> None:
        data_inicio = self.cleaned_data.get(f'data_inicio_{nome_etapa}')
        data_fim = self.cleaned_data.get(f'data_fim_{nome_etapa}')
        if data_inicio and data_fim and data_inicio > data_fim:
            raise forms.ValidationError(f'A data de início da {rotulo} não pode ser maior que a data de encerramento da mesma etapa.')
        if data_inicio and not data_fim:
            raise forms.ValidationError(f'Favor preencher a data de encerramento da {rotulo}.')
        if data_fim and not data_inicio:
            raise forms.ValidationError(f'Favor preencher a data de início da {rotulo}.')

    def _verificar_rit_publicado(self, diario, professor) -> None:
        if self.cleaned_data.get('financiamento_externo'):
            return

        periodo_letivo_selecionado = self.cleaned_data.get('periodo_letivo_ch')
        periodo_letivo = [1, 2] if periodo_letivo_selecionado is None else [periodo_letivo_selecionado]
        rit_publicado = False

        if 'pit_rit_v3' in settings.INSTALLED_APPS:
            from pit_rit_v3.models import PlanoIndividualTrabalhoV3

            rit_publicado = PlanoIndividualTrabalhoV3.objects.filter(
                ano_letivo_id=diario.ano_letivo_id, periodo_letivo__in=periodo_letivo, professor_id=professor.id, publicado=True
            ).exists()

        if not rit_publicado and 'pit_rit_v2' in settings.INSTALLED_APPS:
            from pit_rit_v2.models import PlanoIndividualTrabalhoV2

            rit_publicado = PlanoIndividualTrabalhoV2.objects.filter(
                ano_letivo_id=diario.ano_letivo_id, periodo_letivo__in=periodo_letivo, professor_id=professor.id, publicado=True
            ).exists()

        if rit_publicado:
            raise forms.ValidationError('Esse professor já possui RIT publicado no período letivo selecionado.')

    def clean(self):
        for i in range(1, 5):
            self._validar_datas_etapa(f'etapa_{i}', f'etapa {i}')
        self._validar_datas_etapa('etapa_final', 'etapa final')

        # verificando choque de horário com outros diário no mesmo período letivo
        if settings.IMPEDIR_CHOQUE_HORARIOS_PROFESSOR:
            diarios_choque_horario = self.instance.get_diarios_choque_horario()
            if diarios_choque_horario:
                raise forms.ValidationError(
                    'Não é possível adicionar esse professor ao diário, pois há choque de horário com o(s) diário(s): {}'.format(
                        ', '.join(str(id) for id in diarios_choque_horario)
                    )
                )

        diario = self.cleaned_data.get('diario')
        vinculo = self.cleaned_data.get('vinculo')
        professor = vinculo and Professor.objects.filter(vinculo__id=vinculo.pk).first()
        if professor:
            if professor.tipo == Professor.TIPO_FIC and not diario.turma.curso_campus.is_fic():
                raise forms.ValidationError(
                    'Esse professor só pode ser adicionado a diários de cursos FIC. É necessário atualizar seu cadastro atualizando o tipo para "Curso Regular" antes de vinculá-lo a esse diário.'
                )

            self._verificar_rit_publicado(diario, professor)

        if diario.situacao == Diario.SITUACAO_FECHADO:
            raise forms.ValidationError('Não é possível adicionar professor a um diário que já está fechado.')

        return self.cleaned_data


class TransferirDiarioForm(FormWizardPlus):
    METHOD = 'POST'
    LAST_SUBMIT_LABEL = 'Transferir Alunos Selecionados.'
    diario_destino = forms.ModelChoiceField(Diario.objects.none(), label='Diário de Destino', widget=forms.RadioSelect(), empty_label=None)
    confirmacao = forms.BooleanField(label='Confirmação', required=False, help_text='Marque a opção acima e clique no botão "Finalizar".')

    steps = ([('Diário de Destino', {'fields': ('diario_destino',)})], [('Confirmação dos Dados', {'fields': ('confirmacao',)})])

    def __init__(self, diario_origem, *args, **kwargs):
        self.diario_origem = diario_origem
        super().__init__(*args, **kwargs)

    def first_step(self):
        self.fields['diario_destino'].queryset = Diario.locals.filter(
            componente_curricular__componente=self.diario_origem.componente_curricular.componente,
            ano_letivo=self.diario_origem.ano_letivo,
            periodo_letivo=self.diario_origem.periodo_letivo,
        ).exclude(pk=self.diario_origem.pk)


class DiarioForm(forms.ModelFormPlus):
    class Meta:
        model = Diario
        exclude = (
            'turma',
            'componente_curricular',
            'ano_letivo',
            'periodo_letivo',
            'situacao',
            'horario_campus',
            'turno',
            'estrutura_curso',
            'calendario_academico',
            'local_aula',
            'local_laboratorio',
            'locais_aula_secundarios',
            'posse_etapa_1',
            'posse_etapa_2',
            'posse_etapa_3',
            'posse_etapa_4',
            'posse_etapa_5',
            'search_fields_optimized',
            'possui_segunda_oferta',
            'diario_primeira_oferta',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.componente_curricular and not self.instance.componente_curricular.is_dinamico:
            self.fields['descricao_dinamica'].widget = forms.HiddenInput()

    def clean_segundo_semestre(self):
        segundo_semestre = self.cleaned_data['segundo_semestre']
        if (
            segundo_semestre
            and self.instance.turma.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL
            and self.instance.componente_curricular.qtd_avaliacoes != 2
        ):
            raise forms.ValidationError('Somente diário com duas etapas de um curso de periodicidade anual pode ser marcado como de Segundo Semestre')
        return segundo_semestre


class AulaForm(forms.ModelFormPlus):
    professor_diario = forms.ModelChoiceField(queryset=ProfessorDiario.objects, label='Professor', required=True)
    conteudo = forms.CharField(label='Conteúdo', widget=TextareaCloneWidget())
    url = forms.CharField(
        label='URL',
        required=False,
        help_text='Link disponbilizado na turma virtual para os alunos caso a transmissão seja realizada através de alguma plataforma multi-media ou streaming',
    )
    outros_professor_diario = forms.MultipleModelChoiceField(
        ProfessorDiario.objects,
        label='Outros Professores',
        required=False,
        help_text='A CH desta aula será compartilhada com os professores selecionados',
    )

    class Meta:
        model = Aula
        exclude = ()

    fieldsets = (
        (
            'Dados da Aula',
            {'fields': ('professor_diario', ('quantidade', 'tipo'), ('etapa', 'data'), 'conteudo', 'ead', 'url', 'outros_professor_diario')},
        ),
    )

    def __init__(self, diario, etapa, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.diario = diario
        self.etapa = etapa

        outro_professor_editando = self.instance.pk and self.instance.professor_diario.professor.vinculo.user != self.request.user
        if outro_professor_editando:
            outros_professores_qs = self.diario.professordiario_set.exclude(professor=self.instance.professor_diario.professor)
        else:
            outros_professores_qs = self.diario.professordiario_set.exclude(professor__vinculo__user=self.request.user)

        if outros_professores_qs.exists():
            self.fields['outros_professor_diario'].queryset = outros_professores_qs
            self.fields['outros_professor_diario'].label_from_instance = lambda obj: f'{obj.professor}'
        else:
            del self.fields['outros_professor_diario']

        if hasattr(self.instance, 'outros_professor_diario') and self.instance.outros_professor_diario.exists():
            self.initial['outros_professor_diario'] = list(self.instance.outros_professor_diario.values_list('id', flat=True))

        if outro_professor_editando:
            professor_qs = self.diario.professordiario_set.filter(professor=self.instance.professor_diario.professor)
        else:
            professor_qs = self.diario.professordiario_set.filter(professor__vinculo__user=self.request.user)
        professor_diario = None
        if professor_qs.exists():
            professor_diario = professor_qs[0]
            self.fields['professor_diario'].queryset = professor_qs
        else:
            qs = diario.professordiario_set.all()
            self.fields['professor_diario'].queryset = qs
            if qs.count() == 1:
                professor_diario = qs[0]

        if self.fields['professor_diario'].queryset.count() == 1:
            self.fields['professor_diario'].widget = forms.HiddenInput()
        else:
            self.fields['professor_diario'].label_from_instance = lambda obj: f'{obj.professor}'

        if self.diario.componente_curricular.qtd_avaliacoes == 1:
            if self.diario.is_semestral_segundo_semestre():
                self.fields['etapa'].choices = Aula.ETAPA_CHOICES_SEGUNGO_SEMESTRE[0:1] + Aula.ETAPA_CHOICES[4:5]
            else:
                self.fields['etapa'].choices = Aula.ETAPA_CHOICES[0:1] + Aula.ETAPA_CHOICES[4:5]
        elif self.diario.componente_curricular.qtd_avaliacoes == 2:
            if self.diario.is_semestral_segundo_semestre():
                self.fields['etapa'].choices = Aula.ETAPA_CHOICES_SEGUNGO_SEMESTRE + Aula.ETAPA_CHOICES[4:5]
            else:
                self.fields['etapa'].choices = Aula.ETAPA_CHOICES[0:2] + Aula.ETAPA_CHOICES[4:5]
        if not self.instance.data:
            self.fields['data'].initial = datetime.date.today()
        if not self.instance.pk:
            self.fields['etapa'].initial = etapa

        if professor_diario:
            self.fields['professor_diario'].initial = professor_diario.pk
            lista = []
            for diario in Diario.objects.filter(
                professordiario__professor=professor_diario.professor, componente_curricular=professor_diario.diario.componente_curricular
            ).order_by('-id')[0:3]:
                qs = Aula.objects.filter(professor_diario__professor=professor_diario.professor, professor_diario__diario=diario)
                if qs.exists():
                    lista.append(f'<h4>{diario}</h4>')
                for aula in qs:
                    lista.append(
                        '<div><strong>{}</strong> <p>{}</p></div>'.format(
                            format_(aula.data), aula.conteudo.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                        )
                    )

            if not lista:
                lista.append('<strong>Atenção</strong>: Nenhum registro de aula relacionado a esta disciplina foi encontrado.')
            self.fields['conteudo'].widget.clones = ''.join(lista)

        if self.diario.componente_curricular.matriz.estrutura.limitar_ch_por_tipo_aula:
            tipo_choices = [[Aula.AULA, 'Aula Teórica']]
            if self.diario.componente_curricular.ch_pratica:
                tipo_choices.append([Aula.PRATICA, 'Aula Prática'])
            if self.diario.componente_curricular.ch_extensao:
                tipo_choices.append([Aula.EXTENSAO, 'Atividade de Extensão'])
            if self.diario.componente_curricular.ch_pcc:
                tipo_choices.append([Aula.PRATICA_COMO_COMPONENTE_CURRICULAR, 'Prática como Componente Curricular'])
            if self.diario.componente_curricular.ch_visita_tecnica:
                tipo_choices.append([Aula.VISITA_TECNICA, 'Visita Técnica / Aula de Campo'])
            self.fields['tipo'].choices = tipo_choices
        else:
            self.fields['tipo'].widget = forms.HiddenInput()
            self.fields['tipo'].initial = Aula.AULA

        if not self.diario.componente_curricular.possui_ch_ead():
            self.fields['ead'].widget = forms.HiddenInput()

    def clean_ead(self):
        ead = self.cleaned_data.get('ead')
        quantidade = self.cleaned_data.get('quantidade')
        if ead and quantidade and self.diario.componente_curricular.possui_ch_ead():
            qtd_disponivel = self.diario.get_carga_horaria_ead_disponivel()
            if quantidade > qtd_disponivel:
                raise forms.ValidationError(f'A quantidade disponível de aula EAD para esse diário é de {qtd_disponivel} aula(s).')
        return ead

    def clean_data(self):
        data = self.cleaned_data['data']
        professor_diario = self.cleaned_data.get('professor_diario')
        if not professor_diario:
            return data
        if (
            professor_diario.diario.calendario_academico.data_inicio_espaco_pedagogico
            and professor_diario.diario.calendario_academico.data_fim_espaco_pedagogico
            and data >= professor_diario.diario.calendario_academico.data_inicio_espaco_pedagogico
            and data <= professor_diario.diario.calendario_academico.data_fim_espaco_pedagogico
        ):
            return data
        if (
            professor_diario.diario.calendario_academico.data_inicio_etapa_1
            and professor_diario.diario.calendario_academico.data_fim_etapa_1
            and data >= professor_diario.diario.calendario_academico.data_inicio_etapa_1
            and data <= professor_diario.diario.calendario_academico.data_fim_etapa_1
        ):
            return data
        if (
            professor_diario.diario.calendario_academico.data_inicio_etapa_2
            and professor_diario.diario.calendario_academico.data_fim_etapa_2
            and data >= professor_diario.diario.calendario_academico.data_inicio_etapa_2
            and data <= professor_diario.diario.calendario_academico.data_fim_etapa_2
        ):
            return data
        if (
            professor_diario.diario.calendario_academico.data_inicio_etapa_3
            and professor_diario.diario.calendario_academico.data_fim_etapa_3
            and data >= professor_diario.diario.calendario_academico.data_inicio_etapa_3
            and data <= professor_diario.diario.calendario_academico.data_fim_etapa_3
        ):
            return data
        if (
            professor_diario.diario.calendario_academico.data_inicio_etapa_4
            and professor_diario.diario.calendario_academico.data_fim_etapa_4
            and data >= professor_diario.diario.calendario_academico.data_inicio_etapa_4
            and data <= professor_diario.diario.calendario_academico.data_fim_etapa_4
        ):
            return data
        if (
            professor_diario.diario.get_inicio_etapa_final()
            and professor_diario.diario.get_fim_etapa_final()
            and data >= professor_diario.diario.get_inicio_etapa_final()
            and data <= professor_diario.diario.get_fim_etapa_final()
        ):
            return data
        if professor_diario.diario.componente_curricular.qtd_avaliacoes == 1 and professor_diario.diario.calendario_academico.qtd_etapas == 2:
            return data
        raise forms.ValidationError('A data não compreende o intervalo do calendário acadêmico.')

    def clean_outros_professor_diario(self):
        outros_professor_diario = self.cleaned_data['outros_professor_diario']
        professor_diario = self.cleaned_data.get('professor_diario')
        if professor_diario in outros_professor_diario:
            raise forms.ValidationError(
                f'O professor {professor_diario.professor} é o responsável pela aula e não pode ser selecionado para receber o compartilhamento da CH dessa aula.'
            )
        return outros_professor_diario

    def clean_quantidade(self):
        quantidade = self.cleaned_data.get('quantidade')
        if self.instance.id:
            qtd_anterior = Aula.objects.get(id=self.instance.id).quantidade
            if qtd_anterior != quantidade and self.instance.falta_set.filter(quantidade__gt=quantidade).exists():
                raise forms.ValidationError(
                    'Não é possível a alterar a quantidade de aulas pois há alunos com registro de falta maior que a quantidade de aulas.'
                )

        return quantidade


class DefinirLocalAulaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'
    sala = forms.ModelChoiceFieldPlus(Sala.ativas, required=False)
    laboratorio = forms.ModelChoiceFieldPlus(Sala.ativas, label='Laboratório', required=False)
    salas_secundarias = forms.MultipleModelChoiceFieldPlus(Sala.ativas, label='Salas secundárias', required=False)

    def __init__(self, diario, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diario = diario
        uo = diario.calendario_academico.uo
        self.fields['sala'].queryset = Sala.objects.filter(
            pk__in=Sala.ativas.filter(predio__uo_id=uo.id, laboratorio__isnull=True).order_by('pk').values_list('pk', flat=True)
        )
        self.initial['sala'] = diario.local_aula_id

        self.fields['laboratorio'].queryset = Sala.objects.filter(
            pk__in=Sala.ativas.filter(predio__uo_id=uo.id, laboratorio__isnull=False).order_by('pk').values_list('pk', flat=True)
        )
        self.initial['laboratorio'] = diario.local_laboratorio_id

        self.fields['salas_secundarias'].queryset = Sala.ativas.filter(predio__uo_id=uo.id)
        self.initial['salas_secundarias'] = diario.locais_aula_secundarios.values_list('id', flat=True)

    def processar(self):
        self.diario.local_aula = self.cleaned_data['sala']
        self.diario.local_laboratorio = self.cleaned_data['laboratorio']
        self.diario.locais_aula_secundarios.set(self.cleaned_data['salas_secundarias'])
        self.diario.save()


class AlterarNotaForm(forms.FormPlus):
    nota = forms.IntegerFieldPlus(required=False, help_text='Valor entre 0 e 100')


class BuscaDiarioForm(RedirectForm):
    diario = forms.ModelChoiceFieldPlus(
        Diario.objects.none(),
        label='Código/Descrição',
        help_text='Para encontrar um diário entre com a sigla do componente ou o id do diário',
        widget=AutocompleteWidget(search_fields=Diario.SEARCH_FIELDS),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diario'].queryset = Diario.locals.all()

    def get_url(self):
        return self.cleaned_data['diario'].get_absolute_url()


class MateriaisAulaForm(forms.FormPlus):
    diarios = forms.MultipleModelChoiceField(
        Diario.objects.none(), label='', widget=RenderableSelectMultiple('widgets/diarios_cadastro_material_widget.html'), required=False
    )

    quantidade = forms.ChoiceField(
        choices=[[1, 1], [2, 2], [3, 3], [4, 4], [5, 5]],
        label='Quantidade',
        help_text='Informe a quantidade de materiais de aula que deseja cadastrar',
        widget=forms.RadioSelect(),
        initial=1,
        required=False,
    )

    publico = forms.BooleanField(
        label='Público', required=False, help_text='Marque essa opção caso deseje que outros professores visualizem o material'
    )

    descricao1 = forms.CharFieldPlus(label='Descrição', required=False)
    tipo1 = forms.ChoiceField(choices=[[1, 'Upload'], [2, 'Link']], label='Tipo', widget=forms.RadioSelect(), initial=1, required=False)
    arquivo1 = forms.FileFieldPlus(label='Arquivo', required=False)
    url1 = forms.CharFieldPlus(label='URL do Arquivo', required=False)

    descricao2 = forms.CharFieldPlus(label='Descrição', required=False)
    tipo2 = forms.ChoiceField(choices=[[1, 'Upload'], [2, 'Link']], label='Tipo', widget=forms.RadioSelect(), initial=1, required=False)
    arquivo2 = forms.FileFieldPlus(label='Arquivo', required=False)
    url2 = forms.CharFieldPlus(label='URL do Arquivo', required=False)

    descricao3 = forms.CharFieldPlus(label='Descrição', required=False)
    tipo3 = forms.ChoiceField(choices=[[1, 'Upload'], [2, 'Link']], label='Tipo', widget=forms.RadioSelect(), initial=1, required=False)
    arquivo3 = forms.FileFieldPlus(label='Arquivo', required=False)
    url3 = forms.CharFieldPlus(label='URL do Arquivo', required=False)

    descricao4 = forms.CharFieldPlus(label='Descrição', required=False)
    tipo4 = forms.ChoiceField(choices=[[1, 'Upload'], [2, 'Link']], label='Tipo', widget=forms.RadioSelect(), initial=1, required=False)
    arquivo4 = forms.FileFieldPlus(label='Arquivo', required=False)
    url4 = forms.CharFieldPlus(label='URL do Arquivo', required=False)

    descricao5 = forms.CharFieldPlus(label='Descrição', required=False)
    tipo5 = forms.ChoiceField(choices=[[1, 'Upload'], [2, 'Link']], label='Tipo', widget=forms.RadioSelect(), initial=1, required=False)
    arquivo5 = forms.FileFieldPlus(label='Arquivo', required=False)
    url5 = forms.CharFieldPlus(label='URL do Arquivo', required=False)

    notificar_aluno = forms.BooleanField(
        label='Notificar alunos',
        help_text='Marque essa opção caso deseje que os alunos dos diários selecionados recebam a notificação do cadastro deste material de aula.',
        required=False,
    )
    exibir_no_portal = forms.BooleanField(
        label='Exibir este material no portal institucional?',
        required=False,
        help_text='Marque essa opção caso deseje que o material de aula seja exibido no portal institucional.',
    )

    fieldsets = (
        ('Dados gerais', {'fields': ('quantidade', 'publico', 'exibir_no_portal')}),
        ('Material 1', {'fields': ('descricao1', 'tipo1', 'arquivo1', 'url1')}),
        ('Material 2', {'fields': ('descricao2', 'tipo2', 'arquivo2', 'url2')}),
        ('Material 3', {'fields': ('descricao3', 'tipo3', 'arquivo3', 'url3')}),
        ('Material 4', {'fields': ('descricao4', 'tipo4', 'arquivo4', 'url4')}),
        ('Material 5', {'fields': ('descricao5', 'tipo5', 'arquivo5', 'url5')}),
        ('Diários', {'fields': ('diarios',)}),
        ('Notificação', {'fields': ('notificar_aluno',)}),
    )

    class Media:
        js = ('/static/edu/js/MateriaisAulaForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.professor = Professor.objects.get(vinculo__user=self.request.user)
        self.fields['diarios'].queryset = self.qs_diarios()
        if self.request.GET.get('diario'):
            self.fields['diarios'].initial = Diario.objects.filter(pk=self.request.GET['diario']).values_list('pk', flat=True)

        tem_config_valida = hasattr(self.professor, 'config_dados_docentes') and self.professor.config_dados_docentes.modo_exibicao
        if (not tem_config_valida) or (tem_config_valida != ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA):
            del self.fields['exibir_no_portal']

    def qs_diarios(self):
        qs = Diario.objects.filter(professordiario__professor__vinculo__user__username=self.request.user.username)
        pk = self.request.GET.get('diario')
        if pk:
            diario = Diario.objects.get(pk=pk)
            qs = qs.filter(ano_letivo=diario.ano_letivo, periodo_letivo=diario.periodo_letivo)
        return qs.order_by('ano_letivo', '-pk')

    def processar(self):
        hoje = datetime.datetime.now()
        materiais = []

        for quantidade in range(1, int(self.cleaned_data.get('quantidade')) + 1):
            material = MaterialAula()
            material.data_cadastro = hoje
            material.publico = self.cleaned_data.get('publico')
            material.descricao = self.cleaned_data.get(f'descricao{quantidade}')
            material.arquivo = self.cleaned_data.get(f'arquivo{quantidade}')
            material.url = self.cleaned_data.get(f'url{quantidade}')
            material.professor = self.professor
            material.exibir_no_portal = self.cleaned_data.get('exibir_no_portal', False)
            material.save()
            materiais.append(material)

        todos_diarios = self.qs_diarios()
        diarios_selecionados = self.cleaned_data.get('diarios')

        for diario in todos_diarios:
            professor_diario = ProfessorDiario.objects.get(professor=self.professor, diario=diario)
            for material in materiais:
                material_diario = MaterialDiario.objects.filter(professor_diario=professor_diario, material_aula=material)
                if material_diario.exists() and diario not in diarios_selecionados:
                    material_diario.delete()
                elif not material_diario.exists() and diario in diarios_selecionados:
                    material_diario = MaterialDiario()
                    material_diario.professor_diario = professor_diario
                    material_diario.material_aula = material
                    material_diario.save()
        return self.cleaned_data.get('notificar_aluno') or False, diarios_selecionados, materiais

    def clean(self):
        for quantidade in range(1, int(self.cleaned_data.get('quantidade')) + 1):
            arquivo = self.cleaned_data.get(f'arquivo{quantidade}')
            url = self.cleaned_data.get(f'url{quantidade}')
            if arquivo:
                if hasattr(arquivo, 'path') and not os.path.exists(arquivo.path):
                    raise forms.ValidationError('Arquivo inexistente.')
                if len(arquivo.name) > 70:
                    raise forms.ValidationError(f'O nome do arquivo no Material {quantidade} deve conter no máximo 70 caracteres.')
            if not arquivo and not url:
                raise forms.ValidationError(f'Faça o upload ou insira a URL do Material {quantidade}.')
        return self.cleaned_data


class MaterialAulaForm(forms.ModelFormPlus):
    tipo = forms.ChoiceField(choices=[[1, 'Upload'], [2, 'Link']], widget=forms.RadioSelect(), initial=1)
    arquivo = forms.FileFieldPlus(required=False)
    diarios = forms.MultipleModelChoiceField(
        Diario.objects.none(), label='', widget=RenderableSelectMultiple('widgets/diarios_cadastro_material_widget.html'), required=False
    )
    exibir_no_portal = forms.BooleanField(
        label='Exibir este material no portal institucional?',
        required=False,
        help_text='Marque essa opção caso deseje que o material de aula seja exibido no portal institucional.',
    )

    class Meta:
        model = MaterialAula
        fields = ['descricao', 'arquivo', 'url', 'publico', 'exibir_no_portal']

    class Media:
        js = ('/static/edu/js/MaterialAulaForm.js',)

    fieldsets = (
        ('Dados gerais', {'fields': ('descricao', 'tipo', 'publico', 'exibir_no_portal')}),
        ('Arquivo', {'fields': ('arquivo', 'url')}),
        ('Diários', {'fields': ('diarios',)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.professor = Professor.objects.get(vinculo__user=self.request.user)
        self.fields['tipo'].initial = self.instance.arquivo and 1 or 2

        self.fields['diarios'].queryset = self.qs_diarios()
        self.fields['diarios'].initial = MaterialDiario.objects.filter(material_aula=self.instance.pk).values_list(
            'professor_diario__diario', flat=True
        )
        tem_config_valida = hasattr(self.professor, 'config_dados_docentes') and self.professor.config_dados_docentes.modo_exibicao
        if (not tem_config_valida) or (tem_config_valida != ConfiguracaoDadosDocentes.EXIBICAO_COMPLETA):
            # Oculta o campo ao invés de removê-lo
            self.fields['exibir_no_portal'].widget = forms.HiddenInput()
            self.fields['exibir_no_portal'].required = False

    def clean(self):
        arquivo = self.cleaned_data.get('arquivo')
        url = self.cleaned_data.get('url')

        if arquivo:
            if len(arquivo.name) > 70:
                raise forms.ValidationError('O nome do arquivo deve conter no máximo 70 caracteres.')

        if not arquivo and not url:
            raise forms.ValidationError('Faça upload ou insira uma url.')
        else:
            return self.cleaned_data

    def save(self, *args, **kwargs):
        obj = super().save(False)
        obj.professor = self.professor
        obj.save()

        todos_diarios = self.qs_diarios()
        for diario in todos_diarios:
            professor_diario = ProfessorDiario.objects.get(professor=self.professor, diario=diario)
            material_diario = MaterialDiario.objects.filter(professor_diario=professor_diario, material_aula=obj)
            if material_diario.exists() and diario not in self.cleaned_data['diarios']:
                material_diario.delete()
            elif not material_diario.exists() and diario in self.cleaned_data['diarios']:
                material_diario = MaterialDiario()
                material_diario.professor_diario = professor_diario
                material_diario.material_aula = obj
                material_diario.save()

        return obj

    def qs_diarios(self):
        periodo_letivo_atual = PeriodoLetivoAtual.get_instance(self.request)
        qs = Diario.objects.filter(professordiario__professor=self.professor, ano_letivo__ano=periodo_letivo_atual.ano).order_by(
            '-periodo_letivo', '-pk'
        )
        return qs


class EntregaEtapaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Confirmar Entrega'

    sem_aula = forms.BooleanField(
        label='Confirmar entrega sem aula',
        required=True,
        help_text='Quero entregar a etapa sem aula lançada. A carga horária mínima deverá ser cumprida até a entrega da última etapa.',
    )

    zerar_notas = forms.BooleanField(
        label='Confirmar entrega sem nota',
        required=False,
        help_text='Quero entregar a etapa sem nota lançada para o(s) aluno(s) abaixo. As notas em branco serão consideradas como zero.',
    )

    def __init__(self, tem_nota_vazia, pode_entregar_sem_aula, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not pode_entregar_sem_aula:
            self.fields['sem_aula'].widget = forms.HiddenInput()
            self.fields['sem_aula'].required = False
        if not tem_nota_vazia:
            self.fields['zerar_notas'].widget = forms.HiddenInput()


class VincularMaterialAulaForm(forms.FormPlus):
    materiais_aula = forms.MultipleModelChoiceFieldPlus(
        queryset=MaterialAula.objects.none(),
        label='Materiais de aula',
        help_text=mark_safe(
            'Se você não lembra da descrição do material desejado, <a target="_blank" href="/admin/edu/materialaula/?tab=tab_meus_materiais"><strong>liste seus materiais cadastrados</strong></a> em uma nova aba.'
        ),
    )
    diarios = forms.MultipleModelChoiceField(
        Diario.objects.none(),
        label='Outros Diários',
        required=False,
        help_text='Informe os diários relacionados nos quais você também gostaria de vincular o material ou materiais selecionados.',
        widget=forms.CheckboxSelectMultiplePlus,
    )

    def __init__(self, *args, **kwargs):
        self.professor_diario = kwargs.pop('professor_diario')
        super().__init__(*args, **kwargs)
        professor = self.professor_diario.professor
        self.fields['materiais_aula'].queryset = MaterialAula.objects.filter(professor=professor).exclude(
            materialdiario__professor_diario_id=self.professor_diario.id
        )
        self.fields['diarios'].queryset = Diario.objects.filter(
            professordiario__professor=professor,
            ano_letivo=self.professor_diario.diario.ano_letivo,
            periodo_letivo=self.professor_diario.diario.periodo_letivo,
        ).exclude(pk=self.professor_diario.diario.pk)
        if not self.fields['diarios'].queryset.exists():
            del self.fields['diarios']

    def processar(self, etapa):
        professores_diario = [self.professor_diario]
        diarios = self.cleaned_data.get('diarios')
        if diarios:
            for diario in diarios:
                professores_diario.append(diario.professordiario_set.get(professor=self.professor_diario.professor))
        for professor_diario in professores_diario:
            for material_aula in self.cleaned_data['materiais_aula']:
                if not MaterialDiario.objects.filter(professor_diario=professor_diario, material_aula=material_aula).exists():
                    obj = MaterialDiario()
                    obj.professor_diario = professor_diario
                    obj.material_aula = material_aula
                    obj.etapa = int(etapa)
                    obj.save()

        return professores_diario


class SolicitacaoRelancamentoEtapaForm(forms.ModelFormPlus):
    id = forms.CharField(label='Id', widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = SolicitacaoRelancamentoEtapa
        fields = ('id',)


class SolicitacaoProrrogacaoEtapaForm(forms.ModelFormPlus):
    id = forms.CharField(label='Id', widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = SolicitacaoProrrogacaoEtapa
        fields = ('id',)


class SolicitarRelancamentoEtapaForm(forms.ModelFormPlus):
    def __init__(self, professor_diario, etapa, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.instance.professor_diario = professor_diario
        self.instance.etapa = etapa

    class Meta:
        model = SolicitacaoRelancamentoEtapa
        fields = ('motivo',)


class SolicitarProrrogacaoEtapaForm(forms.ModelFormPlus):
    def __init__(self, professor_diario, etapa, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.instance.professor_diario = professor_diario
        self.instance.etapa = etapa

    class Meta:
        model = SolicitacaoProrrogacaoEtapa
        fields = ('motivo',)


class ListarDiarioMatriculaAlunoForm(forms.Form):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Listar Diários'

    fieldsets = (
        ('Filtros', {'fields': ('diretoria', ('matriz', 'componente'), ('outros_componentes',), ('outras_matrizes',), ('ignorar_futuros'))}),
    )

    diretoria = forms.ModelChoiceField(Diretoria.objects.none(), label='Diretoria', required=True)
    matriz = forms.ModelChoiceFieldPlus(Matriz.objects, label='Matriz', required=False)
    componente = forms.ModelChoiceFieldPlus(
        Componente.objects,
        label='Componente',
        required=False,
        widget=AutocompleteWidget(search_fields=Componente.SEARCH_FIELDS, form_filters=[('matriz', 'componentecurricular__matriz')]),
    )
    outros_componentes = forms.BooleanField(
        label='Diários em Outras Matrizes', required=False, help_text='Apenas diários de componentes em outras matrizes comuns à matriz do aluno.'
    )
    outras_matrizes = forms.BooleanField(
        label='Outros Diários',
        required=False,
        help_text='Apenas diários de componentes que não fazem parte da matriz do aluno. Poderá haver quebra de pré e co requisito.',
    )
    ignorar_futuros = forms.BooleanField(
        label='Excluir Períodos Futuros',
        required=False,
        help_text='Apenas diários de componentes relacionados a períodos igual ou inferior ao período atual do aluno no curso.',
    )

    def __init__(self, matricula_periodo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.objects.filter(setor__uo_id=matricula_periodo.aluno.curso_campus.diretoria.setor.uo.pk)
        self.matricula_periodo = matricula_periodo
        self.fields['diretoria'].initial = matricula_periodo.aluno.curso_campus.diretoria.pk
        self.fields['ignorar_futuros'].initial = True

    def clean(self):
        if self.matricula_periodo.situacao.pk not in [SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.EM_ABERTO]:
            raise forms.ValidationError('A situação do aluno no período deve ser Matriculado ou Em Aberto.')
        return self.cleaned_data

    def processar(self):
        if not self.matricula_periodo.aluno.matriz:
            return Diario.objects.none()

        diarios = self.matricula_periodo.aluno.get_diarios_disponiveis_matricular_por_diretoria(
            self.cleaned_data.get('diretoria'),
            self.cleaned_data.get('outros_componentes'),
            self.cleaned_data.get('outras_matrizes'),
            self.cleaned_data.get('ignorar_futuros'),
            self.cleaned_data.get('componente'),
            self.cleaned_data.get('matriz'),
        )

        return diarios


class ListarDiariosVinculoAlunoForm(forms.Form):
    data_matricula = forms.DateFieldPlus(label='Data de matrícula:')
    matriculas_diario = forms.MultipleModelChoiceField(
        MatriculaDiario.objects, label='Diários', widget=RenderableSelectMultiple('widgets/alunos_alterar_data_diario_widget.html'), required=False
    )

    fieldsets = (
        ('', {'fields': ('data_matricula',)}),
        ('Outros diários do período', {'fields': ('matriculas_diario',)}),
    )

    def __init__(self, matricula_diario, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['matriculas_diario'].queryset = MatriculaDiario.objects.filter(
            matricula_periodo_id=matricula_diario.matricula_periodo_id
        ).exclude(id=matricula_diario.id)
        self.matricula_diario = matricula_diario
        self.initial['data_matricula'] = matricula_diario.data_matricula

    def processar(self):
        data_matricula = self.cleaned_data['data_matricula']
        with transaction.atomic():
            self.matricula_diario.data_matricula = data_matricula
            self.matricula_diario.save()
            if self.cleaned_data['matriculas_diario']:
                self.cleaned_data['matriculas_diario'].update(data_matricula=data_matricula)


class DividirDiarioForm(forms.Form):
    matriculas_diario = forms.MultipleModelChoiceField(
        MatriculaDiario.objects, label='', widget=RenderableSelectMultiple('widgets/alunos_dividir_diario_widget.html')
    )

    fieldsets = (('Alunos', {'fields': ('matriculas_diario',)}),)

    def __init__(self, matriculas_diario, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['matriculas_diario'].queryset = matriculas_diario


class AdicionarAlunosDiarioForm(forms.Form):
    matriculas_periodo = forms.MultipleModelChoiceField(
        MatriculaPeriodo.objects, label='', widget=RenderableSelectMultiple('widgets/matriculas_periodo_widget.html')
    )

    def __init__(self, matriculas_periodo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['matriculas_periodo'].queryset = matriculas_periodo

    def processar(self, diario):
        count = 0
        for matricula_periodo in self.cleaned_data['matriculas_periodo']:
            if matricula_periodo.aluno.pode_ser_matriculado_no_diario(diario)[0]:
                if not MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo, diario=diario).exists():
                    matricula_diario = MatriculaDiario()
                    matricula_diario.matricula_periodo = matricula_periodo
                    matricula_diario.diario = diario
                    matricula_diario.save()
                    count += 1
                if matricula_periodo.aluno.situacao.pk != SituacaoMatricula.MATRICULADO:
                    matricula_periodo.aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)
                    matricula_periodo.aluno.save()
                if matricula_periodo.situacao != SituacaoMatriculaPeriodo.MATRICULADO:
                    matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
                    matricula_periodo.save()
        return count


class ConfiguracaoAvaliacaoForm(forms.ModelFormPlus):
    class Media:
        js = ('/static/edu/js/ConfiguracaoAvaliacaoForm.js',)

    class Meta:
        model = ConfiguracaoAvaliacao
        exclude = ('professor',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.NOTA_DECIMAL:
            self.fields['observacao'].widget.attrs['class'] = 'notas-decimais'
        forma_atitudinal = [ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ATITUDINAL, 'Média Atitudinal']
        forma_conceito = [ConfiguracaoAvaliacao.FORMA_CALCULO_AVALIACAO_CONCEITO, 'Avaliação por Conceito']
        if self.instance and self.instance.diario and self.instance.diario.is_lancamento_conceito():
            self.fields['forma_calculo'].choices = [
                forma_conceito,
            ]
        elif self.instance and self.instance.etapa != 5 and self.instance.diario and self.instance.diario.utiliza_nota_atitudinal():
            self.fields['forma_calculo'].choices = [
                forma_atitudinal,
            ]
        else:
            choices = ConfiguracaoAvaliacao.FORMA_CALCULO_CHOICES.copy()
            if forma_conceito in choices:
                choices.remove(forma_conceito)
            if forma_atitudinal in choices:
                choices.remove(forma_atitudinal)
            self.fields['forma_calculo'].choices = choices

    def clean_divisor(self):
        if self.cleaned_data['forma_calculo'] == ConfiguracaoAvaliacao.FORMA_CALCULO_SOMA_DIVISOR:
            if not self.cleaned_data.get('divisor') or self.cleaned_data['divisor'] < 1:
                raise forms.ValidationError('Insira o valor do divisor, maior que 0, a ser utilizado no cálculo.')
        return self.cleaned_data['divisor']

    def clean(self):
        if self.instance.pk == 1 and not in_group(self.request.user, 'Administrador Acadêmico'):
            raise forms.ValidationError(
                'Não é possível alterar a configuração padrão do sistema. Caso necessite, adicione um nova configuração de avaliação para você.'
            )

        return self.cleaned_data

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class ItemConfiguracaoAvaliacaoFormset(forms.models.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.fields['data'] = forms.DateFieldPlus(required=False)

    def clean(self):
        eh_nota_atitudinal = self.instance.diario.utiliza_nota_atitudinal() and self.instance.etapa != 5

        ids_delete = []
        tem_avaliacao_atitudinal = False
        if hasattr(self, 'cleaned_data'):
            for item in self.cleaned_data:
                if item.get('DELETE'):
                    if 'id' in item:
                        ids_delete.append(item['id'].id)
                if eh_nota_atitudinal and 'tipo' in item and item['tipo'] and item['tipo'] == ItemConfiguracaoAvaliacao.TIPO_ATITUDINAL:
                    if not tem_avaliacao_atitudinal:
                        tem_avaliacao_atitudinal = True
                    else:
                        raise ValidationError('Não pode existir mais de uma avaliação do tipo atitudinal.')

            if eh_nota_atitudinal:
                if not tem_avaliacao_atitudinal:
                    raise ValidationError('É obrigatório o cadastro de uma avaliação do tipo Atitudinal.')
                if (
                    ids_delete
                    and ItemConfiguracaoAvaliacao.objects.filter(id__in=ids_delete, tipo=ItemConfiguracaoAvaliacao.TIPO_ATITUDINAL).exists()
                ):
                    raise ValidationError('Não é possível excluir o item de avaliação Atitudinal.')

            if ids_delete and NotaAvaliacao.objects.filter(item_configuracao_avaliacao__id__in=ids_delete).exclude(nota__isnull=True).exists():
                raise ValidationError('Não é possível excluir o item marcado enquanto houver notas lançadas neste item.')

            qtd_avaliacoes_minimo = eh_nota_atitudinal and 2 or 1
            if (len(ids_delete) + qtd_avaliacoes_minimo) > len(self.cleaned_data):
                raise ValidationError(f'A quantidade de avaliações não pode ser menor que {qtd_avaliacoes_minimo}.')

        soma_nota = 0
        soma_peso = 0
        qtd_itens = 0
        configuracao_avaliacao = None
        divisor = 0
        siglas = []
        MULTIPLICADOR_DECIMAL = 1
        if settings.NOTA_DECIMAL:
            MULTIPLICADOR_DECIMAL = settings.CASA_DECIMAL == 1 and 10 or 100
        for form in self.forms:
            if form.cleaned_data:
                # não validar recuperação
                if form.instance and form.instance.tipo == ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO:
                    return
                if not configuracao_avaliacao:
                    configuracao_avaliacao = form.cleaned_data['configuracao_avaliacao']
                    divisor = form.cleaned_data['configuracao_avaliacao'].divisor

                if (
                    configuracao_avaliacao.forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_PONDERADA
                    and form.cleaned_data.get('peso') is None
                ):
                    raise ValidationError('Informe o peso dos itens de configuração de avaliação.')

                if not form.cleaned_data.get('DELETE'):
                    soma_nota += form.cleaned_data.get('nota_maxima') or 0
                    soma_peso += form.cleaned_data.get('peso') or 0
                    siglas.append(form.cleaned_data.get('sigla'))
                    qtd_itens += 1

                if form.instance.pk and NotaAvaliacao.objects.filter(
                    matricula_diario__diario=configuracao_avaliacao.diario,
                    item_configuracao_avaliacao=form.instance,
                    nota__gt=(form.instance.nota_maxima * MULTIPLICADOR_DECIMAL),
                ):
                    raise ValidationError(
                        f'Existe uma nota referente ao item de avaliação {form.instance.sigla} maior do que a nota máxima informada: {form.instance.nota_maxima}'
                    )

        for sigla in siglas:
            if not sigla or len(sigla) > 2:
                raise forms.ValidationError('A sigla das avaliações devem ter 1 ou 2 caracteres')

        if configuracao_avaliacao:
            # validando qtd mínima de itens
            minimo_itens = 1
            if configuracao_avaliacao.menor_nota:
                minimo_itens += 1

            if configuracao_avaliacao.maior_nota:
                minimo_itens += 1

            if qtd_itens < minimo_itens:
                raise forms.ValidationError(
                    'É necessário a escolha de mais itens devido a escolha das opções: Ignorar Menor Nota e/ou Ignorar Maior Nota.'
                )

            nota_maxima = settings.NOTA_DECIMAL and 10 or 100

            # validando somas por forma de calculo
            forma_calculo = configuracao_avaliacao.forma_calculo

            if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_SOMA_SIMPLES:
                if soma_nota != nota_maxima:
                    raise forms.ValidationError(
                        f'O somatório das notas das avaliações deve ser {nota_maxima}, mas o resultado da soma foi {soma_nota}.'
                    )

            if (
                forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MAIOR_NOTA
                or forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_PONDERADA
                or forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ARITMETICA
            ):
                if soma_nota / qtd_itens != nota_maxima:
                    raise forms.ValidationError(f'As notas máximas para esta forma de cálculo devem ser {nota_maxima}.')

            if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_SOMA_DIVISOR:
                if not divisor:
                    return
                if soma_nota / divisor != nota_maxima:
                    raise forms.ValidationError(f'A soma das notas máximas das avaliações deve ser {divisor * nota_maxima}.')

            if eh_nota_atitudinal and forma_calculo != ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ATITUDINAL:
                raise forms.ValidationError('Somente a forma de cálculo Atitudinal é permitida para esta configuração.')

        else:
            raise forms.ValidationError('Informe ao menos um item de configuração da avaliação.')


class OcorrenciaDiarioForm(forms.ModelFormPlus):
    class Meta:
        model = OcorrenciaDiario
        exclude = ('professor_diario',)


class SelecionarHorarioCampusExportarXMLTimeTables(forms.FormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), required=True, label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(required=True, label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    diretoria = forms.ModelChoiceField(Diretoria.objects, label='Diretoria', required=True)
    horario_campus = forms.ModelChoiceField(queryset=HorarioCampus.objects, label='Selecione o Horário do Campus')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['horario_campus'].queryset = HorarioCampus.locals.all()
        self.fields['diretoria'].queryset = Diretoria.locals.all()

    def processar(self):
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        horario_campus = self.cleaned_data.get('horario_campus')
        diretoria = self.cleaned_data.get('diretoria')

        return ano_letivo, periodo_letivo, horario_campus, diretoria


class ImportarXMLTimeTables(forms.FormPlus):
    horario_campus = forms.ModelChoiceField(queryset=HorarioCampus.objects, label='Selecione o Horário do Campus')
    arquivo = forms.FileFieldPlus(help_text='Arquivo XML exportado do TimeTables.', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['horario_campus'].queryset = HorarioCampus.locals.all()
        self.documento_xml = None

    def clean(self):
        if 'horario_campus' in self.cleaned_data and 'arquivo' in self.cleaned_data:
            arquivo = self.cleaned_data.get('arquivo')
            exception_msg = 'Arquivo inválido. Por favor verifique o formato do arquivo e tente novamente'
            try:
                self.documento_xml = minidom.parseString(arquivo.read())
                # Validando se o horário selecionado condiz com o horário vindo do TimeTables.
                for _period in self.documento_xml.getElementsByTagName('period'):
                    horario_inicio_aula = _period.attributes['starttime'].value
                    horario_termino_aula = _period.attributes['endtime'].value

                    # O padrão do TimeTables é H:MM, logo é preciso transformar para HH:MM.
                    if len(horario_inicio_aula) == 4:
                        horario_inicio_aula = '0' + horario_inicio_aula
                    if len(horario_termino_aula) == 4:
                        horario_termino_aula = '0' + horario_termino_aula

                    qs = self.cleaned_data.get('horario_campus').horarioaula_set.filter(inicio=horario_inicio_aula, termino=horario_termino_aula)
                    if not qs.exists():
                        raise forms.ValidationError('O horário selecionado não condiz com o horário vindo no arquivo XML.')
            except KeyError as e:
                raise forms.ValidationError(f'{exception_msg}. Chave {e!s} não encontrada.')
            except Exception as e:
                raise forms.ValidationError(f'{exception_msg}. Detalhe: {e!s}')

        return self.cleaned_data

    def processar(self):
        horario_campus = self.cleaned_data.get('horario_campus')

        # Apagando os horários de aula e os professores registrados para os diários que serão manipulados no XML.
        lista_diarios_manipulados = set()
        for _card in self.documento_xml.getElementsByTagName('card'):
            lista_diarios_manipulados.add(_card.attributes['subjectid'].value)
        HorarioAulaDiario.objects.filter(diario__in=lista_diarios_manipulados).delete()
        ProfessorDiario.objects.filter(diario__pk__in=lista_diarios_manipulados).delete()

        for _card in self.documento_xml.getElementsByTagName('card'):
            # Pegando os valores do XML
            id_diario = _card.attributes['subjectid'].value
            ids_professores = _card.attributes['teacherids'].value.split(',')
            id_sala = _card.attributes['classroomids'].value
            dia = _card.attributes['day'].value
            horario = _card.attributes['period'].value

            # Pegando os objetos
            professores = Professor.objects.filter(
                Q(vinculo__user__username__in=ids_professores) | Q(vinculo__pessoa__pessoa_fisica__cpf__in=ids_professores)
            )
            diario = Diario.objects.get(pk=id_diario)
            horario_aula = None

            if id_sala or id_sala != '':
                sala = Sala.objects.get(pk=id_sala)
            else:
                sala = None

            # Pesquisando o horário a partir da data de início da aula
            for _period in self.documento_xml.getElementsByTagName('period'):
                if _period.attributes['period'].value == horario:
                    horario_inicio_aula = _period.attributes['starttime'].value
                    horario_termino_aula = _period.attributes['endtime'].value

                    # O padrão do TimeTables é H:MM, logo é preciso transformar para HH:MM.
                    if len(horario_inicio_aula) == 4:
                        horario_inicio_aula = '0' + horario_inicio_aula
                    if len(horario_termino_aula) == 4:
                        horario_termino_aula = '0' + horario_termino_aula

                    qs = horario_campus.horarioaula_set.filter(inicio=horario_inicio_aula, termino=horario_termino_aula)
                    if qs.exists():
                        horario_aula = qs[0]

            # Setando os professores no Diário
            if not diario.professordiario_set.exists():
                for professor in professores:
                    professor_diario = ProfessorDiario()
                    professor_diario.professor = professor
                    professor_diario.diario = diario
                    professor_diario.tipo = TipoProfessorDiario.objects.get(descricao='Principal')
                    professor_diario.save()

            # Setando o horário de aula
            if horario_aula:
                HorarioAulaDiario.objects.get_or_create(diario=diario, dia_semana=int(dia) + 1, horario_aula=horario_aula)

            # Setando a sala de aula
            if sala:
                diario.local_aula = sala
                diario.save()


class ObservacaoDiarioForm(forms.ModelForm):
    class Meta:
        model = ObservacaoDiario
        exclude = ('diario', 'usuario', 'data')

    def __init__(self, diario, usuario, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diario = diario
        self.usuario = usuario

    def save(self, *args, **kwargs):
        self.instance.diario = self.diario
        self.instance.usuario = self.usuario
        self.instance.data = datetime.datetime.now()
        self.instance.save()


class AgendarAvaliacaoForm(forms.ModelFormPlus):
    class Meta:
        model = ItemConfiguracaoAvaliacao
        fields = ['data']


class TopicoDiscussaoForm(forms.ModelFormPlus):
    etapa = forms.ChoiceField(label='Etapa', choices=[[1, 'Etapa 1'], [2, 'Etapa 2'], [3, 'Etapa 3'], [4, 'Etapa 4']])

    class Meta:
        model = TopicoDiscussao
        fields = ('titulo', 'etapa', 'descricao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.initial.get('etapa'):
            self.fields['etapa'].widget = forms.HiddenInput()

    def save(self, diario, etapa, *args, **kwargs):
        self.instance.diario = diario
        self.instance.data = datetime.date.today()
        self.instance.user = self.request.user
        if etapa:
            self.instance.etapa = etapa
        return super().save(*args, **kwargs)


class RespostaDiscussaoForm(forms.ModelFormPlus):
    class Meta:
        model = RespostaDiscussao
        fields = ('comentario',)

    def save(self, topico, *args, **kwargs):
        self.instance.topico = topico
        self.instance.data = datetime.date.today()
        self.instance.user = self.request.user
        return super().save(*args, **kwargs)


class TrabalhoForm(forms.ModelFormPlus):
    class Meta:
        model = Trabalho
        fields = ('titulo', 'descricao', 'data_limite_entrega', 'arquivo')

    def save(self, diario, etapa, *args, **kwargs):
        self.instance.diario = diario
        self.instance.etapa = etapa
        self.instance.data_solicitacao = datetime.date.today()
        self.instance.user = self.request.user
        return super().save(*args, **kwargs)


class EntregaTrabalhoForm(forms.ModelFormPlus):
    class Meta:
        model = EntregaTrabalho
        fields = ('comentario', 'arquivo')

    def save(self, trabalho, aluno, *args, **kwargs):
        self.instance.trabalho = trabalho
        if self.instance.trabalho.pode_entregar_trabalho():
            md = MatriculaDiario.objects.filter(diario=trabalho.diario, matricula_periodo__aluno=aluno).first()
            if not EntregaTrabalho.objects.filter(trabalho=trabalho, matricula_diario=md).exists():
                self.instance.matricula_diario = md
                self.instance.data_solicitacao = datetime.date.today()
                return super().save(*args, **kwargs)


class ImportarMaterialAulaForm(forms.FormPlus):
    materiais_aula = forms.MultipleModelChoiceField(
        MaterialAula.objects.none(), required=False, label='', widget=RenderableSelectMultiple('widgets/materiais_aula_widget.html')
    )

    SUBMIT_LABEL = 'Importar Materiais Selecionados'

    def __init__(self, professor, *args, **kwargs):
        self.professor = professor
        super().__init__(*args, **kwargs)
        self.fields['materiais_aula'].queryset = professor.get_materiais_aula_outros_vinculos()

    def processar(self):
        for material_aula in self.cleaned_data['materiais_aula']:
            material_aula.pk = None
            material_aula.professor = self.professor
            material_aula.save()


class ConfigurarAmbienteVirtualDiarioForm(forms.ModelFormPlus):
    fieldsets = (('Ambiente Virtual', {'fields': ('url_ambiente_virtual',)}),)

    class Meta:
        model = Diario
        fields = ('url_ambiente_virtual',)


def ReservarSalaAulaFormFactory(request, diario_id):
    fields = {}
    salas_id = []

    diario = Diario.objects.filter(id=diario_id).first()
    if diario:
        for sala in diario.get_locais_aula():
            salas_id.append(sala.id)

    horarios = HorarioAulaDiario.objects.filter(diario_id=diario_id)
    for horario in horarios:
        fields[f'horario_{horario.get_horario_formatado()}'] = forms.ModelChoiceFieldPlus(
            Sala.objects.filter(id__in=salas_id), label=horario.get_horario_extenso(), required=True
        )

        if horario.sala:
            fields[f'horario_{horario.get_horario_formatado()}'].initial = horario.sala.pk
        elif len(salas_id) == 1:
            fields[f'horario_{horario.get_horario_formatado()}'].initial = salas_id[0]

    def save(self, *args, **kwargs):
        SolicitacaoReservaSala = apps.get_model('comum', 'SolicitacaoReservaSala')
        qs_horarios = HorarioAulaDiario.objects.filter(diario_id=diario_id)

        with transaction.atomic():
            #
            # removendo as salas dos horários do diário
            qs_horarios.update(sala=None)

            erros = []
            for horario in horarios:
                # o melhor jeito para implementar aqui é cadastrar uma solicitação para o diário e horário e verificar se ela está em conflito
                sala = self.cleaned_data.get(f'horario_{horario.get_horario_formatado()}')
                horario.sala = sala
                horario.save()

                # data de inicio e fim (consigo elas no calendário acadêmico que está no arquivo diretorias.py)
                data_agora = datetime.datetime.now()
                data_inicio = diario.calendario_academico.data_inicio
                if data_inicio < data_agora.date():
                    data_inicio = data_agora.date()
                data_fim = diario.calendario_academico.data_fim
                delta = data_fim - data_inicio  # timedelta

                for i in range(delta.days + 1):
                    _data = data_inicio + timedelta(days=i)
                    d_semana = _data.weekday() + 1

                    # apenas realiza as ações nos dias da semana em que terá a aula
                    if d_semana == horario.dia_semana:
                        # criando a solicitação
                        h_hora_inicio = datetime.datetime.strptime(horario.horario_aula.inicio, '%H:%M').time()
                        h_hora_fim = datetime.datetime.strptime(horario.horario_aula.termino, '%H:%M').time()

                        h_data_inicio = h_data_fim = _data
                        data_hora_inicio = datetime.datetime(
                            h_data_inicio.year, h_data_inicio.month, h_data_inicio.day, h_hora_inicio.hour, h_hora_inicio.minute, h_hora_inicio.second
                        )
                        data_hora_fim = datetime.datetime(
                            h_data_fim.year, h_data_fim.month, h_data_fim.day, h_hora_fim.hour, h_hora_fim.minute, h_hora_fim.second
                        )

                        justificativa = diario.gerar_justificativa_reserva_sala()
                        recorrencia = SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO
                        solicitacao = SolicitacaoReservaSala.objects.get_or_create(
                            sala=sala,
                            solicitante=request.user,
                            data_solicitacao=data_agora,
                            data_inicio=h_data_inicio,
                            hora_inicio=h_hora_inicio,
                            data_hora_inicio=data_hora_inicio,
                            data_fim=h_data_fim,
                            hora_fim=h_hora_fim,
                            data_hora_fim=data_hora_fim,
                            recorrencia=recorrencia,
                            justificativa=justificativa,
                            status=SolicitacaoReservaSala.STATUS_DEFERIDA,
                        )[0]

                        if sala.tem_conflito_reserva(solicitacao):
                            msg_erro = f'Conflito no dia <strong>{_data.strftime("%d/%m/%Y")}</strong> no horário de <strong>{h_hora_inicio.strftime("%H:%M")}</strong> a <strong>{h_hora_fim.strftime("%H:%M")}</strong>'
                            erros.append(msg_erro)

                        if not erros:
                            # gerando uma reserva
                            solicitacao.gerar_reservas()
                            solicitacao.data_avaliacao = data_agora
                            solicitacao.avaliador = request.user
                            solicitacao.save()

            # se existir erros
            if erros:
                raise ValidationError(erros)

    return type(
        'ReservarSalaAulaForm',
        (forms.BaseForm,),
        {
            'base_fields': fields,
            'METHOD': 'POST',
            'SUBMIT_LABEL': 'Salvar',
            'save': save,
        },
    )


class SuspensaoDiarioForm(forms.ModelForm):
    class Meta:
        model = SuspensaoDiario
        fields = 'inicio', 'justificativa', 'motivo'

    class Media:
        js = ('/static/edu/js/SuspensaoDiarioForm.js',)


class EncerrarSuspensaoDiarioForm(forms.ModelForm):
    class Meta:
        model = SuspensaoDiario
        fields = ('fim',)

    def clean_fim(self):
        data_inicio = self.instance.inicio
        data_fim = self.cleaned_data.get('fim')
        if data_inicio and data_fim and data_fim < data_inicio:
            raise ValidationError(f'A data final deve ser posterior à data de início: {data_inicio.strftime("%d/%m/%Y")}')
        return data_fim


class FrequenciaPraticaProfissionalForm(forms.ModelForm):
    class Meta:
        model = FrequenciaPraticaProfissional
        exclude = ()
