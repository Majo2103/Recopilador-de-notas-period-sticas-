#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NOTAS DE USO 

Versión MINI: recopilador de notas sobre RECLUTAMIENTO CRIMINAL POR REDES
en TODO MÉXICO (abril 2025 -> hoy), con etiqueta de ZONA METROPOLITANA.

Diferencias con `recopilar_noticias_mexico.py`:
  - Solo usa Google News RSS. Se quitaron GDELT y NewsAPI (GDELT fallaba
    seguido con ConnectionError, y ninguna de las dos era indispensable).
  - Los 3 temas de búsqueda EXIGEN mención de redes/plataformas/internet.
    Se quitó el tema de "reclutamiento criminal" a secas (no mencionaba
    redes) y se le agregó ese requisito al tema de ofertas de trabajo falsas.

Lo demás se mantiene igual: etiqueta de zona metropolitana (CDMX + Estado de
México) y filtro de notas de otros países.

Requisitos:
    pip install -r requirements.txt

Uso:
    python recopilar_noticias_mexico_mini.py
    python recopilar_noticias_mexico_mini.py --inicio 2025-06-01 --fin 2025-06-30
    python recopilar_noticias_mexico_mini.py --filtro-pais estricto
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

#Redes sociales 
REDES = ('("redes sociales" OR TikTok OR Facebook OR Instagram OR WhatsApp OR Telegram OR Discord '
         'OR YouTube OR Snapchat OR "en línea" OR internet OR digital OR videojuegos)')

# TEMAS CON REQUISITO DE REDES/PLATAFORMAS/INTERNET 
TEMAS = [
    '("reclutamiento" OR "reclutan" OR "reclutar" OR "reclutados" OR "reclutadas") '
    + REDES + " " + CRIMEN,

    '("ofertas de trabajo falsas" OR "falsas ofertas de empleo" OR "vacantes falsas" OR "ofertas laborales falsas") '
    '("crimen organizado" OR cártel OR delincuencia OR "grupos criminales") ' + REDES,

    '("reclutan" OR "reclutamiento" OR "captan") (jóvenes OR menores OR adolescentes OR niños) '
    + CRIMEN + " " + REDES,
]

GNEWS_LIMITE = 95  # Google News RSS devuelve máx. ~100 items por consulta

# --- Zona metropolitana = CDMX + Estado de México (solo para etiquetar) ---
ALIAS_CDMX = ["CDMX", "Ciudad de México"]
ALCALDIAS_CDMX = [
    "alcaldía Álvaro Obregón", "Azcapotzalco", "alcaldía Benito Juárez", "Coyoacán",
    "Cuajimalpa", "alcaldía Cuauhtémoc", "Gustavo A. Madero", "Iztacalco", "Iztapalapa",
    "Magdalena Contreras", "alcaldía Miguel Hidalgo", "Milpa Alta", "Tláhuac", "Tlalpan",
    "alcaldía Venustiano Carranza", "Xochimilco",
]

ALIAS_EDOMEX = ["Estado de México", "Edomex", "mexiquense", "mexiquenses"]
# Lista de referencia generada por Claude (IA). No es exhaustiva: Edomex tiene 125 municipios. Se omitieron
# nombres que se confunden con lugares de otros estados (Tenancingo, Chiautla, Melchor Ocampo, Rayón, Villa Guerrero, El Oro, etc.). 
# Amplíala si hace falta.
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

# "Zona metropolitana" a secas NO cuenta: en el resto del país puede referirse a
# Guadalajara, Monterrey, etc. Estos términos sí indican el Valle de México.

GENERICOS_ZM = ["Valle de México", "ZMVM"]

# Palabras clave para marcar relevancia (se comparan sin acentos y en minúsculas)
RE_RECLUTA = re.compile(r"reclut|enganch|ofertas? (falsas?|de (trabajo|empleo) falsas?)|vacantes? falsas?")
RE_REDES = re.compile(
    r"redes sociales|tiktok|facebook|instagram|whatsapp|telegram|discord|videojuego|"
    r"youtube|snapchat|twitter|internet|en linea|digital|plataforma"
)

