import datetime

from djtools.management.commands import BaseCommandPlus
from gestao.models import INDICADORES_DESATIVADOS, VARIAVEIS_GRUPOS, Indicador, PeriodoReferencia, Variavel
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        exibir_variaveis = False
        exibir_indicadores = True

        # Caso deseje ver um detalhamento por campus, basta deixar este atributo "True". O resultado é uma string csv
        # e pode ser copiado para uma planilha de excel.
        detalhar_por_campus = False

        if exibir_variaveis:
            print()
            print('- - - - -')
            print('Variáveis')
            print('- - - - -')
            print(
                'Ano de Referência: {} ({} à {})'.format(
                    PeriodoReferencia.get_ano_referencia(),
                    PeriodoReferencia.get_data_base().strftime('%d/%m/%Y'),
                    PeriodoReferencia.get_data_limite().strftime('%d/%m/%Y'),
                )
            )
            print('Data da consulta: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M')))
            print()

            for vg in VARIAVEIS_GRUPOS:
                variaveis = Variavel.objects.filter(sigla__in=vg.get('variaveis')).order_by('sigla')
                # variaveis = Variavel.objects.all().order_by('sigla')
                # variaveis = Variavel.objects.filter(sigla__in=['VO', 'I']).order_by('sigla')
                # variaveis = Variavel.objects.filter(sigla__in=['AM', 'AC', 'AE', 'AR', 'AJ', 'AI', 'AIC']).order_by('sigla')

                subtitulo = vg.get('subtitulo')
                titulo = vg.get('titulo')
                print()
                if subtitulo:
                    print(f'{titulo} ({subtitulo})')
                else:
                    print(titulo)

                if detalhar_por_campus:
                    uos = UnidadeOrganizacional.objects.suap().all()

                    csv_cols = 'Variavel;Nome;'
                    for uo in uos:
                        csv_cols += f'{uo.sigla};'
                    csv_cols += 'Tempo de Processamento'
                    print(csv_cols)

                    for v in variaveis:
                        inicio_calc = datetime.datetime.now().replace(microsecond=0)
                        csv_values = f'{v.sigla};{v.nome};'
                        for uo in uos:
                            valor = v.get_valor_formatado(uo=uo)
                            csv_values += f'{valor};'
                        fim_calc = datetime.datetime.now().replace(microsecond=0)
                        print(f'{csv_values}{fim_calc - inicio_calc}')
                else:
                    print('Sigla;Nome;Valor;Tempo de Processamento')
                    for v in variaveis:
                        inicio_calc = datetime.datetime.now().replace(microsecond=0)
                        valor = v.get_valor_formatado()
                        fim_calc = datetime.datetime.now().replace(microsecond=0)
                        print(f'{v.sigla};{v.nome};{valor};{fim_calc - inicio_calc}')

                    # print ''
                    # print ''

        if exibir_indicadores:
            print('- - - - - -')
            print('Indicadores')
            print('- - - - - -')
            print(
                'Ano de Referência: {} ({} à {})'.format(
                    PeriodoReferencia.get_ano_referencia(),
                    PeriodoReferencia.get_data_base().strftime('%d/%m/%Y'),
                    PeriodoReferencia.get_data_limite().strftime('%d/%m/%Y'),
                )
            )
            print('Data da consulta: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M')))
            print()

            for orgao_regulamentador in Indicador.ORGAO_REGULAMENTADOR_TIPO_CHOICES:
                # indicadores = Indicador.objects.all()
                indicadores = Indicador.objects.filter(orgao_regulamentador=orgao_regulamentador[0])
                # indicadores = Indicador.objects.filter(orgao_regulamentador=Indicador.ORGAO_REGULAMENTADOR_MEC)
                # indicadores = Indicador.objects.filter(orgao_regulamentador=Indicador.ORGAO_REGULAMENTADOR_OUTROS)
                indicadores = indicadores.order_by('orgao_regulamentador', 'sigla')

                # Indicadores que foram desavitados na auditoria referente ao ano de 2015, atendendo a pedido de Anna Catharina.
                indicadores = indicadores.all().exclude(sigla__in=INDICADORES_DESATIVADOS)

                print()
                titulo = orgao_regulamentador[1]
                print(titulo)

                if detalhar_por_campus:
                    uos = UnidadeOrganizacional.objects.suap().all()

                    csv_cols = 'Indicador;Nome;'
                    for uo in uos:
                        csv_cols += f'{uo.sigla};'
                    csv_cols += 'Tempo de Processamento'
                    print(csv_cols)

                    for i in indicadores:
                        inicio_calc = datetime.datetime.now().replace(microsecond=0)
                        csv_values = f'{i.sigla};{i.nome};'
                        for uo in uos:
                            valor = i.get_valor_formatado(uo=uo)
                            csv_values += f'{valor};'
                        fim_calc = datetime.datetime.now().replace(microsecond=0)
                        print(f'{csv_values}{fim_calc - inicio_calc}')
                else:
                    print('Sigla;Descrição;Valor;Fórmula;Fórmula Valorada;Tempo de Processamento')
                    for i in indicadores:
                        inicio_calc = datetime.datetime.now().replace(microsecond=0)
                        valor = i.get_valor_formatado()
                        formula_com_valor = i.get_formula_valorada()
                        fim_calc = datetime.datetime.now().replace(microsecond=0)
                        print(f'{i.sigla};{i.nome};{valor};{i.formula};{formula_com_valor};{fim_calc - inicio_calc};')
