import os
import sys
import threading
import time
import json
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import pandas as pd
import numpy as np
import requests

# ================= ESTADO CENTRALIZADO =================
ESTADO = {
    "status": "Iniciando sistema...",
    "conectado": False,
    "robo_ativo": True,
    "email": os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip(),
    "tipo_conta": os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper(),
    "saldo_atual": 0.0,
    "saldo_inicial": 0.0,
    "lucro_dia": 0.0,
    "placar_w": 0,
    "placar_l": 0,
    "soros_nivel": 1,
    "soros_lucro": 0.0,
    "ativo": "EURUSD-OTC",
    "preco_pip": "0.00000",
    "score": 0.0,
    "tendencia": "AGUARDANDO",
    "adx": 0.0,
    "historico": []
}

API_GLOBAL = None
LOCK_ORDEM = threading.Lock()

# ================= TELEGRAM =================
TG_TOKEN = os.environ.get("TG_TOKEN", "8601904952:AAHPJhTPKnE2UOoTrtm228cHCyFv8wNHxY8").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "999294230").strip()

def notificar_tg(msg):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    def _envio():
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except Exception:
            pass
    threading.Thread(target=_envio, daemon=True).start()

# ================= MATRIZ QUANTITATIVA =================
class Indicadores:
    @staticmethod
    def calcular_adx(df, periodo=14):
        try:
            df = df.copy()
            df['tr'] = np.maximum(df['max'] - df['min'], np.maximum(abs(df['max'] - df['close'].shift(1)), abs(df['min'] - df['close'].shift(1))))
            df['up'] = df['max'] - df['max'].shift(1)
            df['down'] = df['min'].shift(1) - df['min']
            df['+dm'] = np.where((df['up'] > df['down']) & (df['up'] > 0), df['up'], 0.0)
            df['-dm'] = np.where((df['down'] > df['up']) & (df['down'] > 0), df['down'], 0.0)
            tr_s = df['tr'].rolling(periodo).sum()
            p_di = 100 * (df['+dm'].rolling(periodo).sum() / (tr_s + 1e-9))
            m_di = 100 * (df['-dm'].rolling(periodo).sum() / (tr_s + 1e-9))
            dx = 100 * (abs(p_di - m_di) / (p_di + m_di + 1e-9))
            adx = dx.rolling(periodo).mean()
            return float(adx.iloc[-1]) if not adx.empty else 0.0
        except Exception:
            return 0.0

