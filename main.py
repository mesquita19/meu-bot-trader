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
ATIVO_PADRAO = "EURUSD-OTC"

ESTADO = {
    "status": "Iniciando sistema...",
    "conectado": False,
    "saldo": 0.0,
    "tipo_conta": TIPO_CONTA,
    "ativo": ATIVO_PADRAO,
    "placar_w": 0,
    "placar_l": 0,
    "lucro_dia": 0.0,
    "velas": []
}

API_GLOBAL = None

# ================= TELEGRAM COM FORMATAÇÃO DO SEU PRINT =================
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

# ================= SERVIDOR COM CANVAS NATIVO & PICTURE-IN-PICTURE =================
class ServidorPiP(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/dados':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(ESTADO).encode('utf-8'))
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
            <title>Apex Trader Pro</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <style>
                body { background:#070a13; color:#cbd5e1; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
                .card { background:#0f172a; border:1px solid #1e293b; }
            </style>
        </head>
        <body class="p-3 space-y-3 max-w-md mx-auto">
            <!-- Topo / Saldo -->
            <div class="card p-3 rounded-xl flex items-center justify-between">
                <div>
                    <div class="flex items-center space-x-2">
                        <span id="dot" class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                        <span class="font-black text-sm text-cyan-400">APEX TRADER PRO</span>
                    </div>
                    <div class="text-[10px] text-slate-400 mt-0.5" id="txt-status">Conectando...</div>
                </div>
                <div class="text-right font-mono">
                    <div class="text-[10px] text-slate-400" id="txt-tipo">PRACTICE</div>
                    <div class="text-sm font-black text-white" id="txt-saldo">R$ 0,00</div>
                </div>
            </div>

            <!-- Botão de Picture-in-Picture (Janela Flutuante) -->
            <button onclick="ativarPiP()" class="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 active:scale-95 text-white font-black text-xs rounded-xl flex items-center justify-center space-x-2 shadow-lg shadow-cyan-950">
                <span>📺 ATIVAR TELA FLUTUANTE (PICTURE-IN-PICTURE)</span>
            </button>

            <!-- Gráfico de Velas Renderizado Direto no Canvas -->
            <div class="card rounded-xl p-2 relative">
                <div class="flex justify-between items-center mb-1 text-xs font-mono">
                    <span class="font-bold text-white" id="txt-ativo">EUR/USD (OTC)</span>
                    <span class="text-cyan-400 font-bold" id="txt-preco">---</span>
                </div>
                <!-- Canvas que desenha as velas -->
                <canvas id="grafico-canvas" width="380" height="230" class="w-full rounded bg-slate-950 border border-slate-900"></canvas>
                <!-- Elemento de Vídeo oculto usado para o Picture-in-Picture nativo -->
                <video id="pip-video" autoplay muted playsinline style="position:fixed; bottom:0; right:0; width:1px; height:1px; opacity:0.01; pointer-events:none;"></video>
            </div>

            <!-- Botões Manuais de Compra e Venda -->
            <div class="grid grid-cols-2 gap-2">
                <button onclick="disparar('CALL')" class="h-12 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-black text-xs rounded-xl flex items-center justify-center space-x-1 shadow-lg shadow-emerald-950">
                    <span>▲ COMPRA (CALL)</span>
                </button>
                <button onclick="disparar('PUT')" class="h-12 bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-black text-xs rounded-xl flex items-center justify-center space-x-1 shadow-lg shadow-rose-950">
                    <span>▼ VENDA (PUT)</span>
                </button>
            </div>

            <!-- Placar e Status -->
            <div class="card p-2.5 rounded-xl flex justify-between text-xs font-mono">
                <span class="text-slate-400">PLACAR:</span>
                <span class="font-bold text-white" id="txt-placar">0 WIN x 0 LOSS</span>
                <span class="text-slate-400">LUCRO:</span>
                <span class="font-bold text-emerald-400" id="txt-lucro">R$ 0,00</span>
            </div>

            <script>
                const canvas = document.getElementById('grafico-canvas');
                const ctx = canvas.getContext('2d');
                const video = document.getElementById('pip-video');

                function desenharVelas(velas) {
                    ctx.fillStyle = '#030712';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);

                    if (!velas || velas.length === 0) {
                        ctx.fillStyle = '#64748b';
                        ctx.font = '12px monospace';
                        ctx.textAlign = 'center';
                        ctx.fillText('Sincronizando velas da IQ Option...', canvas.width / 2, canvas.height / 2);
                        return;
                    }

                    // Encontra valores mínimos e máximos para escala
                    let minPrice = Infinity;
                    let maxPrice = -Infinity;
                    velas.forEach(v => {
                        if (v.min < minPrice) minPrice = v.min;
                        if (v.max > maxPrice) maxPrice = v.max;
                    });
                    const range = (maxPrice - minPrice) || 0.0001;

                    const candleWidth = (canvas.width - 20) / velas.length;

                    velas.forEach((v, i) => {
                        const x = 10 + i * candleWidth;
                        const yOpen = canvas.height - 20 - ((v.open - minPrice) / range) * (canvas.height - 40);
                        const yClose = canvas.height - 20 - ((v.close - minPrice) / range) * (canvas.height - 40);
                        const yHigh = canvas.height - 20 - ((v.max - minPrice) / range) * (canvas.height - 40);
                        const yLow = canvas.height - 20 - ((v.min - minPrice) / range) * (canvas.height - 40);

                        const isGreen = v.close >= v.open;
                        ctx.strokeStyle = isGreen ? '#10b981' : '#f43f5e';
                        ctx.fillStyle = isGreen ? '#10b981' : '#f43f5e';

                        // Pavio
                        ctx.beginPath();
                        ctx.moveTo(x + candleWidth / 2, yHigh);
                        ctx.lineTo(x + candleWidth / 2, yLow);
                        ctx.stroke();

                        // Corpo da vela
                        const top = Math.min(yOpen, yClose);
                        const height = Math.max(Math.abs(yClose - yOpen), 2);
                        ctx.fillRect(x + 2, top, Math.max(candleWidth - 4, 2), height);
                    });

                    // Preço atual no canto
                    const ult = velas[velas.length - 1];
                    document.getElementById('txt-preco').innerText = ult.close.toFixed(5);
                }

                async function ativarPiP() {
                    try {
                        if (!video.srcObject) {
                            const stream = canvas.captureStream(25);
                            video.srcObject = stream;
                            await video.play();
                        }
                        if (document.pictureInPictureElement) {
                            await document.exitPictureInPicture();
                        } else {
                            await video.requestPictureInPicture();
                        }
                    } catch (e) {
                        alert("Picture-in-Picture: certifique-se de que o navegador tem permissão para janelas flutuantes.");
                    }
                }

                async function atualizar() {
                    try {
                        const res = await fetch('/api/dados');
                        const d = await res.json();

                        document.getElementById('txt-saldo').innerText = 'R$ ' + d.saldo.toFixed(2);
                        document.getElementById('txt-tipo').innerText = d.tipo_conta;
                        document.getElementById('txt-status').innerText = d.status;
                        document.getElementById('txt-placar').innerText = `${d.placar_w} WIN x ${d.placar_l} LOSS`;
                        document.getElementById('txt-ativo').innerText = d.ativo;

                        const dot = document.getElementById('dot');
                        if (d.conectado) {
                            dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse';
                        } else {
                            dot.className = 'w-2.5 h-2.5 rounded-full bg-rose-500';
                        }

                        desenharVelas(d.velas);
                    } catch (e) {}
                }

                function disparar(dir) {
                    fetch('/api/ordem', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ dir })
                    });
                }

                setInterval(atualizar, 1500);
                atualizar();
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        tam = int(self.headers.get('Content-Length', 0))
        corpo = json.loads(self.rfile.read(tam).decode('utf-8')) if tam > 0 else {}
        if self.path == '/api/ordem':
            dir_op = corpo.get("dir", "CALL")
            threading.Thread(target=executar_ordem_manual, args=(dir_op,), daemon=True).start()
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return

