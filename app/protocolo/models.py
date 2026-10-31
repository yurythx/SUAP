import re
from datetime import datetime
from functools import reduce

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.safestring import mark_safe

from comum.models import Configuracao, Vinculo
from comum.utils import get_setor, get_sigla_reitoria, get_todos_setores, tl
from djtools.db import models
from rh.models import Setor, UnidadeOrganizacional


class ProcessoQuery(models.QuerySet):
    def da_pessoafisica(self, pessoa_fisica):
        return self.filter(interessado_pf=True, interessado_documento=pessoa_fisica.cpf)


class ProcessoManager(models.Manager):
    def get_queryset(self):
        return ProcessoQuery(self.model, using=self._db)

    def da_pessoafisica(self, pessoa_fisica):
        return self.get_queryset().da_pessoafisica(pessoa_fisica)


class Processo(models.ModelPlus):
    SEARCH_FIELDS = ['numero_processo', 'numero_processo_eletronico']

    STATUS_EM_TRAMITE = 1
    STATUS_FINALIZADO = 2
    STATUS_ARQUIVADO = 3

    PROCESSO_STATUS = [[STATUS_EM_TRAMITE, 'Em trâmite'], [STATUS_FINALIZADO, 'Finalizado'], [STATUS_ARQUIVADO, 'Arquivado']]

    TIPO_MEMORANDO = 1
    TIPO_OFICIO = 2
    TIPO_REQUERIMENTO = 3

    PROCESSO_TIPO = [[TIPO_MEMORANDO, 'Memorando'], [TIPO_OFICIO, 'Ofício'], [TIPO_REQUERIMENTO, 'Requerimento']]

    data_cadastro = models.DateTimeField(auto_now_add=True)
    vinculo_cadastro = models.ForeignKeyPlus(
        Vinculo, related_name='processos_cadastro', editable=False, default=tl.get_vinculo, on_delete=models.CASCADE
    )
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, editable=False, on_delete=models.CASCADE)
    interessado_nome = models.UnaccentField('Nome do Interessado', max_length=200, db_index=True)
    interessado_documento = models.CharField('CPF/CNPJ do Interessado', max_length=20)
    interessado_pf = models.BooleanField('É Pessoa Física?', default=True)
    interessado_email = models.EmailField('Email do Interessado', blank=True)
    interessado_telefone = models.CharFieldPlus('Telefone do Interessado', null=True, blank=True)

    # NUP 17
    numero_processo = models.CharField('Número do Processo', max_length=25, editable=False, unique=True)

    # Caso "numero_processo_eletronico" seja diferente de null, então o processo em questão é eletrônico e foi gerado
    # um registro aqui no módulo de Protocolo apenas por conta da necessidade atual do módulo de processo eletrônico
    # ter um identificador com NUP 17 devido a sistemas do governo que ainda não estão, INDEVIDAMENTE, usando o NUP 21,
    # contrariando determinação do próprio governo.
    # NUP 21
    numero_processo_eletronico = models.CharField('Número do Processo Eletrônico', max_length=25, editable=False, blank=True, null=True)

    numero_documento = models.CharField('Número do Documento', max_length=25, null=True, blank=True)
    assunto = models.CharField(max_length=100)
    tipo = models.PositiveIntegerField(choices=PROCESSO_TIPO)
    status = models.PositiveIntegerField('Situação', choices=PROCESSO_STATUS, editable=False, default=STATUS_EM_TRAMITE)
    setor_origem = models.ForeignKeyPlus(Setor, verbose_name='Setor de Origem', default=get_setor, editable=False, on_delete=models.CASCADE)
    palavras_chave = models.TextField('Palavras-chave', null=True)

    # Dados armazenados no caso do status do processo ser "Finalizado".
    data_finalizacao = models.DateTimeField(editable=False, null=True)
    vinculo_finalizacao = models.ForeignKeyPlus(Vinculo, related_name='processos_finalizacao', editable=False, null=True, on_delete=models.CASCADE)
    observacao_finalizacao = models.TextField('Despacho', null=True, blank=True)
    search = models.SearchField(
        attrs=(
            'numero_processo',
            'numero_processo_eletronico',
            'numero_documento',
            'interessado_nome',
            'assunto',
            'palavras_chave',
            'observacao_finalizacao',
        )
    )

    objects = ProcessoManager()
    todos = models.Manager()

    class Meta:
        verbose_name = 'Processo'
        verbose_name_plural = 'Processos'
        permissions = (
            ('pode_editar_processo_em_tramite', 'Pode editar processo em trâmite'),
            ('pode_editar_processo_sem_tramite_completo', 'Pode editar processo sem trâmite completo'),
            ('pode_gerar_capa', 'Pode gerar capa'),
            ('pode_imprimir_comprovante', 'Pode imprimir comprovante'),
            ('pode_ver_processo', 'Pode ver processo'),
            ('pode_tramitar_processo', 'Pode tramitar processo'),
        )

    def __str__(self):
        if self.numero_processo_eletronico:
            exibir_numeracao_nup21 = bool(Configuracao.get_valor_por_chave('processo_eletronico', 'exibir_numeracao_nup21'))
            if exibir_numeracao_nup21:
                return self.numero_processo_eletronico
        return self.numero_processo

    def get_ext_combo_template(self):
        out = [f'{self}']
        out.append(f'<span class="disabled">Pessoa Interessada: {self.interessado_nome}</span>')
        if not hasattr(self, 'assunto'):
            out.append('<span class="false">Não possui assunto</span>')
        else:
            out.append(f'<span class="disabled">Assunto: {self.assunto}</span>')
        template = """
        <div style="overflow: hidden">
            <div style="float: left">
                {}
            </div>
        </div>
        """.format('<br/>'.join(out))
        return template

    @transaction.atomic()
    def save(self, *args, **kwargs):
        if not self.pk:
            self.numero_processo = self.get_proximo_numero_processo()
            if self.vinculo_cadastro.relacionamento.setor and self.vinculo_cadastro.relacionamento.setor.uo:
                self.uo = self.vinculo_cadastro.relacionamento.setor.uo
            elif self.vinculo_cadastro.relacionamento.setor_lotacao:
                self.uo = self.vinculo_cadastro.relacionamento.setor_lotacao.uo.equivalente
            else:
                self.uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
        else:
            if self.tem_vinculo_com_processo_eletronico:
                if not (hasattr(self, 'operacao_via_modulo_processo_eletronico') and self.operacao_via_modulo_processo_eletronico):
                    raise PermissionDenied('Para editar este processo acesse o módulo de Processos Eletrônicos.')

        try:
            with transaction.atomic():
                super().save(*args, **kwargs)
        except IntegrityError as e:
            # Atribui ao numero_processo o valor do próximo NUP 17 para resolver problema que acontecia
            # de retornar o mesmo NUP 17 para duas transações concorrentes.
            # Exemplo da mensagem de erro:
            # UniqueViolation: duplicate key value violates unique constraint "protocolo_processo_numero_processo_key"
            # DETAIL:  Key (numero_processo)=(23035.003047.2024-17) already exists.
            if 'protocolo_processo_numero_processo_key' in ''.join(e.args):
                self.numero_processo = self.get_proximo_numero_processo()
                super().save(*args, **kwargs)
            else:
                raise e

    def delete(self, using=None, keep_parents=False):
        if self.tem_vinculo_com_processo_eletronico:
            if not (hasattr(self, 'operacao_via_modulo_processo_eletronico') and self.operacao_via_modulo_processo_eletronico):
                raise PermissionDenied('Para remover este processo acesse o módulo de Processos Eletrônicos.')

        return super().delete(using, keep_parents)

    def get_absolute_url(self):
        try:
            if self.numero_processo_eletronico and 'processo_eletronico' in settings.INSTALLED_APPS:
                ProcessoNup21 = apps.get_model('processo_eletronico', 'Processo')
                processo_nup_21 = ProcessoNup21.objects.get(numero_protocolo=self.numero_processo_eletronico)
                return processo_nup_21.get_absolute_url()
            else:
                return f'/protocolo/processo/{self.id}/'
        except ObjectDoesNotExist:
            pass

    def get_url_consulta_publica(self):
        try:
            if self.numero_processo_eletronico and 'processo_eletronico' in settings.INSTALLED_APPS:
                ProcessoNup21 = apps.get_model('processo_eletronico', 'Processo')
                processo_nup_21 = ProcessoNup21.objects.get(numero_protocolo=self.numero_processo_eletronico)
                return processo_nup_21.get_absolute_url_consulta_publica()
            else:
                return f'/protocolo/visualizar_processo_consulta_publica/{self.id}/'
        except ObjectDoesNotExist:
            pass

    @property
    def tem_vinculo_com_processo_eletronico(self):
        return self.numero_processo_eletronico is not None

    @classmethod
    def get_pendentes(cls):
        return cls.objects.filter(status=cls.STATUS_EM_TRAMITE)

    def get_proximo_numero_processo(self):
        # Obtendo o código do protocolo.
        codigo_protocolo = self.get_codigo_protocolo()
        if not codigo_protocolo:
            raise Exception("Não foi possível obter o 'código do protocolo', necessário para a geração do número do processo.")

        # Ano corrente.
        ano_corrente = datetime.today().year

        try:
            ultimo_processo_ano = Processo.objects.filter(data_cadastro__year=ano_corrente, numero_processo__startswith=codigo_protocolo).latest('id')
            bloco_numero = ultimo_processo_ano.numero_processo.split('.')[1]
            proximo_id_processo = int(bloco_numero.split(settings.NUM_PROCESSO_DIVISOR_SUFIXO)[0]) + 1
        except Processo.DoesNotExist:
            # Ainda não existe nenhum processo no ano corrente
            proximo_id_processo = 1

        # Montando o número do processo.
        # Inicialmente o número do processo é montando formatado de maneira básica, somente com os
        # números. Os dígitos verificadores não estão presentes.
        # Ex: 040000014122000
        numero_processo = f'{codigo_protocolo}{proximo_id_processo:06d}{ano_corrente:4d}'

        # Calculando o primeiro digito verificador.
        dv1 = (11 - (reduce(lambda x, y: x + y, [int(numero_processo[::-1][x - 2]) * x for x in range(16, 1, -1)]) % 11)) % 10

        # Calculando o segundo digito verificador.
        numero_processo = numero_processo + str(dv1)
        dv2 = (11 - (reduce(lambda x, y: x + y, [int(numero_processo[::-1][x - 2]) * x for x in range(17, 1, -1)]) % 11)) % 10

        # Número do processo completamente calculado e formatado.
        # Ex: 04000.001412/2000-26
        numero_processo = f'{codigo_protocolo}.{proximo_id_processo:06d}{settings.NUM_PROCESSO_DIVISOR_SUFIXO}{ano_corrente:4d}-{dv1}{dv2}'

        return numero_processo

    def get_numero(self):
        exibir_numeracao_nup21 = Configuracao.get_valor_por_chave('processo_eletronico', 'exibir_numeracao_nup21')
        return self.numero_processo_eletronico if exibir_numeracao_nup21 else self.numero_processo

    @classmethod
    def get_numero_formatado_com_digito(cls, prefixo, contador, ano):
        """
        Retorna número formatado e com os dígitos verificadores

        >>> Processo.get_numero_formatado_com_digito(23057, 20703, 2010)
        '23057.020703.2010-84'
        """

        numero = f'{prefixo}{contador:06d}{ano:4d}'
        if len(numero) != 15:
            raise ValueError(f'O numero deve ter 15 digitos, recebido {len(numero)} ({numero})')

        # Dígito verificador 1
        dv1 = (11 - (reduce(lambda x, y: x + y, [int(numero[::-1][x - 2]) * x for x in range(16, 1, -1)]) % 11)) % 10

        # Dígito verificador 2
        numero = numero + str(dv1)
        dv2 = (11 - (reduce(lambda x, y: x + y, [int(numero[::-1][x - 2]) * x for x in range(17, 1, -1)]) % 11)) % 10

        return f'{prefixo}.{contador:06d}{settings.NUM_PROCESSO_DIVISOR_SUFIXO}{ano:4d}-{dv1}{dv2}'

    @classmethod
    def get_numero_formatado_from_texto_busca(cls, texto_busca_numero_processo):
        """
        Este método retorna o número do processo formatado caso o usuário tenha digitado o código completo (com ou sem
        formatação) ou se o número do processo foi informado a partir da leitura do código de barras. Caso contrário,
        o retorno será o mesmo conteúdo informado, pois o usuário pode estar querendo fazer uma busca por parte do número
        do processo.

        :param texto_busca_numero_processo
        :return: numero do processso formatado
        """
        numero_processo_formatado = None

        if texto_busca_numero_processo:
            texto_busca_numero_processo = texto_busca_numero_processo.strip()
            numero_processo_formatado = texto_busca_numero_processo

            # Deixando somente os números contidos na string.
            # Ex: 23057.018986.2016-90 vira 23057018986201690
            numero_processo_formatado = re.sub(r'\D', '', numero_processo_formatado)

            # Verificando se o usuário digitou o número do processo com seu tamanho máximo (17 dígitos) ou se o número em
            # questão veio da leitura do código de barras (18 dígitos). Se sim, então a formatação será realizada.
            # Ex: 23057018986201690 ou 023057018986201690.
            if len(numero_processo_formatado) in (17, 18):
                if numero_processo_formatado.startswith('0') and len(numero_processo_formatado) == 18:
                    # Removendo o primeiro zero à esquerda, pois é algo inerente exclusivamente ao código de barras.
                    numero_processo_formatado = numero_processo_formatado[1:]

                # O número do processo é composto de 13 a 17 dígitos. Como o código do protocolo é string e pode ter
                # tamanho variável entre 1 e 5, faremos a decomposição do número da direita pra esquerda, que é de
                # tamanho fixo.
                # Ex: 23057 018986 2016 90
                #
                # Decompondo da direita pra esquerda:
                # - codigo_verificador (tamanho fixo: 2): 90
                # - ano (tamanho fixo: 4): 2016
                # - id_processo (tamanho fixo: 6): 018986
                # - codigo_protocolo (tamanho variavel: de 1 até 5. Normalmente fica em 5 dígitos): 23057
                codigo_verificador = numero_processo_formatado[-2:]
                ano = numero_processo_formatado[-6:-2]
                id_processo = numero_processo_formatado[-12:-6]
                codigo_protocolo = numero_processo_formatado[:-12]

                # Ao final teremos 23057.018986.2016-90.
                numero_processo_formatado = f'{codigo_protocolo}.{id_processo}{settings.NUM_PROCESSO_DIVISOR_SUFIXO}{ano}-{codigo_verificador}'

            # Caso contrário a formatação é abortada.
            else:
                numero_processo_formatado = None

        # Retornando o número do processo formatado, caso a formatação possa ter sido realizada, ou então retorna-se o
        # número do processo da mesma forma que foi recebida pelo método. Isso é necessário pois o usuário pode estar
        # querendo fazer a busca com base apenas em parte do número do processo.
        return numero_processo_formatado or texto_busca_numero_processo

    def get_codigo_protocolo(self):
        codigo_protocolo = None
        if self.vinculo_cadastro.relacionamento.setor and self.vinculo_cadastro.relacionamento.setor.uo:
            codigo_protocolo = self.vinculo_cadastro.relacionamento.setor.uo.codigo_protocolo
        elif self.vinculo_cadastro.relacionamento.setor_lotacao and self.vinculo_cadastro.relacionamento.setor_lotacao.uo:
            codigo_protocolo = self.vinculo_cadastro.relacionamento.setor_lotacao.uo.equivalente.codigo_protocolo
        elif self.vinculo_cadastro.eh_servidor() and self.vinculo_cadastro.relacionamento.eh_aposentado:
            codigo_protocolo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria()).codigo_protocolo

        return codigo_protocolo or ''

    def get_link_form_edicao(self):
        return mark_safe(f'<a href="/protocolo/processo/{self.id}/editar">{self.numero_processo}</a>')

    get_link_form_edicao.short_description = 'Número do processo'

    def get_ultimo_tramite(self):
        ultimo_tramite = Tramite.objects.filter(processo=self).order_by('-ordem')[:1]
        if ultimo_tramite.exists():
            return ultimo_tramite[0]
        else:
            return None

    def get_orgao_responsavel_atual(self):
        # Se o processo está arquivado, então será exibido o setor no qual
        # o processo encontra-se arquivado.

        if self.status == self.STATUS_ARQUIVADO:
            return None
        # Caso contrário, exibi-se o setor do último trâmite realizado.
        else:
            ultimo_tramite = self.get_ultimo_tramite()
            if ultimo_tramite is not None:
                if ultimo_tramite.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_INTERNO:
                    if ultimo_tramite.data_recebimento:
                        return ultimo_tramite.orgao_interno_recebimento
                    else:
                        return ultimo_tramite.orgao_interno_encaminhamento
                else:
                    if ultimo_tramite.data_recebimento:
                        return ultimo_tramite.orgao_vinculo_externo_recebimento
                    else:
                        return ultimo_tramite.orgao_interno_encaminhamento

    def get_vinculo_responsavel_atual(self):
        if self.status == self.STATUS_ARQUIVADO:
            return None
        else:
            ultimo_tramite = self.get_ultimo_tramite()
            if ultimo_tramite is not None:
                if ultimo_tramite.data_recebimento:
                    return ultimo_tramite.vinculo_recebimento
                else:
                    return ultimo_tramite.vinculo_encaminhamento

    def tramitavel(self):
        return self.status == self.STATUS_EM_TRAMITE

    def remover_finalizacao(self):
        self.data_finalizacao = None
        self.vinculo_finalizacao = None
        self.observacao_finalizacao = None
        self.status = Processo.STATUS_EM_TRAMITE
        self.save()

    def is_atrasado(self):
        # Inicialmente só considera trâmites entre órgãos internos
        if not self.get_ultimo_tramite():
            return False
        if (
            self.status == Processo.STATUS_EM_TRAMITE
            and not self.get_ultimo_tramite().data_recebimento
            and self.get_ultimo_tramite().orgao_interno_recebimento
            and self.get_ultimo_tramite().orgao_interno_encaminhamento
        ):
            intervalo = datetime.today() - self.get_ultimo_tramite().data_encaminhamento
            origem = (self.get_ultimo_tramite()).orgao_interno_encaminhamento.uo
            destino = (self.get_ultimo_tramite()).orgao_interno_recebimento.uo
            horas = intervalo.seconds / 3600
            intervalo_horas = intervalo.days * 24 + horas
            try:
                return intervalo_horas >= TempoTramite.objects.get(uo_origem=origem, uo_destino=destino).tempo_maximo
            except ObjectDoesNotExist:
                if origem == destino:
                    valor_padrao = Configuracao.get_valor_por_chave('protocolo', 'tempo_tramite_mesmo_campus')
                else:
                    valor_padrao = Configuracao.get_valor_por_chave('protocolo', 'tempo_tramite_diferentes_campi')
                if valor_padrao and valor_padrao != 'VALOR EM BRANCO':
                    return intervalo_horas >= int(valor_padrao)
                else:
                    return False
        elif (
            self.status == Processo.STATUS_EM_TRAMITE
            and self.get_ultimo_tramite().data_recebimento
            and self.get_ultimo_tramite().orgao_interno_recebimento
        ):
            intervalo = datetime.today() - self.get_ultimo_tramite().data_recebimento
            horas = intervalo.seconds / 3600
            intervalo_horas = intervalo.days * 24 + horas
            try:
                return intervalo_horas >= TempoAnalise.objects.get(setor=self.get_ultimo_tramite().orgao_interno_recebimento).tempo_maximo
            except ObjectDoesNotExist:
                valor_padrao = Configuracao.get_valor_por_chave('protocolo', 'tempo_analise')
                if valor_padrao and valor_padrao != 'VALOR EM BRANCO':
                    return intervalo_horas >= int(valor_padrao)
                else:
                    return False
        else:
            return False

    def pode_editar_processo(self, usuario):
        """
        Testa se o usuário pode editar o processo em questão. Atualmente apenas
        processos com status STATUS_EM_TRAMITE podem ser editados. Situações de
        edição:
        1) Processo sem nenhum trâmite completo
            a) Permissão ``pode_editar_processo_sem_tramite_completo``
            b) Permissão ``pode_editar_processo_em_tramite``
        2) Processo com algum trâmite completo
            b) Permissão ``pode_editar_processo_em_tramite``
        """

        # O processo deve ter status ``STATUS_EM_TRAMITE``
        if self.status != Processo.STATUS_EM_TRAMITE:
            return False

        # Testando se o processo tem algum trâmite completo
        tem_tramite_completo = self.tramite_set.filter(data_recebimento__isnull=False).exists()
        if tem_tramite_completo:
            return usuario.has_perm('protocolo.pode_editar_processo_em_tramite')
        else:
            return usuario.has_perm('protocolo.pode_editar_processo_em_tramite') or usuario.has_perm(
                'protocolo.pode_editar_processo_sem_tramite_completo'
            )

    def set_interessado(self, pessoa_interessada):
        interessado = pessoa_interessada
        interessado_nome = interessado.nome
        interessado_documento = interessado.get_cpf_ou_cnpj() or ''
        interessado_pf = hasattr(interessado, 'pessoafisica')
        interessado_email = interessado.email_notificacao
        interessado_telefone = interessado.pessoa.pessoatelefone_set.first() and interessado.pessoa.pessoatelefone_set.first().numero or ''

        self.interessado_nome = interessado_nome
        self.interessado_documento = interessado_documento
        self.interessado_pf = interessado_pf
        self.interessado_email = interessado_email
        self.interessado_telefone = interessado_telefone

    @staticmethod
    def get_protocolos_por_vinculo(vinculo):
        if not vinculo:
            return Processo.objects.none()
        # Cada condição é resolvida por índice e unida via UNION. Um OR atravessando o JOIN com trâmite
        # (ou uma subconsulta em `pk__in`) força o Postgres a varrer protocolo_processo e protocolo_tramite inteiras.
        processos_ids = (
            Processo.objects.filter(Q(vinculo_cadastro=vinculo) | Q(vinculo_finalizacao=vinculo))
            .order_by()
            .values('id')
            .union(
                Tramite.objects.filter(
                    Q(orgao_vinculo_externo_encaminhamento=vinculo) | Q(vinculo_encaminhamento=vinculo) | Q(vinculo_recebimento=vinculo)
                )
                .order_by()
                .values('processo_id')
            )
        )
        return Processo.objects.filter(pk__in=processos_ids)


