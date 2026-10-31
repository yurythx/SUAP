import datetime
import hashlib
import io

import sentry_sdk
from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import FileExtensionValidator
from django.db import transaction

from comum.utils import tl
from djtools.db import models
from djtools.templatetags.filters import format_
from djtools.utils import render_to_string, to_ascii
from remanejamento.utils import ajustar_sigla_campus_lotacao, obter_campos_alterados, tempo_servico_no_cargo_em_dias
from rh.models import AfastamentoSiape, Servidor, ServidorAfastamento, UnidadeOrganizacional


class Edital(models.ModelPlus):
    DOCENTE = 'docente'
    TAE = 'tae'
    CATEGORIA_CHOICES = (
        (DOCENTE, 'Docente'),
        (TAE, 'Técnico-Administrativo em Educação'),
    )

    titulo = models.CharField('Título', max_length=255)
    descricao = models.TextField('Descrição')
    url = models.URLField(
        verbose_name='Link para mais informações',
        null=True,
        blank=True,
    )
    campus = models.ManyToManyField(
        'rh.UnidadeOrganizacional', verbose_name='Campus', blank=True, help_text='Informe os campi participantes desta Remoção Interna.'
    )
    cargos = models.ManyToManyField('rh.cargoemprego', verbose_name='Cargos', help_text='Servidores destes cargos poderão se inscrever neste edital.')
    coordenadores = models.ManyToManyField(
        'comum.User', verbose_name='Coordenadores', blank=True, help_text='Os coordenadores poderão acompanhar as inscrições deste edital.'
    )
    tem_anexo = models.BooleanField(
        default=False, verbose_name='Permite anexo?', help_text='Indica que deverá ser anexado um arquivo no formulário de inscrição.'
    )
    chave_hash = models.CharField(
        max_length=128, help_text='Irá compor a chave de autenticidade da inscrição.<br/> Em nenhuma hipótese um candidato pode ver este campo.'
    )

    permite_recursos_contra_edital = models.BooleanField(
        default=False,
        verbose_name='Permite recursos contra o edital?',
        help_text='Indica se será permitido os servidores cadastrem recursos questionando informações publicadas no Edital.',
    )
    categoria = models.CharFieldPlus(verbose_name='Categoria', choices=CATEGORIA_CHOICES, null=True, blank=False, max_length=20)
    inicio_recursos_edital = models.DateTimeFieldPlus(verbose_name='Início dos Recursos ao Edital', null=True, blank=True)
    fim_recursos_edital = models.DateTimeFieldPlus(verbose_name='Fim dos Recursos ao Edital', null=True, blank=True)
    resultado_recursos_edital = models.DateTimeFieldPlus(verbose_name='Resultado dos Recursos ao Edital', null=True, blank=True)

    inicio_inscricoes = models.DateTimeFieldPlus(verbose_name='Início das inscrições')
    fim_inscricoes = models.DateTimeFieldPlus(verbose_name='Fim das inscrições')

    inicio_desistencias = models.DateTimeFieldPlus(verbose_name='Início da Desistência do edital', null=True, blank=True)
    fim_desistencias = models.DateTimeFieldPlus(verbose_name='Fim da desistência do edital', null=True, blank=True)

    inicio_recursos = models.DateTimeFieldPlus(verbose_name='Início dos recursos do resultado', null=True, blank=True)
    fim_recursos = models.DateTimeFieldPlus(verbose_name='Fim dos recursos do resultado', null=True, blank=True)
    resultado_recursos = models.DateTimeFieldPlus(verbose_name='Resultado dos recursos ao resultado', null=True, blank=True)

    # Documento - Edital de Abertura da Remoção
    edital_documentotexto = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        null=True,
        on_delete=models.PROTECT,
        related_name='editais_remocao_set',
        verbose_name='Edital da Remoção Interna - Documento Eletrônico',
    )

    # Documentos / Resultados

    # Parcial
    data_resultado_parcial = models.DateTimeFieldPlus(verbose_name='Resultado Parcial', null=True, blank=True)
    resultado_parcial_documentotexto = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        null=True,
        on_delete=models.PROTECT,
        related_name='resultados_parciais_remocao_set',
        verbose_name='Resultado Parcial - Documento Eletrônico',
    )

    # Resultado Final
    inicio_resultados = models.DateTimeFieldPlus(verbose_name='Resultado Final')
    resultado_final_documentotexto = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        null=True,
        on_delete=models.PROTECT,
        related_name='resultados_finais_remocao_set',
        verbose_name='Resultado Final - Documento Eletrônico',
    )

    # Homologação do Resultado Parcial
    data_homologacao_resultado = models.DateTimeFieldPlus(verbose_name='Homologação do Resultado Final', null=True, blank=False)
    resultado_final_homologacao_documentotexto = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        null=True,
        on_delete=models.PROTECT,
        related_name='resultados_finais_homologacoes_remocao_set',
        verbose_name='Homologação do Resultado Final - Documento Eletrônico',
    )

    inicio_avaliacoes = models.DateTimeFieldPlus(verbose_name='Início das avaliações', null=True, blank=True)  # Deprecated
    fim_avaliacoes = models.DateTimeFieldPlus(verbose_name='Fim das avaliações', null=True, blank=True)  # Deprecated

    # Permitir múltiplas inscrições (somente para edital do tipo Docente)
    servidores_permitidos_multiplas_inscricoes = models.ManyToManyField(
        'comum.Vinculo',
        verbose_name='Servidores que podem realizar múltiplas inscrições',
        blank=True,
        help_text='Inserir os servidores que poderão realizar múltiplas inscrições neste edital.',
        limit_choices_to={'tipo_relacionamento__model': 'servidor'},
    )

    class Meta:
        verbose_name = 'Edital'
        verbose_name_plural = 'Editais'

    def __str__(self):
        return self.titulo

    @classmethod
    def get_em_periodo_de_inscricao(cls):
        agora = datetime.datetime.now()
        return cls.objects.filter(inicio_inscricoes__lte=agora, fim_inscricoes__gte=agora)

    @classmethod
    def get_em_periodo_de_recurso(cls):
        agora = datetime.datetime.now()
        return cls.objects.filter(inicio_recursos__lte=agora, fim_recursos__gte=agora)

    @classmethod
    def get_em_periodo_de_recurso_edital(cls):
        agora = datetime.datetime.now()
        return cls.objects.filter(inicio_recursos_edital__lte=agora, fim_recursos_edital__gte=agora)

    @classmethod
    def get_em_periodo_de_inscricao_servidor(cls, servidor):
        if not servidor.cargo_emprego:
            return cls.objects.none()

        editais_em_periodo_inscricao = cls.get_em_periodo_de_inscricao()
        if servidor.cargo_emprego_area:
            area_do_servidor_contemplada = editais_em_periodo_inscricao.filter(
                vagaedital__cargo_emprego_area__id=servidor.cargo_emprego_area.id
            ).distinct('id')
            areacorrelata_do_servidor_contemplada = editais_em_periodo_inscricao.filter(
                vagaedital__areas_correlatas__id=servidor.cargo_emprego_area.id
            ).distinct('id')
            return area_do_servidor_contemplada.union(areacorrelata_do_servidor_contemplada)

        # Para Editais de Remoção Interna Docente verifica se disciplina de ingresso está dentre configuradas no edital
        for edital in editais_em_periodo_inscricao:
            Professor = apps.get_model('edu', 'Professor')
            professor = Professor.objects.filter(vinculo=servidor.get_vinculo()).first()
            if edital.eh_edital_remocao_docente() and professor and professor.disciplina:
                disciplinas_edital = editais_em_periodo_inscricao.filter(vagaedital__disciplina__id=professor.disciplina.id).distinct('id')
                disciplinas_correlatas_edital = editais_em_periodo_inscricao.filter(
                    vagaedital__disciplinas_correlatas__id=professor.disciplina.id
                ).distinct('id')
                return disciplinas_edital.union(disciplinas_correlatas_edital)

        # TODO: Disciplinas equivalentes - Como buscar as disciplinas equivalentes?
        return cls.get_em_periodo_de_inscricao().filter(cargos=servidor.cargo_emprego)

    @classmethod
    def get_em_periodo_recurso_edital_servidor(cls, servidor):
        if not servidor.cargo_emprego:
            cls.objects.none()
        return cls.get_em_periodo_de_recurso_edital().filter(cargos=servidor.cargo_emprego)

    @classmethod
    def get_em_periodo_de_recurso_servidor(cls, servidor):
        if not servidor.cargo_emprego:
            return cls.objects.none()
        return cls.get_em_periodo_de_recurso().filter(cargos=servidor.cargo_emprego)

    def is_em_periodo_aguardando_inicio_inscricao(self):
        """
        Edital foi publicado e ainda não foi iníciado o periodo de incrição
        """
        if self.inicio_recursos_edital and self.inicio_inscricoes:
            return self.inicio_recursos_edital <= datetime.datetime.now() <= self.inicio_inscricoes
        return False

    def is_em_periodo_de_inscricao(self):
        return self.inicio_inscricoes <= datetime.datetime.now() <= self.fim_inscricoes

    def is_em_periodo_de_processamento_resultado(self):
        if self.fim_inscricoes and self.inicio_recursos:
            return self.fim_inscricoes <= datetime.datetime.now() <= self.inicio_recursos
        return False

    def is_em_periodo_de_avaliacao(self):
        if self.inicio_avaliacoes and self.fim_avaliacoes:
            return self.inicio_avaliacoes <= datetime.datetime.now() <= self.fim_avaliacoes
        return False

    def is_em_periodo_de_recurso_edital(self):
        """
        Edital foi publicado e está em período de recursos
        """
        if self.inicio_recursos_edital and self.fim_recursos_edital:
            return self.inicio_recursos_edital <= datetime.datetime.now() <= self.fim_recursos_edital
        return False

    def is_em_periodo_de_recursos(self):
        if self.inicio_recursos and self.fim_recursos:
            return self.inicio_recursos <= datetime.datetime.now() <= self.fim_recursos
        return False

    def is_em_periodo_de_inscricao_servidor(self, servidor):
        em_periodo_inscricao_e_cargo_contemplado = self.is_em_periodo_de_inscricao() and self.cargos.filter(pk=servidor.cargo_emprego.pk).exists()
        if servidor.cargo_emprego_area:
            area_do_servidor_contemplada = servidor.cargo_emprego_area.id in VagaEdital.objects.filter(edital=self).values_list(
                'cargo_emprego_area__id', flat=True
            )
            areacorrelata_do_servidor_contemplada = servidor.cargo_emprego_area.id in VagaEdital.objects.filter(edital=self).values_list(
                'areas_correlatas__id', flat=True
            )
            return em_periodo_inscricao_e_cargo_contemplado and (area_do_servidor_contemplada or areacorrelata_do_servidor_contemplada)
        return em_periodo_inscricao_e_cargo_contemplado

    def is_em_periodo_de_recurso_edital_servidor(self, servidor):
        return self.is_em_periodo_de_recurso_edital() and self.cargos.filter(pk=servidor.cargo_emprego.pk).exists()

    def is_em_periodo_de_recurso_servidor(self, servidor):
        return self.is_em_periodo_de_recursos() and self.cargos.filter(pk=servidor.cargo_emprego.pk).exists()

    def is_pode_exibir_resultado(self):
        return self.inicio_resultados <= datetime.datetime.now() if self.inicio_resultados else False

    def is_pode_exibir_resultado_recurso(self):
        return self.resultado_recursos <= datetime.datetime.now() if self.resultado_recursos else False

    def is_coordenador(self, user):
        return self.coordenadores.filter(pk=user.pk).exists()

    def pode_editar(self, user):
        eh_coordenador = user.has_group_cached('Coordenador de Remanejamento') or self.is_coordenador(user)
        eh_avaliador = user.has_group_cached('Avaliador de Remanejamento')
        eh_coordenador_sistemico_rh = user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico')
        eh_administrador_remanejamento = user.has_group_cached('remanejamento Administrador')
        return eh_coordenador or eh_avaliador or eh_coordenador_sistemico_rh or eh_administrador_remanejamento

    def get_url_inscrever(self):
        return f'/remanejamento/inscrever/{self.pk}/'

    def get_url_recurso(self):
        return f'/remanejamento/recurso_edital/{self.pk}/'

    @staticmethod
    def get_etapas():
        """
        Retorna lista de etapas do processo de remoção interna: Edital
        """
        EDITAL_PUBLICADO = 'Edital Publicado'
        INSCRICOES = 'Inscrições'
        RESULTADO_PARCIAL = 'Resultado Parcial'
        RECURSOS = 'Recursos'
        RESULTADO_FINAL = 'Resultado Final'
        return [EDITAL_PUBLICADO, INSCRICOES, RESULTADO_PARCIAL, RECURSOS, RESULTADO_FINAL]

    def get_etapas_com_status(self):
        """
        Retorna lista de tuplas de etapas do processo de remoção interna indicando a etapa ativa: [{"Edital Publicado": False}]
        """
        lista = []
        for etapa in Edital.get_etapas():
            etapa_atual = False
            if (
                etapa == 'Edital Publicado'
                and self.is_em_periodo_aguardando_inicio_inscricao()
                or etapa == 'Inscrições'
                and self.is_em_periodo_de_inscricao()
                or etapa == 'Resultado Parcial'
                and self.is_em_periodo_de_processamento_resultado()
                or etapa == 'Recursos'
                and self.is_em_periodo_de_recursos()
                or etapa == 'Resultado Final'
                and self.is_pode_exibir_resultado()
            ):
                etapa_atual = True

            lista.append((etapa, etapa_atual))

        return lista

    def get_etapa_atual(self):
        """
        Retorna etapa atual do processo de remoção
        """
        for etapa, ativa in self.get_etapas_com_status():
            if ativa:
                return etapa

    def get_lista_inscritos(self):
        campi = UnidadeOrganizacional.objects.suap().order_by('setor__sigla')
        dados = []

        count = 0
        for inscricao in self.inscricao_set.filter(confirmada=True).order_by('servidor__cargo_emprego__nome', 'id'):
            servidor = inscricao.servidor
            matriculas_substituto = servidor.get_matriculas_por_cpf().filter(eh_docente=True).values_list('matricula', flat=True)

            # normaliza siglas de setores
            sigla_unidade_lotacao = inscricao.campus_origem_ajustado.sigla if inscricao.campus_origem_ajustado else servidor.setor_lotacao.uo.sigla
            sigla_unidade_lotacao = ajustar_sigla_campus_lotacao(sigla_unidade_lotacao)

            sigla_unidade_exercicio = (
                inscricao.campus_origem_ajustado.sigla if inscricao.campus_origem_ajustado else servidor.setor_exercicio.uo.sigla
            )

            # Pode reduzir a quantidade de dias referente a afastamentos configurados no edital que o servidor tenha realizado o usufruto com data de ínício maior que a data de início do exercício
            dias_exercicio_servidor_suap = int(tempo_servico_no_cargo_em_dias(inscricao, inscricao.edital.inicio_inscricoes.date()))
            if afastamentos_para_descontar := ServidorAfastamentoRemocaoInterna.objects.filter(
                inscricao__edital=inscricao.edital, inscricao__servidor=servidor, validado_em__isnull=False
            ):
                for afastamento_para_descontar in afastamentos_para_descontar:
                    dias_descontar = (
                        afastamento_para_descontar.servidor_afastamento.data_termino - afastamento_para_descontar.servidor_afastamento.data_inicio
                    ).days + 1
                    dias_exercicio_servidor_suap -= dias_descontar

            # Pode adicionar dias se existir tempo adicional cadastrado no edital
            if ServidorTempoAdicionalRemocaoInterna.objects.filter(servidor=servidor).exists():
                for registro_tempo_adicional in ServidorTempoAdicionalRemocaoInterna.objects.filter(servidor=servidor):
                    dias_exercicio_servidor_suap = dias_exercicio_servidor_suap + int(registro_tempo_adicional.quantidade_dias)

            Inscricao.objects.filter(id=inscricao.id).update(dias_exercicio_servidor_suap=dias_exercicio_servidor_suap)
            count += 1
            item = [
                count,
                inscricao.id,
                inscricao.horario,
                inscricao.vaga_edital.disciplina if inscricao.vaga_edital else None,
                servidor.disciplina_ingresso,
                inscricao.anexo and inscricao.anexo.name or '-',
                servidor.matricula,
                inscricao.servidor.pessoa_fisica.nome,
                inscricao.servidor.pessoa_fisica.nascimento_data,
                inscricao.servidor.email_institucional,
                inscricao.inicio_exercicio,
                servidor.data_inicio_exercicio_no_cargo,
                inscricao.dou_numero,
                inscricao.dou_data.year > 1950 and inscricao.dou_data or '-',  # evita erros de conversao de data
                inscricao.dou_pagina,
                inscricao.dou_sessao,
                inscricao.classificacao_concurso,
                inscricao.jornada_trabalho,
                inscricao.campus_origem_ajustado.id if inscricao.campus_origem_ajustado else servidor.setor_lotacao.uo.id,
                sigla_unidade_lotacao,
                sigla_unidade_exercicio,
                inscricao.recurso_texto or '-',
                inscricao.avaliacao_recurso or '-',
                dias_exercicio_servidor_suap,
                servidor.tempo_servico_no_cargo_via_pca(inscricao.edital.inicio_inscricoes.date()).days,
                servidor.get_cargo_area(),
                format_(matriculas_substituto),
                inscricao.avaliacao_status,
            ]

            for campus in campi:
                inscricao_item = inscricao.inscricaoitem_set.filter(campus=campus)
                item.append(inscricao_item and inscricao_item[0].preferencia or '-')
            dados.append(item)
        return dados

    def get_lista_inscritos_com_cabecalho(self):
        cabecalho = [
            '#',
            'Identificador da Inscrição',
            'Horário',
            'Disciplina Inscrita',
            'Disciplina de Ingresso',
            'Anexo',
            'Matrícula',
            'Nome',
            'Nascimento',
            'E-mail',
            'Início Exercício',
            'Início de Exercício no Cargo(SUAP)',
            'DOU - Número',
            'DOU - Data',
            'DOU - Página',
            'DOU - Sessão',
            'DOU - Classificação Concurso',
            'DOU - Jornada de Trabalho',
            'ID Unidade de Lotação',
            'Lotação SIAPE Atual',
            'Exercício SIAPE Atual',
            'Texto do recurso',
            'Parecer do recurso',
            'Dias em Serviço',
            'Dias em Serviço(via PCA)',
            'Cargo/Área',
            'Matricula_Substituto',
            'Situação da Inscrição',
        ]
        campi = UnidadeOrganizacional.objects.suap().order_by('setor__sigla')
        for campus in campi:
            cabecalho.append(str(campus))
        dados = [cabecalho]

        dados.extend(self.get_lista_inscritos())
        return dados

    def get_absolute_url(self):
        return f'/admin/remanejamento/edital/{self.pk}/view/'

    def get_lista_vagas_por_cargo(self):
        vagas_edital = VagaEdital.objects.filter(edital=self)

        # Convertendo o resultado em uma lista de dicionários
        lista = []
        for vagaedital in vagas_edital:
            cargo = vagaedital.get_cargo_area()
            campus = vagaedital.campus.sigla
            qtd_edital = vagaedital.qtd_edital

            # Verificando se a quantidade de vagas é maior que zero
            if qtd_edital > 0:
                # Verificando se já existe uma entrada para o cargo na estrutura
                cargo_existente = next((c for c in lista if c.get(cargo)), None)
                if cargo_existente:
                    # Se o cargo já existe na lista, adicionamos o campus e a quantidade de vagas para esse campus
                    cargo_existente[cargo][campus] = qtd_edital
                else:
                    # Se o cargo não existe na lista, criamos uma nova entrada para o cargo com o campus e a quantidade de vagas
                    lista.append({cargo: {campus: qtd_edital}})
        return lista

    def get_lista_vagas_por_disciplina(self):
        vagas_edital = VagaEdital.objects.filter(edital=self)

        # Convertendo o resultado em uma lista de dicionários
        lista = []
        for vagaedital in vagas_edital:
            disciplina = vagaedital.disciplina.descricao
            campus = vagaedital.campus.sigla
            qtd_edital = vagaedital.qtd_edital

            # Verificando se a quantidade de vagas é maior que zero
            if qtd_edital > 0:
                # Verificando se já existe uma entrada para a disciplina na estrutura
                disciplina_existente = next((c for c in lista if c.get(disciplina)), None)
                if disciplina_existente:
                    # Se a disciplina já existe na lista, adicionamos o campus e a quantidade de vagas para esse campus
                    disciplina_existente[disciplina][campus] = qtd_edital
                else:
                    # Se a disciplina não existe na lista, criamos uma nova entrada para a disciplina com o campus e a quantidade de vagas
                    lista.append({disciplina: {campus: qtd_edital}})
        return lista

    @staticmethod
    def classificar_por_criterios(dados_inscricao, edital_pk):
        """
        Função para classificar os inscritos em um edital com base nos critérios cadastrados no edital
        """
        criterios = []
        criterios_do_edital = EditalCriterioClassificacao.objects.filter(edital__id=edital_pk).all()

        if criterios_do_edital.filter(criterio_classificacao__nome=CriterioClassificacaoChoices.DATA_INICIO_EXERCICIO_CARGO_NO_ORGAO).exists():
            # 1. Maior tempo de serviço, como efetivo e no cargo, no IFRN
            dias_exercicio_servidor_suap = int(dados_inscricao['Dias em Serviço'])
            criterios.append(-dias_exercicio_servidor_suap)  # sinal negativo para ordenar do maior para o menor

        if criterios_do_edital.filter(criterio_classificacao__nome=CriterioClassificacaoChoices.DATA_CONCURSO_PUBLICO).exists():
            # 2. Maior antiguidade do concurso público para ingresso no IFRN
            data_concurso_publico = dados_inscricao['DOU - Data']
            criterios.append(data_concurso_publico)

        if criterios_do_edital.filter(criterio_classificacao__nome=CriterioClassificacaoChoices.CLASSIFICACAO_CONCURSO).exists():
            # 3. Melhor classificação no concurso público para ingresso no IFRN
            classificacao_concurso = int(dados_inscricao['DOU - Classificação Concurso'])
            criterios.append(classificacao_concurso)

        if criterios_do_edital.filter(criterio_classificacao__nome=CriterioClassificacaoChoices.REGIME_TRABALHO).exists():
            # 4. Regime de trabalho, com prioridade para Dedicação Exclusiva, 40 horas, depois 30 horas e depois 20 horas semanais
            regime_trabalho = dados_inscricao['DOU - Jornada de Trabalho']
            prioridades_regime = {'40 HORAS SEMANAIS': 0, '30 HORAS SEMANAIS': 1, '20 HORAS SEMANAIS': 2}
            prioridade_regime = prioridades_regime.get(regime_trabalho, 3)
            criterios.append(prioridade_regime)

        if criterios_do_edital.filter(criterio_classificacao__nome=CriterioClassificacaoChoices.REGIME_TRABALHO).exists():
            # 5. Maior idade
            data_nascimento = dados_inscricao['Nascimento']
            criterios.append(data_nascimento)

        return tuple(criterios)

    @transaction.atomic()
    def processar_resultado(self):
        try:
            # Exclui todas as inscricoes na situaçção contemplada do edital para reprocessar resultado e se o edital ainda não esta em fase de resultado parcial exclui o log de processamento
            situacoes_para_excluir = [InscricaoContemplada.CONTEMPLADO]
            if self.resultado_parcial_documentotexto and self.resultado_parcial_documentotexto.estah_em_rascunho:
                situacoes_para_excluir.append(InscricaoContemplada.PUBLICADA_PARCIAL)
            InscricaoContemplada.objects.filter(inscricao__edital=self, situacao__in=situacoes_para_excluir).delete()

            # Cria instancia do ProcessamentoResultado
            processamento_resultado = ProcessamentoResultado()
            processamento_resultado.edital = self
            processamento_resultado.save()

            # Cria buffer BytesIO para armazenar log em memória
            log_buffer = io.BytesIO()
            log_buffer.write(
                f'Log do Processamento de Resultado para Edital {self.titulo} criado em {datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n'.encode()
            )
            lista_inscricoes = self.get_lista_inscritos_com_cabecalho()
            header = lista_inscricoes[0]
            rows = lista_inscricoes[1:]

            dict_inscricoes = [dict(zip(header, row, strict=False)) for row in rows]

            if self.eh_edital_remocao_docente():
                dados_classificados = self.classificar_inscricoes_remocao_docente(dict_inscricoes, log_buffer)
            else:
                dados_classificados = self.classificar_inscricoes_remocao_tae(dict_inscricoes, log_buffer)
            # SALVA INSCRICOES CONTEMPLADAS
            inscricoes_contempladas_cargo = [item for item in dados_classificados if item.get('Unidade Alocada', False)]
            for registro in inscricoes_contempladas_cargo:
                # Dados para registro
                try:
                    inscricao = Inscricao.objects.filter(id=registro['Identificador da Inscrição']).first()
                    campus_origem = UnidadeOrganizacional.objects.filter(pk=registro['ID Unidade de Lotação']).first()
                    campus_destino = UnidadeOrganizacional.objects.filter(sigla=registro['Unidade Alocada'], setor__codigo__isnull=False).first()
                    situacao = InscricaoContemplada.CONTEMPLADO
                    situacoes_finais = [
                        InscricaoContemplada.CONTEMPLADO,
                        InscricaoContemplada.PUBLICADA_PARCIAL,
                        InscricaoContemplada.PUBLICADA_FINAL,
                        InscricaoContemplada.HOMOLOGADA,
                    ]
                    # Cadastra se não existir InscricaoContemplada em situacoes_finais para o edital
                    if not InscricaoContemplada.objects.filter(inscricao=inscricao, inscricao__edital=self, situacao__in=situacoes_finais).exists():
                        InscricaoContemplada.cadastrar(inscricao, campus_origem, campus_destino, situacao, processamento_resultado)
                except Exception as e:
                    msg_erro = f'Erro ao salvar Inscrição Contemplada ID {registro["Identificador da Inscrição"]} - {registro["Matrícula"]} - {registro["Nome"]} - {registro["Dias em Serviço"]} - classificacao {registro["DOU - Classificação Concurso"]} - Unidade {registro["Lotação SIAPE Atual"]} - Alocado para {registro["Unidade Alocada"]}\n'
                    log_buffer.write(msg_erro.encode())
                    sentry_sdk.capture_exception(e)
            processamento_resultado.salvar_log(conteudo=log_buffer.getvalue())
            log_buffer.close()
        except Exception as e:
            if settings.DEBUG:
                raise (e)
            sentry_sdk.capture_exception(e)

    def get_vaga_correlata(self, servidor: Servidor) -> VagaEdital | None:
        """Retorna a vaga do edital à qual o servidor concorre por correlação, se houver.

        O servidor concorre às vagas de outro Cargo/Área quando:
        - sua área é correlata de uma vaga do mesmo cargo (ex.: Técnico de Laboratório - Sistemas de Informação
          concorre às vagas de Técnico de Laboratório - Informática); ou
        - seu cargo é correlato de uma vaga (ex.: ODONTOLOGO - 30H - DEC JUD concorre às vagas de ODONTOLOGO - 40 HORAS).

        Args:
            servidor: servidor inscrito no edital.

        Returns:
            A vaga correlata, ou ``None`` quando o servidor concorre pelo próprio Cargo/Área.
        """
        vagas = VagaEdital.objects.filter(edital=self)
        if servidor.cargo_emprego_area:
            vaga = vagas.filter(cargo=servidor.cargo_emprego, areas_correlatas=servidor.cargo_emprego_area).first()
            if vaga:
                return vaga
        return vagas.filter(cargos_correlatos=servidor.cargo_emprego).first()

    def _agrupar_inscricoes_tae_por_cargo(self, dict_inscricoes: list[dict]) -> dict[str, list[dict]]:
        """Agrupa as inscrições pelo Cargo/Área em que o servidor concorre, considerando as correlações da vaga."""
        dados_classificados_por_cargo = {}
        for registro in dict_inscricoes:
            servidor_inscrito = Servidor.objects.filter(matricula=registro['Matrícula']).first()
            vagaedital = self.get_vaga_correlata(servidor_inscrito) if servidor_inscrito else None
            if vagaedital:
                registro['Cargo/Área'] = vagaedital.get_cargo_area()
            dados_classificados_por_cargo.setdefault(registro['Cargo/Área'], []).append(registro)
        return dados_classificados_por_cargo

    @staticmethod
    def _get_vagas_remanescentes_do_cargo(vagas_disponiveis: list[dict], cargo: str) -> dict | None:
        return next((vagas[cargo] for vagas in vagas_disponiveis if cargo in vagas), None)

    @staticmethod
    def _alocar_servidor_tae(servidor: dict, campi, vagas_disponiveis: list[dict], log_buffer) -> bool:
        """Move o servidor para a unidade de maior preferência que ainda tenha vaga do seu Cargo/Área.

        Returns:
            ``True`` se o servidor foi realocado (a alocação deve recomeçar do primeiro classificado).
        """
        sigla_unidade_atual_servidor = servidor.get('Unidade Alocada') or servidor['Lotação SIAPE Atual']

        # Obter preferências do servidor ordenadas pela prioridade
        novo_dict = {k: v for k, v in servidor.items() if v != '-' and k in campi}
        preferencias = sorted(novo_dict, key=lambda k: int(novo_dict[k]) if novo_dict[k] else 0)

        preferencias_msg = (
            f'PREFERENCIAS DO SERVIDOR {servidor["Matrícula"]} - {servidor["Nome"]} - Lotado em {sigla_unidade_atual_servidor}: {preferencias}\n'
        )
        log_buffer.write(preferencias_msg.encode())

        cargo_servidor = servidor['Cargo/Área']
        vagas_remanescentes = Edital._get_vagas_remanescentes_do_cargo(vagas_disponiveis, cargo_servidor)
        for unidade_preferida in preferencias:
            log_buffer.write(f'Verificando para a unidade {unidade_preferida}\n'.encode())

            if unidade_preferida == sigla_unidade_atual_servidor:
                return False  # Já está na unidade preferida mais alta possível

            if vagas_remanescentes and vagas_remanescentes.get(unidade_preferida, 0) > 0:
                # Libera vaga anterior
                vagas_remanescentes[sigla_unidade_atual_servidor] = vagas_remanescentes.get(sigla_unidade_atual_servidor, 0) + 1

                # Ocupa nova vaga
                vagas_remanescentes[unidade_preferida] -= 1
                servidor['Unidade Alocada'] = unidade_preferida

                log_buffer.write(
                    f'SERVIDOR {servidor["Matrícula"]} - {servidor["Nome"]} removido de {sigla_unidade_atual_servidor} para {unidade_preferida}\n'.encode()
                )
                log_buffer.write(f'VAGAS DISPONÍVEIS: {vagas_remanescentes}\n'.encode())
                log_buffer.write(f'Reinicia do primeiro classificado para o cargo {cargo_servidor} com vagas {vagas_remanescentes}\n'.encode())
                return True
        return False

    def classificar_inscricoes_remocao_tae(self, dict_inscricoes, log_buffer=None):
        # Classificando os dados com base nos critérios para cada cargo
        dados_classificados_por_cargo = self._agrupar_inscricoes_tae_por_cargo(dict_inscricoes)
        resultado_classificacao = []

        for cargo, dados_cargo in dados_classificados_por_cargo.items():
            dados_classificados = sorted(dados_cargo, key=lambda x: Edital.classificar_por_criterios(x, self.id))

            # LOG - Imprimir a lista classificada para cada cargo (e áreas correlatas se existir)
            log_buffer.write(f'Lista classificada para o cargo: {cargo}\n'.encode())
            for indice, registro in enumerate(dados_classificados, start=1):
                msg_d = f'{indice}: {registro["Matrícula"]} - {registro["Nome"]} - {registro["Dias em Serviço"]} - classificacao {registro["DOU - Classificação Concurso"]}\n'
                log_buffer.write(msg_d.encode())
        # LOG - FIM

        # Campi Participantes
        campi = self.campus.all().values_list('sigla', flat=True)
        log_buffer.write(f'CAMPI PARTICIPANTES: {list(campi)}\n'.encode())

        for cargo, dados_cargo in dados_classificados_por_cargo.items():
            dados_classificados = sorted(dados_cargo, key=lambda x: Edital.classificar_por_criterios(x, self.id))

            # Vagas iniciais dísponíves por cargo/área
            vagas_disponiveis = self.get_lista_vagas_por_cargo()
            log_buffer.write(f'VAGAS INICIAIS DISPONÍVEIS: {vagas_disponiveis}\n'.encode())

            # Toda realocação reinicia a varredura do primeiro classificado (any() para no primeiro servidor realocado)
            while any(Edital._alocar_servidor_tae(servidor, campi, vagas_disponiveis, log_buffer) for servidor in dados_classificados):
                pass
            log_buffer.write(f'VAGAS FINAL DO CARGO {cargo}: {Edital._get_vagas_remanescentes_do_cargo(vagas_disponiveis, cargo)}\n'.encode())
            resultado_classificacao.extend(dados_classificados)
        return resultado_classificacao

    def classificar_inscricoes_remocao_docente(self, dict_inscricoes, log_buffer=None):
        # Classificando os dados com base nos critérios para cada disciplina (VagaEdital com disciplina)
        # Inicio
        dados_classificados_por_disciplina = {}
        resultado_classificacao = []
        for registro in dict_inscricoes:
            disciplina = registro['Disciplina Inscrita'].descricao

            if disciplina not in dados_classificados_por_disciplina:
                dados_classificados_por_disciplina[disciplina] = []
            dados_classificados_por_disciplina[disciplina].append(registro)

        for disciplina, dados_disciplina in dados_classificados_por_disciplina.items():
            dados_classificados = sorted(dados_disciplina, key=lambda x: Edital.classificar_por_criterios(x, self.id))

            # LOG - Imprimir a lista classificada para cada disciplina inscrita
            log_buffer.write(f'Lista classificada para a disciplina: {disciplina}\n'.encode())
            for indice, registro in enumerate(dados_classificados, start=1):
                msg_d = f'{indice}: {registro["Matrícula"]} - {registro["Nome"]} - {registro["Dias em Serviço"]} - classificacao {registro["DOU - Classificação Concurso"]}\n'
                log_buffer.write(msg_d.encode())
        # LOG - FIM

        # Campi Participantes
        campi = self.campus.all().values_list('sigla', flat=True)
        log_buffer.write(f'CAMPI PARTICIPANTES: {list(campi)}\n'.encode())

        for dados_disciplina in dados_classificados_por_disciplina.values():
            dados_classificados = sorted(dados_disciplina, key=lambda x: Edital.classificar_por_criterios(x, self.id))

            # Vagas iniciais dísponíves por disciplina
            vagas_disponiveis = self.get_lista_vagas_por_disciplina()
            log_buffer.write(f'VAGAS INICIAIS DISPONÍVEIS: {vagas_disponiveis}\n'.encode())

            alocacao_feita = True
            while alocacao_feita:
                alocacao_feita = False
                for servidor in dados_classificados:
                    sigla_unidade_atual_servidor = servidor.get('Unidade Alocada') or servidor['Lotação SIAPE Atual']

                    # Obter preferências do servidor ordenadas pela prioridade
                    novo_dict = {k: v for k, v in servidor.items() if v != '-' and k in campi}
                    preferencias = sorted(novo_dict, key=lambda k: int(novo_dict[k]) if novo_dict[k] else 0)

                    preferencias_msg = f'PREFERENCIAS DO SERVIDOR {servidor["Matrícula"]} - {servidor["Nome"]} - Lotado em {sigla_unidade_atual_servidor}: {preferencias}\n'
                    log_buffer.write(preferencias_msg.encode())

                    for unidade_preferida in preferencias:
                        log_buffer.write(f'Verificando para a unidade {unidade_preferida}\n'.encode())

                        if unidade_preferida == sigla_unidade_atual_servidor:
                            break  # Já está na unidade preferida mais alta possível

                        for vagas in vagas_disponiveis:
                            disciplina_inscricao_servidor = servidor['Disciplina Inscrita'].descricao
                            if disciplina_inscricao_servidor in vagas:
                                vagas_remanescentes = vagas[disciplina_inscricao_servidor]
                                if unidade_preferida in vagas_remanescentes and vagas_remanescentes[unidade_preferida] > 0:
                                    # Libera vaga anterior
                                    if sigla_unidade_atual_servidor not in vagas_remanescentes:
                                        vagas_remanescentes[sigla_unidade_atual_servidor] = 0
                                    vagas_remanescentes[sigla_unidade_atual_servidor] += 1

                                    # Ocupa nova vaga
                                    vagas_remanescentes[unidade_preferida] -= 1
                                    servidor['Unidade Alocada'] = unidade_preferida

                                    log_buffer.write(
                                        f'SERVIDOR {servidor["Matrícula"]} - {servidor["Nome"]} removido de {sigla_unidade_atual_servidor} para {unidade_preferida}\n'.encode()
                                    )
                                    log_buffer.write(f'VAGAS DISPONÍVEIS: {vagas_remanescentes}\n'.encode())

                                    alocacao_feita = True  # Reiniciar o loop para reconsiderar todos
                                    break
                        if alocacao_feita:
                            log_buffer.write(
                                f'Reinicia do primeiro classificado para a disciplina {disciplina_inscricao_servidor} com vagas {vagas_remanescentes}\n'.encode()
                            )
                            break  # Reinicia do primeiro servidor
                    if alocacao_feita:
                        break
            log_buffer.write(f'VAGAS FINAL DA DISCIPLINA {disciplina_inscricao_servidor}: {vagas_remanescentes}\n'.encode())
            resultado_classificacao.extend(dados_classificados)
        return resultado_classificacao

    def get_resultado_html(self, dados_classificados_por_cargo, inscricoes_contempladas_resultado, final, homologacao=False):
        return render_to_string(
            'resultado_edital.html',
            {
                'edital': self,
                'dados_classificados_por_cargo': dados_classificados_por_cargo,
                'inscricoes_contempladas_resultado': inscricoes_contempladas_resultado,
                'final': final,
                'homologacao': homologacao,
            },
        )

    def get_inscricoes_contempladas_no_resultado_final(self):
        inscricoes_contempladas_resultado = InscricaoContemplada.objects.filter(
            inscricao__edital=self, situacao__in=InscricaoContemplada.PUBLICADA_FINAL
        )
        return inscricoes_contempladas_resultado

    def get_inscricoes_contempladas_resultado(self, final):
        situacoes = (
            [InscricaoContemplada.PUBLICADA_PARCIAL, InscricaoContemplada.DESISTENCIA]
            if final
            else [InscricaoContemplada.CONTEMPLADO, InscricaoContemplada.PUBLICADA_PARCIAL]
        )
        inscricoes_contempladas_resultado = InscricaoContemplada.objects.filter(inscricao__edital=self, situacao__in=situacoes)
        return inscricoes_contempladas_resultado

    def get_dados_classificados_por_cargo_resultado(self):
        lista_inscricoes = self.get_lista_inscritos_com_cabecalho()
        header = lista_inscricoes[0]
        rows = lista_inscricoes[1:]

        dict_inscricoes = [dict(zip(header, row, strict=True)) for row in rows]

        # Classificando os dados com base nos critérios para cada cargo
        dados_classificados_por_cargo = {}

        for registro in dict_inscricoes:
            # Define qual o Cargo/Área que será levado em consideração para gerar a lista de classificação (ver get_vaga_correlata)
            servidor_inscrito = Servidor.objects.filter(matricula=registro['Matrícula']).first()
            vagaedital = self.get_vaga_correlata(servidor_inscrito) if servidor_inscrito else None
            if vagaedital:
                cargo = vagaedital.get_cargo_area()
                registro['Cargo/Área'] = cargo
                correlatos = [*vagaedital.areas_correlatas.all(), *(cargo.nome for cargo in vagaedital.cargos_correlatos.all())]
                registro['areascorrelatas'] = ', '.join(str(correlato) for correlato in correlatos)
            else:
                cargo = registro['Cargo/Área']
                registro['areascorrelatas'] = None
            if cargo not in dados_classificados_por_cargo:
                dados_classificados_por_cargo[cargo] = []
            dados_classificados_por_cargo[cargo].append(registro)
        return dados_classificados_por_cargo

    def get_dados_classificados_por_cargo(self, dados_cargo):
        """Retorna os dados classificados por cargo com informações de resultado.

        Args:
            dados_cargo: lista de dicionários com os dados dos candidatos
                classificados para o cargo.

        Returns:
            DataFrame: pandas DataFrame com os dados enriquecidos com flags
            de resultado parcial e homologação.
        """
        import pandas as pd

        final = bool(self.resultado_parcial_documentotexto)
        homologacao = bool(self.resultado_final_documentotexto and self.resultado_final_documentotexto.estah_finalizado)
        df = pd.DataFrame(dados_cargo)
        # Obtem lista de matriculas dos servidores contemplados
        matriculas = df['Matrícula'].tolist()
        if homologacao:
            inscricoes_contempladas_resultado_cargo = InscricaoContemplada.objects.filter(
                inscricao__edital=self,
                situacao__in=[InscricaoContemplada.PUBLICADA_FINAL, InscricaoContemplada.HOMOLOGADA],
                inscricao__servidor__matricula__in=matriculas,
            )
        else:
            inscricoes_contempladas_resultado_cargo = self.get_inscricoes_contempladas_resultado(final=final).filter(
                inscricao__servidor__matricula__in=matriculas
            )
        dados_classificados = sorted(dados_cargo, key=lambda x: Edital.classificar_por_criterios(x, self.id))
        resultado_cargo = []
        for indice, dados_inscricao in enumerate(dados_classificados, start=1):
            campus_destino = 'Não Houve Vaga na(s) opção(ões) do servidor'
            if inscricoes_contempladas_resultado_cargo.filter(inscricao__id=dados_inscricao['Identificador da Inscrição']).exists():
                inscricao_contemplada = inscricoes_contempladas_resultado_cargo.filter(
                    inscricao__id=dados_inscricao['Identificador da Inscrição']
                ).first()
                if final and inscricao_contemplada.situacao == InscricaoContemplada.DESISTENCIA:
                    campus_destino = 'Desistiu'
                else:
                    campus_destino = inscricao_contemplada.campus_destino_sigla_ajustado
                    dias_exercicio_servidor_suap = (
                        inscricao_contemplada.inscricao.dias_exercicio_servidor_suap
                        or inscricao_contemplada.inscricao.servidor.tempo_servico_no_cargo(
                            inscricao_contemplada.inscricao.edital.inicio_inscricoes.date()
                        ).days
                    )
                    resultado_cargo.append(
                        (
                            True,
                            [
                                indice,
                                inscricao_contemplada.inscricao.servidor.matricula,
                                inscricao_contemplada.inscricao.servidor.pessoa_fisica.nome,
                                dias_exercicio_servidor_suap,
                                inscricao_contemplada.inscricao.classificacao_concurso,
                                inscricao_contemplada.campus_origem_sigla_ajustado,
                                campus_destino,
                            ],
                        )
                    )
            else:
                resultado_cargo.append(
                    (
                        False,
                        [
                            indice,
                            dados_inscricao['Matrícula'],
                            dados_inscricao['Nome'],
                            dados_inscricao['Dias em Serviço'],
                            dados_inscricao['DOU - Classificação Concurso'],
                            ajustar_sigla_campus_lotacao(dados_inscricao['Lotação SIAPE Atual']),
                            campus_destino,
                        ],
                    )
                )
        return resultado_cargo

    def get_dados_classificados_por_disciplina_resultado(self):
        lista_inscricoes = self.get_lista_inscritos_com_cabecalho()
        header = lista_inscricoes[0]
        rows = lista_inscricoes[1:]

        dict_inscricoes = [dict(zip(header, row, strict=True)) for row in rows]

        # Classificando os dados com base nos critérios para cada disciplina (VagaEdital com disciplina)
        dados_classificados_por_disciplina = {}

        for registro in dict_inscricoes:
            vagaedital = VagaEdital.objects.filter(edital=self, disciplina=registro['Disciplina Inscrita']).first()
            registro['areascorrelatas'] = ', '.join([str(area) for area in vagaedital.disciplinas_correlatas.all()])
            disciplina = registro['Disciplina Inscrita'].descricao
            if disciplina not in dados_classificados_por_disciplina:
                dados_classificados_por_disciplina[disciplina] = []
            dados_classificados_por_disciplina[disciplina].append(registro)
        return dict(sorted(dados_classificados_por_disciplina.items()))

    def get_inscricoes_inabilitadas(self):
        return self.inscricao_set.filter(confirmada=False, data_inapta__isnull=False)

    def get_disciplinas_sem_inscricoes(self):
        disciplinas_inscricoes_confirmadas = self.inscricao_set.filter(vaga_edital__isnull=False, confirmada=True).values_list(
            'vaga_edital__disciplina', flat=True
        )
        disciplinas_sem_inscricao = (
            VagaEdital.objects.filter(edital=self)
            .exclude(disciplina__isnull=False, disciplina__in=disciplinas_inscricoes_confirmadas)
            .distinct('disciplina')
        )
        return disciplinas_sem_inscricao

    def get_cargo_areas_sem_inscricoes(self):
        cargos_inscricoes_confirmadas = self.inscricao_set.filter(confirmada=True).values_list('servidor__cargo_emprego', flat=True)
        cargos_areas_sem_inscricao = (
            VagaEdital.objects.filter(edital=self)
            .exclude(cargo__in=cargos_inscricoes_confirmadas)
            .exclude(cargos_correlatos__in=cargos_inscricoes_confirmadas)
            .distinct('cargo', 'cargo_emprego_area')
        )
        return cargos_areas_sem_inscricao

    def eh_edital_remocao_docente(self):
        return bool(self.cargos.filter(nome__contains='PROFESSOR').exists()) or self.categoria == Edital.DOCENTE

    def pode_publicar_resultado_parcial(self) -> bool:
        # Verifica se o resultado parcial pode ser publicado:
        # - Caso o documento de resultado parcial não exista e a data atual seja maior ou igual à data prevista para o resultado parcial.
        # - Caso o documento de resultado parcial exista, mas não esteja assinado ou finalizado, até o fim dos recursos.
        # As datas são opcionais: sem a data prevista (ou sem o fim dos recursos) não há como publicar.
        agora = datetime.datetime.now()
        documento = self.resultado_parcial_documentotexto
        if not documento:
            return bool(self.data_resultado_parcial and agora >= self.data_resultado_parcial)
        documento_pendente = not documento.estah_assinado or not documento.estah_finalizado
        return bool(documento_pendente and self.fim_recursos and agora <= self.fim_recursos)

    def pode_publicar_resultado_final(self) -> bool:
        documento = self.resultado_parcial_documentotexto
        if not (documento and documento.estah_finalizado and self.fim_recursos):
            return False
        agora = datetime.datetime.now()
        return agora >= self.fim_recursos and agora >= self.inicio_resultados

    def pode_publicar_homologacao_resultado_final(self) -> bool:
        documento = self.resultado_final_documentotexto
        return bool(
            documento
            and documento.estah_finalizado
            and self.data_homologacao_resultado
            and datetime.datetime.now() >= self.data_homologacao_resultado
        )

    def resultado_parcial_foi_homologado(self):
        if self.resultado_parcial_documentotexto:
            return self.resultado_parcial_documentotexto.estah_assinado or self.resultado_parcial_documentotexto.estah_finalizado
        return False

    def resultado_final_foi_homologado(self):
        if self.resultado_final_documentotexto:
            return self.resultado_final_documentotexto.estah_assinado or self.resultado_final_documentotexto.estah_finalizado
        return False

    def existem_anexos_nao_avaliados(self):
        return self.inscricao_set.filter(confirmada=True, anexo_avaliado_por__isnull=True).exclude(anexo__isnull=True).exclude(anexo='').exists()

    def existem_inscricoes_com_avaliacoes_pendentes(self):
        return self.inscricao_set.filter(confirmada=True, validado_por__isnull=True, licenca_afastamento_verificado_por__isnull=True).exists()


