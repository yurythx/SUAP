import tempfile

from django.conf import settings

from comum.models import Configuracao
from djtools.assincrono import task
from djtools.utils import render_to_string
from ponto.forms import FrequenciaCargoEmpregoFormFactory
from ponto.models import Frequencia
from ponto.utils import get_relatorios_ponto_adaptados_para_relatorios_pit_rit_ponto_docente, get_response_xls_registros_frequencias


@task('Relatório de Frequência por Cargo Emprego')
def relatorio_frequencia_cargo_emprego(cargo_emprego, faixa_0, faixa_1, request, task=None):
    relatorios = Frequencia.relatorio_cargo_emprego(cargo_emprego=cargo_emprego, data_ini=faixa_0, data_fim=faixa_1, request=request, task=task)

    ponto_docente_via_app_pit_rit_is_ativado = 'pit_rit' in settings.INSTALLED_APPS and Configuracao.get_valor_por_chave(
        'pit_rit', 'ponto_docente_ativado'
    )
    if ponto_docente_via_app_pit_rit_is_ativado:
        relatorios = get_relatorios_ponto_adaptados_para_relatorios_pit_rit_ponto_docente(relatorios, faixa_0, faixa_1, task=None)

    FormClass = FrequenciaCargoEmpregoFormFactory()
    form = FormClass(request.GET or None)
    form.ACTION = '/ponto/frequencia_cargo_emprego/'
    ctx = {'relatorios': relatorios, 'form': form, 'title': 'Relatório de Frequência por Cargo Emprego'}

    response = render_to_string('ponto/templates/relatorio_frequencia.html', ctx, request)
    f = tempfile.NamedTemporaryFile(suffix='.html', mode='w+', delete=False)
    f.write(response)
    f.close()
    task.finalize('Arquivo gerado com sucesso.', '..', file_path=f.name)


@task('Relatório de Frequência por Setor')
def relatorio_frequencia_setor(servidores, faixa_0, faixa_1, request, task=None):
    from ponto.views import frequencia_funcionario_get_relatorio_ponto_pessoa_info

    relatorios = []

    for servidor in task.iterate(servidores):
        try:
            relatorio_info = frequencia_funcionario_get_relatorio_ponto_pessoa_info(request, servidor, faixa_0, faixa_1)
            relatorios.append(relatorio_info['relatorio'])
        except Exception:
            pass

    if relatorios:
        xls_todos = get_response_xls_registros_frequencias(relatorios, filename='Relatorio.xls')

        f = tempfile.NamedTemporaryFile(suffix='.xls', mode='wb+', delete=False)
        f.write(xls_todos.content)
        f.close()
        task.finalize('Arquivo gerado com sucesso.', '..', file_path=f.name)

    task.finalize('Relatório não possui nenhum servidor.', '..')