class Tramite(models.ModelPlus):
    TIPO_ENCAMINHAMENTO_INTERNO = 1
    TIPO_ENCAMINHAMENTO_EXTERNO = 2

    TRAMITE_TIPO_ENCAMINHAMENTO = [[TIPO_ENCAMINHAMENTO_INTERNO, 'Interno'], [TIPO_ENCAMINHAMENTO_EXTERNO, 'Externo']]

    processo = models.ForeignKeyPlus(Processo, on_delete=models.CASCADE)
    # Ordem é o número do tramite.
    ordem = models.PositiveIntegerField(editable=True)
    ultimo = models.BooleanField(default=False)

    # Dados do envio do trâmite, ou seja, de onde ele está saíndo.
    tipo_encaminhamento = models.PositiveIntegerField(choices=TRAMITE_TIPO_ENCAMINHAMENTO, default=TIPO_ENCAMINHAMENTO_INTERNO)
    orgao_interno_encaminhamento = models.ForeignKeyPlus(
        Setor, related_name='tramites_internos_encaminhados_set', null=True, on_delete=models.CASCADE
    )
    orgao_vinculo_externo_encaminhamento = models.ForeignKeyPlus(Vinculo, related_name='tramites_vinculos_externos_encaminhados_set', null=True)
    vinculo_encaminhamento = models.ForeignKeyPlus(Vinculo, default=tl.get_vinculo, related_name='tramites_vinculos_encaminhados_set')
    data_encaminhamento = models.DateTimeField(db_index=True)
    observacao_encaminhamento = models.TextField('Despacho', null=True, blank=True)

    # Destino do tramite.
    orgao_interno_recebimento = models.ForeignKeyPlus(Setor, related_name='tramites_internos_recebidos_set', null=True, on_delete=models.CASCADE)
    orgao_vinculo_externo_recebimento = models.ForeignKeyPlus(Vinculo, related_name='tramites_vinculos_externos_recebidos_set', null=True)

    # Detalhes de quem recebeu o trâmite.
    data_recebimento = models.DateTimeField(null=True, db_index=True)
    vinculo_recebimento = models.ForeignKeyPlus(Vinculo, null=True, related_name='tramites_vinculos_recebidos_set')
    observacao_recebimento = models.TextField('Despacho', null=True, blank=True)

    class Meta:
        ordering = ['ordem']

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.processo.tem_vinculo_com_processo_eletronico:
            raise ValidationError('Esse processo possui vínculo com o processo eletrônico e não pode ser tramitado.')
        #
        super().save(*args, **kwargs)
        Tramite.objects.filter(processo=self.processo).update(ultimo=False)
        ultimo_id = Tramite.objects.filter(processo=self.processo).latest('ordem').id
        Tramite.objects.filter(id=ultimo_id).update(ultimo=True)

    def delete(self):
        models.Model.delete(self)
        # Organiza o atributo `ultimo` dos trâmites do processo
        if Tramite.objects.filter(processo=self.processo).exists():
            Tramite.objects.filter(processo=self.processo).latest('ordem').save()

    def __str__(self):
        return f'{self.processo.numero_processo} (Tramite: {self.ordem})'

    def is_interno(self):
        return self.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_INTERNO

    def is_externo(self):
        return self.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_EXTERNO

    @property
    def recebido(self):
        return bool(self.data_recebimento)

    @property
    def orgao_encaminhamento(self):
        """
        Verifica o tipo de trâmite (interno ou externo) e retorna o órgao adequado
        """
        if self.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_INTERNO:
            if self.orgao_vinculo_externo_encaminhamento:
                return self.orgao_vinculo_externo_encaminhamento
            return self.orgao_interno_encaminhamento
        elif self.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_EXTERNO:
            if self.ordem == 1:
                # Obrigatoriamente o primeiro encaminhamento é de um órgão interno
                return self.orgao_interno_encaminhamento
            if self.orgao_interno_encaminhamento:
                return self.orgao_interno_encaminhamento
            return self.orgao_vinculo_externo_encaminhamento

    @property
    def orgao_recebimento(self):
        """
        Verifica o tipo de trâmite (interno ou externo) e retorna o órgao adequado
        """
        if self.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_INTERNO:
            return self.orgao_interno_recebimento
        elif self.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_EXTERNO:
            return self.orgao_vinculo_externo_encaminhamento

    @classmethod
    def get_caixas(cls, setores=None):
        """
        Método criado para tornar mais rápida a visualização das caixas de entrada
        e saída, já que ``setores`` e ``processos`` só são calculados uma vez.
        """
        setores = setores or get_todos_setores()
        entrada = cls.get_caixa_entrada(setores)
        saida = cls.get_caixa_saida(setores)
        return {'entrada': entrada, 'saida': saida}

    @classmethod
    def get_caixa_entrada(cls, setores=None):
        """
        Retorna os trâmites em 2 situações
            1. Foram encaminhados PARA o setor e ainda não foram recebidos;
            2. Foram recebidos PELO setor e ainda não foram tramitados/finalizados;
        """
        if setores is None:
            setores = get_todos_setores()
        if get_setor() is None:
            param_select = {}
        else:
            param_select = {'compartilhado': f'orgao_interno_encaminhamento_id != {get_setor().pk}'}

        return (
            cls.objects.filter(
                ultimo=True,
                processo__status=Processo.STATUS_EM_TRAMITE,
                tipo_encaminhamento=Tramite.TIPO_ENCAMINHAMENTO_INTERNO,
                orgao_interno_recebimento__in=setores,
            )
            .extra(select=param_select)
            .select_related('processo', 'orgao_interno_encaminhamento', 'orgao_interno_recebimento', 'vinculo_encaminhamento')
        )

    @classmethod
    def get_caixa_saida(cls, setores=None):
        """
        Retorna os trâmites na seguinte situação:
            - Foram encaminhados PELO setor e ainda não foram recebidos no destino;
        """
        if setores is None:
            setores = get_todos_setores()
        if get_setor() is None:
            param_select = {}
        else:
            param_select = {'compartilhado': f'orgao_interno_encaminhamento_id != {get_setor().pk}'}
        return (
            cls.objects.filter(
                ultimo=True,
                orgao_interno_encaminhamento__in=setores,
                tipo_encaminhamento=Tramite.TIPO_ENCAMINHAMENTO_INTERNO,
                data_recebimento__isnull=True,
                processo__status=Processo.STATUS_EM_TRAMITE,
            )
            .extra(select=param_select)
            .select_related('processo', 'orgao_interno_encaminhamento', 'orgao_interno_recebimento', 'vinculo_encaminhamento')
        )

    @classmethod
    def get_caixa_tramitacao_externa(cls):
        """
        Retorna os trâmites externos que foram encaminhados por algum setor do
        usuário atual.
        """
        return cls.objects.filter(
            ultimo=True,
            orgao_interno_encaminhamento__in=get_todos_setores(),
            tipo_encaminhamento=Tramite.TIPO_ENCAMINHAMENTO_EXTERNO,
            processo__status=Processo.STATUS_EM_TRAMITE,
        )


