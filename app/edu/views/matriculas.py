from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from djtools.utils import (
    httprr,
    permission_required,
    rtr,
    send_mail,
)
from edu.forms import EfetuarMatriculaForm, IdentificacaoCandidatoForm
from edu.models import Aluno, CoordenadorPolo, MatrizCurso
from processo_seletivo.models import CandidatoVaga

from .pdfs import comprovante_matricula_pdf


@rtr()
@permission_required('edu.efetuar_matricula')
def identificar_candidato(request, origem=None):
    title = 'Identificação do Candidato'
    form = IdentificacaoCandidatoForm(request.GET or None, request=request)
    if form.is_valid():
        candidato_vaga = form.processar()
        return httprr(f'/edu/efetuar_matricula/{candidato_vaga.pk}/', 'Candidato identificado com sucesso. Realize sua matrícula institucional.')

    return locals()


@rtr()
@login_required()
def efetuar_matricula(request, candidato_vaga_id=None):
    title = 'Matrícula Institucional'
    candidato_vaga = None
    initial = None
    alunos = Aluno.objects.none()

    cpf = request.POST.get('cpf')
    ignorar_sgc = request.GET.get('ignorar_sgc') or request.method == 'post'
    is_usuario_coordenador_do_polo = False

    if candidato_vaga_id:
        candidato_vaga = get_object_or_404(CandidatoVaga, pk=candidato_vaga_id)
        cpf = candidato_vaga.candidato.cpf
        if candidato_vaga:
            initial = {
                'cpf': cpf,
                'nome': candidato_vaga.candidato.nome,
                'email_pessoal': candidato_vaga.candidato.email,
                'telefone_principal': candidato_vaga.candidato.telefone,
            }

        if request.user.has_group_cached('Coordenador de Polo EAD', ignore_groups_if_superuser=False):
            polos = CoordenadorPolo.objects.filter(vinculo=request.user.get_vinculo()).values_list('polo__descricao', flat=True)
            is_usuario_coordenador_do_polo = candidato_vaga.candidato.campus_polo in polos

    if not request.user.has_perm('edu.efetuar_matricula') and not is_usuario_coordenador_do_polo:
        return HttpResponseForbidden()

    if cpf:
        alunos = Aluno.objects.filter(pessoa_fisica__cpf=cpf).exclude(matriz__estrutura__proitec=True)
        if alunos.exists() and (not candidato_vaga or ignorar_sgc):
            aluno = alunos.latest('id')
            initial = {
                # dados pessoais
                'nome': aluno.pessoa_fisica.nome_registro,
                'nome_social': aluno.pessoa_fisica.nome_social,
                'sexo': aluno.pessoa_fisica.sexo,
                'data_nascimento': aluno.pessoa_fisica.nascimento_data,
                'estado_civil': aluno.pessoa_fisica.estado_civil,
                # dados familiares
                'nome_pai': aluno.nome_pai,
                'estado_civil_pai': aluno.estado_civil_pai,
                # pai_falecido = aluno.pai_falecido,
                'nome_mae': aluno.nome_mae,
                'estado_civil_mae': aluno.estado_civil_mae,
                # mae_falecida = aluno.mae_falecida,
                'responsavel': aluno.responsavel,
                'parentesco_responsavel': aluno.parentesco_responsavel,
                'cpf_responsavel': aluno.cpf_responsavel,
                # endereço
                'logradouro': aluno.logradouro,
                'numero': aluno.numero,
                'complemento': aluno.complemento,
                'bairro': aluno.bairro,
                'cep': aluno.cep,
                'cidade': aluno.cidade,
                'tipo_zona_residencial': aluno.tipo_zona_residencial,
                # informações para contado
                'telefone_principal': aluno.telefone_principal,
                'telefone_secundario': aluno.telefone_secundario,
                'telefone_adicional_1': aluno.telefone_adicional_1,
                'telefone_adicional_2': aluno.telefone_adicional_2,
                'email_pessoal': aluno.email_notificacao,
                # outras informacoes
                'tipo_sanguineo': aluno.tipo_sanguineo,
                'nacionalidade': aluno.nacionalidade,
                'pais_origem': aluno.pais_origem and aluno.pais_origem.id or None,
                'naturalidade': aluno.naturalidade and aluno.naturalidade.id or None,
                'raca': aluno.raca,
                # dados escolares
                'nivel_ensino_anterior': aluno.nivel_ensino_anterior and aluno.nivel_ensino_anterior.id or None,
                'tipo_instituicao_origem': aluno.tipo_instituicao_origem,
                'nome_instituicao_anterior': aluno.nome_instituicao_anterior,
                'ano_conclusao_estudo_anterior': aluno.ano_conclusao_estudo_anterior and aluno.ano_conclusao_estudo_anterior.id or None,
                # rg
                'numero_rg': aluno.numero_rg,
                'uf_emissao_rg': aluno.uf_emissao_rg and aluno.uf_emissao_rg.id or None,
                'orgao_emissao_rg': aluno.orgao_emissao_rg and aluno.orgao_emissao_rg.id or None,
                'data_emissao_rg': aluno.data_emissao_rg,
                # titulo_eleitor
                'numero_titulo_eleitor': aluno.numero_titulo_eleitor,
                'zona_titulo_eleitor': aluno.zona_titulo_eleitor,
                'secao': aluno.secao,
                'data_emissao_titulo_eleitor': aluno.data_emissao_titulo_eleitor,
                'uf_emissao_titulo_eleitor': aluno.uf_emissao_titulo_eleitor and aluno.uf_emissao_titulo_eleitor.id or None,
                # carteira de reservista
                'numero_carteira_reservista': aluno.numero_carteira_reservista,
                'regiao_carteira_reservista': aluno.regiao_carteira_reservista,
                'serie_carteira_reservista': aluno.serie_carteira_reservista,
                'estado_emissao_carteira_reservista': aluno.estado_emissao_carteira_reservista
                and aluno.estado_emissao_carteira_reservista.id
                or None,
                'ano_carteira_reservista': aluno.ano_carteira_reservista,
                # certidao_civil
                'tipo_certidao': aluno.tipo_certidao,
                'cartorio': aluno.cartorio,
                'numero_certidao': aluno.numero_certidao,
                'folha_certidao': aluno.folha_certidao,
                'livro_certidao': aluno.livro_certidao,
                'data_emissao_certidao': aluno.data_emissao_certidao,
                'matricula_certidao': aluno.matricula_certidao,
            }
        elif candidato_vaga and not ignorar_sgc:
            erro_acesso_sgc = False
            if candidato_vaga.candidato.edital.importacaocsv_set.exists():
                try:
                    initial = candidato_vaga.candidato.edital.importacaocsv_set.order_by('id').last().consultar_dados_candidato(candidato_vaga)
                except Exception as e:
                    erro_acesso_sgc = True
                    if not request.POST.get('nome'):
                        alerta = f'Problemas ao tentar obter dados pessoais do arquivo de importação ({e}). Nenhum dado foi importado.'
                    else:
                        alerta = None
            elif candidato_vaga.candidato.edital.webservice:
                try:
                    initial = candidato_vaga.candidato.edital.consultar_candidato(candidato_vaga)
                except Exception as e:
                    erro_acesso_sgc = True
                    if not request.POST.get('nome'):
                        alerta = f'Problemas ao tentar conectar com o Sistema de Gerenciamento de Concursos (SGC): {e}. Nenhum dado foi importado.'
                    else:
                        alerta = None
            else:
                erro_acesso_sgc = True
                alerta = (
                    'O edital não possui arquivo de dados pessoais importado nem webservice configurado. '
                    'Nenhum dado pessoal do candidato foi importado.'
                )

    alunos = alunos.filter(situacao__ativo=True)
    if initial and candidato_vaga:
        qs_matriz_curso = MatrizCurso.objects.filter(curso_campus=candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus)
        initial.update(
            ano_letivo=candidato_vaga.candidato.edital.ano.pk,
            periodo_letivo=candidato_vaga.candidato.edital.semestre,
            turno=candidato_vaga.candidato.turno and candidato_vaga.candidato.turno.pk or None,
            matriz_curso=qs_matriz_curso.count() == 1 and qs_matriz_curso[0].pk or None,
        )
    form = EfetuarMatriculaForm(request, candidato_vaga, data=request.POST or None, initial=initial, files=request.FILES or None)
    if form.is_valid():
        aluno = form.processar()
        if form.is_curso_fic():
            if candidato_vaga_id:
                candidato_vaga = get_object_or_404(CandidatoVaga, pk=candidato_vaga_id)
                candidato_vaga.registrar_matricula()
            return httprr(f'/edu/efetuar_matricula_turma/{aluno.pk}/', 'Matrícula institucional realizada com sucesso. Realize a matrícula na turma.')
        else:
            comprovante_matricula_response = comprovante_matricula_pdf(request, aluno.pk)

            email_pessoal = form.cleaned_data.get('email_pessoal')
            mensagem_envio_email = ''
            if email_pessoal:
                attachments = [('Comprovante.pdf', comprovante_matricula_response.content, 'application/pdf')]
                send_mail(
                    'Comprovante de Matrícula',
                    'Caro aluno(a), segue em anexo seu comprovante de matrícula.',
                    settings.DEFAULT_FROM_EMAIL,
                    [email_pessoal],
                    fail_silently=True,
                    attachments=attachments,
                )
                mensagem_envio_email = f'Um e-mail com o comprovante foi enviado para {email_pessoal}.'

            if candidato_vaga_id:
                candidato_vaga = get_object_or_404(CandidatoVaga, pk=candidato_vaga_id)
                candidato_vaga.registrar_matricula()
                return httprr(
                    f'/processo_seletivo/classificados/{candidato_vaga.oferta_vaga.pk}/',
                    mark_safe(
                        f'Matrícula realizada com sucesso. {mensagem_envio_email} Clique neste link para <a target="_blank" href="/edu/comprovante_matricula_pdf/{aluno.pk}/">imprimir o comprovante</a>.'
                    ),
                )
            else:
                return httprr(
                    '/edu/efetuar_matricula/',
                    mark_safe(
                        f'Matrícula realizada com sucesso. {mensagem_envio_email} Clique neste link para (<a target="_blank" href="/edu/comprovante_matricula_pdf/{aluno.pk}/">imprimir o comprovante</a>).'
                    ),
                )
    return locals()
