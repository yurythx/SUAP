from datetime import datetime

from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from comum.models import User, UsuarioGrupo, UsuarioGrupoSetor, Vinculo, Configuracao
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from edu.models import (
    CalendarioAcademico,
    CoordenadorModalidade,
    CoordenadorRegistroAcademico,
    CursoCampus,
    DataComemorativa,
    Diretoria,
    Professor,
    SabadoLetivo,
    TermoVinculacaoUsuarioDiretoria,
)
from rh.models import Servidor, Setor, UnidadeOrganizacional

from .utils import RedirectForm, grupos


class ReplicacaoCalendarioForm(forms.FormPlus):
    SUBMIT_LABEL = 'Replicar Calendário'
    uos = forms.MultipleModelChoiceFieldPlus(
        UnidadeOrganizacional.objects.campi().all(),
        label='Campus',
        required=True,
        help_text='Informe os campi para os quais você deseja replicar o calendário',
    )

    def processar(self, calendario):
        return calendario.replicar(self.cleaned_data['uos'])


class ReplicacaoHorarioCampusForm(forms.FormPlus):
    SUBMIT_LABEL = 'Replicar Horário'
    descricao = forms.CharFieldPlus(width=500, label='Descrição', required=True)
    uo = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.campi().all(),
        label='Campus',
        required=True,
        help_text='Informe o campus para o qual você deseja replicar o curso',
    )

    def processar(self, horario_campus):
        horario_campus.replicar(self.cleaned_data['descricao'], self.cleaned_data['uo'])
        return horario_campus


class DiretoriaForm(forms.ModelFormPlus):
    setor = forms.ModelChoiceFieldPlus(Setor.objects.none())

    class Meta:
        model = Diretoria
        exclude = ()
        fields = ('setor', 'ead', 'tipo')

    fieldsets = (
        ('Dados gerais', {'fields': (('setor', 'tipo'), 'ead')}),
        (
            'Nomenclatura para Diploma',
            {
                'fields': (
                    ('titulo_autoridade_maxima_masculino', 'titulo_autoridade_maxima_feminino'),
                    ('titulo_autoridade_uo_masculino', 'titulo_autoridade_uo_feminino'),
                    ('titulo_autoridade_diretoria_masculino', 'titulo_autoridade_diretoria_feminino'),
                )
            },
        ),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = Setor.objects.suap_ativos()

    def clean_setor(self) -> Setor:
        setor = self.cleaned_data['setor']
        if not Setor.objects.suap_ativos().filter(pk=setor.pk).exists():
            raise ValidationError('Informe um setor SUAP.')
        return setor


class AdicionarMembroDiretoriaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'
    vinculo = forms.ModelChoiceField(Vinculo.objects, required=True, label='Usuário', widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vinculo'].queryset = Vinculo.objects.funcionarios().filter(ativo=True)

    def processar(self, diretoria, grupo):
        vinculo = self.cleaned_data['vinculo']
        user = User.objects.get(username=vinculo.user.username)
        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupo, user=user)[0]
        usuario_grupo_setor = UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=diretoria.setor)[0]

        if grupo.name == 'Diretor Geral':
            diretorias = Diretoria.objects.filter(setor__uo=diretoria.setor.uo)
            for diretoria in diretorias:
                if not diretoria.diretor_geral:
                    diretoria.diretor_geral = vinculo
                    diretoria.diretor_geral_exercicio = vinculo
                    diretoria.save()
                UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=diretoria.setor)
        if grupo.name == 'Diretor Acadêmico':
            if not diretoria.diretor_academico:
                diretoria.diretor_academico = vinculo
                diretoria.diretor_academico_exercicio = vinculo
                diretoria.save()
        if grupo.name in ('Secretário Acadêmico', 'Auxiliar de Secretaria Acadêmica'):
            if 'centralservicos' in settings.INSTALLED_APPS:
                from centralservicos.models import GrupoAtendimento

                pk = usuario_grupo_setor.setor.diretoria_set.values_list('id_grupo_atendimento', flat=True).first()
                ga = GrupoAtendimento.objects.filter(id=pk).first() if pk else None
                if ga:
                    ga.atendentes.add(usuario_grupo_setor.usuario_grupo.user)
                    ga.responsaveis.add(usuario_grupo_setor.usuario_grupo.user)
        return usuario_grupo_setor


