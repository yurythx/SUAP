import re

from django.contrib.admin.filters import SimpleListFilter
from django.db.models import Q
from django.db.models.aggregates import Max
from django.forms.utils import flatatt
from django.forms.widgets import TextInput
from django.utils.encoding import force_str
from django.utils.html import format_html

from comum.models import User
from comum.utils import get_uo
from djtools.forms.fields import CharFieldPlus
from djtools.templatetags.filters import in_group
from djtools.utils import dinheiro_extenso, to_ascii
from edu.models import SituacaoMatriculaPeriodo
from edu.models.cadastros_gerais import SituacaoMatricula


class SituacaoUltimaMatriculaPeriodoFilter(SimpleListFilter):
    title = 'Situação da Matrícula Período'
    parameter_name = 'situacao_ultima_matricula_periodo'

    def lookups(self, request, model_admin):
        return ((x.pk, x.descricao) for x in SituacaoMatriculaPeriodo.objects.all())

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                aluno__matriculaperiodo__pk__in=queryset.annotate(max_matricula_periodo=Max('aluno__matriculaperiodo__id')).values_list(
                    'max_matricula_periodo', flat=True
                ),
                aluno__matriculaperiodo__situacao__pk=self.value(),
            ).distinct()


class SituacaoUltimaMatriculaPeriodoAprendizagemFilter(SimpleListFilter):
    title = 'Situação da Matrícula Período'
    parameter_name = 'situacao_ultima_matricula_periodo'

    def lookups(self, request, model_admin):
        return ((x.pk, x.descricao) for x in SituacaoMatriculaPeriodo.objects.all())

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                aprendiz__matriculaperiodo__pk__in=queryset.annotate(max_matricula_periodo=Max('aprendiz__matriculaperiodo__id')).values_list(
                    'max_matricula_periodo', flat=True
                ),
                aprendiz__matriculaperiodo__situacao__pk=self.value(),
            ).distinct()


class TipoAditivoContratualFilter(SimpleListFilter):
    title = 'Tipo de Aditivo Contratual'
    parameter_name = 'tipo_aditivo_contratual'

    def lookups(self, request, model_admin):
        from estagios.models import TipoAditivo

        return ((x.pk, x.descricao) for x in TipoAditivo.objects.all())

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(estagioaditivocontratual__tipos_aditivo__pk=self.value()).distinct()
        else:
            return queryset


class PossuiAditivoContratualFilter(SimpleListFilter):
    title = 'Possui Aditivo Contratual?'
    parameter_name = 'possui_aditivo_contratual'

    def lookups(self, request, model_admin):
        return ((1, 'Sim'), (2, 'Não'))

    def queryset(self, request, queryset):
        if self.value():
            if int(self.value()) == 1:
                queryset = queryset.filter(estagioaditivocontratual__pk__gt=0).distinct()
            elif int(self.value()) == 2:
                queryset = queryset.exclude(estagioaditivocontratual__pk__gt=0).distinct()
            return queryset


class ListCharFieldWidget(TextInput):
    def render(self, name, value, attrs=None, rendered=None):
        if value is None:
            value = ['']
        elif not isinstance(value, list | tuple):
            value = [value]
        final_attrs = self.build_attrs(attrs)
        #
        tag_input_vazia = format_html('<input{} name={} size=100px />', flatatt(final_attrs), name)
        tag_remove = '<img src="/static/admin/img/icon-deletelink.svg" class="cleanValue" onclick="listcharfield_remove_item(this);">'
        #
        htmls = ['<ul style="padding: 0px 0px 5px 20px;">']
        for value_item in value:
            htmls.append('<li>')
            if value_item != '':
                final_attrs['value'] = force_str(self.format_value(value_item))
                htmls.append(format_html('<input{} name={} size=100px />', flatatt(final_attrs), name))
            else:
                htmls.append(tag_input_vazia)
            htmls.append(tag_remove)
            htmls.append('</li>')
        #
        htmls.append('<li>')
        js_add = f"""
            <script type="text/javascript">
                function listcharfield_remove_item(link_remove){{
                    if (confirm('Confirma?') == true){{
                        $(link_remove).prev().remove();
                        $(link_remove).remove();
                    }}
                }}

                function listcharfield_add_item(link_add){{
                    $(link_add).parent().before('<li>{tag_input_vazia}{tag_remove}</li>');
                    $(link_add).parent().prev().find("input").focus();
                    return false;
                }}
            </script>
        """

        htmls.append('<br><a href="#" style="margin-top: 20px; padding-top: 20px;" onclick="listcharfield_add_item(this);">Adicionar novo item</a>')
        htmls.append('</li>')
        #
        htmls.append('</ul>')
        #
        html_final = format_html(''.join(htmls)) + js_add
        return html_final

    def value_from_datadict(self, data, files, name):
        return data.getlist(name)


