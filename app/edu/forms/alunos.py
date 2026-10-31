import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import transaction

from comum.models import Ano, Configuracao, EmailBlockList, PovoIndigena, PrestadorServico, Raca, UsuarioGrupo, Vinculo
from djtools import forms
from djtools.forms import ReCaptchaField
from djtools.forms.widgets import (
    AutocompleteWidget,
    PhotoCapturePortraitInput,
    RenderableSelectMultiple,
)
from djtools.forms.wizard import FormWizardPlus
from djtools.utils import get_ldap_conf, sync_ldap_user, validar_email_conta_institucional
from edu import tasks
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    Cartorio,
    Cidade,
    CursoCampus,
    MatriculaPeriodo,
    Matriz,
    Observacao,
    Professor,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turma,
)
from pesquisa.models import CursoProgramaPos, DocenteProgramaPos
from rh.deduplicacao.documentos import digitos, recusar_pais_sem_iso
from rh.deduplicacao.entrada import MENSAGEM_CPF_DE_OUTRA_PESSOA, Politica, aplicar_politica, conferir_politica, dona_do_cpf
from rh.deduplicacao.paises import pais_do_aluno
from rh.forms import get_choices_nome_usual
from rh.models import PessoaFisica, Servidor, UnidadeOrganizacional

from .utils import RedirectForm


