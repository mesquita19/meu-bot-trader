import os
import sys
import threading
import time
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler

# Força o Python a exibir logs imediatamente
sys.stdout.reconfigure(line_buffering=True)

# ================= CONFIGURAÇÕES DO ROBÔ =================
EMAIL_CORRETORA = os.environ.get("IQ_EMAIL", "").strip()
SENHA_CORRETORA = os.environ.get("IQ_PASSWORD", "").strip()
TIPO_CONTA = os.environ.get("IQ_ACCOUNT_TYPE", "PRACTICE").strip().upper()

TG_TOKEN = os.environ.get("TG_TOKEN", "8601904952:AAHPJhTPKnE2UOoTrtm228cHCyFv8wNHxY8").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "999294230").strip()

PAR_OPERACAO = "EURUSD-OTC"
PAR_EXIBICAO = "EUR/USD (OTC)"
TIMEFRAME_SEGUNDOS = 60  # M1
BANCA_INICIAL = 100.0
ENTRADA_BASE = 20.0
STOP_WIN = 50.0
STOP_LOSS = 40.0
PAYOUT_PADRAO = 0.85
# =========================================================

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[TELEGRAM] Token ou Chat ID ausente!", flush=True)
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[TELEGRAM ERRO] Resposta: {resp.text}", flush=True)
        else:
            print("[TELEGRAM] Mensagem enviada com sucesso!", flush=True)
    except Exception as e:
        print(f"[TELEGRAM EXCEÇÃO] {e}", flush=True)

class SorosManager:
    def __init__(self, banca_inicial, entrada_base, payout):
        self.banca_inicial = banca_inicial
        self.banca_atual = banca_inicial
        self.entrada_base = entrada_base
        self.payout = payout
        self.estagio = 1
        self.lucro_anterior = 0.0

    def obter_valor_entrada(self):
        return self.entrada_base if self.estagio == 1 else self.entrada_base + self.lucro_anterior

    def registrar_resultado(self, resultado, lucro_real=None):
        valor_entrada = self.obter_valor_entrada()
        if resultado == "WIN":
            lucro = lucro_real if (lucro_real is not None and lucro_real > 0) else (valor_entrada * self.payout)
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

