import datetime

from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.filters import format_, status
from djtools.templatetags.tags.utils import icon
from rh.models import UnidadeOrganizacional
from temp_rh2.forms import ClassificacaoModalidadeForm, CompeticoesDesportivasForm, ModalidadeDesportivaForm
from temp_rh2.models import (
    Categoria,
    ClassificacaoModalidade,
    CompeticaoDesportiva,
    InscricaoCompeticaoDesportiva,
    MaximoProvasModalidade,
    ModalidadeDesportiva,
    Prova,
    ResultadoModalidade,
)


class MaximoProvasPorModalidadeInline(admin.StackedInline):
    model = MaximoProvasModalidade
    fields = ('modalidade', 'maximo_provas')
    extra = 1


class CompeticaoDesportivaAdmin(ModelAdminPlus):
    list_filter = ('ano',)
    list_display = ('ano', 'nome')
    inlines = [MaximoProvasPorModalidadeInline]
    form = CompeticoesDesportivasForm
    fieldsets = (
        ('Competição', {'fields': ('nome', 'descricao', 'ano', 'uo')}),
        (
            'Configuração da Competição',
            {
                'fields': (
                    'modalidades',
                    'provas',
                    'max_modalidades_coletivas_por_inscricao',
                    'max_modalidades_por_inscricao',
                    'max_modalidades_individuais_por_inscricao',
                    'categorias',
                    'pode_escolher_tamanho_uniforme',
                )
            },
        ),
        (
            'Datas Importantes',
            {
                'fields': (
                    ('data_inicio_periodo_inscricoes', 'data_fim_periodo_inscricoes'),
                    ('data_inicio_periodo_validacao', 'data_fim_periodo_validacao'),
                    ('data_inicio_confirmacao_inscritos', 'data_fim_confirmacao_inscritos'),
                    ('data_inicio_reajustes', 'data_fim_reajustes'),
                    ('data_homologacao_inscricoes',),
                )
            },
        ),
        (
            'Datas Jogos',
            {'fields': (('data_inicio_periodo1_jogos', 'data_fim_periodo1_jogos'), ('data_inicio_periodo2_jogos', 'data_fim_periodo2_jogos'))},
        ),
    )


admin.site.register(CompeticaoDesportiva, CompeticaoDesportivaAdmin)


class ServidorUoFilter(admin.SimpleListFilter):
    title = 'Campus Servidor'
    parameter_name = 'uo_servidor'

    def lookups(self, request, model_admin):
        return UnidadeOrganizacional.objects.suap().all().values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            if UnidadeOrganizacional.objects.suap().filter(pk=self.value()).exists():
                return queryset.filter(servidor__setor__uo__id__exact=self.value())
            else:
                self.used_parameters.pop(self.parameter_name)
        return queryset


class ProvasIndividuaisFilter(admin.SimpleListFilter):
    title = 'Provas Individuais'
    parameter_name = 'prova'

    def lookups(self, request, model_admin):
        provas = Prova.objects.all()
        return [(d.id, f'{d.modalidade} - {d.nome}') for d in provas]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(provas=self.value())
        return queryset


