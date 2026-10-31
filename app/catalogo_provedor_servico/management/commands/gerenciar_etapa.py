import cmd
import json

import tqdm
from django.core.management.base import BaseCommand

from catalogo_provedor_servico.models import Servico, Solicitacao, SolicitacaoEtapa


class Dado:
    def __init__(self, titulo, campo, width):
        self.titulo = titulo
        self.campo = campo
        self.width = width


class Tabela:
    def __init__(self, titulo, stdout, stdin, paginacao=30):
        self.titulo = titulo
        self.stdout = stdout
        self.stdin = stdin
        self.paginacao = paginacao
        self.campos = []

    def print_titulo(self):
        self.stdout('\033[H\033[J')
        self.stdout(self.titulo)
        self.stdout('')

    def add_campo(self, titulo, campo, width):
        self.campos.append(Dado(titulo=titulo, campo=campo, width=width))

    def run(self, dados):
        cabecalho = []
        cabecalho_linha = []

        for campo in self.campos:
            cabecalho.append(f'{campo.titulo:<{campo.width}s}')
            cabecalho_linha.append('=' * campo.width)

        cabecalho = ' '.join(cabecalho)
        cabecalho_linha = ' '.join(cabecalho_linha)

        if not dados.exists():
            self.print_titulo()
            self.stdout('Nenhum dado a listar.')
        else:
            i = 0
            for dado in dados:
                if i % self.paginacao == 0:
                    if i > 0:
                        opcao = self.stdin('Opções: [P]arar, [C]ontinuar: ')
                        if opcao.upper() != 'C':
                            break

                    self.print_titulo()
                    self.stdout(cabecalho)
                    self.stdout(cabecalho_linha)

                linha = []
                for campo in self.campos:
                    valor = getattr(dado, campo.campo)

                    if not isinstance(type(valor), str):
                        valor = str(valor)

                    valor = valor[0 : campo.width]
                    linha.append(f'{valor:<{campo.width}s}')

                self.stdout(' '.join(linha))
                i += 1
        self.stdout('')