# ================= SERVIDOR WEB PROFISSIONAL =================
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

            velas = []
            if API_GLOBAL and ESTADO["conectado"]:
                try:
                    raw = API_GLOBAL.get_candles(par, 60, 50, time.time())
                    if raw:
                        df = pd.DataFrame(raw).drop_duplicates(subset=['from']).sort_values('from')
                        for _, v in df.iterrows():
                            velas.append({
                                "time": int(v["from"]),
                                "open": float(v["open"]),
                                "high": float(v["max"]),
                                "low": float(v["min"]),
                                "close": float(v["close"])
                            })
                        if velas:
                            fechamento = velas[-1]["close"]
                            ESTADO["preco_pip"] = f"{fechamento:.5f}"
                except Exception:
                    pass

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(velas).encode('utf-8'))
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
            <title>Apex Quant Terminal</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
            <style>
                body { background-color: #070a11; color: #cbd5e1; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
                .card { background: #0e1526; border: 1px solid #1e293b; }
            </style>
        </head>
        <body class="p-2 space-y-2 max-w-lg mx-auto select-none">
            <!-- Barra de Status Superior -->
            <div id="status-bar" class="p-2 rounded-lg text-center text-xs font-mono font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">
                Sincronizando com o servidor...
            </div>

            <!-- Topo: Conta e Saldo -->
            <header class="card p-3 rounded-xl flex items-center justify-between">
                <div class="flex items-center space-x-2">
                    <span id="dot-status" class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                    <span class="font-black text-sm text-cyan-400">APEX PRO</span>
                    <select id="sel-ativo" onchange="trocarAtivo()" class="bg-slate-900 border border-slate-700 text-xs font-bold rounded p-1 text-white">
                        <option value="EURUSD-OTC">EUR/USD (OTC)</option>
                        <option value="GBPUSD-OTC">GBP/USD (OTC)</option>
                        <option value="USDJPY-OTC">USD/JPY (OTC)</option>
                        <option value="EURUSD">EUR/USD</option>
                    </select>
                </div>
                <div class="text-right font-mono">
                    <div class="text-[10px] text-slate-400" id="txt-conta">PRACTICE</div>
                    <div class="text-sm font-bold text-white" id="txt-saldo">R$ 0,00</div>
                </div>
            </header>

            <!-- Cards de Métricas e Pips -->
            <div class="grid grid-cols-3 gap-2 text-center text-xs font-mono">
                <div class="card p-2 rounded-lg">
                    <div class="text-[10px] text-slate-400 font-bold">COTAÇÃO / PIP</div>
                    <div class="font-black text-cyan-400 text-sm mt-0.5" id="txt-pip">0.00000</div>
                </div>
                <div class="card p-2 rounded-lg">
                    <div class="text-[10px] text-slate-400 font-bold">CONFLUÊNCIA</div>
                    <div class="font-black text-amber-400 text-sm mt-0.5" id="txt-score">0.0%</div>
                </div>
                <div class="card p-2 rounded-lg">
                    <div class="text-[10px] text-slate-400 font-bold">LUCRO DIA</div>
                    <div class="font-black text-emerald-400 text-sm mt-0.5" id="txt-lucro">R$ 0,00</div>
                </div>
            </div>

            <!-- Gráfico de Velas Interativo -->
            <div class="card rounded-xl p-1 relative" style="height: 270px;">
                <div id="chart-tv" class="w-full h-full"></div>
            </div>

            <!-- Controles Operacionais -->
            <div class="card p-3 rounded-xl space-y-2">
                <div class="grid grid-cols-3 gap-2 text-xs font-mono">
                    <div>
                        <label class="text-[10px] text-slate-400 block mb-0.5">VALOR (R$)</label>
                        <input type="number" id="inp-valor" value="20" class="w-full bg-slate-900 border border-slate-700 rounded p-1 text-white font-bold text-center">
                    </div>
                    <div>
                        <label class="text-[10px] text-slate-400 block mb-0.5">EXPIRAÇÃO</label>
                        <select id="inp-exp" class="w-full bg-slate-900 border border-slate-700 rounded p-1 text-white font-bold text-center">
                            <option value="1">1 Minuto</option>
                            <option value="5">5 Minutos</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-[10px] text-slate-400 block mb-0.5">ROBÔ AUTO</label>
                        <button id="btn-robo" onclick="toggleRobo()" class="w-full bg-emerald-500 text-black font-black p-1 rounded text-xs">LIGADO</button>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-2 pt-1">
                    <button onclick="executarManual('CALL')" class="h-12 bg-emerald-600 active:scale-95 text-white font-black text-xs rounded-xl shadow-lg shadow-emerald-950 flex items-center justify-center space-x-1">
                        <span>▲</span><span>COMPRA (CALL)</span>
                    </button>
                    <button onclick="executarManual('PUT')" class="h-12 bg-rose-600 active:scale-95 text-white font-black text-xs rounded-xl shadow-lg shadow-rose-950 flex items-center justify-center space-x-1">
                        <span>▼</span><span>VENDA (PUT)</span>
                    </button>
                </div>
            </div>

            <!-- Histórico e Placar -->
            <div class="card p-2 rounded-xl text-xs font-mono space-y-1">
                <div class="flex justify-between border-b border-slate-800 pb-1">
                    <span class="text-slate-400">HISTÓRICO</span>
                    <span id="txt-placar" class="font-bold text-white">0W x 0L</span>
                </div>
                <div id="lista-ops" class="max-h-20 overflow-y-auto space-y-1 text-[11px]">
                    <div class="text-slate-500 text-center py-1">Aguardando operações...</div>
                </div>
            </div>

            <script>
                const el = document.getElementById('chart-tv');
                const chart = LightweightCharts.createChart(el, {
                    layout: { background: { color: '#0e1526' }, textColor: '#64748b' },
                    grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
                    timeScale: { timeVisible: true, secondsVisible: true, borderColor: '#1e293b' },
                    rightPriceScale: { borderColor: '#1e293b' }
                });

                const serie = chart.addCandlestickSeries({
                    upColor: '#10b981', downColor: '#f43f5e',
                    borderUpColor: '#10b981', borderDownColor: '#f43f5e',
                    wickUpColor: '#10b981', wickDownColor: '#f43f5e'
                });

                window.addEventListener('resize', () => chart.resize(el.clientWidth, el.clientHeight));
                setTimeout(() => chart.resize(el.clientWidth, el.clientHeight), 300);

                async function sincronizarVelas() {
                    try {
                        const par = document.getElementById('sel-ativo').value;
                        const res = await fetch('/api/velas?par=' + par);
                        const dados = await res.json();
                        if (dados && dados.length > 0) {
                            serie.setData(dados);
                        }
                    } catch (e) {}
                }

                async function sincronizarDados() {
                    try {
                        const res = await fetch('/api/dados');
                        const d = await res.json();

                        const bar = document.getElementById('status-bar');
                        const dot = document.getElementById('dot-status');
                        bar.innerText = d.status;

                        if (d.conectado) {
                            bar.className = 'p-2 rounded-lg text-center text-xs font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
                            dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse';
                        } else {
                            bar.className = 'p-2 rounded-lg text-center text-xs font-mono font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30';
                            dot.className = 'w-2.5 h-2.5 rounded-full bg-rose-500';
                        }

                        document.getElementById('txt-saldo').innerText = 'R$ ' + d.saldo_atual.toFixed(2);
                        document.getElementById('txt-conta').innerText = d.tipo_conta;
                        document.getElementById('txt-pip').innerText = d.preco_pip;
                        document.getElementById('txt-score').innerText = d.score.toFixed(1) + '%';
                        document.getElementById('txt-placar').innerText = `${d.placar_w}W x ${d.placar_l}L`;

                        const lucroEl = document.getElementById('txt-lucro');
                        lucroEl.innerText = (d.lucro_dia >= 0 ? '+R$ ' : '-R$ ') + Math.abs(d.lucro_dia).toFixed(2);
                        lucroEl.className = 'font-black text-sm mt-0.5 ' + (d.lucro_dia >= 0 ? 'text-emerald-400' : 'text-rose-400');

                        if (d.historico && d.historico.length > 0) {
                            document.getElementById('lista-ops').innerHTML = d.historico.map(h => `
                                <div class="flex justify-between bg-slate-900/60 p-1 rounded">
                                    <span>${h.hora} ${h.par}</span>
                                    <span class="${h.dir === 'CALL' ? 'text-emerald-400' : 'text-rose-400'} font-bold">${h.dir}</span>
                                    <span class="${h.res === 'WIN' ? 'text-emerald-400' : 'text-rose-400'} font-bold">${h.res}</span>
                                </div>
                            `).join('');
                        }
                    } catch (e) {}
                }

                function trocarAtivo() { sincronizarVelas(); }

                async function toggleRobo() {
                    const btn = document.getElementById('btn-robo');
                    const r = await (await fetch('/api/toggle', { method: 'POST' })).json();
                    btn.innerText = r.ativo ? 'LIGADO' : 'PAUSADO';
                    btn.className = r.ativo ? 'w-full bg-emerald-500 text-black font-black p-1 rounded text-xs' : 'w-full bg-amber-500 text-black font-black p-1 rounded text-xs';
                }

                async function executarManual(dir) {
                    const par = document.getElementById('sel-ativo').value;
                    const val = parseFloat(document.getElementById('inp-valor').value);
                    const exp = parseInt(document.getElementById('inp-exp').value);
                    await fetch('/api/ordem', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ par, dir, val, exp })
                    });
                }

                setInterval(sincronizarVelas, 2000);
                setInterval(sincronizarDados, 2000);
                sincronizarVelas();
                sincronizarDados();
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        tam = int(self.headers.get('Content-Length', 0))
        corpo = json.loads(self.rfile.read(tam).decode('utf-8')) if tam > 0 else {}

        if self.path == '/api/toggle':
            ESTADO["robo_ativo"] = not ESTADO["robo_ativo"]
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ativo": ESTADO["robo_ativo"]}).encode('utf-8'))
            return

        if self.path == '/api/ordem':
            threading.Thread(target=enviar_ordem, args=(corpo.get("par"), corpo.get("dir"), float(corpo.get("val", 20)), int(corpo.get("exp", 1)), "MANUAL"), daemon=True).start()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            return

    def log_message(self, format, *args):
        return

