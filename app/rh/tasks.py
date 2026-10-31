from __future__ import annotations

import os
import tempfile
import threading
import zipfile
from typing import TYPE_CHECKING

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.db import connection
from django.db.models import Prefetch
from django.forms import ValidationError
from django.utils.safestring import mark_safe

from djtools.assincrono import task
from djtools.choices import campos
from djtools.html.graficos import PieChart
from djtools.middleware import threadlocals as tl
from djtools.storages import cache_file
from djtools.utils import CsvResponse, XlsResponse, getattr_coalesce, getattrr, group_by, render_html_file
from rh.importador_ws import ImportadorWs

if TYPE_CHECKING:
    from djtools.models import Task


def _get_alias_campo(campo):
    # Recupera o alias do campo para formato legível
    for dicionario in campos:
        if dicionario['campo'] == campo:
            return str(dicionario['alias'])
        elif campo == 'nome':
            return 'Nome'
        elif campo == 'matricula':
            return 'Matrícula'


def get_miniaturas(servidores_qs):
    """
    Retorna False caso haja servidores sem fotos no resultado da busca
    """
    # foto migrou de PessoaFisica para Vinculo; acessa via AbstractRelacionamento.foto → Vinculo.foto
    servidores = servidores_qs.filter(vinculos__foto__isnull=False).exclude(vinculos__foto='')
    miniaturas = []
    for s in servidores:
        try:
            remote_filename = s.foto.name.replace('fotos/', 'fotos/150x200/')
            local_filename = cache_file(remote_filename)
            if os.path.exists(local_filename):
                miniaturas.append((local_filename, f'{s.matricula}.jpg'))
        except Exception:
            pass
    return miniaturas


def get_fotos_zip(servidores):
    """
    Cria o arquivo zip de fotos de servidores
    """
    response = tempfile.NamedTemporaryFile(mode='w+b', dir=settings.TEMP_DIR, delete=False, suffix='.zip')
    response.close()
    zip_file = zipfile.ZipFile(response.name, 'w', zipfile.ZIP_DEFLATED)

    miniaturas = get_miniaturas(servidores)

    for m in miniaturas:
        zip_file.write(*m)
    zip_file.close()
    return response.name


def gerar_xls_busca_servidor(request, task, servidores_qs, campos_selecionados):
    rows = []
    header = []
    if request.GET.get('format') == 'csv':
        header = ['#', 'MATRICULA', 'SERVIDOR']
    elif request.GET.get('format') == 'xls':
        header = ['MATRICULA', 'SERVIDOR']
    for campo in campos_selecionados:
        if campo == 'endereco':
            header.append('LOGRADOURO')
            header.append('NUMERO')
            header.append('COMPLEMENTO')
            header.append('BAIRRO')
            header.append('MUNICIPIO')
            header.append('CEP')
        header.append(str(campo).upper().replace('_', ' '))
    rows.append(header)
    idx = 0
    for servidor in task.iterate(servidores_qs):
        row = []
        if request.GET.get('format') == 'csv':
            row = [idx + 1, servidor.matricula, servidor.pessoa_fisica.nome]
        elif request.GET.get('format') == 'xls':
            row = [servidor.matricula, servidor.pessoa_fisica.nome]
        for campo in campos_selecionados:
            if campo == 'endereco':
                row.append(servidor.endereco_logradouro)
                row.append(servidor.endereco_numero)
                row.append(servidor.endereco_complemento)
                row.append(servidor.endereco_bairro)
                row.append(servidor.endereco_municipio)
                row.append(servidor.endereco_cep)
            # Mesmo motivo do relatório em HTML: nenhum campo da whitelist é método,
            # então não há auto-call — e resolve uma vez só, em vez de duas ou três.
            row.append(getattrr(servidor, campo))
        idx += 1
        rows.append(row)
    # Formato CSV
    if request.GET.get('format') == 'csv':
        return CsvResponse(rows, processo=task)
    # Formato XLS
    elif request.GET.get('format') == 'xls':
        return XlsResponse(rows, processo=task)


# Campos do relatório que hoje moram em comum.Vinculo (migração PessoaFisica -> Vinculo).
# Servidor os expõe via property delegando para get_vinculo(), que reaproveita o cache do prefetch.
CAMPOS_VIA_VINCULO = frozenset({'raca', 'povo_indigena', 'deficiencia', 'foto', 'email_pessoal', 'email_notificacao'})


