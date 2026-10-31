from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.http.request import HttpRequest
from django.utils.safestring import mark_safe
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import status
from edu.models import Modalidade
from ppc.forms import ConteudoPPCForm, PlanoDisciplinaForm, PlanoDisciplinaPPCForm, SolicitacaoPPCForm
from ppc.models import (
    AdministradorTipoOferta,
    Camara,
    ComentarioRevisaoPlanoDisciplina,
    ComissaoPTDEM,
    ConteudoPPC,
    Diretriz,
    DocumentoPPC,
    ModeloPlanoDisciplina,
    ModeloPPC,
    MovimentacaoPlanoDisciplina,
    MovimentacaoSolicitacaoPPC,
    PlanoDisciplina,
    PlanoDisciplinaPPC,
    ProjetoPedagogicoCurso,
    ProReitoria,
    RevisaoPlanoDisciplina,
    RevisorPlanoDisciplina,
    SolicitacaoPPC,
)


class DiretrizAdmin(ModelAdminPlus):
    list_display = (
        'descricao',
        'ano',
        'tipo_oferta',
        'modalidade',
        'estrutura_curso',
    )
    ordering = ('descricao',)
    list_filter = (
        'ano',
        'tipo_oferta',
        'modalidade',
        'estrutura_curso',
    )
    search_fields = ('descricao',)
    list_display_icons = True

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    ('descricao',),
                    ('ano', 'estrutura_curso'),
                    ('tipo_oferta', 'modalidade'),
                    ('exige_etapa_unica', 'exige_tcc'),
                    ('exige_colacao_grau', 'exige_enade'),
                    ('emite_certificacao_parcial', 'certificado_parcial_acumulavel'),
                    ('permite_plano_nao_aprovado',),
                )
            },
        ),
        ('Períodos', {'fields': (('qtd_min_periodos', 'qtd_max_periodos'))}),
        (
            'Carga horária geral',
            {
                'fields': (
                    ('ch_min_curso', 'ch_max_curso'),
                    ('ch_min_cc_obrigatorio', 'ch_max_cc_obrigatorio'),
                    ('ch_min_cc_optativo', 'ch_max_cc_optativo'),
                    ('ch_min_cc_eletivo', 'ch_max_cc_eletivo'),
                    ('ch_min_pratica', 'ch_max_pratica'),
                    ('ch_min_ac', 'ch_max_ac'),
                    ('ch_min_atpa', 'ch_max_atpa'),
                )
            },
        ),
        (
            'Carga horária por tipo de componente',
            {
                'fields': (
                    ('ch_min_cc_regular', 'ch_max_cc_regular'),
                    ('ch_min_cc_extensao', 'ch_max_cc_extensao'),
                    ('ch_min_cc_tcc', 'ch_max_cc_tcc'),
                )
            },
        ),
        ('Carga horária EAD', {'fields': (('percentual_min_ead', 'percentual_max_ead'))}),
        ('Equivalência de carga horária', {'fields': (('equivalencia_hr_ha', 'equivalencia_hr_credito'))}),
        ('Disciplinas por semestre', {'fields': (('qtd_min_disciplina_semestre', 'qtd_max_disciplina_semestre'))}),
        ('Carga horária por semestre', {'fields': (('ch_semanal_min_semestre', 'ch_semanal_max_semestre'))}),
        ('Arquivo da diretriz', {'fields': ('arquivo',)}),
    )

    def has_add_permission(self, request):
        return request.user.has_perm('ppc.add_diretriz') or AdministradorTipoOferta.is_administrador(request.user)

    def has_change_permission(self, request, obj=None):
        return obj and obj.can_change(request.user) or False

    def has_delete_permission(self, request, obj=None):
        return obj and obj.can_delete(request.user) or False

    def get_form(self, request, *args, **kwargs):
        form = super().get_form(request, *args, **kwargs)
        if 'tipo_oferta' in form.base_fields:
            if request.user.has_perm('comum.is_administrador_academico') or request.user.has_perm('comum.is_administrador_de_ppc'):
                form.base_fields['tipo_oferta'].queryset = Modalidade.objects.all()
            else:
                ids = AdministradorTipoOferta.objects.filter(servidores__matricula=request.user.username).values_list('tipo_oferta_id', flat=True)
                form.base_fields['tipo_oferta'].queryset = Modalidade.objects.filter(id__in=ids)
        return form


