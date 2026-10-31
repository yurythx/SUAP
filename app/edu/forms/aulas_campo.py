import datetime
import math
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError

from comum.models import Ano, Configuracao
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from djtools.templatetags.filters import format_, in_group
from djtools.utils import adicionar_mes, human_str, send_mail
from edu.models import (
    Aluno,
    AlunoAulaCampo,
    AulaCampo,
    ConfiguracaoSeguro,
    CursoCampus,
    Diario,
    Diretoria,
    Turma,
)
from rh.models import Servidor, UnidadeOrganizacional


class ConfiguracaoSeguroForm(forms.ModelFormPlus):
    valor_repasse_pessoa = forms.CharFieldPlus(
        label='Valor do Repasse por Pessoa', help_text='Esse campo pode ter várias casas decimais e devem ser separadas por "." ao invés de ",'
    )
    fiscais = forms.MultipleModelChoiceFieldPlus(Servidor.objects, required=True, label='Responsáveis pela Fiscalização')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fiscais'].queryset = Servidor.objects.filter(ativo=True)

    def clean_data_fim_contrato(self):
        if self.cleaned_data['data_fim_contrato'] < self.cleaned_data['data_inicio_contrato']:
            raise ValidationError('A data de término do contrato não pode ser menor que a data de início do contrato.')

        return self.cleaned_data['data_fim_contrato']

    def clean_valor_contrato(self):
        if self.cleaned_data['valor_contrato'] < 0:
            raise ValidationError('O valor do contrato deve ser maior que zero.')

        return self.cleaned_data['valor_contrato']

    def clean_valor_repasse_pessoa(self):
        try:
            from decimal import Decimal

            valor_repasse_pessoa = Decimal(self.cleaned_data['valor_repasse_pessoa'].replace(',', '.'))

            if valor_repasse_pessoa < 0:
                raise ValidationError('O valor do repasse por pessoa deve ser maior que zero.')

            return valor_repasse_pessoa
        except Exception:
            raise ValidationError('O valor do repasse por pessoa deve ser um número decimal')

    class Meta:
        model = ConfiguracaoSeguro
        exclude = ()


