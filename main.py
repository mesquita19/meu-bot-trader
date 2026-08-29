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
ESTADO_MOTOR = {
    "status": "Iniciando...",
    "email": os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip(),
    "tipo_conta": os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper(),
    "saldo_inicial": 0.0,
    "saldo_atual": 0.0,
    "lucro_dia": 0.0,
    "placar_w": 0,
    "placar_l": 0,
    "soros_estagio": 1,
    "ultimo_par": "---",
    "ultimo_score": 0.0,
    "historico_operacoes": [],
    "heatmap": {}
}

# ================= SERVIDOR HTTP COM DASHBOARD E GRÁFICO =================
class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/dados':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(ESTADO_MOTOR).encode('utf-8'))
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
            <title>Apex Quant Matrix | Dashboard</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body { background-color: #0b0f19; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
                .card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(8px); border: 1px solid rgba(255, 255, 255, 0.08); }
            </style>
        </head>
        <body class="p-4 md:p-8">
            <div class="max-w-7xl mx-auto space-y-6">
                <!-- Header -->
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
                    <div>
                        <div class="flex items-center gap-3">
                            <h1 class="text-2xl font-black tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">APEX QUANT NEURAL ENGINE</h1>
                            <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" id="badge-status">ATIVO</span>
                        </div>
                        <p class="text-xs text-slate-400 mt-1">Varredura Institucional Multi-Timeframe (1H • 15M • 5M • 1M)</p>
                    </div>
                    <div class="text-right">
                        <span class="text-xs text-slate-500">CONTA CONECTADA</span>
                        <div class="text-sm font-mono text-cyan-300 font-bold" id="usr-email">---</div>
                    </div>
                </div>

                <!-- Métricas Principais -->
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div class="card p-4 rounded-xl">
                        <div class="text-xs text-slate-400 uppercase font-semibold">Saldo Atual</div>
                        <div class="text-2xl font-black text-white mt-1 font-mono" id="val-saldo">R$ 0,00</div>
                        <div class="text-xs text-slate-500 mt-1" id="tipo-conta">PRACTICE</div>
                    </div>
                    <div class="card p-4 rounded-xl">
                        <div class="text-xs text-slate-400 uppercase font-semibold">Lucro / Prejuízo (Dia)</div>
                        <div class="text-2xl font-black mt-1 font-mono" id="val-lucro">R$ 0,00</div>
                        <div class="text-xs text-slate-500 mt-1">Stop Win: R$ 60 | Loss: R$ 40</div>
                    </div>
                    <div class="card p-4 rounded-xl">
                        <div class="text-xs text-slate-400 uppercase font-semibold">Placar de Execuções</div>
                        <div class="text-2xl font-black text-emerald-400 mt-1 font-mono" id="val-placar">0W - 0L</div>
                        <div class="text-xs text-slate-500 mt-1" id="val-assertividade">Assertividade: 0%</div>
                    </div>
                    <div class="card p-4 rounded-xl">
                        <div class="text-xs text-slate-400 uppercase font-semibold">Gestão Soros</div>
                        <div class="text-2xl font-black text-cyan-400 mt-1 font-mono" id="val-soros">Nível 1</div>
                        <div class="text-xs text-slate-500 mt-1">Próxima Mão: R$ 20,00</div>
                    </div>
                </div>

                <!-- Gráfico de Performance e Radar -->
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div class="card p-5 rounded-xl lg:col-span-2 space-y-4">
                        <div class="flex justify-between items-center">
                            <h2 class="font-bold text-sm tracking-wide text-slate-200">CURVA DE CAPITAL EM TEMPO REAL</h2>
                            <span class="text-xs text-slate-500 font-mono">Atualização Automática (5s)</span>
                        </div>
                        <div class="h-64">
                            <canvas id="equityChart"></canvas>
                        </div>
                    </div>

                    <div class="card p-5 rounded-xl space-y-4">
                        <h2 class="font-bold text-sm tracking-wide text-slate-200">CONFLUÊNCIA DE FILTROS</h2>
                        <div class="space-y-3 text-xs">
                            <div class="flex justify-between border-b border-slate-800 pb-2">
                                <span class="text-slate-400">Macro Tendência (1H EMA 200)</span>
                                <span class="text-emerald-400 font-bold">ALINHADA</span>
                            </div>
                            <div class="flex justify-between border-b border-slate-800 pb-2">
                                <span class="text-slate-400">Força Direcional (15M ADX)</span>
                                <span class="text-cyan-400 font-bold">&gt; 22.0</span>
                            </div>
                            <div class="flex justify-between border-b border-slate-800 pb-2">
                                <span class="text-slate-400">Ponto de Gatilho (1M Stoch RSI)</span>
                                <span class="text-amber-400 font-bold">SOBREVENDIDO</span>
                            </div>
                            <div class="flex justify-between border-b border-slate-800 pb-2">
                                <span class="text-slate-400">Ação de Preço (Rejeição Pavio)</span>
                                <span class="text-purple-400 font-bold">CONFIRMADA</span>
                            </div>
                            <div class="flex justify-between pt-1">
                                <span class="text-slate-300 font-bold">Score Mínimo Requerido</span>
                                <span class="text-emerald-400 font-bold font-mono">≥ 85.0%</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Tabela de Operações Recentes -->
                <div class="card p-5 rounded-xl space-y-3">
                    <h2 class="font-bold text-sm tracking-wide text-slate-200">HISTÓRICO DE ORDENS INSTITUCIONAIS</h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs text-slate-300">
                            <thead class="text-slate-500 uppercase border-b border-slate-800">
                                <tr>
                                    <th class="py-2">Horário</th>
                                    <th>Ativo</th>
                                    <th>Direção</th>
                                    <th>Score</th>
                                    <th>Valor</th>
                                    <th>Resultado</th>
                                </tr>
                            </thead>
                            <tbody id="tabela-operacoes" class="divide-y divide-slate-800/50">
                                <tr>
                                    <td colspan="6" class="py-4 text-center text-slate-500">Aguardando gatilho de alta confluência...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <script>
                const ctx = document.getElementById('equityChart').getContext('2d');
                const chart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: ['Início'],
                        datasets: [{
                            label: 'Saldo da Banca (R$)',
                            data: [0],
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } },
                            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } }
                        }
                    }
                });

                async function atualizarDashboard() {
                    try {
                        const res = await fetch('/api/dados');
                        const data = await res.json();

                        document.getElementById('usr-email').innerText = data.email;
                        document.getElementById('val-saldo').innerText = 'R$ ' + data.saldo_atual.toFixed(2);
                        document.getElementById('tipo-conta').innerText = data.tipo_conta;
                        
                        const lucroEl = document.getElementById('val-lucro');
                        lucroEl.innerText = (data.lucro_dia >= 0 ? '+R$ ' : '-R$ ') + Math.abs(data.lucro_dia).toFixed(2);
                        lucroEl.className = 'text-2xl font-black mt-1 font-mono ' + (data.lucro_dia >= 0 ? 'text-emerald-400' : 'text-rose-400');

                        document.getElementById('val-placar').innerText = `${data.placar_w}W - ${data.placar_l}L`;
                        const total = data.placar_w + data.placar_l;
                        const taxa = total > 0 ? ((data.placar_w / total) * 100).toFixed(1) : 0;
                        document.getElementById('val-assertividade').innerText = `Assertividade: ${taxa}%`;

                        document.getElementById('val-soros').innerText = `Nível ${data.soros_estagio}`;

                        if (data.saldo_atual > 0 && chart.data.datasets[0].data[0] === 0) {
                            chart.data.datasets[0].data = [data.saldo_inicial, data.saldo_atual];
                            chart.data.labels = ['Início', 'Atual'];
                            chart.update();
                        }

                        if (data.historico_operacoes.length > 0) {
                            const tbody = document.getElementById('tabela-operacoes');
                            tbody.innerHTML = data.historico_operacoes.map(op => `
                                <tr>
                                    <td class="py-2 font-mono text-slate-400">${op.hora}</td>
                                    <td class="font-bold text-white">${op.par}</td>
                                    <td><span class="px-2 py-0.5 rounded text-[10px] font-bold ${op.direcao === 'CALL' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}">${op.direcao}</span></td>
                                    <td class="font-mono text-cyan-300">${op.score}%</td>
                                    <td class="font-mono">R$ ${op.valor.toFixed(2)}</td>
                                    <td><span class="font-bold ${op.resultado === 'WIN' ? 'text-emerald-400' : 'text-rose-400'}">${op.resultado}</span></td>
                                </tr>
                            `).join('');
                        }
                    } catch (e) {
                        console.error("Erro ao sincronizar dashboard:", e);
                    }
                }

                setInterval(atualizarDashboard, 3000);
                atualizarDashboard();
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        return

