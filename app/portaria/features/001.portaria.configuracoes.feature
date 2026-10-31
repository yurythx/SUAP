# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Configurações do Sistema Portaria.

    @do_document
    Cenário: Adicionando o usuário necessário para essa funcionalidade
        Dado os seguintes usuários
            | Nome                     | Matrícula | Setor | Lotação  | Email                        | CPF            | Senha | Grupo                               |
            | Coordenador de Visitante | 154420    | A0    | A0       | coord.visitante@ifrn.edu.br  | 851.598.524-17 | abc   | Coordenador de Visitantes Sistêmico |
        Dado acesso a página "/"

    Cenário: Efetuar login no sistema
        Quando realizo o login com o usuário "154420" e senha "abc"

    Cenário: Adicionar Configurações
        Quando acesso o menu "Segurança Institucional::Visitantes::Configurações"
        Então vejo a página "Configurações"
        E vejo o botão "Adicionar Configuração"
        Quando clico no botão "Adicionar Configuração"
        Então vejo a página "Adicionar Configuração"
        Quando preencho o formulário com os dados
            | Campo                                        | Tipo           | Valor          |
            | Campus                                       | lista          | A0             |
            | O uso do crachá é obrigatório?               | Checkbox       | marcar         |
            | Habilitar uso da câmera?                     | Checkbox       | marcar         |
            | Habilitar a geração de chave WI-FI?          | Checkbox       | marcar         |
            | Senha do WI-FI                               | Texto          | suapdev        |
            | URL de integração com o Sistema de Wifi      | Texto          |                |
            | Limite de compartilhamento da chave do WI-FI | Data           | 1              |
        E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

        Cenário: Visualizar Configurações
            Quando acesso o menu "Segurança Institucional::Visitantes::Configurações"
            Então vejo a página "Configurações"
            Quando olho para a listagem
            E olho a linha "A0"
            E clico no ícone de exibição
            Então vejo a página "Configurações do campus: A0"