admin.site.register(Diretriz, DiretrizAdmin)


class ModeloPPCAdmin(ModelAdminPlus):
    list_display = ('descricao', 'tipo_oferta', 'modalidade', 'ativo')
    ordering = (
        '-ativo',
        'descricao',
    )
    list_filter = ('tipo_oferta', 'modalidade', 'ativo')
    search_fields = ('descricao',)
    list_display_icons = True

    def get_fieldsets(self, request, obj=None):
        fieldsets = (('Dados gerais', {'fields': (('descricao'), ('tipo_oferta', 'modalidade'))}),)

        if obj and obj.possui_ppc():
            fieldsets = (('Dados gerais', {'fields': (('descricao'),)}),)
        return fieldsets

    def has_add_permission(self, request):
        return request.user.has_perm('ppc.add_modeloppc') or AdministradorTipoOferta.is_administrador(request.user)

    def get_form(self, request, *args, **kwargs):
        form = super().get_form(request, *args, **kwargs)
        if 'tipo_oferta' in form.base_fields:
            if request.user.has_perm('comum.is_administrador_academico') or request.user.has_perm('comum.is_administrador_de_ppc'):
                form.base_fields['tipo_oferta'].queryset = Modalidade.objects.all()
            else:
                ids = AdministradorTipoOferta.objects.filter(servidores__matricula=request.user.username).values_list('tipo_oferta_id', flat=True)
                form.base_fields['tipo_oferta'].queryset = Modalidade.objects.filter(id__in=ids)
        return form


admin.site.register(ModeloPPC, ModeloPPCAdmin)


class ModeloPlanoDisciplinaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'nivel_ensino', 'ativo')
    ordering = (
        '-ativo',
        'descricao',
    )
    list_filter = ('nivel_ensino', 'ativo')
    search_fields = ('descricao',)
    list_display_icons = True

    def get_fields(self, request, obj):
        if obj:
            return (
                'descricao',
                'nivel_ensino',
                'ativo',
                'permite_secoes_ead',
                'permite_versao_ead_plano_aprovado',
                'orientacoes',
            )
        return (
            'descricao',
            'nivel_ensino',
            'permite_secoes_ead',
            'permite_versao_ead_plano_aprovado',
            'orientacoes',
        )


admin.site.register(ModeloPlanoDisciplina, ModeloPlanoDisciplinaAdmin)


