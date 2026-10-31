import decimal
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from tinymce.models import HTMLField

from dateutil.relativedelta import relativedelta
from django.apps.registry import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import F, Prefetch, Q
from django.db.models.aggregates import Avg, Count, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from comum import utils
from comum.models import Configuracao
from djtools.db import models, transaction
from djtools.utils import send_notification
from rh.models import Servidor, Setor, UnidadeOrganizacional
from typing import Any
from collections.abc import Callable, Iterable

assinatura_utils = __import__('progressoes', fromlist=['assinatura']).assinatura
installed_apps = settings.INSTALLED_APPS

logger = logging.getLogger(__name__)

# Padrões dos prazos e textos usados quando a ConfiguracaoProgressaoDocente não existe — ou
# quando o campo correspondente está NULL, o que é possível em todos eles (`null=True`).
CONFIGURACOES_PADRAO = {
    # preenchimento
    'tempo_preenchimento': 30,
    'txt_preenchimento': 'Sua avaliação de progressão docente foi liberada para preenchimento.',
    'txt_tempo_preenchimento_acabando': (
        'O tempo de preenchimento da sua avaliação de progressão docente está chegando ao fim. Preenche o mais rápido possível.'
    ),
    # avaliação
    'tempo_avaliacao': 10,
    'txt_avaliacao': 'Você foi selecionado para realizar avaliação de progressão docente. Acesse o suap para visualizar suas avaliações pendentes.',
    'txt_tempo_avaliacao_acabando': (
        'O tempo para realizar a avaliação de progressão docente está chegando ao fim. Acesso o sua e realize as avaliações que estão pendentes.'
    ),
    # ciência
    'tempo_ciencia': 2,
    'txt_alerta_ciencia': 'Você tem avaliação de progressão docente necessitando de ciência de resultado.',
    # edição e adição para reavaliação
    'tempo_adicao_edicao': 2,
    'txt_alerta_edicao_adicao_reavaliacao': 'Você tem avaliação de progressão docente aguardando edição ou adição de informações para reavaliação.',
    # reavaliação
    'tempo_reavaliacao': 2,
    'txt_alerta_reavaliacao': 'Você tem avaliação aguardando sua reavaliação.',
}


def _prefetch_relacionamentos_servidor() -> list:
    """Prefetches dos GFKs `relacionamento` dos responsáveis, já com `pessoa_fisica`.

    Resolve em poucas queries o N+1 da leitura de nome/matrícula (que delegam para
    `pessoa_fisica` via `__getattr__`) ao montar os conteúdos a assinar. Não altera o
    resultado: apenas evita uma query por item (e o hop extra para `pessoa_fisica`).
    """
    relacionamento_qs = [Servidor.objects.select_related('pessoa_fisica').only('matricula', 'pessoa_fisica__nome')]
    return [
        GenericPrefetch('responsavel__relacionamento', relacionamento_qs),
        GenericPrefetch('responsavel_avaliacao__relacionamento', relacionamento_qs),
    ]