class AlunoForm(forms.ModelFormPlus):
    nome = forms.CharFieldPlus(width=500)
    nome_social = forms.CharFieldPlus(required=False, label='Nome Social', width=255)
    data_nascimento = forms.DateFieldPlus()
    sexo = forms.ChoiceField(choices=[['M', 'Masculino'], ['F', 'Feminino']])
    genero = forms.ChoiceField(required=False, choices=[('', '---------'), *list(PessoaFisica.GENERO_CHOICES.items())])
    cpf = forms.BrCpfField(label='CPF', required=False)
    passaporte = forms.CharField(required=False, label='Nº do Passaporte')
    cartorio = forms.ModelChoiceFieldPlus(
        Cartorio.objects,
        required=False,
        label='Cartório',
        help_text='Digite o nome do cartório ou cidade para listar os catórios cadastrados',
        widget=AutocompleteWidget(search_fields=Cartorio.SEARCH_FIELDS),
    )

    telefone_principal = forms.BrTelefoneField(max_length=255, required=False, label='Telefone Principal', help_text='(XX) XXXX-XXXX')
    telefone_secundario = forms.BrTelefoneField(max_length=255, required=False, label='Telefone Secundário', help_text='(XX) XXXX-XXXX')
    telefone_adicional_1 = forms.BrTelefoneField(max_length=255, required=False, label='Telefone do Responsável', help_text='(XX) XXXX-XXXX')
    telefone_adicional_2 = forms.BrTelefoneField(max_length=255, required=False, label='Telefone do Responsável', help_text='(XX) XXXX-XXXX')

    raca = forms.ModelChoiceField(Raca.objects.all(), required=True, label='Raça')
    povo_indigena = forms.ModelChoiceField(
        label='Povo indígena',
        queryset=PovoIndigena.objects.all(),
        required=False,
        widget=AutocompleteWidget(search_fields=PovoIndigena.SEARCH_FIELDS),
        help_text='A informação sobre o povo indígena é obrigatória quando a raça for declarada como indígena.',
    )
    tipo_instituicao_origem = forms.ChoiceField(
        required=True, label='Tipo da Instituição', choices=[['', '----'], *Aluno.TIPO_INSTITUICAO_ORIGEM_CHOICES]
    )

    cidade = forms.ModelChoiceFieldPlus(
        Cidade.objects,
        label='Cidade',
        required=True,
        widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS),
    )

    naturalidade = forms.ModelChoiceFieldPlus(
        Cidade.objects,
        label='Naturalidade',
        required=False,
        widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS),
    )

    possui_convenio = forms.BooleanRequiredField(label='Possui Convênio?')

    fieldsets = (
        (
            'Identificação',
            {
                'fields': (
                    'nome',
                    'nome_social',
                    ('cpf', 'passaporte'),
                    ('data_nascimento', 'estado_civil'),
                    (
                        'sexo',
                        'genero',
                    ),
                )
            },
        ),
        (
            'Dados Familiares',
            {
                'fields': (
                    'nome_pai',
                    'estado_civil_pai',
                    'pai_falecido',
                    'nome_mae',
                    'estado_civil_mae',
                    'mae_falecida',
                    'responsavel',
                    'email_responsavel',
                    'parentesco_responsavel',
                    'cpf_responsavel',
                )
            },
        ),
        ('Endereço', {'fields': ('cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'tipo_zona_residencial')}),
        ('Contato', {'fields': (('telefone_principal', 'telefone_secundario'), ('telefone_adicional_1', 'telefone_adicional_2'))}),
        (
            'Deficiências e outras NEEs',
            {
                'fields': (
                    'deficiencias',
                    'outras_nees',
                )
            },
        ),
        (
            'Outras Informações',
            {
                'fields': (
                    'tipo_sanguineo',
                    'nacionalidade',
                    'estrangeiro_sem_passaporte',
                    'pais_origem',
                    'naturalidade',
                    'raca',
                    'povo_indigena',
                )
            },
        ),
        (
            'Dados Escolares',
            {
                'fields': (
                    'nivel_ensino_anterior',
                    'tipo_instituicao_origem',
                    'nome_instituicao_anterior',
                    'ano_conclusao_estudo_anterior',
                    'habilitacao_pedagogica',
                )
            },
        ),
        ('RG', {'fields': ('numero_rg', 'uf_emissao_rg', 'orgao_emissao_rg', 'data_emissao_rg')}),
        (
            'Título de Eleitor',
            {'fields': ('numero_titulo_eleitor', 'zona_titulo_eleitor', 'secao', 'data_emissao_titulo_eleitor', 'uf_emissao_titulo_eleitor')},
        ),
        (
            'Carteira de Reservista',
            {
                'fields': (
                    'numero_carteira_reservista',
                    'regiao_carteira_reservista',
                    'serie_carteira_reservista',
                    'estado_emissao_carteira_reservista',
                    'ano_carteira_reservista',
                )
            },
        ),
        (
            'Certidão Civil',
            {
                'fields': (
                    'tipo_certidao',
                    'cartorio',
                    'numero_certidao',
                    'folha_certidao',
                    'livro_certidao',
                    'data_emissao_certidao',
                    'matricula_certidao',
                )
            },
        ),
        ('Registro', {'fields': ('numero_pasta',)}),
        (
            'Dados da Matrícula',
            {
                'fields': (
                    'turno',
                    'linha_pesquisa',
                    'habilitacao',
                    'forma_ingresso',
                    'convenio_internacional',
                    'aluno_especial',
                    'polo',
                    'possui_convenio',
                    'convenio',
                )
            },
        ),
        ('Dados do MEC', {'fields': ('codigo_educacenso', 'nis')}),
        ('Transporte Escolar', {'fields': ('poder_publico_responsavel_transporte', 'tipo_veiculo')}),
    )

    class Meta:
        model = Aluno
        exclude = ()

    class Media:
        js = ('/static/edu/js/AlunoForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['nome'] = self.instance.pessoa_fisica.nome_registro
            self.initial['nome_social'] = self.instance.pessoa_fisica.nome_social
            self.initial['data_nascimento'] = self.instance.pessoa_fisica.nascimento_data
            self.initial['sexo'] = self.instance.pessoa_fisica.sexo
            self.initial['genero'] = self.instance.pessoa_fisica.genero
            self.initial['cpf'] = self.instance.pessoa_fisica.cpf
            self.initial['raca'] = self.instance.raca.pk if self.instance.raca else None
            self.initial['povo_indigena'] = self.instance.povo_indigena.pk if self.instance.povo_indigena else None
        self.permite_edicao_parcial = self.instance.codigo_academico and Configuracao.get_valor_por_chave(
            'edu', 'permite_editar_parcialmente_alunos_migrados'
        )
        if self.permite_edicao_parcial:
            for k in self.fields:
                self.fields[k].required = False
            self.fields['possui_convenio'] = forms.NullBooleanField(label='Possui Convênio', required=False)

    def save(self, *args, **kwargs):
        # antes do CPF: a PF que já tinha documento válido não troca passaporte nem país pelo cadastro acadêmico
        aplicar_politica(self.instance.pessoa_fisica, self._documento_da_pessoa(), Politica.AUTORITATIVA, preservar_documento=True)
        self.instance.pessoa_fisica.nome_registro = self.cleaned_data['nome']
        self.instance.pessoa_fisica.nome_social = self.cleaned_data['nome_social']
        self.instance.pessoa_fisica.nascimento_data = self.cleaned_data['data_nascimento']
        self.instance.pessoa_fisica.sexo = self.cleaned_data['sexo']
        self.instance.pessoa_fisica.genero = self.cleaned_data['genero']
        self.instance.pessoa_fisica.cpf = self.cleaned_data['cpf']
        self.instance.pessoa_fisica.save()
        v = self.instance.get_vinculo()
        if v:
            v.raca = self.cleaned_data['raca']
            v.povo_indigena = self.cleaned_data['povo_indigena']
            v.save(update_fields=['raca', 'povo_indigena'])

        self.instance.deficiencias.clear()
        for deficiencia in self.cleaned_data.get('deficiencias'):
            self.instance.deficiencias.add(deficiencia)

        self.instance.outras_nees.clear()
        for nee in self.cleaned_data.get('outras_nees'):
            self.instance.outras_nees.add(nee)

        return super().save(*args, **kwargs)

    def clean(self) -> dict:
        cleaned_data = super().clean()
        self._recusar_documento_da_pessoa()
        return cleaned_data

    def _documento_da_pessoa(self) -> dict:
        """Passaporte e país que o ``save`` copia para a PF: o país do formulário é edu.Pais, o da pessoa é comum.Pais."""
        return {'passaporte': self.cleaned_data.get('passaporte'), 'pais_origem': pais_do_aluno(self.cleaned_data.get('pais_origem'))}

    def _recusar_documento_da_pessoa(self) -> None:
        """As recusas do ``save`` como erro do campo passaporte, não 500: país sem ISO de quem não tem CPF, ou par de outra PF.

        Não usa o ``verificar_documento`` da matrícula: ele busca o dono do documento sem excluir a própria PF (recusaria a
        correção da data de nascimento) e aceita o par de outra PF com o mesmo nascimento (que viraria ``IntegrityError``).
        """
        dados = self._documento_da_pessoa()
        pais = dados['pais_origem']
        try:
            recusar_pais_sem_iso(self.cleaned_data.get('cpf'), dados['passaporte'], pais is not None, pais and pais.iso_alfa3)
            conferir_politica(self.instance.pessoa_fisica, dados, Politica.AUTORITATIVA, preservar_documento=True)
        except ValidationError as erro:
            self.add_error('passaporte', erro)

    def clean_convenio_internacional(self):
        forma_ingresso = self.cleaned_data.get('forma_ingresso')
        convenio_internacional = self.cleaned_data.get('convenio_internacional')
        if forma_ingresso and forma_ingresso.descricao.replace('â', 'a').upper() == 'INTERCAMBIO' and not convenio_internacional:
            raise forms.ValidationError('Informe o convênio internacional do aluno')
        return convenio_internacional

    def clean_poder_publico_responsavel_transporte(self):
        poder_publico_responsavel_transporte = self.data.get('poder_publico_responsavel_transporte')
        tipo_veiculo = self.data.get('tipo_veiculo')
        if poder_publico_responsavel_transporte and not self.data.get('tipo_veiculo'):
            raise forms.ValidationError('Informe o tipo transporte público')
        if tipo_veiculo and not self.data.get('poder_publico_responsavel_transporte'):
            raise forms.ValidationError('Informe o responsável pelo transporte público')
        return poder_publico_responsavel_transporte

    def clean_passaporte(self):
        nacionalidade = self.data.get('nacionalidade')
        passaporte = self.data.get('passaporte')
        estrangeiro_sem_passaporte = self.data.get('estrangeiro_sem_passaporte')
        if nacionalidade == 'Estrangeira' and not passaporte and not estrangeiro_sem_passaporte:
            raise forms.ValidationError('Informe o passaporte do aluno.')
        return passaporte

    def clean_cpf(self) -> str | None:
        cpf = self.data.get('cpf')
        nacionalidade = self.data.get('nacionalidade')
        estrangeiro_sem_passaporte = self.data.get('estrangeiro_sem_passaporte')

        brasileiro_sem_cpf = nacionalidade != 'Estrangeira' and not cpf
        estrangeiro_sem_cpf = nacionalidade == 'Estrangeira' and estrangeiro_sem_passaporte and not cpf
        if brasileiro_sem_cpf or estrangeiro_sem_cpf:
            raise forms.ValidationError('Informe o CPF do aluno.')
        # só quando o CPF muda, como no PessoaFisicaForm: o aluno com duplicata legada segue editável até a deduplicação
        pessoa_fisica_id = self.instance.pessoa_fisica_id
        cpf_atual = self.instance.pessoa_fisica.cpf if pessoa_fisica_id else None
        if cpf and digitos(cpf) != digitos(cpf_atual) and dona_do_cpf(cpf, pessoa_fisica_id):
            raise forms.ValidationError(MENSAGEM_CPF_DE_OUTRA_PESSOA)
        return cpf

    def clean_polo(self):
        curso_campus = self.instance.curso_campus
        polo = self.cleaned_data.get('polo')

        if curso_campus.diretoria.ead and not polo:
            raise ValidationError('É necessário informar o Polo do Aluno.')

        if not curso_campus.diretoria.ead and polo:
            raise ValidationError('Remova o polo do aluno.')

        return self.cleaned_data.get('polo')

    def clean_pais_origem(self):
        if 'nacionalidade' in self.cleaned_data:
            nacionalidade = self.cleaned_data['nacionalidade']

            if nacionalidade and nacionalidade != 'Brasileira':
                if not self.cleaned_data.get('pais_origem'):
                    raise forms.ValidationError('O campo país de origem é obrigatório quando a pessoa nasceu no exterior.')

        return self.cleaned_data.get('pais_origem')

    def clean_naturalidade(self):
        if 'nacionalidade' in self.cleaned_data:
            nacionalidade = self.cleaned_data['nacionalidade']
            naturalidade = self.cleaned_data.get('naturalidade')
            nome_pais = naturalidade and naturalidade.pais and naturalidade.pais.nome
            if nacionalidade == 'Brasileira':
                if not naturalidade:
                    raise forms.ValidationError('O campo naturalidade é obrigatório quando a pessoa nasceu no Brasil.')

                if nome_pais != 'Brasil':
                    raise forms.ValidationError('Não pode ser informado uma naturalidade fora do Brasil para aluno com nacionalidade Brasileira.')

            elif nome_pais == 'Brasil':
                raise forms.ValidationError(
                    'Não pode ser informado uma naturalidade do Brasil para aluno com nacionalidade Estrangeira ou Brasileira - Nascido no exterior ou naturalizado.'
                )

        return self.cleaned_data.get('naturalidade')

    def clean_convenio(self):
        possui_convenio = self.cleaned_data.get('possui_convenio')
        if self.permite_edicao_parcial:
            return self.cleaned_data.get('convenio')
        if possui_convenio and not self.data.get('convenio'):
            raise forms.ValidationError('Informe o convênio')
        elif not possui_convenio and self.data.get('convenio'):
            raise forms.ValidationError('Não é possível selecionar um convênio quando o valor do campo "Possui Convênio?" é "Não".')
        return self.cleaned_data.get('convenio')

    def clean_povo_indigena(self):
        povo_indigena = self.cleaned_data.get('povo_indigena')
        raca = self.cleaned_data.get('raca')
        if raca and raca.is_indigena() and not povo_indigena:
            raise ValidationError('O campo Povo indígena é de preenchimento obrigatório quando a raça for Indígena.')
        if povo_indigena and (not raca or not raca.is_indigena()):
            raise ValidationError('O campo Povo indígena só pode ser preenchido quando a raça for Indígena.')
        return povo_indigena


class AlunoCRAForm(AlunoForm):
    fieldsets = (
        ('Identificação', {'fields': ('nome', ('cpf', 'passaporte'), ('sexo', 'data_nascimento'), ('raca', 'povo_indigena'))}),
        ('Dados familiares', {'fields': ('nome_pai', 'nome_mae')}),
        ('Endereço', {'fields': (('cep', 'bairro'), 'logradouro', ('numero', 'complemento'), ('cidade', 'tipo_zona_residencial'))}),
        ('Contato', {'fields': ('telefone_principal',)}),
        (
            'Deficiências e outras NEEs',
            {
                'fields': (
                    'deficiencias',
                    'outras_nees',
                )
            },
        ),
        ('Outras informações', {'fields': ('nacionalidade', 'pais_origem', 'naturalidade', 'tipo_sanguineo')}),
        ('Dados escolares', {'fields': ('nivel_ensino_anterior', ('tipo_instituicao_origem', 'ano_conclusao_estudo_anterior'))}),
        ('RG', {'fields': (('numero_rg', 'uf_emissao_rg'), ('orgao_emissao_rg', 'data_emissao_rg'))}),
        (
            'Título de eleitor',
            {'fields': ('numero_titulo_eleitor', 'zona_titulo_eleitor', 'secao', 'data_emissao_titulo_eleitor', 'uf_emissao_titulo_eleitor')},
        ),
        ('Registro', {'fields': ('numero_pasta',)}),
        (
            'Dados da matrícula',
            {'fields': ('turno', 'habilitacao', 'linha_pesquisa', 'forma_ingresso', ('aluno_especial', 'polo'), ('possui_convenio', 'convenio'))},
        ),
    )

    class Meta:
        model = Aluno
        fields = (
            'nome_pai',
            'nome_mae',
            'logradouro',
            'numero',
            'complemento',
            'bairro',
            'cep',
            'cidade',
            'tipo_zona_residencial',
            'telefone_principal',
            'telefone_secundario',
            'telefone_adicional_1',
            'telefone_adicional_2',
            'nacionalidade',
            'pais_origem',
            'naturalidade',
            'nivel_ensino_anterior',
            'tipo_instituicao_origem',
            'ano_conclusao_estudo_anterior',
            'numero_rg',
            'uf_emissao_rg',
            'orgao_emissao_rg',
            'data_emissao_rg',
            'numero_titulo_eleitor',
            'zona_titulo_eleitor',
            'secao',
            'data_emissao_titulo_eleitor',
            'uf_emissao_titulo_eleitor',
            'numero_pasta',
            'observacao_historico',
            'turno',
            'habilitacao',
            'linha_pesquisa',
            'forma_ingresso',
            'aluno_especial',
            'polo',
            'deficiencias',
            'outras_nees',
            'possui_convenio',
            'convenio',
        )

    class Media:
        js = ('/static/edu/js/AlunoCRAForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['raca'].required = False
        self.fields['povo_indigena'].required = False
        self.fields['cidade'].required = False
        self.fields['logradouro'].required = False
        self.fields['numero'].required = False
        self.fields['bairro'].required = False
        self.fields['tipo_instituicao_origem'].required = False
        self.fields['tipo_zona_residencial'].required = False

        self.fields['naturalidade'].required = True
        self.fields['cpf'].required = True
        self.fields['numero_rg'].required = True
        self.fields['uf_emissao_rg'].required = True
        self.fields['orgao_emissao_rg'].required = True

    def clean_convenio(self):
        possui_convenio = self.cleaned_data.get('possui_convenio')
        if possui_convenio and not self.data.get('convenio'):
            raise forms.ValidationError('Informe o convênio')
        elif not possui_convenio and self.data.get('convenio'):
            raise forms.ValidationError('Não é possível selecionar um convênio quando o valor do campo "Possui Convênio?" é "Não".')
        return self.cleaned_data.get('convenio')


class DadosIncompletosAlunoForm(forms.ModelFormPlus):
    data_nascimento = forms.DateFieldPlus(label='Data de nascimento')

    fieldsets = (
        (
            'Dados pendentes',
            {
                'fields': (
                    'naturalidade',
                    'numero_rg',
                    'uf_emissao_rg',
                    'orgao_emissao_rg',
                    'data_emissao_rg',
                    'data_nascimento',
                    'dt_conclusao_curso',
                )
            },
        ),
    )

    class Meta:
        model = Aluno
        fields = ('naturalidade', 'numero_rg', 'uf_emissao_rg', 'orgao_emissao_rg', 'data_emissao_rg', 'dt_conclusao_curso')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pessoa_fisica.nascimento_data:
            del self.fields['data_nascimento']
        if self.instance.naturalidade:
            del self.fields['naturalidade']
        else:
            self.fields['naturalidade'].required = True
        if self.instance.numero_rg or self.instance.curso_campus.is_fic():
            del self.fields['numero_rg']
            del self.fields['uf_emissao_rg']
            del self.fields['orgao_emissao_rg']
            del self.fields['data_emissao_rg']
        else:
            self.fields['numero_rg'].required = True
            self.fields['uf_emissao_rg'].required = True
            self.fields['orgao_emissao_rg'].required = True
        if self.instance.dt_conclusao_curso:
            del self.fields['dt_conclusao_curso']
        else:
            self.fields['dt_conclusao_curso'].required = True

    @transaction.atomic
    def processar(self):
        data_nascimento = self.cleaned_data.get('data_nascimento')
        if data_nascimento and not self.instance.pessoa_fisica.nascimento_data:
            self.instance.pessoa_fisica.nascimento_data = data_nascimento
            self.instance.pessoa_fisica.save()
        self.instance.save()


class CadastrarMatriculaPeriodo(forms.ModelFormPlus):
    fieldsets = (('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'), ('periodo_matriz', 'situacao'))}),)

    class Meta:
        model = MatriculaPeriodo
        fields = 'ano_letivo', 'periodo_letivo', 'periodo_matriz', 'situacao'

    def __init__(self, aluno_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.aluno_id = aluno_id
        self.fields['periodo_letivo'].choices = [['', '----'], *PERIODO_LETIVO_CHOICES]

    def clean(self):
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        if (
            ano_letivo
            and periodo_letivo
            and MatriculaPeriodo.objects.filter(aluno_id=self.instance.aluno_id, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo).exists()
        ):
            raise forms.ValidationError('Já existe uma matrícula para o ano e período letivo informados.')
        return self.cleaned_data


class SituacaoMatriculaPeriodoForm(forms.ModelFormPlus):
    periodo_matriz = forms.ChoiceField(label='Período da Matriz')
    turma = forms.ModelChoiceFieldPlus(Turma.objects, label='Turma', required=False)
    METHOD = 'POST'

    class Meta:
        model = MatriculaPeriodo
        fields = ('situacao', 'periodo_matriz', 'turma', 'periodo_integralizado_ensino_medio')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['turma'].queryset = Turma.objects.filter(ano_letivo_id=self.instance.ano_letivo_id, periodo_letivo=self.instance.periodo_letivo)
        periodo_matriz_choices = [
            ['', '---'],
        ]
        periodo_matriz_choices += [[x, x] for x in range(1, 16)]
        self.fields['periodo_matriz'].choices = periodo_matriz_choices
        if not self.instance.aluno.integralizou_ensino_medio:
            del self.fields['periodo_integralizado_ensino_medio']

    def clean(self):
        turma = self.cleaned_data.get('turma')
        if turma:
            periodo_matriz = self.cleaned_data.get('periodo_matriz')
            if turma.periodo_matriz != int(periodo_matriz):
                raise forms.ValidationError(
                    f'O período da matriz ({periodo_matriz}) está diferente do período da turma selecionada ({turma.periodo_matriz}).'
                )
        else:
            return self.cleaned_data

    def processar(self):
        self.instance.situacao = self.cleaned_data.get('situacao')
        self.instance.save()
        self.instance.aluno.atualizar_situacao('Alteração de Situação de Matrícula no Período')


class SituacaoMatriculaForm(forms.ModelFormPlus):
    METHOD = 'POST'

    class Meta:
        model = Aluno
        fields = ('situacao',)

    def processar(self):
        self.instance.situacao = self.cleaned_data.get('situacao')
        self.instance.save()


class TurnoForm(forms.ModelFormPlus):
    METHOD = 'POST'

    class Meta:
        model = Aluno
        fields = ('turno',)


class AlterarAnoPeriodoIngressoForm(forms.FormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)


class AtualizarDadosPessoaisForm(forms.FormPlus):
    """Formulário de atualização de dados pessoais do aluno durante renovação de matrícula.

    Exibe campos de dados pessoais, endereço, telefones, transporte escolar
    e programas sociais, com validação condicional para o NIS conforme
    participação em programas sociais.
    """

    nome_usual = forms.ChoiceField(label='Nome Usual', required=False, help_text='Nome que será exibido no SUAP')
    lattes = forms.URLField(label='Lattes', help_text='Endereço do currículo lattes', required=False)
    orcid = forms.URLField(label='ORCID', help_text='Endereço do ORCID, por exemplo, https://orcid.org/0000-0000-0000-0000', required=False)
    logradouro = forms.CharFieldPlus(max_length=255, required=True, label='Logradouro', width=500)
    numero = forms.CharFieldPlus(max_length=255, required=True, label='Número', width=100)
    complemento = forms.CharField(max_length=255, required=False, label='Complemento')
    bairro = forms.CharField(max_length=255, required=True, label='Bairro')
    cep = forms.BrCepField(max_length=255, required=False, label='CEP')
    cidade = forms.ModelChoiceFieldPlus(Cidade.objects, required=True, label='Cidade', widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS))

    telefone_principal = forms.CharFieldPlus(max_length=255, label='Telefone Principal', required=False)
    telefone_secundario = forms.CharFieldPlus(max_length=255, label='Telefone Secundário', required=False)
    esconde_telefone = forms.CharFieldPlus(max_length=1, label='esconde_telefone', required=False, widget=forms.HiddenInput())

    utiliza_transporte_escolar_publico = forms.ChoiceField(
        label='Utiliza Transporte Escolar Público', required=True, choices=[['', '---------'], ['Sim', 'Sim'], ['Não', 'Não']]
    )
    poder_publico_responsavel_transporte = forms.ChoiceField(
        label='Poder Público Responsável pelo Transporte Escolar',
        choices=[['', '---------'], *Aluno.PODER_PUBLICO_RESPONSAVEL_TRANSPORTE_CHOICES],
        required=False,
    )
    tipo_veiculo = forms.ChoiceField(
        label='Tipo de Veículo Utilizado no Transporte Escolar', choices=[['', '---------'], *Aluno.TIPO_VEICULO_CHOICES_FOR_FORM], required=False
    )
    nis = forms.CharField(max_length=25, required=False, label='NIS', help_text='Obrigatório para participantes de programas sociais.')

    fieldsets = (
        ('Dados Pessoais', {'fields': ('nome_usual',)}),
        ('Identificadores Acadêmicos', {'fields': ('lattes', 'orcid')}),
        ('Endereço', {'fields': ('cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade')}),
        ('Telefones', {'fields': ('telefone_principal', 'telefone_secundario', 'esconde_telefone')}),
        ('Transporte Escolar Utilizado', {'fields': ('utiliza_transporte_escolar_publico', 'poder_publico_responsavel_transporte', 'tipo_veiculo')}),
        ('Programas Sociais', {'fields': ('nis',)}),
    )

    def __init__(self, instance: Aluno | None = None, pode_realizar_procedimentos: bool = False, *args: object, **kwargs: object) -> None:
        """Inicializa o formulário configurando campos conforme permissões e dados do aluno.

        Args:
            instance: instância do ``Aluno`` a ser editada.
            pode_realizar_procedimentos: quando ``True``, exibe campos de
                telefone em vez do campo oculto ``esconde_telefone``.
        """
        super().__init__(*args, **kwargs)
        self.pode_realizar_procedimentos = pode_realizar_procedimentos
        self.fields['nome_usual'].choices = get_choices_nome_usual(instance.pessoa_fisica.nome)
        if hasattr(instance, 'nome_social'):
            [self.fields['nome_usual'].choices.append(nome) for nome in get_choices_nome_usual(instance.nome_social)]
        # adicionado o nome usual atual caso ele não seja nenhuma combinação retornada pela função acima
        choice = [instance.pessoa_fisica.nome_usual, instance.pessoa_fisica.nome_usual]
        if instance.pessoa_fisica.nome_usual and choice not in self.fields['nome_usual'].choices:
            self.fields['nome_usual'].choices.append(choice)
        if not self.pode_realizar_procedimentos:
            del self.fields['telefone_principal']
            del self.fields['telefone_secundario']
        else:
            del self.fields['esconde_telefone']
        if instance:
            self.fields['lattes'].initial = instance.pessoa_fisica.lattes
            self.fields['orcid'].initial = instance.pessoa_fisica.orcid
        requer_nis = Aluno.objects.filter(id=instance.id if instance else 0, caracterizacao__beneficiario_programa_social__isnull=False).exists()
        self.fields['nis'].required = requer_nis

    def save(self, instance: Aluno | None = None) -> None:
        """Persiste os dados pessoais e de endereço do aluno no banco.

        Args:
            instance: instância do ``Aluno`` a ser atualizada.
        """
        instance.logradouro = self.cleaned_data['logradouro']
        instance.numero = self.cleaned_data['numero']
        instance.complemento = self.cleaned_data['complemento']
        instance.bairro = self.cleaned_data['bairro']
        instance.cep = self.cleaned_data['cep']
        instance.cidade = self.cleaned_data['cidade']
        instance.pessoa_fisica.nome_usual = self.cleaned_data['nome_usual']
        instance.pessoa_fisica.lattes = self.cleaned_data['lattes']
        instance.pessoa_fisica.orcid = self.cleaned_data['orcid']
        if self.pode_realizar_procedimentos:
            instance.telefone_principal = self.cleaned_data['telefone_principal']
            instance.telefone_secundario = self.cleaned_data['telefone_secundario']
        instance.pessoa_fisica.save()
        if self.cleaned_data['utiliza_transporte_escolar_publico']:
            instance.poder_publico_responsavel_transporte = self.cleaned_data['poder_publico_responsavel_transporte']
            instance.tipo_veiculo = self.cleaned_data['tipo_veiculo']
        else:
            instance.poder_publico_responsavel_transporte = None
            instance.tipo_veiculo = None
        instance.nis = self.cleaned_data['nis']
        instance.save()

    def clean_lattes(self) -> str:
        lattes = self.cleaned_data.get('lattes')
        if lattes and len(lattes) > 200:
            raise forms.ValidationError(
                'Endereço do currículo lattes inválido. Informe a URL curta, por exemplo, http://buscatextual.cnpq.br/buscatextual/visualizacv.do?id=123456'
            )
        return lattes

    def clean_orcid(self) -> str:
        orcid = self.cleaned_data.get('orcid')
        if orcid and len(orcid) > 200:
            raise forms.ValidationError('Endereço do ORCID inválido. Informe a URL curta, por exemplo, https://orcid.org/0000-0000-0000-0000')
        return orcid

    def clean_utiliza_transporte_escolar_publico(self) -> str:
        utiliza_transporte_escolar_publico = self.cleaned_data.get('utiliza_transporte_escolar_publico')
        if utiliza_transporte_escolar_publico == 'Sim':
            if not self.data.get('poder_publico_responsavel_transporte') or not self.data.get('tipo_veiculo'):
                raise forms.ValidationError('Informe o responsável pelo transporte público e o tipo utilizado')
        elif utiliza_transporte_escolar_publico == 'Não':
            if self.data.get('poder_publico_responsavel_transporte') or self.data.get('tipo_veiculo'):
                raise forms.ValidationError(
                    'Se não utiliza transporte público, os campos "Poder Público Responsável pelo Transporte Escolar" e "Tipo de Veículo Utilizado no Transporte Escolar" não podem estar preenchidos.'
                )
        else:
            if self.data.get('poder_publico_responsavel_transporte') or self.data.get('tipo_veiculo'):
                raise forms.ValidationError(
                    'Marque a opção "Utiliza Transporte Escolar Público" caso deseje informar o responsável ou tipo de transporte público utilizado.'
                )
        return utiliza_transporte_escolar_publico

    class Media:
        js = ('/static/edu/js/AtualizarDadosPessoaisForm.js',)

    class Meta:
        fields = ('nome_social', 'logradouro', 'numero', 'complemento', 'bairro', 'cep', 'cidade', 'nis')


class AtualizarDadosSISTECAlunoForm(forms.ModelFormPlus):
    class Meta:
        model = Aluno
        fields = ('data_inicio_ciclo', 'data_prevista_termino_ciclo', 'codigo_sistec')


class AtualizarFotoForm(forms.FormPlus):
    aluno = forms.ModelChoiceField(Aluno.objects, widget=forms.HiddenInput())
    foto = forms.PhotoCaptureField(required=False, widget=PhotoCapturePortraitInput)
    arquivo = forms.ImageFieldPlus(required=False)

    fieldsets = (('Captura da Foto com Câmera', {'fields': ('aluno', 'foto')}), ('Upload de Arquivo', {'fields': ('arquivo',)}))

    def clean(self):
        if not self.cleaned_data.get('foto') and not self.cleaned_data.get('arquivo'):
            raise forms.ValidationError('Retire a foto com a câmera ou forneça um arquivo.')
        else:
            return self.cleaned_data

    def processar(self, request):
        aluno = self.cleaned_data.get('aluno')
        if 'foto' in self.cleaned_data and self.cleaned_data.get('foto'):
            dados = self.cleaned_data.get('foto')
        else:
            dados = self.cleaned_data.get('arquivo').read()

        if request.user.has_perm('edu.efetuar_matricula'):
            aluno.foto.save(f'{aluno.pk}.jpg', ContentFile(dados))
            # ponytail: write redundante para PessoaFisica.foto removido — S2.2 migra foto para Vínculo; Aluno.foto (campo próprio) é escalado
            return 'Foto atualizada com sucesso.'
        else:
            return 'Esta funcionalidade encontra-se temporariamente indisponível.'


class BuscaAlunoForm(RedirectForm):
    aluno = forms.ModelChoiceFieldPlus(Aluno.objects, label='Matrícula/Nome', widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS))

    def get_url(self):
        return self.cleaned_data['aluno'].get_absolute_url()


class ImprimirHistoricoParcialForm(RedirectForm):
    aluno = forms.ModelChoiceFieldPlus(Aluno.objects, label='Matrícula/Nome', widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS))

    def get_url(self):
        return '/edu/emitir_historico_parcial_pdf/{}/'.format(self.cleaned_data['aluno'].pk)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['aluno'].queryset = Aluno.objects.filter(matriz__estrutura__proitec=False, matriz__isnull=False)


