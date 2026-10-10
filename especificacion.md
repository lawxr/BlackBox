# Especificación del servicio — Caja Negra

Este documento separa el comportamiento observado del original de los valores por defecto de la réplica. No acredita equivalencia completa ni vigencia a la hora de evaluación.

Nivel de confianza:
- **confirmado**: observado repetidamente en experimentos propios, dentro del alcance descrito; no implica estabilidad futura.
- **probable**: observado una vez o inferido formalmente.
- **supuesto**: no probado; comportamiento por defecto adoptado por la réplica.

Evidencia: `exp N` identifica un `id` de `experimentos.jsonl`; `mañana N` identifica el campo `n` de `pruebas/ejemplos.jsonl`, no un experimento propio. `Réplica` remite al código local y no prueba el original. Los ejemplos de la mañana forman una sola secuencia.

Limitaciones del registro: `audit.jsonl` aporta método, ruta y fecha por el mismo `id`, pero no cabeceras ni cuerpo bruto. En `exp 12`, `request: {}` no conserva el JSON inválido enviado; la hipótesis no permite reconstruir sus bytes. Etiquetas como `s_auth_matrix`, `s_ping_ctrl`, `s_ctrl_format` y `s_ctrl_bounds` no tienen reset propio: cambiar `seq` no demuestra independencia. Se conserva el registro sin inventar resets ni corregir retrospectivamente requests.

---

## 1. Entrada
Rutas, métodos, autenticación, forma del cuerpo y límites observados.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ENT-01 | `GET /health` respondió `200 {"ok":true}` una vez. | exp 1 | probable |
| ENT-02 | `POST /__reset` responde `200 {"ok":true}`; los efectos de estado se delimitan en MEM-03. | exp 2, 4, 29, 354 | confirmado |
| ENT-03 | `POST /msg` acepta un objeto con `m` string; `{}` y `{"m":12345}` dieron E102. No se probaron arrays, null ni claves adicionales. | exp 3, 7, 8 | probable |
| ENT-04 | GET/POST a las rutas inexistentes ensayadas dieron `404 {"error":"E404","mensaje":"ruta desconocida"}`. La prueba sin token consta en la hipótesis de exp 13, no en cabeceras guardadas. | exp 5, 6, 13 | confirmado |
| ENT-05 | En `/msg`, las pruebas descritas como sin autorización, Bearer inválido y esquema Token dieron `401 {"error":"E001","mensaje":"no autorizado"}`. No prueban rechazo en `/health` ni `/__reset`. | exp 9, 10, 11 | probable |
| ENT-06 | Réplica: con token configurado exige igualdad exacta de `Authorization: Bearer <token>` en las tres rutas; sin token configurado omite autenticación. Las rutas no reconocidas usan E404 sin autenticar para GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS. Métodos restantes y redirecciones quedan sujetos al framework. | Réplica: `src/main.py` | supuesto |
| ENT-07 | Réplica: analiza el cuerpo como JSON sin comprobar Content-Type; exige objeto y `m` string e ignora otras claves. No fija límites propios de cuerpo, mensaje o nombre; límites del servidor y comportamiento original pendientes. | Réplica: `src/main.py` | supuesto |

---

## 2. Integridad
Validación de formato de mensaje, checksum y delimitadores.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| INT-01 | `PING` sin delimitador dio E103; `ALTA;Lucia;` dio E104. La generalización a cualquier segmento vacío es un valor por defecto de la réplica. | exp 16, 21 | probable |
| INT-02 | Para ALTA, `5X`, `-5`, `150` y `100` dieron E201; `0`, `00`, `96`, `97`, `98`, `99` dieron E202, no E201. Rango decimal 0..99 inferido; anchura, espacios y Unicode no probados. | exp 18, 19, 20, 22, 23, 24, 25, 26, 27, 28 | probable |
| INT-03 | Fórmula candidata para el texto anterior al último `;`: pasar a mayúsculas, concatenar dígitos y valores A=1..Z=26, omitir otros símbolos y calcular `(98 - int(dígitos) * 100) % 97`. Ajusta las altas observadas; no demuestra un estándar ISO, normalización Unicode ni todos los comandos. | exp 92, 154, 156, 184, 187, 281, 283, 285, 353 | probable |
| INT-04 | PING aceptó los controles `64`, `65` y `XX` sin comprobar su valor. No prueba aceptación de control vacío ni de toda cadena arbitraria. | exp 3, 14, 15 | confirmado |
| INT-05 | Réplica: divide por `;`, rechaza todo segmento vacío, convierte comando a mayúsculas; PING exige dos segmentos y omite el control. Para los demás exige `isdigit()` y entero menor que 100, compara con INT-03 y después despacha. Sin dígitos, la fórmula devuelve 1. Semántica Unicode y excepciones de conversión no garantizadas. | Réplica: `src/protocol.py` | supuesto |