def iniciar_web():
    porta = int(os.environ.get("PORT", 10000))
    srv = ThreadingHTTPServer(('0.0.0.0', porta), ServidorHandler)
    srv.serve_forever()

threading.Thread(target=iniciar_web, daemon=True).start()

# ================= EXECUÇÃO DE ORDENS E SOROS =================
def enviar_ordem(par, dir, valor, exp, origem="AUTO"):
    global API_GLOBAL
    if not API_GLOBAL or not ESTADO["conectado"]:
        return

    hora = datetime.now().strftime("%H:%M:%S")
    notificar_tg(f"⚡ *ENTRADA DISPARADA ({origem})*\n📊 *Ativo:* `{par}` | *Direção:* `{'🟢 CALL' if dir=='CALL' else '🔴 PUT'}`\n💰 *Valor:* `R$ {valor:.2f}`")

    id_ordem = None
    try:
        _, id_dig = API_GLOBAL.buy_digital_spot(par, valor, dir.lower(), exp)
        if id_dig and id_dig != "error":
            id_ordem = id_dig
    except Exception:
        pass

    if not id_ordem:
        try:
            status, id_bin = API_GLOBAL.buy(valor, par, dir.lower(), exp)
            if status and id_bin:
                id_ordem = id_bin
        except Exception:
            pass

    if id_ordem:
        time.sleep(exp * 60 + 2)
        resultado = "LOSS"
        lucro_op = 0.0

        try:
            check, lucro = API_GLOBAL.check_win_digital_v2(id_ordem)
            if check and lucro > 0:
                resultado = "WIN"
                lucro_op = float(lucro)
        except Exception:
            pass

        # Gestão Soros N2
        if resultado == "WIN":
            ESTADO["placar_w"] += 1
            if ESTADO["soros_nivel"] == 1:
                ESTADO["soros_nivel"] = 2
                ESTADO["soros_lucro"] = lucro_op
            else:
                ESTADO["soros_nivel"] = 1
                ESTADO["soros_lucro"] = 0.0
        else:
            ESTADO["placar_l"] += 1
            ESTADO["soros_nivel"] = 1
            ESTADO["soros_lucro"] = 0.0

        try:
            saldo = float(API_GLOBAL.get_balance())
            ESTADO["saldo_atual"] = saldo
            ESTADO["lucro_dia"] = saldo - ESTADO["saldo_inicial"]
        except Exception:
            pass

        ESTADO["historico"].insert(0, {"hora": hora, "par": par, "dir": dir, "res": resultado})
        notificar_tg(f"📋 *DESFECHO*\nResultado: `{'✅ WIN' if resultado=='WIN' else '❌ LOSS'}`\nSaldo: `R$ {ESTADO['saldo_atual']:.2f}`")