class SolicitacaoPPCAdmin(ModelAdminPlus):
    list_display = ('get_nome_curso', 'tipo_oferta', 'modalidade', 'solicitante', 'get_situacao', 'get_situacao_ppc')
    ordering = ('-data_solicitacao',)
    search_fields = (
        'nome_curso',
        'ppc_adequacao__nome_curso',
    )
    list_filter = (CustomTabListFilter, 'tipo_oferta', 'modalidade', 'solicitante', 'situacao')
    list_display_icons = True
    form = SolicitacaoPPCForm

    def changelist_view(self, request, extra_context=None):
        self.minhas_pendencias = request.GET.get('minhas_pendencias', False)
        if self.minhas_pendencias:
            request.GET._mutable = True
            request.GET.pop('minhas_pendencias')
            request.GET._mutable = False
        return super().changelist_view(request, extra_context)

    def has_change_permission(self, request, obj=None):
        return obj and obj.situacao == SolicitacaoPPC.SOLICITADA and request.user.has_perm('ppc.add_solicitacaoppc')

    def response_add(self, request, obj, post_url_continue=None):
        MovimentacaoSolicitacaoPPC.registrar_movimentacao(request.user, obj)
        return super().response_add(request, obj, post_url_continue)

    def get_fieldsets(self, request, obj=None):
        fieldsets = []

        tipo = request.GET.get('tipo', SolicitacaoPPC.TIPO_CRIACAO)
        if tipo == SolicitacaoPPC.TIPO_ADEQUACAO:
            fieldsets.append(
                ('Dados gerais', {'fields': ('ppc_adequacao', 'justificativa')}),
            )
        else:
            fieldsets.append(
                ('Dados gerais', {'fields': ('nome_curso', 'justificativa', ('tipo_oferta', 'modalidade'), 'eixo_tecnologico')}),
            )

        fieldsets.append(('Outros dados', {'fields': ('convenio', 'id_processo_convenio')}))

        return fieldsets

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            # temporariamente desabilitado até validação do fluxo pela proen
            # items.append(dict(url='add/?tipo=2', label='Solicitar adequação de PPC', css_class='success'))
            items.append({'url': 'add/?tipo=1', 'label': 'Solicitar criação de PPC', 'css_class': 'success'})
        return items

    def get_tabs(self, request):
        return [
            'tab_any_data',
            'tab_adequacao',
            'tab_criacao',
            'tab_emissao_ata',
            'tab_finalizacao_ata',
            'tab_indicacao',
            'tab_envio',
            'tab_analise',
            'tab_solicitacao_portaria',
            'tab_emissao_portaria',
            'tab_finalizacao_portaria',
            'tab_geracao_ppc',
        ]

    def tab_adequacao(self, request, queryset):
        return queryset.filter(ppc_adequacao__isnull=False)

    tab_adequacao.short_description = 'Solicitações de adequação'

    def tab_criacao(self, request, queryset):
        return queryset.filter(ppc_adequacao__isnull=True)

    tab_criacao.short_description = 'Solicitações de criação'

    def tab_emissao_ata(self, request, queryset):
        servidor = self.minhas_pendencias and request.user.get_relacionamento()
        return SolicitacaoPPC.get_solicitacoes_emissao_ata_pendente(queryset, servidor)

    tab_emissao_ata.short_description = 'Emissão de ata pendente'

    def tab_finalizacao_ata(self, request, queryset):
        servidor = self.minhas_pendencias and request.user.get_relacionamento()
        return SolicitacaoPPC.get_solicitacoes_finalizacao_ata_pendente(queryset, servidor)

    tab_finalizacao_ata.short_description = 'Finalização de ata pendente'

    def tab_indicacao(self, request, queryset):
        return SolicitacaoPPC.get_solicitacoes_indicacao_pendente(queryset)

    tab_indicacao.short_description = 'Indicação de elaboradores pendente'

    def tab_analise(self, request, queryset):
        servidor = self.minhas_pendencias and request.user.get_relacionamento()
        return SolicitacaoPPC.get_solicitacoes_analise_pendente(queryset, servidor)

    tab_analise.short_description = 'Aguardando análise'

    def tab_envio(self, request, queryset):
        return SolicitacaoPPC.get_solicitacoes_envio_analise_pendente(queryset)

    tab_envio.short_description = 'Envio para análise pendente'

    def tab_solicitacao_portaria(self, request, queryset):
        servidor = self.minhas_pendencias and request.user.get_relacionamento()
        return SolicitacaoPPC.get_solicitacoes_solicitacao_portaria_pendente(queryset, servidor)

    tab_solicitacao_portaria.short_description = 'Solicitação de portaria pendente'

    def tab_emissao_portaria(self, request, queryset):
        servidor = self.minhas_pendencias and request.user.get_relacionamento()
        return SolicitacaoPPC.get_solicitacoes_emissao_portaria_pendente(queryset, servidor)

    tab_emissao_portaria.short_description = 'Emissão de portaria pendente'

    def tab_finalizacao_portaria(self, request, queryset):
        servidor = self.minhas_pendencias and request.user.get_relacionamento()
        return SolicitacaoPPC.get_solicitacoes_finalizacao_portaria_pendente(queryset, servidor)

    tab_finalizacao_portaria.short_description = 'Finalização de portaria pendente'

    def tab_geracao_ppc(self, request, queryset):
        return SolicitacaoPPC.get_solicitacoes_geracao_ppc_pendente(queryset)

    tab_geracao_ppc.short_description = 'Geração de PPC pendente'

    def get_nome_curso(self, obj):
        return obj.ppc_adequacao and obj.ppc_adequacao.nome_curso or obj.nome_curso

    get_nome_curso.short_description = 'Curso'

    def get_situacao_ppc(self, obj):
        return status(obj.get_situacao_ppc())

    get_situacao_ppc.short_description = 'Situação do PPC'

    def get_situacao(self, obj):
        return status(obj.get_situacao_display())

    get_situacao.short_description = 'Situação'


