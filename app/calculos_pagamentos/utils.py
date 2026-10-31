import os

import pandas as pd
from django.conf import settings

from calculos_pagamentos.models import (
    TIPO_CALCULO_CHOICES,
    CalculoDocumento,
    NivelVencimento,
    ValorPorNivelVencimento,
    ValorPorNivelVencimentoDocente,
    ValorRetribuicaoTitulacao,
)
from djtools.storages import cache_file
from djtools.utils import dExtenso
from rh.models import JornadaTrabalho, Titulacao


def isfloat(value):
    try:
        float(value)
        return True
    except ValueError:
        return False


# Método criado no IFMA por Tássio Luz Campos para fazer a leitura de arquivos XLS com os valores de vencimentos de
# TAEs e preencher a tabela de vencimentos de TAEs com esses valores.
def atualizar_tabelas_de_vencimento_tae():
    """
    REQUISITOS:
    - Haver um Grupo de Documentos chamado "Tabelas de Vencimentos de TAEs"
    - A descrição dos arquivos salvos no Grupo de Documentos "Tabelas de Vencimentos de TAEs" deve ser no
        formato TIPO-DATAINICIAL-DATAFINAL, sendo válidos os seguintes valores:
        - TIPO: TAE
        - DATAINICIAL e DATAFINAL: no formato DD.MM.AAAA (00.00.0000 significa que não há data)
    - Os arquivos devem ser do tipo .xls ou .xlsx
    - Na primera planilha, o primeiro número de cada linha que tenha números deve ser o valor de um nível, sendo que o
        primeiro desses valores corresponde ao nível mais baixo e o nível vai aumentando até a última linha com números.
    PS.: Lembrar de não deixar a data de fim de um período sobrepôr a data de início de outro.
    """
    if 'conteudoportal' in settings.INSTALLED_APPS_SUAP:
        from conteudoportal.models import Documento

        niveis = NivelVencimento.objects.filter(categoria='tecnico_administrativo').order_by('id')
        try:
            arquivos = Documento.objects.get(titulo='Tabelas de Vencimentos de TAEs').arquivo_set.all()
            for arquivo in arquivos:
                nome = arquivo.descricao
                parametros = nome.split('-')
                d_ini = parametros[1]
                d_fim = parametros[2]

                if d_ini.split('.')[2] == '0000' and d_ini.split('.')[1] == '00' and d_ini.split('.')[0] == '00':
                    data1 = None
                else:
                    data1 = '{}-{}-{}'.format(d_ini.split('.')[2], d_ini.split('.')[1], d_ini.split('.')[0])
                if d_fim.split('.')[2] == '0000' and d_fim.split('.')[1] == '00' and d_fim.split('.')[0] == '00':
                    data2 = None
                else:
                    data2 = '{}-{}-{}'.format(d_fim.split('.')[2], d_fim.split('.')[1], d_fim.split('.')[0])

                filepath = cache_file(arquivo.arquivo.name)
                # IFMA/Tássio: Se sem arquivo = link externo = não entra
                if arquivo.arquivo and os.path.exists(filepath) and (filepath.endswith(('.xls', '.xlsx'))):
                    df = pd.read_excel(filepath, header=None)
                    nivel_idx = 0
                    for _index, row in df.iterrows():
                        for _j, cell_value in enumerate(row):
                            str_val = cell_value
                            if isfloat(str_val):
                                valor = float(str_val)
                                # print nome, valor
                                nivel = niveis[nivel_idx]
                                ValorPorNivelVencimento.objects.update_or_create(
                                    nivel=nivel, data_inicio=data1, data_fim=data2, defaults={'valor': valor}
                                )
                                nivel_idx += 1
                                break
        except Exception:
            # Mostre na tela
            # import traceback
            # trace = traceback.format_exc()
            # print 'Aconteceu um erro:\n', trace
            return False, 'Erro. Existe Grupo de Documentos chamado "Tabelas de Vencimentos de TAEs"?'
        return True, 'OK'


