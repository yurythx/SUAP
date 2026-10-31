import logging
import re
import secrets
import string
from datetime import datetime, timedelta
from functools import cache, partial
from typing import Any

from botocore.config import Config
from botocore.exceptions import BotoCoreError
from django.core.files.storage import Storage, storages
from storages.backends.s3 import S3Storage

from comum.models import Configuracao
from rh.models import Setor

logger = logging.getLogger('ldap_backend')


def print_(msg, test_mode=False):
    prefix = test_mode and '[TEST] ' or ''
    logger.info(prefix + msg)


def ad_to_datetime(t):
    """Converte datetime do AD para datetime python"""
    # ano base + qtd dias do ``t``
    return datetime(1601, 1, 1) + timedelta(float(t) / 864000000000)


def datetime_to_ad(t):
    """Converte datetime python para datetime AD"""
    delta = t - datetime(1601, 1, 1)
    return delta.days * 864000000000 + (delta.seconds * 10000000)


def senha_randomica(comprimento: int = 12) -> str:
    """
    Gera uma senha aleatória que atende às políticas de complexidade padrão
    do Microsoft Active Directory.

    Argumentos:
        comprimento (int): O comprimento desejado para a senha. O padrão é 12.
                           O valor mínimo recomendado é 8.

    Retorna:
        str: Uma senha aleatória e segura.
    """
    if comprimento < 8:
        raise ValueError('O comprimento da senha deve ser de no mínimo 8 caracteres para garantir a segurança.')

    # 1. Define os conjuntos de caracteres obrigatórios
    maiusculas = string.ascii_uppercase
    minusculas = string.ascii_lowercase
    numeros = string.digits
    simbolos = '!@#$%^&*()-_=+'  # Um conjunto comum de símbolos permitidos

    # 2. Garante pelo menos um caractere de cada categoria
    senha_temporaria = [secrets.choice(maiusculas), secrets.choice(minusculas), secrets.choice(numeros), secrets.choice(simbolos)]

    # 3. Cria um "caldeirão" com todos os caracteres possíveis para preencher o resto
    todos_os_caracteres = maiusculas + minusculas + numeros + simbolos

    # 4. Preenche o restante da senha com caracteres aleatórios do "caldeirão"
    for _ in range(comprimento - len(senha_temporaria)):
        senha_temporaria.append(secrets.choice(todos_os_caracteres))

    # 5. Embaralha a lista para que os caracteres obrigatórios não fiquem sempre no início
    secrets.SystemRandom().shuffle(senha_temporaria)

    # 6. Converte a lista de caracteres em uma string final
    senha_final = ''.join(senha_temporaria)

    return senha_final


def format_name(val):
    """Naming conventions in Active Directory for computers, domains, sites, and OUs:
    https://support.microsoft.com/en-us/kb/909264"""
    disallowed_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    for c in disallowed_chars:
        val = val.replace(c, '-')
    return val


def get_setor_dn(setor, domain):
    caminho = setor.get_caminho()[:-1]
    caminho.reverse()
    dn = f'OU={setor.sigla}'
    for i in caminho:
        dn += f',OU={i.sigla}'
    for i in domain.split('.'):
        dn += f',DC={i}'
    return format_name(dn).replace(' ', '')


TIMEOUT_FOTO_SEGUNDOS = 5


@cache
def _storage_da_foto() -> Storage:
    """O storage padrão; quando é S3, uma cópia com timeout curto e sem novas tentativas.

    A foto é lida dentro do login (``authenticate`` → ``sync_user``), e o S3 do SUAP usa timeout de 600 s: uma lentidão
    nele segurava o request até o gunicorn abortar o worker (#17597).
    """
    storage = storages['default']
    if not isinstance(storage, S3Storage):
        return storage
    storage_da_foto = type(storage)(**storages.backends['default'].get('OPTIONS', {}))
    storage_da_foto.client_config = storage.client_config.merge(
        Config(connect_timeout=TIMEOUT_FOTO_SEGUNDOS, read_timeout=TIMEOUT_FOTO_SEGUNDOS, retries={'total_max_attempts': 1})
    )
    return storage_da_foto


def get_thumbnail_content(servidor: Any) -> bytes | None:
    """Foto 75x100 do servidor para o ``thumbnailPhoto`` do AD.

    Devolve ``None`` sem foto ou se o storage falhar/demorar: o ``sync_user`` segue sem mexer na foto que já está no AD,
    e a sincronia agendada (``sync_ldap_parcial``/``sync_ldap_full``) tenta de novo.
    """
    if not servidor.foto:
        return None
    fname = servidor.foto.name.replace('fotos/', 'fotos/75x100/')
    try:
        with _storage_da_foto().open(fname) as f:
            return f.read()
    except (OSError, BotoCoreError) as e:
        logger.warning('Foto %s indisponível no storage para o thumbnailPhoto: %r', fname, e)
        return None


