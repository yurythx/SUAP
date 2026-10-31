import hashlib
import time
from datetime import date, datetime

from django.contrib.auth.models import Group
from django.core.validators import URLValidator
from django.forms import ValidationError
from django.forms.models import inlineformset_factory
from django.conf import settings
from django.db.models import QuerySet

from centralservicos.models import GrupoAtendimento
from comum.models import Configuracao, User, UsuarioGrupo
from demandas.models import (
    AmbienteHomologacao,
    AnalistaDesenvolvedor,
    Anexos,
    AreaAtuacaoDemanda,
    Atualizacao,
    Demanda,
    DemandaPriorizacao,
    DoD,
    Especificacao,
    HistoricoSituacao,
    HistoricoVinculo,
    NotaInterna,
    Notificar,
    RevisaoEspecificacao,
    Situacao,
    SugestaoAnexo,
    SugestaoMelhoria,
    Tag,
    TagDemandantes,
    TipoDemanda,
)
from demandas.models import Entrega, StatusEntrega
from djtools import forms
from djtools.forms import ModelFormPlus
from djtools.forms.fields import DateFieldPlus
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import AutocompleteWidget
from djtools.templatetags.filters import in_group
from djtools.utils import get_apps_suap_as_choices, gitlab, somar_dias_uteis


