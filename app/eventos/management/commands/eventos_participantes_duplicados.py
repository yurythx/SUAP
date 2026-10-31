from django.db import transaction
from django.db.models import Count

from djtools.management.commands import BaseCommandPlus
from eventos.models import AutorSubmissao, Evento, Participante

"""
python manage.py eventos_participantes_duplicados 8042,8048,7556 --corrigir
python manage.py eventos_participantes_duplicados 8042
"""


class Command(BaseCommandPlus):
    help = 'Verifica e corrige participantes duplicados em um ou mais eventos'

    def add_arguments(self, parser):
        parser.add_argument(
            'evento_ids',
            type=str,
            help='ID(s) do(s) evento(s) para verificar (separados por vírgula)',
        )
        parser.add_argument(
            '--corrigir',
            action='store_true',
            help='Remove duplicatas mantendo apenas o primeiro registro e migrando vínculos',
        )

    def handle(self, *args, **options):
        evento_ids_str = options['evento_ids']
        corrigir = options.get('corrigir', False)

        # Converte a string de IDs em lista de inteiros
        try:
            evento_ids = [int(id.strip()) for id in evento_ids_str.split(',')]
        except ValueError:
            self.stdout.write(self.style.ERROR('IDs de eventos inválidos. Use números separados por vírgula.'))
            return

        # Busca os eventos
        eventos = Evento.objects.filter(id__in=evento_ids)
        eventos_encontrados = {e.id: e for e in eventos}

        # Verifica se todos os eventos existem
        eventos_nao_encontrados = set(evento_ids) - set(eventos_encontrados.keys())
        if eventos_nao_encontrados:
            self.stdout.write(self.style.WARNING(f'Eventos não encontrados: {sorted(eventos_nao_encontrados)}'))

        if not eventos_encontrados:
            self.stdout.write(self.style.ERROR('Nenhum evento válido encontrado.'))
            return

        self.stdout.write(f'\n{"=" * 80}')
        self.stdout.write(f'Verificando {len(eventos_encontrados)} evento(s)')
        self.stdout.write(f'{"=" * 80}\n')

        total_geral_removidos = 0
        total_geral_submissoes_migradas = 0
        resumo_eventos = []

        for evento_id in evento_ids:
            if evento_id not in eventos_encontrados:
                continue

            evento = eventos_encontrados[evento_id]
            self.stdout.write(f'\n{"#" * 80}')
            self.stdout.write(f'EVENTO: {evento.nome} (ID: {evento_id})')
            self.stdout.write(f'{"#" * 80}')

            # Busca duplicatas de forma otimizada
            duplicatas = (
                Participante.objects.filter(evento=evento)
                .values('tipo', 'email', 'cpf')
                .annotate(total=Count('id'))
                .filter(total__gt=1)
                .order_by('tipo', 'email')
            )

            if not duplicatas:
                self.stdout.write(self.style.SUCCESS('✓ Nenhuma duplicata encontrada!\n'))
                resumo_eventos.append({'evento': evento.nome, 'id': evento_id, 'duplicatas': 0, 'removidos': 0})
                continue

            self.stdout.write(self.style.WARNING(f'\nEncontradas {duplicatas.count()} grupos de duplicatas:\n'))

            total_removidos = 0
            total_submissoes_migradas = 0

            for dup in duplicatas:
                # Busca os participantes duplicados ordenados por ID (mantém o mais antigo)
                participantes = list(
                    Participante.objects.filter(evento=evento, tipo_id=dup['tipo'], email=dup['email'], cpf=dup['cpf'])
                    .order_by('id')
                    .select_related('tipo__tipo_participacao')
                )

                primeiro = participantes[0]
                duplicados = participantes[1:]

                tipo_desc = primeiro.tipo.tipo_participacao.descricao if primeiro.tipo else 'Sem tipo'

                self.stdout.write(f'\n{"-" * 80}')
                self.stdout.write(f'Tipo: {tipo_desc}')
                self.stdout.write(f'Nome: {primeiro.nome}')
                self.stdout.write(f'Email: {dup["email"]}')
                self.stdout.write(f'CPF: {dup["cpf"]}')
                self.stdout.write(f'Total de registros: {dup["total"]}')
                self.stdout.write(f'ID mantido: {primeiro.pk}')
                self.stdout.write(f'IDs que serão removidos: {[p.pk for p in duplicados]}')

                if corrigir:
                    with transaction.atomic():
                        submissoes_migradas = 0

                        # Migra as submissões dos participantes duplicados para o primeiro
                        for participante_dup in duplicados:
                            # Busca todas as submissões vinculadas ao participante duplicado
                            autores_submissao = AutorSubmissao.objects.filter(participante=participante_dup)

                            for autor in autores_submissao:
                                # Verifica se já existe vínculo com o primeiro participante
                                existe = AutorSubmissao.objects.filter(submissao=autor.submissao, participante=primeiro).exists()

                                if not existe:
                                    # Migra o vínculo para o primeiro participante
                                    autor.participante = primeiro
                                    autor.save()
                                    submissoes_migradas += 1
                                    self.stdout.write(
                                        f'  → Migrada submissão "{autor.submissao.titulo}" de participante {participante_dup.pk} para {primeiro.pk}'
                                    )
                                else:
                                    # Se já existe, apenas remove o vínculo duplicado
                                    self.stdout.write(
                                        f'  ⚠ Submissão "{autor.submissao.titulo}" já vinculada ao participante {primeiro.pk}, '
                                        f'removendo vínculo duplicado'
                                    )
                                    autor.delete()

                        # Remove os participantes duplicados
                        qtd_removidos = len(duplicados)
                        for p in duplicados:
                            p.delete()

                        total_removidos += qtd_removidos
                        total_submissoes_migradas += submissoes_migradas

                        self.stdout.write(
                            self.style.SUCCESS(f'  ✓ Removidos {qtd_removidos} registro(s), migradas {submissoes_migradas} submissão(ões)')
                        )

            # Adiciona ao resumo do evento
            total_geral_removidos += total_removidos
            total_geral_submissoes_migradas += total_submissoes_migradas
            resumo_eventos.append(
                {
                    'evento': evento.nome,
                    'id': evento_id,
                    'duplicatas': duplicatas.count(),
                    'removidos': total_removidos,
                    'submissoes': total_submissoes_migradas,
                }
            )

        # Exibe resumo geral
        self.stdout.write(f'\n{"=" * 80}')
        self.stdout.write('RESUMO GERAL')
        self.stdout.write(f'{"=" * 80}\n')

        for resumo in resumo_eventos:
            self.stdout.write(f'\nEvento: {resumo["evento"]} (ID: {resumo["id"]})')
            self.stdout.write(f'  • Grupos de duplicatas: {resumo["duplicatas"]}')
            if corrigir:
                self.stdout.write(f'  • Registros removidos: {resumo["removidos"]}')
                self.stdout.write(f'  • Submissões migradas: {resumo["submissoes"]}')

        self.stdout.write(f'\n{"-" * 80}')
        if corrigir:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ TOTAL GERAL:\n'
                    f'  • Registros duplicados removidos: {total_geral_removidos}\n'
                    f'  • Submissões migradas: {total_geral_submissoes_migradas}'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠ MODO SOMENTE LEITURA\n'
                    'Para remover as duplicatas e migrar os vínculos, execute:\n'
                    f'python manage.py eventos_participantes_duplicados {evento_ids_str} --corrigir'
                )
            )
        self.stdout.write(f'{"=" * 80}\n')
