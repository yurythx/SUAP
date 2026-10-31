"""Seed do cenário de demonstração do POC "PGD x GitLab" (lançamento de RIT via GitLab).

Monta, de ponta a ponta e de forma reproduzível numa base nova, tudo o que a skill
``/pgd-rit`` precisa para funcionar:

- mapeia um ``username`` do GitLab a um ``rh.Servidor`` (via ``demandas.AnalistaDesenvolvedor``);
- monta a cadeia real PES + adesão + PIT do período corrente e **homologa** o PIT
  até ``situacao=HOMOLOGADO`` / ``situacao_rit=EM_CADASTRO_RIT``, com entregas
  homologadas ligadas a ``PlanoEntregasSetorialEntregas`` com ``descricao`` e
  ``criterios_avaliacao`` preenchidos (é o que a inferência da skill casa);
- opcionalmente cria uma ``api.AplicacaoOAuth2`` client-credentials e imprime as
  credenciais (o ``client_secret`` é capturado antes do save, pois é hasheado).

A sequência de homologação replica fielmente o caminho comprovado em
``pgd2/tests/models/test_workflow_pgd2.py`` (PitSetores + ``gerar_solicitacao...`` +
``homologar_pit``), usando os modelos/métodos reais — assim o gate
``pode_cadastrar_entrega_rit`` passa de verdade.

Uso típico::

    python manage.py seed_pgd2_gitlab_demo --matricula 1111111 --username-gitlab dev.poc --with-oauth-app
"""

from __future__ import annotations

import datetime
from argparse import ArgumentParser
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pgd2.models import (
    DocumentoAdesaoPesServidor,
    DocumentoAdesaoServidor,
    PeriodoPes,
    PeriodoPitRit,
    PitSetores,
    PitSolicitacaoAnalise,
    PlanoEntregasSetorial,
    PlanoEntregasSetorialEntregas,
    PlanoEntregasSetorialHorarioFuncionamentoSetor,
    PlanoEntregasSetorialHorarioPlanejamentoSetor,
    PlanoIndividualTrabalho,
    PlanoIndividualTrabalhoAtendimento,
    PlanoIndividualTrabalhoEntregas,
    SolicitacaoAdesaoPesServidor,
    SolicitacaoAdesaoServidor,
)
from rh.models import Servidor, Setor

# Entregas "casáveis" pela inferência da skill /pgd-rit: cada uma vira uma
# PlanoEntregasSetorialEntregas (PES) e uma PlanoIndividualTrabalhoEntregas (PIT).
ENTREGAS_DEMO: list[dict[str, str]] = [
    {
        'titulo': 'POC GitLab - Atendimento de erros e chamados',
        'descricao': 'Atendimento de erros e chamados reportados pelos usuários e via Sentry.',
        'criterios_avaliacao': 'Erros corrigidos e chamados encerrados dentro do prazo, com testes de regressão.',
    },
    {
        'titulo': 'POC GitLab - Desenvolvimento de sistemas',
        'descricao': 'Desenvolvimento de novas funcionalidades e melhorias nos sistemas institucionais.',
        'criterios_avaliacao': 'Funcionalidades entregues conforme especificação, com testes automatizados e MR aprovado.',
    },
    {
        'titulo': 'POC GitLab - Revisão de código',
        'descricao': 'Revisão de código (code review) dos merge requests da equipe.',
        'criterios_avaliacao': 'MRs revisados com feedback registrado, padrões de código e segurança verificados.',
    },
]