class BotCloudWorker:
    def __init__(self):
        self.running = True
        self.api = None
        self.gerenciador = SorosManager(BANCA_INICIAL, ENTRADA_BASE, PAYOUT_PADRAO)
        self.wins = 0
        self.losses = 0
        self.ultima_vela_processada = 0

    def conectar(self):
        try:
            from iqoptionapi.stable_api import IQ_Option
            print(f"[NUVEM] Conectando à corretora como: {EMAIL_CORRETORA}...", flush=True)
            self.api = IQ_Option(EMAIL_CORRETORA, SENHA_CORRETORA)
            status, reason = self.api.connect()

            if status:
                self.api.change_balance(TIPO_CONTA)
                saldo = self.api.get_balance()
                self.gerenciador.banca_inicial = saldo
                self.gerenciador.banca_atual = saldo
                print(f"[NUVEM] Conectado ({TIPO_CONTA}) | Saldo: R$ {saldo:.2f}", flush=True)
                send_telegram(
                    f"🚀 *ROBÔ 24H INICIADO NA NUVEM*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💼 *Conta:* `{TIPO_CONTA}`\n"
                    f"💵 *Banca Inicial:* `R$ {saldo:.2f}`\n"
                    f"📈 *Ativo:* `{PAR_EXIBICAO}` | *TF:* `M1`\n"
                    f"🎯 *Estratégia:* `EMA 7/21 + RSI(7) + Soros N2`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 *Status:* _Monitorando mercado 24/7..._"
                )
                return True
            else:
                print(f"[NUVEM] Falha ao autenticar na corretora: {reason}", flush=True)
                send_telegram(f"⚠️ *Falha ao conectar na corretora:* {reason}")
                return False
        except Exception as e:
            print(f"[NUVEM] Erro crítico de conexão: {e}", flush=True)
            send_telegram(f"⚠️ *Erro crítico de conexão:* {e}")
            return False

    def loop_operacional(self):
        while self.running:
            if not self.conectar():
                print("[NUVEM] Tentando reconectar em 15 segundos...", flush=True)
                time.sleep(15)
                continue

            while self.running:
                try:
                    lucro_atual = self.gerenciador.banca_atual - self.gerenciador.banca_inicial
                    if lucro_atual >= STOP_WIN:
                        send_telegram(f"🏆 *STOP WIN ATINGIDO NA NUVEM!*\n*Lucro:* `+R$ {lucro_atual:.2f}`")
                        break

                    if lucro_atual <= -STOP_LOSS:
                        send_telegram(f"⚠️ *STOP LOSS ATINGIDO NA NUVEM!*\n*Perda:* `-R$ {abs(lucro_atual):.2f}`")
                        break

                    time.sleep(1)
                    segundos_atual = int(time.time()) % TIMEFRAME_SEGUNDOS

                    if segundos_atual in [0, 1]:
                        candles_raw = self.api.get_candles(PAR_OPERACAO, TIMEFRAME_SEGUNDOS, 50, time.time())
                        if candles_raw and len(candles_raw) > 0:
                            timestamp_vela = candles_raw[-1].get('from', 0)
                            if timestamp_vela != self.ultima_vela_processada:
                                self.ultima_vela_processada = timestamp_vela

                                fechamentos = [c['close'] for c in candles_raw]
                                df = pd.DataFrame({'close': fechamentos})
                                df['ema7'] = df['close'].ewm(span=7, adjust=False).mean()
                                df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

                                delta = df['close'].diff()
                                gain = (delta.where(delta > 0, 0)).rolling(window=7).mean()
                                loss = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
                                rs = gain / (loss + 1e-9)
                                rsi = (100 - (100 / (1 + rs))).iloc[-1]

                                sinal, prob = self.analisar_sinal(df, rsi)
                                if sinal in ["CALL", "PUT"]:
                                    self.executar_ordem(sinal, rsi, prob)

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
            score_base = 74.0
            bonus_rsi = (65.0 - rsi) * 0.45
            bonus_forca = min(abs(diff_ema) * 15000, 11.0)
            prob = min(round(score_base + bonus_rsi + bonus_forca, 1), 93.5)
            return "CALL", prob

        elif ema7 < ema21 and p < ema7 and (35.0 <= rsi <= 50.0):
            score_base = 74.0
            bonus_rsi = (rsi - 35.0) * 0.45
            bonus_forca = min(abs(diff_ema) * 15000, 11.0)
            prob = min(round(score_base + bonus_rsi + bonus_forca, 1), 93.5)
            return "PUT", prob

        return "NEUTRO", 0.0

    def executar_ordem(self, direcao, rsi_val, prob_val):
        valor = self.gerenciador.obter_valor_entrada()
        fase = f"Mão {self.gerenciador.estagio} (Soros)" if self.gerenciador.estagio == 2 else "Mão 1 (Base)"

        hora_entrada = datetime.now()
        hora_expiracao = hora_entrada + timedelta(seconds=TIMEFRAME_SEGUNDOS)
        txt_hora_entrada = hora_entrada.strftime("%H:%M:%S")
        txt_hora_expiracao = hora_expiracao.strftime("%H:%M:%S")

        emoji_dir = "🟢 *CALL (COMPRA)*" if direcao == "CALL" else "🔴 *PUT (VENDA)*"
        send_telegram(
            f"🎯 *OPERAÇÃO AUTOMÁTICA DISPARADA (NUVEM)*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Ativo:* `{PAR_EXIBICAO}`\n"
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
        status, id_ordem = self.api.buy(valor, PAR_OPERACAO, dir_api, tf_min)

        if status and id_ordem:
            threading.Thread(target=self.acompanhar_ordem, args=(id_ordem, direcao, valor, txt_hora_entrada), daemon=True).start()
        else:
            send_telegram(f"⚠️ *Corretora rejeitou a ordem* de R$ {valor:.2f} ({direcao}).")

    def acompanhar_ordem(self, id_ordem, direcao, valor, txt_hora_entrada):
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
        resumo = self.gerenciador.registrar_resultado(resultado, lucro_real)

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

        send_telegram(
            f"📋 *RESULTADO DA OPERAÇÃO (NUVEM)*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏁 *Desfecho:* {icone_res}\n"
            f"💵 *Resultado:* `{valor_res}`\n"
            f"📈 *Ativo:* `{PAR_EXIBICAO}`\n"
            f"🕒 *Entrada:* `{txt_hora_entrada}` | *Fechamento:* `{hora_fechamento}`\n"
            f"📊 *Placar Atual:* `{self.wins} WIN  x  {self.losses} LOSS`\n"
            f"💼 *Banca Atualizada:* `R$ {saldo:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

# Servidor Web com suporte a HEAD e GET (para o Render não reclamar)
class HealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Apex Trading Bot Cloud 24/7 Ativo e Operando.")

    def log_message(self, format, *args):
        pass

def iniciar_servidor_web():
    porta = int(os.environ.get("PORT", 8080))
    servidor = HTTPServer(('0.0.0.0', porta), HealthHandler)
    print(f"[NUVEM] Servidor Web ativo na porta {porta}", flush=True)
    servidor.serve_forever()

if __name__ == "__main__":
    print("[NUVEM] Iniciando Worker do Robô...", flush=True)
    
    # Teste imediato do Telegram
    send_telegram("⚡ *Robô inicializado no Render. Conectando à corretora...*")

    worker = BotCloudWorker()
    t_bot = threading.Thread(target=worker.loop_operacional, daemon=True)
    t_bot.start()

    iniciar_servidor_web()