# Método criado no IFMA por Tássio Luz Campos para fazer a leitura de arquivos XLS com os valores de vencimentos de
# docentes e preencher a tabela de vencimentos de docentes com esses valores.
def atualizar_tabelas_de_vencimento_docente():
    """
    REQUISITOS:
    - Haver um Grupo de Documentos chamado "Tabelas de Vencimentos de Docentes"
    - A descrição dos arquivos salvos no Grupo de Documentos "Tabelas de Vencimentos de Docentes" deve ser no
        formato TIPO-JORNADA-DATAINICIAL-DATAFINAL, sendo válidos os seguintes valores:
        - TIPO: Superior, EBTT
        - JORNADA: 20, 40, DE
        - DATAINICIAL e DATAFINAL: no formato DD.MM.AAAA (00.00.0000 significa que não há data)
    - Os arquivos devem ser do tipo .xls ou .xlsx
    - Na primeira planilha, as únicas linhas que tenham células com números racionais devem ter pelo menos 5 números
        racionais, sendo que eles estejam na ordem
        vencimento -> RT mais baixa -> ... -> RT mais alta
        e sendo que a primeira dessas linhas contendo os valores do nível mais alto e o nível ir diminuindo até a
        13ª das linhas.
    - Células de valores que estão vazias devem ser preenchidas com 0.
    PS.: Lembrar de não deixar a data de fim de um período sobrepôr a data de início de outro.
    """

    if 'conteudoportal' in settings.INSTALLED_APPS_SUAP:
        from conteudoportal.models import Documento

        niveis_superior = ['8-801', '7-704', '7-703', '7-702', '7-701', '6-604', '6-603', '6-602', '6-601', '5-502', '5-501', '4-402', '4-401']
        niveis_ebtt = ['D501', 'D404', 'D403', 'D402', 'D401', 'D304', 'D303', 'D302', 'D301', 'D202', 'D201', 'D102', 'D101']
        aperf = Titulacao.objects.get(codigo='24')
        espec = Titulacao.objects.get(codigo='25')
        mestr = Titulacao.objects.get(codigo='26')
        douto = Titulacao.objects.get(codigo='27')
        rscI = Titulacao.objects.get(codigo='48')
        rscII = Titulacao.objects.get(codigo='49')
        rscIII = Titulacao.objects.get(codigo='50')
        titulacoes = [None, aperf, espec, mestr, douto]

        arquivos = Documento.objects.get(titulo='Tabelas de Vencimentos de Docentes').arquivo_set.all()
        for arquivo in arquivos:
            nome = arquivo.descricao
            parametros = nome.split('-')
            tipo = parametros[0]
            jornada_str = parametros[1]
            d_ini = parametros[2]
            d_fim = parametros[3]

            if tipo == 'Superior':
                niveis = niveis_superior
            elif tipo == 'EBTT':
                niveis = niveis_ebtt
            else:
                return False, 'Erro em Tipo de Docente. Opções: "Superior" e "EBTT".'

            if jornada_str == '20':
                jornada = JornadaTrabalho.objects.get(nome='20 HORAS SEMANAIS')
            elif jornada_str == '40':
                jornada = JornadaTrabalho.objects.get(nome='40 HORAS SEMANAIS')
            elif jornada_str == 'DE':
                jornada = JornadaTrabalho.objects.get(nome='DEDICACAO EXCLUSIVA')
            else:
                return False, 'Erro em Jornada. Opções:"20", "40" e "DE".'

            if d_ini.split('.')[2] == '0000' and d_ini.split('.')[1] == '00' and d_ini.split('.')[0] == '00':
                data1 = None
            else:
                data1 = '{}-{}-{}'.format(d_ini.split('.')[2], d_ini.split('.')[1], d_ini.split('.')[0])
            if d_fim.split('.')[2] == '0000' and d_fim.split('.')[1] == '00' and d_fim.split('.')[0] == '00':
                data2 = None
            else:
                data2 = '{}-{}-{}'.format(d_fim.split('.')[2], d_fim.split('.')[1], d_fim.split('.')[0])

            filepath = cache_file(arquivo.arquivo.name)
            # IFMA/Tássio: Se sem arquivo = link externo = não entra
            if arquivo.arquivo and os.path.exists(filepath) and (filepath.endswith(('.xls', '.xlsx'))):
                df = pd.read_excel(filepath, header=None)
                nivel_idx = 0
                for _index, row in df.iterrows():
                    linha_ok = False
                    nivel = NivelVencimento.objects.get(codigo=niveis[nivel_idx])
                    valor_idx = 0
                    for _j, cell_value in enumerate(row):
                        str_val = cell_value
                        if isfloat(str_val):
                            valor = float(str_val)
                            # print nome, valor
                            if valor > 50 or valor == 0:
                                if valor_idx == 0:
                                    ValorPorNivelVencimentoDocente.objects.update_or_create(
                                        nivel=nivel, jornada_trabalho=jornada, data_inicio=data1, data_fim=data2, defaults={'valor': valor}
                                    )
                                elif 1 <= valor_idx <= 4:
                                    qs = ValorRetribuicaoTitulacao.objects.filter(
                                        nivel=nivel, jornada_trabalho=jornada, data_inicio=data1, data_fim=data2, titulacoes=titulacoes[valor_idx]
                                    )
                                    if not qs.exists():
                                        obj = ValorRetribuicaoTitulacao.objects.create(
                                            nivel=nivel, jornada_trabalho=jornada, data_inicio=data1, data_fim=data2, valor=valor
                                        )
                                    else:
                                        obj = qs[0]
                                        obj.valor = valor
                                        obj.save()
                                    if valor_idx == 1:
                                        obj.titulacoes.add(aperf)
                                    elif valor_idx == 2:
                                        obj.titulacoes.add(espec, rscI)
                                    elif valor_idx == 3:
                                        obj.titulacoes.add(mestr, rscII)
                                    elif valor_idx == 4:
                                        obj.titulacoes.add(douto, rscIII)
                                        linha_ok = True
                                        break
                                valor_idx += 1
                    if linha_ok:
                        nivel_idx += 1
                    if nivel_idx > 12:
                        break

        return True, 'OK'


