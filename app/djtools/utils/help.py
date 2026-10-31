"""Geração da ajuda (help) das telas de listagem/cadastro do admin do SUAP.

Reúne :func:`get_item` (consumida por :func:`djtools.views.help_view`) e seus
helpers privados, extraídos para manter a complexidade ciclomática de cada função
dentro do limite do projeto (``C901`` ≤ 10).
"""

from django.apps import apps
from django.contrib import admin
from django.contrib.auth.models import Group
from django.utils.safestring import mark_safe

from djtools import HELP_XML_CONTENTS
from djtools.choices import GENDER
from djtools.utils import normalizar_nome_proprio
from rh.models import PessoaFisica


def get_artigo(model, singular=True, definido=True):
    """Retorna o artigo concordante com o gênero do modelo.

    Args:
        model: Classe de modelo cujo gênero é consultado em :data:`GENDER`.
        singular: Se ``True``, usa a forma singular; caso contrário, a plural.
        definido: Se ``True``, retorna artigo definido (o/a); caso contrário,
            indefinido (um/uma).

    Returns:
        str: O artigo apropriado (ex.: ``'a'``, ``'os'``, ``'uma'``, ``'uns'``).
    """
    key = f'{model._meta.app_label}.{model.__name__}'
    model_gender = GENDER.get(key, 'M')
    if model_gender == 'F':
        if definido:
            model_artigo = singular and 'a' or 'as'
        else:
            model_artigo = singular and 'uma' or 'umas'
    else:
        if definido:
            model_artigo = singular and 'o' or 'os'
        else:
            model_artigo = singular and 'um' or 'uns'
    return model_artigo


def get_pronome(model, singular=True):
    """Retorna a contração ``de + artigo`` concordante com o gênero do modelo.

    Args:
        model: Classe de modelo cujo gênero é consultado em :data:`GENDER`.
        singular: Se ``True``, usa a forma singular; caso contrário, a plural.

    Returns:
        str: A contração apropriada (ex.: ``'da'``, ``'do'``, ``'dos'``); string
        vazia se o gênero não estiver mapeado.
    """
    key = f'{model._meta.app_label}.{model.__name__}'
    model_gender = GENDER.get(key, 'M')
    model_artigo = ''
    if model_gender == 'F':
        model_artigo = singular and 'da' or 'das'
    elif model_gender == 'M':
        model_artigo = singular and 'do' or 'dos'
    return model_artigo


def _format_simple_search_field(model, search_field, i, total):
    """Formata um campo de busca direto (sem ``__``) como fragmento HTML.

    Args:
        model: Modelo ao qual o campo pertence.
        search_field: Nome do campo de busca (sem travessia de relacionamento).
        i: Índice do campo na lista ``search_fields`` do admin.
        total: Quantidade total de campos de busca, usada para o conector " e ".

    Returns:
        str: Fragmento HTML com o ``verbose_name`` do campo, prefixado pelo
        separador adequado conforme a posição (``''``, ``', '`` ou ``' e '``).
    """
    field_name = model._meta.get_field(search_field).verbose_name.lower()
    if i == 0:
        return f'<span class="italico">{field_name}</span>'
    elif i == total - 1:
        return f' e <span class="italico">{field_name}</span>'
    return f', <span class="italico">{field_name}</span>'


def _format_related_search_field(model, search_field, i, total):
    """Formata um campo de busca com travessia de relacionamento (``__``).

    Percorre cada segmento do caminho (ex.: ``user__pessoafisica__nome``)
    resolvendo o modelo relacionado a cada passo, e monta os fragmentos HTML
    descrevendo o campo final e os pronomes dos relacionamentos intermediários.

    Args:
        model: Modelo inicial a partir do qual o caminho é percorrido.
        search_field: Caminho de busca com segmentos separados por ``__``.
        i: Índice do campo na lista ``search_fields`` do admin.
        total: Quantidade total de campos de busca, usada para o conector " e ".

    Returns:
        list[str]: Fragmentos HTML do campo final seguidos dos pronomes dos
        relacionamentos intermediários (estes em ordem inversa).
    """
    related_class = model
    related_fields = []
    fragments = []
    parts = search_field.split('__')
    for j, field in enumerate(parts):
        field_name = getattr(related_class._meta.get_field(field), 'verbose_name', str(related_class._meta.get_field(field))).lower()
        if 'user' in related_class._meta.__str__().lower() and field == 'pessoafisica':
            related_class = PessoaFisica
        else:
            related_class = (
                hasattr(related_class._meta.get_field(field), 'related_model') and related_class._meta.get_field(field).related_model or ''
            )
        if j == len(parts) - 1:
            if i == 0:
                fragments.append(f'<span class="italico">{field_name}</span>')
            elif i == total - 1:
                fragments.append(f' e <span class="italico">{field_name}</span>')
            else:
                fragments.append(f', <span class="italico">{field_name}</span>')
        else:
            pronome = get_pronome(related_class)
            related_fields.insert(0, f' {pronome} <span class="italico">{field_name}</span>')
    return fragments + related_fields


