#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recopilador de notas sobre RECLUTAMIENTO CRIMINAL (cualquier método) en la
ZONA METROPOLITANA (CDMX + Estado de México), desde abril 2025 hasta hoy.

A diferencia de `recopilar_noticias_mexico_mini.py` (busca en todo el país y
exige que la nota mencione redes/plataformas), este script:
  - Busca SOLO en la zona metropolitana: cada búsqueda combina un tema con
    los lugares de CDMX/Edomex (CDMX, Edomex, las 16 alcaldías y los
    municipios del Estado de México). Ya no se buscan notas de otros estados.
  - NO exige redes sociales. Los temas cubren reclutamiento criminal por
    cualquier método (presencial, panfletos, redes, lo que sea), siempre que
    se relacione con crimen organizado.

Las columnas `menciona_redes` y `plataformas_mencionadas` se conservan para
que puedas distinguir, ya con los resultados, cuáles sí fueron por redes.

Solo usa Google News RSS (sin GDELT ni NewsAPI, para evitar el ConnectionError
de GDELT). No incluye filtro de país: al buscar solo en lugares de la zona
metropolitana, casi no aparecen notas extranjeras.

Por defecto, `menciona_reclutamiento`, `menciona_redes`, `lugar_zm`,
`plataformas_mencionadas` y `prioridad` se calculan solo con el título y la
breve descripción que da Google News (el cuerpo completo casi nunca viene en
el RSS). Con --cuerpo-completo, el script además descarga cada nota y
recalcula esas columnas usando también el texto del artículo. Es más lento
(una solicitud por nota) y no siempre funciona (paywalls, bloqueos anti-bot,
sitios con mucho JavaScript), así que queda como opción aparte.

Requisitos:
    pip install -r requirements.txt

Uso:
    python recopilar_noticias_zm_general.py
    python recopilar_noticias_zm_general.py --inicio 2025-06-01 --fin 2025-06-30
    python recopilar_noticias_zm_general.py --cuerpo-completo