def perform_queryset(servidores_qs, campos_selecionados):
    select_related = []
    prefetch_related = []
    if 'pessoa_fisica' in campos_selecionados:
        select_related.append('pessoa_fisica')
    if 'pessoa_fisica.banco_display' in campos_selecionados:
        select_related.append('pessoa_fisica__pagto_banco')
    if 'pessoa_fisica.nascimento_municipio' in campos_selecionados:
        select_related.append('pessoa_fisica__nascimento_municipio')
    if 'nivel_escolaridade' in campos_selecionados:
        select_related.append('nivel_escolaridade')
    if 'situacao' in campos_selecionados:
        select_related.append('situacao')
    if 'regime_juridico' in campos_selecionados:
        select_related.append('regime_juridico')
    if 'cargo_emprego_area' in campos_selecionados:
        select_related.append('cargo_emprego_area')
    if 'cargo_classe' in campos_selecionados:
        select_related.append('cargo_classe')
    if 'titulacao' in campos_selecionados:
        select_related.append('titulacao')
    if 'jornada_trabalho' in campos_selecionados:
        select_related.append('jornada_trabalho')
    if 'atividade' in campos_selecionados:
        select_related.append('funcao_atividade')
    if 'campus_exercicio_siape' in campos_selecionados:
        select_related.append('setor_exercicio__uo')
    if 'campus_lotacao_siape' in campos_selecionados:
        select_related.append('setor_lotacao__uo')
    if 'campus' in campos_selecionados:
        select_related.append('setor__uo')
    if 'cargo_emprego' in campos_selecionados:
        select_related.append('cargo_emprego')
        select_related.append('cargo_emprego__grupo_cargo_emprego')
    if 'funcao_display' in campos_selecionados:
        select_related.append('funcao')
    if 'pessoa_fisica.estado_civil' in campos_selecionados:
        select_related.append('pessoa_fisica__estado_civil')
    if CAMPOS_VIA_VINCULO & set(campos_selecionados):
        # Campos migrados para Vinculo: lidos pelas properties do papel (que usam get_vinculo()).
        # select_related não suporta GenericRelation, daí o Prefetch. `_base_manager` evita o
        # ordenados_para_selecao() do VinculoManager, que traria um JOIN com comum_user e uma
        # ordenação inúteis aqui (há no máximo 1 vínculo por servidor).
        Vinculo = apps.get_model('comum', 'vinculo')
        queryset_vinculo = Vinculo._base_manager.select_related('raca', 'povo_indigena', 'deficiencia', 'user')
        prefetch_related.append(Prefetch('vinculos', queryset=queryset_vinculo))
        if 'email_notificacao' in campos_selecionados:
            # Vinculo.email_notificacao lê os e-mails do papel pela GFK `relacionamento`, e o
            # último fallback (`.email`) cai no __getattr__ do Servidor, que busca pessoa_fisica.
            # GenericPrefetch carrega os dois de uma vez; sem ele são 2 queries por servidor.
            Servidor = apps.get_model('rh', 'servidor')
            prefetch_related.append(GenericPrefetch('vinculos__relacionamento', [Servidor.objects.select_related('pessoa_fisica')]))
    if 'pessoa_fisica.endereco' in campos_selecionados:
        PessoaEndereco = apps.get_model('comum', 'pessoaendereco')
        prefetch_related.append(Prefetch('pessoa_fisica__pessoaendereco_set', queryset=PessoaEndereco.objects.select_related('municipio')))
    if 'ocorrencias_display' in campos_selecionados:
        ServidorOcorrencia = apps.get_model('rh', 'servidorocorrencia')
        prefetch_related.append(
            Prefetch('servidorocorrencia_set', queryset=ServidorOcorrencia.objects.select_related('ocorrencia__grupo_ocorrencia'))
        )
    if 'afastamentos_display' in campos_selecionados:
        ServidorAfastamento = apps.get_model('rh', 'servidorafastamento')
        prefetch_related.append(
            Prefetch('servidorafastamento_set', queryset=ServidorAfastamento.objects.filter(cancelado=False).select_related('afastamento'))
        )
    if 'ferias' in campos_selecionados:
        Ferias = apps.get_model('ferias', 'ferias')
        prefetch_related.append(Prefetch('ferias_set', queryset=Ferias.objects.select_related('ano').prefetch_related('interrupcaoferias_set')))
    if 'data_ultima_progressao' in campos_selecionados:
        PCA = apps.get_model('rh', 'pca')
        PosicionamentoPCA = apps.get_model('rh', 'posicionamentopca')
        FormaProvimentoVacancia = apps.get_model('rh', 'formaprovimentovacancia')
        prefetch_posicionamento = Prefetch(
            'posicionamentopca_set',  # ou o related_name definido em PCA, se houver
            queryset=PosicionamentoPCA.objects.filter(forma_entrada__codigo=FormaProvimentoVacancia.CODIGO_PROGRESSAO).order_by(
                '-data_inicio_posicionamento_pca'
            ),
            to_attr='prefetched_progressao',
        )

        # Em seguida, definimos o queryset para pca_set que já faz o prefetch dos posicionamentopca
        prefetch_pca = Prefetch('pca_set', queryset=PCA.objects.prefetch_related(prefetch_posicionamento))
        prefetch_related.append(prefetch_pca)
    return servidores_qs.select_related(*select_related).prefetch_related(*prefetch_related)