class ImprimirHistoricoFinalForm(RedirectForm):
    aluno = forms.ModelChoiceFieldPlus(Aluno.objects, label='Matrícula/Nome', widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS))

    def get_url(self):
        return '/edu/emitir_historico_final_pdf/{}/'.format(self.cleaned_data['aluno'].pk)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['aluno'].queryset = Aluno.objects.filter(
            matriz__estrutura__proitec=False, matriz__isnull=False, situacao__id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.EGRESSO]
        )


class ImprimirHistoricoFinalEmLoteForm(FormWizardPlus):
    FECHAMENTO_POR_MATRICULA = 'MATRICULA'
    FECHAMENTO_POR_TURMA = 'TURMA'
    FECHAMENTO_POR_CURSO = 'CURSO'
    TIPO_FECHAMENTO_CHOICES = [[FECHAMENTO_POR_TURMA, 'Por Turma'], [FECHAMENTO_POR_CURSO, 'Por Curso']]

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    tipo = forms.ChoiceField(choices=TIPO_FECHAMENTO_CHOICES, widget=forms.RadioSelect())
    turma = forms.ModelChoiceFieldPlus(Turma.objects, label='Turma', required=False, help_text='Apenas para turmas de cursos da modalidade FIC.')
    curso = forms.ModelChoiceFieldPlus(CursoCampus.objects, label='Curso', required=False, help_text='Apenas para cursos da modalidade FIC.')
    alunos = forms.MultipleModelChoiceField(Aluno.objects, label='', widget=RenderableSelectMultiple('widgets/alunos_widget.html'))

    class Media:
        js = ('/static/edu/js/ImprimirHistoricoFinalEmLoteForm.js',)

    steps = ([('Filtro', {'fields': ('ano_letivo', 'periodo_letivo', 'tipo', 'turma', 'curso')})], [('Seleção dos Alunos', {'fields': ('alunos',)})])

    def clean_tipo(self):
        curso = self.get_entered_data('curso')
        turma = self.get_entered_data('turma')

        if not (curso or turma):
            raise ValidationError('Você precisa informar o Curso ou a Turma.')

        return self.cleaned_data['tipo']

    def next_step(self):
        curso = self.get_entered_data('curso')
        turma = self.get_entered_data('turma')
        ano_letivo = self.get_entered_data('ano_letivo')
        periodo_letivo = self.get_entered_data('periodo_letivo')
        if 'turma' in self.fields:
            self.fields['turma'].queryset = Turma.locals.all()
        if 'alunos' in self.fields:
            qs = Aluno.objects.filter(situacao__id=SituacaoMatricula.CONCLUIDO).exclude(matriz__id__isnull=True)
            if ano_letivo:
                qs = qs.filter(matriculaperiodo__ano_letivo=ano_letivo)
            if periodo_letivo:
                qs = qs.filter(matriculaperiodo__periodo_letivo=periodo_letivo)
            if curso:
                qs = qs.filter(curso_campus=curso)
            if turma:
                qs = qs.filter(matriculaperiodo__turma=turma)

            self.fields['alunos'].queryset = qs.distinct()

    def processar(self):
        return self.cleaned_data.get('alunos')


