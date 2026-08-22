# confianca.py
# Classifica a confiança de uma análise LAY com base em fatores de risco
# validados por backtest (16/08/2026): minuto=-10 (entrada pré-jogo) e
# no_limite=true (aprovação limítrofe nos filtros).
#
# Win rates observados na base historica (189 apostas resolvidas):
#   Grupo A: sem risco                 -> 95.7% (n=116)
#   Grupo B: so no_limite=true         -> 90.6% (n=53)
#   Grupo C: so minuto=-10             -> 75.0% (n=8)   <- amostra pequena
#   Grupo D: minuto=-10 E no_limite    -> 83.3% (n=6)   <- amostra muito pequena
#
# IMPORTANTE: grupos C e D tem amostra pequena. Reavaliar a cada +50
# apostas novas resolvidas.

from dataclasses import dataclass


@dataclass
class Confianca:
    grupo: str
    label: str
    win_rate_pct: int
    n_amostra: int
    amostra_pequena: bool


def classificar_confianca(minuto, no_limite):
    is_pre_jogo_10min = (minuto == -10)
    is_no_limite = bool(no_limite)

    if not is_pre_jogo_10min and not is_no_limite:
        return Confianca("A", "Alta", 96, 116, False)
    elif not is_pre_jogo_10min and is_no_limite:
        return Confianca("B", "Média", 91, 53, False)
    elif is_pre_jogo_10min and not is_no_limite:
        return Confianca("C", "Baixa", 75, 8, True)
    else:
        return Confianca("D", "Baixa", 83, 6, True)


def formatar_para_telegram(c: Confianca) -> str:
    emoji = {"Alta": "🟢", "Média": "🟡", "Baixa": "🔴"}[c.label]
    if c.amostra_pequena:
        return f"{emoji} Confiança: {c.label} (~{c.win_rate_pct}%, base pequena n={c.n_amostra})"
    return f"{emoji} Confiança: {c.label} (~{c.win_rate_pct}%, n={c.n_amostra})"
