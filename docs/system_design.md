# Diseño de sistemas — Réplica compatible de servicio HTTP legado
## Arquitectura, compatibilidad observable y validación experimental

**Estado del diseño:** arquitectura prevista para un desarrollador, ampliable a dos investigadores sin modificar el servicio desplegado. Se distingue entre observaciones históricas, hipótesis y comportamientos verificados.

---

## 1. Problema, objetivo y criterios de aceptación

**Problema.** Un servicio HTTP legacy recibe mensajes codificados en `m` y mantiene estado entre solicitudes. No tenemos su código ni documentación; las 20 observaciones suministradas son una única secuencia tomada por la mañana. El servicio podría cambiar sin aviso. El sustituto debe responder como el original, no como lo haría una implementación “correcta” de negocio.

**Contrato observable a replicar.** Métodos y rutas (incluidas las inexistentes); autenticación `Authorization: Bearer <token>`; JSON de entrada; parser de `m`; control de integridad; errores y su orden; comandos; contadores, saldos, historial y anulación; código HTTP y cuerpo exactos. `GET /health` debe dar HTTP 200 cuando está listo y `POST /__reset` debe restaurar el estado inicial. Los cuerpos no JSON se comparan carácter por carácter. Los headers de respuesta no puntúan en la comparación del set, aunque `X-Req` se captura en el log experimental.

### Contrato del entrypoint: lectura estricta

| Entrada | Requisito del clon | Incertidumbre que se probará |
|---|---|---|
| `GET /health` | `200` cuando está listo | Comportamiento exacto sin token, con token inválido y método distinto. |
| `POST /__reset` | Estado inicial completo, incluyendo IDs de cuentas/operaciones, saldos e historial | Cuerpo/status exactos; precedencia de auth; si un reset repetido es idéntico. |
| `POST /msg` con `{"m":"..."}` | Mismo status, mismo body y mismas transiciones | Tipos JSON, gramática de `m`, control e interacciones entre validaciones. |
| `/*` (incluidas rutas inexistentes) | Misma respuesta que el original | 404 vs 405, barra final, body HTML/JSON, precedencia frente a auth. |
| `Authorization: Bearer <token>` | Token de equipo configurable con **variable de entorno**, nunca hardcodeado | Comparar header ausente, inválido, scheme/casing, espacio adicional. |

**Consideración del contrato:** «Todas las llamadas llevan token» y «`/health` da 200 cuando está listo» no demuestran que `/health` sea público. Replicar lo observado, no imponer reglas convencionales. El servicio seguirá accesible desde las 20:00 hasta el final del demo day y será ejecutado en una sola instancia siempre activa.

**Definición formal de compatibilidad.** Para cada secuencia `q = (q1…qn)` ejecutada desde un reset, exigimos igualdad en todos los pasos entre original y réplica:

`∀i ∈ [1,n]: (status_original(qi), body_original(qi)) = (status_replicado(qi), body_replicado(qi))`

La igualdad de JSON compara objetos sin importar el orden de claves, preservando tipos, números, strings y orden de arrays. Un test de secuencia falla si **un solo paso** no coincide. Cada respuesta debe tardar **menos de 5 s**.

**Alcance deliberadamente excluido.** No recuperar el código fuente, no reparar defectos de negocio, no usar IA generativa para responder cada request, no consultar al original desde la réplica, no replicar headers no evaluados salvo cuando su estudio aporte evidencia, no implementar clustering ni almacenamiento distribuido. Los descartes privilegian exactitud, latencia y facilidad para corregir reglas. Se documentarán los comportamientos peligrosos sin “arreglarlos” en el clon evaluado.

### Restricciones operacionales y supuestos verificables