admin.site.register(SolicitacaoPPC, SolicitacaoPPCAdmin)


class ProjetoPedagogicoCursoAdmin(ModelAdminPlus):
    list_display = ('nome_curso', 'modelo_ppc', 'diretriz', 'get_situacao')
    list_filter = (CustomTabListFilter, 'modelo_ppc', 'diretriz', 'situacao')
    search_fields = ('nome_curso',)
    list_display_icons = True

    def get_fieldsets(self, request, obj=None):
        fieldsets = []
        if obj:
            if obj.situacao == ProjetoPedagogicoCurso.APROVADO and request.user.has_perm('comum.is_administrador_academico'):
                fieldsets.append(
                    (
                        'Identificação',
                        {
                            'fields': (
                                'identificador_ppc',
                                'nome_curso',
                                'nome_diploma_historico',
                                ('titulo_certificado_masculino', 'titulo_certificado_feminino'),
                                ('codigo_censup', 'codigo_educacenso'),
                                ('codigo_emec', 'codigo_sistec'),
                            )
                        },
                    )
                )
            else:
                fieldsets.append(
                    (
                        'Identificação',
                        {
                            'fields': (
                                'nome_curso',
                                'nome_diploma_historico',
                                ('titulo_certificado_masculino', 'titulo_certificado_feminino'),
                                ('codigo_censup', 'codigo_educacenso'),
                                ('codigo_emec', 'codigo_sistec'),
                            )
                        },
                    )
                )
            fieldsets.append(
                (
                    'Carga horária do curso',
                    {
                        'fields': (
                            ('ch_curso',),
                            ('ch_cc_obrigatorio', 'ch_cc_optativo'),
                            ('ch_cc_eletivo', 'ch_pratica'),
                            ('ch_ac', 'ch_atpa'),
                        )
                    },
                )
            )
            fieldsets.append(
                (
                    'Carga horária por tipo de componente',
                    {
                        'fields': (
                            ('ch_cc_regular', 'ch_cc_extensao'),
                            ('ch_cc_tcc',),
                        )
                    },
                )
            )
            fieldsets.append(
                (
                    'Dados gerais',
                    {
                        'fields': (
                            ('area_concentracao', 'periodicidade'),
                            ('programa', 'formacao_de_professores'),
                        )
                    },
                )
            )

        return fieldsets

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def get_tabs(self, request):
        return ['tab_any_data', 'tab_meus', 'tab_sem_reuniao', 'tab_sem_documento_finalizado', 'tab_sem_matriz']

    def tab_meus(self, request, queryset):
        servidor_id = request.user.get_relacionamento().id
        vinculo_id = request.user.get_vinculo().id
        return queryset.filter(
            Q(elaboradorppc__vinculo_id=vinculo_id)
            | Q(revisorppc__servidor_id=servidor_id)
            | Q(camara__secretario_id=servidor_id)
            | Q(camara__coordenador_id=servidor_id)
        ).distinct()

    tab_meus.short_description = 'Atribuídos a mim'

    def tab_sem_reuniao(self, request, queryset):
        qs = (
            queryset.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CAMARA, data_convocacao_camara=None)
            | queryset.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CONSEPEX, data_convocacao_consepex=None)
            | queryset.filter(situacao=ProjetoPedagogicoCurso.ANALISE_CONSUP, data_convocacao_consup=None)
        )
        return qs.distinct()

    tab_sem_reuniao.short_description = 'Sem data da reunião'

    def tab_sem_documento_finalizado(self, request, queryset):
        return queryset.filter(documentoppc__situacao_documento=DocumentoPPC.DOCUMENTO_CRIADO).distinct()

    tab_sem_documento_finalizado.short_description = 'Sem documento finalizado'

    def tab_sem_matriz(self, request, queryset):
        return queryset.filter(situacao=ProjetoPedagogicoCurso.APROVADO, matrizppc__matriz_id=None)

    tab_sem_matriz.short_description = 'Sem matriz'

    def get_situacao(self, obj):
        return status(obj.get_situacao_display())

    get_situacao.short_description = 'Situação'


