# Especificación del servicio — Caja Negra

Este documento describe el comportamiento observable del servicio para permitir su reimplementación sin consultar al original.

Nivel de confianza:
- **confirmado**: probado y reproducible en experimentos propios con cita en `experimentos.jsonl`.
- **probable**: observado una vez o inferido formalmente.
- **supuesto**: no probado; comportamiento por defecto adoptado por la réplica.

---

## 1. Entrada
Rutas, métodos, autenticación, forma del cuerpo y límites observados.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ENT-01 | `GET /health` responde `200` y cuerpo `{"ok": true}` | 1 | confirmado |
| ENT-02 | `POST /__reset` reinicia el estado lógico completo y responde `200 {"ok": true}` | 2 | confirmado |
| ENT-03 | `POST /msg` recibe `{"m": "..."}` | 3 | confirmado |
| ENT-04 | Rutas inexistentes responden `404 {"error": "E404", "mensaje": "ruta desconocida"}` (el router evalúa antes que la autenticación) | 5, 6, 13 | confirmado |
| ENT-05 | Validación de cabecera `Authorization: Bearer <token>` obligatoria en `/health`, `/__reset` y `/msg`; rechazo responde `401 {"error": "E001", "mensaje": "no autorizado"}` | 9, 10, 11 | confirmado |

---

## 2. Integridad
Validación de formato de mensaje, checksum y delimitadores.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| INT-01 | Formato general `COMANDO;ARG1;...;CONTROL` delimitado por punto y coma. Sin delimitador responde `E103` y con segmento vacío responde `E104`. | 16, 21 | confirmado |
| INT-02 | Control numérico en rango `0..99`. Valores negativos, no numéricos o `>= 100` responden `400 E201`. | 18, 19, 20, 26 | confirmado |
| INT-03 | Algoritmo de control: ISO 7064 MOD 97-10. Normaliza a mayúsculas, concatena dígitos directos (`0..9` como `'0'..'9'`) y letras según orden alfabético 1-indexed (`A=1..Z=26`), omitiendo símbolos no alfanuméricos como `;` y `-`. Calcula `ctrl = (98 - (int(num_str) * 100)) % 97`. | 92, 154, 156, 184, 187, 281, 283, 285, 353 | confirmado |
| INT-04 | El comando `PING` tiene excepción de integridad: ignora el valor y formato del control siempre que tenga exactamente dos partes separadas por `;`. | 14, 15 | confirmado |

---

## 3. Comandos
Comandos soportados, argumentos, efecto y respuesta.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-01 | `PING;...` responde `200 {"pong": true}` | 3, 14, 15 | confirmado |
| CMD-02 | `ALTA;<NOMBRE>;<CTRL>` registra una nueva cuenta y responde `201 {"cuentaId": "AC-XXXX"}` | 92, 154, 156 | confirmado |
| CMD-03 | `DEPOSITO;<CTA>;<MONTO>;<CTRL>` añade saldo a una cuenta y responde `200 {"status": "recieved", "operacionId": "OP-XXXX"}` | pruebas/ejemplos.jsonl (6, 18) | probable |
| CMD-04 | `TRANSFER;<ORIGEN>;<DESTINO>;<MONTO>;<CTRL>` transfiere saldo entre cuentas y responde `200 {"status": "recieved", "operacionId": "OP-XXXX"}` | pruebas/ejemplos.jsonl (7, 10) | probable |
| CMD-05 | `CONSULTA;<CTA>;<CTRL>` consulta balance y estado y responde `200 {"cuenta_id": "<CTA>", "saldo": <MONTO>}` | pruebas/ejemplos.jsonl (5, 8, 11) | probable |
| CMD-06 | `ANULA;<OP-ID>;<CTRL>` anula una transacción previa y responde `200 {"ok": true, "anulada": "<OP-ID>"}` o `200 {"ok": false, "motivo": "ya anulada"}` | pruebas/ejemplos.jsonl (13, 14) | probable |

---