class EditalRecurso(models.ModelPlus):
    """
    Recursos impetrados contra o Edital
    """

    edital = models.ForeignKeyPlus('remanejamento.edital', verbose_name='Edital', on_delete=models.CASCADE)
    servidor = models.ForeignKeyPlus('rh.servidor', verbose_name='Servidor', null=True, on_delete=models.CASCADE)
    recurso_texto = models.TextField('Texto do Recurso', blank=True)
    dh_recurso = models.DateTimeField(auto_now_add=True, verbose_name='Horário de cadastro do recurso')
    recurso_resposta = models.TextField('Resposta ao Recurso', blank=True)
    dh_resposta = models.DateTimeField(verbose_name='Horário de cadastro da resposta ao recurso', null=True, blank=True)
    recurso_respondido = models.BooleanField(verbose_name='O recurso foi respondido?', default=False)

    class Meta:
        verbose_name = 'Recurso ao Edital'
        verbose_name_plural = 'Recursos ao Edital'

    def get_absolute_url(self):
        return f'/remanejamento/visualizar_recurso_edital/{self.pk}/'.format()

    def pode_exibir_resposta_recurso_edital(self, user):
        if not self.recurso_resposta or not self.edital.resultado_recursos_edital:
            return False
        return self.edital.resultado_recursos_edital <= datetime.datetime.now() or user in self.edital.coordenadores.all()


