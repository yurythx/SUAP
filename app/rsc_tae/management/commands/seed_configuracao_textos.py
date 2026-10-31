"""
Management command: seed_configuracao_textos

Cria ou atualiza os textos de instrução da ConfiguracaoRSCTae.
Só sobrescreve campos que estiverem em branco (comportamento padrão).
Use --force para sobrescrever mesmo que já existam textos.

Uso:
    python manage.py seed_configuracao_textos
    python manage.py seed_configuracao_textos --force
"""

from django.core.management.base import BaseCommand

from rsc_tae.models.configuracao_rsc_tae import ConfiguracaoRSCTae


TEXTO_PREENCHIMENTO = """
<h3>Bem-vindo ao processo de Reconhecimento de Saberes e Competências (RSC-PCCTAE)</h3>

<p>
    O RSC-PCCTAE é o instrumento que permite ao Técnico-Administrativo em Educação (TAE) obter
    o reconhecimento de saberes e competências adquiridos ao longo da carreira, sem a necessidade
    de apresentação de diploma formal correspondente, conforme o <strong>Decreto RSC-PCCTAE, Art. 3º</strong>.
</p>

<h4>O que você precisa fazer</h4>

<p>O preenchimento do processo é dividido em quatro etapas:</p>

<ol>
    <li>
        <strong>Documento Preliminar</strong> — anexe o título, diploma ou certificado que habilita
        o nível RSC que você está pleiteando (ex.: certificado de especialização para RSC-IV).
        O RH irá validar esse documento antes do processo avançar.
    </li>
    <li>
        <strong>Itens de Saberes e Competências</strong> — para cada atividade que você deseja
        comprovar, informe a quantidade realizada e faça o upload do(s) documento(s) comprobatório(s).
        Cada item possui uma unidade de medida (horas, meses, projetos etc.) e uma pontuação por unidade.
    </li>
    <li>
        <strong>Memorial Descritivo</strong> — leia e assine a Declaração de Conformidade Legal,
        confirmando que todas as informações são verdadeiras e os documentos são autênticos.
    </li>
    <li>
        <strong>Conclusão do Preenchimento</strong> — após verificar que a pontuação e a quantidade
        de itens atendem ao mínimo exigido para o nível pleiteado, conclua o preenchimento.
        Isso equivale à assinatura eletrônica do processo.
    </li>
</ol>

<h4>Regras importantes</h4>

<ul>
    <li>
        <strong>Documentos comprobatórios obrigatórios:</strong> todo item com quantidade declarada
        deve ter ao menos um documento comprobatório anexado. Documentos sem pontuação informada
        impedirão a conclusão do preenchimento.
    </li>
    <li>
        <strong>Sem duplicidade:</strong> cada atividade ou fato só pode ser utilizado para comprovar
        um único critério específico. Não é permitido usar o mesmo documento para dois itens diferentes
        (Art. 4º, §2º do Decreto RSC-PCCTAE).
    </li>
    <li>
        <strong>Atribuições ordinárias não são computadas:</strong> atividades que fazem parte das
        atribuições regulares do seu cargo não podem ser apresentadas como saberes e competências
        (Art. 4º, §1º do Decreto RSC-PCCTAE).
    </li>
    <li>
        <strong>Interstício:</strong> é necessário aguardar ao menos 3 anos desde a última concessão
        de RSC para solicitar uma nova (Art. 8º do Decreto RSC-PCCTAE).
    </li>
    <li>
        <strong>Saldo de pontuação anterior:</strong> se você teve um processo deferido anteriormente,
        o excedente de pontuação daquele processo será automaticamente somado à sua pontuação atual.
    </li>
    <li>
        <strong>Validade das atividades:</strong> atividades realizadas a qualquer tempo são válidas,
        inclusive durante o estágio probatório, desde que no exercício do cargo
        (Art. 9º do Decreto RSC-PCCTAE).
    </li>
</ul>

<h4>Dúvidas?</h4>

<p>
    Em caso de dúvidas sobre o preenchimento, entre em contato com o setor de Gestão de Pessoas
    do seu campus. Você também pode consultar o texto completo do Decreto RSC-PCCTAE e seus anexos
    para verificar os documentos comprobatórios aceitos para cada item.
</p>
""".strip()


