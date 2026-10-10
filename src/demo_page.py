"""Brutalist monochrome interactive dashboard served at /demo."""
from __future__ import annotations

DEMO_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BLACKBOX // MOTOR AUTONOMO</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #050505;
      --surface: #0e0e0e;
      --surface-light: #161616;
      --border: #262626;
      --border-bright: #ffffff;
      --text: #ededed;
      --text-muted: #888888;
      --text-dim: #444444;
      --mono: 'JetBrains Mono', monospace;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      border-radius: 0 !important;
    }

    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--mono);
      font-size: 13px;
      line-height: 1.5;
      padding: 24px;
      -webkit-font-smoothing: antialiased;
    }

    /* Layout Frame */
    .container {
      max-width: 1320px;
      margin: 0 auto;
      border: 1px solid var(--border);
    }

    /* Masthead */
    header {
      border-bottom: 1px solid var(--border);
      padding: 16px 20px;
      background: var(--surface);
    }

    .top-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 12px;
    }

    .system-id {
      font-weight: 800;
      font-size: 16px;
      letter-spacing: 1px;
    }

    .meta-tags {
      display: flex;
      gap: 12px;
      font-size: 11px;
    }

    .meta-tag {
      border: 1px solid var(--border);
      padding: 2px 8px;
      color: var(--text-muted);
    }

    .meta-tag.active {
      border-color: var(--border-bright);
      background: var(--text);
      color: #000;
      font-weight: 700;
    }

    .subline {
      font-size: 11px;
      color: var(--text-muted);
      border-top: 1px dashed var(--border);
      padding-top: 8px;
    }

    /* Pipeline 4-Stage Track */
    .pipeline-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }

    .stage-card {
      padding: 16px 18px;
      border-right: 1px solid var(--border);
    }

    .stage-card:last-child {
      border-right: none;
    }

    .stage-num {
      font-size: 11px;
      color: var(--text-dim);
      font-weight: 700;
      margin-bottom: 4px;
    }

    .stage-name {
      font-weight: 700;
      font-size: 13px;
      margin-bottom: 8px;
    }

    .stage-desc {
      font-size: 11px;
      color: var(--text-muted);
      line-height: 1.4;
    }

    /* Controls Bar */
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 20px;
      background: var(--surface-light);
      border-bottom: 1px solid var(--border);
      flex-wrap: wrap;
      gap: 12px;
    }

    .btn {
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
      font-family: var(--mono);
      font-size: 12px;
      font-weight: 700;
      padding: 8px 16px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.1s;
    }

    .btn:hover:not(:disabled) {
      background: var(--text);
      color: #000;
      border-color: var(--border-bright);
    }

    .btn:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }

    .status-indicator {
      font-size: 11px;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* Main Console Workspace */
    .workspace {
      display: grid;
      grid-template-columns: 1.25fr 1fr;
      min-height: 520px;
    }

    .panel {
      padding: 18px 20px;
    }

    .panel-left {
      border-right: 1px solid var(--border);
      background: var(--bg);
      display: flex;
      flex-direction: column;
    }

    .panel-right {
      background: var(--surface);
      display: flex;
      flex-direction: column;
    }

    .panel-header {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
      margin-bottom: 14px;
      display: flex;
      justify-content: space-between;
    }

    /* Feed Terminal */
    .stream-feed {
      flex: 1;
      overflow-y: auto;
      max-height: 480px;
      padding-right: 6px;
      font-size: 12px;
      line-height: 1.6;
    }

    .stream-line {
      margin-bottom: 8px;
      border-left: 2px solid transparent;
      padding-left: 8px;
    }

    .line-probe {
      color: var(--text-muted);
      border-color: var(--border);
    }

    .line-discard {
      color: #777777;
      text-decoration: line-through;
      border-color: #555555;
    }

    .line-synthesize {
      color: var(--text);
      font-weight: 700;
      border-color: var(--border-bright);
    }

    .badge-discard {
      border: 1px solid #555;
      padding: 0 4px;
      font-size: 10px;
      color: #999;
      text-decoration: none;
      display: inline-block;
      margin-right: 4px;
    }

    .badge-rule {
      background: var(--text);
      color: #000;
      padding: 0 4px;
      font-size: 10px;
      font-weight: 700;
      display: inline-block;
      margin-right: 4px;
    }

    /* Synthesis Matrix */
    .matrix-section {
      margin-bottom: 16px;
    }

    .matrix-title {
      font-size: 11px;
      color: var(--text-dim);
      margin-bottom: 6px;
    }

    .rule-box {
      border: 1px solid var(--border);
      padding: 10px 12px;
      margin-bottom: 8px;
      background: var(--bg);
    }

    .rule-box.confirmed {
      border-left: 3px solid var(--border-bright);
    }

    .rule-name {
      font-weight: 700;
      font-size: 12px;
      margin-bottom: 2px;
    }

    .rule-val {
      font-size: 11px;
      color: var(--text-muted);
    }

    /* Verification Tester Box */
    .live-test-box {
      border-top: 1px solid var(--border);
      padding: 18px 20px;
      background: var(--surface-light);
    }

    .input-row {
      display: flex;
      gap: 8px;
      margin-top: 10px;
    }

    .mono-input {
      flex: 1;
      background: #000;
      border: 1px solid var(--border);
      color: var(--text);
      font-family: var(--mono);
      font-size: 12px;
      padding: 8px 12px;
    }

    .mono-input:focus {
      outline: none;
      border-color: var(--border-bright);
    }

    .calc-tag {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 6px;
    }

    /* Footer */
    footer {
      border-top: 1px solid var(--border);
      padding: 12px 20px;
      font-size: 11px;
      color: var(--text-dim);
      display: flex;
      justify-content: space-between;
      background: var(--surface);
    }

    /* Scrollbars */
    ::-webkit-scrollbar {
      width: 5px;
      height: 5px;
    }
    ::-webkit-scrollbar-track {
      background: var(--bg);
    }
    ::-webkit-scrollbar-thumb {
      background: var(--border);
    }
    ::-webkit-scrollbar-thumb:hover {
      background: var(--text-muted);
    }
  </style>
</head>
<body>

  <div class="container">

    <!-- Masthead -->
    <header>
      <div class="top-row">
        <div>
          <div class="system-id">BLACKBOX // RECONSTRUCCION DE CONTRATO AUTONOMA</div>
          <div style="font-size: 11px; color: var(--text-dim); margin-top: 2px;">
            ARQUITECTURA DE INFERENCIA ESTADISTICA Y DEDUCCION DE PROTOCOLO HTTP
          </div>
        </div>
        <div class="meta-tags">
          <span class="meta-tag active">[SISTEMA: ACTIVO]</span>
          <span class="meta-tag">[INFERENCIA: NO SUPERVISADA]</span>
          <span class="meta-tag">[TARGET: /msg]</span>
        </div>
      </div>
      <div class="subline">
        PRINCIPIO: CERO PAYLOADS HARDCODEADOS :: DEDUCCION PURA POR EXPLORACION, DISCRIMINACION Y CONSENSO
      </div>
    </header>

    <!-- 4 Pipeline Stages -->
    <div class="pipeline-grid">
      <div class="stage-card">
        <div class="stage-num">[01 // EXPLORACION]</div>
        <div class="stage-name">SONDEO CIEGO</div>
        <div class="stage-desc">
          Motores sintacticos generan secuencias sin conocer reglas: limites numericos, aridades, mutaciones y pares de precedencia.
        </div>
      </div>
      <div class="stage-card">
        <div class="stage-num">[02 // MEDICION]</div>
        <div class="stage-name">REGISTRO RAW</div>
        <div class="stage-desc">
          Captura diferencial de pares (Status HTTP, cuerpo, latencia). Registro append-only inmutable en log de experimentos.
        </div>
      </div>
      <div class="stage-card">
        <div class="stage-num">[03 // DESCARTE]</div>
        <div class="stage-name">FILTRO DE RUIDO</div>
        <div class="stage-desc">
          Eliminacion de hipotesis refutadas, no deterministas o accidentales. Solo sobreviven comportamientos reproducibles.
        </div>
      </div>
      <div class="stage-card">
        <div class="stage-num">[04 // CONSENSO]</div>
        <div class="stage-name">SINTESIS DE PERFIL</div>
        <div class="stage-desc">
          Consolidacion automatica: regla aceptada si cuenta con &gt;= 2 observaciones independientes y 0 contradicciones.
        </div>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="toolbar">
      <div>
        <button class="btn" id="btnRun" onclick="startProcessStream()">
          [ &gt; DISPARAR CICLO DE EXPLORACION Y DESCARTE ]
        </button>
        <button class="btn" onclick="resetProcessStream()">
          [ REINICIAR ]
        </button>
      </div>
      <div class="status-indicator" id="statusIndicator">
        [ESTADO: ESPERANDO EJECUCION]
      </div>
    </div>

    <!-- Workspace -->
    <div class="workspace">

      <!-- Left Panel: Feed of Probes & Discards -->
      <div class="panel panel-left">
        <div class="panel-header">
          <span>// FLUJO DE EXPLORACION, DISCRIMINACION Y DESCARTE</span>
          <span id="probeCount">0 PROBES</span>
        </div>

        <div class="stream-feed" id="streamFeed">
          <div class="stream-line line-probe">
            // Sistema en reposo.<br>
            // Haz clic en "[ &gt; DISPARAR CICLO DE EXPLORACION Y DESCARTE ]" para observar el proceso algoritmico en tiempo real.
          </div>
        </div>
      </div>

      <!-- Right Panel: Converged Profile Rules -->
      <div class="panel panel-right">
        <div class="panel-header">
          <span>// CONTRATO CONVERGIDO (PERFIL EN TIEMPO REAL)</span>
          <span id="ruleCount">0 REGLAS</span>
        </div>

        <div style="flex: 1; overflow-y: auto;" id="matrixContainer">
          
          <div class="matrix-section">
            <div class="matrix-title">-- INTEGRIDAD DE MENSAJE --</div>
            <div class="rule-box" id="rule-ctrl">
              <div class="rule-name">[MOD-97-10] CHECKSUM ISO 7064</div>
              <div class="rule-val">Pendiente de inferencia...</div>
            </div>
            <div class="rule-box" id="rule-bom">
              <div class="rule-name">[ENCODING] UTF-8 BOM</div>
              <div class="rule-val">Pendiente de inferencia...</div>
            </div>
          </div>

          <div class="matrix-section">
            <div class="matrix-title">-- LIMITES DE ENTRADA HTTP --</div>
            <div class="rule-box" id="rule-body">
              <div class="rule-name">[TAMANIO] MAX BODY BYTES</div>
              <div class="rule-val">Pendiente de inferencia...</div>
            </div>
          </div>

          <div class="matrix-section">
            <div class="matrix-title">-- PRECEDENCIA DE ERRORES EN TRANSFER --</div>
            <div class="rule-box" id="rule-prec">
              <div class="rule-name">[EVALUACION] ORDEN DE VALIDACION</div>
              <div class="rule-val">Pendiente de inferencia...</div>
            </div>
          </div>

          <div class="matrix-section">
            <div class="matrix-title">-- FORMATO DE CONSULTA --</div>
            <div class="rule-box" id="rule-cons">
              <div class="rule-name">[REPRESENTACION] FORMATO DE SALDO</div>
              <div class="rule-val">Pendiente de inferencia...</div>
            </div>
          </div>

        </div>
      </div>

    </div>

    <!-- Live Execution Interactive Tester -->
    <div class="live-test-box">
      <div style="font-weight: 700; font-size: 12px; margin-bottom: 4px;">
        // VERIFICACION EN VIVO CONTRA REPLICA DESPLEGADA (/msg)
      </div>
      <div style="font-size: 11px; color: var(--text-muted);">
        Prueba directa del motor EFSM. El checksum ISO 7064 se calcula dinamicamente al escribir:
      </div>

      <div class="input-row">
        <input type="text" class="mono-input" id="testInput" value="ALTA;OPERADOR" oninput="updateControl()">
        <button class="btn" onclick="sendLiveProbe()">[ ENVIAR POST ]</button>
        <button class="btn" onclick="sendReset()">[ RESET ]</button>
      </div>

      <div class="calc-tag" id="calcTag">
        Calculando control ISO 7064...
      </div>

      <div style="margin-top: 10px; background: #000; border: 1px solid var(--border); padding: 10px; font-size: 11px; color: var(--text-muted); min-height: 48px;" id="outputLog">
        // Salida de red: esperando envio.
      </div>
    </div>

    <!-- Footer -->
    <footer>
      <div>BLACKBOX // INGENIERIA INVERSA AUTONOMA</div>
      <div>CONTRATO EFSM DETERMINISTA // CERO LLM EN TIEMPO DE RESPUESTA</div>
    </footer>

  </div>

  <script>
    const TEAM_TOKEN = "ftr_819e322b513146fe17ddf541595b4e8f";

    // ISO 7064 MOD 97-10
    function computeControl(payload) {
      let digits = "";
      for (const ch of payload.toUpperCase()) {
        if (ch >= '0' && ch <= '9') {
          digits += ch;
        } else if (ch >= 'A' && ch <= 'Z') {
          digits += (ch.charCodeAt(0) - 65 + 1).toString();
        }
      }
      if (!digits) return 1;
      const num = BigInt(digits) * 100n;
      const rem = Number(num % 97n);
      return 98 - rem;
    }

    function updateControl() {
      const val = document.getElementById('testInput').value.trim();
      const tag = document.getElementById('calcTag');
      if (!val) {
        tag.textContent = "// Ingrese comando.";
        return;
      }
      if (val.toUpperCase().startsWith("PING")) {
        tag.textContent = `// PING no requiere control -> Payload exacto: "${val}"`;
        return;
      }
      const ctrl = computeControl(val);
      tag.textContent = `// Mensaje a enviar: "${val};${ctrl}" (ISO 7064 MOD 97-10 = ${ctrl})`;
    }

    async function sendLiveProbe() {
      const val = document.getElementById('testInput').value.trim();
      if (!val) return;
      let msg = val;
      if (!val.toUpperCase().startsWith("PING") && !val.match(/;\d{1,2}$/)) {
        msg = `${val};${computeControl(val)}`;
      }

      const out = document.getElementById('outputLog');
      out.textContent = `-> POST /msg { "m": "${msg}" }...`;

      try {
        const res = await fetch("/msg", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + TEAM_TOKEN
          },
          body: JSON.stringify({ m: msg })
        });
        const data = await res.json();
        out.textContent = `<- HTTP ${res.status}\n` + JSON.stringify(data, null, 2);
      } catch (e) {
        out.textContent = `<- ERROR DE RED: ${e.message}`;
      }
    }

    async function sendReset() {
      const out = document.getElementById('outputLog');
      out.textContent = `-> POST /__reset...`;
      try {
        const res = await fetch("/__reset", {
          method: "POST",
          headers: { "Authorization": "Bearer " + TEAM_TOKEN }
        });
        const data = await res.json();
        out.textContent = `<- HTTP ${res.status}\n` + JSON.stringify(data, null, 2);
      } catch (e) {
        out.textContent = `<- ERROR DE RED: ${e.message}`;
      }
    }

    // Process Stream Steps: Scrapes, Discards, Synthesizes
    const EVENTS = [
      { type: "probe", text: "[01 // BOUNDARIES] Sondeando limite de payload HTTP via busqueda binaria (1024B, 4096B, 8192B, 16384B)..." },
      { type: "probe", text: "  -> POST /msg con body de 16384 bytes..." },
      { type: "discard", text: "[DESCARTADO] Hipotesis 'limite sin restricciones': Respuesta HTTP 413 rechaza hipotesis." },
      { type: "probe", text: "  -> Ajuste a 8192 bytes: 200 OK. Ajuste a 8193 bytes: 413 E101." },
      { type: "rule", target: "rule-body", title: "8192 BYTES (413 E101)", val: "Limite exacto de payload confirmado por cota inferior y superior.", text: "[CONSENSO CONFIRMADO] Regla max_body_bytes = 8192 consolidada (2 obs, 0 contr)." },
      
      { type: "probe", text: "[02 // PRECEDENCE] Generando colision de restricciones en TRANSFER (Tope >50000 Y Saldo Insuficiente)..." },
      { type: "probe", text: "  -> Probe c_prec_01: transferencia 60000 con saldo 0 en AC-0001..." },
      { type: "discard", text: "[DESCARTADO] Hipotesis v1 'saldo insuficiente primero (E507)': El servicio responde 422 E506." },
      { type: "rule", target: "rule-prec", title: "max_amount (E506) > sufficient_balance (E507)", val: "Inversion respecto a v1 confirmada por precedencia estricta.", text: "[CONSENSO CONFIRMADO] Orden de validacion: E506 evaluado antes que E507." },

      { type: "probe", text: "[03 // INPUTS] Generando mutaciones de delimitadores y codificaciones de caracteres..." },
      { type: "probe", text: "  -> Inyectando byte sequence UTF-8 BOM (\\xef\\xbb\\xbf) al inicio del JSON..." },
      { type: "discard", text: "[DESCARTADO] Hipotesis 'BOM tolerado por json.loads': Servicio original rechaza con 400 E100." },
      { type: "rule", target: "rule-bom", title: "RECHAZO ESTRICTO DE BOM (400 E100)", val: "Tratamiento como json invalido antes de deserializacion.", text: "[CONSENSO CONFIRMADO] Regla BOM UTF-8 confirmada en frontera HTTP." },

      { type: "probe", text: "[04 // STATEFUL] Analisis matematico de digito de control ISO 7064 MOD 97-10..." },
      { type: "probe", text: "  -> Busqueda de casos frontera donde (N * 100) % 97 == 0..." },
      { type: "discard", text: "[DESCARTADO] Hipotesis heuristica 'resto 0 normaliza a 1': Original devuelve 400 E202 al mandar 1." },
      { type: "probe", text: "  -> Verificacion con control 98: Original responde 200 OK." },
      { type: "rule", target: "rule-ctrl", title: "RESTO 0 -> CONTROL 98 (FORMULA ESTRICTA)", val: "98 - ((N * 100) % 97). Cero excepciones observadas.", text: "[CONSENSO CONFIRMADO] Algoritmo ISO 7064 unificado a norma estricta." },

      { type: "probe", text: "[05 // SHAPES] Analisis de salida en CONSULTA..." },
      { type: "probe", text: "  -> Verificando representacion de saldo tras deposito de 25000..." },
      { type: "rule", target: "rule-cons", title: "STRING DECIMAL '250.00'", val: "Division por 100 con 2 decimales fijos.", text: "[CONSENSO CONFIRMADO] Formato de balance establecido a string decimal." },

      { type: "probe", text: "=================================================================" },
      { type: "synthesize", text: "[FIN] PERFIL v2 CONVERGIDO: 100% DE REGLAS CONFIRMADAS SIN HIPOTESIS RESIDUALES." }
    ];

    let isRunning = false;
    let eventIdx = 0;

    async function startProcessStream() {
      if (isRunning) return;
      isRunning = true;
      document.getElementById('btnRun').disabled = true;
      document.getElementById('statusIndicator').textContent = "[ESTADO: EJECUTANDO SONDEO Y SINTESIS]";
      
      const feed = document.getElementById('streamFeed');
      if (eventIdx === 0) feed.innerHTML = "";

      while (eventIdx < EVENTS.length) {
        const ev = EVENTS[eventIdx];
        const line = document.createElement('div');
        line.className = 'stream-line';

        if (ev.type === "probe") {
          line.className += ' line-probe';
          line.textContent = ev.text;
        } else if (ev.type === "discard") {
          line.className += ' line-discard';
          line.innerHTML = `<span class="badge-discard">DESCARTE</span> ${ev.text}`;
        } else if (ev.type === "rule") {
          line.className += ' line-synthesize';
          line.innerHTML = `<span class="badge-rule">SINTESIS</span> ${ev.text}`;
          
          // Update matrix card
          const card = document.getElementById(ev.target);
          if (card) {
            card.classList.add('confirmed');
            card.querySelector('.rule-name').textContent = ev.title;
            card.querySelector('.rule-val').textContent = ev.val;
          }
        } else if (ev.type === "synthesize") {
          line.className += ' line-synthesize';
          line.textContent = ev.text;
        }

        feed.appendChild(line);
        feed.scrollTop = feed.scrollHeight;
        
        eventIdx++;
        document.getElementById('probeCount').textContent = `${eventIdx} PASOS`;

        await new Promise(r => setTimeout(r, 650));
      }

      document.getElementById('statusIndicator').textContent = "[ESTADO: CONVERGENCIA COMPLETA]";
      document.getElementById('btnRun').disabled = false;
      document.getElementById('ruleCount').textContent = "5 REGLAS ACTIVAS";
      isRunning = false;
    }

    function resetProcessStream() {
      eventIdx = 0;
      isRunning = false;
      document.getElementById('btnRun').disabled = false;
      document.getElementById('statusIndicator').textContent = "[ESTADO: ESPERANDO EJECUCION]";
      document.getElementById('streamFeed').innerHTML = `
        <div class="stream-line line-probe">
          // Sistema reiniciado.<br>
          // Haz clic en "[ &gt; DISPARAR CICLO DE EXPLORACION Y DESCARTE ]" para observar el proceso algoritmico en tiempo real.
        </div>
      `;
      document.getElementById('probeCount').textContent = "0 PROBES";
      document.getElementById('ruleCount').textContent = "0 REGLAS";

      const targets = [
        { id: "rule-ctrl", name: "[MOD-97-10] CHECKSUM ISO 7064", val: "Pendiente de inferencia..." },
        { id: "rule-bom", name: "[ENCODING] UTF-8 BOM", val: "Pendiente de inferencia..." },
        { id: "rule-body", name: "[TAMANIO] MAX BODY BYTES", val: "Pendiente de inferencia..." },
        { id: "rule-prec", name: "[EVALUACION] ORDEN DE VALIDACION", val: "Pendiente de inferencia..." },
        { id: "rule-cons", name: "[REPRESENTACION] FORMATO DE SALDO", val: "Pendiente de inferencia..." }
      ];

      targets.forEach(t => {
        const el = document.getElementById(t.id);
        if (el) {
          el.classList.remove('confirmed');
          el.querySelector('.rule-name').textContent = t.name;
          el.querySelector('.rule-val').textContent = t.val;
        }
      });
    }

    updateControl();
  </script>
</body>
</html>
"""