class Disciplina(models.ModelPlus):
    """
    Disciplinas disponíveis para um determinado Edital.
    É usado em Remoção Interna para docentes.
    """

    edital = models.ForeignKeyPlus('remanejamento.edital', on_delete=models.CASCADE)
    descricao = models.CharField('Descrição', max_length=255)
    avaliadores = models.ManyToManyField('comum.User')

    class Meta:
        ordering = ['-edital', 'descricao']
        unique_together = ('edital', 'descricao')

    def __str__(self):
        return f'{self.descricao}'

    @classmethod
    def get_avaliadores_ids(cls):
        avaliadores_ids = []
        for disciplina in cls.objects.all():
            avaliadores_ids += disciplina.avaliadores.values_list('id', flat=True)
        return list(set(avaliadores_ids))


class DisciplinaItem(models.ModelPlus):
    disciplina = models.ForeignKeyPlus('remanejamento.disciplina', on_delete=models.CASCADE)
    descricao = models.TextField('Descrição')
    sequencia = models.PositiveIntegerField('Sequência')
    nao_avaliar = models.BooleanField(
        'Não avaliar', default=False, help_text='será exibido na tela de avaliação, mas não será solicitado a porcentagem.'
    )

    class Meta:
        ordering = ['disciplina', 'sequencia']
        verbose_name = 'Critério de avaliação de disciplina'
        verbose_name_plural = 'Critérios de avaliação de disciplinas'
        unique_together = (('disciplina', 'descricao'), ('disciplina', 'sequencia'))

    def __str__(self):
        return f'{self.disciplina} - {self.descricao}'