admin.site.register(ProjetoPedagogicoCurso, ProjetoPedagogicoCursoAdmin)


class ConteudoPPCAdmin(ModelAdminPlus):
    form = ConteudoPPCForm

    change_form_template = 'conteudoppc_change_form.html'

    fieldsets = (
        (
            'Conteúdo',
            {
                'fields': ('texto',),
            },
        ),
    )

    def render_change_form(self, request, context, **kwargs):
        obj = kwargs.get('obj')
        if obj:
            context.update({'orientacao': obj.conteudo_modelo.orientacao_preenchimento})
            context.update({'comentarios': obj.comentarioconteudoppc_set.all()})
            context.update({'revisor': obj.revisor})
            context.update({'parecer_revisor': obj.parecer_revisor})
        return super().render_change_form(request, context, **kwargs)


admin.site.register(ConteudoPPC, ConteudoPPCAdmin)


class PlanoDisciplinaAdmin(ModelAdminPlus):
    list_display = (
        'nome_disciplina',
        'ch_disciplina',
        'tipo_oferta',
        'nucleo',
        'periodicidade',
        'comissao_ptdem',
        'ppc_criacao',
        'get_situacao',
        'ativo',
        'desconsiderar_qtd_credito',
    )
    ordering = ('nome_disciplina',)
    list_filter = (
        CustomTabListFilter,
        'tipo_oferta',
        'nucleo',
        'periodicidade',
        'comissao_ptdem',
        'avaliador',
        'planodisciplinappc__matriz_ppc__ppc',
        'situacao',
        'ativo',
        'desconsiderar_qtd_credito',
    )
    search_fields = ('nome_disciplina',)
    list_display_icons = True
    form = PlanoDisciplinaForm
    change_form_template = 'planodisciplina_change_form.html'

    def has_add_permission(self, request):
        return ComissaoPTDEM.objects.filter(servidores__matricula=request.user.username).exists()

    def response_add(self, request, obj, post_url_continue=None):
        MovimentacaoPlanoDisciplina.registrar_movimentacao(request.user, obj)
        return super().response_add(request, obj, post_url_continue)

    def add_view(self, request, form_url='', extra_context=None):
        try:
            return super().add_view(request, form_url, extra_context)
        except ValidationError as e:
            self.message_user(request, e.message, messages.ERROR)
            return HttpResponseRedirect('/admin/ppc/planodisciplina/')

    def get_tabs(self, request):
        return ['tab_meus_planos', 'tab_inconsistente']

    def tab_meus_planos(self, request, queryset):
        vinculo = request.user.get_vinculo()
        return PlanoDisciplina.get_meus_planos(vinculo, queryset)

    tab_meus_planos.short_description = 'Meus planos de disciplinas'

    def tab_inconsistente(self, request, queryset):
        return queryset.filter(comissao_ptdem__isnull=True, planodisciplinappc__isnull=True)

    tab_inconsistente.short_description = 'Planos inconsistentes'

    def get_situacao(self, obj):
        return status(obj.get_situacao_display())

    get_situacao.short_description = 'Situação'


admin.site.register(PlanoDisciplina, PlanoDisciplinaAdmin)


class PlanoDisciplinaPPCAdmin(ModelAdminPlus):
    list_display = ('plano_disciplina', 'matriz_ppc', 'periodo_oferta', 'optativo', 'tipo', 'quantidade_etapas', 'ch_teorica', 'ch_extensao')
    ordering = ('periodo_oferta', 'plano_disciplina')
    search_fields = ('plano_disciplina__nome_disciplina',)
    list_filter = (
        'plano_disciplina',
        'matriz_ppc__ppc',
        'matriz_ppc__cursos',
        'matriz_ppc__matriz',
        'periodo_oferta',
        'optativo',
        'tipo',
        'quantidade_etapas',
    )
    list_display_icons = True
    form = PlanoDisciplinaPPCForm
    fieldsets = PlanoDisciplinaPPCForm.fieldsets
    change_form_template = 'planodisciplinappc_change_form.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def response_change(self, request, obj):
        if '_ementa' in request.POST:
            self.message_user(request, 'Plano de disciplina atualizado com sucesso. Complete o cadastro de ementa e programa.')
            return HttpResponseRedirect(f'{obj.plano_disciplina.get_absolute_url()}?tab=programa')
        else:
            return super().response_change(request, obj)


