(function () {
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return (root || document).querySelectorAll(sel); }

  function setStatus(pane, pendentes, total) {
    var banner = $('#qr-status', pane);
    if (!banner) return;
    if (pendentes <= 0) {
      banner.style.display = 'none';
      pane.removeAttribute('aria-busy');
    } else {
      banner.style.display = '';
      pane.setAttribute('aria-busy', 'true');
      var restam = (pendentes === total)
        ? 'Preparando o quadro-resumo…'
        : 'Carregando… restam ' + pendentes + ' de ' + total + ' bloco(s).';
      banner.textContent = restam;
    }
  }

  function setExportEnabled(pane, enabled) {
    var btn = $('#qr-export', pane);
    if (!btn) return;
    if (enabled) {
      // habilita: restaura o href e estados de acessibilidade
      var href = btn.getAttribute('data-export-href');
      if (href) btn.setAttribute('href', href);
      btn.classList.remove('disabled');
      btn.removeAttribute('aria-disabled');
    } else {
      // desabilita: remove href e marca acessível
      btn.removeAttribute('href');
      btn.classList.add('disabled');
      btn.setAttribute('aria-disabled', 'true');
    }
  }

  function loadBlock(el, onDone) {
    if (!el || el.getAttribute('data-loaded') === '1') { onDone(false); return; }
    var url = el.getAttribute('data-url');
    if (!url) { onDone(false); return; }

    // indicador por bloco
    el.setAttribute('aria-busy', 'true');

    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        el.innerHTML = html;
        el.setAttribute('data-loaded', '1');
        el.removeAttribute('aria-busy');
        onDone(true);
      })
      .catch(function () {
        el.innerHTML = '' +
          '<div class="alert alert-danger" role="alert">' +
          'Falha ao carregar este bloco. ' +
          '<button type="button" class="btn default qr-retry" aria-label="Tentar novamente">Tentar novamente</button>' +
          '</div>';
        el.removeAttribute('aria-busy');
        // marca como falha; permanece pendente até a pessoa clicar “Tentar novamente”
        onDone(false, true);
      });
  }

  function carregarQuadroResumo() {
    var pane = document.querySelector('.tab-pane[data-tab="quadro_resumo"]');
    if (!pane) return;

    // coleta blocos e inicializa estado
    var blocks = $all('.quadro-resumo-bloco', pane);
    var total = blocks.length;
    var pendentes = total;

    setExportEnabled(pane, false);
    setStatus(pane, pendentes, total);

    // carregamento inicial de todos os blocos
    blocks.forEach(function (el) {
      loadBlock(el, function (ok, falha) {
        if (ok) pendentes = Math.max(0, pendentes - 1);
        setStatus(pane, pendentes, total);
        if (pendentes === 0) setExportEnabled(pane, true);
      });
    });

    // re-tentativa local por bloco
    pane.addEventListener('click', function (ev) {
      var btn = ev.target.closest('.qr-retry');
      if (!btn) return;
      var holder = ev.target.closest('.quadro-resumo-bloco');
      if (!holder) return;

      // ao re-tentar, considera o bloco novamente como pendente
      pendentes = Math.min(total, pendentes + 1);
      setStatus(pane, pendentes, total);
      setExportEnabled(pane, false);

      loadBlock(holder, function (ok) {
        if (ok) pendentes = Math.max(0, pendentes - 1);
        setStatus(pane, pendentes, total);
        if (pendentes === 0) setExportEnabled(pane, true);
      });
    });

    // impedir clique no botão enquanto desabilitado
    var exportBtn = $('#qr-export', pane);
    if (exportBtn) {
      pane.addEventListener('click', function (ev) {
        var t = ev.target.closest('#qr-export');
        if (!t) return;
        if (t.classList.contains('disabled') || t.getAttribute('aria-disabled') === 'true') {
          ev.preventDefault();
          ev.stopPropagation();
          return false;
        }
      });
    }
  }

  // carregamento ao abrir a aba Resumo (mantém heurísticas existentes)
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    carregarQuadroResumo();
  } else {
    document.addEventListener('DOMContentLoaded', carregarQuadroResumo);
  }
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (t.matches('[data-tab-target="quadro_resumo"], a[href*="quadro_resumo"]')) {
      setTimeout(carregarQuadroResumo, 0);
    }
  });
})();