# listas de palabras clave para detectar menciones de redes sociales y plataformas
_PLATAFORMAS = {
    "TikTok": r"tik ?tok", "Facebook": r"facebook", "Instagram": r"instagram",
    "WhatsApp": r"whats ?app", "Telegram": r"telegram", "Discord": r"discord",
    "YouTube": r"youtube", "Snapchat": r"snapchat", "X (Twitter)": r"twitter|red social x",
    "Twitch": r"twitch", "Roblox": r"roblox", "Free Fire": r"free fire",
    "Fortnite": r"fortnite", "Videojuegos": r"videojuegos?|gamers?",
}
RE_PLATAFORMAS = {k: re.compile(r"\b(?:" + v + r")\b") for k, v in _PLATAFORMAS.items()}

UA = "Mozilla/5.0 (compatible; recopilador-noticias/1.0)"

#columnas del DataFrame final (ordenadas)
COLUMNAS = ["fecha", "titulo", "fuente", "dominio", "url", "descripcion",
            "consulta", "prioridad", "menciona_reclutamiento", "menciona_redes",
            "zona_metropolitana", "lugar_zm", "ambito", "paises_extranjeros",
            "plataformas_mencionadas"]


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


# --- Etiqueta de zona metropolitana (CDMX + Estado de México) -------------
_ENTIDAD_DE_TERMINO = {}
for _lista, _entidad in ((ALIAS_CDMX + ALCALDIAS_CDMX, "CDMX"),
                         (ALIAS_EDOMEX + MUNICIPIOS_EDOMEX, "Estado de México"),
                         (GENERICOS_ZM, None)):
    for _t in _lista:
        _ENTIDAD_DE_TERMINO[normalizar(_t)] = _entidad

RE_ZM = re.compile("|".join(
    r"\b" + re.escape(t) + r"\b" for t in sorted(_ENTIDAD_DE_TERMINO, key=len, reverse=True)
))
_ORDEN_ENTIDADES = ("CDMX", "Estado de México")


def etiquetar_zm(texto_norm):
    """
    Devuelve (zona_metropolitana: bool, lugar_zm: str) para un texto normalizado.
    lugar_zm: "CDMX", "Estado de México", "CDMX; Estado de México" o
    "Sin especificar" (si solo dice "Valle de México" / "ZMVM"); vacío si no aplica.
    """
    encontradas, hay_zm = set(), False
    for m in RE_ZM.finditer(texto_norm):
        hay_zm = True
        entidad = _ENTIDAD_DE_TERMINO[m.group(0)]
        if entidad:
            encontradas.add(entidad)
    if not hay_zm:
        return False, ""
    if not encontradas:
        return True, "Sin especificar"
    return True, "; ".join(e for e in _ORDEN_ENTIDADES if e in encontradas)


# ==========================================================================
# FILTRO DE NOTAS DE OTROS PAÍSES
# ==========================================================================
# Cada nota recibe un `ambito` según lo que dicen su título/descripción y el
# dominio del medio:
#   "México"          -> menciona lugares o términos mexicanos y ningún otro país
#   "Mixto"           -> menciona México y también otro país (p. ej. EE.UU.)
#   "Extranjero"      -> menciona otro país y nada de México (o el medio es de otro país
#                        y el texto no nombra ningún lugar mexicano)
#   "Sin identificar" -> no hay ninguna señal (p. ej. "Reclutan jóvenes por TikTok")
#
# Con --filtro-pais se decide qué se aparta de las hojas/archivos principales:
#   ninguno   : no aparta nada (solo etiqueta)
#   moderado  : aparta "Extranjero" (por defecto)
#   estricto  : aparta "Extranjero" y "Mixto"
# Lo apartado no se borra: va a la hoja "Otros países" y al CSV *_otros_paises.csv.

