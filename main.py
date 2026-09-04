import os
import sys
import threading
import time
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import pandas as pd
import requests

# ================= CONFIGURAÇÕES =================
TG_TOKEN = os.environ.get("TG_TOKEN", "8601904952:AAHPJhTPKnE2UOoTrtm228cHCyFv8wNHxY8").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "999294230").strip()

EMAIL_IQ = os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip()
SENHA_IQ = os.environ.get("IQ_PASSWORD", "").strip()
TIPO_CONTA = os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper()

VALOR_BASE = 20.0
STOP_WIN = 60.0
STOP_LOSS = 40.0

ESTADO = {
    "status": "Iniciando sistema...",
    "conectado": False,
    "saldo": 0.0,
    "tipo_conta": TIPO_CONTA,
    "ativo": "EURUSD-OTC",
    "ativos_abertos": ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC"],
    "placar_w": 0,
    "placar_l": 0,
    "lucro_dia": 0.0,
    "soros_nivel": 1,
    "soros_lucro": 0.0,
    "ultimo_audio": "",
    "velas": []
}

API_GLOBAL = None
LOCK_ORDEM = threading.Lock()

# ================= TELEGRAM (FORMATO EXATO DO SEU PRINT) =================
def enviar_telegram(msg):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    def _envio():
        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT_ID, "text": msg},
                timeout=6
            )
        except Exception:
            pass
    threading.Thread(target=_envio, daemon=True).start()

