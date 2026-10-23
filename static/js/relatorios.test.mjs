import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("./relatorios.js", import.meta.url),
  "utf8"
);

function criarHarness({ dpr = 1 } = {}) {
  const listeners = {};
  const canvas = {
    dataset: {
      chart: "grouped",
      labels: JSON.stringify(["FS", "Iaçu"]),
      series: JSON.stringify([
        { label: "Receita", color: "#2f6b4f", values: [100, 80] },
        { label: "CMV", color: "#b07d3f", values: [60, 40] },
      ]),
    },
    style: {},
    width: 0,
    height: 0,
    _attributeHeight: "240",
    getAttribute(name) {
      return name === "height" ? this._attributeHeight : null;
    },
    parentElement: {
      clientWidth: 800,
      getBoundingClientRect() {
        return { width: 800, height: 240 };
      },
    },
    getContext() {
      return new Proxy(
        {
          measureText() {
            return { width: 40 };
          },
        },
        {
          get(target, prop) {
            if (prop in target) return target[prop];
            return () => {};
          },
          set(target, prop, value) {
            target[prop] = value;
            return true;
          },
        }
      );
    },
  };
  Object.defineProperty(canvas, "height", {
    get() {
      return this._height || 0;
    },
    set(value) {
      this._height = Number(value);
      this._attributeHeight = String(value);
    },
  });

  const window = {
    devicePixelRatio: dpr,
    setTimeout,
    clearTimeout,
    addEventListener(name, handler) {
      listeners[name] = handler;
    },
  };
  const document = {
    readyState: "complete",
    querySelectorAll() {
      return [canvas];
    },
    addEventListener() {},
  };
  const context = vm.createContext({
    window,
    document,
    JSON,
    String,
    Number,
    Math,
    console,
    setTimeout,
    clearTimeout,
  });
  vm.runInContext(source, context, { filename: "relatorios.js" });

  const fireResize = () => {
    assert.ok(listeners.resize, "handler de resize registrado");
    listeners.resize();
  };
  return { canvas, window, fireResize };
}

const espera = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("DPR 1 mantém altura lógica e backing store 1x", async () => {
  const { canvas, fireResize } = criarHarness({ dpr: 1 });
  fireResize();
  await espera(180);

  assert.equal(canvas.style.height, "240px");
  assert.equal(canvas.height, 240);
});

test("DPR 2 não acumula altura em resizes sucessivos", async () => {
  const { canvas, window, fireResize } = criarHarness({ dpr: 1 });
  window.devicePixelRatio = 2;

  for (let i = 0; i < 4; i += 1) {
    fireResize();
    await espera(180);
    assert.equal(canvas.style.height, "240px");
    assert.equal(canvas.height, 480);
    assert.equal(canvas.dataset.logicalHeight, "240");
  }
});
