from datetime import datetime

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.safestring import mark_safe

from comum.models import PrestadorServico
from comum.utils import get_setor_cppd, tl
from djtools import forms
from djtools.forms import AutocompleteWidget
from djtools.utils import send_mail
from processo_eletronico.models import Processo, TipoProcesso
from progressoes.assinatura import SuapAssinaturaForm
from rh import utils
from rh.models import Avaliador, Servidor, Situacao
from rsc.models import Avaliacao, ConfiguracaoRSC, ProcessoAvaliador, ProcessoRSC, TipoRsc, ValidacaoCPPD


class ProcessoRSCAddForm(forms.Form):
    rsc_pretendida = forms.ModelChoiceField(queryset=TipoRsc.objects.all(), label='RSC Pretendida')
    SUBMIT_LABEL = 'Adicionar'


class ProcessoRSCDocumentoExigidosForm(forms.ModelFormPlus):
    class Meta:
        model = ProcessoRSC
        fields = ('data_concessao_ultima_rt', 'data_exercio_carreira', 'data_conclusao_titulacao_rsc_pretendido')
        exclude = ()


class ProcessoRSCForm(forms.FormPlus):
    # fields que representam todos os arquivos do processo
    qtd_itens = forms.IntegerFieldPlus()
    data_referencia = forms.DateFieldPlus()
    nota_pretendida = forms.DecimalField()
    descricao = forms.CharField(label='Motivo de Saída', widget=forms.Textarea(), required=True)

    # relatório descritivo do processo
    introducao_relatorio_descritivo = forms.CharFieldPlus(max_length=10000, widget=forms.Textarea())
    conclusao_relatorio_descritivo = forms.CharFieldPlus(max_length=10000, widget=forms.Textarea())

    # datas documentos preliminares
    data_concessao_ultima_rt = forms.DateFieldPlus()
    data_exercio_carreira = forms.DateFieldPlus()
    data_conclusao_titulacao_rsc_pretendido = forms.DateFieldPlus()

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo', None)
        super().__init__(*args, **kwargs)
        if self.processo:
            if not self.processo.avaliado_pode_editar():
                self.fields['data_conclusao_titulacao_rsc_pretendido'].widget.attrs['disabled'] = 'disabled'
                self.fields['data_exercio_carreira'].widget.attrs['disabled'] = 'disabled'
                self.fields['data_concessao_ultima_rt'].widget.attrs['disabled'] = 'disabled'

    @staticmethod
    def factory_field_render_arquivo(processo, criterio, request):
        field_arquivo = forms.AjaxFileUploadField('/rsc/rsc_upload/', f'onCompleteUploadCriterio{criterio.id}')
        field_arquivo.widget.request = request
        field_arquivo.widget.params['criterio'] = criterio.id
        field_arquivo.widget.params['processo'] = processo.id
        return field_arquivo.widget.render('', '')

    @staticmethod
    def factory_field_render_qtd_itens(arquivo_instance):
        form_arquivo = ProcessoRSCForm()
        field_qtd_itens_name = f'Arquivo_{arquivo_instance.id}_qtd'
        field_qtd_itens_onkeyup = f'calcula_nota_pretendida(this, {arquivo_instance.criterio.fator}, {arquivo_instance.id}, {arquivo_instance.criterio.teto}, {arquivo_instance.criterio.diretriz_id}, {arquivo_instance.criterio.diretriz.tipo_rsc_id}, {arquivo_instance.criterio.diretriz.teto}, {arquivo_instance.criterio_id}, {arquivo_instance.criterio.diretriz.peso});'

        field_qtd_itens_onblur = "Processa_Salvamento('{}', {}, '{}', '{}');".format(
            'Autosalvar',
            arquivo_instance.processo_id,
            arquivo_instance.processo.tipo_rsc,
            arquivo_instance.processo.get_status_display(),
        )

        if (arquivo_instance.processo.avaliado_pode_editar()) and (tl.get_user().get_vinculo() == arquivo_instance.processo.servidor.get_vinculo()):
            field_qtd_itens = form_arquivo.fields['qtd_itens'].widget.render(
                field_qtd_itens_name,
                arquivo_instance.qtd_itens,
                {
                    'id': f'qtd_{arquivo_instance.id}',
                    'OnKeyUp': field_qtd_itens_onkeyup,
                    'onchange': field_qtd_itens_onkeyup + field_qtd_itens_onblur,
                    'onblur': field_qtd_itens_onkeyup + field_qtd_itens_onblur,
                },
            )
        else:
            field_qtd_itens = form_arquivo.fields['qtd_itens'].widget.render(
                field_qtd_itens_name,
                arquivo_instance.qtd_itens,
                {
                    'id': f'qtd_{arquivo_instance.id}',
                    'OnKeyUp': field_qtd_itens_onkeyup,
                    'onchange': field_qtd_itens_onkeyup + field_qtd_itens_onblur,
                    'onblur': field_qtd_itens_onkeyup + field_qtd_itens_onblur,
                    'disabled': 'disabled',
                },
            )

        return mark_safe('{} {}'.format(field_qtd_itens, f'Máx: {arquivo_instance.criterio.teto}'))

    @staticmethod
    def factory_field_render_data_referencia(arquivo_instance):
        form_arquivo = ProcessoRSCForm()
        field_data_referencia_name = f'Arquivo_{arquivo_instance.id}_data'
        field_data_referencia_onblur = "Processa_Salvamento('{}', {}, '{}', '{}');".format(
            'Autosalvar',
            arquivo_instance.processo_id,
            arquivo_instance.processo.tipo_rsc,
            arquivo_instance.processo.get_status_display(),
        )
        attrs = {'id': f'data_{arquivo_instance.id}', 'onchange': field_data_referencia_onblur}

        if not (arquivo_instance.processo.avaliado_pode_editar()) or tl.get_user().get_vinculo() != arquivo_instance.processo.servidor.get_vinculo():
            attrs['disabled'] = 'disabled'

        field_data_referencia = form_arquivo.fields['data_referencia'].widget.render(
            field_data_referencia_name, arquivo_instance.data_referencia, attrs
        )
        return field_data_referencia

    @staticmethod
    def factory_field_render_nota_pretendida(arquivo_instance):
        form_arquivo = ProcessoRSCForm()
        field_nota_pretendida_name = f'Arquivo_{arquivo_instance.id}_nota'
        # field_nota_pretendida = form_arquivo.fields['nota_pretendida'].widget.render(field_nota_pretendida_name,
        #                                                                               arquivo_instance.nota_pretendida, {'id': 'nota_%s' % arquivo_instance.id,
        #                                                                                                                  'type': 'hidden'})
        form_arquivo.fields['nota_pretendida'].widget = forms.HiddenInput(attrs={'id': f'nota_{arquivo_instance.id}'})
        return form_arquivo.fields['nota_pretendida'].widget.render(field_nota_pretendida_name, arquivo_instance.nota_pretendida)

    @staticmethod
    def factory_field_render_descricao(arquivo_instance):
        form_arquivo = ProcessoRSCForm()
        field_name = f'Arquivo_{arquivo_instance.id}_descricao'
        field_onblur = "Processa_Salvamento('{}', {}, '{}', '{}');".format(
            'Autosalvar',
            arquivo_instance.processo_id,
            arquivo_instance.processo.tipo_rsc,
            arquivo_instance.processo.get_status_display(),
        )

        if (arquivo_instance.processo.avaliado_pode_editar() or arquivo_instance.processo.avaliado_pode_ajustar()) and (
            tl.get_user().get_vinculo() == arquivo_instance.processo.servidor.get_vinculo()
        ):
            field_descricao = form_arquivo.fields['descricao'].widget.render(
                field_name,
                arquivo_instance.descricao,
                {'id': f'descricao_{arquivo_instance.id}', 'onchange': field_onblur, 'class': 'textarea_descricao', 'style': 'width: 100%'},
            )
        else:
            field_descricao = form_arquivo.fields['descricao'].widget.render(
                field_name,
                arquivo_instance.descricao,
                {
                    'id': f'descricao_{arquivo_instance.id}',
                    'onchange': field_onblur,
                    'class': 'textarea_descricao',
                    'style': 'width: 100%',
                    'disabled': 'disabled',
                },
            )

        return field_descricao


