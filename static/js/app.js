/* Rei do Feno — comportamento visual mínimo (sem lógica de negócio).
   Gaveta mobile · estado de envio em formulários · menus details. */
(function () {
  "use strict";

  var mobile = window.matchMedia("(max-width: 63.99rem)");

  /* ---------- Gaveta da navegação ---------- */
  var lateral = document.querySelector("[data-gaveta]");
  var veu = document.querySelector("[data-veu]");
  var abridores = Array.prototype.slice.call(document.querySelectorAll("[data-abrir-gaveta]"));
  var focoAnterior = null;

  function gaveta(aberta) {
    if (!lateral) return;
    lateral.dataset.aberta = String(aberta);
    if (veu) veu.dataset.visivel = String(aberta);
    abridores.forEach(function (b) { b.setAttribute("aria-expanded", String(aberta)); });
    document.body.style.overflow = aberta && mobile.matches ? "hidden" : "";
    if (aberta) {
      focoAnterior = document.activeElement;
      var alvo = lateral.querySelector("a[href], button:not([disabled])");
      if (alvo) alvo.focus();
    } else if (focoAnterior && document.body.contains(focoAnterior)) {
      focoAnterior.focus();
      focoAnterior = null;
    }
  }

  abridores.forEach(function (b) {
    b.addEventListener("click", function () {
      gaveta(lateral && lateral.dataset.aberta !== "true");
    });
  });
  if (veu) veu.addEventListener("click", function () { gaveta(false); });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && lateral && lateral.dataset.aberta === "true") {
      gaveta(false);
      return;
    }
    /* Armadilha de foco dentro da gaveta aberta (apenas mobile) */
    if (
      e.key === "Tab" &&
      mobile.matches &&
      lateral &&
      lateral.dataset.aberta === "true"
    ) {
      var focaveis = lateral.querySelectorAll('a[href], button:not([disabled])');
      if (!focaveis.length) return;
      var primeiro = focaveis[0];
      var ultimo = focaveis[focaveis.length - 1];
      if (e.shiftKey && document.activeElement === primeiro) {
        e.preventDefault();
        ultimo.focus();
      } else if (!e.shiftKey && document.activeElement === ultimo) {
        e.preventDefault();
        primeiro.focus();
      }
    }
  });

  window.matchMedia("(min-width: 64rem)").addEventListener("change", function (e) {
    if (e.matches) gaveta(false);
  });

  /* ---------- Estado de envio (evita duplo envio) ---------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.hasAttribute("data-enviando")) {
      e.preventDefault();
      return;
    }
    if (form.hasAttribute("data-no-busy")) return;
    form.setAttribute("data-enviando", "");
    var botoes = form.querySelectorAll('button[type="submit"]');
    setTimeout(function () {
      botoes.forEach(function (b) { b.setAttribute("aria-busy", "true"); b.disabled = true; });
    }, 150);
  });

  /* ---------- Menus <details> fecham ao clicar fora ---------- */
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details[open].detalhes-menu").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
})();
