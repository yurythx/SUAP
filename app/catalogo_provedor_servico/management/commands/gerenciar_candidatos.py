import cmd
import datetime

import tqdm
from django.core.management.base import BaseCommand

from djtools.utils import send_mail
from processo_seletivo.models import CandidatoVaga, Edital
from rh.models import PessoaFisica


class GerenciarCandidato(cmd.Cmd):
    prompt = '[PS] '
    doc_header = 'Comandos disponíveis (digite help <comando>):'
    misc_header = 'Outros comandos do help:'
    undoc_header = 'Comandos não documentados:'
    nohelp = '*** Nenhum help para %s'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paginacao = 30

    def pergunta_continuar(self):
        sim_nao = input('Deseja continuar [S/N]? ')

        return bool(sim_nao and sim_nao.upper() == 'S')

    def preloop(self):
        self.stdout.write('\033[H\033[J')
        self.stdout.write('Gerenciamento básico dos candidatos de processo seletivo\n')
        self.stdout.write(''.join(['-' * 60, '\n\n']))

    def do_configurar(self, arg):
        """Configurações geraos."""
        leitura = input(f'Paginação desejada, atual {self.paginacao}: ')
        if leitura is not None and leitura != '':
            try:
                self.paginacao = int(leitura)
            except Exception:
                self.stdout.write('O valor digitado deve ser um número inteiro.\n\n')

    def do_listar_editais(self, arg):
        """Lista todos os editais em período de matrícula."""
        agora = datetime.datetime.now().date()

        self.stdout.write('Lista dos editais com períoro de inscrição aberto.\n')
        self.stdout.write(''.join(['-' * 50, '\n']))
        for edital in Edital.objects.filter(data_inicio_matricula__lte=agora, data_fim_matricula__gte=agora):
            self.stdout.write(f'{edital.pk} - {edital.descricao}\n')
        self.stdout.write('\n')

    def do_listar_candidatos(self, arg):
        """Lista os candidatos de um edital."""

        def cabecalho(edital):
            self.stdout.write('\033[H\033[J')
            self.stdout.write(f'Edital: {edital.descricao}\n')
            self.stdout.write(''.join(['-' * 60, '\n']))

        self.stdout.write('Lista dos candidatos.\n')
        self.stdout.write(''.join(['-' * 50, '\n']))

        edital = None
        edital = input('Digite o código do edital: ')

        if edital is None:
            return

        try:
            edital = Edital.objects.get(pk=int(edital))
            self.stdout.write(f'Edital: {edital.descricao}')
        except Exception as e:
            self.stdout.write('Ocorreu algum problema ao buscar edital.\n')
            self.stdout.write(f'{e}\n')
            return

        situacaoes = dict(CandidatoVaga.SITUACAO_CHOICES)
        candidatos_vaga = CandidatoVaga.objects.filter(candidato__edital=edital)

        while True:
            i = 0
            opcao = ''

            if not candidatos_vaga.exists():
                self.stdout.write('Nenhum dado a listar.\n')
                break

            for candidato in candidatos_vaga:
                if i % self.paginacao == 0:
                    if i > 0:
                        opcao = input('Opções, [P]arar, [C]ontiuar, [F]iltrar, [O]rdenar: ')

                        if opcao.upper() != 'C':
                            break
                    cabecalho(edital)
                    self.stdout.write(f'{"CPF":<15} {"Nome":<50} {"Situação":<20} Convocação\n')

                situacao = '-'
                if candidato.situacao is not None:
                    situacao = situacaoes[candidato.situacao]

                self.stdout.write(f'{candidato.candidato.cpf: <15} {candidato.candidato.nome: <50} {situacao:<20} {candidato.convocacao}\n')
                i += 1

            if opcao.upper() == 'F':
                cabecalho(edital)
                filtro = input('Digite o filtro desejado, [S]ituação ou [C]onvocação: ')
                if filtro.upper() == 'C':
                    convocacao = input('Entre com a convocação: ')
                    try:
                        candidatos_vaga_tmp = CandidatoVaga.objects.filter(candidato__edital=edital)
                        candidatos_vaga = candidatos_vaga_tmp.filter(convocacao=int(convocacao))
                    except Exception as e:
                        self.stdout.write('Ocorreu erro ao filtrar pela convocação informada.\n')
                        self.stdout.write(str(e))
                elif filtro.upper() == 'S':
                    self.stdout.write('Situações disponíveis para escolha:\n')
                    for id, descricao in situacaoes.items():
                        self.stdout.write(f'\t{id:<2} - {descricao}\n')
                    situacao = input('Entre com a situação escolhida: ')
                    try:
                        candidatos_vaga_tmp = CandidatoVaga.objects.filter(candidato__edital=edital)
                        candidatos_vaga = candidatos_vaga_tmp.filter(situacao=int(situacao))
                    except Exception as e:
                        self.stdout.write('Ocorreu erro ao filtrar pela situação informada.\n')
                        self.stdout.write(str(e))
            elif opcao.upper() == 'O':
                cabecalho(edital)
                filtro = input('Digite a coluna a ordenar, [C]PF, [N]ome, [S]ituação ou C[O]nvocação: ')

                filtros = {'C': 'candidato__cpf', 'N': 'candidato__nome', 'S': 'situacao', 'O': 'convocacao'}

                ordem = filtros.get(filtro.upper())
                if ordem is not None:
                    candidatos_vaga = candidatos_vaga.order_by()
                    candidatos_vaga = candidatos_vaga.order_by(ordem)
            else:
                break

    def do_alterar_cpf_candidato(self, arg):
        """Altera o CPF de um candidato para um determinado edital."""
        self.stdout.write('Altera o CPF de candidato em um edital.\n')
        self.stdout.write(''.join(['-' * 50, '\n']))

        edital = None
        edital = input('Digite o código do edital: ')

        if edital is None:
            return

        try:
            edital = Edital.objects.get(pk=int(edital))
            self.stdout.write(f'Edital: {edital.descricao}\n')
        except Exception as e:
            self.stdout.write('Ocorreu algum problema ao buscar edital.\n')
            self.stdout.write(f'{e}\n')
            return

        candidato_vaga = None
        candidato_vaga = input('Digite o CPF atual: ')

        if candidato_vaga is None:
            return

        try:
            candidato_vaga = CandidatoVaga.objects.get(candidato__edital=edital, candidato__cpf=candidato_vaga)
            self.stdout.write(f'Candidato: {candidato_vaga.candidato.nome}\n')
        except Exception as e:
            self.stdout.write('Ocorreu algum problema ao buscar candidato com os dados fornecidos.\n')
            self.stdout.write(f'{e}\n')
            return

        novo_cpf = None
        novo_cpf = input('Digite o novo CPF: ')

        if novo_cpf is None:
            return

        salvar = True

        outro_candidato = CandidatoVaga.objects.filter(candidato__edital=edital, candidato__cpf=novo_cpf).exclude(pk=candidato_vaga.pk)
        if outro_candidato.exists():
            outro_candidato = outro_candidato[0]
            self.stdout.write(f'Existe outro candidato com esse CPF: {outro_candidato.candidato.nome}\n')

            if not self.pergunta_continuar():
                salvar = False

        pessoa_fisica = PessoaFisica.objects.filter(cpf=novo_cpf)
        if pessoa_fisica.exists():
            pessoa_fisica = pessoa_fisica[0]
            self.stdout.write(f'Existe uma pessoa física com esse CPF: {pessoa_fisica.nome}\n')

            if not self.pergunta_continuar():
                salvar = False

        if salvar:
            candidato_vaga.candidato.cpf = novo_cpf
            candidato_vaga.candidato.save()
            self.stdout.write('Alteração realizada.\n')

    def do_matricula_enviar_email_candidato(self, arg):
        """Envia um e-mail para os candidatos de um processo de matrícula."""
        """Altera o CPF de um candidato para um determinado edital."""
        self.stdout.write('Envia um e-mail para os candidatos em um processo de matrícula.\n')
        self.stdout.write(''.join(['-' * 50, '\n']))

        edital = None
        edital = input('Digite o código do edital: ')

        if edital is None:
            return

        try:
            edital = Edital.objects.get(pk=int(edital))
            self.stdout.write(f'Edital: {edital.descricao}\n')
        except Exception as e:
            self.stdout.write('Ocorreu algum problema ao buscar edital.\n')
            self.stdout.write(f'{e}\n')
            return

        email_file = None
        email_file = input('Nome do arquivo contendo o e-mail: ')
        email_assunto = input('Assunto do e-mail: ')
        email_from = input('E-mail do remetente: ')
        email_html = input('O e-mail é html? (S/N): ')

        if email_file is None or email_assunto is None or email_from is None or email_html is None:
            return

        email_texto = ''
        with open(email_file) as fd:
            email_texto = ''.join(fd.readlines())

        candidatos_vaga = CandidatoVaga.objects.filter(candidato__edital=edital, situacao__isnull=True, convocacao__gt=0)

        for candidato_vaga in tqdm.tqdm(candidatos_vaga):
            send_mail(assunto=email_assunto, mensagem=email_texto, de=email_from, para=candidato_vaga.candidato.email)

    def do_exit(self, arg):
        """Sai do gerenciador de candidatos."""
        return True


class Command(BaseCommand):
    def handle(self, *args, **options):
        gerenciar_candidato = GerenciarCandidato()
        gerenciar_candidato.cmdloop()