"""

import argparse
import html
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd
import requests

# --------------------------------------------------------------------------
# CONFIGURACIÓN DE BÚSQUEDA
# --------------------------------------------------------------------------
INICIO_DEFECTO = date(2025, 4, 1)

CRIMEN = ('("crimen organizado" OR cártel OR cárteles OR delincuencia OR "delincuencia organizada" '
          'OR "grupos criminales" OR "grupo criminal" OR "grupos delictivos" OR sicarios OR narcotráfico)')

# Los 4 temas NO exigen redes: cubren cualquier tipo de reclutamiento criminal.
TEMAS = [
    '("reclutamiento" OR "reclutan" OR "reclutar" OR "reclutados" OR "reclutadas") ' + CRIMEN,

    '"reclutamiento criminal"',

    '("ofertas de trabajo falsas" OR "falsas ofertas de empleo" OR "vacantes falsas" OR "ofertas laborales falsas") '
    + CRIMEN,

    '("reclutan" OR "reclutamiento" OR "captan") (jóvenes OR menores OR adolescentes OR niños) ' + CRIMEN,
]

GNEWS_LIMITE = 95  # Google News RSS devuelve máx. ~100 items por consulta

# --- Lugares: zona metropolitana = CDMX + Estado de México ---------------
# Se usan tanto para ARMAR las búsquedas (solo se busca en estos lugares) como
# para etiquetar cuál entidad aparece en el título/descripción de cada nota.
LUGARES_GENERALES = [
    "CDMX", "Ciudad de México", "Estado de México", "Edomex", "mexiquense",
    "mexiquenses", "zona metropolitana", "área metropolitana", "Valle de México", "ZMVM",
]

ALCALDIAS_CDMX = [
    "alcaldía Álvaro Obregón", "Azcapotzalco", "alcaldía Benito Juárez", "Coyoacán",
    "Cuajimalpa", "alcaldía Cuauhtémoc", "Gustavo A. Madero", "Iztacalco", "Iztapalapa",
    "Magdalena Contreras", "alcaldía Miguel Hidalgo", "Milpa Alta", "Tláhuac", "Tlalpan",
    "alcaldía Venustiano Carranza", "Xochimilco",
]

# Lista de referencia (NO exhaustiva: Edomex tiene 125 municipios). Se omitieron
# nombres que se confunden con lugares de otros estados (Tenancingo, Chiautla,
# Melchor Ocampo, Rayón, Villa Guerrero, El Oro, etc.). Amplíala si hace falta.
MUNICIPIOS_EDOMEX = [
    "Acolman", "Amecameca", "Apaxco", "Atenco", "Atizapán", "Atizapán de Zaragoza",
    "Atlautla", "Axapusco", "Ayapango", "Coacalco", "Cocotitlán", "Cuautitlán",
    "Cuautitlán Izcalli", "Chalco", "Chicoloapan", "Chiconcuac", "Chimalhuacán",
    "Ecatepec", "Ecatzingo", "Huehuetoca", "Hueypoxtla", "Huixquilucan", "Ixtapaluca",
    "Jaltenco", "Jilotzingo", "Juchitepec", "Los Reyes La Paz", "Naucalpan",
    "Nezahualcóyotl", "Nextlalpan", "Nicolás Romero", "Nopaltepec", "Otumba", "Ozumba",
    "Papalotla", "San Martín de las Pirámides", "Tecámac", "Temamatla", "Temascalapa",
    "Tenango del Aire", "Teoloyucan", "Teotihuacán", "Tepetlaoxtoc", "Tepetlixpa",
    "Tepotzotlán", "Tequixquiac", "Texcoco", "Tezoyuca", "Tlalmanalco", "Tlalnepantla",
    "Tonanitla", "Tultepec", "Tultitlán", "Valle de Chalco", "Villa del Carbón", "Zumpango",
    "Toluca", "Metepec", "Lerma", "Zinacantepec", "Almoloya de Juárez", "San Mateo Atenco",
    "Ocoyoacac", "Tianguistenco", "Tejupilco", "Valle de Bravo", "Ixtapan de la Sal",
    "Atlacomulco", "Ixtlahuaca", "Jilotepec", "Temoaya", "Xonacatlán", "Malinalco",
    "Tenango del Valle", "Coatepec Harinas", "Sultepec", "Luvianos", "Tlatlaya",
    "Amatepec", "Temascaltepec", "Villa Victoria", "Villa de Allende", "Jiquipilco",
    "Jocotitlán", "Acambay", "Aculco", "Temascalcingo", "Capulhuac", "Calimaya",
    "Mexicaltzingo", "Ocuilan", "Joquicingo", "Tonatico", "Zumpahuacán", "Xalatlaco",
    "Texcalyacac", "San Antonio la Isla", "Almoloya del Río", "Otzolotepec",
    "Chapa de Mota", "Timilpan", "Soyaniquilpan", "Polotitlán", "Donato Guerra",
    "Amanalco", "Ixtapan del Oro", "Otzoloapan", "Zacazonapan", "Zacualpan",
    "Texcaltitlán", "San Simón de Guerrero", "Santo Tomás", "San José del Rincón",
    "Almoloya de Alquisiras",
]

TODOS_LOS_LUGARES = LUGARES_GENERALES + ALCALDIAS_CDMX + MUNICIPIOS_EDOMEX

# Palabras clave para marcar relevancia (se comparan sin acentos y en minúsculas)
RE_RECLUTA = re.compile(r"reclut|enganch|ofertas? (falsas?|de (trabajo|empleo) falsas?)|vacantes? falsas?")
RE_REDES = re.compile(
    r"redes sociales|tiktok|facebook|instagram|whatsapp|telegram|discord|videojuego|"
    r"youtube|snapchat|twitter|internet|en linea|digital|plataforma"
)

_PLATAFORMAS = {
    "TikTok": r"tik ?tok", "Facebook": r"facebook", "Instagram": r"instagram",
    "WhatsApp": r"whats ?app", "Telegram": r"telegram", "Discord": r"discord",
    "YouTube": r"youtube", "Snapchat": r"snapchat", "X (Twitter)": r"twitter|red social x",
    "Twitch": r"twitch", "Roblox": r"roblox", "Free Fire": r"free fire",
    "Fortnite": r"fortnite", "Videojuegos": r"videojuegos?|gamers?",
}
RE_PLATAFORMAS = {k: re.compile(r"\b(?:" + v + r")\b") for k, v in _PLATAFORMAS.items()}

UA = "Mozilla/5.0 (compatible; recopilador-noticias/1.0)"
COLUMNAS = ["fecha", "titulo", "fuente", "dominio", "url", "descripcion",
            "consulta", "prioridad", "menciona_reclutamiento", "menciona_redes",
            "lugar_zm", "plataformas_mencionadas"]
COLUMNAS_CUERPO = ["texto_completo", "cuerpo_descargado"]  # se agregan solo con --cuerpo-completo

# Ancho de columna en el Excel, por nombre (las que no aparecen aquí usan 18)
ANCHOS_COLUMNAS = {
    "fecha": 18, "titulo": 70, "fuente": 22, "dominio": 24, "url": 60, "descripcion": 50,
    "consulta": 24, "prioridad": 10, "menciona_reclutamiento": 12, "menciona_redes": 12,
    "lugar_zm": 24, "plataformas_mencionadas": 26, "texto_completo": 70, "cuerpo_descargado": 14,
}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# UTILIDADES
# --------------------------------------------------------------------------
def normalizar(texto):
    """Minúsculas, sin acentos ni signos raros (para comparar y deduplicar)."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\.]", " ", texto)).strip()


