from django.utils.text import slugify
from djtools import forms
from djtools.forms.fields.tinymce import TinyMCEFormField
from .models import TopicoDocumentoPDA, BaseDados, Organizacao, AvaliacaoBaseDados, RecursoDados
from .enums import ODS, FormatoRecurso, NotaAvaliacaoBaseDados, TipoVersao
from .services.espelho_csv import EspelhoIndisponivel, atualizar_espelho


class TopicoDocumentoPDAForm(forms.ModelFormPlus):
    conteudo = TinyMCEFormField(label='Conteúdo', required=False, help_text='Use o editor para formatar o texto conforme necessário.')

    class Meta:
        model = TopicoDocumentoPDA
        exclude = []


class OrganizacaoForm(forms.ModelFormPlus):
    titulo = forms.CharFieldPlus(
        label='Título',
        required=True,
        max_length=200,
        widget=forms.TextInput(
            attrs={
                'data-slug-target-id': 'id_nome',  # <- indica o campo slug alvo
            }
        ),
    )
    nome = forms.SlugField(
        label='Identificador',
        required=True,
        max_length=100,
        widget=forms.TextInput(attrs={'readonly': 'readonly'}),  # não editável
        help_text='Identificador único da organização no CKAN (gerado automaticamente a partir do título).',
    )

    class Meta:
        model = Organizacao
        exclude = []

    def clean(self):
        cleaned = super().clean()
        titulo = cleaned.get('titulo')
        nome = cleaned.get('nome')

        # Se não tiver nome ou se quiser sempre regerar a partir do título:
        if titulo and not nome:
            cleaned['nome'] = slugify(titulo)

        return cleaned


class BaseDadosForm(forms.ModelFormPlus):
    titulo = forms.CharFieldPlus(
        label='Título',
        required=True,
        max_length=200,
        widget=forms.TextInput(
            attrs={
                'data-slug-target-id': 'id_nome',  # <- indica o campo slug alvo
            }
        ),
    )
    nome = forms.SlugField(
        label='Identificador',
        required=True,
        max_length=120,
        widget=forms.TextInput(attrs={'readonly': 'readonly'}),  # não editável
        help_text='Slug único do conjunto de dados no CKAN (gerado automaticamente a partir do título).',
    )
    ods = forms.TypedMultipleChoiceField(
        label='ODS relacionados',
        required=False,
        coerce=int,
        choices=ODS.get_choices(),
        # O Plus gera `ul.checkboxes`, que o tema distribui em colunas; "Marcar todos" não faz sentido para ODS.
        widget=forms.CheckboxSelectMultiplePlus(disable_mark_all=True),
        help_text='Objetivos de Desenvolvimento Sustentável aos quais o conjunto se relaciona.',
    )

    class Meta:
        model = BaseDados
        exclude = []
        labels = {'extras': 'Extras livres (além do DCAT-BR)'}
        help_texts = {
            'extras': 'JSON apenas para o que não tem campo próprio nesta tela. Chave igual à de um campo do DCAT-BR é ignorada no envio.',
        }

    def clean_extras(self):
        """Os extras livres sobem ao CKAN como pares chave/valor: só um objeto JSON serve."""
        extras = self.cleaned_data.get('extras')
        if extras in (None, '', [], {}):
            return {}
        if not isinstance(extras, dict):
            raise forms.ValidationError(
                'Informe um objeto JSON de pares chave/valor, como {"fonte": "SUAP"}. '
                'Lista, como [{"key": ..., "value": ...}], é o formato interno do CKAN e não é aceita aqui.'
            )
        return extras

    def clean(self):
        cleaned = super().clean()
        titulo = cleaned.get('titulo')
        nome = cleaned.get('nome')

        # Se não tiver nome ou se quiser sempre regerar a partir do título:
        if titulo and not nome:
            cleaned['nome'] = slugify(titulo)

        return cleaned


class SelectAvaliacaoBaseForm(forms.Form):
    @staticmethod
    def factory_field_render_select(base_dados, criterio_matriz, soh_texto=False):
        field_name = f'nota_{base_dados.id}_{criterio_matriz.id}'
        field = forms.ChoiceField(
            choices=[('', '-- Selecione --'), *NotaAvaliacaoBaseDados.get_choices()],
            widget=forms.Select(attrs={'class': 'form-control'}),
        )

        # verificando se existe uma avaliação para esse choice
        a = AvaliacaoBaseDados.objects.filter(base_dados=base_dados, criterio_matriz=criterio_matriz).first()
        value = ''
        if a:
            value = a.nota
            if a.finalizado:
                field.widget.attrs.update({'disabled': 'disabled'})

        if soh_texto:
            return NotaAvaliacaoBaseDados.LABELS.get(value, '')
        return field.widget.render(field_name, value)


class CriarVersaoPDAForm(forms.FormPlus):
    tipo = forms.ChoiceField(
        label='Tipo de versão',
        choices=TipoVersao.get_choices(),
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    justificativa = forms.CharFieldPlus(
        max_length=2000,
        label='Justificativa da versão',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
    )

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo')
        justificativa = cleaned.get('justificativa')

        if not tipo:
            self.add_error('tipo', 'O campo "Tipo de versão" é obrigatório.')

        if not justificativa:
            self.add_error('justificativa', 'O campo "Justificativa" é obrigatório.')

        return cleaned

    def processar(self, pda):
        tipo = int(self.cleaned_data.get('tipo'))
        justificativa = self.cleaned_data.get('justificativa')
        #
        pda.gerar_versao(
            tipo=tipo,
            justificativa=justificativa,
        )


class RecursoDadosForm(forms.ModelFormPlus):
    """Formulário do recurso, com a opção de gerar o gêmeo em CSV."""

    gerar_csv = forms.BooleanField(
        label='Gerar também em CSV',
        required=False,
        help_text=(
            'Cria um recurso gêmeo em CSV com o mesmo conteúdo, mantido em dia sempre que este for atualizado. '
            'Desmarcar não remove um espelho já criado — para isso, apague o recurso CSV diretamente.'
        ),
    )

    class Meta:
        model = RecursoDados
        exclude = ['derivado_de']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.derivado_de_id:
            # Espelho não gera espelho: o campo fica visível para explicar, mas inerte.
            campo = self.fields['gerar_csv']
            campo.disabled = True
            campo.help_text = 'Este recurso já é o espelho CSV de outro — não há o que derivar dele.'
        elif self.instance.pk:
            self.fields['gerar_csv'].initial = self.instance.derivados.exists()

    def clean(self):
        dados = super().clean()
        if dados.get('gerar_csv') and dados.get('formato') != FormatoRecurso.JSON:
            self.add_error('gerar_csv', 'O espelho em CSV só faz sentido para um recurso JSON.')
        return dados

    def save(self, commit=True):
        recurso = super().save(commit)
        if commit:
            self.aviso_espelho = self.aplicar_espelho(recurso)
        return recurso

    def aplicar_espelho(self, recurso) -> str:
        """Cria ou atualiza o espelho quando pedido. Devolve o aviso quando não foi possível.

        Não levanta: o recurso em si é válido, e recusar o cadastro inteiro porque o conteúdo não
        tabula seria punir o certo pelo opcional. O admin transforma o aviso em mensagem.
        """
        if not self.cleaned_data.get('gerar_csv'):
            return ''
        try:
            atualizar_espelho(recurso)
        except EspelhoIndisponivel as erro:
            return f'O recurso foi salvo, mas o espelho em CSV não pôde ser gerado: {erro}'
        return ''