class InscricaoCompeticaoDesportivaAdmin(ModelAdminPlus):
    list_filter = (
        'competicao_desportiva',
        'uo',
        ServidorUoFilter,
        'servidor__pessoa_fisica__sexo',
        'preferencia_camisa',
        'preferencia_short',
        'termo_pcd',
        'termo_recebimento_hospedagem',
        'modalidades',
        ProvasIndividuaisFilter,
        'categoria',
        'situacao',
    )
    list_display = (
        'competicao_desportiva',
        'get_servidor',
        'uo',
        'get_uo',
        'get_modalidades_inscritas',
        'categoria',
        'termo_pcd',
        'termo_recebimento_hospedagem',
        'get_situacao',
        'get_atestado',
        'get_acoes',
    )

    export_to_xls = True
    list_display_icons = True

    def get_atestado(self, obj):
        retorno = ''
        if obj.atestado_medico and InscricaoCompeticaoDesportiva.pode_ver_atestado_medico(self.request.user):
            retorno = icon('file', obj.atestado_medico.url, 'Atestado médico anexado')
        return retorno

    get_atestado.short_description = 'Atestado Médico'

    def get_servidor(self, obj):
        return mark_safe(f'{format_(obj.servidor)}')

    get_servidor.admin_order_field = 'servidor'
    get_servidor.short_description = 'Servidor'

    def get_modalidades_inscritas(self, obj):
        retorno = '<ul>'
        for modalidade in obj.modalidades.only('pk', 'nome'):
            if obj.provas.filter(modalidade_id=modalidade.pk).exists():
                retorno += f'<li class="has-child">{modalidade.nome}'
                retorno += '<ul>'
                for prova in obj.provas.filter(modalidade_id=modalidade.pk).values_list('nome', flat=True):
                    retorno += f'<li>{prova}</li>'
                retorno += '</ul>'
            else:
                retorno += f'<li>{modalidade}'
            retorno += '</li>'
        retorno += '</ul>'
        return mark_safe(retorno)

    get_modalidades_inscritas.short_description = 'Modalidades'

    def get_uo(self, obj):
        if obj.servidor.setor:
            return mark_safe(obj.servidor.setor.uo)
        return 'Sem campus'

    get_uo.admin_order_field = 'servidor__setor__uo'
    get_uo.short_description = 'Campus do Servidor'

    def get_situacao(self, obj):
        if obj.situacao:
            return mark_safe(status(obj.get_situacao_display()))
        return '-'

    get_situacao.admin_order_field = 'situacao'
    get_situacao.short_description = 'Situação'

    def get_acoes(self, obj):
        txt = ''
        usuario_logado = self.request.user
        servidor_logado = usuario_logado.get_relacionamento()
        hoje = datetime.date.today()
        campus_servidor_logado = None
        if servidor_logado.setor:
            campus_servidor_logado = servidor_logado.setor.uo
        if (
            usuario_logado.has_perm('temp_rh2.pode_validar_inscricaocompeticaodesportiva') and campus_servidor_logado == obj.uo
        ) or usuario_logado.has_perm('temp_rh2.change_inscricaocompeticaodesportiva'):
            if (obj.competicao_desportiva.data_inicio_periodo_validacao <= hoje <= obj.competicao_desportiva.data_fim_periodo_validacao) or (
                obj.competicao_desportiva.data_inicio_confirmacao_inscritos <= hoje <= obj.competicao_desportiva.data_fim_confirmacao_inscritos
            ):
                txt += f'<a class="btn popup" href="/temp_rh2/validar/{obj.pk}/">Avaliar</a>'
            elif (obj.competicao_desportiva.data_inicio_reajustes <= hoje <= obj.competicao_desportiva.data_fim_reajustes) or (
                hoje == obj.competicao_desportiva.data_homologacao_inscricoes
            ):
                txt += f'<a class="btn popup success" href="/temp_rh2/validar/{obj.pk}/">Homologar</a>'
        return mark_safe(txt)

    get_acoes.short_description = 'Opções'

    def get_export_to_xls(self):
        return self.request.user.has_perm('temp_rh2.add_competicaodesportiva')

    def to_xls(self, request, queryset, processo):
        rows = [[]]
        if request.user.has_perm('temp_rh2.add_competicaodesportiva'):
            header = [
                '#',
                'Competição',
                'Matrícula',
                'cpf',
                'Nome',
                'Data de Nascimento',
                'E-mail para contato',
                'Campus Lotado',
                'Campus Inscrito',
                'Sexo',
                'Tamanho da Camisa',
                'Tamanho do Short',
                'Deseja receber Hospedagem',
                'Situação',
                'Modalidades',
                'Provas de Atletismo',
                'Provas de Natação',
                'Provas Jogos Eletrônicos',
            ]

            rows = [header]
            queryset = queryset.select_related('servidor', 'uo').prefetch_related(
                'modalidades',
                'provas',
            )
            for idx, obj in enumerate(processo.iterate(queryset)):
                row = [
                    idx,
                    obj.competicao_desportiva,
                    obj.servidor.matricula,
                    obj.servidor.pessoa_fisica.cpf,
                    obj.servidor.pessoa_fisica.nome,
                    obj.servidor.pessoa_fisica.nascimento_data,
                    obj.servidor.email_institucional,
                    self.get_uo(obj),
                    obj.uo,
                    obj.servidor.pessoa_fisica.sexo,
                    obj.get_preferencia_camisa_display(),
                    obj.get_preferencia_short_display(),
                    'Sim' if obj.termo_pcd else 'Não',
                    'Sim' if obj.termo_recebimento_hospedagem else 'Não',
                    obj.get_situacao_display(),
                    ', '.join(obj.modalidades.all().values_list('nome', flat=True)),
                    ', '.join(obj.provas.all().values_list('nome', flat=True)),
                ]
                rows.append(row)
        return rows