| Tipo | Restricción / supuesto | Consecuencia del diseño |
|---|---|---|
| Dado | 100 tests: 40 de un request; 45 de 2–5; 15 de 6–12 | Medir **secuencia completa**, no solo exactitud por request. |
| Dado | Cada test comienza con `POST /__reset` | Estado efímero inicializable de manera determinista. |
| Dado | Un proceso recibe el set; cada paso admite 5 s | Una réplica y un worker, estado local protegido de carreras. |
| Dado | 10 req/s y 8.000 req/día **por token** en el original | Exploración con límite de tasa y presupuesto por token, contabilizando también los resets. |
| Dado | Estados del original separados por token | Exploraciones paralelas entre integrantes, secuenciales por token. |
| Dado | La réplica no puede llamar al original ni a otra réplica | Separación física/lógica del laboratorio y del servicio productivo. |
| Dado | La versión de las 20 muestras es de la mañana | Las muestras son corpus inicial, **no especificación definitiva**. |
| Dado | Última versión a las 20:00 es la evaluada | Monitorizar cambios y poder sustituir reglas en un despliegue. |
| Por comprobar | Errores de auth, rutas inválidas, body no JSON y prioridades | Nunca confiar en los errores automáticos del framework. |
| Por comprobar | Atomicidad de fallos, contadores, límites, normalizaciones | Evitar atribuir invariantes “bancarias” al servicio sin evidencia. |

## 2. Conocimiento inicial y casos difíciles

Estos datos provienen del *corpus histórico entregado*, no de nuestros experimentos. Por tanto son **observaciones orientadoras**; únicamente nuestro `experimentos.jsonl` podrá soportar afirmaciones «confirmado» en la especificación final.

| Observación de la mañana | Ejemplos | Qué todavía no demuestra |
|---|---|---|
| `PING;64` responde `200 {"pong":true}` | 1 | Que PING ignore controles inválidos o no modifique estado. |
| `ALTA;Lucia;83` → E202 y `...;82` crea `AC-0001` | 2–3 | Fórmula del control ni precedencia de errores. |
| `ALTA;Mateo;3` crea `AC-0002` | 4 | Manejo de duplicados y fallos que consumen IDs. |
| `DEPOSITO` y `TRANSFER` aceptados devuelven `"status":"recieved"` y OP-ID | 6, 7, 10, 18 | Si el status implica un proceso diferido; no corregir el typo. |
| TRANSFER de 120.000 → E506; 100.000 aceptada | 9–10 | Umbral exacto ni si el límite es acumulado. |
| `CONSULTa` es aceptado; `SALDOS` → E301 con espacio final | 11–12 | Que todo el protocolo sea case-insensitive; que se pueda quitar el espacio. |
| Doble `ANULA` → `ok:true` y después `ok:false` | 13–14 | Todas las condiciones de reversión y errores. |
| `CONSULTA` de cuenta inexistente → E401; TRANSFER sin saldo → E507 | 15–16 | Orden ante errores simultáneos. |
| Control `5X` → E201; `35` válido en cierto depósito; ALTA con campo extra → E302 | 17–18, 20 | Algoritmo de control ni prioridad aridad/control. |

**Inferencia relevante, aún por verificar:** AC-0002 termina en 40.700 después de recibir 40.000, recibir 100.000, anular OP-0003 y recibir 700. Cuadra con reversión contable de la transferencia anulada. No extrapolar sin probar anulación de depósitos, dinero ya gastado o transferencias hacia la misma cuenta.

**Casos límite que más arriesgan un mismatch:** JSON inválido/`m` ausente/`m` con tipo incorrecto; auth ausente o incorrecta en ruta inválida; aridad y control incorrectos simultáneamente; overflow/negativos/decimales; fallos mutadores que consuman IDs; operaciones anuladas dos veces; anulación de fondos gastados; rutas y métodos inexistentes; cambio de reglas durante la jornada; timeout tras posible mutación de estado.

## 3. Arquitectura propuesta

**Separación esencial:** el **reemplazo** es el artefacto productivo evaluado. El **laboratorio** solo alimenta su diseño mediante experimentos; jamás se integra en el camino de atención HTTP.

**Flujo de réplica:** `HTTP → autenticación/rutas → parser JSON+m → pipeline de validación configurable → dispatch → motor EFSM/ledger → serializador exacto → respuesta`.

**Motor EFSM (máquina de estados extendida):** define `transition(estado, request) -> (nuevo_estado, status, body)`. Estado local inicial hipotético: `next_account_id`, `next_operation_id`, `accounts[id]={name,balance}` y `operations[id]={kind,amount,source,target,annulled}`. Esta estructura es un **modelo propuesto**, no una afirmación sobre la implementación interna original.

**Regla de atomicidad a descubrir:** un rechazo puede dejar el estado intacto, o alterar contadores. No imponer semántica de rollback antes de medirla. El executor serializa transiciones bajo un lock para mantener coherencia. El reset reconstruye *todo* el estado lógico, incluyendo IDs y marcas de anulación.

