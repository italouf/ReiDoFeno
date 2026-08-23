"""Busca fotos licenciadas no Wikimedia Commons e baixa versões de 800px (descartável)."""
import json
import pathlib
import urllib.parse
import urllib.request

DEST = pathlib.Path("static/img/produtos")
DEST.mkdir(parents=True, exist_ok=True)

BUSCAS = {
    "sal-mineral.jpg": "salt block",
    "suplemento.jpg": "cattle feed",
}

PREFERENCIA_LICENCA = ["CC0", "CC BY-SA", "CC BY", "Public domain", "GFDL"]

UA = {"User-Agent": "ReiDoFenoDev/1.0 (contato@reidofeno.com.br)"}


def api(params):
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


for nome_arquivo, termo in BUSCAS.items():
    destino = DEST / nome_arquivo
    if destino.exists() and destino.stat().st_size > 20000:
        print("já existe:", nome_arquivo)
        continue
    dados = api({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": termo, "gsrnamespace": "6", "gsrlimit": "10",
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata|size", "iiurlwidth": "900",
    })
    paginas = sorted((dados.get("query", {}).get("pages", {}) or {}).values(),
                     key=lambda p: p.get("index", 99))
    candidatas = []
    for p in paginas:
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("mime") not in ("image/jpeg", "image/png"):
            continue
        largura, altura = info.get("width", 0), info.get("height", 0)
        if largura < 1000 or altura < 600:
            continue
        meta = info.get("extmetadata", {})
        licenca = (meta.get("LicenseShortName", {}) or {}).get("value", "?")
        if any(x in licenca for x in ("Fair use", "non-free")):
            continue
        rank = next((i for i, pref in enumerate(PREFERENCIA_LICENCA)
                     if licenca.startswith(pref) or pref in licenca), len(PREFERENCIA_LICENCA))
        candidatas.append((rank, p, info, licenca))
    candidatas.sort(key=lambda c: c[0])
    escolhida = candidatas[0] if candidatas else None
    if escolhida:
        _, pagina, info, licenca = escolhida
    if not escolhida:
        print("SEM RESULTADO:", nome_arquivo, termo)
        continue
    url = info.get("thumburl") or info.get("url")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
        f.write(r.read())
    artista = (info.get("extmetadata", {}).get("Artist", {}) or {}).get("value", "?")
    print(f"OK {nome_arquivo} | {pagina['title']} | {licenca} | {artista[:60]} | {url[:90]}")
