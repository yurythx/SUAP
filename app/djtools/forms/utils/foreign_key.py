class ModelChoiceIteratorPlus:
    """
    Este Iterator foi criado para evitar problemas com cache de choices no
    ``ModelChoiceFieldPlus``.
    """

    def __init__(self, field):
        self.field = field
        self.queryset = field.queryset

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ('', self.field.empty_label)
        if self.field.group_by:
            groups = list(set(self.queryset.values_list(self.field.group_by, flat=True)))
            groups.sort()
            for group in groups:
                group_choices = []
                for obj in self.queryset.filter(**{str(self.field.group_by): group}):
                    group_choices.append([obj.pk, self.field.label_from_instance(obj)])
                yield [str(group), group_choices]
        else:
            for obj in self.queryset.all():
                yield self.choice(obj)

    def choice(self, obj):
        if self.field.to_field_name:
            key = obj.serializable_value(self.field.to_field_name)
        else:
            key = obj.pk
        return (key, self.field.label_from_instance(obj))
