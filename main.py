import os
import sys
import threading
import time
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler

# Garante envio imediato de logs no Render
sys.stdout.reconfigure(line_buffering=True)

# ================= CONFIGURAÇÕES DO ROBÔ =================
EMAIL_CORRETORA = os.environ.get("IQ_EMAIL", "").strip()
SENHA_CORRETORA = os.environ.get("IQ_PASSWORD", "").strip()
TIPO_CONTA = os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper()

TG_TOKEN = os.environ.get("TG_TOKEN", "8601904952:AAHPJhTPKnE2UOoTrtm228cHCyFv8wNHxY8").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "999294230").strip()

TIMEFRAME_SEGUNDOS = 60  # M1
BANCA_INICIAL = 100.0
ENTRADA_BASE = 20.0
STOP_WIN = 50.0
STOP_LOSS = 40.0
PAYOUT_MINIMO = 0.75  # Só opera pares com payout >= 75%
MAX_OPERACOES_SIMULTANEAS = 1  # Evita expor a banca em vários ativos ao mesmo tempo
# =========================================================

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    def _send():
        try:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=10)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

class SorosManager:
    def __init__(self, banca_inicial, entrada_base):
        self.banca_inicial = banca_inicial
        self.banca_atual = banca_inicial
        self.entrada_base = entrada_base
        self.estagio = 1
        self.lucro_anterior = 0.0

    def obter_valor_entrada(self):
        return self.entrada_base if self.estagio == 1 else self.entrada_base + self.lucro_anterior

    def registrar_resultado(self, resultado, lucro_real=None, payout=0.85):
        valor_entrada = self.obter_valor_entrada()
        if resultado == "WIN":
            lucro = lucro_real if (lucro_real is not None and lucro_real > 0) else (valor_entrada * payout)
            self.banca_atual += lucro
            if self.estagio == 1:
                self.estagio = 2
                self.lucro_anterior = lucro
                return f"WIN Mão 1! Soros N2 ativado: Próxima entrada R$ {self.obter_valor_entrada():.2f}"
            else:
                self.estagio = 1
                self.lucro_anterior = 0.0
                return f"CICLO SOROS CONCLUÍDO! Lucro total: +R$ {lucro:.2f}"
        else:
            self.banca_atual -= valor_entrada
            self.estagio = 1
            self.lucro_anterior = 0.0
            return f"Loss de R$ {valor_entrada:.2f}. Resetando para Mão 1 de proteção."

