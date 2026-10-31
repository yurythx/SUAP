# Serviços gerais do SUAP

Reúne o que não pertence a uma área específica do SUAP e serve a todo mundo que usa o sistema: a **sua conta** (senha, verificação em duas etapas, sessões e dispositivos), os **prédios e as salas** da instituição — com a reserva de salas de ponta a ponta —, os **documentos** emitidos e assinados digitalmente, os **cadastros de pessoas** que não são servidores nem alunos (prestadores de serviço, usuários externos), os **calendários** que organizam a rotina administrativa e das reuniões dos conselhos, e a **página inicial** que você vê ao entrar.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Qualquer pessoa com conta no SUAP | Cuida da própria conta, reserva salas, acompanha notificações, organiza a página inicial e consulta os calendários da instituição |
| Servidor | Além do acima: mantém os próprios contatos de emergência, pede o cadastro da sua biometria e acompanha as reuniões dos conselhos superiores |
| Administrador, equipe de TI e gestores | Mantém os cadastros da instituição: prédios e salas, grupos de acesso, usuários externos, telefones, reuniões dos colegiados, extrações de pessoal e configurações |
| Prestador de serviço e usuário externo | Entra no SUAP com o cadastro, a ocupação e o papel que a instituição registrou, e usa os mesmos serviços de conta, documentos e notificações |
| Público externo, sem login | Confere a autenticidade de um documento emitido pelo SUAP e consulta a documentação do sistema, sem precisar de conta |

---

## Tarefas

### 1. Cadastrar um prédio e suas salas

**Quem pode:** perfis com permissão de cadastrar prédios e salas — Coordenador da Sede, Coordenador de Chaves (e o sistêmico), Coordenador de Patrimônio (e o sistêmico) e Operador de Patrimônio. O cadastro é sempre do **seu próprio campus**: o campo *Campus* só oferece a sua unidade.
**Quando usar:** ao registrar uma edificação nova, ou ao preparar uma sala para receber reservas.

**Etapa 1 — cadastrar o prédio**

1. No menu, acesse **Administração › Prédios e Salas › Prédios** e clique em **Adicionar Prédio**.

   ![Listagem de prédios](usuario/predio-listagem.webp)