def _entrecomillar(termino):
    return f'"{termino}"' if " " in termino else termino


def agrupar(terminos, max_chars):
    """Junta los términos en grupos '(a OR b OR c)' de máx. `max_chars` caracteres."""
    grupos, actual = [], []
    for t in terminos:
        candidato = " OR ".join(_entrecomillar(x) for x in actual + [t])
        if actual and len(candidato) + 2 > max_chars:
            grupos.append("(" + " OR ".join(_entrecomillar(x) for x in actual) + ")")
            actual = [t]
        else:
            actual.append(t)
    if actual:
        grupos.append("(" + " OR ".join(_entrecomillar(x) for x in actual) + ")")
    return grupos


def construir_consultas(presupuesto_lugares=380):
    """
    Devuelve [(etiqueta, consulta)] = cada TEMA x cada grupo de lugares.
    Como todos los grupos se consultan para todos los temas y en todas las
    ventanas de fechas, ningún lugar queda favorecido sobre otro.
    """
    consultas = []
    for n, tema in enumerate(TEMAS, 1):
        for k, grupo in enumerate(agrupar(TODOS_LOS_LUGARES, presupuesto_lugares), 1):
            consultas.append((f"tema{n}/lugares{k}", f"{tema} {grupo}"))
    return consultas


# --- Etiqueta de qué entidad aparece (CDMX / Estado de México) -----------
_ENTIDAD_DE_TERMINO = {}
for _t in LUGARES_GENERALES:
    if _t in ("CDMX", "Ciudad de México"):
        _ENTIDAD_DE_TERMINO[normalizar(_t)] = "CDMX"
    elif _t in ("Estado de México", "Edomex", "mexiquense", "mexiquenses"):
        _ENTIDAD_DE_TERMINO[normalizar(_t)] = "Estado de México"
    else:
        _ENTIDAD_DE_TERMINO[normalizar(_t)] = None  # "zona metropolitana", "Valle de México"... ambiguos
for _t in ALCALDIAS_CDMX:
    _ENTIDAD_DE_TERMINO[normalizar(_t)] = "CDMX"
for _t in MUNICIPIOS_EDOMEX:
    _ENTIDAD_DE_TERMINO[normalizar(_t)] = "Estado de México"

RE_ZM = re.compile("|".join(
    r"\b" + re.escape(t) + r"\b" for t in sorted(_ENTIDAD_DE_TERMINO, key=len, reverse=True)
))
_ORDEN_ENTIDADES = ("CDMX", "Estado de México")


def etiquetar_zm(texto_norm):
    """
    Devuelve lugar_zm para un texto normalizado: "CDMX", "Estado de México",
    "CDMX; Estado de México", "Sin especificar" (solo dice "zona metropolitana"
    o "Valle de México"), o "" si el texto no nombra ningún lugar (aunque la
    nota sí haya salido de la búsqueda de zona metropolitana).
    """
    encontradas, hay_zm = set(), False
    for m in RE_ZM.finditer(texto_norm):
        hay_zm = True
        entidad = _ENTIDAD_DE_TERMINO[m.group(0)]
        if entidad:
            encontradas.add(entidad)
    if not hay_zm:
        return ""
    if not encontradas:
        return "Sin especificar"
    return "; ".join(e for e in _ORDEN_ENTIDADES if e in encontradas)


def limpiar_html(texto):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))).strip()


def dominio_de(url):
    d = urlparse(url or "").netloc.lower()
    return d[4:] if d.startswith("www.") else d