def _rx(patron):
    return re.compile(r"(?<!\w)(?:" + patron + r")(?!\w)")


_ESTADOS_MX = (
    r"aguascalientes|baja california(?: sur)?|campeche|chiapas|chihuahua|coahuila|colima|"
    r"durango|guanajuato|jalisco|michoacan|morelos|nayarit|nuevo leon|oaxaca|puebla|"
    r"queretaro|quintana roo|san luis potosi|sinaloa|sonora|tabasco|tamaulipas|tlaxcala|"
    r"veracruz|yucatan|zacatecas|(?:en|estado de) (?:guerrero|hidalgo)|guerrerenses?|hidalguenses?"
)
_OTRAS_SENALES_MX = (
    r"(?<!nuevo )mexico|mexican[oa]s?|cjng|fgr|sedena|guardia nacional|sheinbaum|amlo|"
    r"tijuana|monterrey|guadalajara|culiacan|mexicali|ciudad juarez|acapulco|cancun|"
    r"torreon|reynosa|matamoros|nuevo laredo|morelia|hermosillo|saltillo|mazatlan|zapopan|"
    r"villahermosa|xalapa|cuernavaca|pachuca|tepic"
)
RE_MEXICO = _rx(_ESTADOS_MX + "|" + _OTRAS_SENALES_MX)

# lista de países y gentilicios para detectar menciones de otros países (no exhaustiva)
_PAISES_EXTRANJEROS = {
    "Colombia": r"colombia|colombian[oa]s?",
    "Ecuador": r"ecuador|ecuatorian[oa]s?",
    "Perú": r"peru|peruan[oa]s?",
    "Bolivia": r"bolivia|bolivian[oa]s?",
    "Chile": r"chile|chilen[oa]s?",
    "Argentina": r"argentina|argentin[oa]s?",
    "Uruguay": r"uruguay|uruguay[oa]s?",
    "Paraguay": r"paraguay|paraguay[oa]s?",
    "Brasil": r"brasil|brazil|brasilen[oa]s?",
    "Venezuela": r"venezuela|venezolan[oa]s?",
    "Guatemala": r"guatemala|guatemaltec[oa]s?",
    "Honduras": r"honduras|hondure[nñ][oa]s?|honduren[oa]s?",
    "El Salvador": r"el salvador|salvadoren[oa]s?",
    "Nicaragua": r"nicaragua|nicaraguenses?",
    "Costa Rica": r"costa rica|costarricenses?",
    "Panamá": r"panama|panamen[oa]s?",
    "Cuba": r"cuba|cuban[oa]s?",
    "República Dominicana": r"republica dominicana|dominican[oa]s?",
    "Haití": r"haiti|haitian[oa]s?",
    "Puerto Rico": r"puerto rico|puertorriquen[oa]s?",
    "España": r"espana|espanoles|espanolas",
    "Estados Unidos": (r"estados unidos(?! mexicanos)|ee\.? ?uu\.?|eeuu|estadounidenses?|nuevo mexico|"
                       r"nueva york|(?<!baja )california|texas|florida|arizona|chicago|washington"),
    "Canadá": r"canada|canadienses?",
    "Reino Unido": r"reino unido|inglaterra|britanic[oa]s?|londres|escocia",
    "Francia": r"francia|franceses|francesas",
    "Alemania": r"alemania|alemanes|alemanas",
    "Italia": r"italia|italian[oa]s?",
    "Portugal": r"portugal",
    "Rusia": r"rusia|rusos|rusas",
    "Ucrania": r"ucrania|ucranian[oa]s?",
    "China": r"china",
    "Israel": r"israel|israeli(?:es)?",
    "Palestina": r"palestina|palestin[oa]s?",
    "Irán": r"iran|iranies?",
    "Siria": r"siria|sirios|sirias",
    "Afganistán": r"afganistan|afgan[oa]s?",
    "Nigeria": r"nigeria|nigerian[oa]s?",
    "Turquía": r"turquia|turc[oa]s?",
    "Japón": r"japon|japones(?:es|a|as)?",
    "Filipinas": r"filipinas|filipin[oa]s?",
    "Australia": r"australia|australian[oa]s?",
}
RE_PAISES = {pais: _rx(p) for pais, p in _PAISES_EXTRANJEROS.items()}

