"""Fatia 3 da doc de usuário do ``comum`` — grupos, notificações e configuração do sistema.

Cobre o mecanismo de **autorização** do SUAP inteiro (quem está em qual grupo, e a regra que
concede grupo sozinha no login), o interruptor de **notificações** de cada pessoa e as telas
de **administração** do sistema: parâmetros por aplicação, contas de usuário e o aviso de
parada programada.

Cada teste é o roteiro de UMA tarefa da doc, na ordem em que ela as apresenta; as asserções
existem para a rodada falhar alto quando a tela muda de forma, e as ``anotar`` despejam
rótulos/opções que a redação copia em vez de deduzir de ``views.py``.

**A regra desta fatia** é a mesma do e2e do módulo: grupo é o que dá permissão, e as outras
cinco fatias dependem dos grupos de ``PAPEIS``. Nada aqui muta papel compartilhado — quem entra
e sai de grupo é o servidor descartável ``alvo_grupo`` (que nunca loga) ou a conta descartável
``conta_pessoal``, e os dois grupos usados são inertes e nascem vazios.

Nenhuma tarefa desta fatia veio de ``.feature``: o ``comum`` só tem cinco, todas de cadastro e
de senha. As tarefas 12 a 19 foram **propostas** a partir do ``menu.yaml``, do admin e do
encadeamento das telas.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from comum.tests.doc.conftest import (
    CATEGORIA_NOTIFICACAO_DOC,
    MOTIVO_DA_MANUTENCAO_DOC,
    MOTIVO_NO_GRUPO_DOC,
    SISTEMA_EM_MANUTENCAO_DOC,
    anotar,
)
from comum.tests.e2e.conftest import GRUPO_AUTOMATIZADO, GRUPO_GERENCIADO, SIGLA_SETOR_SEM_SERVIDOR
from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

MINHA_CONTA = '/comum/minha_conta/'
GERENCIAMENTO_GRUPO = '/comum/gerenciamento_grupo/'
AUTOMATIZACAO_LISTAR = '/comum/automatizacao_grupo/{grupo}/'
PREFERENCIAS = '/admin/comum/preferencianotificacao/'
CATEGORIAS = '/admin/comum/categorianotificacao/'
MANUTENCOES = '/admin/comum/manutencaoprogramada/'
USUARIOS = '/admin/comum/user/'
PAINEL = '/comum/admin/'
CONFIGURACAO = '/comum/configuracao/'
CONFIGURACAO_DO_APP = '/comum/configuracao/{app}/'
EXCLUIR = '/comum/excluir/{app}/{model}/{pks}/'

# O rótulo da opção no filtro *Módulo* das duas telas de grupo. É `AppConfig.get_full_name()`
# (`djtools/apps.py:8`), isto é, `área :: verbose_name` — e não o nome do diretório da aplicação,
# que é o que vai na query string.
MODULO_COMUM = 'Comum :: Comum'

# O grupo cujos menus a tela de menus exibe. Medido pelo e2e: `Avaliador de Sala` resolve 7
# entradas de `menu.yaml` a partir das suas permissões, e os dois grupos inertes desta fatia
# resolvem zero — tela vazia não ilustra o cruzamento permissão -> menu.
GRUPO_COM_MENUS = 'Avaliador de Sala'

# A aplicação cuja configuração o teste GRAVA, herdada da escolha medida do e2e: é a única com
# um único campo, e o valor gravado é o próprio default documentado — a gravação é semanticamente
# um no-op para o resto da suíte, que compartilha o banco.
#
# NUNCA submeta `/comum/configuracao/comum/`: aquele formulário tem 42 campos e o `save` reescreve
# TODAS as chaves de `Configuracao` do app de uma vez, inclusive `url_webmail` e
# `permite_autenticacao_duplo_fator`, de que as fatias 2 e 4 a 6 dependem.
APP_CONFIGURAVEL = 'licenca_capacitacao'
CAMPO_CONFIGURAVEL = 'Quando permitir análise de solicitações de alteração'
VALOR_CONFIGURAVEL = 'Somente após o término das inscrições (padrão)'


def _filtro(grupo) -> str:
    """Query string que devolve a tela de grupos ao grupo do teste.

    ``modulo`` e ``grupo`` são obrigatórios: sem o primeiro a tela nem monta as abas, e sem o
    segundo a view escolhe ``grupos_gerenciados[0]`` de uma queryset sem ordenação — o teste
    passaria a ilustrar o grupo que o banco devolver primeiro.
    """
    return f'?modulo=comum&grupo={grupo.pk}'


def _momento(dias: int, hora: int) -> str:
    """Momento futuro em ``dd/mm/aaaa HH:MM``, o formato do tipo ``data e hora`` do SUAP."""
    return (datetime.now() + timedelta(days=dias)).strftime(f'%d/%m/%Y {hora:02d}:00')


def test_colocar_e_tirar_alguem_de_um_grupo(logado_comum, grupo_gerenciado, servidores_comum, capturar):
    """Tarefa 12 — o ciclo inteiro de um usuário num grupo, pela tela do gestor.

    Um teste só, e não três, porque "ver o histórico" e "remover do grupo" não existem sem a
    inclusão anterior: são degraus do mesmo estado, e é assim que a doc os apresenta.

    O filtro é percorrido pela interface (o ``select`` *Módulo* + *Filtrar* + a aba do grupo) e
    não por query string, porque ele **é** o primeiro passo da tarefa: sem filtrar, a tela não
    mostra grupo nenhum.
    """
    from comum.models import HistoricoUsuarioGrupo, UsuarioGrupo

    alvo = servidores_comum['alvo_grupo']
    pagina = logado_comum('gestor_grupos')

    tela = Tela(pagina).ir(GERENCIAMENTO_GRUPO)
    tela.ver_titulo('Gerenciamento de grupos')
    anotar('grupos-filtro', tela)
    tela.preencher('Módulo', 'lista', MODULO_COMUM)
    tela.clicar_botao('Filtrar')
    tela.esperar()
    tela.clicar_link(GRUPO_GERENCIADO)
    tela.esperar()
    tela.ver_texto('Nenhum usuário encontrado nesse grupo.')

    # `class="btn success popup"` no template: o formulário abre num fancybox em iframe, e o
    # `httprr('..')` da view devolve `close_fancybox()` porque o link carrega `_popup=1`
    # (`djtools/utils/response.py:112`) — daí a mensagem aparecer na página de trás, recarregada.
    tela.clicar_botao('Adicionar usuário ao grupo')
    popup = tela.popup()
    popup.ver_titulo('Adicionar Usuário ao Grupo')
    anotar('grupo-adicionar-usuario', popup)
    popup.preencher_formulario(
        [
            ('Usuário', 'autocomplete multiplo', alvo.matricula),
            ('Motivo', 'textarea', MOTIVO_NO_GRUPO_DOC),
            # Prefixo curto de propósito: o rótulo real tem 300 caracteres e o XPath de checkbox
            # casa por `contains`.
            ('Confirmo que desejo adicionar', 'checkbox', 'marcar'),
        ]
    )
    capturar(pagina, 'grupo-adicionar-usuario')
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Usuário(s) adicionado(s) com sucesso.')
    usuario_grupo = UsuarioGrupo.objects.filter(user=alvo.get_user(), group=grupo_gerenciado).first()
    assert usuario_grupo, 'a UI disse que adicionou, mas o vínculo com o grupo não persistiu'
    assert HistoricoUsuarioGrupo.objects.filter(usuario=alvo.get_user(), grupo=grupo_gerenciado, motivo__contains=MOTIVO_NO_GRUPO_DOC).exists(), (
        'o histórico da inclusão não registrou o motivo informado'
    )

    tela.ver_texto(alvo.matricula)
    tela.ver_texto(MOTIVO_NO_GRUPO_DOC)
    anotar('grupos-gerenciamento', tela)
    capturar(pagina, 'grupos-gerenciamento')

    tela.clicar_botao('Histórico')
    historico = tela.popup()
    historico.ver_texto(f'Adicionado(a) ao grupo {grupo_gerenciado}')
    anotar('grupo-historico', historico)
    capturar(pagina, 'grupo-historico')

    # O fancybox cobre a página de trás: para clicar no cartão é preciso sair dele, e recarregar
    # a tela filtrada é o caminho mais curto.
    tela.ir(GERENCIAMENTO_GRUPO + _filtro(grupo_gerenciado))
    tela.clicar_botao('Remover deste Grupo')

    tela.sucesso(f'Usuário foi removido do grupo {grupo_gerenciado} com sucesso.')
    assert not UsuarioGrupo.objects.filter(pk=usuario_grupo.pk).exists(), 'a UI disse que removeu, mas o vínculo continua no banco'

    # Etapa 3 — conferir o que um grupo libera ANTES de conceder. A aba trocada de propósito:
    # medido pelo e2e, os dois grupos inertes desta fatia resolvem ZERO entradas de menu, e uma
    # tela vazia não ilustraria o cruzamento permissão -> menu que esta porta existe para mostrar.
    tela.clicar_link(GRUPO_COM_MENUS)
    tela.esperar()
    tela.clicar_botao('Menus do grupo')
    menus = tela.popup()
    menus.ver_titulo(f'Menus Visíveis para Grupo: {GRUPO_COM_MENUS}')
    menus.ver_texto('Administração::Reservas de Salas::Indicadores')
    anotar('menus-do-grupo', menus)
    capturar(pagina, 'menus-do-grupo')


def test_automatizar_a_entrada_no_grupo_por_setor(logado_comum, grupo_automatizado, servidores_comum, capturar):
    """Tarefa 13 — a regra que põe (e tira) gente do grupo sozinha, no login.

    O assistente de dois passos é a tarefa inteira: o segundo passo não existe sem o primeiro —
    é o POST do passo 1 que produz a análise de impacto exibida no passo 2.

    A asserção do meio é a que a doc promete ao leitor: a tela **anuncia** quem será removido
    antes de a regra valer. O usuário que hoje está no grupo vem da fixture; o setor escolhido
    não tem servidor nenhum, então a regra gravada é real e não alcança papel compartilhado.
    """
    from comum.models import ConfiguracaoAutomatizacaoGrupo

    alvo = servidores_comum['alvo_grupo']
    pagina = logado_comum('gestor_grupos')

    tela = Tela(pagina).ir(GERENCIAMENTO_GRUPO + _filtro(grupo_automatizado))
    tela.clicar_botao('Automatizar grupo em setores')
    tela.esperar()
    assert AUTOMATIZACAO_LISTAR.format(grupo=grupo_automatizado.pk) in tela.pagina.url, (
        f'o botão do gerenciamento não levou à automatização: {tela.pagina.url}'
    )
    tela.ver_titulo(f'Automatização do grupo {grupo_automatizado} em setores')
    tela.ver_texto('Não existem automatizações do grupo')
    anotar('automatizacao-listagem', tela)
    capturar(pagina, 'automatizacao-listagem')

    tela.clicar_botao('Adicionar automatização a grupo')
    tela.esperar()
    anotar('automatizacao-formulario', tela)
    tela.preencher('Setores', 'autocomplete multiplo', SIGLA_SETOR_SEM_SERVIDOR)
    capturar(pagina, 'automatizacao-formulario')
    tela.clicar_botao('Continuar')

    tela.ver_texto('Análise de impacto da nova Automatização')
    tela.ver_texto(str(alvo.get_user()))
    anotar('automatizacao-impacto', tela)
    tela.preencher('Confirma operação?', 'checkbox', 'marcar')
    capturar(pagina, 'automatizacao-impacto')
    tela.clicar_botao('Finalizar')

    tela.sucesso('Automatização de grupo em setores realizada com sucesso.')
    configuracao = ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo=grupo_automatizado).first()
    assert configuracao, 'a UI disse que automatizou, mas a configuração não persistiu'
    assert configuracao.setores.filter(sigla=SIGLA_SETOR_SEM_SERVIDOR).exists(), 'a configuração gravou sem o setor escolhido'
    tela.ver_texto(SIGLA_SETOR_SEM_SERVIDOR)
    tela.ver_botao('Alterar')


def test_consultar_os_proprios_grupos(logado_efemero, conta_pessoal, grupo_gerenciado, capturar):
    """Tarefa 14 — *Meus grupos*: em que grupos você está, e como sair de um.

    Autosserviço de **todo** usuário, e por isso roda sobre a conta descartável: o passo que a
    doc afirma é o *Remover do grupo*, que só é afirmável se alguém de verdade sair de um grupo
    de verdade. ``conta_pessoal`` entra no grupo inerte por ORM (a entrada pela tela já é a
    tarefa 12) e sai por ele pela interface — e ``grupo_gerenciado`` zera o grupo no setup, de
    modo que uma execução interrompida não deixa a conta dentro dele.

    O login vem **depois** da entrada no grupo: o SUAP resolve grupo com cache por processo
    (``get_groups_cached``), e logar antes deixaria a sessão sem enxergar o grupo recém-dado.
    """
    from comum.models import UsuarioGrupo

    user = conta_pessoal.get_user()
    user.groups.add(grupo_gerenciado)
    vinculo = UsuarioGrupo.objects.get(user=user, group=grupo_gerenciado)

    pagina = logado_efemero('conta_pessoal')
    tela = Tela(pagina).ir(MINHA_CONTA)
    tela.clicar_link('Meus grupos')
    tela.esperar()
    assert f'/comum/grupos_usuario/{user.pk}/' in tela.pagina.url, f'o atalho "Meus grupos" não levou à lista de grupos: {tela.pagina.url}'
    tela.ver_texto(GRUPO_GERENCIADO)
    anotar('meus-grupos', tela)
    capturar(pagina, 'meus-grupos')

    # Pela LINHA do grupo, e não por `clicar_botao` cru: a tela lista um grupo por linha, cada
    # uma com o seu "Remover do grupo" — o botão solto pegaria o primeiro da tabela, que é o
    # grupo `Servidor`, e a conta perderia o vínculo de que todo o resto da suíte depende.
    tela.linha(GRUPO_GERENCIADO).clicar_botao('Remover do grupo')
    tela.sucesso(f'Usuário foi removido do grupo {grupo_gerenciado} com sucesso.')
    assert not UsuarioGrupo.objects.filter(pk=vinculo.pk).exists(), 'a UI disse que removeu, mas o vínculo continua no banco'
    # A saída devolve o usuário à Minha conta (`comum/views.py:2123`), e não à lista de grupos.
    assert MINHA_CONTA in tela.pagina.url, f'a saída do grupo não devolveu à Minha conta: {tela.pagina.url}'


def test_escolher_por_onde_receber_as_notificacoes(logado_comum, preferencia_notificacao, capturar):
    """Tarefa 15 — o interruptor por categoria: SUAP, e-mail, ou os dois.

    Autosserviço de todo usuário. A tela é uma listagem que **não grava nada**: cada botão
    redireciona para uma das seis rotas que ligam/desligam o canal e voltam para cá.

    O invariante é provocado de propósito, e é a única regra de negócio da tela: desligados os
    dois canais a categoria pararia de notificar em silêncio, então o SUAP recusa o segundo.
    Sem provocá-lo, a frase da doc seria leitura de ``comum/views.py``, não fato observado.
    """
    categoria, preferencia = preferencia_notificacao

    tela = Tela(logado_comum('solicitante')).ir(PREFERENCIAS)
    tela.ver_titulo('Preferências de Notificações')
    tela.ver_texto(CATEGORIA_NOTIFICACAO_DOC)
    anotar('preferencias-notificacao', tela)
    capturar(tela.pagina, 'preferencias-notificacao')

    # Pela LINHA da categoria do teste: a listagem traz também as categorias que o próprio SUAP
    # criou para esta conta (o alerta de dispositivo desconhecido nasce no primeiro login), e o
    # botão solto desligaria o canal de outra.
    tela.linha(CATEGORIA_NOTIFICACAO_DOC).clicar_botao('Desativar Envio via E-mail')
    tela.sucesso('Preferência atualizada com sucesso.')
    preferencia.refresh_from_db()
    assert not preferencia.via_email, 'a UI disse que atualizou, mas o envio por e-mail continua ligado'

    tela.linha(CATEGORIA_NOTIFICACAO_DOC).clicar_botao('Desativar Envio via SUAP')
    tela.erro('Não é possível inativar as duas formas de Notificação.')
    preferencia.refresh_from_db()
    assert preferencia.via_suap, 'o SUAP recusou pela mensagem, mas desligou o último canal da categoria'

    tela.linha(CATEGORIA_NOTIFICACAO_DOC).clicar_botao('Ativar Envio via E-mail')
    tela.sucesso('Preferência atualizada com sucesso.')
    preferencia.refresh_from_db()
    assert preferencia.via_email, 'a religação do canal de e-mail não foi gravada'
    assert categoria.ativa, 'a categoria do teste deixou de estar ativa'


def test_desligar_e_religar_uma_categoria_de_notificacao(logado_comum, preferencia_notificacao, capturar):
    """Tarefa 16 — o interruptor coletivo, um degrau acima da preferência de cada pessoa.

    ``CategoriaNotificacao.ativa`` desligada tira a categoria da tela de preferências de **todo
    mundo**, e o sintoma da quebra é o silêncio: ninguém recebe erro, as notificações
    simplesmente param. Os dois sentidos num teste só porque a tela troca o botão conforme o
    estado — a volta não existe antes da ida.

    Quem abre é ``gestor_ti`` (*Coordenador de TI sistêmico*), o único perfil padrão com
    ``comum.view_categorianotificacao``, e não o superusuário: o "Quem pode" da doc tem de ser
    reproduzível por alguém que não administra o SUAP inteiro.
    """
    from comum.models import CategoriaNotificacao

    categoria, _preferencia = preferencia_notificacao

    tela = Tela(logado_comum('gestor_ti')).ir(CATEGORIAS + f'?q={CATEGORIA_NOTIFICACAO_DOC}')
    tela.ver_titulo('Categorias de Notificações')
    tela.ver_texto(CATEGORIA_NOTIFICACAO_DOC)
    anotar('categorias-notificacao', tela)
    capturar(tela.pagina, 'categorias-notificacao')

    tela.linha(CATEGORIA_NOTIFICACAO_DOC).clicar_botao('Desativar')
    tela.sucesso('A Categoria de Notificações foi desativada com sucesso.')
    assert not CategoriaNotificacao.objects.get(pk=categoria.pk).ativa, 'a UI disse que desativou, mas a categoria continua ativa'

    tela.ir(CATEGORIAS + f'?q={CATEGORIA_NOTIFICACAO_DOC}')
    tela.linha(CATEGORIA_NOTIFICACAO_DOC).clicar_botao('Ativar')
    tela.sucesso('A Categoria de Notificações foi ativada com sucesso.')
    assert CategoriaNotificacao.objects.get(pk=categoria.pk).ativa, 'a UI disse que ativou, mas a categoria continua inativa'


def test_anunciar_uma_parada_programada(logado_comum, servidores_comum, manutencao_limpa, capturar):
    """Tarefa 17 — o aviso de indisponibilidade que todo usuário vê antes de a parada acontecer.

    Não é tabela de apoio, embora more no admin: o cadastro tem público-alvo, janela de
    divulgação e efeito visível para quem não o cadastrou — é a tela que enche o *Fique atento!*
    da página inicial (a leitura do aviso é da fatia 5). É também a única tela desta fatia cuja
    **consulta** é liberada aos quatro vínculos e cuja **inclusão** não é: as duas metades são
    afirmadas aqui, a segunda pela listagem que o cadastrante vê.
    """
    from comum.models import ManutencaoProgramada

    responsavel = servidores_comum['gestor_ti']
    pagina = logado_comum('gestor_ti')
    tela = Tela(pagina).ir(MANUTENCOES)
    tela.ver_titulo('Manutenções Programadas')
    anotar('manutencoes-listagem', tela)

    tela.clicar_botao('Adicionar Manutenção Programada')
    tela.esperar()
    anotar('manutencao-formulario', tela)
    tela.preencher_formulario(
        [
            ('Tipo', 'lista', 'Manutenção Preventiva'),
            ('Sistema ou servico', 'texto', SISTEMA_EM_MANUTENCAO_DOC),
            ('Data da atualização', 'data e hora', _momento(3, 22)),
            ('Previsão de minutos de inatividade', 'número', '90'),
            ('Motivo', 'textarea', MOTIVO_DA_MANUTENCAO_DOC),
            ('Data de início notificação', 'data e hora', _momento(0, 8)),
            # Obrigatório, e nada na tela avisa: `equipe_manutencao` é `ManyToManyFieldPlus` sem
            # `blank=True`, então o formulário recusa o cadastro sem pelo menos um vínculo. Medido
            # na primeira execução ("Este campo é obrigatório." depois de preencher todo o resto).
            ('Equipe de manutenção', 'autocomplete multiplo', responsavel.matricula),
        ]
    )
    capturar(pagina, 'manutencao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    manutencao = ManutencaoProgramada.objects.filter(sistema_ou_servico=SISTEMA_EM_MANUTENCAO_DOC).first()
    assert manutencao, 'a UI disse que cadastrou, mas a parada programada não persistiu'
    assert manutencao.previsao_minutos_inatividade == 90, 'a previsão de inatividade digitada não chegou ao banco'
    # Sem público escolhido, o aviso vale para todo mundo — é o que a doc promete ao leitor.
    assert not manutencao.publico, 'a parada nasceu restrita a um público, e o formulário foi preenchido sem escolher nenhum'
    assert manutencao in ManutencaoProgramada.proximas_atualizacoes(), 'a parada cadastrada não entrou na lista de próximas atualizações'

    # Pelo MOTIVO, e não pelo sistema: a listagem não tem coluna para `sistema_ou_servico` — ela
    # identifica cada parada por tipo, data e motivo (`ManutencaoProgramadaAdmin.get_list_display`),
    # e o nome do serviço só aparece na ficha e no aviso que o usuário final lê.
    tela.ir(MANUTENCOES)
    tela.ver_texto(MOTIVO_DA_MANUTENCAO_DOC)
    capturar(pagina, 'manutencoes-listagem')


def test_administrar_as_contas_de_usuario(logado_comum, conta_administravel, capturar):
    """Tarefa 18 — forçar a troca de senha e suspender uma conta, pela listagem de usuários.

    As duas ações são o que a tela oferece a quem cuida das contas, e as duas são reversíveis
    pela própria tela — a doc descreve os dois sentidos, então o teste percorre os dois. O alvo
    é o servidor descartável, que nunca loga: suspender conta compartilhada derrubaria as outras
    fatias, e ``conta_administravel`` repõe as três colunas no setup.

    A autorização destas ações **não** é permissão de model: cada uma checa o NOME do grupo
    (``in_group(user, 'Coordenador de TI de campus, Coordenador de TI sistêmico')``, que a
    vírgula transforma em "qualquer um dos dois"). Por isso o papel é ``gestor_ti`` e não um
    qualquer com ``comum.view_user``: só a listagem abriria.
    """
    from comum.models import User

    alvo = conta_administravel
    pagina = logado_comum('gestor_ti')

    tela = Tela(pagina).ir(USUARIOS + f'?q={alvo.matricula}')
    tela.ver_titulo('Usuários')
    tela.ver_texto(alvo.matricula)
    anotar('usuarios-listagem', tela)
    capturar(pagina, 'usuarios-listagem')

    tela.selecionar_item(alvo.matricula)
    tela.preencher('Ação', 'lista', 'Forçar troca de senha no próximo login')
    tela.clicar_acao('Aplicar')

    tela.sucesso('Procedimento realizado com sucesso.')
    assert User.objects.get(pk=alvo.get_user().pk).forcar_troca_senha, 'a UI disse que aplicou, mas a conta não ficou marcada para trocar a senha'

    tela.selecionar_item(alvo.matricula)
    tela.preencher('Ação', 'lista', 'Desabilitar usuário')
    tela.clicar_acao('Aplicar')

    tela.sucesso('Procedimento realizado com sucesso.')
    assert not User.objects.get(pk=alvo.get_user().pk).is_active, 'a UI disse que aplicou, mas a conta continuou ativa'

    tela.selecionar_item(alvo.matricula)
    tela.preencher('Ação', 'lista', 'Habilitar usuário')
    tela.clicar_acao('Aplicar')

    tela.sucesso('Procedimento realizado com sucesso.')
    assert User.objects.get(pk=alvo.get_user().pk).is_active, 'a reabilitação não foi gravada'

    tela.selecionar_item(alvo.matricula)
    tela.preencher('Ação', 'lista', 'Desfazer a troca de senha no próximo login')
    tela.clicar_acao('Aplicar')

    tela.sucesso('Procedimento realizado com sucesso.')
    assert not User.objects.get(pk=alvo.get_user().pk).forcar_troca_senha, 'a marcação de troca de senha não foi desfeita'


def test_ajustar_os_parametros_do_sistema(logado_comum, predio_descartavel, capturar):
    """Tarefa 19 — o painel de administração, os parâmetros por aplicação e a exclusão de registro.

    As três telas num teste só porque a primeira é a porta das outras duas: o painel é o índice
    das ferramentas de manutenção, e é de lá que se chega à configuração.

    A aplicação configurada é ``licenca_capacitacao`` por medição do e2e — um único campo, e o
    valor gravado é o default documentado. Gravar a configuração do próprio ``comum`` reescreveria
    de uma vez as 42 chaves de que as outras fatias dependem.

    A exclusão genérica fecha a tarefa porque é a porta de apagamento de dezenas de telas do
    SUAP, e a senha não é formalidade: é ela que separa esta tela de um link que apaga — a rota
    aceita os pks pela URL.
    """
    from comum.models import Configuracao, Predio

    pagina = logado_comum('admin')
    tela = Tela(pagina).ir(PAINEL)
    tela.ver_titulo('Administração do SUAP')
    tela.ver_texto('Usuários e grupos')
    anotar('painel-administracao', tela)
    capturar(pagina, 'painel-administracao')

    tela.clicar_link('Configurações SUAP')
    tela.esperar()
    assert CONFIGURACAO in tela.pagina.url, f'o painel não levou à configuração do sistema: {tela.pagina.url}'
    tela.ver_titulo('Configuração do Sistema')
    # A lista de abas É a lista de aplicações que declaram `ConfiguracaoForm`: a tela as importa
    # uma a uma, então ela só abre se nenhuma das ~90 aplicações estourar no import.
    tela.ver_texto(APP_CONFIGURAVEL)
    anotar('configuracao-sistema', tela)
    capturar(pagina, 'configuracao-sistema')

    tela.ir(CONFIGURACAO_DO_APP.format(app=APP_CONFIGURAVEL))
    anotar('configuracao-aplicacao', tela)
    tela.preencher(CAMPO_CONFIGURAVEL, 'lista', VALOR_CONFIGURAVEL)
    capturar(pagina, 'configuracao-aplicacao')
    tela.clicar_botao('Enviar')

    tela.sucesso('Configuração salva com sucesso.')
    assert Configuracao.objects.filter(app=APP_CONFIGURAVEL, chave='analise_permitida_desde', valor='fim_submissao').exists(), (
        'a UI disse que salvou, mas o parâmetro não persistiu'
    )

    tela.ir(EXCLUIR.format(app='comum', model='predio', pks=predio_descartavel.pk))
    tela.ver_titulo('Confirmação de Exclusão')
    tela.ver_texto(predio_descartavel.nome)
    anotar('confirmacao-exclusao', tela)
    tela.preencher('Senha para confirmação', 'senha', SENHA_E2E)
    capturar(pagina, 'confirmacao-exclusao')
    tela.clicar_botao('Excluir')

    tela.sucesso('Registro(s) excluído(s) com sucesso.')
    assert not Predio.objects.filter(pk=predio_descartavel.pk).exists(), 'a UI disse que excluiu, mas o registro continua no banco'


def test_o_substrato_de_grupos_continua_intacto_para_as_outras_fatias(servidores_comum):
    """Guarda da fatia: nada aqui mexeu nos grupos de que as outras cinco dependem.

    Não é tarefa nenhuma da doc — é a asserção de que os fluxos destrutivos ficaram dentro dos
    dois grupos inertes e das contas descartáveis. Roda por último no arquivo e afirma o efeito
    papel a papel: o grupo de ``PAPEIS`` que cada um precisa ter, a conta ativa e a ausência de
    marcação de troca de senha.

    **Sem pedir ``grupo_gerenciado``/``grupo_automatizado``**: essas fixtures zeram o grupo no
    setup, então requisitá-las aqui apagaria justamente o resíduo que se quer procurar.
    """
    from django.contrib.auth.models import Group

    from comum.tests.e2e.conftest import PAPEIS

    for apelido, (matricula, nome_grupo, _sigla) in PAPEIS.items():
        user = servidores_comum[apelido].get_user()
        assert user.is_active, f'{matricula} ({apelido}) ficou com a conta desabilitada'
        assert not user.forcar_troca_senha, f'{matricula} ({apelido}) ficou marcado para trocar a senha'
        if nome_grupo:
            assert user.groups.filter(name=nome_grupo).exists(), f'{matricula} ({apelido}) perdeu o grupo {nome_grupo}'

    # Cinto e suspensório: as fixtures dos dois grupos já zeram no setup E no teardown, então aqui
    # eles estarão vazios mesmo se um fluxo tiver falhado no meio. A asserção que de fato pega
    # resíduo é o laço acima — é a tarefa 18 que muta conta, e ela mexe num papel de `PAPEIS`.
    descartavel = PAPEIS['alvo_grupo'][0]
    for nome in (GRUPO_GERENCIADO, GRUPO_AUTOMATIZADO):
        sobraram = Group.objects.get(name=nome).user_set.exclude(username=descartavel).values_list('username', flat=True)
        assert not sobraram, f'o grupo inerte {nome} ficou com usuário que não o descartável: {list(sobraram)}'


def test_as_telas_de_apoio_desta_fatia_abrem(logado_comum):
    """As quatro telas que a doc cita no parágrafo *Telas de apoio* — abertas, não deduzidas.

    Tela de apoio não vira passo a passo, mas a frase que a doc escreve sobre ela ainda é uma
    afirmação: dizer que *Definir Gerenciamento de grupos* associa grupo gerenciador a grupos
    gerenciados é leitura de ``models.py`` se ninguém abriu a tela. Este teste abre as quatro,
    afirma o título e despeja as colunas — o que a redação copia.

    Não captura: o parágrafo de telas de apoio não leva imagem, e capturar quatro listagens
    vazias só encareceria a rodada.

    Pelo superusuário porque os quatro acessos são de perfis diferentes (``change_tipoarquivo`` é
    do *Coordenador de TI sistêmico*, ``change_apiexterna`` do *Coordenador de Sistemas* e
    ``view_oauthlogin`` não é de perfil padrão nenhum) — e o que se afirma aqui é que a tela
    existe e abre, não quem a alcança.
    """
    tela = Tela(logado_comum('admin'))

    for rota, titulo in (
        ('/admin/comum/tipoarquivo/', 'Tipos de arquivo'),
        # O título sai em minúsculas ("api externas") porque `APIExterna` não declara
        # `verbose_name`: o admin deriva do nome da classe. O menu publica "APIs Externas".
        ('/admin/comum/apiexterna/', 'api externas'),
        ('/admin/comum/oauthlogin/', 'Autenticações Oauth'),
        ('/admin/comum/gerenciamentogrupo/', 'Gerenciamento de Grupos'),
    ):
        tela.ir(rota)
        tela.ver_titulo(titulo)
        anotar(f'apoio{rota.rstrip("/").rsplit("/", 1)[-1]}', tela)