class AdicionarMembroDiretoriaPeloCampusForm(AdicionarMembroDiretoriaForm):
    ciente = forms.BooleanField(
        label='Ciente', required=True, help_text='Declaro-me ciente de que é de responsabilidade do campus a inclusão desse usuário nesse perfil.'
    )
    senha = forms.PasswordField()

    fieldsets = (
        ('Dados Gerais', {'fields': ('vinculo',)}),
        ('Termo de Responsabilidade', {'fields': ('ciente', 'senha')}),
    )

    def __init__(self, *args, **kwargs):
        self.diretoria = kwargs.pop('diretoria')
        super().__init__(*args, **kwargs)
        self.fields['vinculo'].queryset = self.get_vinculos_queryset()

    def processar(self, grupo):
        usuario_grupo_setor = super().processar(self.diretoria, grupo)
        TermoVinculacaoUsuarioDiretoria.objects.create(
            responsavel=self.request.user.get_vinculo(),
            diretoria=self.diretoria,
            user=usuario_grupo_setor.usuario_grupo.user,
            group=usuario_grupo_setor.usuario_grupo.group,
            data_hora_assinatura=datetime.now(),
        )
        return usuario_grupo_setor

    def get_prestadores(self):
        return Vinculo.objects.prestadores().filter(ativo=True, setor__uo_id=self.diretoria.setor.uo_id)

    def get_estagiarios(self):
        return Vinculo.objects.estagiarios_siape().filter(ativo=True, setor__uo_id=self.diretoria.setor.uo_id)

    def get_bolsistas(self):
        return Vinculo.objects.filter(
            pessoa__pessoafisica__aluno_set__participacao__programa__tipo='TRB',
            pessoa__pessoafisica__aluno_set__participacao__data_termino__isnull=True,
            pessoa__pessoafisica__aluno_set__participacao__programa__instituicao_id=self.diretoria.setor.uo_id,
        )

    def get_vinculos_queryset(self):
        return Vinculo.objects.none()


class AdicionarAuxiliarSecretariaDiretoriaForm(AdicionarMembroDiretoriaPeloCampusForm):
    def get_vinculos_queryset(self):
        return self.get_prestadores()


class AdicionarEstagiarioDiretoriaForm(AdicionarMembroDiretoriaPeloCampusForm):
    def get_vinculos_queryset(self):
        return self.get_estagiarios() | self.get_bolsistas()


class AdicionarCoordenadorForm(forms.FormPlus):
    vinculo = forms.ModelChoiceField(Vinculo.objects, required=True, label='Usuário', widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS))
    cursos = forms.ModelMultipleChoiceField(CursoCampus.objects, required=False, widget=forms.CheckboxSelectMultiplePlus)

    def __init__(self, *args, **kwargs):
        self.diretoria = kwargs.pop('diretoria', None)
        self.tipo_coordenador = kwargs.pop('tipo_coordenador', 'coordenador')
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['vinculo'].queryset = Vinculo.objects.funcionarios().filter(ativo=True)
        self.fields['cursos'].queryset = CursoCampus.objects.filter(ativo=True, diretoria=self.diretoria)
        if user:
            self.fields['vinculo'].initial = user.get_vinculo().id
            if self.tipo_coordenador == 'coordenador':
                self.fields['cursos'].initial = list(
                    user.get_vinculo().cursocampus_set.filter(ativo=True, diretoria=self.diretoria).values_list('id', flat=True)
                )
            else:
                self.fields['cursos'].initial = list(
                    user.get_vinculo().cursocampus_vicecoordenador_set.filter(ativo=True, diretoria=self.diretoria).values_list('id', flat=True)
                )

    def processar(self, diretoria, usuario_grupo):
        vinculo = self.cleaned_data['vinculo']
        user = vinculo.user
        cursos = self.cleaned_data['cursos']
        usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR'], user=user)[0]
        if self.tipo_coordenador == 'coordenador':
            usuario_grupo.user.get_vinculo().cursocampus_set.filter(diretoria=self.diretoria).update(coordenador=None)
            for curso in cursos:
                curso.coordenador = vinculo
                curso.save()
        else:
            usuario_grupo.user.get_vinculo().cursocampus_vicecoordenador_set.filter(diretoria=self.diretoria).update(coordenador_2=None)
            for curso in cursos:
                curso.coordenador_2 = vinculo
                curso.save()
        ugs = UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=diretoria.setor)[0]
        if (
            not cursos
            and not usuario_grupo.user.get_vinculo().cursocampus_set.exists()
            and not usuario_grupo.user.get_vinculo().cursocampus_vicecoordenador_set.filter(diretoria=self.diretoria).exists()
        ):
            ugs.delete()


