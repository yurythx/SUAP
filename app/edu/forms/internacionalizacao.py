from djtools import forms
from edu.models import (
    Cidade,
    Diretoria,
    MatrizCurso,
    PlanilhaConvocacao,
    PreMatriculaInternacional,
    InscricaoAlunoEstrangeiro,
    SolicitacaoCorrecaoInscricaoAlunoEstrangeiro,
    Turno,
    Polo,
    FormaIngresso,
    Convenio,
)
from convenios.models import ParceriaInternacional
from djtools.forms.widgets import AutocompleteWidget
from djtools.forms.widgets import PhotoCapturePortraitInput
from datetime import datetime
from django.core.files.base import ContentFile

from rh.deduplicacao.documentos import formatar_passaporte


class PreMatriculaInternacionalForm(forms.ModelFormPlus):
    diretoria = forms.ModelChoiceFieldPlus(Diretoria.objects.none(), label='Campus')
    matriz_curso = forms.ModelChoiceField(
        MatrizCurso.objects,
        label='Matriz/Curso',
        widget=AutocompleteWidget(
            search_fields=MatrizCurso.SEARCH_FIELDS,
            form_filters=[
                ('diretoria', 'curso_campus__diretoria'),
            ],
        ),
    )

    class Meta:
        model = PreMatriculaInternacional
        fields = (
            'descricao',
            'diretoria',
            'ano_letivo',
            'periodo_letivo',
            'matriz_curso',
            'qtd_vagas',
            'data_inicio_inscricoes',
            'data_termino_inscricoes',
            'data_limite_correcao_inscricoes',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals.all()


class RealizarConvocacaoInternacionalForm(forms.ModelFormPlus):
    class Meta:
        model = PlanilhaConvocacao
        fields = 'data_publicacao', 'arquivo'


class SolicitarCorrecaoInscricaoForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoCorrecaoInscricaoAlunoEstrangeiro
        fields = ('observacao_solicitacao',)

    def save(self, *args, **kwargs):
        self.instance.solicitante = self.request.user.get_vinculo()
        self.instance.data_hora_solicitacao = datetime.now()
        self.instance.inscricao.situacao = InscricaoAlunoEstrangeiro.SITUACAO_AGUARDANDO_CORRECAO
        self.instance.inscricao.save()
        super().save(*args, **kwargs)


class EnviarCorrecaoInscricaoForm(forms.ModelFormPlus):
    confirmacao = forms.BooleanField(label='Confirmação', help_text='Confirmo que realizei a correção/edição sugerida pelo revisor.', required=True)

    class Meta:
        model = SolicitacaoCorrecaoInscricaoAlunoEstrangeiro
        fields = ('observacao_correcao',)

    def save(self, *args, **kwargs):
        self.instance.data_hora_correcao = datetime.now()
        super().save(*args, **kwargs)
        self.instance.inscricao.situacao = InscricaoAlunoEstrangeiro.SITUACAO_SOLICITADA
        self.instance.inscricao.save()


class AvalicaoInscricaoAlunoEstrangeiroForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoAlunoEstrangeiro
        fields = ('observacao_avaliacao',)


class InscricaoAlunoEstrangeiroForm(forms.ModelFormPlus):
    captura_foto = forms.PhotoCaptureField(required=False, widget=PhotoCapturePortraitInput)
    arquivo_foto = forms.ImageFieldPlus(label='Arquivo', required=False)
    naturalidade = forms.ModelChoiceField(
        Cidade.objects,
        label='Naturalidade',
        help_text='Lugar onde nasceu / Lugar de nacimiento / Place of birth',
        widget=AutocompleteWidget(
            search_fields=['nome'],
            form_filters=[
                ('pais_origem', 'pais'),
            ],
        ),
    )
    cidade = forms.ModelChoiceField(
        Cidade.objects,
        label='Cidade',
        help_text='Ciudad / City',
        widget=AutocompleteWidget(
            search_fields=['nome'],
            form_filters=[
                ('pais', 'pais'),
            ],
        ),
    )

    class Meta:
        model = InscricaoAlunoEstrangeiro
        fields = (
            'nacionalidade',
            'pais_origem',
            'naturalidade',
            'numero_passaporte',
            'data_passaporte',
            'raca',
            'povo_indigena',
            'estado_civil',
            'deficiencias',
            'outras_nees',
            'tipo_vinculo_universitario',
            'nivel_ensino',
            'tipo_instituicao',
            'universidade',
            'nome_mae',
            'sobrenome_mae',
            'estado_civil_mae',
            'nome_pai',
            'sobrenome_pai',
            'estado_civil_pai',
            'logradouro',
            'numero',
            'complemento',
            'bairro',
            'cidade',
            'pais',
            'cep',
            'email_secundario',
            'telefone',
            'arquivo_passaporte',
            'declaracao_vinculo',
            'documento_adicional_1',
            'documento_adicional_2',
            'documento_adicional_3',
            'documento_adicional_4',
            'documento_adicional_5',
        )

    fieldsets = (
        ('Foto  (captura com câmera ou upload de arquivo)', {'fields': ('captura_foto', 'arquivo_foto')}),
        ('Dados Pessoais', {'fields': (('estado_civil', 'nacionalidade'), ('pais_origem', 'naturalidade'))}),
        ('Passaporte', {'fields': (('numero_passaporte', 'data_passaporte'), 'arquivo_passaporte')}),
        (
            'Caracterização',
            {
                'fields': (
                    ('raca', 'povo_indigena'),
                    (
                        'deficiencias',
                        'outras_nees',
                    ),
                )
            },
        ),
        (
            'Dados Institucionais',
            {
                'fields': (
                    ('tipo_vinculo_universitario', 'nivel_ensino'),
                    (
                        'tipo_instituicao',
                        'universidade',
                    ),
                )
            },
        ),
        ('Dados Familiares', {'fields': (('nome_mae', 'sobrenome_mae'), ('nome_pai', 'sobrenome_pai'), ('estado_civil_mae', 'estado_civil_pai'))}),
        ('Endereço', {'fields': ('logradouro', ('numero', 'complemento'), ('cep', 'bairro'), ('pais', 'cidade'))}),
        ('Telefone', {'fields': ('telefone',)}),
        (
            'Documentos',
            {
                'fields': (
                    'declaracao_vinculo',
                    'documento_adicional_1',
                    'documento_adicional_2',
                    'documento_adicional_3',
                    'documento_adicional_4',
                    'documento_adicional_5',
                )
            },
        ),
    )

    def clean_numero_passaporte(self):
        numero_passaporte = self.cleaned_data.get('numero_passaporte')
        # o login do convocado é o número (legado) ou a chave ARG-AB123456: compara com o passaporte da pessoa dele
        pessoa = self.request.user.get_profile()
        passaporte_do_usuario = formatar_passaporte(pessoa.passaporte if pessoa else None)
        if self.request.user.get_vinculo().eh_usuario_externo() and formatar_passaporte(numero_passaporte) != passaporte_do_usuario:
            raise forms.ValidationError(f'Número de passaporte não corresponde ao do usuário autenticado: {self.request.user.username}.')
        return numero_passaporte

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if 'captura_foto' in self.cleaned_data and self.cleaned_data.get('captura_foto'):
            self.instance.foto.save(f'{self.instance.pk}.jpg', ContentFile(self.cleaned_data['captura_foto']))
        elif 'arquivo_foto' in self.cleaned_data and self.cleaned_data.get('arquivo_foto'):
            self.instance.foto.save(f'{self.instance.pk}.jpg', ContentFile(self.cleaned_data.get('arquivo_foto').read()))
        self.instance.save()


class ProcessarPreMatriculaForm(forms.FormPlus):
    turno = forms.ModelChoiceField(Turno.objects, required=True, label='Turno')
    polo = forms.ModelChoiceField(Polo.objects, required=False, label='Polo EAD', help_text='Apenas para o Turno EAD.')
    forma_ingresso = forms.ModelChoiceField(FormaIngresso.objects, required=True, label='Forma de Ingresso')
    convenio_internacional = forms.ModelChoiceField(
        ParceriaInternacional.objects.none(),
        required=False,
        label='Convênio Internacional',
        help_text='Obrigatório para alunos de intercâmbio internacional. Caso o convênio não tenha sido cadastrado, solicite seu cadastro ao setor de extensao. O tipo de convênio deve ser "Relações Internacionais".',
    )
    possui_convenio = forms.BooleanRequiredField(label='Possui Convênio')
    convenio = forms.ModelChoiceField(Convenio.objects, required=False, label='Convênio')
    numero_pasta = forms.CharFieldPlus(label='Número da Pasta', required=False, max_length=255)

    observacao_matricula = forms.CharField(widget=forms.Textarea(), required=False, label='Observação')

    fieldsets = (
        (
            'Matrícula Institucional',
            {
                'fields': (
                    ('turno', 'forma_ingresso'),
                    ('polo', 'convenio_internacional'),
                    ('possui_convenio', 'convenio'),
                    'numero_pasta',
                    'observacao_matricula',
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['convenio_internacional'].queryset = ParceriaInternacional.objects.all()