RE_TLD_EXTRANJERO = re.compile(
    r"\.(co|ec|pe|cl|ar|es|ve|gt|bo|uy|py|br|cu|do|pa|cr|sv|hn|ni|pr|uk|fr|de|it|ru|cn|ca|au|jp)$")


#FUNCIONES PARA CREAR Y LIMPIAR EL DATAFRAME FINAL

def clasificar_ambito(texto_norm, dominio):
    """
    Devuelve (ambito, paises_extranjeros) para un texto ya normalizado y el dominio del medio.
    `paises_extranjeros`: países mencionados en el texto, o "(medio .xx)" si solo se
    dedujo por la terminación del dominio.
    """
    hay_mx = bool(RE_MEXICO.search(texto_norm)) or bool(RE_ZM.search(texto_norm))
    paises = [p for p, rx in RE_PAISES.items() if rx.search(texto_norm)]
    d = (dominio or "").lower()
    tld = RE_TLD_EXTRANJERO.search(d)
    if hay_mx:
        return ("Mixto" if paises else "México"), "; ".join(paises)
    if paises:
        return "Extranjero", "; ".join(paises)
    if tld:
        return "Extranjero", f"(medio .{tld.group(1)})"
    if d.endswith(".mx"):
        return "México", ""
    return "Sin identificar", ""


def aplicar_filtro_pais(df, modo):
    """Separa el DataFrame en (conservadas, apartadas) según el modo de filtro."""
    if modo == "ninguno":
        mascara = pd.Series(False, index=df.index)
    elif modo == "estricto":
        mascara = df["ambito"].isin(["Extranjero", "Mixto"])
    else:  # moderado
        mascara = df["ambito"] == "Extranjero"
    return df[~mascara].reset_index(drop=True), df[mascara].reset_index(drop=True)


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
# GOOGLE NEWS RSS 
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
    todo = []
    for n, consulta in enumerate(TEMAS, 1):
        etiqueta = f"tema{n}"
        log(f"[Google News] tema {n}/{len(TEMAS)}")

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
# CONSOLIDACIÓN, ETIQUETAS Y EXPORTACIÓN
# --------------------------------------------------------------------------
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
    df["menciona_reclutamiento"] = texto.map(lambda t: bool(RE_RECLUTA.search(t)))
    df["menciona_redes"] = texto.map(lambda t: bool(RE_REDES.search(t)))
    df["prioridad"] = "baja"
    df.loc[df["menciona_reclutamiento"], "prioridad"] = "media"
    df.loc[df["menciona_reclutamiento"] & df["menciona_redes"], "prioridad"] = "alta"

    zm = texto.map(etiquetar_zm)
    df["zona_metropolitana"] = zm.map(lambda r: r[0])
    df["lugar_zm"] = zm.map(lambda r: r[1])

    ambito = pd.Series([clasificar_ambito(t, d) for t, d in zip(texto, df["dominio"])], index=df.index)
    df["ambito"] = ambito.map(lambda r: r[0])
    df["paises_extranjeros"] = ambito.map(lambda r: r[1])
    df["plataformas_mencionadas"] = texto.map(
        lambda t: "; ".join(k for k, rx in RE_PLATAFORMAS.items() if rx.search(t)))

    df = df.sort_values("fecha", ascending=False, na_position="last").reset_index(drop=True)
    return df[COLUMNAS]


def decodificar_links(df):
    """Reemplaza los enlaces de Google News por la URL real (requiere googlenewsdecoder)."""
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        log("Para --decodificar-links instala: pip install googlenewsdecoder")
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