class ListCharField(CharFieldPlus):
    widget = ListCharFieldWidget

    def __init__(self, *args, **kwargs):
        kwargs['width'] = '800'
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value is None:
            return ['']
        elif not isinstance(value, list | tuple):
            return [value]
        return value  # uma lista de unicodes


def get_diretores_academicos(aluno):
    if aluno and aluno.curso_campus and aluno.curso_campus.diretoria:
        return User.objects.filter(
            Q(groups__name='Diretor Acadêmico Sistêmico') | Q(vinculo__in=aluno.curso_campus.diretoria.get_diretores_academicos())
        )

    return User.objects.none()


def get_coordenadores_estagio(aluno):
    if aluno and aluno.campus:
        return User.objects.filter(groups__name='Coordenador de Estágio', vinculo__setor__uo=aluno.campus)

    return User.objects.none()


def get_coordenadores_extensao(aluno):
    if aluno and aluno.campus:
        return User.objects.filter(groups__name='Coordenador de Extensão', vinculo__setor__uo=aluno.campus)

    return User.objects.none()


def get_coordenadores_nomes(coordenadores):
    return ', '.join([coordenador.get_profile().nome for coordenador in coordenadores])


def get_coordenadores_emails(coordenadores):
    return ', '.join([coordenador.email for coordenador in coordenadores])


def get_coordenadores_vinculos(coordenadores):
    vinculos = []
    for coordenador in coordenadores:
        vinculos.append(coordenador.get_vinculo())
    return vinculos


def get_situacoes_irregulares():
    return SituacaoMatricula.objects.exclude(id__in=[SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL])


def visualiza_todos_estagios_afins(user):
    return user.is_superuser or in_group(
        user,
        [
            'Coordenador de Estágio Sistêmico',
            'Administrador Acadêmico',
            'Auditor',
            'Visualizador de Estágios Sistêmico',
            'Estagiário Acadêmico Sistêmico',
            'Operador de Censo',
        ],
    )


def usuario_possui_cadastro(user):
    return user is not None and not user.is_anonymous


def tem_permissao_de_coordenador(user, campus=None):
    eh_do_mesmo_campus = user and campus and get_uo(user) == campus
    return (
        in_group(user, 'Coordenador de Estágio Sistêmico')
        or eh_do_mesmo_campus
        and in_group(user, ['Coordenador de Estágio', 'Coordenador de Extensão'])
    )


def por_extenso(value):
    if bool(value):
        reais, centavos = str(value).split('.')
        return f'{dinheiro_extenso(reais, centavos)}'
    else:
        return '-'


def textos_diferem(texto_1, texto_2):
    regex_ignorar = r'\W+'
    return re.sub(regex_ignorar, '', to_ascii(texto_1.lower())) != re.sub(regex_ignorar, '', to_ascii(texto_2.lower()))


