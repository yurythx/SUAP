Instruções para Desenvolvedores
===============================

Ferramentas Sugeridas no Desenvolvimento
----------------------------------------

A coordenação de sistemas do IFRN busca utilizar ferramentas que são indicadas pela comunidade de código livre, tendo
como alvo um ambiente produtivo. Para tal, sugerimos e utilizamos as seguintes ferramentas:

* GIT: é um sistema de controle de versões distribuído, usado principalmente no desenvolvimento de software. Inicialmente projetado e desenvolvido por Linus Torvald para o desenvolvimento do kernel Linux (https://pt.wikipedia.org/wiki/Git);
* PyCharm: IDE criada pela jetbrains que une um conjunto de ferramentas que tem como foco ser mais produtiva (https://www.jetbrains.com/pycharm/);
* Eclipse: IDE que une um conjutno de ferramentas que tem como foco ser mais produtiva (https://www.eclipse.org).
* SUAP - módulo de demandas: o módulo de demandas foi criado para controlar o desenvolvimento de novas funcionalidades para o SUAP.


Fluxo de Trabalho
-----------------

Fluxo com o Git
~~~~~~~~~~~~~~~

No desenvolvimento utilizamos a plataforma GitLab, a qual gerencia o repositório GIT, como também tarefas no desenvolvimento.
A partir dessa ferramenta, temos um controle centralizado da evolução do código, por meio de ramificações, criação de branches, 
e junções, a partir de merge requests.

O primeiro passo: no uso do GIT, é instalar um cliente git de acordo com o ambiente de desenvolvimento (estação de trabalho).
Por exemplo, pode-se utilizar o seguinte comando no linux (deistribuíção debian):

Instalação ::

    apt install git

Segundo passo: deve-se configurar os dados do desenvolvedor, para cada usuário da estação de trabalho, com suas
informações:

Configuração Global ::

    git config --global user.name "Nome do Desenvolvedor"
    git config --global user.email "email-do-desenvolvedor@dominio"
    git config --gloval color.ui true

Note:
    * o email informado deve ser o institucional
    * todas as configurações serão armazenadas no arquivo ~/.gitconfig


O fluxo de trabalho, com o GIT, é apresentado a seguir, o qual inicia com base em uma demanda ou em um chamado, 
quando for uma solução de bugs. Os passos do trabalho são:

.. graphviz::

    digraph git_work {
        {
            start [label="Início"]
            master [shape=rect label="Sincronizar master"]
            create_branch [shape=rect label="Criar branch de trabalho"]
            commit [shape=rect label="Commit de alterações"]
            push_branch [shape=rect label="Push na branch de trabalho"]
            merge_request [shape=rect label="Cria um merge request"]
            end [label="Fim"]
        }
        rankdir=LR
        start -> master -> create_branch
        create_branch -> commit
        commit -> commit
        commit -> push_branch
        push_branch -> merge_request
        push_branch -> commit
        merge_request -> end
    }

1. **git pull origin master**: sincronizar o repositório local com o gitlab. Deve-se está na branch master;
2. **git checkout -b <nome_branch>**: criar a branch de trabalho com base na branch master;
3. **git add <arquivo1> <arquivo2> ...**: prepara os arquivos, novos ou alterados, para serem adicionados no repositório;
4. **git commit -m "Mensagem"**: realiza o commit dos arquivos no repositório local;
5. **git push origin master**: envia os commits para o servidor;
6. Entrar no site do **gitlab** e criar o **merge request** solicitando a sincronização com a branch master.


Dicas no uso do Git
~~~~~~~~~~~~~~~~~~~

**Commits** 

Apenas arquivos no Stage podem ser commitados ::

    git commit -m "Mensagem"
    git commit -a -m "Mensagem" (commita também os arquivos versionados mesmo nao estando no Stage)

Voltando e recuperando commits anteriores ::

    git reset --hard HEAD~1 (volta ao último commit)
    git reset --soft HEAD~1 (volta ao último commit e mantém os últimos arquivos no Stage)
    git reset --hard XXXXXXXXXXX (Volta para o commit com a hash XXXXXXXXXXX)
    git reflog (Para visualizar os hashs de commits apagados pelo git reset)
    git merge <hash> (recupera um determinado commit)

**Aliases**

Caso deseje, adicione as seguintes linhas ao arquivo ~/.gitconfig ::

    [alias]
        undo = reset --soft HEAD~1
        ci = !git add . && git commit -am
        st = !git status
        ms = !git checkout master && git pull origin master
        pl = !git pull origin \"$(git rev-parse --abbrev-ref HEAD)\"
        ps = !git push origin \"$(git rev-parse --abbrev-ref HEAD)\"
        lg = log --graph --pretty=format:'%Cred%h%Creset %C(yellow)%an%d%Creset %s %Cgreen(%cr)%Creset' --date=relative
        ls = log --pretty=format:"%C(yellow)%h%Cred%d\\ %Creset%s%Cblue\\ [%cn]" --decorate
            limpar = !git branch --merged | grep -v master | xargs git branch -d
        nc = commit -a --allow-empty-message -m \"\"

Uso ::

    git undo: volta o último commit
    git ci <mensagem>: adiciona todos os arquivos e realiza o commit com a mensagem a ser especificada
    git st  : forma curta de git status
    git pl  : faz um pull na branch atual
    git ps  : faz um push na branch atual
    git lg  : exibe os relacionamentos entre as branchs
    git ls  : exibe os últimos commits
    git ms : vai pra branch master e atualiza
    git limpar : apaga as branchs que já entraram no master
    git nc : comita sem mensagem

**Diffs**

Para transferir o diff de uma branch para outra ::

    git checkout nome_branch_com_alteracoes
    git diff --no-prefix master > diff.patch
    git checkout nome_branch_a_receber_alteracoes
    patch -p0 < diff.patch



Desenvolvimento de Novas Funcionalidades
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~



Correção de BUGs
~~~~~~~~~~~~~~~~



Padrões de Código
-----------------