class ImprimirBoletinsEmLoteForm(FormWizardPlus):
    FECHAMENTO_POR_MATRICULA = 'MATRICULA'
    FECHAMENTO_POR_TURMA = 'TURMA'
    FECHAMENTO_POR_CURSO = 'CURSO'
    TIPO_FECHAMENTO_CHOICES = [[FECHAMENTO_POR_TURMA, 'Por Turma'], [FECHAMENTO_POR_CURSO, 'Por Curso']]

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    situacao = forms.ModelChoiceField(SituacaoMatricula.objects, label='Situação no Curso', required=False)
    situacao_periodo = forms.ModelChoiceField(SituacaoMatriculaPeriodo.objects, label='Situação no Período', required=False)
    tipo = forms.ChoiceField(choices=TIPO_FECHAMENTO_CHOICES, widget=forms.RadioSelect())
    turma = forms.ModelChoiceFieldPlus(
        Turma.objects,
        label='Turma',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Turma.SEARCH_FIELDS, form_filters=[('ano_letivo', 'ano_letivo'), ('periodo_letivo', 'periodo_letivo')]
        ),
    )
    curso = forms.ModelChoiceFieldPlus(CursoCampus.objects, label='Curso', required=False)
    alunos = forms.MultipleModelChoiceField(Aluno.objects, label='', widget=RenderableSelectMultiple('widgets/alunos_widget.html', max_result=500))

    disposicao_texto = forms.ChoiceField(
        label='Formato da Página', choices=[('retrato', 'Retrato'), ('paisagem', 'Paisagem')], widget=forms.RadioSelect(), initial='retrato'
    )

    class Media:
        js = ('/static/edu/js/ImprimirHistoricoFinalEmLoteForm.js',)

    steps = (
        [('Filtro', {'fields': ('ano_letivo', 'periodo_letivo', 'situacao', 'situacao_periodo', 'tipo', 'turma', 'curso')})],
        [('Seleção dos Alunos', {'fields': ('disposicao_texto', 'alunos')})],
    )

    def clean_tipo(self):
        curso = self.get_entered_data('curso')
        turma = self.get_entered_data('turma')

        if not (curso or turma):
            raise ValidationError('Você precisa informar o Curso ou a Turma.')

        return self.cleaned_data['tipo']

    def next_step(self):
        curso = self.get_entered_data('curso')
        turma = self.get_entered_data('turma')
        ano_letivo = self.get_entered_data('ano_letivo')
        periodo_letivo = self.get_entered_data('periodo_letivo')
        situacao = self.get_entered_data('situacao')
        situacao_periodo = self.get_entered_data('situacao_periodo')
        if 'alunos' in self.fields:
            qs = MatriculaPeriodo.objects.filter(
                matriculadiario__isnull=False, aluno__matriz_id__isnull=False, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo
            )
            if curso:
                qs = qs.filter(aluno__curso_campus=curso)
            if turma:
                qs = qs.filter(turma=turma)
            if situacao:
                qs = qs.filter(aluno__situacao=situacao)
            if situacao_periodo:
                qs = qs.filter(situacao=situacao_periodo)
            qs = qs.values_list('aluno_id', flat=True)
            qs = Aluno.objects.filter(pk__in=qs)
            self.fields['alunos'].queryset = qs.distinct()

    def processar(self):
        return MatriculaPeriodo.objects.filter(
            aluno__in=self.cleaned_data.get('alunos'),
            ano_letivo=self.cleaned_data.get('ano_letivo'),
            periodo_letivo=self.cleaned_data.get('periodo_letivo'),
        )


