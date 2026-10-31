"""Seed do módulo Eventos: a nomenclatura que o behave carregava em ``features/steps/given.py``.

A suíte do módulo não tem mais ``features/`` (modo 2, unidade de cobertura = rota). A função
abaixo é o corpo do antigo step ``os dados básicos para eventos``, sem o decorador e sem o
``context`` que ela ignorava. É idempotente (``get_or_create``), requisito do banco
compartilhado entre os módulos e do ``--reuse-db`` do CI.
"""

from __future__ import annotations


def dados_basicos_eventos() -> None:
    """Cadastra dimensões, tipos, classificações, públicos, naturezas e participações."""
    from django.contrib.auth.models import Group

    from eventos.models import (
        ClassificacaoEvento,
        Dimensao,
        Espacialidade,
        Natureza,
        PorteEvento,
        PublicoAlvoEvento,
        SubtipoEvento,
        TipoEvento,
        TipoParticipacao,
    )

    registro = Dimensao.objects.get_or_create(descricao=' Ensino')[0]
    Dimensao.objects.get_or_create(descricao='Pesquisa')[0]
    Dimensao.objects.get_or_create(descricao='Extensão')[0]
    Dimensao.objects.get_or_create(descricao=' Recursos Humanos')[0]
    Dimensao.objects.get_or_create(descricao='Gestão')[0]
    grupo = Group.objects.get(name='Secretário Acadêmico')
    registro.grupos_avaliadores_locais.add(grupo)

    tipo = TipoEvento.objects.get_or_create(descricao='Científico/tecnológico')[0]
    SubtipoEvento.get_or_create(tipo=tipo, nome='Palestras', detalhamento='...')[0]

    ClassificacaoEvento.objects.get_or_create(descricao='Local')[0]
    ClassificacaoEvento.objects.get_or_create(descricao='Regional')[0]

    PublicoAlvoEvento.objects.get_or_create(descricao='Aluno')[0]
    PublicoAlvoEvento.objects.get_or_create(descricao='Servidor')[0]
    PublicoAlvoEvento.objects.get_or_create(descricao='Pai ou Responsável')[0]
    PublicoAlvoEvento.objects.get_or_create(descricao='Público Externo')[0]
    PublicoAlvoEvento.objects.get_or_create(descricao='Empresário')[0]
    PublicoAlvoEvento.objects.get_or_create(descricao='Gestor')[0]
    PublicoAlvoEvento.objects.get_or_create(descricao='Prestador de Serviço')[0]
    PublicoAlvoEvento.objects.get_or_create(descricao='Estagiário')[0]
    PublicoAlvoEvento.objects.get_or_create(descricao='Bolsista')[0]

    Natureza.objects.get_or_create(descricao='Certificação')[0]
    Natureza.objects.get_or_create(descricao='Formatura')[0]
    Natureza.objects.get_or_create(descricao='Posse')[0]
    Natureza.objects.get_or_create(descricao='Congresso')[0]
    Natureza.objects.get_or_create(descricao='Seminário')[0]
    Natureza.objects.get_or_create(descricao='Oficina')[0]
    Natureza.objects.get_or_create(descricao='Encontro')[0]

    TipoParticipacao.objects.get_or_create(descricao='Participante')[0]
    TipoParticipacao.objects.get_or_create(descricao='Palestrante')[0]
    TipoParticipacao.objects.get_or_create(descricao='Convidado')[0]
    TipoParticipacao.objects.get_or_create(descricao='Organizador')[0]

    Espacialidade.objects.get_or_create(descricao='Ambiente Virtual')[0]
    PorteEvento.objects.get_or_create(descricao='Pequeno Porte')[0]