@task('Gerar Busca de Servidor')
def gerar_busca_servidor(request, cleaned_data, servidores_qs, campos_selecionados, encoded_url, task=None):
    task.update_progress(1)
    url_base = '/rh/servidor/buscar/' + '?' + encoded_url
    url_csv = url_base + '&format=csv'
    url_xls = url_base + '&format=xls'
    url_zip = ''
    # foto migrou de PessoaFisica para Vinculo; filter+exclude garante semântica idêntica ao original
    tem_fotos = servidores_qs.filter(vinculos__foto__isnull=False).exclude(vinculos__foto='').exists()
    # Só poderá haver formato zip caso algum servidor retornado pela busca tenha foto
    if tem_fotos:
        url_zip = url_base + '&format=zip'

    servidores_qs = perform_queryset(servidores_qs, campos_selecionados)
    if request.GET.get('format') == 'zip':
        return task.finalize('Arquivo de fotos gerado com sucesso.', '..', file_path=get_fotos_zip(servidores_qs))

    if request.GET.get('format') in ['csv', 'xls']:
        return gerar_xls_busca_servidor(request, task, servidores_qs, campos_selecionados)

    # Populando lista de dicionário de servidores
    servidores_dict = []
    agrupador_valores = {}
    subagrupador_valores = {}

    for servidor in task.iterate(servidores_qs):
        item = {'nome': servidor.pessoa_fisica.nome, 'matricula': servidor.matricula}
        for campo in campos_selecionados:
            if campo == 'foto':
                valor = servidor.foto and servidor.foto.url_75x100 or '/static/comum/img/default.jpg'
                item['foto'] = str(valor)
            elif campo == 'endereco':
                item['Logradouro'] = servidor.pessoa_fisica.endereco_logradouro
                item['Numero'] = servidor.pessoa_fisica.endereco_numero
                item['Complemento'] = servidor.pessoa_fisica.endereco_complemento
                item['Bairro'] = servidor.pessoa_fisica.endereco_bairro
                item['Municipio'] = servidor.pessoa_fisica.endereco_municipio
                item['CEP'] = servidor.pessoa_fisica.endereco_cep
            else:
                if campo == 'ferias':
                    ferias_lista = servidor.ferias_lista
                    valor = []
                    valor.append('<ul>')
                    for ferias in ferias_lista:
                        valor.append(f'<li>{ferias}</li>')
                    valor.append('</ul>')
                    valor = ''.join(valor)
                else:
                    # Sem auto-call: os 75 campos de `djtools.choices.campos` resolvem para
                    # campo, FK ou property — nenhum é método. Chamar o resultado só criaria a
                    # invariante implícita de que ninguém pode adicionar um método à whitelist.
                    valor = getattr_coalesce(servidor, str(campo))
                    if valor is None or valor == '':
                        valor = 'Nenhum'
                if campo == cleaned_data['agrupador']:
                    agrupador_valores[str(valor)] = hasattr(valor, 'id') and valor.id or str(valor)
                if campo == cleaned_data['subagrupador']:
                    subagrupador_valores[str(valor)] = hasattr(valor, 'id') and valor.id or str(valor)
                item[str(campo)] = str(valor)
        servidores_dict.append(item)

    if cleaned_data['subagrupador']:  # 2 agrupamentos
        todos_valores_agrupador = list({i.get(cleaned_data['agrupador']) or 'Nenhum' for i in servidores_dict})
        todos_valores_agrupador.sort()
        todos_valores_subagrupador = list({i.get(cleaned_data['subagrupador']) or 'Nenhum' for i in servidores_dict})
        todos_valores_subagrupador.sort()
        servidores_dict = group_by(servidores_dict, cleaned_data['agrupador'], cleaned_data['subagrupador'], as_dict=1)
        matriz = [[{'valor': ''}] + [{'valor': a} for a in todos_valores_agrupador] + [{'valor': 'Total'}]]

        for s in todos_valores_subagrupador:
            linha_a = [{'valor': s}]
            for a in todos_valores_agrupador:
                count = len(servidores_dict[a]['subgroups_as_dict'].get(s, {'items': []})['items'])
                url = '{}&{}={}&{}={}&agrupador=&subagrupador='.format(
                    url_base, cleaned_data['agrupador'], agrupador_valores[str(a)], cleaned_data['subagrupador'], subagrupador_valores[str(s)]
                )
                linha_a.append({'valor': count, 'url': url})
            linha_a.append({'valor': sum(i['valor'] for i in linha_a[1:])})
            matriz.append(linha_a)
        linha_total = [{'valor': 'TOTAL'}]
        for a in todos_valores_agrupador:
            linha_total.append({'valor': len(servidores_dict[a]['items'])})
        linha_total.append({'valor': sum(i['valor'] for i in linha_total[1:])})
        matriz.append(linha_total)
        return render_html_file('rh/templates/servidor_buscar_2_agrupamentos.html', {'matriz': matriz}, request, task)

    elif cleaned_data['agrupador']:  # 1 agrupamento
        dicionario = {}
        if servidores_dict:
            servidores_agrupados = group_by(servidores_dict, cleaned_data['agrupador'])
            for g in servidores_agrupados:
                g['title'] = '{} ({:d})'.format(g['group'], len(g['items']))
            campo_agrupador_from_alias = _get_alias_campo(cleaned_data['agrupador'])
            grafico = PieChart(
                'grafico',
                title=f'Servidores por {campo_agrupador_from_alias}',
                data=[(str(i['group']), len(i['items'])) for i in servidores_agrupados],
            )
            cabecalhos = []
            for cabecalho in servidores_agrupados[0]['items'][0]:
                cabecalhos.append(_get_alias_campo(cabecalho))

            dicionario = {
                'grafico': grafico,
                'servidores': servidores_agrupados,
                'campo_agrupador_from_alias': campo_agrupador_from_alias,
                'campo_agrupador': cleaned_data['agrupador'],
                'cabecalhos': cabecalhos,
            }
        return render_html_file('rh/templates/servidor_buscar_1_agrupamento.html', dicionario, request, task)

    else:  # Nenhum agrupamento
        novos_campos_selecionados = []
        for campo in campos_selecionados:
            if campo == 'endereco':
                novos_campos_selecionados.append('Logradouro')
                novos_campos_selecionados.append('Numero')
                novos_campos_selecionados.append('Complemento')
                novos_campos_selecionados.append('Bairro')
                novos_campos_selecionados.append('Municipio')
                novos_campos_selecionados.append('CEP')
            else:
                novos_campos_selecionados.append(str(campo))
        dicionario = {
            'campos_selecionados': novos_campos_selecionados,
            'servidores': servidores_dict,
            'url_csv': url_csv,
            'url_xls': url_xls,
            'url_zip': url_zip,
        }
        return render_html_file('rh/templates/tela_relatorio.html', dicionario, request, task)