# Create your models here.
class ProgressaoDocente(models.ModelPlus):
    # marca se `_load_configs` já rodou nesta instância (memoização; ver o método)
    _configs_carregadas = False

    ULTIMOS_NIVEIS = ['501', 'T1']
    INTERSTICIO_AVALIATIVO_MESES = 24
    INTERSTICIO_PRIMEIRA_PROMOCAO_MESES = 36
    MINIMO_PONTUACAO_APROVACAO = 60
    DIAS_ANTECEDENCIA_CALCULAR_NOVAS_PROGRESSOES = 90
    #
    TIPO_PROGRESSAO = 1
    TIPO_PROMOCAO = 2

    TIPO_CHOICES = (
        (TIPO_PROGRESSAO, 'Progressão'),
        (TIPO_PROMOCAO, 'Promoção'),
    )

    A_INICIAR = 1
    AGUARDANDO_PREENCHIMENTO = 2
    EM_AVALIACAO = 3
    RECURSO_AVALIACAO = 4
    REAVALIACAO = 5
    AGUARDANDO_CIENCIA_RESULTADO = 6
    CIENTE_RESULTADO = 7
    FINALIZADO = 8

    SITUACAO_CHOICES = (
        (A_INICIAR, 'A Iniciar'),
        (AGUARDANDO_PREENCHIMENTO, 'Aguardando Preenchimento'),
        (EM_AVALIACAO, 'Em Avaliação'),
        (RECURSO_AVALIACAO, 'Recurso da Avaliação'),
        (REAVALIACAO, 'Em Reavaliação'),
        (AGUARDANDO_CIENCIA_RESULTADO, 'Aguardando Ciência de Resultado'),
        (CIENTE_RESULTADO, 'Ciente de Resultado'),
        (FINALIZADO, 'Finalizado'),
    )

    SEARCH_FIELDS = ['avaliado__pessoa_fisica__nome', 'avaliado__matricula']

    NIVEIS_ENCADEADOS = {
        '101': 'D-I-01',
        '102': 'D-I-02',
        '201': 'D-II-01',
        '202': 'D-II-02',
        '301': 'D-III-01',
        '302': 'D-III-02',
        '303': 'D-III-03',
        '304': 'D-III-04',
        '401': 'D-IV-01',
        '402': 'D-IV-02',
        '403': 'D-IV-03',
        '404': 'D-IV-04',
        '501': 'D-V-01',  # nivel titular
    }

    NOVOS_NIVEIS_ENCADEADOS = {
        'A1': 'A1',
        'B1': 'B1',
        'B2': 'B2',
        'B3': 'B3',
        'B4': 'B4',
        'C1': 'C1',
        'C2': 'C2',
        'C3': 'C3',
        'C4': 'C4',
        'T1': 'T1',  # nível titular
    }

    # tipo de arquivo para aceleração da progressão
    ESPECIALIZACAO = 1
    MESTRADO_DOUTORADO = 2
    NAO_DESEJO_ACELERACAO = 3
    ACELERACAO_CHOICES = (
        (ESPECIALIZACAO, 'Especialização'),
        (MESTRADO_DOUTORADO, 'Mestrado/Doutorado'),
        (NAO_DESEJO_ACELERACAO, 'Não desejo aceleração'),
    )

    ACELERACAO_VALIDADA = 1
    ACELERACAO_INVALIDADA = 2
    VALIDACAO_ACELERACAO = (
        (ACELERACAO_VALIDADA, 'Aceleração Validada'),
        (ACELERACAO_INVALIDADA, 'Aceleração Invalidada'),
    )

    #
    avaliado = models.ForeignKeyPlus('rh.Servidor', verbose_name='Avaliado', on_delete=models.SET_NULL, null=True)
    data_inicio_periodo = models.DateFieldPlus('Data de Início do Período', null=False)
    data_fim_periodo = models.DateFieldPlus('Data de Fim do Período', null=True, blank=True)
    tipo = models.IntegerFieldPlus('Tipo', choices=TIPO_CHOICES, default=TIPO_PROGRESSAO, null=True, blank=True)
    situacao = models.IntegerFieldPlus('Situação', choices=SITUACAO_CHOICES, null=False, blank=False, default=A_INICIAR)
    ids_afastamentos_utilizados = models.CharFieldPlus('Afastamentos Utilizados', max_length=5000, null=True, blank=True)
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', auto_now=True)
    pontuacao_final_progressao = models.DecimalFieldPlus('Pontuação Final da Progressão', null=True, blank=True, max_digits=12, decimal_places=2)
    relatorio_a_progredir = models.ForeignKeyPlus(
        'progressao_docente.DocenteAProgredir', on_delete=models.SET_NULL, null=True, verbose_name='Relatório a Progredir Relacionado'
    )
    nivel_atual = models.CharFieldPlus('Nível Atual', null=True, blank=True)
    proximo_nivel = models.CharFieldPlus('Próximo Nível', null=True, blank=True)
    eh_primeira_promocao = models.BooleanField('É a primeira promoção?', default=False)
    #
    arquivo_aceleracao = models.FileFieldPlus(upload_to='progressao_docente/arquivos_aceleracao/', null=True, blank=True)
    tipo_aceleracao = models.IntegerFieldPlus(verbose_name='Tipo de Aceleração', choices=ACELERACAO_CHOICES, null=True, blank=True)
    pode_acelerar = models.BooleanField('Pode acelerar progressão?', default=False)
    #
    validacao_aceleracao = models.IntegerFieldPlus(verbose_name='Validação da Aceleração', choices=VALIDACAO_ACELERACAO, null=True, blank=True)
    motivo_invalidacao = models.TextField(verbose_name='Motivo da Invalidação', blank=True, null=True)
    #
    processo_eletronico = models.ForeignKeyPlus(
        'processo_eletronico.Processo', verbose_name='Processo Eletrônico', blank=True, null=True, on_delete=models.SET_NULL
    )
    #
    progressao_principal = models.ForeignKeyPlus(
        'progressao_docente.ProgressaoDocente',
        verbose_name='Progressão Principal',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        help_text='Selecione a progressão principal caso esta seja uma progressão complementar.',
    )
    progressao_complementar = models.BooleanField('Progressão Complementar?', default=False)

    class Meta:
        verbose_name = 'Progressão Docente'
        verbose_name_plural = 'Progressões Docente'
        permissions = (
            ('pode_ver_docente_a_progredir', 'Pode Ver o Docente a Progredir'),
            ('pode_ver_relatorio_docente_sem_database', 'Pode Ver Relatório de Docente sem Database'),
        )
        unique_together = (
            'avaliado',
            'data_inicio_periodo',
            'nivel_atual',
        )

    def __str__(self):
        return f'{self.avaliado} - [{self.nivel_atual} - {self.proximo_nivel}]'

    def get_absolute_url(self):
        return f'/progressao_docente/ver/{self.pk}/'

    def _load_configs(self, recarregar: bool = False) -> None:
        """Carrega os prazos e textos da ConfiguracaoProgressaoDocente sobre os padrões.

        Todo campo da configuração é anulável, e `tempo_adicao_edicao` foi campo morto até
        os prazos do ciclo de reavaliação passarem a ser aplicados — a linha
        CONFIG_EMAILS_TEMPOS existente pode perfeitamente tê-lo em NULL. Por isso o padrão
        é a base e a configuração só sobrescreve o que estiver preenchido: um NULL
        chegando a `timedelta(days=...)` abortaria o lote inteiro do cron.

        Memoizado por instância — a varredura e as listagens do admin chamam isto por
        avaliação, e sem cache cada chamada custava um SELECT.
        """
        if self._configs_carregadas and not recarregar:
            return
        for atributo, padrao in CONFIGURACOES_PADRAO.items():
            setattr(self, atributo, padrao)
        config = ConfiguracaoProgressaoDocente.objects.filter(descricao='CONFIG_EMAILS_TEMPOS').first()
        if config:
            for atributo in CONFIGURACOES_PADRAO:
                valor = getattr(config, atributo, None)
                if valor is not None:
                    setattr(self, atributo, valor)
        self._configs_carregadas = True

    def enviar_email(self, assunto, txt, avaliacao, destinatario):
        send_notification(assunto, txt, settings.DEFAULT_FROM_EMAIL, destinatario, categoria='Progressão Docente')
        avaliacao.data_ultima_notificacao = datetime.now()
        avaliacao.save()

    # notificação de via e-mail
    def enviar_email_alerta(self, ignorar_limite_tempo=False):
        #
        self._load_configs()
        hoje = datetime.now()
        destinatarios = []

        #
        # função de substituição que retorna o valor do dicionário ou a marcação original, caso o valor não esteja presente.
        def substituir_marcacoes(texto, dados):
            def substitutor(match):
                chave = match.group(1).strip()
                return str(dados.get(chave, f'{{{{ {chave} }}}}'))

            padrao = r'\{\{\s*(\w+)\s*\}\}'
            return re.sub(padrao, substitutor, texto)

        #
        dados = {
            'TOTAL_DIAS_PREENCHIMENTO': self.tempo_preenchimento,
            'NIVEL_ATUAL': self.nivel_atual,
            'PROXIMO_NIVEL': self.proximo_nivel,
            'TOTAL_DIAS_AVALIACAO': self.tempo_avaliacao,
            'LINK_AVALIACOES': settings.SITE_URL + reverse_lazy('admin:progressao_docente_avaliacao_changelist'),
            'LINK_PROGRESSAO': settings.SITE_URL
            + reverse_lazy('progressao_docente:ver_processo', current_app='progressao_docente', kwargs={'pk': self.id}),
            'LINK_PROGRESSOES': settings.SITE_URL + reverse_lazy('admin:progressao_docente_progressaodocente_changelist'),
        }
        #
        for avaliacao in self.avaliacao_set.exclude(situacao=Avaliacao.CONCLUIDA):
            #
            avaliado = self.avaliado.get_vinculo()
            avaliador = avaliacao.avaliadores.all().first().get_vinculo()
            #
            dados.update(
                {
                    'NOME_AVALIADO': avaliado.nome,
                    'NOME_AVALIADOR': avaliador.nome,
                }
            )
            #
            if avaliacao.data_liberacao_preenchimento:
                dados.update(
                    {
                        'DATA_LIBERACAO_PREENCHIMENTO': avaliacao.data_liberacao_preenchimento.date().strftime('%d/%m/%Y'),
                    }
                )
            #
            if avaliacao.data_liberacao_avaliacao:
                dados.update({'DATA_LIBERACAO_AVALIACAO': avaliacao.data_liberacao_avaliacao.date().strftime('%d/%m/%Y')})
            #
            if avaliacao.data_liberacao_reavaliacao:
                dados.update({'DATA_LIBERACAO_REAVALIACAO': avaliacao.data_liberacao_reavaliacao.date().strftime('%d/%m/%Y')})
            #
            # Verificar estado e aplicar lógica de envio de emails
            if avaliacao.situacao == Avaliacao.AGUARDANDO_PREENCHIMENTO:
                if avaliacao.data_liberacao_preenchimento:
                    #
                    dados.update(
                        {
                            'LINK_AVALIACAO': settings.SITE_URL
                            + reverse_lazy('progressao_docente:preencher', current_app='progressao_docente', kwargs={'pk': avaliacao.id}),
                        }
                    )
                    #
                    data_limite = avaliacao.data_liberacao_preenchimento + timedelta(days=self.tempo_preenchimento)
                    dias_restantes = (data_limite - hoje).days + 1
                    if dias_restantes < 0:
                        dias_restantes = 0
                    # Envio a cada 3 dias até restarem 10 dias, depois diariamente
                    destinatarios.append(avaliado)
                    if ignorar_limite_tempo or dias_restantes > 10:
                        if ignorar_limite_tempo or dias_restantes % 3 == 0:
                            self.enviar_email(
                                '[SUAP] Progressão Docente - Preenchimento',
                                substituir_marcacoes(self.txt_preenchimento, dados),
                                avaliacao=avaliacao,
                                destinatario=destinatarios,
                            )
                    elif ignorar_limite_tempo or dias_restantes <= 10:
                        self.enviar_email(
                            '[SUAP] Progressão Docente - Preenchimento',
                            substituir_marcacoes(self.txt_tempo_preenchimento_acabando, dados),
                            avaliacao=avaliacao,
                            destinatario=destinatarios,
                        )
                else:
                    # se a avaliação não tem uma data de liberação para preenchimento, enviamos o email com um texto padrão
                    self.enviar_email(
                        '[SUAP] Progressão Docente - Preenchimento',
                        'Foi liberada uma avaliação de progressão docente para você preencher. Acesse o suap e verifique as avaliações pendentes.',
                        avaliacao=avaliacao,
                        destinatario=destinatarios,
                    )
            #
            elif avaliacao.situacao == Avaliacao.EM_AVALIACAO:
                #
                dados.update(
                    {
                        'LINK_AVALIACAO': settings.SITE_URL
                        + reverse_lazy('progressao_docente:avaliar_processo', current_app='progressao_docente', kwargs={'pk': avaliacao.id}),
                    }
                )
                #
                data_limite = avaliacao.data_liberacao_avaliacao + timedelta(days=self.tempo_avaliacao)
                dias_restantes = (data_limite - hoje).days
                if dias_restantes < 0:
                    dias_restantes = 0
                #
                destinatarios.append(avaliador)
                # Envio a cada 2 dias até restarem 5 dias, depois diariamente
                if ignorar_limite_tempo or dias_restantes > 5:
                    if ignorar_limite_tempo or dias_restantes % 2 == 0:
                        self.enviar_email(
                            '[SUAP] Progressão Docente - Avaliação',
                            substituir_marcacoes(self.txt_avaliacao, dados),
                            avaliacao=avaliacao,
                            destinatario=destinatarios,
                        )
                elif ignorar_limite_tempo or dias_restantes <= 5:
                    self.enviar_email(
                        '[SUAP] Progressão Docente - Avaliação',
                        substituir_marcacoes(self.txt_tempo_avaliacao_acabando, dados),
                        avaliacao=avaliacao,
                        destinatario=destinatarios,
                    )
            #
            elif avaliacao.situacao in [Avaliacao.AGUARDANDO_CIENCIA_RESULTADO, Avaliacao.REAVALIACAO, Avaliacao.EDITACAO_PARA_REAVALIACAO]:
                # Envio diário
                if avaliacao.situacao == Avaliacao.REAVALIACAO:
                    destinatarios.append(avaliador)
                    self.enviar_email(
                        '[SUAP] Progressão Docente - Reavaliação',
                        substituir_marcacoes(self.txt_alerta_reavaliacao, dados),
                        avaliacao=avaliacao,
                        destinatario=destinatarios,
                    )
                elif avaliacao.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO:
                    destinatarios.append(avaliado)
                    self.enviar_email(
                        '[SUAP] Progressão Docente - Preenchimento para reavaliação',
                        substituir_marcacoes(self.txt_alerta_edicao_adicao_reavaliacao, dados),
                        avaliacao=avaliacao,
                        destinatario=destinatarios,
                    )
                elif avaliacao.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO:
                    destinatarios.append(avaliado)
                    self.enviar_email(
                        '[SUAP] Progressão Docente - Ciência de resultado',
                        substituir_marcacoes(self.txt_alerta_ciencia, dados),
                        avaliacao=avaliacao,
                        destinatario=destinatarios,
                    )

    def get_tipo_progressao(self):
        """Retorna o tipo (progressão ou promoção).

        Critério atual: compara o primeiro caractere (classe/padrão) do nível atual e do próximo nível.
        """
        # Usa fallback para nível atual, quando possível
        nivel_atual = self.nivel_atual or self._nivel_atual()
        proximo_nivel = self.proximo_nivel

        # Validações para evitar TypeError/IndexError
        if not nivel_atual or not str(nivel_atual).strip():
            raise ValidationError('Nível atual não informado ou inválido para determinar o tipo de progressão.')
        if not proximo_nivel or not str(proximo_nivel).strip():
            raise ValidationError('Próximo nível não informado ou inválido para determinar o tipo de progressão.')

        s_atual = str(nivel_atual).strip()
        s_prox = str(proximo_nivel).strip()

        _check1 = s_atual[0]
        _check2 = s_prox[0]
        return self.TIPO_PROGRESSAO if _check1 == _check2 else self.TIPO_PROMOCAO

    def gerar_processo_eletronico(self, avaliacoes_file, user):
        if 'processo_eletronico' in settings.INSTALLED_APPS:
            from processo_eletronico.models import Documento, TipoConferencia, TipoDocumento, TipoProcesso
            from processo_eletronico.models import Processo as ProcessoEletronico

            try:
                # configurações SUAP
                pk_tipo_processo = Configuracao.get_valor_por_chave('progressao_docente', 'pd_tipo_processo')
                pk_tipo_documento = Configuracao.get_valor_por_chave('progressao_docente', 'pd_tipo_documento')
                pk_tipo_conferencia = Configuracao.get_valor_por_chave('progressao_docente', 'pd_tipo_conferencia')
                if not pk_tipo_processo:
                    raise ValidationError('Configuração SUAP ausente: "Aplicação Progressão Docente > Tipo de processo (Processo Eletrônico)"')

                if not pk_tipo_documento:
                    raise ValidationError('Configuração SUAP ausente: "Aplicação Progressão Docente > Tipo de documento (Processo Eletrônico)"')

                if not pk_tipo_conferencia:
                    raise ValidationError('Configuração SUAP ausente: "Aplicação Progressão Docente > Tipo de conferência (Processo Eletrônico)"')

                setor_primeiro_tramite = self.calcular_setor_primeiro_tramite(self.avaliado.setor)
                tipo_processo = TipoProcesso.objects.get(pk=pk_tipo_processo)
                tipo_documento = TipoDocumento.objects.get(pk=pk_tipo_documento)
                tipo_conferencia = TipoConferencia.objects.get(pk=pk_tipo_conferencia)
                user_gerador_processo_eletronico = user
                assunto = None
                try:
                    tipo_proc = self.get_tipo_progressao()
                except ValidationError as e:
                    raise ValidationError(f'Erro ao definir assunto do processo eletrônico: {e}. Verifique nível atual e próximo.')
                if tipo_proc == self.TIPO_PROGRESSAO:
                    assunto = f'Progressão Funcional de {self.nivel_atual} para {self.proximo_nivel}'
                elif tipo_proc == self.TIPO_PROMOCAO:
                    assunto = f'Promoção por mérito de {self.nivel_atual} para {self.proximo_nivel}'
                processo_tramite = {'tipo_processo': tipo_processo, 'assunto': f'{assunto}', 'setor_destino': setor_primeiro_tramite}
                processo_documento_avaliacoes = {
                    'tipo': tipo_documento,
                    'tipo_conferencia': tipo_conferencia,
                    'assunto': assunto,
                    'nivel_acesso': Documento.NIVEL_ACESSO_PUBLICO,
                    'arquivo': avaliacoes_file,
                }
                self.processo_eletronico = ProcessoEletronico.cadastrar_processo(
                    user=user_gerador_processo_eletronico,
                    processo_tramite=processo_tramite,
                    papel=user_gerador_processo_eletronico.get_relacionamento().papeis_ativos.first(),
                    documentos_texto=[],
                    documentos_digitalizados=[processo_documento_avaliacoes],
                    interessados=[self.avaliado.get_vinculo()],
                )
                if not self.processo_eletronico:
                    raise Exception('Erro ao gerar o processo eletrônico.')
                self.save()
                avaliacoes_file.close()
            except ValidationError as error:
                raise error
            except Exception as error:
                raise Exception(f'{error}')
        else:
            raise ValidationError('App não encontrada: "A aplicação Processo Eletrônico não está configurada no installed apps do SUAP."')

    @staticmethod
    def _get_setor_reitoria_primeiro_tramite(uo):
        sigla_primeiro_tramite_reitoria = Configuracao.get_valor_por_chave('progressao_docente', 'pd_sigla_setor_primeiro_tramite_reitoria')
        # se reitoria, setor primeiro trâmite é codepe
        return uo.setor_set.filter(sigla=sigla_primeiro_tramite_reitoria).first()

    @staticmethod
    def calcular_setor_primeiro_tramite(setor_avaliado: Setor) -> Setor:
        #
        uo = setor_avaliado.uo
        setor = None
        if uo.eh_reitoria:
            setor = ProgressaoDocente._get_setor_reitoria_primeiro_tramite(uo)
        else:
            # senão, setor é cogpe, asgpe ou diape.
            # Sigla vazia ('ABC,' ou chave ausente) casaria qualquer setor no icontains: descarta.
            siglas = Configuracao.get_valor_por_chave_str('progressao_docente', 'pd_sigla_setor_primeiro_tramite_campus').split(',')
            siglas_primeiro_tramite_campus = [sigla.strip() for sigla in siglas if sigla.strip()]
            for sigla in siglas_primeiro_tramite_campus:
                setor = uo.setor_set.filter(sigla__icontains=sigla).first()
                if setor:
                    return setor
            # se não encontrar o setor de primeiro tramite nas configurações, o trâmite será similar ao da reitoria
            # forçando uo igual RE
            reitoria = UnidadeOrganizacional.objects.suap().filter(sigla=utils.get_sigla_reitoria()).first()
            if reitoria:
                setor = ProgressaoDocente._get_setor_reitoria_primeiro_tramite(reitoria)
        # Sem a reitoria ou sem o setor configurado nela, o trâmite seria criado sem destino.
        if setor:
            return setor
        raise ValidationError(
            'Configuração de primeiro trâmite do processo inexistente ou mau configurada. Por favor '
            'entrar em contato com o administraor do sistema para realizar essa configuração'
        )

    def eh_avaliador_processo(self, user):
        return any(user.get_relacionamento() in i.avaliadores.all() for i in self.avaliacao_set.all())

    @staticmethod
    def calcular_docentes_a_progredir(matriculas=None):
        qs_docentes = Servidor.objects.docentes().ativos()
        if matriculas:
            qs_docentes = qs_docentes.filter(matricula__in=matriculas)
        #
        for docente in qs_docentes:
            relatorio = None
            data_inicio = None
            _nivel_atual = None
            _padrao_atual = docente.cargo_classe.codigo if docente.cargo_classe else None
            _qs = DocenteAProgredir.objects.filter(avaliado=docente)
            # verificando se existe algum registro QUE NÃO foi criado ou finalizado
            # - caso positivo, pula a execução
            if _qs.filter(Q(progressao_criada=False) | Q(progressao_finalizada=False)).exists():
                continue
            # se chegou aqui, entende-se que todos os registros do relatório estão criados e finalizados
            # - neste caso, devemos ordenar os registros pela data_fim_contagem em ordem decrescente e pegar o primeiro registro encontrado para ser a base do processo
            _qs = _qs.order_by('-data_fim_contagem')
            if _qs.exists():
                relatorio = _qs.first()
            # se existir uma progressão, esta será utilizada como base de cálculo
            if relatorio:
                data_inicio = relatorio.data_fim_contagem + timedelta(days=1)
                # verificar se no processo o servidor foi aprovado
                if relatorio.progressaodocente_set.exists():
                    # pegando o processo de progressão para identificar se foi aprovado
                    _processo = relatorio.progressaodocente_set.first()
                    if _processo and _processo._aprovado():
                        # se aprovado, setar o próximo nível como nivel atual
                        _nivel_atual = relatorio.proximo_nivel
                    else:
                        # se não aprovado, mantem o nível
                        _nivel_atual = relatorio.nivel_atual
                else:
                    # se não encontrar processo, pegar o nível diretamente do servidor (assumindo que é o atual)
                    _nivel_atual = str(_padrao_atual) + str(docente.nivel_padrao)
            else:
                if not _qs.exists():
                    # se não existir, pegamos as informações base do próprio docente
                    data_inicio = docente.data_base_progressao
                    _nivel_atual = str(_padrao_atual) + str(docente.nivel_padrao)
            # verificando se o nível atual reenquadrado é A1 (novo padrão de nível)
            eh_primeira_promocao = False
            if _nivel_atual == 'A1':
                eh_primeira_promocao = True
            #
            if data_inicio:
                # obtendo informações da progressão
                pd = ProgressaoDocente()
                pd.data_inicio_periodo = data_inicio
                pd.avaliado = docente
                pd.eh_primeira_promocao = eh_primeira_promocao
                pd.calcular_data_fim()
                # verificando se o nível permite a progressão docente
                # - se o docente estiver no nível 501, já está no topo da carreira, não sendo necessário/permitido a progressão
                if docente.nivel_padrao not in ProgressaoDocente.ULTIMOS_NIVEIS:
                    # se necessário, cadastrar registro de docente a progredir
                    _qs_a_progredir = DocenteAProgredir.objects.filter(data_inicio_contagem=data_inicio, avaliado=docente)
                    if not _qs_a_progredir.exists():
                        nivel_atual = _nivel_atual
                        proximo_nivel = DocenteAProgredir.calcular_proximo_nivel(nivel_atual)
                        DocenteAProgredir.objects.create(
                            avaliado=pd.avaliado,
                            data_inicio_contagem=pd.data_inicio_periodo,
                            data_fim_contagem=pd.data_fim_periodo,
                            progressao_criada=False,
                            progressao_finalizada=False,
                            nivel_atual=nivel_atual,
                            proximo_nivel=proximo_nivel,
                            eh_primeira_promocao=eh_primeira_promocao,
                        )
            # verificando registros duplicados, mantendo apenas um registro com a progressão não criada e não finalizada
            for registro_duplicado in (
                DocenteAProgredir.objects.filter(avaliado=docente).exclude(progressao_criada=True, progressao_finalizada=True).order_by('id')[1:]
            ):
                registro_duplicado.delete()

    #
    def save(self, *args, **kwargs):
        if not self.id:
            # calcula data final da contagem
            self.calcular_data_fim()
        #
        super().save(*args, **kwargs)

    #
    def _adicionar_afastamento(self, novo_id_afastamento):
        if self.ids_afastamentos_utilizados is None:
            self.ids_afastamentos_utilizados = str(novo_id_afastamento)
        else:
            ids_atuais = self.ids_afastamentos_utilizados.split(',')
            if str(novo_id_afastamento) not in ids_atuais:
                ids_atuais.append(str(novo_id_afastamento))
                self.ids_afastamentos_utilizados = ','.join(ids_atuais)

    #
    def get_periodo_descricao(self):
        return f'{self.data_inicio_periodo.strftime("%d/%m/%Y")} a {self.data_fim_periodo.strftime("%d/%m/%Y")}'

    # retorna apenas a string pura com o nível do servidor
    def _nivel_atual(self):
        # se tem o nível atuali no processo, mostra ele
        if self.nivel_atual:
            return self.nivel_atual
        # se não tem nível no processo, vamos ver se existe algum processo de progressão anterior para calcularmos o próximo nível
        try:
            progressao_anterior = ProgressaoDocente.objects.filter(avaliado=self.avaliado, situacao=ProgressaoDocente.FINALIZADO).latest('pk')
            if progressao_anterior:
                return progressao_anterior.proximo_nivel
        except Exception:
            pass
        # se não, procura o nível no avaliado
        nivel = self.avaliado.nivel_padrao
        if self.nivel_atual:
            nivel = self.nivel_atual
        return nivel

    #
    def get_nivel_atual(self):
        """
        TODO: DEPRECATED
        - Esta definição será removida nas versões futuras
        """
        nivel = self._nivel_atual()
        return self.NOVOS_NIVEIS_ENCADEADOS.get(nivel, None)

    #
    def get_proximo_nivel(self, apenas_numeros=False):
        """
        TODO: DEPRECATED
        - Esta definição será removida nas versões futuras
        """
        parar = False
        nivel = self._nivel_atual()
        # calculando o próximo nível
        for k, v in self.NOVOS_NIVEIS_ENCADEADOS.items():
            if parar:
                if apenas_numeros:
                    return k
                return v
            if k == nivel:
                parar = True
        return None

    #
    @staticmethod
    def _gerar_dicionario_de_datas(inicio, fim):
        dicionario_datas = []
        data_atual = inicio

        while data_atual <= fim:
            dicionario_datas.append(data_atual.strftime('%d/%m/%Y'))
            data_atual += timedelta(days=1)

        return dicionario_datas

    #
    def _lista_dias_nao_cobertos(self):
        lista_dias_periodo_completo = self._gerar_dicionario_de_datas(self.data_inicio_periodo, self.data_fim_periodo)
        # verificando períodos das avaliações cadastradas
        for a in self.avaliacao_set.all():
            dias_periodo_avaliacao = self._gerar_dicionario_de_datas(a.periodo_inicio, a.periodo_fim)
            for dia in dias_periodo_avaliacao:
                if dia in lista_dias_periodo_completo:
                    lista_dias_periodo_completo.remove(dia)
        return lista_dias_periodo_completo

    #
    def iniciar_avaliacao(self):
        if self.pode_iniciar_avaliacao():
            self.situacao = self.AGUARDANDO_PREENCHIMENTO
            self.save()
            # verificando as avaliações cadastradas para o processo
            # - se tiver avaliação que necessita de avaliação discente, selecionar os discentes aptos
            for avaliacao in self.avaliacao_set.all():
                eh_avaliacao_discente = False
                for criterio in avaliacao.formulario.criterio_set.all():
                    if criterio.avaliacao_discente:
                        eh_avaliacao_discente = True
                        break
                if eh_avaliacao_discente:
                    # selecionando os discentes aptos
                    self.popular_discentes_aptos(avaliacao=avaliacao)
                # aqui é iniciada a avaliação, onde o primeiro passo e o preenchimento do avaliado
                # sendo necessário registrar a data
                avaliacao.data_liberacao_preenchimento = datetime.today()
                avaliacao.save()

            # TODO notificar avaliadores e avaliado sobre o início da avaliação

    #

    def finalizar(self):
        with transaction.atomic():
            if not self.progressao_complementar:
                #
                # recalcula a data final da contagem
                #
                data_fim_contagem_progressao_anterior = self.data_fim_periodo
                self.calcular_data_fim()
                data_fim_contagem_progressao_estava_errada = data_fim_contagem_progressao_anterior != self.data_fim_periodo
                if data_fim_contagem_progressao_estava_errada:
                    self.save()  # salva a data final que foi recalculada
                    return (
                        False,
                        'A data final da contagem foi recalculada e modificada de {} para {}. '
                        'Se for o caso, o trâmite do processo deve ser cancelado para que os ajustes nos '
                        'períodos de avaliação sejam realizados. Em seguida, o processo deve ser colocado '
                        'novamente em trâmite e, por fim, finalizado.'.format(
                            data_fim_contagem_progressao_anterior.strftime('%d/%m/%Y'), self.data_fim_periodo.strftime('%d/%m/%Y')
                        ),
                    )
            #
            # verificando períodos
            #
            lista_dias = self._lista_dias_nao_cobertos()
            if lista_dias:
                return (False, f'Existe(m) dia(s) do período avaliativo não coberto(s). Dias: {lista_dias}')

            #
            # chegou nesse ponto, está tudo OK com as avaliações, com as médias dos períodos e do processo e com a
            # data final da contagem
            #
            self.situacao = ProgressaoDocente.FINALIZADO
            self.save()
            self.calcular_pontuacao_final_processo()
            # #
            relatorio = self.relatorio_a_progredir
            if relatorio:
                relatorio.progressao_finalizada = True
                relatorio.save()

            return True, 'O processo foi finalizado.'

    #
    def calcular_pontuacao_final_processo(self):
        #
        # Aplica-se a seguinte fórmula
        # [NF =
        #   (nota no perfil I x nº de meses de enquadramento) +
        #   (nota no Perfil II x nº de meses de enquadramento) +
        #   (nota no Perfil III x nº de meses de enquadramento) +
        #   (nota no Perfil IV x nº de meses de enquadramento) / (dividido por) 24 = ],
        # por meio da qual obter-se-á a média ponderada das notas obtidas em cada um dos perfis,
        # considerando o período (em meses) de enquadramento

        # selecionando as avaliações finalizadas
        total_pontuacao = 0
        total_meses = 0
        intersticio = self.INTERSTICIO_AVALIATIVO_MESES
        for a in self.avaliacao_set.filter(situacao__in=[Avaliacao.CONCLUIDA, Avaliacao.AGUARDANDO_CIENCIA_RESULTADO, Avaliacao.REAVALIACAO]):
            total_pontuacao_avaliacao = a.pontuacao_final or Decimal('0')
            total_pontuacao += total_pontuacao_avaliacao * Decimal(a.total_meses_avaliacao(mostrar_dias=False))
            total_meses += a.total_meses_avaliacao(mostrar_dias=False)
        # se o interstício for menor que o configurado e NÃO for um progressão complementar
        if total_meses < intersticio and not self.progressao_complementar:
            total_meses = intersticio
        #
        nota_final = total_pontuacao / Decimal(total_meses)
        #
        self.pontuacao_final_progressao = round(nota_final, 2)
        self.save()

    #
    # Definindo permissões
    def pode_iniciar_avaliacao(self):
        # TODO checar usuário
        lista_dias = self._lista_dias_nao_cobertos()
        # só é permitido iniciar a avaliação quando todos os dias estiverem cobertos por avaliação e a situação do processo for "A_INICIAR"
        return not (lista_dias or self.situacao != self.A_INICIAR)

    #
    # é permitido adicionar uma avaliação por qualquer servidor do rh, desde que o processo de progressão não esteja finalizado
    def pode_adicionar_avaliacao(self, request):
        usuario = request.user
        return bool((usuario.has_perm('rh.eh_rh_sistemico') or usuario.has_perm('rh.eh_rh_campus')) and self.situacao != self.FINALIZADO)

    #
    def pode_finalizar_processo(self, request):
        usuario = request.user
        # se existir dias descobertos, não permitir finalizar o processo
        dias_descobertos = self._lista_dias_nao_cobertos()
        if dias_descobertos:
            return False
        #
        if self.situacao != self.CIENTE_RESULTADO:
            return False
        #
        if usuario.has_perm('rh.eh_rh_sistemico') or usuario.has_perm('rh.eh_rh_campus'):
            # verificando se todas as avaliações estão concluidas
            return all(a.situacao == Avaliacao.CONCLUIDA for a in self.avaliacao_set.all())
        #
        return False

    def situacao_derivada_das_avaliacoes(self):
        """Situação que o processo deve ter, espelhando a avaliação **mais atrasada**.

        É na etapa mais atrasada que está a ação pendente, então é ela que o processo
        precisa anunciar — para o avaliado e para o avaliador. Antes, `Avaliacao.save()`
        encadeava `if`s em que o último vencia e não havia ramo para
        AGUARDANDO_PREENCHIMENTO: um processo com uma avaliação concluída e outra
        aguardando preenchimento não casava com nenhuma condição e mantinha a situação
        antiga, exibindo ao avaliador uma ciência que já fora dada.

        Returns:
            A situação derivada, ou ``None`` quando não se aplica: processo A_INICIAR
            (as avaliações já existem, mas a CPPD ainda não liberou o processo — ver
            `pode_iniciar`), processo FINALIZADO (terminal) ou processo sem avaliações.
        """
        if self.situacao in (ProgressaoDocente.A_INICIAR, ProgressaoDocente.FINALIZADO):
            return None
        situacoes = set(self.avaliacao_set.values_list('situacao', flat=True))
        if not situacoes:
            return None
        for etapa in ETAPAS_AVALIACAO_DA_MAIS_ATRASADA:
            if etapa in situacoes:
                return SITUACAO_PROCESSO_POR_ETAPA_DA_AVALIACAO[etapa]
        return None

    def pode_reabrir_edicao(self, request):
        usuario = request.user
        return usuario.has_perm('rh.eh_rh_sistemico') and self.situacao in [ProgressaoDocente.CIENTE_RESULTADO, ProgressaoDocente.FINALIZADO]

    #
    def pode_gerar_processo_eletronico(self, request):
        usuario = request.user
        return (usuario.has_perm('rh.eh_rh_sistemico') or usuario.has_perm('rh.eh_rh_campus')) and self.situacao == self.FINALIZADO

    def pode_notificar_responsaveis(self, request):
        usuario = request.user
        return (usuario.has_perm('rh.eh_rh_sistemico') or usuario.has_perm('rh.eh_rh_campus')) and self.situacao != self.FINALIZADO

    #
    # identificando discentes aptos a realizar a avaliação no processo de progressão
    def popular_discentes_aptos(self, avaliacao):
        if 'edu' in settings.INSTALLED_APPS:
            #
            ProfessorDiario = apps.get_model('edu', 'ProfessorDiario')
            MatriculaDiario = apps.get_model('edu', 'MatriculaDiario')
            #
            vinculo = self.avaliado.get_vinculo()
            dt_inicio_intersticio = self.data_inicio_periodo
            dt_fim_intersticio = self.data_fim_periodo
            #
            alunos = []
            situacoes_alunos = [
                MatriculaDiario.SITUACAO_CURSANDO,
                MatriculaDiario.SITUACAO_APROVADO,
                MatriculaDiario.SITUACAO_REPROVADO,
                MatriculaDiario.SITUACAO_PROVA_FINAL,
                MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
                MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO,
                MatriculaDiario.SITUACAO_PENDENTE,
                MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO,
            ]
            qs_prof = ProfessorDiario.objects.filter(professor__vinculo=vinculo).filter(
                Q(data_fim_etapa_final__gte=dt_inicio_intersticio, data_inicio_etapa_1__lt=dt_inicio_intersticio)
                | Q(data_inicio_etapa_1__lte=dt_fim_intersticio, data_fim_etapa_final__gt=dt_fim_intersticio)
                | Q(data_inicio_etapa_1__gte=dt_inicio_intersticio, data_fim_etapa_final__lte=dt_fim_intersticio)
            )
            for p in qs_prof:
                for d in MatriculaDiario.objects.filter(diario=p.diario, situacao__in=situacoes_alunos):
                    dict_aluno = {'matricula': d.matricula_periodo.aluno.matricula, 'nome': d.matricula_periodo.aluno.pessoa_fisica.nome}
                    if dict_aluno not in alunos:
                        alunos.append(dict_aluno)
            # lista_ordenada = sorted(alunos, key=lambda x: x['nome'])
            for a in alunos:
                # se o obj for criado, atualizamos a avaliação
                # isso garante que o discente terá apenas uma avaliação para fazer por processo de progressão
                # TODO verificar a possibilidade de criação de um módulo à parte
                obj, created = DiscenteAptosAvaliacao.objects.get_or_create(
                    nome=a.get('nome'), matricula=a.get('matricula'), progressao=self, avaliacao=avaliacao
                )
                if created:
                    obj.avaliacao = avaliacao
                    obj.save()

    #
    # calculando a data final da progressão docente
    # padrão: 2 anos + dias de afastamentos encontrados no interstício

    def calcular_data_fim(self):
        if not self.data_fim_periodo:
            data_fim = self.data_inicio_periodo + relativedelta(months=self.INTERSTICIO_AVALIATIVO_MESES, days=-1)
            self.data_fim_periodo = data_fim

        # consulta ids de afastamentos utilizados
        ids_ignorar = []
        if self.ids_afastamentos_utilizados:
            ids_ignorar = list(self.ids_afastamentos_utilizados.split(','))
        #
        total_dias = 0
        #
        # dias de afastamentos que interrompem tempo de serviço
        dados = self.avaliado.dados_afastamentos_interrompem_tempo_servico(self.data_inicio_periodo, self.data_fim_periodo, ids_ignorar)
        if dados:
            total_dias += dados.get('total_dias', 0)
            for id in dados.get('afastamentos_ids'):
                self._adicionar_afastamento(id)
        #
        # dias de afastamentos que extrapolam 30 dias em um ano
        dados2 = self.avaliado.dados_afastamentos_efetivo_exercicio_30_dias(self.data_inicio_periodo, self.data_fim_periodo, ids_ignorar)
        if dados2:
            qtd_obs = len(dados2.get('observacoes'))
            if qtd_obs > 0:  # se não tiver observações, não tem afastamentos a serem computados
                total_dias += qtd_obs
                for id in dados2.get('afastamentos_ids'):
                    self._adicionar_afastamento(id)
        #
        # regra dos 24 meses - licença para tratamento de saúde
        dados_afast = self.avaliado.dados_afastamentos_efetivo_exercicio_24_meses(
            contar_a_partir_de=self.data_inicio_periodo, ids_ignorar=ids_ignorar
        )
        if dados_afast and dados_afast.get('total_dias') > 0:
            for i in dados_afast:
                if hasattr(i, 'pk'):
                    self._adicionar_afastamento(i.pk)
            total_dias += dados_afast.get('total_dias') or 0
        #
        # adicionando os dias de afastamentos no fim do interstício
        self.data_fim_periodo = self.data_fim_periodo + timedelta(days=total_dias)
        #
        if total_dias > 0:
            self.calcular_data_fim()
        elif self.eh_primeira_promocao:
            # se for a primeira promoção
            self.data_fim_periodo = self.data_inicio_periodo + relativedelta(months=self.INTERSTICIO_PRIMEIRA_PROMOCAO_MESES, days=-1)

    def _aprovado(self):
        if not self.pontuacao_final_progressao:
            return False
        return self.pontuacao_final_progressao >= self.MINIMO_PONTUACAO_APROVACAO

    def progressao_aprovada_display(self):
        txt = '<span class="status status-warning">Em andamento</span>'
        if self.situacao in [self.FINALIZADO, self.CIENTE_RESULTADO] and self.pontuacao_final_progressao:
            txt = '<span class="status status-error">Não aprovado</span>'
            if self._aprovado():
                txt = '<span class="status status-success">Aprovado</span>'
        return mark_safe(txt)

    def _get_dados_novo_padrao(self):
        pos_vert_anterior = self.nivel_atual
        pos_vert_novo = self.proximo_nivel
        #
        _padrao_anterior_reenq = Servidor.calcula_novo_padrao(nivel_padrao=pos_vert_anterior, eh_docente=True)
        padrao_anterior_reenq = f'{_padrao_anterior_reenq}'
        #
        _padrao_novo_reenq = Servidor.calcula_novo_padrao(nivel_padrao=pos_vert_novo, eh_docente=True)
        padrao_novo_reenq = f'{_padrao_novo_reenq}'
        return padrao_anterior_reenq, padrao_novo_reenq