## 4. Memoria entre requests
Estado persistido entre solicitudes, identificadores secuenciales y saldos.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| MEM-01 | Los identificadores de cuenta siguen patrón incremental `AC-0001`, `AC-0002`... | 92, 281 | confirmado |
| MEM-02 | Los identificadores de operación siguen patrón incremental `OP-0001`, `OP-0002`... | pruebas/ejemplos.jsonl (6, 7, 10, 18) | probable |
| MEM-03 | El estado se aísla por token y se restablece a cero tras `POST /__reset` | 2, 4, 354 | confirmado |

---

## 5. Errores
Códigos de error observados, cuerpo exacto y orden de evaluación.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ERR-00 | Error E001: Token ausente, esquema no-Bearer o token inválido devuelve `401 {"error":"E001","mensaje":"no autorizado"}` | 9, 10, 11 | confirmado |
| ERR-01 | Error E100: Cuerpo HTTP no analizable como JSON válido devuelve `400 {"error":"E100","mensaje":"json inválido"}` | 12 | confirmado |
| ERR-02 | Error E102: Cuerpo JSON sin clave `"m"` o con tipo no string devuelve `400 {"error":"E102","mensaje":"falta m"}` | 7, 8 | confirmado |
| ERR-03 | Error E103: Mensaje sin punto y coma delimitador devuelve `400 {"error":"E103","mensaje":"falta control"}` | 16 | confirmado |
| ERR-04 | Error E104: Mensaje con segmentos vacíos (ej. `;;` o terminando en `;`) devuelve `400 {"error":"E104","mensaje":"segmento vacío"}` | 21 | confirmado |
| ERR-05 | Error E201: Formato de control no numérico, negativo o `>= 100` devuelve `400 {"error":"E201","mensaje":"control mal formado"}` | 18, 19, 20, 26 | confirmado |
| ERR-06 | Error E202: Checksum en rango 0..99 pero discrepante con fórmula devuelve `400 {"error":"E202","mensaje":"control inválido"}` | 22, 23, 24, 25 | confirmado |
| ERR-07 | Error E301: Comando desconocido devuelve `400 {"error":"E301","mensaje":"comando desconocido "}` | pruebas/ejemplos.jsonl (12) | probable |
| ERR-08 | Error E302: Aridad de comando incorrecta devuelve `400 {"error":"E302","mensaje":"aridad inválida"}` | 17 | confirmado |
| ERR-09 | Error E401: Cuenta inexistente devuelve `404 {"error":"E401","mensaje":"cuenta inexistente"}` | pruebas/ejemplos.jsonl (15) | probable |
| ERR-10 | Error E404: Ruta inexistente (GET/POST) devuelve `404 {"error":"E404","mensaje":"ruta desconocida"}` | 5, 6, 13 | confirmado |
| ERR-11 | Error E506: Límite por transferencia individual superado (>100.000) devuelve `422 {"error":"E506","mensaje":"límite excedido"}` | pruebas/ejemplos.jsonl (9) | probable |
| ERR-12 | Error E507: Saldo insuficiente devuelve `422 {"error":"E507","mensaje":"saldo insuficiente"}` | pruebas/ejemplos.jsonl (16) | probable |

---

## 6. Cambios durante el día
Registro de divergencias detectadas en la versión activa del servicio durante la jornada.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| DRIFT-01 | Línea base inicial establecida por la mañana; coincidencia confirmada al 100% | 1-354 | confirmado |

---

## 7. Riesgos
Comportamientos anómalos o peligrosos del servicio original que no deberían heredarse en un cliente nuevo.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| RSK-01 | Errores ortográficos en contratos legacy (`"status":"recieved"` con typo en lugar de `"received"`) | pruebas/ejemplos.jsonl (6, 7, 10, 18) | probable |
| RSK-02 | Espacio final anómalo en mensaje de error E301 (`"mensaje":"comando desconocido "`) | pruebas/ejemplos.jsonl (12) | probable |
| RSK-03 | PING ignora completamente la validación del campo de control | 14, 15 | confirmado |
| RSK-04 | Falta de control de replay o idempotencia en transferencias | pruebas/ejemplos.jsonl | probable |
