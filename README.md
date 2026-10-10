# BlackBox — Reverse Engineering & Service Replacement

Proyecto para resolver el **Reto 2: La caja negra**. Consiste en entender el comportamiento de un servicio HTTP heredado sin documentación mediante experimentación controlada, y construir una réplica compatible de alta fidelidad.

## Entregables

1. **Reemplazo desplegado**: Servicio ASGI accesible públicamente con contrato de entrypoint (`GET /health`, `POST /__reset`, `POST /msg`, `/*`).
2. **Especificación** (`especificacion.md`): Documento con taxonomía de comportamientos (`confirmado`, `probable`, `supuesto`), tablas estructuradas y citas al log de experimentos.
3. **Log de experimentos** (`experimentos.jsonl`): Registro auditable de cada llamada al servicio original con hipótesis y conclusiones.

## Estructura del repositorio

```text
.
├── Dockerfile              # Empaquetado de producción (un solo worker ASGI)
├── README.md               # Documentación general y guía operativa
├── pyproject.toml          # Metadatos y dependencias
├── requirements.txt        # Dependencias fijadas para despliegue
├── .env.example            # Variables de entorno de referencia
├── .gitignore              # Exclusiones de Git
├── especificacion.md       # Entregable de especificación formal
├── experimentos.jsonl      # Entregable del log de experimentos
├── audit.jsonl             # Registro de auditoría técnica (latencias, timestamps, infra)
├── docs/
│   └── system_design.md    # Documento de diseño de sistemas
├── pruebas/
│   └── ejemplos.jsonl      # Secuencia histórica inicial (20 ejemplos)
├── src/                    # Código del reemplazo evaluado
│   ├── main.py             # Entrypoint ASGI y enrutador
│   ├── config.py           # Configuración y variables de entorno
│   ├── protocol.py         # Parser de mensajes, checksum ISO 7064 y despacho de comandos
│   ├── state.py            # Motor EFSM y ledger transaccional en memoria
│   └── errors.py           # Definición de errores del protocolo
├── lab/                    # Laboratorio de ingeniería inversa (fuera del runtime)
│   ├── client.py           # Cliente HTTP con rate-limiting y generador de JSONL
│   ├── runner.py           # Ejecutor de secuencias y pruebas diferenciales
│   └── probe_edge_cases.py # Pruebas focalizadas de casos borde
└── tests/                  # Banco de pruebas automatizadas
    ├── test_compat.py      # Pruebas de contrato, auth, replay y casos borde
    ├── test_lab_client.py  # Pruebas herméticas del cliente del laboratorio
    └── test_lab_runner.py  # Pruebas del ejecutor de secuencias y paradas tempranas
```

## Arquitectura del Reemplazo (Diseño Universal sin Hardcodeo)

Este reemplazo **no utiliza tablas estáticas, mocks ni respuestas pregrabadas**. Es un motor formal de protocolo bancario ASGI que computa matemáticamente la integridad de los mensajes, despacha comandos y muta el estado contable en memoria de forma determinista ante cualquier entrada arbitraria:

1. **Motor de Integridad (ISO 7064 MOD 97-10)**:
   - Implementado en `src/protocol.py` (`compute_control`).
   - Normaliza cadenas alfanuméricas a mayúsculas, mapea `0..9` directos y `A..Z` a ordinales 1..26.
   - Computa el resto $R = (N \times 100) \pmod{97}$ y el control $C = 98 - R$ (normalizado a $1$ si $C=98$).
   - Rango válido estricto: **$1 \dots 97$** (el valor 0 nunca es válido; cuando $R=1$, el control es $97$).
   - Validación estricta de formato: exige 1 o 2 dígitos decimales sin ceros a la izquierda (`len in (1, 2)` y `str(expected) == ctrl_str`). Controles como `03` se rechazan con `E202 control inválido` y `003` con `E201 control mal formado`.

