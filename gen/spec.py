"""Spec compartida del laboratorio Meilisearch (clientes 100% ficticios).

Escenario: simulacion fintech de credito al consumo. Ninguna empresa real.

Todo aqui es determinista: semilla fija + tablas fijas. El ground truth se
calcula sobre los arreglos generados (no sobre Meilisearch).
"""
from __future__ import annotations

SEED = 20261013

# Escalas exactas del laboratorio (el usuario pidio 1k, 3k, 10k, 300k, 1M -> se
# agregan 100k y 4M como puntos intermedios y techo del dataset).
SCALES = [1_000, 3_000, 10_000, 100_000, 300_000, 1_000_000, 4_000_000]
TOTAL = SCALES[-1]
SHARD_SIZE = 100_000

# ---------------------------------------------------------------- geografia
# (nombre, peso_poblacional_relativo, codigo_curp, lat, lng, prefijo_cp, municipio)
ESTADOS = [
    ("Estado de Mexico", 134, "MC", 19.2925, -99.6558, 50000, "Toluca"),
    ("Ciudad de Mexico", 69, "DF", 19.4326, -99.1332, 1000, "Coyoacan"),
    ("Jalisco", 66, "JC", 20.6736, -103.3442, 44100, "Guadalajara"),
    ("Veracruz", 64, "VZ", 19.5438, -96.9102, 91000, "Xalapa"),
    ("Puebla", 52, "PL", 19.0414, -98.2063, 72000, "Puebla"),
    ("Guanajuato", 49, "GT", 21.0190, -101.2574, 36000, "Leon"),
    ("Nuevo Leon", 46, "NL", 25.6866, -100.3161, 64000, "Monterrey"),
    ("Chiapas", 45, "CS", 16.7569, -93.1292, 29000, "Tuxtla Gutierrez"),
    ("Michoacan", 38, "MN", 19.7060, -101.1950, 58000, "Morelia"),
    ("Oaxaca", 34, "OC", 17.0732, -96.7266, 68000, "Oaxaca"),
    ("Baja California", 31, "BC", 32.5149, -117.0382, 22000, "Tijuana"),
    ("Chihuahua", 30, "CH", 28.6353, -106.0889, 31000, "Chihuahua"),
    ("Guerrero", 29, "GR", 17.5515, -99.5008, 39000, "Chilpancingo"),
    ("Tamaulipas", 28, "TS", 23.7369, -99.1411, 87000, "Ciudad Victoria"),
    ("Coahuila", 25, "CL", 25.4232, -101.0053, 25000, "Saltillo"),
    ("Hidalgo", 24, "HG", 20.1011, -98.7591, 42000, "Pachuca"),
    ("Sinaloa", 24, "SL", 24.8091, -107.3940, 80000, "Culiacan"),
    ("Sonora", 23, "SR", 29.0729, -110.9559, 83000, "Hermosillo"),
    ("San Luis Potosi", 22, "SP", 22.1565, -100.9855, 78000, "San Luis Potosi"),
    ("Tabasco", 20, "TC", 17.9869, -92.9303, 86000, "Villahermosa"),
    ("Queretaro", 18, "QT", 20.5888, -100.3899, 76000, "Queretaro"),
    ("Yucatan", 18, "YN", 20.9674, -89.5926, 97000, "Merida"),
    ("Quintana Roo", 15, "QR", 21.1619, -86.8515, 77500, "Cancun"),
    ("Morelos", 15, "MS", 18.9242, -99.2216, 62000, "Cuernavaca"),
    ("Durango", 13, "DG", 24.0277, -104.6532, 34000, "Durango"),
    ("Zacatecas", 12, "ZS", 22.7709, -102.5832, 98000, "Zacatecas"),
    ("Aguascalientes", 11, "AS", 21.8853, -102.2916, 20000, "Aguascalientes"),
    ("Tlaxcala", 10, "TL", 19.3182, -98.2375, 90000, "Tlaxcala"),
    ("Nayarit", 9, "NT", 21.5082, -104.8950, 63000, "Tepic"),
    ("Campeche", 7, "CC", 19.8301, -90.5349, 24000, "Campeche"),
    ("Colima", 6, "CM", 19.2452, -103.7241, 28000, "Colima"),
    ("Baja California Sur", 6, "BS", 24.1426, -110.3128, 23000, "La Paz"),
]