admin.site.register(InscricaoCompeticaoDesportiva, InscricaoCompeticaoDesportivaAdmin)


class ProvaInline(admin.StackedInline):
    model = Prova
    fields = ('nome', 'ativa')
    extra = 1

    def has_delete_permission(self, request, obj):
        tem_permissao_delete = super().has_delete_permission(request, obj)
        tem_inscricao_na_modalidade = InscricaoCompeticaoDesportiva.objects.filter(provas__modalidade=obj).exists()
        return tem_permissao_delete and not tem_inscricao_na_modalidade


class ModalidadeDesportivaAdmin(ModelAdminPlus):
    search_fields = ('nome',)
    list_filter = ('tipo', 'sexo')
    list_display = ('nome', 'tipo', 'sexo', 'get_provas')
    list_display_icons = True
    inlines = [ProvaInline]
    form = ModalidadeDesportivaForm

    def get_provas(self, obj):
        retorno = '-'
        if obj.prova_set.all().exists():
            retorno = ', '.join([prova.nome for prova in obj.prova_set.all()])
        return retorno

    get_provas.admin_order_field = 'provas'
    get_provas.short_description = 'Provas'


admin.site.register(ModalidadeDesportiva, ModalidadeDesportivaAdmin)


class CategoriaAdmin(ModelAdminPlus):
    list_filter = ('nome', 'idade_inferior', 'idade_superior', 'excluido')


admin.site.register(Categoria, CategoriaAdmin)


class ClassificacaoModalidadeInline(admin.StackedInline):
    model = ClassificacaoModalidade
    fields = ('inscricoes', 'equipe', 'classificacao', 'prova')
    extra = 1
    form = ClassificacaoModalidadeForm


class ResultadoModalidadeAdmin(ModelAdminPlus):
    list_display_icons = True
    search_fields = ('competicao_desportiva__nome', 'modalidade_desportiva__nome')
    list_filter = ('competicao_desportiva', 'modalidade_desportiva', 'categoria')
    list_display = ('competicao_desportiva', 'modalidade_desportiva', 'categoria', 'get_classificacao')
    inlines = [ClassificacaoModalidadeInline]

    def get_classificacao(self, obj):
        lista = []
        if obj.classificacaomodalidade_set.all().exists():
            lista.append('<ul>')
            [
                lista.append(f'<li>{classificacao.classificacao}º lugar - {classificacao.get_campus_ou_polo()}</li>')
                for classificacao in obj.classificacaomodalidade_set.all().order_by('classificacao')
            ]
            lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_classificacao.short_description = 'Classificação'


admin.site.register(ResultadoModalidade, ResultadoModalidadeAdmin)