# ================= MOTOR DE ANÁLISE QUANTITATIVA 24/7 =================
def loop_motor():
    global API_GLOBAL
    from iqoptionapi.stable_api import IQ_Option

    email = os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip()
    senha = os.environ.get("IQ_PASSWORD", "").strip()
    tipo = os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper()

    while True:
        if not ESTADO["conectado"]:
            if not senha:
                ESTADO["status"] = "ERRO: Adicione IQ_PASSWORD no Render."
                time.sleep(5)
                senha = os.environ.get("IQ_PASSWORD", "").strip()
                continue

            ESTADO["status"] = "Conectando à corretora..."
            try:
                api = IQ_Option(email, senha)
                ok, _ = api.connect()
                if ok:
                    api.change_balance(tipo)
                    saldo = float(api.get_balance())
                    ESTADO["saldo_inicial"] = saldo
                    ESTADO["saldo_atual"] = saldo
                    ESTADO["tipo_conta"] = tipo
                    ESTADO["conectado"] = True
                    ESTADO["status"] = f"Conectado com sucesso ({tipo})!"
                    API_GLOBAL = api
                    notificar_tg(f"🏛️ *SISTEMA APEX PRO OPERACIONAL*\nConta: `{tipo}` | Saldo: `R$ {saldo:.2f}`")
                else:
                    ESTADO["status"] = "Falha no login. Verifique email e senha."
                    time.sleep(10)
            except Exception as e:
                ESTADO["status"] = f"Erro: {e}"
                time.sleep(10)

        # Loop de Análise nos fechamentos de vela M1 (segundo 00)
        time.sleep(1)
        seg = int(time.time()) % 60

        if seg == 0 and ESTADO["conectado"] and ESTADO["robo_ativo"]:
            try:
                par = ESTADO["ativo"]
                # 1. Filtro Macro 1H (EMA 200)
                v_1h = API_GLOBAL.get_candles(par, 3600, 30, time.time())
                tend_macro = "NEUTRO"
                if v_1h:
                    df_1h = pd.DataFrame(v_1h)
                    ema200 = df_1h['close'].ewm(span=30, adjust=False).mean().iloc[-1]
                    tend_macro = "ALTA" if df_1h['close'].iloc[-1] > ema200 else "BAIXA"

                # 2. Filtro Força 15M (ADX)
                v_15m = API_GLOBAL.get_candles(par, 900, 30, time.time())
                adx = Indicadores.calcular_adx(pd.DataFrame(v_15m)) if v_15m else 0.0

                # 3. Micro Gatilho 1M (Pavio de Rejeição)
                v_1m = API_GLOBAL.get_candles(par, 60, 20, time.time())
                if v_1m and len(v_1m) >= 15:
                    df_1m = pd.DataFrame(v_1m)
                    corpo = abs(df_1m['close'].iloc[-1] - df_1m['open'].iloc[-1])
                    pavio_inf = min(df_1m['close'].iloc[-1], df_1m['open'].iloc[-1]) - df_1m['min'].iloc[-1]
                    pavio_sup = df_1m['max'].iloc[-1] - max(df_1m['close'].iloc[-1], df_1m['open'].iloc[-1])

                    score = 0.0
                    direcao = None
                    if tend_macro == "ALTA" and adx >= 20.0 and pavio_inf > (corpo * 1.5):
                        score = 88.0
                        direcao = "CALL"
                    elif tend_macro == "BAIXA" and adx >= 20.0 and pavio_sup > (corpo * 1.5):
                        score = 88.0
                        direcao = "PUT"

                    ESTADO["score"] = score
                    if score >= 85.0 and direcao:
                        valor_ordem = 20.0 if ESTADO["soros_nivel"] == 1 else (20.0 + ESTADO["soros_lucro"])
                        threading.Thread(target=enviar_ordem, args=(par, direcao, valor_ordem, 1, "AUTO"), daemon=True).start()
            except Exception:
                pass

if __name__ == "__main__":
    loop_motor()