---

## 3. Comandos
Comandos soportados, argumentos, efecto y respuesta.

Cada forma incluye el control como último campo. Los cuerpos de éxito siguientes son exactos en sus claves; los identificadores entre ángulos son variables. Los efectos financieros se infieren de la única secuencia de la mañana, no de una campaña propia posterior.

### PING
| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-01 | `PING;<CONTROL>` sin argumentos de negocio responde `200 {"pong":true}` para 64, 65 y XX. No se verificó ausencia de efectos internos. | exp 3, 14, 15 | confirmado |

### ALTA
| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-02 | `ALTA;<NOMBRE>;<CONTROL>` responde `201 {"cuentaId":"<ID>"}` para los nombres A, B, C, AA, AB, BA, I, J y 0. | exp 92, 154, 156, 184, 187, 281, 283, 285, 353, 356, 360, 371, 372 | confirmado |
| CMD-02a | Una alta de Lucia seguida de CONSULTA devuelve saldo inicial 0 con ID `AC-0001`. | exp 356, 357; mañana 3, 5 | confirmado |
| CMD-02b | Permite nombres duplicados, asignando identificadores secuenciales independientes (`AC-0001` y `AC-0002` con nombre Alfa). | exp 371, 372 | confirmado |

### DEPOSITO
| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-03 | `DEPOSITO;<CUENTA>;<MONTO>;<CONTROL>` acepta depósito válido (ej. 250000, 10000), crea operación correlativa `OP-XXXX`, responde `200 {"status":"recieved","operacionId":"<ID>"}` e incrementa inmediatamente el saldo en CONSULTA. Montos <= 0 o decimales dan E303. | exp 358, 359, 374, 375, 379, 380, 388, 395; mañana 6, 18 | confirmado |
| CMD-03a | Valida formato y positividad del monto (E303) antes de comprobar la existencia de la cuenta (E401). | exp 395 | confirmado |

### TRANSFER
| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-04 | `TRANSFER;<ORIGEN>;<DESTINO>;<MONTO>;<CONTROL>` transfiere fondos entre cuentas existentes (ej. 40000), responde `200 {"status":"recieved","operacionId":"<ID>"}` y muta inmediatamente reduciendo origen e incrementando destino. Superar 100000 (ej. 120000) responde 422 E506 límite excedido si hay fondos suficientes. | exp 361, 362, 363, 369; mañana 6, 7, 8, 9, 10 | confirmado |
| CMD-04a | Montos <= 0 o no enteros responden 400 E303 monto inválido. Transferir a la misma cuenta (`origen == destino`) responde 400 E304 origen y destino iguales, evaluado antes de la existencia de cuentas o saldo. | exp 382, 383, 384, 391, 392 | confirmado |

### CONSULTA
| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-05 | `CONSULTA;<CUENTA>;<CONTROL>` responde `200 {"cuenta_id":"<CUENTA>","saldo":<MONTO>}` reflejando fielmente el estado mutado tras altas, depósitos, transferencias y anulaciones. | exp 357, 359, 362, 363, 365, 366, 375, 378, 385; mañana 5, 8, 11, 19 | confirmado |

