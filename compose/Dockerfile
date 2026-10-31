# syntax=docker/dockerfile:1.7
# Contexto de build: diretório pai de compose/ (ex.: /opt/suap)
# Contém app/ (fonte oficial) e compose/ (este Dockerfile + overlay).

############################
# Stage: base
############################
FROM ghcr.io/astral-sh/uv:python3.14-trixie AS base

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=pt_BR.UTF-8 \
    LANGUAGE=pt_BR:pt \
    LC_ALL=pt_BR.UTF-8 \
    TZ=America/Sao_Paulo \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.14 \
    UV_PROJECT_ENVIRONMENT=/venv

RUN mkdir -p /var/www \
    && usermod -u 33 -d /var/www www-data \
    && groupmod -g 33 www-data \
    && chown -R www-data:www-data /var/www

RUN set -eux; \
    apt-get update -qy; \
    apt-get install -qyy --no-install-recommends \
      locales git build-essential openssl curl qpdf \
      libldap2-dev libsasl2-dev \
      libjpeg-dev libfreetype6-dev zlib1g-dev \
      freetds-dev \
      libxmlsec1-dev libxml2-dev libxslt1-dev \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
      libmagic1 \
      gettext \
      ca-certificates; \
    echo "pt_BR.UTF-8 UTF-8" >> /etc/locale.gen; \
    locale-gen pt_BR.UTF-8; \
    rm -rf /var/lib/apt/lists/* /var/cache/*

WORKDIR /opt/suap

COPY app/pyproject.toml app/uv.lock ./
RUN --mount=type=cache,target=/root/.cache \
    uv sync --locked --group prod --no-dev --no-install-project

ENV PATH="/venv/bin:$PATH"
RUN python -m nltk.downloader -d /usr/local/share/nltk_data punkt_tab punkt stopwords || true

############################
# Stage: produção
############################
FROM base AS suap-app

ENV GUNICORN_WORKERS=6 \
    GUNICORN_THREADS=2 \
    GUNICORN_TIMEOUT=120 \
    DJANGO_SETTINGS_MODULE=suap.settings \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER root
COPY --chown=www-data:www-data app/ /opt/suap/
COPY --chown=www-data:www-data compose/compose-overlay/settings.py /opt/suap/suap/settings.py
COPY --chown=www-data:www-data compose/compose-overlay/entrypoint.sh /entrypoint.sh
COPY --chown=www-data:www-data compose/compose-overlay/migrate_empty.py /migrate_empty.py

RUN chmod +x /entrypoint.sh /migrate_empty.py \
    && mkdir -p \
      deploy/logs/history \
      deploy/logs/email \
      deploy/logs/supervisor \
      deploy/logs/cron \
      deploy/media/public-media \
      deploy/media/private-media \
      deploy/media/tmp \
      static \
    && chown -R www-data:www-data /opt/suap /entrypoint.sh

USER www-data
WORKDIR /opt/suap

RUN uv sync --locked --group prod --no-dev --no-install-project \
    && python manage.py collectstatic -c --no-input -v 0 || true

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn"]
