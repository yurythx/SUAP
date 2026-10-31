"""Cria a árvore de setores e os servidores a partir das planilhas da prefeitura.

Uso, dentro do container web::

    python manage.py importar_prefeitura unidades.csv usuarios.csv
"""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.core.management.base import CommandError
from django.db import transaction

from comum.models import Configuracao, Municipio, User
from djtools.management.commands import BaseCommandPlus
from rh.importacao_prefeitura import NOME_RAIZ, SIGLA_RAIZ, ler_unidades, ler_usuarios, ordenar_unidades, validar
from rh.models import PessoaFisica, Servidor, Setor, Situacao, UnidadeOrganizacional

GRUPO_SERVIDOR = 'Servidor'
SITUACAO_ATIVA = '01'
DESCRICOES = {
    'instituicao_sigla': 'Sigla da instituição',
    'instituicao': 'Nome da instituição',
    'reitoria_sigla': 'Sigla da unidade raiz',
    'instituicao_estado': 'UF da instituição',
    'dominios_institucionais': 'Domínios de e-mail institucional',
}


class Command(BaseCommandPlus):
    help = 'Importa organograma e servidores da prefeitura. Pode ser executado de novo sem duplicar.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('unidades', help='CSV de unidades (exemploUnidades).')
        parser.add_argument('usuarios', help='CSV de usuários (exemploUsuarios).')

    def handle(self, *args, **options) -> None:
        unidades = ler_unidades(options['unidades'])
        usuarios = ler_usuarios(options['usuarios'])
        erros = validar(unidades, usuarios)
        if erros:
            raise CommandError('\n'.join(erros))

        User.enviar_email_boas_vindas = lambda self: None
        _passaporte_como_texto()
        self._definir_identidade(unidades)
        setores = self._gravar_setores(ordenar_unidades(unidades))
        situacao = self._situacao_ativa()
        grupo_servidor, _ = Group.objects.get_or_create(name=GRUPO_SERVIDOR)
        criados, atualizados, conflitos = self._gravar_usuarios(usuarios, setores, situacao, grupo_servidor)
        self.stdout.write(f'Setores: {len(setores)}. Servidores criados: {criados}. Atualizados: {atualizados}. Conflitos: {conflitos}.')

    def _definir_identidade(self, unidades: list[dict[str, str]]) -> None:
        _configurar('instituicao_sigla', SIGLA_RAIZ)
        _configurar('instituicao', NOME_RAIZ)
        _configurar('reitoria_sigla', SIGLA_RAIZ)
        _configurar('instituicao_estado', 'MT')
        _configurar('dominios_institucionais', 'rondonopolis.mt.gov.br')
        municipio, _ = Municipio.get_or_create('Rondonópolis', 'MT')
        raiz = _obter_ou_criar_setor(SIGLA_RAIZ, NOME_RAIZ, None, '')
        telefone = next((item['telefone'] for item in unidades if item['telefone']), '')
        uo = UnidadeOrganizacional.objects.filter(setor=raiz).first()
        if uo is None:
            UnidadeOrganizacional.objects.create(nome=NOME_RAIZ, sigla=SIGLA_RAIZ, setor=raiz, municipio=municipio, telefone=telefone)
            return
        uo.nome = NOME_RAIZ
        uo.municipio = municipio
        uo.telefone = telefone or uo.telefone
        uo.save()

    def _gravar_setores(self, unidades: list[dict[str, str]]) -> dict[str, Setor]:
        raiz = Setor.objects.get(sigla=SIGLA_RAIZ, codigo__isnull=True)
        setores = {SIGLA_RAIZ: raiz}
        for item in unidades:
            superior = setores[item['superior'] or SIGLA_RAIZ]
            setores[item['sigla']] = _obter_ou_criar_setor(item['sigla'], item['nome'], superior, item['email'])
        return setores

    def _situacao_ativa(self) -> Situacao:
        situacao = Situacao.objects.filter(codigo=SITUACAO_ATIVA).first()
        if situacao is not None:
            return situacao
        return Situacao.objects.create(codigo=SITUACAO_ATIVA, nome='ATIVO PERMANENTE', nome_siape='ATIVO PERMANENTE')

    def _gravar_usuarios(self, usuarios, setores, situacao, grupo_servidor) -> tuple[int, int, int]:
        criados = atualizados = conflitos = 0
        total = len(usuarios)
        for indice, usuario in enumerate(usuarios, start=1):
            try:
                resultado = _gravar_usuario(usuario, setores[usuario['setor']], situacao, grupo_servidor)
            except Exception as exc:
                texto = str(exc).split('DETAIL:', 1)[0].strip()
                raise CommandError(f'Falha em {usuario["login"]}: {texto}') from None
            if resultado == 'criado':
                criados += 1
            elif resultado == 'atualizado':
                atualizados += 1
            else:
                conflitos += 1
                self.stdout.write(f'Conflito de CPF no login {usuario["login"]}.')
            if indice % 50 == 0:
                self.stdout.write(f'{indice}/{total}')
        return criados, atualizados, conflitos


