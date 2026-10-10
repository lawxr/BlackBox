# Debrief de Incidente #FR-0153 (Actualización a Versión 2)

### Qué cambió y desde cuándo
A las 15:30 local, el proveedor de la caja negra desplegó la versión 2 del servicio sin previo aviso, introduciendo tres cambios de comportamiento respecto a la versión 1:
1. El límite máximo de fondos transferibles (`transfer_limit`) se redujo de 100.000 a 50.000 (rechazando montos superiores con HTTP 422 `E506 límite excedido`).
2. El formato del saldo en la respuesta de `CONSULTA` pasó de un entero (`0`) a una cadena decimal con dos decimales (`"0.00"`).
3. La precedencia de validaciones en `TRANSFER` alteró su orden: la comprobación de monto máximo (`max_amount`, E506) ahora se evalúa antes que la comprobación de saldo suficiente (`sufficient_balance`, E507).
Adicionalmente, se caracterizó un límite de tamaño de payload HTTP a 8192 bytes que responde con HTTP 413 `E101 cuerpo demasiado grande`.

### Cómo se detectó
El equipo implementó un pipeline de aprendizaje y exploración 100% autónomo (`lab.learn --autonomous`), eliminando hipótesis manuales o intervención asistida por LLM:
- El motor de búsqueda binaria (`boundaries.search_transfer_limit` y `search_body_size`) acotó exactamente la frontera en $50.000 y 8.192 bytes.
- El motor de precedencia (`precedence.determine_transfer_checks_order`) envió violaciones concurrentes revelando la inversión del orden entre `E506` y `E507`.
- El motor de formas (`shapes.infer_balance_format`) detectó la estructura decimal a partir de las trazas recolectadas.
- Toda la evidencia quedó registrada en `experimentos.jsonl` con procedencia exacta trazada en el manifiesto (`profiles/<timestamp>/manifest.json`).

### Cómo responde la réplica
La réplica desacopló completamente los literales y reglas del código mediante una arquitectura dirigida por perfiles versionados (`src/profile.json` y `profiles/ACTIVE`). El pipeline autónomo sintetizó el perfil candidato con consenso estadístico ($\ge 2$ observaciones sin contradicciones), superó las compuertas automatizadas de pruebas herméticas y oráculo de regresión, y activó la versión v2 de forma atómica. La réplica reproduce fielmente el 100% de los comportamientos de la versión 2 manteniendo compatibilidad hacia atrás en sus suites de prueba.
