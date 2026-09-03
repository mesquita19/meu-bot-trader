import os
import sys
import threading
import time
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import pandas as pd
import numpy as np
import requests

# ================= ESTADO GLOBAL COMPARTILHADO =================
ESTADO = {
    "status": "Iniciando...",
    "robo_ativo": True,
    "email": os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip(),
    "tipo_conta": os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper(),
    "saldo_atual": 0.0,
    "saldo_inicial": 0.0,
    "lucro_dia": 0.0,
    "placar_w": 0,
    "placar_l": 0,
    "soros_estagio": 1,
    "ativo": "EURUSD-OTC",
    "preco_atual": 0.0,
    "score": 0.0,
    "tendencia": "NEUTRO",
    "adx": 0.0,
    "historico": []
}

API_GLOBAL = None
LOCK_API = threading.Lock()

# ================= SERVIDOR WEB RESPONSIVO =================
class MobileTerminalHandler(BaseHTTPRequestHandler):
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

            velas_limpas = []
            if API_GLOBAL:
                try:
                    raw = API_GLOBAL.get_candles(par, 60, 60, time.time())
                    if raw:
                        df = pd.DataFrame(raw).drop_duplicates(subset=['from']).sort_values('from')
                        for _, v in df.iterrows():
                            velas_limpas.append({
                                "time": int(v["from"]),
                                "open": float(v["open"]),
                                "high": float(v["max"]),
                                "low": float(v["min"]),
                                "close": float(v["close"])
                            })
                        if velas_limpas:
                            ESTADO["preco_atual"] = velas_limpas[-1]["close"]
                except Exception as e:
                    print(f"Erro ao buscar velas: {e}", flush=True)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(velas_limpas).encode('utf-8'))
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
            <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
            <style>
                body { background-color: #080c14; color: #cbd5e1; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
                .card { background: #0f172a; border: 1px solid #1e293b; }
            </style>
        </head>
        <body class="flex flex-col min-h-screen p-2 sm:p-4 space-y-3">
            <!-- Header Superior -->
            <header class="card p-3 rounded-xl flex items-center justify-between">
                <div class="flex items-center space-x-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span class="font-black text-sm text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">APEX PRO</span>
                    <select id="par-select" onchange="mudarAtivo()" class="bg-slate-900 border border-slate-700 text-xs font-bold rounded px-2 py-1 text-white">
                        <option value="EURUSD-OTC">EUR/USD (OTC)</option>
                        <option value="GBPUSD-OTC">GBP/USD (OTC)</option>
                        <option value="USDJPY-OTC">USD/JPY (OTC)</option>
                        <option value="EURUSD">EUR/USD</option>
                        <option value="BTCUSD">BTC/USD</option>
                    </select>
                </div>
                <div class="text-right font-mono">
                    <div class="text-[10px] text-slate-400" id="tipo-conta">PRACTICE</div>
                    <div class="text-sm font-bold text-white" id="val-saldo">R$ 0,00</div>
                </div>
            </header>

            <!-- Preço e Métricas Rápidas -->
            <div class="grid grid-cols-3 gap-2 text-center text-xs font-mono">
                <div class="card p-2 rounded-lg">
                    <div class="text-[10px] text-slate-400">PREÇO ATUAL</div>
                    <div class="font-bold text-cyan-400 mt-0.5" id="val-preco">---</div>
                </div>
                <div class="card p-2 rounded-lg">
                    <div class="text-[10px] text-slate-400">CONFLUÊNCIA</div>
                    <div class="font-bold text-amber-400 mt-0.5" id="val-score">0.0%</div>
                </div>
                <div class="card p-2 rounded-lg">
                    <div class="text-[10px] text-slate-400">LUCRO DO DIA</div>
                    <div class="font-bold text-emerald-400 mt-0.5" id="val-lucro">R$ 0,00</div>
                </div>
            </div>

            <!-- Gráfico de Velas Japonesas -->
            <div class="card rounded-xl p-1 relative flex-1 flex flex-col" style="min-height: 280px; height: 42vh;">
                <div id="chart-area" class="w-full h-full"></div>
            </div>

            <!-- Controles Manuais e Botões Grandes de Ação -->
            <div class="card p-3 rounded-xl space-y-3">
                <div class="flex items-center justify-between gap-2 text-xs font-mono">
                    <div class="flex-1">
                        <label class="text-[10px] text-slate-400 block mb-1">VALOR (R$)</label>
                        <input type="number" id="input-valor" value="20" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-bold outline-none text-center">
                    </div>
                    <div class="flex-1">
                        <label class="text-[10px] text-slate-400 block mb-1">EXPIRAÇÃO</label>
                        <select id="input-exp" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-bold outline-none text-center">
                            <option value="1">1 Minuto</option>
                            <option value="5">5 Minutos</option>
                        </select>
                    </div>
                    <div class="flex-1">
                        <label class="text-[10px] text-slate-400 block mb-1">ROBÔ AUTO</label>
                        <button id="btn-auto" onclick="toggleRobo()" class="w-full bg-emerald-500 text-black font-black p-2 rounded-lg text-xs">LIGADO</button>
                    </div>
                </div>

                <!-- Botões de Compra e Venda -->
                <div class="grid grid-cols-2 gap-3 pt-1">
                    <button onclick="dispararOrdem('CALL')" class="h-14 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-black text-sm flex items-center justify-center space-x-2 transition-all shadow-lg shadow-emerald-900/30">
                        <span>▲</span>
                        <span>COMPRA (CALL)</span>
                    </button>
                    <button onclick="dispararOrdem('PUT')" class="h-14 rounded-xl bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-black text-sm flex items-center justify-center space-x-2 transition-all shadow-lg shadow-rose-900/30">
                        <span>▼</span>
                        <span>VENDA (PUT)</span>
                    </button>
                </div>
            </div>

            <!-- Histórico Recente -->
            <div class="card p-3 rounded-xl space-y-2">
                <div class="flex justify-between items-center text-xs border-b border-slate-800 pb-1">
                    <span class="font-bold text-slate-300">ÚLTIMAS EXECUÇÕES</span>
                    <span class="font-mono text-slate-400" id="val-placar">0W - 0L</span>
                </div>
                <div id="historico-container" class="space-y-1 text-xs font-mono max-h-24 overflow-y-auto">
                    <div class="text-slate-500 text-center py-2">Nenhuma operação disparada ainda.</div>
                </div>
            </div>

            <script>
                const container = document.getElementById('chart-area');
                const chart = LightweightCharts.createChart(container, {
                    layout: { background: { color: '#0f172a' }, textColor: '#64748b' },
                    grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
                    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                    timeScale: { timeVisible: true, secondsVisible: true, borderColor: '#1e293b' },
                    rightPriceScale: { borderColor: '#1e293b' }
                });

                const candles = chart.addCandlestickSeries({
                    upColor: '#10b981', downColor: '#f43f5e',
                    borderUpColor: '#10b981', borderDownColor: '#f43f5e',
                    wickUpColor: '#10b981', wickDownColor: '#f43f5e'
                });

                function ajustarGrafico() {
                    chart.resize(container.clientWidth, container.clientHeight);
                }
                window.addEventListener('resize', ajustarGrafico);
                setTimeout(ajustarGrafico, 300);

                async function puxarVelas() {
                    try {
                        const par = document.getElementById('par-select').value;
                        const res = await fetch('/api/velas?par=' + par);
                        const dados = await res.json();
                        if (dados && dados.length > 0) {
                            candles.setData(dados);
                            const ult = dados[dados.length - 1];
                            document.getElementById('val-preco').innerText = ult.close.toFixed(5);
                        }
                    } catch (e) {
                        console.error("Erro nas velas:", e);
                    }
                }

                async function puxarDados() {
                    try {
                        const res = await fetch('/api/dados');
                        const data = await res.json();
                        document.getElementById('val-saldo').innerText = 'R$ ' + data.saldo_atual.toFixed(2);
                        document.getElementById('tipo-conta').innerText = data.tipo_conta;
                        document.getElementById('val-score').innerText = data.score.toFixed(1) + '%';
                        document.getElementById('val-placar').innerText = `${data.placar_w}W - ${data.placar_l}L`;

                        const lucroEl = document.getElementById('val-lucro');
                        lucroEl.innerText = (data.lucro_dia >= 0 ? '+R$ ' : '-R$ ') + Math.abs(data.lucro_dia).toFixed(2);
                        lucroEl.className = 'font-bold mt-0.5 ' + (data.lucro_dia >= 0 ? 'text-emerald-400' : 'text-rose-400');

                        if (data.historico.length > 0) {
                            document.getElementById('historico-container').innerHTML = data.historico.map(h => `
                                <div class="flex justify-between p-1 bg-slate-900 rounded">
                                    <span>${h.hora} ${h.par}</span>
                                    <span class="${h.direcao === 'CALL' ? 'text-emerald-400' : 'text-rose-400'} font-bold">${h.direcao}</span>
                                    <span class="${h.resultado === 'WIN' ? 'text-emerald-400' : 'text-rose-400'} font-bold">${h.resultado}</span>
                                </div>
                            `).join('');
                        }
                    } catch (e) {}
                }

                function mudarAtivo() {
                    puxarVelas();
                }

                async function toggleRobo() {
                    const btn = document.getElementById('btn-auto');
                    const resp = await fetch('/api/toggle', { method: 'POST' });
                    const res = await resp.json();
                    if (res.ativo) {
                        btn.innerText = 'LIGADO';
                        btn.className = 'w-full bg-emerald-500 text-black font-black p-2 rounded-lg text-xs';
                    } else {
                        btn.innerText = 'PAUSADO';
                        btn.className = 'w-full bg-amber-500 text-black font-black p-2 rounded-lg text-xs';
                    }
                }

                async function dispararOrdem(direcao) {
                    const par = document.getElementById('par-select').value;
                    const valor = parseFloat(document.getElementById('input-valor').value);
                    const exp = parseInt(document.getElementById('input-exp').value);
                    await fetch('/api/executar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ par, direcao, valor, exp })
                    });
                }

                setInterval(puxarVelas, 2000);
                setInterval(puxarDados, 3000);
                puxarVelas();
                puxarDados();
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        dados = self.rfile.read(content_length).decode('utf-8')

        if self.path == '/api/toggle':
            ESTADO["robo_ativo"] = not ESTADO["robo_ativo"]
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ativo": ESTADO["robo_ativo"]}).encode('utf-8'))
            return

        if self.path == '/api/executar':
            corpo = json.loads(dados)
            threading.Thread(target=enviar_ordem, args=(corpo.get("par"), corpo.get("direcao"), float(corpo.get("valor", 20)), int(corpo.get("exp", 1))), daemon=True).start()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "enviado"}).encode('utf-8'))
            return

    def log_message(self, format, *args):
        return

