from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.base import ModelBase


class AgendamentoMeta(ModelBase):
    """
    A metaclass for abstract models that orchestrates the relationships
    """

    def __new__(mcs, name, bases, attrs):
        model = super().__new__(mcs, name, bases, attrs)
        meta = model._meta
        if not meta.abstract:
            AgendamentoMeta.get_agendamento_model(model)
        return model

    @staticmethod
    def get_agendamento_model(model):
        meta = getattr(model, 'AgendamentoMeta', None)
        if meta is None:
            raise RuntimeError(f'Model must specify AgendamentoMeta for {model}')
        result = getattr(meta, 'agendamento_model', None)
        if result is None:
            raise RuntimeError(f'Model must specify agendamento_model for {model}')
        return result


class SolicitacaoMeta(AgendamentoMeta):
    def __new__(mcs, name, bases, attrs):
        model = super().__new__(mcs, name, bases, attrs)
        meta = model._meta
        if not meta.abstract:
            related_name = 'reservas'
            field_name = SolicitacaoMeta.get_reserva_field(model)
            booking_cls = SolicitacaoMeta.get_reserva_model(model)
            try:
                meta.get_field(field_name)
            except FieldDoesNotExist:
                fk = models.ForeignKey(to=booking_cls, on_delete=models.CASCADE, related_name=related_name)
                model.add_to_class(field_name, fk)
        return model

    @staticmethod
    def get_reserva_field(model):
        meta = getattr(model, 'AgendamentoMeta', None)
        if meta is None:
            raise RuntimeError(f'Model must specify AgendamentoMeta for {model}')
        return getattr(meta, 'reserva_field', 'reserva')

    @staticmethod
    def get_reserva(model):
        return getattr(model, SolicitacaoMeta.get_reserva_field(model))

    @staticmethod
    def get_reserva_model(model):
        meta = getattr(model, 'AgendamentoMeta', None)
        if meta is None:
            raise RuntimeError(f'Model must specify AgendamentoMeta for {model}')
        result = getattr(meta, 'reserva_model', None)
        if result is None:
            raise RuntimeError(f'Model must specify AgendamentoMeta.booking_model for {model}')
        return result