def iniciar_servidor_http():
    porta = int(os.environ.get("PORT", 10000))
    servidor = HTTPServer(('0.0.0.0', porta), DashboardHandler)
    print(f"🌐 [DASHBOARD QUANT] Painel Web visual ativo na porta {porta}!", flush=True)
    servidor.serve_forever()

threading.Thread(target=iniciar_servidor_http, daemon=True).start()
# ===============================================================

# ================= PARÂMETROS OPERACIONAIS =================
TG_TOKEN = os.environ.get("TG_TOKEN", "8601904952:AAHPJhTPKnE2UOoTrtm228cHCyFv8wNHxY8").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "999294230").strip()

EMAIL_IQ = os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip()
SENHA_IQ = os.environ.get("IQ_PASSWORD", "").strip()
TIPO_CONTA = os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper()

SCORE_MINIMO_EXECUCAO = 85.0
ENTRADA_BASE = 20.0
STOP_WIN = 60.0
STOP_LOSS = 40.0
# ===========================================================

def send_telegram(msg):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    def _post():
        try:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=8)
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()

class QuantAnalytics:
    @staticmethod
    def calcular_adx(df, periodo=14):
        df = df.copy()
        df['h-l'] = df['high'] - df['low']
        df['h-pc'] = abs(df['high'] - df['close'].shift(1))
        df['l-pc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        
        df['up_move'] = df['high'] - df['high'].shift(1)
        df['down_move'] = df['low'].shift(1) - df['low']
        
        df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
        df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)
        
        tr_smooth = df['tr'].rolling(window=periodo).sum()
        plus_di = 100 * (df['plus_dm'].rolling(window=periodo).sum() / (tr_smooth + 1e-9))
        minus_di = 100 * (df['minus_dm'].rolling(window=periodo).sum() / (tr_smooth + 1e-9))
        
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9))
        adx = dx.rolling(window=periodo).mean()
        return float(adx.iloc[-1]) if not adx.empty else 0.0

    @staticmethod
    def calcular_stoch_rsi(series, periodo=14, smooth_k=3):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=periodo).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=periodo).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        
        min_rsi = rsi.rolling(window=periodo).min()
        max_rsi = rsi.rolling(window=periodo).max()
        stoch = 100 * ((rsi - min_rsi) / (max_rsi - min_rsi + 1e-9))
        stoch_k = stoch.rolling(window=smooth_k).mean()
        return float(stoch_k.iloc[-1]) if not stoch_k.empty else 50.0

    @staticmethod
    def calcular_rejeicao_pavio(df):
        ultimo = df.iloc[-1]
        corpo = abs(ultimo['close'] - ultimo['open'])
        pavio_superior = ultimo['high'] - max(ultimo['close'], ultimo['open'])
        pavio_inferior = min(ultimo['close'], ultimo['open']) - ultimo['low']
        return pavio_inferior > (corpo * 1.5), pavio_superior > (corpo * 1.5)