class DiscenteAptosAvaliacao(models.ModelPlus):
    progressao = models.ForeignKeyPlus('progressao_docente.ProgressaoDocente', verbose_name='Progressão', on_delete=models.CASCADE, null=True)
    avaliacao = models.ForeignKeyPlus('progressao_docente.Avaliacao', verbose_name='Avaliação', on_delete=models.CASCADE, null=True)
    nome = models.CharFieldPlus('Nome Discente', null=False)
    matricula = models.CharFieldPlus('Matrícula Discente', null=False)
    avaliacao_realizada = models.BooleanField('Avaliação Realizada?', default=False)
    nao_reconhece_docente = models.BooleanField('Não Reconhece Docente?', default=False)
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', auto_now=True)

    class Meta:
        verbose_name = 'Discente Apto para Avaliação'
        verbose_name_plural = 'Discentes Aptos para Avaliação'

    def __str__(self):
        return super().__str__()


##
# A avaliação deve conter o processo, o formulário, chefia e deve abranger um período do interstício em avaliação. Pode ou não ser o período todos.
class Avaliacao(models.ModelPlus):
    SEARCH_FIELDS = ['progressao__avaliado__pessoa_fisica__nome', 'formulario__nome']

    PONTUACAO_MAXIMA_POR_AVALIACAO = 180  # pontuação máxima que um formulário pode ter

    AGUARDANDO_PREENCHIMENTO = 1
    EM_AVALIACAO = 2
    REAVALIACAO = 3
    AGUARDANDO_CIENCIA_RESULTADO = 4
    CONCLUIDA = 5
    EDITACAO_PARA_REAVALIACAO = 6

    SITUACAO_CHOICES = (
        (AGUARDANDO_PREENCHIMENTO, 'Aguardando Preenchimento'),
        (EM_AVALIACAO, 'Em Avaliação'),
        (REAVALIACAO, 'Em Reavaliação'),
        (AGUARDANDO_CIENCIA_RESULTADO, 'Aguardando Ciência de Resultado'),
        (EDITACAO_PARA_REAVALIACAO, 'Em Edição para Reavaliação'),
        (CONCLUIDA, 'Concluída'),
    )
    # dias corridos
    TEMPO_PREENCHIMENTO = 30
    TEMPO_AVALIACAO = 10
    TEMPO_REAVALIACAO = 2
    #
    progressao = models.ForeignKeyPlus('progressao_docente.ProgressaoDocente', verbose_name='Progressão', on_delete=models.CASCADE, null=True)
    formulario = models.ForeignKeyPlus('progressao_docente.Formulario', verbose_name='Formulário', on_delete=models.CASCADE, null=True)
    periodo_inicio = models.DateFieldPlus('Data de Início do Período', null=True, blank=False)
    periodo_fim = models.DateFieldPlus('Data Fim do Período', null=True, blank=False)
    avaliadores = models.ManyToManyFieldPlus('rh.Servidor', verbose_name='Avaliadores')
    situacao = models.IntegerFieldPlus('Situação', choices=SITUACAO_CHOICES, default=AGUARDANDO_PREENCHIMENTO)
    #
    preenchida = models.BooleanField('Preenchida', default=False)  # indica que a avaliação foi totalmente preenchida pelo avaliado
    preenchimento_expirado = models.BooleanField(
        'Preenchimento expirado por prazo', default=False
    )  # indica que a avaliação foi tramitada automaticamente para avaliação por estouro do prazo de preenchimento
    data_liberacao_ciencia = models.DateTimeFieldPlus('Data de Liberação para Ciência de Resultado', null=True, blank=True)
    ciencia_expirada = models.BooleanField(
        'Ciência expirada por prazo', default=False
    )  # indica que a avaliação foi concluída automaticamente por estouro do prazo de ciência (ciência tácita)
    finalizada = models.BooleanField(
        'Finalizada', default=False
    )  # indica que a avaliação foi finalizada mas ainda está sujeita a recurso e reavaliação
    #
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', auto_now=True)
    data_liberacao_preenchimento = models.DateTimeFieldPlus('Data de Liberação para Preenchimento', null=True, blank=True)
    data_liberacao_avaliacao = models.DateTimeFieldPlus('Data de Liberação para Avaliação', null=True, blank=True)
    data_liberacao_edicao_reavaliacao = models.DateTimeFieldPlus('Data de Liberação para Edição para Reavaliação', null=True, blank=True)
    edicao_reavaliacao_expirada = models.BooleanField(
        'Edição para reavaliação expirada por prazo', default=False
    )  # indica que a avaliação foi concluída automaticamente por estouro do prazo de edição para reavaliação
    data_liberacao_reavaliacao = models.DateTimeFieldPlus('Data de Liberação para Reavaliação', null=True, blank=True)
    reavaliacao_expirada = models.BooleanField(
        'Reavaliação expirada por prazo', default=False
    )  # indica que a avaliação foi encaminhada automaticamente para ciência por estouro do prazo de reavaliação
    data_ultima_notificacao = models.DateTimeFieldPlus('Data da Última Notificação', null=True, blank=True)
    #
    pontuacao_final = models.DecimalFieldPlus(
        'Pontuação Final', null=True, blank=True, max_digits=12, decimal_places=2
    )  # pontuacao com limite, caso tenha ultrapassado
    pontuacao_final_sem_limite = models.DecimalFieldPlus(
        'Pontuação Final sem Limite', null=True, blank=True, max_digits=12, decimal_places=2
    )  # pontuacao total sem o limite (somatória geral)
    #
    assinatura_avaliador = models.TextField('Assinatura do Avaliador', blank=True, null=True, default='')
    string_assinatura_avaliador = models.TextField('String Assinatura do Avaliador', blank=True, null=True, default='')
    data_assinatura_avaliador = models.DateTimeFieldPlus('Data da Assinatura do Avaliador', null=True, blank=True)
    assinatura_avaliado_processo = models.TextField('Assinatura do Avaliado do Processo', blank=True, null=True, default='')
    string_assinatura_avaliado_processo = models.TextField('String Assinatura do Avaliado do Processo', blank=True, null=True, default='')
    data_assinatura_avaliado_processo = models.DateTimeFieldPlus('Data da Assinatura do Avaliado do Processo', null=True, blank=True)

    class Meta:
        verbose_name = 'Avaliação'
        verbose_name_plural = 'Avaliações'
        permissions = (('pode_avaliar_processo', 'Pode Avaliar Processo'),)

    def __str__(self):
        return self.formulario.nome

    def get_absolute_url(self):
        return f'/progressao_docente/avaliacao/{self.pk}/ver/'

    def get_avaliador(self):
        return self.avaliadores.first()

    def save(self, *args, **kwargs):
        eh_nova_avaliacao = self.pk is None
        super().save(*args, **kwargs)
        progressao = self.progressao
        #
        # verificando se o processo já está em andamento para, no cadastro de uma nova avaliação e se necessário, popular os discentes aptos para a avaliação
        if eh_nova_avaliacao and progressao.situacao not in [ProgressaoDocente.FINALIZADO, ProgressaoDocente.A_INICIAR]:
            eh_avaliacao_discente = False
            for criterio in self.formulario.criterio_set.all():
                if criterio.avaliacao_discente:
                    eh_avaliacao_discente = True
                    break
            if eh_avaliacao_discente:
                # selecionando os discentes aptos
                progressao.popular_discentes_aptos(avaliacao=self)  # popula discentes aptos a realizar a avaliação
        #
        # mantendo a situação do processo atualizada de acordo com as avaliações
        situacao_derivada = progressao.situacao_derivada_das_avaliacoes()
        if situacao_derivada is not None:
            progressao.situacao = situacao_derivada

        # salvando processo
        progressao.save()

    def _dias_restantes_da_etapa(self, situacao: int) -> int | None:
        """Dias até o fim do prazo da etapa informada (negativo = vencido); ``None`` sem data de liberação.

        Lê o prazo da configuração, não das constantes de classe: é o mesmo número que
        expira a etapa, e uma contagem exibida que divergisse da aplicada enganaria
        avaliado e avaliador. Conta em dias de calendário — a mesma convenção da coluna
        "Prazo" do admin, que antes divergia desta em um dia para a mesma etapa.
        """
        liberacao, dias = self._prazo_da_etapa(situacao)
        if not liberacao:
            return None
        return ((liberacao + timedelta(days=dias)).date() - date.today()).days

    @property
    def get_tempo_restante_preenchimento(self):
        return self._dias_restantes_da_etapa(Avaliacao.AGUARDANDO_PREENCHIMENTO)

    @property
    def get_tempo_restante_avaliacao(self):
        return self._dias_restantes_da_etapa(Avaliacao.EM_AVALIACAO)

    @property
    def get_tempo_restante_edicao_reavaliacao(self):
        return self._dias_restantes_da_etapa(Avaliacao.EDITACAO_PARA_REAVALIACAO)

    @property
    def get_tempo_restante_reavaliacao(self):
        return self._dias_restantes_da_etapa(Avaliacao.REAVALIACAO)

    def _prazo_da_etapa(self, situacao: int) -> tuple[datetime | None, int]:
        """Data de liberação e quantidade de dias da etapa informada.

        Cada etapa tem o seu par (data de liberação, prazo em dias); os prazos vêm da
        ConfiguracaoProgressaoDocente e são os mesmos que regem o trâmite automático.
        Etapas sem prazo (concluída) devolvem ``(None, 0)``.
        """
        self.progressao._load_configs()
        prazos = {
            Avaliacao.AGUARDANDO_PREENCHIMENTO: (self.data_liberacao_preenchimento, self.progressao.tempo_preenchimento),
            Avaliacao.EM_AVALIACAO: (self.data_liberacao_avaliacao, self.progressao.tempo_avaliacao),
            Avaliacao.EDITACAO_PARA_REAVALIACAO: (self.data_liberacao_edicao_reavaliacao, self.progressao.tempo_adicao_edicao),
            Avaliacao.REAVALIACAO: (self.data_liberacao_reavaliacao, self.progressao.tempo_reavaliacao),
            Avaliacao.AGUARDANDO_CIENCIA_RESULTADO: (self.data_liberacao_ciencia, self.progressao.tempo_ciencia),
        }
        return prazos.get(situacao, (None, 0))

    def data_limite_etapa_atual(self) -> datetime | None:
        """Retorna a data limite da etapa atual da avaliação, ou ``None``.

        Cobre as cinco etapas com prazo: preenchimento, avaliação, edição para
        reavaliação, reavaliação e ciência de resultado. Demais situações — e etapas
        ainda sem data de liberação — retornam ``None``.
        """
        liberacao, dias = self._prazo_da_etapa(self.situacao)
        if not liberacao:
            return None
        return liberacao + timedelta(days=dias)

    def dias_restantes_etapa_atual(self) -> int | None:
        """Dias até a data limite da etapa atual (negativo = vencido); ``None`` se não se aplica."""
        return self._dias_restantes_da_etapa(self.situacao)

    @property
    def get_periodo_txt(self):
        data_inicio = self.periodo_inicio.strftime('%d/%m/%Y')
        data_fim = self.periodo_fim.strftime('%d/%m/%Y')
        return f'{data_inicio} à {data_fim}'

    @property
    def tem_avaliacao_discente(self):
        return self.formulario.criterio_set.filter(avaliacao_discente=True).exists()

    @property
    def conteudo_a_ser_assinado_da_avaliacao(self):
        lista_string_conteudo = []

        if 'edu' in installed_apps:
            tipo_objeto = ContentType.objects.get_for_model(apps.get_model('edu.aluno'))
            qs = (
                self.avaliacaoitem_set.select_related('pontuacao', 'item', 'responsavel', 'responsavel_avaliacao')
                .exclude(responsavel__tipo_relacionamento=tipo_objeto)
                .order_by('pk')
            )
        else:
            qs = self.avaliacaoitem_set.select_related('pontuacao', 'item', 'responsavel', 'responsavel_avaliacao').order_by('pk')

        for i in qs.prefetch_related(*_prefetch_relacionamentos_servidor()):
            pontuacao = i.pontuacao_form
            if pontuacao is None:
                pontuacao = i.pontuacao.pontos if i.pontuacao else 'None'

            item_pk = i.item.pk if i.item else 'None'

            responsavel = 'None'
            if i.responsavel and i.responsavel.relacionamento:
                r = i.responsavel.relacionamento
                responsavel = f'{r.nome} ({r.matricula})'

            responsavel_avaliacao = 'None'
            if i.responsavel_avaliacao and i.responsavel_avaliacao.relacionamento:
                r = i.responsavel_avaliacao.relacionamento
                responsavel_avaliacao = f'{r.nome} ({r.matricula})'

            lista_string_conteudo.append(slugify(f'{item_pk} {pontuacao} {responsavel} {responsavel_avaliacao}'))

        return '|'.join(lista_string_conteudo)

    @property
    def chave_a_ser_utilizada_na_assinatura_da_avaliacao(self):
        chave = slugify(f'{self.pk} {self.progressao.pk} {self.progressao.avaliado}')
        return chave

    @property
    def conteudo_a_ser_assinado_da_ciencia_de_resultado(self):
        #
        # informações dos itens avaliados
        qs = None
        lista_string_conteudo = [f'pontuacao_final:{self.pontuacao_final}']
        base_qs = self.avaliacaoitem_set.select_related('pontuacao', 'item', 'responsavel', 'responsavel_avaliacao')
        if 'edu' in installed_apps:
            tipo_objeto = ContentType.objects.get_for_model(apps.get_model('edu.aluno'))
            qs = base_qs.exclude(responsavel__tipo_relacionamento=tipo_objeto).order_by('pk')
        else:
            qs = base_qs.order_by('pk')
        for i in qs.prefetch_related(*_prefetch_relacionamentos_servidor()):
            # pontuacao
            pontuacao = i.pontuacao_form
            if not pontuacao and pontuacao != 0:
                pontuacao = i.pontuacao.pontos
            # item pk
            item_pk = i.item.pk
            # responsavel
            responsavel = 'None'
            if i.responsavel and i.responsavel.relacionamento:
                servidor = i.responsavel.relacionamento
                responsavel = f'{servidor.pessoa_fisica.nome} ({servidor.matricula})'
            #
            responsavel_avaliacao = 'None'
            if i.responsavel_avaliacao and i.responsavel_avaliacao.relacionamento:
                servidor = i.responsavel_avaliacao.relacionamento
                responsavel_avaliacao = f'{servidor.pessoa_fisica.nome} ({servidor.matricula})'
            #
            lista_string_conteudo.append(slugify(f'{item_pk} {pontuacao} {responsavel} {responsavel_avaliacao}'))
        conteudo_completo = '|'.join(lista_string_conteudo)
        return conteudo_completo

    @property
    def chave_a_ser_utilizada_na_assinatura_da_ciencia_de_resultado(self):
        chave = slugify(f'{self.pk} {self.progressao.pk} {self.progressao.avaliado} {self.pontuacao_final}')
        return chave

    def assinatura_avaliador_fomatada(self):
        if self.assinatura_avaliador:
            return assinatura_utils.quebra_assinatura(self.assinatura_avaliador, num_caracteres_por_linha=10)

    def situacao_assinatura_avaliador_html(self):
        return self._situacao_assinaturas(
            self.conteudo_a_ser_assinado_da_avaliacao, self.assinatura_avaliador, self.string_assinatura_avaliador or ''
        )

    def _situacao_assinaturas(self, _conteudo, _assinatura, _snapshot=''):
        """HTML do rótulo de uma assinatura: Pendente, Válida, Inválida ou Não verificável.

        "Não verificável" cobre as assinaturas antigas, feitas antes de o snapshot do
        conteúdo assinado passar a ser gravado. Sem o snapshot não dá para distinguir uma
        mudança real de conteúdo de uma simples reordenação dos itens — e chamar isso de
        "Inválida" sugere adulteração onde há apenas ausência de dado histórico.

        Args:
            _conteudo: conteúdo atual, recalculado a partir do estado do banco.
            _assinatura: assinatura gravada.
            _snapshot: conteúdo que foi efetivamente assinado, quando registrado.
        Returns:
            O ``<span>`` com o rótulo e a classe de status correspondente.
        """
        assinatura_situacao = 'Pendente'
        assinatura_situacao_attrs = "class='status status-warning'"
        # o gate olha a assinatura recebida, não a do avaliador: o método é genérico e
        # também atende a assinatura da ciência.
        if _assinatura:
            check_assinatura = assinatura_utils.verifica_assinatura(_conteudo, _assinatura)
            if check_assinatura:
                assinatura_situacao = 'Válida'
                assinatura_situacao_attrs = "class='status status-success'"
            elif not _snapshot:
                assinatura_situacao = 'Não verificável'
                assinatura_situacao_attrs = "class='status status-alert'"
            else:
                assinatura_situacao = 'Inválida'
                assinatura_situacao_attrs = "class='status status-error'"
        #
        situacao_assinatura_html = f'<span {assinatura_situacao_attrs}>{assinatura_situacao}</span>'
        return situacao_assinatura_html

    def _mensagem_expiracao(self, dias: int, responsavel: str = 'o servidor') -> str:
        return f'O processo ficou disponível para {responsavel} por {dias} dia(s); não houve manifestação no prazo estipulado.'

    def manifestacao_ciencia_html(self) -> str:
        """HTML da manifestação do avaliado na ciência: assinatura, mensagem de expiração ou pendente.

        Vazio nas etapas anteriores à ciência (preenchimento/avaliação/reavaliação),
        onde a ciência ainda não foi solicitada.
        """
        if self.assinatura_avaliado_processo:
            data = self.data_assinatura_avaliado_processo.strftime('%d/%m/%Y') if self.data_assinatura_avaliado_processo else ''
            return mark_safe(f'<span class="status status-success">Ciente em {data}</span>')
        if self.ciencia_expirada:
            self.progressao._load_configs()
            return mark_safe(f'<span class="status status-warning">{self._mensagem_expiracao(self.progressao.tempo_ciencia)}</span>')
        if self.situacao != Avaliacao.AGUARDANDO_CIENCIA_RESULTADO:
            # concluída sem assinatura e sem expiração (ex.: conclusão manual) não está "pendente": vazio.
            return mark_safe('')
        return mark_safe('<span class="status status-warning">Pendente</span>')

    def manifestacao_preenchimento_html(self) -> str:
        """HTML da manifestação do preenchimento: mensagem de expiração, ou vazio quando não expirou."""
        if self.preenchimento_expirado:
            self.progressao._load_configs()
            return mark_safe(f'<span class="status status-warning">{self._mensagem_expiracao(self.progressao.tempo_preenchimento)}</span>')
        return mark_safe('')

    def manifestacao_edicao_reavaliacao_html(self) -> str:
        """HTML da manifestação do avaliado na edição para reavaliação: expiração ou pendente.

        Vazio fora da etapa, para não poluir o processo impresso das avaliações que
        nunca foram reabertas.
        """
        if self.edicao_reavaliacao_expirada:
            self.progressao._load_configs()
            return mark_safe(f'<span class="status status-warning">{self._mensagem_expiracao(self.progressao.tempo_adicao_edicao)}</span>')
        if self.situacao != Avaliacao.EDITACAO_PARA_REAVALIACAO:
            return mark_safe('')
        return mark_safe('<span class="status status-warning">Pendente</span>')

    def manifestacao_reavaliacao_html(self) -> str:
        """HTML da manifestação do avaliador na reavaliação: mensagem de expiração, ou vazio.

        Só aparece quando houve decurso de prazo — nos demais casos a reavaliação está
        registrada no próprio texto de conclusão do recurso.
        """
        if self.reavaliacao_expirada:
            self.progressao._load_configs()
            return mark_safe(
                f'<span class="status status-warning">{self._mensagem_expiracao(self.progressao.tempo_reavaliacao, "o avaliador")}</span>'
            )
        return mark_safe('')

    #
    # retorno a quantidade de dias da última notificaçãoa até hoje
    def dias_da_ultima_notificacao(self):
        hoje = datetime.now()
        if not self.data_ultima_notificacao:
            return 9999  # retornar um número alto de dias para forçar nova notificação
        delta = hoje - self.data_ultima_notificacao
        return delta.days

    #
    # verifica a periodicidade de notificação

    def check_notificacao(self):
        hoje = datetime.now()
        dias = None
        #
        # AGUARDANDO PREENCHIMENTO
        if self.situacao == self.AGUARDANDO_PREENCHIMENTO:
            if not self.data_liberacao_preenchimento:
                self.data_liberacao_preenchimento = hoje
                self.data_ultima_notificacao = hoje
                self.notificar(self.situacao, 'AGUARDANDO PREENCHIMENTO')
            dias = self.TEMPO_PREENCHIMENTO - (hoje - self.data_liberacao_preenchimento).days
        #
        # AGUARDANDO AVALIAÇÃO
        if self.situacao == self.EM_AVALIACAO:
            if not self.data_liberacao_avaliacao:
                self.data_liberacao_avaliacao = hoje
                self.data_ultima_notificacao = hoje
                self.notificar(self.situacao, 'AGUARDANDO AVALIAÇÃO')
            dias = self.TEMPO_AVALIACAO - (hoje - self.data_liberacao_avaliacao).days
        #
        # AUGARDANDO REAVALIAÇÃO
        if self.situacao == self.REAVALIACAO:
            self.data_ultima_notificacao = hoje
            self.notificar(self.situacao, 'AGUARDANDO REAVALIAÇÃO')
        #
        if dias:
            if dias <= 5:
                self.notificar(self.situacao, 'NOTIFICAR TODOS OS DIAS')
            if 10 >= dias > 5:
                if self.dias_da_ultima_notificacao() >= 2:
                    self.notificar(self.situacao, 'NOTIFICAR A CADA 2 DIAS')
            if 15 >= dias > 10:
                if self.dias_da_ultima_notificacao() >= 3:
                    self.notificar(self.situacao, 'NOTIFICAR A CADA 3 DIAS')

    #
    # sendmail notificação

    def notificar(self, situacao, texto):
        hoje = datetime.now()
        #
        if situacao in [self.AGUARDANDO_PREENCHIMENTO, self.EM_AVALIACAO, self.REAVALIACAO]:
            # TODO verificar funcionalidade
            self.data_ultima_notificacao = hoje
            self.save()

    #

    def usuario_eh_avaliador(self, user):
        try:
            return self.avaliadores.filter(matricula=user.get_relacionamento().matricula).exists()
        except Exception:
            return False

    #

    def usuario_eh_dono(self, user):
        if self.progressao:
            return self.progressao.avaliado == user.get_relacionamento()
        return False

    #

    def percentual_concluido(self, responsavel):
        #
        # necessário separa os tipos de critérios em "necessitam de arquivo" e os que não necessitam de arquivos
        qs_criterio_arquivo = self.formulario.criterio_set.filter(necessita_arquivos=True)
        qs_criterio = self.formulario.criterio_set.filter(necessita_arquivos=False)
        if self.situacao == Avaliacao.AGUARDANDO_PREENCHIMENTO:
            qs_criterio = qs_criterio.filter(autoavaliacao=True)
        else:
            qs_criterio = qs_criterio.filter(autoavaliacao=False)
        #
        # nos critérios que não necessitam de arquivos, vamos verificar a quantidade de itens
        qtd = 0
        qtd_total = 0
        for c1 in qs_criterio:
            qtd_total += c1.item_set.count()
            qtd += (
                c1.get_itens(avaliacao=self, responsavel=responsavel).exclude(Q(pontuacao_form__isnull=True) | Q(pontuacao_form=Decimal(0))).count()
            )  # excluíndo arquivos
        #
        # para os critérios que exigem arquivos, iremos contabilizar apenas se existir pelo menos um arquivo cadastrado com a pontuação definida
        for c2 in qs_criterio_arquivo:
            tem_avaliacao = AvaliacaoItem.objects.filter(avaliacao=self, item__criterio=c2, responsavel=responsavel).exists()
            if tem_avaliacao:
                qtd_total += 1
                qtd += 1
        #
        return {'qtd': qtd, 'qtd_total': qtd_total}

    #

    def percentual_avaliado(self, responsavel):
        #
        # IMPORTANTE: aqui não devemos considerar os itens de avaliação das AUTOAVALIAÇÕES
        formulario = self.formulario
        # Usar prefetch_related para carregar critérios e itens de uma vez
        criterios = formulario.criterio_set.prefetch_related('item_set')
        #
        # necessário separa os tipos de critérios em "necessitam de arquivo" e os que não necessitam de arquivos
        qs_criterio_arquivo = criterios.filter(necessita_arquivos=True, autoavaliacao=False)
        qs_criterio = criterios.filter(necessita_arquivos=False, autoavaliacao=False)
        if responsavel.eh_aluno():
            qs_criterio = criterios.filter(necessita_arquivos=False, avaliacao_discente=False)
        #
        # nos critérios que não necessitam de arquivos, vamos verificar a quantidade de itens
        ids_itens = []
        for c1 in qs_criterio:
            for item in c1.item_set.all():
                ids_itens.append(item.pk)
        #
        if not responsavel.eh_aluno():
            #
            # aqui devemos contar todos os arquivos de todos os critérios, que foram preenchidos, que estão cadastrados para o "AVALIADO"
            avaliado_processo = self.progressao.avaliado.get_vinculo()
            for c2 in qs_criterio_arquivo:  # Atenção: sempre que for arquivos, o responsável SEMPRE será o avaliado do processo!
                qs_avaliacao_item_nao_avaliado = AvaliacaoItem.objects.filter(avaliacao=self, item__criterio=c2, responsavel=avaliado_processo)
                for item in qs_avaliacao_item_nao_avaliado:
                    ids_itens.append(item.item.pk)
        #
        # total de itens
        qtd_itens_total = len(ids_itens)
        #
        # total de itens avaliados
        responsavel_query = Q(responsavel_avaliacao=responsavel) | Q(responsavel=responsavel)
        qtd_itens_avaliados = (
            AvaliacaoItem.objects.filter(avaliacao=self, item__id__in=ids_itens, deferimento__isnull=False).filter(responsavel_query).count()
        )
        #
        return {'qtd': qtd_itens_avaliados, 'qtd_total': qtd_itens_total}

    def pode_revalidar_assinatura(self, request):
        assinatura_valida = assinatura_utils.verifica_assinatura(self.conteudo_a_ser_assinado_da_avaliacao, self.assinatura_avaliador)
        return bool(request.user.is_superuser and not assinatura_valida)

    def revalidar_assinatura(self, request):
        if self.pode_revalidar_assinatura(request):
            self.assinatura_avaliador = assinatura_utils.gera_assinatura(
                self.conteudo_a_ser_assinado_da_avaliacao, self.chave_a_ser_utilizada_na_assinatura_da_avaliacao
            )
            self.string_assinatura_avaliador = self.conteudo_a_ser_assinado_da_avaliacao
            self.save()

    def revalidar_assinaturas_se_apenas_ordenacao(self, dry_run: bool = False) -> dict:
        """Revalida as assinaturas desta avaliação quando a divergência é só de ordenação.

        Para o avaliador e para a ciência, compara o snapshot do que foi assinado com o
        conteúdo atual (já ordenado por pk). Se os segmentos forem os mesmos (só a ordem
        mudou) e a assinatura estiver inválida, regenera-a sobre o conteúdo atual.
        Divergências reais (itens/pontuações alterados) NÃO são revalidadas.
        Retorna {'avaliador': <estado>, 'ciencia': <estado>} com estados
        'revalidada' | 'divergencia' | 'ja_valida' | 'sem_assinatura'.
        """
        # conteúdo/chave passados como callables: só são computados (queries caras) quando
        # há assinatura para o campo, e a chave apenas quando há de fato regeneração.
        campos = (
            (
                'avaliador',
                'assinatura_avaliador',
                'string_assinatura_avaliador',
                lambda: self.conteudo_a_ser_assinado_da_avaliacao,
                lambda: self.chave_a_ser_utilizada_na_assinatura_da_avaliacao,
            ),
            (
                'ciencia',
                'assinatura_avaliado_processo',
                'string_assinatura_avaliado_processo',
                lambda: self.conteudo_a_ser_assinado_da_ciencia_de_resultado,
                lambda: self.chave_a_ser_utilizada_na_assinatura_da_ciencia_de_resultado,
            ),
        )
        resultado = {}
        atualizar = {}
        for rotulo, assinatura_attr, snapshot_attr, get_conteudo, get_chave in campos:
            estado = self._revalidar_campo_assinatura(assinatura_attr, snapshot_attr, get_conteudo, get_chave, dry_run)
            resultado[rotulo] = estado
            if estado == 'revalidada' and not dry_run:
                atualizar[assinatura_attr] = getattr(self, assinatura_attr)
                atualizar[snapshot_attr] = getattr(self, snapshot_attr)
        if atualizar:
            # persistência cirúrgica: NÃO usar self.save(), que recalcula/sobrescreve progressao.situacao
            type(self).objects.filter(pk=self.pk).update(**atualizar)
            # o update() não passa por self; ressincroniza a instância para não ficar em estado misto
            self.refresh_from_db()
        return resultado

    def _revalidar_campo_assinatura(
        self, assinatura_attr: str, snapshot_attr: str, get_conteudo: Callable[[], str], get_chave: Callable[[], str], dry_run: bool
    ) -> str:
        assinatura = getattr(self, assinatura_attr) or ''
        if not assinatura:
            return 'sem_assinatura'
        conteudo_atual = get_conteudo()
        if assinatura_utils.verifica_assinatura(conteudo_atual, assinatura):
            return 'ja_valida'
        snapshot = getattr(self, snapshot_attr) or ''
        if sorted(snapshot.split('|')) != sorted(conteudo_atual.split('|')):
            return 'divergencia'
        if not dry_run:
            setattr(self, assinatura_attr, assinatura_utils.gera_assinatura(conteudo_atual, get_chave()))
            setattr(self, snapshot_attr, conteudo_atual)
        return 'revalidada'

    def pode_recalcular_pontuacao(self, request):
        usuario = request.user
        return bool(usuario.has_perm('rh.eh_rh_sistemico') or usuario.has_perm('rh.eh_rh_campus'))

    """
    REGRAS PARA EDITAR AVALIAÇÃO:
        - apenas usuários do rh sistêmico pode editar E
        - se o processo estiver com situção "a iniciar" OU
        - se a avaliação estiver com a situação "aguardando preenchimento" OU
        - se a avaliação estiver com a situação "em avaliação" E não existir nenhuma avaliação realizada
    """

    def pode_editar_avaliacao(self, request):
        usuario = request.user
        if usuario.has_perm('rh.eh_rh_sistemico') or usuario.has_perm('rh.eh_rh_campus'):
            if self.situacao == Avaliacao.AGUARDANDO_PREENCHIMENTO:
                return True
            if self.situacao == Avaliacao.EM_AVALIACAO:
                # existem avaliacoes realizadas?
                avaliador = self.avaliadores.first().get_vinculo()
                qtd_avaliado = self.percentual_avaliado(avaliador).get('qtd')
                if qtd_avaliado == 0:
                    return True
            #
            # se a avaliação estiver concluída, ainda assim é possível alterar a data fim do período avaliativo
            if self.progressao and self.progressao.situacao == ProgressaoDocente.CIENTE_RESULTADO and self.situacao == Avaliacao.CONCLUIDA:
                return True
        #
        return False

    #
    def pode_remover_avaliacao(self, request):
        usuario = request.user
        return bool(
            usuario.has_perm('rh.eh_rh_sistemico')
            and self.situacao == Avaliacao.AGUARDANDO_PREENCHIMENTO
            and self.progressao.situacao == ProgressaoDocente.A_INICIAR
        )

    # checa se a avaliação pode receber alterações por avaliadores
    def pode_ser_avaliada(self):
        return self.situacao in [
            Avaliacao.REAVALIACAO,
            Avaliacao.EM_AVALIACAO,
            Avaliacao.AGUARDANDO_PREENCHIMENTO,
            Avaliacao.EDITACAO_PARA_REAVALIACAO,
        ]

    def pode_concluir_preenchimento(self, request):
        if not self.usuario_eh_dono(request.user):
            return False
        #
        # recuperando todos os itens de autoavaliação e verificando se todos tem notas
        qs_criterio = self.formulario.criterio_set.filter(necessita_arquivos=False, autoavaliacao=True)
        ids_itens = []
        for c1 in qs_criterio:
            for item in c1.item_set.all():
                ids_itens.append(item.pk)
        #
        # total de itens
        qtd_itens_total = len(ids_itens)
        #
        # total de itens avaliados
        _qs = AvaliacaoItem.objects.filter(avaliacao=self, item__id__in=ids_itens, deferimento__isnull=False, responsavel=request.user.get_vinculo())
        qtd_itens_avaliados = _qs.count()
        #
        # selecionando todos os critérios que necessitam de arquivos
        # qs_criterio_arquivo = self.formulario.criterio_set.filter(necessita_arquivos=True)
        tem_arquivos = True  # TODO se necessário liberar a verificação de critérios que necessitam de arquivos, mas, a princípio, não será obrigatório o preenchimento
        # for c2 in qs_criterio_arquivo:
        #     if not AvaliacaoItem.objects.filter(avaliacao=self, item__criterio=c2).exists():
        #         tem_arquivos = False
        #         break
        #
        return qtd_itens_total == qtd_itens_avaliados and tem_arquivos

    #
    # pontuação total validada de todos os critérios da avaliação

    def total_pontuacao_avaliacao(self, avaliador, avaliado_processo):
        pontuacao = 0
        #
        # verificando quais são os critérios dessa avaliação

        for criterio in self.formulario.criterio_set.all():
            d = None
            #
            if criterio.avaliacao_discente or criterio.autoavaliacao:
                # # verificando a nota da avaliação discente
                discentes_aptos = DiscenteAptosAvaliacao.objects.filter(avaliacao=self, avaliacao_realizada=True).values('matricula')
                Aluno = apps.get_model('edu', 'Aluno')
                qtd_avaliacoes_positivas = 0
                qtd_avaliacoes_negativas = 0
                for a in discentes_aptos:
                    aluno = Aluno.objects.get(matricula=a.get('matricula'))
                    _resultado = self.resultado_consideracao_positiva(avaliador=aluno.get_vinculo())
                    resultado = _resultado.get(criterio.nome)
                    if resultado:
                        if resultado.get('positiva'):
                            qtd_avaliacoes_positivas += 1
                        else:
                            qtd_avaliacoes_negativas += 1
                # # por padrão a pontuação "p" vai zerada
                d = {'p': 0.0, 'nota_discente': 0.0, 'qtd_positivas': qtd_avaliacoes_positivas, 'qtd_negativas': qtd_avaliacoes_negativas}
                # verificando se a quantidade de avaliações positivas está acima do mínimo considerado
                minimo = (qtd_avaliacoes_positivas + qtd_avaliacoes_negativas) / 2
                if qtd_avaliacoes_positivas > minimo:
                    d.update(
                        {
                            'p': 5.0,
                            'nota_discente': 5.0,
                        }
                    )

                # verificando a nota da autoavaliação
                dict_avaliadores = self.get_avaliadores(apenas_avaliado=True)
                avaliadores = dict_avaliadores.get(criterio.nome) or {}
                d.update(
                    {
                        'nota_avaliado': 0.0,
                    }
                )
                if avaliadores.get('avaliadores'):
                    _avaliador = avaliadores.get('avaliadores')[0]
                    # se a avaliação do avaliador for considerada positiva
                    if _avaliador.get('avaliacao_positiva'):
                        pontuacao_adicional = 5.0
                        d.update(
                            {
                                'p': d.get('p') + pontuacao_adicional,
                                'nota_avaliado': pontuacao_adicional,
                            }
                        )
            else:
                if criterio.necessita_arquivos:
                    d = criterio.get_pontuacao_total_avaliado(avaliacao=self, responsavel=avaliado_processo)
                else:
                    if type(avaliador) is dict:
                        avaliador = avaliador.get('avaliador')
                    d = criterio.get_pontuacao_total_avaliado(avaliacao=self, responsavel_avaliacao=avaliador)
            p = float(d.get('p'))
            if p is not None:
                pontuacao += p
        return pontuacao

    def _diferenca_em_meses_e_dias(self, data_inicio, data_fim, adicionar_ultimo_dia=False):
        inicio = data_inicio
        fim = data_fim
        anos = fim.year - inicio.year
        meses = fim.month - inicio.month
        total_meses = anos * 12 + meses

        if fim.day < inicio.day:
            total_meses -= 1
            ultimo_dia_mes_anterior = (fim.replace(day=1) - timedelta(days=1)).day
            dias = fim.day + (ultimo_dia_mes_anterior - inicio.day)
        else:
            dias = fim.day - inicio.day

        if adicionar_ultimo_dia:
            dias += 1

        # Se os dias acumularem um mês completo, incrementar os meses e ajustar os dias
        if dias >= (fim.replace(day=1) - timedelta(days=1)).day:
            dias = 0
            total_meses += 1

        return total_meses, dias

    def _calcular_diferenca_em_dias(self, data_inicio, data_fim):
        # Calcula a diferença em dias
        diferenca = (data_fim - data_inicio).days

        # Se as datas forem diferentes, adiciona 1 dia para incluir o dia final
        if diferenca != 0:
            diferenca += 1

        # Retorna o número de dias
        return diferenca

    def _meses_e_dias_para_decimal(self, meses, dias):
        # Duração média de um mês em dias
        dias_por_mes = 30.44
        # Converte os dias em fração de um mês
        meses_decimais = meses + (dias / dias_por_mes)
        # Retorna o valor decimal
        return meses_decimais

    #
    # calculando quantidade de meses da avaliação/formulário
    def total_meses_avaliacao(self, mostrar_dias=True):
        if self.periodo_inicio and self.periodo_fim:
            inicio = self.periodo_inicio
            fim = self.periodo_fim
            # Retorna o total em meses e dias
            meses_dias = self._diferenca_em_meses_e_dias(inicio, fim, adicionar_ultimo_dia=True)
            if mostrar_dias:
                return meses_dias
            return self._meses_e_dias_para_decimal(*meses_dias)
        else:
            return 0

    def concluir_preenchimento_avaliacao(self, request):
        if self.pode_concluir_preenchimento(request):
            if self.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO:
                self.situacao = Avaliacao.REAVALIACAO
                # o relógio que passa a valer é o da reavaliação; carimbar apenas
                # data_liberacao_avaliacao deixava o prazo preso à data do recurso original.
                self.data_liberacao_reavaliacao = datetime.now()
            else:
                self.situacao = Avaliacao.EM_AVALIACAO
                self.data_liberacao_avaliacao = datetime.now()
            self.preenchida = True
            self.save()
            self._atualizar_situacao_progressao(self)

    def _prazo_etapa_vencido(self, situacao: int) -> bool:
        """Indica se o prazo da etapa informada venceu — e se a avaliação ainda está nela.

        A checagem da situação é o que torna as expirações idempotentes: uma avaliação
        já tramitada não está mais na etapa e, portanto, não tem prazo a vencer.
        """
        if self.situacao != situacao:
            return False
        limite = self.data_limite_etapa_atual()
        if not limite:
            return False
        return datetime.now() > limite

    def prazo_preenchimento_vencido(self) -> bool:
        """Indica se o prazo de preenchimento desta avaliação já venceu.

        O prazo é ``data_liberacao_preenchimento + tempo_preenchimento`` (dias),
        onde ``tempo_preenchimento`` vem da ConfiguracaoProgressaoDocente (padrão 30).
        """
        return self._prazo_etapa_vencido(Avaliacao.AGUARDANDO_PREENCHIMENTO)

    def prazo_edicao_reavaliacao_vencido(self) -> bool:
        """Indica se o prazo de edição para reavaliação desta avaliação já venceu.

        O prazo é ``data_liberacao_edicao_reavaliacao + tempo_adicao_edicao`` (dias),
        onde ``tempo_adicao_edicao`` vem da ConfiguracaoProgressaoDocente (padrão 2).
        """
        return self._prazo_etapa_vencido(Avaliacao.EDITACAO_PARA_REAVALIACAO)

    def prazo_reavaliacao_vencido(self) -> bool:
        """Indica se o prazo de reavaliação desta avaliação já venceu.

        O prazo é ``data_liberacao_reavaliacao + tempo_reavaliacao`` (dias), onde
        ``tempo_reavaliacao`` vem da ConfiguracaoProgressaoDocente (padrão 2).
        """
        return self._prazo_etapa_vencido(Avaliacao.REAVALIACAO)

    def prazo_ciencia_vencido(self) -> bool:
        """Indica se o prazo de ciência do resultado desta avaliação já venceu.

        O prazo é ``data_liberacao_ciencia + tempo_ciencia`` (dias), onde
        ``tempo_ciencia`` vem da ConfiguracaoProgressaoDocente (padrão 2).
        """
        return self._prazo_etapa_vencido(Avaliacao.AGUARDANDO_CIENCIA_RESULTADO)

    def expirar_preenchimento(self) -> bool:
        """Tramita a avaliação para EM_AVALIACAO ao vencer o prazo de preenchimento.

        Mesmo sem preenchimento do avaliado, encaminha para a etapa de avaliação
        (chefia imediata / avaliadores). Idempotente: só age se o prazo venceu e
        a avaliação ainda está em AGUARDANDO_PREENCHIMENTO. Retorna ``True`` se
        tramitou.
        """
        if not self.prazo_preenchimento_vencido():
            return False
        with transaction.atomic():
            self.situacao = Avaliacao.EM_AVALIACAO
            self.preenchida = False
            self.preenchimento_expirado = True
            self.data_liberacao_avaliacao = datetime.now()
            self.save()
            self._atualizar_situacao_progressao(self)
        # notificação best-effort: falha de e-mail não reverte a tramitação nem aborta o lote.
        try:
            self._notificar_expiracao_preenchimento()
        except Exception:
            logger.exception('Falha ao notificar expiração do preenchimento da avaliação %s', self.pk)
        return True

    def _notificar_expiracao_preenchimento(self) -> None:
        """Notifica o avaliado e o(s) avaliador(es) sobre a tramitação automática."""
        self._notificar_expiracao(
            '[SUAP] Progressão Docente - Prazo de preenchimento expirado',
            'O prazo de preenchimento da avaliação de progressão docente expirou. '
            'A avaliação foi encaminhada automaticamente para a etapa de avaliação (chefia imediata).',
        )

    def expirar_ciencia(self) -> bool:
        """Conclui a avaliação ao vencer o prazo de ciência do resultado (ciência tácita).

        Mesmo sem ciência do avaliado, conclui a avaliação. Idempotente: só age se
        o prazo venceu e a avaliação ainda está em AGUARDANDO_CIENCIA_RESULTADO.
        Retorna ``True`` se tramitou.
        """
        if not self.prazo_ciencia_vencido():
            return False
        with transaction.atomic():
            self.situacao = Avaliacao.CONCLUIDA
            self.ciencia_expirada = True
            self.finalizada = True
            # a transição do processo (CONCLUIDA -> CIENTE_RESULTADO) é resolvida no próprio save();
            # não chamamos _atualizar_situacao_progressao aqui pois ele não trata a etapa de ciência.
            self.save()
        # notificação best-effort: enviada fora da transação e com a falha contida, para não reverter a
        # conclusão nem abortar o processamento em lote das demais avaliações se o e-mail falhar.
        try:
            self._notificar_expiracao_ciencia()
        except Exception:
            logger.exception('Falha ao notificar expiração da ciência da avaliação %s', self.pk)
        return True

    def _notificar_expiracao_ciencia(self) -> None:
        """Notifica o avaliado e o(s) avaliador(es) sobre a conclusão automática por estouro do prazo de ciência."""
        self._notificar_expiracao(
            '[SUAP] Progressão Docente - Prazo de ciência expirado',
            'O prazo para ciência do resultado da avaliação de progressão docente expirou. '
            'A avaliação foi concluída automaticamente por decurso de prazo.',
        )

    def _notificar_expiracao(self, assunto: str, texto: str) -> None:
        """Envia o aviso de tramitação automática ao avaliado e ao(s) avaliador(es)."""
        destinatarios = []
        if self.progressao.avaliado:
            destinatarios.append(self.progressao.avaliado.get_vinculo())
        destinatarios.extend(avaliador.get_vinculo() for avaliador in self.avaliadores.all())
        if not destinatarios:
            return
        self.progressao.enviar_email(assunto, texto, avaliacao=self, destinatario=destinatarios)

    def reabrir_para_edicao_reavaliacao(self) -> None:
        """Devolve a avaliação ao avaliado para editar/adicionar informações e, com isso,
        abre o relógio da etapa: sem ``data_liberacao_edicao_reavaliacao`` o processo
        ficava parado indefinidamente à espera de uma manifestação que podia não vir
        (chamado 10625).
        """
        self.situacao = Avaliacao.EDITACAO_PARA_REAVALIACAO
        self.data_liberacao_edicao_reavaliacao = datetime.now()
        self.save()

    def expirar_edicao_reavaliacao(self) -> bool:
        """Conclui a avaliação ao vencer o prazo de edição para reavaliação.

        Sem manifestação do avaliado não há o que reavaliar: a avaliação volta ao estado
        em que estava antes da reabertura, com o resultado que já vigorava.

        A etapa tem dois pontos de entrada, com estados anteriores diferentes:

        - `reabrir_edicao` (RH sistêmico), a partir de processo em CIENTE_RESULTADO ou
          FINALIZADO — a ciência já foi dada (ou já expirou);
        - `preparar_edicao_reavaliacao` (o próprio avaliado), a partir de
          AGUARDANDO_CIENCIA_RESULTADO — o avaliado abriu mão da ciência ao pedir a edição.

        Nos dois casos o destino é CONCLUIDA, e não uma nova janela de ciência: o
        resultado é o mesmo que o avaliado já conhecia quando a etapa foi aberta, e
        reabrir a ciência apenas alongaria o processo sem nada novo a dar ciência.
        Decisão do demandante do chamado 10625.

        Idempotente: só age se o prazo venceu e a avaliação ainda está em
        EDITACAO_PARA_REAVALIACAO. Retorna ``True`` se tramitou.
        """
        if not self.prazo_edicao_reavaliacao_vencido():
            return False
        with transaction.atomic():
            self.situacao = Avaliacao.CONCLUIDA
            self.edicao_reavaliacao_expirada = True
            self.finalizada = True
            # a situação do processo sai da derivação no próprio save() (CONCLUIDA -> CIENTE_RESULTADO)
            self.save()
        # notificação best-effort: falha de e-mail não reverte a conclusão nem aborta o lote.
        try:
            self._notificar_expiracao_edicao_reavaliacao()
        except Exception:
            logger.exception('Falha ao notificar expiração da edição para reavaliação da avaliação %s', self.pk)
        return True

    def _notificar_expiracao_edicao_reavaliacao(self) -> None:
        """Notifica o avaliado e o(s) avaliador(es) sobre a conclusão automática por estouro do prazo de edição."""
        self._notificar_expiracao(
            '[SUAP] Progressão Docente - Prazo de edição para reavaliação expirado',
            'O prazo para edição/adição de informações para reavaliação da sua progressão docente expirou. '
            'Sem manifestação, a avaliação foi concluída automaticamente por decurso de prazo, '
            'mantido o resultado anterior.',
        )

    def expirar_reavaliacao(self) -> bool:
        """Encaminha a avaliação para ciência ao vencer o prazo de reavaliação.

        Sem manifestação do avaliador, o recurso é encerrado sem alteração e o resultado
        volta ao avaliado para ciência — o mesmo destino de `finalizar_reavaliacao`, e não
        a conclusão direta, porque o avaliado não pode perder a ciência do que foi decidido.
        Idempotente: só age se o prazo venceu e a avaliação ainda está em REAVALIACAO.
        Retorna ``True`` se tramitou.
        """
        if not self.prazo_reavaliacao_vencido():
            return False
        with transaction.atomic():
            self.recursoavaliacao_set.filter(situacao=RecursoAvaliacao.EM_REAVALIACAO).update(
                situacao=RecursoAvaliacao.FINALIZADO,
                texto_conclusao_reavaliacao='Reavaliação encerrada por decurso de prazo, sem manifestação do avaliador.',
                data_conclusao_reavaliacao=datetime.now(),
            )
            self.situacao = Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
            self.reavaliacao_expirada = True
            # o prazo de ciência recomeça aqui; herdar a data da ciência anterior faria a
            # etapa nascer vencida e o avaliado perderia a chance de se manifestar.
            self.data_liberacao_ciencia = datetime.now()
            self.save()
            # `reavaliar_avaliacao` zera a pontuação ao abrir o recurso; sem recalcular, o
            # avaliado receberia a ciência sem resultado. Exige avaliador (calcular_pontuacao_avaliacao).
            if self.avaliadores.exists():
                self.calcular_pontuacao_avaliacao()
            else:
                logger.warning('Avaliação %s sem avaliador: pontuação não recalculada ao expirar a reavaliação.', self.pk)
        # notificação best-effort: falha de e-mail não reverte a tramitação nem aborta o lote.
        try:
            self._notificar_expiracao_reavaliacao()
        except Exception:
            logger.exception('Falha ao notificar expiração da reavaliação da avaliação %s', self.pk)
        return True

    def _notificar_expiracao_reavaliacao(self) -> None:
        """Notifica o avaliado e o(s) avaliador(es) sobre o encaminhamento automático para ciência."""
        self._notificar_expiracao(
            '[SUAP] Progressão Docente - Prazo de reavaliação expirado',
            'O prazo para reavaliação da progressão docente expirou. Sem manifestação do avaliador, '
            'o recurso foi encerrado sem alteração e o resultado foi encaminhado para ciência do avaliado.',
        )

    def pode_finalizar_avaliacao(self, request):
        responsavel = request.user.get_vinculo()
        if not self.usuario_eh_avaliador(request.user):
            return False
        qtd = self.percentual_avaliado(responsavel).get('qtd')
        qtd_total = self.percentual_avaliado(responsavel).get('qtd_total')
        if qtd == 0:
            # se o formulário da avaliação tiver critérios que NÃO necessite de arquivo, retorno False
            if self.formulario.criterio_set.filter(necessita_arquivos=False).exists():
                return False
            # se o formulário da avaliação tiver critérios que NECESSITAM de arquivos, é necessário verificar e foi preenchido
            # caso positivo (foi preenchido), retorna False
            for criterio in self.formulario.criterio_set.filter(necessita_arquivos=True):
                for item in criterio.item_set.all():  # apenas itens de critérios que necessitam de arquivos
                    if AvaliacaoItem.objects.filter(avaliacao=self, item=item).exists():
                        return False
        return qtd == qtd_total

    def pode_assinar_avaliacao(self, request):
        return self.pode_finalizar_avaliacao(request)

    def pode_finalizar_avaliacao_discente(self, request):
        responsavel = request.user.get_vinculo()
        qtd_item_total = 0
        for criterio in self.formulario.criterio_set.filter(avaliacao_discente=True):
            qtd_item_total += criterio.item_set.all().count()
        qtd_avaliado = AvaliacaoItem.objects.filter(avaliacao=self, responsavel=responsavel).count()
        return qtd_item_total == qtd_avaliado

    def pode_encaminhar_avaliacao_para_ciencia(self, request):
        return self.situacao in [Avaliacao.REAVALIACAO, Avaliacao.EM_AVALIACAO]

    def encaminhar_avaliacao_para_ciencia(self, request):
        if self.pode_encaminhar_avaliacao_para_ciencia(request):
            with transaction.atomic():
                self.situacao = self.AGUARDANDO_CIENCIA_RESULTADO
                self.data_liberacao_ciencia = datetime.now()
                self.finalizada = True
                self.save()
                self.calcular_pontuacao_avaliacao()
                self._atualizar_situacao_progressao(self)

    def pode_finalizar_ciencia_resultado(self, request):
        return bool(self.usuario_eh_dono(request.user) and self.situacao == Avaliacao.AGUARDANDO_CIENCIA_RESULTADO)

    def finalizar_ciencia_resultado(self, request):
        if self.pode_finalizar_ciencia_resultado(request):
            with transaction.atomic():
                self.situacao = self.CONCLUIDA
                self.finalizada = True
                self.save()
                self._atualizar_situacao_progressao(self)

    def finalizar_avaliacao(self, request):
        if self.pode_finalizar_avaliacao(request):
            with transaction.atomic():
                self.situacao = self.CONCLUIDA
                self.finalizada = True
                self.save()
                self._atualizar_situacao_progressao(self)

    def finalizar_avaliacao_discente(self, relacionamento):
        with transaction.atomic():
            try:
                obj = DiscenteAptosAvaliacao.objects.get(matricula=relacionamento.matricula, progressao=self.progressao, avaliacao=self)
            except DiscenteAptosAvaliacao.DoesNotExist:
                raise ValueError(f'Discente apto não encontrado para a matrícula {relacionamento.matricula} na avaliação {self}')
            obj.avaliacao_realizada = True
            obj.save()
            #
            # selecionando avaliações
            qs_avaliacoes = self.progressao.avaliacao_set.all().exclude(pk=self.pk).prefetch_related('formulario__criterio_set__item_set')
            #
            if qs_avaliacoes.exists():
                Aluno = apps.get_model('edu', 'Aluno')
                avaliador = Aluno.objects.get(matricula=obj.matricula)
                for a in qs_avaliacoes:
                    #
                    # se não existe e foi criado, vamos copiar os itens de avaliação
                    criterio = a.formulario.criterio_set.filter(avaliacao_discente=True).first()
                    if not criterio:
                        # critério não exige avaliação discente, então não há o que fazer
                        continue
                    #
                    # verificando se para a avaliação existe o objeto de discente apto a realizar a avaliação
                    discente_apto, _ = DiscenteAptosAvaliacao.objects.get_or_create(
                        nome=obj.nome, matricula=obj.matricula, progressao=self.progressao, avaliacao=a
                    )
                    for ai in AvaliacaoItem.objects.filter(avaliacao=self, responsavel=avaliador.get_vinculo()):
                        #
                        novo_item = criterio.item_set.filter(nome=ai.item.nome).first()
                        if not novo_item:
                            continue
                        #
                        AvaliacaoItem.objects.get_or_create(
                            avaliacao=a,
                            item=novo_item,
                            responsavel=ai.responsavel,
                            defaults={
                                'pontuacao_form': ai.pontuacao_form,
                                'deferimento': ai.deferimento,
                            },
                        )
                    #
                    discente_apto.avaliacao_realizada = True
                    discente_apto.save()

    @staticmethod
    def _atualizar_situacao_progressao(avaliacao):
        #
        # verificando todas as avaliações que estão com a sitação REAVALIACAO
        if avaliacao.progressao.situacao == ProgressaoDocente.REAVALIACAO:
            # varrendo as avaliações
            em_reavaliacao = False
            for i in avaliacao.progressao.avaliacao_set.all():
                if i.situacao == Avaliacao.REAVALIACAO:
                    em_reavaliacao = True
                    break
            if not em_reavaliacao:
                avaliacao.progressao.situacao = ProgressaoDocente.EM_AVALIACAO
                avaliacao.progressao.save()

        # verificando todas as avaliações do processo de progressão
        # - se todas as avaliações estão finalizadas, mudar a situação do processo
        if avaliacao.progressao.situacao == ProgressaoDocente.EM_AVALIACAO:
            avancar = True
            for i in avaliacao.progressao.avaliacao_set.all():
                if i.finalizada is False:
                    avancar = False
                    break
            if avancar:
                avaliacao.progressao.situacao = ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO
                avaliacao.progressao.save()

        # verificando se todas as avaliações estão com a situação "em_avaliacao"
        # - em caso positivo, atualiza a situação do processo de progressão
        if avaliacao.progressao.situacao == ProgressaoDocente.AGUARDANDO_PREENCHIMENTO:
            avancar = True
            for i in avaliacao.progressao.avaliacao_set.all():
                if i.situacao != Avaliacao.EM_AVALIACAO:
                    avancar = False
                    break
            if avancar:
                avaliacao.progressao.situacao = ProgressaoDocente.EM_AVALIACAO
                avaliacao.progressao.save()

    # 1. quando o dono do processo está ciente do resultado e concorda com ele, concluído a avaliação em definitivo
    # 2. ao dar ciência do resultado, verificar se todas as avaliações estão com ciência e avançar o processo
    def concluir_avaliacao(self, request):
        if self.pode_concluir_avaliacao(request):
            with transaction.atomic():
                self.situacao = self.CONCLUIDA
                self.save()
                self.calcular_pontuacao_avaliacao()
                self._atualizar_situacao_progressao(self)

    def pode_concluir_avaliacao(self, request):
        return self.usuario_eh_dono(request.user)

    def pode_dar_ciencia_avaliacao(self, request):
        return self.situacao in [Avaliacao.AGUARDANDO_CIENCIA_RESULTADO, Avaliacao.EDITACAO_PARA_REAVALIACAO] and self.usuario_eh_dono(request.user)

    def pode_voltar_para_reavaliacao(self, request):
        return self.pode_dar_ciencia_avaliacao(request)

    def pode_reavaliar_avaliacao(self, request):
        return self.situacao == Avaliacao.REAVALIACAO and self.usuario_eh_avaliador(request.user)

    def reavaliar_avaliacao(self, request):
        if self.pode_voltar_para_reavaliacao(request):
            with transaction.atomic():
                #
                # cadastrando o recurso da avaliação
                r = RecursoAvaliacao()
                r.avaliacao = self
                r.texto_recurso = request.POST.get('observacao')
                r.situacao = RecursoAvaliacao.EM_REAVALIACAO
                r.data_cadastro_recurso = datetime.now()
                r.save()
                #
                # mudando situação da avaliação
                self.situacao = self.REAVALIACAO
                self.pontuacao_final = None
                self.data_liberacao_reavaliacao = datetime.today()

                self.save()
                #
                # mudando situação do processo
                self.progressao.situacao = ProgressaoDocente.REAVALIACAO
                self.progressao.save()

    def finalizar_reavaliacao(self, request):
        if self.pode_reavaliar_avaliacao(request):
            with transaction.atomic():
                #
                # recursos
                for i in self.recursoavaliacao_set.filter(situacao=RecursoAvaliacao.EM_REAVALIACAO):
                    i.situacao = RecursoAvaliacao.FINALIZADO
                    i.texto_conclusao_reavaliacao = request.POST.get('texto_conclusao_reavaliacao')
                    i.data_conclusao_reavaliacao = datetime.now()
                    i.save()
                #
                # avaliação
                self.situacao = Avaliacao.AGUARDANDO_CIENCIA_RESULTADO
                # o prazo de ciência recomeça aqui; herdar a data da ciência anterior faria a
                # etapa nascer vencida e o avaliado perderia a chance de se manifestar.
                self.data_liberacao_ciencia = datetime.now()
                self.save()
                self.calcular_pontuacao_avaliacao()
                #
                # progressão docente
                self._atualizar_situacao_progressao(self)

    #
    # devolver um dicionário de dados com os avaliadores de cada critério da avaliação em questão

    def get_avaliadores(self, apenas_discentes=False, apenas_avaliado=False):
        d = {}
        qs_avaliacoes_itens = AvaliacaoItem.objects.filter(avaliacao=self)
        if apenas_discentes and not apenas_avaliado:
            qs_avaliacoes_itens = qs_avaliacoes_itens.exclude(responsavel=self.progressao.avaliado.get_vinculo())
        if apenas_avaliado and not apenas_discentes:
            qs_avaliacoes_itens = qs_avaliacoes_itens.filter(responsavel=self.progressao.avaliado.get_vinculo())
        for i in qs_avaliacoes_itens:
            #
            responsavel = i.responsavel
            resultado_consideracao_positiva = self.resultado_consideracao_positiva(avaliador=responsavel)
            dados_consideracao_positiva = resultado_consideracao_positiva.get(i.item.criterio.nome)
            media = None
            positiva = None
            if dados_consideracao_positiva:
                media = dados_consideracao_positiva.get('media')
                positiva = dados_consideracao_positiva.get('positiva')
            #
            if i.item.criterio.necessita_arquivos:
                responsavel = i.responsavel_avaliacao
            # nome_responsavel = None
            # if responsavel:
            #     nome_responsavel = responsavel.nome
            #
            _di = {
                'avaliador': responsavel,
                'media_avaliacao': media,
                'avaliacao_positiva': positiva,
            }
            #
            if i.item.criterio.nome not in d:
                d[i.item.criterio.nome] = {'avaliadores': [_di]}
            else:
                if _di not in d[i.item.criterio.nome]['avaliadores']:
                    d[i.item.criterio.nome]['avaliadores'].append(_di)
            #
        return d

    #
    # retorna um dicionário de dados das avaliações dicentes de um aluno em específico

    def resultado_consideracao_positiva(self, avaliador, criterio=None):
        qs = (
            AvaliacaoItem.objects.filter(avaliacao=self, responsavel=avaliador)
            .values(
                responsavel_nome=F('responsavel__pessoa__nome'),
                avaliacao_discente=F('item__criterio__avaliacao_discente'),
                valor_minimo_consideracao_positiva=F('item__criterio__valor_minimo_consideracao_positiva'),
                pontuacao_consideracao_positiva=F('item__criterio__pontuacao_consideracao_positiva'),
                nome_criterio=F('item__criterio__nome'),
            )
            .annotate(valor=Sum('pontuacao_form'), qtd=Count('pk'), media=Avg('pontuacao_form'))
        )
        # qs = AvaliacaoItem.objects.filter(avaliacao=self, responsavel=avaliador).prefetch_related('item__criterio')
        if criterio:
            qs = qs.filter(criterio=criterio).select_related('criterio')
        d = {}
        pontos = 0
        cont = 1
        for i in qs:
            divisao = decimal.Decimal(i.get('qtd') / 2)
            if i.get('avaliacao_discente') and i.get('valor_minimo_consideracao_positiva'):
                valor_minimo = i.get('pontuacao_consideracao_positiva')
                pontos += i.get('valor')
                media = pontos / divisao
                positiva = media >= valor_minimo
                #
                nome_criterio = i.get('nome_criterio')
                if nome_criterio not in d:
                    d[nome_criterio] = {'total_notas': pontos, 'media': f'{media:.2f}', 'positiva': positiva}
                else:
                    d[nome_criterio]['total_notas'] = pontos
                    d[nome_criterio]['media'] = f'{media:.2f}'
                    d[nome_criterio]['positiva'] = positiva
                cont += 1
        return d

    #
    # gerando um dicionário com informações relevantes da avaliação

    def info_avaliacao(self, **kwargs):
        dict_info = {}
        #
        avaliado_processo = kwargs.pop('avaliado', None)
        avaliador = kwargs.pop('avaliador', None)
        avaliacao = kwargs.pop('avaliacao', None)
        #
        # Prefetch otimizado para carregar os itens e as avaliações relacionadas de uma só vez
        criterios = self.formulario.criterio_set.prefetch_related(
            'item_set', Prefetch('item_set__avaliacaoitem_set', queryset=AvaliacaoItem.objects.filter(avaliacao=avaliacao))
        )

        totais_cache = {}

        for criterio in criterios:
            eh_autoavaliacao = criterio.autoavaliacao
            necessita_arquivos = criterio.necessita_arquivos
            eh_avaliacao_discente = criterio.avaliacao_discente

            cont = 1
            for item in criterio.item_set.all():
                _dados = {
                    'order': f'{criterio.order}.{cont}',
                    'item': item.nome,
                    'eh_arquivo': necessita_arquivos,
                }
                item_tem_avaliacao = False

                # Unificação da lógica de autoavaliação e arquivos

                if eh_autoavaliacao:
                    _qs = item.avaliacaoitem_set.filter(avaliacao=avaliacao, responsavel=avaliado_processo).order_by('item__criterio')
                else:
                    _qs = item.avaliacaoitem_set.filter(avaliacao=avaliacao, responsavel=avaliador).order_by('item__criterio')
                    if necessita_arquivos:
                        _qs = item.avaliacaoitem_set.filter(
                            avaliacao=avaliacao, responsavel=avaliado_processo, responsavel_avaliacao=avaliador
                        ).order_by('item__criterio')

                _itens = []
                for ai in _qs:
                    item_tem_avaliacao = True
                    pontuacao_original = None
                    pontos = str(ai.pontuacao.pontos) if ai.pontuacao else str(ai.pontuacao_form)
                    if ai.pontuacao_validada:
                        pontuacao_original = ai.pontuacao.pontos
                        pontos = str(ai.pontuacao_validada)

                    _itens.append(
                        {
                            'avaliacao_item_id': ai.id,
                            'deferimento': ai.deferimento,
                            'justificativa': ai.justificativa,
                            'arquivo': ai.arquivo,
                            'pontuacao': pontos,
                            'pontuacao_original': pontuacao_original,
                            'eh_arquivo': necessita_arquivos,
                        }
                    )

                d = {'itens': _itens, 'item_tem_avaliacao': item_tem_avaliacao, 'permitir_opcao_nao_se_aplica': item.permitir_opcao_nao_se_aplica}
                _dados.update(d)

                # Cache das pontuações
                if criterio.nome not in totais_cache:
                    if eh_autoavaliacao or eh_avaliacao_discente:
                        totais_cache[criterio.nome] = criterio.get_pontuacao_total_avaliado(avaliacao=avaliacao, responsavel=avaliado_processo)
                    else:
                        totais_cache[criterio.nome] = criterio.get_pontuacao_total_avaliado(avaliacao=avaliacao, responsavel_avaliacao=avaliador)
                        if necessita_arquivos:
                            totais_cache[criterio.nome] = criterio.get_pontuacao_total_avaliado(avaliacao=avaliacao, responsavel=avaliado_processo)

                totais = totais_cache[criterio.nome]

                # Atualizando dicionário de dados
                if criterio.nome not in dict_info:
                    dict_info[criterio.nome] = {
                        'order': criterio.order,
                        'autoavaliacao': eh_autoavaliacao,
                        'avaliacao_discente': eh_avaliacao_discente,
                        'eh_arquivos': necessita_arquivos,
                        'totais': totais,
                        'dados': [_dados],
                    }
                else:
                    dict_info[criterio.nome]['dados'].append(_dados)

                cont += 1
        return dict_info

    #
    # calcula a pontuação da avaliação

    def calcular_pontuacao_avaliacao(self):
        avaliador = self.avaliadores.first().get_vinculo()
        avaliado_processo = self.progressao.avaliado.get_vinculo()
        total_pontos_avaliacao = 0
        for criterio in self.formulario.criterio_set.all():
            dados = criterio.get_pontuacao_total_avaliado(avaliacao=self, responsavel=avaliado_processo, responsavel_avaliacao=avaliador)
            total_pontos_avaliacao += decimal.Decimal(dados.get('p'))
        # setando valor
        self.pontuacao_final = total_pontos_avaliacao
        self.pontuacao_final_sem_limite = None
        if total_pontos_avaliacao > Avaliacao.PONTUACAO_MAXIMA_POR_AVALIACAO:
            self.pontuacao_final = decimal.Decimal(Avaliacao.PONTUACAO_MAXIMA_POR_AVALIACAO)
            self.pontuacao_final_sem_limite = total_pontos_avaliacao
        self.save()


