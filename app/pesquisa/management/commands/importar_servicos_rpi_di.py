import datetime

import mechanicalsoup
from dateutil.relativedelta import relativedelta

from djtools.management.commands import BaseCommandPlus
from pesquisa.models import (
    AnuidadeRegistroPropriedadeIntelectual,
    DespachoINPIDI,
    PublicacaoPropriedadeIntelectual,
    RegistroPropriedadeIntelectual,
    ServicoRegistroPropriedadeIntelectual,
)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        numero_processo = options.get('numero_processo', False)
        queryset = RegistroPropriedadeIntelectual.objects.filter(tipo__descricao='Desenho Industrial')
        if numero_processo:
            queryset = queryset.filter(numero_processo=numero_processo)
        for pi in queryset:
            br = mechanicalsoup.StatefulBrowser()
            url = 'https://busca.inpi.gov.br/pePI/jsp/desenhos/DesenhoSearchBasico.jsp'
            try:
                br.open(url, timeout=100, verify=False)
                br.select_form('form[action="/pePI/servlet/LoginController"]')
            except Exception:
                continue
            br.submit_selected()

            url = 'https://busca.inpi.gov.br/pePI/jsp/desenhos/DesenhoSearchBasico.jsp'
            try:
                br.open(url, timeout=100, verify=False)
                br.select_form('form[action="/pePI/servlet/DesenhoServletController"]')
            except Exception:
                continue
            br['NumPedido'] = f'{pi.numero_processo}'
            br.submit_selected()
            url_busca = 'https://busca.inpi.gov.br' + br.get_current_page().find_all('a')[8]['href']
            try:
                br.open(url_busca, timeout=100, verify=False)
            except Exception:
                continue
            data_deposito = br.get_current_page().find_all('div', class_='accordions')[0].find_all('td')[4].text.strip().split(' ')[-1]
            pi.data = datetime.datetime.strptime(data_deposito, '%d/%m/%Y').date()
            pi.situacao = br.get_current_page().find_all('div', class_='accordions')[0].find_all('td')[5].text.strip()
            pi.locarno_edicao = br.get_current_page().find_all('div', class_='accordions')[3].find_all('td')[3].text.strip().split(' ')[-1]
            pi.locarno_codigo = br.get_current_page().find_all('div', class_='accordions')[3].find_all('td')[4].text.strip().split(' ')[-1]
            pi.locarno_descricao = br.get_current_page().find_all('div', class_='accordions')[3].find_all('td')[5].text.strip()
            if not pi.titulo:
                pi.titulo = br.get_current_page().find_all('div', class_='accordions')[2].find_all('td')[1].text.strip()
            if not pi.inventores:
                pi.inventores = br.get_current_page().find_all('div', class_='accordions')[4].find_all('td')[3].text.strip()
            if not pi.titulares:
                pi.titulares = br.get_current_page().find_all('div', class_='accordions')[5].find_all('td')[3].text.strip()
            data_concessao = br.get_current_page().find_all('div', class_='accordions')[7].find_all('td')[4].text.strip()
            if data_concessao:
                pi.data_concessao = datetime.datetime.strptime(data_concessao, '%d/%m/%Y').date()
            pi.save()
            if 'Petições' in br.get_current_page().find_all('div', class_='accordions')[8].find_all('div')[0].find_all('font')[0].text:
                lista_servicos = (
                    br.get_current_page()
                    .find_all('div', class_='accordions')[8]
                    .find_all('div')[0]
                    .find_all('div')[0]
                    .find_all('table')[0]
                    .find_all('tr', {'bgcolor': '#e5e5e5'})
                )
            else:
                lista_servicos = (
                    br.get_current_page()
                    .find_all('div', class_='accordions')[9]
                    .find_all('div')[0]
                    .find_all('div')[0]
                    .find_all('table')[0]
                    .find_all('tr', {'bgcolor': '#e5e5e5'})
                )
            indice = 0
            total_servicos = len(lista_servicos)
            while indice < total_servicos:
                numero = lista_servicos[indice].find_all('td')[8].find('a').text.strip()
                protocolo = lista_servicos[indice].find_all('td')[5].text
                data_str = lista_servicos[indice].find_all('td')[6].text.strip()
                data = datetime.datetime.strptime(data_str, '%d/%m/%Y')
                descricao = lista_servicos[indice].find_all('td')[12].text.strip().split('\n\t\t')[1].strip()
                dados_pagamento = lista_servicos[indice].find_all('td')[0].find_all('font')[2].text.strip()
                valor = ''
                tem_valor = lista_servicos[indice].find_all('td')[0].text.split('Valor: R$')
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
            if 'Publicações' in br.get_current_page().find_all('div', class_='accordions')[9].find_all('div')[0].find_all('font')[0].text:
                lista_publicacoes = (
                    br.get_current_page().find_all('div', class_='accordions')[9].find_all('table')[0].find_all('tr', {'bgcolor': '#e5e5e5'})
                )
            else:
                lista_publicacoes = (
                    br.get_current_page().find_all('div', class_='accordions')[10].find_all('table')[0].find_all('tr', {'bgcolor': '#e5e5e5'})
                )
            total_pub = len(lista_publicacoes)
            indice = 0
            while indice < total_pub:
                numero_rpi = lista_publicacoes[indice].find_all('td')[0].text
                despacho = lista_publicacoes[indice].find_all('td')[2].find_all('font')[0].text.strip()
                data_pub = lista_publicacoes[indice].find_all('td')[1].text.strip()
                complemento = lista_publicacoes[indice].find_all('td')[9].text.strip()
                if not PublicacaoPropriedadeIntelectual.objects.filter(propriedadeintelectual=pi, rpi=numero_rpi, despacho=despacho).exists():
                    desp = DespachoINPIDI.objects.filter(descricao=despacho).first()
                    novo_despacho = PublicacaoPropriedadeIntelectual()
                    novo_despacho.propriedadeintelectual = pi
                    novo_despacho.rpi = numero_rpi
                    novo_despacho.data = datetime.datetime.strptime(data_pub, '%d/%m/%Y').date()
                    novo_despacho.despacho = despacho
                    novo_despacho.codigo = desp and desp.codigo
                    if complemento:
                        novo_despacho.complemento = complemento
                    novo_despacho.save()
                indice += 1
            if not pi.primeira_rpi:
                pi.primeira_rpi = lista_publicacoes[indice - 1].find_all('td')[0].text
                pi.save()
            if pi.data_concessao and not AnuidadeRegistroPropriedadeIntelectual.objects.filter(propriedadeintelectual=pi).exists():
                data_inicio = pi.data + relativedelta(years=4)
                data_fim = pi.data + relativedelta(years=5)
                novo_servico = AnuidadeRegistroPropriedadeIntelectual()
                novo_servico.propriedadeintelectual = pi
                novo_servico.anuidade = 'Primeiro pagamento (2ª quinquênio)'
                novo_servico.situacao = 'Pendente'
                novo_servico.inicio_ordinario = data_inicio
                novo_servico.fim_ordinario = data_fim
                novo_servico.save()

                data_inicio = data_inicio + relativedelta(years=5)
                data_fim = data_fim + relativedelta(years=5)
                novo_servico = AnuidadeRegistroPropriedadeIntelectual()
                novo_servico.propriedadeintelectual = pi
                novo_servico.anuidade = 'Renovação 1'
                novo_servico.situacao = 'Pendente'
                novo_servico.inicio_ordinario = data_inicio
                novo_servico.fim_ordinario = data_fim
                novo_servico.save()

                data_inicio = data_inicio + relativedelta(years=5)
                data_fim = data_fim + relativedelta(years=5)
                novo_servico = AnuidadeRegistroPropriedadeIntelectual()
                novo_servico.propriedadeintelectual = pi
                novo_servico.anuidade = 'Renovação 2'
                novo_servico.situacao = 'Pendente'
                novo_servico.inicio_ordinario = data_inicio
                novo_servico.fim_ordinario = data_fim
                novo_servico.save()

                data_inicio = data_inicio + relativedelta(years=5)
                data_fim = data_fim + relativedelta(years=5)
                novo_servico = AnuidadeRegistroPropriedadeIntelectual()
                novo_servico.propriedadeintelectual = pi
                novo_servico.anuidade = 'Renovação 3'
                novo_servico.situacao = 'Pendente'
                novo_servico.inicio_ordinario = data_inicio
                novo_servico.fim_ordinario = data_fim
                novo_servico.save()
