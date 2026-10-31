# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Registrar Visitante no Campus.

    @do_document
      Cenário: Adicionando o usuário necessário para essa funcionalidade
        Dado os seguintes usuários
            | Nome                     | Matrícula | Setor | Lotação  | Email                        | CPF            | Senha | Grupo                               |
            | Coordenador de Visitante | 154420    | A0    | A0       | coord.visitante@ifrn.edu.br  | 851.598.524-17 | abc   | Coordenador de Visitantes Sistêmico |
        Dado acesso a página "/"

    Cenário: Efetuar login no sistema
        Quando realizo o login com o usuário "154420" e senha "abc"

    Cenário: Adicionar Visitante ao Campus
        Quando acesso o menu "Segurança Institucional::Visitantes::Registrar Visita"
        Então vejo a página "Visitas ao Campus: A0"
        E vejo o botão "Registrar Visita"
        Quando clico no botão "Registrar Visita"
        Então vejo a página "Registrar Visita(s) ao Campus A0"
        E vejo o botão "Cadastrar Pessoa (Sem Vínculo com o IFRN)"
        Quando clico no botão "Cadastrar Pessoa (Sem Vínculo com o IFRN)"
        Então vejo a página "Cadastrar Pessoa (Sem Vínculo com o IFRN)"
        Quando preencho o formulário com os dados
            | Campo                       | Tipo      | Valor             |
            | Nome                        | Texto     | Maria Clara       |
            | Sexo                        | Lista     | Feminino          |
            | Documento de Identificação  | Texto     | 11122             |
            | CPF                         | Texto     | 001.132.174-12    |
            | E-mail                      | Texto     | maria@ifrn.edu.br |
            | Deseja registrar uma visita | Checkbox  | marcar            |
        E clico no botão "Enviar"
        Então vejo mensagem de sucesso "Pessoa Externa cadastrada com sucesso."
        E vejo a página "Registrar Visita ao Campus A0"

    Cenário: Registrar Visita ao Campus
        Quando preencho o formulário com os dados
            | Campo                                      | Tipo     | Valor         |
            | Objetivo                                   | Texto    | Aula de campo |
            | Crachá                                     | Texto    | 001           |
            | Deseja gerar chave do WI-FI                | Checkbox | marcar        |
            | Quantidade de Dias Validade Chave do WI-FI | lista    | 2             |
        E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Registro da Visita realizado com sucesso"

    Cenário: Registrar saída da visita
        Então vejo a página "Visitas ao Campus: A0"
        Quando olho para a tabela
        E olho a linha "Maria Clara"
        Então vejo o botão "Registrar Saída"
        Quando clico no botão "Registrar Saída"
        E olho para o popup
        E clico no botão "Confirmar"
