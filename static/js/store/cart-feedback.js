/* Rei do Feno — Loja · feedback visual: revelar imagens, pulsar contador, toast */
(function () {
  "use strict";

  /* Revela imagens quando carregam (skeleton some por cima delas) */
  function revelar(img) {
    if (img.complete && img.naturalWidth > 0) img.classList.add("carregada");
    else img.addEventListener("load", function () { img.classList.add("carregada"); });
    img.addEventListener("error", function () { img.style.display = "none"; });
  }
  document.querySelectorAll(".card-produto__midia img, .produto-detalhe__midia img, .item-carrinho .produto-imagem")
    .forEach(revelar);

  /* Pulsa o contador quando a página confirma uma ação (ex.: item adicionado) */
  var contador = document.querySelector("[data-carrinho-contador]");
  if (contador && !contador.hidden && document.querySelector(".alerta--sucesso")) {
    contador.classList.add("pulsa");
    contador.addEventListener("animationend", function () { contador.classList.remove("pulsa"); }, { once: true });
  }
})();