class DefinirCoordenadorCursoForm(forms.ModelFormPlus):
    class Meta:
        model = CursoCampus
        fields = ('coordenador', 'numero_portaria_coordenador', 'coordenador_2', 'numero_portaria_coordenador_2')

    def processar(self, curso_campus):
        vinculo = self.cleaned_data['coordenador']
        if vinculo:
            user = vinculo.user
            usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR'], user=user)[0]
            UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=curso_campus.diretoria.setor)

        vinculo_2 = self.cleaned_data['coordenador_2']
        if vinculo_2:
            user_2 = vinculo_2.user
            usuario_grupo_2 = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR'], user=user_2)[0]
            UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo_2, setor=curso_campus.diretoria.setor)

        self.save()


class CalendarioAcademicoForm(forms.ModelFormPlus):
    qtd_etapas = forms.ChoiceField(widget=forms.RadioSelect(), choices=CalendarioAcademico.QTD_ETAPAS_CHOICES, initial=1)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.none(), label='Campus')
    diretoria = forms.ModelChoiceField(
        Diretoria.objects.none(),
        required=False,
        label='Diretoria',
        widget=AutocompleteWidget(
            search_fields=Diretoria.SEARCH_FIELDS,
            form_filters=[('uo', 'setor__uo_id')],
        ),
    )

    class Meta:
        model = CalendarioAcademico
        exclude = ()

    class Media:
        js = ('/static/edu/js/CalendarioAcademicoForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['uo'].queryset = UnidadeOrganizacional.locals.all()
        self.fields['diretoria'].queryset = Diretoria.locals.all()
        self.fields[
            'eh_calendario_referencia'
        ].help_text = 'Marque essa opcão caso deseje utilizar esse calendário como calendário de referência anual do campus, ou seja, cujas datas das etapas poderão ser utilizadas como base para notificações (Ex: envio do PIT/RIT dos professores).'

    def clean_eh_calendario_referencia(self):
        uo = self.cleaned_data.get('uo')
        ano_letivo = self.cleaned_data.get('ano_letivo')
        tipo = self.cleaned_data.get('tipo')
        eh_calendario_referencia = self.cleaned_data['eh_calendario_referencia']
        if eh_calendario_referencia and not tipo == CalendarioAcademico.TIPO_ANUAL:
            raise forms.ValidationError('Apenas calendários anuais podem ser de referência.')
        if uo and ano_letivo and eh_calendario_referencia:
            qs = CalendarioAcademico.objects.filter(uo=uo, ano_letivo=ano_letivo, eh_calendario_referencia=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f'Já existe um calendário de referência para o ano {ano_letivo} no campus {uo}')
        return eh_calendario_referencia


class BuscaCalendarioForm(RedirectForm):
    calendario = forms.ModelChoiceFieldPlus(
        CalendarioAcademico.objects, label='Código/Descrição', widget=AutocompleteWidget(search_fields=CalendarioAcademico.SEARCH_FIELDS)
    )

    def get_url(self):
        return self.cleaned_data['calendario'].get_absolute_url()


class InserirDiretoriaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'
    diretoria = forms.ModelChoiceField(Diretoria.objects, label='Diretoria', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.objects.order_by('setor')


class CoordenadorRegistroAcademicoForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        diretoria = kwargs.pop('diretoria')
        super().__init__(*args, **kwargs)
        pks_coordenadores_cadastrados = (
            CoordenadorRegistroAcademico.objects.filter(ativo=True)
            .exclude(pk=self.instance.pk)
            .filter(diretoria=diretoria)
            .values_list('servidor__pk', flat=True)
        )
        self.fields['servidor'].queryset = Servidor.objects.all().exclude(pk__in=pks_coordenadores_cadastrados)

    class Meta:
        model = CoordenadorRegistroAcademico
        exclude = ['diretoria']


class CoordenadorModalidadeForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        diretoria = kwargs.pop('diretoria')
        super().__init__(*args, **kwargs)
        pks_coordenadores_cadastrados = CoordenadorModalidade.objects.filter(diretoria=diretoria).values_list('servidor__pk', flat=True)
        self.fields['servidor'].queryset = Servidor.objects.all().exclude(pk__in=pks_coordenadores_cadastrados)
        if self.instance and self.instance.pk and self.instance.servidor:
            self.fields['servidor'].queryset = self.fields['servidor'].queryset | Servidor.objects.filter(pk=self.instance.servidor.pk)
            self.fields['servidor'].initial = self.instance.servidor.pk

    class Meta:
        model = CoordenadorModalidade
        exclude = ['diretoria']


class DefinirCoordenadoresEstagioDocente(forms.ModelFormPlus):
    coordenadores_estagio_docente = forms.MultipleModelChoiceFieldPlus(Professor.objects, label='Coordenadores de Estágio Docente', required=True)

    class Meta:
        model = CursoCampus
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['coordenadores_estagio_docente'] = [professor.pk for professor in self.instance.coordenadores_estagio_docente.all()]

    @transaction.atomic
    def save(self, *args, **kwargs):
        for professor in self.instance.coordenadores_estagio_docente.all():
            user = User.objects.filter(username=professor.vinculo.user.username)[0]
            if professor.cursos_coordenacao_estagio_docente_set.all().count() == 1:
                UsuarioGrupo.objects.filter(group=grupos()['COORDENADOR_ESTAGIO_DOCENTE'], user=user).delete()
        self.instance.coordenadores_estagio_docente.clear()
        for professor in self.cleaned_data['coordenadores_estagio_docente'].all():
            user = User.objects.filter(username=professor.vinculo.user.username)[0]
            usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupos()['COORDENADOR_ESTAGIO_DOCENTE'], user=user)[0]
            UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=self.instance.diretoria.setor)
            self.instance.coordenadores_estagio_docente.add(professor)
        self.instance.save()

        return super().save(*args, **kwargs)


