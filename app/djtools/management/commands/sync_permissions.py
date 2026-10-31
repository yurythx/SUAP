import time
from collections import defaultdict
from os.path import isfile

import yaml
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import AppRegistryNotReady
from django.core.management.base import CommandError
from django.db import transaction
from django.utils.text import slugify

from comum.models import GerenciamentoGrupo, GroupDetail
from djtools.management.commands import BaseCommandPlus


class PermissionLoader:
    """
    Responsável por carregar, validar e consolidar as definições de permissões
    a partir dos arquivos YAML, mantendo-se agnóstico ao banco de dados.
    """

    def __init__(self, app_names: list):
        # Estrutura: { 'group_name': {'permissions': set(), 'description': '', ...} }
        self.consolidated_groups = {}
        self.warnings = []
        self.errors = []
        self.model_permissions = self.get_model_permissions()
        self.load_all_yamls(app_names)
        self.check_for_nonexistent_permissions()

    def load_all_yamls(self, app_names: list):
        """Carrega todos os arquivos YAML de permissões das apps especificadas."""
        for app_name in app_names:
            try:
                app_config = apps.get_app_config(app_name)
                permission_file = f'{app_config.path}/permissions.yaml'
                if settings.LPS:
                    permission_file_lps = f'{app_config.path}/lps/{settings.LPS}/permissions.yaml'
                    if isfile(permission_file_lps):
                        permission_file = permission_file_lps
                self.load_and_process_yaml(permission_file, app_name)
            except LookupError, AppRegistryNotReady:
                self.errors.append(f"App '{app_name}' não encontrada ou não está pronta.")
                continue

    def load_and_process_yaml(self, file_path: str, current_app: str) -> None:
        """Carrega um único arquivo YAML e o processa."""
        try:
            with open(file_path) as f:
                data = yaml.safe_load(f)
                if not data:
                    return
        except FileNotFoundError:
            return  # Arquivo não existe, apenas ignorar.
        except yaml.YAMLError as e:
            self.errors.append(f"Erro de sintaxe no arquivo YAML '{file_path}': {e}")
            return

        for group_name, details in data.items():
            # Extrai metadados do grupo
            app_manager = details.pop('app_manager', current_app)
            group_data = self.consolidated_groups.setdefault(
                group_name,
                {
                    'permissions': set(),
                    'description': details.pop('description', ''),
                    'can_manager': details.pop('can_manager', True),
                    'app_manager': app_manager,
                    'defined_in_app': current_app,
                },
            )
            self.check_app_manager(group_name, group_data, app_manager, file_path)

            # Processa as permissões
            for app_label, models in details.items():
                for model_name, perms in models.items():
                    for perm_name in perms:
                        full_perm_str = f'{app_label}.{model_name}.{perm_name}'
                        if full_perm_str in group_data['permissions']:
                            self.warnings.append(
                                f"Permissão duplicada '{full_perm_str}' encontrada para o grupo '{group_name}' no arquivo '{file_path}'."
                            )
                        group_data['permissions'].add(full_perm_str)

    def check_app_manager(self, group_name: str, group_data: dict, app_manager: str, file_path: str) -> None:
        """Avisa quando o mesmo grupo é declarado com gerenciadores diferentes em mais de um YAML.

        O ``app_manager`` consolidado é o da primeira app carregada, mas
        ``GroupPermission.obter_grupos_por_app_yaml`` lê cada arquivo isoladamente: se os arquivos
        divergem, os dois caminhos discordam sobre quem gerencia o grupo (#17403).
        """
        if group_data['app_manager'] != app_manager:
            self.warnings.append(
                f"Grupo '{group_name}' tem app_manager '{app_manager}' no arquivo '{file_path}', mas "
                f"'{group_data['app_manager']}' na app '{group_data['defined_in_app']}'. Declare o mesmo app_manager em todos os arquivos."
            )

    def get_all_permission_strings(self) -> set:
        """Retorna um set com todas as strings de permissão de todos os grupos."""
        all_perms = set()
        for data in self.consolidated_groups.values():
            all_perms.update(data['permissions'])
        return all_perms

    def get_model_permissions(self):
        """
        Obtém todas as permissões definidas nos modelos do Django.
        """
        model_perms = set()
        for app_config in apps.get_app_configs():
            try:
                for model in app_config.get_models():
                    model_name = model._meta.model_name
                    app_label = model._meta.app_label

                    # Permissões padrão (add, change, delete, view)
                    for perm_type in model._meta.default_permissions:
                        codename = f'{perm_type}_{model_name}'
                        model_perms.add(f'{app_label}.{model_name}.{codename}')

                    # Permissões customizadas
                    for codename, _ in model._meta.permissions:
                        model_perms.add(f'{app_label}.{model_name}.{codename}')
            except AppRegistryNotReady:
                continue
        return model_perms

    def check_for_nonexistent_permissions(self):
        """
        Verifica se todas as permissões definidas nos grupos existem nos modelos do Django.
        """
        defined_perms = self.get_all_permission_strings()
        nonexistent_perms = defined_perms - self.model_permissions

        if nonexistent_perms:
            self.errors.append(f'As seguintes permissões não existem nos modelos: {", ".join(sorted(nonexistent_perms))}')
            return False
        return True