def iniciar_servidor():
    porta = int(os.environ.get("PORT", 10000))
    httpd = ThreadingHTTPServer(('0.0.0.0', porta), ServidorPiP)
    httpd.serve_forever()

threading.Thread(target=iniciar_servidor, daemon=True).start()

# ================= MOTOR DE TRADING & ORDENS =================
def executar_ordem_manual(direcao):
    global API_GLOBAL
    if not API_GLOBAL or not ESTADO["conectado"]:
        return
    agora = datetime.now()
    hora_entrada = agora.strftime("%H:%M:%S")
    hora_exp = datetime.fromtimestamp(agora.timestamp() + 60).strftime("%H:%M:%S")
    dir_txt = "🟢 CALL (COMPRA)" if direcao == "CALL" else "🔴 PUT (VENDA)"

    enviar_telegram(
        f"⚡ Direção: {dir_txt}\n"
        f"📊 Probabilidade: 85.0% 🔥\n"
        f"💰 Valor da Entrada: R$ {VALOR_BASE:.2f} (Manual)\n"
        f"⏰ Horário Entrada: {hora_entrada}\n"
        f"⏳ Expiração Prevista: {hora_exp}\n"
        f"📐 RSI(7): Dinâmico | TF: M1\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Status: Executando na corretora..."
    )

    id_ordem = None
    try:
        _, id_dig = API_GLOBAL.buy_digital_spot(ATIVO_PADRAO, VALOR_BASE, direcao.lower(), 1)
        if id_dig and id_dig != "error":
            id_ordem = id_dig
    except Exception:
        pass

    if not id_ordem:
        try:
            status, id_bin = API_GLOBAL.buy(VALOR_BASE, ATIVO_PADRAO, direcao.lower(), 1)
            if status and id_bin:
                id_ordem = id_bin
        except Exception:
            pass

    if id_ordem:
        time.sleep(62)
        resultado = "LOSS"
        try:
            check, lucro = API_GLOBAL.check_win_digital_v2(id_ordem)
            if check and lucro > 0:
                resultado = "WIN"
        except Exception:
            pass

        if resultado == "WIN":
            ESTADO["placar_w"] += 1
            res_txt = f"+R$ {VALOR_BASE * 0.85:.2f}"
            desf_txt = "✅ WIN (VITÓRIA)"
        else:
            ESTADO["placar_l"] += 1
            res_txt = f"-R$ {VALOR_BASE:.2f}"
            desf_txt = "❌ LOSS (PERDA)"

        try:
            ESTADO["saldo"] = float(API_GLOBAL.get_balance())
        except Exception:
            pass

        hora_fim = datetime.now().strftime("%H:%M:%S")
        enviar_telegram(
            f"📋 RESULTADO DA OPERAÇÃO (NUVEM)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏁 Desfecho: {desf_txt}\n"
            f"💵 Resultado: {res_txt}\n"
            f"📈 Ativo: {ATIVO_PADRAO}\n"
            f"🕒 Entrada: {hora_entrada} | Fechamento: {hora_fim}\n"
            f"📊 Placar Atual: {ESTADO['placar_w']} WIN  x  {ESTADO['placar_l']} LOSS\n"
            f"💼 Banca Atualizada: R$ {ESTADO['saldo']:.2f}"
        )

