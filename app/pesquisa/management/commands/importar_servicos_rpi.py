import datetime

import mechanicalsoup
from dateutil.relativedelta import relativedelta

from djtools.management.commands import BaseCommandPlus
from pesquisa.models import (
    AnuidadeRegistroPropriedadeIntelectual,
    PropriedadeIntelectual,
    RegistroPropriedadeIntelectual,
    ServicoRegistroPropriedadeIntelectual,
)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for pi in RegistroPropriedadeIntelectual.objects.filter(tipo=PropriedadeIntelectual.objects.get(descricao='Patente')):
            br = mechanicalsoup.StatefulBrowser()
            url = 'https://busca.inpi.gov.br/pePI/jsp/patentes/PatenteSearchBasico.jsp'
            try:
                br.open(url, timeout=100, verify=False)
                br.select_form('form[action="/pePI/servlet/LoginController"]')
            except Exception:
                continue
            br.submit_selected()

            url = 'https://busca.inpi.gov.br/pePI/jsp/patentes/PatenteSearchBasico.jsp'
            try:
                br.open(url, timeout=100, verify=False)
                br.select_form('form[action="/pePI/servlet/PatenteServletController"]')
            except Exception:
                continue
            br['NumPedido'] = f'{pi.numero_processo}'
            br.submit_selected()
            url_busca = 'https://busca.inpi.gov.br' + br.get_current_page().find_all('a')[8]['href']
            try:
                br.open(url_busca, timeout=100, verify=False)
            except Exception:
                continue
            if not pi.data:
                data_deposito = br.get_current_page().find_all('tr')[6].text.strip().split(' ')[-1].split('\t')[-1:][0]
                pi.data = datetime.datetime.strptime(data_deposito, '%d/%m/%Y').date()
                pi.save()
            if not pi.data_concessao:
                data_concessao = None
                try:
                    data_concessao = br.get_current_page().find_all('tr')[8].text.strip().split(' ')[-1].split('\t')[-1:][0]
                except Exception:
                    pass
                if data_concessao and data_concessao != '-':
                    pi.data_concessao = datetime.datetime.strptime(data_concessao, '%d/%m/%Y').date()
                    pi.save()
            try:
                lista_servicos = br.get_current_page().find_all('div', class_='accordion-content')[1].find_all('tr', class_='normal')
            except Exception:
                continue
            indice = 0
            total_servicos = len(lista_servicos)
            while indice < total_servicos:
                numero = lista_servicos[indice].find_all('td')[0].find('a').text.strip()

                protocolo = lista_servicos[indice].find_all('td')[10].text.strip()

                data_str = lista_servicos[indice].find_all('td')[11].text.strip()
                data = datetime.datetime.strptime(data_str, '%d/%m/%Y')
                descricao = lista_servicos[indice].find_all('td')[4].text.split(' ', 1)[1].strip()
                dados_pagamento = lista_servicos[indice].find_all('td')[9].text.strip()
                valor = ''
                tem_valor = lista_servicos[indice].find_all('td')[9].text.split('Valor: R$')
                if len(tem_valor) > 1:
                    valor = tem_valor[1].split(' ')[0].strip()
                if not ServicoRegistroPropriedadeIntelectual.objects.filter(
                    propriedadeintelectual=pi, numero=numero, protocolo=protocolo, data=data
                ).exists():
                    novo_servico = ServicoRegistroPropriedadeIntelectual()
                    novo_servico.propriedadeintelectual = pi
                    novo_servico.numero = numero
                    novo_servico.protocolo = protocolo
                    novo_servico.data = data
                    novo_servico.descricao = descricao
                    novo_servico.valor = valor
                    novo_servico.dados_pagamento = dados_pagamento
                    novo_servico.save()
                indice += 1
            lista_anuidades = br.get_current_page().find_all('div', class_='textoAnuidades')
            indice = 1
            total_anuidades = len(lista_anuidades)
            data_inicio_periodo = pi.data + relativedelta(years=2)
            inicio_ordinario = data_inicio_periodo
            fim_ordinario = inicio_ordinario + relativedelta(months=3)
            inicio_extraordinario = fim_ordinario + relativedelta(days=1)
            fim_extraordinario = inicio_extraordinario + (relativedelta(months=6) - relativedelta(days=1))
            if total_anuidades > 1:
                while indice < total_anuidades:
                    anuidade = lista_anuidades[indice].find_all('font', class_='normal')[0].text.split(':')[0].strip()
                    status = lista_anuidades[indice].find_all('font', class_='normal')[1].text
                    descricao_situacao = 'Pendente'
                    if status == 'Status: OK':
                        descricao_situacao = 'Pago'
                        gru = lista_anuidades[indice].find_all('font', class_='normal')[3].text.split(' ', 2)[1]
                        valor = lista_anuidades[indice].find_all('font', class_='normal')[3].text.split(' ', 4)[4][1:]

                        data_str = lista_anuidades[indice].find_all('font', class_='normal')[4].text.strip().split(' ')[2]
                        data = datetime.datetime.strptime(data_str, '%d/%m/%Y')
                    elif status == 'Status: ':
                        if len(lista_anuidades[indice].find_all('font', class_='normal')) > 6:
                            status = lista_anuidades[indice].find_all('font', class_='normal')[5].text
                            if status == 'Status: OK':
                                descricao_situacao = 'Pago'
                                gru = lista_anuidades[indice].find_all('font', class_='normal')[7].text.split(' ', 2)[1]
                                valor = lista_anuidades[indice].find_all('font', class_='normal')[7].text.split(' ', 4)[4][1:]

                                data_str = lista_anuidades[indice].find_all('font', class_='normal')[8].text.strip().split(' ')[2]
                                data = datetime.datetime.strptime(data_str, '%d/%m/%Y')

                    if AnuidadeRegistroPropriedadeIntelectual.objects.filter(propriedadeintelectual=pi, anuidade=anuidade).exists():
                        novo_servico = AnuidadeRegistroPropriedadeIntelectual.objects.filter(propriedadeintelectual=pi, anuidade=anuidade).first()
                    else:
                        novo_servico = AnuidadeRegistroPropriedadeIntelectual()
                    novo_servico.propriedadeintelectual = pi
                    novo_servico.anuidade = anuidade
                    if novo_servico.situacao != 'Pago':
                        novo_servico.situacao = descricao_situacao
                    novo_servico.inicio_ordinario = inicio_ordinario
                    novo_servico.fim_ordinario = fim_ordinario
                    novo_servico.inicio_extraordinario = inicio_extraordinario
                    novo_servico.fim_extraordinario = fim_extraordinario
                    if status == 'Status: OK':
                        novo_servico.gru = gru
                        novo_servico.data = data
                        novo_servico.valor = valor
                    novo_servico.save()
                    indice += 1
                    inicio_ordinario += relativedelta(years=1)
                    fim_ordinario = inicio_ordinario + relativedelta(months=3)
                    inicio_extraordinario = fim_ordinario + relativedelta(days=1)
                    fim_extraordinario = inicio_extraordinario + (relativedelta(months=6) - relativedelta(days=1))
            elif not AnuidadeRegistroPropriedadeIntelectual.objects.filter(propriedadeintelectual=pi).exists():
                novo_servico = AnuidadeRegistroPropriedadeIntelectual()
                novo_servico.propriedadeintelectual = pi
                novo_servico.anuidade = '3ª anuidade'
                novo_servico.situacao = 'Pendente'
                novo_servico.inicio_ordinario = inicio_ordinario
                novo_servico.fim_ordinario = fim_ordinario
                novo_servico.inicio_extraordinario = inicio_extraordinario
                novo_servico.fim_extraordinario = fim_extraordinario
                novo_servico.save()
