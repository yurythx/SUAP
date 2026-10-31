import datetime
import sys

import feedparser
import tqdm
from django.conf import settings
from sentry_sdk import capture_exception

from clipping.models import Editorial, Fonte, PublicacaoDigital, Veiculo
from djtools.utils import requests


def download(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'}
    response = requests.get(url, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
    if response.status_code != 200:
        raise Exception(f'Failed to download RSS feed from {url}')
    return response.text


def read(url):
    from dateutil.parser import parse

    rss_links = []
    content = download(url)
    feed = feedparser.parse(content)
    channel = feed.get('channel', {})
    if channel:
        pubdate = parse(
            channel.get('updated', '') or channel.get('lastBuildDate', '') or channel.get('last_build_date', '') or datetime.date.today().isoformat()
        )
        title = channel.get('title', '')
        link = channel.get('link', '')
        description = channel.get('content', '') or channel.get('description', '') or channel.get('summary', '')
        rss_links.append({'title': title, 'pubdate': pubdate, 'link': link, 'description': description})
    if feed.get('entries', []):
        for entry in feed.entries:
            title = entry.get('title', '')
            link = entry.get('link', '')
            description = channel.get('content', '') or channel.get('description', '') or channel.get('summary', '')
            pubdate = parse(entry.get('published', '') or entry.get('updated', '') or datetime.date.today().isoformat())
            rss_links.append({'title': title, 'pubdate': pubdate, 'link': link, 'description': description})

    return rss_links


def importar_tudo(verbosity=3, task=None):
    count = 0
    qs = Fonte.objects.filter(ativo=True)
    if verbosity:
        fontes = tqdm.tqdm(qs)
    else:
        fontes = qs
    if task:
        fontes = task.iterate(qs)
    for fonte in fontes:
        try:
            itens = read(fonte.link)
            for item in itens:
                publicacao = PublicacaoDigital()
                publicacao.data = item['pubdate']
                publicacao.titulo = item['title'].strip()
                publicacao.texto = item['description']
                publicacao.link = item['link']
                publicacao.subtitulo = ''
                publicacao.veiculo = Veiculo.objects.get_or_create(nome=fonte.nome)[0]
                publicacao.editorial = Editorial.objects.get_or_create(nome=fonte.editorial)[0]
                if not PublicacaoDigital.objects.filter(titulo=publicacao.titulo, veiculo__nome=fonte.nome).exists():
                    palavras_chaves = publicacao.get_palavras_chaves()
                    if palavras_chaves:
                        publicacao.save()
                        publicacao.palavras_chaves.set(palavras_chaves)
                        publicacao.save()
                        count += 1
                        # print '[OK]'
                        # print publicacao.titulo
                        # print publicacao.texto
                        # print '\n\n\n\n'
        except Exception as e:
            import traceback

            capture_exception(e)

            if verbosity:
                sys.stderr.write(f'Link com problemas: {fonte.link}')
                traceback.print_exc()
    return count