class AulaCampoForm(forms.ModelFormPlus):
    configuracao_seguro = forms.ModelChoiceField(ConfiguracaoSeguro.objects, label='Configuração de Seguro')
    uo = forms.ModelChoiceField(UnidadeOrganizacional.locals, label='Campus')
    descricao = forms.CharFieldPlus(label='Descrição', max_length=300, width=500)
    responsaveis = forms.MultipleModelChoiceFieldPlus(Servidor.objects, required=True, label='Servidores responsáveis pela Aula')
    arquivo = forms.FileFieldPlus(
        label='Relação de Alunos Participantes',
        help_text='O arquivo deve ser no formato "xlsx", sem cabeçalho, e contendo a matrícula na primeira coluna.',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not in_group(self.request.user, 'Administrador Acadêmico'):
            if self.instance.situacao != AulaCampo.SITUACAO_AGENDADA:
                self.fields['configuracao_seguro'].widget.attrs['disabled'] = 'disabled'
                self.fields['uo'].widget.attrs['disabled'] = 'disabled'
                self.fields['descricao'].widget.attrs['readonly'] = 'readonly'
                self.fields['finalidade'].widget.attrs['readonly'] = 'readonly'
                self.fields['roteiro'].widget.attrs['readonly'] = 'readonly'
                self.fields['data_partida'].widget.attrs['readonly'] = 'readonly'
                self.fields['data_chegada'].widget.attrs['readonly'] = 'readonly'
                self.fields['responsaveis'].widget.attrs['disabled'] = 'disabled'
                self.fields['arquivo'].widget.attrs['disabled'] = 'disabled'

        self.fields['configuracao_seguro'].queryset = ConfiguracaoSeguro.objects.filter(ativa=True)
        self.fields['responsaveis'].queryset = Servidor.objects.filter(ativo=True)
        self.matriculas_alunos = []

    def clean_responsaveis(self):
        if 'configuracao_seguro' in self.cleaned_data and 'data_partida' in self.cleaned_data and 'data_chegada' in self.cleaned_data:
            configuracao_seguro = self.cleaned_data['configuracao_seguro']
            data_partida = self.cleaned_data['data_partida']
            data_chegada = self.cleaned_data['data_chegada']
            responsaveis = self.cleaned_data['responsaveis']

            qs = configuracao_seguro.aulacampo_set.filter(situacao=AulaCampo.SITUACAO_AGENDADA)
            qs = qs.exclude(data_chegada__lt=data_partida)
            qs = qs.exclude(data_partida__gt=data_chegada)

            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            for responsavel in responsaveis:
                qs = qs.filter(responsaveis__pk=responsavel.pk)

                if qs.exists():
                    aulas_conflitos = qs.values_list('pk', flat=True).distinct()
                    raise ValidationError(f'Existe conflito de datas para o(a) servidor(a) {responsavel}  nas aulas de campo {aulas_conflitos}.')

        return self.cleaned_data['responsaveis']

    def clean_arquivo(self):
        """Valida e processa o arquivo de planilha de alunos da aula de campo.

        Returns:
            dict: dados limpos do formulário.
        """
        import pandas as pd

        if self.cleaned_data['arquivo']:
            if 'configuracao_seguro' in self.cleaned_data and 'data_partida' in self.cleaned_data and 'data_chegada' in self.cleaned_data:
                try:
                    self.matriculas_alunos = []
                    matriculas_erro = []
                    arquivo = self.cleaned_data['arquivo']

                    # Alterado: Leitura usando Pandas
                    df = pd.read_excel(arquivo, header=None)

                    # Itera sobre a primeira coluna
                    for valor in df.iloc[:, 0]:
                        # Remove NaN e converte para string/int conforme lógica original
                        if pd.isna(valor):
                            continue
                        try:
                            matricula = int(valor)
                        except ValueError:
                            matricula = str(valor)

                        self.matriculas_alunos.append(matricula)

                except UnicodeEncodeError:
                    raise ValidationError(
                        'Não foi possível processar a planilha. Verfique se a primeira coluna contém somente as matrículas dos alunos.'
                    )
                except Exception:
                    raise ValidationError(
                        'Não foi possível processar a planilha. Verfique se o formato do arquivo é .xls ou .xlsx e se a primeira coluna contém as matrículas dos alunos.'
                    )

                matriculas_encontradas = Aluno.objects.filter(matricula__in=self.matriculas_alunos).values_list('matricula', flat=True)
                for matricula in self.matriculas_alunos:
                    if str(matricula) not in matriculas_encontradas:
                        matriculas_erro.append(matricula)

                if matriculas_erro:
                    raise forms.ValidationError(f'As matrículas {matriculas_erro} não foram encontradas.')

                qtd_alunos_selecionados = len(self.matriculas_alunos)
                configuracao_seguro = self.cleaned_data['configuracao_seguro']
                data_partida = self.cleaned_data['data_partida']
                data_chegada = self.cleaned_data['data_chegada']
                qtd_dias = (data_chegada - data_partida).days + 1
                gasto_previsto_aula = qtd_alunos_selecionados * qtd_dias * configuracao_seguro.valor_repasse_pessoa

                # Verificando conflitos de datas para os alunos
                qs = configuracao_seguro.aulacampo_set.filter(situacao=AulaCampo.SITUACAO_AGENDADA)
                qs = qs.exclude(data_chegada__lt=data_partida)
                qs = qs.exclude(data_partida__gt=data_chegada)

                if self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)

                for aluno in self.matriculas_alunos:
                    qs = qs.filter(alunos__matricula=aluno)

                    if qs.exists():
                        aulas_conflitos = qs.values_list('pk', flat=True).distinct()
                        aluno = Aluno.objects.get(matricula=aluno)
                        raise ValidationError(f'Existe conflito de datas para o(a) aluno(a) {aluno} nas aulas de campo {aulas_conflitos}.')

                if not configuracao_seguro.possui_saldo_suficiente(gasto_previsto_aula):
                    num_participantes_disponivel = configuracao_seguro.get_participantes_disponiveis(qtd_dias)
                    raise ValidationError(
                        f'Não existe saldo disponível para a quantidade de alunos selecionados. Você pode incluir até {num_participantes_disponivel:d} alunos.'
                    )
            else:
                raise ValidationError('Você precisa informar a configuração de seguro, a data de partida e a data de chegada.')

        return self.cleaned_data['arquivo']

    def clean(self):
        if (
            'configuracao_seguro' in self.cleaned_data
            and 'data_partida' in self.cleaned_data
            and 'data_chegada' in self.cleaned_data
            and 'responsaveis' in self.cleaned_data
        ):
            configuracao_seguro = self.cleaned_data['configuracao_seguro']

            if not in_group(self.request.user, 'Administrador Acadêmico'):
                if self.cleaned_data['data_partida'] < (datetime.datetime.today() + datetime.timedelta(days=1)).date():
                    raise ValidationError('A data de partida não pode ser menor que a data de amanhã.')

            if self.cleaned_data['data_chegada'] < self.cleaned_data['data_partida']:
                raise ValidationError('A data de chegada não pode ser menor que a data de partida.')

            if self.cleaned_data['data_chegada'] > configuracao_seguro.data_fim_contrato:
                raise ValidationError('A configuração de Seguro selecionada não estará mais vigente para a data da Aula.')

            qtd_responsaveis_atual = self.cleaned_data['responsaveis'].count()

            if self.instance.pk:
                qtd_responsaveis_anterior = self.instance.responsaveis.count()
            else:
                qtd_responsaveis_anterior = 0

            if qtd_responsaveis_anterior < qtd_responsaveis_atual:
                qtd_responsaveis = int(math.fabs(qtd_responsaveis_atual - qtd_responsaveis_anterior))

                data_partida = self.cleaned_data['data_partida']
                data_chegada = self.cleaned_data['data_chegada']
                qtd_dias = (data_chegada - data_partida).days + 1
                gasto_previsto_aula = qtd_responsaveis * qtd_dias * configuracao_seguro.valor_repasse_pessoa

                if not configuracao_seguro.possui_saldo_suficiente(gasto_previsto_aula):
                    num_participantes_disponivel = configuracao_seguro.get_participantes_disponiveis(qtd_dias)
                    raise ValidationError(
                        f'Não existe saldo disponível para a quantidade de responsáveis selecionados. Você pode incluir até {num_participantes_disponivel:d} responsáveis.',
                        'error',
                    )

        return self.cleaned_data

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.instance.save()

        for aluno in Aluno.objects.filter(matricula__in=self.matriculas_alunos).exclude(pk__in=self.instance.alunos.values_list('pk', flat=True)):
            aluno_aula = AlunoAulaCampo()
            aluno_aula.aluno = aluno
            aluno_aula.aula_campo = self.instance
            aluno_aula.save()

        return self.instance

    class Meta:
        model = AulaCampo
        exclude = ('situacao',)