@task('Importação SIAPE')
def executar_importacao_siape(importacao_id: int, task: Task | None = None) -> None:
    from rh.importacao_siape.execucao import executar_importacao, workers_configurados
    from rh.models import ImportacaoSiape

    importacao = ImportacaoSiape.objects.get(pk=importacao_id)
    request_anterior, user_anterior = tl.get_request(), tl.get_user()
    # Task despachada a partir de uma requisição: sem isso os signals de `rh/signals.py`
    # (post_save de ServidorAfastamento etc.) atribuiriam ao operador que clicou em "Importar
    # selecionados" os alertas gerados pelos milhares de registros da importação em massa.
    # Restaurado no finally porque quem chamou a task (ex.: a própria view, em modo síncrono de
    # teste) ainda usa o threadlocal depois — `httprr` monta o redirect a partir dele.
    tl.context.request = None
    tl.context.user = None
    try:
        executar_importacao(importacao, workers_configurados())
    finally:
        tl.context.request = request_anterior
        tl.context.user = user_anterior
        # só fecha quando a task roda em thread própria (worker Celery ou Thread de
        # `djtools.assincrono`): em teste ela roda inline na mesma thread principal do pytest,
        # e fechar a conexão ali quebraria o restante do teste.
        if threading.current_thread() is not threading.main_thread():
            connection.close()
    if task:
        task.finalize(f'Importação SIAPE #{importacao.pk} finalizada.', importacao.get_absolute_url())


@task('Importar Servidor por WebService')
def importar_servidor_ws(cpf, apenas_servidores_em_exercicio, task=None):
    try:
        importador = ImportadorWs()
    except ValidationError as e:
        return task.finalize(str(e), '/rh/importar_servidor/', error=True)
    task.update_progress(25)
    dados_atualizar = importador.importacao_servidor(cpf, False, apenas_servidores_em_exercicio)
    task.update_progress(50)
    importador.atualizar_ferias_afastamentos(cpf)
    task.update_progress(75)
    msg = []
    for dados, criado in dados_atualizar:
        msg.append(f'Servidor <a href="{dados.get_absolute_url()}">{dados}</a> {"cadastrado" if criado else "atualizado"} com sucesso.')
    task.finalize(mark_safe(', '.join(msg)), '/rh/importar_servidor/')