class Inscricao(models.ModelPlus):
    horario = models.DateTimeField(auto_now_add=True, verbose_name='Horário')
    edital = models.ForeignKeyPlus('remanejamento.edital', on_delete=models.CASCADE)
    disciplina = models.ForeignKeyPlus(Disciplina, null=True, blank=True, on_delete=models.CASCADE)  # FIXME Deprecated - vai sair
    vaga_edital = models.ForeignKeyPlus('remanejamento.VagaEdital', null=True, blank=True, verbose_name='Vaga do Edital', on_delete=models.PROTECT)
    servidor = models.ForeignKeyPlus('rh.Servidor', null=True, verbose_name='Servidor', on_delete=models.CASCADE)
    inicio_exercicio = models.DateFieldPlus(verbose_name='Início de exercício')
    anexo = models.FileFieldPlus(upload_to='remanejamento/anexos/', max_length=255, blank=True)
    dou_numero = models.CharField('Número', max_length=255, blank=False)
    dou_data = models.DateFieldPlus(verbose_name='Data', blank=False)
    dou_pagina = models.CharField('Página', max_length=255, blank=False)
    dou_sessao = models.CharField('Seção', max_length=255, blank=False)
    classificacao_concurso = models.PositiveIntegerField('Classificação no concurso para ingresso no IFRN', blank=False)
    concurso_ingresso_eh_ifrn = models.BooleanField('Concurso para ingresso foi do IFRN', null=True, blank=False)
    jornada_trabalho = models.ForeignKeyPlus('rh.JornadaTrabalho', on_delete=models.CASCADE)
    frase_pura = models.TextField(help_text='Este campo é o que o candidato pode ver')
    frase_pura_com_chave = models.TextField(help_text='Em nenhuma hipótese um candidato pode ver este campo')
    frase_hash = models.CharField(
        max_length=128,
        help_text='Este campo é o que o candidato pode ver. Juntamente com '
        '"frase_pura", é a garantia de que os dados inseridos pelo usuário '
        'estão intactos.',
    )
    confirmada = models.BooleanField(default=True)
    observacao = models.TextField('Observações', blank=True)

    # Campos calculados para fins de classificação
    dias_exercicio_servidor_suap = models.IntegerField(
        'Dias de exercício do servidor no cargo',
        null=True,
        blank=True,
        help_text='Quantidade de dias de exercício do servidor no cargo, considerando o início de exercício informado na inscrição e descontando possíveis afastamentos que estejam configurados no edital.',
    )

    # Recurso
    recurso_texto = models.TextField('Texto do Recurso', blank=True)
    situacao_recurso = models.CharFieldPlus(
        'Situação do Recurso',
        max_length=30,
        null=True,
        blank=True,
        choices=[
            ('PENDENTE_DE_ANALISE', 'Pendente de Análise'),
            ('DEFERIDO', 'Deferido'),
            ('DEFERIDO_PARCIALMENTE', 'Deferido Parcialmente'),
            ('INDEFERIDO', 'Indeferido'),
        ],
    )
    recurso_respondido_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Resposta ao recurso Por',
        related_name='inscricao_remocaointerna_recurso_respondido_por',
        on_delete=models.CASCADE,
    )
    recurso_respondido_em = models.DateTimeFieldPlus('Resposta ao recurso em', null=True, blank=True)

    # Campus do Servidor a ser utilizado no processamento
    campus_origem_ajustado = models.ForeignKeyPlus(
        'rh.UnidadeOrganizacional',
        verbose_name='Campus de Lotação Ajustado',
        related_name='inscricoes_campus_origem_ajustado',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    avaliacao_recurso = models.TextField('Resposta ao recurso', null=True, blank=True)

    # Desistencia
    data_desistencia = models.DateTimeFieldPlus(null=True, blank=True, verbose_name='Data/hora da desistência')

    # Inabilitação
    data_inapta = models.DateTimeFieldPlus(null=True, blank=True, verbose_name='Inapta em')
    motivo_inapta = models.TextField('Motivo da Inaptidão', blank=True, null=True)
    atualizado_inapta_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Inabilitada Por',
        related_name='inscricoes_remocao_inapta_atualizado_por',
        on_delete=models.CASCADE,
    )

    # Informação do servidor que validou as informações
    validado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Validado Por',
        related_name='inscricao_remocaointerna_validado_por',
        on_delete=models.CASCADE,
    )
    validado_em = models.DateTimeFieldPlus('Validado em', null=True, blank=True)

    # Informação do servidor que verificou as licenças/afastamentos
    licenca_afastamento_verificado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Licença/afastamentos verificado por',
        related_name='licenca_afastamento_verificado_por',
        on_delete=models.CASCADE,
    )
    licenca_afastamento_verificado_em = models.DateTimeFieldPlus('Licença/afastamentos verificado em', null=True, blank=True)

    # Avaliação do arquivo anexo
    anexo_avaliado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Anexo Avaliado Por',
        related_name='inscricao_remocaointerna_anexo_avaliado_por',
        on_delete=models.CASCADE,
    )
    anexo_avaliado_em = models.DateTimeFieldPlus('Anexo Avaliado em', null=True, blank=True)
    anexo_deferido = models.BooleanField('Anexo Aceito?', null=True, blank=True)

    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Atualizado Por',
        related_name='inscricao_remocaointerna_atualizado_por',
        on_delete=models.CASCADE,
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True, blank=True)

    # Avaliação - #DEPRECATED
    avaliacao_avaliador = models.ForeignKeyPlus('comum.User', null=True, blank=True, on_delete=models.CASCADE, verbose_name='Avaliador da inscrição')
    avaliacao_status = models.CharField(
        max_length=255,
        default='Pendente',
        blank=True,
        verbose_name='Status avaliação',
        choices=[
            ['Pendente', 'Pendente'],
            ['Aguardando habilitação da banca', 'Aguardando habilitação da banca'],
            ['Habilitado', 'Habilitado'],
            ['Não habilitado', 'Não habilitado'],
            ['Avaliado', 'Avaliado'],
            ['Apto', 'Apto'],
            ['Não apto', 'Não apto'],
        ],
    )
    avaliacao_score = models.FloatField(null=True, blank=True, verbose_name='Score')

    class Meta:
        verbose_name = 'Inscrição'
        verbose_name_plural = 'Inscrições'

    def __str__(self):
        return f'{self.id} - {self.servidor} - {self.servidor.cargo_emprego}'

    @transaction.atomic()
    def save(self, *args, **kwargs):
        """
        O método foi sobrescrito para preencher automaticamente o campo ``confirmada``.
        """
        # Vamos desconfirmar as inscrições anteriores para o mesmo edital e disciplina
        # caso esteja cadastrando uma nova inscrição
        # Exceto se for uma inscrição de remoção docente que permitam múltiplas inscrições para o servidor em disciplinas diferentes
        permitir_multiplas_inscricoes = self.edital.servidores_permitidos_multiplas_inscricoes.filter(pk=self.servidor.get_vinculo().id).exists()
        if not self.pk:
            self.confirmada = True
            if not permitir_multiplas_inscricoes:
                Inscricao.objects.filter(servidor=self.servidor, edital=self.edital, disciplina=self.disciplina).update(confirmada=False)

        user = tl.get_user()
        if user:
            self.atualizado_em = datetime.datetime.now()
            self.atualizado_por = user.get_vinculo()

        if self.pk and user and self.is_pode_editar(user):
            # Salva informações de atualização no histórico se o usuario for coordenador do edital ou do RH
            objeto_anterior = Inscricao.objects.get(pk=self.pk)
            super().save(*args, **kwargs)
            campos_modificados = obter_campos_alterados(objeto_anterior, self)
            acao_realizada = f'Atualizou os seguinte campos da inscrição número {self.id}: {campos_modificados}'
            AcaoEditalHistorico.cadastrar_acao(self.edital, self.edital.get_etapa_atual(), acao_realizada, self.atualizado_por)

            # Atualiza o atributo inicio_exercicio caso exista instancia de ServidorDataInicioExercicioRemocaoInterna para o servidor da inscricao
            if not self.inicio_exercicio and ServidorDataInicioExercicioRemocaoInterna.objects.filter(servidor=self.servidor).exists():
                servidor_data_inicio_ajustada = ServidorDataInicioExercicioRemocaoInterna.objects.filter(servidor=self.servidor).first()
                self.inicio_exercicio = servidor_data_inicio_ajustada.data_inicio_exercicio
                acao_realizada = f'Inscrição número {self.id} teve a data de início do exercício ajustada para {servidor_data_inicio_ajustada.data_inicio_exercicio.strftime("%d/%m/%Y")}'
                AcaoEditalHistorico.cadastrar_acao(self.edital, self.edital.get_etapa_atual(), acao_realizada, self.atualizado_por)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f'/remanejamento/inscricao/{self.pk}/'

    def atualizar_frases(self):
        self.frase_pura, self.frase_pura_com_chave = self.get_frase_pura_e_com_chave()
        self.frase_hash = self.get_frase_hash()
        self.save()

    def efetivar_desistencia(self):
        self.confirmada = False
        self.data_desistencia = datetime.datetime.now()
        self.save()

    def efetivar_inaptidao(self, motivo_inapta, vinculo):
        """
        Atualiza o campo data_inapta  de uma inscrição com motivo sobre alteração
        """
        self.confirmada = False
        self.data_inapta = datetime.datetime.now()
        self.motivo_inapta = motivo_inapta
        self.atualizado_inapta_por = vinculo
        self.save()

    def efetivar_reabilitacao(self, observacao, vinculo):
        """
        Atualiza o campo data_inapta, motivo_inapta e atualizado_inapta_por  para None e confirmada para Sim
        """
        self.observacao = observacao
        self.atualizado_por = vinculo
        self.confirmada = True
        self.data_inapta = None
        self.motivo_inapta = None
        self.atualizado_inapta_por = None
        self.save()

    def get_frase_pura_e_com_chave(self):
        # Itens padrão
        itens = [
            'id',
            str(self.pk),
            'horario',
            str(self.horario),
            'edital',
            str(self.edital.titulo),
            'servidor',
            str(self.servidor),
            'inicio_exercicio',
            str(self.inicio_exercicio),
            'dou_numero',
            str(self.dou_numero),
            'dou_data',
            str(self.dou_data),
            'dou_pagina',
            str(self.dou_pagina),
            'dou_sessao',
            str(self.dou_sessao),
            'classificacao_concurso',
            str(self.classificacao_concurso),
            'jornada_trabalho',
            str(self.jornada_trabalho),
        ]

        # Adicionando ``self.inscricaoitem_set.all()``
        for item in self.inscricaoitem_set.all():
            itens.append(str(item.campus))
            itens.append(str(item.preferencia))

        if self.disciplina:
            itens.append('Disciplina')
            itens.append(str(self.disciplina))

        frase_pura = []
        for idx, i in enumerate(itens):
            frase_pura.append(i)
            if idx % 2 == 0:  # label
                frase_pura.append(': ')
            elif idx != (len(itens) - 1):  # valor e não é o último
                frase_pura.append(' | ')
        frase_pura = ''.join(frase_pura)
        frase_pura_com_chave = frase_pura + ' | ' + self.edital.chave_hash
        return to_ascii(frase_pura).upper(), to_ascii(frase_pura_com_chave).upper()

    def get_frase_hash(self):
        return hashlib.sha512(self.frase_pura_com_chave.encode('utf-8')).hexdigest()

    def pode_ver(self, user):
        """Testa se o usuário pode ver a inscrição"""
        return any(
            [
                user.is_superuser,
                self.servidor.get_vinculo().user == user,
                user in self.edital.coordenadores.all(),
                self.disciplina and user in self.disciplina.avaliadores.all(),
            ]
        )

    def pode_mudar_status(self, user):
        """Testa se o usuário pode mudar o status da inscrição"""
        return self.disciplina and any([user.is_superuser, user in self.edital.coordenadores.all()])

    def avaliador_pode_habilitar(self, user):
        """
        Testa se o usuário pode mudar o status da inscrição para
        `Não Habilitado`.
        """
        return self.pode_avaliar(user) and self.avaliacao_status == 'Aguardando habilitação da banca'

    def pode_ver_parecer(self, user):
        return (
            self.pode_ver(user)
            and self.avaliacao_status in ('Apto', 'Não apto', 'Não habilitado')
            and self.disciplina.edital.is_pode_exibir_resultado()
        )

    def pode_ver_resultado_recurso(self, user):
        return self.edital.is_pode_exibir_resultado_recurso() or user in self.edital.coordenadores.all()

    def pode_avaliar(self, user):
        """Testa se o usuário pode avaliar a inscrição"""
        if not self.disciplina:
            return False
        if not self.disciplina.edital.is_em_periodo_de_avaliacao():
            return False
        if self.avaliacao_status not in ['Aguardando habilitação da banca', 'Habilitado', 'Avaliado']:
            return False
        return any([user.is_superuser, user == self.avaliacao_avaliador, user in self.edital.coordenadores.all()])

    def pode_cadastrar_recurso(self, user):
        return all(
            [
                self.servidor.get_vinculo().user == user,
                self.confirmada,
                self.edital.is_em_periodo_de_recurso_servidor(self.servidor),
                not self.recurso_texto,
            ]
        ) or all(
            [
                self.servidor.get_vinculo().user == user,
                self.data_inapta,
                self.edital.is_em_periodo_de_recurso_servidor(self.servidor),
                not self.recurso_texto,
            ]
        )

    def pode_excluir_recurso(self, user):
        return all(
            [
                self.servidor.get_vinculo().user == user,
                self.confirmada,
                self.edital.is_em_periodo_de_recurso_servidor(self.servidor),
                self.recurso_texto,
            ]
        )

    def atualizar_score(self):
        valores = self.inscricaodisciplinaitem_set.values_list('apto_percentual', flat=True)
        if len(valores) > 0:
            self.avaliacao_score = float(sum(valores)) / len(valores)
            self.save()

    def is_habilitado(self):
        return self.avaliacao_status in ('Habilitado', 'Avaliado', 'Apto', 'Não apto')

    def is_apto(self):
        return self.avaliacao_status == 'Apto'

    def get_itens(self):
        return self.inscricaodisciplinaitem_set.all()

    def is_pode_desistir(self, user):
        if not self.edital.inicio_desistencias or not self.edital.fim_desistencias:
            return False
        if not (self.edital.inicio_desistencias <= datetime.datetime.now() and self.edital.fim_desistencias >= datetime.datetime.now()):
            return False
        return self.servidor.get_vinculo().user == user

    def is_pode_inabilitar(self, user):
        return bool(self.edital.pode_editar(user) and not InscricaoContemplada.objects.filter(inscricao=self).exists())

    def is_pode_editar(self, user):
        return bool(self.edital.pode_editar(user) and not self.edital.resultado_final_foi_homologado())

    def deferir_anexo(self, vinculo):
        self.anexo_deferido = True
        self.anexo_avaliado_por = vinculo
        self.anexo_avaliado_em = datetime.datetime.now()
        self.save()

    def indeferir_anexo(self, vinculo):
        self.anexo_deferido = False
        self.anexo_avaliado_por = vinculo
        self.anexo_avaliado_em = datetime.datetime.now()
        self.save()

    @classmethod
    def get_em_periodo_cancelamento_servidor(cls, servidor):
        agora = datetime.datetime.now()
        # se não é servidor retorna none
        if not servidor:
            return cls.objects.none()

        return cls.objects.filter(
            edital__inicio_desistencias__lte=agora, edital__fim_desistencias__gte=agora, data_desistencia__isnull=True, servidor=servidor
        )

    @classmethod
    def get_em_periodo_recurso_servidor(cls, servidor):
        agora = datetime.datetime.now()
        # se não é servidor retorna none
        if not servidor:
            return cls.objects.none()

        return cls.objects.filter(edital__inicio_recursos__lte=agora, edital__fim_recursos__gte=agora, servidor=servidor, recurso_texto='')

    @property
    def data_exercicio_ajustada(self):
        return True if ServidorDataInicioExercicioRemocaoInterna.objects.filter(servidor=self.servidor).exists() else None

    def get_data_exercicio_ajustada(self):
        if self.data_exercicio_ajustada:
            return ServidorDataInicioExercicioRemocaoInterna.objects.filter(servidor=self.servidor).last().data_inicio_exercicio

    @property
    def contemplada(self):
        return InscricaoContemplada.objects.filter(inscricao=self).exists()


