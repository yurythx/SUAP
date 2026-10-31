import datetime
from datetime import date

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import Q

from comum.models import PrestadorServico, Vinculo
from djtools.db import models
from djtools.db.models import Count, ModelPlus
from djtools.utils import anonimizar_cpf
from edu.models import Aluno
from rh.models import Servidor


class Edital(ModelPlus):
    descricao = models.CharFieldPlus('Descrição', blank=False)
    # Período para inscrição de candidatos/chapa
    data_inscricao_inicio = models.DateTimeFieldPlus('Início das Inscrições', help_text='Período em que os candidatos podem se inscrever.')
    data_inscricao_fim = models.DateTimeFieldPlus('Fim das Inscrições')
    # Período de validação das inscrições
    data_validacao_inicio = models.DateTimeFieldPlus(
        'Início da Validação', help_text='Período de validação das candidaturas por parte dos Coordenadores.'
    )
    data_validacao_fim = models.DateTimeFieldPlus('Fim da Validação')
    # Período da campanha
    data_campanha_inicio = models.DateTimeFieldPlus(
        'Início da Campanha', help_text='Período em que os candidatos são tornados públicos na tela inicial.'
    )
    data_campanha_fim = models.DateTimeFieldPlus('Fim da Campanha')
    # Período de votação
    data_votacao_inicio = models.DateTimeFieldPlus('Início da Votação', help_text='Período em que usuários habilitados podem votar.')
    data_votacao_fim = models.DateTimeFieldPlus('Fim da Votação')
    # Período de homologação dos votos
    data_homologacao_inicio = models.DateTimeFieldPlus(
        'Início da Homologação', help_text='Período em que os coordenadores podem invalidar os votos em caso de descumprimento do edital.'
    )
    data_homologacao_fim = models.DateTimeFieldPlus('Fim da Homologação')
    # Período do resultado preliminar
    data_pre_resultado_inicio = models.DateTimeFieldPlus(
        'Início do Resultado Preliminar', null=True, blank=True, help_text='Período em que o resultado preliminar é exibido ao público.'
    )
    data_pre_resultado_fim = models.DateTimeFieldPlus('Fim do Resultado Preliminar', null=True, blank=True)
    # Data para publicação do resultado final
    data_resultado_final = models.DateTimeFieldPlus('Data para Resultado Final', help_text='O resultado final é exibido somente aos coordenadores.')
    vinculos_coordenadores = models.ManyToManyFieldPlus(
        'comum.Vinculo', related_name='vinculos_coordenadores_editais', verbose_name='Coordenador(es)'
    )
    # Permite voto branco e nulo
    permite_voto_branco_nulo = models.BooleanField(
        'Permite voto branco e nulo?',
        default=False,
        help_text='Marcando essa opção serão habilitados em todas as eleições a opção de voto branco e nulo.',
    )

    class Meta:
        verbose_name = 'Edital'
        verbose_name_plural = 'Editais'

    def clean(self):
        errors = {}
        if (self.data_inscricao_inicio or self.data_inscricao_fim) and self.data_inscricao_fim <= self.data_inscricao_inicio:
            errors['data_inscricao_inicio'] = ['A data final de inscrição deve ser maior que a data de início.']

        if (self.data_validacao_inicio or self.data_validacao_fim) and self.data_validacao_fim <= self.data_validacao_inicio:
            errors['data_validacao_inicio'] = ['A data final de validação deve ser maior que a data de início.']

        if (self.data_campanha_inicio or self.data_campanha_fim) and self.data_campanha_fim <= self.data_campanha_inicio:
            errors['data_campanha_inicio'] = ['A data final da campanha deve ser maior que a data de início.']

        if (self.data_votacao_inicio or self.data_votacao_fim) and self.data_votacao_fim <= self.data_votacao_inicio:
            errors['data_votacao_inicio'] = ['A data final de votação deve ser maior que a data de início.']

        if self.data_homologacao_inicio or self.data_homologacao_fim:
            if self.data_homologacao_inicio and self.data_homologacao_fim and self.data_homologacao_fim <= self.data_homologacao_inicio:
                errors['data_homologacao_inicio'] = ['A data final de homologação deve ser maior que a data de início.']
            if not self.data_homologacao_inicio:
                errors['data_homologacao_inicio'] = ['A data de início da homologação é obrigatória quando você definir uma data fim da homologação.']
            if not self.data_homologacao_fim:
                errors['data_homologacao_fim'] = ['A data fim de homologação é obrigatória quando você definir uma data de início da homologação.']

        # Falta validar as datas entre si
        # A sequencia seria:
        # inscricao < validacao < campanha < votacao < homologacao < pre_resultado < recurso < final
        if errors:
            raise ValidationError(errors)

    def eh_coordenador(self, vinculo):
        return self.vinculos_coordenadores.filter(id=vinculo.id).exists()

    def eh_periodo_inscricao(self):
        return self.data_inscricao_inicio <= datetime.datetime.now() <= self.data_inscricao_fim

    def eh_periodo_validacao(self):
        return self.data_validacao_inicio <= datetime.datetime.now() <= self.data_validacao_fim

    def eh_periodo_campanha(self):
        return self.data_campanha_inicio <= datetime.datetime.now() <= self.data_campanha_fim

    def eh_periodo_votacao(self):
        return self.data_votacao_inicio <= datetime.datetime.now() <= self.data_votacao_fim

    def eh_periodo_homologacao(self):
        return self.data_homologacao_inicio <= datetime.datetime.now() <= self.data_homologacao_fim

    def eh_periodo_resultado_preliminar(self):
        return bool(
            self.data_pre_resultado_inicio
            and self.data_pre_resultado_inicio <= datetime.datetime.now()
            and (
                (self.data_pre_resultado_fim and datetime.datetime.now() <= self.data_pre_resultado_fim)
                or (not self.data_pre_resultado_fim and self.data_homologacao_inicio and self.data_homologacao_inicio >= datetime.datetime.now())
            )
        )

    def eh_periodo_resultado_final(self):
        return self.data_resultado_final <= datetime.datetime.now()

    def pode_ver_resultado(self, vinculo):
        return self.eh_periodo_resultado_final() and (self.eh_coordenador(vinculo) or vinculo.user.is_superuser)


