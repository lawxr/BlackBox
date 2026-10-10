# Especificación del servicio — Caja Negra

Este documento describe el comportamiento observable del servicio para permitir su reimplementación sin consultar al original.

Nivel de confianza:
- **confirmado**: probado y reproducible en experimentos propios.
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
| INT-01 | Formato general `COMANDO;ARG1;...;CONTROL` delimitado por punto y coma | TBD | supuesto |
| INT-02 | Algoritmo de checksum / control | TBD | supuesto |

---

## 3. Comandos
Comandos soportados, argumentos, efecto y respuesta.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-01 | `PING;...` responde `{"pong": true}` | 3 | confirmado |
| CMD-02 | `ALTA;<NOMBRE>;<CTRL>` registra una nueva cuenta | TBD | supuesto |
| CMD-03 | `DEPOSITO;<CTA>;<MONTO>;<CTRL>` añade saldo a una cuenta | TBD | supuesto |
| CMD-04 | `TRANSFER;<ORIGEN>;<DESTINO>;<MONTO>;<CTRL>` transfiere saldo | TBD | supuesto |
| CMD-05 | `CONSULTA;<CTA>;<CTRL>` consulta balance y estado | TBD | supuesto |
| CMD-06 | `ANULA;<OP-ID>;<CTRL>` anula una transacción previa | TBD | supuesto |

---

## 4. Memoria entre requests
Estado persistido entre solicitudes, identificadores secuenciales y saldos.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| MEM-01 | Los identificadores de cuenta siguen patrón incremental `AC-XXXX` | TBD | supuesto |
| MEM-02 | Los identificadores de operación siguen patrón incremental `OP-XXXX` | TBD | supuesto |
| MEM-03 | El estado se aísla por token y se restablece tras `POST /__reset` | TBD | supuesto |

---

## 5. Errores
Códigos de error observados, cuerpo exacto y orden de evaluación.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ERR-00 | Error E001: Token ausente, esquema no-Bearer o token inválido devuelve `401 {"error":"E001","mensaje":"no autorizado"}` | 9, 10, 11 | confirmado |
| ERR-01 | Error E100: Cuerpo HTTP no analizable como JSON válido devuelve `400 {"error":"E100","mensaje":"json inválido"}` | 12 | confirmado |
| ERR-02 | Error E102: Cuerpo JSON sin clave `"m"` o con tipo no string devuelve `400 {"error":"E102","mensaje":"falta m"}` | 7, 8 | confirmado |
| ERR-03 | Error E404: Ruta inexistente (GET/POST) devuelve `404 {"error":"E404","mensaje":"ruta desconocida"}` | 5, 6, 13 | confirmado |
| ERR-04 | Error E201: Formato de control inválido | TBD | supuesto |
| ERR-05 | Error E202: Checksum / control no coincide | TBD | supuesto |
| ERR-06 | Error E301 / E302: Formato o aridad de comando incorrecta | TBD | supuesto |
| ERR-07 | Error E401: Cuenta inexistente | TBD | supuesto |
| ERR-08 | Error E506: Límite por transferencia superado | TBD | supuesto |
| ERR-09 | Error E507: Saldo insuficiente | TBD | supuesto |

---

## 6. Cambios durante el día
Registro de divergencias detectadas en la versión activa del servicio durante la jornada.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| DRIFT-01 | Línea base inicial establecida por la mañana | TBD | supuesto |

---

## 7. Riesgos
Comportamientos anómalos o peligrosos del servicio original que no deberían heredarse en un cliente nuevo.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| RSK-01 | Errores ortográficos en contratos (e.g., `"status":"recieved"`) | TBD | supuesto |
| RSK-02 | Falta de idempotencia en mutaciones sin control de replay | TBD | supuesto |