def get_obj_attrs(model_obj: Any, ldap_conf: Any, com_foto: bool = True) -> dict[str, Any]:
    """
    Retorna os atributos do ``model_obj`` que são importantes para a sincronia com
    o LDAP. O ``model_obj`` deve ser `rh.Servidor` ou `edu.Aluno`.

    ``com_foto=False`` não lê a foto do servidor (ver ``get_servidor_attrs``).
    """
    func_by_model_name = {
        'aluno': get_aluno_attrs,
        'servidor': partial(get_servidor_attrs, com_foto=com_foto),
        'prestadorservico': get_prestadorservico_attrs,
    }
    model_name = model_obj.__class__.__name__.lower()
    obj_attrs = func_by_model_name[model_name](model_obj, ldap_conf)
    if not obj_attrs:
        return obj_attrs
    if ldap_conf.use_extension_attributes:
        obj_attrs['extensionAttribute6'], obj_attrs['extensionAttribute7'] = get_cafe_attrs(model_obj.pessoa_fisica)
        obj_attrs['extensionAttribute8'] = model_obj.email_pessoal or None
        # `extensionAttribute9` é utilizado para o Campus ZL/EAD na integração com o Moodle.
        # Se for aluno ou prestador, será o email pessoal/secundário; se for servidor será o institucional.
        if model_name == 'servidor':
            obj_attrs['extensionAttribute9'] = model_obj.email_institucional or None
        else:
            obj_attrs['extensionAttribute9'] = obj_attrs['extensionAttribute8']

    return obj_attrs


def get_senha_inicial(obj: Any) -> str:
    """
    Retorna a senha inicial no formato:

        @INSTITUICAO_SIGLA + data de nascimento (ddmmaaaa)

    caso haja sigla configurada e o objeto tenha data de nascimento. Caso contrário retorna uma string randômica.
    """
    sigla = Configuracao.get_valor_por_chave_str('comum', 'instituicao_sigla')
    utilizar_senha_randomica = Configuracao.get_valor_por_chave('ldap_backend', 'utilizar_senha_randomica')
    if utilizar_senha_randomica or not sigla:
        return senha_randomica(12)
    try:
        if hasattr(obj, 'nascimento_data'):
            senha = f'@{sigla.upper()}{obj.nascimento_data.strftime("%d%m%Y")}'
        else:
            senha = f'@{sigla.upper()}{obj.pessoa_fisica.nascimento_data.strftime("%d%m%Y")}'
    except Exception:
        senha = senha_randomica(12)
    return senha


def get_tipos_email_disponiveis(user):
    instance = user.get_relacionamento()

    dominio_institucional = Configuracao.get_valor_por_chave('ldap_backend', 'dominio_institucional')
    dominio_academico = Configuracao.get_valor_por_chave('ldap_backend', 'dominio_academico')
    dominio_google_classroom = Configuracao.get_valor_por_chave('ldap_backend', 'dominio_google_classroom')

    tipos = {}

    # Servidor
    if user.eh_servidor and instance.ativo:
        if dominio_institucional and not instance.email_institucional:
            tipos['institucional'] = 'Institucional'
        if not instance.eh_estagiario and dominio_google_classroom and not instance.email_google_classroom:
            tipos['google_classroom'] = 'Google Sala de Aula'
        if dominio_academico and not instance.email_academico and not instance.eh_aposentado:
            tipos['academico'] = 'Acadêmico'

    # Grupo Professor e Prestador de Serviço
    elif user.eh_prestador:
        if user.has_perm('edu.eh_professor') and dominio_google_classroom and not instance.email_google_classroom:
            tipos['google_classroom'] = 'Google Sala de Aula'

        elif dominio_academico and not instance.email_academico and instance.tem_ocupacao_ativa():
            tipos['academico'] = 'Acadêmico'
    # Aluno
    elif (
        user.eh_aluno
        and instance.situacao.ativo
        and not instance.eh_aluno_minicurso()
        and not instance.is_fic()
        and not instance.is_proitec()
        and not instance.is_pronatec()
        and not instance.is_sica()
    ):
        if dominio_academico and not instance.email_academico:
            tipos['academico'] = 'Acadêmico'
        if dominio_google_classroom and not instance.email_google_classroom:
            tipos['google_classroom'] = 'Google Sala de Aula'

    return tipos