def _build_filters_description(model, model_admin):
    """Monta o texto HTML que descreve o filtro de busca por texto da listagem.

    Args:
        model: Modelo da listagem.
        model_admin: Instância de admin do modelo; fornece ``search_fields``,
            ``avoid_short_search`` e ``list_per_page``.

    Returns:
        str: Parágrafo HTML descrevendo os campos pesquisáveis (e as regras de
        busca quando ``avoid_short_search`` está ativo); string vazia se não há
        admin ou nenhum campo de busca.
    """
    if not model_admin:
        return ''
    search_fields = []
    total = len(model_admin.search_fields)
    for i, search_field in enumerate(model_admin.search_fields):
        if '__' not in search_field:
            search_fields.append(_format_simple_search_field(model, search_field, i, total))
        else:
            search_fields.extend(_format_related_search_field(model, search_field, i, total))
    if not search_fields:
        return ''
    filters = f"""<p>Através do filtro de <b>Texto</b> , é possível buscar
                            {get_artigo(model, False)} {model._meta.verbose_name_plural.lower()}
                            através do(s) seguinte(s) campo(s): {''.join(search_fields)}."""
    if model_admin.avoid_short_search:
        filters += f"""
                        As preposições "da", "de", "di", "do", "du", "das", "dos", "e" e termos com tamanho menor que 3
                        caracteres são desconsiderados na busca. O resultado é paginado e apenas <span class="italico">{model_admin.list_per_page}
                        registros</span> são listados por vez. Para visualizar outros
                        registros, navegue clicando no link da página contendo seu respectivo número.</p>"""
    return filters


def _get_groups(app, view):
    """Lista os grupos que possuem a permissão correspondente à view.

    Para views de alteração (``change_*``) considera também a permissão de
    visualização (``view_*``).

    Args:
        app: ``app_label`` ao qual a permissão pertence.
        view: Codename da permissão/view (ex.: ``change_pessoa``).

    Returns:
        list[str]: Nomes dos grupos com a(s) permissão(ões).
    """
    groups = []
    codenames = (view, view.replace('change_', 'view_')) if view.startswith('change_') else (view,)
    for group in Group.objects.filter(permissions__codename__in=codenames, permissions__content_type__app_label=app).distinct():
        groups.append(group.name)
    return groups


def _get_auto_related(model):
    """Retorna os relacionamentos reversos auto-criados do modelo.

    Args:
        model: Modelo cujos campos reversos são inspecionados.

    Returns:
        list[tuple]: Pares ``(field, model_dono)`` para cada relação um-para-um
        ou um-para-muitos auto-criada e não concreta; ``model_dono`` é ``None``
        quando a relação aponta para o próprio ``model``.
    """
    return [
        (f, f.model if f.model != model else None)
        for f in model._meta.get_fields()
        if (f.one_to_many or f.one_to_one) and f.auto_created and not f.concrete
    ]


def _append_required_model(required_models, verbose_name, optional):
    """Acrescenta um modelo pré-requisito à lista, evitando duplicatas e ``User``.

    Args:
        required_models: Lista acumuladora de descrições de modelos requeridos
            (modificada in-place).
        verbose_name: ``verbose_name`` do modelo relacionado.
        optional: Se ``True``, anexa o sufixo ``(Opcional)`` à descrição.
    """
    required_models_string = '{} {}'.format(verbose_name, optional and '(Opcional)' or '')
    if required_models_string not in required_models and not required_models_string.startswith('User'):
        required_models.append(required_models_string)


def _collect_fk_required_models(required_models, fields, model, normalize=False):
    """Coleta os modelos referenciados por chaves estrangeiras dos campos dados.

    Ignora campos sem modelo remoto e auto-referências ao próprio ``model``.

    Args:
        required_models: Lista acumuladora (modificada in-place).
        fields: Iterável de campos a inspecionar.
        model: Modelo corrente, usado para descartar auto-referências.
        normalize: Se ``True``, normaliza o ``verbose_name`` como nome próprio.
    """
    for field in fields:
        if not hasattr(field.remote_field, 'model') or field.remote_field.model == model:
            continue
        verbose_name = field.remote_field.model._meta.verbose_name
        if normalize:
            verbose_name = normalizar_nome_proprio(verbose_name)
        _append_required_model(required_models, verbose_name, field.null or field.blank)