class SabadoLetivoForm(forms.ModelFormPlus):
    class Meta:
        model = SabadoLetivo
        fields = 'sabado', 'dia_semana', 'data'

    def __init__(self, *args, **kwargs):
        calendario_academico = kwargs.pop('calendario_academico', None)
        super().__init__(*args, **kwargs)
        self.instance.calendario_academico = calendario_academico

    def clean(self):
        data = self.cleaned_data.get('data')
        dia_semana = self.cleaned_data.get('dia_semana')
        if data and dia_semana:
            mapa = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira']
            if mapa[data.weekday()] != dia_semana:
                raise forms.ValidationError('Dia de semana incompatível com a data de referência')
        return self.cleaned_data

    def clean_data(self):
        data = self.cleaned_data['data']
        if data:
            if data.weekday() > 4:
                raise forms.ValidationError('Selecione um dia de semana')
            if data < self.instance.calendario_academico.data_inicio:
                raise forms.ValidationError(
                    'A data não deve ser inferior a {}'.format(self.instance.calendario_academico.data_inicio.strftime('%d/%m/%Y'))
                )
            if data > self.instance.calendario_academico.data_fim:
                raise forms.ValidationError(
                    'A data não deve ser superior a {}'.format(self.instance.calendario_academico.data_fim.strftime('%d/%m/%Y'))
                )
        return data

    def clean_sabado(self):
        data = self.cleaned_data['sabado']
        if data.weekday() != 5:
            raise forms.ValidationError('Selecione um sábado')
        if data < self.instance.calendario_academico.data_inicio:
            raise forms.ValidationError(
                'A data não deve ser inferior a {}'.format(self.instance.calendario_academico.data_inicio.strftime('%d/%m/%Y'))
            )
        if data > self.instance.calendario_academico.data_fim:
            raise forms.ValidationError('A data não deve ser superior a {}'.format(self.instance.calendario_academico.data_fim.strftime('%d/%m/%Y')))
        return data