class Eleicao(ModelPlus):
    TIPO_INDIVIDUAL = 'Individual'
    TIPO_CHAPA = 'Chapa'
    TIPO_CHOICES = ((TIPO_INDIVIDUAL, TIPO_INDIVIDUAL), (TIPO_CHAPA, TIPO_CHAPA))

    tipo = models.CharFieldPlus('Tipo', choices=TIPO_CHOICES, blank=False)
    descricao = models.CharFieldPlus('Descrição')
    publico = models.ForeignKey('comum.Publico', verbose_name='Público', on_delete=models.CASCADE, null=True, blank=True)
    campi = models.ManyToManyField('rh.UnidadeOrganizacional', blank=True)
    pessoas_relacionadas_eleicao = models.ManyToManyFieldPlus(
        'rh.Servidor', blank=True, verbose_name='Servidores Relacionados à Eleição', related_name='pessoas_relacionadas_eleicao'
    )
    alunos_relacionados_eleicao = models.ManyToManyFieldPlus(
        'edu.Aluno', blank=True, verbose_name='Alunos Relacionadas à Eleição', related_name='alunos_relacionados_eleicao'
    )
    caracteres_campanha = models.PositiveIntegerField('Número de Caracteres para a Campanha', default=2000)
    caracteres_recurso = models.PositiveIntegerField('Número de Caracteres para Recurso', default=2000)
    edital = models.ForeignKeyPlus('eleicao.Edital', verbose_name='Edital', blank=False, on_delete=models.CASCADE)
    votacao_global = models.BooleanField(
        'Votação Global',
        default=False,
        help_text='Se marcado, permite votar em candidatos de qualquer campus.',
    )
    resultado_global = models.BooleanField(
        'Resultado Global',
        default=False,
        help_text='Se marcado, os votos serão apurados de forma unificada entre os campi, sem separação por campus.',
    )
    obs_voto = models.TextField('Observação para Votação', help_text='Esta observação será visível para o eleitor no momento da votação', blank=True)
    vinculo_publico_eleicao = models.ManyToManyFieldPlus(
        'comum.Vinculo', blank=True, verbose_name='Público da Eleição', related_name='publico_eleicao'
    )

    class Meta:
        ordering = ['-edital__data_resultado_final']
        verbose_name = 'Eleição'
        verbose_name_plural = 'Eleições'

    def __str__(self):
        return f'{self.descricao} ({self.edital})'

    def save(self, *args, **kargs):
        if self.pk:
            self.vinculo_publico_eleicao.set(self.get_publicos())
        super().save(*args, **kargs)

    def pode_inscrever(self, vinculo):
        return (
            self.edital.eh_periodo_inscricao()
            and self.eh_parte_publico(vinculo)
            and not self.candidato_set.filter(candidato_vinculo=vinculo).exists()
        )

    def pode_validar(self, vinculo):
        return self.edital.eh_periodo_validacao() and (self.edital.eh_coordenador(vinculo) or vinculo.user.is_superuser)

    def pode_votar(self, vinculo):
        return self.edital.eh_periodo_votacao() and self.eh_parte_publico(vinculo) and not Voto.get_por_eleicao_eleitor(self, vinculo)

    def pode_votar_em(self, vinculo, candidato):
        return self.pode_votar(vinculo) and self.get_candidatos_validos(vinculo).filter(id=candidato.id).exists()

    def pode_ver_resultado_preliminar(self, vinculo):
        return self.edital.eh_periodo_resultado_preliminar() and (
            self.eh_parte_publico(vinculo) or self.edital.eh_coordenador(vinculo) or vinculo.user.is_superuser
        )

    def pode_homologar(self, vinculo):
        return self.edital.eh_periodo_homologacao() and (self.edital.eh_coordenador(vinculo) or vinculo.user.is_superuser)

    def pode_ver_resultado_final(self, vinculo):
        return self.edital.eh_periodo_resultado_final() and (self.edital.eh_coordenador(vinculo) or vinculo.user.is_superuser)

    def get_candidatos_validos(self, vinculo):
        candidatos = self.candidato_set.filter(status=Candidato.STATUS_DEFERIDO)
        publico = self.vinculo_publico_eleicao
        if not self.votacao_global:
            # Eleitor somente poderá votar em candidato do seu campus
            # Eleitor aluno somente poderá votar em candidato aluno
            # Eleitor servidor ou prestador de serviço somente poderá votar em candidato servidor ou prestador de serviço
            campus_id = []
            sub_instance = vinculo.relacionamento
            if isinstance(sub_instance, Aluno):
                campus_id.append(sub_instance.curso_campus.diretoria.setor.uo_id)
            elif isinstance(sub_instance, PrestadorServico | Vinculo):
                campus_id.append(sub_instance.setor.uo_id)
            elif isinstance(sub_instance, Servidor):
                if sub_instance.campus_lotacao_siape:
                    campus_id.append(sub_instance.campus_lotacao_siape.equivalente_id)
                elif sub_instance.campus_exercicio_siape:
                    campus_id.append(sub_instance.campus_exercicio_siape.equivalente_id)
                elif sub_instance.campus:
                    campus_id.append(sub_instance.campus.equivalente_id)
            campi = self.campi.filter(id__in=campus_id)
            if isinstance(sub_instance, Aluno):
                filtro = Q(aluno_set__curso_campus__diretoria__setor__uo__id__in=campi)
            else:
                filtro = Q(setor__uo__id__in=campi)
            publico = publico.filter(filtro).distinct()

        return candidatos.filter(candidato_vinculo__id__in=publico.values_list('id', flat=True))

    def get_publicos(self):
        qs1 = list(self.pessoas_relacionadas_eleicao.values_list('vinculos__id', flat=True))
        qs2 = list(self.alunos_relacionados_eleicao.values_list('vinculos__id', flat=True))

        qs = Vinculo.objects.filter(id__in=qs1 + qs2).distinct()
        if self.publico:
            qs = qs | self.publico.get_queryset_vinculo(campi=self.campi.all()).distinct()
        return qs

    def eh_parte_publico(self, vinculo):
        return self.vinculo_publico_eleicao.filter(id=vinculo.id).exists()

    def obter_votos_validos(self):
        return self.voto_set.filter(valido=True)

    def obter_votos(self):
        return self.voto_set.all()

    def obter_candidatos_validos(self):
        return self.candidato_set.filter(status=Candidato.STATUS_DEFERIDO)

    def obter_candidatos(self):
        return self.candidato_set.all()

    @staticmethod
    def obter_qtd_votos_por_relacao(votos):
        return votos.aggregate(
            servidores=Count('id', filter=Q(eleitor__eh_servidor=True)),
            alunos=Count('id', filter=Q(eleitor__eh_aluno=True)),
            prestadores=Count('id', filter=Q(eleitor__eh_prestador=True)),
            usuarios_externos=Count('id', filter=Q(eleitor__eh_usuarioexterno=True)),
            docentes=Count('id', filter=Q(eleitor__eh_docente=True)),
            tecnicos_adm=Count('id', filter=Q(eleitor__eh_tecnico_administrativo=True)),
        )

    def obter_resultados_por_campus(self):
        votos = self.obter_votos_validos()
        candidatos = self.obter_candidatos_validos().order_by('candidato_vinculo__pessoa__nome')
        campi = self.campi.all()
        for campus in campi:
            if self.edital.id == 43 and campus.id == 14:
                continue

            campus.candidatos = []
            qtd_votos_geral = votos.filter(campus=campus).count()
            # A exibição do resultado é por campus mas a votação é global
            if self.votacao_global:
                qtd_votos_geral = votos.count()
            else:
                # A exibição do resultado e votação é por campus
                if self.edital.id == 43 and campus.id == 1:
                    qtd_votos_geral = votos.filter(campus__in=[1, 14]).count()
                else:
                    qtd_votos_geral = votos.filter(campus=campus).count()

            if self.edital.id == 43 and campus.id == 1:
                query = Q(campus__in=[1, 14])
            else:
                query = Q(campus=campus)
            for candidato in candidatos.filter(query):
                qtd_votos = 0
                percentual_votos = 0
                votos_por_candidato = candidato.voto_set.filter(eleicao=self, valido=True).distinct()
                if qtd_votos_geral:
                    qtd_votos = votos_por_candidato.count()
                    # Calculo da porcentagem utilizando 4 casas decimais
                    percentual_votos = round(float(qtd_votos) / qtd_votos_geral * 100, 4)
                    # arredondamento para o inteiro mais próximo (0,5 = 1)
                    if self.edital.id != 43:
                        percentual_votos = round(percentual_votos)

                candidato.qtd_votos = qtd_votos
                candidato.dict_votos = Eleicao.obter_qtd_votos_por_relacao(votos_por_candidato)
                candidato.percentual_votos = percentual_votos
                if self.edital.id != 43:
                    candidato.percentual_votos_label = f'{percentual_votos:d}%'
                else:
                    candidato.percentual_votos_label = f'{percentual_votos}%'
                campus.candidatos.append(candidato)

            # Caso tenha empate ordena os candidatos pela idade
            campus.candidatos = sorted(campus.candidatos, key=lambda c: c.get_idade(), reverse=True)
            # Caso tenha empate ordena os candidatos pelo tempo na instituição
            campus.candidatos = sorted(campus.candidatos, key=lambda c: c.get_tempo_na_instituicao().days, reverse=True)
            # ordenando os candidatos pelo percentual de votos em ordem decrescente
            campus.candidatos = sorted(campus.candidatos, key=lambda c: c.percentual_votos, reverse=True)

        return campi

    def obter_resultados(self):
        votos = self.obter_votos_validos()
        candidatos = self.obter_candidatos_validos().order_by('candidato_vinculo__pessoa__nome')
        qtd_votos_geral = votos.count()
        for candidato in candidatos:
            votos_por_candidato = None
            # A exibição do resultado e a votação é global
            if self.votacao_global:
                votos_por_candidato = candidato.voto_set.filter(eleicao=self, valido=True).distinct()
                qtd_votos = votos_por_candidato.count()
            else:
                # A exibição do resultado é global mas a votação é por campus
                votos_por_candidato = candidato.voto_set.filter(eleicao=self, valido=True, campus=candidato.campus).distinct()
                qtd_votos = votos_por_candidato.count()

            percentual_votos = 0
            if qtd_votos_geral:
                # Calculo da porcentagem utilizando 4 casas decimais
                percentual_votos = round(float(qtd_votos) / qtd_votos_geral * 100, 4)
                # arredondamento para o inteiro mais próximo (0,5 = 1)
                percentual_votos = round(percentual_votos)

            candidato.qtd_votos = qtd_votos
            candidato.dict_votos = Eleicao.obter_qtd_votos_por_relacao(votos_por_candidato)
            candidato.percentual_votos = percentual_votos
            candidato.percentual_votos_label = f'{percentual_votos:d}%'

        # Caso tenha empate ordena os candidatos pela idade
        candidatos = sorted(candidatos, key=lambda c: c.get_idade(), reverse=True)
        # Caso tenha empate ordena os candidatos pelo tempo na instituição
        candidatos = sorted(candidatos, key=lambda c: c.get_tempo_na_instituicao().days, reverse=True)
        # ordenando os candidatos pelo percentual de votos em ordem decrescente
        candidatos = sorted(candidatos, key=lambda c: c.percentual_votos, reverse=True)
        return candidatos

    def obter_brancos_nulos(self):
        votos = self.obter_votos_validos()
        qtd_votos_geral = votos.count()
        percentual_votos_brancos = percentual_votos_nulos = 0
        # A exibição do resultado e a votação é global
        qtd_votos_branco = Voto.objects.filter(eleicao=self, valido=True, eh_voto_branco=True).distinct().count()
        qtd_votos_nulo = Voto.objects.filter(eleicao=self, valido=True, eh_voto_nulo=True).distinct().count()

        if qtd_votos_geral:
            # Calculo da porcentagem utilizando 4 casas decimais
            percentual_votos_brancos = round(float(qtd_votos_branco) / qtd_votos_geral * 100, 4)
            # arredondamento para o inteiro mais próximo (0,5 = 1)
            percentual_votos_brancos = round(percentual_votos_brancos)

            percentual_votos_nulos = round(float(qtd_votos_nulo) / qtd_votos_geral * 100, 4)
            # arredondamento para o inteiro mais próximo (0,5 = 1)
            percentual_votos_nulos = round(percentual_votos_nulos)
        dicionario = {
            'Geral': {
                'qtd_votos_brancos': qtd_votos_branco,
                'qtd_votos_nulos': qtd_votos_nulo,
                'percentual_votos_brancos': percentual_votos_brancos,
                'percentual_votos_nulos': percentual_votos_nulos,
                'percentual_votos_brancos_label': f'{percentual_votos_brancos:d}%',
                'percentual_votos_nulos_label': f'{percentual_votos_nulos:d}%',
            }
        }

        if not self.votacao_global:
            campi = self.campi.all()
            for campus in campi:
                qtd_votos_branco_campus = Voto.objects.filter(eleicao=self, valido=True, eh_voto_branco=True, campus=campus).count()
                qtd_votos_nulo_campus = Voto.objects.filter(eleicao=self, valido=True, eh_voto_nulo=True, campus=campus).count()
                percentual_votos_brancos_campus = percentual_votos_nulos_campus = 0
                if qtd_votos_geral:
                    # Calculo da porcentagem utilizando 4 casas decimais
                    percentual_votos_brancos_campus = round(float(qtd_votos_branco_campus) / qtd_votos_geral * 100, 4)
                    # arredondamento para o inteiro mais próximo (0,5 = 1)
                    percentual_votos_brancos_campus = round(percentual_votos_brancos_campus)

                    percentual_votos_nulos_campus = round(float(qtd_votos_nulo_campus) / qtd_votos_geral * 100, 4)
                    # arredondamento para o inteiro mais próximo (0,5 = 1)
                    percentual_votos_nulos_campus = round(percentual_votos_nulos_campus)

                dicionario[f'{campus.sigla}'] = {
                    'qtd_votos_brancos': qtd_votos_branco_campus,
                    'qtd_votos_nulos': qtd_votos_nulo_campus,
                    'percentual_votos_brancos': percentual_votos_brancos_campus,
                    'percentual_votos_nulos': percentual_votos_nulos_campus,
                    'percentual_votos_brancos_label': f'{percentual_votos_brancos_campus:d}%',
                    'percentual_votos_nulos_label': f'{percentual_votos_nulos_campus:d}%',
                }

        return dicionario

    @staticmethod
    def get_abertas(usuario=None):
        hoje = datetime.datetime.now()
        eleicoes_abertas = Eleicao.objects.filter(edital__data_inscricao_inicio__lte=hoje, edital__data_resultado_final__gte=hoje)
        if usuario:
            vinculo = usuario.get_vinculo()
            eleicoes_abertas = eleicoes_abertas.filter(vinculo_publico_eleicao__id=vinculo.id)
        return eleicoes_abertas

    @staticmethod
    def get_inscricao_aberta(usuario=None):
        hoje = datetime.datetime.now()
        eleicoes_inscricao_aberta = Eleicao.objects.filter(edital__data_inscricao_inicio__lte=hoje, edital__data_inscricao_fim__gte=hoje)
        if usuario:
            vinculo = usuario.get_vinculo()
            eleicoes_inscricao_aberta = eleicoes_inscricao_aberta.filter(vinculo_publico_eleicao__id=vinculo.id).exclude(
                candidato__candidato_vinculo_id=vinculo.id
            )
        return eleicoes_inscricao_aberta

    @staticmethod
    def get_em_campanha(usuario=None):
        hoje = datetime.datetime.now()
        eleicoes_em_campanha = Eleicao.objects.filter(edital__data_campanha_inicio__lte=hoje, edital__data_campanha_fim__gte=hoje)
        if usuario:
            vinculo = usuario.get_vinculo()
            eleicoes_em_campanha = eleicoes_em_campanha.filter(vinculo_publico_eleicao__id=vinculo.id)
        return eleicoes_em_campanha

    @staticmethod
    def get_em_votacao(usuario):
        vinculo = usuario.get_vinculo()
        hoje = datetime.datetime.now()
        eleicoes_em_votacao = (
            Eleicao.objects.filter(edital__data_votacao_inicio__lte=hoje, edital__data_votacao_fim__gte=hoje, vinculo_publico_eleicao__id=vinculo.id)
            .filter(vinculo_publico_eleicao__id=vinculo.id)
            .distinct()
        )
        # for eleicao_em_votacao in todas_eleicoes_em_votacao:
        #     if eleicao_em_votacao.vinculo_publico_eleicao.filter(id=vinculo.id).exists():
        #         eleicoes_em_votacao.append(eleicao_em_votacao)

        return eleicoes_em_votacao


