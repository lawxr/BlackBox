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
│   ├── protocol.py         # Parser de mensajes y despacho de comandos
│   ├── state.py            # Motor EFSM y ledger transaccional en memoria
│   └── errors.py           # Códigos y formatos de error del protocolo
├── lab/                    # Laboratorio de ingeniería inversa (fuera del runtime)
│   ├── client.py           # Cliente HTTP con rate-limiting y generador de JSONL
│   └── runner.py           # Ejecutor de secuencias y pruebas diferenciales
└── tests/                  # Banco de pruebas de regresión y conformidad
    └── test_compat.py      # Verificaciones de sanidad del entrypoint
```

## Guía rápida

### 1. Variables de entorno

```bash
cp .env.example .env
# Configura TEAM_TOKEN con el token asignado en /evento
```

### 2. Ejecutar la réplica localmente

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 3. Ejecutar pruebas unitarias

```bash
uv run pytest
```