class InscricaoItem(models.ModelPlus):
    inscricao = models.ForeignKeyPlus('remanejamento.inscricao', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', on_delete=models.CASCADE)
    preferencia = models.PositiveIntegerField()

    class Meta:
        ordering = ['inscricao', 'preferencia']
        unique_together = (('inscricao', 'campus'), ('inscricao', 'preferencia'))


class InscricaoDisciplinaItem(models.ModelPlus):
    inscricao = models.ForeignKeyPlus('remanejamento.inscricao', on_delete=models.CASCADE)
    disciplina_item = models.ForeignKeyPlus('remanejamento.disciplinaitem', on_delete=models.CASCADE)
    apto = models.BooleanField(default=False)  # DEPRECATE
    apto_percentual = models.IntegerField()
    observacao = models.TextField('Observações', blank=True)

    class Meta:
        ordering = ['inscricao', 'disciplina_item']
        unique_together = ('inscricao', 'disciplina_item')


class InscricaoContemplada(models.ModelPlus):
    DESISTENCIA = 'desistencia'
    CONTEMPLADO = 'contemplado'  # Contemplado em Processamento de Resultado
    PUBLICADA_PARCIAL = 'publicada_parcial'  # Publicada no Resultado Parcial
    PUBLICADA_FINAL = 'publicada_final'  # Publicada no Resultado Parcial
    HOMOLOGADA = 'homologada'  # Resultado Final Homologado
    EM_PROCESSAMENTO = 'em_processamento'  # Os resultados estão em fase de processamento
    EFETIVADA = 'efetivada'  # Servidor movimento para campus de destino
    SITUACAO_CHOICES = (
        (CONTEMPLADO, 'Comtemplada em Processamento de Resultado'),
        (HOMOLOGADA, 'Homologada'),
        (EFETIVADA, 'Remoção Efetivada'),
        (PUBLICADA_PARCIAL, 'Publicada em Resultado Parcial'),
        (PUBLICADA_FINAL, 'Publicada em Resultado Final'),
        (EM_PROCESSAMENTO, 'Em processamento'),
        (DESISTENCIA, 'Desistência'),
    )

    inscricao = models.OneToOneFieldPlus('remanejamento.Inscricao', on_delete=models.CASCADE)
    campus_origem = models.ForeignKeyPlus(
        'rh.UnidadeOrganizacional', related_name='inscricoes_contempladas_remocaointerna_campus_origem', on_delete=models.CASCADE
    )
    campus_destino = models.ForeignKeyPlus(
        'rh.UnidadeOrganizacional', related_name='inscricoes_contempladas_remocaointerna_campus_destino', on_delete=models.CASCADE
    )
    situacao = models.CharFieldPlus(choices=SITUACAO_CHOICES, default=EM_PROCESSAMENTO)
    justificativa = models.TextField('Justificativa', blank=True)
    processamento_resultado = models.ForeignKeyPlus(
        'ProcessamentoResultado', verbose_name='Processamento do Resultado', null=True, blank=True, on_delete=models.SET_NULL
    )
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        verbose_name='Atualizado Por',
        related_name='inscricao_remocao_contempladas_atualizado_por',
        on_delete=models.CASCADE,
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Inscrição Contemplada'
        verbose_name_plural = 'Inscrições Contempladas'

    @classmethod
    def cadastrar(cls, inscricao, campus_origem, campus_destino, situacao, processamento_resultado):
        cls.objects.create(
            inscricao=inscricao,
            campus_origem=campus_origem,
            campus_destino=campus_destino,
            situacao=situacao,
            processamento_resultado=processamento_resultado,
        )

    @property
    def campus_origem_sigla_ajustado(self):
        """
        Retorna a sigla do campus de origem ajustada para o IFRN
        """
        return ajustar_sigla_campus_lotacao(self.campus_origem.sigla) if self.campus_origem else None

    @property
    def campus_destino_sigla_ajustado(self):
        """
        Retorna a sigla do campus de destino ajustada para o IFRN
        """
        return ajustar_sigla_campus_lotacao(self.campus_destino.sigla) if self.campus_destino else None


class AcaoEditalHistorico(models.ModelPlus):
    """
    Guarda o histórico da mudança em ações relacionadas a um Edital de Remoção Interna

    """

    edital = models.ForeignKeyPlus('remanejamento.edital', on_delete=models.CASCADE)
    #: Etapa do processo de remoção no momento da ação
    etapa = models.CharFieldPlus(verbose_name='Etapa', max_length=50)
    acao_realizada = models.CharFieldPlus('Ação Realizada', max_length=1000, blank=True, null=True)
    data_criacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)
    vinculo_responsavel = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável', blank=True, null=True)

    class History:
        disabled = True

    @staticmethod
    def cadastrar_acao(edital, etapa, acao_realizada, vinculo_responsavel):
        AcaoEditalHistorico.objects.create(
            edital=edital,
            etapa=etapa or 'Indefinida',
            acao_realizada=acao_realizada[:999],
            vinculo_responsavel=vinculo_responsavel,
            data_criacao=datetime.datetime.now(),
        )


