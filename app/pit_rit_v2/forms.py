import io
from datetime import datetime
from django.conf import settings
from tinymce.widgets import TinyMCE
from django.core.files.storage import default_storage
from comum.models import Ano
from djtools import forms
from edu.models import Professor
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES
from pit_rit_v2.models import (
    AtividadeEnsino,
    AtividadeExtensao,
    AtividadeGestao,
    AtividadePesquisa,
    HistoricoReaberturaRelatorio,
    Parecer,
    PlanoIndividualTrabalhoV2,
)
from rh.models import Servidor


class PlanoIndividualTrabalhoForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalhoV2
        exclude = ('data_envio', 'avaliador', 'avaliador_relatorio', 'aprovado')

    # DADOS GERAIS
    ano_letivo = forms.ModelChoiceField(Ano.objects.filter(ano__gt=2018), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=PERIODO_LETIVO_CHOICES)

    professor = forms.ModelChoiceFieldPlus(Professor.objects, label='Professor')

    # ENSINO
    # Preparação e Manutenção ao Ensino
    ch_preparacao_manutencao_ensino = forms.IntegerField(label='Carga Horária')

    # Apoio ao Ensino
    ch_apoio_ensino = forms.IntegerField(label='Carga Horária')
    atividades_apoio_ensino = forms.ModelMultiplePopupChoiceField(AtividadeEnsino.objects.none(), label='Atividades', required=False)
    outras_atividades_apoio_ensino = forms.CharField(
        label='Outras Atividades',
        required=False,
        widget=forms.Textarea(),
        help_text='Informe outras atividades separadas por linha caso a atividade desejada não conste no rol de atividades acima.',
    )
    obs_apoio_ensino = forms.CharField(label='Observações', required=False, widget=forms.Textarea())

    # Programas ou Projetos de Ensino
    ch_programas_projetos_ensino = forms.IntegerField(label='Carga Horária')
    obs_programas_projetos_ensino = forms.CharField(label='Observações', required=False, widget=forms.Textarea())

    # Atendimento, Acompanhamento, Avaliação e Orientação de Alunos
    ch_orientacao_alunos = forms.IntegerField(label='Carga Horária')
    atividades_orientacao_alunos = forms.ModelMultiplePopupChoiceField(AtividadeEnsino.objects.none(), label='Atividades', required=False)
    outras_atividades_orientacao_alunos = forms.CharField(
        label='Outras Atividades',
        required=False,
        widget=forms.Textarea(),
        help_text='Informe outras atividades separadas por linha caso a atividade desejada não conste no rol de atividades acima.',
    )
    obs_orientacao_alunos = forms.CharField(label='Observações', required=False, widget=forms.Textarea())

    # Reuniões Pedagógicas, de Grupo e Afins
    ch_reunioes = forms.IntegerField(label='Carga Horária')
    atividades_reunioes = forms.ModelMultiplePopupChoiceField(AtividadeEnsino.objects.none(), label='Atividades', required=False)
    outras_atividades_reunioes = forms.CharField(
        label='Outras Atividades',
        required=False,
        widget=forms.Textarea(),
        help_text='Informe outras atividades separadas por linha caso a atividade desejada não conste no rol de atividades acima.',
    )
    obs_reunioes = forms.CharField(label='Observações', required=False, widget=forms.Textarea())

    # PESQUISA E INOVAÇÃO
    ch_pesquisa = forms.IntegerField(label='Carga Horária')
    atividades_pesquisa = forms.ModelMultiplePopupChoiceField(AtividadePesquisa.objects, label='Atividades', required=False)
    outras_atividades_pesquisa = forms.CharField(
        label='Outras Atividades',
        required=False,
        widget=forms.Textarea(),
        help_text='Informe outras atividades separadas por linha caso a atividade desejada não conste no rol de atividades acima.',
    )
    obs_pesquisa = forms.CharField(label='Observações', required=False, widget=forms.Textarea())

    # EXTENSÃO
    ch_extensao = forms.IntegerField(label='Carga Horária')
    atividades_extensao = forms.ModelMultiplePopupChoiceField(AtividadeExtensao.objects, label='Atividades', required=False)
    outras_atividades_extensao = forms.CharField(
        label='Outras Atividades',
        required=False,
        widget=forms.Textarea(),
        help_text='Informe outras atividades separadas por linha caso a atividade desejada não conste no rol de atividades acima.',
    )
    obs_extensao = forms.CharField(label='Observações', required=False, widget=forms.Textarea())

    # GESTÃO E REPRESENTAÇÃO INSTITUCIONAL
    ch_gestao = forms.IntegerField(label='Carga Horária')
    atividades_gestao = forms.ModelMultiplePopupChoiceField(AtividadeGestao.objects, label='Atividades', required=False)
    outras_atividades_gestao = forms.CharField(
        label='Outras Atividades',
        required=False,
        widget=forms.Textarea(),
        help_text='Informe outras atividades separadas por linha caso a atividade desejada não conste no rol de atividades acima.',
    )
    obs_gestao = forms.CharField(label='Observações', required=False, widget=forms.Textarea())

    fieldsets = (
        ('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'), 'professor')}),
        ('Preparação e Manutenção do Ensino', {'fields': ('ch_preparacao_manutencao_ensino',)}),
        ('Apoio ao Ensino', {'fields': ('ch_apoio_ensino', 'atividades_apoio_ensino', 'outras_atividades_apoio_ensino')}),
        ('Programas ou Projetos de Ensino', {'fields': ('ch_programas_projetos_ensino',)}),
        (
            'Atendimento, Acompanhamento, Avaliação e Orientação de Alunos',
            {'fields': ('ch_orientacao_alunos', 'atividades_orientacao_alunos', 'outras_atividades_orientacao_alunos')},
        ),
        ('Reuniões Pedagógicas, de Grupo e Afins', {'fields': ('ch_reunioes', 'atividades_reunioes', 'outras_atividades_reunioes')}),
        ('Pesquisa e Inovação', {'fields': ('ch_pesquisa', 'atividades_pesquisa', 'outras_atividades_pesquisa')}),
        ('Extensão', {'fields': ('ch_extensao', 'atividades_extensao', 'outras_atividades_extensao')}),
        ('Gestão e Representação Institucional', {'fields': ('ch_gestao', 'atividades_gestao', 'outras_atividades_gestao')}),
    )

    def clean_atividades(self, tipo):
        ch = self.cleaned_data.get(f'ch_{tipo}')
        atividades = self.cleaned_data.get(f'atividades_{tipo}')
        if ch and not atividades:
            raise forms.ValidationError(f'Informe as atividades através das quais você pretente cumprir {ch} horas semanais.')
        if atividades and not ch:
            raise forms.ValidationError('Informe a carga horária que você pretende cumprir para essa(s) atividade(s).')
        return atividades

    def clean_atividades_apoio_ensino(self):
        return self.clean_atividades('apoio_ensino')

    def clean_atividades_orientacao_alunos(self):
        return self.clean_atividades('orientacao_alunos')

    def clean_atividades_reunioes(self):
        return self.clean_atividades('reunioes')

    def clean_atividades_pesquisa(self):
        return self.clean_atividades('pesquisa')

    def clean_atividades_extensao(self):
        return self.clean_atividades('extensao')

    def clean_atividades_gestao(self):
        return self.clean_atividades('gestao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atividades_apoio_ensino'].queryset = AtividadeEnsino.objects.filter(subgrupo=2)
        self.fields['atividades_orientacao_alunos'].queryset = AtividadeEnsino.objects.filter(subgrupo=4)
        self.fields['atividades_reunioes'].queryset = AtividadeEnsino.objects.filter(subgrupo=5)


class EnviarPlanoForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalhoV2
        fields = ('avaliador',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avaliador'].queryset = Servidor.objects.ativos()
        self.fields['avaliador'].help_text = 'Servidor responsável pela avaliação ano/período do plano individual de trabalho'


class EntregarRelatorioForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalhoV2
        fields = ('avaliador_relatorio',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avaliador_relatorio'].queryset = Servidor.objects.ativos()
        self.fields['avaliador_relatorio'].help_text = 'Servidor responsável pela avaliação ano/período do relatório individual de trabalho'


class PlanoIndividualTrabalhoProfessorForm(PlanoIndividualTrabalhoForm):
    class Meta:
        model = PlanoIndividualTrabalhoV2
        exclude = (
            'data_envio',
            'avaliador',
            'avaliador_relatorio',
            'aprovado',
            'data_aprovacao',
            'relatorio_aprovado',
            'data_aprovacao_relatorio',
            'publicado',
            'responsavel_publicacao',
            'data_publicacao',
            'data_envio_relatorio',
            'obs_aulas',
            'arquivo_aulas',
            'obs_preparacao_manutencao_ensino',
            'arquivo_preparacao_manutencao_ensino',
            'obs_apoio_ensino',
            'obs_programas_projetos_ensino',
            'obs_orientacao_alunos',
            'obs_reunioes',
            'obs_pesquisa',
            'obs_extensao',
            'obs_gestao',
            'arquivo_apoio_ensino',
            'arquivo_programas_projetos_ensino',
            'arquivo_orientacao_alunos',
            'arquivo_reunioes',
            'arquivo_pesquisa',
            'arquivo_extensao',
            'arquivo_gestao',
        )

    fieldsets = PlanoIndividualTrabalhoForm.fieldsets

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in 'ano_letivo', 'periodo_letivo':
            self.fields[field_name].widget.attrs.update(readonly='readonly')
        self.fields['professor'].widget = forms.HiddenInput()
        for field_name in self.fields:
            if 'obs_' in field_name:
                self.fields[field_name].input = forms.HiddenInput()

    def clean_ch_preparacao_manutencao_ensino(self):
        value = self.cleaned_data['ch_preparacao_manutencao_ensino']
        ch_aulas = self.instance.get_cargas_horarias()[1]
        if value > ch_aulas:
            raise forms.ValidationError(f'A carga horária deve ser igual ou inferior a {ch_aulas} horas')
        return value


class RelatorioIndividualTrabalhoProfessorForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalhoV2
        fields = (
            'obs_aulas',
            'arquivo_aulas',
            'obs_preparacao_manutencao_ensino',
            'arquivo_preparacao_manutencao_ensino',
            'obs_apoio_ensino',
            'obs_programas_projetos_ensino',
            'obs_orientacao_alunos',
            'obs_reunioes',
            'obs_pesquisa',
            'obs_extensao',
            'obs_gestao',
            'arquivo_apoio_ensino',
            'arquivo_programas_projetos_ensino',
            'arquivo_orientacao_alunos',
            'arquivo_reunioes',
            'arquivo_pesquisa',
            'arquivo_extensao',
            'arquivo_gestao',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            if 'obs_' in field_name:
                self.fields[field_name].widget = TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'})
                self.fields[field_name].label = ''

        self.fieldsets = [('Aulas', {'fields': ('obs_aulas', 'arquivo_aulas')})]
        self.fieldsets.append(
            ('Preparação e Manutenção do Ensino', {'fields': ('obs_preparacao_manutencao_ensino', 'arquivo_preparacao_manutencao_ensino')})
        )
        self.fieldsets.append(('Apoio ao Ensino', {'fields': ('obs_apoio_ensino', 'arquivo_apoio_ensino')}))
        self.fieldsets.append(('Programas ou Projetos de Ensino', {'fields': ('obs_programas_projetos_ensino', 'arquivo_programas_projetos_ensino')}))
        self.fieldsets.append(
            ('Atendimento, Acompanhamento, Avaliação e Orientação de Alunos', {'fields': ('obs_orientacao_alunos', 'arquivo_orientacao_alunos')})
        )
        self.fieldsets.append(('Reuniões Pedagógicas, de Grupo e Afins', {'fields': ('obs_reunioes', 'arquivo_reunioes')}))
        self.fieldsets.append(('Pesquisa e Inovação', {'fields': ('obs_pesquisa', 'arquivo_pesquisa')}))
        self.fieldsets.append(('Extensão', {'fields': ('obs_extensao', 'arquivo_extensao')}))
        self.fieldsets.append(('Gestão e Representação Institucional', {'fields': ('obs_gestao', 'arquivo_gestao')}))


class ParecerForm(forms.ModelFormPlus):
    class Meta:
        model = Parecer
        fields = ('obs',)


class AprovarRelatorioForm(ParecerForm):
    responsavel_publicacao = forms.ModelChoiceFieldPlus(Servidor.objects.all(), label='Responsável pela Publicação')

    class Meta:
        model = Parecer
        fields = ('obs',)


class CriarPlanoIndividualTrabalhoForm(forms.FormPlus):
    ano_letivo = forms.ModelChoiceFieldPlus(Ano.objects, label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=PERIODO_LETIVO_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'pit_rit' in settings.INSTALLED_APPS:
            self.fields['ano_letivo'].queryset = Ano.objects.filter(ano__gte=PlanoIndividualTrabalhoV2.ANO_INICIO_APP)

    def clean(self):
        cleaned_data = super().clean()
        ano_letivo = cleaned_data.get('ano_letivo')
        periodo_letivo = cleaned_data.get('periodo_letivo')

        if ano_letivo and periodo_letivo:
            if 'pit_rit_v3' in settings.INSTALLED_APPS:
                from pit_rit_v3.models import PlanoIndividualTrabalhoV3

                if PlanoIndividualTrabalhoV3.modulo_ativo(ano_letivo.ano, int(periodo_letivo)):
                    self.add_error(None, 'A partir deste ano/período, os planos devem ser criados na nova versão do módulo (PIT/RIT V3).')

        return cleaned_data

    def processar(self, professor_id):
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        qs = PlanoIndividualTrabalhoV2.objects.filter(professor_id=professor_id, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
        if qs.exists():
            return qs.first()
        else:
            return PlanoIndividualTrabalhoV2.objects.create(professor_id=professor_id, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)


class ReabrirRelatorioForm(forms.FormPlus):
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea())

    def processar(self, pit, relatorio):
        justificativa = self.cleaned_data['justificativa']
        h = HistoricoReaberturaRelatorio.objects.create(pit=pit, justificativa=justificativa, data=datetime.now())
        h.relatorio = default_storage.save(f'rits/rit-{pit.id}.pdf', io.BytesIO(relatorio))
        h.save()
        pit.data_publicacao = None
        pit.responsavel_publicacao = None
        pit.publicado = None
        pit.data_aprovacao_relatorio = None
        pit.relatorio_aprovado = None
        pit.avaliador_relatorio = None
        pit.data_envio_relatorio = None
        pit.save()