# Etapas da avaliação em ordem de fluxo, da MAIS ATRASADA para a mais adiantada. A situação do
# processo espelha a avaliação mais atrasada, porque é nela que está a ação pendente.
# EDITACAO_PARA_REAVALIACAO vem logo após AGUARDANDO_PREENCHIMENTO por ser a mesma etapa do ponto
# de vista de quem age: a bola está com o avaliado, que volta a preencher.
ETAPAS_AVALIACAO_DA_MAIS_ATRASADA = (
    Avaliacao.AGUARDANDO_PREENCHIMENTO,
    Avaliacao.EDITACAO_PARA_REAVALIACAO,
    Avaliacao.EM_AVALIACAO,
    Avaliacao.REAVALIACAO,
    Avaliacao.AGUARDANDO_CIENCIA_RESULTADO,
    Avaliacao.CONCLUIDA,
)

# ProgressaoDocente não tem estado equivalente a EDITACAO_PARA_REAVALIACAO; ele cai em REAVALIACAO,
# que é o estado do processo durante todo o ciclo de reavaliação.
SITUACAO_PROCESSO_POR_ETAPA_DA_AVALIACAO = {
    Avaliacao.AGUARDANDO_PREENCHIMENTO: ProgressaoDocente.AGUARDANDO_PREENCHIMENTO,
    Avaliacao.EDITACAO_PARA_REAVALIACAO: ProgressaoDocente.REAVALIACAO,
    Avaliacao.EM_AVALIACAO: ProgressaoDocente.EM_AVALIACAO,
    Avaliacao.REAVALIACAO: ProgressaoDocente.REAVALIACAO,
    Avaliacao.AGUARDANDO_CIENCIA_RESULTADO: ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO,
    Avaliacao.CONCLUIDA: ProgressaoDocente.CIENTE_RESULTADO,
}


