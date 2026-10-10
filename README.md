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

## Arquitectura del Reemplazo

- **Motor de Integridad**: Implementación exacta de **ISO 7064 MOD 97-10** sobre cadenas alfanuméricas en mayúsculas (`(98 - int(num_str) * 100) % 97`).
- **Ledger Transaccional**: Ledger en memoria thread-safe (`src/state.py`) que gestiona cuentas (`AC-XXXX`), operaciones (`OP-XXXX`), saldos acumulados y reversiones contables bidireccionales en transferencias y depósitos.
- **Precedencia Estricta**: Evaluación determinista de errores que reproduce fielmente el orden heredado: Rutas → Auth → JSON → Formato/Delimitador → Control → Aridad/Comando → Monto inválido (E303) → Origen=Destino (E304) → Existencia de cuenta/operación (E401/E402) → Saldo insuficiente (E507) → Límite excedido (E506).
- **Contrato de Evaluación**: Entrypoints `GET /health`, `POST /__reset`, `POST /msg` y captura estricta 404 E404 para cualquier ruta no mapeada.

## Guía de Ejecución

### 1. Variables de entorno

```bash
cp .env.example .env
# Configura TEAM_TOKEN con el token asignado en /evento
```

### 2. Ejecución local con uv o Python

```bash
# Con uv
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000

# O con python estándar
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 3. Ejecución en contenedor Docker

```bash
docker build -t blackbox .
docker run -p 8000:8000 -e TEAM_TOKEN="tu-token" blackbox
```

### 4. Ejecutar suite de pruebas

```bash
uv run pytest
```