class ImprimirBoletimAlunoForm(RedirectForm):
    matricula_periodo = forms.ModelChoiceFieldPlus(
        MatriculaPeriodo.objects, label='Matrícula/Nome', widget=AutocompleteWidget(search_fields=MatriculaPeriodo.SEARCH_FIELDS)
    )

    def get_url(self):
        return '/edu/emitir_boletim_pdf/{}/'.format(self.cleaned_data['matricula_periodo'].pk)


class ImportacaoAlunosForm(forms.FormPlus):
    prefixo = forms.CharField(
        label='Prefixo',
        required=False,
        help_text='Caso o prefixo não seja informado, serão importados todos os alunos que foram atualizados desde a última importação.',
    )

    def processar(self):
        if self.cleaned_data['prefixo']:
            call_command('edu_importar_dados', self.cleaned_data['prefixo'], verbosity='0')
        else:
            call_command('edu_importar_dados', verbosity='0')

    def clean_prefixo(self):
        if 5 > len(self.cleaned_data['prefixo']) > 0:
            raise forms.ValidationError('Insira um prefixo com no mínimo 5 (cinco) dígitos')
        else:
            return self.cleaned_data['prefixo']


class ExportarAlunosCaracterizacaoForm(forms.FormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects, label='Ano Letivo de Ingresso', required=True)
    periodo_letivo = forms.ChoiceField(choices=PERIODO_LETIVO_CHOICES, label='Período Letivo de Ingresso', required=True)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.campi(), label='Campus', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ano_corrente = datetime.datetime.now().year
        self.fields['ano_letivo'].queryset = Ano.objects.filter(ano__gte=2015, ano__lte=ano_corrente)

    def processar(self):
        return tasks.exportar_dados_aluno_caracterizacao(
            ano_ingresso=self.cleaned_data['ano_letivo'].ano,
            periodo_ingresso=int(self.cleaned_data['periodo_letivo']),
            sigla_campus=self.cleaned_data['uo'].sigla,
        )


