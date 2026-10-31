import datetime
import os
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import F, OuterRef, Q, Subquery
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from ae.forms import CaracterizacaoForm
from ae.models import Caracterizacao, DocumentoInscricaoAluno, IntegranteFamiliarCaracterizacao
from auxilioemergencial import tasks
from auxilioemergencial.forms import (
    AdicionarDocumentoForm,
    AdicionarDocumentoObrigatorioForm,
    AssinarTermoForm,
    AssinaturaResponsavelForm,
    AtualizarDadosBancariosForm,
    ComprovanteGRUDispositivoForm,
    ComprovanteGRUMaterialForm,
    DataEncerramentoForm,
    FiltraPrestacaoForm,
    FolhaPagamentoForm,
    GRUDispositivoForm,
    GRUMaterialForm,
    InscricaoAlunoConectadoForm,
    InscricaoAlunoForm,
    InscricaoAusenciaRendaForm,
    InscricaoDispositivoForm,
    InscricaoInternetForm,
    InscricaoMaterialPedagogicoForm,
    IntegranteFamiliarForm,
    ParecerInscricaoForm,
    PendenciaDispositivoForm,
    PendenciaMaterialForm,
    PrestacaoContasDispositivoForm,
    PrestacaoContasForm,
    PrestacaoContasMaterialForm,
    RelatorioAlunosAtendidosForm,
    RelatorioRendimentoFrequenciaForm,
)
from auxilioemergencial.models import (
    DEFERIDO,
    DEFERIDO_SEM_RECURSO,
    INSCRICAO_CONCLUIDA,
    PENDENTE_ASSINATURA,
    PENDENTE_DOCUMENTACAO,
    SEM_PARECER,
    DocumentoAluno,
    Edital,
    InscricaoAluno,
    InscricaoAlunoConectado,
    InscricaoDispositivo,
    InscricaoInternet,
    InscricaoMaterialPedagogico,
    IntegranteFamiliar,
    TipoAuxilio,
)

# from comum.models import Configuracao
from comum.utils import get_uo
from djtools import layout
from djtools.html.graficos import PieChart
from djtools.storages.utils import generate_filename
from djtools.templatetags.filters import format_
from djtools.utils import httprr, permission_required, rtr, send_notification
from edu.models import Aluno, MatriculaPeriodo, Modalidade, SituacaoMatriculaPeriodo


