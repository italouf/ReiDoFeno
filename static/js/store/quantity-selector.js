/* Rei do Feno — Loja · seletor de quantidade (limita mínimo e step) */
(function () {
  "use strict";

  document.querySelectorAll("input[data-quantidade]").forEach(function (input) {
    input.addEventListener("change", function () {
      var min = parseInt(input.getAttribute("min") || "1", 10);
      var valor = parseInt(input.value, 10);
      if (isNaN(valor) || valor < min) {
        input.value = min;
      }
    });
  });
})();
