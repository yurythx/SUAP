import datetime

import mechanicalsoup

from djtools.management.commands import BaseCommandPlus
from pesquisa.models import RegistroPropriedadeIntelectual, ServicoRegistroPropriedadeIntelectual


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for pi in RegistroPropriedadeIntelectual.objects.filter(tipo__descricao='Software'):
            br = mechanicalsoup.StatefulBrowser()
            url = 'https://busca.inpi.gov.br/pePI/jsp/programas/ProgramaSearchBasico.jsp'
            try:
                br.open(url, timeout=100, verify=False)
                br.select_form('form[action="/pePI/servlet/LoginController"]')
            except Exception:
                continue
            br.submit_selected()

            url = 'https://busca.inpi.gov.br/pePI/jsp/programas/ProgramaSearchBasico.jsp'
            try:
                br.open(url, timeout=100, verify=False)
                br.select_form('form[action="/pePI/servlet/ProgramaServletController"]')
            except Exception:
                continue
            br['NumPedido'] = f'{pi.numero_processo}'
            br.submit_selected()
            url_busca = 'https://busca.inpi.gov.br' + br.get_current_page().find_all('a')[8]['href']
            try:
                br.open(url_busca, timeout=100, verify=False)
            except Exception:
                continue
            data_deposito = br.get_current_page().find_all('tr')[7].text.strip().split(' ')[-1]
            pi.data = datetime.datetime.strptime(data_deposito, '%d/%m/%Y').date()
            pi.save()
            lista_servicos = br.get_current_page().find_all('div', class_='accordion-content')[0].find_all('tr', class_='normal')
            indice = 0
            total_servicos = len(lista_servicos)
            while indice < total_servicos:
                numero = lista_servicos[indice].find_all('td')[9].find('a').text.strip()
                protocolo = lista_servicos[indice].find_all('td')[5].text
                data_str = lista_servicos[indice].find_all('td')[6].text.strip()
                data = datetime.datetime.strptime(data_str, '%d/%m/%Y')
                descricao = lista_servicos[indice].find_all('td')[9].text.strip().split('  ')[-1]
                dados_pagamento = lista_servicos[indice].find_all('td')[0].text.strip()
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