class AvaliacaoItem(models.ModelPlus):
    SEARCH_FIELDS = ['avaliacao__progressao__avaliado__pessoa_fisica__nome', 'avaliacao__formulario__nome', 'item__nome', 'item__descricao']

    TIPO_DEFERIDO = 1
    TIPO_INDEFERIDO = 2

    TIPO_CHOICES = (
        (TIPO_DEFERIDO, 'Deferido'),
        (TIPO_INDEFERIDO, 'Indeferido'),
    )

    avaliacao = models.ForeignKeyPlus('progressao_docente.Avaliacao', verbose_name='Avaliação', on_delete=models.CASCADE, null=True)
    item = models.ForeignKeyPlus('progressao_docente.Item', verbose_name='Item', on_delete=models.CASCADE, null=True)
    arquivo = models.FileFieldPlus(upload_to='progressao_docente/arquivos/', max_length=250, null=True, blank=True)
    #
    # quando for pontuação de arquivos
    pontuacao = models.ForeignKeyPlus('progressao_docente.PontuacaoItem', verbose_name='Pontuação', on_delete=models.CASCADE, null=True, blank=True)
    #
    # quando for pontuação de form (input radio)
    pontuacao_form = models.DecimalFieldPlus('Pontuação do Item', max_length=4, max_digits=12, decimal_places=1, null=True, blank=True)
    #
    # se o campo pontuacao_validada estiver preenchido, é um indicativo de que a pontuação validada foi alterada pelo avaliador
    pontuacao_validada = models.DecimalFieldPlus('Pontuação Validada', max_digits=12, decimal_places=2, null=True, blank=True)
    deferimento = models.IntegerFieldPlus('Deferimento', choices=TIPO_CHOICES, null=True, blank=True)
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    # IMPORTATE
    # - o atributo responsavel_avaliacao será setado apenas nos itens que necessitam de arquivo
    responsavel = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável', on_delete=models.SET_NULL, null=True, blank=True
    )  # responsável pelo cadastros do item
    responsavel_avaliacao = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Responsável pela Avaliação',
        on_delete=models.SET_NULL,
        related_name='responsavel_avaliacao_related',
        null=True,
        blank=True,
    )  # responsável pelo deferimento/indeferimento do item

    class Meta:
        verbose_name = 'Avaliação de Item'
        verbose_name_plural = 'Avaliações de Itens'
        unique_together = ('avaliacao', 'item', 'responsavel', 'arquivo')

    def pode_editar(self):
        pode_editar = False
        if (
            self.deferimento is None
            or self.deferimento == AvaliacaoItem.TIPO_INDEFERIDO
            or self.pontuacao_validada
            or self.avaliacao.situacao == Avaliacao.AGUARDANDO_PREENCHIMENTO
            or self.avaliacao.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO
        ):
            pode_editar = True
        return pode_editar

    def get_pontuacao_validada(self):
        if self.deferimento == AvaliacaoItem.TIPO_DEFERIDO:
            if self.pontuacao is not None:
                if self.pontuacao_validada is not None:
                    return self.pontuacao_validada
                else:
                    return self.pontuacao.pontos
        return None

    def validar_dados(self, request):
        pontuacao_validada = request.POST.get('pontuacao_validada', None)
        if pontuacao_validada:
            pontuacao_validada = decimal.Decimal(pontuacao_validada)
            if pontuacao_validada > self.pontuacao.pontos:
                raise ValueError(
                    _(f'A pontuação validada ({pontuacao_validada}) não pode ser maior que o valor padrão do item ({self.pontuacao.pontos}).')
                )

    def deferir(self, request):
        justificativa = request.POST.get('justificativa', None)
        pontuacao_validada = request.POST.get('pontuacao_validada', None)
        # TODO: verificar permissão para deferir
        self.deferimento = AvaliacaoItem.TIPO_DEFERIDO
        self.justificativa = justificativa
        if pontuacao_validada:  # trantando se a pontuação valida vier vazio ao inves de none
            self.pontuacao_validada = pontuacao_validada
        if pontuacao_validada == '':
            self.pontuacao_validada = None
        self.responsavel_avaliacao = request.user.get_vinculo()
        self.save()

    def indeferir(self, request, justificativa):
        # TODO: verificar permissão para indeferir
        self.deferimento = AvaliacaoItem.TIPO_INDEFERIDO
        self.justificativa = justificativa
        self.responsavel_avaliacao = request.user.get_vinculo()
        self.save()

    def apagar(self, request):
        # TODO verificar usuário que está executando a ação; apagar arquivos relacionado com a avaliação;
        self.delete()


