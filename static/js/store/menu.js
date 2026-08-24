/* Rei do Feno — Loja · menu mobile de categorias */
(function () {
  "use strict";

  var botao = document.querySelector("[data-abrir-menu]");
  var menu = document.querySelector("[data-menu]");

  if (botao && menu) {
    botao.addEventListener("click", function () {
      var aberto = menu.dataset.aberta === "true";
      menu.dataset.aberta = String(!aberto);
      botao.setAttribute("aria-expanded", String(!aberto));
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.dataset.aberta === "true") {
        menu.dataset.aberta = "false";
        botao.setAttribute("aria-expanded", "false");
        botao.focus();
      }
    });
    window.matchMedia("(min-width: 64rem)").addEventListener("change", function (e) {
      if (e.matches) {
        menu.dataset.aberta = "false";
        botao.setAttribute("aria-expanded", "false");
      }
    });
  }
})();