def _collect_required_models(request, model, model_admin):
    """Reúne os modelos que precisam existir para cadastrar o modelo dado.

    Considera as chaves estrangeiras dos campos do modelo, os campos de escolha
    do formulário do admin, os inlines e os modelos pais (herança).

    Args:
        request: Requisição atual, usada para instanciar o formulário do admin.
        model: Modelo a ser cadastrado.
        model_admin: Instância de admin do modelo.

    Returns:
        list[str]: Descrições dos modelos pré-requisito (com sufixo
        ``(Opcional)`` quando aplicável), sem duplicatas.
    """
    required_models = []
    form = model_admin.get_form(request)()
    _collect_fk_required_models(required_models, model_admin.model._meta.fields, model)
    for field in form.fields.values():
        if hasattr(field.widget, 'choices') and hasattr(field.widget.choices, 'queryset'):
            _append_required_model(required_models, field.widget.choices.queryset.model._meta.verbose_name, not field.required)
    for inline in model_admin.inlines:
        _collect_fk_required_models(required_models, inline.model._meta.fields, model)
    for pai in model_admin.model._meta.get_parent_list():
        _collect_fk_required_models(required_models, pai._meta.fields, model, normalize=True)
    return required_models


def _build_save_actions(model, groups):
    """Constrói as ações de salvamento do formulário de cadastro para a ajuda.

    Args:
        model: Modelo sendo cadastrado.
        groups: Grupos com permissão sobre a ação, copiados para cada item.

    Returns:
        list[dict]: Itens de ajuda para "Salvar", "Salvar e Adicionar Outro(a)"
        e "Salvar e Continuar Editando".
    """
    actions = []
    actions.append(
        {
            'view': None,
            'name': 'Salvar',
            'description': f'Salva {get_artigo(model)} {model._meta.verbose_name.lower()} no sistema e retorna para a página anterior.',
            'groups': groups,
            'url': None,
            'tip': 'clique no botão "Salvar" localizado abaixo do formulário.',
        }
    )
    actions.append(
        {
            'view': None,
            'name': 'Salvar e Adicionar Outro(a)',
            'description': f'Salva {get_artigo(model)} {model._meta.verbose_name.lower()} no sistema e limpa o formulário para que mais {get_artigo(model, True, False)} {model._meta.verbose_name.lower()} possa ser cadastrada.',
            'groups': groups,
            'url': None,
            'tip': 'clique no botão "Salvar e adicionar outro" localizado abaixo do formulário.',
        }
    )
    actions.append(
        {
            'view': None,
            'name': 'Salvar e Continuar Editando',
            'description': f'Salva {get_artigo(model)} {model._meta.verbose_name.lower()} no sistema e continua na mesma página para que uma nova \
                                    alteração seja realizada, se necessário.',
            'groups': groups,
            'url': None,
            'tip': 'clique no botão "Salvar e continuar editando" localizado abaixo do formulário.',
        }
    )
    return actions


def _build_adicionar_details(request, model, model_admin, groups):
    """Monta os detalhes de ajuda da ação "Adicionar" de um modelo.

    Args:
        request: Requisição atual (checagem de permissões e formulário).
        model: Modelo a ser cadastrado.
        model_admin: Instância de admin do modelo (pode ser ``None``).
        groups: Grupos com permissão sobre a ação.

    Returns:
        tuple[list, list, list]: Tripla ``(required_to, required_models,
        actions)`` com os cadastros pré-requisito permitidos ao usuário, os
        modelos requeridos e as ações de salvamento.
    """
    required_to = []
    for relation in _get_auto_related(model):
        if relation[0].related_model not in admin.site._registry:
            continue
        add_permission = f'add_{relation[0].related_model.__name__.lower()}'
        app_label = relation[0].related_model._meta.app_label
        if not request.user.has_perm(f'{app_label}.{add_permission}'):
            continue
        sub_item = get_item(request, app_label, add_permission)
        if sub_item and sub_item['groups'] and sub_item not in required_to:
            required_to.append(sub_item['view'])
    required_models = []
    actions = []
    if model_admin:
        required_models = _collect_required_models(request, model, model_admin)
        actions = _build_save_actions(model, groups)
    return required_to, required_models, actions