class Chapa(ModelPlus):
    STATUS_DEFERIDO = 'Deferido'
    STATUS_INDEFERIDO = 'Indeferido'
    STATUS_PENDENTE = 'Pendente'
    STATUS_CHOICES = ((STATUS_DEFERIDO, STATUS_DEFERIDO), (STATUS_INDEFERIDO, STATUS_INDEFERIDO), (STATUS_PENDENTE, STATUS_PENDENTE))

    eleicao = models.ForeignKeyPlus('eleicao.Eleicao', verbose_name='Eleição', on_delete=models.CASCADE)
    nome = models.CharFieldPlus('Nome')
    descricao = models.TextField('Descrição')
    status = models.CharFieldPlus('Parecer', choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    justificativa_parecer = models.TextField('Justificativa do Parecer', blank=True)

    class Meta:
        unique_together = ('eleicao', 'nome')
        verbose_name = 'Chapa'
        verbose_name_plural = 'Chapas'
        permissions = (('validar_chapa', 'Pode validar chapa'),)

    def clean(self):
        errors = {}

        if len(self.descricao) > self.eleicao.caracteres_campanha:
            errors['descricao'] = ['O número de caracteres é maior que o permitido.']

        if errors:
            raise ValidationError(errors)

    def pode_ser_validado(self):
        return self.status == Candidato.STATUS_PENDENTE

    def __str__(self):
        return self.nome

    def get_numero_votos(self):
        return self.voto_set.filter(valido=True).count()


class Candidato(ModelPlus):
    STATUS_DEFERIDO = 'Deferido'
    STATUS_INDEFERIDO = 'Indeferido'
    STATUS_PENDENTE = 'Pendente'
    STATUS_NAO_APLICADO = 'Não aplicado'
    STATUS_CHOICES = (
        (STATUS_DEFERIDO, STATUS_DEFERIDO),
        (STATUS_INDEFERIDO, STATUS_INDEFERIDO),
        (STATUS_PENDENTE, STATUS_PENDENTE),
        (STATUS_NAO_APLICADO, STATUS_NAO_APLICADO),
    )

    eleicao = models.ForeignKeyPlus('eleicao.Eleicao', verbose_name='Eleição', null=True, on_delete=models.CASCADE)
    chapa = models.ForeignKeyPlus('eleicao.Chapa', null=True, on_delete=models.CASCADE)
    candidato_vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Candidato')
    descricao = models.TextField('Texto de Apresentação', blank=True)
    status = models.CharFieldPlus('Parecer', choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    justificativa_parecer = models.TextField('Justificativa do Parecer', blank=True)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus do Candidato no Momento da Inscrição', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('eleicao', 'candidato_vinculo')
        verbose_name = 'Candidato'
        verbose_name_plural = 'Candidatos'
        permissions = (('validar_candidato', 'Pode validar candidato'),)

    def __str__(self):
        return self.candidato_vinculo.pessoa.nome

    def clean(self):
        errors = {}

        if (self.eleicao and self.chapa) or (self.eleicao is None and self.chapa is None):
            errors[NON_FIELD_ERRORS] = ['Não é possível associar um candidato a uma chapa e a uma eleição ao mesmo tempo.']
        else:
            import re

            qtd_caracteres = len(re.sub('[\r\n]', '', self.descricao.strip()))
            if self.eleicao:
                if qtd_caracteres > 0 and self.eleicao.tipo == Eleicao.TIPO_CHAPA:
                    errors['descricao'] = ['A descrição não se aplica a esse tipo de eleição.']
                if qtd_caracteres > self.eleicao.caracteres_campanha:
                    errors['descricao'] = ['O número de caracteres é maior que o permitido.']
                if (
                    self.candidato_vinculo_id
                    and not self.eleicao.eh_parte_publico(self.candidato_vinculo)
                    and self.status == Candidato.STATUS_DEFERIDO
                ):
                    errors['candidato_vinculo'] = ['O candidato não faz parte do público.']
            else:
                if qtd_caracteres > 0 and self.chapa.eleicao.tipo == Eleicao.TIPO_CHAPA:
                    errors['descricao'] = ['A descrição não se aplica a esse tipo de eleição.']

                if qtd_caracteres > self.chapa.eleicao.caracteres_campanha:
                    errors['descricao'] = ['O número de caracteres é maior que o permitido.']

        if errors:
            raise ValidationError(errors)

        return super().clean()

    def save(self, *args, **kwargs):
        self.candidato_id = self.candidato_vinculo.pessoa_id
        if not self.campus_id:
            self.campus = self.candidato_vinculo.relacionamento.setor.uo
        super().save(*args, **kwargs)

    def get_numero_votos(self):
        return self.voto_set.filter(valido=True).count()

    def pode_ser_validado(self):
        eleicao = self.eleicao
        if self.chapa:
            eleicao = self.chapa.eleicao

        return self.status == Candidato.STATUS_PENDENTE and eleicao.eh_parte_publico(self.candidato_vinculo)

    def get_foto(self):
        vinculo = self.candidato_vinculo
        return f'<img src="{vinculo.get_foto_75x100_url()}" alt="Foto de {vinculo.relacionamento.pessoa_fisica.nome_usual}"/>'

    def get_info_principal(self):
        subinstance = self.candidato_vinculo.relacionamento
        perfil = subinstance.__class__._meta.verbose_name
        return f"""
        <div class="photo-circle sm">
            {self.get_foto()}
        </div>
        <h4><strong>{subinstance.pessoa_fisica.nome}</strong> ({perfil})</h4>
        """

    def get_info_auxilar(self):
        subinstance = self.candidato_vinculo.relacionamento
        out = []
        if isinstance(subinstance, Aluno):
            out.append(f'<dl><dt>Matrícula:</dt><dd>{subinstance.matricula}</dd></dl>')
            out.append(f'<dl><dt>Curso:</dt><dd>{subinstance.curso_campus}</dd></dl>')
            out.append(f'<dl><dt>Situação:</dt><dd>{subinstance.situacao}</dd></dl>')
            out.append(f'<dl><dt>Período Letivo:</dt><dd>{subinstance.periodo_letivo}</dd></dl>')
            out.append(f'<dl><dt>Ano Letivo:</dt><dd>{subinstance.ano_letivo}</dd></dl>')

        elif isinstance(subinstance, Servidor):
            out.append(f'<dl><dt>Matrícula:</dt><dd>{subinstance.matricula}</dd></dl>')
            if subinstance.setor:
                telefones_institucionais = ', '.join(subinstance.setor.setortelefone_set.values_list('numero', flat=True))
                if telefones_institucionais:
                    out.append(f'<dl><dt>Telefones institucionais:</dt><dd>{telefones_institucionais}</dd></dl>')
            if subinstance.email_notificacao:
                out.append(f'<dl><dt>E-mail:</dt><dd><a href="mailto:{subinstance.email_notificacao}">{subinstance.email_notificacao}</a></dd></dl>')
            if subinstance.cargo_emprego:
                out.append(f'<dl><dt>Cargo:</dt><dd>{subinstance.cargo_emprego.nome}</dd></dl>')
            if subinstance.funcao:
                out.append(f'<dl><dt>Atividade:</dt><dd>{subinstance.atividade.nome}</dd></dl>')
            if subinstance.setor:
                out.append(f'<dl><dt>Setor SUAP:</dt><dd>{subinstance.setor.sigla}</dd></dl>')

        elif isinstance(subinstance, PrestadorServico):
            out.append(f'<dl><dt>CPF:</dt><dd>{anonimizar_cpf(subinstance.pessoa_fisica.cpf)}</dd></dl>')
            out.append(f'<dl><dt>E-mail:</dt><dd><a href="mailto:{subinstance.email_pessoal}">{subinstance.email_pessoal}</a></dd></dl>')
            if subinstance.setor:
                out.append(f'<dl><dt>Setor:</dt><dd>{subinstance.setor.sigla}</dd></dl>')

        return ''.join(out)

    def get_tempo_na_instituicao(self):
        subinstance = self.candidato_vinculo.relacionamento
        if isinstance(subinstance, Aluno):
            return date.today() - subinstance.data_matricula.date()

        elif isinstance(subinstance, Servidor):
            return subinstance.tempo_servico_na_instituicao_via_pca()

        elif isinstance(subinstance, PrestadorServico):
            pass

    def get_idade(self):
        return self.candidato_vinculo.relacionamento.pessoa_fisica.idade


class VotosValidosManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(valido=True)


class Voto(ModelPlus):
    eleicao = models.ForeignKeyPlus('eleicao.Eleicao', verbose_name='Eleição', null=True, on_delete=models.CASCADE)
    chapa = models.ForeignKeyPlus('eleicao.Chapa', null=True, on_delete=models.CASCADE)
    candidato = models.ForeignKeyPlus('eleicao.Candidato', null=True, on_delete=models.CASCADE)
    eleitor = models.CurrentUserField()
    data_voto = models.DateTimeFieldPlus('Data do Voto', auto_now_add=True)
    ip = models.GenericIPAddressField('IP da Origem do Voto')
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus do Eleitor no Momento do Voto', on_delete=models.CASCADE)
    hash = models.CharFieldPlus('Hash', blank=True)
    string_hash = models.TextField('String formadora do hash', blank=True)
    valido = models.BooleanField('Ativo', default=True)
    justificativa_avaliacao = models.TextField('Justificativa da Avaliação', blank=True)
    eh_voto_branco = models.BooleanField('Voto branco?', default=False)
    eh_voto_nulo = models.BooleanField('Voto nulo?', default=False)

    objects = models.Manager()
    validos = VotosValidosManager()

    class Meta:
        verbose_name = 'Voto'
        verbose_name_plural = 'Votos'
        permissions = (('validar_voto', 'Pode validar voto'),)

    def clean(self):
        errors = {}

        if self.chapa and self.candidato:
            errors[NON_FIELD_ERRORS] = ['Voto inválido. Não é possível vorar em uma chapa e em um candidato ao mesmo tempo.']

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        if self.chapa:
            return self.chapa
        elif self.candidato:
            return self.candidato.candidato_vinculo.pessoa.nome
        else:
            return 'Branco' if self.eh_voto_branco else 'Nulo'

    @staticmethod
    def get_por_eleicao_eleitor(eleicao, vinculo):
        if Voto.objects.filter(eleicao=eleicao, eleitor__vinculo=vinculo).exists():
            return Voto.objects.filter(eleicao=eleicao, eleitor__vinculo=vinculo).latest('id')

        return None

    def get_foto_eleitor(self) -> str:
        vinculo = self.eleitor.get_vinculo()
        return f'<img src="{vinculo.get_foto_75x100_url()}" alt="Foto de {self.eleitor.get_profile().nome_usual}" />'

    def get_info_principal_eleitor(self):
        subinstance = self.eleitor.get_relacionamento()
        perfil = subinstance.__class__._meta.verbose_name
        if isinstance(subinstance, Aluno):
            out = f"""
                    <dl>
                        <dt class="hidden">Nome:</dt><dd class="negrito">{subinstance.pessoa_fisica.nome}</dd>
                        <dt class="hidden">Perfil:</dt><dd>{perfil}</dd>
                        <dt>Matrícula:</dt><dd>{subinstance.matricula}</dd>
                        <dt>Curso:</dt><dd>{subinstance.curso_campus}</dd>
                        <dt>Situação:</dt><dd>{subinstance.situacao}</dd>
                    </dl>
                """

        elif isinstance(subinstance, Servidor):
            show_telefones, show_email = '', ''
            if subinstance.setor:
                telefones_institucionais = ', '.join(subinstance.setor.setortelefone_set.values_list('numero', flat=True))
                if telefones_institucionais:
                    show_telefones = f'<dt>Telefones institucionais:</dt><dd>{telefones_institucionais}</dd>'
            if subinstance.email_notificacao:
                show_email = f'<a href="mailto:{subinstance.email_notificacao}">{subinstance.email_notificacao}</a>'
            out = f"""
            <dl>
                <dt class="hidden">Nome:</dt><dd class="negrito">{subinstance.pessoa_fisica.nome}</dd>
                <dt class="hidden">Perfil:</dt><dd>{perfil}</dd>
                <dt class="hidden">E-mail:</dt><dd>{show_email} </dd>
                <dt>Matrícula:</dt><dd>{subinstance.matricula}</dd>
                {show_telefones}
            </dl>
            """

        else:
            out = f"""
            <dl>
                <dt class="hidden">Nome:</dt><dd class="negrito">{subinstance.pessoa_fisica.nome}</dd>
                <dt class="hidden">Perfil:</dt><dd>{perfil}</dd>
                <dt>CPF:</dt><dd>{anonimizar_cpf(subinstance.pessoa_fisica.cpf)}</dd>
                <dt class="hidden">E-mail:</dt><dd><a href="mailto:{subinstance.email_pessoal}">{subinstance.email_pessoal}</a></dd>
            </dl>
            """
        return out

    def get_info_auxilar_eleitor(self):
        subinstance = self.eleitor.get_relacionamento()
        out = ['<dl>']
        if isinstance(subinstance, Aluno):
            out.append(f'<dt>Período Letivo:</dt><dd>{subinstance.periodo_letivo}</dd>')
            out.append(f'<dt>Ano Letivo:</dt><dd>{subinstance.ano_letivo}</dd>')

        elif isinstance(subinstance, Servidor):
            if subinstance.cargo_emprego:
                out.append(f'<dt>Cargo:</dt><dd>{subinstance.cargo_emprego.nome}</dd>')
            if subinstance.funcao:
                out.append(f'<dt>Atividade:</dt><dd>{subinstance.atividade.nome}</dd>')
            if subinstance.setor:
                out.append(f'<dt>Setor SUAP:</dt><dd>{subinstance.setor.sigla}</dd>')

        elif isinstance(subinstance, PrestadorServico):
            if subinstance.setor:
                out.append(f'<dt>Setor:</dt><dd>{subinstance.setor.sigla}</dd>')

        out.append('</dl>')
        return ''.join(out)