class TempoTramite(models.ModelPlus):
    uo_origem = models.ForeignKeyPlus(UnidadeOrganizacional, related_name='tempo_tramite_origem', on_delete=models.CASCADE)
    uo_destino = models.ForeignKeyPlus(UnidadeOrganizacional, related_name='tempo_tramite_destino', on_delete=models.CASCADE)
    tempo_maximo = models.PositiveIntegerField()

    class Meta:
        unique_together = ('uo_origem', 'uo_destino')
        verbose_name = 'Tempo de trâmite'
        verbose_name_plural = 'Tempos de trâmite'

    def __str__(self):
        return f'{self.uo_origem} para {self.uo_destino}'


class TempoAnalise(models.ModelPlus):
    setor = models.ForeignKeyPlus(Setor, on_delete=models.CASCADE)
    tempo_maximo = models.PositiveIntegerField('Tempo máximo do processo em análise')

    class Meta:
        verbose_name = 'Tempo de análise'
        verbose_name_plural = 'Tempos de análise'

    def __str__(self):
        return f'{self.setor}'


def corrigir_tramite(request):
    processos = Processo.objects.all()
    for processo in processos:
        tramite = Tramite.objects.filter(processo=processo.id)
        detalhes = []
        for t in tramite:
            if t.ordem != 1:
                ordem = t.ordem - 1
                tramite_ordem = Tramite.objects.filter(ordem=ordem, processo=processo)
                qtd = len(tramite_ordem)
                for tram in tramite_ordem:
                    if tram.orgao_vinculo_externo_recebimento:
                        t.orgao_vinculo_externo_encaminhamento = tram.orgao_vinculo_externo_recebimento
                    else:
                        if qtd > 1:
                            if t.recebido:
                                t.orgao_interno_encaminhamento = tram.orgao_interno_recebimento
                        else:
                            t.orgao_interno_encaminhamento = tram.orgao_interno_recebimento

                    t.save()
    return locals()
