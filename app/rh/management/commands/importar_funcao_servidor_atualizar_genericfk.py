import datetime

from django.contrib.contenttypes.models import ContentType

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import Assinatura
from rh.models import CargoEmprego, Funcao, Papel


class ItemLog:
    ERRO, SUCESSO = 'ERRO', 'SUCESSO'

    def __init__(self):
        self.papel = None
        self.tipo = None
        self.msg = ''
        self.sugestao_ids_para_generic_fk = []

    def isSucesso(self):
        return self.tipo == ItemLog.SUCESSO

    def __str__(self):
        return f'{self.papel.id};{self.papel.descricao};{self.papel.tipo_papel};{self.tipo};{self.msg};{self.sugestao_ids_para_generic_fk}'


class Command(BaseCommandPlus):
    def __atualizar_genericfk_em_papel(self, papel, papel_content_object):
        papel.papel_content_type = ContentType.objects.get_for_model(papel_content_object.__class__)
        papel.papel_content_id = papel_content_object.id
        papel.papel_content_object = papel_content_object
        papel.save()

    def handle(self, *args, **options):
        title = 'RH - Criando vínculo entre Papel e CargoEmprego/Funcao via GenericForeignKey'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        print(
            'O objetivo deste command é criar um link entre a entidade Papel e a entidade CargoEmprego '
            'e/ou Funcao, pois atualmente esse vínculo não existe, e ele é necessário para que o recurso de restrição '
            'de assinatura (Ex: Permitir que somente que o reitor possa assinar uma portaria) possa funcionar.'
        )

        print()
        print(
            'ATENÇÃO: (1) Como os papéis dos servidores podem ser importados a qualquer tempo, e atualmente os papéis '
            'só vem sendo utilizados para a assinatura eletrônica de documentos, todos os registros de Papel '
            'que não tiverem sido usados em assinaturas serão excluídos. Ao serem reimportados novamente, eles já terão '
            'o vínculo com CargoEmprego e/ou Funcao criados. (2) Caso não seja possível criar o referido vínculo, ele '
            'terá de ser feito manualmente.'
        )

        print()

        executar_command = options.get('executar_command') or input('Deseja continuar? (S/n)').strip().upper() == 'S'
        if not executar_command:
            print()
            print('Processamento abortado.')
            return

        print()
        print('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        print()

        papel_pks = Assinatura.objects.values_list('papel__id', flat=True)
        papeis_usados_em_assinaturas = Papel.objects.filter(id__in=papel_pks, vinculo__tipo_relacionamento__model='servidor')
        print()
        print(f'Papéis usados: {papeis_usados_em_assinaturas.count()}')

        # - - - - - - - - - - - - - - -
        # Removenddo papéis não usados
        # - - - - - - - - - - - - - - -
        papeis_servidor_nao_usados = Papel.objects.exclude(id__in=papel_pks)
        print()
        print(f'Papéis não usados: {papeis_servidor_nao_usados.count()}')
        if papeis_servidor_nao_usados.count() > 0:
            papeis_servidor_nao_usados.delete()
            print('Papéis não usados removidos com sucesso.')

        # - - - - - - - - - - - - - - - - - - - - -
        # Ajustando os papéis usados em assianturas
        # - - - - - - - - - - - - - - - - - - - - -
        lista_sucesso = []
        lista_erro = []

        for papel in papeis_usados_em_assinaturas:
            item_log = ItemLog()
            item_log.papel = papel

            # Caso o papel em questão seja um CargoEmprego...
            if papel.tipo_papel == Papel.TIPO_PAPEL_CARGO:
                # Se a descrição do PapelServidor em questão tiver o mesmo nome do cargo atual do servidor, então assumimos
                # que esse foi o CargoEmprego usado na época da assinatura do documento.
                if papel.descricao == papel.vinculo.relacionamento.cargo_emprego.nome:
                    cargo_emprego = papel.vinculo.relacionamento.cargo_emprego
                    self.__atualizar_genericfk_em_papel(papel, cargo_emprego)
                    item_log.tipo = ItemLog.SUCESSO
                    item_log.msg = f'Papel atualizado (via Servidor). Agora ele faz referência ao CargoEmprego de id {papel.papel_content_id}'

                # Caso contrário, faremos então uma busca em todos os registros de CargoEmprego existentes usando como
                # parâmetros os mesmos critérios utilizados para criar o PapelServidor com base em CargoEmprego, que no
                # caso é o nome do cargo.
                else:
                    cargo_emprego_qs = CargoEmprego.objects.filter(nome=papel.descricao)

                    if not cargo_emprego_qs.exists():
                        item_log.tipo = ItemLog.ERRO
                        item_log.msg = 'Nenhum cargo emprego localizado'
                    else:
                        if cargo_emprego_qs.count() == 1:
                            cargo_emprego = cargo_emprego_qs.first()
                            self.__atualizar_genericfk_em_papel(papel, cargo_emprego)
                            item_log.tipo = ItemLog.SUCESSO
                            item_log.msg = f'Papel atualizado. Agora ele faz referência ao CargoEmprego de id {papel.papel_content_id}'
                        else:
                            item_log.tipo = ItemLog.ERRO
                            item_log.msg = f'Papel não atualizado. Foram encontrados {cargo_emprego_qs.count()} registros de CargoEmprego'
                            item_log.sugestao_ids_para_generic_fk = list(cargo_emprego_qs.values_list('id', flat=True))

            # Caso o papel em questão seja uma Funcao...
            elif papel.tipo_papel == Papel.TIPO_PAPEL_FUNCAO:
                # No caso das funções, todos os registro de PapelServidor criados com base em funções tiveram como descrição:
                # funcao.nome - self.funcao.codigo
                funcao = papel.descricao.split(' - ')
                funcao_codigo = funcao[-1]
                funcao_nome = ' - '.join(funcao[0 : len(funcao) - 1])
                # print funcao_codigo
                # print funcao_nome
                # print 'Qtd de Funcoes Encontradas: {0}'.format(Funcao.objects.filter(nome=funcao_nome, codigo=funcao_codigo).count())

                # Se a descrição do PapelServidor em questão tiver o mesmo nome e código da função atual do servidor,
                # então assumimos que essa foi a Funcao usado na época da assinatura do documento.
                if (
                    papel.vinculo.relacionamento.funcao
                    and papel.vinculo.relacionamento.funcao.codigo == funcao_codigo
                    and papel.vinculo.relacionamento.funcao.nome == funcao_nome
                ):
                    funcao = papel.vinculo.relacionamento.funcao
                    self.__atualizar_genericfk_em_papel(papel, funcao)
                    item_log.tipo = ItemLog.SUCESSO
                    item_log.msg = f'Papel atualizado (via Servidor). Agora ele faz referência a Funcao de id {papel.papel_content_id}'
                else:
                    # Caso contrário, faremos então uma busca em todos os registros de Funcao existentes usando como
                    # parâmetros os mesmos critérios utilizados para criar o PapelServidor com base em Funcao, que no
                    # caso é o nome e o codigo da função.
                    funcao_qs = Funcao.objects.filter(nome=funcao_nome, codigo=funcao_codigo)

                    if not funcao_qs.exists():
                        item_log.tipo = ItemLog.ERRO
                        item_log.msg = 'Nenhuma função localizada'
                    else:
                        if funcao_qs.count() == 1:
                            funcao = funcao_qs.first()
                            self.__atualizar_genericfk_em_papel(papel, funcao)
                            item_log.tipo = ItemLog.SUCESSO
                            item_log.msg = f'Papel atualizado. Agora ele faz referência a Funcao de id {papel.papel_content_id}'
                        else:
                            item_log.tipo = ItemLog.ERRO
                            item_log.msg = f'Papel não atualizado. Foram encontrados {funcao_qs.count()} registros de Funcao'
                            item_log.sugestao_ids_para_generic_fk = list(funcao_qs.values_list('id', flat=True))

            if item_log.isSucesso():
                lista_sucesso.append(item_log)
            else:
                lista_erro.append(item_log)

        print()
        print(f'Registros atualizados: {len(lista_sucesso)}')
        print('-' * 50)
        for item_log in lista_sucesso:
            print(item_log.__str__())

        print()
        print(f'Registros NÃO atualizados: {len(lista_erro)}')
        if len(lista_erro) > 0:
            print('Obs: Caso registros devem ser atualizados manualmente.')
        print('-' * 50)
        for item_log in lista_erro:
            print(item_log.__str__())

        print()
        print('Processamento concluído')
        print('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))

        gerar_excecao = options.get('gerar_excecao')
        if gerar_excecao and Papel.objects.filter(papel_content_id__isnull=True).exists():
            raise Exception('Ainda existem registros de Papel sem CargoEmprego ou Funcao definidos. Corrija manualmente esse registros')