class DataConclusaoTitulacaoRSCForm(forms.FormPlus):
    arquivo = forms.AjaxFileUploadField('/rsc/rsc_upload_documentos_exigidos/', 'onCompleteUploadDataConclusaoTitulacaoRSC', multiple=False)

    def __init__(self, *args, **kwargs):
        processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].widget.request = self.request
        self.fields['arquivo'].widget.params['processo'] = processo.id
        self.fields['arquivo'].widget.params['tipo'] = 'TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO'


class DataExercicioCarreiraForm(forms.FormPlus):
    arquivo = forms.AjaxFileUploadField('/rsc/rsc_upload_documentos_exigidos/', 'onCompleteUploadDataExercicioCarreira', multiple=False)

    def __init__(self, *args, **kwargs):
        processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].widget.request = self.request
        self.fields['arquivo'].widget.params['processo'] = processo.id
        self.fields['arquivo'].widget.params['tipo'] = 'INICIO_EXERCIO_CARREIRA'


class DocumentosExigidosForm(forms.FormPlus):
    arquivo = forms.AjaxFileUploadField('/rsc/rsc_upload_documentos_exigidos/', 'onCompleteUploadDocumentosExigidos', multiple=False)

    def __init__(self, *args, **kwargs):
        processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].widget.request = self.request
        self.fields['arquivo'].widget.params['processo'] = processo.id
        self.fields['arquivo'].widget.params['tipo'] = 'CONCESSAO_ULTIMA_RT'