def get_corpo_documento(calculo, corpo_padrao, tipo):
    corpo = ''
    if tipo == CalculoDocumento.DECLARACAO_NAO_AJUIZAMENTO:
        corpo = corpo_padrao
        corpo = corpo.replace('###NOME_DO_SERVIDOR###', calculo.servidor.pessoa_fisica.nome)
        corpo = corpo.replace('###MATRICULA_DO_SERVIDOR###', calculo.servidor.matricula)
        corpo = corpo.replace('###CARGO_DO_SERVIDOR###', calculo.servidor.cargo_emprego.nome)
        corpo = corpo.replace(
            '###LOTACAO_DO_SERVIDOR###',
            '{} ({})'.format(
                calculo.servidor.setor_lotacao and calculo.servidor.setor_lotacao.nome or '-',
                calculo.servidor.setor_lotacao and calculo.servidor.setor_lotacao.uo.nome or '-',
            ),
        )
        corpo = corpo.replace('###NUMERO_DO_PROCESSO###', calculo.portaria.processo.numero_processo)
        corpo = corpo.replace('##SIAPE_DO_SERVIDOR###', calculo.servidor.matricula)
        corpo = corpo.replace('###MOTIVO###', TIPO_CALCULO_CHOICES[calculo.tipo - 1][1].replace('Cálculo de ', ''))

    elif tipo == CalculoDocumento.AMPARO_LEGAL:
        corpo = corpo_padrao
        corpo = corpo.replace('###NUMERO_DO_PROCESSO###', calculo.portaria.processo.numero_processo)
        corpo = corpo.replace('###NOME_INTERESSADO###', calculo.servidor.pessoa_fisica.nome)
        corpo = corpo.replace('###SIGLA_SETOR_DESTINO###', 'DIGEPE')
        corpo = corpo.replace('###MOTIVO###', TIPO_CALCULO_CHOICES[calculo.tipo - 1][1].replace('Cálculo de ', ''))
        corpo = corpo.replace('###NOME_DO_SERVIDOR###', calculo.servidor.pessoa_fisica.nome)
        corpo = corpo.replace('###CARGO_DO_SERVIDOR###', calculo.servidor.cargo_emprego.nome)
        corpo = corpo.replace(
            '###UNIDADE###',
            '{} ({})'.format(
                calculo.servidor.setor_lotacao and calculo.servidor.setor_lotacao.nome or '-',
                calculo.servidor.setor_lotacao and calculo.servidor.setor_lotacao.uo.nome or '-',
            ),
        )

    elif tipo in (CalculoDocumento.NOTA_TECNICA_COM_PORTARIA, CalculoDocumento.NOTA_TECNICA_SEM_PORTARIA):
        valor = str(calculo.consolidacao).split('.')
        ext = dExtenso()
        reais = str(ext.getExtenso(valor[0], quebradelinhas=0))
        centavos = str(ext.getExtenso(valor[1], quebradelinhas=0))
        valor_extenso = f'{reais} reais'
        if centavos and centavos != '':
            valor_extenso += f' e {centavos} centavos'
        corpo = corpo_padrao
        corpo = corpo.replace('###MOTIVO###', TIPO_CALCULO_CHOICES[calculo.tipo - 1][1].replace('Cálculo de ', ''))
        corpo = corpo.replace('###NOME_DO_SERVIDOR###', calculo.servidor.pessoa_fisica.nome)
        corpo = corpo.replace('###MATRICULA_SERVIDOR###', calculo.servidor.matricula)
        corpo = corpo.replace(
            '###UNIDADE###',
            '{} ({})'.format(
                calculo.servidor.setor_lotacao and calculo.servidor.setor_lotacao.nome or '-',
                calculo.servidor.setor_lotacao and calculo.servidor.setor_lotacao.uo.nome or '-',
            ),
        )
        corpo = corpo.replace('#####,##', str(calculo.consolidacao))
        corpo = corpo.replace('###VALOR_POR_EXTENSO###', valor_extenso)

        if tipo == CalculoDocumento.NOTA_TECNICA_COM_PORTARIA:
            corpo = corpo.replace('######', str(calculo.portaria.numero))
            corpo = corpo.replace('##/##/###', str(calculo.portaria.data_portaria.strftime('%d/%m/%Y')))
            corpo = corpo.replace('###CAMPUS_PORTARIA###', calculo.portaria.campus.nome)

        if calculo.data_inicio and calculo.data_fim:
            corpo = corpo.replace('###PERIODO###', '{} a {}'.format(calculo.data_inicio.strftime('%d/%m/%Y'), calculo.data_fim.strftime('%d/%m/%Y')))
    return corpo


# IFMA/Tássio
def getHTMLFromView(view, lista_argumentos):
    response = view(*lista_argumentos)
    html = response.content.decode('utf-8')  # Bytes to String
    # Pegar html específico da view (abaixo de breadcrumbs e acima de links de rodapé)
    html = html.split('<div class="title-container">')[1].split('<ul class="action-links">')[0]
    # Recolocada tag HTML retirada acima
    html = '<div class="title-container">' + html
    return html


# IFMA/Tássio
def getHTMLFromCalculoView(view, lista_argumentos):
    html = getHTMLFromView(view, lista_argumentos)
    # Tirar botões superiores
    if '<ul class="action-bar">' in html:
        partes = html.split('<ul class="action-bar">')
        html = partes[0] + partes[1].split('</ul>')[-1]
    # Tirar botões de férias e outros (Informar valor de IRPF da Gratificação Natalina)
    while '<a class="btn' in html:
        partes = html.split('<a class="btn', maxsplit=1)
        html = partes[0] + partes[1].split('</a>', maxsplit=1)[1]
    # Incluir bordas nas tabelas
    html = '<style>table, th, td, tr {border: 1px solid; border-collapse: collapse;}</style>' + html
    return html