class PesquisarAlunosForm(forms.FormPlus):
    SUBMIT_LABEL = 'Pesquisar'
    METHOD = 'GET'

    curso_campus = forms.ModelChoiceFieldPlus(
        CursoCampus.objects,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo__in')]),
    )
    turma = forms.ModelChoiceFieldPlus(Turma.objects.none(), required=False)
    diario = forms.ModelChoiceFieldPlus(
        Diario.objects.none(),
        help_text='Para encontrar um diário entre com a sigla do componente ou o id do diário.',
        widget=AutocompleteWidget(search_fields=Diario.SEARCH_FIELDS),
        required=False,
        label='Diário',
    )
    aluno = forms.ModelChoiceFieldPlus(Aluno.locals, required=False, widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals
        self.fields['turma'].queryset = Turma.locals

    def clean(self):
        if (
            not self.cleaned_data['curso_campus']
            and not self.cleaned_data['turma']
            and not self.cleaned_data['diario']
            and not self.cleaned_data['aluno']
        ):
            raise forms.ValidationError('Insira, no mínimo o curso, a turma, o diário ou o aluno nos filtros.')

        return self.cleaned_data

    def processar(self):
        qs = Aluno.objects.all()
        aluno = self.cleaned_data['aluno']
        curso_campus = self.cleaned_data['curso_campus']
        turma = self.cleaned_data['turma']
        diario = self.cleaned_data['diario']

        if curso_campus:
            qs = qs.filter(curso_campus=curso_campus)
        if turma:
            qs = qs.filter(curso_campus__ativo=True, matriculaperiodo__matriculadiario__diario__turma=turma)
        if diario:
            qs = qs.filter(matriculaperiodo__matriculadiario=diario)
        if aluno:
            qs = qs.filter(pk=aluno.pk)

        retorno = qs.distinct()

        return retorno


class EnviarPlanilhaMensalSeguroAulaCampoForm(forms.FormPlus):
    ano = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano', widget=forms.Select())
    mes = forms.MesField(label='Mês', empty_label=None)

    def __init__(self, configuracao_seguro, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configuracao_seguro = configuracao_seguro

    def processar(self):
        """Gera planilha mensal de seguro e envia por e-mail para a seguradora.

        Returns:
            bool: ``True`` se o e-mail foi enviado com sucesso, ``False`` caso contrário.
        """
        import pandas as pd

        ano_desejado = self.cleaned_data['ano']
        mes_desejado = self.cleaned_data['mes']
        primeiro_dia_mes = date(ano_desejado.ano, mes_desejado, 1)
        ultimo_dia_mes = adicionar_mes(date(ano_desejado.ano, mes_desejado, 1), 1) - timedelta(days=1)

        aulas_campo_mes = self.configuracao_seguro.aulacampo_set.filter(
            situacao=AulaCampo.SITUACAO_REALIZADA, data_partida__range=(primeiro_dia_mes, ultimo_dia_mes)
        ).order_by('data_partida')
        datas_aulas_campo = aulas_campo_mes.values_list('data_partida', 'data_chegada').distinct()

        if aulas_campo_mes.exists():
            subject = '[SUAP] Planilha de Participantes - Aula de Campo - {} a {}'.format(
                primeiro_dia_mes.strftime('%d/%m'), ultimo_dia_mes.strftime('%d/%m')
            )
            body = """
                Seguem em anexo as planilhas referentes às aulas de campo.
            """
            from_email = settings.DEFAULT_FROM_EMAIL
            to = self.configuracao_seguro.email_disparo_planilha.split(',')

            # Criando a planilha
            instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
            # Alterado: Extensão para .xlsx
            filename = '/tmp/{}_RelatorioMensal_{}_{}.xlsx'.format(
                instituicao, datetime.datetime.today().strftime('%Y'), primeiro_dia_mes.strftime('%m')
            )

            # Alterado: Usando Pandas ExcelWriter
            with pd.ExcelWriter(filename) as writer:
                # Percorrendo as datas e gerando as abas das planilhas com dias de chegada e partida iguais
                for data_partida, data_chegada in datas_aulas_campo:
                    aulas_campo_dia = aulas_campo_mes.filter(data_partida=data_partida, data_chegada=data_chegada)

                    # Nomeando a aba a partir da data de partida e chegada
                    if data_partida == data_chegada:
                        sheet_name = data_partida.strftime('%d_%m_%Y')
                    else:
                        sheet_name = '{}_a_{}'.format(data_partida.strftime('%d_%m_%Y'), data_chegada.strftime('%d_%m_%Y'))

                    rows_data = []
                    count = 0

                    for aula_campo in aulas_campo_dia:
                        # Inserindo os Responsáveis
                        for responsavel in aula_campo.responsaveis.all():
                            count += 1
                            row = [
                                human_str(count, blank='-'),
                                human_str(format_(responsavel.matricula), blank='-'),
                                human_str(format_(responsavel.cpf), blank='-'),
                                human_str(format_(responsavel.nome), blank='-'),
                                human_str(format_(responsavel.nascimento_data), blank='-'),
                                human_str(format_(responsavel.sexo), blank='-'),
                                human_str(format_('Servidor'), blank='-'),
                                human_str(aula_campo.roteiro, blank='-'),
                            ]
                            rows_data.append(row)

                        # Inserindo os Alunos
                        for aluno in aula_campo.alunos.all():
                            count += 1
                            row = [
                                human_str(count, blank='-'),
                                human_str(format_(aluno.matricula), blank='-'),
                                human_str(format_(aluno.pessoa_fisica.cpf), blank='-'),
                                human_str(format_(aluno.get_nome_social_composto()), blank='-'),
                                human_str(format_(aluno.pessoa_fisica.nascimento_data), blank='-'),
                                human_str(format_(aluno.pessoa_fisica.sexo), blank='-'),
                                human_str(format_('Aluno'), blank='-'),
                                human_str(aula_campo.roteiro, blank='-'),
                            ]
                            rows_data.append(row)

                    # Criando DataFrame e salvando na aba
                    columns = ['#', 'Matrícula', 'CPF', 'Nome', 'Data de Nascimento', 'Sexo', 'Tipo', 'Roteiro']
                    df = pd.DataFrame(rows_data, columns=columns)
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

            files = []
            files.append(filename)

            # Enviando o email para a seguradora
            send_mail(subject, body, from_email, to, files=files)
            return True
        return False
