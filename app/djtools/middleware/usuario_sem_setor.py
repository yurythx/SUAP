import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin
from sentry_sdk import capture_exception

from comum.models import Configuracao
from comum.utils import get_setor
from djtools.utils import get_ldap_conf, get_module_from_url, get_view_name_from_url, ignore_request_for_tests, send_mail


def verifica_usuario_sem_setor(request):
    usuario = request.user
    chave = f'usuario_tem_setor_middleware_{usuario.username}'
    if usuario.is_anonymous:
        return
    if not cache.get(chave, False, local_ttl=30):
        setor = get_setor(usuario)
        try:
            if usuario.eh_servidor and not (setor and setor.uo):
                usuario.reset_vinculo()
                usuario.reset_profile()
                cache.set(chave, False)
                logout(request)

                msg_erro = 'Você foi deslogado do sistema porque está sem setor SUAP'
                if setor and not setor.uo:
                    msg_erro = f'Você foi deslogado do sistema porque seu setor SUAP ({setor}) está sem campus definido'

                messages.error(
                    request,
                    f"""
                        {msg_erro}. Favor entrar em contato com a
                        Gestão de Pessoas do seu campus para regularizar sua situação.
                        """,
                )
                return HttpResponseRedirect('/')
            if usuario.eh_prestador and not (setor and setor.uo):
                requested_view = get_view_name_from_url(request.build_absolute_uri())
                requested_module = get_module_from_url(request.build_absolute_uri())
                permitted_views = [
                    'admin.edu.edu_ataeletronica_changelist',
                    'admin.edu.ataeletronica',
                    'edu.views.projeto_final.visualizar_ata_eletronica',
                    'edu.views.diplomas.assinar_ata_eletronica',
                    'edu.views.professores.professor',
                    'edu.views.professores.declaracaodocencia_pdf',
                    'edu.views.estagio_docente.emitir_declaracao_de_orientacao_pdf',
                    'edu.views.projeto_final.emitir_declaracao_de_orientacao_tcc_pdf',
                    'edu.views.projeto_final.declaracao_participacao_projeto_final_pdf',
                    'edu.views.internacionalizacao.inscricao_internacional',
                    'edu.views.internacionalizacao.inscricao_aluno_estrangeiro',
                    'edu.views.internacionalizacao.enviar_correcao_inscricao_aluno_estrangeiro',
                ]
                permitted_modules = [
                    None,
                    'comum',
                    'rh',
                    'demandas',
                    'django',
                    'djtools',
                    'documento_eletronico',
                    'processo_eletronico',
                    'erros',
                    'estagios',
                    'centralservicos',
                    'plan_estrategico',
                    'pesquisa',
                    'projetos',
                    'professor_titular',
                    'rsc',
                    'projetos_ensino',
                    'progressoes',
                ]
                cache.set(chave, False)
                if not (requested_view in permitted_views or requested_module in permitted_modules):
                    messages.error(
                        request,
                        """
                            Você não pode realizar esta ação pois não possui uma Ocupação ativa na instituição.
                            Por favor, entrar em contato com o setor responsável pelo seu cadastro.
                            """,
                    )
                    return HttpResponseRedirect('/')
            if (usuario.eh_servidor or usuario.eh_prestador or usuario.eh_aluno) and not usuario.get_profile():
                usuario.reset_vinculo()
                usuario.reset_profile()
                cache.set(chave, False)
                logout(request)
                titulo = f'Usuário {usuario.username} está sem pessoa física associada.'
                msg_notificacao = (
                    'Infelizmente, nenhuma matrícula está associada a este username, talvez seja necessário criar uma nova pessoa física.'
                )
                alerta = """
                Você foi deslogado do sistema porque está sem uma pessoa física associada. A equipe de TI já foi notificada,
                mas você pode entrar em contato com a equipe de TI da reitoria da instituição para regularizar sua situação.
                """
                capture_exception(Exception(f'{titulo} {msg_notificacao}'))
                send_mail(titulo, f'{titulo} {msg_notificacao}', settings.DEFAULT_FROM_EMAIL, settings.ADMINS)
                messages.error(
                    request,
                    alerta,
                )
                return HttpResponseRedirect('/')
        except Exception as e:
            if settings.DEBUG:
                raise e
            cache.set(chave, False)
            messages.error(request, 'Você foi deslogado pois sua sessão expirou. Efetue o login novamente.')
            return HttpResponseRedirect('/')
        if not usuario.is_superuser:
            message = None

            if not usuario.get_vinculo() and not request.session.get('autenticou_com_govbr'):
                message = """
                    Você foi deslogado pois não existe um vínculo associado a este usuário. Favor entrar em contato com a
                    Coordenação de TI do seu campus para regularizar sua situação.
                """
            if not usuario.get_profile() and not request.session.get('autenticou_com_govbr'):
                message = """
                    Você foi deslogado pois não existe uma pessoa física associada a este usuário. Favor entrar em contato com a
                    Coordenação de TI do seu campus para regularizar sua situação.
                """
            if message:
                cache.set(chave, False)
                messages.error(request, message)
                logout(request)
                return HttpResponseRedirect('/')

    if cache.get(chave, local_ttl=30) is None:
        cache.set(chave, True)


def verifica_usuario_expirado_ad(request):
    usuario = request.user
    if usuario.is_anonymous:
        return

    utiliza_autenticacao_gov_br = Configuracao.get_valor_por_chave('comum', 'habilitar_autenticacao_govbr')
    autenticou_gov_br = utiliza_autenticacao_gov_br and request.session.get('autenticou_com_govbr', False)
    if autenticou_gov_br:
        return

    ldap_conf = get_ldap_conf()
    if ldap_conf:
        # Na tela inicial caso tenha ldap_backend verifica se expirou o account e se sim força o sync_suap
        if request.path == '/':
            accountExpires = request.session.get('adAccountExpires', False)
            if accountExpires:
                accountExpires = datetime.datetime.fromisoformat(accountExpires)
                data_hora_expira = None
                hoje = datetime.datetime.today()
                data_hora_expira = accountExpires
                if data_hora_expira < hoje:
                    ldap_conf.sync_user(usuario.username)
                    messages.error(request, 'Seu usuário foi inativado no sistema no dia. Você ainda pode acessar o SUAP via GovBr.')
                    logout(request)
                    return HttpResponseRedirect('/')
    return


class UsuarioSemSetorMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if ignore_request_for_tests(request):
            return None
        response = verifica_usuario_sem_setor(request)
        if response:
            return response
        response = verifica_usuario_expirado_ad(request)
        if response:
            return response
