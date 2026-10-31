# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Acompanhamento de Egressos

    Cenário: Adicionando os usuários necessários para os testes egressos
        Dado os seguintes usuários
            | Nome    | Matrícula      | Setor | Lotação | Email               | CPF            | Senha | Grupo                         |
            | Gerente dos Egressos | 101001         | CZN   | CZN     | gerente@ifrn.edu.br | 000.101.001-80 | abcd  | Gerente Sistêmico de Extensão |
            | Aluno1  | 20191101011012 | CZN   | CZN     | aluno_1@ifrn.edu.br | 413.244.180-60 | abcd  | Aluno                         |
            | Aluno2  | 20191101011013 | CZN   | CZN     | aluno_2@ifrn.edu.br | 826.526.814-94 | abcd  | Aluno                         |

    @do_document
    Cenário: Cria uma nova Pesquisa de Acompanhamento
        Dado acesso a página "/"
        Quando realizo o login com o usuário "101001" e senha "abcd"
            E acesso o menu "Extensão::Egressos::Pesquisas de Acompanhamento de Egressos"
        Então vejo a página "Pesquisas de Acompanhamento de Egressos"
            E vejo o botão "Adicionar Pesquisa de Acompanhamento de Egressos"
        Quando clico no botão "Adicionar Pesquisa de Acompanhamento de Egressos"
        Então vejo a página "Adicionar Pesquisa de Acompanhamento de Egressos"
            E vejo os seguintes campos no formulário
            | Campo                          | Tipo     |
            | Título                         | Texto    |
            | Descrição                      | TextArea |
            | Público Alvo                   | Autocomplete    |
            | Ano de Conclusão               | Autocomplete multiplo    |
            | Campus                         | Autocomplete multiplo    |
            |Curso                           | Autocomplete |
            E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
            | Campo                               | Tipo     | Valor                    |
            | Título                         | Texto    | Título da pesquisa de acompanhamento |
            | Descrição                      | TextArea | descrição da pesquisa                |
            | Público Alvo                   | Autocomplete    | Técnico integrado ao ensino médio                    |
            E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
        
        Quando acesso o menu "Extensão::Egressos::Pesquisas de Acompanhamento de Egressos" 
        E olho para a listagem
            E olho a linha "Título da pesquisa de acompanhamento"
            E clico no ícone de exibição
        Então vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
            E vejo a aba "Categorias"
        Quando clico na aba "Categorias"
        Então vejo o botão "Adicionar Categoria"
        Quando clico no botão "Adicionar Categoria"
        E olho para o popup
        Então vejo os seguintes campos no formulário
            | Campo                          | Tipo  |
            | Título                         | Texto |
            | Ordem                          | Texto |

        E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
            | Campo                          | Tipo  | Valor |
            | Título                         | Texto | Descrição da Categoria 1    |
            | Ordem                          | Texto | 1     |
            E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Categoria registrada com sucesso."

        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
        E vejo a aba "Categorias"
        Quando clico na aba "Categorias"
        Então vejo o botão "Adicionar Categoria"
        Quando clico no botão "Adicionar Categoria"
        E olho para o popup
        Então vejo os seguintes campos no formulário
            | Campo                          | Tipo  |
            | Título                         | Texto |
            | Ordem                          | Texto |

        E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
            | Campo                          | Tipo  | Valor |
            | Título                         | Texto | Descrição da Categoria 2    |
            | Ordem                          | Texto | 2     |
            E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Categoria registrada com sucesso."

        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
        E vejo a aba "Perguntas"
        Quando clico na aba "Perguntas"
        Então vejo o botão "Adicionar Pergunta"
        Quando clico no botão "Adicionar Pergunta"
        E olho para o popup
        Então vejo os seguintes campos no formulário
            | Campo                          | Tipo  |
            | Conteúdo                       | TextArea |
            | Categoria                      | Autocomplete |
            | Tipo                           | Lista |
            | Preenchimento Obrigatório       | checkbox |

        E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
            | Campo                          | Tipo  | Valor |
            | Conteúdo                       | TextArea | Pergunta 1 do bloco 1 |
            | Categoria                      | Autocomplete | Descrição da Categoria 1 |
            | Tipo                           | Lista | Objetiva de resposta única |
            | Preenchimento Obrigatório       | checkbox | marcar                  |
            E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Pergunta registrada com sucesso."

        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
        E vejo a aba "Perguntas"
        Quando clico na aba "Perguntas"
        Então vejo o botão "Adicionar Pergunta"
        Quando clico no botão "Adicionar Pergunta"
        E olho para o popup
        Então vejo os seguintes campos no formulário
            | Campo                          | Tipo  |
            | Conteúdo                       | TextArea |
            | Categoria                      | Autocomplete |
            | Tipo                           | Lista |
            | Preenchimento Obrigatório       | checkbox |

        E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
            | Campo                          | Tipo  | Valor |
            | Conteúdo                       | TextArea | Pergunta 2 do bloco 1 |
            | Categoria                      | Autocomplete | Descrição da Categoria 1 |
            | Tipo                           | Lista | Objetiva de resposta única |
            | Preenchimento Obrigatório       | checkbox | desmarcar                  |
            E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Pergunta registrada com sucesso."

        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
        E vejo a aba "Perguntas"
        Quando clico na aba "Perguntas"
        Então vejo o botão "Adicionar Pergunta"
        Quando clico no botão "Adicionar Pergunta"
        E olho para o popup
        Então vejo os seguintes campos no formulário
            | Campo                          | Tipo  |
            | Conteúdo                       | TextArea |
            | Categoria                      | Autocomplete |
            | Tipo                           | Lista |
            | Preenchimento Obrigatório       | checkbox |

        E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
            | Campo                          | Tipo  | Valor |
            | Conteúdo                       | TextArea | Pergunta 1 do bloco 2 |
            | Categoria                      | Autocomplete | Descrição da Categoria 2 |
            | Tipo                           | Lista | Subjetiva |
            | Preenchimento Obrigatório       | checkbox | marcar                  |
            E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Pergunta registrada com sucesso."
        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
        E vejo a aba "Perguntas"
        Quando clico na aba "Perguntas"
            E olho a linha "Pergunta 1 do bloco 1"
        Então vejo o botão "Adicionar Opção de Resposta"
        Quando clico no botão "Adicionar Opção de Resposta"
        E olho para o popup
        Então vejo os seguintes campos no formulário
            | Campo                          | Tipo  |
            | Opção de Resposta              | TextArea |
            | Direcionar à Categoria         | Autocomplete |

        E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
            | Campo                          | Tipo  | Valor |
            | Opção de Resposta              | TextArea | Sim |
            | Direcionar à Categoria         | Autocomplete |  Descrição da Categoria 1 |
            E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Opção de pergunta registrada com sucesso."
        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"

        Quando  olho a linha "Pergunta 1 do bloco 1"
        Então vejo o botão "Adicionar Opção de Resposta"
        Quando clico no botão "Adicionar Opção de Resposta"
        E olho para o popup
        Então vejo os seguintes campos no formulário
            | Campo                          | Tipo  |
            | Opção de Resposta              | TextArea |
            | Direcionar à Categoria         | Autocomplete |

        E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
            | Campo                          | Tipo  | Valor |
            | Opção de Resposta              | TextArea | Não |
            | Direcionar à Categoria         | Autocomplete |  Descrição da Categoria 1 |
            E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Opção de pergunta registrada com sucesso."
        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
        Quando olho a linha "Pergunta 2 do bloco 1"
        Então vejo o botão "Copiar Opções de Resposta de uma pergunta anterior"
        Quando clico no botão "Copiar Opções de Resposta de uma pergunta anterior"
        E olho para o popup
        Então vejo a página "Copiar Opções de Resposta de uma pergunta anterior"

        Quando seleciono o item "Pergunta 1 do bloco 1" da lista
            E clico no botão "Enviar"
        Então vejo mensagem de sucesso "Opções de resposta copiadas com sucesso."
        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
        E vejo o botão "Publicar Pesquisa"
        Quando clico no botão "Publicar Pesquisa"
        Então vejo a página "Publicar Pesquisa: Título da pesquisa de acompanhamento"
        E vejo os seguintes campos no formulário
            | Campo               | Tipo  |
            | Início              | Texto |
            | Fim                 | Texto |
        E vejo o botão "Publicar a Pesquisa e Enviar Convites"
        Quando preencho o formulário com os dados
            | Campo               | Tipo  | Valor |
            | Início              | Data | 01/01/2018 |
            | Fim                 | Data | 01/02/2018 |
        E clico no botão "Publicar a Pesquisa e Enviar Convites"
        Então vejo mensagem de sucesso "A pesquisa foi publicada e foram enviados os convites para os alunos alvo."
        E vejo a página "Pesquisa de Acompanhamento de Egressos: Título da pesquisa de acompanhamento"
        E vejo a aba "E-mails Enviados"
        Quando clico na aba "E-mails Enviados"
            E olho a linha "Destinatários"

    Cenário: Sai do sistema
        Quando acesso o menu "Sair"
