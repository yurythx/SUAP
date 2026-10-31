from django.http import HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin

from djtools.utils import running_tests


class InformarTitulacaoMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not running_tests():
            if request.user.is_authenticated and 'informacao-titulacao-pendente' not in request.session:
                professor = request.user.get_vinculo().professor_set.first()
                if professor:
                    dados_informados = (
                        professor.titulacao
                        and professor.ultima_instituicao_de_titulacao
                        and professor.area_ultima_titulacao
                        and professor.ano_ultima_titulacao
                    )
                    request.session['informacao-titulacao-pendente'] = not dados_informados
                else:
                    request.session['informacao-titulacao-pendente'] = False
                request.session.save()
            if request.session.get('informacao-titulacao-pendente'):
                if (
                    request.path != '/edu/preencher_dados_titulacao/'
                    and request.path != '/comum/logout/'
                    and not request.path.startswith('/static')
                    and not request.path.startswith('/media')
                ):
                    return HttpResponseRedirect('/edu/preencher_dados_titulacao/')