############
# Servidor #
############


def get_funcionario_dn(funcionario, ldap_conf):
    """
    Retorna o DN para o ``funcionario`` com base no seu setor (Pode ser servidor
    e prestador).
    """
    if not funcionario.matricula:
        return None
    setor = funcionario.setor
    reitoria = Setor.raiz_suap()
    if not setor:
        setor = reitoria
        if hasattr(funcionario, 'usuario_externo'):
            return f'CN={funcionario.matricula.strip()},OU=Usuários Externos,{get_setor_dn(setor, ldap_conf.domain)}'
        else:
            return f'CN={funcionario.matricula.strip()},OU=Servidores Sem Setor,{get_setor_dn(setor, ldap_conf.domain)}'
    elif funcionario.eh_servidor:
        if getattr(funcionario, 'eh_aposentado', False):
            return f'CN={funcionario.matricula.strip()},OU=Servidores Aposentados,{get_setor_dn(reitoria, ldap_conf.domain)}'
        if not getattr(funcionario, 'ativo', True):
            return f'CN={funcionario.matricula.strip()},OU=Servidores Inativos,{get_setor_dn(reitoria, ldap_conf.domain)}'
    return f'CN={funcionario.matricula.strip()},{get_setor_dn(setor, ldap_conf.domain)}'


def get_servidor_grupos(servidor, ldap_conf):
    grupos = []
    grupo_servidores = Configuracao.get_valor_por_chave('ldap_backend', 'grupo_servidores')
    grupo_estagiarios = Configuracao.get_valor_por_chave('ldap_backend', 'grupo_estagiarios')
    grupo_google_classroom = Configuracao.get_valor_por_chave('ldap_backend', 'grupo_google_classroom')
    if not servidor.eh_estagiario and grupo_servidores:
        grupos.append(grupo_servidores)
    elif Configuracao.get_valor_por_chave('ldap_backend', 'permite_ldap_group_estagiario') and grupo_estagiarios:
        grupos.append(grupo_estagiarios)
    if servidor.email_google_classroom and Configuracao.get_valor_por_chave('ldap_backend', 'dominio_google_classroom') and grupo_google_classroom:
        grupos.append(grupo_google_classroom)
    return grupos


def get_prestadorservico_grupos():
    grupos = []
    grupo_prestadores = Configuracao.get_valor_por_chave('ldap_backend', 'grupo_prestadores')
    if Configuracao.get_valor_por_chave('ldap_backend', 'permite_ldap_group_prestador') and grupo_prestadores:
        grupos.append(grupo_prestadores)
    return grupos


def get_cafe_attrs(pessoa_fisica):
    cpf = pessoa_fisica.cpf and re.sub(r'\D', '', pessoa_fisica.cpf) or None
    try:
        data_nascimento = pessoa_fisica.nascimento_data.strftime('%Y%m%d')
    except AttributeError, ValueError:
        data_nascimento = None
    return cpf, data_nascimento


def get_servidor_attrs(servidor: Any, ldap_conf: Any, com_foto: bool = True) -> dict[str, Any]:
    """
    Retorna os atributos para sincronização do usuário no LDAP.

    Com ``com_foto=False`` a foto não é lida do storage e o ``thumbnailPhoto`` fica ``None`` (o AD mantém a que tem).
    """
    dn = get_funcionario_dn(servidor, ldap_conf)
    if not dn:
        return {}

    # department: sigla do setor de exercício
    department = servidor.setor.sigla if servidor.setor else None
    attrs = {
        'dn': dn,
        'userPrincipalName': f'{servidor.matricula}@{ldap_conf.domain}',
        'active': servidor.acesso_ldap_liberado(),
        'objectClass': ['top', 'person', 'organizationalPerson', 'user'],
        'cn': servidor.matricula,
        'givenName': servidor.pessoa_fisica.nome.split()[0],
        'sn': ' '.join(servidor.pessoa_fisica.nome.split()[1:])[:64] or None,
        'DisplayName': servidor.pessoa_fisica.nome,
        'memberOf': get_servidor_grupos(servidor, ldap_conf),
        'userAccountControl': servidor.acesso_ldap_liberado() and '512' or '514',
        'accountExpires': '0',  # Nunca expira
        'department': department,
        'description': servidor.pessoa_fisica.nome,
        'title': servidor.cargo_emprego and servidor.cargo_emprego.nome or None,
        'thumbnailPhoto': get_thumbnail_content(servidor) if com_foto else None,
        'mail': servidor.email_institucional or None,
        'setor': servidor.setor or None,
    }
    if ldap_conf.use_extension_attributes:
        attrs = {**attrs, **_extension_attrs_servidor(servidor)}
    # Filtro de autenticação
    for filtro in ldap_conf.filterstr:
        attrs[filtro] = servidor.matricula
    return _sem_espacos(attrs)