class ConfiguracaoForm(forms.FormPlus):
    gitlab_url = forms.CharFieldPlus(label='URL do gitlab', required=False, initial='https://gitlab.ifrn.edu.br')
    gitlab_token = forms.CharFieldPlus(label='Token do gitlab', required=False)
    gitlab_suap_id = forms.CharFieldPlus(label='ID do projeto SUAP', required=False, initial='8')
    gitlab_api_version = forms.CharFieldPlus(label='Versão da API do Gitlab', required=False, initial='4')
    dominio_suapdevs = forms.CharFieldPlus(label='Domínio do Ambiente de Homologação', required=False, initial='suapdevs.ifrn.edu.br')
    bancos_suapdevs = forms.CharFieldPlus(
        label='Bancos de Template para Ambientes de Homologação', required=False, initial='behave suap_mascarado_pequeno'
    )
    qtd_demandas_prioritarias_por_area = forms.IntegerField(
        label='Quantidade de demandas prioritárias por área',
        min_value=DemandaPriorizacao.QTD_DEMANDAS_PRIORITARIAS_MIN,
        max_value=DemandaPriorizacao.QTD_DEMANDAS_PRIORITARIAS_MAX,
        help_text=f'De {DemandaPriorizacao.QTD_DEMANDAS_PRIORITARIAS_MIN} a {DemandaPriorizacao.QTD_DEMANDAS_PRIORITARIAS_MAX}. Será igual a {DemandaPriorizacao.QTD_DEMANDAS_PRIORITARIAS_DEFAULT} se não for informado.',
        required=False,
    )
    grupos_atendimento = forms.MultipleModelChoiceFieldPlus(
        GrupoAtendimento.objects,
        label='Grupos de atendimento',
        help_text='Grupos de atendimento da Central de Serviços a serem usados no Relatório de atividades reprimidas',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        grupos_atendimento = Configuracao.get_valor_por_chave(app='demandas', chave='grupos_atendimento')
        self.fields['grupos_atendimento'].initial = list(grupos_atendimento.split(',')) if grupos_atendimento else []


class ListarDemandaForm(forms.ModelForm):
    class Meta:
        model = Demanda
        exclude = ()


class ConfirmarComSenhaForm(forms.FormPlus):
    senha = forms.PasswordField()
    confirmar = forms.BooleanField(label='Confirma a operação')


class AreaAtuacaoDemandaForm(ModelFormPlus):
    demandantes = forms.MultipleModelChoiceFieldPlus(
        label='Demandantes',
        queryset=User.objects.filter(is_active=True),
        help_text='Vincule demandantes a essa Área de Atuação',
        required=False,
    )
    demandante_responsavel = forms.ModelChoiceFieldPlus(
        label='Demandante Responsável',
        queryset=User.objects.filter(is_active=True),
        help_text='Vincule um Demandante Responsável por essa Área de Atuação',
        required=True,
    )
    tags_relacionadas = forms.MultipleModelChoiceFieldPlus(
        label='Módulos',
        queryset=Tag.objects,
        help_text='Vincule módulos a essa Área de Atuação',
        required=False,
    )

    class Meta:
        model = AreaAtuacaoDemanda
        fields = (
            'area',
            'demandante_responsavel',
            'demandantes',
            'tags_relacionadas',
            'recebe_sugestoes_publico_aluno',
            'recebe_sugestoes_publico_servidor',
            'recebe_sugestoes_publico_prestador_servico',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not in_group(self.request.user, 'Coordenador de TI sistêmico'):
            self.fields['area'].widget = forms.HiddenInput()
            self.fields['demandante_responsavel'].widget = forms.HiddenInput()

    def clean(self, *args, **kwargs):
        recebe_sugestoes_de_alunos = self.cleaned_data.get('recebe_sugestoes_publico_aluno')
        recebe_sugestoes_de_servidores = self.cleaned_data.get('recebe_sugestoes_publico_servidor')
        recebe_sugestoes_de_prestadores = self.cleaned_data.get('recebe_sugestoes_publico_prestador_servico')

        recebe_sugestoes = recebe_sugestoes_de_alunos or recebe_sugestoes_de_servidores or recebe_sugestoes_de_prestadores

        if recebe_sugestoes:
            tags_relacionadas = self.cleaned_data.get('tags_relacionadas')

            if tags_relacionadas:
                tags_ja_selecionadas = {}  # {tag: [area, area, ...]}

                for tag in tags_relacionadas:
                    tags_ja_selecionadas.update({tag: []})

                    for area in AreaAtuacaoDemanda.areas_recebem_sugestoes().exclude(id=self.instance.id).filter(tags_relacionadas=tag):
                        tags_ja_selecionadas[tag].append(area)

                    if not len(tags_ja_selecionadas[tag]):
                        del tags_ja_selecionadas[tag]

                if tags_ja_selecionadas:
                    self.add_error(None, 'Área de Atuação recebe sugestões de melhoria.')
                    self.add_error(
                        'tags_relacionadas',
                        ValidationError(
                            'Tags já selecionadas em outras Áreas de Atuação: {}'.format(
                                ', '.join(
                                    [
                                        '{} ({})'.format(tag, ', '.join(f'{area}' for area in tags_ja_selecionadas[tag]))
                                        for tag in tags_ja_selecionadas
                                    ]
                                )
                            )
                        ),
                    )
            else:
                self.add_error(None, 'Área de Atuação recebe sugestões de melhoria.')
                self.add_error(
                    'tags_relacionadas', ValidationError('Informe pelo menos uma Tag para ativar o recebimento de sugestões de melhorias.')
                )

        return self.cleaned_data


class DemandaForm(ModelFormPlus):
    dependencia = forms.ModelChoiceFieldPlus(
        label='Demanda Pré-requisito',
        help_text='O desenvolvimento desta demanda pode depender da conclusão de uma outra demanda (demanda pré-requisito).',
        queryset=Demanda.objects,
        required=False,
    )

    def save(self, *args, **kwargs):
        insert = not self.instance.pk
        notificar_alteracao = False

        atualizar_prioridades = False

        if insert:
            self.instance.data_atualizacao = date.today()
            atualizar_prioridades = True
        else:
            demanda = Demanda.objects.get(pk=self.instance.pk)

            if demanda.descricao != self.instance.descricao:
                notificar_alteracao = True

            # Se a área de atuação da demanda mudar, a lista de prioridades deve ser atualizada após o Save da demanda
            if demanda.area != self.instance.area:
                demanda_anterior_area = demanda.area
                self.instance.prioridade = None
                atualizar_prioridades = True
            if self.cleaned_data.get('desenvolvedores'):
                novos_desenvolvedores = set(self.cleaned_data.get('desenvolvedores')) - set(self.instance.desenvolvedores.all())
                Notificar.desenvolvedores_vinculados_a_demanda(self.instance, novos_desenvolvedores, self.request.user)
            if self.cleaned_data.get('analistas'):
                novos_analistas = set(self.cleaned_data.get('analistas')) - set(self.instance.analistas.all())
                Notificar.analistas_vinculados_a_demanda(self.instance, novos_analistas, self.request.user)

        users = self.cleaned_data.get('interessados').all() | self.cleaned_data.get('observadores').all()
        group = Group.objects.get(name='Visualizador de Demandas')
        for user in users.distinct():
            if not UsuarioGrupo.objects.filter(user=user, group=group).exists():
                UsuarioGrupo.objects.get_or_create(group=group, user=user)

        retorno = super().save(commit=True)
        if insert:
            HistoricoSituacao.objects.create(demanda=self.instance, usuario=self.request.user, situacao=self.instance.situacao)
        if atualizar_prioridades:
            if not insert and demanda_anterior_area:
                Demanda.atualizar_prioridades(demanda_anterior_area, self.request.user)
            Demanda.atualizar_prioridades(self.instance.area, self.request.user)
            retorno = Demanda.objects.get(pk=retorno.pk)

        if notificar_alteracao:
            Notificar.alteracao_demanda(self.instance)

        return retorno

    def save_m2m(self):
        pass

    def clean(self, *args, **kwargs):
        clean = super().clean(*args, **kwargs)

        privada = clean.get('privada')
        observadores = clean.get('observadores')
        interessados = clean.get('interessados')

        if privada and (observadores or interessados):
            if observadores:
                self.add_error('observadores', 'Demandas privadas não podem ter observadores.')
            if interessados:
                self.add_error('interessados', 'Demandas privadas não podem ter interessados.')

        if clean.get('dependencia') and clean.get('area') and clean.get('dependencia').area != clean.get('area'):
            self.add_error('dependencia', 'A demanda pré-requisito deve ser ativa e da mesma área de atuação.')

        # valida a demanda (o restante)
        Demanda.validar(clean, self.instance)

        return clean


class DemandaAddForm(DemandaForm):
    tipo = forms.ChoiceField(
        label='Tipo',
        choices=TipoDemanda.TIPODEMANDA_CHOICES,
        widget=forms.RadioSelect,
        initial=TipoDemanda.MELHORIA,
    )
    demandantes = forms.MultipleModelChoiceFieldPlus(
        label='Demandantes',
        queryset=User.objects.filter(is_active=True),
        help_text='Vincule demandantes a esta demanda.',
        required=False,
    )
    interessados = forms.MultipleModelChoiceFieldPlus(
        queryset=User.objects.filter(is_active=True),
        label='Interessados',
        help_text='Vincule outros usuários a esta demanda. Eles poderão acompanhar as alterações e comentários desta demanda.',
        required=False,
    )
    observadores = forms.MultipleModelChoiceFieldPlus(
        queryset=User.objects.filter(is_active=True),
        label='Observadores',
        help_text='Vincule outros usuários a esta demanda. Eles poderão acompanhar as alterações desta demanda.',
        required=False,
    )
    tags = forms.MultipleModelChoiceFieldPlus(
        queryset=Tag.objects,
        label='Módulos',
        help_text='Selecione uma área de atuação para visualizar os módulos disponíveis.',
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Demanda
        fields = (
            'area',
            'tipo',
            'titulo',
            'descricao',
            'prazo_legal',
            'privada',
            'tags',
            'demandantes',
            'interessados',
            'observadores',
            'consolidacao_sempre_visivel',
            'dependencia',
        )

    class Media:
        js = ('demandas/js/demanda_form.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['demandantes'].queryset = User.objects.filter(groups=Group.objects.get(name='Demandante'))
        tags_field = self.fields['tags']
        tags_field.queryset = Tag.objects.filter(ativa=True)
        area_qs = AreaAtuacaoDemanda.objects.filter(demandantes=self.request.user) | AreaAtuacaoDemanda.objects.filter(
            demandante_responsavel=self.request.user
        )
        if area_qs.exists():
            self.fields['area'].queryset = area_qs.distinct()
        eh_analista = in_group(self.request.user, 'Analista')
        if not eh_analista and 'consolidacao_sempre_visivel' in self.fields:
            del self.fields['consolidacao_sempre_visivel']

        if self.instance.pode_editar_dependencia:
            self.fields['dependencia'].queryset = self.instance.dependencia_demandas_choices
        else:
            self.fields['dependencia'].widget.readonly = True
            if not self.instance.eh_dependente:
                self.fields['dependencia'].widget.readonly_no_value_text = 'Nenhuma demanda pré-requisito foi selecionada.'

        # Filtrar tags por área de atuação quando área for selecionada
        if hasattr(self.instance, 'area') and self.instance.area:
            tags_field.queryset = self.instance.area.tags_relacionadas.filter(ativa=True)
        elif 'area' in self.data:
            try:
                area_id = int(self.data.get('area'))
                area_atuacao = AreaAtuacaoDemanda.objects.get(id=area_id)
                tags_field.queryset = area_atuacao.tags_relacionadas.filter(ativa=True)
            except ValueError, TypeError, AreaAtuacaoDemanda.DoesNotExist:
                pass
        else:
            # Sem área selecionada, não exibe nenhuma tag para evitar piscar toda a lista
            tags_field.queryset = Tag.objects.none()


class AlterarUsuarioDemandaForm(ModelFormPlus):
    demandantes = forms.MultipleModelChoiceFieldPlus(
        label='Demandantes',
        queryset=User.objects,
        help_text='Vincule demandantes a esta demanda.',
        required=False,
    )
    interessados = forms.MultipleModelChoiceFieldPlus(
        label='Interessados',
        queryset=User.objects,
        help_text='Vincule outros usuários a esta demanda. Eles poderão acompanhar as alterações e comentários desta demanda.',
        required=False,
    )
    observadores = forms.MultipleModelChoiceFieldPlus(
        queryset=User.objects,
        label='Observadores',
        help_text='Vincule outros usuários a esta demanda. Eles poderão acompanhar as alterações desta demanda.',
        required=False,
    )
    analistas = forms.MultipleModelChoiceFieldPlus(
        label='Analistas', queryset=User.objects, help_text='Vincule usuários analistas desta demanda.', required=False
    )

    class Meta:
        model = Demanda
        fields = ('demandantes', 'interessados', 'observadores', 'analistas')

    def __delete_unnecessary_fields(self):
        campos = list(self.fields)
        for field in campos:
            if field != self.tipo:
                del self.fields[field]

    def __init__(self, *args, **kwargs):
        self.tipo = kwargs.pop('tipo')
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

        if self.tipo == 'demandantes':
            self.fields['demandantes'].queryset = self.instance.area.demandantes.all()
        if self.tipo == 'interessados':
            self.fields['interessados'].queryset = User.objects.filter(is_active=True)
        if self.tipo == 'analistas':
            self.fields['analistas'].queryset = User.objects.filter(groups=Group.objects.get(name='Analista'), is_active=True)
        if self.tipo == 'observadores':
            self.fields['observadores'].queryset = User.objects.filter(is_active=True)

        self.__delete_unnecessary_fields()

        # Se a demanda já estiver em situação terminal e o usuário for superuser,
        # exibe um campo de comentário obrigatório para registrar o motivo da alteração
        try:
            from demandas.models import Situacao

            if self.instance and self.instance.situacao in Situacao.TERMINAL and getattr(self.user, 'is_superuser', False):
                from django import forms as _forms

                self.fields['comentario'] = _forms.CharField(label='Comentário (motivo da alteração)', widget=_forms.Textarea, required=True)
        except Exception:
            # em caso de erro ao importar modelos, não bloqueia funcionamento normal
            pass

    def clean(self):
        clean = super().clean()

        # valida a demanda
        Demanda.validar(clean, self.instance, self.tipo)

        return clean

    def save(self, commit=True):
        novos_usuarios = []
        usuarios_removidos = []
        if self.tipo == 'demandantes':
            self.papel = 'Demandante'
            novos_usuarios = set(self.cleaned_data.get('demandantes')) - set(self.instance.demandantes.all())
            usuarios_removidos = set(self.instance.demandantes.all()) - set(self.cleaned_data.get('demandantes'))
        elif self.tipo == 'interessados':
            self.papel = 'Interessado'
            novos_usuarios = set(self.cleaned_data.get('interessados')) - set(self.instance.interessados.all())
            usuarios_removidos = set(self.instance.interessados.all()) - set(self.cleaned_data.get('interessados'))
        elif self.tipo == 'analistas':
            self.papel = 'Analista'
            novos_usuarios = set(self.cleaned_data.get('analistas')) - set(self.instance.analistas.all())
            usuarios_removidos = set(self.instance.analistas.all()) - set(self.cleaned_data.get('analistas'))
        elif self.tipo == 'observadores':
            self.papel = 'Observador'
            novos_usuarios = set(self.cleaned_data.get('observadores')) - set(self.instance.observadores.all())
            usuarios_removidos = set(self.instance.observadores.all()) - set(self.cleaned_data.get('observadores'))

        save = super().save(commit)
        if novos_usuarios or usuarios_removidos:
            if self.papel in ['Analista', 'Demandante']:
                for usuario in novos_usuarios:
                    HistoricoVinculo.objects.create(
                        demanda=self.instance, usuario=self.user, acao=f'{usuario} foi atribuído ao papel de {self.papel}'
                    )
                for usuario in usuarios_removidos:
                    HistoricoVinculo.objects.create(demanda=self.instance, usuario=self.user, acao=f'{usuario} foi removido do papel de {self.papel}')
            if novos_usuarios:
                Notificar.usuarios_vinculados_a_demanda(self.instance, novos_usuarios, self.user, self.papel)
            if usuarios_removidos:
                Notificar.usuarios_desvinculados_a_demanda(self.instance, usuarios_removidos, self.user, self.papel)

        # Se foi fornecido comentário (p.ex. edição por superuser em demanda terminal), registra como comentário da demanda
        comentario = self.cleaned_data.get('comentario') if hasattr(self, 'cleaned_data') else None
        if comentario:
            try:
                from demandas.utils import adicionar_comentario

                adicionar_comentario(usuario=self.user, mensagem=f'Alteração pós-finalização: {comentario}', demanda=self.instance)
            except Exception:
                # não falhar a operação principal se por algum motivo não conseguir salvar comentário
                pass

        return save


class DemandaChangeForm(DemandaForm):
    tipo = forms.ChoiceField(
        label='Tipo',
        choices=TipoDemanda.TIPODEMANDA_CHOICES,
        widget=forms.RadioSelect,
        initial=TipoDemanda.MELHORIA,
    )
    demandantes = forms.MultipleModelChoiceFieldPlus(
        label='Demandantes', queryset=User.objects, help_text='Vincule demandantes a esta demanda.', required=False
    )
    interessados = forms.MultipleModelChoiceFieldPlus(
        label='Interessados',
        queryset=User.objects,
        help_text='Vincule outros usuários a esta demanda. Eles poderão acompanhar as alterações e comentários desta demanda.',
        required=False,
    )
    observadores = forms.MultipleModelChoiceFieldPlus(
        queryset=User.objects.filter(is_active=True),
        label='Observadores',
        help_text='Vincule outros usuários a esta demanda. Eles poderão acompanhar as alterações desta demanda.',
        required=False,
    )
    analistas = forms.MultipleModelChoiceFieldPlus(
        label='Analistas', queryset=User.objects, help_text='Vincule usuários analistas desta demanda.', required=False
    )
    tags = forms.MultipleModelChoiceFieldPlus(
        queryset=Tag.objects,
        label='Módulos',
        help_text='Selecione uma área de atuação para visualizar os módulos disponíveis.',
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Demanda
        exclude = ('aberto_em', 'situacao', 'especificacao_tecnica')

    class Media:
        js = ('demandas/js/demanda_form.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Definir valor default para o campo Tipo em novos registros
        if not self.instance.pk:
            self.initial['tipo'] = TipoDemanda.MELHORIA

        tags_field = self.fields['tags']
        tags_field.queryset = Tag.objects.filter(ativa=True)
        self.fields['demandantes'].queryset = User.objects.filter(groups=Group.objects.get(name='Demandante'))
        self.fields['interessados'].queryset = User.objects.filter(is_active=True)
        self.fields['analistas'].queryset = User.objects.filter(groups=Group.objects.get(name='Analista'), is_active=True)
        if 'id_repositorio' in self.fields:
            self.fields['id_repositorio'].required = False
        eh_analista = in_group(self.request.user, 'Analista')
        if not eh_analista and 'consolidacao_sempre_visivel' in self.fields:
            del self.fields['consolidacao_sempre_visivel']

        if self.instance.pode_editar_dependencia:
            self.fields['dependencia'].queryset = self.instance.dependencia_demandas_choices
        else:
            self.fields['dependencia'].widget.readonly = True
            if not self.instance.eh_dependente:
                self.fields['dependencia'].widget.readonly_no_value_text = 'Nenhuma demanda pré-requisito foi selecionada.'

        # Filtra tags de acordo com a área enviada no formulário ou, em último caso, da instância existente
        area_id = self.data.get('area')
        if not area_id:
            area_id = getattr(self.instance, 'area_id', None)

        if area_id:
            try:
                area_atuacao = AreaAtuacaoDemanda.objects.get(id=int(area_id))
                tags_field.queryset = area_atuacao.tags_relacionadas.filter(ativa=True)
            except ValueError, TypeError, AreaAtuacaoDemanda.DoesNotExist:
                pass
        else:
            # Sem área selecionada, não mostrar nenhuma tag
            tags_field.queryset = Tag.objects.none()

    def clean_demandantes(self):
        data = self.cleaned_data['demandantes']
        if not data:
            raise forms.ValidationError('A demanda deve ter pelo menos um demandante.')
        return data


class DoDForm(forms.ModelForm):
    descricao = forms.CharFieldPlus(label='Descrição', required=True, help_text='Forneça uma descrição sucinta da demanda.')
    detalhamento = forms.CharFieldPlus(
        label='Detalhamento',
        required=False,
        widget=forms.Textarea(),
        help_text='Forneça uma descrição detalhada das mudanças/funcionalidades implementadas nesta demanda',
    )
    grupos_envolvidos = forms.MultipleModelChoiceFieldPlus(Group.objects, label='Grupos de Usuários Relacionados', required=False)
    envolvidos = forms.CharField(label='Grupos de Usuários Relacionados/Novos Grupos de Usuários', required=False, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.eh_demanda_antiga:
            del self.fields['grupos_envolvidos']
            self.fields['envolvidos'].label = 'Grupos de Usuários Relacionados'
        else:
            self.fields['envolvidos'].label = 'Novos Grupos de Usuários'

    class Meta:
        model = DoD
        fields = ('descricao', 'detalhamento', 'grupos_envolvidos', 'envolvidos')


class RevisaoEspecificacaoForm(forms.ModelForm):
    atividades = TinyMCEFormField(label='Atividade(s)')

    class Meta:
        model = RevisaoEspecificacao
        fields = ('nome', 'atividades')

    def __init__(self, *args, **kwargs):
        dod = kwargs.pop('dod', None)
        especificacao = kwargs.pop('especificacao', None)
        super().__init__(*args, **kwargs)
        if especificacao:
            self.instance.especificacao = especificacao
            self.instance.dod = especificacao.dod
            self.initial['nome'] = especificacao.nome
            self.initial['atividades'] = especificacao.atividades
        elif dod:
            self.instance.dod = dod


class EspecificacaoForm(forms.ModelForm):
    atividades = TinyMCEFormField(label='Atividade(s)')

    class Meta:
        model = Especificacao
        fields = ('nome', 'atividades', 'ordem')

    def __init__(self, *args, **kwargs):
        self.dod = kwargs.pop('dod')

        super().__init__(*args, **kwargs)

        if self.instance.dod_id is None:
            self.instance.dod = self.dod

        if self.instance.id is None:
            self.initial['ordem'] = Especificacao.objects.filter(dod_id=self.dod.id).order_by('ordem').count() + 1

    def save(self, commit=True):
        if commit:
            save = super().save()
            if save:
                self.dod.atualizar_ordens(self.instance)
            return save


class EspecificacaoTecnicaForm(forms.ModelForm):
    especificacao_tecnica = TinyMCEFormField(label='Especificação Técnica')

    class Meta:
        model = Demanda
        fields = ('especificacao_tecnica',)


class GerarDemandaSugestaoMelhoriaForm(forms.ModelForm):
    demandantes = forms.MultipleModelChoiceFieldPlus(
        label='Demandantes',
        queryset=User.objects.filter(is_active=True),
        help_text='Vincule demandantes a essa demanda',
    )
    interessados = forms.MultipleModelChoiceFieldPlus(
        label='Interessados',
        queryset=User.objects.filter(is_active=True),
        help_text='Vincule interessados a essa demanda',
    )
    tags = forms.MultipleModelChoiceFieldPlus(
        queryset=Tag.objects,
        label='Tags',
        help_text='Vincule tags a esta demanda.',
        required=True,
    )

    class Meta:
        model = Demanda
        fields = ('area', 'titulo', 'descricao', 'demandantes', 'interessados', 'tags')

    def __init__(self, *args, **kwargs):
        self._area = kwargs.pop('area')
        self._titulo = kwargs.pop('titulo')
        self._descricao = kwargs.pop('descricao')
        self._demandantes = kwargs.pop('demandantes')
        self._interessados = kwargs.pop('interessados')
        self._tags = kwargs.pop('tags')

        super().__init__(*args, **kwargs)
        self.fields['tags'].queryset = Tag.objects.filter(ativa=True)
        self.fields['area'].initial = self._area
        self.fields['titulo'].initial = self._titulo
        self.fields['descricao'].initial = self._descricao
        self.fields['demandantes'].initial = self._demandantes
        self.fields['interessados'].initial = self._interessados
        self.fields['tags'].initial = self._tags

    def clean(self):
        clean = super().clean()

        # valida a demanda
        Demanda.validar(clean, self.instance)

        return clean


def SituacaoAlterarFormFactory(situacao, analistas_demanda, branch):
    hoje = date.today()

    situacao_form_factory = 'default'

    comentario = forms.CharField(
        label='Comentário', required=situacao == Situacao.ESTADO_ABERTO, widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'})
    )
    data_conclusao = DateFieldPlus(label='Conclusão', required=True, help_text='Informe a Data de Conclusão da etapa anterior', initial=hoje)
    data_previsao = DateFieldPlus(label='Previsão', required=True, help_text='Informe a Data de Previsão para conclusão desta etapa')
    analistas = forms.MultipleModelChoiceFieldPlus(
        label='Analistas',
        queryset=User.objects.filter(groups=Group.objects.get(name='Analista'), is_active=True),
        help_text='Vincule usuários analistas desta demanda.',
        required=True,
        initial=analistas_demanda,
    )
    id_merge_request = forms.IntegerFieldPlus(label='ID Merge-request', required=False)

    branch = forms.CharFieldPlus(
        label='Nome da branch',
        required=False,
        initial=branch,
        help_text='Ao informar o nome da branch, o SUAP criará o merge request assim que a demanda for homologada.',
    )

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'comentario',
                    'analistas',
                    'data_conclusao',
                    'data_previsao',
                    'id_merge_request',
                    'branch',
                )
            },
        ),
    )

    base_fields = {
        Situacao.ESTADO_ABERTO: {'comentario': comentario},
        Situacao.ESTADO_EM_NEGOCIACAO: {'comentario': comentario, 'analistas': analistas},
        Situacao.ESTADO_EM_ANALISE: {'comentario': comentario, 'data_previsao': data_previsao},
        Situacao.ESTADO_APROVADO: {'comentario': comentario},
        Situacao.ESTADO_EM_DESENVOLVIMENTO: {'comentario': comentario, 'data_previsao': data_previsao},
        Situacao.ESTADO_CANCELADO: {'comentario': comentario},
        Situacao.ESTADO_SUSPENSO: {'comentario': comentario},
        Situacao.ESTADO_CONCLUIDO: {'comentario': comentario, 'data_conclusao': data_conclusao},
        Situacao.ESTADO_EM_IMPLANTACAO: {'comentario': comentario, 'data_previsao': data_previsao, 'id_merge_request': id_merge_request},
        'default': {'comentario': comentario, 'data_conclusao': data_conclusao, 'data_previsao': data_previsao},
    }

    if situacao in base_fields:
        situacao_form_factory = situacao

    def clean(self, *args, **kwargs):
        data_previsao = self.cleaned_data.get('data_previsao')
        data_conclusao = self.cleaned_data.get('data_conclusao')
        if data_previsao and data_conclusao:
            if data_previsao < data_conclusao:
                self.add_error('data_conclusao', 'A Data de Previsão não pode ser menor que a última Data de Conclusão.')

        branch = self.cleaned_data.get('branch')
        if branch and not Demanda.branch_existe(branch):
            self.add_error('branch', 'A branch informada não existe no projeto SUAP.')

        return self.cleaned_data

    return type(
        'SituacaoAlterarForm',
        (forms.BaseForm,),
        {'base_fields': base_fields[situacao_form_factory], 'fieldsets': fieldsets, 'METHOD': 'POST', 'clean': clean},
    )


class DataPrevisaoAlterarForm(forms.FormPlus):
    comentario = forms.CharField(
        label='Comentário',
        required=True,
        widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}),
        help_text='Justifique a edição da Data de Previsão desta etapa. Este comentário será visualizado por todos os interessados da demanda.',
    )
    data_previsao = DateFieldPlus(label='Previsão', required=True, help_text='Informe a Data de Previsão para conclusão desta etapa')

    fieldsets = (('Alterar Data de Previsão da Etapa', {'fields': ('data_previsao', 'comentario')}),)


class NotaInternaForm(forms.ModelForm):
    class Meta:
        model = NotaInterna
        fields = ('nota',)

    def __init__(self, *args, **kwargs):
        demanda = kwargs.pop('demanda')
        super().__init__(*args, **kwargs)

        if not hasattr(self.instance, 'demanda'):
            self.instance.demanda = demanda

        if self.instance.demanda is None:
            self.instance.demanda = demanda


class AnexosForm(forms.ModelForm):
    class Meta:
        model = Anexos
        fields = ('arquivo',)

    def __init__(self, *args, **kwargs):
        usuario = kwargs.pop('usuario')
        demanda = kwargs.pop('demanda')

        super().__init__(*args, **kwargs)
        self.fields['arquivo'].required = True

        self.instance.usuario = usuario
        self.instance.demanda = demanda


class DashboardForm(forms.FormPlus):
    inicio = forms.DateFieldPlus(label='Data Inicial', required=False)
    final = forms.DateFieldPlus(label='Data Final', required=False)
    tag = forms.ModelChoiceField(label='Tag', queryset=Tag.objects, required=False)


class AcompanhamentoForm(forms.FormPlus):
    inicio = forms.DateFieldPlus(label='Data Inicial', required=True)
    fim = forms.DateFieldPlus(label='Data Final', required=True)
    area = forms.ModelChoiceField(
        label='Área de atuação',
        queryset=AreaAtuacaoDemanda.objects.all(),
        widget=AutocompleteWidget(search_fields=AreaAtuacaoDemanda.SEARCH_FIELDS),
        required=False,
    )

    METHOD = 'GET'


class RelatorioForm(forms.FormPlus):
    inicio = forms.DateFieldPlus(label='Data Inicial', required=True)
    final = forms.DateFieldPlus(label='Data Final', required=True)


class AtualizacaoForm(forms.ModelFormPlus):
    tags = forms.MultipleModelChoiceFieldPlus(
        queryset=Tag.objects,
        label='Tags',
        help_text='Vincule tags a esta demanda.',
        required=True,
    )
    grupos = forms.MultipleModelChoiceFieldPlus(Group.objects, label='Grupos Envolvidos', required=False)
    demanda = forms.ModelChoiceField(
        queryset=Demanda.objects.filter(situacao=Situacao.ESTADO_CONCLUIDO),
        widget=AutocompleteWidget(search_fields=Demanda.SEARCH_FIELDS),
        label='Demanda Vinculada',
        required=False,
    )
    responsaveis = forms.MultipleModelChoiceFieldPlus(
        label='Responsáveis',
        queryset=User.objects,
        help_text='Vincule usuários desenvolvedores desta atualização.',
        required=False,
    )

    class Meta:
        model = Atualizacao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data'].initial = datetime.now().date()
        self.fields['responsaveis'].queryset = User.objects.filter(groups=Group.objects.get(name='Analista'), is_active=True)
        self.fields['tags'].queryset = Tag.objects.filter(ativa=True)


class NovaPrioridadeDemandaForm(forms.FormPlus):
    nova_prioridade = forms.IntegerField(min_value=0, required=True)


# ------------------
sugestao_melhoria_formfield_interessados = forms.MultipleModelChoiceFieldPlus(
    label='Interessados', queryset=User.objects.filter(is_active=True), required=False
)

sugestao_melhoria_formfield_outros_interessados = forms.MultipleModelChoiceFieldPlus(
    label='Outros Interessados',
    queryset=User.objects.filter(is_active=True),
    required=False,
    help_text='Você é o Requisitante desta Sugestão de Melhoria, logo, não precisa se colocar como Interessado.',
)


def BuscarModuloSugestaoMelhoriaFormFactory(modulos: QuerySet[Tag]) -> type[forms.BaseForm]:
    fields = {
        'modulo': forms.ModelChoiceFieldPlus(
            queryset=modulos,
            widget=AutocompleteWidget(search_fields=Tag.SEARCH_FIELDS, submit_on_select=True),
            label='Busque um módulo:',
            required=False,
        )
    }

    fieldsets = ((None, {'fields': ('modulo',)}),)

    return type('BuscarModuloSugestaoMelhoriaForm', (forms.BaseForm,), {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'POST'})


class SugestaoMelhoriaAddForm(forms.ModelFormPlus):
    requisitante_info = forms.CharField(
        label='Requisitante',
    )
    area_atuacao_info = forms.CharField(
        label='Área de Atuação',
    )
    tags_info = forms.CharField(
        label='Módulo',
    )
    interessados = sugestao_melhoria_formfield_outros_interessados

    class Meta:
        model = SugestaoMelhoria
        fields = ('requisitante_info', 'area_atuacao_info', 'tags_info', 'titulo', 'descricao', 'interessados')

    def __init__(self, *args, **kwargs):
        self._area_atuacao = kwargs.pop('area_atuacao')
        self._tags = kwargs.pop('tags')
        self._user_requisitante = kwargs.pop('user_requisitante')

        assert self._area_atuacao
        assert self._tags
        assert self._user_requisitante

        super().__init__(*args, **kwargs)

        field_requisitante_info = self.fields['requisitante_info']
        field_requisitante_info.initial = f'{self._user_requisitante}'
        field_requisitante_info.widget.attrs['readonly'] = 'readonly'

        field_area_atuacao_info = self.fields['area_atuacao_info']
        field_area_atuacao_info.initial = f'{self._area_atuacao}'
        field_area_atuacao_info.widget.attrs['readonly'] = 'readonly'

        field_tags_info = self.fields['tags_info']
        field_tags_info.initial = ', '.join(f'{_}' for _ in self._tags)
        field_tags_info.widget.attrs['readonly'] = 'readonly'

        self.fields['interessados'].queryset = self.fields['interessados'].queryset.exclude(pk=self._user_requisitante.pk)

    def save(self, commit=True):
        self.instance.area_atuacao = self._area_atuacao
        self.instance.requisitante = self._user_requisitante
        save = super().save(commit)
        if save:
            self.instance.tags.set(self._tags)
        return save


class SugestaoMelhoriaEdicaoBasicaForm(forms.ModelFormPlus):
    interessados = sugestao_melhoria_formfield_interessados

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user == self.instance.requisitante:
            self.fields['interessados'].help_text = sugestao_melhoria_formfield_outros_interessados.help_text
            self.fields['interessados'].queryset = self.fields['interessados'].queryset.exclude(pk=self.request.user.pk)

    class Meta:
        model = SugestaoMelhoria
        fields = (
            'titulo',
            'descricao',
            'interessados',
        )


class SugestaoMelhoriaEdicaoCompletaForm(forms.ModelFormPlus):
    interessados = sugestao_melhoria_formfield_interessados
    modulo = forms.ModelChoiceFieldPlus(
        label='Módulo',
        queryset=Tag.objects,
    )
    responsavel = forms.ModelChoiceFieldPlus(label='Responsável', queryset=User.objects.filter(is_active=True), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['modulo'].initial = self.instance.tags.first().id
        self.fields['modulo'].queryset = self.instance.area_atuacao.tags_relacionadas
        self.fields['modulo'].help_text = f'Módulos de {self.instance.area_atuacao.area.nome}'
        self.fields['responsavel'].queryset = User.objects.filter(
            id__in=[demandante.id for demandante in self.instance.demandantes_area], is_active=True
        )
        if self.request.user == self.instance.requisitante:
            self.fields['interessados'].help_text = sugestao_melhoria_formfield_outros_interessados.help_text
            self.fields['interessados'].queryset = self.fields['interessados'].queryset.exclude(pk=self.request.user.pk)

    class Meta:
        model = SugestaoMelhoria
        fields = ('titulo', 'descricao', 'interessados', 'modulo', 'responsavel', 'situacao')


class SugestaoMelhoriaEdicaoAreaAtuacaoForm(forms.ModelFormPlus):
    class Meta:
        model = SugestaoMelhoria
        fields = ('area_atuacao',)


SugestaoAnexoFormset = inlineformset_factory(
    SugestaoMelhoria, SugestaoAnexo, extra=3, exclude=['sugestao', 'anexado_em', 'anexado_por'], can_delete=False
)


class SugestaoAnexoForm(forms.ModelForm):
    class Meta:
        model = SugestaoAnexo
        fields = ['descricao', 'anexo']


class AmbienteHomologacaoForm(forms.ModelFormPlus):
    banco = forms.ChoiceField(label='Banco', choices=[])

    class Meta:
        model = AmbienteHomologacao
        fields = 'criador', 'branch', 'banco', 'data_expiracao', 'senha'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bancos = Configuracao.get_valor_por_chave('demandas', 'bancos_suapdevs') or 'suap'
        self.fields['banco'].choices = [(x, x) for x in bancos.split()]
        self.fields['criador'].initial = AnalistaDesenvolvedor.objects.filter(usuario_id=self.request.user.id).first()
        self.fields['senha'].initial = self.sugestao_senha()

    def clean_branch(self):
        branch = self.cleaned_data['branch']
        if not settings.DEBUG and branch not in gitlab.list_branche_names(branch):
            raise forms.ValidationError('Branch inválida.')
        return branch

    def sugestao_senha(self):
        hash = hashlib.sha1()
        hash.update(str(time.time()).encode('utf-8'))
        return hash.hexdigest()[:6]


class ExecutarComandoForm(forms.FormPlus):
    comando = forms.CharFieldPlus(label='python manage.py')

    def clean_comando(self):
        raise forms.ValidationError('Funcionalidade ainda não implementada')


class SubstituirDemandanteForm(forms.FormPlus):
    demandantes = forms.MultipleModelChoiceFieldPlus(
        label='Demandantes', queryset=User.objects, help_text='Defina quais demandantes irão se vincular às demandas', required=True
    )
    remover = forms.BooleanField(label='Remover este demandante das demandas vinculadas', required=False)

    class Meta:
        fields = ('demandantes',)

    def __init__(self, *args, **kwargs):
        self._area_atuacao = kwargs.pop('area_atuacao')
        self._demandante = kwargs.pop('demandante')
        super().__init__(*args, **kwargs)
        self.fields['demandantes'].help_text = f'Defina quais demandantes irão se vincular às demandas de {self._demandante}.'
        demandantes_escopo_ids = [_.id for _ in self._area_atuacao.demandantes.exclude(pk=self._demandante.id)]
        if self._area_atuacao.demandante_responsavel:
            demandantes_escopo_ids.append(self._area_atuacao.demandante_responsavel.id)
        self.fields['demandantes'].queryset = User.objects.filter(is_active=True, id__in=demandantes_escopo_ids)

    def processar(self):
        remover = self.cleaned_data.get('remover')
        novos_demandantes = self.cleaned_data.get('demandantes')
        for demanda in Demanda.objects.ativas().filter(demandantes__in=[self._demandante]):
            for usuario in novos_demandantes:
                if not demanda.demandantes.filter(id=usuario.id).exists():
                    demanda.demandantes.add(usuario)
            if remover:
                demanda.demandantes.remove(self._demandante)


class AreaAtuacaoGerenciarDemandantesForm(forms.FormPlus):
    demandantes = forms.MultipleModelChoiceFieldPlus(
        label='Demandantes', queryset=User.objects, help_text='Vincule demandantes à Tag (Módulo) selecionada', required=False
    )

    class Meta:
        fields = ('demandantes',)

    def __init__(self, *args, **kwargs):
        self._area_atuacao = kwargs.pop('area_atuacao')
        self._tag = kwargs.pop('tag')

        super().__init__(*args, **kwargs)

        demandantes_escopo_ids = [_.id for _ in self._area_atuacao.demandantes.all()]
        if self._area_atuacao.demandante_responsavel:
            demandantes_escopo_ids.append(self._area_atuacao.demandante_responsavel.id)

        self.fields['demandantes'].queryset = User.objects.filter(is_active=True, id__in=demandantes_escopo_ids)
        self.fields['demandantes'].initial = TagDemandantes.get_demandantes(self._tag)

    def save(self):
        return TagDemandantes.save_demandantes(self._tag, self.cleaned_data.get('demandantes', []))


class VincularIssueGitlabForm(forms.FormPlus):
    url = forms.CharFieldPlus(label='URL da Issue no Gitlab')

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance')
        url = kwargs.pop('url')
        super().__init__(*args, **kwargs)
        if url:
            self.initial['url'] = url

    def clean_url(self):
        url = self.cleaned_data.get('url')
        URLValidator()(url)
        return url

    def processar(self):
        url = self.cleaned_data.get('url')
        self.instance.vincular_issue_gitlab(url)


class MultipleChoiceAutocompleteNoRequiredField(forms.MultipleChoiceField):
    def __init__(self, *args, **kwargs):
        """Os parâmetros widget e required serão ignorados mesmo
        que passados para o construtor. Este field é sempre opcional
        e tem um específico widget."""
        if 'widget' in kwargs:
            kwargs.pop('widget')
        if 'required' in kwargs:
            kwargs.pop('required')
        super().__init__(widget=AutocompleteWidget(multiple=True), required=False, **kwargs)

    def validate(self, value):
        # O widget pode produzir um value = [''] que, nesse caso,
        # seria tratado como um valor inválido, porém trata-se de um
        # valor vazio e válido no contexto de um field opcional.
        if not self.required and value:
            if isinstance(value, list) and len(value) == 1 and not value[0]:
                value = []
        return super().validate(value)


class TagForm(forms.ModelFormPlus):
    apps_relacionadas = MultipleChoiceAutocompleteNoRequiredField(
        label='Apps relacionadas',
        choices=[*get_apps_suap_as_choices()],
        help_text='Vincule apps do SUAP à essa Tag.',
    )

    class Meta:
        model = Tag
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['apps_relacionadas'] = self.instance.apps_relacionadas_as_list

    def clean_apps_relacionadas(self):
        value = self.cleaned_data.get('apps_relacionadas')
        if value:
            return ','.join(value)
        return value or ''


# ─────────────────────────────────────────────────────────────────────────────
# EntregaForm — cadastro de nova entrega
# ─────────────────────────────────────────────────────────────────────────────


class EntregaForm(forms.ModelFormPlus):
    """Formulário para registrar uma nova entrega: ao salvar, a demanda vai para "Em homologação"."""

    especificacoes = forms.MultipleModelChoiceFieldPlus(
        label='Especificações entregues',
        queryset=Especificacao.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Selecione as especificações do DoD incluídas nesta entrega.',
    )

    class Meta:
        model = Entrega
        fields = [
            'titulo',
            'descricao',
            'notas',
            'ambiente_homologacao',
            'url_validacao',
            'senha_homologacao',
            'prazo_feedback',
            'conclui_demanda',
            'branch',
            'id_merge_request',
            'pipeline_id',
            'versionamento',
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'notas': forms.Textarea(attrs={'rows': 4}),
            'prazo_feedback': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'titulo': 'Título da entrega',
            'descricao': 'O que está sendo entregue',
            'notas': 'Notas para o demandante (o que testar, fluxos, dados de exemplo)',
            'prazo_feedback': 'Prazo para o demandante responder',
        }

    DIAS_UTEIS_PRAZO_HOMOLOGACAO = 5

    def __init__(self, *args, **kwargs):
        self.demanda = kwargs.pop('demanda')
        homologar = kwargs.pop('homologar', False)
        super().__init__(*args, **kwargs)
        self.instance.demanda = self.demanda

        self.fields['prazo_feedback'].required = True
        self.fields['prazo_feedback'].help_text = 'É também a previsão de conclusão da etapa "Em homologação".'

        # Filtra ambientes de homologação ativos
        self.fields['ambiente_homologacao'].queryset = AmbienteHomologacao.objects.filter(ativo=True)
        self.fields['ambiente_homologacao'].required = False

        # Campos opcionais de GitLab — collapse no template
        for campo in ['branch', 'id_merge_request', 'pipeline_id', 'versionamento']:
            self.fields[campo].required = False

        # Com especificações, quem decide se a aprovação conclui a demanda é a cobertura;
        # a marca "Conclui a demanda?" só existe para demanda sem especificações.
        especs = Especificacao.objects.filter(dod__demanda=self.demanda)
        if especs.exists():
            self.fields['especificacoes'].queryset = especs
            del self.fields['conclui_demanda']
        else:
            del self.fields['especificacoes']

        if homologar:
            self._preencher_para_homologar(especs)

    def _preencher_para_homologar(self, especs) -> None:
        """Atalho "Homologar": entrega tudo o que falta, de modo que quem entrega de uma vez só confirma o prazo."""
        self.initial['titulo'] = f'Homologação: {self.demanda.titulo}'[:250]
        self.initial['prazo_feedback'] = somar_dias_uteis(date.today(), self.DIAS_UTEIS_PRAZO_HOMOLOGACAO).isoformat()
        if 'especificacoes' in self.fields:
            self.initial['especificacoes'] = list(especs.exclude(entregas__status=StatusEntrega.APROVADA).values_list('pk', flat=True))
        else:
            self.initial['conclui_demanda'] = True

    def clean_branch(self):
        branch = self.cleaned_data.get('branch')
        if branch and not Demanda.branch_existe(branch):
            raise forms.ValidationError('A branch informada não existe no projeto SUAP.')
        return branch


# ─────────────────────────────────────────────────────────────────────────────
# AprovarEntregaForm
# ─────────────────────────────────────────────────────────────────────────────


class AprovarEntregaForm(forms.Form):
    """Confirmação de aprovação de entrega."""

    observacao = forms.CharField(
        label='Observação (opcional)',
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ReprovarEntregaForm
# ─────────────────────────────────────────────────────────────────────────────


class ReprovarEntregaForm(forms.Form):
    """Reprovação de entrega com motivo obrigatório."""

    motivo = forms.CharField(
        label='Motivo da reprovação',
        widget=forms.Textarea(attrs={'rows': 3}),
        required=True,
        help_text='Descreva o que precisa ser corrigido para a próxima entrega.',
    )


# ─────────────────────────────────────────────────────────────────────────────
# SubdemandaForm — criação de sub-demanda
# ─────────────────────────────────────────────────────────────────────────────


class SubdemandaAddForm(DemandaAddForm):
    titulo = forms.CharField(label='Título da sub-demanda', max_length=250)
    descricao = forms.CharField(
        label='Descrição',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    tipo = forms.ChoiceField(
        label='Tipo',
        choices=TipoDemanda.TIPODEMANDA_CHOICES,
    )

    def __init__(self, *args, pai=None, **kwargs):
        super().__init__(*args, **kwargs)

        if pai is None:
            return

        # ── Fixo: área herdada sem edição ────────────────────────────────────
        area_field = self.fields['area']
        area_field.initial = pai.area_id
        area_field.queryset = pai.area.__class__.objects.filter(pk=pai.area_id)
        area_field.widget.attrs['disabled'] = True
        area_field.help_text = f'Herdada da demanda pai: {pai.area}'

        # ── Herdados como default, editáveis ─────────────────────────────────
        self.fields['tipo'].initial = pai.tipo
        self.fields['privada'].initial = pai.privada

        # Tags: filtradas pela área do pai, pré-selecionadas as do pai
        self.fields['tags'].queryset = pai.area.tags_relacionadas.filter(ativa=True)
        self.fields['tags'].initial = list(pai.tags.values_list('pk', flat=True))

        # Pessoas: pré-preenchidas do pai
        self.fields['demandantes'].initial = list(pai.demandantes.values_list('pk', flat=True))
        self.fields['interessados'].initial = list(pai.interessados.values_list('pk', flat=True))
        self.fields['observadores'].initial = list(pai.observadores.values_list('pk', flat=True))

        # ── Silencioso: consolidacao_sempre_visivel ───────────────────────────
        if 'consolidacao_sempre_visivel' in self.fields:
            self.fields['consolidacao_sempre_visivel'].initial = pai.consolidacao_sempre_visivel
            self.fields['consolidacao_sempre_visivel'].widget = forms.HiddenInput()

        # ── Dependência: restrita à área do pai ──────────────────────────────
        self.fields['dependencia'].queryset = Demanda.objects.filter(area=pai.area).ativas().exclude(pk=pai.pk)

    def clean_area(self):
        # Campo área está disabled no browser — não vem no POST.
        # Recuperamos da instância do pai via initial.
        area_qs = self.fields['area'].queryset
        return area_qs.first()