def iniciar_servidor():
    porta = int(os.environ.get("PORT", 10000))
    httpd = HTTPServer(('0.0.0.0', porta), MobileTerminalHandler)
    httpd.serve_forever()

threading.Thread(target=iniciar_servidor, daemon=True).start()

# ================= EXECUÇÃO E MOTOR =================
TG_TOKEN = os.environ.get("TG_TOKEN", "8601904952:AAHPJhTPKnE2UOoTrtm228cHCyFv8wNHxY8").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "999294230").strip()

def notificar_telegram(texto):
    if TG_TOKEN and TG_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": texto, "parse_mode": "Markdown"}, timeout=5)
        except Exception:
            pass

def enviar_ordem(par, direcao, valor, exp):
    global API_GLOBAL
    if not API_GLOBAL:
        return

    hora = datetime.now().strftime("%H:%M:%S")
    notificar_telegram(f"⚡ *ORDEM EXECUTADA*\nPar: `{par}` | Dir: `{direcao}` | Valor: `R$ {valor:.2f}`")

    id_ordem = None
    try:
        _, id_dig = API_GLOBAL.buy_digital_spot(par, valor, direcao.lower(), exp)
        if id_dig and id_dig != "error":
            id_ordem = id_dig
    except Exception:
        pass

    if not id_ordem:
        try:
            status, id_bin = API_GLOBAL.buy(valor, par, direcao.lower(), exp)
            if status and id_bin:
                id_ordem = id_bin
        except Exception:
            pass

    if id_ordem:
        time.sleep(exp * 60 + 2)
        resultado = "LOSS"
        try:
            check, lucro = API_GLOBAL.check_win_digital_v2(id_ordem)
            if check and lucro > 0:
                resultado = "WIN"
        except Exception:
            pass

        if resultado == "WIN":
            ESTADO["placar_w"] += 1
        else:
            ESTADO["placar_l"] += 1

        try:
            saldo = float(API_GLOBAL.get_balance())
            ESTADO["saldo_atual"] = saldo
            ESTADO["lucro_dia"] = saldo - ESTADO["saldo_inicial"]
        except Exception:
            pass

        ESTADO["historico"].insert(0, {"hora": hora, "par": par, "direcao": direcao, "resultado": resultado})
        notificar_telegram(f"🏁 *RESULTADO: {resultado}*\nAtivo: `{par}` | Saldo: `R$ {ESTADO['saldo_atual']:.2f}`")