def limpiar_url(url):
    """Quita parámetros de rastreo (utm_*, fbclid, etc.) para deduplicar mejor."""
    try:
        p = urlparse(url)
        q = [(k, v) for k, v in parse_qsl(p.query)
             if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid", "ref")]
        return urlunparse(p._replace(query=urlencode(q), fragment=""))
    except Exception:
        return url


def http_get(sesion, url, params, pausa, intentos=4):
    """GET con reintentos y espera progresiva. Devuelve Response o None."""
    for i in range(intentos):
        try:
            r = sesion.get(url, params=params, timeout=40)
        except requests.RequestException as e:
            log(f"   red/timeout ({e.__class__.__name__}); reintento {i + 1}/{intentos}")
            time.sleep(pausa * (i + 2))
            continue
        if r.status_code == 200:
            time.sleep(pausa)
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            espera = pausa * (2 ** (i + 1))
            log(f"   HTTP {r.status_code}; espero {espera:.0f}s y reintento {i + 1}/{intentos}")
            time.sleep(espera)
            continue
        log(f"   HTTP {r.status_code} en {url}")
        return None
    return None


def dividir_ventana(fetch, d0, d1, limite, min_dias=1):
    """
    Consulta [d0, d1). Si la respuesta llega al tope de resultados, parte la
    ventana a la mitad y consulta cada mitad (recursivo) para no perder notas.
    """
    items = fetch(d0, d1)
    dias = (d1 - d0).days
    if len(items) >= limite and dias > min_dias:
        mitad = d0 + timedelta(days=dias // 2)
        return dividir_ventana(fetch, d0, mitad, limite, min_dias) + \
               dividir_ventana(fetch, mitad, d1, limite, min_dias)
    if len(items) >= limite:
        log(f"   AVISO: {d0} llegó al tope de resultados con ventana de 1 día; puede haber notas sin capturar")
    return items


def ventanas(inicio, fin, dias):
    """Genera pares (d0, d1) que cubren [inicio, fin] en pasos de `dias`."""
    d0 = inicio
    fin_excl = fin + timedelta(days=1)
    while d0 < fin_excl:
        d1 = min(d0 + timedelta(days=dias), fin_excl)
        yield d0, d1
        d0 = d1


# --------------------------------------------------------------------------
# GOOGLE NEWS RSS (única fuente en esta versión)
# --------------------------------------------------------------------------
def parsear_gnews_rss(contenido, consulta):
    registros = []
    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError:
        return registros
    for it in raiz.iter("item"):
        titulo = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        src = it.find("source")
        fuente = (src.text or "").strip() if src is not None else ""
        dom = dominio_de(src.get("url", "")) if src is not None else ""
        if fuente and titulo.endswith(" - " + fuente):
            titulo = titulo[: -(len(fuente) + 3)].strip()
        desc = limpiar_html(it.findtext("description") or "")
        if normalizar(desc).startswith(normalizar(titulo)):
            desc = ""  # Google repite título + fuente; no aporta
        fecha = None
        if pub:
            try:
                fecha = parsedate_to_datetime(pub).astimezone(timezone.utc).replace(tzinfo=None)
            except (TypeError, ValueError):
                pass
        registros.append(dict(fecha=fecha, titulo=titulo, fuente=fuente, dominio=dom,
                              url=link, descripcion=desc, consulta=consulta))
    return registros


def recolectar_gnews(inicio, fin, dias_ventana, pausa):
    sesion = requests.Session()
    sesion.headers["User-Agent"] = UA
    consultas = construir_consultas()
    log(f"[Google News] {len(consultas)} búsquedas (temas x grupos de lugares)")
    todo = []
    for i, (etiqueta, consulta) in enumerate(consultas, 1):
        log(f"[Google News] búsqueda {i}/{len(consultas)} ({etiqueta})")

        def fetch(d0, d1, consulta=consulta, etiqueta=etiqueta):
            q = f"{consulta} after:{d0.isoformat()} before:{d1.isoformat()}"
            params = {"q": q, "hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}
            r = http_get(sesion, "https://news.google.com/rss/search", params, pausa)
            items = parsear_gnews_rss(r.content, etiqueta) if r is not None else []
            log(f"   {d0} -> {d1}: {len(items)} notas")
            return items

        for d0, d1 in ventanas(inicio, fin, dias_ventana):
            todo += dividir_ventana(fetch, d0, d1, GNEWS_LIMITE)
    return todo


# --------------------------------------------------------------------------
# CONSOLIDACIÓN Y ETIQUETAS (a partir de título + descripción)
# --------------------------------------------------------------------------
def _calcular_etiquetas(df, texto):
    """Recalcula menciona_reclutamiento, menciona_redes, prioridad, lugar_zm y
    plataformas_mencionadas a partir de una Serie de texto ya normalizado
    (una por fila de `df`). Se usa tanto con título+descripción como, si se
    activa --cuerpo-completo, con título+descripción+cuerpo."""
    df["menciona_reclutamiento"] = texto.map(lambda t: bool(RE_RECLUTA.search(t)))
    df["menciona_redes"] = texto.map(lambda t: bool(RE_REDES.search(t)))
    df["prioridad"] = "baja"
    df.loc[df["menciona_reclutamiento"], "prioridad"] = "media"
    df.loc[df["menciona_reclutamiento"] & df["menciona_redes"], "prioridad"] = "alta"
    df["lugar_zm"] = texto.map(etiquetar_zm)
    df["plataformas_mencionadas"] = texto.map(
        lambda t: "; ".join(k for k, rx in RE_PLATAFORMAS.items() if rx.search(t)))
    return df


def consolidar(registros, inicio, fin):
    """Filtra por fechas, deduplica (título normalizado + dominio) y agrega etiquetas."""
    unicos = {}
    for r in registros:
        if not r["titulo"]:
            continue
        f = r["fecha"]
        if f is not None and not (inicio <= f.date() <= fin):
            continue
        clave = (normalizar(r["titulo"])[:120], r["dominio"] or normalizar(r["fuente"]))
        if clave in unicos:
            u = unicos[clave]
            u["consulta"] = "|".join(sorted(set(u["consulta"].split("|")) | {r["consulta"]}))
            if not u["descripcion"] and r["descripcion"]:
                u["descripcion"] = r["descripcion"]
        else:
            r = dict(r)
            r["url"] = limpiar_url(r["url"])
            unicos[clave] = r

    df = pd.DataFrame(list(unicos.values()))
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS)

    texto = (df["titulo"].fillna("") + " " + df["descripcion"].fillna("")).map(normalizar)
    df = _calcular_etiquetas(df, texto)

    df = df.sort_values("fecha", ascending=False, na_position="last").reset_index(drop=True)
    return df[COLUMNAS]


def decodificar_links(df):
    """Reemplaza los enlaces de Google News por la URL real (requiere googlenewsdecoder)."""
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        log("Para --decodificar-links (o --cuerpo-completo) instala: pip install googlenewsdecoder")
        return df
    urls = []
    for i, u in enumerate(df["url"], 1):
        if "news.google.com" in u:
            try:
                res = gnewsdecoder(u, interval=1)
                u = res["decoded_url"] if res.get("status") else u
            except Exception:
                pass
            if i % 25 == 0:
                log(f"   decodificados {i}/{len(df)}")
        urls.append(u)
    df["url"] = urls
    return df


# --------------------------------------------------------------------------
# CUERPO COMPLETO (opcional, --cuerpo-completo)
# --------------------------------------------------------------------------
_RE_TAGS_RUIDO = re.compile(r"<(script|style|nav|header|footer|aside|form)[^>]*>.*?</\1>", re.I | re.S)
_avisado_trafilatura = False


def _hay_trafilatura():
    try:
        import trafilatura  # noqa: F401
        return True
    except ImportError:
        return False


def _extraer_texto_basico(html_texto):
    """Fallback sin trafilatura: quita <script>/<style>/menús obvios y el resto de etiquetas.
    Es más ruidoso (puede traer menús, pies de página, etc.) que trafilatura."""
    limpio = _RE_TAGS_RUIDO.sub(" ", html_texto)
    return limpiar_html(limpio)


def obtener_cuerpo(sesion, url, pausa, max_chars):
    """Descarga una nota y extrae su texto principal. Devuelve '' si falla o si
    la URL sigue siendo una redirección de Google News (no se pudo decodificar)."""
    global _avisado_trafilatura
    if not url or "news.google.com" in url:
        return ""
    try:
        r = sesion.get(url, timeout=20)
    except requests.RequestException:
        return ""
    finally:
        time.sleep(pausa)
    if r.status_code != 200 or not r.text:
        return ""
    if _hay_trafilatura():
        import trafilatura
        texto = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
    else:
        if not _avisado_trafilatura:
            log("   Para mejor extracción del cuerpo instala: pip install trafilatura "
                "(usando un método más básico mientras tanto)")
            _avisado_trafilatura = True
        texto = _extraer_texto_basico(r.text)
    return texto.strip()[:max_chars]


def enriquecer_con_cuerpo(df, pausa, max_chars):
    """
    Descarga el cuerpo de cada nota (requiere URLs ya decodificadas) y
    recalcula menciona_reclutamiento, menciona_redes, prioridad, lugar_zm y
    plataformas_mencionadas usando título + descripción + cuerpo.
    """
    sesion = requests.Session()
    sesion.headers["User-Agent"] = UA
    cuerpos = []
    log(f"[Cuerpo completo] descargando {len(df)} notas...")
    for i, url in enumerate(df["url"], 1):
        cuerpos.append(obtener_cuerpo(sesion, url, pausa, max_chars))
        if i % 20 == 0 or i == len(df):
            log(f"   {i}/{len(df)} notas procesadas")

    df = df.copy()
    df["texto_completo"] = cuerpos
    df["cuerpo_descargado"] = df["texto_completo"].str.len() > 0
    log(f"[Cuerpo completo] {int(df['cuerpo_descargado'].sum())}/{len(df)} notas con cuerpo descargado "
        f"(las demás: enlace sin decodificar, bloqueo del sitio, error de red, etc.)")

    texto = (df["titulo"].fillna("") + " " + df["descripcion"].fillna("") + " "
             + df["texto_completo"].fillna("")).map(normalizar)
    df = _calcular_etiquetas(df, texto)
    return df[COLUMNAS + COLUMNAS_CUERPO]


# --------------------------------------------------------------------------
# EXPORTACIÓN
# --------------------------------------------------------------------------
def exportar(df, base):
    csv_path, xlsx_path = f"{base}.csv", f"{base}.xlsx"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")  # utf-8-sig: Excel abre bien los acentos
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        df[df["prioridad"] == "alta"].to_excel(w, sheet_name="Alta prioridad", index=False)
        df.to_excel(w, sheet_name="Todas", index=False)
        for hoja in w.book.worksheets:
            hoja.freeze_panes = "A2"
            hoja.auto_filter.ref = hoja.dimensions
            for i, col in enumerate(df.columns, start=1):
                hoja.column_dimensions[hoja.cell(row=1, column=i).column_letter].width = \
                    ANCHOS_COLUMNAS.get(col, 18)
    return csv_path, xlsx_path


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inicio", type=date.fromisoformat, default=INICIO_DEFECTO, help="YYYY-MM-DD (def. 2025-04-01)")
    ap.add_argument("--fin", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD (def. hoy)")
    ap.add_argument("--dias-ventana", type=int, default=10, help="tamaño inicial de ventana de fechas")
    ap.add_argument("--pausa", type=float, default=1.5, help="segundos entre solicitudes a Google News")
    ap.add_argument("--decodificar-links", action="store_true",
                    help="resolver URL real de Google News (se activa solo con --cuerpo-completo)")
    ap.add_argument("--cuerpo-completo", action="store_true",
                    help="descarga el texto de cada nota y recalcula las columnas con él (más lento; "
                         "requiere decodificar los enlaces primero, ver requirements.txt)")
    ap.add_argument("--pausa-cuerpo", type=float, default=1.0, help="segundos entre descargas de cuerpo")
    ap.add_argument("--max-caracteres-cuerpo", type=int, default=6000,
                    help="cuántos caracteres del cuerpo de cada nota guardar")
    ap.add_argument("--salida", default="noticias_reclutamiento_zm_general", help="prefijo de archivos de salida")
    a = ap.parse_args()

    if a.inicio > a.fin:
        sys.exit("--inicio no puede ser posterior a --fin")
    log(f"Periodo: {a.inicio} -> {a.fin} | fuente: Google News (solamente) | lugares: CDMX + Estado de México")

    registros = []
    try:
        registros = recolectar_gnews(a.inicio, a.fin, a.dias_ventana, a.pausa)
    except KeyboardInterrupt:
        log("\nInterrumpido: guardo lo recolectado hasta ahora...")

    df = consolidar(registros, a.inicio, a.fin)
    total_unicas = len(df)

    if a.cuerpo_completo and not df.empty:
        if not a.decodificar_links:
            log("--cuerpo-completo necesita las URL reales: decodificando enlaces primero...")
        df = decodificar_links(df)
        df = enriquecer_con_cuerpo(df, a.pausa_cuerpo, a.max_caracteres_cuerpo)
    elif a.decodificar_links and not df.empty:
        df = decodificar_links(df)

    csv_path, xlsx_path = exportar(df, a.salida)

    log(f"\nListo. {len(registros)} registros brutos -> {total_unicas} notas únicas")
    if not df.empty:
        log(df["prioridad"].value_counts().to_string())
        log(df["lugar_zm"].value_counts(dropna=False).to_string())
    log(f"Archivos: {csv_path} | {xlsx_path}")


if __name__ == "__main__":
    main()