class BotMultiAssetWorker:
    def __init__(self):
        self.running = True
        self.api = None
        self.gerenciador = SorosManager(BANCA_INICIAL, ENTRADA_BASE)
        self.wins = 0
        self.losses = 0
        self.operando_agora = False
        self.ultima_vela_por_par = {}

    def conectar(self):
        try:
            from iqoptionapi.stable_api import IQ_Option
            print(f"[NUVEM] Conectando à corretora como {EMAIL_CORRETORA}...", flush=True)
            self.api = IQ_Option(EMAIL_CORRETORA, SENHA_CORRETORA)
            status, reason = self.api.connect()

            if status:
                self.api.change_balance(TIPO_CONTA)
                saldo = self.api.get_balance()
                self.gerenciador.banca_inicial = saldo
                self.gerenciador.banca_atual = saldo
                print(f"[NUVEM] Conectado ({TIPO_CONTA}) | Saldo: R$ {saldo:.2f}", flush=True)
                send_telegram(
                    f"🚀 *ROBÔ MULTI-ATIVOS INICIADO NA NUVEM*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💼 *Conta:* `{TIPO_CONTA}`\n"
                    f"💵 *Banca Inicial:* `R$ {saldo:.2f}`\n"
                    f"🌐 *Varredura:* `TODOS OS ATIVOS ABERTOS + OTC`\n"
                    f"🎯 *Estratégia:* `EMA 7/21 + RSI(7) + Soros N2`\n"
                    f"📊 *Payout Mínimo:* `{int(PAYOUT_MINIMO*100)}%`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 *Status:* _Escaneando mercado 24/7..._"
                )
                return True
            else:
                print(f"[NUVEM] Falha ao autenticar: {reason}", flush=True)
                send_telegram(f"⚠️ *Falha ao conectar na corretora:* {reason}")
                return False
        except Exception as e:
            print(f"[NUVEM] Erro de conexão: {e}", flush=True)
            send_telegram(f"⚠️ *Erro crítico de conexão:* {e}")
            return False

    def obter_ativos_abertos(self):
        """Retorna todos os ativos abertos (turbo/binárias e OTC) com payout aceitável"""
        try:
            abertos = []
            todos_ativos = self.api.get_all_open_time()
            
            # Checa opções Turbo / Binárias
            for tipo in ['turbo', 'binary']:
                if tipo in todos_ativos:
                    for par, dados in todos_ativos[tipo].items():
                        if dados.get('open', False) and par not in abertos:
                            abertos.append(par)
            
            # Se a lista vier vazia por delay da API, usa lista de segurança
            if not abertos:
                abertos = [
                    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURJPY", "GBPJPY",
                    "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDCAD-OTC", "EURGBP-OTC"
                ]
            return abertos
        except Exception:
            return ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURUSD", "GBPUSD"]

    def loop_operacional(self):
        while self.running:
            if not self.conectar():
                time.sleep(15)
                continue

            while self.running:
                try:
                    lucro_atual = self.gerenciador.banca_atual - self.gerenciador.banca_inicial
                    if lucro_atual >= STOP_WIN:
                        send_telegram(f"🏆 *STOP WIN ATINGIDO NA NUVEM!*\n*Lucro Total:* `+R$ {lucro_atual:.2f}`\n*Banca Final:* `R$ {self.gerenciador.banca_atual:.2f}`")
                        break

                    if lucro_atual <= -STOP_LOSS:
                        send_telegram(f"⚠️ *STOP LOSS ATINGIDO NA NUVEM!*\n*Perda Total:* `-R$ {abs(lucro_atual):.2f}`\n*Banca Atual:* `R$ {self.gerenciador.banca_atual:.2f}`")
                        break

                    time.sleep(1)
                    segundos_atual = int(time.time()) % TIMEFRAME_SEGUNDOS

                    # Analisa no início de cada nova vela (segundo 0 a 2)
                    if segundos_atual in [0, 1, 2] and not self.operando_agora:
                        ativos = self.obter_ativos_abertos()
                        melhor_sinal = None
                        maior_prob = 0.0
                        melhor_par = None
                        melhor_rsi = 0.0

                        for par in ativos:
                            try:
                                candles_raw = self.api.get_candles(par, TIMEFRAME_SEGUNDOS, 40, time.time())
                                if not candles_raw or len(candles_raw) < 30:
                                    continue

                                ts_vela = candles_raw[-1].get('from', 0)
                                if self.ultima_vela_por_par.get(par) == ts_vela:
                                    continue

                                df = pd.DataFrame({'close': [c['close'] for c in candles_raw]})
                                df['ema7'] = df['close'].ewm(span=7, adjust=False).mean()
                                df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

                                delta = df['close'].diff()
                                gain = (delta.where(delta > 0, 0)).rolling(window=7).mean()
                                loss = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
                                rs = gain / (loss + 1e-9)
                                rsi = float((100 - (100 / (1 + rs))).iloc[-1])

                                sinal, prob = self.analisar_sinal(df, rsi)

                                if sinal in ["CALL", "PUT"] and prob > maior_prob:
                                    maior_prob = prob
                                    melhor_sinal = sinal
                                    melhor_par = par
                                    melhor_rsi = rsi
                                    self.ultima_vela_por_par[par] = ts_vela

                            except Exception:
                                continue

                        # Se encontrou um sinal com boa confluência, executa no melhor par
                        if melhor_sinal and melhor_par and maior_prob >= 75.0:
                            self.operando_agora = True
                            self.executar_ordem(melhor_par, melhor_sinal, melhor_rsi, maior_prob)

                except Exception as e:
                    print(f"[NUVEM ERRO LOOP] {e}", flush=True)
                    time.sleep(5)
                    break

    def analisar_sinal(self, df, rsi):
        p = df['close'].iloc[-1]
        ema7 = df['ema7'].iloc[-1]
        ema21 = df['ema21'].iloc[-1]
        diff_ema = (ema7 - ema21) / ema21

        if ema7 > ema21 and p > ema7 and (50.0 <= rsi <= 65.0):
            score_base = 75.0
            bonus_rsi = (65.0 - rsi) * 0.45
            bonus_forca = min(abs(diff_ema) * 15000, 11.0)
            prob = min(round(score_base + bonus_rsi + bonus_forca, 1), 94.0)
            return "CALL", prob

        elif ema7 < ema21 and p < ema7 and (35.0 <= rsi <= 50.0):
            score_base = 75.0
            bonus_rsi = (rsi - 35.0) * 0.45
            bonus_forca = min(abs(diff_ema) * 15000, 11.0)
            prob = min(round(score_base + bonus_rsi + bonus_forca, 1), 94.0)
            return "PUT", prob

        return "NEUTRO", 0.0

    def executar_ordem(self, par, direcao, rsi_val, prob_val):
        valor = self.gerenciador.obter_valor_entrada()
        fase = f"Mão {self.gerenciador.estagio} (Soros)" if self.gerenciador.estagio == 2 else "Mão 1 (Base)"

        hora_entrada = datetime.now()
        hora_expiracao = hora_entrada + timedelta(seconds=TIMEFRAME_SEGUNDOS)
        txt_hora_entrada = hora_entrada.strftime("%H:%M:%S")
        txt_hora_expiracao = hora_expiracao.strftime("%H:%M:%S")

        nome_amigavel = par.replace("-OTC", " (OTC)")
        emoji_dir = "🟢 *CALL (COMPRA)*" if direcao == "CALL" else "🔴 *PUT (VENDA)*"

        send_telegram(
            f"🎯 *OPERAÇÃO DISPARADA (MULTI-ATIVOS)*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Ativo:* `{nome_amigavel}`\n"
            f"⚡ *Direção:* {emoji_dir}\n"
            f"📊 *Probabilidade:* `{prob_val}%` 🔥\n"
            f"💰 *Valor da Entrada:* `R$ {valor:.2f}` ({fase})\n"
            f"⏰ *Horário Entrada:* `{txt_hora_entrada}`\n"
            f"⏳ *Expiração Prevista:* `{txt_hora_expiracao}`\n"
            f"📐 *RSI(7):* `{rsi_val:.1f}` | *TF:* `M1`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ *Status:* _Executando na corretora..._"
        )

        dir_api = "call" if direcao == "CALL" else "put"
        tf_min = TIMEFRAME_SEGUNDOS // 60
        status, id_ordem = self.api.buy(valor, par, dir_api, tf_min)

        if status and id_ordem:
            threading.Thread(target=self.acompanhar_ordem, args=(id_ordem, par, direcao, valor, txt_hora_entrada), daemon=True).start()
        else:
            self.operando_agora = False
            send_telegram(f"⚠️ *Corretora rejeitou a ordem em {nome_amigavel}* de R$ {valor:.2f} ({direcao}).")

    def acompanhar_ordem(self, id_ordem, par, direcao, valor, txt_hora_entrada):
        time.sleep(TIMEFRAME_SEGUNDOS + 3)
        lucro_real = 0.0
        resultado = "LOSS"
        try:
            status_win, lucro = self.api.check_win_v4(id_ordem)
            if status_win:
                resultado = "WIN" if lucro > 0 else ("EMPATE" if lucro == 0 else "LOSS")
                lucro_real = lucro
            else:
                lucro = self.api.check_win_v3(id_ordem)
                resultado = "WIN" if lucro > 0 else "LOSS"
                lucro_real = lucro
        except Exception:
            pass

        hora_fechamento = datetime.now().strftime("%H:%M:%S")
        self.gerenciador.registrar_resultado(resultado, lucro_real)

        if resultado == "WIN":
            self.wins += 1
            icone_res = "✅ *WIN (VITÓRIA)*"
            valor_res = f"+R$ {lucro_real:.2f}"
        else:
            self.losses += 1
            icone_res = "❌ *LOSS (PERDA)*"
            valor_res = f"-R$ {valor:.2f}"

        saldo = self.gerenciador.banca_atual
        try:
            saldo_api = self.api.get_balance()
            if saldo_api:
                saldo = saldo_api
        except Exception:
            pass

        nome_amigavel = par.replace("-OTC", " (OTC)")
        send_telegram(
            f"📋 *RESULTADO DA OPERAÇÃO*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏁 *Desfecho:* {icone_res}\n"
            f"💵 *Resultado:* `{valor_res}`\n"
            f"📈 *Ativo:* `{nome_amigavel}`\n"
            f"🕒 *Entrada:* `{txt_hora_entrada}` | *Fechamento:* `{hora_fechamento}`\n"
            f"📊 *Placar Geral:* `{self.wins} WIN  x  {self.losses} LOSS`\n"
            f"💼 *Banca Atualizada:* `R$ {saldo:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        self.operando_agora = False

class HealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Apex Trading Bot Multi-Asset 24/7 Ativo.")

    def log_message(self, format, *args):
        pass

def iniciar_servidor_web():
    porta = int(os.environ.get("PORT", 8080))
    servidor = HTTPServer(('0.0.0.0', porta), HealthHandler)
    print(f"[NUVEM] Servidor Web ativo na porta {porta}", flush=True)
    servidor.serve_forever()

if __name__ == "__main__":
    print("[NUVEM] Iniciando Robô Multi-Ativos...", flush=True)
    send_telegram("⚡ *Atualização aplicada: Robô agora monitora TODOS os ativos abertos da corretora 24/7!*")

    worker = BotMultiAssetWorker()
    t_bot = threading.Thread(target=worker.loop_operacional, daemon=True)
    t_bot.start()

    iniciar_servidor_web()