# --- Módulo de Sincronização com o Banco de Dados ---


class PermissionSyncer:
    """
    Coordena a interação com o banco de dados para sincronizar os grupos e permissões.
    """

    def __init__(self, consolidated_data: dict, stdout, stderr, style, show_tqdm=False):
        self.data = consolidated_data
        self.stdout = stdout
        self.stderr = stderr
        self.style = style
        self.show_tqdm = show_tqdm
        self.permission_cache = {}
        self.user_ct = ContentType.objects.get_for_model(get_user_model())

    def _get_iterator(self, iterable, description):
        if self.show_tqdm:
            try:
                import tqdm

                return tqdm.tqdm(iterable, desc=description)
            except ImportError:
                self.stderr.write(f'{description}...')
                return iterable
        return iterable

    def prefetch_permissions(self, perm_strings: set[str]) -> None:
        """
        Carrega as permissões pedidas pelos YAMLs num cache indexado por ``app.model.codename``.

        Lê a tabela inteira (~9 mil linhas) e filtra em Python. Um ``OR`` com uma cláusula por
        permissão fazia o Postgres gastar ~4,4 GB e ~1 min só nessa query, o que derrubava os
        runners de CI por falta de memória.
        """
        if not perm_strings:
            return

        for p_str in perm_strings:
            if p_str.count('.') != 2:
                raise CommandError(f'Formato de permissão inválido: "{p_str}"')

        self.permission_cache = {
            chave: p
            for p in Permission.objects.select_related('content_type')
            if (chave := f'{p.content_type.app_label}.{p.content_type.model}.{p.codename}') in perm_strings
        }

    def clear_group_permissions(self, group_names: list):
        """
        OTIMIZAÇÃO: Limpa as permissões de múltiplos grupos com uma única query DELETE.
        """
        if not group_names:
            return

        self.stdout.write('Limpando permissões dos grupos especificados...')
        # A tabela 'through' armazena as relações ManyToMany
        Group.permissions.through.objects.filter(group__name__in=group_names).delete()

    @transaction.atomic
    def sync(self):
        """
        Processo principal de sincronização. Envolvido em uma transação para garantir atomicidade.
        """
        group_names = list(self.data.keys())
        if not group_names:
            self.stderr.write('Nenhum grupo para sincronizar.')
            return

        self.clear_group_permissions(group_names)

        # OTIMIZAÇÃO: Pré-busca de todas as permissões e grupos existentes
        all_perms_needed = {p for g_data in self.data.values() for p in g_data['permissions']}
        self.prefetch_permissions(all_perms_needed)

        existing_groups = {g.name: g for g in Group.objects.filter(name__in=group_names)}

        # OTIMIZAÇÃO: Criação em lote (bulk) de grupos que não existem
        new_groups_to_create = []
        for name in group_names:
            if name not in existing_groups:
                new_groups_to_create.append(Group(name=name))

        if new_groups_to_create:
            self.stdout.write(f'Criando {len(new_groups_to_create)} novos grupos...')
            created_groups = Group.objects.bulk_create(new_groups_to_create)
            for group in created_groups:
                existing_groups[group.name] = group

        # --- Sincronização das Permissões ---
        group_to_perms_map = defaultdict(list)
        group_details_to_update = []

        iterator = self._get_iterator(self.data.items(), 'Processando grupos')
        for group_name, details in iterator:
            group = existing_groups[group_name]

            # 1. Coleta permissões do YAML
            for p_str in details['permissions']:
                perm_obj = self.permission_cache.get(p_str)
                if perm_obj:
                    group_to_perms_map[group.id].append(perm_obj.id)
                else:
                    # Permissão não encontrada no cache (pode ser um erro de digitação no YAML)
                    self.stderr.write(f"[Aviso] Permissão '{p_str}' para o grupo '{group_name}' não encontrada no banco. Será ignorada.")

            # 2. Coleta permissão customizada 'is_<group_name>'
            if not group_name.endswith('_administrador'):
                codename = f'is_{slugify(group_name).replace("-", "_")}'
                perm, _ = Permission.objects.get_or_create(
                    codename=codename, content_type=self.user_ct, defaults={'name': f'É membro do grupo {group_name}'}
                )
                group_to_perms_map[group.id].append(perm.id)

            # 3. Prepara dados para GroupDetail
            group_details_to_update.append(
                GroupDetail(group=group, app=details['defined_in_app'], descricao=details['description'], app_manager=details['app_manager'])
            )

        # OTIMIZAÇÃO: Adiciona as permissões em lote
        self.stdout.write('Sincronizando permissões nos grupos...')
        GroupPermissionThrough = Group.permissions.through
        relations_to_create = []
        for group_id, perm_ids in group_to_perms_map.items():
            for perm_id in set(perm_ids):  # Garante unicidade
                relations_to_create.append(GroupPermissionThrough(group_id=group_id, permission_id=perm_id))

        GroupPermissionThrough.objects.bulk_create(relations_to_create, ignore_conflicts=True)

        # OTIMIZAÇÃO: Atualiza/Cria GroupDetail em lote
        self.stdout.write('Sincronizando detalhes dos grupos (GroupDetail)...')
        GroupDetail.objects.bulk_create(
            group_details_to_update, update_conflicts=True, unique_fields=['group', 'app'], update_fields=['descricao', 'app_manager']
        )

    @transaction.atomic
    def sync_manager_groups(self):
        """Sincroniza os grupos de gerenciamento."""
        apps_com_grupos = defaultdict(list)
        for group_name, details in self.data.items():
            apps_com_grupos[details['app_manager']].append(group_name)

        iterator = self._get_iterator(apps_com_grupos.items(), 'Processando grupos gerenciadores')
        for app_name, group_names_in_app in iterator:
            # Garante a existência dos grupos gerenciador e configurador
            grupo_gerenciador, _ = Group.objects.get_or_create(name=GerenciamentoGrupo.NOME_GRUPO_GERENCIADOR_FORMAT.format(app_name))
            Group.objects.get_or_create(name=GerenciamentoGrupo.NOME_GRUPO_CONFIGURADOR_FORMAT.format(app_name))

            # Obtém o objeto GerenciamentoGrupo
            gerenciamento, _ = GerenciamentoGrupo.objects.get_or_create(grupo_gerenciador=grupo_gerenciador)

            # OTIMIZAÇÃO: Busca todos os grupos a serem gerenciados de uma vez
            grupos_gerenciaveis = list(Group.objects.filter(name__in=group_names_in_app))

            # Adiciona o próprio grupo gerenciador à lista
            grupos_gerenciaveis.append(grupo_gerenciador)

            # OTIMIZAÇÃO: Usa .set() para definir todas as relações de uma vez
            gerenciamento.grupos_gerenciados.set(grupos_gerenciaveis)

    @transaction.atomic
    def clean_orphan_permissions(self, loader: PermissionLoader, force_delete_used: bool = False) -> None:
        """
        Verifica permissões que existem no DB mas não nos modelos e remove as que não estão em uso.
        """
        self.stdout.write('\nIniciando verificação de permissões órfãs')
        if force_delete_used:
            self.stderr.write(self.style.WARNING('AVISO: A opção --force-delete-used-orphans está ativa. Permissões órfãs em uso SERÃO REMOVIDAS.'))

        # 1. Obter todas as permissões definidas nos modelos
        defined_perms_str = loader.model_permissions

        # 2. Obter todas as permissões do banco para as apps escaneadas
        # O prefetch_related acelera drasticamente a verificação de uso
        db_perms = Permission.objects.all().select_related('content_type').prefetch_related('group_set', 'user_set')

        db_perms_map = {f'{p.content_type.app_label}.{p.content_type.model}.{p.codename}': p for p in db_perms}

        # 3. Identificar as permissões órfãs
        orphan_perms_str = set(db_perms_map.keys()) - defined_perms_str
        for p_str in sorted(orphan_perms_str):
            perm = db_perms_map[p_str]
            # Ignora permissões de usuário customizadas que são criadas dinamicamente
            if perm.content_type.model == 'user' and perm.codename.startswith('is_'):
                orphan_perms_str.remove(p_str)

        if not orphan_perms_str:
            self.stdout.write('Nenhuma permissão órfã encontrada.')
            return

        self.stdout.write(f'Encontradas {len(orphan_perms_str)} permissões órfãs.')

        # 4. Verificar uso e separar as permissões
        perms_to_delete = []
        perms_in_use = []

        for p_str in orphan_perms_str:
            perm = db_perms_map[p_str]
            # A verificação é instantânea graças ao prefetch_related
            is_in_use = perm.group_set.exists() or perm.user_set.exists()

            if is_in_use and not force_delete_used:
                perms_in_use.append(p_str)
            else:
                perms_to_delete.append(perm)

        # 5. Reportar
        if perms_in_use:
            self.stderr.write('\nAs seguintes permissões órfãs ESTÃO EM USO e não serão excluídas:')
            for p_str in sorted(perms_in_use):
                self.stderr.write(f'- {p_str}')

        # 6. Excluir permissões órfãs não utilizadas
        if perms_to_delete:
            delete_header = (
                '\nAs seguintes permissões órfãs (incluindo as em uso) serão excluídas:'
                if force_delete_used
                else '\nAs seguintes permissões órfãs NÃO ESTÃO EM USO e serão excluídas:'
            )
            self.stderr.write(delete_header)
            pks_to_delete = [p.pk for p in perms_to_delete]
            for p in sorted(perms_to_delete, key=str):
                self.stderr.write(f'- {p.content_type.app_label}.{p.content_type.model}.{p.codename}')

            User = get_user_model()
            GroupPermission = Group.permissions.through
            UserPermission = User.user_permissions.through

            # Remove os relacionamentos com Grupos
            self.stdout.write('Removendo relacionamentos de permissões órfãs com Grupos...')
            deleted_group_rels, _ = GroupPermission.objects.filter(permission_id__in=pks_to_delete).delete()
            self.stdout.write(f'{deleted_group_rels} relacionamentos com Grupos removidos.')

            # Remove os relacionamentos com Usuários
            self.stdout.write('Removendo relacionamentos de permissões órfãs com Usuários...')
            deleted_user_rels, _ = UserPermission.objects.filter(permission_id__in=pks_to_delete).delete()
            self.stdout.write(f'{deleted_user_rels} relacionamentos com Usuários removidos.')

            # Finalmente, remove as permissões
            self.stdout.write('Excluindo os objetos de Permissão órfãos...')
            count, _ = Permission.objects.filter(pk__in=pks_to_delete).delete()
            self.stdout.write(f'\n{count} permissões órfãs foram excluídas com sucesso.')
        elif not perms_in_use:
            self.stdout.write('\nNenhuma permissão órfã para limpar.')
        else:
            self.stderr.write('\nNenhuma permissão órfã pôde ser limpa (todas estão em uso). Use --check para exibi-las sem excluir.')