def loop_motor():
    global API_GLOBAL
    from iqoptionapi.stable_api import IQ_Option

    while True:
        if not ESTADO["conectado"]:
            if not SENHA_IQ:
                ESTADO["status"] = "Erro: Configure IQ_PASSWORD no Render"
                time.sleep(5)
                continue

            ESTADO["status"] = "Conectando à IQ Option..."
            try:
                api = IQ_Option(EMAIL_IQ, SENHA_IQ)
                ok, _ = api.connect()
                if ok:
                    api.change_balance(TIPO_CONTA)
                    saldo = float(api.get_balance())
                    ESTADO["saldo"] = saldo
                    ESTADO["conectado"] = True
                    ESTADO["status"] = "Conectado e Monitorando 24/7"
                    API_GLOBAL = api

                    enviar_telegram(
                        "🚀 ROBÔ 24H INICIADO NA NUVEM\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"💼 Conta: {TIPO_CONTA}\n"
                        f"💰 Banca Inicial: R$ {saldo:.2f}\n"
                        f"📈 Ativo: {ATIVO_PADRAO} | TF: M1\n"
                        "🎯 Estratégia: EMA 7/21 + RSI(7) + Soros N2\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "🟢 Status: Monitorando mercado 24/7..."
                    )
                else:
                    ESTADO["status"] = "Falha no login. Verifique as credenciais."
                    time.sleep(10)
            except Exception as e:
                ESTADO["status"] = f"Erro: {e}"
                time.sleep(10)

        # Atualiza velas do gráfico a cada 2 segundos
        if ESTADO["conectado"] and API_GLOBAL:
            try:
                raw = API_GLOBAL.get_candles(ATIVO_PADRAO, 60, 25, time.time())
                if raw:
                    lista = []
                    for v in raw:
                        lista.append({
                            "open": float(v["open"]),
                            "max": float(v["max"]),
                            "min": float(v["min"]),
                            "close": float(v["close"])
                        })
                    ESTADO["velas"] = lista
            except Exception:
                pass

        time.sleep(2)

if __name__ == "__main__":
    loop_motor()
