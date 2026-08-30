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

# ================= ESTADO GLOBAL DO TERMINAL =================
ESTADO_TERMINAL = {
    "status": "Iniciando...",
    "robo_ativo": True,
    "email": os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip(),
    "tipo_conta": os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper(),
    "saldo_inicial": 0.0,
    "saldo_atual": 0.0,
    "lucro_dia": 0.0,
    "placar_w": 0,
    "placar_l": 0,
    "soros_estagio": 1,
    "ativo_selecionado": "EURUSD-OTC",
    "ativos_disponiveis": ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "BTCUSD", "ETHUSD", "EURUSD"],
    "score_atual": 0.0,
    "velas_grafico": [],
    "historico_operacoes": [],
    "indicadores": {"ema200": 0.0, "adx": 0.0, "stoch": 50.0, "tendencia": "NEUTRO"}
}

API_IQ_GLOBAL = None
LOCK_OPERACIONAL = threading.Lock()

# ================= SERVIDOR HTTP & API REST =================
class ProfessionalTerminalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/terminal-data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(ESTADO_TERMINAL).encode('utf-8'))
            return

        if self.path.startswith('/api/candles'):
            # Formato: /api/candles?par=EURUSD-OTC
            par = ESTADO_TERMINAL["ativo_selecionado"]
            if 'par=' in self.path:
                par = self.path.split('par=')[1].split('&')[0]
                ESTADO_TERMINAL["ativo_selecionado"] = par
            
            velas_formatadas = []
            if API_IQ_GLOBAL:
                try:
                    velas = API_IQ_GLOBAL.get_candles(par, 60, 60, time.time())
                    if velas:
                        for v in velas:
                            velas_formatadas.append({
                                "time": v["from"],
                                "open": float(v["open"]),
                                "high": float(v["max"]),
                                "low": float(v["min"]),
                                "close": float(v["close"]),
                                "volume": float(v.get("volume", 0))
                            })
                        ESTADO_TERMINAL["velas_grafico"] = velas_formatadas
                except Exception:
                    pass

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(velas_formatadas).encode('utf-8'))
            return

        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()

        html = """
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Apex Quant Terminal Pro | Live Candlesticks</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
            <style>
                body { background: #07090e; color: #cbd5e1; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
                .glass-panel { background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); }
                .glow-call { box-shadow: 0 0 20px rgba(16, 185, 129, 0.4); }
                .glow-put { box-shadow: 0 0 20px rgba(244, 63, 94, 0.4); }
            </style>
        </head>
        <body class="h-screen flex flex-col overflow-hidden">
            <!-- Top Navigation Bar -->
            <header class="h-14 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between px-4 z-20">
                <div class="flex items-center gap-4">
                    <div class="flex items-center gap-2">
                        <div class="w-3 h-3 rounded-full bg-emerald-500 animate-ping"></div>
                        <span class="font-black text-lg text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">APEX PRO MATRIX</span>
                    </div>
                    <div class="h-5 w-px bg-slate-800"></div>
                    <select id="select-par" onchange="trocarPar()" class="bg-slate-900 border border-slate-700 text-white font-bold rounded-lg px-3 py-1.5 text-xs focus:ring-2 focus:ring-cyan-500 outline-none">
                        <option value="EURUSD-OTC">EUR/USD (OTC)</option>
                        <option value="GBPUSD-OTC">GBP/USD (OTC)</option>
                        <option value="USDJPY-OTC">USD/JPY (OTC)</option>
                        <option value="BTCUSD">BTC/USD (Cripto)</option>
                        <option value="EURUSD">EUR/USD (Forex)</option>
                    </select>
                </div>

                <div class="flex items-center gap-6">
                    <div class="hidden md:flex items-center gap-4 text-xs font-mono">
                        <div><span class="text-slate-500">TENDÊNCIA 1H:</span> <span id="val-tendencia" class="text-emerald-400 font-bold">ALTA</span></div>
                        <div><span class="text-slate-500">ADX 15M:</span> <span id="val-adx" class="text-cyan-400 font-bold">28.4</span></div>
                        <div><span class="text-slate-500">CONFLUÊNCIA:</span> <span id="val-score" class="text-amber-400 font-bold">88.5%</span></div>
                    </div>
                    <div class="h-5 w-px bg-slate-800 hidden md:block"></div>
                    <div class="text-right">
                        <span class="text-[10px] text-slate-500 font-mono tracking-wider block uppercase" id="badge-tipo-conta">PRACTICE ACCOUNT</span>
                        <span class="text-lg font-black text-white font-mono" id="txt-saldo">R$ 0,00</span>
                    </div>
                </div>
            </header>

            <!-- Main Workspace -->
            <div class="flex-1 flex overflow-hidden">
                <!-- Left: Interactive Candlestick Chart -->
                <div class="flex-1 flex flex-col relative bg-[#07090e]">
                    <!-- Chart Tools Overlay -->
                    <div class="absolute top-3 left-3 z-10 flex gap-2">
                        <span class="px-2 py-1 bg-slate-900/90 border border-slate-700 rounded text-[11px] font-mono text-cyan-400">1M (Micro)</span>
                        <span class="px-2 py-1 bg-slate-900/90 border border-slate-700 rounded text-[11px] font-mono text-slate-300" id="live-price">Preço: ---</span>
                    </div>
                    
                    <!-- Candlestick Canvas Container -->
                    <div id="chart-container" class="flex-1 w-full h-full"></div>

                    <!-- Bottom Live Order History -->
                    <div class="h-44 border-t border-slate-800 bg-slate-950/70 p-3 overflow-y-auto">
                        <div class="flex justify-between items-center mb-2">
                            <span class="text-xs font-bold uppercase tracking-wider text-slate-400">Ordens Executadas em Tempo Real</span>
                            <span class="text-xs font-mono text-slate-400" id="txt-placar">Placar: 0W x 0L</span>
                        </div>
                        <table class="w-full text-left text-xs font-mono">
                            <thead class="text-slate-600 border-b border-slate-800/80 pb-1">
                                <tr>
                                    <th>HORA</th>
                                    <th>PAR</th>
                                    <th>TIPO</th>
                                    <th>SCORE</th>
                                    <th>VALOR</th>
                                    <th>RESULTADO</th>
                                </tr>
                            </thead>
                            <tbody id="lista-operacoes" class="divide-y divide-slate-900/60">
                                <tr>
                                    <td colspan="6" class="py-3 text-center text-slate-600">Nenhuma ordem disparada no ciclo atual.</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Right: Trading Console & Automation Controls -->
                <div class="w-80 border-l border-slate-800 bg-slate-950/90 p-4 flex flex-col justify-between overflow-y-auto z-10">
                    <div class="space-y-4">
                        <!-- Switch Automação -->
                        <div class="glass-panel p-3 rounded-xl flex items-center justify-between">
                            <div>
                                <div class="text-xs font-bold text-white">AUTOMAÇÃO NEURAL</div>
                                <div class="text-[10px] text-slate-400">Varredura Institucional 24/7</div>
                            </div>
                            <button id="btn-toggle-robo" onclick="toggleRobo()" class="px-3 py-1 bg-emerald-500 hover:bg-emerald-600 text-black text-xs font-black rounded-lg transition-all">LIGADO</button>
                        </div>

                        <!-- Painel Manual de Execução Instantânea -->
                        <div class="glass-panel p-4 rounded-xl space-y-3">
                            <div class="text-xs font-bold tracking-wider text-slate-300 uppercase">Execução Manual Imediata</div>
                            
                            <div>
                                <label class="text-[10px] text-slate-400 uppercase font-semibold">Valor da Entrada (R$)</label>
                                <input type="number" id="input-valor" value="20" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-white font-mono mt-1 focus:ring-2 focus:ring-cyan-500 outline-none">
                            </div>

                            <div>
                                <label class="text-[10px] text-slate-400 uppercase font-semibold">Expiração</label>
                                <select id="input-exp" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-xs text-white font-mono mt-1 outline-none">
                                    <option value="1">1 Minuto (M1 Turbo)</option>
                                    <option value="5">5 Minutos (M5)</option>
                                </select>
                            </div>

                            <!-- Botões de Compra e Venda Clicáveis -->
                            <div class="grid grid-cols-2 gap-3 pt-2">
                                <button onclick="executarOrdemManual('CALL')" class="h-16 rounded-xl bg-gradient-to-t from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white font-black text-sm flex flex-col items-center justify-center gap-1 glow-call transition-transform active:scale-95">
                                    <i class="fa-solid fa-arrow-trend-up text-lg"></i>
                                    <span>COMPRA (CALL)</span>
                                </button>
                                <button onclick="executarOrdemManual('PUT')" class="h-16 rounded-xl bg-gradient-to-t from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white font-black text-sm flex flex-col items-center justify-center gap-1 glow-put transition-transform active:scale-95">
                                    <i class="fa-solid fa-arrow-trend-down text-lg"></i>
                                    <span>VENDA (PUT)</span>
                                </button>
                            </div>
                        </div>

                        <!-- Card de Gestão e Lucro -->
                        <div class="glass-panel p-3 rounded-xl space-y-2 text-xs">
                            <div class="flex justify-between">
                                <span class="text-slate-400">Lucro do Dia:</span>
                                <span id="txt-lucro" class="font-bold text-emerald-400 font-mono">+R$ 0,00</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-slate-400">Soros Nível:</span>
                                <span id="txt-soros" class="font-bold text-cyan-400 font-mono">Mão 1 (R$ 20.00)</span>
                            </div>
                        </div>
                    </div>

                    <div class="text-center pt-4 border-t border-slate-900 text-[10px] text-slate-600">
                        Apex Quant Engine v3.0 • Host Conectado
                    </div>
                </div>
            </div>

            <!-- JavaScript do Gráfico Interativo e Sincronização -->
            <script>
                // 1. Inicializa o gráfico de velas profissionais estilo TradingView
                const chartContainer = document.getElementById('chart-container');
                const chart = LightweightCharts.createChart(chartContainer, {
                    layout: { background: { color: '#07090e' }, textColor: '#94a3b8' },
                    grid: { vertLines: { color: '#0f172a' }, horzLines: { color: '#0f172a' } },
                    timeScale: { timeVisible: true, secondsVisible: true, borderColor: '#1e293b' },
                    rightPriceScale: { borderColor: '#1e293b' }
                });

                const candleSeries = chart.addCandlestickSeries({
                    upColor: '#10b981', downColor: '#f43f5e', borderUpColor: '#10b981',
                    borderDownColor: '#f43f5e', wickUpColor: '#10b981', wickDownColor: '#f43f5e'
                });

                window.addEventListener('resize', () => {
                    chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
                });

                async function sincronizarVelas() {
                    try {
                        const par = document.getElementById('select-par').value;
                        const res = await fetch('/api/candles?par=' + par);
                        const dadosVelas = await res.json();
                        if (dadosVelas && dadosVelas.length > 0) {
                            candleSeries.setData(dadosVelas);
                            const ultima = dadosVelas[dadosVelas.length - 1];
                            document.getElementById('live-price').innerText = 'Preço: ' + ultima.close.toFixed(5);
                        }
                    } catch (e) {
                        console.error("Erro ao carregar velas:", e);
                    }
                }

                async function atualizarDadosGerais() {
                    try {
                        const res = await fetch('/api/terminal-data');
                        const data = await res.json();

                        document.getElementById('txt-saldo').innerText = 'R$ ' + data.saldo_atual.toFixed(2);
                        document.getElementById('badge-tipo-conta').innerText = data.tipo_conta + ' ACCOUNT';
                        
                        const lucroEl = document.getElementById('txt-lucro');
                        lucroEl.innerText = (data.lucro_dia >= 0 ? '+R$ ' : '-R$ ') + Math.abs(data.lucro_dia).toFixed(2);
                        lucroEl.className = 'font-bold font-mono ' + (data.lucro_dia >= 0 ? 'text-emerald-400' : 'text-rose-400');

                        document.getElementById('txt-placar').innerText = `Placar: ${data.placar_w}W x ${data.placar_l}L`;
                        document.getElementById('val-tendencia').innerText = data.indicadores.tendencia;
                        document.getElementById('val-adx').innerText = data.indicadores.adx.toFixed(1);
                        document.getElementById('val-score').innerText = data.score_atual.toFixed(1) + '%';
                        document.getElementById('txt-soros').innerText = `Nível ${data.soros_estagio}`;

                        if (data.historico_operacoes && data.historico_operacoes.length > 0) {
                            const tbody = document.getElementById('lista-operacoes');
                            tbody.innerHTML = data.historico_operacoes.map(op => `
                                <tr>
                                    <td class="py-1 text-slate-500">${op.hora}</td>
                                    <td class="font-bold text-white">${op.par}</td>
                                    <td><span class="font-bold ${op.direcao === 'CALL' ? 'text-emerald-400' : 'text-rose-400'}">${op.direcao}</span></td>
                                    <td class="text-cyan-400">${op.score}%</td>
                                    <td>R$ ${op.valor.toFixed(2)}</td>
                                    <td class="font-bold ${op.resultado === 'WIN' ? 'text-emerald-400' : 'text-rose-400'}">${op.resultado}</td>
                                </tr>
                            `).join('');
                        }
                    } catch (e) {
                        console.error("Erro ao sincronizar terminal:", e);
                    }
                }

                async function executarOrdemManual(direcao) {
                    const par = document.getElementById('select-par').value;
                    const valor = parseFloat(document.getElementById('input-valor').value);
                    const exp = parseInt(document.getElementById('input-exp').value);

                    try {
                        const res = await fetch('/api/ordem-manual', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ par, direcao, valor, exp })
                        });
                        const resultado = await res.json();
                        alert(`Ordem de ${direcao} enviada para ${par} com sucesso!`);
                    } catch (e) {
                        alert("Ordem enviada ao processador.");
                    }
                }

                function trocarPar() {
                    sincronizarVelas();
                }

                function toggleRobo() {
                    const btn = document.getElementById('btn-toggle-robo');
                    if (btn.innerText === 'LIGADO') {
                        btn.innerText = 'PAUSADO';
                        btn.className = 'px-3 py-1 bg-amber-500 hover:bg-amber-600 text-black text-xs font-black rounded-lg transition-all';
                    } else {
                        btn.innerText = 'LIGADO';
                        btn.className = 'px-3 py-1 bg-emerald-500 hover:bg-emerald-600 text-black text-xs font-black rounded-lg transition-all';
                    }
                    fetch('/api/toggle-robo', { method: 'POST' });
                }

                // Sincronizações periódicas
                setInterval(sincronizarVelas, 2500);
                setInterval(atualizarDadosGerais, 3000);
                sincronizarVelas();
                atualizarDadosGerais();
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')

        if self.path == '/api/toggle-robo':
            ESTADO_TERMINAL["robo_ativo"] = not ESTADO_TERMINAL["robo_ativo"]
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "robo_ativo": ESTADO_TERMINAL["robo_ativo"]}).encode('utf-8'))
            return

        if self.path == '/api/ordem-manual':
            try:
                params = json.loads(post_data)
                par = params.get("par", "EURUSD-OTC")
                direcao = params.get("direcao", "CALL")
                valor = float(params.get("valor", 20))
                exp = int(params.get("exp", 1))

                threading.Thread(target=despachar_ordem_iq, args=(par, direcao, valor, exp, 99.0, "MANUAL"), daemon=True).start()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ordem_enviada"}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
            return

    def log_message(self, format, *args):
        return

def iniciar_servidor_http():
    porta = int(os.environ.get("PORT", 10000))
    servidor = HTTPServer(('0.0.0.0', porta), ProfessionalTerminalHandler)
    print(f"🌐 [TERMINAL PRO] Dashboard Visual ativo na porta {porta}!", flush=True)
    servidor.serve_forever()

threading.Thread(target=iniciar_servidor_http, daemon=True).start()
# ===============================================================

# ================= CONFIGURAÇÕES & DISPARADOR =================
TG_TOKEN = os.environ.get("TG_TOKEN", "8601904952:AAHPJhTPKnE2UOoTrtm228cHCyFv8wNHxY8").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "999294230").strip()

EMAIL_IQ = os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip()
SENHA_IQ = os.environ.get("IQ_PASSWORD", "").strip()
TIPO_CONTA = os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper()

SCORE_MINIMO_EXECUCAO = 85.0
ENTRADA_BASE = 20.0

def send_telegram(msg):
    if not TG_TOKEN or not TG_CHAT_ID: return
    def _post():
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=8)
        except Exception: pass
    threading.Thread(target=_post, daemon=True).start()

def despachar_ordem_iq(par, direcao, valor, exp, score, origem="AUTO"):
    global API_IQ_GLOBAL
    if not API_IQ_GLOBAL: return

    hora = datetime.now().strftime("%H:%M:%S")
    send_telegram(
        f"⚡ *ORDEM EXECUTADA ({origem})*\n"
        f"📊 *Par:* `{par}` | *Direção:* `{'🟢 CALL' if direcao=='CALL' else '🔴 PUT'}`\n"
        f"💰 *Valor:* `R$ {valor:.2f}` | *Exp:* `{exp}M`"
    )

    id_ordem, tipo_exec = None, "DIGITAL"
    try:
        _, id_dig = API_IQ_GLOBAL.buy_digital_spot(par, valor, direcao.lower(), exp)
        if id_dig and id_dig != "error": id_ordem = id_dig
    except Exception: pass

    if not id_ordem:
        try:
            status, id_bin = API_IQ_GLOBAL.buy(valor, par, direcao.lower(), exp)
            if status and id_bin: id_ordem, tipo_exec = id_bin, "BINARY"
        except Exception: pass

    if id_ordem:
        time.sleep(exp * 60 + 3)
        lucro_real, resultado = 0.0, "LOSS"
        try:
            if tipo_exec == "DIGITAL":
                check, lucro = API_IQ_GLOBAL.check_win_digital_v2(id_ordem)
                resultado = "WIN" if (check and lucro > 0) else "LOSS"
                lucro_real = float(lucro)
            else:
                status, lucro = API_IQ_GLOBAL.check_win_v4(id_ordem)
                resultado = "WIN" if (status and lucro > 0) else "LOSS"
                lucro_real = float(lucro)
        except Exception: pass

        if resultado == "WIN":
            ESTADO_TERMINAL["placar_w"] += 1
        else:
            ESTADO_TERMINAL["placar_l"] += 1

        try:
            saldo = float(API_IQ_GLOBAL.get_balance())
            ESTADO_TERMINAL["saldo_atual"] = saldo
            ESTADO_TERMINAL["lucro_dia"] = saldo - ESTADO_TERMINAL["saldo_inicial"]
        except Exception: pass

        ESTADO_TERMINAL["historico_operacoes"].insert(0, {
            "hora": hora, "par": par, "direcao": direcao, "score": score, "valor": valor, "resultado": resultado
        })
        if len(ESTADO_TERMINAL["historico_operacoes"]) > 15:
            ESTADO_TERMINAL["historico_operacoes"].pop()

        send_telegram(
            f"📋 *DESFECHO DA ORDEM*\n"
            f"🏁 *Resultado:* `{'✅ WIN' if resultado=='WIN' else '❌ LOSS'}`\n"
            f"💼 *Saldo:* `R$ {ESTADO_TERMINAL['saldo_atual']:.2f}`"
        )

class ApexEngineWorker:
    def conectar(self):
        global API_IQ_GLOBAL
        from iqoptionapi.stable_api import IQ_Option
        print(f"⚡ [APEX ENGINE] Conectando como {EMAIL_IQ}...", flush=True)
        api = IQ_Option(EMAIL_IQ, SENHA_IQ)
        check, reason = api.connect()

        if check:
            api.change_balance(TIPO_CONTA)
            saldo = float(api.get_balance())
            ESTADO_TERMINAL["saldo_inicial"] = saldo
            ESTADO_TERMINAL["saldo_atual"] = saldo
            ESTADO_TERMINAL["tipo_conta"] = TIPO_CONTA
            API_IQ_GLOBAL = api
            send_telegram(f"🏛️ *TERMINAL PRO CONECTADO*\n💼 *Conta:* `{TIPO_CONTA}` | *Saldo:* `R$ {saldo:.2f}`")
            return True
        return False

    def loop(self):
        while True:
            if not API_IQ_GLOBAL:
                if not self.conectar():
                    time.sleep(15)
                    continue

            time.sleep(1)
            segundo = int(time.time()) % 60

            # Varredura no segundo 00
            if segundo in [0, 1] and ESTADO_TERMINAL["robo_ativo"]:
                try:
                    par = ESTADO_TERMINAL["ativo_selecionado"]
                    velas_1h = API_IQ_GLOBAL.get_candles(par, 3600, 30, time.time())
                    if velas_1h:
                        df_1h = pd.DataFrame(velas_1h)
                        ema200 = df_1h['close'].ewm(span=30, adjust=False).mean().iloc[-1]
                        tend = "ALTA" if df_1h['close'].iloc[-1] > ema200 else "BAIXA"
                        ESTADO_TERMINAL["indicadores"]["tendencia"] = tend

                    velas_1m = API_IQ_GLOBAL.get_candles(par, 60, 30, time.time())
                    if velas_1m and len(velas_1m) >= 20:
                        df_1m = pd.DataFrame(velas_1m)
                        corpo = abs(df_1m['close'].iloc[-1] - df_1m['open'].iloc[-1])
                        pavio_inf = min(df_1m['close'].iloc[-1], df_1m['open'].iloc[-1]) - df_1m['min'].iloc[-1]
                        
                        score = 75.0
                        if tend == "ALTA" and pavio_inf > corpo:
                            score = 90.0
                            ESTADO_TERMINAL["score_atual"] = score
                            despachar_ordem_iq(par, "CALL", ENTRADA_BASE, 1, score, "AUTO")
                except Exception:
                    pass

if __name__ == "__main__":
    worker = ApexEngineWorker()
    worker.loop()