class ServidorDataInicioExercicioRemocaoInterna(models.ModelPlus):
    """
    Cadastro de data inicio de exercicio para fins de remoção interna para servidores que não estejam com a data correta importada pelo SIAPE
    """

    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    data_inicio_exercicio = models.DateFieldPlus('Data de início de exercício ajustada')
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        verbose_name='Atualizado Por',
        related_name='datainicioexercicio_remocaointerna_atualizado_por',
        on_delete=models.CASCADE,
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Ajuste em Data início de exercício para Remoção Interna'
        verbose_name_plural = 'Ajustes em Data de início de exercício para fins Remoção Interna'
        unique_together = ('servidor',)

    def __str__(self):
        return f'{self.servidor} - {self.data_inicio_exercicio}'

    @classmethod
    def get_data_ajustada(cls, servidor):
        if data_inicio_obj := cls.objects.filter(servidor=servidor).last():
            return data_inicio_obj.data_inicio_exercicio


class CriterioClassificacaoChoices:
    DATA_INICIO_EXERCICIO_CARGO_NO_ORGAO = 'data_inicio_exercicio_cargo_no_orgao'
    DATA_CONCURSO_PUBLICO = 'data_concurso_publico'
    CLASSIFICACAO_CONCURSO = 'classificacao_concurso'
    REGIME_TRABALHO = 'regime_trabalho'
    IDADE = 'idade'
    CRITERIO_CHOICES = (
        (DATA_INICIO_EXERCICIO_CARGO_NO_ORGAO, 'Maior tempo de serviço, como efetivo e no cargo, no IFRN'),
        (DATA_CONCURSO_PUBLICO, 'Maior antiguidade do concurso público para ingresso no cargo'),
        (CLASSIFICACAO_CONCURSO, 'Melhor classificação no concurso público para ingresso no cargo'),
        (REGIME_TRABALHO, 'Regime de trabalho, com prioridade para Dedicação Exclusiva, 40 horas, depois 30 horas e depois 20 horas semanais'),
        (IDADE, 'Idade, tendo preferência os servidores de maior idade'),
    )