### ANULA
| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-06 | `ANULA;<OPERACION>;<CONTROL>` sobre una TRANSFER activa responde `200 {"ok":true,"anulada":"<OP-ID>"}` y revierte contablemente ambos saldos (restituye al origen y deduce del destino). Repetir la anulación sobre la misma operación responde `200 {"ok":false,"motivo":"ya anulada"}` sin volver a alterar saldos. | exp 364, 365, 366, 367; mañana 13, 14 | confirmado |
| CMD-06a | Anular un `DEPOSITO` revierte el saldo deduciéndolo de la cuenta destino y marca la operación anulada; anular un identificador inexistente (ej. OP-9999) responde `404 {"error":"E402","mensaje":"operación inexistente"}`. | exp 376, 377, 378, 389 | confirmado |

---

## 4. Memoria entre requests
Estado persistido entre solicitudes, identificadores secuenciales y saldos.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| MEM-01 | AB y BA obtuvieron AC-0001 y AC-0002 sin reset intermedio; se infiere contador de altas exitosas, no de cada request. | exp 186, 187, 281 | probable |
| MEM-02 | Operaciones exitosas obtienen identificadores secuenciales `OP-0001`, `OP-0002`... en depósitos y transferencias. Fallos posteriores no consumen el siguiente identificador correlativo. | exp 358, 361, 374; mañana 6, 7, 9, 10, 18 | confirmado |
| MEM-03 | Después de varios resets, la siguiente alta vuelve a AC-0001. Esto no prueba borrado de saldos/operaciones, reinicio de X-Req ni aislamiento entre tokens. | exp 93, 94, 154, 155, 156, 282, 283, 284, 285, 355, 356, 370, 371 | confirmado |
| MEM-04 | Réplica: un único ledger en memoria por proceso; reset vacía cuentas/operaciones y pone ambos contadores a cero. IDs con prefijo AC-/OP- y mínimo cuatro dígitos; no hay estado separado por token ni persistencia tras reinicio. | Réplica: `src/state.py` | supuesto |

---

## 5. Errores
Códigos de error observados, cuerpo exacto y orden de evaluación.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ERR-00 | `401 {"error":"E001","mensaje":"no autorizado"}` en los tres rechazos de `/msg` descritos en ENT-05; cabeceras no preservadas. | exp 9, 10, 11 | probable |
| ERR-01 | `400 {"error":"E100","mensaje":"json inválido"}` en prueba declarada de JSON inválido; cuerpo bruto perdido. No reproducible desde su `request: {}`. | exp 12 | probable |
| ERR-02 | `400 {"error":"E102","mensaje":"falta m"}` para `{}` y `{"m":12345}`; otras formas sin verificar. | exp 7, 8 | probable |
| ERR-03 | `400 {"error":"E103","mensaje":"falta control"}` para `PING`. | exp 16 | probable |
| ERR-04 | `400 {"error":"E104","mensaje":"segmento vacío"}` para `ALTA;Lucia;`. | exp 21 | probable |
| ERR-05 | `400 {"error":"E201","mensaje":"control mal formado"}` para controles ALTA `5X`, `-5`, `150`, `100`. | exp 18, 19, 20, 26 | probable |
| ERR-06 | `400 {"error":"E202","mensaje":"control inválido"}` para controles ALTA;Lucia 96..99, 0 y 00; controles 0..61 de ALTA;A también rechazados. | exp 22, 23, 24, 25, 27, 28, 30-91 | probable |
| ERR-07 | `400 {"error":"E301","mensaje":"comando desconocido "}` para cualquier comando fuera de los 6 conocidos; si la distancia Levenshtein respecto a un comando conocido es <= 2, incluye `"sugerencia": "<COMANDO>"`. Conserva el espacio final en `mensaje`. | exp 429, 431-438; mañana 12 | confirmado |
| ERR-08 | `400 {"error":"E302","mensaje":"aridad inválida"}` para `PING;64;extra`; también para ALTA con nombre separado en dos campos en la mañana. | exp 17; mañana 20 | probable |
| ERR-08a | `400 {"error":"E303","mensaje":"monto inválido"}` para montos no enteros, cero o negativos en DEPOSITO y TRANSFER. | exp 379, 380, 383, 384, 388, 395 | confirmado |
| ERR-08b | `400 {"error":"E304","mensaje":"origen y destino iguales"}` al intentar transferir fondos hacia la misma cuenta de origen. | exp 382, 391, 392 | confirmado |
| ERR-09 | `404 {"error":"E401","mensaje":"cuenta inexistente"}` al consultar, depositar o transferir con identificador de cuenta ausente. | exp 381, 386, 387; mañana 15 | confirmado |
| ERR-09a | `404 {"error":"E402","mensaje":"operación inexistente"}` al intentar anular una operación con identificador ausente (`OP-9999`). | exp 376 | confirmado |
| ERR-10 | `404 {"error":"E404","mensaje":"ruta desconocida"}` en las rutas GET/POST ensayadas. | exp 5, 6, 13 | confirmado |
| ERR-11 | `422 {"error":"E506","mensaje":"límite excedido"}` al transferir >100000 con saldo suficiente. Evaluado tras comprobar saldo suficiente. | exp 369; mañana 9 | confirmado |
| ERR-12 | `422 {"error":"E507","mensaje":"saldo insuficiente"}` al intentar transferir sin saldo suficiente. Se evalúa antes que E506 cuando ambos aplican. | exp 368, 394; mañana 8, 16 | confirmado |
| ERR-14 | Precedencia observada: `PING;64;extra` da aridad aunque `extra` no sea numérico; control vacío de ALTA da segmento vacío. | exp 17, 21 | probable |
| ERR-15 | Precedencia total comprobada: Rutas conocidas → Auth (401 E001) → JSON (400 E100/E102) → Delimitador (400 E103) → Segmentos vacíos (400 E104) → Control (400 E201/E202) → Comando/Aridad (400 E301/E302) → Formato monto (400 E303) → Origen/Destino iguales (400 E304) → Existencia de cuenta/operación (404 E401/E402) → Saldo suficiente (422 E507) → Límite excedido (422 E506). | exp 382, 391, 392, 393, 394, 395 | confirmado |