class ValidacaoCPPDForm(forms.ModelFormPlus):
    processo = forms.ModelChoiceFieldPlus(ProcessoRSC.objects, label='Processo', widget=forms.HiddenInput())
    tipo_rsc = forms.CharField(max_length=100, widget=forms.HiddenInput())
    motivo_rejeicao = forms.CharField(widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        if 'processo' in kwargs:
            self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        if self.processo:
            self.fields['processo'].initial = self.processo
            self.fields['tipo_rsc'].initial = self.processo.tipo_rsc
        self.fields['data_conclusao_titulacao_rsc_pretendido_validada'].widget.attrs['disabled'] = 'disabled'
        self.fields['data_exercio_carreira_validada'].widget.attrs['disabled'] = 'disabled'
        self.fields['data_concessao_ultima_rt_validada'].widget.attrs['disabled'] = 'disabled'

    class Meta:
        model = ValidacaoCPPD
        exclude = ()


class JustificativaDesistenciaForm(forms.FormPlus):
    avaliacao = forms.ModelChoiceFieldPlus(Avaliacao.objects, label='Avaliação', widget=forms.HiddenInput())
    tipo = forms.ChoiceField(label='Tipo', choices=Avaliacao.TIPO_DESISTENCIA_CHOICES)
    justificativa = forms.CharFieldPlus(max_length=10000, widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        if 'avaliacao' in kwargs:
            self.avaliacao = kwargs.pop('avaliacao')
        super().__init__(*args, **kwargs)
        if self.avaliacao:
            self.fields['avaliacao'].initial = self.avaliacao.id


class RecusaAvaliacaoForm(forms.FormPlus):
    processo_avaliador = forms.ModelChoiceFieldPlus(ProcessoAvaliador.objects, label='Processo Avaliador', widget=forms.HiddenInput())
    tipo = forms.ChoiceField(label='Tipo', choices=ProcessoAvaliador.TIPO_RECUSA_CHOICES)
    motivo_recusa = forms.CharFieldPlus(label='Motivo da Recusa', max_length=10000, widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        if 'processo_avaliador' in kwargs:
            self.processo_avaliador = kwargs.pop('processo_avaliador')
        super().__init__(*args, **kwargs)
        if self.processo_avaliador:
            self.fields['processo_avaliador'].initial = self.processo_avaliador.id

    @transaction.atomic
    def processar(self):
        if self.cleaned_data.get('processo_avaliador'):
            processo_id = self.cleaned_data.get('processo_avaliador').id
        else:
            raise forms.ValidationError('Processo Avaliador não setado!')
        processo_avaliador = ProcessoAvaliador.objects.get(id=processo_id)
        processo_avaliador.rejeitar(self.cleaned_data)


class RejeitarProcessoCPPDForm(forms.FormPlus):
    processo = forms.ModelChoiceFieldPlus(ProcessoRSC.objects, label='Processo RSC', widget=forms.HiddenInput())
    tipo = forms.ChoiceField(label='Tipo', choices=ProcessoAvaliador.TIPO_RECUSA_CHOICES)
    motivo_recusa = forms.CharFieldPlus(label='Motivo da Recusa', max_length=10000, widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        if 'processo' in kwargs:
            self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        if self.processo:
            self.fields['processo'].initial = self.processo.id

    @transaction.atomic
    def processar(self):
        if self.cleaned_data.get('processo'):
            processo_id = self.cleaned_data.get('processo').id
        else:
            raise forms.ValidationError('Processo não encontrado.')

        processo = ProcessoRSC.objects.get(id=processo_id)
        motivo_recusa = self.cleaned_data.get('motivo_recusa')
        if not motivo_recusa or motivo_recusa == '':
            raise Exception('O motivo da rejeição deve ser preenchido.')
        else:
            validacaoCPPD = ValidacaoCPPD()
            validacaoCPPD.acao = validacaoCPPD.ACAO_REJEITAR
            validacaoCPPD.processo = processo
            validacaoCPPD.validador = self.request.user.get_relacionamento()
            validacaoCPPD.motivo_rejeicao = motivo_recusa
            validacaoCPPD.save()
            processo.status = ProcessoRSC.STATUS_REJEITADO
            processo.save()


class AvaliadorForm(forms.FormPlus):
    processo = forms.ModelChoiceFieldPlus(ProcessoRSC.objects, label='Processo', widget=forms.HiddenInput())
    avaliador_interno = forms.MultipleModelChoiceFieldPlus(Servidor.objects.docentes_permanentes(), required=False)
    avaliador_externo = forms.MultipleModelChoiceFieldPlus(PrestadorServico.objects.all(), required=False)

    def __init__(self, *args, **kwargs):
        if 'processo' in kwargs:
            self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['avaliador_externo'].queryset = PrestadorServico.objects.filter(
            vinculos__avaliador__isnull=False, vinculos__avaliador__ativo=True
        )
        # Ativos permanentes e ativos em outro órgão (cedidos) podem compor a banca como avaliador interno
        self.fields['avaliador_interno'].queryset = (
            Servidor.objects.docentes()
            .filter(situacao__codigo__in=Situacao.situacoes_servidores_de_carreira_vinculada_ao_orgao())
            .exclude(vinculos__avaliador__in=Avaliador.objects.filter(ativo=False))
        )
        if self.processo:
            self.fields['processo'].initial = self.processo.id

    @transaction.atomic
    def processar(self, vinculo):
        if self.cleaned_data.get('processo'):
            processo_id = self.cleaned_data.get('processo').id
        else:
            raise forms.ValidationError('Processo não encontrado.')

        processo = ProcessoRSC.objects.get(id=processo_id)

        # configuração
        config = ConfiguracaoRSC.objects.first()
        if config is None:
            raise Exception('Configuração de email não encontrada.')

        erros = []
        erros += self._cadastrar_avaliadores_internos(processo, vinculo, config)
        erros += self._cadastrar_avaliadores_externos(processo, vinculo, config)

        if erros:
            raise forms.ValidationError(erros)

        #
        # Inicia as avaliações assim que houver ao menos um avaliador ativo, desde
        # que o processo ainda não esteja em avaliação. A banca completa (1 interno
        # + 2 externos) deixa de ser pré-requisito para iniciar; a conclusão do
        # processo continua exigindo 3 avaliações finalizadas.
        if processo.status != ProcessoRSC.STATUS_EM_AVALIACAO and processo.tem_algum_avaliador_ativo():
            processo.status = ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR
        processo.save()

    def _cadastrar_avaliadores_internos(self, processo, vinculo, config):
        """Cadastra os avaliadores internos selecionados (extraído de ``processar``).

        Cria o ``Avaliador`` quando ainda não existe, evita duplicatas no processo e
        registra cada ``ProcessoAvaliador`` — o primeiro como convidado
        (``AGUARDANDO_ACEITE``, com e-mail) e os demais como reserva (``EM_ESPERA``).
        Retorna a lista de mensagens de erro (vazia se não houver).
        """
        erros = []
        for avaliador_interno in self.cleaned_data.get('avaliador_interno'):
            check_avaliador_interno = Avaliador.objects.filter(vinculo__pessoa=avaliador_interno.pessoa_fisica.pessoa_ptr)
            if not check_avaliador_interno.exists():
                avaliador = Avaliador()
                avaliador.vinculo = avaliador_interno.vinculos.first()
                avaliador.email_contato = avaliador_interno.email_notificacao
                avaliador.save()

        avaliadores_internos = Avaliador.objects.filter(
            vinculo__id__in=self.cleaned_data.get('avaliador_interno').values_list('vinculos__id', flat=True)
        )

        qs_processo_avaliador = ProcessoAvaliador.objects.filter(processo=processo, tipo_avaliador=ProcessoAvaliador.AVALIADOR_INTERNO)
        if qs_processo_avaliador.filter(avaliador__in=avaliadores_internos).exists():
            avaliadores_internos_problema = []
            for ava in avaliadores_internos:
                if qs_processo_avaliador.filter(avaliador=ava).exists():
                    avaliadores_internos_problema.append(ava.pessoa_fisica.nome)
            erros.append('Os seguintes avaliadores internos já estão no processo: {}'.format(', '.join(avaliadores_internos_problema)))
        else:
            count_avaliador_interno = qs_processo_avaliador.filter(status__in=[1, 2, 3]).count()
            for avaliador_interno in avaliadores_internos:
                enviar_email = False
                processoAvaliador = ProcessoAvaliador()
                if count_avaliador_interno == 0:
                    processoAvaliador.status = ProcessoAvaliador.AGUARDANDO_ACEITE
                    processoAvaliador.data_convite = datetime.today()
                    enviar_email = True
                else:
                    processoAvaliador.status = ProcessoAvaliador.EM_ESPERA
                processoAvaliador.processo = processo
                processoAvaliador.avaliador = avaliador_interno
                processoAvaliador.tipo_avaliador = ProcessoAvaliador.AVALIADOR_INTERNO
                processoAvaliador.responsavel_cadastro = vinculo
                processoAvaliador.save()
                count_avaliador_interno = count_avaliador_interno + 1

                if enviar_email:
                    dados = {
                        'NOME_AVALIADOR': str(avaliador_interno.vinculo.user.get_profile().nome),
                        'NOME_PROFESSOR_AVALIADO': str(processo.servidor.pessoa_fisica.nome),
                        'DATA_LIMITE_ACEITE_AVALIACAO': str(processoAvaliador.data_limite()),
                        'DIAS_PARA_AVALIACAO': config.dias_para_avaliacao,
                        'SITE_URL': settings.SITE_URL,
                    }
                    assunto = '[SUAP] Avaliação de Processo RSC'
                    mensagem = utils.substituir_marcacoes(config.email_professor_sorteado, dados)
                    send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [avaliador_interno.email_contato])

        return erros

    def _cadastrar_avaliadores_externos(self, processo, vinculo, config):
        """Cadastra os avaliadores externos selecionados (extraído de ``processar``).

        Mesma lógica dos internos, porém os dois primeiros entram como convidados
        (``AGUARDANDO_ACEITE``) e os demais como reserva (``EM_ESPERA``).
        Retorna a lista de mensagens de erro (vazia se não houver).
        """
        erros = []
        avaliadores_externos = []
        for avaliador_externo in self.cleaned_data.get('avaliador_externo'):
            check_avaliador_externo = Avaliador.objects.filter(vinculo=avaliador_externo.get_vinculo())
            if not check_avaliador_externo.exists():
                avaliador = Avaliador()
                avaliador.vinculo = avaliador_externo.vinculos.first()
                avaliador.save()
                avaliadores_externos.append(avaliador)
            else:
                avaliadores_externos.append(check_avaliador_externo[0])

        qs_processo_avaliador_externo = ProcessoAvaliador.objects.filter(processo=processo, tipo_avaliador=ProcessoAvaliador.AVALIADOR_EXTERNO)
        if qs_processo_avaliador_externo.filter(avaliador__in=avaliadores_externos).exists():
            avaliadores_externos_problema = []
            for ava in avaliadores_externos:
                if qs_processo_avaliador_externo.filter(avaliador=ava).exists():
                    avaliadores_externos_problema.append(ava.vinculo.pessoa.nome)
            erros.append('Os seguintes avaliadores externos já estão no processo: {}'.format(', '.join(avaliadores_externos_problema)))
        else:
            count_avaliador_externo = qs_processo_avaliador_externo.filter(status__in=[1, 2, 3]).count()
            for avaliador_externo in avaliadores_externos:
                enviar_email = False
                processoAvaliador = ProcessoAvaliador()
                if count_avaliador_externo < 2:
                    processoAvaliador.status = ProcessoAvaliador.AGUARDANDO_ACEITE
                    processoAvaliador.data_convite = datetime.today()
                    enviar_email = True
                else:
                    processoAvaliador.status = ProcessoAvaliador.EM_ESPERA

                processoAvaliador.responsavel_cadastro = vinculo
                processoAvaliador.processo = processo
                processoAvaliador.avaliador = avaliador_externo
                processoAvaliador.tipo_avaliador = ProcessoAvaliador.AVALIADOR_EXTERNO
                processoAvaliador.save()
                count_avaliador_externo = count_avaliador_externo + 1

                if enviar_email:
                    dados = {
                        'NOME_AVALIADOR': str(avaliador_externo.vinculo.user.get_profile().nome),
                        'NOME_PROFESSOR_AVALIADO': str(processo.servidor.pessoa_fisica.nome),
                        'DATA_LIMITE_ACEITE_AVALIACAO': str(processoAvaliador.data_limite()),
                        'DIAS_PARA_AVALIACAO': config.dias_para_avaliacao,
                        'SITE_URL': settings.SITE_URL,
                    }
                    assunto = '[SUAP] Avaliação de Processo RSC'
                    mensagem = utils.substituir_marcacoes(config.email_professor_sorteado, dados)
                    send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [avaliador_externo.email_contato])

        return erros

    def clean_avaliador_interno(self):
        """
        validando avaliadores internos
        """
        avaliadores_internos = self.cleaned_data.get('avaliador_interno')
        if self.processo.servidor in avaliadores_internos:
            raise forms.ValidationError(f'Você não pode escolhe o próprio avaliado ({self.processo.servidor}) com sendo um avaliador.')

        return avaliadores_internos


class ProcessoAvaliadorForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.get('instance')
        if self.instance:
            if self.instance.status == 4:
                self.base_fields['status'].choices = [[0, 'Em espera'], [4, 'Excedeu o tempo de aceite']]
            if self.instance.status == 5:
                self.base_fields['status'].choices = [[2, 'Aguardando avaliação']]
                if self.instance.calcula_porcentagem_avaliacao() == '100%':
                    self.base_fields['status'].choices.append([ProcessoAvaliador.AVALIACAO_FINALIZADA, 'Finalizar avaliação'])
            elif self.instance.status == 6:
                raise PermissionDenied('Não é possivel alterar essa avaliação.')
            elif self.instance.status == 3:
                self.base_fields['status'].choices = [[0, 'Em espera'], [2, 'Aguardando avaliação'], [3, 'Avaliação finalizada']]
            elif self.instance.status == 2:
                self.base_fields['status'].choices = [[0, 'Em espera'], [2, 'Aguardando avaliação']]
            elif self.instance.status == 1:
                self.base_fields['status'].choices = [[0, 'Em espera'], [1, 'Aguardando aceite']]
            else:
                self.base_fields['status'].choices = [[0, 'Em espera']]
        else:
            self.base_fields['status'].choices = [[0, 'Em espera']]
        super().__init__(*args, **kwargs)

    class Meta:
        model = ProcessoAvaliador
        fields = ('status',)

    def save(self, *args, **kwargs):
        status = self.cleaned_data.get('status')
        obj_old = ProcessoAvaliador.objects.get(pk=self.instance.pk)
        status_antigo_processo = obj_old.processo.status

        if status and status == ProcessoAvaliador.EM_AVALIACAO or ProcessoAvaliador.EM_ESPERA:
            if status == ProcessoAvaliador.EM_AVALIACAO and obj_old.status != status:
                self.instance.data_aceite = datetime.today()

            elif status == ProcessoAvaliador.EM_ESPERA and obj_old.status != status:
                self.instance.data_aceite = None
                self.instance.data_convite = None

            avaliacao = Avaliacao.objects.filter(processo=self.instance.processo, avaliador=self.instance.avaliador)
            if avaliacao.exists():
                avaliacao = avaliacao[0]
                avaliacao.status = Avaliacao.EM_AVALIACAO
                avaliacao.save()

        save = super().save(*args, **kwargs)

        if status == ProcessoAvaliador.AVALIACAO_FINALIZADA:
            avaliacao = self.instance.avaliacao_correspondente()
            avaliacao.finalizar_avaliacao()

            if obj_old.processo.status in [
                ProcessoRSC.STATUS_APROVADO,
                ProcessoRSC.STATUS_REPROVADO,
                ProcessoRSC.STATUS_AGUARDANDO_CIENCIA,
                ProcessoRSC.STATUS_CIENTE_DO_RESULTADO,
            ]:
                processo = self.instance.processo
                processo.status = status_antigo_processo
                processo.save()

        return save


class ProcessoPagamentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'

    TODAS = '0'
    AVALIACOES_PAGAS = '1'
    AVALIACOES_NAO_PAGAS = '2'
    TIPO_AVALIACAO_CHOICES = [
        [TODAS, 'Todas as Avaliações'],
        [AVALIACOES_PAGAS, 'Com Avaliações Pagas'],
        [AVALIACOES_NAO_PAGAS, 'Com Avaliações Não Pagas'],
    ]

    avaliadores_pagamento_avaliacao = forms.ChoiceField(label='Avaliadores com:', required=False, choices=TIPO_AVALIACAO_CHOICES)
    avaliador = forms.CharFieldPlus(label='Avaliador', max_length=1000, required=False)
    interessado = forms.CharFieldPlus(label='Interessado', max_length=1000, required=False)

    fieldsets = (('Filtros de Pesquisa', {'fields': ('avaliador', 'interessado', 'avaliadores_pagamento_avaliacao')}),)


class RelatorioPagamentoForm(forms.FormPlus):
    avaliacao_paga = forms.BooleanField(label='Apenas Avaliações Pagas', required=False)
    data_inicio = forms.DateFieldPlus(label='Data de Incício', required=False)
    data_final = forms.DateFieldPlus(label='Data Final', required=False)

    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'

    fieldsets = (('Filtros de Pesquisa', {'fields': (('avaliacao_paga'), ('data_inicio', 'data_final'))}),)

    def clean_data_inicio(self):
        data = self.cleaned_data.get('data_inicio')
        if not data:
            raise forms.ValidationError('Por favor, defina um período para a consulta.')
        return data

    def clean_data_final(self):
        data = self.cleaned_data.get('data_final')
        if not data:
            raise forms.ValidationError('Por favor, defina um período para a consulta.')
        return data


class AssinaturaRequerimentoForm(SuapAssinaturaForm):
    pass


class AtualizarProcessoRSCForm(forms.FormPlus):
    processo = forms.ModelChoiceField(queryset=ProcessoRSC.objects.all(), widget=AutocompleteWidget(search_fields=ProcessoRSC.SEARCH_FIELDS))

    def clean(self):
        clean = super().clean()
        processo = self.cleaned_data.get('processo')
        docente_enviou_processo = processo.status != ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD
        processo_eletronico_gerado = processo.processo_eletronico
        if not docente_enviou_processo:
            self.add_error('processo', 'Esse processo ainda não foi enviado para CPPD.')

        if processo_eletronico_gerado:
            self.add_error('processo', 'O processo eletrônico já foi gerado para esse processo')

        return clean

    def processar(self):
        processo = self.cleaned_data.get('processo')
        processo_tramite = {
            'tipo_processo': TipoProcesso.objects.get(id=517),
            'assunto': 'Reconhecimento de Saberes e Competências - RSC',
            'setor_destino': get_setor_cppd(),
        }

        processo.processo_eletronico = Processo.cadastrar_processo(
            user=processo.servidor,
            processo_tramite=processo_tramite,
            papel=processo.servidor.papeis_ativos.first(),
            documentos_texto=[],
            documentos_digitalizados=[],
            interessados=processo.servidor,
        )
        return processo.processo_eletronico


class DashboardFiltroForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'

    ano = forms.ChoiceField(label='Ano (finalizados)', required=False)
    tipo_rsc = forms.ModelChoiceFieldPlus(queryset=TipoRsc.objects, label='Tipo de RSC', required=False, empty_label='Todos')

    fieldsets = (('Filtros', {'fields': (('ano', 'tipo_rsc'),)}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_rsc'].queryset = TipoRsc.objects.all()

        ano_atual = datetime.now().year
        self.fields['ano'].choices = [(str(ano), str(ano)) for ano in range(ano_atual, ano_atual - 6, -1)]


class RelatorioSituacaoFiltroForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'

    # O módulo passou a receber processos em 2014 (Resolução nº 15/2014-CONSUP/IFRN).
    ANO_INICIAL = 2014

    ano = forms.ChoiceField(label='Ano de entrada', required=False)
    tipo_rsc = forms.ModelChoiceFieldPlus(queryset=TipoRsc.objects, label='Tipo de RSC', required=False, empty_label='Todos')

    fieldsets = (('Filtros', {'fields': (('ano', 'tipo_rsc'),)}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_rsc'].queryset = TipoRsc.objects.all()

        ano_atual = datetime.now().year
        self.fields['ano'].choices = [(str(ano), str(ano)) for ano in range(ano_atual, self.ANO_INICIAL - 1, -1)]