class Formulario(models.ModelPlus):
    SEARCH_FIELDS = [
        'nome',
    ]

    nome = models.CharFieldPlus(
        'Formulário',
    )
    inicio_vigencia = models.DateFieldPlus('Início da Vigência')
    fim_vigencia = models.DateFieldPlus('Fim da Vigência', null=True, blank=True)
    data_cadastro = models.DateFieldPlus('Data de Cadastro', auto_now=True)

    class Meta:
        verbose_name = 'Formulário'
        verbose_name_plural = 'Formulários'

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/progressao_docente/formulario/{self.pk}/ver/'

    def estah_vigente(self):
        hoje = date.today()
        return not (self.fim_vigencia and self.fim_vigencia < hoje)


class Criterio(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'descricao']

    formulario = models.ForeignKeyPlus('progressao_docente.Formulario', verbose_name='Formulário', on_delete=models.CASCADE, null=True)
    order = models.CharFieldPlus('Order')
    nome = models.CharFieldPlus('Critério')
    descricao = models.TextField('Descrição', null=True, blank=True)
    inicio_vigencia = models.DateFieldPlus('Início da Vigência')
    fim_vigencia = models.DateFieldPlus('Fim da Vigência', null=True, blank=True)
    # limite de pontos gerais
    limite_pontos = models.DecimalFieldPlus('Limite de Pontos', max_digits=12, decimal_places=2, null=True, blank=True)
    data_cadastro = models.DateFieldPlus('Data de Cadastro', auto_now=True)
    #
    necessita_arquivos = models.BooleanField('Necessita de Arquivos?', default=True)
    autoavaliacao = models.BooleanField('Autoavaliação', default=False)
    avaliacao_discente = models.BooleanField('Avaliação Discente', default=False)
    # valor mínimo de consideração positiva é o valor mínimo que o servido tem que atingir no critério para, na avaliação, ele ser considerado positivo
    #  - se o avalido NÃO atingir o valor mínimo, ele receberá zero no critério
    #  - se o avaliado ATINGIR o valor mínimo, ele receberá o valor cadastrado no campo "pontuacao_consideracao_positiva"
    valor_minimo_consideracao_positiva = models.DecimalFieldPlus(
        'Valor Mínimo para Consideração Positiva',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Valor mínimo da média dos itens para considerar a avaliação como positiva.',
    )
    pontuacao_consideracao_positiva = models.DecimalFieldPlus(
        'Pontos', max_digits=12, decimal_places=2, null=True, blank=True, help_text='Pontuação final do critério se a avaliação for positiva.'
    )
    # campo que diz se na verificação do critério será levado em consideração as funções CD3 ou CD4 do avaliado
    # - se o avaliado tiver CD3 ou CD4 no período de avaliação, o máximo de pontuação no critérios será do campo "maximo_pontuacao_com_cd"
    # - se o avaliado NÃO tiver CD3 ou CD4 no período de avaliação, o máximo de pontuação no critérios será do campo "maximo_pontuacao_sem_cd"
    verificar_cd = models.BooleanField('Verificar CDs?', default=False)
    maximo_pontuacao_com_cd = models.DecimalFieldPlus('Pontuação Máxima com CD3 ou CD4', max_digits=12, decimal_places=2, null=True, blank=True)
    maximo_pontuacao_sem_cd = models.DecimalFieldPlus('Pontuação Máxima sem CD3 ou CD4', max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = 'Critério'
        verbose_name_plural = 'Critérios'

    #

    def __str__(self):
        return self.nome

    #

    def get_absolute_url(self):
        return f'/progressao_docente/criterio/{self.pk}/ver/'

    #

    def qtd_itens(self):
        cache_key = f'criterio_item_set_count_{self.id}'
        cont = cache.get(cache_key)
        if cont is None:
            cont = self.item_set.count()
            cache.set(cache_key, cont)
        return cont

    #

    def media_avaliacao_criterio(self, avaliacao, avaliador, avaliado_processo):
        pontuacao_total_avaliado = self.get_pontuacao_total_avaliado(
            avaliacao=avaliacao, responsavel=avaliado_processo, responsavel_avaliacao=avaliador
        )
        return pontuacao_total_avaliado.get('media_pontuacao') or 0

    #
    # caso o critério seja auto avaliação ou avaliação discente, essa será a pontuação real do critério

    def get_pontuacao_consideracao_positiva(self, avaliacao, avaliador, avaliado_processo):
        pontuacao = 0.0
        if (
            self.valor_minimo_consideracao_positiva
            and self.media_avaliacao_criterio(avaliacao, avaliador, avaliado_processo) > self.valor_minimo_consideracao_positiva
        ):
            pontuacao = self.pontuacao_consideracao_positiva
        return pontuacao

    #

    def get_itens(self, avaliacao, avaliados=None, deferidos=None, **kwargs):
        qs = AvaliacaoItem.objects.filter(item__criterio=self, avaliacao=avaliacao)
        #
        responsavel = kwargs.pop('responsavel', None)
        if responsavel:
            qs = qs.filter(responsavel=responsavel)
        #
        responsavel_avaliacao = kwargs.pop('responsavel_avaliacao', None)
        if responsavel_avaliacao:
            qs = qs.filter(responsavel_avaliacao=responsavel)
        #
        if avaliados:
            qs = qs.filter(deferimento__isnull=False)
        if deferidos is True:
            qs = qs.filter(deferimento=AvaliacaoItem.TIPO_DEFERIDO)
        if deferidos is False:
            qs = qs.filter(deferimento=AvaliacaoItem.TIPO_INDEFERIDO)
        return qs

    #

    def get_pontuacao_total(self, avaliacao, responsavel, avaliados=None, deferidos=None, itens=None):
        if not itens:
            d_retorno = self.get_itens(avaliacao=avaliacao, responsavel=responsavel, avaliados=avaliados, deferidos=deferidos)
        else:
            d_retorno = itens
        #
        if self.necessita_arquivos:
            if avaliacao.situacao == Avaliacao.AGUARDANDO_PREENCHIMENTO:
                d_retorno = d_retorno.aggregate(p=Coalesce(Sum('pontuacao__pontos'), Decimal(0)))
            else:
                _p = 0
                if d_retorno.exists():
                    for _item in d_retorno:
                        pontuacao_validada = _item.get_pontuacao_validada()
                        if pontuacao_validada:
                            _p += pontuacao_validada
                d_retorno = {'p': Decimal(value=_p)}
            # d_retorno = d_retorno.aggregate(p=Coalesce(Sum("pontuacao__pontos"), Decimal(0)))
        else:
            # nesta condição, devemos verificar os critérios de autoavaliação e avaliação discente, pois a
            # pontuação não é a soma simples de todos os itens, e sim uma porcentagem de avaliações positivas
            # sendo a regra:
            # -----------------------------------------------------
            # AUTOAVALIAÇÃO
            # se a média da nota da autoavaliação for MAIOR OU IGUAL A que 5
            #  - A NOTA É 5
            # senão
            #  - A NOTA É 0
            # -----------------------------------------------------
            # AVALIAÇÃO DISCENTE
            # se a quantidade de avaliações positivas for MAIOR QUE 50%
            # - A NOTA É 5 PONTOS
            # senão
            # - A NOTA É 0
            #
            # A QUANTIDADE TOTAL DO CRITÉRIO SERÁ
            #  - NOTA DA AUTOAVALIAÇÃO + NOTA DA AVALIAÇÃO DISCENTE

            #
            if self.avaliacao_discente or self.autoavaliacao:
                #
                # verificando a nota da avaliação discente
                discentes_aptos = DiscenteAptosAvaliacao.objects.filter(avaliacao=avaliacao, avaliacao_realizada=True).values('matricula')
                Aluno = apps.get_model('edu', 'Aluno')
                qtd_avaliacoes_positivas = 0
                qtd_avaliacoes_negativas = 0
                for a in discentes_aptos:
                    aluno = Aluno.objects.get(matricula=a.get('matricula'))
                    _resultado = avaliacao.resultado_consideracao_positiva(avaliador=aluno.get_vinculo())
                    resultado = _resultado.get(self.nome)
                    if resultado:
                        if resultado.get('positiva'):
                            qtd_avaliacoes_positivas += 1
                        else:
                            qtd_avaliacoes_negativas += 1
                # # por padrão a pontuação "p" vai zerada
                d_retorno = {'p': 0.0, 'nota_discente': 0.0, 'qtd_positivas': qtd_avaliacoes_positivas, 'qtd_negativas': qtd_avaliacoes_negativas}
                # verificando se a quantidade de avaliações positivas está acima do mínimo considerado
                minimo = (qtd_avaliacoes_positivas + qtd_avaliacoes_negativas) / 2
                if qtd_avaliacoes_positivas > minimo:
                    d_retorno.update(
                        {
                            'p': 5.0,
                            'nota_discente': 5.0,
                        }
                    )

                # verificando a nota da autoavaliação
                dict_avaliadores = avaliacao.get_avaliadores(apenas_avaliado=True)
                avaliadores = dict_avaliadores.get(self.nome) or {}
                d_retorno.update(
                    {
                        'nota_avaliado': 0.0,
                    }
                )
                if avaliadores.get('avaliadores'):
                    avaliador = avaliadores.get('avaliadores')[0]
                    # se a avaliação do avaliador for considerada positiva
                    if avaliador.get('avaliacao_positiva'):
                        pontuacao_adicional = 5.0
                        d_retorno.update(
                            {
                                'p': d_retorno.get('p') + pontuacao_adicional,
                                'nota_avaliado': pontuacao_adicional,
                            }
                        )
            #
            else:
                qs_itens = d_retorno
                d_retorno = qs_itens.aggregate(p=Coalesce(Sum('pontuacao_form'), Decimal(0)))
                qtd_total_item = qs_itens.count()
                media = 0
                d_retorno.update({'pontuacao_positiva': None, 'media_pontuacao': media})
                if qtd_total_item > 0:
                    # pontuacao positica
                    if self.valor_minimo_consideracao_positiva:
                        soma_pontuacao = 0
                        for i in qs_itens:
                            soma_pontuacao += i.pontuacao_form
                        media = soma_pontuacao / qtd_total_item
                        d_retorno.update({'pontuacao_positiva': 0, 'media_pontuacao': media, 'soma_pontuacao': soma_pontuacao, 'p': 0.0})
                        if media > self.valor_minimo_consideracao_positiva:
                            d_retorno.update({'pontuacao_positiva': self.pontuacao_consideracao_positiva, 'p': self.pontuacao_consideracao_positiva})
        #
        if self.limite_pontos and self.limite_pontos < int(d_retorno.get('p') or 0):
            d_retorno.update({'p': self.limite_pontos, 'total': d_retorno.get('p'), 'ajuste': d_retorno.get('p') - self.limite_pontos})
        else:
            #
            # quando o critério não tem limite de pontuação
            d_retorno.update({'total': d_retorno.get('p'), 'p': d_retorno.get('p')})
            #
            # se não tem limite de pontos mas o critério exige verificação das funções de CD3 e CD4
            if self.verificar_cd:
                # se é criterio que verifica cd e o avaliado não tem cd, o máximo de pontuação é o valor cadastrado no campo "maximo_pontuacao_sem_cd"
                # se o avaliado tiver cd, o máximo de pontuação é o valor cadastrado no campo "maximo_pontuacao_com_cd"
                _limite = self.maximo_pontuacao_sem_cd
                tem_cd = self._verifica_cd(avaliacao)
                if tem_cd:
                    _limite = self.maximo_pontuacao_com_cd
                d_retorno.update(
                    {
                        '_limite': _limite,
                    }
                )
                if d_retorno.get('p') > _limite:
                    d_retorno.update({'p': _limite, 'ajuste': d_retorno.get('p') - _limite, 'total': d_retorno.get('p')})
        #
        return d_retorno

    #

    def get_pontuacao_total_avaliado(self, **kwargs):
        avaliacao = kwargs.pop('avaliacao', None)
        responsavel = kwargs.pop('responsavel', None)
        responsavel_avaliacao = kwargs.pop('responsavel_avaliacao', None)
        #
        eh_autoavaliacao = self.autoavaliacao
        eh_avaliacao_discente = self.avaliacao_discente
        #
        if eh_autoavaliacao or eh_avaliacao_discente:
            dados = self.get_pontuacao_total(avaliacao, responsavel, True, True)
        else:
            dados = self.get_pontuacao_total(avaliacao, responsavel_avaliacao, True, True)
            if self.necessita_arquivos:
                dados = self.get_pontuacao_total(avaliacao, responsavel, True, True)
        #
        return dados

    #

    def get_qtde_itens_avaliados(self, avaliacao, responsavel, atualizar=False):
        cache_key = f'get_qtde_itens_avaliados_count_{self.id}_{avaliacao.pk}'
        cont = cache.get(cache_key)
        if cont is None or atualizar:
            cont = self.get_itens(avaliacao=avaliacao, responsavel=responsavel, avaliados=True).count()
            cache.set(cache_key, cont)
        return cont

    #

    def pode_adicionar_pontuacao(self, avaliacao, responsavel):
        if not self.necessita_arquivos:
            return False
        if self.limite_pontos:
            return True  # a regra atual permite a adição de arquivos mesmo atingindo o limite do criterio
            # return self.necessita_arquivos and int(self.get_pontuacao_total(avaliacao, responsavel).get("p") or 0) < self.limite_pontos
        return True

    #

    def _verifica_cd(self, avaliacao):
        avaliado = avaliacao.progressao.avaliado
        tem_cd3_ou_cd4 = False
        for f in avaliado.historico_funcao(data_inicio=avaliacao.periodo_inicio, data_fim=avaliacao.periodo_fim):
            if 'CD3'.lower() in f.funcao_display.lower() or 'CD4'.lower() in f.funcao_display.lower():
                tem_cd3_ou_cd4 = True
                break
        return tem_cd3_ou_cd4


class Item(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'descricao']

    criterio = models.ForeignKeyPlus('progressao_docente.Criterio', verbose_name='Critério', on_delete=models.CASCADE, null=True)
    nome = models.CharFieldPlus('Nome', max_length=1500)
    descricao = models.TextField('Descrição', null=True, blank=True)
    pontuacao_fixa = models.BooleanField(
        'Pontuação Fixa?',
        default=False,
        help_text='Quando marcado, não permite que a pontuação seja alterada. Neste caso, quando validado será considerado o valor total do item e quando invalidado será zerada a pontuação.',
    )
    insercao_unica = models.BooleanField(
        'Inserção Única?',
        default=False,
        help_text='Quando marcado, não será possível adicionar este item mais de uma vez para avaliação, mesmo a pontuação sendo diferente.',
    )
    permitir_opcao_nao_se_aplica = models.BooleanField(
        "Permitir a opção de 'Não se Aplica'?",
        default=False,
        help_text="Quando marcado, o item irá apresentar a opção de 'Não se aplica' para o usuário.",
    )
    inicio_vigencia = models.DateFieldPlus('Início da Vigência')
    fim_vigencia = models.DateFieldPlus('Fim da Vigência', null=True, blank=True)

    class Meta:
        verbose_name = 'Item'
        verbose_name_plural = 'Itens'

    def __str__(self):
        return self.nome

    # apenas para itens com critérios que não necessitam de arquivos
    def get_range_valores(self, avaliacao, ignorar_zero=False):
        lista = []
        inicio = 0
        if ignorar_zero:
            inicio = 1
        #
        qs_pontuacaoitem = self.pontuacaoitem_set.all()
        #
        if self.criterio.verificar_cd:
            #
            tem_cd3_ou_cd4 = self.criterio._verifica_cd(avaliacao)
            #
            qs_pontuacaoitem = self.pontuacaoitem_set.all().exclude(Q(descricao__icontains='CD3') | Q(descricao__icontains='CD4'))
            if tem_cd3_ou_cd4:
                qs_pontuacaoitem = self.pontuacaoitem_set.filter(Q(descricao__icontains='CD3') | Q(descricao__icontains='CD4'))
        #
        for p in qs_pontuacaoitem:
            if p.limite_pontos:
                lista.extend(range(inicio, int(p.limite_pontos) + 1))
        return lista


class PontuacaoItem(models.ModelPlus):
    SEARCH_FIELDS = [
        'descricao',
    ]
    item = models.ForeignKeyPlus('progressao_docente.Item', verbose_name='Item', on_delete=models.CASCADE, null=True)
    descricao = models.TextField('Descrição', null=True, blank=True)
    pontos = models.DecimalFieldPlus('Pontos', max_digits=12, decimal_places=2)
    limite_pontos = models.DecimalFieldPlus('Limite de Pontos', max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = 'Pontuação'
        verbose_name_plural = 'Pontuações'

    def __str__(self):
        return self.get_descricao

    @property
    def get_descricao(self):
        txt_limite = ''
        if self.limite_pontos:
            txt_limite = ' com limite de ' + str(self.limite_pontos)
        if self.descricao:
            return f'{self.descricao} {txt_limite}'
        return f'pontos: {self.pontos!s}{txt_limite}'


class RecursoAvaliacao(models.ModelPlus):
    EM_REAVALIACAO = 1
    FINALIZADO = 2

    SITUACAO_RECURSO = ((EM_REAVALIACAO, 'Em Reavaliação'), (FINALIZADO, 'Finalizado'))

    avaliacao = models.ForeignKeyPlus('progressao_docente.Avaliacao', verbose_name='Avaliação', on_delete=models.CASCADE, null=True)
    texto_recurso = models.TextField(verbose_name='Texto do Recurso', max_length=5000, null=False)
    data_cadastro_recurso = models.DateTimeFieldPlus('Data de Cadastro do Recurso', null=False)
    #
    texto_conclusao_reavaliacao = models.TextField(verbose_name='Texto do Recurso', max_length=5000, null=True)
    data_conclusao_reavaliacao = models.DateTimeFieldPlus('Data de Conclusão da Reavaliação', null=True)
    situacao = models.IntegerFieldPlus('Situação', choices=SITUACAO_RECURSO, null=False)
    #
    rever_aceleracao = models.BooleanField('Rever Aceleração?', default=False)

    class Meta:
        verbose_name = 'Recurso de Avaliação'
        verbose_name_plural = 'Recursos de Avaliação'

    def __str__(self):
        return f'Recurso - {self.avaliacao}'


class RevisaoItem(models.ModelPlus):
    recurso_avaliacao = models.ForeignKeyPlus(RecursoAvaliacao, verbose_name='Recurso Avaliação')
    avaliacao_item = models.ForeignKeyPlus(AvaliacaoItem, verbose_name='Avaliação Item', on_delete=models.CASCADE, null=True)
    nota_questionada = models.CharFieldPlus('Nota Questinada')
    nota_reavaliada = models.CharFieldPlus('Nota Reavaliada')
    observacao = models.TextField('Observação', null=True, blank=True)
    data_cadastro = models.DateFieldPlus('Data de Cadastro', auto_now_add=True)
    data_reavaliacao = models.DateFieldPlus('Data da Reavaliação', null=True, blank=True)

    class Meta:
        verbose_name = 'Revisão de Item'
        verbose_name_plural = 'Revisões de Itens'

    def __str__(self):
        return f'Revisão :: {self.recurso_avaliacao}'


class ConfiguracaoProgressaoDocente(models.ModelPlus):
    SEARCH_FIELDS = ['tempo_preenchimento', 'tempo_avaliacao', 'texto_email_avaliadores', 'texto_email_preenchimento']

    descricao = models.CharFieldPlus('Descrição', null=True, blank=False)

    #
    # tempos
    tempo_preenchimento = models.PositiveIntegerFieldPlus(verbose_name='Tempo de Preenchimento do Processo', null=False)
    tempo_avaliacao = models.PositiveIntegerFieldPlus(verbose_name='Tempo de Avaliação do Processo', null=False)
    tempo_ciencia = models.PositiveIntegerFieldPlus(verbose_name='Tempo para ciência de resultado', null=True, blank=False)
    tempo_adicao_edicao = models.PositiveIntegerFieldPlus(
        verbose_name='Tempo para edições/adições de informações para reavaliação', null=True, blank=False
    )
    tempo_reavaliacao = models.PositiveIntegerFieldPlus(verbose_name='Tempo para reavaliação', null=True, blank=False)
    #
    # textos
    txt_preenchimento = HTMLField(
        verbose_name='Texto de preenchimento para o avaliado',
        help_text='Texto que será enviado para o docente em avaliação sobre o preenchimento do processo.',
        max_length=5000,
        null=True,
        blank=False,
    )
    txt_tempo_preenchimento_acabando = HTMLField(
        verbose_name='Texto de tempo no fim para preenchimento',
        help_text='Texto que será enviado para o docente o alertando sobre o fim do prazo para preenchimento da avaliação.',
        max_length=5000,
        null=True,
        blank=False,
    )
    #
    txt_avaliacao = HTMLField(
        verbose_name='Texto de avaliação para o avaliador',
        help_text='Texto que será enviado para o avaliador sobre a avaliação do processo.',
        max_length=5000,
        null=True,
        blank=False,
    )
    txt_tempo_avaliacao_acabando = HTMLField(
        verbose_name='Texto de tempo no fim para avaliação',
        help_text='Texto que será enviado para o avaliador o alertando sobre o fim do prazo da avaliação.',
        max_length=5000,
        null=True,
        blank=False,
    )
    #
    txt_alerta_ciencia = HTMLField(
        verbose_name='Texto de alerta para ciência de resultado',
        help_text='Texto que será enviado para o avaliado sobre a ciência de resultado em suas avaliações.',
        max_length=5000,
        null=True,
        blank=False,
    )
    #
    txt_alerta_edicao_adicao_reavaliacao = HTMLField(
        verbose_name='Texto de alerta para edição/adição de informações',
        help_text='Texto que será enviado para o avaliado para finalizar a edição e adição de arquivos para reavaliação.',
        max_length=5000,
        null=True,
        blank=False,
    )
    #
    txt_alerta_reavaliacao = HTMLField(
        verbose_name='Texto de alerta para reavaliação',
        help_text='Texto que será enviado para o avaliador sobre reavaliações que precisam ser realizadas.',
        max_length=5000,
        null=True,
        blank=False,
    )

    class Meta:
        verbose_name = 'Configuração de Progressão Docente'
        verbose_name_plural = 'Configurações de Progressão Docente'

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return reverse_lazy('progressao_docente:detalhar_configuracao', kwargs={'pk': self.pk})


class DocenteAProgredir(models.ModelPlus):
    SEARCH_FIELDS = ['avaliado__pessoa_fisica__nome', 'avaliado__matricula']
    #
    avaliado = models.ForeignKeyPlus('rh.Servidor', on_delete=models.CASCADE)
    data_inicio_contagem = models.DateFieldPlus('Data de Início da Contagem', null=False, blank=False)
    data_fim_contagem = models.DateFieldPlus('Data de Fim da Contagem', null=False, blank=False)
    nivel_atual = models.CharFieldPlus(
        'Nível Atual', null=True, blank=False
    )  # adicionado após a elaboração do modelo inicial, por isso null=True e blank=False
    proximo_nivel = models.CharFieldPlus(
        'Próximo Nível', null=True, blank=False
    )  # adicionado após a elaboração do modelo inicial, por isso null=True e blank=False
    eh_primeira_promocao = models.BooleanField('É a primeira promoção?', default=False)
    progressao_criada = models.BooleanField('Progressão Criada?', default=False)
    progressao_finalizada = models.BooleanField('Progressão Finalizada?', default=False)

    class Meta:
        verbose_name = 'Docente a Progredir'
        verbose_name_plural = 'Docente a Progredir'

    def __str__(self):
        return f'{self.avaliado} - {self.data_inicio_contagem.strftime("%d/%m/%Y")} a {self.data_fim_contagem.strftime("%d/%m/%Y")}'

    # consulta de inconsistências
    @classmethod
    def get_inconsistencias(cls) -> Iterable[dict[str, Any]]:
        """
        Retorna agrupamentos com possível inconsistência:
        múltiplos registros por (nível, servidor, UO),
        desconsiderando progressões finalizadas sem nota ou reprovadas
        e também progressões complementares.
        """
        FINALIZADO = ProgressaoDocente.FINALIZADO
        MINIMO = ProgressaoDocente.MINIMO_PONTUACAO_APROVACAO

        reprovadas = Q(progressaodocente__situacao=FINALIZADO) & (
            Q(progressaodocente__pontuacao_final_progressao__lt=MINIMO) | Q(progressaodocente__pontuacao_final_progressao__isnull=True)
        )

        return (
            cls.objects.exclude(reprovadas)
            .exclude(progressaodocente__progressao_complementar=True)
            .values(
                'nivel_atual',
                'avaliado__pessoa_fisica__nome',
                'avaliado__matricula',
                'avaliado__setor__uo__sigla',
            )
            .annotate(count=Count('id', distinct=True))
            .filter(count__gt=1)
            .order_by('avaliado__pessoa_fisica__nome')
        )

    @classmethod
    def remover_pendentes_fora_do_quadro(cls) -> int:
        """Apaga as linhas ainda sem progressão de quem deixou de ser docente ativo (redistribuído, exonerado, aposentado...).

        O cálculo diário só percorre ``Servidor.objects.docentes().ativos()``, então a linha criada antes da saída
        ficava na lista para sempre. Linhas com progressão criada ficam: o processo existe e o destino dele é do RH.
        Devolve quantas linhas foram removidas.
        """
        _, removidos = cls.objects.filter(progressao_criada=False).exclude(avaliado__in=Servidor.objects.docentes().ativos()).delete()
        return removidos.get(cls._meta.label, 0)

    #
    def _get_progressao_simulada(self, nivel_atual, proximo_nivel):
        pd = ProgressaoDocente()
        pd.data_inicio_periodo = self.data_inicio_contagem
        pd.avaliado = self.avaliado
        pd.nivel_atual = nivel_atual
        pd.proximo_nivel = proximo_nivel
        pd.calcular_data_fim()
        return pd

    #
    def _get_progressao(self):
        return self.progressaodocente_set.first()

    #
    def get_datafim_normal(self):
        return self.data_inicio_contagem + relativedelta(months=ProgressaoDocente.INTERSTICIO_AVALIATIVO_MESES, days=-1)

    #
    def get_absolute_url(self):
        return f'/progressao_docente/docenteaprogredir/{self.id}/'

    #
    def get_dias_restantes(self):
        hoje = date.today()
        dias = (self.data_fim_contagem - hoje).days
        if dias > 0:
            return dias
        return 0

    #
    @staticmethod
    def calcular_proximo_nivel(nivel_atual):
        parar = False
        nivel = nivel_atual
        #
        # se o nível atual do servidor for A1 (novo padrão) ele terá a promoção para o B1 (D-III-1)
        if nivel == 'A1':
            itens = list(ProgressaoDocente.NOVOS_NIVEIS_ENCADEADOS.items())
            _, valor = itens[1]
            return valor
        #
        for v in ProgressaoDocente.NOVOS_NIVEIS_ENCADEADOS.values():
            if parar:
                return v
            if v == nivel:
                parar = True
        return None