def loop_motor():
    global API_GLOBAL
    from iqoptionapi.stable_api import IQ_Option

    email = os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip()
    senha = os.environ.get("IQ_PASSWORD", "").strip()
    tipo = os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper()

    while True:
        if not API_GLOBAL:
            print(f"Tentando autenticar como {email}...", flush=True)
            api = IQ_Option(email, senha)
            ok, _ = api.connect()
            if ok:
                api.change_balance(tipo)
                saldo = float(api.get_balance())
                ESTADO["saldo_inicial"] = saldo
                ESTADO["saldo_atual"] = saldo
                ESTADO["tipo_conta"] = tipo
                API_GLOBAL = api
                notificar_telegram(f"🤖 *TERMINAL ONLINE*\nConta: `{tipo}` | Saldo: `R$ {saldo:.2f}`")
            else:
                time.sleep(15)
                continue

        time.sleep(1)
        seg = int(time.time()) % 60

        # Disparo no segundo 00 da vela se confluência alta
        if seg == 0 and ESTADO["robo_ativo"]:
            try:
                par = ESTADO["ativo"]
                velas = API_GLOBAL.get_candles(par, 60, 20, time.time())
                if velas and len(velas) >= 15:
                    df = pd.DataFrame(velas)
                    corpo = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
                    pavio_inferior = min(df['close'].iloc[-1], df['open'].iloc[-1]) - df['min'].iloc[-1]
                    
                    if pavio_inferior > corpo * 1.6:
                        ESTADO["score"] = 88.0
                        threading.Thread(target=enviar_ordem, args=(par, "CALL", 20.0, 1), daemon=True).start()
            except Exception:
                pass

if __name__ == "__main__":
    loop_motor()
