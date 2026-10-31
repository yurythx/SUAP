from django.apps.registry import apps
from django.db.models import F, Q

from comum.models import Ano
from contracheques.layout import (
    classificacao_titulacoes as clt,
)
from contracheques.layout import (
    tabela_incentivo_qualificacao as tiq,
)
from contracheques.layout import (
    tabela_retribuicao_por_titulacao as trpt,
)
from contracheques.managers import ContraChequeQueryset
from djtools.choices import Meses
from djtools.db import models
from djtools.utils import normalizar_nome_proprio
from rh.models import CargoClasse, Titulacao


class ContraCheque(models.ModelPlus):
    IMPORTACAO_FITA_ESPELHO = 1
    IMPORTACAO_WS = 2

    TIPO_IMPORTACAO_CHOICES = ((IMPORTACAO_FITA_ESPELHO, 'Fita Espelho'), (IMPORTACAO_WS, 'Webservice'))

    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE)
    mes = models.SmallIntegerField('Mês', choices=Meses.get_choices())
    servidor = models.ForeignKeyPlus('rh.Servidor', on_delete=models.CASCADE)
    pensionista = models.ForeignKeyPlus('comum.Pensionista', null=True, on_delete=models.CASCADE)
    servidor_titulacao = models.ForeignKeyPlus(
        'rh.Titulacao', null=True, blank=True, on_delete=models.CASCADE, verbose_name='Titulação baseada no contracheque'
    )
    servidor_cargo_emprego = models.ForeignKeyPlus('rh.CargoEmprego', null=True, blank=True, verbose_name='Cargo Emprego', on_delete=models.CASCADE)
    servidor_cargo_classe = models.ForeignKeyPlus('rh.CargoClasse', null=True, blank=True, verbose_name='Cargo Classe', on_delete=models.CASCADE)
    servidor_nivel_padrao = models.CharField(max_length=4, null=True, blank=True, verbose_name='Nível Padrão')
    servidor_setor_lotacao = models.ForeignKeyPlus(
        'rh.Setor', null=True, blank=True, verbose_name='Setor de Lotação', on_delete=models.CASCADE, related_name='setor_lotacao'
    )
    servidor_setor_localizacao = models.ForeignKeyPlus(
        'rh.Setor', null=True, blank=True, on_delete=models.CASCADE, verbose_name='Setor de Localização', related_name='setor_exercicio'
    )
    servidor_situacao = models.ForeignKeyPlus('rh.Situacao', null=True, blank=True, verbose_name='Situação', on_delete=models.CASCADE)
    servidor_jornada_trabalho = models.ForeignKeyPlus(
        'rh.JornadaTrabalho', null=True, blank=True, on_delete=models.CASCADE, verbose_name='Jornada de Trabalho'
    )
    bruto = models.DecimalFieldPlus(null=True)  # porque permite nulo e não põe zero?
    desconto = models.DecimalFieldPlus(null=True)  # porque permite nulo e não põe zero?
    liquido = models.DecimalFieldPlus(null=True)  # porque permite nulo e não põe zero?

    tem_permissao_visualizacao = False

    tipo_importacao = models.SmallIntegerField(
        'Tipo de Importação', null=True, blank=True, default=IMPORTACAO_FITA_ESPELHO, choices=TIPO_IMPORTACAO_CHOICES
    )

    excluido = models.BooleanField('Excluído', default=False)

    objects = ContraChequeQueryset.as_manager()

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Contracheque'
        verbose_name_plural = 'Contracheques'
        # unique_together = ("ano", "mes", "servidor", "tipo_importacao")

        permissions = (
            ('pode_ver_contracheques_detalhados', 'Ver qualquer Contracheque detalhado'),
            ('pode_ver_contracheques_agrupados', 'Ver o total de Contracheque ou grupo'),
            ('pode_ver_contracheques_historicos', 'Buscar dados no histórico'),
        )

    def __str__(self):
        return f'{self.mes}/{self.ano} - Mat.: {self.servidor.matricula} - Bruto: {self.bruto}'

    def get_absolute_url(self):
        return f'/contracheques/contra_cheque/{self.pk}'

    @staticmethod
    def importar_contracheque_webservice(dados):
        choice_mes = {
            'JAN': 1,
            'FEV': 2,
            'MAR': 3,
            'ABR': 4,
            'MAI': 5,
            'JUN': 6,
            'JUL': 7,
            'AGO': 8,
            'SET': 9,
            'OUT': 10,
            'NOV': 11,
            'DEZ': 12,
        }

        for mat, dic in dados.items():
            # carregando dados do servidor
            Servidor = apps.get_model('rh', 'Servidor')
            servidor_instance = Servidor.objects.get(matricula=mat)

            for k, v in dic.items():
                ano_cc = Ano.objects.get(ano=k[3:7])
                mes_cc = choice_mes.get(k[:3])
                servidor_cc = servidor_instance
                cc_valor_bruto = 0
                cc_valor_desconto = 0
                cc_valor_liquido = 0

                for rubrica in v:
                    codigo_rubrica = rubrica.get('codRubrica')
                    valor_rubrica = rubrica.get('valorRubrica').replace('.', '').replace(',', '.')
                    # bruto
                    if codigo_rubrica == '99997':
                        cc_valor_bruto = valor_rubrica
                        continue
                    # desconto
                    if codigo_rubrica == '99998':
                        cc_valor_desconto = valor_rubrica
                        continue
                    # liquido
                    if codigo_rubrica == '99999':
                        cc_valor_liquido = valor_rubrica
                        continue

                # verificando se existe mais de um cc para o mesmo tipo de importação, servidor, ano e mês
                qs_check_cc = ContraCheque.objects.ativos().webservice().filter(servidor=servidor_cc, mes=mes_cc, ano=ano_cc)
                if qs_check_cc.exists() and qs_check_cc.count() > 1:
                    # existir mais de um cc para as condições da consulta, é necessário corrigir a importação, apagando todos os registros de cc
                    qs_check_cc.delete()

                cc, cc_created = (
                    ContraCheque.objects.ativos()
                    .webservice()
                    .get_or_create(
                        servidor=servidor_cc,
                        mes=mes_cc,
                        ano=ano_cc,
                        pensionista=None,
                        bruto=cc_valor_bruto,
                        desconto=cc_valor_desconto,
                        liquido=cc_valor_liquido,
                        tipo_importacao=ContraCheque.IMPORTACAO_WS,
                    )
                )
                if cc_created:
                    # se for um cadastro de um novo cc, precisamos atualizar com informações atuais do servidor
                    cc.servidor_titulacao = servidor_instance.titulacao
                    cc.servidor_cargo_emprego = servidor_instance.cargo_emprego
                    cc.servidor_cargo_classe = servidor_instance.cargo_classe
                    cc.servidor_nivel_padrao = servidor_instance.nivel_padrao
                    cc.servidor_setor_lotacao = servidor_instance.setor_lotacao
                    cc.servidor_setor_localizacao = servidor_instance.setor_exercicio
                    cc.servidor_situacao = servidor_instance.situacao
                    cc.servidor_jornada_trabalho = servidor_instance.jornada_trabalho
                    cc.save()

                cc.contrachequerubrica_set.all().delete()

                for rubrica in v:
                    codigo_rubrica = rubrica.get('codRubrica')
                    if codigo_rubrica in ['99997', '99998', '99999']:
                        continue

                    valor_rubrica = rubrica.get('valorRubrica').replace('.', '').replace(',', '.')
                    indicador = rubrica.get('indicadorRD')
                    sequencia = rubrica.get('numeroSeq')
                    prazo = rubrica.get('pzRubrica')

                    # salvando informações das rubricas
                    rendimento_desconto = 3
                    if indicador == 'D':
                        rendimento_desconto = 2
                    if indicador == 'R':
                        rendimento_desconto = 1

                    cc.insere_contra_cheque_rubrica(
                        rendimento_desconto=rendimento_desconto,
                        codigo_rubrica=codigo_rubrica,
                        sequencia=sequencia,
                        valor=valor_rubrica,
                        prazo=prazo or '000',
                    )

    @classmethod
    def tem_contracheque_para_mim(self, servidor):
        return ContraCheque.objects.ativos().fita_espelho().filter(servidor=servidor).exists()

    def recebe_rt_ou_iq(self):
        return ContraChequeRubrica.objects.filter(contra_cheque=self, rubrica__codigo__in=['82462', '82606'], tipo__nome='Rendimento').count()

    @classmethod
    def get_servidores_com_titulacao_dispar(self):
        """
        Retorna lista de ContraCheque de servidores que apresentam divergências referentes ao cadastro e aos rendimentos
        apresentados nos últimos contracheques de cada servidor.

        Returns:
            list: Lista de ContraCheque
        """
        situacao_serv = ['ATIVO PERMANENTE', 'CEDIDO', 'CONT.PROF.SUBSTITUTO', 'CONT.PROF.TEMPORARIO', 'CONTRATO TEMPORARIO']

        if ContraCheque.objects.ativos().fita_espelho().count():
            ultimo_mes, ultimo_ano = (
                ContraCheque.objects.ativos().fita_espelho().latest('id').mes,
                ContraCheque.objects.ativos().fita_espelho().latest('id').ano.id,
            )
            # verifica quais os contracheques que possuem titulações divergentes
            ids_cc = (
                ContraCheque.objects.filter(mes=ultimo_mes, ano=ultimo_ano)
                .filter(
                    Q(servidor_titulacao__isnull=True, servidor__titulacao__isnull=False)
                    | Q(servidor_titulacao__isnull=False, servidor__titulacao__isnull=True)
                    | ~Q(servidor_titulacao_id=F('servidor__titulacao_id'))
                )
                .exclude(servidor_titulacao__isnull=True, servidor__titulacao__isnull=True)
                .values_list('id', flat=True)
                .distinct()
            )

            # So interessa os ativos permanentes, substitutos e cedidos
            ccs = (
                ContraCheque.objects.ativos()
                .fita_espelho()
                .filter(
                    id__in=ids_cc,
                    contrachequerubrica__rubrica__codigo__in=['82462', '82606'],
                    contrachequerubrica__tipo__nome='Rendimento',
                    servidor_situacao__nome_siape__in=situacao_serv,
                )
                .distinct()
                .order_by('servidor__setor__uo', 'servidor__pessoa_fisica__nome')
            )
            contracheques = []
            # TODO: Este queryset de ContraCheque, chamado ccs, deveria retornar somente seridores com "cargo_classe.codigo" A, B, C, D e E?
            for cc in ccs:
                # se existir divergência entre os cadastros

                if cc.servidor.cargo_classe != cc.servidor_cargo_classe or not cc.servidor.titulacao or not cc.servidor_titulacao:
                    contracheques.append(cc)
                    continue

                # Se for vigilante por mais que seja um cargo de nivel 'D' a tabela pra RT é 'C'
                s_cargoclasse = cc.servidor.cargo_classe.codigo
                s_cargoemprego = cc.servidor.cargo_emprego.nome
                if 'VIGILANTE' in s_cargoemprego:
                    s_cargoclasse = CargoClasse.objects.get(codigo='C').codigo

                # verifica se a titulação do servidor existe para o cargo
                s_titulacao = cc.servidor.titulacao.nome
                t_possivel = False
                if s_cargoclasse in tiq:
                    # tiq contém as classes usadas no PCCTAE (A, B, C, D, E) e os percentuais devidos a qualificação.
                    # Exemplo: A -> 10% -> GRADUACAO
                    for relacao in tiq[s_cargoclasse]:
                        for porcentagem in tiq[s_cargoclasse][relacao]:
                            if tiq[s_cargoclasse][relacao][porcentagem] == s_titulacao:
                                t_possivel = True
                                break

                t_servidor = 0
                t_contracheque = 0
                for classificacao in clt:
                    if cc.servidor.titulacao and cc.servidor.titulacao.nome in clt[classificacao]:
                        t_servidor = classificacao
                    if cc.servidor_titulacao and cc.servidor_titulacao.nome in clt[classificacao]:
                        t_contracheque = classificacao

                # se um servidor possui uma titulação maior do que ele pode atingir na carreira e em contracheque ele possui
                # gratificação igual a última possível (a mais alta em valor), não será necessário apresentar esse servidor
                if not (not t_possivel and t_servidor >= t_contracheque):
                    contracheques.append(cc)

            return contracheques
        return None

    @classmethod
    def find_servidor_com_titulacao_dispar(cls):
        """
        Procura pelo menos um servidor com titulação dispar para exibir no index
        """
        if ContraCheque.objects.ativos().fita_espelho().exists():
            ultimo_ano, ultimo_mes = ContraCheque.objects.ativos().fita_espelho().values_list('ano', 'mes').latest('id')
            return (
                ContraCheque.objects.ativos()
                .fita_espelho()
                .filter(ano=ultimo_ano, mes=ultimo_mes)
                .exclude(servidor_titulacao=models.F('servidor__titulacao'))
                .exists()
            )
        return False

    def pode_ver(self, request=None):
        """
        Testa se o usuário autenticado pode ver este contra-cheque.
        """
        if request:
            user = request.user
            verificacao_propria = user == self.servidor.get_user()
            if user.is_superuser or verificacao_propria or user.has_perm('contracheques.pode_ver_contracheques_detalhados'):
                self.tem_permissao_visualizacao = True
                return True
        return False

    def get_titulacao_por_contracheque(self, tabelaiq=None, tabelart=None):
        CODIGOS_RUBRICA_TECNICO = ['82926', '82918', '82919', '82920', '82921', '82922', '82923', '82924', '82925', '82462']
        CODIGOS_RUBRICA_DOCENTE = ['82606']

        CODIGOS_RUBRICA_DOCENTE_RSC = ['82915', '82916']
        tabelaiq = tabelaiq or tiq
        tabelart = tabelart or trpt

        def encontra_titulacao(valor1, valor2=None, cargo_classe=None, tabelaiq=None, tabelart=None):
            if valor2:
                # a consulta consiste em descobrir qual a titulação de um servidor de acordo com o valor do benefício recebido, porém
                # pode acontecer do servidor receber 10%, por exemplo, e esse benefício corresponder a duas titulações distintas
                # (10% para técnico quando for relação direta ou 10% para graduação quando for relação indireta) dependendo da relação
                # do curso com a área de atuação. por este motivo este método retorna uma string contendo as titulações possíveis
                titulacao = None

                for r in tabelaiq[cargo_classe]:
                    if valor1:
                        porcentagem = f'{round(float((valor2 / valor1) * 100)):.0f}%'
                    else:
                        porcentagem = '0%'
                    if porcentagem in tabelaiq[cargo_classe][r]:
                        if not titulacao:
                            titulacao = tabelaiq[cargo_classe][r][porcentagem]
                        else:
                            titulacao = f'{titulacao} / {tabelaiq[cargo_classe][r][porcentagem]}'
                if titulacao:
                    return {'classe': cargo_classe, 'relacao': r, 'titulacao': titulacao, 'porcentagem': porcentagem}
            else:
                for j in tabelart:
                    for c in tabelart[j]:
                        for n in tabelart[j][c]:
                            for t in tabelart[j][c][n]:
                                if float(valor1) == tabelart[j][c][n][t]:
                                    return {'jornada': j, 'classe': c, 'nivel': n, 'titulacao': t, 'valor': valor1}
            return {}

        titulacao = None
        possui_titulacao = False
        possui_rubrica = False
        dict_contracheque = None
        referencia = None
        if (not self.servidor_situacao or self.servidor_situacao.nome != 'INSTITUIDOR PENSAO') and self.servidor_cargo_emprego:
            if self.servidor_cargo_emprego.grupo_cargo_emprego.categoria == 'tecnico_administrativo':
                rubricas = Rubrica.objects.filter(codigo__in=CODIGOS_RUBRICA_TECNICO)
            else:
                rubricas = Rubrica.objects.filter(codigo__in=CODIGOS_RUBRICA_DOCENTE + CODIGOS_RUBRICA_DOCENTE_RSC)

            ccrs = self.contrachequerubrica_set.filter(rubrica__in=rubricas, tipo__nome__unaccent__icontains='rendimento', sequencia__lt=6)

            vencimento = self.contrachequerubrica_set.filter(rubrica__codigo='00001', tipo__nome__unaccent__icontains='rendimento', sequencia=0)
            # Alguns tecnicos recebem complementos e esses devem ser somados ao vencimento para calcular o incentivo
            complemento = self.contrachequerubrica_set.filter(rubrica__codigo='82374', tipo__nome__unaccent__icontains='rendimento', sequencia=1)
            if complemento.exists():
                complemento = complemento.first().valor
            else:
                complemento = 0
            if vencimento:
                referencia = vencimento[0].valor + complemento
            else:
                referencia = complemento

            for ccr in ccrs:
                if ccr.rubrica.codigo in CODIGOS_RUBRICA_TECNICO:
                    dict_contracheque = encontra_titulacao(
                        valor1=referencia,
                        valor2=ccr.valor,
                        cargo_classe=self.servidor_cargo_classe.codigo,
                        tabelaiq=tabelaiq,
                        tabelart=tabelart,
                    )
                    possui_rubrica = True
                elif ccr.rubrica.codigo in CODIGOS_RUBRICA_DOCENTE:
                    dict_contracheque = encontra_titulacao(ccr.valor, tabelaiq=tabelaiq, tabelart=tabelart)
                    possui_rubrica = True
                elif ccr.rubrica.codigo in CODIGOS_RUBRICA_DOCENTE_RSC:
                    dict_contracheque = encontra_titulacao(ccr.valor, tabelaiq=tabelaiq, tabelart=tabelart)
                    if dict_contracheque.get('titulacao') == 'DOUTORADO':
                        dict_contracheque['titulacao'] = 'MESTRE+RSC-III (LEI 12772/12 ART 18)'
                    elif dict_contracheque.get('titulacao') == dict_contracheque.get('titulacao') == 'MESTRADO':
                        dict_contracheque['titulacao'] = 'POS-GRADUAÇÃO+RSC-II LEI 12772/12 ART 18'
                    elif dict_contracheque.get('titulacao') == 'ESPECIALIZACAO NIVEL SUPERIOR':
                        dict_contracheque['titulacao'] = 'GRADUAÇÃO+RSC-I LEI 12772/12 ART 18'
                    possui_rubrica = True
                if dict_contracheque:
                    possui_titulacao = True
                    break
            if possui_rubrica and possui_titulacao:
                if self.servidor.titulacao and dict_contracheque['titulacao'] and self.servidor.titulacao.nome in dict_contracheque['titulacao']:
                    titulacao = self.servidor.titulacao
                else:
                    titulacao = Titulacao.objects.filter(nome__unaccent__icontains=dict_contracheque['titulacao'])
                    titulacao = titulacao and titulacao[0] or None
            return titulacao

    def insere_contra_cheque_rubrica(
        self,
        rendimento_desconto,
        codigo_rubrica,
        sequencia,
        valor,
        prazo,
        beneficiario_nome=None,
        beneficiario_banco=None,
        beneficiario_agencia=None,
        beneficiario_ccor=None,
    ):
        try:
            r = Rubrica.objects.get(codigo=codigo_rubrica)
        except Rubrica.DoesNotExist:
            r = Rubrica(codigo=codigo_rubrica, nome='REALIZAR EXTRACAO PARA RUBRICAS')
            r.save()
        t = TipoRubrica.objects.get_or_create(codigo=rendimento_desconto)[0]
        seq = int(sequencia)
        b = None
        if beneficiario_nome and beneficiario_nome.strip():
            nome = normalizar_nome_proprio(beneficiario_nome)
            # Beneficiarios nao tem identificadores unicos como matricula ou cpf. E complicado mas o jeito e buscar
            # conjuntamente pelo nome, banco e etc ja que e comum ocorrer homonimos com nomes.
            b = Beneficiario.objects.get_or_create(nome=nome, banco=beneficiario_banco, agencia=beneficiario_agencia, ccor=beneficiario_ccor)[0]
        ContraChequeRubrica.objects.get_or_create(contra_cheque=self, rubrica=r, tipo=t, valor=valor, beneficiario=b, sequencia=seq, prazo=prazo)