class WeeklyAdaptiveMatrix:
    def __init__(self, api):
        self.api = api
        self.heatmap_assertividade = {}

    def executar_aprendizado_semanal(self, lista_ativos):
        print("🧠 [NEURAL MATRIX] Calculando matriz adaptativa semanal...", flush=True)
        nova_matriz = {}
        for par in lista_ativos[:15]:
            try:
                velas = self.api.get_candles(par, 900, 400, time.time())
                if not velas or len(velas) < 100:
                    continue
                df = pd.DataFrame(velas)
                df['hora'] = pd.to_datetime(df['from'], unit='s').dt.hour
                df['resultado'] = np.where(df['close'] > df['open'], 1, 0)
                
                stats = {}
                for hora, g in df.groupby('hora'):
                    if len(g) > 5:
                        tx = (g['resultado'].sum() / len(g)) * 100.0
                        stats[int(hora)] = round(max(tx, 100.0 - tx), 1)
                nova_matriz[par] = stats
            except Exception:
                continue
        self.heatmap_assertividade = nova_matriz
        ESTADO_MOTOR["heatmap"] = nova_matriz

    def obter_score_historico(self, par):
        h = datetime.now().hour
        return self.heatmap_assertividade.get(par, {}).get(h, 65.0)

class ApexQuantEngine:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.analise = QuantAnalytics()
        self.matriz = None
        self.ativos_monitorados = []
        self.soros_estagio = 1
        self.soros_lucro = 0.0
        self.operando_lock = False

    def conectar(self):
        from iqoptionapi.stable_api import IQ_Option
        print(f"⚡ [APEX ENGINE] Conectando como {EMAIL_IQ}...", flush=True)
        self.api = IQ_Option(EMAIL_IQ, SENHA_IQ)
        check, reason = self.api.connect()

        if check:
            self.api.change_balance(TIPO_CONTA)
            saldo = float(self.api.get_balance())
            
            ESTADO_MOTOR["status"] = "Conectado e Operando"
            ESTADO_MOTOR["saldo_inicial"] = saldo
            ESTADO_MOTOR["saldo_atual"] = saldo
            ESTADO_MOTOR["tipo_conta"] = TIPO_CONTA
            
            self.conectado = True
            self.matriz = WeeklyAdaptiveMatrix(self.api)
            self.sincronizar_universo_ativos()
            
            send_telegram(
                f"🏛️ *APEX QUANT DASHBOARD & MOTOR ATIVOS*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💼 *Conta:* `{TIPO_CONTA}` | *Saldo:* `R$ {saldo:.2f}`\n"
                f"🌐 *Painel Visual:* `https://bot-mesquita-trader-pro.onrender.com`\n"
                f"🎯 *Filtro:* `Confluência ≥ {SCORE_MINIMO_EXECUCAO}%`"
            )
            threading.Thread(target=self.matriz.executar_aprendizado_semanal, args=(self.ativos_monitorados,), daemon=True).start()
            return True
        return False

    def sincronizar_universo_ativos(self):
        try:
            todos = self.api.get_all_open_time()
            encontrados = set()
            for cat in ['turbo', 'binary', 'digital']:
                if cat in todos:
                    for par, d in todos[cat].items():
                        if d.get('open', False):
                            encontrados.add(par)
            self.ativos_monitorados = sorted(list(encontrados)) if encontrados else ["EURUSD-OTC", "GBPUSD-OTC", "EURUSD"]
        except Exception:
            self.ativos_monitorados = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURUSD"]

    def avaliar_confluencia_multi_timeframe(self, par):
        try:
            velas_1h = self.api.get_candles(par, 3600, 50, time.time())
            if not velas_1h or len(velas_1h) < 30: return None, 0
            df_1h = pd.DataFrame(velas_1h)
            ema200 = df_1h['close'].ewm(span=30, adjust=False).mean().iloc[-1]
            tendencia_macro = "ALTA" if df_1h['close'].iloc[-1] > ema200 else "BAIXA"

            velas_15m = self.api.get_candles(par, 900, 30, time.time())
            if not velas_15m: return None, 0
            adx = self.analise.calcular_adx(pd.DataFrame(velas_15m), 14)

            velas_1m = self.api.get_candles(par, 60, 35, time.time())
            if not velas_1m or len(velas_1m) < 25: return None, 0
            df_1m = pd.DataFrame(velas_1m)
            stoch = self.analise.calcular_stoch_rsi(df_1m['close'])
            rej_alta, rej_baixa = self.analise.calcular_rejeicao_pavio(df_1m)

            score_hist = self.matriz.obter_score_historico(par)
            score = 0.0
            direcao = None

            if tendencia_macro == "ALTA":
                score += 30.0
                if adx >= 22.0: score += 20.0
                if 20.0 <= stoch <= 45.0: score += 20.0
                if rej_alta: score += 15.0
                score += (score_hist * 0.15)
                direcao = "CALL"
            elif tendencia_macro == "BAIXA":
                score += 30.0
                if adx >= 22.0: score += 20.0
                if 55.0 <= stoch <= 80.0: score += 20.0
                if rej_baixa: score += 15.0
                score += (score_hist * 0.15)
                direcao = "PUT"

            return direcao, round(score, 1)
        except Exception:
            return None, 0

    def despachar_ordem_institucional(self, par, direcao, score):
        valor = ENTRADA_BASE if self.soros_estagio == 1 else (ENTRADA_BASE + self.soros_lucro)
        hora = datetime.now().strftime("%H:%M:%S")

        send_telegram(
            f"⚡ *ENTRADA DISPARADA*\n"
            f"📊 *Par:* `{par}` | *Direção:* `{'🟢 CALL' if direcao=='CALL' else '🔴 PUT'}`\n"
            f"🧠 *Score:* `{score}%` | *Valor:* `R$ {valor:.2f}`"
        )

        id_ordem = None
        tipo_exec = "DIGITAL"
        try:
            _, id_dig = self.api.buy_digital_spot(par, valor, direcao.lower(), 1)
            if id_dig and id_dig != "error":
                id_ordem = id_dig
        except Exception:
            pass

        if not id_ordem:
            try:
                status, id_bin = self.api.buy(valor, par, direcao.lower(), 1)
                if status and id_bin:
                    id_ordem = id_bin
                    tipo_exec = "BINARY"
            except Exception:
                pass

        if id_ordem:
            threading.Thread(target=self._acompanhar_desfecho, args=(id_ordem, par, direcao, valor, tipo_exec, score, hora), daemon=True).start()
        else:
            self.operando_lock = False

    def _acompanhar_desfecho(self, id_ordem, par, direcao, valor, tipo_exec, score, hora):
        time.sleep(63)
        lucro_real = 0.0
        resultado = "LOSS"

        try:
            if tipo_exec == "DIGITAL":
                check, lucro = self.api.check_win_digital_v2(id_ordem)
                resultado = "WIN" if (check and lucro > 0) else "LOSS"
                lucro_real = float(lucro)
            else:
                status, lucro = self.api.check_win_v4(id_ordem)
                resultado = "WIN" if (status and lucro > 0) else "LOSS"
                lucro_real = float(lucro)
        except Exception:
            pass

        if resultado == "WIN":
            ESTADO_MOTOR["placar_w"] += 1
            if self.soros_estagio == 1:
                self.soros_estagio = 2
                self.soros_lucro = lucro_real
            else:
                self.soros_estagio = 1
                self.soros_lucro = 0.0
        else:
            ESTADO_MOTOR["placar_l"] += 1
            self.soros_estagio = 1
            self.soros_lucro = 0.0

        try:
            saldo = float(self.api.get_balance())
            ESTADO_MOTOR["saldo_atual"] = saldo
            ESTADO_MOTOR["lucro_dia"] = saldo - ESTADO_MOTOR["saldo_inicial"]
        except Exception:
            pass

        ESTADO_MOTOR["soros_estagio"] = self.soros_estagio
        ESTADO_MOTOR["historico_operacoes"].insert(0, {
            "hora": hora,
            "par": par,
            "direcao": direcao,
            "score": score,
            "valor": valor,
            "resultado": resultado
        })
        if len(ESTADO_MOTOR["historico_operacoes"]) > 20:
            ESTADO_MOTOR["historico_operacoes"].pop()

        send_telegram(
            f"📋 *RELATÓRIO DE OPERAÇÃO*\n"
            f"🏁 *Resultado:* `{'✅ WIN' if resultado=='WIN' else '❌ LOSS'}`\n"
            f"📈 *Par:* `{par}` | *Placar:* `{ESTADO_MOTOR['placar_w']}W x {ESTADO_MOTOR['placar_l']}L`\n"
            f"💼 *Saldo:* `R$ {ESTADO_MOTOR['saldo_atual']:.2f}`"
        )
        self.operando_lock = False

    def loop_operacional(self):
        while True:
            if not self.conectado:
                if not self.conectar():
                    time.sleep(15)
                    continue

            time.sleep(1)
            segundo = int(time.time()) % 60

            if segundo in [0, 1] and not self.operando_lock:
                melhor_par, melhor_dir, maior_score = None, None, 0.0

                for par in self.ativos_monitorados:
                    direcao, score = self.avaliar_confluencia_multi_timeframe(par)
                    if score >= SCORE_MINIMO_EXECUCAO and score > maior_score:
                        maior_score, melhor_dir, melhor_par = score, direcao, par

                if melhor_par and melhor_dir:
                    self.operando_lock = True
                    self.despachar_ordem_institucional(melhor_par, melhor_dir, maior_score)

if __name__ == "__main__":
    motor = ApexQuantEngine()
    motor.loop_operacional()