2. Preencha o formulário, dividido em dois blocos — *Dados gerais* e *Sistemas Construtivos*. Só **Nome** e **Campus** são obrigatórios; o restante é o inventário da edificação e pode ser completado depois:

   | Campo | O que informar |
   | --- | --- |
   | Campus | A unidade a que o prédio pertence — é o que define quem enxerga o prédio e quais salas podem ser cadastradas nele |
   | Ativo | Vem marcado; desmarque para sinalizar que a edificação saiu de uso. A listagem pode ser filtrada por esse campo |
   | Sistemas Construtivos (Estrutura, Vedação, Cobertura, Sistema Sanitário, de Abastecimento, de Alimentação Elétrica, de Proteção Contra Descargas Atmosféricas, Acabamento Externo) | Inventário da edificação; cada lista é alimentada pelas telas de apoio descritas no fim deste guia |

   ![Formulário de cadastro do prédio](usuario/predio-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** aparece *"Cadastro realizado com sucesso."* Na listagem de prédios, o ícone de exibição da linha abre a ficha, onde também se registram **Obra** e **Combate a Incêndio e Pânico**.

![Ficha do prédio](usuario/predio-ficha.webp)

**Etapa 2 — cadastrar a sala**

4. No menu, acesse **Administração › Prédios e Salas › Salas** e clique em **Adicionar Sala**.

   ![Listagem de salas](usuario/sala-listagem.webp)

5. Preencha o formulário, dividido em quatro blocos (*Dados gerais*, *Agendamento*, *Dados complementares*, *Acabamento e Sistemas Prediais*). Obrigatórios são só **Nome** e **Prédio** — os campos que decidem o comportamento da sala são estes:

   | Campo | O que informar |
   | --- | --- |
   | Prédio | Só aparecem os prédios do seu campus |
   | Agendável | Marque para a sala aceitar reserva. Sem isso ela existe, mas não aparece para quem procura sala livre |
   | Avaliadores de Agendamento | Os servidores que vão deferir ou indeferir as solicitações desta sala. **Sem pelo menos um, a sala não aceita solicitação nenhuma**, mesmo marcada como agendável |
   | Agendamento apenas por servidores do campus | Restringe a reserva a quem é lotado no campus da sala |
   | Capacidade da sala | Em número de pessoas; é exibida a quem for solicitar a reserva |
   | Informações complementares | Texto livre mostrado no formulário de solicitação (equipamentos disponíveis, regras de uso) |
   | Setores | Meramente informativo: quais setores ocupam a sala |

   ![Formulário de cadastro da sala](usuario/sala-formulario.webp)

6. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."* A ficha da sala (ícone de exibição na linha da listagem) mostra as tarjas **Ativa** e **Agendável**, os dados gerais e a agenda atual.

![Ficha da sala](usuario/sala-ficha.webp)

> Na coluna **Opções** da listagem de salas, a sala pronta para uso exibe o botão *Solicitar/Ver Reservas*. Quando ela não está reservável, essa coluna diz o motivo — *Inativa*, *Não é agendável*, *Não possui avaliador* ou *Esta sala só pode ser agendada por usuários do mesmo campus*.

---

### 2. Reservar uma sala

**Quem pode:** Servidor e Prestador de Serviço. Salas marcadas com *Agendamento apenas por servidores do campus* só aceitam pedido de quem é lotado naquele campus.
**Quando usar:** para pedir uma sala para uma aula, reunião, defesa ou evento.

1. No menu, acesse **Administração › Reservas de Salas › Listagem de Salas Disponíveis**. Informe **Data Inicial**, **Data Final**, **Hora Inicial** e **Hora Final** — e, se quiser restringir a busca, **Campus**, **Prédio** ou **Sala**. Clique em **Enviar**.

   ![Salas disponíveis no período consultado](usuario/salas-disponiveis.webp)

2. Na linha da sala escolhida, clique em **Solicitar/Ver Reservas**.
3. Preencha o formulário de solicitação. A mesma página mostra, acima, a **agenda atual da sala**, com o que já está marcado:

   | Campo | O que informar |
   | --- | --- |
   | Recorrência | **Evento único**, **Semanalmente**, **Quinzenalmente** ou **Mensalmente**. Nas recorrentes, marque também os dias da semana (Segunda a Domingo) |
   | Data de Início e Data de Fim | O período. Data ou hora já passada é recusada |
   | Hora de Início e Hora de Fim | O horário dentro de cada dia do período |
   | Justificativa | Obrigatória — é o que o avaliador da sala lê para decidir |
   | Interessados | Outras pessoas que acompanham a solicitação |
   | Anexo | Documento de apoio, quando houver |

   ![Formulário de solicitação de reserva](usuario/reserva-formulario.webp)

4. Clique em **Salvar**.

**Resultado:** *"Solicitação realizada com sucesso."* A solicitação nasce com a situação **Aguardando Avaliação** e fica à espera do avaliador da sala (tarefa 3). A página da solicitação reúne período, justificativa, informações complementares da sala e a agenda.

![Solicitação aguardando avaliação](usuario/reserva-solicitacao.webp)

**Se mudar de ideia:** na página da solicitação, clique em **Cancelar Solicitação**, informe a **Justificativa do Cancelamento** e clique em **Salvar**. A solicitação passa a constar como **Indeferida**, com o cancelamento e o motivo registrados — e, se já havia reservas geradas, todas são canceladas junto.

![Cancelamento da solicitação](usuario/reserva-cancelar-solicitacao.webp)

---

### 3. Avaliar uma solicitação de reserva

**Quem pode:** o **avaliador daquela sala**. Não basta pertencer ao grupo Avaliador de Sala: é preciso estar na lista *Avaliadores de Agendamento* da sala em questão (tarefa 1, etapa 2).
**Pré-condição:** a solicitação ainda estar **Aguardando Avaliação** e o período não ter passado — solicitação já deferida não é avaliada de novo.

1. No menu, acesse **Administração › Reservas de Salas › Solicitações de Reserva** e abra a aba **Solicitações a Avaliar**.

   ![Solicitações a avaliar](usuario/solicitacoes-listagem.webp)

2. Clique no ícone de exibição da linha para abrir a solicitação e conferir período, justificativa, solicitante e a agenda da sala.

   ![Solicitação aberta pelo avaliador](usuario/solicitacao-ficha.webp)

3. Clique em **Avaliar Solicitação**. Abre o diálogo *Avaliar Agendamento de Sala*: escolha a **Situação** (*Deferida* ou *Indeferida*), escreva uma **Observação** e clique em **Salvar**.

   ![Diálogo de avaliação](usuario/avaliacao-formulario.webp)

**Resultado:** *"Avaliação realizada com sucesso."* Deferida, a solicitação gera as **reservas** correspondentes — uma para cada ocorrência da recorrência pedida —, que passam a constar em **Administração › Reservas de Salas › Reservas Deferidas**.

![Reservas deferidas](usuario/reservas-deferidas.webp)

> A tela **Administração › Reservas de Salas › Salas** traz, na aba **Salas que Avalio**, apenas as salas de que você é avaliador, com o atalho *Solicitar/Ver Reservas* em cada linha.
>
> ![Salas que avalio](usuario/minhas-salas.webp)

---

### 4. Registrar a ocorrência e cancelar reservas

**Quem pode:** o avaliador da sala (mesma regra da tarefa 3). O cancelamento de uma reserva também é permitido a quem a solicitou.
**Quando usar:** depois de a solicitação ser deferida — para dizer se a atividade aconteceu, ou para desfazer a reserva.

**Etapa 1 — informar se a atividade ocorreu**

1. Abra a solicitação deferida (tarefa 3, passos 1 e 2). No quadro **Reservas**, clique em **Informar ocorrência**.

   ![Quadro de reservas da solicitação deferida](usuario/reserva-quadro-reservas.webp)

2. No diálogo, escolha **Atividade Ocorreu** (*Sim* ou *Não*; escolhendo *Não*, informe o **Motivo da Atividade Não Ter Ocorrido**) e clique em **Salvar**.

   ![Diálogo de ocorrência](usuario/reserva-ocorrencia.webp)

**Resultado:** *"Operação realizada com sucesso."* A reserva passa a exibir **Ocorreu** ou **Não ocorreu**.

**Etapa 2 — cancelar uma reserva**

3. No mesmo quadro **Reservas**, clique em **Cancelar Reserva**, informe a **Justificativa do Cancelamento** e clique em **Salvar**.

   ![Diálogo de cancelamento da reserva](usuario/reserva-cancelamento.webp)

**Resultado:** *"Cancelamento realizado com sucesso."* A reserva fica **Cancelada**, registrando quem cancelou e por quê. **Se era a única reserva ativa**, a solicitação inteira passa a **Indeferida**.

**Etapa 3 — cancelar tudo num período**

4. Na ficha da sala, clique em **Cancelar Reservas por Período** (o botão só aparece para quem avalia a sala). Informe **Data de Início do Cancelamento**, **Data de Término do Cancelamento** e a **Justificativa do Cancelamento**, e clique em **Enviar**.

   ![Cancelamento em lote por período](usuario/reserva-cancelamento-periodo.webp)

**Resultado:** *"Cancelamento realizado com sucesso."* Todas as reservas da sala dentro do intervalo são canceladas de uma vez, com a mesma justificativa.

---

### 5. Indisponibilizar uma sala para manutenção

**Quem pode:** o avaliador da sala. É preciso avaliar ao menos uma sala para abrir a tela, e só as salas que você avalia aparecem para escolha.
**Quando usar:** para fechar a sala num período — reforma, dedetização, troca de piso — sem que exista solicitação nenhuma a recusar.

1. No menu, acesse **Administração › Reservas de Salas › Indisponibilizações** e clique em **Registrar Indisponibilização**.

   ![Listagem de indisponibilizações](usuario/indisponibilizacao-listagem.webp)

2. Escolha **Campus**, **Prédio** e **Sala** — as três listas são encadeadas: cada uma só se preenche depois da anterior. Informe **Data/Hora de Início**, **Data/Hora Final** e a **Justificativa**, e clique em **Salvar**.

   ![Formulário de indisponibilização](usuario/indisponibilizacao-formulario.webp)

**Resultado:** *"Cadastro realizado com sucesso."* O registro passa a constar na listagem. Ela tem duas abas: **Qualquer**, com todos os registros, e **Salas Atualmente em Manutenção**, só com os que estão em curso neste momento — um período futuro aparece na primeira e não na segunda.

![Indisponibilização registrada](usuario/indisponibilizacao-registrada.webp)

**Para desfazer:** clique no ícone de remoção da linha. Aparece *"Indisponibilização removida com sucesso."* e o registro deixa a listagem.

---

### 6. Consultar os indicadores de uso das salas

**Quem pode:** o avaliador de sala.
**Quando usar:** para saber o quanto as salas de um prédio foram usadas num intervalo — insumo de remanejamento e de pedido de espaço novo.

1. No menu, acesse **Administração › Reservas de Salas › Indicadores**. Informe **Data Inicial**, **Data Final** e o **Campus**; o **Prédio** é opcional e restringe o resultado. Clique em **Enviar**.

**Resultado:** um quadro por sala, com as reservas do período.

![Indicadores de uso das salas](usuario/indicadores.webp)

---

<!--
Fatias 2 a 6 da doc de usuário do `comum`: acrescente as suas tarefas AQUI, nesta ordem,
continuando a numeração (a fatia 1 terminou na tarefa 6) e deixando as seções "Para o público
externo" e "Telas de apoio" sempre ao fim do arquivo. A fatia que cobrir fluxo sem login
escreve a sua parte na seção "Para o público externo"; toda tela de tabela de apoio vai para a
seção "Telas de apoio", em parágrafo, nunca em passo a passo.
-->

### 7. Cuidar da sua conta

**Quem pode:** qualquer pessoa com conta no SUAP — Aluno, Servidor ou Prestador de Serviço.
**Quando usar:** é o ponto de partida de tudo o que diz respeito à sua conta — senha, verificação em duas etapas, notificações, aparência do sistema e saída.

1. No menu, acesse **Tec. da Informação › Usuários › Minha conta**. O mesmo endereço está em *Links úteis › Minha conta*, no rodapé de qualquer tela.

   ![Página Minha conta](usuario/minha-conta.webp)

   A página reúne, de cima para baixo:

   | Bloco | O que oferece |
   | --- | --- |
   | Barra do título | **Alterar senha** (tarefa 8), **Alterar emails** e **Sair do sistema** |
   | Atalhos em círculo | *Meus dados*, *Meus grupos*, *Minhas ações*, *Meus documentos* e *Minhas sessões* (tarefa 10) |
   | Notificações | Os interruptores de receber aviso **No Suap** e **No E-mail**, e o botão que abre as preferências detalhadas |
   | Aparência do sistema | O tema em uso, com os botões de trocar de tema e de organizar os quadros da página inicial |
   | Verificação em duas etapas | Só aparece quando a instituição habilita o recurso; é a porta da tarefa 9 |
   | Biometria | Solicitação de cadastro da digital para os terminais de ponto, quando o seu vínculo permite |
   | Coluna da direita | *Dados gerais* (nome, usuário, último login, data de registro) e o *Histórico em grupos* |

> O botão **Alterar emails** é onde se atualiza o seu **e-mail pessoal**. Vale a pena conferir se ele está certo antes de precisar dele: é para esse endereço, e nunca para o institucional, que o SUAP manda o link de troca de senha (tarefa 8).

**Ver o que você fez no sistema**

2. Nos atalhos do topo, clique em **Minhas ações**. Informe **Data de Início** e **Data de Término** e clique em **Enviar**.

**Resultado:** a lista do que a sua conta registrou no período. Sem nada no intervalo, a tela informa *"Nenhuma ação foi encontrada para o período passado."*

![Minhas ações](usuario/minhas-acoes.webp)

**Sair do sistema**

3. Na barra do título, clique em **Sair do sistema** e confirme.

**Resultado:** você volta à tela de entrada, e aquela sessão passa a constar como encerrada na listagem de sessões (tarefa 10).

> O menu **Tec. da Informação › Serviços › Webmail** não é uma tela do SUAP: é um atalho que leva ao endereço do correio eletrônico institucional configurado pela sua instituição.

---

### 8. Trocar a senha

**Quem pode:** qualquer pessoa com conta no SUAP.
**Pré-condição:** ter um **e-mail pessoal** cadastrado. O SUAP envia o link de troca só para ele — nunca para o institucional, que usa exatamente a senha que se quer trocar. Sem e-mail pessoal, o sistema leva você antes à tela de atualização de e-mail.
**Quando usar:** para trocar a senha por vontade própria, ou quando não consegue mais entrar.

**Etapa 1 — pedir o link**

1. Em **Minha conta**, clique em **Alterar senha**. A tela mostra em que endereço o e-mail vai chegar.
2. Responda o captcha e clique em **Enviar**.

   ![Solicitação de troca de senha](usuario/senha-solicitar.webp)

**Resultado:** *"Foi enviado um email para &lt;seu e-mail pessoal&gt; com as instruções para realizar a mudança de senha."* Se o e-mail não chegar, confira a caixa de spam.

**Etapa 2 — escolher a senha nova**

3. Abra o link recebido. Ele leva à tela *Efetuar mudança de senha do usuário &lt;seu usuário&gt;*.
4. Digite a **Senha** e repita em **Confirmação de senha** — o botão **Exibir a senha** revela o que você digitou. Responda o captcha e clique em **Enviar**.

   ![Cadastro da senha nova](usuario/senha-nova.webp)

**Resultado:** *"Senha alterada com sucesso."* e você volta à tela de entrada, já podendo entrar com a senha nova. **O link é de uso único:** depois de usado ele não serve mais, e uma nova troca exige pedir outro.

> Senha curta demais é recusada na hora, com a mensagem *"A senha deve ter pelo menos 10 caracteres."* A confirmação precisa ser idêntica à senha.

**Se você não consegue entrar**

5. Na tela de entrada do SUAP, clique em **Esqueceu ou deseja alterar sua senha?**.
6. Informe o **Usuário** — a matrícula, para servidor e aluno; o CPF, para prestador de serviço e usuário externo — e o **CPF/Passaporte**. Responda o captcha e clique em **Enviar**.

   ![Recuperação de senha sem estar logado](usuario/senha-esqueci.webp)

**Resultado:** o mesmo e-mail com o link, e daí em diante o caminho é o da etapa 2. Quem não tem e-mail pessoal cadastrado recebe um aviso orientando a procurar a Gestão de Pessoas (servidores) ou a secretaria acadêmica (alunos) para cadastrá-lo.

---

### 9. Ativar a verificação em duas etapas

**Quem pode:** qualquer pessoa com conta no SUAP, desde que a instituição tenha habilitado o recurso — sem isso, o bloco *Verificação em duas etapas* não aparece na Minha conta.
**Quando usar:** para que uma senha vazada não baste para entrar na sua conta. Além da senha, passa a ser pedido um código de seis dígitos que só o seu aparelho gera.

1. Em **Minha conta**, no bloco **Verificação em duas etapas**, clique em **Habilitar autenticação com dois fatores**.
2. A tela mostra um **QR Code**. Leia-o com um aplicativo autenticador no seu celular (Google Authenticator ou equivalente).
3. Digite em **Codigo** o número de seis dígitos que o aplicativo passou a exibir e clique em **Enviar**.

   ![Leitura do QR Code](usuario/2fa-habilitar.webp)

**Resultado:** *"A autenticação por Dois Fatores está habilitada."* O bloco da Minha conta muda de cara: some o botão de habilitar e aparecem o interruptor **Ativar Autenticação via Senha de Uso Unico**, o botão **Visualizar QR Code** e o **Remover autenticação com dois fatores**.

![Minha conta com a verificação ativa](usuario/2fa-minha-conta.webp)

**Trocar de aparelho:** clique em **Visualizar QR Code**, leia o código no aparelho novo, digite os seis dígitos e clique em **Enviar** — aparece *"A autenticação por Dois Fatores está ativida."*

![Revisita ao QR Code](usuario/2fa-qrcode.webp)

**Desligar:** clique em **Remover autenticação com dois fatores**. Aparece *"Autenticação com dois fatores removida com sucesso"* e a conta volta a exigir só a senha.

**Se você perdeu o aparelho**

Sem o aplicativo autenticador não há como entrar, e a remoção pelo caminho acima exige estar dentro do sistema. Nesse caso, quem administra o SUAP desliga a verificação por você:

- **Quem pode:** apenas quem administra o sistema (superusuário). Nenhum outro perfil alcança essa tela — os demais recebem "acesso negado" no mesmo endereço.
- Na listagem de usuários do sistema, a linha da pessoa com a verificação ativa traz o botão **Desabilitar 2FA**. Informe o **Motivo** e clique em **Desabilitar 2FA**.

  ![Desabilitação da verificação por quem administra](usuario/2fa-desabilitar.webp)

**Resultado:** *"Autenticação com dois fatores removida para &lt;usuário&gt;"*, e a pessoa volta a entrar apenas com a senha — podendo refazer a tarefa 9 no aparelho novo.

---

### 10. Ver e cortar os acessos à sua conta

**Quem pode:** Aluno, Servidor e Prestador de Serviço, para os **próprios** dispositivos e sessões (a listagem de sessões alcança também o Usuário Externo). Quem pertence ao grupo *Coordenador de Segurança da Informação*, e quem administra o sistema, vê os de todo mundo — com colunas e filtros a mais por usuário.
**Quando usar:** quando desconfiar de um acesso que não reconhece, ou ao deixar a conta aberta num computador emprestado.

**Etapa 1 — os dispositivos**

1. No menu, acesse **Tec. da Informação › Segurança › Dispositivos**. Cada linha é um aparelho/navegador em que a sua conta já entrou.

   ![Listagem de dispositivos](usuario/dispositivos.webp)

   | Coluna | O que mostra |
   | --- | --- |
   | Apelido | O nome que **você** deu ao aparelho |
   | Dispositivo | O que o SUAP detectou do aparelho — sistema e navegador |
   | Ativado / Situação | Se o aparelho pode abrir sessões; o que você está usando agora aparece como *Ativado - Dispositivo Atual* |
   | Opções | **Apelidar**, **Desativar** e, nos já desativados, **Reativar** |

2. Para reconhecer o aparelho depois, clique em **Apelidar** na linha dele, escreva o **Apelido** e clique em **Salvar**.

   ![Diálogo de apelido](usuario/dispositivo-apelidar.webp)

**Resultado:** *"Apelido concedido com sucesso."* O apelido passa a identificar o aparelho — inclusive na listagem de sessões da etapa 2, que mostra o apelido no lugar do nome detectado.

3. Para cortar um aparelho que você não reconhece, clique em **Desativar** na linha dele.

**Resultado:** *"Dispositivo desativado e N sessões expiradas."* — além de bloquear o aparelho, **todas as sessões abertas nele são encerradas na hora**. O botão **Reativar** desfaz o bloqueio quando você conferir que era um acesso legítimo.

> O aparelho em que você está no momento **não** oferece *Desativar*: não dá para se trancar para fora.

**Etapa 2 — as sessões**

4. No menu, acesse **Tec. da Informação › Segurança › Sessões** (ou, em Minha conta, o atalho *Minhas sessões*). A tela *Informações de Sessões* lista cada entrada no sistema, com **Dispositivo**, **Endereço IP**, **Horário do Login** e se já está **Expirada**.

   ![Listagem de sessões](usuario/sessoes.webp)

5. Na linha de uma sessão que não seja a sua, clique em **Deslogar**. Para derrubar todas de uma vez, use **Deslogar todas as outras sessões**, no alto da tela.

**Resultado:** *"Sessão remota deslogada com sucesso."* (ou *"Sessões remotas deslogadas com sucesso."*), e quem estiver usando aquela sessão é desconectado. A sessão em que você está aparece marcada como **Sessão atual** e nunca é derrubada por essas ações.

---

### 11. Consultar as senhas expostas

**Quem pode:** qualquer pessoa com conta no SUAP — Aluno, Servidor, Prestador de Serviço ou Usuário Externo — vê **os próprios** registros. Os grupos *Coordenador de Segurança da Informação* e *Coordenador de TI sistêmico* veem os de todo mundo, com a coluna e o filtro por usuário.
**Quando usar:** para saber se alguma senha ligada aos seus endereços já apareceu em vazamento conhecido.

1. No menu, acesse **Tec. da Informação › Segurança › Senhas Expostas**.

**Resultado:** uma linha por senha localizada, com o **Email/Username** em que apareceu, a **Senha**, o **Formato da Senha** e a **Data de Exposição**. Dá para restringir por texto, por formato e pela data do lado esquerdo.

![Senhas expostas](usuario/senhas-expostas.webp)

> A tela é só de consulta — não há como incluir, alterar nem excluir registro. Se uma senha sua aparecer aqui e você ainda a usa, em qualquer sistema, **troque-a imediatamente** (tarefa 8).

---

### 12. Dar e tirar o acesso de alguém: os grupos

**Quem pode:** quem **gerencia o grupo**. Não é uma permissão avulsa: o SUAP cria, para cada módulo, um grupo *&lt;Aplicação&gt; Administrador* — quem pertence a ele gerencia os grupos daquele módulo, e quem administra o sistema gerencia todos. Quando o gerenciamento é **local**, só dá para incluir e remover pessoas do seu próprio campus.
**Quando usar:** sempre que alguém precisar de uma tela que hoje não enxerga, ou deixar de precisar dela. Grupo é o que dá acesso no SUAP inteiro: é por grupo que cada um dos módulos decide o que cada pessoa vê.

**Etapa 1 — encontrar o grupo**

1. No menu, acesse **Tec. da Informação › Usuários › Gerenciamento de grupos**. A tela começa vazia: escolha o **Módulo** e clique em **Filtrar**. Os outros dois filtros — **Nome/Usuário** e o campus — restringem o resultado.
2. Os grupos do módulo aparecem como abas, cada uma com o número de pessoas dentro. Clique na aba do grupo.

   ![Gerenciamento de grupos](usuario/grupos-gerenciamento.webp)

   A tela do grupo reúne três blocos:

   | Bloco | O que mostra |
   | --- | --- |
   | É gerenciado por | Quais grupos podem incluir e remover gente **deste** grupo |
   | Usuários do grupo | Um cartão por pessoa, com vínculo, setor, matrícula, o motivo da inclusão e o último acesso |
   | Permissões Relacionadas ao Grupo | Tudo o que o grupo libera, cadastro por cadastro — é a resposta para *"o que eu estou concedendo?"* |

**Etapa 2 — incluir a pessoa**

3. Clique em **Adicionar usuário ao grupo**. Abre o diálogo *Adicionar Usuário ao Grupo*:

   | Campo | O que informar |
   | --- | --- |
   | Usuário | Uma ou mais pessoas, procuradas por parte do nome, matrícula, CPF ou e-mail institucional. Só aparecem servidores e prestadores de serviço ativos |
   | Prazo | Opcional, mas é o que evita acesso esquecido: no fim do prazo, a pessoa sai do grupo sozinha no próximo acesso dela ao sistema |
   | Motivo | Obrigatório — fica registrado no histórico e aparece no cartão da pessoa |
   | Confirmação | Caixa de marcação obrigatória: você declara que conferiu que as atribuições do grupo correspondem à responsabilidade da pessoa |

   ![Inclusão de um usuário no grupo](usuario/grupo-adicionar-usuario.webp)

4. Clique em **Enviar**.

**Resultado:** *"Usuário(s) adicionado(s) com sucesso."* A pessoa passa a ter o cartão dela na aba do grupo, com o motivo que você escreveu — e passa a enxergar, no próximo acesso, as telas que o grupo libera.

> Quando o grupo tem uma **automatização** ativa (tarefa 13), o campo *Prazo* deixa de ser opcional.

**Etapa 3 — acompanhar e remover**

5. No cartão da pessoa, **Histórico** abre a lista de todas as entradas e saídas dela em grupos, com data, motivo e quem fez.

   ![Histórico de grupos do usuário](usuario/grupo-historico.webp)

6. Ainda no cartão, **Remover deste Grupo** desfaz o acesso.

**Resultado:** *"Usuário foi removido do grupo &lt;grupo&gt; com sucesso."* A pessoa perde, a partir do próximo acesso, tudo o que aquele grupo liberava.

> **Antes de conceder, confira o que o grupo abre.** O botão **Menus do grupo**, na barra de ações da aba, traduz as permissões do grupo na lista dos itens de menu que ele destrava — caminho por caminho.
>
> ![Menus visíveis para o grupo](usuario/menus-do-grupo.webp)

---

### 13. Automatizar a entrada num grupo por setor

**Quem pode:** quem gerencia o grupo (mesma regra da tarefa 12).
**Quando usar:** quando o acesso não é de uma pessoa, e sim de um **posto**: todo mundo lotado em determinados setores — opcionalmente só quem ocupa determinado cargo — deve estar no grupo.

1. Na aba do grupo (tarefa 12, etapa 1), clique em **Automatizar grupo em setores**. A tela lista as regras que já existem; na primeira vez, informa *"Não existem automatizações do grupo"*.

   ![Automatizações do grupo](usuario/automatizacao-listagem.webp)

2. Clique em **Adicionar automatização a grupo**. Escolha os **Setores** (um ou vários) e, se quiser restringir mais, o **Cargo emprego**. Clique em **Continuar**.

   ![Escolha dos setores da regra](usuario/automatizacao-formulario.webp)

3. O segundo passo é a **análise de impacto**: antes de a regra valer, a tela diz nominalmente quem **será adicionado**, quem **permanecerá** e quem **será removido** do grupo — na ilustração abaixo, só a última lista tem gente. Leia, marque **Confirma operação?** e clique em **Finalizar**.

   ![Análise de impacto da automatização](usuario/automatizacao-impacto.webp)

**Resultado:** *"Automatização de grupo em setores realizada com sucesso."* A regra passa a constar na listagem, com os setores, o cargo e quem a criou — e o botão **Alterar**, que reabre a regra para acrescentar setores ou desligá-la, passando de novo pela análise de impacto.

> **A regra age sozinha, e nos dois sentidos.** A cada acesso de uma pessoa ao SUAP, quem passou a se encaixar entra no grupo e **quem deixou de se encaixar sai dele** — sem ninguém aprovar caso a caso. É por isso que a confirmação do passo 3 existe: uma regra errada tira o acesso de um campus inteiro, e o efeito aparece aos poucos, à medida que cada pessoa entra no sistema.

---

### 14. Ver em que grupos você está (e sair de um)

**Quem pode:** qualquer pessoa com conta no SUAP, para os próprios grupos. Quem gerencia um grupo também abre a lista das outras pessoas, pelo cartão delas (tarefa 12).
**Quando usar:** para entender por que você enxerga (ou não enxerga) determinada tela, e para abrir mão de um acesso que você não usa mais.

1. Em **Minha conta**, nos atalhos em círculo do topo, clique em **Meus grupos**.

   ![Meus grupos](usuario/meus-grupos.webp)

   A tabela tem uma linha por grupo, agrupada por **Módulo** — é a lista de tudo o que a sua conta pode fazer no SUAP.

2. Para sair de um grupo, clique em **Remover do grupo** na linha dele.

**Resultado:** *"Usuário foi removido do grupo &lt;grupo&gt; com sucesso."*, e você volta à Minha conta.

> **Sair é imediato e não se desfaz sozinho.** Você perde todas as telas que aquele grupo liberava, e só quem gerencia o grupo pode devolvê-lo (tarefa 12). Na dúvida, confira antes o que o grupo abre.

---

### 15. Escolher por onde receber as notificações

**Quem pode:** qualquer pessoa com conta no SUAP — Aluno, Servidor, Prestador de Serviço ou Usuário Externo.
**Quando usar:** quando um tipo de aviso estiver chegando demais (ou de menos) no seu e-mail.

1. No menu, acesse **Tec. da Informação › Usuários › Notificações › Preferências**. Cada linha é um **assunto** sobre o qual o SUAP já lhe mandou aviso, com os dois canais possíveis: **Via SUAP** (o sininho da página inicial) e **Via E-mail**.

   ![Preferências de notificação](usuario/preferencias-notificacao.webp)

2. Na linha do assunto, use **Desativar Envio via E-mail** ou **Desativar Envio via SUAP** — e os equivalentes *Ativar* para voltar atrás. Para mudar vários assuntos de uma vez, marque as linhas, escolha a **Ação** e clique em **Aplicar**.

**Resultado:** *"Preferência atualizada com sucesso."*, e a linha passa a mostrar o novo estado de cada canal. Os filtros *Via SUAP* e *Via E-mail*, à esquerda, mostram rapidamente o que está desligado.

> **Não dá para desligar os dois canais do mesmo assunto.** Com um já desligado, o SUAP recusa o outro: *"Não é possível inativar as duas formas de Notificação."* — senão o aviso simplesmente deixaria de existir, sem ninguém perceber. A ação em massa segue a mesma regra: ela pula as linhas que ficariam sem canal nenhum.

> Os botões **Desativar Envio Padrão via SUAP** e **Desativar Envio Padrão via E-mail**, no alto da tela, são outra coisa: eles valem para os assuntos **novos**, que você ainda não recebeu. São os mesmos interruptores do bloco *Notificações* da Minha conta (tarefa 7).

---

### 16. Desligar uma categoria de notificação para todo mundo

**Quem pode:** o perfil *Coordenador de TI sistêmico*.
**Quando usar:** quando um aviso do sistema perdeu o sentido, ou está sendo disparado indevidamente, e a correção não pode esperar — desligar a categoria vale para **todas as pessoas** de uma vez, e não só para você.

1. No menu, acesse **Tec. da Informação › Usuários › Notificações › Categorias**. A listagem traz o **Assunto**, quantas **Notificações** já foram geradas e se a categoria está **Ativa**.

   ![Categorias de notificação](usuario/categorias-notificacao.webp)

2. Na linha da categoria, clique em **Desativar** (ou **Ativar**, para religar).

**Resultado:** *"A Categoria de Notificações foi desativada com sucesso."* A categoria some da tela de preferências (tarefa 15) de todo mundo e o SUAP para de mandar aquele aviso — por isso é a diferença entre *"esta pessoa não quer receber"* e *"o sistema parou de mandar"*.

---

### 17. Anunciar uma parada programada do sistema

**Quem pode:** o perfil *Coordenador de TI sistêmico* cadastra. **Consultar** o que está por vir é de qualquer pessoa com conta — Aluno, Servidor, Prestador de Serviço ou Usuário Externo —, que vê a mesma tela apenas com as próximas paradas.
**Quando usar:** antes de qualquer indisponibilidade prevista — atualização de versão, manutenção preventiva, correção. É o que faz o aviso aparecer para quem usa o sistema, em vez de a tela simplesmente cair.

1. No menu, acesse **Tec. da Informação › Desenvolvimento › Cadastros › Manutenções Programadas** e clique em **Adicionar Manutenção Programada**.
2. Preencha o formulário, dividido em três blocos — *Dados gerais*, *Público da Manutenção Programada* e *Dados Extras*:

   | Campo | O que informar |
   | --- | --- |
   | Tipo | *Adição de Funcionalidades*, *Manutenção Preventiva* ou *Correção de Bugs* |
   | Sistema ou servico | O que vai parar. É o nome que aparece no aviso lido por quem usa o sistema |
   | Data da atualização | Quando a parada acontece |
   | Previsão de minutos de inatividade | Quanto tempo o serviço deve ficar fora |
   | Motivo | O texto que explica a parada |
   | Público e Unidade Organizacional | Restringem o aviso. **Deixados em branco, a parada é avisada a todo mundo**; só é possível escolher um campus junto com um público |
   | Data de início notificação | A partir de quando o aviso aparece. É o que separa "cadastrei" de "as pessoas estão vendo" |
   | Equipe de manutenção | Obrigatório: quem responde pela parada |
   | Efetivos minutos de inatividade | Preenchido **depois**, para registrar quanto tempo a parada realmente durou |

   ![Cadastro da parada programada](usuario/manutencao-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."* A partir da data de início da notificação, a parada entra no aviso **Fique atento!** da página inicial de quem se encaixa no público escolhido. A listagem identifica cada parada por tipo, data, previsão e motivo — o nome do serviço aparece na ficha e no aviso, não na lista.

![Listagem de paradas programadas](usuario/manutencoes-listagem.webp)

---

### 18. Administrar as contas de usuário

**Quem pode:** abrir a listagem exige o perfil *Coordenador de TI sistêmico*; as ações em massa exigem estar em *Coordenador de TI de campus* ou *Coordenador de TI sistêmico* — ou administrar o sistema.
**Quando usar:** ao desligar alguém, ao responder a um incidente de segurança, ou para obrigar a troca de uma senha comprometida.

1. No menu, acesse **Tec. da Informação › Usuários › Usuários**. Procure a pessoa pelo campo de texto (matrícula, nome ou e-mail) ou pelos filtros da esquerda — **campus**, **setor**, **grupos**, **vínculo**, se está **ativo**, se tem **2FA**, por **tema** e por **tipo de notificação**.

   ![Listagem de usuários](usuario/usuarios-listagem.webp)

2. Marque a linha da pessoa, escolha a **Ação** e clique em **Aplicar**:

   | Ação | O que faz |
   | --- | --- |
   | Forçar troca de senha no próximo login | A pessoa continua entrando normalmente, mas é obrigada a definir uma senha nova antes de seguir |
   | Desfazer a troca de senha no próximo login | Cancela a exigência acima |
   | Desabilitar usuário | Suspende a conta: a pessoa deixa de conseguir entrar |
   | Habilitar usuário | Devolve o acesso |
   | Sincronizar usuário no AD | Reenvia os dados da conta ao serviço de diretório, quando a instituição usa um |

**Resultado:** *"Procedimento realizado com sucesso."*, e a coluna correspondente da listagem passa a refletir o novo estado.

> A mesma listagem é a porta de **desligar a verificação em duas etapas** de quem perdeu o aparelho (tarefa 9) — mas esse botão é só de quem administra o sistema.

---

### 19. Ajustar os parâmetros do sistema

**Quem pode:** o painel de administração exige permissão de gerenciar as extrações SIAPE ou SCDP — na prática, os perfis *Coordenador de TI sistêmico*, *Coordenador de Gestão de Pessoas Sistêmico*, *Gerenciador de Extração SIAPE* e *Gerenciador de Extração SCDP*. Já a **Configuração do Sistema** é de quem administra o sistema ou pertence ao grupo *&lt;Aplicação&gt; Configurador* do módulo que quer configurar — e, nesse caso, só as abas daquele módulo aparecem.
**Quando usar:** ao pôr o SUAP em operação, e sempre que uma regra de um módulo depender de um valor da instituição (prazos, setores responsáveis, modelos de documento, integrações).

1. Abra a *Administração do SUAP*, no endereço **/comum/admin/** — ela não tem entrada de menu. É o índice das ferramentas de manutenção, reunidas em *Configurações*, *Usuários e grupos*, *Acesso Rápido*, *SIAPE e SCDP* e um resumo das *Preferências de Usuários* (quais temas as pessoas usam e por quais canais recebem aviso).

   ![Painel de administração do SUAP](usuario/painel-administracao.webp)

2. Clique em **Configurações SUAP**. A tela traz uma aba por módulo que tem o que configurar — perto de cinquenta.

   ![Configuração do Sistema](usuario/configuracao-sistema.webp)

3. Abra a aba do módulo, ajuste os campos e clique em **Enviar**.

   ![Configuração de um módulo](usuario/configuracao-aplicacao.webp)

**Resultado:** *"Configuração salva com sucesso."* O valor passa a valer para **toda a instituição**, imediatamente e para todas as pessoas — não existe configuração por usuário aqui.

> **Excluir registro no SUAP pede a sua senha.** Boa parte das telas do sistema, ao remover, leva à *Confirmação de Exclusão*: ela lista o que será apagado e só conclui depois de você digitar a **senha para confirmação** — a sua, a mesma com que entrou. É o segundo fator que separa a remoção de um clique acidental.
>
> ![Confirmação de exclusão](usuario/confirmacao-exclusao.webp)

---

### 20. Assinar um documento digitalmente

**Quem pode:** *Reitor* e *Diretor Geral* — são os perfis que veem o serviço de **Assinatura Digital** no menu e os únicos que abrem as telas de **assinar** e de **verificar** a assinatura. Cada pessoa trabalha **só com os próprios certificados**: o que você guardar aqui ninguém mais vê, e o que outra pessoa guardou não aparece para você.
**Pré-condição:** ter um **certificado digital A1** em arquivo (`.p12` ou `.pfx`) e a senha dele. Certificado em cartão ou token (A3) não serve para esta tela — para esse caso existe a assinatura em nuvem, descrita na nota ao fim da tarefa.
**Quando usar:** quando o documento precisa sair assinado de forma que quem o receber possa conferir a assinatura sozinho, inclusive sem ter conta no SUAP.

**Etapa 1 — guardar o seu certificado no SUAP**

1. No menu, acesse **Tec. da Informação › Serviços › Assinatura Digital › Certificados Digitais** e clique em **Adicionar Certificado Digital**.

   ![Certificados digitais guardados](usuario/certificados-listagem.webp)

2. O formulário pede **duas** coisas, e só: o **Arquivo** do certificado (até 10 MB) e a **Senha do Certificado**. Clique em **Salvar**.

   ![Cadastro do certificado digital](usuario/certificado-formulario.webp)

**Resultado:** o cadastro aparece na listagem já preenchido — **Nome**, **Organização**, **Unidade Organizacional** e **Validade** são lidos de dentro do próprio arquivo, nenhum deles é digitado. A senha **não fica guardada**: ela serve só para abrir o arquivo na hora do cadastro, e será pedida de novo a cada assinatura.

> **Certificado vencido continua no cadastro, mas não assina.** Ele permanece na listagem, com a data de validade à mostra, e simplesmente deixa de ser oferecido na tela de assinatura. Se o seu certificado não aparece lá, é aqui que se confere o porquê.

**Etapa 2 — assinar o PDF**

3. No menu, acesse **Tec. da Informação › Serviços › Assinatura Digital › Assinar Documento**. Envie o **Arquivo PDF**, escolha o **Certificado** — a lista traz apenas os seus, e apenas os dentro da validade, identificados por *nome – organização – (VÁLIDO ATÉ …)* — e digite a **Senha do Certificado**. Clique em **Enviar**.

   ![Formulário de assinatura](usuario/assinar-formulario.webp)

   O PDF é exibido na própria tela com os botões *Página anterior* e *Próxima página*: arraste o carimbo até onde ele deve sair impresso. É opcional — sem arrastar nada, o carimbo vai para a posição padrão da primeira página.

**Resultado:** o navegador recebe de volta **o mesmo PDF, agora assinado**. É esse arquivo que deve ser enviado adiante; o original sem assinatura não serve. O carimbo impresso traz um QR code que aponta para a tela pública de validação (veja *Para o público externo*, no fim deste guia).

**Etapa 3 — conferir um PDF que você recebeu**

4. No menu, acesse **Tec. da Informação › Serviços › Assinatura Digital › Verificar Assinatura**, envie o **Arquivo** e clique em **Enviar**.

**Resultado:** *"Documento assinado digitalmente por &lt;nome&gt;."* Se o arquivo não tiver assinatura reconhecível, a resposta é *"Assinatura digital não identificada."* — e aí o documento não vale como assinado. Para conferir não é preciso ter certificado nenhum, só um dos dois perfis acima.

![Conferência da assinatura](usuario/verificar-assinatura.webp)

> **Assinatura em nuvem (ICP EDU).** O menu traz também **Assinar Documento (ICP EDU)**, que assina com um certificado guardado no serviço da rede acadêmica, sem arquivo nem senha local. Ele depende de contrato da instituição: onde o serviço não está ligado, a tela responde *"O serviço de assinatura ICP EDU está temporariamente indisponível"* em vez de abrir o formulário. O acesso a essa tela não vem de nenhum perfil padrão do SUAP — é concedido pessoa a pessoa.

---

### 21. Despachar uma solicitação de documento funcional

**Quem pode:** *Confeccionador de Documentos*, *Coordenador de Gestão de Pessoas* e *Coordenador de Gestão de Pessoas Sistêmico*. Abrir a listagem e acompanhar um pedido é mais amplo — qualquer *Servidor* consegue, e por isso cada pessoa vê ali o próprio pedido; **atender e rejeitar** são só desses três perfis.
**Pré-condição:** o campus precisa ter uma **Configuração de Impressão de Documento** (veja *Telas de apoio*). Sem ela, a listagem abre vazia mesmo para a Gestão de Pessoas: o que cada campus enxerga é definido por essa configuração.
**Quando usar:** ao despachar os pedidos de crachá e de carteira funcional dos servidores.

1. No menu, acesse **Gestão de Pessoas › Administração de Pessoal › Solicitações › Documentos › Solicitações**. Os filtros do topo — *Texto*, *Tipo de Documento*, *Campus* e *Situação da Solicitação* — são o caminho normal de trabalho: filtrar por **Não Atendida** é a fila do dia.

   ![Fila de solicitações de documento](usuario/documentos-solicitacoes-listagem.webp)

   Cada linha traz a foto, os dados do solicitante e, na coluna *Ações*, os botões **Marcar como Atendida**, **Rejeitar Solicitação** e **Imprimir** — este último só para os tipos que o SUAP imprime (crachá e carteira funcional).

   O botão **Adicionar Solicitação de Documento**, no alto, é por onde a Gestão de Pessoas abre um pedido em nome de um servidor; o formulário muda conforme o tipo de documento e não é descrito neste guia.

2. Antes de decidir, clique no **ícone de exibição** da linha para abrir o pedido.

   ![Solicitação e seu histórico](usuario/solicitacao-acompanhamento.webp)

   A tela reúne o **Histórico da Solicitação** — uma linha por mudança de situação, com justificativa, responsável e data — e os **Dados do Solicitante**. É essa trilha que justifica o despacho meses depois.

3. Para **atender**, clique em **Marcar Solicitação como Atendida** e confirme.

**Resultado:** *"Solicitação atendida com sucesso."* A situação passa a *Atendida*, o histórico ganha a linha do despacho e uma eventual solicitação anterior do mesmo tipo é desativada.

4. Para **recusar**, volte à listagem e clique em **Rejeitar Solicitação** na linha do pedido. Abre-se uma janela pedindo o **Motivo**; escreva-o e clique em **Salvar**.

   ![Rejeição com motivo](usuario/solicitacao-rejeitar.webp)

**Resultado:** *"Solicitação rejeitada com sucesso."* A situação passa a *Rejeitada* e o motivo fica gravado no histórico — é o que o servidor vai ler ao acompanhar o próprio pedido.

> Atender e rejeitar são de **mão única**: valem enquanto a situação for *Não Atendida*. Depois disso os dois botões somem da linha, e um novo pedido precisa ser aberto.

---

### 22. Acompanhar os documentos que o sistema emitiu

**Quem pode:** *Meus documentos* é de qualquer pessoa com conta. Já os **Registros de Emissão** exigem uma permissão que **nenhum perfil padrão do SUAP concede** — o acesso é atribuído individualmente, normalmente a quem administra o sistema.
**Quando usar:** para reemitir uma via, conferir o que já foi emitido em nome de alguém ou **cancelar** um documento que não deve mais valer.

**Etapa 1 — os seus documentos**

1. Em **Minha conta** (tarefa 7), clique no atalho **Meus documentos**.

**Resultado:** o índice dos documentos que você pode emitir, agrupado por área do sistema. Quando não há nenhum, a tela informa *"Não há documentos."*

![Meus documentos SUAP](usuario/meus-documentos.webp)

**Etapa 2 — a trilha de tudo o que foi emitido**

2. No menu, acesse **Documentos/Processos › Autenticação de Documentos › Registros de Emissão**. Cada linha é um documento emitido: **Tipo de Documento**, **Data de Emissão**, **Código Verificador** (o mesmo impresso no rodapé do papel), a **Referência** ao registro que o originou e se está **Cancelado**. As abas separam **Vencidos**, **À vencer** e **Permanentes**, com a contagem de cada uma.

   ![Registros de emissão de documento](usuario/registros-emissao.webp)

3. Para invalidar um documento já entregue, marque a caixa da linha, escolha **Cancelar** na lista *Ação* e clique em **Aplicar**.

**Resultado:** a coluna *Cancelado* passa a indicar o cancelamento, e quem tentar autenticar aquele código na tela pública (veja *Para o público externo*) recebe o aviso de que o documento foi cancelado pela instituição, em vez da autenticação.

---

### 23. Achar um ramal e manter os telefones de um setor

**Quem pode:** consultar a lista é de qualquer perfil com permissão de consultar servidor — na prática, quase todo mundo com conta. **Manter** os telefones e o e-mail de um setor é de *Coordenador de Gestão de Pessoas*, *Coordenador de Gestão de Pessoas Sistêmico*, *Operador de Gestão de Pessoas*, *Operador de Gabinete* e *Operador de Gabinete Sistêmico* — **ou de quem chefia aquele setor**, que pode cuidar do próprio sem nenhuma dessas atribuições.
**Quando usar:** é a lista telefônica da instituição, e a tela mais visitada por quem não usa o SUAP para mais nada.

1. No menu, acesse **Administração › Telefones**. Os setores vêm agrupados por campus, com os números e o ramal de cada um; a coluna da direita tem âncoras para saltar direto ao campus. **Exportar CSV**, na barra de ações, baixa a mesma lista em planilha.

   ![Lista telefônica](usuario/telefones-lista.webp)

2. Para corrigir um número, clique no **nome do setor** — o link abre a página dele — e depois em **Editar Telefones**.

3. A tela mostra os **Telefones cadastrados**, cada linha com o botão **Remover**, e abaixo o bloco **Adicionar novo telefone**. Informe o **Número telefônico** no formato `(99) 99999-9999`, o **Ramal** e uma **Observação** opcional; clique em **Enviar**.

   ![Telefones de um setor](usuario/setor-telefones.webp)

   O **Ramal é obrigatório**, inclusive para setores que só têm ramal e nenhum número externo — é por ele que a lista é organizada.

**Resultado:** *"Telefone adicionado com sucesso."*, e o número passa a aparecer na lista telefônica imediatamente. **Remover não pede confirmação**: o clique apaga o telefone.

4. Na mesma página do setor, **Editar E-mail** grava o endereço institucional do setor — é para ele que o SUAP manda o que é do setor e não de uma pessoa.

**Resultado:** *"E-mail editado com sucesso."*

---

### 24. Usar a página inicial

**Quem pode:** qualquer pessoa com conta no SUAP — é a primeira tela que aparece depois da entrada.
**Quando usar:** todo dia. A página inicial é o painel do sistema: o que está por vir, o que espera por você e as portas para as telas do seu trabalho.

1. Entre no SUAP. A qualquer momento dá para voltar a ela por **Início**, no alto do menu lateral.

   ![Página inicial](usuario/inicio-pagina.webp)

   A tela tem três partes:

   | Parte | O que traz |
   | --- | --- |
   | Faixa do topo | O aviso que a instituição publica para todo mundo. Uma parada programada (tarefa 17) aparece aqui com o sistema afetado, o dia, a hora e a duração prevista |
   | Coluna da esquerda | **Fique atento!**, com o que está por vir, e **Minhas pendências**, com o que espera por você |
   | Quadros | Um bloco por assunto — *Atalhos*, *Calendário Administrativo*, *Gestão de Pessoas*, *Processos Eletrônicos*, *Frequências*, *Central de Serviços*… Cada pessoa vê os quadros das áreas a que tem acesso, então duas pessoas quase nunca veem a mesma página inicial |

2. **Minhas pendências** lista o que está parado à sua espera, com o link para resolver.

   ![Minhas pendências de quem avalia reservas de sala](usuario/inicio-pendencias.webp)

   *A caixa só existe para quem tem algo a responder: quem não avalia reserva de sala não vê esta linha — nem a caixa.*

**Deixar a página do seu jeito**

3. Para tirar um quadro da sua página inicial, clique no ícone de ações dele — o menu traz **Reposicionar quadro** e **Esconder quadro** — e escolha **Esconder quadro**. O quadro sai da coluna na hora, e só da **sua** página inicial.

   ![Ações de um quadro](usuario/inicio-acoes-do-quadro.webp)

4. Escondeu e se arrependeu? Na barra de botões do rodapé da página inicial, clique em **Quadros**. A janela *Gerenciar Quadros* lista os quadros escondidos — pelo nome em caixa alta. Marque o que quer de volta e clique em **Exibir**.

   ![Gerenciar Quadros](usuario/inicio-gerenciar-quadros.webp)

**Resultado:** *"Atualização exibida com sucesso."*, e o quadro volta ao seu lugar. A mesma janela é aberta pelo botão **Gerenciar quadros do Início**, na *Minha conta* (tarefa 7).

---

### 25. Acompanhar as suas notificações

**Quem pode:** qualquer pessoa com conta — Aluno, Servidor, Prestador de Serviço ou Usuário Externo.
**Quando usar:** sempre que o sino do menu lateral mostrar um número. É por ele que o SUAP conta o que aconteceu com os seus pedidos, documentos e prazos.

1. Clique no **sino**, no alto do menu lateral; o número ao lado dele é quanto você ainda não leu. O mesmo endereço está em **Tec. da Informação › Usuários › Notificações › Notificações**.

   ![Caixa de notificações](usuario/notificacoes-caixa.webp)

   A tela lista as **não lidas**, da mais recente para a mais antiga. A primeira já abre lida: o SUAP a marca no próprio carregamento da página — por isso o número do sino costuma cair de um assim que você entra aqui.

2. Clique no assunto para abrir a mensagem.

   ![Mensagem aberta](usuario/notificacoes-mensagem.webp)

   Os botões à direita de cada linha:

   | Botão | O que faz |
   | --- | --- |
   | Olho | Marca aquele aviso como lido — ou como não lido, para voltar a ele depois |
   | **SUAP** e **E-mail**, em vermelho | Desligam o canal **para aquele assunto**; é a mesma preferência da tarefa 15, alcançada da linha do aviso que incomodou |
   | Lixeira | Remove o aviso |

3. **Todas as notificações**, na barra do topo, abre a lista completa — inclusive o que já foi lido —, com filtros por *Lida?* e por *Assunto*, busca por texto e as ações em massa *Marcar como lida*, *Marcar como não lida* e *Remover*.

   ![Lista completa das notificações](usuario/notificacoes-todas.webp)

4. Para limpar a caixa: **Marcar todas como lidas** zera o contador de uma vez, e **Remover N notificações antigas** apaga o que está lido **há mais de um mês** — e só isso; o que é recente fica.

   ![Limpeza da caixa](usuario/notificacoes-faxina.webp)

**Resultado:** *"Todas as suas notificações foram marcadas como lida com sucesso."* e, na limpeza, *"Todas as suas notificações lidas há mais de um mês foram excluídas."*

> **Nem todo aviso pode ser lido ou removido na hora.** Alguns ficam bloqueados por alguns dias — é o caso do alerta de acesso a partir de um dispositivo novo (tarefa 10) —, e a própria linha informa *Desbloqueio para leitura* e *Desbloqueio para remoção*, com a data.

> Quem só quer decidir **por onde** cada assunto chega — no SUAP, no e-mail ou nos dois — vai direto a **Preferências de recebimento**, também na barra do topo (tarefa 15).

---

### 26. Mudar a aparência do sistema

**Quem pode:** qualquer pessoa com conta no SUAP. As duas telas estão no rodapé, em *Links úteis*, de qualquer página do sistema.
**Quando usar:** para trabalhar mais confortável — tema claro ou escuro, alto contraste, mais espaço na tela.

1. No rodapé, clique em **Temas** (ou acesse **Tec. da Informação › Usuários › Temas**). A galeria mostra cada tema com a descrição, uma miniatura da tela e quantas pessoas o usam; o seu vem marcado como **Selecionado**.

   ![Galeria de temas](usuario/temas-galeria.webp)

   | Bloco | Temas |
   | --- | --- |
   | Gerais | Aurora, Dunas, Luna e Padrão |
   | Padrões do Governo | Gov.br e IFs |
   | Acessibilidade | Alto Contraste e Modo Daltonismo |

2. Clique em **Selecionar**, na caixa do tema escolhido.

**Resultado:** *"Tema alterado para "Dunas" com sucesso."* — e a mudança vale para **todo** o SUAP, não só para esta tela. A escolha fica gravada na sua conta e continua valendo no próximo acesso.

![Tema Dunas aplicado](usuario/tema-dunas.webp)

3. Ainda no rodapé, **Acessibilidade** reúne o tema **Alto Contraste**, pensado para baixa visão, e a lista das **teclas de acesso** — atalhos de teclado para o conteúdo (1), a busca (2), o menu principal (3), a página inicial (4), o rodapé (5), a saída (6), esta própria tela (7) e a abertura de chamado (8).

   ![Acessibilidade](usuario/acessibilidade.webp)

4. Para ganhar espaço, clique na **seta na borda do menu lateral**: a barra se recolhe e as telas seguintes continuam assim. A mesma seta a traz de volta.

   ![Menu lateral retraído](usuario/inicio-menu-retraido.webp)

> Diferente do tema, o menu recolhido não acompanha a sua conta: ele vale enquanto durar este acesso ao SUAP.

---

### 27. Guardar atalhos para as telas que você mais usa

**Quem pode:** qualquer pessoa com conta no SUAP.
**Quando usar:** quando uma tela faz parte da sua rotina e o caminho até ela pelo menu é longo.

1. Abra a tela que quer guardar e, na barra de botões do rodapé da página, clique em **Adicionar atalho**.
2. Dê um **Nome** ao atalho e clique em **Salvar**. O endereço não se digita: é o da tela em que você estava — por isso o atalho se cria **de dentro** dela, e não de um cadastro à parte.

   ![Adicionar atalho](usuario/atalho-cadastrar.webp)

**Resultado:** *"Atalho cadastrado com sucesso"*, e ele passa a aparecer no quadro **Atalhos** da página inicial, a um clique de distância.

![Quadro Atalhos na página inicial](usuario/inicio-quadro-atalhos.webp)

3. No próprio quadro, **Gerenciar atalhos** abre a lista dos seus atalhos: o ícone de edição renomeia, e a barra de **Ação** exclui os que forem marcados.

   ![Meus atalhos](usuario/atalhos-listagem.webp)

---

### 28. Cadastrar um usuário externo

**Quem pode:** vários perfis de gestão concedem essa permissão — entre eles *Coordenador de Gestão de Pessoas* (e o sistêmico), *Gerente de Usuário Externo*, *Gerenciador de Prestador de Serviço*, *Coordenador da Administração*, as coordenações de Estágio, Extensão, Contrato e Convênios, e também quem **chefia um setor**.
**Quando usar:** quando alguém que não é servidor nem aluno — terceirizado, bolsista, colaborador de convênio, estagiário de empresa, pensionista — precisa entrar no SUAP para tramitar processo, assinar documento ou ter crachá.

1. No menu, acesse **Administração › Cadastros › Usuários Externos › Usuários Externos** e clique em **Adicionar Usuário Externo**. A listagem procura por **Texto** (nome, CPF ou matrícula) e filtra por campus, setor, se é estrangeiro, se já é usuário externo e se está ativo.

   ![Listagem de usuários externos](usuario/externos-listagem.webp)

2. Preencha os dois quadros — *Dados gerais* e *Dados extras* — e clique em **Salvar**.

   ![Cadastro de usuário externo](usuario/externo-cadastro.webp)

   | Campo | Por que importa |
   | --- | --- |
   | Perfil | A que título a pessoa entra no SUAP. A lista vem de um cadastro à parte (*Perfis para Usuários Externos*); enquanto ele estiver vazio, o campo fica vazio e o cadastro não conclui |
   | Nacionalidade | Decide qual documento é exigido: brasileiro exige **CPF**, estrangeiro exige **Nº do Passaporte** |
   | CPF | Não pode repetir o de outro usuário externo — é por ele que o SUAP reconhece que se trata da mesma pessoa |
   | Email Pessoal | É para onde vão as instruções de acesso, e é repetido no campo seguinte para evitar erro de digitação. Endereço institucional costuma ser recusado aqui — ele usa a mesma senha do SUAP —, e a instituição escolhe se aceita ou não |
   | Nome Usual | O nome que aparece nas telas. No cadastro novo a lista está vazia: as combinações são montadas a partir do nome de registro e só ficam disponíveis na edição |
   | Ativo | Desmarcado, a pessoa fica cadastrada e sem conseguir entrar |

**Resultado:** *"Usuário Externo cadastrado com sucesso"*, e a tela avisa que foi enviado um e-mail com as instruções de acesso para o endereço informado. A pessoa já existe no SUAP, com vínculo e usuário — mas ainda **sem ocupação**, que é o que a tarefa 29 resolve.

---

### 29. Vincular (e encerrar) a ocupação do usuário externo

**Quem pode:** os mesmos perfis da tarefa 28 — a tela exige permissão de editar usuário externo.
**Quando usar:** logo depois do cadastro, e de novo a cada renovação de contrato. Enquanto não há ocupação, a própria ficha avisa: *"Este usuário não tem nenhuma ocupação associada e, por isso, não pode utilizar algumas funcionalidades do Suap."*

**Etapa 1 — vincular**

1. Na listagem de usuários externos, clique no **ícone de exibição** da linha da pessoa para abrir a ficha dela.

   ![Ficha sem ocupação](usuario/externo-ficha-sem-ocupacao.webp)

2. No quadro **Ocupações**, clique em **Vincular ocupação**. A janela pede cinco dados: **Ocupação**, **Pessoa Jurídica** (a empresa ou o órgão de origem), **Data de início**, **Data fim** e **Setor suap**.

   ![Vincular ocupação](usuario/externo-ocupacao.webp)

**Resultado:** *"Ocupação vinculada com sucesso."* A ficha passa a marcar **É prestador de serviço**, a ocupação aparece na tabela com a situação *Ativa*, e o **Setor SUAP da pessoa é atualizado** para o setor da ocupação — é a própria tela que avisa isso. A partir daqui a pessoa conta como prestador de serviço para o processo eletrônico e para a assinatura de documentos.

![Ficha com a ocupação vinculada](usuario/externo-ficha.webp)

**Etapa 2 — encerrar**

3. Na linha da ocupação, em *Opções*, clique em **Encerrar ocupação**, digite a **sua** senha do SUAP e clique em **Enviar**.

   ![Encerrar ocupação](usuario/externo-encerrar-ocupacao.webp)

**Resultado:** *"Ocupação encerrada com sucesso."* Encerrar **não apaga** a ocupação: recua a *Data Fim* para ontem e a situação passa a *Inativa*. O registro continua no histórico porque os documentos já assinados sob aquele vínculo precisam continuar tendo a que se referir.

> A data fim que você informa na etapa 1 já encerra a ocupação sozinha quando chega. O botão existe para o encerramento **antecipado** — contrato rescindido, bolsa interrompida.

---

### 30. Ligar e desligar o acesso de um usuário externo

**Quem pode:** *Coordenador de TI sistêmico*. A criação do papel de acesso é também do *Gerente de Usuário Externo*. Repare que aqui não basta ter permissão de editar usuário externo: os botões só aparecem para quem está nesses grupos — por isso a coluna *Opções* mostra coisas diferentes para cada perfil.
**Quando usar:** ao liberar o primeiro acesso de alguém já cadastrado, ao suspender a conta de quem saiu, e ao devolvê-la quando o contrato é renovado.

1. Abra **Administração › Cadastros › Usuários Externos › Usuários Externos** e localize a pessoa. Todas as ações ficam na coluna **Opções**, à direita.

   ![Opções da linha do usuário externo](usuario/externo-opcoes.webp)

   | Botão | O que faz |
   | --- | --- |
   | Criar papel de Usuário Externo | Dá à pessoa o papel que a habilita a usar o SUAP como usuário externo. Some da linha depois de criado |
   | Inativar usuário | Suspende a conta: a pessoa deixa de conseguir entrar |
   | Ativar usuário | Devolve o acesso |
   | Vincular ocupação | O mesmo da tarefa 29, a partir da listagem |
   | Alterar foto | O mesmo da tarefa 31 |

**Resultado:** *"Papel de Usuário Externo Criado com Sucesso."*, *"Usuário Externo Desativado com Sucesso."* ou *"Usuário Externo Ativado com Sucesso."*, e a coluna **Ativo** da listagem passa a refletir o novo estado.

> Desativar aqui derruba o **login** da pessoa, não só a marca de ativo — é a diferença entre um cadastro encerrado no papel e um cadastro encerrado de fato. A coluna *Tipos de Login* diz por onde cada pessoa entra: pelo SUAP (quem tem ocupação ativa) e/ou pelo Gov.BR (quem tem CPF e papel de usuário externo).

---

### 31. Manter o cadastro de um usuário externo: foto e e-mail

**Quem pode:** a foto exige permissão de editar usuário externo; o **e-mail**, uma permissão específica de editar o e-mail de usuário externo — *Coordenador de TI sistêmico* e *de campus*, *Gerenciador de Prestador de Serviço*, *Coordenador da Sede* e os perfis de contrato (*Gerente de Contrato*, *Operador de Contrato*, *Coordenador de Contrato Sistêmico*) — **ou ser a própria pessoa**.
**Quando usar:** quando a foto do crachá está desatualizada, ou quando a pessoa perdeu o acesso ao e-mail de recuperação.

Os dois caminhos saem do mesmo lugar: o botão **Editar** da ficha do usuário externo.

![Menu Editar da ficha](usuario/externo-menu-editar.webp)

**Etapa 1 — a foto**

1. Em **Editar › Foto**, escolha o **Arquivo** e clique em **Enviar**.

   ![Alterar foto](usuario/externo-foto.webp)

**Resultado:** *"Foto atualizada com sucesso."* É essa a foto que sai no crachá e na barra do SUAP.

**Etapa 2 — o e-mail pessoal**

2. Em **Editar › E-mail**. Antes do formulário, o SUAP pede um **código de verificação**, que ele manda para o **seu** e-mail pessoal: digite-o e clique em **Autenticar**.

   ![Autenticação em duas etapas](usuario/externo-duplo-fator.webp)

3. Informe o novo **E-mail Pessoal** e clique em **Enviar**.

   ![Atualização do e-mail](usuario/externo-email.webp)

**Resultado:** *"E-mail atualizado com sucesso."* A verificação em duas etapas não é enfeite: quem troca o e-mail de recuperação de alguém pode, a partir dele, tomar a conta dessa pessoa — por isso esta é uma das poucas telas do SUAP que exigem o código mesmo de quem já está logado.

---

### 32. Cadastrar os seus contatos de emergência

**Quem pode:** cada servidor, para os **próprios** contatos. *Coordenador de Gestão de Pessoas*, *Coordenador de Gestão de Pessoas Sistêmico* e *Operador de Gestão de Pessoas* alcançam os de outras pessoas.
**Quando usar:** ao entrar na instituição, e sempre que o telefone de quem deve ser avisado mudar. É o único dado do SUAP consultado numa urgência médica.

1. Abra **Minha conta** e clique em **Meus dados**: é o atalho para a sua página de servidor. Nela, no botão **Editar**, escolha **Contatos de Emergência**.

   ![Contatos de emergência](usuario/contatos-listagem.webp)

2. Clique em **Adicionar Contato de Emergência**, informe **Nome do Contato** e **Telefone** e clique em **Salvar**.

   ![Novo contato de emergência](usuario/contato-formulario.webp)

**Resultado:** *"Contato adicionado com sucesso."*, e o contato passa a constar na lista. Vale repetir a operação para mais de uma pessoa; o mesmo telefone não pode ser cadastrado duas vezes.

![Contato cadastrado](usuario/contatos-cadastrado.webp)

---

### 33. Pedir o autocadastro da sua biometria

**Quem pode:** qualquer servidor — o quadro *Biometria* fica na sua **Minha conta**.
**Quando usar:** quando o seu registro de ponto vai passar a ser pelo terminal físico e a sua digital ainda não está cadastrada. O código que sai daqui evita a ida à Gestão de Pessoas: com ele, você cadastra o próprio dedo direto no terminal.

1. Abra **Minha conta** e, no quadro **Biometria**, clique em **Solicitar autocadastro**.

2. Digite a **sua senha do SUAP**, marque **Confirma a solicitação** e clique em **Enviar**.

   ![Solicitar autocadastro de biometria](usuario/biometria-solicitar.webp)

**Resultado:** *"Solicitação realizada, verifique seu e-mail."* A solicitação passa a aparecer no quadro *Biometria*, com a **data de expiração** e a indicação de que está ativa.

![Biometria na Minha conta](usuario/biometria-minha-conta.webp)

3. Enquanto a solicitação estiver ativa, **Refazer autocadastro** reenvia o código para o seu e-mail de notificação — é por aí que se resolve quando ele não chega.

**Resultado:** *"O código de autorização foi reenviado."*

> O código vale como credencial: quem o tiver em mãos cadastra um dedo **no seu lugar**. É por isso que a solicitação pede a sua senha e que o código expira.

---

### 34. Baixar a macro do SIAPE

**Quem pode:** *Coordenador de Gestão de Pessoas Sistêmico*, *Coordenador de TI sistêmico* e *Gerenciador de Extração SIAPE*.
**Quando usar:** a cada extração de dados do SIAPE. O SUAP não conversa com o sistema federal por integração automática: ele **gera um arquivo de macro** que você roda no emulador de terminal, e o resultado dessa extração é o que alimenta o cadastro de pessoal.
**Pré-condição:** a UF e o código da instituição precisam estar definidos na configuração do sistema (tarefa 19) — é isso que a macro leva escrito dentro.

1. Abra a *Administração do SUAP* (tarefa 19) e vá ao bloco **SIAPE e SCDP**. Cada link ali baixa uma macro pronta: **SIAPE Completa**, as de **PCA** (histórico, órgão anterior, posicionamento sem diploma legal) e **Personalizar Macro**.

2. Para extrair só parte dos dados, clique em **Personalizar Macro**: a tela lista os arquivos do extrator, **todos marcados**. Desmarque o que não quer (ou use **Desmarcar todos**) e clique em **Enviar**.

   ![Macro personalizável do SIAPE](usuario/macro-siape.webp)

**Resultado:** o navegador baixa o arquivo **macro_siape.mac**. Não há tela de confirmação — o desfecho é o arquivo. Abra-o no emulador de terminal para rodar a extração.

> Desmarcar um arquivo não é só tirar uma linha da lista: o SUAP refaz a ordem das telas da macro para que ela continue começando e terminando nos lugares certos. Por isso é melhor personalizar aqui do que editar o arquivo à mão.

---

### 35. Publicar e consultar as reuniões dos órgãos colegiados

**Quem pode:** cadastrar é do perfil *Administrador de Reuniões de Órgãos Colegiados Superiores*; **consultar o calendário e abrir a ficha de uma reunião é de qualquer Servidor**.
**Quando usar:** ao divulgar a pauta do CODIR, do CONSUP ou do CONSEPEX, e sempre que alguém quiser saber quando e onde o conselho se reúne.

**Etapa 1 — publicar a reunião**

1. No menu, acesse **Administração › Reuniões de Órgaos Colegiados Superiores › Cadastro** e clique em **Adicionar Reunião de Órgão Colegiado Superior**.

2. Informe **Título**, **Órgão Colegiado** (CODIR, CONSUP ou CONSEPEX), **Descrição** (a pauta), **Local**, **Data Início**, **Data Fim**, **Hora Início** e **Hora Fim**; clique em **Salvar**.

   ![Cadastro de reunião](usuario/colegiado-cadastro.webp)

**Etapa 2 — consultar o calendário**

3. Em **Administração › Reuniões de Órgaos Colegiados Superiores › Consultar Calendários**, escolha o **Formato** (*Mensal* ou *Anual*), o mês e o ano, e clique em **Enviar**. O calendário nasce vazio: é o filtro que traz as reuniões do período.

   ![Calendário de reuniões](usuario/colegiado-calendario.webp)

   A legenda no alto do calendário dá a cor de cada órgão — CODIR, CONSUP, CONSEPEX — e a marcação de *Conflito de Horários*.

4. Clique no título da reunião no calendário: a ficha abre ali mesmo, com pauta, local, data e horário.

   ![Ficha da reunião](usuario/colegiado-reuniao.webp)

**Resultado:** a reunião publicada passa a aparecer no calendário para **todos os servidores**, que é o público a que esta tela se destina.

---

### 36. Consultar o calendário administrativo do campus

**Quem pode:** qualquer pessoa com conta no SUAP.
**Quando usar:** para saber as datas que organizam o mês administrativo — consulta da prévia da folha, fechamento do processamento, abertura da folha seguinte — e os prazos de outras áreas que o sistema publica ali (férias, liberações de ponto, afastamentos), conforme o que você pode ver.

1. Abra o calendário no endereço **/comum/calendario_administrativo/** — ele não tem entrada de menu. Escolha o **Ano** e a **Unidade Organizacional** e clique em **Enviar**. O calendário do campus escolhido é desenhado mês a mês, com os eventos do ano inteiro.

   ![Calendário administrativo](usuario/calendario-administrativo.webp)

**Resultado:** o calendário do campus, com os eventos marcados nos dias. Trocar a unidade no filtro é como se consulta o calendário de outro campus.

---

## Para o público externo

Algumas telas do SUAP funcionam **sem conta e sem login**. Duas existem para quem recebeu um documento emitido pela instituição e quer saber se ele é verdadeiro: ficam reunidas no rodapé **Serviços de Acesso Público**, presente em qualquer página aberta do sistema, e uma leva à outra. A terceira é a documentação do próprio sistema.

**Escolha pelo que você tem em mãos:** o **papel impresso** (ou o PDF sem assinatura digital) leva à *Verificação de autenticação de documento*; o **arquivo PDF assinado** leva à *Validação de assinatura digital*.

### Conferir um documento pelo código do rodapé

Todo documento emitido pelo SUAP — declaração, certificado, carteira funcional, diploma — sai com **tipo, data de emissão e código verificador** impressos no rodapé, e com um QR code que leva direto a esta tela.

1. Abra **Verificação de autenticação de documento**, pelo QR code do documento ou pelo rodapé *Serviços de Acesso Público* de qualquer tela aberta do SUAP.

2. Preencha os três dados do rodapé do documento — **Tipo de Documento**, **Data da Emissão** e **Código Verificador** — resolva o desafio *não sou um robô* e clique em **Enviar**.

   ![Formulário de autenticação](usuario/autenticar-formulario.webp)

   A lista *Tipo de Documento* traz apenas os tipos que a instituição já emitiu. Quando o mesmo código corresponde a mais de um documento, a tela pede uma **Informação Auxiliar** para desempatar.

**Resultado:** *"Documento autenticado com sucesso."*, com a indicação de quem o assinou digitalmente, quando for o caso, e um **link para baixar a versão original em PDF** — que também dispensa login. Carteira funcional é um caso à parte: em vez do link, a tela exibe os dados do servidor (foto, nome, matrícula, cargo), que é o que se quer conferir.

![Documento autenticado](usuario/autenticar-resultado.webp)

Código que não existe, ou data que não corresponde, devolve *"Documento não autenticado."* — e é exatamente o que se espera de um documento forjado. Documento **cancelado** pela instituição (tarefa 22) também não autentica: a tela avisa o cancelamento, com o motivo e o responsável, quando registrados.

### Validar a assinatura de um PDF

Quando se tem o arquivo digital, dá para ir além da emissão e conferir a **assinatura** dentro dele.

1. Abra **Validação de assinatura digital**, pelo QR code impresso no carimbo da assinatura ou pelo rodapé *Serviços de Acesso Público*.

2. Envie o **Arquivo** em PDF e clique em **Enviar**.

**Resultado:** a tela informa quantas assinaturas foram detectadas e, para cada uma, quem assinou, quem emitiu o certificado e três confirmações: *A assinatura é VÁLIDA*, *Cadeia do certificado é VÁLIDA* e *Documento não foi alterado após assinatura* — a última é a que garante que nada foi trocado depois de assinado. Arquivo sem assinatura reconhecível devolve *"Assinatura digital não identificada."*

![Validação de assinatura digital](usuario/validar-assinatura.webp)

> Não está com o PDF, só com o papel? A própria tela oferece o atalho: *"Caso não esteja com a versão digital do documento no formato PDF, valide a emissão"*.

### Consultar a documentação do sistema

O SUAP publica a sua própria documentação em **/comum/documentacao/**, e ela também dispensa login — o atalho fica no rodapé *Links úteis* de qualquer tela.

1. Escolha o **módulo** na página inicial da documentação: eles vêm agrupados pela área a que pertencem, e o campo **Buscar** procura em todos ao mesmo tempo.

   ![Índice da documentação](usuario/documentacao-indice.webp)

2. A página de um módulo reúne o que ele faz, os perfis que o acessam e os **fluxogramas** dos seus processos; dentro dela, cada funcionalidade se abre em cenários, e cada cenário lista os passos com as telas correspondentes.

**Resultado:** a documentação do módulo, com data da última atualização no alto da barra lateral. O conteúdo é gerado a partir da execução dos testes do sistema, de modo que só aparecem ali os módulos já cobertos — a lista varia de instituição para instituição.


---

## Telas de apoio

Telas que os formulários deste guia consultam e que ele não descreve passo a passo: todas seguem o mesmo padrão do SUAP — listar, adicionar, editar, remover —, e cada uma é mantida por quem responde pelo assunto dela.

Em **Administração › Prédios e Salas › Cadastros › Prédios**: Acabamento Externo · Cobertura · Estrutura · Sistema de Abastecimento · Sistema de Alimentação Elétrica · Sistema de Proteção de Descarga Atmosférica · Sistema Sanitário · Vedação

Em **Administração › Prédios e Salas › Cadastros › Salas**: Acabamento das Paredes · Classificação · Climatização · Esquadrias · Forro · Instalação de Gases · Instalação Elétrica · Instalação Hidráulica · Instalação Lógica · Piso · Uso da Sala

Em **Tec. da Informação › Cadastros**, mantidos por quem cuida do sistema: **Tipos de arquivo**, que diz quais extensões o SUAP aceita em cada anexo, e **APIs Externas**, a lista dos serviços de fora com que o sistema conversa — nela, além de listar, dá para **Alternar Atividade**, **Testar Conectividade** e **Testar Consulta por CPF**.

Em **Tec. da Informação › Usuários › Autenticações Oauth**: o registro de quem entrou no SUAP por um serviço de autenticação externo, com filtro por usuário. O acesso a ela é concedido pessoa a pessoa — nenhum perfil padrão do SUAP a inclui.

Na barra de ações do **Gerenciamento de grupos** (tarefa 12), **Definir Gerenciamento de grupos** é a tela que decide *quem gerencia quem*: cada linha associa um grupo gerenciador aos grupos que ele pode conceder, e o campo **É Local?** diz se esse gerenciamento vale só dentro do campus de quem gerencia.

Em **Gestão de Pessoas › Administração de Pessoal › Solicitações › Documentos › Cadastros**, mantidos por quem coordena a Gestão de Pessoas: **Tipos de Documentos**, que define quais documentos podem ser solicitados e a quais situações funcionais cada um se aplica (a *Abrangência*), e **Configuração de Impressão de Documento**, que diz quais tipos cada campus imprime e para quais campi — é ela que decide o que aparece na fila da tarefa 21, e sem nenhuma configuração cadastrada a fila fica vazia para todo mundo.

Em **Tec. da Informação › Notificações › Push Web Notification** — a tela chama-se *Inscrições de Notificação* — fica o registro dos navegadores que pediram para receber aviso do SUAP por fora do sistema. É tela de administração: o acesso é concedido pessoa a pessoa, e nenhum perfil padrão do SUAP o inclui.

Várias telas do SUAP — de processos, de compras, de planejamento, de chamados — trazem no fim uma **caixa de comentários**. *Adicionar Comentário* abre o formulário abaixo, com um único campo, **Texto**, e **Enviar** publica; *Responder* pendura a sua resposta num comentário já existente. Comentário não se apaga: quem escreveu pode **desconsiderá-lo**, e ele fica riscado, à vista de todos. A caixa não é uma tela deste guia — ela vive dentro da tela do assunto comentado —, mas o formulário é sempre este:

![Formulário de comentário](usuario/comentario-formulario.webp)

Em **Administração › Cadastros**, o que sustenta o cadastro de usuário externo: **Ocupações** (a que título alguém presta serviço; mantida por quem coordena os estágios de forma sistêmica), **Usuários Externos › Perfis para Usuários Externos** (o campo *Perfil* da tarefa 28 — de *Gerente de Usuário Externo* e de quem **chefia um setor**) e **Áreas de Atuação**.

Ainda em **Administração › Cadastros**, três listagens de consulta ao cadastro de pessoas, abertas a perfis de auditoria e de operação: **Pessoas Físicas**, **Pessoas Externas** e **Pessoas Jurídicas** — esta última é a que alimenta o campo *Pessoa Jurídica* da ocupação (tarefa 29). São telas de consulta ao registro: o que se **faz** com uma pessoa está nas tarefas deste guia.

Fora das telas, o SUAP ainda serve ao **terminal de ponto** e ao **terminal do refeitório**: de tempos em tempos eles buscam sozinhos a tabela de pessoas com as digitais e os pacotes de fotos. Não há nada a fazer ali — mas é bom saber que existe quando a catraca de um campus para.
