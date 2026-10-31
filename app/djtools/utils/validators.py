from django.core import validators
from django.db import models
from django.forms import ValidationError


def cpf_valido(value):
    """
    Verifica se o valor passado é um CPF.

    Args:
        value (string): valor a ser testado.

    Returns:
        True se o **value** for um CPF.
    """
    from djtools.forms.fields import BrCpfField

    cpf_field = BrCpfField()
    try:
        cpf_field.clean(value)
        return True
    except ValidationError:
        return False


def email_valido(value):
    """
    Verifica se o valor passado é um e-mail.

    Args:
        value (string): valor a testar se é e-mail.

    Returns:
        True se o **value** for um e-mail.
    """
    try:
        validators.validate_email(value)
        return True
    except ValidationError:
        return False


def cnpj_valido(value):
    """
    Verifica se o valor passado é um CNPJ.

    Args:
        value (string): valor a ser testado.

    Returns:
        True se o **value** for um CNPJ.
    """
    from djtools.forms.fields import BrCnpjField

    cnpj_field = BrCnpjField()
    try:
        cnpj_field.clean(value)
        return True
    except ValidationError:
        return False


class ModelValidation:
    """Objetivo principal: manter toda a validação do model no model.

    Ciclo de validação de um model:
        https://docs.djangoproject.com/en/5.1/ref/models/instances/#validating-objects

    A validação de uma instância deve usar a versão final dos dados candidatos a serem
    salvos. O ciclo de validação do model inclui métodos para realizar a validação de uma
    instância cuja versão final dos dados é de responsabilidade do cliente requisitante da
    validação (ex: forms, modelforms, views, etc), bastando o cliente consumir os métodos
    de validação de uma dada instância (full_clean, clean_fields, clean, ...). Mas há algumas
    problemáticas:
        - a validação de fields m2m só deve ser feita em instâncias já salvas (com pk),
        pois não será possível acessar o field durante o ciclo de validação;
        - o valor atual de um field m2m pode já está desatualizado durante o ciclo de validação,
        pois o cliente não poderá atualizar esses fields antes do ciclo de validação sem
        salvá-los primeiro e, no caso de instância sem pk, a instância também deve ser salva;
        - um cliente não pode salvar informações antes ou durante a validação, pois a ação
        de salvar deve ocorrer após o ciclo de validação;
        - um cliente pode escolher manipular apenas parte dos fields e invocar a validação de
        uma instância com dados parciais, o que poderia gerar erros durante uma validação
        centralizada no model.

    O ModelForm chama automaticamente o método full_clean de uma instância, mas a problemática
    envolvendo os fields m2m continua:
        - dados inacessíveis (instância sem pk)
        - dados desatualizados (a entrada no formulário ainda não foi salva)

    Na prática do dia-a-dia, a validação dos models se concentra nos forms, que passam a ter
    muito da lógica de negócio que deveria pertencer ao model. Embora o ModelForm chame
    automaticamente o método full_clean da instância, isso não acontece nos demais clientes, que
    devem chamar manualmente os métodos de validação de um model, e essa exigência (lembrança)
    aumenta as chances de dispersar as regras de negócio. Mas como foi dito, a validação de uma
    instância deve usar a versão final dos dados candidatos a serem salvos, e esses novos dados
    estão disponíveis durante o ciclo de validação de um cliente (ex: um form), mas que ainda não
    foram salvos.

    A ideia aqui é passar um conjunto de dados na forma {field: value} para ser validado no contexto
    de um model. Isso permitirá que os clientes (forms, modelforms, views, etc) possam validar
    uma instância de um model informando os novos valores de seus fields (todo ou parte dos fields).

    Uso desta classe:

        class MyModel(ModelPlus):
            ...

            @classmethod
            def my_validate_1(cls, data=None, instance=None):
                instance_for_validation = ModelValidation.instance_for_validation(cls, data, instance)
                ...
                raise ValidationError('Error 1')
                ...

            @classmethod
            def my_validate_2(cls, data=None, instance=None):
                instance_for_validation = ModelValidation.instance_for_validation(cls, data, instance)
                ...
                raise ValidationError('Error 2')
                ...

    Exemplo de um código cliente validando um model:

        # contexto de validação aguardando possíveis exceções ValidationError

        data = {
            'field_1': valor,
            'field_2': valor,
            'field_m2m_1': [valor, valor, ...],
            'field_m2m_2': [valor, valor, ...],
        }

        MyModel.my_validate_1(data, instance=None)

        # no clean de um modelform

        def clean(self):
            clean = super().clean()
            MyModel.my_validate_1(clean, instance=self.instance)
            MyModel.my_validate_2(clean, instance=self.instance)
            ...

    Saída de exemplo prático da problemática dos fields m2m durante a validação de um ModelForm:

        Change Demanda:
        =============================

        Validação com a proposta da classe ModelValidation:
            class Demanda(ModelPlus):
                def my_validate(cls, data=None, instance=None):
                    instance_for_validation = ModelValidation.instance_for_validation(cls, data, instance)
                    instance.demandantes = <QuerySet [<User: Fulano 1 (000001)>, <User: Fulano 2 (000001)>]>
                    *** dados atualizados (mas não foram salvos ainda)

        Validação automática com o ModelForm:
            class Demanda(ModelPlus):
                def clean(self):
                    self.demandantes = <QuerySet [<User: Fulano 1 (000001)>]>
                    *** dados desatualizados

        Add Demanda:
        =============================

        Validação com a proposta da classe ModelValidation:
            class Demanda(ModelPlus):
                def my_validate(cls, data=None, instance=None):
                    instance_for_validation = ModelValidation.instance_for_validation(cls, data, instance)
                    instance.demandantes = <QuerySet [<User: Fulano 1 (000001)>]>
                    *** dados atualizados (mas não foram salvos ainda)

        Validação automática com o ModelForm:
            class Demanda(ModelPlus):
                def clean(self):
                    self.demandantes = ?
                    *** dados inacessíveis
                    Internal Server Error: /admin/demandas/demanda/add/
                    'Demanda' instance needs to have a primary key value before this relationship can be used.
    """

    class InstanceForValidation:
        """Objeto temporário para fins de validação.
        Representa a instância do model e se comporta
        como tal (é um proxy). O cliente pode interagir
        como se fosse a própria instância do model.
        A própria instância do model não resolveria?
            - Não. Há uma problemática com os fields m2m
            conforme doc da classe ModelValidation.
        """

        def __init__(self, instance_tmp, fields_m2m):
            self._instance_tmp = instance_tmp
            self._fields_m2m = fields_m2m

        def __getattribute__(self, name):
            if name in ['_instance_tmp', '_fields_m2m']:
                # evita recursão deste __getattribute__
                return super().__getattribute__(name)
            if name in self._fields_m2m:
                return self._fields_m2m.get(name)
            return getattr(self._instance_tmp, name)

    @staticmethod
    def instance_for_validation(model_class, data=None, instance=None) -> InstanceForValidation:
        """Dado um 'data' ({field: value, ...}), cria uma instância temporária do model
        para fins de validação.

        Os valores de todos os fields serão mesclados entre 'data' (novos valores) e
        'instance' (valores anteriores). Os valores novos em 'data' terão maior
        prioridade em relação aos valores anteriores em 'instance'.

        Com a instância temporária será possivel validar o model usando a versão
        atualizada de todos os seus dados.
        """

        instance_tmp = model_class()

        if instance:
            instance_tmp = model_class.objects.filter(id=instance.id).first() or instance_tmp

        data = data or {}
        fields_m2m = {}

        for field in model_class._meta.get_fields(include_parents=False):
            # https://docs.djangoproject.com/en/5.1/ref/models/meta/
            is_field_type = isinstance(field, models.fields.related.Field)
            if is_field_type:
                field_is_m2m = isinstance(field, models.fields.related.ManyToManyField)
                if field_is_m2m:
                    field_old_value = getattr(instance_tmp, field.name) if instance_tmp.id else field.related_model.objects.none()
                    field_upd_value = data.get(field.name, field_old_value)
                    if isinstance(field_upd_value, list | tuple):
                        # Assumindo que field_upd_value contém PKs ou objetos
                        pks = [obj.pk if hasattr(obj, 'pk') else obj for obj in field_upd_value]
                        field_upd_value = field.related_model.objects.filter(pk__in=pks)
                    elif hasattr(field_upd_value, 'all'):
                        field_upd_value = field_upd_value.all()

                    fields_m2m[field.name] = field_upd_value
                else:
                    field_old_value = getattr(instance_tmp, field.name)
                    field_upd_value = data.get(field.name, field_old_value)
                    setattr(instance_tmp, field.name, field_upd_value)

        return ModelValidation.InstanceForValidation(instance_tmp, fields_m2m)
