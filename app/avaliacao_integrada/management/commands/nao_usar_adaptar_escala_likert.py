import hashlib
import os
import re
import sys

from django.db import transaction
from django.db.models import Count
from django.utils.text import slugify

from avaliacao_integrada.models import EscalaLikert, Indicador, NivelEscalaLikert, OpcaoResposta, Resposta
from djtools.management.commands import BaseCommandPlus, bcolors

UNICA_ESCOLHA = Indicador.UNICA_ESCOLHA  # 'Única Escolha' (5)
FAIXA_NUMERICA = 8  # 'Escala Padrão'. Constante removida de Indicador, substituida por ESCALA_LIKERT
GRAU_SATISFACAO = 9  # 'Grau de Satisfação'. Constante removida de Indicador, substituida por ESCALA_LIKERT
ESCALA_LIKERT = Indicador.ESCALA_LIKERT  # 'Escala Likert' (99)
MULTIPLA_ESCOLHA = Indicador.MULTIPLA_ESCOLHA  # (6)
TIPOS_RESPOSTAS = (UNICA_ESCOLHA, FAIXA_NUMERICA, GRAU_SATISFACAO, ESCALA_LIKERT, MULTIPLA_ESCOLHA)

TIPOS_RESPOSTAS_PARSE = {
    UNICA_ESCOLHA: '5 - Única Escolha',
    FAIXA_NUMERICA: '8 - Faixa Númerica (Escala Padrão)',
    GRAU_SATISFACAO: '9 - Grau de Satisfação',
    ESCALA_LIKERT: '99 - Escala Likert',
    MULTIPLA_ESCOLHA: '6 - Multipla escolha',
}
# Função para remover os caracteres ANSI


def remover_caracteres_ansi(texto):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', texto)


# Classe Tee adaptada para remover caracteres ANSI ao gravar no arquivo


class Tee:
    def __init__(self, *files):
        self.files = files

    def write(self, obj):
        # Remover caracteres ANSI antes de escrever nos arquivos
        texto_sem_ansi = remover_caracteres_ansi(obj)
        for f in self.files:
            f.write(texto_sem_ansi)

    def flush(self):
        for f in self.files:
            f.flush()