NOMBRES = [
    "Maria", "Jose", "Juan", "Luis", "Ana", "Guadalupe", "Carlos", "Miguel",
    "Francisco", "Laura", "Alejandro", "Fernanda", "Jesus", "Daniela",
    "Roberto", "Sofia", "Jorge", "Valeria", "Ricardo", "Andrea", "Antonio",
    "Gabriela", "Pedro", "Patricia", "Manuel", "Monica", "Eduardo", "Claudia",
    "Rafael", "Adriana", "Fernando", "Veronica", "Sergio", "Alejandra",
    "Arturo", "Rosa", "Enrique", "Carmen", "Alberto", "Silvia", "Gerardo",
    "Elizabeth", "Oscar", "Diana", "Raul", "Leticia", "Hector", "Yolanda",
    "Ivan", "Norma", "Salvador", "Alicia", "Armando", "Beatriz", "Julio",
    "Sandra", "Ruben", "Marisol", "Andres", "Lucia", "Emilio", "Rocio",
    "Diego", "Gloria", "Javier", "Irene", "Marco", "Teresa", "Angel",
    "Cristina", "Israel", "Karina", "Gustavo", "Mariana", "Felipe", "Paola",
    "Ramon", "Nayeli", "Alfredo", "Vanessa", "Ignacio", "Brenda", "Guillermo",
    "Araceli", "Ernesto", "Lorena", "Cesar", "Mayra", "Julian", "Cecilia",
    "Adan", "Noemi", "Everardo", "Anahi", "Benjamin", "Perla", "Uriel",
    "Itzel", "Saul", "Ximena", "Ramiro", "Citlali", "Genaro", "Quetzali",
]

APELLIDOS = [
    "Hernandez", "Garcia", "Martinez", "Lopez", "Gonzalez", "Perez",
    "Rodriguez", "Sanchez", "Ramirez", "Cruz", "Flores", "Gomez", "Morales",
    "Vazquez", "Reyes", "Jimenez", "Torres", "Diaz", "Gutierrez", "Ruiz",
    "Mendoza", "Aguilar", "Ortiz", "Moreno", "Castillo", "Romero", "Alvarez",
    "Chavez", "Ramos", "Herrera", "Medina", "Vargas", "Castro", "Guzman",
    "Juarez", "Rojas", "Dominguez", "Salazar", "Contreras", "Luna", "Rios",
    "Estrada", "Nunez", "Bautista", "Cortes", "Valdez", "Delgado", "Rivera",
    "Campos", "Espinoza", "Padilla", "Soto", "Cervantes", "Molina", "Ibarra",
    "Suarez", "Mejia", "Villanueva", "Rosas", "Tapia", "Barrera", "Zamora",
    "Cardenas", "Pena", "Acosta", "Bravo", "Ochoa", "Serrano", "Carrillo",
    "Valencia", "Leon", "Maldonado", "Beltran", "Carrasco", "Escobar",
    "Navarro", "Fuentes", "Vega", "Miranda", "Quintero", "Salinas", "Pacheco",
    "Galvan", "Trejo", "Solano", "Arellano", "Baez", "Cabrera", "Rangel",
    "Olvera", "Aparicio", "Zuniga", "Villegas", "Palacios", "Betancourt",
    "Alvarado", "Renteria", "Figueroa", "Hurtado", "Montiel", "Zepeda",
]