class EditarDadosResponsavelForm(forms.ModelFormPlus):
    fieldsets = (('Dados do Responsável', {'fields': (('parentesco_responsavel', 'cpf_responsavel'), 'responsavel', 'email_responsavel')}),)

    class Meta:
        model = Aluno
        fields = ('parentesco_responsavel', 'cpf_responsavel', 'responsavel', 'email_responsavel')


class AlterarMatrizAlunoForm(forms.ModelFormPlus):
    matriz = forms.ModelChoiceField(Matriz.objects, label='Nova Matriz')
    motivo = forms.CharFieldPlus(
        label='Motivo',
        required=True,
        widget=forms.Textarea(),
        help_text='Informe a justificativa para a alteração da matriz do aluno.',
    )

    class Meta:
        model = Aluno
        fields = ['matriz']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['matriz'].queryset = (
            self.fields['matriz']
            .queryset.filter(matrizcurso__curso_campus=self.instance.curso_campus)
            .exclude(matrizcurso__matriz=self.instance.matriz)
        )

        self.ch_cumprida_anterior = self.instance.get_ch_cumprida()
        self.matriz_anterior = self.instance.matriz

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.eh_aluno_minicurso():
            raise forms.ValidationError('Alunos de curso FIC- (Minicurso) não possuem matriz curricular.')
        return cleaned_data

    @transaction.atomic()
    def processar(self, vinculo):
        self.save()
        self.instance.atualizar_situacao('Alteração de Matriz')
        self.instance.identificar_registros_equivalencia(gerar=True)
        ch_cumprida_nova_matriz = self.instance.get_ch_cumprida()
        if self.ch_cumprida_anterior != ch_cumprida_nova_matriz:
            from edu.models import ProcedimentoReducaoCH

            pr = ProcedimentoReducaoCH()
            pr.matricula_periodo = self.instance.get_ultima_matricula_periodo()
            pr.tipo_procedimento = ProcedimentoReducaoCH.MUDANCA_MATRIZ
            pr.motivo = self.cleaned_data.get('motivo')
            pr.informacao_complementar = f'Alteração da matriz <strong>{self.matriz_anterior}</strong> para <strong>{self.instance.matriz}</strong>.'
            pr.vinculo = vinculo
            pr.ch_nova = ch_cumprida_nova_matriz
            pr.ch_anterior = self.ch_cumprida_anterior
            pr.save()