def _passaporte_como_texto() -> None:
    """O banco desta instalação não aceita passaporte nulo; a pessoa da prefeitura não tem passaporte."""
    from rh.deduplicacao import documentos

    formatar = documentos.formatar_passaporte

    def formatar_passaporte(valor: str | None) -> str:
        texto = formatar(valor)
        return '' if not texto else texto

    documentos.formatar_passaporte = formatar_passaporte


def _configurar(chave: str, valor: str) -> None:
    conf = Configuracao.objects.filter(app='comum', chave=chave).first()
    if conf is None:
        Configuracao.objects.create(app='comum', chave=chave, valor=valor, descricao=DESCRICOES[chave])
        return
    if conf.valor != valor:
        conf.valor = valor
        conf.save(update_fields=['valor'])


def _obter_ou_criar_setor(sigla: str, nome: str, superior: Setor | None, email: str) -> Setor:
    setor = Setor.objects.filter(sigla=sigla, codigo__isnull=True).first()
    if setor is None:
        return Setor.objects.create(sigla=sigla, nome=nome, superior=superior, email=email or None)
    setor.nome = nome
    setor.superior = superior
    setor.email = email or setor.email
    setor.excluido = False
    setor.save()
    return setor


def _gravar_usuario(usuario: dict[str, str], setor: Setor, situacao: Situacao, grupo_servidor: Group) -> str:
    with transaction.atomic():
        pessoa = PessoaFisica.objects.filter(cpf=usuario['cpf']).first()
        if pessoa is None:
            pessoa = PessoaFisica(nome=usuario['nome'], cpf=usuario['cpf'])
            pessoa.save()
        elif pessoa.nome != usuario['nome']:
            pessoa.nome = usuario['nome']
            pessoa.save()
        servidor = Servidor.objects.filter(matricula=usuario['login']).first()
        if servidor is not None and servidor.pessoa_fisica_id != pessoa.id:
            return 'conflito'
        criado = servidor is None
        if criado:
            servidor = Servidor(
                matricula=usuario['login'],
                pessoa_fisica=pessoa,
                situacao=situacao,
                matricula_crh='',
                matricula_sipe='',
                email_siape='',
                email_academico='',
                email_google_classroom='',
            )
        servidor.setor = setor
        servidor.ativo = True
        servidor.eh_tecnico_administrativo = True
        servidor.eh_docente = False
        servidor.email_institucional = usuario['email']
        servidor.situacao = situacao
        servidor.save()
        grupo_perfil, _ = Group.objects.get_or_create(name=usuario['perfil'])
        servidor.get_user().groups.add(grupo_servidor, grupo_perfil)
        return 'criado' if criado else 'atualizado'