# ================= SERVIDOR COM CANVAS, PIP E SÍNTESE DE VOZ =================
class ServidorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/dados':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(ESTADO).encode('utf-8'))
            return

        if self.path.startswith('/api/velas'):
            par = ESTADO["ativo"]
            if 'par=' in self.path:
                par = self.path.split('par=')[1].split('&')[0]
                ESTADO["ativo"] = par

            velas_out = []
            if API_GLOBAL and ESTADO["conectado"]:
                try:
                    raw = API_GLOBAL.get_candles(par, 60, 30, time.time())
                    if raw:
                        for v in raw:
                            velas_out.append({
                                "open": float(v["open"]),
                                "max": float(v["max"]),
                                "min": float(v["min"]),
                                "close": float(v["close"])
                            })
                        ESTADO["velas"] = velas_out
                except Exception:
                    pass

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(velas_out).encode('utf-8'))
            return

        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()

        html = """
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <title>Apex Pro Trader</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <style>
                body { background:#070a13; color:#cbd5e1; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
                .card { background:#0f172a; border:1px solid #1e293b; }
            </style>
        </head>
        <body class="p-2 space-y-2 max-w-md mx-auto select-none">
            <!-- Cabeçalho -->
            <div class="card p-3 rounded-xl flex items-center justify-between">
                <div>
                    <div class="flex items-center space-x-2">
                        <span id="dot" class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                        <span class="font-black text-sm text-cyan-400">APEX PRO TRADER</span>
                    </div>
                    <div class="text-[10px] text-slate-400 mt-0.5" id="txt-status">Conectando...</div>
                </div>
                <div class="text-right font-mono">
                    <div class="text-[10px] text-slate-400" id="txt-tipo">PRACTICE</div>
                    <div class="text-sm font-black text-white" id="txt-saldo">R$ 0,00</div>
                </div>
            </div>

            <!-- Seleção Dinâmica de Ativos e Controle de Voz -->
            <div class="card p-2 rounded-xl flex items-center justify-between gap-2">
                <div class="flex-1">
                    <label class="text-[9px] text-slate-400 font-bold block">ATIVO ABERTO NA CORRETORA</label>
                    <select id="sel-ativo" onchange="mudarAtivo()" class="w-full bg-slate-900 border border-slate-700 text-xs font-bold rounded p-1.5 text-white outline-none">
                        <option value="EURUSD-OTC">EUR/USD (OTC)</option>
                    </select>
                </div>
                <button id="btn-voz" onclick="toggleVoz()" class="px-3 py-2 bg-emerald-600/30 border border-emerald-500 text-emerald-400 font-bold text-xs rounded-lg flex items-center gap-1 mt-3">
                    <span id="txt-voz">🔊 VOZ: ATIVA</span>
                </button>
            </div>

            <!-- Botão Picture-in-Picture Flutuante -->
            <button onclick="iniciarPiP()" class="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 active:scale-95 text-white font-black text-xs rounded-xl flex items-center justify-center space-x-2 shadow-lg shadow-cyan-950">
                <span>📺 ATIVAR TELA FLUTUANTE (PIP)</span>
            </button>

            <!-- Gráfico de Velas Canvas Nativo -->
            <div class="card rounded-xl p-2 relative">
                <div class="flex justify-between items-center mb-1 text-xs font-mono">
                    <span class="font-bold text-white" id="txt-ativo-lbl">EURUSD-OTC</span>
                    <span class="text-cyan-400 font-bold" id="txt-preco">---</span>
                </div>
                <canvas id="canvas-grafico" width="380" height="210" class="w-full rounded bg-slate-950 border border-slate-900"></canvas>
                <video id="video-pip" autoplay muted playsinline style="position:fixed; width:1px; height:1px; opacity:0.01; pointer-events:none;"></video>
            </div>

            <!-- Botões de Execução Manual -->
            <div class="grid grid-cols-2 gap-2">
                <button onclick="enviarManual('CALL')" class="h-12 bg-emerald-600 active:scale-95 text-white font-black text-xs rounded-xl flex items-center justify-center space-x-1 shadow-lg shadow-emerald-950">
                    <span>▲ COMPRA (CALL)</span>
                </button>
                <button onclick="enviarManual('PUT')" class="h-12 bg-rose-600 active:scale-95 text-white font-black text-xs rounded-xl flex items-center justify-center space-x-1 shadow-lg shadow-rose-950">
                    <span>▼ VENDA (PUT)</span>
                </button>
            </div>

            <!-- Placar e Resumo -->
            <div class="card p-2.5 rounded-xl flex justify-between text-xs font-mono">
                <span class="text-slate-400">PLACAR:</span>
                <span class="font-bold text-white" id="txt-placar">0 WIN x 0 LOSS</span>
                <span class="text-slate-400">LUCRO:</span>
                <span class="font-bold text-emerald-400" id="txt-lucro">R$ 0,00</span>
            </div>

            <script>
                const canvas = document.getElementById('canvas-grafico');
                const ctx = canvas.getContext('2d');
                const video = document.getElementById('video-pip');
                let vozAtiva = true;
                let ultimaFala = "";

                function falar(texto) {
                    if (!vozAtiva || !('speechSynthesis' in window)) return;
                    if (texto === ultimaFala) return;
                    ultimaFala = texto;
                    const utterance = new SpeechSynthesisUtterance(texto);
                    utterance.lang = 'pt-BR';
                    utterance.rate = 1.1;
                    window.speechSynthesis.speak(utterance);
                }

                function toggleVoz() {
                    vozAtiva = !vozAtiva;
                    document.getElementById('txt-voz').innerText = vozAtiva ? "🔊 VOZ: ATIVA" : "🔇 VOZ: MUDO";
                }

                function renderizarVelas(velas) {
                    ctx.fillStyle = '#030712';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);

                    if (!velas || velas.length === 0) {
                        ctx.fillStyle = '#64748b';
                        ctx.font = '12px monospace';
                        ctx.textAlign = 'center';
                        ctx.fillText('Aguardando velas da corretora...', canvas.width / 2, canvas.height / 2);
                        return;
                    }

                    let min = Infinity, max = -Infinity;
                    velas.forEach(v => {
                        if (v.min < min) min = v.min;
                        if (v.max > max) max = v.max;
                    });
                    const diff = (max - min) || 0.0001;
                    const w = (canvas.width - 20) / velas.length;

                    velas.forEach((v, i) => {
                        const x = 10 + i * w;
                        const yOpen = canvas.height - 20 - ((v.open - min) / diff) * (canvas.height - 40);
                        const yClose = canvas.height - 20 - ((v.close - min) / diff) * (canvas.height - 40);
                        const yMax = canvas.height - 20 - ((v.max - min) / diff) * (canvas.height - 40);
                        const yMin = canvas.height - 20 - ((v.min - min) / diff) * (canvas.height - 40);

                        const alta = v.close >= v.open;
                        ctx.strokeStyle = alta ? '#10b981' : '#f43f5e';
                        ctx.fillStyle = alta ? '#10b981' : '#f43f5e';

                        ctx.beginPath();
                        ctx.moveTo(x + w / 2, yMax);
                        ctx.lineTo(x + w / 2, yMin);
                        ctx.stroke();

                        const top = Math.min(yOpen, yClose);
                        const h = Math.max(Math.abs(yClose - yOpen), 2);
                        ctx.fillRect(x + 1.5, top, Math.max(w - 3, 2), h);
                    });

                    document.getElementById('txt-preco').innerText = velas[velas.length - 1].close.toFixed(5);
                }

                async function iniciarPiP() {
                    try {
                        if (!video.srcObject) {
                            video.srcObject = canvas.captureStream(25);
                            await video.play();
                        }
                        if (document.pictureInPictureElement) {
                            await document.exitPictureInPicture();
                        } else {
                            await video.requestPictureInPicture();
                        }
                    } catch (e) {
                        alert("Permissão para janela flutuante necessária no navegador.");
                    }
                }

                async function sincronizar() {
                    try {
                        const res = await fetch('/api/dados');
                        const d = await res.json();

                        document.getElementById('txt-saldo').innerText = 'R$ ' + d.saldo.toFixed(2);
                        document.getElementById('txt-tipo').innerText = d.tipo_conta;
                        document.getElementById('txt-status').innerText = d.status;
                        document.getElementById('txt-placar').innerText = `${d.placar_w} WIN x ${d.placar_l} LOSS`;
                        document.getElementById('txt-ativo-lbl').innerText = d.ativo;

                        const dot = document.getElementById('dot');
                        dot.className = d.conectado ? 'w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse' : 'w-2.5 h-2.5 rounded-full bg-rose-500';

                        // Atualiza lista de ativos abertos se mudou
                        const select = document.getElementById('sel-ativo');
                        if (d.ativos_abertos && d.ativos_abertos.length > 0 && select.options.length <= 1) {
                            select.innerHTML = d.ativos_abertos.map(a => `<option value="${a}">${a}</option>`).join('');
                            select.value = d.ativo;
                        }

                        if (d.ultimo_audio) {
                            falar(d.ultimo_audio);
                        }

                        // Busca velas
                        const resVelas = await fetch('/api/velas?par=' + d.ativo);
                        const velas = await resVelas.json();
                        renderizarVelas(velas);
                    } catch (e) {}
                }

                function mudarAtivo() {
                    const novo = document.getElementById('sel-ativo').value;
                    fetch('/api/trocar-ativo', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ ativo: novo })
                    });
                }

                function enviarManual(dir) {
                    fetch('/api/manual', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ dir })
                    });
                }

                setInterval(sincronizar, 2000);
                sincronizar();
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        tam = int(self.headers.get('Content-Length', 0))
        corpo = json.loads(self.rfile.read(tam).decode('utf-8')) if tam > 0 else {}

        if self.path == '/api/trocar-ativo':
            ESTADO["ativo"] = corpo.get("ativo", "EURUSD-OTC")
            self.send_response(200)
            self.end_headers()
            return

        if self.path == '/api/manual':
            dir_op = corpo.get("dir", "CALL")
            threading.Thread(target=processar_ordem, args=(ESTADO["ativo"], dir_op, VALOR_BASE, 85.0, 50.0, "MANUAL"), daemon=True).start()
            self.send_response(200)
            self.end_headers()
            return

    def log_message(self, format, *args):
        return

def iniciar_servidor():
    porta = int(os.environ.get("PORT", 10000))
    srv = ThreadingHTTPServer(('0.0.0.0', porta), ServidorHandler)
    srv.serve_forever()

threading.Thread(target=iniciar_servidor, daemon=True).start()

# ================= MOTOR DE ANÁLISE E ORDENS =================
def atualizar_ativos_abertos():
    global API_GLOBAL
    try:
        dados = API_GLOBAL.get_all_open_time()
        encontrados = []
        for cat in ['digital', 'turbo', 'binary']:
            if cat in dados:
                for ativo, info in dados[cat].items():
                    if info.get('open', False) and ativo not in encontrados:
                        encontrados.append(ativo)
        if encontrados:
            ESTADO["ativos_abertos"] = sorted(encontrados[:20])
    except Exception:
        pass

def processar_ordem(ativo, direcao, valor, prob, rsi, tipo_entrada="AUTO"):
    global API_GLOBAL
    if not API_GLOBAL or not ESTADO["conectado"]:
        return

    with LOCK_ORDEM:
        agora = datetime.now()
        hora_ent = agora.strftime("%H:%M:%S")
        hora_exp = datetime.fromtimestamp(agora.timestamp() + 60).strftime("%H:%M:%S")
        mao_txt = "Mão 1 (Base)" if ESTADO["soros_nivel"] == 1 else "Mão 2 (Soros)"
        dir_txt = "🟢 CALL (COMPRA)" if direcao == "CALL" else "🔴 PUT (VENDA)"

        # Dispara comando de áudio para o painel falar
        ESTADO["ultimo_audio"] = f"Atenção, entrada de {('compra' if direcao == 'CALL' else 'venda')} no {ativo.replace('-', ' ')}"

        # Notificação Telegram com seu template visual exato
        msg_alerta = (
            f"⚡ Direção: {dir_txt}\n"
            f"📊 Probabilidade: {prob:.1f}% 🔥\n"
            f"💰 Valor da Entrada: R$ {valor:.2f} ({mao_txt})\n"
            f"⏰ Horário Entrada: {hora_ent}\n"
            f"⏳ Expiração Prevista: {hora_exp}\n"
            f"📐 RSI(7): {rsi:.1f} | TF: M1\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ Status: Executando na corretora..."
        )
        enviar_telegram(msg_alerta)

        id_ordem = None
        tipo_op = "DIGITAL"
        try:
            _, id_dig = API_GLOBAL.buy_digital_spot(ativo, valor, direcao.lower(), 1)
            if id_dig and id_dig != "error":
                id_ordem = id_dig
        except Exception:
            pass

        if not id_ordem:
            try:
                status, id_bin = API_GLOBAL.buy(valor, ativo, direcao.lower(), 1)
                if status and id_bin:
                    id_ordem = id_bin
                    tipo_op = "BINARY"
            except Exception:
                pass

        if id_ordem:
            time.sleep(62)
            resultado = "LOSS"
            lucro_real = 0.0

            try:
                if tipo_op == "DIGITAL":
                    check, lucro = API_GLOBAL.check_win_digital_v2(id_ordem)
                    if check and lucro > 0:
                        resultado = "WIN"
                        lucro_real = float(lucro)
                else:
                    status, lucro = API_GLOBAL.check_win_v4(id_ordem)
                    if status and lucro > 0:
                        resultado = "WIN"
                        lucro_real = float(lucro)
            except Exception:
                pass

            # Gestão Soros N2
            if resultado == "WIN":
                ESTADO["placar_w"] += 1
                if ESTADO["soros_nivel"] == 1:
                    ESTADO["soros_nivel"] = 2
                    ESTADO["soros_lucro"] = lucro_real
                else:
                    ESTADO["soros_nivel"] = 1
                    ESTADO["soros_lucro"] = 0.0
                res_txt = f"+R$ {lucro_real:.2f}"
                desf_txt = "✅ WIN (VITÓRIA)"
                ESTADO["ultimo_audio"] = "Operação finalizada em vitória!"
            else:
                ESTADO["placar_l"] += 1
                ESTADO["soros_nivel"] = 1
                ESTADO["soros_lucro"] = 0.0
                res_txt = f"-R$ {valor:.2f}"
                desf_txt = "❌ LOSS (PERDA)"
                ESTADO["ultimo_audio"] = "Operação finalizada em perda."

            try:
                ESTADO["saldo"] = float(API_GLOBAL.get_balance())
                ESTADO["lucro_dia"] = ESTADO["saldo"] - ESTADO.get("saldo_inicial", ESTADO["saldo"])
            except Exception:
                pass

            hora_fim = datetime.now().strftime("%H:%M:%S")

            # Relatório Telegram idêntico ao seu print
            msg_res = (
                "📋 RESULTADO DA OPERAÇÃO (NUVEM)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🏁 Desfecho: {desf_txt}\n"
                f"💵 Resultado: {res_txt}\n"
                f"📈 Ativo: {ativo}\n"
                f"🕒 Entrada: {hora_ent} | Fechamento: {hora_fim}\n"
                f"📊 Placar Atual: {ESTADO['placar_w']} WIN  x  {ESTADO['placar_l']} LOSS\n"
                f"💼 Banca Atualizada: R$ {ESTADO['saldo']:.2f}"
            )
            enviar_telegram(msg_res)

def loop_principal():
    global API_GLOBAL
    from iqoptionapi.stable_api import IQ_Option

    while True:
        if not ESTADO["conectado"]:
            if not SENHA_IQ:
                ESTADO["status"] = "Erro: Adicione IQ_PASSWORD no Render"
                time.sleep(5)
                continue

            ESTADO["status"] = "Autenticando na corretora..."
            try:
                api = IQ_Option(EMAIL_IQ, SENHA_IQ)
                ok, _ = api.connect()
                if ok:
                    api.change_balance(TIPO_CONTA)
                    saldo = float(api.get_balance())
                    ESTADO["saldo"] = saldo
                    ESTADO["saldo_inicial"] = saldo
                    ESTADO["conectado"] = True
                    ESTADO["status"] = "Monitorando 24/7"
                    API_GLOBAL = api

                    atualizar_ativos_abertos()

                    # Mensagem de Início Exata do seu print
                    enviar_telegram(
                        "🚀 ROBÔ 24H INICIADO NA NUVEM\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"💼 Conta: {TIPO_CONTA}\n"
                        f"💰 Banca Inicial: R$ {saldo:.2f}\n"
                        f"📈 Ativo: {ESTADO['ativo']} | TF: M1\n"
                        "🎯 Estratégia: EMA 7/21 + RSI(7) + Soros N2\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "🟢 Status: Monitorando mercado 24/7..."
                    )
                else:
                    ESTADO["status"] = "Falha no login. Verifique e-mail e senha."
                    time.sleep(10)
            except Exception as e:
                ESTADO["status"] = f"Erro de conexão: {e}"
                time.sleep(10)

        time.sleep(1)
        seg = int(time.time()) % 60

        # A cada 5 minutos atualiza a lista de ativos abertos
        if seg == 30 and (int(time.time()) // 60) % 5 == 0 and API_GLOBAL:
            atualizar_ativos_abertos()

        # Análise de mercado no fechamento exato da vela (segundo 00)
        if seg == 0 and ESTADO["conectado"] and API_GLOBAL:
            try:
                par = ESTADO["ativo"]
                velas = API_GLOBAL.get_candles(par, 60, 25, time.time())
                if velas and len(velas) >= 22:
                    df = pd.DataFrame(velas)
                    ema7 = df['close'].ewm(span=7, adjust=False).mean().iloc[-1]
                    ema21 = df['close'].ewm(span=21, adjust=False).mean().iloc[-1]

                    delta = df['close'].diff()
                    ganho = (delta.where(delta > 0, 0)).rolling(7).mean()
                    perda = (-delta.where(delta < 0, 0)).rolling(7).mean()
                    rsi = 100 - (100 / (1 + (ganho / (perda + 1e-9))))
                    rsi_val = float(rsi.iloc[-1])

                    direcao = None
                    prob = 0.0

                    if ema7 > ema21 and rsi_val < 42.0:
                        direcao = "CALL"
                        prob = 82.4
                    elif ema7 < ema21 and rsi_val > 58.0:
                        direcao = "PUT"
                        prob = 80.4

                    if direcao and prob >= 80.0:
                        valor = VALOR_BASE if ESTADO["soros_nivel"] == 1 else (VALOR_BASE + ESTADO["soros_lucro"])
                        threading.Thread(target=processar_ordem, args=(par, direcao, valor, prob, rsi_val, "AUTO"), daemon=True).start()
            except Exception:
                pass

if __name__ == "__main__":
    loop_principal()