admin.site.register(PlanoDisciplinaPPC, PlanoDisciplinaPPCAdmin)


class ComissaoPTDEMAdmin(ModelAdminPlus):
    list_display = ('nome',)
    ordering = ('nome',)
    search_fields = (
        'nome',
        'servidores__pessoa_fisica__nome',
        'servidores__matricula',
    )
    list_display_icons = True


admin.site.register(ComissaoPTDEM, ComissaoPTDEMAdmin)


class AdministradorTipoOfertaAdmin(ModelAdminPlus):
    list_display = ('tipo_oferta', 'get_servidores')
    ordering = ('tipo_oferta',)
    list_filter = ('tipo_oferta',)
    list_display_icons = True

    def get_servidores(self, obj):
        lista = ['<ul>']
        for servidor in obj.servidores.all():
            lista.append(f'<li>{servidor}</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_servidores.short_description = 'Servidores'


admin.site.register(AdministradorTipoOferta, AdministradorTipoOfertaAdmin)


class CamaraAdmin(ModelAdminPlus):
    list_display = ('nome', 'coordenador', 'secretario', 'ativo', 'get_tipos_oferta')
    list_display_icons = True
    list_filter = ('coordenador', 'secretario', 'ativo', 'tipos_oferta')
    search_fields = ('nome',)

    def has_view_permission(self, request, obj=None):
        return False

    def get_tipos_oferta(self, obj):
        lista = ['<ul>']
        for tipo_oferta in obj.tipos_oferta.all():
            lista.append(f'<li>{tipo_oferta}</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_tipos_oferta.short_description = 'Tipos de oferta'


admin.site.register(Camara, CamaraAdmin)


class ProReitoriaAdmin(ModelAdminPlus):
    list_display = ('setor', 'ativo', 'get_tipos_oferta')
    list_display_icons = True
    list_filter = ('setor', 'ativo', 'tipos_oferta')

    def has_view_permission(self, request, obj=None):
        return False

    def get_tipos_oferta(self, obj):
        lista = ['<ul>']
        for tipo_oferta in obj.tipos_oferta.all():
            lista.append(f'<li>{tipo_oferta}</li>')
        lista.append('</ul>')
        return mark_safe(''.join(lista))

    get_tipos_oferta.short_description = 'Tipos de oferta'


admin.site.register(ProReitoria, ProReitoriaAdmin)


class RevisorPlanoDisciplinaAdmin(ModelAdminPlus):
    list_display = ('servidor', 'ativo')
    list_filter = ('ativo',)
    search_fields = (
        'servidor__matricula',
        'servidor__pessoa_fisica__nome',
    )
    list_display_icons = True


admin.site.register(RevisorPlanoDisciplina, RevisorPlanoDisciplinaAdmin)


class RevisaoPlanoDisciplinaAdmin(ModelAdminPlus):
    list_display = ('vinculo', 'texto', 'resolvido')
    list_filter = (
        'vinculo',
        'resolvido',
    )
    exclude = ('plano_disciplina', 'vinculo', 'resolvido', 'numero_revisao')

    def has_add_permission(self, request):
        return PlanoDisciplina.is_avaliador(request.user)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            plano = PlanoDisciplina.objects.get(pk=int(request.GET.get('plano_id')))
            obj.numero_revisao = plano.revisaoplanodisciplina_set.count() + 1
            obj.plano_disciplina = plano
            obj.vinculo = request.user.get_vinculo()
            obj.resolvido = False
            obj.save()
            mensagem_notificacao = (
                f'Foi adicionada uma nova revisão para o plano de disciplina {obj.plano_disciplina}. Descrição da revisão: {obj.texto}'
            )
            obj.plano_disciplina.notificar(mensagem_notificacao, notificar_elaboradores=True, notificar_avaliadores=False)

        if change:
            ComentarioRevisaoPlanoDisciplina.adicionar(obj, request.user.get_vinculo(), 'editou esta revisão', automatico=True)
        super().save_model(request, obj, form, change)


admin.site.register(RevisaoPlanoDisciplina, RevisaoPlanoDisciplinaAdmin)