**Perfil de compatibilidad:** encapsula gramática, algoritmo de control, precedencia de errores, límites por comando y formas exactas de respuesta. La versión aplicada se empaqueta con el despliegue; no hay dependencia de la red ni modelos remotos durante una solicitud. Esto permite sustituir una regla que cambie, conservando las restantes.

**Operación del servicio:** un worker ASGI, un único proceso, sin autoscaling, con variable de entorno `TEAM_TOKEN`. `GET /health` debe representar disponibilidad real; errores de auth y rutas pasan por handlers de compatibilidad, no por defaults del framework. La réplica no guarda el token en logs. Actualizar o reiniciar el proceso durante un test haría perder estado: evitar redeploys próximos a validaciones y congelar la versión antes del cierre.

**Laboratorio de ingeniería inversa:** runner que ejecuta experimentos con reset, limita la tasa por token, captura respuestas/status/`X-Req`/latencia y registra hipótesis. Genera diferencias, reduce contraejemplos y acumula evidencia. Canarios temporales repiten **secuencias idénticas desde reset** para distinguir cambios reales de contaminación del estado.

### Decisiones y trade-offs — qué se descarta y por qué

| Decisión adoptada | Alternativa descartada | Razón y coste asumido |
|---|---|---|
| EFSM + ledger de operaciones | Tabla `request → response` | La respuesta depende de saldos, IDs y anulaciones; más código a cambio de generalizar secuencias nuevas. |
| Parser y errores explícitos | Validación HTTP automática de FastAPI | Las respuestas automáticas pueden ser 422 con JSON distinto; asumimos mantenimiento extra para ganar exactitud. |
| Motor determinista sin LLM en runtime | Agente LLM generando respuestas | Reduce variabilidad, latencia y dependencia externa; se pierde adaptación espontánea a comandos imprevistos. |
| Una réplica, un proceso, estado en memoria | Redis/DB y múltiples workers | El evaluador usa un proceso y resetea antes de cada test; más simple y rápido, pero redeploy pierde estado (aceptable entre tests, no durante uno). |
| Versionar reglas de compatibilidad | Codificar reglas por todas partes | Facilita reacción a un cambio; requiere pruebas para evitar introducir regresiones. |
| Exploración dirigida por hipótesis | Fuzzing exhaustivo indiscriminado | Cuota finita de requests; puede perder comportamientos exóticos fuera de hipótesis. |
| Diferencial por secuencias | Comparar requests aislados | Detecta divergencias de estado y precedencia; cada experimento cuesta más requests y resets. |
| Despliegue siempre activo y lock | Serverless suspendido/múltiples réplicas | Evita cold start >5 s y estados incoherentes; coste de hosting mayor. |

## 4. Hipótesis falsables y experimentos discriminantes

*Ninguna hipótesis de esta tabla se declara confirmada por aparecer en el corpus de la mañana.*

| Hipótesis | Experimento que podría refutarla | Qué medir |
|---|---|---|
| H01 — control = checksum `mod 97` | Predecir valores en diferentes comandos/payloads y probar muestras nuevas; una predicción fallida refuta la variante | Tasa de predicción en entradas no usadas para ajustar fórmula. |
| H02 — errores E2xx/E3xx/E4xx/E5xx siguen categorías por etapa | Combinar dos defectos y observar precedencia, además de errores de otras rutas/comandos | Árbol real de prioridad; códigos y bodies exactos. |
| H03 — E506 es tope por transferencia | Desde reset, saldo suficiente, probar 120.000 una vez vs dos transferencias de 60.000 con controles válidos | Status de cada paso y saldos posteriores. |
| H04 — `recieved` significa proceso diferido | Aceptar depósito, consultar inmediatamente, repetir consulta y comparar con secuencia base | Si muta el saldo antes de la siguiente consulta. |
| H05 — PING ignora el control | Comparar PING con control válido, `XX`, vacío y fuera de rango | Status/body; efecto en contadores posteriores. |
| H06 — `X-Req` es contador de requests | Comparar después de reset, en errores, entre tokens y rutas | Serie del header, sin incorporarlo al runtime hasta encontrar necesidad. |
| H07 — un fallo no consume IDs | `reset → fallo mutador → alta/depósito válido` versus `reset → alta/depósito válido` | IDs producidos y estado consultado. |
| H08 — ANULA revierte siempre sin restricciones | Anular depósitos, transferencias ya gastadas, doble anulación y operación inexistente | Status, cuerpos y saldos posteriores. |