# --- Comando do Django ---


class Command(BaseCommandPlus):
    help = 'Sincroniza grupos e permissões a partir de arquivos permissions.yaml nas apps.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Força a sincronização mesmo que existam avisos (warnings).')
        parser.add_argument(
            '--check',
            action='store_true',
            help='Apenas carrega e valida os arquivos, sem aplicar mudanças no banco. Também limpa permissões órfãs não utilizadas.',
        )
        parser.add_argument(
            '--force-delete-used-orphans',
            action='store_true',
            help='Força a exclusão de permissões órfãs que ainda estão em uso por algum grupo ou usuário.',
        )

    def handle(self, *args, **options):
        start_time = time.time()

        force = options['force']
        check_only = options['check']
        verbosity = options['verbosity']
        force_delete_used_orphans = options['force_delete_used_orphans']

        # 1. Carregar e consolidar dados de todas as apps alvo
        apps_to_scan = (*settings.INSTALLED_APPS_SUAP, 'djtools')

        loader = PermissionLoader(apps_to_scan)

        # 2. Exibir Erros e Avisos
        if loader.errors:
            self.stderr.write(self.style.ERROR('Erros encontrados. A sincronização foi abortada:'))
            for error in loader.errors:
                self.stderr.write(f'- {error}')
            raise CommandError('Corrija os erros nos arquivos YAML e tente novamente.')

        if loader.warnings:
            self.stdout.write(self.style.WARNING('Avisos encontrados durante o carregamento:'))
            for warning in loader.warnings:
                self.stdout.write(f'- {warning}')
            if check_only:
                raise CommandError('Avisos encontrados. Comando falhou.')
            if not force:
                raise CommandError('Use --force para continuar a sincronização mesmo com avisos.')

        if check_only:
            self.stdout.write(self.style.SUCCESS('Verificação de sintaxe dos arquivos concluída. Nenhum erro fatal encontrado.'))
            return

        syncer = PermissionSyncer(loader.consolidated_groups, stdout=self.stdout, stderr=self.stderr, style=self.style, show_tqdm=(verbosity > 0))

        syncer.clean_orphan_permissions(loader, force_delete_used=force_delete_used_orphans)

        # 3. Sincronizar com o Banco de Dados
        self.stdout.write(self.style.HTTP_INFO('Iniciando a sincronização com o banco de dados...'))

        try:
            syncer.sync()
            syncer.sync_manager_groups()
        except Exception as e:
            raise CommandError(f'Ocorreu um erro durante a sincronização com o banco: {e}')

        duration = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f'Sincronização concluída com sucesso em {duration:.2f} segundos.'))
