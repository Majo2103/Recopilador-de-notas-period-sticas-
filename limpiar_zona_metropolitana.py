#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Limpieza de notas que NO son de la zona metropolitana (CDMX / Estado de
México), a partir de un CSV.

Qué hace este script:
  1. Lee csv generado por el recopilador (recopilar_noticias_zm_general.py o
  2. Busca en ese texto: (a) señales de CDMX/Edomex (las mismas alcaldías y
     municipios que usa recopilar_noticias_zm_general.py) y (b) señales de
     OTRO estado de México o de OTRO país.
  3. Clasifica cada nota en una de 4 categorías (ninguna se borra):
       - Limpia: sí menciona CDMX/Edomex y no menciona ningún otro lugar.
       - Descartada: NO menciona CDMX/Edomex pero SÍ menciona otro lugar
         (este es el caso de las notas que se colaron).
       - Revisar (menciona ambos): menciona CDMX/Edomex Y también otro
         lugar (p. ej. notas que comparan varios estados). Necesita ojo
         humano, así que no se descarta sola.
       - Revisar (sin lugar): no hay ninguna señal de lugar en el texto
         disponible. Puede ser una nota de la zona metropolitana cuyo
         título no la nombra, o puede no serlo. También necesita revisión.

Requisitos:
    pip install pandas openpyxl

Uso:
    python limpiar_zona_metropolitana.py noticias_reclutamiento_zm_general.csv
    python limpiar_zona_metropolitana.py mi_archivo.csv --salida resultado_limpio
"""

import argparse
import re
import sys
import unicodedata

import pandas as pd

# --------------------------------------------------------------------------
# LUGARES DE LA ZONA METROPOLITANA (CDMX + Estado de México)
# Mismas listas que recopilar_noticias_zm_general.py, copiadas aquí para que
# este script funcione solo, sin depender de ningún otro archivo.
# --------------------------------------------------------------------------
LUGARES_GENERALES_ZM = [
    "CDMX", "Ciudad de México", "Estado de México", "Edomex", "mexiquense",
    "mexiquenses", "zona metropolitana", "área metropolitana", "Valle de México", "ZMVM",
]

ALCALDIAS_CDMX = [
    "alcaldía Álvaro Obregón", "Azcapotzalco", "alcaldía Benito Juárez", "Coyoacán",
    "Cuajimalpa", "alcaldía Cuauhtémoc", "Gustavo A. Madero", "Iztacalco", "Iztapalapa",
    "Magdalena Contreras", "alcaldía Miguel Hidalgo", "Milpa Alta", "Tláhuac", "Tlalpan",
    "alcaldía Venustiano Carranza", "Xochimilco",
]

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

# --------------------------------------------------------------------------
# OTROS LUGARES (para detectar las notas que se colaron)
# --------------------------------------------------------------------------
# Los otros 30 estados (todo México menos CDMX y Edomex). "Hidalgo" y
# "Guerrero" exigen "en"/"estado de" antes, porque si no chocan con la
# alcaldía Miguel Hidalgo y con nombres de calles/colonias "Guerrero".
_OTROS_ESTADOS_MX = (
    r"aguascalientes|baja california(?: sur)?|campeche|chiapas|chihuahua|coahuila|colima|"
    r"durango|guanajuato|jalisco|michoacan|morelos|nayarit|nuevo leon|oaxaca|puebla|"
    r"queretaro|quintana roo|san luis potosi|sinaloa|sonora|tabasco|tamaulipas|tlaxcala|"
    r"veracruz|yucatan|zacatecas|(?:en|estado de) (?:guerrero|hidalgo)"
)
# Ciudades grandes que casi siempre implican un estado distinto a CDMX/Edomex.
_CIUDADES_OTROS_ESTADOS = (
    r"tijuana|monterrey|guadalajara|culiacan|mexicali|ciudad juarez|acapulco|cancun|"
    r"torreon|reynosa|matamoros|nuevo laredo|morelia|hermosillo|saltillo|mazatlan|zapopan|"
    r"villahermosa|xalapa|cuernavaca|pachuca|tepic"
)

# Países distintos de México (nombre y gentilicio).
#Esta lista fue generada por una IA. No es exhaustiva ni perfecta, 
# pero sirve para detectar la mayoría de los casos.
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


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def normalizar(texto):
    """Minúsculas, sin acentos ni signos raros (para que el texto coincida con los patrones)."""
    texto = unicodedata.normalize("NFKD", str(texto) if texto is not None else "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\.]", " ", texto)).strip()


def _rx(patron):
    return re.compile(r"(?<!\w)(?:" + patron + r")(?!\w)")


# --- Detector de CDMX/Edomex (igual que recopilar_noticias_zm_general.py) --
_ENTIDAD_DE_TERMINO = {}
for _t in LUGARES_GENERALES_ZM:
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


def detectar_zm(texto_norm):
    """Devuelve 'CDMX', 'Estado de México', 'CDMX; Estado de México', 'Sin especificar' o ''."""
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


# --- Detector de OTROS lugares (estados de México, ciudades, países) -------
RE_OTRO_ESTADO = _rx(_OTROS_ESTADOS_MX)
RE_OTRA_CIUDAD = _rx(_CIUDADES_OTROS_ESTADOS)
RE_PAISES = {pais: _rx(p) for pais, p in _PAISES_EXTRANJEROS.items()}


def detectar_otro_lugar(texto_norm):
    """Devuelve una lista de nombres de otros lugares (estados, ciudades, países) encontrados."""
    encontrados = []
    m = RE_OTRO_ESTADO.search(texto_norm)
    if m:
        encontrados.append(m.group(0).strip())
    m = RE_OTRA_CIUDAD.search(texto_norm)
    if m:
        encontrados.append(m.group(0).strip())
    for pais, rx in RE_PAISES.items():
        if rx.search(texto_norm):
            encontrados.append(pais)
    return encontrados


def clasificar(lugar_zm, otro_lugar):
    zm_confirmada = lugar_zm in ("CDMX", "Estado de México", "CDMX; Estado de México", "Sin especificar")
    if zm_confirmada and not otro_lugar:
        return "Limpia (zona metropolitana)"
    if otro_lugar and not zm_confirmada:
        return "Descartada (otro lugar)"
    if zm_confirmada and otro_lugar:
        return "Revisar (menciona zona metropolitana y otro lugar)"
    return "Revisar (sin ninguna señal de lugar)"


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def limpiar(archivo):
    df = pd.read_csv(archivo, encoding="utf-8-sig")
    log(f"Leídas {len(df)} filas de {archivo}")

    columnas_texto = [c for c in ("titulo", "descripcion", "texto_completo") if c in df.columns]
    if not columnas_texto:
        sys.exit("El CSV no tiene ninguna columna 'titulo', 'descripcion' ni 'texto_completo'; no hay texto que analizar.")
    log(f"Analizando el texto de: {', '.join(columnas_texto)}")

    texto = df[columnas_texto[0]].fillna("").astype(str)
    for c in columnas_texto[1:]:
        texto = texto + " " + df[c].fillna("").astype(str)
    texto_norm = texto.map(normalizar)

    # Si el CSV ya trae `lugar_zm` (de recopilar_noticias_zm_general.py o
    # recopilar_noticias_mexico_mini.py), se recalcula de todos modos para
    # que sea consistente con exactamente el mismo texto que se analiza aquí.
    df["lugar_zm_verificado"] = texto_norm.map(detectar_zm)
    otros = texto_norm.map(detectar_otro_lugar)
    df["otro_lugar_detectado"] = otros.map(lambda l: "; ".join(l))
    df["categoria_limpieza"] = [clasificar(z, o) for z, o in zip(df["lugar_zm_verificado"], otros)]

    return df


def exportar(df, base):
    csv_path, xlsx_path = f"{base}.csv", f"{base}.xlsx"
    limpias = df[df["categoria_limpieza"] == "Limpia (zona metropolitana)"]
    limpias.to_csv(csv_path, index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        limpias.to_excel(w, sheet_name="Limpias", index=False)
        df[df["categoria_limpieza"] == "Descartada (otro lugar)"].to_excel(w, sheet_name="Descartadas", index=False)
        df[df["categoria_limpieza"].str.startswith("Revisar")].to_excel(w, sheet_name="Revisar", index=False)
        df.to_excel(w, sheet_name="Todas", index=False)
        for hoja in w.book.worksheets:
            hoja.freeze_panes = "A2"
            hoja.auto_filter.ref = hoja.dimensions
    return csv_path, xlsx_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivo", help="CSV de entrada (el que ya generaste con el recopilador)")
    ap.add_argument("--salida", default=None,
                    help="prefijo de los archivos de salida (por defecto: <archivo>_limpio)")
    a = ap.parse_args()

    base = a.salida or re.sub(r"\.csv$", "", a.archivo, flags=re.I) + "_limpio"

    df = limpiar(a.archivo)
    conteos = df["categoria_limpieza"].value_counts()
    log("\nResultado:\n" + conteos.to_string())

    csv_path, xlsx_path = exportar(df, base)
    log(f"\nArchivos: {csv_path} (solo las limpias) | {xlsx_path} "
        f"(hojas: Limpias, Descartadas, Revisar, Todas)")


if __name__ == "__main__":
    main()