COLONIAS = [
    "Centro", "Las Flores", "Lomas de Chapultepec", "San Jose", "La Esperanza",
    "El Mirador", "Nueva Aurora", "Villas del Sol", "Lazaro Cardenas",
    "Reforma", "Independencia", "Los Pinos", "Benito Juarez", "Emiliano Zapata",
    "Francisco I Madero", "Miguel Hidalgo", "Guadalupe Victoria", "El Paraiso",
    "Santa Maria", "San Antonio", "La Paz", "Ampliacion Norte", "Prados",
    "Bosques", "Jardin", "Bellavista", "Las Palmas", "El Rosario", "Tlalpan",
    "Xochimilco", "Azcapotzalco", "Ninos Heroes", "Plan de Ayala", "Obregon",
    "Zapopan", "Chapalita", "Providencia", "Del Valle", "Narvarte", "Portales",
]

CALLES = [
    "Av. Juarez", "Calle Hidalgo", "Av. Reforma", "Calle Morelos",
    "Av. Insurgentes", "Calle Zaragoza", "Av. Universidad", "Calle Allende",
    "Av. Constituyentes", "Calle Guerrero", "Av. Revolucion",
    "Calle Independencia", "Av. Patriotismo", "Cerrada de los Pinos",
    "Privada Alamos", "Av. Central", "Calle 5 de Mayo", "Av. Las Torres",
]

DOMINIOS = ["fintech-demo.mx", "gmail.com", "hotmail.com", "outlook.com", "yahoo.com"]

# Categorias: (nombre_campo, [valores], [pesos])
CATEGORICAS = [
    ("genero", ["H", "M", "X"], [48, 50, 2]),
    ("producto", ["credito_personal", "credito_nomina", "credito_express",
                  "linea_credito", "seguro"], [30, 22, 28, 12, 8]),
    ("kyc_status", ["verificado", "pendiente", "rechazado", "no_iniciado"],
     [58, 22, 9, 11]),
    ("estatus_cuenta", ["activo", "moroso", "pagado", "cancelado", "bloqueado"],
     [42, 18, 24, 10, 6]),
    ("canal_adquisicion", ["referido", "facebook", "google_ads", "tiktok",
                           "organico", "appstore", "prensa"],
     [21, 24, 17, 15, 11, 7, 5]),
    ("dispositivo", ["android", "ios", "web"], [71, 19, 10]),
    ("banda_riesgo", ["bajo", "medio", "alto", "muy_alto"], [38, 34, 22, 6]),
    ("banda_ingreso", ["A", "B", "C", "D", "E"], [30, 32, 24, 10, 4]),
    ("tipo_vivienda", ["propia", "rentada", "familiar", "hipoteca"],
     [28, 41, 27, 4]),
    ("nivel_educativo", ["basica", "media", "superior", "posgrado"],
     [18, 34, 40, 8]),
    ("tipo_contrato", ["formal", "informal", "independiente", "desempleado"],
     [46, 27, 19, 8]),
    ("segmento_comercial", ["nuevo", "recurrente", "vip", "inactivo"],
     [34, 40, 9, 17]),
]

TAGS = ["promo_2026", "premium", "referido_oro", "reactivacion", "cobranza",
        "prueba_a", "prueba_b", "alto_valor", "bloqueo_manual", "verificado_ine",
        "sin_buro", "app_instalada"]

# Banda de riesgo -> (media_score, sigma) para score_buro
SCORE_POR_RIESGO = {
    "bajo": (718, 58),
    "medio": (622, 55),
    "alto": (521, 50),
    "muy_alto": (432, 45),
}
INGRESO_POR_BANDA = {
    "A": (6_800, 2_100),
    "B": (11_800, 3_100),
    "C": (21_500, 6_200),
    "D": (41_000, 12_000),
    "E": (74_000, 26_000),
}

# --------------------------------------------------------------- consultas
# Cada query tiene: id, tipo, descripcion de negocio y el body listo para
# POST /indexes/<uid>/search (o /facet-search). El ground truth se calcula en
# gen_arrays.py a partir de los mismos arreglos.
MAX_OFFSETS = [0, 1_000, 10_000, 100_000, 500_000, 1_000_000]

