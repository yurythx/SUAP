# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atos de Admissão/Concessão
  Gerenciamento de envio ao E-Pessoal de Atos de Admissão de Pessoal, Concessão de Aposentadoria e Pensão Civil

  Cenário: Adicionando os usuários necessários para os testes Atos
    Dado os seguintes usuários
      | Nome               | Matrícula      | Setor | Lotação | Email                    | CPF            | Senha | Grupo                                       |
      | RH Sistemico       | 1000001        | A0    | A0      | rhsistemico@ifrn.edu.br  | 001.000.001-18 | abc1  | Coordenador de Gestão de Pessoas Sistêmico  |
      | RH Campus          | 1000002        | B0    | B0      | rhcampus@ifrn.edu.br     | 001.000.002-07 | abc2  | Coordenador de Gestão de Pessoas            |

  @do_document
  Cenário: RH Sistêmico: adicionar ato de admissão de pessoal de servidor qualquer
    Dado acesso a página "/"
    Quando realizo o login com o usuário "1000001" e senha "abc1"
    E acesso o menu "Gestão de Pessoas::Administração de Pessoal::Acompanhamento Funcional::Controle de Atos"
    Então vejo a página "Atos de Admissão/Concessão"
    Quando clico no botão "Adicionar Ato de Admissão/Concessão"
    Então vejo a página "Adicionar Ato de Admissão/Concessão"
    Quando preencho o formulário com os dados
      | Campo                     | Tipo            | Valor               |
      | Servidor                  | Autocomplete    | 1111111             |
      | Tipo de ato               | lista           | Admissão de pessoal |
      | Data da ocorrência do ato | Data            | 31/07/2020          |

    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: RH de Campus: adicionar ato de admissão de pessoal de servidor do mesmo campus
    Dado acesso a página "/"
    Quando realizo o login com o usuário "1000002" e senha "abc2"
    E acesso o menu "Gestão de Pessoas::Administração de Pessoal::Acompanhamento Funcional::Controle de Atos"
    Então vejo a página "Atos de Admissão/Concessão"
    Quando clico no botão "Adicionar Ato de Admissão/Concessão"
    Então vejo a página "Adicionar Ato de Admissão/Concessão"
    Quando preencho o formulário com os dados
      | Campo                     | Tipo            | Valor               |
      | Servidor                  | Autocomplete    | 2222222             |
      | Tipo de ato               | lista           | Admissão de pessoal |
      | Data da ocorrência do ato | Data            | 03/08/2020          |

    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
    Quando acesso o menu "Sair"
