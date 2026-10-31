from django.core.management.base import BaseCommand
from django.db import transaction
from bs4 import BeautifulSoup
from ppc.models import SecaoPlanoDisciplina, PlanoDisciplina, PlanoDisciplinaPPC, ProjetoPedagogicoCurso
from ppc.utils import processar_bibliografia


class Command(BaseCommand):
    help = 'Refactor malformed HTML in a model field using BeautifulSoup.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Dry run mode, no changes to DB')

    def clean_html(self, html):
        if not html:
            return ''
        soup = BeautifulSoup(html, 'html.parser')
        richtext_div = soup.select_one('div.richtext')
        if richtext_div:
            container = richtext_div
        else:
            container = soup.body or soup
        # Convert lists to paragraphs (deepest first)
        lists = container.find_all(['ul', 'ol'])[::-1]
        if lists:
            for list_tag in lists:
                lis = list(list_tag.find_all('li', recursive=False))
                for li in lis:
                    p = soup.new_tag('p')
                    while li.contents:
                        p.append(li.contents[0].extract())
                    list_tag.insert_before(p)
                list_tag.extract()
            self.wrap_loose_elements_in_p(container, soup)
            # Return inner contents
        return container.decode_contents().strip()

    def wrap_loose_elements_in_p(self, container, soup):
        BLOCK_TAGS = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'figure', 'figcaption', 'table', 'hr'}
        children = [child.extract() for child in list(container.children)]
        i = 0
        while i < len(children):
            child = children[i]
            if child.name and child.name in BLOCK_TAGS:
                container.append(child)
                i += 1
                continue
            p = soup.new_tag('p')
            while i < len(children):
                child = children[i]
                if child.name and child.name in BLOCK_TAGS:
                    break
                p.append(child)
                i += 1
            container.append(p)

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        qs = SecaoPlanoDisciplina.objects.filter(
            modelo_secao_plano_disciplina__titulo__in=['Bibliografia Básica', 'Bibliografia Complementar'],
            plano_disciplina__situacao=PlanoDisciplina.APROVADO,
        )

        total_count = qs.count()
        self.stdout.write(f'Total objects to process: {total_count}')

        processed = 0
        changed = 0

        msg = self.style.WARNING('DRY-RUN MODE - No changes will be made.') if dry_run else 'Processing with updates...'
        self.stdout.write(msg)
        objects_to_update = []
        ppcs_reprocessar = set()
        for obj in qs.iterator():
            try:
                original = obj.texto
                if original is None or original.strip() == '':
                    continue
                cleaned = self.clean_html(original)
                if cleaned != original:
                    if dry_run:
                        self.stdout.write(self.style.WARNING(f"#{obj.plano_disciplina_id}: '{original}' -> '{cleaned}'"))
                    else:
                        obj.texto = cleaned
                        objects_to_update.append(obj)
                    changed += 1
                    ids = set(
                        PlanoDisciplinaPPC.objects.filter(plano_disciplina_id=obj.plano_disciplina_id).values_list('matriz_ppc__ppc_id', flat=True)
                    )
                    ppcs_reprocessar.update(ids)
                processed += 1
                if processed % 100 == 0:
                    self.stdout.write(f'Processed: {processed}/{total_count}')

            except Exception as e:
                self.stderr.write(f'Error processing {obj.id}: {e}')

        if objects_to_update:
            with transaction.atomic():
                SecaoPlanoDisciplina.objects.bulk_update(objects_to_update, ['texto'])
            self.stdout.write(self.style.SUCCESS(f'Final bulk update: {len(objects_to_update)} objects'))

            ppcs_to_update = []
            for id in ppcs_reprocessar:
                ppc = ProjetoPedagogicoCurso.objects.get(id=id)
                ppc.bibliografia_html = processar_bibliografia(ppc)
                ppcs_to_update.append(ppc)
                self.stdout.write(self.style.SUCCESS(f'Updating PPC {id} due to changes in related PlanoDisciplina'))
            if ppcs_to_update:
                with transaction.atomic():
                    ProjetoPedagogicoCurso.objects.bulk_update(ppcs_to_update, ['bibliografia_html'])

        self.stdout.write(self.style.SUCCESS(f'Completed. Processed: {processed}, Changed: {changed}, PPCs reprocessed: {len(ppcs_reprocessar)}'))
