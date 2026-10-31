(function () {
    // Abas da tela de validação — a aba ativa fica persistida na URL (?tab=), sobrevivendo ao
    // refresh e ao reload após as ações de validar/solicitar correção.
    const tabs = document.querySelectorAll('[data-rsc-validar-tab]');
    if (!tabs.length) return;

    function ativar(targetId) {
        tabs.forEach(function (b) {
            const alvo = b.getAttribute('data-rsc-validar-tab') === targetId;
            b.classList.toggle('active', alvo);
            b.setAttribute('aria-selected', alvo ? 'true' : 'false');
        });
        document.querySelectorAll('.rsc-validar-pane').forEach(function (pane) {
            const alvo = pane.id === targetId;
            if (alvo) {
                pane.removeAttribute('hidden');
                pane.classList.add('rsc-validar-pane--active');
            } else {
                pane.setAttribute('hidden', '');
                pane.classList.remove('rsc-validar-pane--active');
            }
        });
    }

    function slug(targetId) {
        return targetId.replace(/^tab-/, '');
    }

    tabs.forEach(function (btn) {
        btn.addEventListener('click', function () {
            const targetId = btn.getAttribute('data-rsc-validar-tab');
            ativar(targetId);
            const url = new URL(window.location.href);
            url.searchParams.set('tab', slug(targetId));
            window.history.replaceState(null, '', url);
        });
    });

    // Ativa a aba indicada em ?tab=... no carregamento (ignora valor inválido/vazio).
    const inicial = new URLSearchParams(window.location.search).get('tab');
    if (inicial) {
        const targetId = 'tab-' + inicial;
        if (document.querySelector('[data-rsc-validar-tab="' + targetId + '"]')) {
            ativar(targetId);
        }
    }
})();
