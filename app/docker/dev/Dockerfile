# Argumentos padrão
ARG DEV_IMAGE=gitlab.ifrn.edu.br:4567/cosinf/suap:dev

# Herda a imagem já pronta a partir da fase de desenvolvimento
FROM ${DEV_IMAGE} AS suap-dev-user

ARG UID="1000"
ARG GID="1000"
ARG USER_NAME=customuser
ARG WORK_DIR

USER root

# Instala as dependências necessárias
RUN apt-get update && apt-get install -y --fix-missing openssh-server openssh-client procps sudo \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 libxrandr2 libxdamage1 libgbm-dev \
    libpango1.0-0 libasound2 libpangocairo-1.0-0 libxshmfence1 libxkbcommon0 \
    git \
    && apt-get -y autoremove && apt-get clean \
    && rm -rf /var/cache/apt/* && rm -rf /var/lib/apt/lists/*

# Cria o grupo e o usuário com base nos UID e GID fornecidos
RUN groupadd -g "${GID}" customgroup && \
    useradd -m -u "${UID}" -g "${GID}" -m --no-log-init -s /bin/bash $USER_NAME

# Adicionando usuário ao grupo root
RUN usermod -G root $USER_NAME

# [Opcional] Adiciona suporte para Sudo.
RUN echo $USER_NAME ALL=\(ALL\) NOPASSWD:ALL > /etc/sudoers.d/$USER_NAME && \
    chmod 0440 /etc/sudoers.d/$USER_NAME && \
    echo "$USER_NAME:mudar@123" | chpasswd

# Defina o usuário padrão para o container
USER $USER_NAME

# Definir o diretório de trabalho usando o argumento passado
WORKDIR $WORK_DIR

RUN pip install --upgrade pip

# diciona o diretório especificado em $WORK_DIR como um "diretório seguro"
# na configuração global do Git.
RUN git config --global --add safe.directory $WORK_DIR

# Usar ENV para alterar o PATH permanentemente
ENV PATH="$PATH:/home/$USER_NAME/.local/bin"
# Adiciona a linha ao arquivo ~/.bashrc, garantindo que qualquer
# sessão de bash carregue o caminho correto
# RUN echo 'export PATH="$PATH:/home/$USER_NAME/.local/bin"' >> /home/$USER_NAME/.bashrc

# Se o $USER_NAME == "customuser", gera uma nova chave ssh.
RUN if [ "$USER_NAME" = "customuser" ]; then \
        ssh-keygen -t ed25519 -C "Usuário $USER_NAME" -f /home/$USER_NAME/.ssh/id_ed25519_$USER_NAME -N ""; \
    fi

# O CMD final herdado do Dockerfile original
CMD ["/bin/sh", "-c", "echo 'Starting dev container'; sleep infinity"]
