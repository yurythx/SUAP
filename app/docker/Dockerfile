ARG BASE_IMAGE=gitlab.instituicao.edu.br:4567/cosinf/suap:base
FROM ${BASE_IMAGE} AS suap-app
ENV GUNICORN_WORKERS=2 \ 
    GUNICORN_THREADS=1 \
    GUNICORN_LOGFILE=deploy/logs/supervisor/gunicorn.log
ADD --chown=www-data:www-data . .
RUN cp suap/settings_sample.py suap/settings.py && \
    mkdir -p deploy/logs/history && \
    mkdir -p deploy/logs/email && \
    mkdir -p deploy/logs/supervisor && \
    mkdir -p deploy/logs/cron
USER root
RUN uv sync --locked --group prod --no-dev --no-install-project
USER www-data
RUN python manage.py collectstatic -c --no-input -v 0 && ./bin/clean_pyc.sh
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:8000 suap.wsgi:application -w $GUNICORN_WORKERS --threads $GUNICORN_THREADS -t 360 --max-requests 1000 --max-requests-jitter 30 2>&1 | tee -a $GUNICORN_LOGFILE"]

ARG BASE_IMAGE=gitlab.instituicao.edu.br:4567/cosinf/suap:base
FROM ${BASE_IMAGE} AS suap-dev
ENV PLAYWRIGHT_BROWSERS_PATH=/playwright-browsers
USER root
ADD --chown=www-data:www-data docker/dev/sources.list /etc/apt/sources.list.d/suap.list
RUN apt update && apt-get install -y zip wget && rm -rf /var/lib/apt/lists/* && rm -rf /var/cache/*

RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --all-groups

RUN playwright install chromium --with-deps && chmod -Rf 777 $PLAYWRIGHT_BROWSERS_PATH

USER www-data
CMD ["/bin/sh", "-c", "echo 'Starting dev container'; sleep infinity"]