def _sigla_campus(uo: Any) -> str:
    return uo.equivalente.sigla if uo.equivalente else uo.sigla


def _campus_lotacao_e_exercicio(servidor: Any) -> str | None:
    """``extensionAttribute11``: câmpus de lotação e de exercício, ``<lotação>_<exercício>``, ou só o que houver."""
    lotacao = None
    if servidor.setor_lotacao and servidor.setor_lotacao.uo:
        lotacao = f'{_sigla_campus(servidor.setor_lotacao.uo)}'
    if servidor.setor and servidor.setor.uo:
        exercicio = servidor.setor.uo.sigla
    elif servidor.setor_exercicio and servidor.setor_exercicio.uo:
        exercicio = _sigla_campus(servidor.setor_exercicio.uo)
    else:
        return lotacao
    return f'{lotacao}_{exercicio}' if lotacao else exercicio


def _extension_attrs_servidor(servidor: Any) -> dict[str, Any]:
    return {
        'extensionAttribute1': servidor.setor.uo.setor.sigla if servidor.setor and servidor.setor.uo else None,  # campus
        'extensionAttribute2': servidor.categoria_display or None,  # docente, tec-adm, estagiario
        'extensionAttribute3': None if servidor.eh_estagiario else servidor.funcao_display or None,
        'extensionAttribute4': servidor.email_academico or None,
        'extensionAttribute5': servidor.email_google_classroom or None,
        'extensionAttribute10': servidor.ativo and 'Ativo' or 'Inativo',
        'extensionAttribute11': _campus_lotacao_e_exercicio(servidor),
        'extensionAttribute12': servidor.situacao.nome if servidor.situacao else None,
    }


def _sem_espacos(attrs: dict[str, Any]) -> dict[str, Any]:
    """Tira os espaços das pontas dos valores texto (e das listas de texto); o ``thumbnailPhoto`` (binário) fica como está."""
    for key, value in list(attrs.items()):
        if key == 'thumbnailPhoto':
            continue
        if isinstance(value, str):
            value = value.strip()
        elif isinstance(value, list):
            value = [i.strip() for i in value]
        attrs[key] = value
    return attrs


#########
# Aluno #
#########


def get_aluno_dn(aluno, ldap_conf):
    """
    Retorna o DN para o ``aluno``.
    """
    try:
        setor = aluno.campus.setor
        username = aluno.username.strip()
    except AttributeError:
        return None
    return f'CN={username},OU=Alunos,{get_setor_dn(setor, ldap_conf.domain)}'


def get_aluno_grupos(aluno, ldap_conf):
    dn = get_aluno_dn(aluno, ldap_conf)
    dn_sem_cn = ','.join(dn.split(',')[1:])
    campus_identificacao = aluno.campus.setor.sigla.split('/')[-1]
    grupo_dn = f'CN=G_{campus_identificacao}_ALUNOS,{dn_sem_cn}'
    return [grupo_dn]