## 5. Plan de medición definido antes de construir

### Banco de conformidad local (no presupone conocer el set oculto)

| Suite | Diseño y casos concretos | Oráculo y criterio de éxito |
|---|---|---|
| T1 — Contrato HTTP | Matriz `auth válido/incorrecto/ausente` × `GET/POST` × `/health,/msg,/__reset,/ruta-inexistente`; JSON válido e inválido | Coincidencia 100% de status y cuerpo para todos los casos muestreados. |
| T2 — Gramática e integridad | Aridad `esperada±1`, separadores, `m` no-string, casing, controles alfanuméricos, fuera de rango y calculados | Cada caso reproduce el error exacto, o la respuesta válida exacta. |
| T3 — Comandos | Alta, consulta, depósito, transferencia, anulación; éxito/fallo y montos 0, 1, límite-1, límite, límite+1 | Concordancia status/body + efectos posteriores por consulta. |
| T4 — Orden de errores | Pares de defectos: auth+ruta; aridad+control; control+cuenta inexistente; saldo insuficiente+límite | Error ganador idéntico al original, incluido texto y espacios. |
| T5 — Estado corto | ≥30 secuencias **nuevas**, 2–5 pasos, después de reset; incluir fallos intercalados | 100% pasos exactos para aprobar cada secuencia. |
| T6 — Estado largo | ≥20 secuencias **nuevas**, 6–12 pasos, con mutaciones/anulaciones/resets iniciales | Coincidencia integral, no promedio de pasos. |
| T7 — Históricos y drift | Replay de los 20 ejemplos + canarios rotativos de nuevas secuencias desde reset | Detectar primera divergencia reproducible y etiquetar su subsistema. |
| T8 — Performance/operación | 100–500 requests locales, cold/warm; reinicio y verificación de una sola réplica | `p95 < 1s`, `max < 5s`, 0 dependencias al original. Metas internas, no observaciones actuales. |

### Presupuesto de consultas por token, incluidas las llamadas de reset

| Campaña | Presupuesto máximo |
|---|---:|
| HTTP/auth/rutas | 250 |
| Gramática, control e integridad | 1.800 |
| Comandos y precedencia de errores | 2.100 |
| Estado, ledger y anulaciones | 1.900 |
| Canarios, incidente y contingencia | 1.950 |
| **Total por token** | **8.000** |

## 6. Gestión de cambios del servicio de referencia

1. **Antes:** obtener baseline reproducible por secuencias con reset, cubrir rutas, control, negocio, errores y ledger; archivar hash/versión del perfil y hora.
2. **Detectar:** ejecutar canarios periódicos desde reset usando el mismo token aislado; comparar status/body paso a paso.
3. **Confirmar:** descartar rate-limit, timeout y contaminación; repetir secuencia.
4. **Investigar:** lanzar experimentos discriminantes de la regla afectada, actualizar solo ese perfil si la evidencia lo permite.
5. **Validar y desplegar:** comprobar canarios + suites no afectadas, publicar una versión coherente con el original actual.
6. **Documentar:** registrar hora de detección, antes/después, IDs de evidencia, hipótesis rechazadas y riesgos residuales.

## 7. Riesgos, comportamientos heredados y decisiones pendientes

| Riesgo | Consecuencia | Mitigación / decisión |
|---|---|---|
| Control mal inferido | Rechaza casi todas las operaciones normales | Validar predicciones fuera del conjunto usado para inferir. |
| Errores con precedencia incorrecta | Falla incluso sin cambiar estado | Matrices de doble defecto y cuerpos exactos. |
| `ANULA` mal modelada | Falla casi cualquier secuencia con operaciones | Ledger completo; probar reversión, doble anulación y fondos gastados. |
| Estado perdido en redeploy | Secuencia inconsistente | No desplegar durante una secuencia de evaluación; un proceso siempre activo. |
| Atributos “correctos” no observados | Corrige bugs que el evaluador espera ver | Compatibilidad primero, riesgos del legado documentados por separado. |
