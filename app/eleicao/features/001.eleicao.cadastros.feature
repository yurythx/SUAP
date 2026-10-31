# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas a criação de uma eleição
    Essa funcionalidade verifica a criação de um edital e de uma nova eleição e o acesso dos participantes nesse processo eleitoral.

      Cenário: Monta os dados básicos e adiciona os usuários necessários para os testes de Eleição
          Dado os seguintes usuários
              | Nome                  | Matrícula      | Setor    | Lotação  | Email           | CPF            | Senha | Grupo                 |
              | Criador de Eleição    | 106001         | DIAC/CEN | DIAC/CEN | d01@ifrn.edu.br | 000.106.001-59 | abcd  | Criador de Eleição    |
              | Coordenador de Edital | 106002         | DIAC/CEN | DIAC/CEN | d02@ifrn.edu.br | 647.115.806-89 | abcd  | Coordenador de Edital |
              | Candidato de Eleição  | 106003         | DIAC/CZN | DIAC/CZN | d03@ifrn.edu.br | 735.785.191-54 | abcd  | Servidor              |
              | Eleitor 1             | 20191101011061 | DIAC/CZN | DIAC/CZN | d04@ifrn.edu.br | 824.587.211-33 | abcd  | Aluno                 |
              | Eleitor 2             | 106004         | DIAC/CZN | DIAC/CZN | d05@ifrn.edu.br | 583.596.500-12 | abcd  | Servidor              |
              | Eleitor 3             | 106005         | DIAC/CZN | DIAC/CZN | d06@ifrn.edu.br | 227.216.860-46 | abcd  | Servidor              |
             E um Público cadastrado

      @do_document
      Cenário: Criação de um Edital para as Eleições
          Dado acesso a página "/"
          Quando a data do sistema for "01/10/2018"
        Quando realizo o login com o usuário "106001" e senha "abcd"
             E acesso o menu "Administração::Eleições::Editais"
         Então vejo a página "Editais"
             E vejo mensagem de alerta "Nenhum Edital encontrado."
        Quando clico no botão "Adicionar Edital"
         Então vejo a página "Adicionar Edital"
             E vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com
                 | Campo                          | Tipo                  | Obrigatório | Valor      |
                 | Descrição                      | Texto                 | Sim         | Edital 1   |
                 | Início das Inscrições          | Data                  | Sim         | 01/10/2018 |
                 | Fim das Inscrições             | Data                  | Sim         | 31/10/2018 |
                 | Início da Validação            | Data                  | Sim         | 01/10/2018 |
                 | Fim da Validação               | Data                  | Sim         | 31/10/2018 |
                 | Início da Campanha             | Data                  | Sim         | 01/11/2018 |
                 | Fim da Campanha                | Data                  | Sim         | 30/11/2018 |
                 | Início da Votação              | Data                  | Sim         | 01/12/2018 |
                 | Fim da Votação                 | Data                  | Sim         | 31/12/2018 |
                 | Início do Resultado Preliminar | Data                  | Não         | 01/01/2019 |
                 | Fim do Resultado Preliminar    | Data                  | Não         | 31/01/2019 |
                 | Início da Homologação          | Data                  | Sim         | 01/02/2019 |
                 | Fim da Homologação             | Data                  | Sim         | 28/02/2019 |
                 | Data para Resultado Final      | Data                  | Sim         | 01/03/2019 |
                 | Coordenadores do Edital        | Autocomplete Multiplo | Sim         | 106002     |
        Quando clico no botão "Salvar"
         Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"

      @do_document
      Cenário: Criação de uma Eleição
          Dado acesso a página "/"
          Quando a data do sistema for "01/10/2018"
        Quando realizo o login com o usuário "106002" e senha "abcd"
            E acesso o menu "Administração::Eleições::Eleições"
         Então vejo a página "Eleições"
        Quando clico no botão "Adicionar Eleição"
         Então vejo a página "Adicionar Eleição"
             E vejo os seguintes campos no formulário
               | Campo                                | Tipo                   |
               | Edital                               | Autocomplete           |
               | Descrição                            | Texto                  |
               | Servidores                           | autocomplete multiplo  |
               | Público                              | Lista                  |
               | Campi                                | FilteredSelectMultiple |
               | Votação Global                       | Checkbox               |
               | Resultado Global                     | Checkbox               |
               | Número de Caracteres para a Campanha | Texto                  |
               | Número de Caracteres para Recurso    | Texto                  |
               | Observação para Votação              | Textarea               |

        Quando preencho o formulário com os dados

            | Campo                                | Tipo                   | Valor            |
            | Edital                               | Autocomplete           | Edital 1         |
            | Descrição                            | Texto                  | Eleição 1        |
            | Público                              | Lista                  | Todos do sistema |
            | Campi                                | FilteredSelectMultiple | CZN, CEN         |
            | Número de Caracteres para a Campanha | Texto                  | 200              |
            | Número de Caracteres para Recurso    | Texto                  | 1200             |

        E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"

      @do_document
      Cenário: Candidato se cadastra na Eleição
          Dado acesso a página "/"
          Quando a data do sistema for "10/10/2018"
        Quando realizo o login com o usuário "106003" e senha "abcd"
            E aguardo o conteúdo ajax carregar
         Então vejo o quadro "Eleições"
        Quando clico no link "Eleição 1"
         Então vejo a página "Inscrição para Eleição"
             E vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com
               | Campo                 | Tipo     | Obrigatório | Valor       |
               | Texto de Apresentação | Textarea | Sim         | Vote em mim |
        Quando clico no botão "Salvar"
         Então vejo mensagem de sucesso "Sua inscrição foi realizada."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"

      @do_document
      Cenário: Avaliar Candidato de Eleição
          Dado acesso a página "/"
          Quando a data do sistema for "30/10/2018"
        Quando realizo o login com o usuário "106002" e senha "abcd"
             E acesso o menu "Administração::Eleições::Candidatos"
         Então vejo a página "Candidatos"
        Quando clico no botão "Avaliar"
         Então vejo a página "Avaliar Candidatura"
             E vejo os seguintes campos no formulário preenchidos com
               | Campo                 | Tipo     | Valor                |
               | Eleição               | Texto    | Eleição 1 (Edital 1) |
               | Candidato             | Texto    | Candidato de Eleição |
               | Texto de Apresentação | Textarea | Vote em mim          |
               | Parecer               | Lista    | Pendente             |
             E vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com
               | Campo                 | Tipo     | Obrigatório | Valor       |
               | Eleição               | Texto    | Não         |             |
               | Candidato             | Texto    | Não         |             |
               | Texto de Apresentação | Textarea | Não         |             |
               | Parecer               | Lista    | Não         | Deferido    |
               | Justificativa         | Textarea | Não         |             |
        Quando clico no botão "Salvar"
         Então vejo mensagem de sucesso "O candidato foi avaliado."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"

      @do_document
      Cenário: Iniciar Campanha
          Dado acesso a página "/"
          Quando a data do sistema for "10/11/2018"
        Quando realizo o login com o usuário "106004" e senha "abcd"
         Então vejo o quadro "Eleições"
        Quando clico no link "Eleição 1"
         Então vejo a página "Campanhas para Eleições"
             E vejo o quadro "Candidatos para Eleição 1"
             E vejo a caixa de informações "Candidato" com "Vote em mim"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"

      @do_document
      Cenário: Votar
          Dado acesso a página "/"
          Quando a data do sistema for "10/12/2018"
        Quando realizo o login com o usuário "106004" e senha "abcd"
         Então vejo o quadro "Eleições"
        Quando clico no link "Eleição 1"
         Então vejo a página "Votação para Eleição 1"
             E vejo o quadro "Candidatos"
             E vejo a caixa de informações "Candidato" com "Vote em mim"
        Quando clico no botão "Votar"
         Então vejo a página "Comprovante de Votação"
             E vejo o texto "Eleição 1 (Edital 1)"
             E vejo o texto "Eleitor 2"
             E vejo o texto "Candidato Escolhido"
             E vejo o texto "Hash"
             E vejo o texto "QRCode"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"

      @do_document
      Cenário: Exibir Resultado Preliminar
          Dado acesso a página "/"
          Quando a data do sistema for "10/01/2019"
        Quando realizo o login com o usuário "106002" e senha "abcd"
             E acesso o menu "Administração::Eleições::Eleições"
         Então vejo a página "Eleições"
        Quando clico no link "Ver resultados"
         Então vejo a página "Resultado: Eleição 1"
             E vejo o quadro "CZN"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