TEXTO_AVALIACAO = """
<h3>Instruções para Avaliadores — RSC-PCCTAE</h3>

<p>
    Você foi designado como avaliador de um processo de Reconhecimento de Saberes e Competências
    (RSC-PCCTAE). Sua responsabilidade é analisar, com critério técnico e imparcialidade, os
    documentos comprobatórios apresentados pelo servidor, validando ou indeferindo cada item
    conforme os critérios estabelecidos no Decreto RSC-PCCTAE e seus anexos.
</p>

<h4>Como realizar a avaliação</h4>

<ol>
    <li>
        <strong>Acesse "Minhas avaliações"</strong> no menu do módulo RSC-TAE para visualizar os
        processos sob sua responsabilidade e o prazo disponível para cada avaliação.
    </li>
    <li>
        <strong>Analise cada documento comprobatório</strong> individualmente. Para cada anexo,
        você deverá informar:
        <ul>
            <li>
                <strong>Situação:</strong> Deferido (documento válido e suficiente) ou
                Indeferido (documento inválido, insuficiente ou não aceito).
            </li>
            <li>
                <strong>Pontuação validada:</strong> confirme ou corrija a pontuação proposta
                pelo servidor, respeitando a pontuação máxima permitida para o item.
            </li>
            <li>
                <strong>Observação (opcional):</strong> registre o motivo do indeferimento ou
                qualquer ressalva relevante. Obrigatória em caso de indeferimento.
            </li>
        </ul>
    </li>
    <li>
        <strong>Verifique o resumo da avaliação</strong> antes de finalizar. O sistema mostrará
        a pontuação total validada, a quantidade de itens deferidos e se o processo atingiu os
        mínimos exigidos para o nível pleiteado.
    </li>
    <li>
        <strong>Finalize a avaliação</strong> após analisar todos os documentos. Ao finalizar,
        você deverá assinar eletronicamente e indicar seu resultado individual (Deferido ou
        Indeferido), com justificativa em caso de indeferimento.
    </li>
</ol>

<h4>Critérios de análise</h4>

<ul>
    <li>
        <strong>Autenticidade e suficiência:</strong> o documento deve comprovar, de forma clara
        e inequívoca, a atividade declarada pelo servidor no período informado.
    </li>
    <li>
        <strong>Tipo de documento aceito:</strong> consulte o Rol de Saberes e Competências
        (Anexo IV do Decreto RSC-PCCTAE) para verificar quais documentos são aceitos para cada item.
    </li>
    <li>
        <strong>Atribuições ordinárias:</strong> rejeite documentos que comprovem atividades que
        fazem parte das atribuições regulares do cargo do servidor (Art. 4º, §1º). Registre
        o motivo do indeferimento.
    </li>
    <li>
        <strong>Duplicidade:</strong> verifique se o mesmo documento está sendo utilizado para
        comprovar mais de um item. Em caso de duplicidade, indefira o item excedente e registre
        a ocorrência na observação.
    </li>
    <li>
        <strong>Itens temporais:</strong> para itens medidos em meses (ex.: participação em
        comissões), verifique se as datas de início e fim informadas são consistentes com
        o documento e calcule a pontuação proporcionalmente.
    </li>
    <li>
        <strong>Imparcialidade:</strong> a avaliação deve ser baseada exclusivamente nos
        documentos apresentados e nos critérios do Decreto RSC-PCCTAE, sem qualquer
        favorecimento ou prejuízo pessoal ao servidor.
    </li>
</ul>

<h4>Resultado do processo</h4>

<p>
    Quando todos os avaliadores designados finalizarem suas avaliações, o sistema calculará
    o resultado final com base na <strong>maioria simples</strong> dos resultados individuais.
    O processo será <strong>Deferido</strong> se a maioria dos avaliadores concluir pelo deferimento,
    ou <strong>Indeferido</strong> caso contrário.
</p>

<h4>Prazo e impedimentos</h4>

<ul>
    <li>
        Respeite o prazo estabelecido para a avaliação, visível na coluna "SLA" em
        "Minhas avaliações". Processos com prazo estourado são monitorados pelo setor de
        Gestão de Pessoas.
    </li>
    <li>
        Se você estiver impedido de avaliar (suspeição, parentesco, interesse direto no resultado),
        comunique imediatamente ao RH para que seja realizado o remanejamento do avaliador.
    </li>
</ul>

<h4>Dúvidas?</h4>

<p>
    Em caso de dúvidas sobre os critérios de avaliação, consulte o texto completo do
    Decreto RSC-PCCTAE e seus anexos, ou entre em contato com o setor de Gestão de Pessoas
    responsável pelo processo.
</p>
""".strip()


class Command(BaseCommand):
    help = 'Cria ou atualiza os textos de instrução da ConfiguracaoRSCTae.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Sobrescreve os textos mesmo que já existam.',
        )

    def handle(self, *args, **options):
        force = options['force']

        config, criada = ConfiguracaoRSCTae.objects.get_or_create()

        if criada:
            self.stdout.write('ConfiguracaoRSCTae criada.')
        else:
            self.stdout.write('ConfiguracaoRSCTae já existe — verificando campos.')

        campos_atualizados = []

        if not config.texto_instrucao_preenchimento or force:
            config.texto_instrucao_preenchimento = TEXTO_PREENCHIMENTO
            campos_atualizados.append('texto_instrucao_preenchimento')
        else:
            self.stdout.write('  texto_instrucao_preenchimento já preenchido — ignorado (use --force para sobrescrever).')

        if not config.texto_instrucao_avaliacao or force:
            config.texto_instrucao_avaliacao = TEXTO_AVALIACAO
            campos_atualizados.append('texto_instrucao_avaliacao')
        else:
            self.stdout.write('  texto_instrucao_avaliacao já preenchido — ignorado (use --force para sobrescrever).')

        if campos_atualizados:
            config.save(update_fields=campos_atualizados)
            for campo in campos_atualizados:
                self.stdout.write(self.style.SUCCESS(f'  {campo} atualizado.'))
        else:
            self.stdout.write(self.style.WARNING('Nenhum campo foi alterado.'))
