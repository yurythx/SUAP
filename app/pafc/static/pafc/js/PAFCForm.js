const QTD_VAGAS_CACHE = {}

function redefinirCamposSituacaoCurso() {
    const previsto_pdi = $('#id_previsto_pdi').val()
    const curso_ja_ofertado = $('#id_curso_ja_ofertado_campus').val()
    const id_curso = $('select[name="curso"]').val()

    if (previsto_pdi) {
        if (previsto_pdi === "true") {
            $('label[for="id_justificativa_ausencia_pdi"]').removeClass('required')
            $('#id_justificativa_ausencia_pdi').parent().parent().hide()
        }
        else {
            $('#id_justificativa_ausencia_pdi').parent().parent().show()
            $('label[for="id_justificativa_ausencia_pdi"]').addClass('required')
        }
    }

    if (curso_ja_ofertado) {
        if (curso_ja_ofertado === "true") {
            // esconde campo da ata da reunião do CODIAC, desnecessária quando curso existe
            $('label[for="id_ata_reuniao_codiac"]').removeClass('required')
            $('select[name="ata_reuniao_codiac"]').parent().parent().hide()

            // exibe campo para informar o curso existente
            $('select[name="curso"]').parent().parent().show()
            $('label[for="id_curso"]').addClass('required')

            // esconde campos sobre período letivo da primeira oferta
            $('label[for="id_ano_letivo_primeira_oferta"]').removeClass('required')
            $('select[name="ano_letivo_primeira_oferta"]').parent().parent().hide()
            $('label[for="id_periodo_letivo_primeira_oferta"]').removeClass('required')
            $('select[name="periodo_letivo_primeira_oferta"]').parent().parent().hide()
        }
        else {
            // exibe campo da ata da reunião do CODIAC autorizando criação do curso
            $('select[name="ata_reuniao_codiac"]').parent().parent().show()
            $('label[for="id_ata_reuniao_codiac"]').addClass('required')

            // esconde campo do curso existente, já que se trata de uma criação
            $('label[for="id_curso"]').removeClass('required')
            $('select[name="curso"]').parent().parent().hide()

            // exibe campos sobre período letivo da primeira oferta
            $('select[name="ano_letivo_primeira_oferta"]').parent().parent().show()
            $('label[for="id_ano_letivo_primeira_oferta"]').addClass('required')
            $('select[name="periodo_letivo_primeira_oferta"]').parent().parent().show()
            $('label[for="id_periodo_letivo_primeira_oferta"]').addClass('required')
        }

        if (id_curso) {
            if (QTD_VAGAS_CACHE[id_curso]) {
                $("#id_numero_vagas_curso").val(QTD_VAGAS_CACHE[id_curso] || QTD_VAGAS_CACHE['default'] || '');
            }
            else {
                $.ajax({
                    method: "GET",
                    url: `/pafc/total_vagas_curso/${id_curso}`,
                    success: function (vagas, textStatus, jqXHR) {
                        QTD_VAGAS_CACHE[id_curso] = vagas
                        $("#id_numero_vagas_curso").val(vagas || QTD_VAGAS_CACHE['default'] || '');
                    },
                    error: function () {
                        console.log("Erro ao consultar quantidade de vagas.");
                    }
                });
            }
        }
    }
}

jQuery(function () {

    QTD_VAGAS_CACHE['default'] = $("#id_numero_vagas_curso").val();

    $('#id_previsto_pdi, #id_curso_ja_ofertado_campus, select[name="curso"]').on('change', function () {
        redefinirCamposSituacaoCurso();
    });

    redefinirCamposSituacaoCurso();
});