def get_aluno_attrs(aluno, ldap_conf):
    """
    Retorna os atributos para sincronização do usuário no LDAP.
    """
    dn = get_aluno_dn(aluno, ldap_conf)
    if not dn:
        return {}

    if aluno.email_academico:
        userPrincipalName = aluno.email_academico
    else:
        userPrincipalName = f'{aluno.username}@{ldap_conf.domain}'
    from edu.models.cadastros_gerais import SituacaoMatricula

    aluno_ativo = aluno.situacao_id not in SituacaoMatricula.SITUACOES_SEM_VINCULO_INSTITUCIONAL
    attrs = {
        'dn': dn,
        'userPrincipalName': userPrincipalName,
        # sAMAccountName       = aluno.username,
        'active': aluno_ativo,
        'objectClass': ['top', 'person', 'organizationalPerson', 'user'],
        'memberOf': get_aluno_grupos(aluno, ldap_conf),
        'cn': aluno.username,
        'givenName': aluno.pessoa_fisica.nome.split()[0],
        'sn': ' '.join(aluno.pessoa_fisica.nome.split()[1:])[:64] or None,
        'DisplayName': aluno.pessoa_fisica.nome,
        'userAccountControl': aluno_ativo and '512' or '514',  # 512 ativo, 514 inativo
        'accountExpires': '0',  # Nunca expira
        'description': aluno.pessoa_fisica.nome,
        'thumbnailPhoto': None,
        'mail': aluno.email_academico or None,
        'setor': aluno.campus and aluno.campus.setor or None,
    }
    if ldap_conf.use_extension_attributes:
        extension_attrs = {
            'extensionAttribute1': None,
            'extensionAttribute2': 'Aluno',
            'extensionAttribute3': None,
            'extensionAttribute4': aluno.email_academico or None,
            'extensionAttribute5': aluno.email_google_classroom or None,
            'extensionAttribute10': aluno.situacao.ativo and 'Ativo' or 'Inativo',
            'extensionAttribute12': aluno.situacao.descricao if aluno.situacao else None,
        }
        attrs = {**attrs, **extension_attrs}
    # Filtro de autenticação
    for filtro in ldap_conf.filterstr:
        attrs[filtro] = aluno.matricula
    for key, value in list(attrs.items()):
        if key == 'thumbnailPhoto':
            continue
        if isinstance(value, str):
            value = value.strip()
        elif isinstance(value, list):
            value = [i.strip() for i in value]
        attrs[key] = value

    return attrs


####################
# PrestadorServico #
####################


def get_prestadorservico_attrs(prestador, ldap_conf):
    """
    Retorna os atributos para sincronização do usuário no LDAP.
    """
    dn = get_funcionario_dn(prestador, ldap_conf)
    if not dn:
        return {}

    department = None
    extensionAttribute1 = None

    if prestador.setor:
        department = prestador.setor.sigla
        if prestador.setor.uo:
            extensionAttribute1 = prestador.setor.uo.setor.sigla
    vinculo = prestador.get_vinculo()
    extenssionAttribute2 = 'Prestador'
    if vinculo and hasattr(vinculo, 'professor_set') and vinculo.professor_set.exists():
        extenssionAttribute2 = 'Prestador-Docente'

    ativo_ad = prestador.tem_ocupacao_ativa() and prestador.ativo

    attrs = {
        'dn': dn,
        'userPrincipalName': f'{prestador.matricula}@{ldap_conf.domain}',
        # sAMAccountName       = prestador.matricula,
        'active': ativo_ad,
        'objectClass': ['top', 'person', 'organizationalPerson', 'user'],
        'cn': prestador.matricula,
        'givenName': prestador.pessoa_fisica.nome.split()[0],
        'sn': ' '.join(prestador.pessoa_fisica.nome.split()[1:])[:64] or None,
        'DisplayName': prestador.pessoa_fisica.nome,
        'memberOf': get_prestadorservico_grupos(),
        'userAccountControl': ativo_ad and '512' or '514',  # 512 ativo, 514 inativo
        'accountExpires': '0',  # Nunca expira
        'department': department,
        'description': prestador.pessoa_fisica.nome,
        'title': 'Prestador',
        'thumbnailPhoto': None,
        'setor': prestador.setor or None,
    }
    if ldap_conf.use_extension_attributes:
        extension_attrs = {
            'extensionAttribute1': extensionAttribute1,  # campus
            'extensionAttribute2': extenssionAttribute2,
            'extensionAttribute3': None,
            'extensionAttribute4': prestador.email_academico or None,
            'extensionAttribute5': prestador.email_google_classroom or None,
            'extensionAttribute10': prestador.ativo and 'Ativo' or 'Inativo',
            'extensionAttribute12': prestador.tem_ocupacao_ativa() and 'Tem ocupação ativa' or 'Sem ocupação ativa',
        }
        attrs = {**attrs, **extension_attrs}
    # Filtro de autenticação
    for filtro in ldap_conf.filterstr:
        attrs[filtro] = prestador.matricula

    for key, value in list(attrs.items()):
        if isinstance(value, str):
            value = value.strip()
        elif isinstance(value, list):
            value = [i.strip() for i in value]
        attrs[key] = value

    return attrs


def extract_cn_from_ldap_user(member):
    import ldap

    exploded_dn = ldap.dn.explode_dn(member, flags=ldap.DN_FORMAT_LDAPV2)
    # member_dn = {parts[0]: parts[1] for item in exploded_dn if (parts := item.split('='))}
    member_dn = {}
    for item in exploded_dn:
        parts = item.split('=')
        if parts:
            member_dn[parts[0]] = parts[1]
    return member_dn['CN']
