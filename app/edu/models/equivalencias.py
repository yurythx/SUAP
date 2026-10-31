from djtools.db import models
from django.db.models import Q
from edu.models.atividades import AtividadeCurricularExtensao
from edu.models.cadastros_gerais import SituacaoMatricula
from edu.models.historico import AproveitamentoEstudo
from edu.models.logs import LogModel
from django.db import transaction


class EquivalenciaComponente(LogModel):
    SEARCH_FIELDS = (
        'componentes__descricao',
        'componentes__sigla',
        'equivalentes__descricao',
        'equivalentes__sigla',
    )

    componentes = models.ManyToManyFieldPlus('edu.componente', verbose_name='Componentes A', related_name='eq1')
    equivalentes = models.ManyToManyFieldPlus('edu.componente', verbose_name='Componentes B', related_name='eq2')
    ativa = models.BooleanField(verbose_name='Ativa', default=True)

    simples = models.BooleanField(verbose_name='Simples', null=True, blank=True)
    aprovada = models.BooleanField(verbose_name='Aprovada', null=True, blank=True)

    automatica = models.BooleanField(verbose_name='Automática', default=False)

    class Meta:
        verbose_name = 'Equivalência de Componente'
        verbose_name_plural = 'Equivalências de Componentes'

    def get_absolute_url(self):
        return f'/edu/equivalenciacomponente/{self.pk}/'

    def is_aprovada(self):
        qs = self.avaliadorequivalenciacomponente_set
        return qs.count() and qs.count() == qs.filter(aprovada=True).count()

    @transaction.atomic()
    def excluir_registros(self):
        qs = self.aproveitamentocomponente_set.filter(matricula_periodo__aluno__situacao_id__in=SituacaoMatricula.SITUACOES_CURSANDO)
        AtividadeCurricularExtensao.objects.filter(
            id_referencia__in=qs.values_list('pk', flat=True), tipo_referencia__model='aproveitamentocomponente'
        ).delete()
        qs.delete()
        EquivalenciaComponente.objects.filter(pk=self.pk).update(automatica=False)

    def pode_ser_excluida(self):
        return not self.aproveitamentocomponente_set.exists()

    def cancelar_avaliacao(self, pk):
        if self.pode_ser_excluida():
            avaliacao = self.avaliadorequivalenciacomponente_set.filter(pk=pk).first()
            if avaliacao:
                avaliacao.aprovada = None
                avaliacao.data_avaliacao = None
                avaliacao.observacao = None
                avaliacao.save()

    def pode_adicionar_avaliador(self, user):
        return self.aprovada is None and user.has_perm('edu.change_equivalenciacomponente')

    def identificar_registros_equivalencia(self, gerar=False):
        registros = []
        for ecm in self.equivalenciacomponentematriz_set.all():
            registros.extend(ecm.identificar_registros_equivalencia(gerar=gerar))
        if gerar:
            EquivalenciaComponente.objects.filter(pk=self.pk).update(automatica=True)
        return registros

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        EquivalenciaComponente.objects.filter(pk=self.pk).update(
            simples=EquivalenciaComponente.objects.filter(pk=self.pk).values_list('componentes', 'equivalentes').count() == 1
        )