class CriterioClassificacao(models.ModelPlus):
    """
    Cadastro dos criterios de classificacao existentes para processar o resultado de um processo de Remoção Interna
    """

    nome = models.CharField('Nome', choices=CriterioClassificacaoChoices.CRITERIO_CHOICES, max_length=100)
    descricao = models.TextField('Descrição', null=True, blank=True)
    ativo = models.BooleanField('Ativo', default=True)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='criterioclassificacao_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Critério para Classificação em Remoção Interna'
        verbose_name_plural = 'Critérios para Classificação em Remoção Interna'

    def __str__(self):
        return self.get_nome_display()

    def get_nome_display(self):
        for valor, texto in CriterioClassificacaoChoices.CRITERIO_CHOICES:
            if valor == self.nome:
                return texto


class EditalCriterioClassificacao(models.ModelPlus):
    edital = models.ForeignKeyPlus('Edital', verbose_name='Edital')
    criterio_classificacao = models.ForeignKeyPlus('CriterioClassificacao', verbose_name='Critério de Classificacao')
    ordem = models.PositiveIntegerField('Ordem', null=False, blank=False)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='editalcriterioclassificacao_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Critério para Classificação do Edital'
        verbose_name_plural = 'Critérios para Classificação do Edital'

        unique_together = ('edital', 'criterio_classificacao')


