# check=skip=InvalidDefaultArgInFrom
ARG base_image
FROM ${base_image} AS suap-base
USER root
RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --all-groups && \
    chmod -R a+rwX /venv

FROM suap-base AS suap-dev
RUN apt-get update; apt-get install -y wget unzip curl zip 
RUN pip install supervisor
RUN printf \[supervisord\]\\nnodaemon=true\\n\[supervisorctl\]\\nserverurl=http://127.0.0.1:9001\\n\[inet_http_server\]\\nport=127.0.0.1:9001\\n\[rpcinterface:supervisor\]\\nsupervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface\\n\[program:suap\]\\ncommand=gunicorn\ -b\ 0.0.0.0:80\ suap.wsgi:application\ -w\ 2\ -t\ 360\\ndirectory=/suap\\nuser=root\\nautostart=true\\nautorestart=true\\nstopasgroup=true\\nkillasgroup=true\\n > /etc/supervisord.conf

CMD ["bash", "-c", "supervisord -s -c /etc/supervisord.conf -l /etc/supervisord.log"]

FROM suap-base AS suap-test
ENV PLAYWRIGHT_BROWSERS_PATH=/playwright-browsers
ENV PRE_COMMIT_HOME=/pre-commit-cache

RUN playwright install chromium --with-deps && chmod -Rf 777 $PLAYWRIGHT_BROWSERS_PATH
RUN pip install supervisor pre-commit
COPY .pre-commit-config.yaml /tmp/.pre-commit-config.yaml
RUN cd /tmp && \
    git init && \
    pre-commit install-hooks && \
    chmod -Rf 777 $PRE_COMMIT_HOME && \
    rm -rf /tmp/.git /tmp/.pre-commit-config.yaml

CMD ["sleep", "infinity"]

FROM suap-test AS suap-ide
RUN wget https://github.com/cdr/code-server/releases/download/v3.12.0/code-server-3.12.0-linux-amd64.tar.gz
RUN tar -xzf code-server-3.12.0-linux-amd64.tar.gz
RUN ln -s /code-server-3.12.0-linux-amd64/bin/code-server /usr/local/bin/code-server
RUN mkdir /var/lib/code-server
RUN code-server --user-data-dir /var/lib/code-server --install-extension ms-python.python
RUN echo if ! [ -d /suap/deploy/code-server ]\; then cp -r /var/lib/code-server /suap/deploy/code-server\; fi > /bin/entrypoint.sh
RUN echo if ! [ -d /suap/deploy/postgres ]\; then pg_dropcluster 13 main \&\& pg_createcluster -d /suap/deploy/postgres 13 main -- --auth-local=trust\; fi >> /bin/entrypoint.sh
RUN echo /etc/init.d/postgresql start >> /bin/entrypoint.sh
RUN echo code-server --host 0.0.0.0 --user-data-dir /suap/deploy/code-server --auth password /suap >> /bin/entrypoint.sh
RUN chmod +x /bin/entrypoint.sh
CMD ["/bin/entrypoint.sh"]
