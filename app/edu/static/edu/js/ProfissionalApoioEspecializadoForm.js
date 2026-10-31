// JavaScript para filtrar profissionais por ocupação no ProfissionalApoioEspecializadoForm

$(function() {
    const $acolhimento = $('#id_codigo_acolhimento');
    const $profissional = $('#id_profissional');

    function filtrarProfissionais(acolhimentoId, apoioId, uoId) {
        $.ajax({
            url: `/edu/napne/profissionais/${acolhimentoId}/${apoioId}/${uoId}/json/`,
            dataType: 'json',
            success: function(data) {
                $profissional.empty();
                $profissional.append($('<option>', { value: '', text: '---------'}));
                data.profissionais.forEach(function(prof) {
                    $profissional.append($('<option>', {
                        value: prof.id,
                        text: prof.nome
                    }));
                });
            }
        });
    }

    // Usando delegação de eventos para garantir que o handler funcione mesmo se o elemento for criado depois
    $(document).on('change', 'select[name="apoio_especializado"]', function() {
        const apoioId = $(this).val();
        const uoId = $('#id_aluno_campus').val();
        const acolhimentoId = $acolhimento.val();
        if (!apoioId || !uoId) {
            $profissional.empty();
            $profissional.append($('<option>', { value: '', text: '---------'}));
            return;
        }
        filtrarProfissionais(acolhimentoId, apoioId, uoId);
    });

    // Inicialização: se já houver valor selecionado
    const apoioIdInit = $('#id_apoio_especializado').val();
    const uoIdInit = $('#id_aluno_campus').val();
    const acolhimentoIdInit = $acolhimento.val();
    if (apoioIdInit && uoIdInit) {
        filtrarProfissionais(acolhimentoIdInit, apoioIdInit, uoIdInit);
    }
});
