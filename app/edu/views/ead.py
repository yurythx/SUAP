from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from djtools.utils import (
    rtr,
)
from edu.models import OfertaEAD


@login_required()
@rtr()
def ofertaead(request, pk):
    obj = get_object_or_404(OfertaEAD, pk=pk)
    title = str(obj)
    return locals()