class RubricasQuery(models.QuerySet):
    def usadas_no_if(self):
        return self.filter(id__in=ContraChequeRubrica.objects.values_list('rubrica', flat=True))


class RubricasManager(models.Manager):
    def usadas_no_if(self):
        return self.get_queryset().usadas_no_if()

    def get_queryset(self):
        return RubricasQuery(self.model, using=self._db)


class Rubrica(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome']

    codigo = models.CharField(max_length=5, unique=True)
    excluido = models.BooleanField(default=False)
    nome = models.CharField(max_length=40)

    objects = RubricasManager()

    def __str__(self):
        return self.nome


class Beneficiario(models.ModelPlus):
    nome = models.CharField(max_length=40)
    banco = models.ForeignKeyPlus('rh.Banco', null=True, on_delete=models.CASCADE)
    agencia = models.CharField(max_length=6, null=True)
    ccor = models.CharField(max_length=13, null=True)

    class Meta:
        verbose_name = 'Beneficiário'
        verbose_name_plural = 'Beneficiários'

    def __str__(self):
        return self.nome


class TipoRubrica(models.ModelPlus):
    nome = models.CharField(max_length=20)
    codigo = models.CharField(max_length=2)

    class Meta:
        verbose_name = 'Tipo de Rubrica'
        verbose_name_plural = 'Tipos de Rubricas'

    def __str__(self):
        return self.nome


class ContraChequeRubrica(models.ModelPlus):
    contra_cheque = models.ForeignKeyPlus(ContraCheque, on_delete=models.CASCADE)
    rubrica = models.ForeignKeyPlus(Rubrica, null=True, on_delete=models.CASCADE)
    beneficiario = models.ForeignKeyPlus(Beneficiario, null=True, on_delete=models.CASCADE)
    tipo = models.ForeignKeyPlus(TipoRubrica, null=True, on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus(null=True)
    sequencia = models.IntegerField(null=True)
    prazo = models.CharField(max_length=3, null=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Rubrica de Contracheque'
        verbose_name_plural = 'Rubricas de Contracheques'

    def __str__(self):
        return f'{self.rubrica} {self.valor}'


class AgrupamentoRubricas(models.ModelPlus):
    descricao = models.CharField(max_length=150, null=False)
    rubricas = models.ManyToManyFieldPlus(Rubrica)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Agrupamento de Rubrica'
        verbose_name_plural = 'Agrupamento de Rubricas'