class EquivalenciaComponenteMatriz(LogModel):
    equivalencia_componente = models.ForeignKeyPlus(EquivalenciaComponente, verbose_name='Equivalência de Componente')
    matriz_origem = models.ForeignKeyPlus('edu.matriz', verbose_name='Matriz A', related_name='eq1')
    matriz_destino = models.ForeignKeyPlus('edu.matriz', verbose_name='Matriz B', related_name='eq2')
    chave_unica_1 = models.CharField('Chave 1', null=True, max_length=255)
    chave_unica_2 = models.CharField('Chave 2', null=True, max_length=255)

    class Meta:
        verbose_name = 'Matrizes de Equivalência de Componente'
        verbose_name_plural = 'Matrizes de Equivalências de Componentes'

    def gerar_chaves(self, ids_componentes, ids_equivalentes, id_matriz_origem, id_matriz_destino):
        ids_componentes.sort()
        ids_equivalentes.sort()
        ka = '-'.join([str(i) for i in ids_componentes])
        kb = '-'.join([str(i) for i in ids_equivalentes])
        self.chave_unica_1 = ':'.join([ka, kb, str(id_matriz_origem), str(id_matriz_destino)])
        self.chave_unica_2 = ':'.join([kb, ka, str(id_matriz_destino), str(id_matriz_origem)])

    def save(self, *args, **kwargs):
        if self.chave_unica_1 is None or self.chave_unica_2 is None:
            self.gerar_chaves(
                list(self.equivalencia_componente.componentes.values_list('pk', flat=True)),
                list(self.equivalencia_componente.equivalentes.values_list('pk', flat=True)),
                self.matriz_origem_id,
                self.matriz_destino_id,
            )
        super().save(*args, **kwargs)

    def processar_alunos(self, qs_aluno, ids_componentes_aluno, ids_componentes_equivalentes, gerar, registros):
        from edu.models import Aluno, MatriculaDiario

        if ids_componentes_equivalentes:
            for id_componente in ids_componentes_equivalentes:
                qs_aluno_md = qs_aluno.filter(
                    matriculaperiodo__matriculadiario__situacao=MatriculaDiario.SITUACAO_APROVADO,
                    matriculaperiodo__matriculadiario__diario__componente_curricular__componente_id=id_componente,
                )

                qs_aluno_rh = qs_aluno.filter(
                    matriculaperiodo__registrohistorico__situacao=MatriculaDiario.SITUACAO_APROVADO,
                    matriculaperiodo__registrohistorico__componente_id=id_componente,
                )

                qs_aluno_aproveitamento = qs_aluno.filter(
                    matriculaperiodo__aproveitamentoestudo__componente_curricular__componente_id=id_componente,
                )

            pks = []
            pks.extend(qs_aluno_md.values_list('pk', flat=True))
            pks.extend(qs_aluno_rh.values_list('pk', flat=True))
            pks.extend(qs_aluno_aproveitamento.values_list('pk', flat=True))

            alunos_distintos = list(
                Aluno.objects.filter(pk__in=set(pks))
                .select_related('matriz', 'matriz__estrutura')
                .only(
                    'id',
                    'matricula',
                    'matriz__id',
                    'matriz__estrutura__proitec',
                    'curso_campus',
                    'situacao_id',
                    'matriz__estrutura__media_certificacao_conhecimento',
                )
            )

            # Todos os alunos deste lote compartilham a mesma matriz (filtro por matriz_id na origem);
            # pré-carrega os componentes cumpridos em lote para evitar N+1 no loop abaixo.
            if alunos_distintos:
                Aluno.calcular_componentes_cumpridos_em_lote(alunos_distintos)
            for aluno in alunos_distintos:
                cumpridos = aluno.get_ids_componentes_cumpridos()
                for id_componente in ids_componentes_aluno:
                    if id_componente not in cumpridos:
                        matricula_diario = MatriculaDiario.objects.filter(
                            matricula_periodo__aluno_id=aluno.id,
                            situacao=MatriculaDiario.SITUACAO_CURSANDO,
                            diario__componente_curricular__componente_id=id_componente,
                        )
                        if gerar:
                            self.gerar_registro_equivalencia(aluno, id_componente, ids_componentes_equivalentes, matricula_diario)
                        registros.append([aluno, id_componente, ids_componentes_equivalentes, matricula_diario])

    def identificar_registros_equivalencia(self, aluno=None, gerar=False):
        from edu.models import Aluno, SituacaoMatricula

        registros = []

        # Obter alunos A e B
        alunos_A = Aluno.objects.filter(
            situacao__in=SituacaoMatricula.SITUACOES_CURSANDO,
            matriz_id=self.matriz_origem_id,
        ).filter(
            Q(matriculaperiodo__matriculadiario__diario__componente_curricular__matriz_id=self.matriz_destino_id)
            | Q(matriculaperiodo__registrohistorico__componente__componentecurricular__matriz_id=self.matriz_destino_id)
            | Q(matriculaperiodo__aproveitamentoestudo__componente_curricular__matriz_id=self.matriz_destino_id)
        )
        alunos_B = Aluno.objects.filter(
            situacao__in=SituacaoMatricula.SITUACOES_CURSANDO,
            matriz_id=self.matriz_destino_id,
        ).filter(
            Q(matriculaperiodo__matriculadiario__diario__componente_curricular__matriz_id=self.matriz_origem_id)
            | Q(matriculaperiodo__registrohistorico__componente__componentecurricular__matriz_id=self.matriz_origem_id)
            | Q(matriculaperiodo__aproveitamentoestudo__componente_curricular__matriz_id=self.matriz_origem_id)
        )

        # Filtrar por aluno, se fornecido
        if aluno:
            alunos_A = alunos_A.filter(pk=aluno.id).distinct()
            alunos_B = alunos_B.filter(pk=aluno.id).distinct()

        if alunos_A.exists() or alunos_B.exists():
            ids_componentes_A = self.equivalencia_componente.componentes.values_list('pk', flat=True)
            ids_componentes_B = self.equivalencia_componente.equivalentes.values_list('pk', flat=True)

            # Processar alunos A
            if alunos_A.exists():
                self.processar_alunos(alunos_A, ids_componentes_A, ids_componentes_B, gerar, registros)

            # Processar alunos B
            if alunos_B.exists():
                self.processar_alunos(alunos_B, ids_componentes_B, ids_componentes_A, gerar, registros)

        return registros

    @transaction.atomic()
    def gerar_registro_equivalencia(self, aluno, id_equivalente, ids_componentes, matricula_diario):
        from edu.models import AproveitamentoComponente, MatriculaDiario, RegistroHistorico

        componente_curricular = aluno.matriz.componentecurricular_set.get(componente=id_equivalente)
        matricula_periodo = aluno.get_ultima_matricula_periodo()
        aproveitamento = AproveitamentoComponente.objects.filter(
            matricula_periodo=matricula_periodo, componente_curricular=componente_curricular
        ).first()
        if aproveitamento is None:
            matriculas_diario = set()
            registro_historico = set()
            aproveitamentos = set()

            qs_md = MatriculaDiario.objects.filter(matricula_periodo__aluno_id=aluno.id, situacao=MatriculaDiario.SITUACAO_APROVADO)
            qs_rh = RegistroHistorico.objects.filter(matricula_periodo__aluno_id=aluno.id, situacao=MatriculaDiario.SITUACAO_APROVADO)
            qs_aproveitamento = AproveitamentoEstudo.objects.filter(matricula_periodo__aluno_id=aluno.id)

            for id_componente in ids_componentes:
                md = qs_md.filter(diario__componente_curricular__componente_id=id_componente).first()
                if md:
                    matriculas_diario.add(md)
                else:
                    rh = qs_rh.filter(componente_id=id_componente).first()
                    if rh:
                        registro_historico.add(rh)
                    else:
                        apr = qs_aproveitamento.filter(componente_curricular__componente_id=id_componente).first()
                        if apr:
                            aproveitamentos.add(apr)

            if registro_historico or matriculas_diario or aproveitamentos:
                aproveitamento = AproveitamentoComponente.objects.create(
                    matricula_periodo=matricula_periodo,
                    componente_curricular=componente_curricular,
                    equivalencia_componente=self.equivalencia_componente,
                )
                aproveitamento.matriculas_diario.set(matriculas_diario)
                aproveitamento.registros_historico.set(registro_historico)
                aproveitamento.aproveitamentos_estudo.set(aproveitamentos)

                ch_extensao = componente_curricular.get_ch_extensao_a_registrar()

                if ch_extensao:
                    atividade = AtividadeCurricularExtensao.registrar(
                        aluno,
                        type(aproveitamento),
                        aproveitamento.pk,
                        ch_extensao,
                        componente_curricular.componente.descricao_historico,
                        True,
                        True,
                        matricula_periodo,
                    )

                    if atividade:
                        ids_atividades_substituidas = set()
                        ids_md = qs_md.filter(diario__componente_curricular__componente_id__in=ids_componentes).values_list('id', flat=True)
                        ids_atividades_substituidas.update(
                            AtividadeCurricularExtensao.objects.filter(
                                id_referencia__in=ids_md, tipo_referencia__model='matriculadiario'
                            ).values_list('id', flat=True)
                        )
                        ids_rh = qs_rh.filter(componente_id__in=ids_componentes).values_list('id', flat=True)
                        ids_atividades_substituidas.update(
                            AtividadeCurricularExtensao.objects.filter(
                                id_referencia__in=ids_rh, tipo_referencia__model='registrohistorico'
                            ).values_list('id', flat=True)
                        )
                        AtividadeCurricularExtensao.objects.filter(id__in=ids_atividades_substituidas).update(substituida=atividade)
                        aluno.atualizar_situacao('Substituição de atividade curricular de extensão')

        if matricula_diario:
            matricula_diario.delete()


class AvaliadorEquivalenciaComponente(LogModel):
    SEARCH_FIELDS = 'vinculo__pessoa__nome', 'vinculo__user__username'

    equivalencia_componente = models.ForeignKeyPlus(EquivalenciaComponente, verbose_name='Equivalência de Componente')
    vinculo = models.ForeignKeyPlus('comum.vinculo', verbose_name='Avaliador', limit_choices_to={'tipo_relacionamento__model': 'servidor'})
    aprovada = models.BooleanField(verbose_name='Aprovada', null=True)
    data_avaliacao = models.DateTimeField(verbose_name='Data da Avaliação', null=True)
    observacao = models.TextField(verbose_name='Observação', null=True)

    class Meta:
        verbose_name = 'Avaliador de Equivalência de Componente'
        verbose_name_plural = 'Avaliadores de Equivalências de Componentes'

    def can_delete(self, user=None):
        return self.aprovada is None and self.equivalencia_componente.aprovada is None and user.has_perm('edu.delete_avaliadorequivalenciacomponente')