class DataComemorativaForm(forms.ModelFormPlus):
    class Meta:
        model = DataComemorativa
        fields = 'descricao', 'inicio', 'fim'

    fieldsets = (('Dados gerais', {'fields': ('descricao', ('inicio', 'fim'))}),)

    def __init__(self, *args, **kwargs):
        calendario_academico = kwargs.pop('calendario_academico', None)
        super().__init__(*args, **kwargs)
        self.instance.calendario_academico = calendario_academico

    def clean_inicio(self):
        data = self.cleaned_data['inicio']
        if data < self.instance.calendario_academico.data_inicio:
            raise forms.ValidationError(
                'A data não deve ser inferior a {}'.format(self.instance.calendario_academico.data_inicio.strftime('%d/%m/%Y'))
            )
        if data > self.instance.calendario_academico.data_fim:
            raise forms.ValidationError('A data não deve ser superior a {}'.format(self.instance.calendario_academico.data_fim.strftime('%d/%m/%Y')))
        return data

    def clean_fim(self):
        data = self.cleaned_data['fim']
        if data < self.instance.calendario_academico.data_inicio:
            raise forms.ValidationError(
                'A data não deve ser inferior a {}'.format(self.instance.calendario_academico.data_inicio.strftime('%d/%m/%Y'))
            )
        if data > self.instance.calendario_academico.data_fim:
            raise forms.ValidationError('A data não deve ser superior a {}'.format(self.instance.calendario_academico.data_fim.strftime('%d/%m/%Y')))
        return data


class VincularGrupoAtendimentoDiretoria(forms.ModelFormPlus):
    id_grupo_atendimento = forms.ChoiceField(
        label='Grupo de Atendimento',
        required=True,
        help_text='Identificador do grupo de atendimento da central de serviços relacionado aos chamados da secretaria acadêmica (SEAC). Ao ser informado, a inclusão e remoção dos usuários na central será realizada automaticamente sempre que secretários acadêmicos ou auxiliares de secretaria forem adicionados/removidos da diretoria. O grupo de atendimento deve ser da mesma unidade e ter a sigla SEAC em seu nome.',
    )

    class Meta:
        model = Diretoria
        fields = ('id_grupo_atendimento',)

    def clean(self):
        if not Configuracao.get_valor_por_chave('edu', 'sigla_setor_seacs'):
            raise forms.ValidationError('A sigla para os setores relacionados as secretarias acadêmicas deve ser configurada no SUAP.')
        return super().clean()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'centralservicos' in settings.INSTALLED_APPS:
            from centralservicos.models import GrupoAtendimento

            choices = [('', '')]
            sigla_setor_seacs = Configuracao.get_valor_por_chave('edu', 'sigla_setor_seacs') or ''
            for ga in GrupoAtendimento.objects.filter(campus_id=self.instance.setor.uo_id, nome__icontains=sigla_setor_seacs):
                choices.append((ga.id, ga.nome))
            self.fields['id_grupo_atendimento'].choices = choices
