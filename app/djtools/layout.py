import hashlib
from typing import Any

from django.dispatch import Signal
from django.utils.text import slugify

from djtools.modulos_ocultos import funcao_oculta
from djtools.utils import get_cache, get_session_cache, silenciar

index_infos_data = Signal()  # providing_args=["request"]
index_quick_access_data = Signal()  # providing_args=["request"]
index_inscricoes_data = Signal()  # providing_args=["request"]
index_quadros_data = Signal()  # providing_args=["request"]
index_notificacoes_importantes_data = Signal()
index_atribuidos_a_mim_data = Signal()  # providing_args=["request"]
index_atribuidos_a_meus_grupos_data = Signal()  # providing_args=["request"]
servicos_anonimos_data = Signal()  # providing_args=["request"]
quadros_cadastrados = []
apps_dos_quadros: dict[str, str] = {}


class Layout:
    pass


class Quadro(Layout):
    def __init__(self, titulo, icone, classes=''):
        self.klass_name = ''
        self.items = {}
        self.titulo = titulo
        self.icone = icone
        self.classes = classes

    def add_item(self, item):
        klass_name = type(item).__name__
        self.klass_name = klass_name

        if klass_name not in self.items:
            self.items[klass_name] = []

        self.items[klass_name].append(item)

    def add_itens(self, itens):
        for item in itens:
            self.add_item(item)

    def has_items(self):
        return len(self.items) > 0

    def get_items(self, klass_name):
        return self.items.get(klass_name)

    def get_acessos_rapidos(self):
        return self.get_items('ItemAcessoRapido')

    def get_buscas_rapidas(self):
        return self.get_items('BuscaRapida')

    def get_calendarios(self):
        return self.get_items('ItemCalendario')

    def get_contadores(self):
        return self.get_items('ItemContador')

    def get_indicadores(self):
        return self.get_items('ItemIndicador')

    def get_grupos(self):
        return self.get_items('ItemGrupo')

    def get_imagens(self):
        return self.get_items('ItemImagem')

    def get_listas(self):
        return self.get_items('ItemLista')

    def get_noticias(self):
        return self.get_items('ItemNoticia')

    def get_videos(self):
        return self.get_items('ItemVideo')

    def get_titulos(self):
        return self.get_items('ItemTitulo')

    def get_hash(self):
        retorno = []
        if hasattr(self, 'klass_name') and self.items and self.items.get(self.klass_name):
            for key, value in self.items.items():
                retorno.append(str(key) + str([str(v) for v in value]))
            retorno = ' '.join(sorted(retorno)).encode('utf-8')
            return hashlib.md5(retorno).hexdigest()
        else:
            return None


class ItemBase(Layout):
    def __init__(self, titulo, url):
        self.titulo = titulo
        self.url = url

    def __str__(self):
        if self.url:
            return self.url
        else:
            return str(id(self))


class ItemCalendario(Layout):
    def __init__(self, calendario, legenda='', titulo='', url=''):
        self.calendario = calendario
        self.legenda = legenda
        self.titulo = titulo
        self.url = url


class ItemLista(Layout):
    def __init__(self, titulo, valor, grupo='', url=''):
        self.titulo = titulo
        self.valor = valor
        self.grupo = grupo
        self.url = url