class Command(BaseCommandPlus):
    HASH_NIVES_ESCALA = {}
    NIVEIS_PARSE = {UNICA_ESCOLHA: {'Discordo Parcilamente': 'Discordo Parcialmente', 'Discordo parcilamente': 'Discordo Parcialmente'}}

    help = 'Processa os dados e redireciona a saída para um arquivo'

    def add_arguments(self, parser):
        # Define um argumento posicional obrigatório chamado "arquivo"
        parser.add_argument(
            'path_arquivo_saida',
            type=str,
            help='Especifique o nome do arquivo de saída para armazenar os resultados do processamento.',
            nargs='?',  # Permite que o argumento seja opcional
            default=None,  # Define o valor padrão se não for passado
        )

        parser.add_argument(
            '--list',
            '-l',
            action='store_true',
            help='Lista itens',
        )

    def get_itens(self, escala: EscalaLikert) -> set[str]:
        niveis = set()

        for nivel in escala.get_niveis():
            niveis.add(nivel)

        for dados in self.HASH_NIVES_ESCALA.values():
            if escala.id == dados['escala_id']:
                niveis.update(dados['sniveis'])
        return niveis

    def get_nivel(self, item: str, escala: EscalaLikert) -> NivelEscalaLikert:
        item_sfy = slugify(item)
        for nivel in escala.get_niveis():
            if item_sfy == slugify(nivel):
                return nivel
        raise ValueError(f'Item não encontrado {item}')

    def define_constante_niveis_escala_hash(self):
        def get_hash(escala: EscalaLikert = None, iniciais_maiusculas: bool = False):
            sniveis = []
            for nivel in escala.get_niveis():
                descricao = nivel.descricao
                if nivel.emoji:
                    descricao = f'{nivel.emoji!s} {nivel.descricao}'
                descricao_iniciais_maiusculas = ' '.join(word.capitalize() for word in descricao.split())
                if iniciais_maiusculas:
                    sniveis.append(descricao_iniciais_maiusculas)
                else:
                    sniveis.append(descricao)
            escala_str = ''.join(snivel.replace(' ', '') for snivel in sorted(sniveis))
            codigo_hash = hashlib.sha256(escala_str.encode('utf-8')).hexdigest()
            return sniveis, codigo_hash

        escala = EscalaLikert.objects.get(nome='Escala Padrão')
        nniveis = (
            ['Concordo', 'Concordo Parcialmente', 'Desconheço', 'Discordo', 'Discordo Parcialmente'],
            ['Concordo', 'Concordo Parcialmente', 'Desconheço', 'Discordo', 'Discordo Parcilamente'],
            ['Concordo', 'Concordo Parcialmente', 'Discordo Parcilamente', 'Discordo', 'Desconheço'],
            ['Concordo', 'Concordo parcialmente', 'Discordo parcilamente', 'Discordo', 'Desconheço'],
            ['Concordo', 'Concordo parcialmente', 'Desconheço', 'Discordo', 'Discordo parcialmente'],
        )
        for sniveis in nniveis:
            escala_str = ''.join(snivel.replace(' ', '') for snivel in sorted(sniveis))
            codigo_hash = hashlib.sha256(escala_str.encode('utf-8')).hexdigest()
            self.HASH_NIVES_ESCALA[codigo_hash] = {'escala_id': escala.id, 'escala_nome': escala.nome, 'sniveis': sorted(sniveis)}

        for escala in EscalaLikert.objects.all():
            sniveis, codigo_hash = get_hash(escala, False)
            self.HASH_NIVES_ESCALA[codigo_hash] = {'escala_id': escala.id, 'escala_nome': escala.nome, 'sniveis': sorted(sniveis)}

            sniveis, codigo_hash = get_hash(escala, True)
            self.HASH_NIVES_ESCALA[codigo_hash] = {'escala_id': escala.id, 'escala_nome': escala.nome, 'sniveis': sorted(sniveis)}

    def imprimir_detalhes_dados(self, qs_resposta):
        # self.stdout.write(qs_resposta.query)
        qs_resposta_sum = (
            qs_resposta.values('respondente__avaliacao', 'nivel_escala', 'indicador__tipo_resposta', 'valor')
            .annotate(total=Count('id'))
            .values('respondente__avaliacao', 'nivel_escala', 'indicador__tipo_resposta', 'valor', 'total')
            .order_by('respondente__avaliacao', 'nivel_escala', 'indicador__tipo_resposta')
        )
        for sumario in qs_resposta_sum:
            self.stdout.write(sumario)

        qs_indicador = qs_resposta.values_list('indicador', flat=True)
        sindicadores = set(qs_indicador)
        self.stdout.write(f'\t\t{bcolors.ENDC}Indicadores: ', sindicadores or 0)

    def adaptar(self, ids_avaliacoes, tipo_resposta: int, escala_likert_nome: str):
        """
        Atuliza os campos valor e nivel_escala das respostas de todas as
        respostas das avaliações cujos ids são menores ou igual a [avaliacao_id].

        O campo valor passa a conter o id do nível da escala correspondente.

        Também é atualizado o campo escala do indicador, cujo tipo_resposta é igual ao argumento tipo_resposta
        """

        def atualizar_indicadores_tipo_resposa_unica_escolha(
            qs_resposta, s_indicadores_sem_escala_padrao: set, sindicadores_a_serem_atualizados: set, escala: EscalaLikert
        ):
            self.stdout.write(f'\t\t{bcolors.ENDC}Corrigindo possíveis incossistências.  ... ')
            if s_indicadores_sem_escala_padrao:
                self.stdout.write(
                    f'\t\t{bcolors.ENDC}Atualizando indicadores com resposta única escolha sem escala Likert associada, mas o tipo é ESCALA_LIKERT: {s_indicadores_sem_escala_padrao} ... ',
                )
                with transaction.atomic():
                    self.stdout.write(f'\t\t\t{bcolors.ENDC}Atualizando respostas associadas com esses indicadores para nivel_escala=None:')
                    qs_resposta = qs_resposta.filter(indicador__id__in=s_indicadores_sem_escala_padrao, indicador__tipo_resposta=ESCALA_LIKERT)
                    if qs_resposta.exists():
                        rows = qs_resposta.update(nivel_escala=None)
                        if rows > 0:
                            self.stdout.write(f'\t\t\t\t{bcolors.OKBLUE}Respostas atualizadas: {rows}')
                        else:
                            self.stdout.write('\t\t\t\tNada a atualizar!')
                    else:
                        self.stdout.write('\t\t\t\tNada a atualizar!')

                    self.stdout.write(
                        f'\t\t\t{bcolors.ENDC}Atualizando esses indicadores para escala=None e tipo_resposta=UNICA_ESCOLHA: {s_indicadores_sem_escala_padrao} ... '
                    )
                    qs_indicador = Indicador.objects.filter(id__in=s_indicadores_sem_escala_padrao, tipo_resposta=ESCALA_LIKERT)
                    if qs_indicador.exists():
                        rows = qs_indicador.update(escala=None, tipo_resposta=UNICA_ESCOLHA)
                        if rows > 0:
                            self.stdout.write(f'\t\t\t\t{bcolors.OKBLUE}Indicadores atualizados: {rows}')
                        else:
                            self.stdout.write('\t\t\t\tNada a atualizar!')
                    else:
                        self.stdout.write('\t\t\t\tNada a atualizar!')
            else:
                self.stdout.write('\t\t\tNada a atualizar!')

            if sindicadores_a_serem_atualizados:
                self.stdout.write(f'\t\t\t{bcolors.ENDC}Indicadores com escala Likerd definida, mas tipo ainda é "{UNICA_ESCOLHA} - Única Escolha"')
                qs_indicador = Indicador.objects.filter(escala__isnull=False, id__in=sindicadores_a_serem_atualizados, tipo_resposta=UNICA_ESCOLHA)
                if qs_indicador.exists():
                    rows = qs_indicador.update(escala=escala, tipo_resposta=ESCALA_LIKERT)
                    if rows > 0:
                        self.stdout.write(f'\t\t\t\t{bcolors.OKBLUE}Indicadores atualizados: {rows}')
                    else:
                        self.stdout.write('\t\t\t\tNada a atualizar!')
                else:
                    self.stdout.write('\t\t\t\tNada a atualizar!')
            else:
                self.stdout.write('\t\t\tNada a atualizar!')

        self.stdout.write(
            f'\n\n# {bcolors.ENDC}Atualizando as respostas:\n\tAvaliações: {ids_avaliacoes}, \n\tEscala: "{escala_likert_nome}", \n\tTipo resposta: "{tipo_resposta}" ...'
        )

        qs_resposta = Resposta.objects.filter(
            respondente__avaliacao__in=ids_avaliacoes, indicador__tipo_resposta=tipo_resposta, nivel_escala__isnull=True
        ).exclude(valor='')

        if qs_resposta.exists():
            escala = EscalaLikert.objects.get(nome=escala_likert_nome)
            sindicadores_a_serem_atualizados = set()
            s_indicadores_sem_escala_padrao = set()

            for item in self.get_itens(escala):
                valor = str(item)
                try:
                    nivel = self.get_nivel(valor, escala)
                except ValueError:
                    # Tratamento de inconsistência de valores de respostas.
                    nivel = self.get_nivel(self.NIVEIS_PARSE[tipo_resposta][valor], escala)
                if tipo_resposta in (FAIXA_NUMERICA, GRAU_SATISFACAO):
                    valor = str(nivel.nivel)
                    sindicadores_a_serem_atualizados = set(qs_resposta.filter(valor=valor).values_list('indicador', flat=True))
                elif tipo_resposta == UNICA_ESCOLHA:
                    # Há situações que a palavra "Desconheço" não faz parte de uma escala Likder, como acontece
                    # no indicador de id 93.
                    # Para essas situações, o valor da resposta permanece o mesmo, não deve ser alterado
                    # Verifica todos os itens de opções de respostas do indicador obtido da resposta são os
                    # os mesmos dos níveis da escala.
                    sindicadores_ids = set(qs_resposta.values_list('indicador', flat=True))
                    for indicador_id in sindicadores_ids:
                        sopcoes_descricoes = OpcaoResposta.objects.filter(indicador=indicador_id).values_list('descricao', flat=True)
                        escala_str = ''.join(snivel.replace(' ', '') for snivel in sorted(sopcoes_descricoes))
                        codigo_hash = hashlib.sha256(escala_str.encode('utf-8')).hexdigest()

                        if self.HASH_NIVES_ESCALA.get(codigo_hash):
                            # Aqui, TODAS as opções de respostas informado no indicador, correspondem a TODOS os níveis da escala.
                            sindicadores_a_serem_atualizados.add(indicador_id)
                        else:
                            s_indicadores_sem_escala_padrao.add(indicador_id)
                            # self.stdout.write(hash(str(sorted(sopcoes_descricoes))), '----', sorted(sopcoes_descricoes))

                if sindicadores_a_serem_atualizados:
                    qs_resposta = qs_resposta.filter(indicador__in=sindicadores_a_serem_atualizados)

                    self.stdout.write(f'\t{bcolors.ENDC}Atualizando repostas referente ao valor "{valor}" ...')

                    if qs_resposta.filter(valor=valor).exists():
                        rows = qs_resposta.filter(valor=valor).update(valor=str(nivel.nivel), nivel_escala=nivel)
                        if rows > 0:
                            self.stdout.write(f'\t\t{bcolors.OKBLUE}Respostas atualizadas: {rows}')
                        else:
                            self.stdout.write('\t\tNada a atualizar!')
                    else:
                        self.stdout.write('\t\tNada a atualizar!')

                    self.stdout.write(f'\t\t{bcolors.ENDC}Atualizando repostas remanescente onde nível escala é nulo ...')
                    qs_resposta_pendencia = Resposta.objects.filter(respondente__avaliacao__in=ids_avaliacoes, nivel_escala__isnull=True, valor=valor)
                    qs_resposta_pendencia = qs_resposta_pendencia.filter(indicador__in=sindicadores_a_serem_atualizados)

                    if tipo_resposta == UNICA_ESCOLHA and qs_resposta_pendencia.exists():
                        rows = qs_resposta_pendencia.update(valor=str(nivel.nivel), nivel_escala=nivel)
                        if rows > 0:
                            self.stdout.write(f'\t\t\t{bcolors.OKBLUE}Respostas atualizadas: {rows}')
                        else:
                            self.stdout.write('\t\t\tNada a atualizar!')
                    else:
                        self.stdout.write('\t\t\tNada a atualizar!')
                atualizar_indicadores_tipo_resposa_unica_escolha(
                    qs_resposta, s_indicadores_sem_escala_padrao, sindicadores_a_serem_atualizados, nivel.escala
                )
        else:
            self.stdout.write('\tNada a atualizar!')

    def imprimir_avaliacao_com_pendencias(self):
        existem_pendencias = False
        pendencias = {}
        tipos_resposas = []
        sumario = {}

        qs_sum_tipo_resposta = Resposta.objects.values('indicador__tipo_resposta').exclude(valor='').annotate(total=Count('id'))
        self.stdout.write(f"{bcolors.ENDC}Total de respostas válidas (valor <> '') por tipo de resposta: ")
        for tipo_resposta, total in qs_sum_tipo_resposta.values_list('indicador__tipo_resposta', 'total'):
            sumario[tipo_resposta] = total
            self.stdout.write(f'{bcolors.ENDC}{tipo_resposta}:{total}')
            tipos_resposas.append(tipo_resposta)

        self.stdout.write(f'\n# {bcolors.ENDC}Verificando existências de pendências ... ')
        for tipo_resposta in tipos_resposas:
            if tipo_resposta in (FAIXA_NUMERICA, GRAU_SATISFACAO, ESCALA_LIKERT):
                qs_resposta = Resposta.objects.filter(indicador__tipo_resposta=tipo_resposta).exclude(valor='')
                if tipo_resposta == ESCALA_LIKERT:
                    self.stdout.write('Resposta cujo tipo do indicador é ESCALA_LIKERT, mas nivel_escala da resposta é nulo. ')
                    qs_resposta = qs_resposta.filter(nivel_escala__isnull=True)
                else:
                    self.stdout.write(
                        'Resposta cujo tipo do indicador é (FAIXA_NUMERICA ou GRAU_SATISFACAO), mas nivel_escala da resposta não é nula. '
                    )
                    qs_resposta = qs_resposta.filter(nivel_escala__isnull=False)
                if not qs_resposta.exists():
                    continue

                existem_pendencias = True
                self.stdout.write(f'{bcolors.WARNING}AVISO: Tipo resposta {tipo_resposta} necessita de verificação.')
                qs_resposta = qs_resposta.values('respondente__avaliacao', 'respondente__avaliacao__nome').annotate(quant=Count('id'))
                self.stdout.write('\tAvaliações: ')
                for respondente__avaliacao, respondente__avaliacao__nome, quant in qs_resposta.values_list(
                    'respondente__avaliacao', 'respondente__avaliacao__nome', 'quant'
                ):
                    if pendencias.get(respondente__avaliacao) is None:
                        pendencias[respondente__avaliacao] = {
                            'avaliacao_id': respondente__avaliacao,
                            'avaliacao_nome': respondente__avaliacao__nome,
                            'total_resposta': quant,
                            'tipos_respostas': {},
                        }
                    if pendencias[respondente__avaliacao].get('tipos_respostas') is None:
                        pendencias[respondente__avaliacao]['tipos_respostas'] = {}

                    # pendencias[respondente__avaliacao]['total_resposta']['totais_respostas'].append(quant)

                    self.stdout.write(f'\t{respondente__avaliacao} - {respondente__avaliacao__nome}, total: {quant} respostas')
                    # respostas = Resposta.objects.filter(respondente__avaliacao=respondente__avaliacao, indicador__tipo_resposta=tipo_resposta, nivel_escala__isnull=True).exclude(valor='')
                    respostas = (
                        qs_resposta.filter(respondente__avaliacao=respondente__avaliacao)
                        .values('indicador', 'valor')
                        .annotate(quant=Count('id'))
                        .values('valor', 'quant')
                    )
                    self.stdout.write('\tValores: ')
                    self.stdout.write('\t\t[Tipo Resposta], Indicador ID, Resposta Valor, Total')
                    for indicador, valor, quant in respostas.values_list('indicador', 'valor', 'quant'):
                        if pendencias[respondente__avaliacao]['tipos_respostas'].get(tipo_resposta) is None:
                            pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta] = {}
                        if pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta].get(indicador) is None:
                            pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta][indicador] = {}
                            pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta][indicador] = []
                        pendencias[respondente__avaliacao]['tipos_respostas'][tipo_resposta][indicador].append((valor, quant))

                        self.stdout.write(f'\t\t[{tipo_resposta}], {indicador}, {valor}, {quant}')
        if not existem_pendencias:
            self.stdout.write(f'{bcolors.OKGREEN}Processamento concluído com sucesso, não foram encontrados pendências')

        qs_repostas = Resposta.objects.filter(nivel_escala__isnull=True, indicador__tipo_resposta=99).exclude(valor='')
        self.imprimir_detalhes_dados(qs_repostas)

        qs_repostas = Resposta.objects.filter(nivel_escala__isnull=False).exclude(valor='').exclude(indicador__tipo_resposta=99)
        self.imprimir_detalhes_dados(qs_repostas)

        return existem_pendencias, pendencias, sumario

    def atualiza_indicadores(self, mensagem: str, escala_likert_nome: str, indicador_tipos_respostas: list):
        self.stdout.write(mensagem)
        escala = EscalaLikert.objects.get(nome=escala_likert_nome)
        qs_resposta = Resposta.objects.filter(nivel_escala__isnull=False, indicador__tipo_resposta__in=indicador_tipos_respostas)
        if qs_resposta.exists:
            qs_indicadores_ids = qs_resposta.values_list('indicador', flat=True)

            qs_indicador = Indicador.objects.filter(id__in=set(qs_indicadores_ids), escala__isnull=True, tipo_resposta__in=indicador_tipos_respostas)
            if qs_indicador.exists():
                rows = qs_indicador.update(escala=escala, tipo_resposta=ESCALA_LIKERT)
                if rows > 0:
                    self.stdout.write(f'\t{bcolors.OKBLUE}Indicadores atualizados: {rows}')
                else:
                    self.stdout.write('\tNada a atualizar!')
            else:
                self.stdout.write('\t\tNada a atualizar!')
        else:
            self.stdout.write('\t\tNada a atualizar!')

    def tratar_inconsistencias(self):
        self.stdout.write(f'\n# {bcolors.ENDC}Corrigindo possíveis incossistências... ')

        self.stdout.write(
            f'\t{bcolors.ENDC}Atualizando indicadores de respostas com multiplas escolhas, cujo tipo é ESCALA_LIKERT para o tipo MULTIPLA_ESCOLHA'
        )
        qs_indicadores_ids = Resposta.objects.filter(valor__contains='::', indicador__tipo_resposta=ESCALA_LIKERT).values_list('indicador', flat=True)
        if qs_indicadores_ids.exists():
            sindicadores = set(qs_indicadores_ids)
            self.stdout.write(f'\t\t{bcolors.ENDC}Indicadores: ', sindicadores or 0)
            qs_indicador = Indicador.objects.filter(id__in=sindicadores, tipo_resposta=ESCALA_LIKERT)
            if qs_indicador.exists():
                rows = qs_indicador.update(escala=None, tipo_resposta=MULTIPLA_ESCOLHA)
                if rows > 0:
                    self.stdout.write(f'\t\t\t{bcolors.OKBLUE}Indicadores atualizados: {rows}')
                else:
                    self.stdout.write('\t\t\tNada a atualizar!')
            else:
                self.stdout.write('\t\t\tNada a atualizar!')
        else:
            self.stdout.write('\t\tNada a atualizar!')

        self.stdout.write(
            f'\t{bcolors.ENDC}Atualizando indicadores das respostas em que o nível de escala likert padrão é NULO, cujo tipo de indicador é ESCALA_LIKERT para o tipo UNICA_ESCOLHA'
        )

        qs_resposta = Resposta.objects.filter(nivel_escala__isnull=True, indicador__tipo_resposta=ESCALA_LIKERT).exclude(valor='')
        if qs_resposta.exists():
            qs_indicadores_ids = qs_resposta.values_list('indicador', flat=True)
            sindicadores = set(qs_indicadores_ids)
            self.stdout.write(f'\t\t{bcolors.ENDC}Indicadores: ', sindicadores or 0)
            # self.imprimir_detalhes_dados(qs)
            qs_indicador = Indicador.objects.filter(id__in=sindicadores, tipo_resposta=ESCALA_LIKERT)
            if qs_indicador.exists():
                rows = qs_indicador.update(escala=None, tipo_resposta=UNICA_ESCOLHA)
                if rows > 0:
                    self.stdout.write(f'\t\t{bcolors.OKBLUE}Indicadores atualizados: {rows}')
                else:
                    self.stdout.write('\t\tNada a atualizar!')
            else:
                self.stdout.write('\t\tNada a atualizar!')
        else:
            self.stdout.write('\t\tNada a atualizar!')

        self.stdout.write(
            f'\t{bcolors.ENDC}Atualizando indicadores das respostas em que consta DEFINIDO algum nível de escala likert cujo tipo de indicador é UNICA_ESCOLHA para o tipo ESCALA_LIKERT'
        )
        qs_resposta = Resposta.objects.filter(nivel_escala__isnull=False, indicador__tipo_resposta=UNICA_ESCOLHA).exclude(valor='')
        if qs_resposta.exists():
            qs_indicadores_agg = (
                qs_resposta.values('indicador', 'nivel_escala__escala')
                .annotate(quant=Count('indicador'))
                .values_list('indicador', 'nivel_escala__escala', 'quant')
            )
            escalas_indicadores = {}
            for indicador, nivel_escala__escala, _quant in qs_indicadores_agg:
                if escalas_indicadores.get(nivel_escala__escala) is None:
                    escalas_indicadores[nivel_escala__escala] = set()
                escalas_indicadores[nivel_escala__escala].add(indicador)

            for escala_id, indicadores in escalas_indicadores.items():
                self.stdout.write(f'\t\t{bcolors.ENDC}Indicadores: ', indicadores)
                self.stdout.write(
                    f'\t\t{bcolors.ENDC}Atualizando esses indicadores, cujo tipo_resposta=UNICA_ESCOLHA para escala_id={escala_id} e tipo_resposta=ESCALA_LIKERT'
                )
                qs_indicador = Indicador.objects.filter(id__in=indicadores, tipo_resposta=UNICA_ESCOLHA)
                if qs_indicador.exists():
                    rows = qs_indicador.update(escala_id=escala_id, tipo_resposta=ESCALA_LIKERT)
                    if rows > 0:
                        self.stdout.write(f'\t\t\t{bcolors.OKBLUE}Indicadores atualizados: {rows}')
                    else:
                        self.stdout.write('\t\t\tNada a atualizar!')
                else:
                    self.stdout.write('\t\t\tNada a atualizar!')
        else:
            self.stdout.write('\t\tNada a atualizar!')

    def executar(self, iteracao_id):
        self.stdout.write(80 * '-')
        self.stdout.write(f'Iteração ID: {iteracao_id}')
        self.stdout.write(80 * '_')

        # with transaction.atomic():
        #     Resposta.objects.filter(valor='Discordo Parcilamente').update(valor='Discordo parcialmente')
        #     Resposta.objects.filter(valor='Discordo Parcialmente').update(valor='Discordo parcialmente')
        #     Resposta.objects.filter(valor='Concordo Parcialmente').update(valor='Concordo parcialmente')

        escala_likert_nome = 'Escala Grau Satisfação'
        self.adaptar(
            ids_avaliacoes=(4, 5, 8),
            tipo_resposta=GRAU_SATISFACAO,  # 9
            escala_likert_nome=escala_likert_nome,
        )

        self.adaptar(
            ids_avaliacoes=(2, 3, 4, 5, 16),
            tipo_resposta=FAIXA_NUMERICA,  # 8
            escala_likert_nome=escala_likert_nome,
        )

        self.atualiza_indicadores(
            mensagem=f"""\n# {bcolors.ENDC}Atualizando indicadores das respostas COM nível escala likert definida (nivel_escala__isnull=False), cujo tipo são (FAIXA_NUMERICA, GRAU_SATISFACAO) para escala {escala_likert_nome} e tipo ESCALA_LIKERT ...""",
            escala_likert_nome=escala_likert_nome,
            indicador_tipos_respostas=(FAIXA_NUMERICA, GRAU_SATISFACAO),
        )

        self.adaptar(ids_avaliacoes=(10,), tipo_resposta=UNICA_ESCOLHA, escala_likert_nome='Escala 2019')

        escala_likert_nome = 'Escala Padrão'
        self.adaptar(
            ids_avaliacoes=(2, 13, 14, 16, 17, 18, 19, 20, 21),
            tipo_resposta=UNICA_ESCOLHA,  # 5
            escala_likert_nome=escala_likert_nome,
        )

        self.atualiza_indicadores(
            mensagem=f"""\n# {bcolors.ENDC}Atualizando indicadores das respostas COM nível escala likert definida (nivel_escala__isnull=False), cujo tipo é UNICA_ESCOLHA para escala {escala_likert_nome} e tipo ESCALA_LIKERT ...""",
            escala_likert_nome=escala_likert_nome,
            indicador_tipos_respostas=(UNICA_ESCOLHA,),
        )

        self.tratar_inconsistencias()

        return self.imprimir_avaliacao_com_pendencias()

    def imprimir_sumario(self, all_sumario):
        self.stdout.write(f'{bcolors.OKBLUE}SUMÁRIO')
        self.stdout.write('Total de respostas válidas.')
        # Encontrar o número máximo de iterações
        max_iteracoes = max(len(totais_respostas) for totais_respostas in all_sumario.values())

        # Cabeçalho
        header = ['Tipo Resposta'] + [f'Iteração {i}' for i in range(max_iteracoes)]
        self.stdout.write(f'{" | ".join(header)}')

        # Impressão da tabela
        for tipo_resposta, totais_respostas in all_sumario.items():
            # Preencher com valores vazios se não houver total de resposta suficiente
            totais_respostas += [''] * (max_iteracoes - len(totais_respostas))
            row = [f'{tipo_resposta:<13}'] + [f'{total:>10}' if total != '' else f'{"":>10}' for total in totais_respostas]
            self.stdout.write(f'{" | ".join(row)}')

    # Função para organizar a impressão

    def imprimir_all_pendencias(self, all_pendencias):
        self.stdout.write(f'\n{bcolors.WARNING}PENDÊNCIAS:')
        cabecalho_avaliacao_id = 0
        for dados in all_pendencias.values():
            avaliacao = dados['avaliacao']
            if cabecalho_avaliacao_id != avaliacao['id']:
                self.stdout.write(f'{avaliacao["id"]} - {avaliacao["nome"]}, total: {avaliacao["total_respostas"]} respostas.')

            # Cabeçalho da tabela
            execucoes = dados['execucoes']
            num_iteracoes = len(execucoes)
            if cabecalho_avaliacao_id != avaliacao['id']:
                cabecalho = ['Tipo de Resposta', 'ID Indicador'] + [
                    f"Iteração {i + 1} ('Resposta Valor'), 'Quantidade')" for i in range(num_iteracoes)
                ]
                self.stdout.write(f'{cabecalho[0]:<18}{cabecalho[1]:<15}', end='')

                for i in range(2, len(cabecalho)):
                    self.stdout.write(f'{cabecalho[i]:<20}', end='')
                self.stdout.write('\n')  # Nova linha após o cabeçalho

            cabecalho_avaliacao_id = avaliacao['id']

            # Linhas com dados
            tipo_resposta = dados['tipo_resposta']
            indicador_id = dados['indicador_id']

            valores_por_iteracao = []
            for execucao in execucoes:
                respostas_valores = execucao['respostas_valores_com_totais']
                valores_por_iteracao.append(', '.join([f'({val[0]}: {val[1]})' for val in respostas_valores]))

            # Imprime a linha com os dados
            self.stdout.write(f'{tipo_resposta:<18}{indicador_id:<15}', end='')
            for valores in valores_por_iteracao:
                self.stdout.write(f'{valores:<20}', end='')
            self.stdout.write('\n')  # Nova linha após os dados de cada avaliação

    def processar(self):
        all_pendencias = {}
        all_sumario = {}
        existem_pendencias = True  # Inicialmente, assume-se que há pendências.

        contador_execucao = 0
        while existem_pendencias:
            contador_execucao += 1

            existem_pendencias, pendencias, sumario = self.executar(contador_execucao)

            for tipo_resposta, total_respostas in sumario.items():
                if all_sumario.get(tipo_resposta) is None:
                    all_sumario[tipo_resposta] = []
                all_sumario[tipo_resposta].append(total_respostas)

            for avaliacao_id, detalhe in pendencias.items():
                for tipo_resposta, indicadores in detalhe['tipos_respostas'].items():
                    for indicador_id, respostas_valores in indicadores.items():
                        # respostas_valores é um tupla (resposta_valor, resposta_total)
                        chave = (contador_execucao, avaliacao_id, tipo_resposta, indicador_id)
                        if all_pendencias.get(chave) is None:
                            all_pendencias[chave] = {
                                'avaliacao': {
                                    'id': avaliacao_id,
                                    'nome': detalhe['avaliacao_nome'],
                                    'total_respostas': detalhe['total_resposta'],
                                },
                                'iteracao_id': contador_execucao,
                                'tipo_resposta': tipo_resposta,
                                'indicador_id': indicador_id,
                                'execucoes': [],
                            }
                            all_pendencias[chave]['execucoes'].append(
                                {'iteracao_id': contador_execucao, 'respostas_valores_com_totais': respostas_valores}
                            )

        self.stdout.write(f'\n# {bcolors.ENDC}Verificando existências de pendências ... ')
        self.stdout.write('Dicionário Sumário:')
        self.stdout.write(str(all_sumario))
        self.stdout.write('Dicionário Pendências:')
        self.stdout.write(str(all_pendencias))

        self.imprimir_all_pendencias(all_pendencias)
        self.imprimir_sumario(all_sumario)

    # Função para tratar a lógica do comando
    def listar_avaliacoes_por_tipo_resposta(self):
        qs = Resposta.objects.filter(indicador__tipo_resposta__in=(5, 6, 8, 9)).exclude(valor='')
        respostas_qs = qs.values('indicador__tipo_resposta', 'respondente__avaliacao')
        respostas_qs_list = respostas_qs.annotate(quant=Count('id')).values_list('indicador__tipo_resposta', 'respondente__avaliacao', 'quant')
        dados = {}
        for tipo_resposta, avaliacao_id, _quant in respostas_qs_list:
            tipo_resposta_str = TIPOS_RESPOSTAS_PARSE[tipo_resposta]
            if dados.get(tipo_resposta_str) is None:
                dados[tipo_resposta_str] = []
            dados[tipo_resposta_str].append(avaliacao_id)

        for k, v in dados.items():
            self.stdout.write(k, v)

        respostas = set()
        for escala in EscalaLikert.objects.all():
            sindicadores_a_serem_atualizados = set()
            self.stdout.write(f'Verificando escala: {escala.nome}')
            for tipo_resposta in TIPOS_RESPOSTAS:
                self.stdout.write(f'\tVerificando tipo resposta: {TIPOS_RESPOSTAS_PARSE[tipo_resposta]}')
                qs_resposta = Resposta.objects.filter(indicador__tipo_resposta=tipo_resposta).exclude(valor='')
                for item in self.get_itens(escala):
                    escalas_detectadas = set()
                    valor = str(item)
                    try:
                        nivel = self.get_nivel(valor, escala)
                    except ValueError:
                        # Tratamento de inconsistência de valores de respostas.
                        nivel = self.get_nivel(self.NIVEIS_PARSE[tipo_resposta][valor], escala)
                    if tipo_resposta in (FAIXA_NUMERICA, GRAU_SATISFACAO):
                        escalas_detectadas.add(f'{escala.id} - {escala.nome}')
                        valor = str(nivel.nivel)
                        sindicadores_a_serem_atualizados = set(qs_resposta.filter(valor=valor).values_list('indicador', flat=True))
                    elif tipo_resposta == UNICA_ESCOLHA:
                        sindicadores_ids = set(qs_resposta.values_list('indicador', flat=True))
                        for indicador_id in sindicadores_ids:
                            sopcoes_descricoes = OpcaoResposta.objects.filter(indicador=indicador_id).values_list('descricao', flat=True)
                            escala_str = ''.join(snivel.replace(' ', '') for snivel in sorted(sopcoes_descricoes))
                            codigo_hash = hashlib.sha256(escala_str.encode('utf-8')).hexdigest()
                            escala_detectada = self.HASH_NIVES_ESCALA.get(codigo_hash)
                            if escala_detectada:
                                self.stdout.write(indicador_id, end=' ', flush=True)
                                # self.stdout.write(indicador_id, ",", valor, ",", escala_detectada['escala_nome'])
                                escalas_detectadas.add(f'{escala_detectada["escala_id"]} - {escala_detectada["escala_nome"]}')
                                # Aqui, TODAS as opções de respostas informado no indicador, correspondem a TODOS os níveis da escala.
                                sindicadores_a_serem_atualizados.add(indicador_id)

                    if sindicadores_a_serem_atualizados:
                        qs_resposta = qs_resposta.filter(indicador__in=sindicadores_a_serem_atualizados)
                        if qs_resposta.filter(valor=valor).exists():
                            respostas_qs_list = respostas_qs.annotate(quant=Count('id')).values_list(
                                'indicador__tipo_resposta', 'respondente__avaliacao', 'quant'
                            )
                            respostas.update(respostas_qs_list)
                            self.stdout.write(f'\n\t\tValor = "{valor}", total respostas: {qs_resposta.count()}')
                        else:
                            self.stdout.write(f'\n\t\tValor = "{valor}", total respostas: 0')
                        self.stdout.write(f'\t\t\tEscalas detectadas: {", ".join(escalas_detectadas)}')

        dados = {}
        for respostas_qs_list in respostas:
            for tipo_resposta, avaliacao_id, _quant in respostas_qs_list:
                tipo_resposta_str = TIPOS_RESPOSTAS_PARSE[tipo_resposta]
                if dados.get(tipo_resposta_str) is None:
                    dados[tipo_resposta_str] = []
                dados[tipo_resposta_str].append(avaliacao_id)

        for k, v in dados.items():
            self.stdout.write(k, v)

    def indicadores_definir_escala(self):
        escalas_encontradas = {}

        indicadores_ids = Indicador.objects.filter(tipo_resposta=UNICA_ESCOLHA).values_list('id', flat=True)
        for indicador_id in indicadores_ids:
            sopcoes_descricoes = OpcaoResposta.objects.filter(indicador=indicador_id).values_list('descricao', flat=True)
            escala_str = ''.join(snivel.replace(' ', '') for snivel in sopcoes_descricoes)
            codigo_hash = hashlib.sha256(escala_str.encode('utf-8')).hexdigest()

            if escalas_encontradas.get(codigo_hash) is None:
                escalas_encontradas[codigo_hash] = {
                    'niveis': list(sopcoes_descricoes),
                    'valores': set(),
                    'indicadores': [],
                }
            escalas_encontradas[codigo_hash]['indicadores'].append(indicador_id)

            respostas_qs = Resposta.objects.filter(indicador=indicador_id)
            valores = list(respostas_qs.values_list('valor', flat=True))
            escalas_encontradas[codigo_hash]['valores'].update(valores)

        for codigo_hash, dados in escalas_encontradas.items():
            # escala, created = EscalaLikert.objects.get_or_create(nome=codigo_hash)
            #
            # Indicador.objects.filter(id__in=dados['indicadores']).update(escala=escala)
            #
            # for valor in valores:
            #     escala_nivel, created = NivelEscalaLikert.objects.get_or_create(
            #         escala=escala,
            #
            #             )
            # if created:
            #     for nivel in niveis
            #     NivelEscalaLikert.objects.get_or_create(
            #         escala=escala,
            #     )
            # escala = models.ForeignKey(EscalaLikert, on_delete=models.CASCADE, related_name='niveis_escala')
            # nivel = models.IntegerFieldPlus('Nível')
            # descricao = models.CharFieldPlus('Descrição', max_length=50)
            # emoji = models.CharFieldPlus('Emoji', max_length=10, null=True, blank=True)
            # tipo_criterio = models.CharField('Critério Padronização Gráficos', choices=TIPO_CRITERIO_CHOICES,
            #                                  max_length=1)
            self.stdout.write('\n')
            self.stdout.write(f'Código: {codigo_hash}')
            self.stdout.write(f'Níveis: {dados["niveis"]}')
            self.stdout.write(f'Valores: {dados["valores"]}')
            self.stdout.write(f'Indicadores: {sorted(dados["indicadores"])}')

            respostas_qs = Resposta.objects.filter(indicador__in=dados['indicadores']).values('respondente__avaliacao')
            avaliacoes_ids = respostas_qs.annotate(quant=Count('id')).values_list('respondente__avaliacao', flat=True)
            self.stdout.write(f'Avaliações: {sorted(avaliacoes_ids)}')

    def handle(self, *args, **options):
        self.define_constante_niveis_escala_hash()

        if options['list']:
            self.indicadores_definir_escala()
            return

        # Obtém o nome do arquivo passado como argumento
        arquivo_saida = options['path_arquivo_saida']

        if not arquivo_saida:
            # Se o arquivo não foi passado, exibe um erro e encerra o programa
            self.stdout.write(f'{bcolors.FAIL}Erro: O nome do arquivo de saída é obrigatório.{bcolors.ENDC}')
            return

        # Verifica se o arquivo tem um nome válido
        if not os.path.splitext(arquivo_saida)[1]:
            self.stdout.write(f'{bcolors.WARNING}Aviso: O arquivo não tem uma extensão. Defina uma extensão, como ".txt".{bcolors.ENDC}')

        # Redirecionando a saída padrão para o arquivo e console ao mesmo tempo
        with open(arquivo_saida, 'w', encoding='utf-8') as f:
            tee = Tee(sys.stdout, f)
            sys.stdout = tee  # Substitui stdout pelo Tee

            # Chama o processo principal
            self.processar()

            # Restaura a saída padrão para o console
            sys.stdout = sys.__stdout__

        self.stdout.write(f'{bcolors.OKGREEN}Processamento concluído.')
        self.stdout.write(f'Envie o arquivo resultante do processamento {arquivo_saida} para o desenvolvedor responsável.')
        self.stdout.write(f'{bcolors.ENDC}Processamento concluído.')
