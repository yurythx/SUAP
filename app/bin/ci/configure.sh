#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

if ! [ -f ".env" ]; then
  cp bin/ci/suap.env .env
  echo "CLONE_URL=$(git remote get-url origin)" >> .env
  mkdir -p bin/ci/nginx
  touch bin/ci/nginx/suapdevs.conf
fi

if [ ! -x "$(command -v docker)" ]; then
    apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" |  tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io
    curl -L "https://github.com/docker/compose/releases/download/v2.0.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

if [ ! -x "$(command -v gitlab-runner)" ]; then
  curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
fi

if [ ! -x "$(command -v gitlab-runner)" ]; then
    wget -O /usr/local/bin/gitlab-runner https://gitlab-runner-downloads.s3.amazonaws.com/latest/binaries/gitlab-runner-linux-amd64
    chmod +x /usr/local/bin/gitlab-runner
    useradd --comment "GitLab Runner" --create-home gitlab-runner --shell /bin/bash
    gitlab-runner install --user=gitlab-runner --working-directory=/home/gitlab-runner
    usermod -aG docker gitlab-runner
    gpasswd -d gitlab-runner docker
fi

printf "cd %s && bin/ci/start.sh" "$(pwd)" > /usr/local/bin/gitlab-ci-start
printf "cd %s && bin/ci/stop.sh" "$(pwd)" > /usr/local/bin/gitlab-ci-stop

chmod +x /usr/local/bin/gitlab-ci-start
chmod +x /usr/local/bin/gitlab-ci-stop

rm -f /home/gitlab-runner/.bash_logout
mkdir -p /var/suapdevs
chown -R gitlab-runner /opt/suap
chown -R gitlab-runner /var/suapdevs