class Command(BaseCommand):
    help = 'Monta o cenário de demonstração do POC PGD x GitLab (lançamento de RIT via GitLab).'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('--username-gitlab', required=True, help='Username do autor do MR no GitLab (mapeado ao servidor).')
        parser.add_argument(
            '--matricula',
            help='Matrícula de um rh.Servidor existente a usar como dono do PIT/RIT. '
            'Caminho principal: reusar um servidor já existente na base (ex.: o seu).',
        )
        parser.add_argument(
            '--with-oauth-app', action='store_true', help='Também cria a api.AplicacaoOAuth2 (client-credentials) e imprime as credenciais.'
        )
        parser.add_argument('--oauth-owner', help='Username do dono da app OAuth2 (default: o user do servidor).')

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        username_gitlab: str = options['username_gitlab']
        matricula: str | None = options.get('matricula')
        with_oauth_app: bool = options['with_oauth_app']
        oauth_owner: str | None = options.get('oauth_owner')

        servidor = self._resolver_servidor(matricula)
        user = servidor.get_user()
        if user is None:
            raise CommandError(f'O servidor {servidor.matricula} não possui usuário associado (get_user retornou None).')

        self._garantir_analista_desenvolvedor(user, username_gitlab)

        pit, entregas_pit = self._montar_cadeia_homologada(servidor)

        oauth_info: dict[str, str] | None = None
        if with_oauth_app:
            oauth_info = self._criar_oauth_app(user, oauth_owner)

        self._imprimir_resumo(servidor, username_gitlab, pit, entregas_pit, oauth_info)

    # ------------------------------------------------------------------
    # Servidor + mapeamento GitLab
    # ------------------------------------------------------------------
    def _resolver_servidor(self, matricula: str | None) -> Servidor:
        if matricula:
            servidor = Servidor.objects.filter(matricula=matricula).first()
            if servidor is None:
                raise CommandError(f'Nenhum rh.Servidor encontrado com matricula={matricula!r}.')
            return servidor

        servidor = Servidor.objects.filter(ativo=True).order_by('matricula').first()
        if servidor is None:
            raise CommandError(
                'Nenhum rh.Servidor disponível na base. Informe --matricula de um servidor existente '
                '(criar um Servidor do zero é complexo e foge ao escopo deste seed).'
            )
        self.stdout.write(self.style.WARNING(f'--matricula não informada; usando o servidor existente {servidor.matricula} ({servidor}).'))
        return servidor

    def _garantir_analista_desenvolvedor(self, user: Any, username_gitlab: str) -> None:
        # Import local: evita acoplar pgd2 -> demandas no carregamento do app.
        from django.contrib.auth.models import Group

        from demandas.models import AnalistaDesenvolvedor

        # AnalistaDesenvolvedor.save() exige o grupo 'Analista'; garante a existência numa base nova.
        Group.objects.get_or_create(name='Analista')

        dev, criado = AnalistaDesenvolvedor.objects.get_or_create(
            usuario=user,
            defaults={'username_gitlab': username_gitlab, 'ativo': True},
        )
        if not criado and (dev.username_gitlab != username_gitlab or not dev.ativo):
            dev.username_gitlab = username_gitlab
            dev.ativo = True
            dev.save()
            self.stdout.write(self.style.SUCCESS(f'AnalistaDesenvolvedor atualizado: username_gitlab={username_gitlab!r}.'))
        else:
            acao = 'criado' if criado else 'já existente (mantido)'
            self.stdout.write(self.style.SUCCESS(f'AnalistaDesenvolvedor {acao}: username_gitlab={username_gitlab!r}.'))

    # ------------------------------------------------------------------
    # Cadeia PES + adesão + PIT homologado (EM_CADASTRO_RIT)
    # ------------------------------------------------------------------
    def _montar_cadeia_homologada(self, servidor: Servidor) -> tuple[PlanoIndividualTrabalho, list[PlanoIndividualTrabalhoEntregas]]:
        hoje = datetime.date.today()
        inicio = hoje.replace(day=1)
        fim = inicio + datetime.timedelta(days=29)
        setor = servidor.setor

        # Já existe um PIT seedado homologado e editável para este servidor? Reusa (idempotência).
        pit_existente = (
            PlanoIndividualTrabalho.objects.filter(
                adesao__servidor=servidor,
                situacao_rit=PlanoIndividualTrabalho.EM_CADASTRO_RIT,
                periodo_pit_rit__titulo='POC GitLab - PIT/RIT',
            )
            .order_by('-id')
            .first()
        )
        if pit_existente is not None:
            entregas = list(pit_existente.get_entregas_pit_para_rit())
            self.stdout.write(self.style.WARNING(f'PIT já seedado encontrado (id={pit_existente.id}); reusando.'))
            return pit_existente, entregas

        # Documentos e configurações de adesão (idempotentes por descrição distintiva).
        documento_pgd, _ = DocumentoAdesaoServidor.objects.get_or_create(
            descricao='POC GitLab - Regras de adesão ao PGD', defaults={'data_inicio': inicio}
        )
        documento_pes, _ = DocumentoAdesaoPesServidor.objects.get_or_create(
            descricao='POC GitLab - Regras de adesão ao PES', defaults={'data_inicio': inicio}
        )

        # Períodos PES e PIT/RIT do mês corrente.
        periodo_pes, _ = PeriodoPes.objects.get_or_create(
            titulo='POC GitLab - PES',
            defaults={
                'data_inicio': inicio,
                'data_fim': fim,
                'data_prazo_solicitar_avaliacao_execucao': fim,
            },
        )
        periodo_pit_rit, _ = PeriodoPitRit.objects.get_or_create(
            titulo='POC GitLab - PIT/RIT',
            defaults={
                'periodo_pes': periodo_pes,
                'data_inicio': inicio,
                'data_fim': fim,
                'data_prazo_entrega_pit': fim,
                'data_prazo_entrega_rit': fim,
                'data_prazo_homologacao_pit': fim,
                'data_prazo_homologacao_rit': fim,
            },
        )

        # PES do setor, já aprovado, com horários e entregas planejadas.
        pes = PlanoEntregasSetorial.objects.create(
            periodo_pes=periodo_pes,
            setor=setor,
            doc_insfraestrutura='Estrutura suficiente para teletrabalho.',
            doc_tecnica='Ferramentas digitais institucionais.',
            situacao=PlanoEntregasSetorial.APROVADO,
        )
        PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.create(
            pes=pes, data=inicio, hora_inicio=datetime.time(8), hora_final=datetime.time(17)
        )
        PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.create(
            pes=pes,
            data=inicio,
            hora_inicio=datetime.time(9),
            hora_final=datetime.time(10),
            reuniao=PlanoEntregasSetorialHorarioPlanejamentoSetor.REUNIAO_ONLINE,
        )
        entregas_pes = [
            PlanoEntregasSetorialEntregas.objects.create(
                pes=pes,
                titulo=dados['titulo'],
                descricao=dados['descricao'],
                criterios_avaliacao=dados['criterios_avaliacao'],
                metrica=PlanoEntregasSetorialEntregas.PERCENTUAL,
                meta=100,
                data_prazo=fim,
            )
            for dados in ENTREGAS_DEMO
        ]

        # Adesões deferidas (PGD + PES).
        adesao_pgd = SolicitacaoAdesaoServidor.objects.create(
            servidor=servidor,
            documento_adesao=documento_pgd,
            situacao=SolicitacaoAdesaoServidor.DEFERIDO,
            data_inicio=inicio,
        )
        SolicitacaoAdesaoPesServidor.objects.create(
            adesao=adesao_pgd,
            setor=setor,
            documento_adesao=documento_pes,
            situacao=SolicitacaoAdesaoPesServidor.DEFERIDO,
        )

        # PIT em cadastro, setor envolvido (pode_homologar), atendimento e entregas.
        pit = PlanoIndividualTrabalho.objects.create(
            adesao=adesao_pgd,
            periodo_pit_rit=periodo_pit_rit,
            data_inicio=inicio,
            data_fim=fim,
            regime_execucacao=PlanoIndividualTrabalho.TRABALHO_TELETRABALHO_INTEGRAL,
            percentual_teletrabalho=100,
            situacao=PlanoIndividualTrabalho.EM_CADASTRO,
        )
        PitSetores.objects.create(pit=pit, pes=pes, setor=setor, pode_homologar=True)
        PlanoIndividualTrabalhoAtendimento.objects.create(pit=pit, data=inicio, hora_inicio=datetime.time(10), hora_final=datetime.time(11))
        entregas_pit = [
            PlanoIndividualTrabalhoEntregas.objects.create(
                pit=pit,
                entrega_pes=entrega_pes,
                titulo=f'Executar: {entrega_pes.titulo}',
                descricao=f'Trabalho planejado para "{entrega_pes.titulo}".',
                tempo_planejado=Decimal('8'),
                data_prazo=fim,
            )
            for entrega_pes in entregas_pes
        ]

        # Solicita e homologa o PIT pelo chefe -> situacao_rit = EM_CADASTRO_RIT, entregas homologadas.
        chefe = self._resolver_chefe(servidor)
        pit.gerar_solicitacao_aprovacao_homologacao_pit_rit(PitSolicitacaoAnalise.PIT)
        pit.homologar_pit(Setor.objects.filter(pk=setor.pk), chefe)
        pit.refresh_from_db()

        if pit.situacao != PlanoIndividualTrabalho.HOMOLOGADO or pit.situacao_rit != PlanoIndividualTrabalho.EM_CADASTRO_RIT:
            raise CommandError(
                f'Falha ao homologar o PIT (situacao={pit.situacao}, situacao_rit={pit.situacao_rit}). O cenário não ficaria lançável.'
            )

        for entrega_pit in entregas_pit:
            entrega_pit.refresh_from_db()

        self.stdout.write(self.style.SUCCESS(f'PIT {pit.id} homologado (situacao_rit=EM_CADASTRO_RIT) com {len(entregas_pit)} entrega(s).'))
        return pit, entregas_pit

    def _resolver_chefe(self, servidor: Servidor) -> Servidor:
        # Quem dá o parecer de homologação. O método homologar_pit apenas registra o
        # autor do parecer; não depende de o chefe ser realmente chefia do setor.
        chefe = Servidor.objects.exclude(pk=servidor.pk).order_by('matricula').first()
        return chefe or servidor

    # ------------------------------------------------------------------
    # App OAuth2 (opcional)
    # ------------------------------------------------------------------
    def _criar_oauth_app(self, user_servidor: Any, oauth_owner: str | None) -> dict[str, str]:
        from django.contrib.auth.models import User

        from api.models import AplicacaoOAuth2

        owner = user_servidor
        if oauth_owner:
            owner = User.objects.filter(username=oauth_owner).first()
            if owner is None:
                raise CommandError(f'Nenhum usuário com username={oauth_owner!r} para ser dono da app OAuth2.')

        app = AplicacaoOAuth2.full.filter(name='POC GitLab - pgd-rit').first()
        if app is not None:
            self.stdout.write(self.style.WARNING(f'App OAuth2 já existe (client_id={app.client_id}); client_secret não é recuperável (hasheado).'))
            return {'client_id': app.client_id, 'client_secret': '<existente - não recuperável (hasheado)>'}

        # client_id/client_secret são gerados no __init__ via defaults dos campos.
        # Captura o client_secret em texto puro ANTES do save (ele é hasheado no save).
        app = AplicacaoOAuth2(
            name='POC GitLab - pgd-rit',
            user=owner,
            client_type=AplicacaoOAuth2.CLIENT_CONFIDENTIAL,
            authorization_grant_type=AplicacaoOAuth2.GRANT_CLIENT_CREDENTIALS,
            skip_authorization=True,
        )
        client_id = app.client_id
        client_secret = app.client_secret
        app.save()

        self.stdout.write(self.style.SUCCESS(f'App OAuth2 criada (client_id={client_id}).'))
        return {'client_id': client_id, 'client_secret': client_secret}

    # ------------------------------------------------------------------
    # Resumo final
    # ------------------------------------------------------------------
    def _imprimir_resumo(
        self,
        servidor: Servidor,
        username_gitlab: str,
        pit: PlanoIndividualTrabalho,
        entregas_pit: list[PlanoIndividualTrabalhoEntregas],
        oauth_info: dict[str, str] | None,
    ) -> None:
        w = self.stdout.write
        w('')
        w(self.style.SUCCESS('=' * 70))
        w(self.style.SUCCESS('RESUMO - Cenário de demo PGD x GitLab pronto'))
        w(self.style.SUCCESS('=' * 70))
        w(f'Servidor:        {servidor} (matrícula {servidor.matricula})')
        w(f'Username GitLab: {username_gitlab}')
        w(f'PIT:             id={pit.id} | período={pit.periodo_pit_rit.titulo} ({pit.data_inicio} a {pit.data_fim})')
        w('Entregas disponíveis para RIT:')
        for entrega in entregas_pit:
            w(f'  - [{entrega.id}] {entrega.titulo}')

        if oauth_info:
            ctx = 'poc'
            w('')
            w(self.style.SUCCESS('Credenciais OAuth2 (client-credentials):'))
            w(f'  client_id:     {oauth_info["client_id"]}')
            w(f'  client_secret: {oauth_info["client_secret"]}')
            w('')
            w(self.style.SUCCESS('Trecho para contexts.yaml:'))
            w(f'  {ctx}:')
            w('    suap_base_url: http://localhost:8000')
            w(f'    suap_client_id: {oauth_info["client_id"]}')
            w(f'    gitlab_username: {username_gitlab}')
            w('')
            w(self.style.SUCCESS('Export do client secret:'))
            w(f'  export CODING_AGENTS_SUAP_{ctx.upper()}={oauth_info["client_secret"]}')
        w(self.style.SUCCESS('=' * 70))