class GerenciarEtapa(cmd.Cmd):
    prompt = '[PS] '
    doc_header = 'Comandos disponíveis (digite help <comando>):'
    misc_header = 'Outros comandos do help:'
    undoc_header = 'Comandos não documentados:'
    nohelp = '*** Nenhum help para %s'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paginacao = 30

    def input(self, texto):
        valor = None
        valor = input(texto)
        return valor

    def pergunta_continuar(self):
        sim_nao = input('Deseja continuar [S/N]? ')

        return bool(sim_nao and sim_nao.upper() == 'S')

    def stdout(self, texto):
        self.stdout.write(f'{texto}\n')

    def preloop(self):
        self.stdout.write('\033[H\033[J')
        self.stdout.write('Gerenciamento dos Dados da Etapa\n')
        self.stdout.write(''.join(['-' * 60, '\n\n']))

    def do_listar_servicos(self, arg):
        """Lista todos os serviços cadastrados."""
        tabela = Tabela(titulo='Listagem dos Serviços', stdout=self.stdout, stdin=input, paginacao=self.paginacao)
        tabela.add_campo(titulo='ID', campo='id_servico_portal_govbr', width=4)
        tabela.add_campo(titulo='Título', campo='titulo', width=70)
        tabela.add_campo(titulo='Ativo', campo='ativo', width=5)
        tabela.run(Servico.objects.all())

    def do_listar_solicitacoes(self, arg):
        """Lista as solicitações de um serviço."""
        tabela = Tabela(titulo='Listagem das Solicitações', stdout=self.stdout, stdin=input, paginacao=self.paginacao)
        tabela.add_campo(titulo='Id', campo='id', width=5)
        tabela.add_campo(titulo='CPF', campo='cpf', width=15)
        tabela.add_campo(titulo='Nome', campo='nome', width=50)
        tabela.add_campo(titulo='Status', campo='status', width=10)

        codigo = self.input('Entre com o código do serviço: ')

        if codigo is not None:
            tabela.run(Solicitacao.objects.filter(servico__id_servico_portal_govbr=codigo))

    def do_mostrar_formularios(self, arg):
        """Apresenta os formulários contidos nas etapas."""
        solicitacao = None
        solicitacao = self.input('Digite o id de uma solicitação, preferencialmente uma com todas as etapas: ')

        if solicitacao is not None:
            dados_apresentar = {}
            try:
                solicitacao = Solicitacao.objects.get(pk=solicitacao)
                for etapa in solicitacao.solicitacaoetapa_set.all().order_by('numero_etapa'):
                    key = etapa.numero_etapa
                    dados_apresentar[key] = []
                    dados = etapa.get_dados_as_json()

                    dados_apresentar[key].append(f'Etapa: {dados["nome"]}')
                    dados_apresentar[key].append(f'Número da Etapa: {etapa.numero_etapa}')
                    dados_apresentar[key].append('-' * 30)
                    dados_apresentar[key].append('Campos:')

                    for campo in dados['formulario']:
                        dados_apresentar[key].append('*' * 30)
                        for nome, valor in campo.items():
                            if nome in ['choices_resource_id', 'choices', 'value']:
                                continue
                            dados_apresentar[key].append(f'{nome}: {valor}')
                        dados_apresentar[key].append('')
                cont = 0
                for linhas in dados_apresentar.values():
                    etapa_cabecalho = f'{linhas[0]}\n{linhas[1]}\n{linhas[2]}'
                    for linha in linhas[3:]:
                        if cont % self.paginacao == 0:
                            if cont > 0:
                                opcao = self.input('Opções: [P]arar, [C]ontinuar: ')
                                if opcao.upper() != 'C':
                                    return
                            self.stdout('\033[H\033[J')
                            self.stdout(etapa_cabecalho)
                        self.stdout(linha)
                        cont += 1
                    opcao = self.input('Opções: [P]arar, [C]ontinuar: ')
                    if opcao.upper() != 'C':
                        return
                    cont = 0

            except Exception as e:
                self.stdout('Algum problema ao tentar processar as etapas.')
                self.stderr.write(str(e))

    def do_alterar_campo(self, arg):
        """Altera um campo existeste em um formulário"""
        solicitacao = None
        solicitacao = self.input('Digite o id de uma solicitação, preferencialmente que contenha a etapa: ')
        if solicitacao is None:
            return

        solicitacao = Solicitacao.objects.filter(pk=solicitacao)
        if solicitacao.exists():
            solicitacao = solicitacao.first()
        else:
            self.stdout('Solicitação não encontrada!')
            return

        etapa_solicitacao = self.input('Digite o número da etapa: ')
        if etapa_solicitacao is None or etapa_solicitacao == '':
            self.stdout('O número da etapa não pode ser vázio.')
            return

        etapa_solicitacao = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=etapa_solicitacao)
        if etapa_solicitacao.exists():
            etapa_solicitacao = etapa_solicitacao.first()
        else:
            self.stdout('A etapa solicitada não encontrada!')

        campo_solicitacao = self.input('Digite o campo a alterar: ')
        if campo_solicitacao is None or campo_solicitacao == '':
            self.stdout('O campo não pode ser vázio.')
            return

        atributo_nome = self.input('Digite o atributo a ser modificado, caso não exista será inserido: ')
        if atributo_nome is None or atributo_nome == '':
            self.stdout('O nome do atributo não pode ser vázio.')
            return

        if atributo_nome == 'name':
            self.stdout("Não é possível alterar o atributo '{atributo_nome}.")
            return

        atributo_valor = self.input('Digite o valor do atributo: ')
        if atributo_valor is None:
            atributo_valor = ''

        etapas_processar = SolicitacaoEtapa.objects.filter(
            solicitacao__servico=solicitacao.servico, numero_etapa=etapa_solicitacao.numero_etapa
        ).exclude(solicitacao__status__in=Solicitacao.STATUS_DEFINITIVOS)

        alterados = 0
        for etapa in tqdm.tqdm(etapas_processar):
            dados_etapa = etapa.get_dados_as_json()
            salvar_etapa = False
            dados_formulario = []
            for campo in dados_etapa['formulario']:
                if campo['name'] == campo_solicitacao:
                    if isinstance(campo[atributo_nome], int):
                        atributo_valor = int(atributo_valor)
                    elif isinstance(campo[atributo_nome], bool):
                        atributo_valor = atributo_valor == 'True'

                    campo[atributo_nome] = atributo_valor
                    salvar_etapa = True
                dados_formulario.append(campo)

            if salvar_etapa:
                dados_etapa['formulario'] = dados_formulario
                etapa_solicitacao.dados = json.dumps(dados_etapa, indent=4)
                etapa_solicitacao.save()
                alterados += 1

    def do_exit(self, arg):
        """Sai do gerenciador de candidatos."""
        return True


class Command(BaseCommand):
    def handle(self, *args, **options):
        gerenciar_etapa = GerenciarEtapa()
        gerenciar_etapa.cmdloop()