2. **Ledger Transaccional en Memoria (`src/state.py`)**:
   - Máquina de estados extendida (EFSM) protegida contra condiciones de carrera mediante `threading.Lock`.
   - Generación correlativa dinámica de cuentas (`AC-0001`, `AC-0002`...) y operaciones (`OP-0001`, `OP-0002`...).
   - Gestión estricta de saldos acumulados: sumas en depósitos, deducciones en transferencias y **reversiones contables completas** al anular operaciones (restituye fondos al origen y deduce del destino en transferencias; descuenta el saldo en depósitos).
   - Reset determinista (`POST /__reset`): reinicia contadores a cero y vacía todas las estructuras de memoria.

3. **Corrector Tipográfico Métrico (`compute_levenshtein`)**:
   - En caso de comandos desconocidos fuera del conjunto base (`{PING, ALTA, CONSULTA, DEPOSITO, TRANSFER, ANULA}`), calcula la distancia de edición Levenshtein.
   - Si la distancia mínima es $\le 2$, devuelve `400 {"error": "E301", "mensaje": "comando desconocido ", "sugerencia": "<COMANDO>"}`.
   - Si la distancia es $> 2$, devuelve `400 {"error": "E301", "mensaje": "comando desconocido "}` sin el campo de sugerencia.

4. **Precedencia Determinista de Errores**:
   - Rutas conocidas $\rightarrow$ Auth (`401 E001`) $\rightarrow$ JSON (`400 E100/E102`) $\rightarrow$ Delimitadores (`400 E103/E104`) $\rightarrow$ Control (`400 E201/E202`) $\rightarrow$ Comando/Aridad (`400 E301/E302`) $\rightarrow$ Monto inválido (`400 E303`) $\rightarrow$ Origen=Destino (`400 E304`) $\rightarrow$ Cuentas/Operaciones inexistentes (`404 E401/E402`) $\rightarrow$ Saldo insuficiente (`422 E507`) $\rightarrow$ Límite excedido (`422 E506`).

---

## Guía de Ejecución y Reproducibilidad

Cualquier persona puede clonar este repositorio y reproducir la totalidad de la réplica y las pruebas con comandos estándar:

### 1. Variables de entorno

```bash
cp .env.example .env
# Configura TEAM_TOKEN con el token asignado en /evento
```

### 2. Ejecución local de la réplica

```bash
# Con uv (recomendado)
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000

# O con python estándar
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 3. Ejecución en contenedor Docker

```bash
docker build -t blackbox .
docker run -p 8000:8000 -e TEAM_TOKEN="tu-token" blackbox
```

### 4. Batería de pruebas automatizadas (113 tests herméticos en <2s)

Ejecuta todas las pruebas unitarias, de contrato, precedencia, motores de exploración y oráculo de regresión sin necesidad de red:

```bash
uv run pytest
```

### 5. Pipeline de Aprendizaje 100% Autónomo (`lab.learn`)

Aprende el contrato de la caja negra directamente por exploración genérica (búsqueda binaria de límites numéricos, inferencia de precedencia de validaciones, mutación de gramática HTTP/mensajes, secuencias de estado largas y deducción de formatos de respuesta), sintetiza el perfil con consenso estadístico y lo promueve a través de compuertas automáticas:

```bash
# Modo autónomo en vivo (explora, sintetiza y promueve el perfil activo)
uv run python -m lab.learn --autonomous --live --budget 600 --profiles-dir profiles

# Verificación de paridad y detección de drift canario (sin mutar estado)
uv run python -m lab.learn --check
```

### 6. Arquitectura de Perfiles Versionados (`profiles/`)

El comportamiento del servicio está 100% desacoplado del código fuente y gobernado por perfiles declarativos:
- `profiles/ACTIVE`: Puntero atómico a la versión en producción (ej. `20261010T220931Z`).
- `profiles/<timestamp>/`: Carpeta inmutable que contiene `profile.json`, `manifest.json` (con procedencia de experimentos por campo) y `diff.md`.
- `BLACKBOX_PROFILE`: Variable de entorno para sobreescribir el perfil en entornos aislados o pruebas de regresión.