class AlterarMatrizLoteForm(forms.FormPlus):
    SUBMIT_LABEL = 'Pesquisar'
    METHOD = 'GET'

    ano_letivo = forms.ModelChoiceField(Ano.objects, label='Ano letivo')
    periodo_letivo = forms.ChoiceField(label='Período letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    matriz_origem = forms.ModelChoiceFieldPlus(Matriz.objects, label='Matriz de Origem', required=False)
    matriz_destino = forms.ModelChoiceFieldPlus(
        Matriz.objects,
        label='Matriz de Destino',
        widget=AutocompleteWidget(
            search_fields=Matriz.SEARCH_FIELDS, form_filters=[('matriz_origem', 'matrizcurso__curso_campus__matrizcurso__matriz')]
        ),
    )

    matriculas = forms.CharField(
        label='Matrículas',
        widget=forms.Textarea(),
        help_text='Informe as matrículas dos alunos separadas por espaço ou quebra de linha.',
        required=False,
    )

    ano_ingresso_inicio = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano de ingresso a partir de', required=False)
    ano_ingresso_fim = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano de ingresso até', required=False)
    periodo_ingresso_inicio = forms.ChoiceField(
        choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período de ingresso a partir de', required=False
    )
    periodo_ingresso_fim = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período de ingresso até', required=False)

    periodo_referencia = forms.ChoiceField(
        label='Período de referência atual', required=False, choices=[[0, '----']] + [[x, x] for x in range(1, 11)]
    )

    motivo = forms.CharFieldPlus(
        label='Motivo',
        required=True,
        widget=forms.Textarea(),
        help_text='Informe o motivo da alteração em lote da matriz curricular dos alunos.',
    )

    fieldsets = (
        ('Período letivo', {'fields': (('ano_letivo', 'periodo_letivo'), 'matriz_destino')}),
        (
            'Alunos',
            {
                'fields': (
                    'matriz_origem',
                    'matriculas',
                )
            },
        ),
        (
            'Período de ingresso',
            {
                'fields': (
                    ('ano_ingresso_inicio', 'periodo_ingresso_inicio'),
                    ('ano_ingresso_fim', 'periodo_ingresso_fim'),
                )
            },
        ),
        (
            'Outros filtros',
            {'fields': ('periodo_referencia',)},
        ),
        (
            'Justificativa',
            {'fields': ('motivo',)},
        ),
    )

    def clean(self):
        if not self.cleaned_data.get('matriz_origem') and not self.cleaned_data.get('matriculas'):
            raise forms.ValidationError('Informe a matriz de origem ou as matrículas')
        return super().clean()

    def processar(self):
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        matriz_origem = self.cleaned_data['matriz_origem']

        ano_ingresso_inicio = self.cleaned_data['ano_ingresso_inicio']
        ano_ingresso_fim = self.cleaned_data['ano_ingresso_fim']
        periodo_ingresso_inicio = self.cleaned_data['periodo_ingresso_inicio'] or 0
        periodo_ingresso_fim = self.cleaned_data['periodo_ingresso_fim'] or 0
        periodo_referencia = self.cleaned_data['periodo_referencia'] or 0

        matriculas = self.cleaned_data['matriculas']
        matriculas = [matricula for matricula in matriculas.split() if matricula]

        qs = Aluno.locals_uo.filter(
            matriculaperiodo__ano_letivo=ano_letivo,
            matriculaperiodo__periodo_letivo=periodo_letivo,
            situacao__ativo=True,
        )

        if matriculas:
            qs = qs.filter(matricula__in=matriculas)
        if matriz_origem:
            qs = qs.filter(matriz=matriz_origem)

        if int(periodo_referencia):
            qs = qs.filter(periodo_atual=periodo_referencia)
        if ano_ingresso_inicio:
            qs = qs.filter(ano_letivo__ano__gte=ano_ingresso_inicio.ano)
            if int(periodo_ingresso_inicio) == 2:
                qs = qs.exclude(ano_letivo=ano_ingresso_inicio, periodo_letivo=1)
        if ano_ingresso_fim:
            qs = qs.filter(ano_letivo__ano__lte=ano_ingresso_fim.ano)
            if int(periodo_ingresso_fim) == 1:
                qs = qs.exclude(ano_letivo=ano_ingresso_fim, periodo_letivo=2)
        return qs.order_by('curso_campus__codigo')


class AtualizarFotosAlunosForm(forms.FormPlus):
    fotos = forms.MultiFileField(
        help_text='Os nomes dos arquivos devem conter apenas a MATRÍCULA do aluno. Só serão aceitos arquivos com a extensão JPG.'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def processar(self):
        arquivos_problemas = []
        arquivos = self.request.FILES.getlist('fotos')
        for arquivo in arquivos:
            try:
                matricula = arquivo.name.lower().split('.jpg')[0]
                qs_aluno = Aluno.objects.filter(matricula=matricula.upper())
                if qs_aluno.exists():
                    aluno = qs_aluno[0]
                    aluno.foto.save(f'{aluno.pk}.jpg', ContentFile(arquivo.read()))
                else:
                    arquivos_problemas.append(arquivo.name)
            except Exception:
                arquivos_problemas.append(arquivo.name)
        return arquivos_problemas


class AcessoResponsavelForm(forms.FormPlus):
    SUBMIT_LABEL = 'Acessar'

    matricula = forms.CharField(label='Matrícula', help_text='Informe a matrícula do aluno.', widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    chave = forms.CharField(label='Chave', help_text='Informe a chave de acesso do aluno.', widget=forms.PasswordInput(attrs={'autocomplete': 'off'}))

    recaptcha = ReCaptchaField(label='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['recaptcha'].public_key = settings.RECAPTCHA_PUBLIC_KEY
        self.fields['recaptcha'].private_key = settings.RECAPTCHA_PRIVATE_KEY

    def get_chave(self, matricula):
        qs = Aluno.objects.filter(matricula=matricula)
        if qs.exists():
            return qs[0].get_chave_responsavel()
        return None

    def clean(self):
        matricula = self.cleaned_data.get('matricula')
        chave = self.cleaned_data.get('chave')
        if matricula and chave:
            if chave.lower() != self.get_chave(matricula):
                raise ValidationError('Chave de acesso é incompatível com matrícula do aluno.')
        return self.cleaned_data


class ObservacaoForm(forms.ModelForm):
    class Meta:
        model = Observacao
        exclude = ('aluno', 'usuario', 'data')

    def __init__(self, aluno, usuario, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aluno = aluno
        self.usuario = usuario

    def save(self, *args, **kwargs):
        self.instance.aluno = self.aluno
        self.instance.usuario = self.usuario
        self.instance.data = datetime.datetime.now()
        self.instance.save()


class AtualizarEmailAlunoForm(forms.FormPlus):
    email_secundario = forms.EmailField(max_length=255, required=False, label='E-mail Pessoal')
    email_academico = forms.EmailField(max_length=255, required=False, label='E-mail Acadêmico')
    email_google_classroom = forms.EmailField(max_length=255, required=False, label='E-mail Google ClassRoom')

    def _clean_email_conta_institucional(self, email: str) -> str:
        email = (email or '').strip().lower()
        if not validar_email_conta_institucional(email):
            raise forms.ValidationError('Informe um e-mail com apenas letras, números e pontos antes do @.')
        return email

    def __init__(self, *args, **kwargs):
        self.aluno = kwargs.pop('aluno')

        super().__init__(*args, **kwargs)

        if self.aluno.get_vinculo() is None:
            self.aluno.save()  # força criação de vínculo
        self.fields['email_secundario'].initial = self.aluno.get_vinculo().email_pessoal
        self.fields['email_academico'].initial = self.aluno.email_academico
        self.fields['email_google_classroom'].initial = self.aluno.email_google_classroom
        cra = UsuarioGrupo.objects.filter(
            user=self.request.user, group__name='Coordenador de Registros Acadêmicos', setores__uo=self.aluno.curso_campus.diretoria.setor.uo_id
        ).exists()
        if not self.request.user.has_perm('rh.pode_editar_email_secundario_aluno') and not cra:
            del self.fields['email_secundario']
        if not self.request.user.has_perm('rh.pode_editar_email_academico'):
            del self.fields['email_academico']
        if not self.request.user.has_perm('rh.pode_editar_email_google_classroom'):
            del self.fields['email_google_classroom']

        texto_politica_email = Configuracao.get_valor_por_chave('comum', 'texto_politica_email')
        if texto_politica_email and (
            self.fields.get('email_institucional') or self.fields.get('email_academico') or self.fields.get('email_google_classroom')
        ):
            self.INFO = texto_politica_email

    def clean_email_secundario(self):
        if not Configuracao.get_valor_por_chave('comum', 'permite_email_institucional_email_secundario') and Configuracao.eh_email_institucional(
            self.cleaned_data['email_secundario']
        ):
            raise forms.ValidationError('Escolha um e-mail que não seja institucional.')
        return self.cleaned_data['email_secundario']

    def clean_email_academico(self) -> str:
        email_academico = self._clean_email_conta_institucional(self.cleaned_data['email_academico'])
        if email_academico:
            if Aluno.objects.exclude(pk=self.aluno.id).filter(email_academico=email_academico).exists():
                raise forms.ValidationError('O e-mail informado já existe para outro usuário.')
            if Servidor.objects.filter(email_academico=email_academico).exists():
                raise forms.ValidationError('O e-mail informado já existe para outro usuário.')
            if EmailBlockList.objects.filter(email=email_academico).exists():
                raise forms.ValidationError('O e-mail informado está bloqueado.')
            ldap_conf = get_ldap_conf()
            if ldap_conf and ldap_conf.has_write_permission():
                usernames = ldap_conf.get_usernames_from_principalname(email_academico)
                usernames.extend(ldap_conf.get_usernames_from_mail(email_academico))
                if usernames and self.aluno.matricula not in usernames:
                    raise forms.ValidationError('O e-mail informado já é utilizado por outro usuário.')
        return email_academico

    def clean_email_google_classroom(self) -> str:
        email_google_classroom = self._clean_email_conta_institucional(self.cleaned_data['email_google_classroom'])
        if email_google_classroom:
            if Aluno.objects.exclude(pk=self.aluno.id).filter(email_google_classroom=email_google_classroom).exists():
                raise forms.ValidationError('O e-mail informado já existe para outro usuário.')
            if Servidor.objects.filter(email_google_classroom=email_google_classroom).exists():
                raise forms.ValidationError('O e-mail informado já existe para outro usuário.')
            if PrestadorServico.objects.filter(email_google_classroom=email_google_classroom).exists():
                raise forms.ValidationError('O e-mail informado já existe para outro usuário.')
            if EmailBlockList.objects.filter(email=email_google_classroom).exists():
                raise forms.ValidationError('O e-mail informado está bloqueado.')

            ldap_conf = get_ldap_conf()
            if ldap_conf and ldap_conf.has_write_permission():
                usernames = ldap_conf.get_usernames_from_email_google_classroom(email_google_classroom)
                if usernames and self.aluno.matricula not in usernames:
                    raise forms.ValidationError('O e-mail informado já é utilizado por outro usuário.')
        return email_google_classroom

    def save(self):
        if 'email_academico' in self.cleaned_data:
            self.aluno.email_academico = self.cleaned_data.get('email_academico')
        if 'email_google_classroom' in self.cleaned_data:
            self.aluno.email_google_classroom = self.cleaned_data.get('email_google_classroom')
        self.aluno.save()
        if 'email_secundario' in self.cleaned_data:
            v = self.aluno.get_vinculo()
            if v:
                v.email_pessoal = self.cleaned_data.get('email_secundario') or ''
                v.save(update_fields=['email_pessoal'])

        # Sincroniza o usuário no LDAP, se o app ldap_backend estiver instalado
        sync_ldap_user(self.aluno.matricula)


class EditarOrientacaoForm(forms.ModelFormPlus):
    orientador = forms.ModelChoiceField(
        queryset=Professor.objects,
        widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS),
        label='Orientador',
        required=True,
        help_text='Serão listados docentes cadastrados no Corpo Docente do programa de Pós-Graduação',
    )
    coorientadores = forms.MultipleModelChoiceFieldPlus(
        Vinculo.objects.funcionarios_ativos(),
        label='Coorientadores',
        required=False,
    )

    class Meta:
        model = Aluno
        fields = (
            'orientador',
            'coorientadores',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            pks_curso_programas = CursoProgramaPos.objects.filter(curso=self.instance.curso_campus).values_list('programa', flat=True)
            pks_professores_curso = DocenteProgramaPos.objects.filter(programa__in=pks_curso_programas).values_list('docente', flat=True)
            self.fields['orientador'].queryset = self.fields['orientador'].queryset.filter(pk__in=pks_professores_curso)


class SolicitarQuitacaoNadaConstaForm(forms.FormPlus):
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(attrs={'rows': 5}))

    def processar(self, aluno, item_id):
        justificativa = self.cleaned_data.get('justificativa')
        aluno.solicitar_quitacao_nada_consta(justificativa=justificativa, item_id=item_id)