class ItemAcessoRapido(ItemBase):
    def __init__(self, icone='link', classe='default', target='', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icone = icone
        self.classe = classe
        self.target = target


class BuscaRapida(ItemBase):
    def __init__(self, extra_valor='', extra_nome='', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_valor = extra_valor
        self.extra_nome = extra_nome


class ItemNoticia(ItemBase):
    def __init__(self, chapeu='', target='', grupo='', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chapeu = chapeu
        self.target = target
        self.grupo = grupo

    def __str__(self):
        return f'{self.url} {self.chapeu} {self.target} '


class ItemVideo(ItemBase):
    def __init__(self, descricao='', youtube_id='', layout='', botao='', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.descricao = descricao
        self.youtube_id = youtube_id
        self.layout = layout
        self.botao = botao

    def __str__(self):
        return f'{self.titulo} {self.descricao}'


class ItemContador(ItemBase):
    def __init__(self, qtd, subtitulo='', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.qtd = qtd
        self.subtitulo = subtitulo


class ItemIndicador(ItemBase):
    def __init__(self, qtd, grupo='', icone='', classname='', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.qtd = qtd
        self.grupo = grupo
        self.icone = icone
        self.classname = classname


class ItemGrupo(ItemBase):
    def __init__(self, grupo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.grupo = grupo


class ItemImagem(ItemBase):
    def __init__(self, path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = path


class ItemTitulo(Layout):
    def __init__(self, titulo):
        self.titulo = titulo

    def __str__(self):
        return self.titulo


def quadro(titulo, icone, classes='', pode_esconder=False, session_cache=0, global_cache=0):
    nome_quadro = titulo.upper()
    quadros_cadastrados.append(nome_quadro)

    def receive_function(func):
        @silenciar()
        def index_quadro(sender, request, **kwargs):
            from comum.models import IndexLayout

            layouts_salvos = request.session.get('index_layout')
            if not layouts_salvos:
                layouts_salvos = request.session['index_layout'] = {}

            if nome_quadro in list(layouts_salvos.keys()):
                quadro_visivel = not request.session['index_layout'][nome_quadro]['escondido']
            else:
                qs = IndexLayout.objects.filter(quadro_nome=nome_quadro, usuario=request.user)
                if not qs.exists():
                    i = IndexLayout(quadro_nome=nome_quadro, quadro_coluna=1, quadro_ordem=1, usuario=request.user)
                    i.save()
                    IndexLayout.recarregar_layouts(request)
                quadro_visivel = True

            obj = Quadro(titulo, icone, classes)
            obj.pode_esconder = pode_esconder
            if quadro_visivel or not pode_esconder:
                key = f'quadro_{slugify(titulo.upper())}'

                def do():
                    result = func(obj, request)
                    return result

                if session_cache:
                    return get_session_cache(request, key, do, session_cache)
                if global_cache:
                    return get_cache(key, do, global_cache)
                return do()
            else:
                return None

        apps_dos_quadros[nome_quadro] = func.__module__.split('.')[0]
        index_quadros_data.connect(index_quadro, dispatch_uid=titulo.upper())
        return index_quadro

    return receive_function


def connect_signal(signal):
    def receive_function(func):
        @silenciar(return_on_error=[])
        def index_signal(sender, request, **kwargs) -> list:
            if funcao_oculta(func):
                return []
            return func(request)

        signal.connect(index_signal)
        return index_signal

    return receive_function


def quick_access():
    return connect_signal(index_quick_access_data)


def info():
    return connect_signal(index_infos_data)


def inscricao():
    return connect_signal(index_inscricoes_data)


def notificacoes_importantes():
    return connect_signal(index_notificacoes_importantes_data)


def servicos_anonimos():
    return connect_signal(servicos_anonimos_data)


def atribuidos_a_mim():
    return connect_signal(index_atribuidos_a_mim_data)


def atribuidos_a_meus_grupos():
    return connect_signal(index_atribuidos_a_meus_grupos_data)


def gerar_servicos_anonimos(request):
    servicos_anonimos = []
    for _, data in servicos_anonimos_data.send(sender=gerar_servicos_anonimos, request=request):
        servicos_anonimos.extend(data)
    servicos_anonimos = sorted(servicos_anonimos, key=lambda data: data['categoria'])
    return servicos_anonimos


def chaves_de_quadros_visiveis() -> list[str]:
    from djtools.modulos_ocultos import app_oculto

    chaves = []
    for receiver in index_quadros_data.receivers:
        chave = receiver[0][0].upper()
        if app_oculto(apps_dos_quadros.get(chave, '')):
            continue
        chaves.append(chave)
    return chaves


def get_quadro_by_name(name: str, request: Any) -> Quadro | None:
    from djtools.modulos_ocultos import app_oculto

    if app_oculto(apps_dos_quadros.get(name, '')):
        return None
    quadro = None
    for ids, function, _ in index_quadros_data.receivers:
        if name == ids[0]:
            quadro = function()(name, request)
    return quadro