def _build_listar_actions(request, app, view, model, model_admin):
    """Monta as ações de ajuda da tela de listagem de um modelo.

    Inclui o item "Adicionar" (quando o usuário tem a permissão) e a exportação
    para XLS (quando habilitada no admin).

    Args:
        request: Requisição atual (checagem de permissão).
        app: ``app_label`` do modelo.
        view: Codename da view de listagem.
        model: Modelo listado.
        model_admin: Instância de admin do modelo (pode ser ``None``).

    Returns:
        list[dict]: Itens de ação disponíveis na listagem.
    """
    actions = []
    add_permission = f'add_{model.__name__.lower()}'
    if request.user.has_perm(f'{app}.{add_permission}'):
        sub_item = get_item(request, app, add_permission)
        if sub_item and sub_item['groups']:
            actions.append(sub_item)
    if model_admin and hasattr(model_admin, 'export_to_xls') and model_admin.export_to_xls:
        actions.append({'view': 'admin.exportar_xls'})
    return actions


def _merge_help_xml_item(default, item, action):
    """Mescla, in-place, o conteúdo de ajuda do XML sobre o item padrão.

    Para chaves de lista, concatena; para as demais, sobrescreve. No caso
    especial ``description`` em listagens, preserva o restante do texto padrão
    após o primeiro parágrafo.

    Args:
        default: Dicionário de ajuda gerado dinamicamente (modificado in-place).
        item: Conteúdo de ajuda proveniente do XML (``HELP_XML_CONTENTS``).
        action: Ação corrente (``'Listar'`` ou ``'Adicionar'``).
    """
    for key in item:
        if item[key] and item[key] != 'None':
            if default[key].__class__ is list:
                default[key] += item[key]
            else:
                if key == 'description' and action == 'Listar':
                    default[key] = '{}{}'.format(item[key], '</p>'.join(default[key].split('</p>')[1:]))
                else:
                    default[key] = item[key]


def get_item(request, app, view, detail=False):
    """Monta o dicionário de ajuda de uma view de listagem ou cadastro.

    Resolve o modelo e o admin a partir de ``app``/``view``, gera a descrição,
    os filtros, os grupos com permissão e — quando ``detail`` é ``True`` — os
    cadastros pré-requisito, modelos requeridos e ações; por fim mescla o
    conteúdo manual definido em ``HELP_XML_CONTENTS``.

    Args:
        request: Requisição atual (checagem de permissões e formulários).
        app: ``app_label`` do modelo.
        view: Codename da view (ex.: ``change_pessoa``, ``add_pessoa``).
        detail: Se ``True``, inclui ações e pré-requisitos detalhados.

    Returns:
        dict | None: Dicionário de ajuda da view; quando ``view`` não mapeia um
        modelo, retorna o conteúdo manual de ``HELP_XML_CONTENTS`` ou ``None``.
    """
    view_name = view.replace('change_', '').replace('add_', '')
    if view_name != view:
        model = apps.get_model(app, view_name)
        model_admin = model in admin.site._registry and admin.site._registry[model] or None
    else:
        model = None
        model_admin = None

    if not model:
        help_key = f'{app}.{view}'
        return help_key in HELP_XML_CONTENTS and HELP_XML_CONTENTS[help_key] or None

    action = view.startswith('change_') and 'Listar' or view.startswith('add_') and 'Adicionar' or view
    name = f'{action} {model._meta.verbose_name}'
    tip = None
    filters = ''
    if action == 'Listar':
        description = f"""<p>Esta funcionalidade tem por objetivo listar {get_artigo(model, False)}
                                {model._meta.verbose_name_plural.lower()} cadastrad{get_artigo(model, False)}
                                no sistema.</p>"""
        filters = _build_filters_description(model, model_admin)
    else:
        description = (
            f'<p>Esta funcionalidade tem por objetivo adicionar {get_artigo(model, False)} {model._meta.verbose_name_plural.lower()} no sistema.</p>'
        )
        tip = f'clique no botão "{name}" localizado no canto superior direito da tela.'

    groups = _get_groups(app, view)
    required_to = []
    required_models = []
    actions = []
    if detail and action == 'Adicionar':
        required_to, required_models, actions = _build_adicionar_details(request, model, model_admin, groups)
    if detail and action == 'Listar':
        actions = _build_listar_actions(request, app, view, model, model_admin)

    url = f'/djtools/help_view/{app}/{view}/'
    default = {
        'view': f'{app}.{view}',
        'name': name,
        'description': mark_safe(description),
        'filters': mark_safe(filters),
        'groups': groups,
        'url': url,
        'actions': actions,
        'required_to': required_to,
        'required_models': required_models,
        'detail': '',
        'conditions': [],
        'tip': tip,
    }

    help_key = f'{app}.{view}'
    item = help_key in HELP_XML_CONTENTS and HELP_XML_CONTENTS[help_key] or None
    if item:
        _merge_help_xml_item(default, item, action)
    return default