def exportar(df, base, apartadas=None):
    """
    Guarda `df` en CSV y Excel. Si hay notas `apartadas` por el filtro de país, van a la
    hoja "Otros países" y a un CSV aparte (`<base>_otros_paises.csv`), para poder auditarlas.
    """
    csv_path, xlsx_path = f"{base}.csv", f"{base}.xlsx"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")  # utf-8-sig: Excel abre bien los acentos
    hay_apartadas = apartadas is not None and not apartadas.empty
    if hay_apartadas:
        apartadas.to_csv(f"{base}_otros_paises.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        df[df["prioridad"] == "alta"].to_excel(w, sheet_name="Alta prioridad", index=False)
        df[(df["prioridad"] == "alta") & df["zona_metropolitana"]].to_excel(
            w, sheet_name="Alta prioridad - ZM", index=False)
        df.to_excel(w, sheet_name="Todas", index=False)
        if hay_apartadas:
            apartadas.to_excel(w, sheet_name="Otros países", index=False)
        anchos = (18, 70, 22, 24, 60, 50, 24, 10, 12, 12, 14, 24, 14, 28, 26)
        for hoja in w.book.worksheets:
            hoja.freeze_panes = "A2"
            hoja.auto_filter.ref = hoja.dimensions
            for col, ancho in zip("ABCDEFGHIJKLMNO", anchos):
                hoja.column_dimensions[col].width = ancho
    return csv_path, xlsx_path


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inicio", type=date.fromisoformat, default=INICIO_DEFECTO, help="YYYY-MM-DD (def. 2025-04-01)")
    ap.add_argument("--fin", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD (def. hoy)")
    ap.add_argument("--dias-ventana", type=int, default=7, help="tamaño inicial de ventana para Google News")
    ap.add_argument("--pausa", type=float, default=1.5, help="segundos entre solicitudes a Google News")
    ap.add_argument("--filtro-pais", choices=["ninguno", "moderado", "estricto"], default="moderado",
                    help="qué hacer con notas de otros países: ninguno (solo etiqueta), moderado "
                         "(aparta 'Extranjero'; por defecto) o estricto (aparta 'Extranjero' y 'Mixto')")
    ap.add_argument("--decodificar-links", action="store_true", help="resolver URL real de Google News")
    ap.add_argument("--salida", default="noticias_reclutamiento_mexico_mini", help="prefijo de archivos de salida")
    a = ap.parse_args()

    if a.inicio > a.fin:
        sys.exit("--inicio no puede ser posterior a --fin")
    log(f"Periodo: {a.inicio} -> {a.fin} | fuente: Google News (solamente)")

    registros = []
    try:
        registros = recolectar_gnews(a.inicio, a.fin, a.dias_ventana, a.pausa)
    except KeyboardInterrupt:
        log("\nInterrumpido: guardo lo recolectado hasta ahora...")

    df = consolidar(registros, a.inicio, a.fin)
    total_unicas = len(df)
    if not df.empty:
        log("\nÁmbito de las notas:\n" + df["ambito"].value_counts().to_string())
    df, apartadas = aplicar_filtro_pais(df, a.filtro_pais)
    if a.decodificar_links and not df.empty:
        df = decodificar_links(df)
    csv_path, xlsx_path = exportar(df, a.salida, apartadas)

    log(f"\nListo. {len(registros)} registros brutos -> {total_unicas} notas únicas "
        f"({len(df)} conservadas, {len(apartadas)} apartadas por filtro '{a.filtro_pais}')")
    if not df.empty:
        log(df["prioridad"].value_counts().to_string())
        log(f"En zona metropolitana (CDMX/Edomex): {int(df['zona_metropolitana'].sum())} notas")
    log(f"Archivos: {csv_path} | {xlsx_path}" + (f" | {a.salida}_otros_paises.csv" if len(apartadas) else ""))


if __name__ == "__main__":
    main()
