from pathlib import Path

from django.conf import settings

from djtools.management.commands.sync_permissions import PermissionLoader


def _avisos_de_app_manager(loader: PermissionLoader) -> list[str]:
    return [aviso for aviso in loader.warnings if 'app_manager' in aviso]


def test_yamls_do_suap_concordam_sobre_o_gerenciador_de_cada_grupo() -> None:
    """Mesmo grupo em vários ``permissions.yaml`` precisa do mesmo ``app_manager`` em todos (#17403).

    Com divergência, o ``sync`` fica com o da primeira app carregada, enquanto
    ``obter_grupos_por_app_yaml`` lê cada arquivo sozinho — e ``/comum/grupos_usuarios/`` quebrava.
    """
    loader = PermissionLoader((*settings.INSTALLED_APPS_SUAP, 'djtools'))

    assert _avisos_de_app_manager(loader) == []


def test_app_manager_divergente_gera_aviso(tmp_path: Path) -> None:
    (tmp_path / 'a.yaml').write_text('Grupo Compartilhado:\n  app_manager: rsc\n')
    (tmp_path / 'b.yaml').write_text('Grupo Compartilhado:\n  app_b: {}\n')

    loader = PermissionLoader(())
    loader.load_and_process_yaml(str(tmp_path / 'a.yaml'), 'app_a')
    loader.load_and_process_yaml(str(tmp_path / 'b.yaml'), 'app_b')

    assert len(_avisos_de_app_manager(loader)) == 1