def aluno_pode_se_inscrever(aluno, edital):
    if edital.impedir_fic and aluno.curso_campus.modalidade_id in [Modalidade.FIC, Modalidade.PROEJA_FIC_FUNDAMENTAL]:
        return False
    return not (
        edital.impedir_pos_graduacao
        and aluno.curso_campus.modalidade_id in [Modalidade.MESTRADO, Modalidade.ESPECIALIZACAO, Modalidade.DOUTORADO, Modalidade.APERFEICOAMENTO]
    )


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Reúne pendências de Auxílio Emergencial atribuídas ao usuário logado.

    Para alunos, lista inscrições em editais ativos que ainda precisam de
    documentação, recurso, frequência, comprovante ou conclusão do cadastro.
    Para servidores responsáveis, contabiliza inscrições por etapa
    (análise, recurso, encerramento, etc.).

    Args:
        request: requisição HTTP usada para identificar o usuário e o campus.

    Returns:
        list[dict]: pendências apropriadas ao perfil; lista vazia quando não há nenhuma.
    """
    pendencias = []
    uo = get_uo(request.user)
    if request.user.eh_aluno:
        aluno = request.user.get_relacionamento()
        editais = Edital.objects.filter(campus=uo, ativo=True)
        tem_assinatura_pendente = False
        tem_documentacao_pendente = False
        if aluno.situacao.ativo:
            hoje = datetime.date.today()

            if editais.exists():
                if editais.filter(data_inicio__lte=datetime.datetime.now(), data_termino__gte=datetime.datetime.now()).exists():
                    if InscricaoInternet.objects.filter(aluno=aluno, situacao=PENDENTE_ASSINATURA).exists():
                        tem_assinatura_pendente = True
                    if not tem_assinatura_pendente and InscricaoDispositivo.objects.filter(aluno=aluno, situacao=PENDENTE_ASSINATURA).exists():
                        tem_assinatura_pendente = True
                    if not tem_assinatura_pendente and InscricaoMaterialPedagogico.objects.filter(aluno=aluno, situacao=PENDENTE_ASSINATURA).exists():
                        tem_assinatura_pendente = True
                    if not tem_assinatura_pendente and InscricaoAlunoConectado.objects.filter(aluno=aluno, situacao=PENDENTE_ASSINATURA).exists():
                        tem_assinatura_pendente = True

                # Cada modelo é consultado 1x via `.first()` em vez de `.exists()` + `[0]` (que rematerializa a query).
                # Procura na ordem original: Internet → Dispositivo → Material → AlunoConectado, parando no primeiro match.
                registro = None
                for modelo in (InscricaoInternet, InscricaoDispositivo, InscricaoMaterialPedagogico, InscricaoAlunoConectado):
                    registro = modelo.objects.filter(aluno=aluno, parecer=PENDENTE_DOCUMENTACAO, data_limite_envio_documentacao__gte=hoje).first()
                    if registro:
                        break
                if registro:
                    tem_documentacao_pendente = f'O Serviço Social do seu Campus solicita que você anexe a seguinte documentação complementar: <strong>{registro.documentacao_pendente}</strong>. Caso não anexe a documentação solicitada até a data <strong>{format_(registro.data_limite_envio_documentacao)}</strong>, sua inscrição será invalidada. Qualquer dúvida contate o Serviço Social do seu Campus.'

        # if tem_assinatura_pendente:
        #     alertas.append(dict(url='/auxilioemergencial/minhas_inscricoes/', titulo='Você possui <strong>inscrição para auxílio emergencial pendente de assinatura</strong> pelo seu responsável.'))
        if tem_documentacao_pendente:
            pendencias.append(
                {
                    'url': f'/auxilioemergencial/documentacao_aluno/{aluno.pk}/{registro.get_tipo_auxilio()}/{registro.pk}/',
                    'titulo': f'{tem_documentacao_pendente}',
                }
            )
        # if tem_termo_pendente:
        #     alertas.append(dict(url='/auxilioemergencial/minhas_inscricoes/', titulo='Você <strong>precisa assinar o termo de compromisso e inserir sua conta bancária</strong> para ter seu auxílio validado.'))
        if InscricaoAlunoConectado.objects.filter(aluno=aluno, parecer='Deferido', fim_auxilio__isnull=True).exists():
            pendencias.append(
                {
                    'url': '/auxilioemergencial/minhas_inscricoes/',
                    'titulo': 'Você será contemplado(a) com o Programa Alunos(as) Conectados(as). Acompanhe os canais de comunicação (Portal, redes sociais) do campus para saber o dia da entrega do CHIP.',
                }
            )

        # `.first()` substitui `.exists()` + `[0]` (que reexecuta a query). 1 query por bloco em vez de 2.
        inscricao_dis = InscricaoDispositivo.objects.filter(
            aluno=aluno,
            parecer='Deferido',
            termo_compromisso_assinado_em__isnull=False,
            edital__ativo=True,
            situacao_prestacao_contas=InscricaoDispositivo.AGUARDANDO_DOCUMENTOS,
            prestacao_contas_cadastrada_em__isnull=True,
        ).first()
        if inscricao_dis:
            pendencias.append(
                {
                    'url': f'/auxilioemergencial/prestacao_contas/{inscricao_dis.id}/{inscricao_dis.get_tipo_auxilio()}/',
                    'titulo': 'Você precisa <strong>comprovar a compra do(s) equipamento(s) eletrônico(s) em até 30 dias</strong> após o recebimento do Auxílio para aquisição de dispositivo eletrônico anexando nota ou cupom fiscal da compra.',
                }
            )
        inscricao_mat = InscricaoMaterialPedagogico.objects.filter(
            aluno=aluno,
            parecer='Deferido',
            termo_compromisso_assinado_em__isnull=False,
            edital__ativo=True,
            situacao_prestacao_contas=InscricaoDispositivo.AGUARDANDO_DOCUMENTOS,
            prestacao_contas_cadastrada_em__isnull=True,
        ).first()
        if inscricao_mat:
            pendencias.append(
                {
                    'url': f'/auxilioemergencial/prestacao_contas/{inscricao_mat.id}/{inscricao_mat.get_tipo_auxilio()}/',
                    'titulo': 'Você precisa <strong>comprovar a compra do(s) material(is) didático(s) em até 30 dias</strong> após o recebimento do Auxílio de Material Didático Pedagógico anexando nota ou cupom fiscal da compra.',
                }
            )

        inscricao_dis = InscricaoDispositivo.objects.filter(
            data_limite_envio_prestacao_contas__gte=datetime.datetime.now(),
            aluno=aluno,
            parecer='Deferido',
            termo_compromisso_assinado_em__isnull=False,
            edital__ativo=True,
            situacao_prestacao_contas=InscricaoDispositivo.AGUARDANDO_DOCUMENTOS,
            prestacao_contas_cadastrada_em__isnull=False,
            pendencia_prestacao_contas__isnull=False,
            prestacao_contas_atualizada_em__lt=F('pendencia_cadastrada_em'),
        ).first()
        if inscricao_dis:
            pendencias.append(
                {
                    'url': f'/auxilioemergencial/prestacao_contas/{inscricao_dis.id}/{inscricao_dis.get_tipo_auxilio()}/',
                    'titulo': 'A Comissão de prestação de contas dos auxílios emergenciais do seu Campus solicita que você anexe a seguinte documentação: <strong>{}</strong>. Você deverá editar o documento da sua prestação de contas até a data <strong>{}</strong>, adicionando o documento solicitado pela Comissão.'.format(
                        inscricao_dis.pendencia_prestacao_contas, inscricao_dis.data_limite_envio_prestacao_contas.strftime('%d/%m/%Y')
                    ),
                }
            )
        inscricao_mat = InscricaoMaterialPedagogico.objects.filter(
            data_limite_envio_prestacao_contas__gte=datetime.datetime.now(),
            aluno=aluno,
            parecer='Deferido',
            termo_compromisso_assinado_em__isnull=False,
            edital__ativo=True,
            situacao_prestacao_contas=InscricaoDispositivo.AGUARDANDO_DOCUMENTOS,
            prestacao_contas_cadastrada_em__isnull=False,
            pendencia_prestacao_contas__isnull=False,
            prestacao_contas_atualizada_em__lt=F('pendencia_cadastrada_em'),
        ).first()
        if inscricao_mat:
            pendencias.append(
                {
                    'url': f'/auxilioemergencial/prestacao_contas/{inscricao_mat.id}/{inscricao_mat.get_tipo_auxilio()}/',
                    'titulo': 'A Comissão de prestação de contas dos auxílios emergenciais do seu Campus solicita que você anexe a seguinte documentação: <strong>{}</strong>. Você deverá editar o documento da sua prestação de contas até a data <strong>{}</strong>, adicionando o documento solicitado pela Comissão.'.format(
                        inscricao_mat.pendencia_prestacao_contas, inscricao_mat.data_limite_envio_prestacao_contas.strftime('%d/%m/%Y')
                    ),
                }
            )

        inscricao_dis = InscricaoDispositivo.objects.filter(
            aluno=aluno,
            parecer='Deferido',
            termo_compromisso_assinado_em__isnull=False,
            edital__ativo=True,
            situacao_prestacao_contas=InscricaoDispositivo.AGUARDANDO_DOCUMENTOS,
            arquivo_gru__isnull=False,
            prestacao_contas_atualizada_em__lt=F('arquivo_gru_cadastrado_em'),
        )
        if inscricao_dis.exists():
            pendencias.append(
                {
                    'url': '/auxilioemergencial/minhas_inscricoes/',
                    'titulo': 'A Comissão de prestação de contas dos auxílios emergenciais do seu Campus <strong>adicionou GRU para pagamento</strong> na sua prestação de contas.',
                }
            )
        inscricao_mat = InscricaoMaterialPedagogico.objects.filter(
            aluno=aluno,
            parecer='Deferido',
            termo_compromisso_assinado_em__isnull=False,
            edital__ativo=True,
            situacao_prestacao_contas=InscricaoDispositivo.AGUARDANDO_DOCUMENTOS,
            arquivo_gru__isnull=False,
            prestacao_contas_atualizada_em__lt=F('arquivo_gru_cadastrado_em'),
        )
        if inscricao_mat.exists():
            pendencias.append(
                {
                    'url': '/auxilioemergencial/minhas_inscricoes/',
                    'titulo': 'A Comissão de prestação de contas dos auxílios emergenciais do seu Campus <strong>adicionou GRU para pagamento</strong> na sua prestação de contas.',
                }
            )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if request.user.has_perm('auxilioemergencial.pode_adicionar_prestacao_contas', ignore_superuser=True):
        inscricoes_dis_sem_prestacao_contas = InscricaoDispositivo.objects.filter(
            edital__campus=get_uo(request.user), parecer='Deferido', situacao_prestacao_contas=InscricaoDispositivo.PENDENTE_VALIDACAO
        ).count()
        inscricoes_mat_sem_prestacao_contas = InscricaoMaterialPedagogico.objects.filter(
            edital__campus=get_uo(request.user), parecer='Deferido', situacao_prestacao_contas=InscricaoDispositivo.PENDENTE_VALIDACAO
        ).count()
        qtd = inscricoes_dis_sem_prestacao_contas + inscricoes_mat_sem_prestacao_contas
        if qtd:
            pendencias.append(
                {
                    'titulo': f'Prestaç{pluralize(qtd, "ão,ões")} de Contas de Auxílios Emergenciais',
                    'subtitulo': 'a validar',
                    'qtd': qtd,
                    'url': '/auxilioemergencial/listar_prestacoes_conta/?situacao=Pendente+de+validação&filtraprestacao_form=Aguarde...',
                }
            )

    return pendencias


@layout.inscricao()
def index_inscricoes(request):
    """Retorna inscrições/avisos de Auxílio Emergencial para o aluno logado.

    Para alunos ativos, indica termo de aceite pendente em inscrições recentes
    e, conforme editais abertos para o campus, oferece atalhos de inscrição
    em Auxílio Internet, Dispositivo, Material Pedagógico e Domiciliar.

    Args:
        request: requisição HTTP usada para identificar o aluno e o campus.

    Returns:
        list[dict]: itens de inscrição com ``url``, ``titulo`` e ``prazo``;
        lista vazia quando o usuário não é aluno elegível.
    """
    inscricoes = []
    if request.user.eh_aluno:
        aluno = request.user.get_relacionamento()
        uo = aluno.curso_campus.diretoria.setor.uo
        tem_termo_pendente = False
        data_limite = None
        if aluno.situacao.ativo:
            agora = datetime.datetime.now()
            for modelo in (InscricaoInternet, InscricaoDispositivo, InscricaoMaterialPedagogico):
                if tem_termo_pendente:
                    break
                for registro in modelo.objects.filter(
                    aluno=aluno,
                    edital__data_divulgacao__lte=agora,
                    parecer='Deferido',
                    termo_compromisso_assinado=False,
                    data_limite_assinatura_termo__gte=agora,
                ):
                    tem_termo_pendente = True
                    data_limite = registro.data_limite_assinatura_termo
                    break
            if tem_termo_pendente:
                inscricoes.append(
                    {
                        'url': '/auxilioemergencial/minhas_inscricoes/',
                        'titulo': 'Você tem até o dia <strong>{}</strong> para assinar <strong>o termo de compromisso e inserir sua conta bancária</strong> para ter seu auxílio validado.'.format(
                            data_limite.strftime('%d/%m/%Y')
                        ),
                    }
                )

        editais = Edital.objects.filter(campus=uo, data_inicio__lte=datetime.datetime.now(), data_termino__gte=datetime.datetime.now(), ativo=True)
        if editais.exists() and aluno.situacao.ativo:
            for edital in editais:
                if aluno_pode_se_inscrever(aluno, edital):
                    for auxilio in edital.tipo_auxilio.all():
                        if (
                            not (
                                auxilio.pk == 1
                                and (
                                    InscricaoInternet.objects.filter(aluno=aluno, edital=edital).exclude(parecer=SEM_PARECER).exists()
                                    or InscricaoInternet.objects.filter(
                                        aluno=aluno, fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False
                                    ).exists()
                                )
                            )
                            and not (
                                auxilio.pk == 2
                                and InscricaoDispositivo.objects.filter(aluno=aluno, edital=edital).exclude(parecer=SEM_PARECER).exists()
                            )
                            and not (
                                auxilio.pk == 3
                                and InscricaoMaterialPedagogico.objects.filter(aluno=aluno, edital=edital).exclude(parecer=SEM_PARECER).exists()
                            )
                        ):
                            inscricoes.append(
                                {
                                    'url': f'/auxilioemergencial/inscricao_caracterizacao/{aluno.pk}/{auxilio.pk}/{edital.id}/',
                                    'titulo': f'Solicitar Auxílio Emergencial: <strong>{auxilio.titulo} - {edital.descricao}</strong>',
                                    'prazo': edital.data_termino.strftime('%d/%m/%Y %H:%M'),
                                }
                            )
    return inscricoes


@layout.quadro('Ações Emergenciais', icone='suitcase', pode_esconder=True)
def index_quadros(quadro, request):
    if request.user.has_perm('comum.is_assistente_social'):
        uo = get_uo(request.user)
        internet = InscricaoInternet.objects.filter(edital__campus=uo)
        dispositivo = InscricaoDispositivo.objects.filter(edital__campus=uo)
        material = InscricaoMaterialPedagogico.objects.filter(edital__campus=uo)
        conectado = InscricaoAlunoConectado.objects.filter(edital__campus=uo)

        internet_pendente = internet.filter(data_limite_envio_documentacao__isnull=False, parecer=SEM_PARECER)
        if internet_pendente.exists():
            qtd = internet_pendente.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Solicitaç{pluralize(qtd, "ão,ões")} de Auxílio de Serviços de Internet',
                    subtitulo='Pendente de parecer após envio de documentação',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaointernet/?pendentes_pos_envio=1',
                )
            )

        dispositivo_pendente = dispositivo.filter(data_limite_envio_documentacao__isnull=False, parecer=SEM_PARECER)
        if dispositivo_pendente.exists():
            qtd = dispositivo_pendente.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Solicitaç{pluralize(qtd, "ão,ões")} para Aquisição de Dispositivo Eletrônico',
                    subtitulo='Pendente de parecer após envio de documentação',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaodispositivo/?pendentes_pos_envio=1',
                )
            )

        material_pendente = material.filter(data_limite_envio_documentacao__isnull=False, parecer=SEM_PARECER)
        if material_pendente.exists():
            qtd = material_pendente.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Solicitaç{pluralize(qtd, "ão,ões")} para Aquisição de Material Pedagógico',
                    subtitulo='Pendente de parecer após envio de documentação',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaomaterialpedagogico/?pendentes_pos_envio=1',
                )
            )

        conectado_pendente = conectado.filter(data_limite_envio_documentacao__isnull=False, parecer=SEM_PARECER)
        if conectado_pendente.exists():
            qtd = conectado_pendente.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Solicitaç{pluralize(qtd, "ão,ões")} para o Projeto Alunos Conectados',
                    subtitulo='Pendente de parecer após envio de documentação',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaoalunoconectado/?pendentes_pos_envio=1',
                )
            )

        internet_documentacao = internet.filter(documentacao_atualizada_em__gt=F('data_parecer'))
        if internet_documentacao.exists():
            qtd = internet_documentacao.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Solicitaç{pluralize(qtd, "ão,ões")} de Auxílio de Serviços de Internet',
                    subtitulo='Com envio de documentação após o registro do parecer',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaointernet/?documentacao_pos_parecer=1',
                )
            )

        dispositivo_documentacao = dispositivo.filter(documentacao_atualizada_em__gt=F('data_parecer'))
        if dispositivo_documentacao.exists():
            qtd = dispositivo_documentacao.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Solicitaç{pluralize(qtd, "ão,ões")} para Aquisição de Dispositivo Eletrônico',
                    subtitulo='Com envio de documentação após o registro do parecer',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaodispositivo/?documentacao_pos_parecer=1',
                )
            )

        material_documentacao = material.filter(documentacao_atualizada_em__gt=F('data_parecer'))
        if material_documentacao.exists():
            qtd = material_documentacao.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Solicitaç{pluralize(qtd, "ão,ões")} para Aquisição de Material Pedagógico',
                    subtitulo='Com envio de documentação após o registro do parecer',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaomaterialpedagogico/?documentacao_pos_parecer=1',
                )
            )

        conectado_documentacao = conectado.filter(documentacao_atualizada_em__gt=F('data_parecer'))
        if conectado_documentacao.exists():
            qtd = conectado_documentacao.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Solicitaç{pluralize(qtd, "ão,ões")} para o Projeto Alunos Conectados',
                    subtitulo='Com envio de documentação após o registro do parecer',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaoalunoconectado/?documentacao_pos_parecer=1',
                )
            )

        internet_inativa = (
            internet.filter(fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False)
            .annotate(
                situacao_matricula=Subquery(
                    MatriculaPeriodo.objects.filter(aluno=OuterRef('aluno')).order_by('-ano_letivo__ano', '-periodo_letivo').values('situacao')[:1]
                )
            )
            .exclude(situacao_matricula=SituacaoMatriculaPeriodo.MATRICULADO)
        )
        if internet_inativa.exists():
            qtd = internet_inativa.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Participante{pluralize(qtd)} de Auxílio de Serviços de Internet',
                    subtitulo='Com situação no período inativa',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaointernet/?eh_participante=1&matricula_ativa=2',
                )
            )

        dispositivo_inativa = (
            dispositivo.filter(fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False)
            .annotate(
                situacao_matricula=Subquery(
                    MatriculaPeriodo.objects.filter(aluno=OuterRef('aluno')).order_by('-ano_letivo__ano', '-periodo_letivo').values('situacao')[:1]
                )
            )
            .exclude(situacao_matricula=SituacaoMatriculaPeriodo.MATRICULADO)
        )
        if dispositivo_inativa.exists():
            qtd = dispositivo_inativa.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Participante{pluralize(qtd)} de Aquisição de Dispositivo Eletrônico',
                    subtitulo='Com situação no período inativa',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaodispositivo/?eh_participante=1&matricula_ativa=2',
                )
            )

        material_inativa = (
            material.filter(fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False)
            .annotate(
                situacao_matricula=Subquery(
                    MatriculaPeriodo.objects.filter(aluno=OuterRef('aluno')).order_by('-ano_letivo__ano', '-periodo_letivo').values('situacao')[:1]
                )
            )
            .exclude(situacao_matricula=SituacaoMatriculaPeriodo.MATRICULADO)
        )
        if material_inativa.exists():
            qtd = material_inativa.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Participante{pluralize(qtd)} de Aquisição de Material Pedagógico',
                    subtitulo='Com situação no período inativa',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaomaterialpedagogico/?eh_participante=1&matricula_ativa=2',
                )
            )

        conectado_inativa = (
            conectado.filter(fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False)
            .annotate(
                situacao_matricula=Subquery(
                    MatriculaPeriodo.objects.filter(aluno=OuterRef('aluno')).order_by('-ano_letivo__ano', '-periodo_letivo').values('situacao')[:1]
                )
            )
            .exclude(situacao_matricula=SituacaoMatriculaPeriodo.MATRICULADO)
        )
        if conectado_inativa.exists():
            qtd = conectado_inativa.count()
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Participante{pluralize(qtd)} do Projeto Alunos Conectados',
                    subtitulo='Com situação no período inativa',
                    qtd=qtd,
                    url='/admin/auxilioemergencial/inscricaoalunoconectado/?eh_participante=1&matricula_ativa=2',
                )
            )

    return quadro


def tem_permissao(request, aluno, edital, auxilio_pk):
    pode_submeter = aluno_pode_se_inscrever(aluno, edital)
    if not pode_submeter:
        raise PermissionDenied
    campus_do_aluno = aluno.curso_campus.diretoria.setor.uo
    periodos_permitidos = Edital.objects.filter(campus=campus_do_aluno, data_termino__gte=datetime.datetime.now(), ativo=True)
    if not periodos_permitidos.exists():
        raise PermissionDenied
    if auxilio_pk not in edital.tipo_auxilio.values_list('id', flat=True):
        raise PermissionDenied
    if request.user.get_relacionamento() != aluno:
        raise PermissionDenied
    if (
        (
            auxilio_pk == 1
            and (
                InscricaoInternet.objects.filter(aluno=aluno, edital=edital).exclude(parecer=SEM_PARECER).exists()
                or InscricaoInternet.objects.filter(
                    aluno=aluno, fim_auxilio__isnull=True, parecer=DEFERIDO, termo_compromisso_assinado_em__isnull=False
                ).exists()
            )
        )
        or (auxilio_pk == 2 and InscricaoDispositivo.objects.filter(aluno=aluno, edital=edital).exclude(parecer=SEM_PARECER).exists())
        or (auxilio_pk == 3 and InscricaoMaterialPedagogico.objects.filter(aluno=aluno, edital=edital).exclude(parecer=SEM_PARECER).exists())
    ):
        raise PermissionDenied
    return True


def retorna_inscricao(tipo_auxilio, inscricao_pk):
    inscricao = None
    if tipo_auxilio == 'INT':
        inscricao = get_object_or_404(InscricaoInternet, pk=inscricao_pk)
    elif tipo_auxilio == 'DIS':
        inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
    elif tipo_auxilio == 'MAT':
        inscricao = get_object_or_404(InscricaoMaterialPedagogico, pk=inscricao_pk)
    elif tipo_auxilio == 'CHP':
        inscricao = get_object_or_404(InscricaoAlunoConectado, pk=inscricao_pk)
    return inscricao


@rtr(two_factor_authentication=True)
@permission_required('edu.pode_editar_caracterizacao')
def inscricao_composicao(request, aluno_pk, auxilio_pk, edital_pk):
    auxilio = get_object_or_404(TipoAuxilio, pk=auxilio_pk)
    edital = get_object_or_404(Edital, pk=edital_pk)
    title = f'Inscrição para {auxilio} - Edital {edital}'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    tem_permissao(request, aluno, edital, auxilio_pk)
    # if not Caracterizacao.objects.filter(aluno=aluno).exists() or Caracterizacao.objects.filter(aluno=aluno).latest('id').data_ultima_atualizacao.date() < datetime.datetime.now().date():
    #     return httprr('/ae/caracterizacao/{:d}/'.format(aluno.pk), 'Por favor, efetue ou atualize sua caracterização social antes de solicitar o auxílio.')

    qtd_pessoas_domicilio = aluno.caracterizacao.qtd_pessoas_domicilio
    if not qtd_pessoas_domicilio:
        return httprr(
            f'/auxilioemergencial/inscricao_caracterizacao/{aluno.pk}/{auxilio_pk}/{edital_pk}/',
            'Informe o número de pessoas que moram no domicílio, incluíndo você. Caso more sozinho, informe o valor "1".',
            tag='error',
        )
    registros_composicao = qtd_pessoas_domicilio
    inscricao_caracterizacao = None
    if InscricaoAluno.objects.filter(aluno__pk=aluno.pk).exists():
        inscricao_caracterizacao = InscricaoAluno.objects.filter(aluno__pk=aluno.pk)[0]
        total_componentes = qtd_pessoas_domicilio - IntegranteFamiliar.objects.filter(inscricao=inscricao_caracterizacao).count()
        if total_componentes > 0:
            registros_composicao = total_componentes
        else:
            registros_composicao = 0

        if not request.POST:
            for registro in IntegranteFamiliar.objects.filter(inscricao=inscricao_caracterizacao):
                if registro.remuneracao is not None:
                    registro.ultima_remuneracao = registro.remuneracao
                    registro.save()
        # IntegranteFamiliar.objects.filter(inscricao=inscricao_caracterizacao).update(remuneracao=None)

    if qtd_pessoas_domicilio:
        IntegranteFamiliarSet = inlineformset_factory(
            InscricaoAluno,
            IntegranteFamiliar,
            form=IntegranteFamiliarForm,
            extra=registros_composicao,
            exclude=('idade', 'ultima_remuneracao', 'aluno', 'id_inscricao'),
        )

    formset = IntegranteFamiliarSet(request.POST or None, request.FILES or None, instance=inscricao_caracterizacao)

    renda_bruta_informada = Decimal('0.00')
    if formset.is_valid():
        for item in formset.cleaned_data:
            if (
                'nome' not in item
                or 'parentesco' not in item
                or 'estado_civil' not in item
                or 'situacao_trabalho' not in item
                or 'remuneracao' not in item
                or 'data_nascimento' not in item
            ):
                return httprr(
                    f'/auxilioemergencial/inscricao_composicao/{aluno_pk}/{auxilio_pk}/{edital_pk}/',
                    'Informe os dados de todas as pessoas do domicílio.',
                    tag='error',
                )
            else:
                if not item.get('DELETE'):
                    renda_bruta_informada = renda_bruta_informada + Decimal(item['remuneracao'])

        numero_salarios = 0
        # valor_salario_minimo = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
        # if Decimal(valor_salario_minimo) > 0 and qtd_pessoas_domicilio > 0:
        #     numero_salarios = (Decimal(renda_bruta_informada) / Decimal(qtd_pessoas_domicilio)) / Decimal(valor_salario_minimo)
        if qtd_pessoas_domicilio > 0:
            numero_salarios = Decimal(renda_bruta_informada) / Decimal(qtd_pessoas_domicilio)
        inscricao_caracterizacao.renda_bruta_familiar = renda_bruta_informada
        inscricao_caracterizacao.renda_per_capita = numero_salarios
        inscricao_caracterizacao.aluno = aluno
        inscricao_caracterizacao.save()
        aluno.caracterizacao.renda_bruta_familiar = renda_bruta_informada
        aluno.caracterizacao.informado_por = request.user.get_vinculo()
        aluno.caracterizacao.save()
        if qtd_pessoas_domicilio:
            formset.instance = inscricao_caracterizacao
            formset.save()
        if renda_bruta_informada:
            return httprr(f'/auxilioemergencial/inscricao_documento/{aluno_pk}/{auxilio_pk}/{edital_pk}/')
        else:
            return httprr(f'/auxilioemergencial/inscricao_ausencia_renda/{aluno_pk}/{auxilio_pk}/{edital_pk}/')
    return locals()


@rtr(two_factor_authentication=True)
@permission_required('edu.pode_editar_caracterizacao')
def inscricao_ausencia_renda(request, aluno_pk, auxilio_pk, edital_pk):
    auxilio = get_object_or_404(TipoAuxilio, pk=auxilio_pk)
    edital = get_object_or_404(Edital, pk=edital_pk)
    title = f'Inscrição para {auxilio} - Edital {edital}'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    tem_permissao(request, aluno, edital, auxilio_pk)
    if DocumentoAluno.objects.filter(aluno=aluno, tipo=DocumentoAluno.AUSENCIA_RENDA).exists():
        return httprr(f'/auxilioemergencial/inscricao_documento/{aluno_pk}/{auxilio_pk}/{edital_pk}/')
    modelo_ausencia_renda = os.path.join(settings.BASE_DIR, 'auxilioemergencial/templates/modelos/declaracao_ausencia_de_renda_da_familia.pdf')
    inscricao_caracterizacao = None
    if InscricaoAluno.objects.filter(aluno__pk=aluno.pk).exists():
        inscricao_caracterizacao = InscricaoAluno.objects.filter(aluno__pk=aluno.pk)[0]
    form = InscricaoAusenciaRendaForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        agora = datetime.datetime.now()
        o = form.save(False)
        o.aluno = aluno
        o.data_cadastro = agora
        o.tipo = DocumentoAluno.AUSENCIA_RENDA
        o.descricao = 'Declaração de ausência de renda da família'
        o.cadastrado_por = request.user.get_vinculo()
        o.save()
        inscricao_caracterizacao.valor_doacoes = form.cleaned_data.get('valor')
        inscricao_caracterizacao.save()
        return httprr(f'/auxilioemergencial/inscricao_documento/{aluno_pk}/{auxilio_pk}/{edital_pk}/')

    return locals()


@rtr(two_factor_authentication=True)
@permission_required('edu.pode_editar_caracterizacao')
def inscricao(request, aluno_pk, auxilio_pk, edital_pk):
    auxilio = get_object_or_404(TipoAuxilio, pk=auxilio_pk)
    edital = get_object_or_404(Edital, pk=edital_pk)
    title = f'Inscrição para {auxilio} - Edital {edital}'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    tem_permissao(request, aluno, edital, auxilio_pk)
    inscricao_caracterizacao = None
    if InscricaoAluno.objects.filter(aluno__pk=aluno.pk).exists():
        inscricao_caracterizacao = InscricaoAluno.objects.filter(aluno__pk=aluno.pk)[0]
    form = InscricaoAlunoForm(request.POST or None, instance=inscricao_caracterizacao)
    if form.is_valid():
        o = form.save(False)
        o.aluno = aluno
        o.save()
        return httprr(f'/auxilioemergencial/inscricao_composicao/{aluno_pk}/{auxilio_pk}/{edital_pk}/')

    return locals()


@rtr(two_factor_authentication=True)
@permission_required('edu.pode_editar_caracterizacao')
def inscricao_caracterizacao(request, aluno_pk, auxilio_pk, edital_pk):
    auxilio = get_object_or_404(TipoAuxilio, pk=auxilio_pk)
    edital = get_object_or_404(Edital, pk=edital_pk)
    title = f'Inscrição para {auxilio} - Edital {edital}'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    tem_permissao(request, aluno, edital, auxilio_pk)
    # if auxilio_pk == '3':
    #     return httprr("/auxilioemergencial/inscricao_detalhamento/{}/{}/{}/".format( aluno_pk, auxilio_pk, edital_pk))
    if hasattr(aluno, 'caracterizacao') or request.user.get_relacionamento():
        if not request.user == aluno.get_user():
            raise PermissionDenied

    form = CaracterizacaoForm(aluno, data=request.POST or None)

    if Caracterizacao.objects.filter(aluno=aluno).exists():
        form = CaracterizacaoForm(aluno, instance=aluno.caracterizacao, data=request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            caracterizacao = form.save(False)
            caracterizacao.aluno = aluno
            caracterizacao.informado_por = request.user.get_vinculo()
            if Caracterizacao.objects.filter(id=caracterizacao.id).exists():
                registro_atual = Caracterizacao.objects.get(id=caracterizacao.id)
                if (
                    registro_atual.qtd_pessoas_domicilio != form.cleaned_data.get('qtd_pessoas_domicilio')
                    or registro_atual.companhia_domiciliar != form.cleaned_data.get('companhia_domiciliar')
                    or registro_atual.responsavel_financeir_trabalho_situacao != form.cleaned_data.get('responsavel_financeir_trabalho_situacao')
                    or registro_atual.renda_bruta_familiar != form.cleaned_data.get('renda_bruta_familiar')
                ):
                    IntegranteFamiliarCaracterizacao.objects.filter(aluno=aluno).update(inscricao_caracterizacao=None)
            caracterizacao.save()
            form.save_m2m()

            return httprr(f'/auxilioemergencial/inscricao/{aluno_pk}/{auxilio_pk}/{edital_pk}/', 'Preencha os dados da sua inscrição.')
    return locals()


@rtr(two_factor_authentication=True)
@permission_required('edu.pode_editar_caracterizacao')
def inscricao_detalhamento(request, aluno_pk, auxilio_pk, edital_pk):
    auxilio = get_object_or_404(TipoAuxilio, pk=auxilio_pk)
    edital = get_object_or_404(Edital, pk=edital_pk)
    title = f'Inscrição para {auxilio} - Edital {edital}'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    tem_permissao(request, aluno, edital, auxilio_pk)
    # if not Caracterizacao.objects.filter(aluno=aluno).exists() or Caracterizacao.objects.filter(aluno=aluno).latest('id').data_ultima_atualizacao.date() < datetime.datetime.now().date():
    #     return httprr('/ae/caracterizacao/{:d}/'.format(aluno.pk), 'Por favor, efetue ou atualize sua caracterização social antes de solicitar o auxílio.')
    eh_maior_dezoito_anos = aluno.pessoa_fisica.nascimento_data < (date.today() + relativedelta(years=-18))
    if auxilio_pk == 1:
        inscricao = InscricaoInternet()
        if InscricaoInternet.objects.filter(edital=edital, aluno=aluno).exists():
            inscricao = InscricaoInternet.objects.filter(edital=edital, aluno=aluno)[0]
        form = InscricaoInternetForm(request.POST or None, instance=inscricao)
        if form.is_valid():
            o = form.save(False)
            o.aluno = aluno
            o.edital = edital
            o.ultima_atualizacao = datetime.datetime.now()
            o.assinado_pelo_responsavel = False
            o.assinado_pelo_responsavel_em = None
            o.data_limite_assinatura_termo = edital.data_divulgacao + relativedelta(days=+3)
            o.parecer = SEM_PARECER
            o.situacao = INSCRICAO_CONCLUIDA
            o.save()
            return httprr(
                f'/auxilioemergencial/inscricao_confirmacao/{auxilio.get_tipo_auxilio()}/{inscricao.pk}/',
                'Inscrição concluída com sucesso. Por favor, confira seus dados.',
            )
    elif auxilio_pk == 2:
        inscricao = InscricaoDispositivo()
        if InscricaoDispositivo.objects.filter(edital=edital, aluno=aluno).exists():
            inscricao = InscricaoDispositivo.objects.filter(edital=edital, aluno=aluno)[0]
        form = InscricaoDispositivoForm(request.POST or None, instance=inscricao)
        if form.is_valid():
            o = form.save(False)
            o.aluno = aluno
            o.edital = edital
            o.ultima_atualizacao = datetime.datetime.now()
            o.assinado_pelo_responsavel = False
            o.assinado_pelo_responsavel_em = None
            o.situacao_prestacao_contas = InscricaoDispositivo.AGUARDANDO_DOCUMENTOS
            o.data_limite_assinatura_termo = edital.data_divulgacao + relativedelta(days=+3)
            o.parecer = SEM_PARECER
            o.situacao = INSCRICAO_CONCLUIDA
            o.save()
            return httprr(
                f'/auxilioemergencial/inscricao_confirmacao/{auxilio.get_tipo_auxilio()}/{inscricao.pk}/',
                'Inscrição concluída com sucesso. Por favor, confira seus dados.',
            )
    elif auxilio_pk == 3:
        inscricao = InscricaoMaterialPedagogico()
        if InscricaoMaterialPedagogico.objects.filter(edital=edital, aluno=aluno).exists():
            inscricao = InscricaoMaterialPedagogico.objects.filter(edital=edital, aluno=aluno)[0]
        form = InscricaoMaterialPedagogicoForm(request.POST or None, instance=inscricao)
        if form.is_valid():
            o = form.save(False)
            o.aluno = aluno
            o.edital = edital
            o.ultima_atualizacao = datetime.datetime.now()
            o.assinado_pelo_responsavel = False
            o.assinado_pelo_responsavel_em = None
            o.situacao_prestacao_contas = InscricaoMaterialPedagogico.AGUARDANDO_DOCUMENTOS
            o.data_limite_assinatura_termo = edital.data_divulgacao + relativedelta(days=+3)
            o.parecer = SEM_PARECER
            o.situacao = INSCRICAO_CONCLUIDA
            o.save()
            return httprr(
                f'/auxilioemergencial/inscricao_confirmacao/{auxilio.get_tipo_auxilio()}/{inscricao.pk}/',
                'Inscrição concluída com sucesso. Por favor, confira seus dados.',
            )
    elif auxilio_pk == 4:
        inscricao = InscricaoAlunoConectado()
        if InscricaoAlunoConectado.objects.filter(edital=edital, aluno=aluno).exists():
            inscricao = InscricaoAlunoConectado.objects.filter(edital=edital, aluno=aluno)[0]
        form = InscricaoAlunoConectadoForm(request.POST or None, instance=inscricao)
        if form.is_valid():
            o = form.save(False)
            o.aluno = aluno
            o.edital = edital
            o.ultima_atualizacao = datetime.datetime.now()
            o.assinado_pelo_responsavel = False
            o.assinado_pelo_responsavel_em = None
            o.data_limite_assinatura_termo = edital.data_divulgacao + relativedelta(days=+3)
            o.parecer = SEM_PARECER
            o.situacao = INSCRICAO_CONCLUIDA
            o.save()
            return httprr(
                f'/auxilioemergencial/inscricao_confirmacao/{auxilio.get_tipo_auxilio()}/{inscricao.pk}/',
                'Inscrição concluída com sucesso. Por favor, confira seus dados.',
            )

            # return httprr("/auxilioemergencial/inscricao_caracterizacao/{:d}/{}/{}/{}/".format(inscricao.aluno.pk, auxilio_pk, edital_pk, inscricao.pk), 'Cadastre ou atualize a sua caracterização socioeconômica.')

    return locals()


@rtr()
@permission_required('edu.pode_editar_caracterizacao')
def inscricao_documento(request, aluno_pk, auxilio_pk, edital_pk):
    auxilio = get_object_or_404(TipoAuxilio, pk=auxilio_pk)
    title = 'Documentação da Inscrição'
    edital = get_object_or_404(Edital, pk=edital_pk)
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    tem_permissao(request, aluno, edital, auxilio_pk)
    modelo_atividade_informal = os.path.join(settings.BASE_DIR, 'auxilioemergencial/templates/modelos/declaracao_atividade_informal.pdf')
    modelo_pensao = os.path.join(settings.BASE_DIR, 'auxilioemergencial/templates/modelos/declaracao_pensao_alimenticia.pdf')
    modelo_renda_aluguel = os.path.join(settings.BASE_DIR, 'auxilioemergencial/templates/modelos/declaracao_rendimentos_proveninentes_aluguel.pdf')
    # if not Caracterizacao.objects.filter(aluno=aluno).exists() or Caracterizacao.objects.filter(aluno=aluno).latest('id').data_ultima_atualizacao.date() < datetime.datetime.now().date():
    #     return httprr('/ae/caracterizacao/{:d}/'.format(aluno.pk), 'Por favor, efetue ou atualize sua caracterização social antes de solicitar o auxílio.')
    documentos_atuais = DocumentoAluno.objects.filter(aluno=aluno)
    documentos_previos = DocumentoInscricaoAluno.objects.filter(aluno=aluno)
    tem_documentos = documentos_atuais.exists()
    renda_bruta = aluno.caracterizacao.renda_bruta_familiar
    integrantes = IntegranteFamiliar.objects.filter(aluno=aluno, remuneracao__gt=0)
    eh_material_pedagogico = auxilio.get_tipo_auxilio() == 'MAT'
    form = AdicionarDocumentoObrigatorioForm(
        request.POST or None, request.FILES or None, aluno=aluno, integrantes=integrantes, eh_material=eh_material_pedagogico
    )
    if form.is_valid():
        if form.cleaned_data.get('comprovante_endereco'):
            nova_documentacao = DocumentoAluno()
            nova_documentacao.aluno = aluno
            nova_documentacao.descricao = 'Comprovante de Residência'
            nova_documentacao.tipo = DocumentoAluno.COMPROVANTE_RESIDENCIA
            arquivo = form.cleaned_data.get('comprovante_endereco')
            filename = generate_filename(
                parts=[request.user.get_profile().id, datetime.datetime.now().date(), datetime.datetime.now()],
                file_obj=arquivo,
            )
            arquivo.name = filename
            nova_documentacao.arquivo = arquivo
            nova_documentacao.cadastrado_por = request.user.get_vinculo()
            nova_documentacao.data_cadastro = datetime.datetime.now()
            nova_documentacao.save()
        if form.cleaned_data.get('parecer'):
            nova_documentacao = DocumentoAluno()
            nova_documentacao.aluno = aluno
            nova_documentacao.descricao = 'Parecer emitido pelo NAPNE e/ou ETEP'
            nova_documentacao.tipo = DocumentoAluno.PARECER
            arquivo = form.cleaned_data.get('parecer')
            filename = generate_filename(
                parts=[request.user.get_profile().id, datetime.datetime.now().date(), datetime.datetime.now()],
                file_obj=arquivo,
            )
            arquivo.name = filename
            nova_documentacao.arquivo = arquivo
            nova_documentacao.cadastrado_por = request.user.get_vinculo()
            nova_documentacao.data_cadastro = datetime.datetime.now()
            nova_documentacao.save()

        if form.cleaned_data.get('documentacao_complementar'):
            nova_documentacao = DocumentoAluno()
            nova_documentacao.aluno = aluno
            nova_documentacao.descricao = 'Documentos Complementares'
            nova_documentacao.tipo = DocumentoAluno.DOCUMENTACAO_COMPLEMENTAR
            arquivo = form.cleaned_data.get('documentacao_complementar')
            filename = generate_filename(
                parts=[request.user.get_profile().id, datetime.datetime.now().date(), datetime.datetime.now()],
                file_obj=arquivo,
            )
            arquivo.name = filename
            nova_documentacao.arquivo = arquivo
            nova_documentacao.cadastrado_por = request.user.get_vinculo()
            nova_documentacao.data_cadastro = datetime.datetime.now()
            nova_documentacao.save()

        for item in integrantes:
            id = f'{item.id}'
            arquivo = form.cleaned_data.get(id)
            if arquivo:
                integrante_familiar = get_object_or_404(IntegranteFamiliar, pk=int(id))
                nova_documentacao = DocumentoAluno()
                nova_documentacao.aluno = aluno
                nova_documentacao.descricao = f'Comprovante de Renda - {integrante_familiar.nome}'
                nova_documentacao.tipo = DocumentoAluno.COMPROVANTE_RENDA
                arquivo = form.cleaned_data.get(id)
                filename = generate_filename(
                    parts=[request.user.get_profile().id, datetime.datetime.now().date(), datetime.datetime.now()],
                    file_obj=arquivo,
                )
                arquivo.name = filename
                nova_documentacao.arquivo = arquivo
                nova_documentacao.cadastrado_por = request.user.get_vinculo()
                nova_documentacao.data_cadastro = datetime.datetime.now()

                nova_documentacao.integrante_familiar = integrante_familiar
                nova_documentacao.save()
        return httprr(f'/auxilioemergencial/inscricao_detalhamento/{aluno_pk}/{auxilio_pk}/{edital_pk}/', 'Documentação cadastrada com sucesso.')

    return locals()


@rtr()
@permission_required('edu.pode_editar_caracterizacao')
def inscricao_confirmacao(request, tipo_auxilio, inscricao_pk):
    title = 'Confirmação de Inscrição'
    inscricao = retorna_inscricao(tipo_auxilio, inscricao_pk)
    aluno_logado = request.user.get_relacionamento()
    if aluno_logado != inscricao.aluno:
        raise PermissionDenied
    inscricao_caracterizacao = None
    if InscricaoAluno.objects.filter(aluno=aluno_logado).exists():
        inscricao_caracterizacao = InscricaoAluno.objects.filter(aluno=aluno_logado)[0]
        integrantes_familiares = IntegranteFamiliar.objects.filter(aluno=aluno_logado).distinct('nome')
    return locals()


@rtr()
@permission_required('ae.pode_ver_comprovante_inscricao')
def parecer_inscricao(request, tipo_auxilio, inscricao_pk):
    inscricao = retorna_inscricao(tipo_auxilio, inscricao_pk)
    title = f'Parecer da Inscrição {inscricao}'
    if inscricao.pendente_assinatura():
        raise PermissionDenied
    url_origem = request.META.get('HTTP_REFERER', '.')
    if request.POST:
        form = ParecerInscricaoForm(request.POST or None, inscricao=inscricao)
        if form.is_valid():
            inscricao.parecer = form.cleaned_data.get('parecer')
            inscricao.autor_parecer = request.user.get_vinculo()
            inscricao.data_parecer = datetime.datetime.now()
            if form.cleaned_data.get('parecer') == 'Deferido':
                inscricao.valor_concedido = form.cleaned_data.get('valor')
                if tipo_auxilio == 'CHP':
                    titulo = '[SUAP] Auxílio Emergencial: Projeto Alunos Conectados'
                    texto = (
                        '<h1>Serviço Social</h1>'
                        '<h2>Auxílio Emergencial</h2>'
                        '<p>Você será contemplado(a) com o Programa Alunos(as) Conectados(as). Acompanhe os canais de comunicação (Portal, redes sociais) do campus para saber o dia da entrega do CHIP.</p>'
                        '<p>Procure o setor de Serviço Social do seu campus para mais informações.</p>'
                    )
                    # else:
                    #
                    #     titulo = '[SUAP] Auxílio Emergencial: Assinatura de Termo Pendente'
                    #     texto = (
                    #         '<h1>Serviço Social</h1>'
                    #         '<h2>Auxílio Emergencial</h2>'
                    #         '<p>Você tem o <strong>prazo de 3 dias</strong> para assinar o termo de compromisso e inserir sua conta bancária para ter seu auxílio validado.</p>'
                    #         '<p>Procure o setor de Serviço Social do seu campus para mais informações.</p>'
                    #     )
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [inscricao.aluno.get_vinculo()])
            else:
                inscricao.valor_concedido = None
            if form.cleaned_data.get('parecer') == PENDENTE_DOCUMENTACAO:
                inscricao.documentacao_pendente = form.cleaned_data.get('documentacao_pendente')
                inscricao.data_limite_envio_documentacao = form.cleaned_data.get('data_limite')
                titulo = '[SUAP] Auxílio Emergencial: Documentação Pendente'
                texto = (
                    '<h1>Serviço Social</h1>'
                    '<h2>Auxílio Emergencial</h2>'
                    '<p>O Serviço Social do seu Campus solicita que você anexe a seguinte documentação complementar: <strong>{}</strong>. Caso não anexe a documentação solicitada até a data <strong>{}</strong>, sua inscrição será invalidada.</p><p>Procure o setor de Serviço Social do seu campus para mais informações.</p>'.format(
                        form.cleaned_data.get('documentacao_pendente'), format_(form.cleaned_data.get('data_limite'))
                    )
                )
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [inscricao.aluno.get_vinculo()])
            else:
                inscricao.documentacao_pendente = None
                inscricao.data_limite_envio_documentacao = None
            inscricao.save()
            return httprr(form.cleaned_data.get('url'), 'Parecer cadastrado com sucesso.')
    else:
        form = ParecerInscricaoForm(request.POST or None, inscricao=inscricao, url=url_origem)
    return locals()


@rtr()
@permission_required('ae.pode_ver_comprovante_inscricao')
def comprovante_inscricao(request, tipo_auxilio, inscricao_pk):
    title = 'Comprovante de Inscrição'
    inscricao = retorna_inscricao(tipo_auxilio, inscricao_pk)
    if InscricaoAluno.objects.filter(aluno__pk=inscricao.aluno_id).exists():
        inscricao_caracterizacao = InscricaoAluno.objects.filter(aluno__pk=inscricao.aluno_id).latest('id')
        integrantes_familiares = IntegranteFamiliar.objects.filter(aluno=inscricao.aluno).distinct('nome')

    return locals()


@rtr(two_factor_authentication=True)
@permission_required('edu.pode_editar_caracterizacao, ae.change_programa')
def atualizar_dados_bancarios(request, aluno_pk):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    title = f'Atualizar Dados Bancários - {aluno}'
    if request.user.get_relacionamento() != aluno and not request.user.has_perm('ae.change_programa'):
        raise PermissionDenied
    inscricao_aluno = get_object_or_404(InscricaoAluno, aluno=aluno)
    form = AtualizarDadosBancariosForm(request.POST or None, instance=inscricao_aluno)
    if form.is_valid():
        form.save()
        if request.user.has_perm('ae.change_programa'):
            return httprr('/', 'Dados Bancários atualizados com sucesso.')
        else:
            return httprr('/auxilioemergencial/minhas_inscricoes/', 'Dados Bancários atualizados com sucesso.')

    return locals()


@rtr()
@permission_required('edu.pode_editar_caracterizacao')
def assinar_termo(request, tipo_auxilio, inscricao_pk):
    title = 'Assinar Termo de Compromisso'
    inscricao = retorna_inscricao(tipo_auxilio, inscricao_pk)
    if request.user.get_relacionamento() != inscricao.aluno:
        raise PermissionDenied
    if not inscricao.pode_assinar_termo():
        raise PermissionDenied

    eh_maior_dezoito_anos = inscricao.aluno.pessoa_fisica.nascimento_data < (date.today() + relativedelta(years=-18))
    # if inscricao.get_tipo_auxilio() == 'MAT':
    #    eh_maior_dezoito_anos = True
    form = AssinarTermoForm(request.POST or None, request.FILES or None, eh_maior_dezoito_anos=eh_maior_dezoito_anos)
    if form.is_valid():
        inscricao.termo_compromisso_assinado = True
        inscricao.termo_compromisso_assinado_em = datetime.datetime.now()
        inscricao.save()
        if form.cleaned_data.get('termo'):
            nova_documentacao = DocumentoAluno()
            nova_documentacao.aluno = inscricao.aluno
            nova_documentacao.descricao = 'Termo de Compromisso'
            nova_documentacao.tipo = DocumentoAluno.TERMO_COMPROMISSO
            arquivo = form.cleaned_data.get('termo')
            filename = generate_filename(
                parts=[request.user.get_profile().id, datetime.datetime.now().date(), datetime.datetime.now()],
                file_obj=arquivo,
            )
            arquivo.name = filename
            nova_documentacao.arquivo = arquivo
            nova_documentacao.cadastrado_por = request.user.get_vinculo()
            nova_documentacao.data_cadastro = datetime.datetime.now()
            nova_documentacao.save()

        return httprr('/auxilioemergencial/minhas_inscricoes/', 'Termo de compromisso assinado com sucesso.')

    return locals()


@rtr()
@permission_required('edu.pode_editar_caracterizacao')
def minhas_inscricoes(request):
    title = 'Minhas Inscrições - Auxílios Emergenciais'
    if not request.user.eh_aluno:
        return httprr('/', 'Somente alunos têm acesso aos auxílios emergenciais.', 'error')

    aluno = request.user.get_relacionamento()
    lista_inscricoes = [
        *list(InscricaoInternet.objects.filter(aluno=aluno)),
        *list(InscricaoDispositivo.objects.filter(aluno=aluno)),
        *list(InscricaoMaterialPedagogico.objects.filter(aluno=aluno)),
        *list(InscricaoAlunoConectado.objects.filter(aluno=aluno)),
    ]

    return locals()


@rtr()
@permission_required('edu.pode_editar_caracterizacao, ae.change_programa, auxilioemergencial.pode_adicionar_prestacao_contas')
def documentacao_aluno(request, aluno_pk, tipo_auxilio, inscricao_pk):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    title = f'Documentação de {aluno}'
    if (
        aluno != request.user.get_relacionamento()
        and not request.user.has_perm('ae.change_programa')
        and not request.user.has_perm('auxilioemergencial.pode_adicionar_prestacao_contas')
    ):
        raise PermissionDenied
    eh_assistente_social = request.user.has_perm('ae.change_programa') or request.user.has_perm('auxilioemergencial.pode_adicionar_prestacao_contas')
    inscricao_dispositivo_2021 = InscricaoDispositivo.objects.filter(
        aluno=aluno, prestacao_contas_cadastrada_em__isnull=False, data_cadastro__year=2021
    )
    inscricao_dispositivo_2020 = InscricaoDispositivo.objects.filter(
        aluno=aluno, prestacao_contas_cadastrada_em__isnull=False, data_cadastro__year=2020
    )
    documentos_atuais = DocumentoAluno.objects.filter(aluno=aluno, data_cadastro__year=2021).order_by('-data_cadastro')
    documentos_2020 = DocumentoAluno.objects.filter(aluno=aluno, data_cadastro__year=2020).order_by('-data_cadastro')
    contador_2021 = documentos_atuais.count() + inscricao_dispositivo_2021.count()
    contador_2020 = documentos_2020.count() + inscricao_dispositivo_2020.count()
    tem_documentos = documentos_atuais.exists() or documentos_2020.exists()
    campus_do_aluno = aluno.curso_campus.diretoria.setor.uo
    id_da_inscricao = request.GET.get('id')
    inscricao = retorna_inscricao(tipo_auxilio, inscricao_pk)
    if inscricao:
        edital_em_inscricao = inscricao.edital.eh_ativo()
        inscricao_pendente_documentos = inscricao.parecer == PENDENTE_DOCUMENTACAO
        edital_ativo = inscricao.edital.ativo
        pode_cadastrar = (
            edital_em_inscricao
            or (edital_ativo and inscricao_pendente_documentos and inscricao.data_limite_envio_documentacao >= datetime.date.today())
        ) and not request.user.has_perm('ae.change_programa')

        form = AdicionarDocumentoForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            agora = datetime.datetime.now()
            o = form.save(False)
            o.aluno = aluno
            o.tipo = DocumentoAluno.DOCUMENTACAO_COMPLEMENTAR
            o.data_cadastro = agora
            o.cadastrado_por = request.user.get_vinculo()
            o.save()
            if edital_em_inscricao:
                InscricaoInternet.objects.filter(aluno=aluno).update(documentacao_atualizada_em=agora)
                InscricaoDispositivo.objects.filter(aluno=aluno).update(documentacao_atualizada_em=agora)
                InscricaoMaterialPedagogico.objects.filter(aluno=aluno).update(documentacao_atualizada_em=agora)
            inscricao.documentacao_atualizada_em = agora
            if edital_ativo and inscricao.parecer == PENDENTE_DOCUMENTACAO:
                inscricao.parecer = SEM_PARECER
                inscricao.data_parecer = None
            inscricao.save()
            return httprr('.', 'Documentação cadastrada com sucesso.')
        else:
            form = AdicionarDocumentoForm()
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required('ae.pode_ver_comprovante_inscricao')
def folha_pagamento(request, tipo_auxilio):
    if tipo_auxilio == 'INT':
        registros = InscricaoInternet.objects.filter(termo_compromisso_assinado_em__isnull=False, parecer='Deferido')
        title = 'Folha de Pagamento - Auxílio de Serviço de Internet'
    elif tipo_auxilio == 'DIS':
        registros = InscricaoDispositivo.objects.filter(termo_compromisso_assinado_em__isnull=False, parecer='Deferido')
        title = 'Folha de Pagamento - Auxílio para Aquisição de Dispositivo Eletrônico'
    elif tipo_auxilio == 'MAT':
        registros = InscricaoMaterialPedagogico.objects.filter(termo_compromisso_assinado_em__isnull=False, parecer='Deferido')
        title = 'Folha de Pagamento - Auxílio para Material Didático Pedagógico'
    elif tipo_auxilio == 'CHP':
        registros = InscricaoAlunoConectado.objects.filter(termo_compromisso_assinado_em__isnull=False, parecer='Deferido')
        title = 'Folha de Pagamento - Auxílio para o Projeto Alunos Conectados'
    lista = []
    form = FolhaPagamentoForm(request.GET or None, tipo=tipo_auxilio, request=request)
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        edital = form.cleaned_data.get('edital')
        ano = form.cleaned_data.get('ano')
        mes = form.cleaned_data.get('mes')
        ver_nome = form.cleaned_data['ver_nome']
        ver_matricula = form.cleaned_data['ver_matricula']
        ver_cpf = form.cleaned_data['ver_cpf']
        ver_banco = form.cleaned_data['ver_banco']
        ver_agencia = form.cleaned_data['ver_agencia']
        ver_operacao = form.cleaned_data['ver_operacao']
        ver_conta = form.cleaned_data['ver_conta']
        ver_tipo_passe = form.cleaned_data['ver_tipo_passe']
        ver_valor_padrao = form.cleaned_data['ver_valor_padrao']
        ver_valor_pagar = form.cleaned_data['ver_valor_pagar']
        total_escolhido = len(form.changed_data) - 2

        registros = registros.filter(edital__campus=campus)
        dias_do_mes = 30

        total = 0
        if edital:
            registros = registros.filter(edital=edital)
        if tipo_auxilio == 'INT':
            data_inicio = datetime.datetime(ano.ano, int(mes), 1).date()
            if int(mes) == 12:
                data_termino = datetime.datetime(ano.ano + 1, 1, 1).date()
            else:
                data_termino = datetime.datetime(ano.ano, int(mes) + 1, 1).date()
            registros = registros.filter(
                Q(fim_auxilio__gt=data_inicio, termo_compromisso_assinado_em__lt=data_termino)
                | Q(fim_auxilio__isnull=True, termo_compromisso_assinado_em__lt=data_termino)
            )
            for item in registros:
                inicio_auxilio = item.termo_compromisso_assinado_em.date()
                fim_auxilio = None
                valor = item.valor_concedido
                # if inicio_auxilio > data_inicio and inicio_auxilio.month == int(mes):
                #     diferenca = data_termino - inicio_auxilio
                #     valor = Decimal((valor / dias_do_mes) * diferenca.days).quantize(Decimal(10) ** -2)
                # if fim_auxilio and fim_auxilio < data_termino and fim_auxilio.month == int(mes):
                #     diferenca = fim_auxilio - data_inicio
                #     valor = Decimal((valor / dias_do_mes) * diferenca.days).quantize(Decimal(10) ** -2)
                total += Decimal(valor)
                lista.append((item, valor))
        else:
            registros = registros.filter(fim_auxilio__isnull=True)
            for item in registros:
                inicio_auxilio = item.termo_compromisso_assinado_em.date()
                fim_auxilio = None
                valor = item.valor_concedido or 0
                # if inicio_auxilio > data_inicio and inicio_auxilio.month == int(mes):
                #     diferenca = data_termino - inicio_auxilio
                #     valor = Decimal((valor / dias_do_mes) * diferenca.days).quantize(Decimal(10) ** -2)
                # if fim_auxilio and fim_auxilio < data_termino and fim_auxilio.month == int(mes):
                #     diferenca = fim_auxilio - data_inicio
                #     valor = Decimal((valor / dias_do_mes) * diferenca.days).quantize(Decimal(10) ** -2)
                total += Decimal(valor)
                lista.append((item, valor))

        if 'xls' in request.GET:
            return tasks.folha_pagamento_to_xls(
                lista,
                ver_nome,
                ver_matricula,
                ver_cpf,
                ver_banco,
                ver_agencia,
                ver_operacao,
                ver_conta,
                ver_valor_pagar,
                total,
            )

    return locals()


@rtr()
@permission_required('ae.pode_ver_comprovante_inscricao')
def encerrar_auxilio(request, tipo_auxilio, inscricao_pk):
    title = 'Encerrar Auxílio'
    inscricao = retorna_inscricao(tipo_auxilio, inscricao_pk)
    form = DataEncerramentoForm(request.POST or None)
    if form.is_valid():
        inscricao.fim_auxilio = form.cleaned_data.get('data')
        inscricao.save()
        return httprr(f'/admin/auxilioemergencial/{inscricao.get_nome_admin()}/', 'Auxílio encerrado com sucesso.')
    return locals()


@rtr()
@permission_required('auxilioemergencial.pode_adicionar_prestacao_contas')
def prestacao_contas_dispositivo(request, inscricao_pk):
    title = 'Adicionar Prestação de Contas'
    inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
    if inscricao.edital.campus != get_uo(request.user):
        raise PermissionDenied
    url = request.META.get('HTTP_REFERER', '.')
    if request.POST:
        form = PrestacaoContasDispositivoForm(request.POST or None, request.FILES or None, instance=inscricao)
        if form.is_valid():
            o = form.save(False)
            o.prestacao_contas_cadastrada_em = datetime.datetime.now()
            o.prestacao_contas_cadastrada_por = request.user.get_vinculo()
            o.situacao_prestacao_contas = InscricaoMaterialPedagogico.CONCLUIDA
            o.save()
            return httprr(form.cleaned_data.get('url'), 'Auxílio encerrado com sucesso.')
    else:
        form = PrestacaoContasDispositivoForm(request.POST or None, request.FILES or None, instance=inscricao, url=url)
    return locals()


@rtr()
@permission_required('edu.pode_editar_caracterizacao')
def prestacao_contas(request, inscricao_pk, tipo_auxilio):
    title = 'Adicionar Prestação de Contas'
    if tipo_auxilio == 'DIS':
        inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
        form = PrestacaoContasForm(request.POST or None, request.FILES or None, instance=inscricao)
    elif tipo_auxilio == 'MAT':
        inscricao = get_object_or_404(InscricaoMaterialPedagogico, pk=inscricao_pk)
        form = PrestacaoContasMaterialForm(request.POST or None, request.FILES or None, instance=inscricao)
    else:
        raise PermissionDenied
    if inscricao.aluno != request.user.get_relacionamento():
        raise PermissionDenied
    if not inscricao.pode_cadastrar_prestacao_contas():
        raise PermissionDenied

    title = f'Prestação de Contas - {inscricao}'
    if form.is_valid():
        o = form.save(False)
        if not inscricao.prestacao_contas_cadastrada_em:
            o.prestacao_contas_cadastrada_em = datetime.datetime.now()
            o.prestacao_contas_cadastrada_por = request.user.get_vinculo()
        o.prestacao_contas_atualizada_em = datetime.datetime.now()
        o.prestacao_contas_atualizada_por = request.user.get_vinculo()
        o.situacao_prestacao_contas = InscricaoMaterialPedagogico.PENDENTE_VALIDACAO
        o.save()
        return httprr('/auxilioemergencial/minhas_inscricoes/', 'Prestação de contas cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.pode_editar_caracterizacao, ae.change_programa, auxilioemergencial.pode_adicionar_prestacao_contas')
def editar_documento(request, documento_pk, inscricao_pk, tipo_auxilio):
    documento = get_object_or_404(DocumentoAluno, pk=documento_pk)
    inscricao = retorna_inscricao(tipo_auxilio, inscricao_pk)
    edital_em_inscricao = inscricao.edital.eh_ativo()
    edital_ativo = inscricao.edital.ativo
    eh_assistente_social = request.user.has_perm('ae.change_programa') or request.user.has_perm('auxilioemergencial.pode_adicionar_prestacao_contas')
    if (
        inscricao and inscricao.pode_atualizar_documentacao() and documento.tipo and documento.cadastrado_por == request.user.get_vinculo()
    ) or eh_assistente_social:
        aluno = documento.aluno
        title = f'Editar Documentação de {aluno}'

        form = AdicionarDocumentoForm(request.POST or None, request.FILES or None, instance=documento)
        if form.is_valid():
            agora = datetime.datetime.now()
            o = form.save(False)
            o.aluno = aluno
            o.tipo = DocumentoAluno.DOCUMENTACAO_COMPLEMENTAR
            o.data_cadastro = agora
            o.cadastrado_por = request.user.get_vinculo()
            o.save()
            if edital_em_inscricao:
                InscricaoInternet.objects.filter(aluno=aluno, edital=inscricao.edital).update(documentacao_atualizada_em=agora)
                InscricaoDispositivo.objects.filter(aluno=aluno, edital=inscricao.edital).update(documentacao_atualizada_em=agora)
                InscricaoMaterialPedagogico.objects.filter(aluno=aluno, edital=inscricao.edital).update(documentacao_atualizada_em=agora)
            inscricao.documentacao_atualizada_em = agora
            if edital_ativo and inscricao.parecer == PENDENTE_DOCUMENTACAO:
                inscricao.parecer = SEM_PARECER
                inscricao.data_parecer = None
            inscricao.save()
            return httprr(f'/auxilioemergencial/documentacao_aluno/{aluno.pk}/{tipo_auxilio}/{inscricao_pk}/', 'Documentação editada com sucesso.')
        return locals()

    else:
        raise PermissionDenied


@rtr()
@permission_required(['auxilioemergencial.view_inscricaodispositivo', 'comum.is_auditor'])
def listar_prestacoes_conta(request):
    title = 'Prestações de Contas'
    eh_assistente_social = request.user.has_perm('auxilioemergencial.add_edital')
    inscricoes_dispositivo = (
        InscricaoDispositivo.objects.filter(parecer='Deferido')
        .exclude(situacao_prestacao_contas=InscricaoDispositivo.NAO_INFORMADO)
        .order_by('aluno')
    )
    inscricoes_material = (
        InscricaoMaterialPedagogico.objects.filter(parecer='Deferido')
        .exclude(situacao_prestacao_contas=InscricaoDispositivo.NAO_INFORMADO)
        .order_by('aluno')
    )
    if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
        inscricoes_dispositivo = inscricoes_dispositivo.filter(edital__campus=get_uo(request.user))
        inscricoes_material = inscricoes_material.filter(edital__campus=get_uo(request.user))
    form = FiltraPrestacaoForm(request.GET or None, request=request)
    if form.is_valid():
        situacao = form.cleaned_data.get('situacao')
        busca = form.cleaned_data.get('busca')
        edital = form.cleaned_data.get('edital')
        campus = form.cleaned_data.get('campus')
        ano = form.cleaned_data.get('ano')

        if situacao:
            inscricoes_dispositivo = inscricoes_dispositivo.filter(situacao_prestacao_contas=situacao)
            inscricoes_material = inscricoes_material.filter(situacao_prestacao_contas=situacao)
        if busca:
            inscricoes_dispositivo = inscricoes_dispositivo.filter(
                Q(aluno__matricula__icontains=busca) | Q(aluno__pessoa_fisica__nome__icontains=busca)
            )
            inscricoes_material = inscricoes_material.filter(Q(aluno__matricula__icontains=busca) | Q(aluno__pessoa_fisica__nome__icontains=busca))
        if edital:
            inscricoes_dispositivo = inscricoes_dispositivo.filter(edital=edital)
            inscricoes_material = inscricoes_material.filter(edital=edital)
        if campus:
            inscricoes_dispositivo = inscricoes_dispositivo.filter(edital__campus=campus)
            inscricoes_material = inscricoes_material.filter(edital__campus=campus)
        if ano:
            inscricoes_dispositivo = inscricoes_dispositivo.filter(prestacao_contas_cadastrada_em__year=ano)
            inscricoes_material = inscricoes_material.filter(prestacao_contas_cadastrada_em__year=ano)

    return locals()


@rtr()
@permission_required('auxilioemergencial.pode_adicionar_prestacao_contas')
def adicionar_pendencia(request, inscricao_pk, tipo_auxilio):
    if tipo_auxilio == 'DIS':
        inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
        form = PendenciaDispositivoForm(request.POST or None, request.FILES or None, instance=inscricao)
    elif tipo_auxilio == 'MAT':
        inscricao = get_object_or_404(InscricaoMaterialPedagogico, pk=inscricao_pk)
        form = PendenciaMaterialForm(request.POST or None, request.FILES or None, instance=inscricao)
    else:
        raise PermissionDenied
    if inscricao.edital.campus != get_uo(request.user) and not request.user.has_perm('ae.pode_ver_relatorios_todos'):
        raise PermissionDenied

    title = f'Adicionar Pendência - {inscricao} - {inscricao.aluno}'
    if form.is_valid():
        o = form.save(False)
        o.pendencia_cadastrada_em = datetime.datetime.now()
        o.pendencia_cadastrada_por = request.user.get_vinculo()
        o.situacao_prestacao_contas = InscricaoMaterialPedagogico.AGUARDANDO_DOCUMENTOS
        o.save()

        titulo = '[SUAP] Auxílio Emergencial: Pendência na Prestação de Contas'
        texto = (
            '<h1>Serviço Social</h1>'
            '<h2>Auxílio Emergencial</h2>'
            '<p>A Comissão de prestação de contas dos auxílios emergenciais do seu Campus solicita que você anexe a seguinte documentação: {}. Você deverá editar o documento da sua prestação de contas até a data {}, adicionando o documento solicitado pela Comissão.</p>'.format(
                inscricao.pendencia_prestacao_contas, inscricao.data_limite_envio_prestacao_contas.strftime('%d/%m/%Y')
            )
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [inscricao.aluno.get_vinculo()])
        return httprr('/auxilioemergencial/listar_prestacoes_conta/', 'Pendências cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('auxilioemergencial.view_inscricaodispositivo')
def adicionar_gru(request, inscricao_pk, tipo_auxilio):
    if tipo_auxilio == 'DIS':
        inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
        form = GRUDispositivoForm(request.POST or None, request.FILES or None, instance=inscricao)
    elif tipo_auxilio == 'MAT':
        inscricao = get_object_or_404(InscricaoMaterialPedagogico, pk=inscricao_pk)
        form = GRUMaterialForm(request.POST or None, request.FILES or None, instance=inscricao)
    else:
        raise PermissionDenied
    if inscricao.edital.campus != get_uo(request.user) and not request.user.has_perm('ae.pode_ver_relatorios_todos'):
        raise PermissionDenied
    if not inscricao.arquivo_prestacao_contas:
        raise PermissionDenied

    title = f'Adicionar GRU - {inscricao} - {inscricao.aluno}'
    if form.is_valid():
        o = form.save(False)
        o.arquivo_gru_cadastrado_em = datetime.datetime.now()
        o.arquivo_gru_cadastrado_por = request.user.get_vinculo()
        o.situacao_prestacao_contas = InscricaoMaterialPedagogico.AGUARDANDO_DOCUMENTOS
        o.save()

        titulo = '[SUAP] Auxílio Emergencial: Cadastro de GRU da Prestação de Contas'
        texto = (
            '<h1>Serviço Social</h1>'
            '<h2>Auxílio Emergencial</h2>'
            '<p>A Comissão de prestação de contas dos auxílios emergenciais do seu Campus adicionou GRU para pagamento na sua prestação de contas.</p>'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [inscricao.aluno.get_vinculo()])

        return httprr('/auxilioemergencial/listar_prestacoes_conta/', 'GRU cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('auxilioemergencial.pode_adicionar_prestacao_contas')
def concluir_prestacao(request, inscricao_pk, tipo_auxilio):
    if tipo_auxilio == 'DIS':
        inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
    elif tipo_auxilio == 'MAT':
        inscricao = get_object_or_404(InscricaoMaterialPedagogico, pk=inscricao_pk)
    else:
        raise PermissionDenied
    if inscricao.edital.campus != get_uo(request.user) and not request.user.has_perm('ae.pode_ver_relatorios_todos'):
        raise PermissionDenied

    inscricao.prestacao_concluida_em = datetime.datetime.now()
    inscricao.prestacao_concluida_por = request.user.get_vinculo()
    inscricao.situacao_prestacao_contas = InscricaoMaterialPedagogico.CONCLUIDA
    inscricao.save()

    titulo = '[SUAP] Auxílio Emergencial: Prestação de Contas Concluída'
    texto = (
        '<h1>Serviço Social</h1>'
        '<h2>Auxílio Emergencial</h2>'
        f'<p>A sua prestação de contas referente ao auxílio de {inscricao} foi aprovada e concluída pela Comissão.</p>'
    )
    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [inscricao.aluno.get_vinculo()])

    return httprr('/auxilioemergencial/listar_prestacoes_conta/', 'Prestação de contas concluída com sucesso.')


@rtr()
@permission_required('edu.pode_editar_caracterizacao')
def cadastrar_gru(request, inscricao_pk, tipo_auxilio):
    if tipo_auxilio == 'DIS':
        inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
        form = ComprovanteGRUDispositivoForm(request.POST or None, request.FILES or None, instance=inscricao)
    elif tipo_auxilio == 'MAT':
        inscricao = get_object_or_404(InscricaoMaterialPedagogico, pk=inscricao_pk)
        form = ComprovanteGRUMaterialForm(request.POST or None, request.FILES or None, instance=inscricao)
    else:
        raise PermissionDenied
    if inscricao.aluno != request.user.get_relacionamento():
        raise PermissionDenied

    title = f'Cadastrar Comprovante de GRU - {inscricao}'
    if form.is_valid():
        o = form.save(False)
        o.comprovante_gru_cadastrado_em = datetime.datetime.now()
        o.comprovante_gru_cadastrado_por = request.user.get_vinculo()
        o.situacao_prestacao_contas = InscricaoMaterialPedagogico.PENDENTE_VALIDACAO
        o.save()
        return httprr('/auxilioemergencial/minhas_inscricoes/', 'Prestação de contas cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('auxilioemergencial.pode_adicionar_prestacao_contas')
def editar_prestacao(request, inscricao_pk, tipo_auxilio):
    if tipo_auxilio == 'DIS':
        inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
        form = PrestacaoContasForm(request.POST or None, request.FILES or None, instance=inscricao)
    elif tipo_auxilio == 'MAT':
        inscricao = get_object_or_404(InscricaoMaterialPedagogico, pk=inscricao_pk)
        form = PrestacaoContasMaterialForm(request.POST or None, request.FILES or None, instance=inscricao)
    else:
        raise PermissionDenied
    if inscricao.edital.campus != get_uo(request.user) and not request.user.has_perm('ae.pode_ver_relatorios_todos'):
        raise PermissionDenied
    title = f'Editar Prestação de Contas - {inscricao}'
    if form.is_valid():
        o = form.save(False)
        o.prestacao_contas_atualizada_em = datetime.datetime.now()
        o.prestacao_contas_atualizada_por = request.user.get_vinculo()
        if inscricao.situacao_prestacao_contas == InscricaoMaterialPedagogico.AGUARDANDO_DOCUMENTOS:
            o.situacao_prestacao_contas = InscricaoMaterialPedagogico.PENDENTE_VALIDACAO
        o.save()
        return httprr('/auxilioemergencial/listar_prestacoes_conta/', 'Prestação de Contas editada com sucesso.')
    return locals()


@rtr()
@permission_required('auxilioemergencial.view_inscricaodispositivo')
def editar_comprovante_gru(request, inscricao_pk, tipo_auxilio):
    if tipo_auxilio == 'DIS':
        inscricao = get_object_or_404(InscricaoDispositivo, pk=inscricao_pk)
        form = ComprovanteGRUDispositivoForm(request.POST or None, request.FILES or None, instance=inscricao)
    elif tipo_auxilio == 'MAT':
        inscricao = get_object_or_404(InscricaoMaterialPedagogico, pk=inscricao_pk)
        form = ComprovanteGRUMaterialForm(request.POST or None, request.FILES or None, instance=inscricao)
    else:
        raise PermissionDenied
    if inscricao.edital.campus != get_uo(request.user) and not request.user.has_perm('ae.pode_ver_relatorios_todos'):
        raise PermissionDenied
    title = f'Editar Comprovante de GRU - {inscricao}'
    if form.is_valid():
        o = form.save(False)
        o.comprovante_gru_cadastrado_em = datetime.datetime.now()
        o.comprovante_gru_cadastrado_por = request.user.get_vinculo()
        if inscricao.situacao_prestacao_contas == InscricaoMaterialPedagogico.AGUARDANDO_DOCUMENTOS:
            o.situacao_prestacao_contas = InscricaoMaterialPedagogico.PENDENTE_VALIDACAO
        o.save()
        return httprr('/auxilioemergencial/listar_prestacoes_conta/', 'Comprovante da GRU editada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.pode_editar_caracterizacao')
def assinatura_responsavel(request, tipo_auxilio, inscricao_pk):
    title = 'Assinatura do Responsável'
    inscricao = retorna_inscricao(tipo_auxilio, inscricao_pk)
    aluno_logado = request.user.get_relacionamento()
    if aluno_logado != inscricao.aluno:
        raise PermissionDenied
    if inscricao.pendente_assinatura() and inscricao.edital.eh_ativo():
        form = AssinaturaResponsavelForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            agora = datetime.datetime.now()
            o = form.save(False)
            o.aluno = aluno_logado
            o.data_cadastro = agora
            o.descricao = 'Termo de Compromisso Assinado pelo Responsável'
            o.cadastrado_por = request.user.get_vinculo()
            o.save()
            inscricao.assinado_pelo_responsavel = True
            inscricao.assinado_pelo_responsavel_em = datetime.datetime.now()
            inscricao.situacao = 'Concluída'
            inscricao.save()
            return httprr('/auxilioemergencial/minhas_inscricoes/', 'Inscrição assinada com sucesso.')
        return locals()
    else:
        raise PermissionDenied


@rtr()
@permission_required(['auxilioemergencial.add_edital', 'comum.is_auditor'])
def relatorio_rendimento_frequencia(request):
    title = 'Relatório: Alunos Participantes x Índices Acadêmicos'
    form = RelatorioRendimentoFrequenciaForm(request.GET or None, request=request)
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        ano = form.cleaned_data.get('ano')
        periodo = form.cleaned_data.get('periodo')
        programa = form.cleaned_data.get('programa')
        edital = form.cleaned_data.get('edital')
        data_inicio = datetime.datetime(int(ano), 1, 1).date()
        data_fim = datetime.datetime(int(ano), 12, 31).date()
        edital = form.cleaned_data.get('edital')
        if programa == 'INT':
            total_inscritos = InscricaoInternet.objects.all()
        elif programa == 'DIS':
            total_inscritos = InscricaoDispositivo.objects.all()
        elif programa == 'MAT':
            total_inscritos = InscricaoMaterialPedagogico.objects.all()
        elif programa == 'CHP':
            total_inscritos = InscricaoAlunoConectado.objects.all()
        if edital:
            total_inscritos = total_inscritos.filter(edital=edital)
        periodos_matricula = MatriculaPeriodo.objects.filter(ano_letivo__ano=int(ano))
        if periodo:
            periodos_matricula = periodos_matricula.filter(periodo_letivo=periodo)
            if periodo == '1':
                data_fim = datetime.datetime(int(ano), 6, 30).date()
            else:
                data_inicio = datetime.datetime(int(ano), 7, 1).date()

        hoje = date.today()
        if campus:
            periodos_matricula = periodos_matricula.filter(aluno__curso_campus__diretoria__setor__uo=campus)
            total_inscritos = total_inscritos.filter(aluno__curso_campus__diretoria__setor__uo=campus)
        elif not request.user.has_perm('ae.pode_ver_relatorios_todos'):
            campus = get_uo(request.user).id
            periodos_matricula = periodos_matricula.filter(aluno__curso_campus__diretoria__setor__uo=campus)
            total_inscritos = total_inscritos.filter(aluno__curso_campus__diretoria__setor__uo=campus)

        deferidos = total_inscritos.filter(termo_compromisso_assinado_em__isnull=False)
        indeferidos = total_inscritos.filter(parecer='Indeferido')
        deferidos_sem_recurso = total_inscritos.filter(parecer=DEFERIDO_SEM_RECURSO)
        em_analise = total_inscritos.filter(parecer=SEM_PARECER)
        matriculas = periodos_matricula.filter(aluno__in=deferidos.values_list('aluno', flat=True)).order_by('aluno')

        alunos = []
        frequencia_acima_75 = 0
        frequencia_abaixo_75 = 0
        for matricula in matriculas:
            texto = ''
            if InscricaoInternet.objects.filter(aluno=matricula.aluno, termo_compromisso_assinado_em__isnull=False).exists():
                ultimo = InscricaoInternet.objects.filter(aluno=matricula.aluno, termo_compromisso_assinado_em__isnull=False).latest('id')
                texto = texto + '{} (<b>Entrada em: {}</b>), '.format(ultimo.__str__(), ultimo.termo_compromisso_assinado_em.strftime('%d/%m/%Y'))
            if InscricaoDispositivo.objects.filter(aluno=matricula.aluno, termo_compromisso_assinado_em__isnull=False).exists():
                ultimo = InscricaoDispositivo.objects.filter(aluno=matricula.aluno, termo_compromisso_assinado_em__isnull=False).latest('id')
                texto = texto + '{} (<b>Entrada em: {}</b>), '.format(ultimo.__str__(), ultimo.termo_compromisso_assinado_em.strftime('%d/%m/%Y'))
            if InscricaoMaterialPedagogico.objects.filter(aluno=matricula.aluno, termo_compromisso_assinado_em__isnull=False).exists():
                ultimo = InscricaoMaterialPedagogico.objects.filter(aluno=matricula.aluno, termo_compromisso_assinado_em__isnull=False).latest('id')
                texto = texto + '{} (<b>Entrada em: {}</b>), '.format(ultimo.__str__(), ultimo.termo_compromisso_assinado_em.strftime('%d/%m/%Y'))
            if InscricaoAlunoConectado.objects.filter(aluno=matricula.aluno, termo_compromisso_assinado_em__isnull=False).exists():
                ultimo = InscricaoAlunoConectado.objects.filter(aluno=matricula.aluno, termo_compromisso_assinado_em__isnull=False).latest('id')
                texto = texto + '{} (<b>Entrada em: {}</b>), '.format(ultimo.__str__(), ultimo.termo_compromisso_assinado_em.strftime('%d/%m/%Y'))
            texto = texto[:-2]

            frequencia = matricula.get_percentual_carga_horaria_frequentada()
            if frequencia > 75:
                frequencia_acima_75 = frequencia_acima_75 + 1
            else:
                frequencia_abaixo_75 = frequencia_abaixo_75 + 1

            alunos.append(
                [
                    matricula.aluno.matricula,
                    matricula.aluno,
                    matricula.aluno.curso_campus,
                    texto,
                    matricula.aluno.get_ira(),
                    frequencia,
                    matricula.aluno.get_ira_curso_aluno(),
                    matricula.aluno.get_total_medidas_disciplinares_premiacoes(data_inicio, data_fim),
                    matricula.aluno.get_total_atividades_complementares(data_inicio, data_fim),
                ]
            )

        series1 = (('Entre 60 e 100', matriculas.filter(aluno__ira__gte=60).count()), ('Abaixo de 60', matriculas.filter(aluno__ira__lt=60).count()))

        grafico1 = PieChart(
            'grafico1',
            title='Quantidade de alunos por Rendimento Acadêmico',
            subtitle='Percentual de alunos com rendimento acadêmico entre 60 e 100',
            minPointLength=0,
            data=series1,
        )
        grafico1.id = 'grafico1'

        series2 = (('Acima de 75%', frequencia_acima_75), ('Abaixo de 75%', frequencia_abaixo_75))

        grafico2 = PieChart(
            'grafico2',
            title='Quantidade de alunos por Frequência',
            subtitle='Percentual de alunos com frequência acima de 75%',
            minPointLength=0,
            data=series2,
        )
        grafico2.id = 'grafico2'

        series3 = (
            ('Deferidos', deferidos.count()),
            ('Indeferidos', indeferidos.count()),
            ('Deferido, mas sem recurso disponível para atendimento no momento', deferidos_sem_recurso.count()),
            ('Em análise', em_analise.count()),
        )

        grafico3 = PieChart('grafico3', title='Demanda Reprimida', subtitle='Quantidade de Inscritos e de Deferidos', minPointLength=0, data=series3)
        grafico3.id = 'grafico3'

        graficos_relatorio = [grafico1, grafico2, grafico3]

    if request.method == 'GET' and 'xls' in request.GET:
        return tasks.relatorio_rendimento_frequencia_xls(matriculas, total_inscritos, data_inicio, data_fim)

    return locals()


@rtr()
@permission_required(['auxilioemergencial.add_edital', 'comum.is_auditor'])
def relatorio_alunos_assistidos(request):
    title = 'Relatório de alunos assistidos'
    form = RelatorioAlunosAtendidosForm(request.GET or None, request=request)
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        ano = form.cleaned_data.get('ano')
        edital = form.cleaned_data.get('edital')
        int = InscricaoInternet.objects.filter(parecer='Deferido')
        dis = InscricaoDispositivo.objects.filter(parecer='Deferido')
        mat = InscricaoMaterialPedagogico.objects.filter(parecer='Deferido')
        chp = InscricaoAlunoConectado.objects.filter(parecer='Deferido')
        from ae.models import Participacao

        participacoes_ae = Participacao.objects.all()
        if edital:
            int = int.filter(edital=edital)
            dis = dis.filter(edital=edital)
            mat = mat.filter(edital=edital)
            chp = chp.filter(edital=edital)
        if campus:
            int = int.filter(aluno__curso_campus__diretoria__setor__uo=campus)
            dis = dis.filter(aluno__curso_campus__diretoria__setor__uo=campus)
            mat = mat.filter(aluno__curso_campus__diretoria__setor__uo=campus)
            chp = chp.filter(aluno__curso_campus__diretoria__setor__uo=campus)
            participacoes_ae = participacoes_ae.filter(aluno__curso_campus__diretoria__setor__uo=campus)

        if ano:
            int = int.filter(data_cadastro__year=ano)
            dis = dis.filter(data_cadastro__year=ano)
            mat = mat.filter(data_cadastro__year=ano)
            chp = chp.filter(data_cadastro__year=ano)
            participacoes_ae = participacoes_ae.filter(Q(data_inicio__year__lte=ano), Q(data_termino__isnull=True) | Q(data_termino__year__gte=ano))
        total_int = len(set(int.values_list('aluno', flat=True)))
        total_dis = len(set(dis.values_list('aluno', flat=True)))
        total_chp = len(set(chp.values_list('aluno', flat=True)))
        total_mat = len(set(mat.values_list('aluno', flat=True)))
        total_participacoes = int.count() + dis.count() + mat.count() + chp.count()
        total_assistidos = (
            Aluno.objects.filter(id__in=int.values_list('aluno', flat=True))
            | Aluno.objects.filter(id__in=dis.values_list('aluno', flat=True))
            | Aluno.objects.filter(id__in=mat.values_list('aluno', flat=True))
            | Aluno.objects.filter(id__in=chp.values_list('aluno', flat=True))
        )
        total_assistidos = total_assistidos.count()
        total_geral_alunos_assistidos = (
            Aluno.objects.filter(id__in=int.values_list('aluno', flat=True))
            | Aluno.objects.filter(id__in=dis.values_list('aluno', flat=True))
            | Aluno.objects.filter(id__in=mat.values_list('aluno', flat=True))
            | Aluno.objects.filter(id__in=chp.values_list('aluno', flat=True))
            | Aluno.objects.filter(id__in=participacoes_ae.values_list('aluno', flat=True))
        )
        total_geral_alunos_assistidos = total_geral_alunos_assistidos.count()
    return locals()
