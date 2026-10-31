$(document).ready(function(){
    $('#evento_form').on('submit', function (e) {
        const isPreview = $(document.activeElement).hasClass('preview-certificado');
        if (isPreview) return true;
    });
    

    $('.preview-certificado').click(function () {
        target = $(this);

        $(target).attr("disabled", "disabled");
        var html_antigo = $(target).html();
        $(target).html("<span class='fas fa-spinner fa-spin' aria-hidden='true'></span> Aguarde...");

        tipo_participacao_id = target.parents('tr').find('select[name$=tipo_participacao]').val();
        modelo = target.parents('tr').find('input[type=file][name$=-modelo_certificado]')[0].files[0];
        csrf_token = $('input[name=csrfmiddlewaretoken]').val();

        form = new FormData();
        form.append('tipo_participacao_id', tipo_participacao_id);
        form.append('modelo_certificado', modelo);

        nome = $('input[name=nome]').val();// '#EVENTO#': "Evento Teste",
        form.append('nome', nome);

        campus_id = $('select[name$=campus]').val();// '#CAMPUS#': "Campus Teste",
        form.append('campus_id', campus_id);

        carga_horaria = $('input[name=carga_horaria]').val();// '#CARGAHORARIA#': "Carga Horária Teste",
        form.append('carga_horaria', carga_horaria);

        data_inicial = $('input[name=data_inicio]').val();// '#DATAINICIALADATAFINAL#': "data inicial a data final",
        form.append('data_inicial', data_inicial);

        data_final = $('input[name=data_fim]').val();// '#DATAINICIALADATAFINAL#': "data inicial a data final",
        form.append('data_final', data_final);

        setor_id = $('input[name=setor]').val();// '#SETORRESPONSAVEL#': "Setor Teste",
        form.append('setor_id', setor_id);

        if (!tipo_participacao_id) {
            alert('Por favor, selecione o Tipo de Participação.');
            $(target).removeAttr('disabled');
            $(target).html(html_antigo);
            return;
        }
        if (!campus_id) {
            alert('Por favor, selecione o campus.');
            $(target).removeAttr('disabled');
            $(target).html(html_antigo);
            return;
        }
        $.ajax({
            headers: { "X-CSRFToken": csrf_token },
            url: '/eventos/teste_preview_certificado/'+tipo_participacao_id+'/',
            data: form,
            processData: false,
            contentType: false,
            type: 'POST',
            xhrFields: {
                responseType: 'blob'
            },
            success: function (data) {
                var blob = new Blob([data], { type: 'application/pdf' });
                if (window.navigator && window.navigator.msSaveOrOpenBlob) {
                    window.navigator.msSaveOrOpenBlob(blob); // for IE
                } else {
                    var fileURL = URL.createObjectURL(blob);
                    window.open(fileURL);
                }
                $(target).removeAttr('disabled');
                $(target).html(html_antigo);
            }
        });
    });
})
