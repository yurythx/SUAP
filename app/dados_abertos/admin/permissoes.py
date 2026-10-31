from django.contrib.auth import get_permission_codename
from django.http import HttpRequest


class AcaoDeAlteracaoMixin:
    """Permissão ``alterar`` para actions que modificam dados: ``@admin.action(permissions=('alterar',))``.

    O ``has_change_permission`` do ``ModelAdminPlus``, chamado sem objeto, cai na permissão de
    visualização — é o que deixa quem só consulta abrir a listagem. Por isso ``permissions=('change',)``
    exibiria a action a esse usuário; aqui se exige a permissão de alterar de fato.
    """

    def has_alterar_permission(self, request: HttpRequest) -> bool:
        opts = self.opts
        return request.user.has_perm(f'{opts.app_label}.{get_permission_codename("change", opts)}')