QUERIES = [
    # --- filtros de segmentacion (los conteos reales son >1000 en casi todas
    # las escalas, es el punto del laboratorio) ---
    {
        "id": "seg_estado_cdmx",
        "tipo": "filter",
        "desc": "Usuarios en Ciudad de Mexico",
        "body": {"filter": 'estado = "Ciudad de Mexico"'},
    },
    {
        "id": "seg_riesgo_alto_personal",
        "tipo": "filter",
        "desc": "Riesgo alto con credito personal",
        "body": {"filter": 'banda_riesgo = "alto" AND producto = "credito_personal"'},
    },
    {
        "id": "seg_score_bajo",
        "tipo": "filter",
        "desc": "Buro menor a 520 (candidatos a rechazo)",
        "body": {"filter": "score_buro < 520"},
    },
    {
        "id": "seg_morosos_30d",
        "tipo": "filter",
        "desc": "Morosos con mas de 30 dias de atraso",
        "body": {"filter": 'estatus_cuenta = "moroso" AND dias_atraso > 30'},
    },
    {
        "id": "seg_kyc_verif_jovenes",
        "tipo": "filter",
        "desc": "KYC verificado de 25 a 35 anios",
        "body": {"filter": 'kyc_status = "verificado" AND edad >= 25 AND edad <= 35'},
    },
    {
        "id": "seg_jalisco_ingreso_b",
        "tipo": "filter",
        "desc": "Jalisco con ingreso banda B",
        "body": {"filter": 'estado = "Jalisco" AND banda_ingreso = "B"'},
    },
    {
        "id": "seg_tiktok_android_marketing",
        "tipo": "filter",
        "desc": "TikTok + Android + acepta marketing",
        "body": {"filter": 'canal_adquisicion = "tiktok" AND acepta_marketing = true AND dispositivo = "android"'},
    },
    {
        "id": "seg_mujeres_30_45_kyc",
        "tipo": "filter",
        "desc": "Mujeres de 30 a 45 verificadas",
        "body": {"filter": 'genero = "M" AND edad >= 30 AND edad <= 45 AND kyc_status = "verificado"'},
    },
    {
        "id": "seg_riesgo_muy_alto",
        "tipo": "filter",
        "desc": "Banda muy_alto (segmento chico pero >1000 a gran escala)",
        "body": {"filter": 'banda_riesgo = "muy_alto"'},
    },
    {
        "id": "seg_activos_sin_atraso",
        "tipo": "filter",
        "desc": "Activos sin atraso (~1.1M en 4M): segmento masivo",
        "body": {"filter": 'estatus_cuenta = "activo" AND dias_atraso = 0'},
    },
    {
        "id": "seg_tag_promo",
        "tipo": "filter",
        "desc": "Tag promo_2026",
        "body": {"filter": 'tags = "promo_2026"'},
    },
    {
        "id": "seg_nomina_vip_alto_monto",
        "tipo": "filter",
        "desc": "Nomina VIP con monto > 40000",
        "body": {"filter": 'producto = "credito_nomina" AND segmento_comercial = "vip" AND monto_solicitado > 40000'},
    },
    # --- geo ---
    {
        "id": "geo_cdmx_25km",
        "tipo": "geo",
        "desc": "Dentro de 25 km del Zocalo (CDMX)",
        "body": {"filter": "_geoRadius(19.4326, -99.1332, 25000)"},
    },
    {
        "id": "geo_gdl_50km",
        "tipo": "geo",
        "desc": "Dentro de 50 km de Guadalajara",
        "body": {"filter": "_geoRadius(20.6736, -103.3442, 50000)"},
    },
    # --- texto ---
    {
        "id": "txt_apellido_hernandez",
        "tipo": "search",
        "desc": 'q="Hernandez" sin typo tolerance (conteo exacto)',
        "body": {"q": "Hernandez", "matchingStrategy": "all",
                 "attributesToSearchOn": ["apellido_paterno", "apellido_materno"]},
    },
    {
        "id": "txt_nombre_maria",
        "tipo": "search",
        "desc": 'q="Maria" en nombre',
        "body": {"q": "Maria", "matchingStrategy": "all",
                 "attributesToSearchOn": ["nombre"]},
    },
    {
        "id": "txt_nombre_apellido_jalisco",
        "tipo": "search",
        "desc": 'q="Jose Hernandez" + filtro Jalisco (segmento chico, control <1000)',
        "body": {"q": "Jose Hernandez", "filter": 'estado = "Jalisco"',
                 "matchingStrategy": "all",
                 "attributesToSearchOn": ["nombre", "apellido_paterno"]},
    },
    {
        "id": "txt_apellido_hernandez_riesgo_alto",
        "tipo": "search",
        "desc": 'q="Hernandez" + filtro banda_riesgo=alto (>1000 a gran escala)',
        "body": {"q": "Hernandez", "filter": 'banda_riesgo = "alto"',
                 "matchingStrategy": "all",
                 "attributesToSearchOn": ["apellido_paterno", "apellido_materno"]},
    },
    {
        "id": "txt_prefix_apellido",
        "tipo": "search",
        "desc": 'Prefijo "Hern" (prefix search sobre el ultimo token)',
        "body": {"q": "Hern", "attributesToSearchOn": ["apellido_paterno"]},
    },
    {
        "id": "txt_colonia_centro",
        "tipo": "search",
        "desc": 'q="Centro" en colonia',
        "body": {"q": "Centro", "matchingStrategy": "all",
                 "attributesToSearchOn": ["colonia"]},
    },
    {
        "id": "txt_fulltext_default",
        "tipo": "search",
        "desc": 'q="Guadalupe" sobre todos los campos buscables (sonda fulltext)',
        "body": {"q": "Guadalupe"},
    },
    # --- ordenamiento ---
    {
        "id": "mix_sort_score_riesgo_alto",
        "tipo": "sort",
        "desc": "Riesgo alto ordenado por score ascendente",
        "body": {"filter": 'banda_riesgo = "alto"', "sort": ["score_buro:asc"]},
    },
    {
        "id": "mix_sort_ingreso_banda_c",
        "tipo": "sort",
        "desc": "Banda de ingreso C ordenada por ingreso descendente",
        "body": {"filter": 'banda_ingreso = "C"', "sort": ["ingreso_mensual:desc"]},
    },
    # --- facetas / agregacion para segmentacion exacta ---
    {
        "id": "facet_estado_global",
        "tipo": "facet",
        "desc": "Distribucion por estado (32 buckets sobre todo el indice)",
        "body": {"facets": ["estado"], "limit": 0},
    },
    {
        "id": "facet_morosos_producto_riesgo",
        "tipo": "facet",
        "desc": "Morosos: facet por producto y banda de riesgo",
        "body": {"filter": 'estatus_cuenta = "moroso"',
                 "facets": ["producto", "banda_riesgo"], "limit": 0},
    },
    {
        "id": "facet_score_bajo_canal",
        "tipo": "facet",
        "desc": "Score < 520: facet por canal de adquisicion",
        "body": {"filter": "score_buro < 520", "facets": ["canal_adquisicion"], "limit": 0},
    },
    {
        "id": "facet_kyc_pendiente_dispositivo",
        "tipo": "facet",
        "desc": "KYC pendiente: facet por dispositivo y acepta_marketing",
        "body": {"filter": 'kyc_status = "pendiente"',
                 "facets": ["dispositivo", "acepta_marketing"], "limit": 0},
    },
]

# Segmentos masivos usados para el barrido de paginacion profunda.
DEEP_PAGINATION = [
    {"id": "deep_activos_sin_atraso", "body": {"filter": 'estatus_cuenta = "activo" AND dias_atraso = 0'}},
    {"id": "deep_score_bajo", "body": {"filter": "score_buro < 520"}},
    {"id": "deep_sin_filtro", "body": {}},
]

INDEX_UID = "clientes_fintech"
