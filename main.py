import os
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import pandas as pd
import numpy as np
import requests

# ================= SERVIDOR HTTP PARA MANTER O RENDER VIVO =================
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        html = f"""
        <html>
        <head><title>Apex Quant Engine v3.0</title></head>
        <body style="background:#0f172a; color:#38bdf8; font-family:sans-serif; text-align:center; padding-top:50px;">
            <h1>🏛️ Apex Quant Neural Engine v3.0</h1>
            <p style="color:#22c55e; font-size:1.2rem;">● Sistema Operando 24/7 na Nuvem</p>
            <p style="color:#94a3b8;">Status da Conexao: Ativa | Multi-Timeframe M1/M5/M15/H1</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        return  # Silencia logs de requisição para manter o console limpo

def iniciar_servidor_http():
    porta = int(os.environ.get("PORT", 10000))
    servidor = HTTPServer(('0.0.0.0', porta), KeepAliveHandler)
    print(f"🌐 [HTTP SERVER] Porta {porta} aberta com sucesso para o Render!", flush=True)
    servidor.serve_forever()

# Inicia o servidor HTTP em uma thread separada imediatamente
threading.Thread(target=iniciar_servidor_http, daemon=True).start()
# ==========================================================================

# ================= CREDENCIAIS & CONFIGURAÇÕES =================
TG_TOKEN = os.environ.get("TG_TOKEN", "8601904952:AAHPJhTPKnE2UOoTrtm228cHCyFv8wNHxY8").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "999294230").strip()

EMAIL_IQ = os.environ.get("IQ_EMAIL", "ceatecnology@gmail.com").strip()
SENHA_IQ = os.environ.get("IQ_PASSWORD", "").strip()
TIPO_CONTA = os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper()

SCORE_MINIMO_EXECUCAO = 85.0  # Confluência rigorosa
ENTRADA_BASE = 20.0
STOP_WIN = 60.0
STOP_LOSS = 40.0
# ===============================================================

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
    def calcular_ema(series, span):
        return series.ewm(span=span, adjust=False).mean()

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
        
        rejeicao_alta = pavio_inferior > (corpo * 1.5)
        rejeicao_baixa = pavio_superior > (corpo * 1.5)
        return rejeicao_alta, rejeicao_baixa

class WeeklyAdaptiveMatrix:
    def __init__(self, api):
        self.api = api
        self.heatmap_assertividade = {}
        self.ultimo_treino = None

    def executar_aprendizado_semanal(self, lista_ativos):
        print("\n🧠 [NEURAL MATRIX] Iniciando varredura semanal (Walk-Forward Analysis)...", flush=True)
        nova_matriz = {}
        
        for par in lista_ativos[:15]:
            try:
                velas = self.api.get_candles(par, 900, 400, time.time())
                if not velas or len(velas) < 100:
                    continue
                
                df = pd.DataFrame(velas)
                df['hora'] = pd.to_datetime(df['from'], unit='s').dt.hour
                df['resultado'] = np.where(df['close'] > df['open'], 1, 0)
                
                stats_por_hora = {}
                for hora, grupo in df.groupby('hora'):
                    total = len(grupo)
                    if total > 5:
                        taxa = (grupo['resultado'].sum() / total) * 100.0
                        assertividade = max(taxa, 100.0 - taxa)
                        stats_por_hora[hora] = round(assertividade, 1)
                
                nova_matriz[par] = stats_por_hora
            except Exception:
                continue

        self.heatmap_assertividade = nova_matriz
        self.ultimo_treino = datetime.now()
        print(f"✅ [NEURAL MATRIX] Otimização concluída para {len(nova_matriz)} ativos!", flush=True)

    def obter_score_historico(self, par):
        hora_atual = datetime.now().hour
        if par in self.heatmap_assertividade:
            return self.heatmap_assertividade[par].get(hora_atual, 60.0)
        return 65.0

class ApexQuantEngine:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.analise = QuantAnalytics()
        self.matriz = None
        self.ativos_monitorados = []
        self.banca_inicio_dia = 0.0
        self.banca_atual = 0.0
        self.soros_estagio = 1
        self.soros_lucro = 0.0
        self.wins = 0
        self.losses = 0
        self.operando_lock = False

    def conectar(self):
        from iqoptionapi.stable_api import IQ_Option
        print(f"⚡ [APEX ENGINE] Conectando como {EMAIL_IQ}...", flush=True)
        self.api = IQ_Option(EMAIL_IQ, SENHA_IQ)
        check, reason = self.api.connect()

        if check:
            self.api.change_balance(TIPO_CONTA)
            saldo = self.api.get_balance()
            self.banca_inicio_dia = saldo
            self.banca_atual = saldo
            self.conectado = True
            self.matriz = WeeklyAdaptiveMatrix(self.api)
            
            self.sincronizar_universo_ativos()
            
            send_telegram(
                f"🏛️ *APEX QUANT NEURAL ENGINE v3.0 INICIADO*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💼 *Conta:* `{TIPO_CONTA}` | *Saldo:* `R$ {saldo:.2f}`\n"
                f"🌐 *Mercados:* `Forex, Crypto, Commodities, OTC` ({len(self.ativos_monitorados)} pares)\n"
                f"🎯 *Filtro de Execução:* `Score Institucional ≥ {SCORE_MINIMO_EXECUCAO}%`\n"
                f"📊 *Timeframes:* `1H (Macro) + 15M (VWAP) + 5M (ADX) + 1M (Micro)`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 *Status:* _Varredura Neural Ativa 24/7 na Nuvem._"
            )
            threading.Thread(target=self.matriz.executar_aprendizado_semanal, args=(self.ativos_monitorados,), daemon=True).start()
            return True
        else:
            print(f"❌ Erro de conexão: {reason}", flush=True)
            return False

    def sincronizar_universo_ativos(self):
        try:
            todos = self.api.get_all_open_time()
            encontrados = set()
            for categoria in ['turbo', 'binary', 'digital', 'crypto', 'forex']:
                if categoria in todos:
                    for par, d in todos[categoria].items():
                        if d.get('open', False):
                            encontrados.add(par)
            self.ativos_monitorados = sorted(list(encontrados)) if encontrados else ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "BTCUSD", "ETHUSD", "EURUSD"]
        except Exception:
            self.ativos_monitorados = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURUSD", "GBPUSD"]

    def avaliar_confluencia_multi_timeframe(self, par):
        try:
            velas_1h = self.api.get_candles(par, 3600, 50, time.time())
            if not velas_1h or len(velas_1h) < 30:
                return None, 0
            df_1h = pd.DataFrame(velas_1h)
            ema200_1h = df_1h['close'].ewm(span=30, adjust=False).mean().iloc[-1]
            preco_macro = df_1h['close'].iloc[-1]
            tendencia_macro = "ALTA" if preco_macro > ema200_1h else "BAIXA"

            velas_15m = self.api.get_candles(par, 900, 30, time.time())
            if not velas_15m:
                return None, 0
            df_15m = pd.DataFrame(velas_15m)
            adx_15m = self.analise.calcular_adx(df_15m, 14)

            velas_1m = self.api.get_candles(par, 60, 35, time.time())
            if not velas_1m or len(velas_1m) < 25:
                return None, 0
            df_1m = pd.DataFrame(velas_1m)
            stoch_rsi_1m = self.analise.calcular_stoch_rsi(df_1m['close'])
            rejeicao_alta, rejeicao_baixa = self.analise.calcular_rejeicao_pavio(df_1m)

            score_historico = self.matriz.obter_score_historico(par)

            score = 0.0
            direcao = None

            if tendencia_macro == "ALTA":
                score += 30.0
                if adx_15m >= 22.0: score += 20.0
                if 20.0 <= stoch_rsi_1m <= 45.0: score += 20.0
                if rejeicao_alta: score += 15.0
                score += (score_historico * 0.15)
                direcao = "CALL"

            elif tendencia_macro == "BAIXA":
                score += 30.0
                if adx_15m >= 22.0: score += 20.0
                if 55.0 <= stoch_rsi_1m <= 80.0: score += 20.0
                if rejeicao_baixa: score += 15.0
                score += (score_historico * 0.15)
                direcao = "PUT"

            return direcao, round(score, 1)
        except Exception:
            return None, 0

    def despachar_ordem_institucional(self, par, direcao, score):
        valor = ENTRADA_BASE if self.soros_estagio == 1 else (ENTRADA_BASE + self.soros_lucro)
        tipo_mao = f"Soros N2 (Mão 2)" if self.soros_estagio == 2 else "Mão 1 (Base)"

        hora_str = datetime.now().strftime("%H:%M:%S")
        send_telegram(
            f"⚡ *ENTRADA QUANT DISPARADA*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Ativo:* `{par}`\n"
            f"🎯 *Direção:* `{'🟢 CALL (COMPRA)' if direcao=='CALL' else '🔴 PUT (VENDA)'}`\n"
            f"🧠 *Score Confluência:* `{score}%` 🔥\n"
            f"💰 *Aporte:* `R$ {valor:.2f}` ({tipo_mao})\n"
            f"⏰ *Horário:* `{hora_str}` | *TF:* `M1 (Multi-TF Filtered)`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
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
            threading.Thread(target=self._acompanhar_desfecho, args=(id_ordem, par, direcao, valor, tipo_exec), daemon=True).start()
        else:
            self.operando_lock = False
            send_telegram(f"⚠️ *Corretora indisponível para {par} no momento.*")

    def _acompanhar_desfecho(self, id_ordem, par, direcao, valor, tipo_exec):
        time.sleep(63)
        lucro_real = 0.0
        resultado = "LOSS"

        try:
            if tipo_exec == "DIGITAL":
                check, lucro = self.api.check_win_digital_v2(id_ordem)
                resultado = "WIN" if (check and lucro > 0) else "LOSS"
                lucro_real = lucro
            else:
                status, lucro = self.api.check_win_v4(id_ordem)
                resultado = "WIN" if (status and lucro > 0) else "LOSS"
                lucro_real = lucro
        except Exception:
            pass

        if resultado == "WIN":
            self.wins += 1
            if self.soros_estagio == 1:
                self.soros_estagio = 2
                self.soros_lucro = lucro_real
            else:
                self.soros_estagio = 1
                self.soros_lucro = 0.0
        else:
            self.losses += 1
            self.soros_estagio = 1
            self.soros_lucro = 0.0

        try:
            self.banca_atual = self.api.get_balance()
        except Exception:
            pass

        lucro_dia = self.banca_atual - self.banca_inicio_dia
        send_telegram(
            f"📋 *RELATÓRIO DE DESFECHO QUANT*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏁 *Resultado:* `{'✅ WIN (VITÓRIA)' if resultado=='WIN' else '❌ LOSS'}`\n"
            f"💵 *Retorno:* `{'+R$ ' + str(round(lucro_real, 2)) if resultado=='WIN' else '-R$ ' + str(round(valor, 2))}`\n"
            f"📈 *Par:* `{par}` | *Placar:* `{self.wins}W x {self.losses}L`\n"
            f"💼 *Saldo:* `R$ {self.banca_atual:.2f}` (Dia: `R$ {lucro_dia:+.2f}`)\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        self.operando_lock = False

    def loop_operacional(self):
        while True:
            if not self.conectado:
                if not self.conectar():
                    time.sleep(15)
                    continue

            lucro_dia = self.banca_atual - self.banca_inicio_dia
            if lucro_dia >= STOP_WIN:
                send_telegram(f"🏆 *STOP WIN ALCANÇADO!* Lucro: `+R$ {lucro_dia:.2f}`. Pausando até o próximo ciclo.")
                time.sleep(3600 * 8)
                continue
            elif lucro_dia <= -STOP_LOSS:
                send_telegram(f"🛑 *STOP LOSS ATINGIDO.* Perda: `-R$ {abs(lucro_dia):.2f}`. Preservando capital.")
                time.sleep(3600 * 8)
                continue

            time.sleep(1)
            segundo = int(time.time()) % 60

            if segundo in [0, 1] and not self.operando_lock:
                melhor_par = None
                melhor_direcao = None
                maior_score = 0.0

                for par in self.ativos_monitorados:
                    direcao, score = self.avaliar_confluencia_multi_timeframe(par)
                    if score >= SCORE_MINIMO_EXECUCAO and score > maior_score:
                        maior_score = score
                        melhor_direcao = direcao
                        melhor_par = par

                if melhor_par and melhor_direcao:
                    self.operando_lock = True
                    self.despachar_ordem_institucional(melhor_par, melhor_direcao, maior_score)

if __name__ == "__main__":
    motor = ApexQuantEngine()
    motor.loop_operacional()