def get_divergencias_relatorios_estagio(relatorio_aluno, relatorio_supervisor):
    from estagios.models import RelatorioSemestralEstagioAtividade

    divergencias = {}

    if relatorio_aluno is None or relatorio_supervisor is None:
        return divergencias

    divergencias_atividades_previstas = []

    for atividade in relatorio_aluno.pratica_profissional.atividade_set.order_by('pk').all():
        atividade_rel_aluno = relatorio_aluno.relatoriosemestralestagioatividade_set.filter(atividade=atividade).first()
        atividade_rel_supervisor = relatorio_supervisor.relatoriosemestralestagioatividade_set.filter(atividade=atividade).first()

        # Ignora a atividade se nenhum dos relatórios a mencionou.
        # Isso pode acontecer quando um aditivo acrescenta atividades ao estágio depois que os relatórios foram criados.
        if not atividade_rel_aluno and not atividade_rel_supervisor:
            continue

        # Outro cenário possível é, após um aditivo acrescentar atividades, apenas um dos relatórios
        # terem sido gerados a tempo de incorporar as adições.
        # Nesse caso, é necessário que o outro também contemple as atividades adicionais.
        # O código abaixo garante que ambos os relatórios contemplarão todas as atividades cabíveis.
        if not atividade_rel_aluno:
            atividade_rel_aluno = RelatorioSemestralEstagioAtividade.objects.create(
                relatorio_semestral=relatorio_aluno, atividade=atividade, realizada=RelatorioSemestralEstagioAtividade.REALIZADA_NAO
            )
        if not atividade_rel_supervisor:
            atividade_rel_supervisor = RelatorioSemestralEstagioAtividade.objects.create(
                relatorio_semestral=relatorio_supervisor, atividade=atividade, realizada=RelatorioSemestralEstagioAtividade.REALIZADA_NAO
            )

        if atividade_rel_aluno.realizada != atividade_rel_supervisor.realizada or (
            atividade_rel_aluno.realizada == RelatorioSemestralEstagioAtividade.REALIZADA_NAO
            and textos_diferem(atividade_rel_aluno.get_motivo_nao_realizada() or '', atividade_rel_supervisor.get_motivo_nao_realizada() or '')
        ):
            divergencias_atividades_previstas.append((atividade_rel_aluno, atividade_rel_supervisor))

    if divergencias_atividades_previstas:
        divergencias['atividades_previstas'] = divergencias_atividades_previstas

    divergencias_atividades_nao_previstas = {}
    if relatorio_aluno.realizou_outras_atividades != relatorio_supervisor.realizou_outras_atividades:
        divergencias_atividades_nao_previstas['realizou_outras_atividades'] = (
            relatorio_aluno.realizou_outras_atividades,
            relatorio_supervisor.realizou_outras_atividades,
        )

    if relatorio_aluno.realizou_outras_atividades or relatorio_supervisor.realizou_outras_atividades:
        if textos_diferem(relatorio_aluno.outras_atividades or '', relatorio_supervisor.outras_atividades or ''):
            divergencias_atividades_nao_previstas['outras_atividades'] = (relatorio_aluno.outras_atividades, relatorio_supervisor.outras_atividades)

        if textos_diferem(relatorio_aluno.outras_atividades_justificativa or '', relatorio_supervisor.outras_atividades_justificativa or ''):
            divergencias_atividades_nao_previstas['outras_atividades_justificativa'] = (
                relatorio_aluno.outras_atividades_justificativa,
                relatorio_supervisor.outras_atividades_justificativa,
            )

    if divergencias_atividades_nao_previstas:
        divergencias['atividades_nao_previstas'] = divergencias_atividades_nao_previstas

    return divergencias


def get_divergencias_relatorios_modulo_aprendizagem(relatorio_aprendiz, relatorio_monitor):
    divergencias = {}

    if relatorio_aprendiz is None or relatorio_monitor is None:
        return divergencias

    # Atividades PREVISTAS
    if relatorio_aprendiz.avaliacao_atividades != relatorio_monitor.avaliacao_atividades:
        divergencias['avaliacao_atividades'] = (
            relatorio_aprendiz.get_avaliacao_atividades_display(),
            relatorio_monitor.get_avaliacao_atividades_display(),
        )

    # Analisar divergências na descrição das atividades (apenas se realizadas parcialmente).
    if (
        relatorio_aprendiz.avaliacao_atividades != relatorio_monitor.avaliacao_atividades
        or relatorio_aprendiz.atividades_foram_realizadas_parcialmente()
        or relatorio_monitor.atividades_foram_realizadas_parcialmente()
    ):
        if textos_diferem(relatorio_aprendiz.comentarios_atividades or '', relatorio_monitor.comentarios_atividades or ''):
            divergencias['comentarios_atividades'] = (relatorio_aprendiz.comentarios_atividades, relatorio_monitor.comentarios_atividades)

    # Atividades NÃO PREVISTAS
    if textos_diferem(relatorio_aprendiz.outras_atividades or '', relatorio_monitor.outras_atividades or ''):
        divergencias['outras_atividades'] = (relatorio_aprendiz.outras_atividades, relatorio_monitor.outras_atividades)

    return divergencias