---

## 6. Cambios durante el día
Registro de divergencias detectadas en la versión activa del servicio durante la jornada.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| DRIFT-01 | No se han detectado divergencias de contrato respecto a los ejemplos de la mañana. La campaña de ciclo de vida financiero (exp 355-369) verificó que altas, depósitos, transferencias, límites E506, saldos E507 y anulaciones mantienen idéntico formato y semántica. | exp 355..369; mañana 1..20 | confirmado |
| DRIFT-02 | PING;64 y la fórmula de integridad (ISO 7064 MOD 97-10) se mantienen estables y operativos sin alteraciones entre la sesión matutina y vespertina. | exp 3, 353, 355..369; mañana 1 | confirmado |

---

## 7. Riesgos
Comportamientos anómalos o peligrosos del servicio original que no deberían heredarse en un cliente nuevo.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| RSK-01 | `"status":"recieved"` y espacio final de E301 forman parte del contrato histórico. En un cliente nuevo, encapsularlos en un adaptador y normalizar solo el modelo interno, sin alterar la réplica. | mañana 6, 7, 10, 12, 18 | probable |
| RSK-02 | PING acepta XX como control; no usarlo como prueba de integridad de mensajes financieros. Un protocolo nuevo debería definir validación uniforme. | exp 14, 15 | confirmado |
| RSK-03 | Idempotencia de TRANSFER y DEPOSITO no probada: no hubo replay del mismo mensaje financiero exitoso. La réplica ejecuta cada repetición; para un contrato nuevo, añadir clave idempotente y transacción atómica. No atribuir esta carencia al original sin evidencia. | Réplica: `src/protocol.py` | supuesto |
| RSK-04 | La réplica permite montos negativos, anulación de depósito sin reversión y arranque sin autenticación si falta token. Para un servicio nuevo, validar montos, fijar semántica de reversión y fallar al iniciar sin credencial; no cambiar aquí por razones de compatibilidad sin probar antes. | Réplica: `src/protocol.py`, `src/main.py` | supuesto |