class AfastamentoRemocaoInterna(models.ModelPlus):
    """
    Os afastamentos  serão configurados para efeitos de remoção interna da seguinte forma:
    - Impeditivos: Quando for configurado como impeditivo, os servidores em usufruto desse afastamento no dia da inscrição não podem se inscrever
    - Desconta tempo de exercicío: Para os afastamentos que descontam tempo de exercício, o total de dias do afastamento será descontado do total de dias de exercício
    """

    if 'rh' in settings.INSTALLED_APPS:
        afastamento = models.ForeignKeyPlus(AfastamentoSiape, on_delete=models.CASCADE)
    impeditivo = models.BooleanField(
        default=False,
        verbose_name='Impede servidores de se inscrever?',
        help_text='Impedirá a inscrição para os servidores em usufruto do afastamento',
    )
    desconta_exercicio = models.BooleanField(
        default=False,
        verbose_name='Descontar período do tempo de exercício?',
        help_text='Irá descontar a quantidade de dias do afastamento do tempo de exercício para fins de remoção interna',
    )
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='afastamentoremocaointerna_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Afastamento - Remoção Interna'
        verbose_name_plural = 'Afastamentos - Remoção Interna'


class EditalAfastamento(models.ModelPlus):
    """
    Os afastamentos registrados do edital serão utilizados para efeitos de remoção interna da seguinte forma:
    - Impeditivos: Quando for configurado como impeditivo, os servidores em usufruto desse afastamento no dia da inscrição não podem se inscrever
    - Desconta tempo de exercicío: Para os afastamentos que descontam tempo de exercício, o total de dias do afastamento será descontado do total de dias de exercício
    """

    edital = models.ForeignKeyPlus('Edital', verbose_name='Edital')
    afastamento_remocaointerna = models.ForeignKeyPlus('AfastamentoRemocaoInterna', null=True, on_delete=models.SET_NULL)
    afastamento = models.ForeignKeyPlus(AfastamentoSiape, on_delete=models.CASCADE)
    impeditivo = models.BooleanField(
        default=False,
        verbose_name='Impede servidores de se inscrever?',
        help_text='Impedirá a inscrição para os servidores em usufruto do afastamento',
    )
    desconta_exercicio = models.BooleanField(
        default=False,
        verbose_name='Descontar período do tempo de exercício??',
        help_text='Irá descontar a quantidade de dias do afastamento do tempo de exercício para fins de remoção interna',
    )
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='editalafastamento_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Afastamento do Edital'
        verbose_name_plural = 'Afastamentos do Edital'


class ServidorAfastamentoRemocaoInterna(models.ModelPlus):
    """
    Afastamentos do servidor para fins de remoção interna que serão utilizados para descontar a quantidade de dias para cada edital
    """

    inscricao = models.ForeignKeyPlus('Inscricao', verbose_name='Inscrição', on_delete=models.CASCADE)
    servidor_afastamento = models.ForeignKeyPlus(ServidorAfastamento, on_delete=models.CASCADE)
    afastamento = models.ForeignKeyPlus(AfastamentoSiape, on_delete=models.CASCADE)
    validado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='servidorafastamento_atualizado_por', on_delete=models.CASCADE
    )
    validado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Afastamento do Servidor'
        verbose_name_plural = 'Afastamentos dos Servidores'


class ProcessamentoResultado(models.ModelPlus):
    edital = models.ForeignKeyPlus('Edital', verbose_name='Edital')
    arquivo_log = models.FileFieldPlus(
        upload_to='remanejamento/processamento_resultado/',
        validators=[FileExtensionValidator(allowed_extensions=['txt'])],
        null=False,
        blank=False,
        max_file_size=settings.DEFAULT_FILE_UPLOAD_MAX_SIZE,
    )
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='processamento_resultado_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Processamento de Resultado de Remoção Interna'
        verbose_name_plural = 'Processamentos de Resultados de Remoção Interna'

    def save(self, *args, **kwargs):
        if not self.pk and not self.arquivo_log:
            # Criar um arquivo de log inicial
            storage = default_storage
            storage.file_overwrite = True
            conteudo = f'Log do Processamento de Resultado para Edital {self.edital} criado em {datetime.datetime.now()}'
            nome_arquivo = f'remanejamento/processamento_resultado/edital_pk_{self.edital.pk}_{datetime.datetime.now().isoformat()}.txt'
            storage.save(nome_arquivo, ContentFile(conteudo.encode()))
            self.arquivo_log.name = nome_arquivo

        user = tl.get_user()
        if user:
            self.atualizado_em = datetime.datetime.now()
            self.atualizado_por = user.get_vinculo()
        super().save(*args, **kwargs)

    def salvar_log(self, conteudo):
        storage = default_storage
        storage.file_overwrite = True
        with storage.open(self.arquivo_log.name, 'rb'):
            storage.save(self.arquivo_log.name, ContentFile(conteudo))


class VagaEdital(models.ModelPlus):
    """
    Registra a quantidade de vagas definidas por cargo para Edital de Remoçao Interna
    """

    edital = models.ForeignKeyPlus('Edital', verbose_name='Edital')
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', blank=True)
    cargo = models.ForeignKeyPlus('rh.CargoEmprego', verbose_name='Cargo')
    qtd_edital = models.PositiveIntegerFieldPlus('Quantidade de vagas no edital', null=False, blank=False, min_value=0)
    qtd_remanescente = models.PositiveIntegerFieldPlus('Quantidade de vagas remanescentes', null=False, blank=False, min_value=0)

    # Áreas - TAE
    cargo_emprego_area = models.ForeignKeyPlus(
        'rh.CargoEmpregoArea', verbose_name='Área do Cargo', null=True, blank=True, related_name='vagaedital_cargoempregoarea'
    )
    areas_correlatas = models.ManyToManyFieldPlus('rh.CargoEmpregoArea', verbose_name='Áreas Correlatas', blank=True)
    # Cargos distintos no SIAPE que concorrem às vagas deste cargo (ex.: ODONTOLOGO - 30H - DEC JUD concorre com ODONTOLOGO - 40 HORAS)
    cargos_correlatos = models.ManyToManyFieldPlus(
        'rh.CargoEmprego', verbose_name='Cargos Correlatos', blank=True, related_name='vagaedital_cargos_correlatos'
    )

    # Disciplinas - Docente
    disciplina = models.ForeignKeyPlus('edu.Disciplina', verbose_name='Disciplina', null=True, blank=True, related_name='vagaedital_disciplina')
    disciplinas_correlatas = models.ManyToManyFieldPlus('edu.Disciplina', verbose_name='Disciplinas Correlatas', blank=True)
    possui_concurso_vigente = models.BooleanFieldPlus(
        'Possui concurso vigente para o cargo?', default=False, help_text='Indica se há concurso público vigente para o cargo/disciplina.'
    )

    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='vagaedital_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Vaga por Cargo do Edital'
        verbose_name_plural = 'Vagas por Cargos do Edital'

    def __str__(self):
        if self.edital.eh_edital_remocao_docente():
            return f'{self.disciplina}'
        else:
            return f'{self.get_cargo_area()}'

    def get_cargo_area(self):
        cargo_area = None
        if self.cargo_emprego_area:
            cargo_area = f'{self.cargo.nome} - {self.cargo_emprego_area.descricao}'
        else:
            cargo_area = self.cargo.nome
        return cargo_area

    def pode_excluir(self):
        cargos = [self.cargo, *self.cargos_correlatos.all()]
        return (
            not InscricaoContemplada.objects.filter(inscricao__edital=self.edital, inscricao__servidor__cargo_emprego__in=cargos).exists()
            and not self.edital.resultado_final_foi_homologado()
        )


class ServidorTempoAdicionalRemocaoInterna(models.ModelPlus):
    """
    Cadastro de periodo adicional de tempo de exercício para fins de remoção interna mediante justiticativa. Exemplo: Adição de tempo em outro orgão
    """

    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    data_inicio = models.DateFieldPlus('Data de início', null=False, blank=False)
    data_fim = models.DateFieldPlus('Data de término', null=False, blank=False)
    quantidade_dias = models.PositiveIntegerFieldPlus('Total de dias', null=False, blank=False, min_value=0)
    justificativa = models.TextField('Justificativa', null=False, blank=False)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        verbose_name='Atualizado Por',
        related_name='tempo_adicional_remocaointerna_atualizado_por',
        on_delete=models.CASCADE,
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Tempo Adicional de Exercício para Remoção Interna'
        verbose_name_plural = 'Tempos Adicionais de Exercício para Remoção Interna'

    def __str__(self):
        return f'{self.servidor} - {self.quantidade_dias} dias'

    def save(self, *args, **kwargs):
        """
        O método foi sobrescrito para preencher automaticamente o campo ``atualizado_em``, ``atualizado_por`` e quantidade de dias.
        """
        if self.data_inicio and self.data_fim:
            self.quantidade_dias = (self.data_fim - self.data_inicio).days + 1
        user = tl.get_user()
        if user:
            self.atualizado_em = datetime.datetime.now()
            self.atualizado_por = user.get_vinculo()

        super().save(*args, **kwargs)
