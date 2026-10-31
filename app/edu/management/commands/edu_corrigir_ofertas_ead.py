from djtools.management.commands import BaseCommandPlus
from processo_seletivo.models import CandidatoVaga, Edital, OfertaVaga, OfertaVagaCurso


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        e = Edital.objects.get(pk=201)
        CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso__edital=e).exclude(oferta_vaga__oferta_vaga_curso__campus_polo='').delete()

        for oferta_vaga_curso_sem_polo in e.ofertavagacurso_set.filter(campus_polo=''):
            print((oferta_vaga_curso_sem_polo.curso_campus, oferta_vaga_curso_sem_polo.campus_polo))
            for oferta_vaga_curso_com_polo in e.ofertavagacurso_set.filter(
                curso_campus=oferta_vaga_curso_sem_polo.curso_campus, turno=oferta_vaga_curso_sem_polo.turno
            ).exclude(campus_polo=''):
                print(oferta_vaga_curso_com_polo.campus_polo)
                for oferta_vaga_sem_polo in oferta_vaga_curso_sem_polo.ofertavaga_set.all():
                    oferta_vaga_com_polo = oferta_vaga_curso_com_polo.ofertavaga_set.get(
                        lista=oferta_vaga_sem_polo.lista,
                        oferta_vaga_curso__curso_campus=oferta_vaga_curso_com_polo.curso_campus,
                        oferta_vaga_curso__turno=oferta_vaga_curso_com_polo.turno,
                    )
                    qs_candidato_vaga = oferta_vaga_sem_polo.candidatovaga_set.filter(candidato__campus_polo=oferta_vaga_curso_com_polo.campus_polo)
                    print('\n')
                    print(
                        (
                            oferta_vaga_sem_polo.lista,
                            oferta_vaga_com_polo.lista,
                            oferta_vaga_com_polo.vaga_set.count(),
                            oferta_vaga_com_polo.vaga_set.values_list('oferta_vaga__lista__descricao', flat=True),
                            qs_candidato_vaga.count(),
                            qs_candidato_vaga.filter(vaga__isnull=False).values_list('oferta_vaga__lista__descricao', flat=True),
                        )
                    )
                    for candidato_vaga in qs_candidato_vaga.all():
                        candidato_vaga.oferta_vaga = oferta_vaga_com_polo
                        candidato_vaga.save()

        CandidatoVaga.objects.filter(candidato__edital=e).update(vaga=None)
        OfertaVagaCurso.objects.filter(edital=e, campus_polo='').delete()

        for oferta_vaga in OfertaVaga.objects.filter(oferta_vaga_curso__edital=e):
            numero_ultima_chamada = oferta_vaga.oferta_vaga_curso.get_numero_ultima_chamada()
            qs_matriculados = oferta_vaga.candidatovaga_set.filter(situacao='1').order_by('classificacao')
            qs_ultimos_convocados = oferta_vaga.candidatovaga_set.filter(convocacao=numero_ultima_chamada).order_by('classificacao')
            print(
                (
                    oferta_vaga.lista,
                    oferta_vaga.oferta_vaga_curso.campus_polo,
                    oferta_vaga.vaga_set.count(),
                    qs_matriculados.count() + qs_ultimos_convocados.count(),
                )
            )
            lista = []
            for candidato_vaga in qs_matriculados:
                if len(lista) < oferta_vaga.vaga_set.count():
                    lista.append(candidato_vaga)
            for candidato_vaga in qs_ultimos_convocados:
                if len(lista) < oferta_vaga.vaga_set.count():
                    lista.append(candidato_vaga)
            print((len(lista), oferta_vaga.vaga_set.count(), len(lista) <= oferta_vaga.vaga_set.count()))
            for vaga in oferta_vaga.vaga_set.all():
                if lista:
                    candidato_vaga = lista.pop()
                    candidato_vaga.vaga = vaga
                    candidato_vaga.save()

        CandidatoVaga.objects.filter(candidato__edital=e, situacao__isnull=True, vaga__isnull=True, convocacao__isnull=False).update(convocacao=None)
