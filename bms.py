"""Simulação de um BMS para um pack 4S de células LiFePO4 (passo Ts = 1 s).

Planta: modelo de circuito equivalente 2RC + histerese de Plett, resistência com
Arrhenius e polarização nas pontas, modelo térmico de um nó por célula.
BMS: sensores com ruído/offset/ADC, filtro passa-baixa, proteção com debounce e
rearme, estimador de SOC por filtro de Kalman estendido (EKF) por célula.
Convenção: corrente positiva = descarga.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

N = 4


@dataclass
class Params:
    Ts: float = 1.0
    # células 26650 LFP, cada uma um pouco diferente
    Q: np.ndarray = field(default_factory=lambda: np.array([3.05, 2.94, 3.00, 3.02]))   # Ah
    R0: np.ndarray = field(default_factory=lambda: 0.018 * np.array([1.00, 1.08, 0.97, 1.03]))  # ohm
    R1: float = 0.010
    tau1: float = 20.0
    R2: float = 0.012
    tau2: float = 420.0
    eta_carga: float = 0.999
    # histerese (Plett)
    M: float = 0.015            # V, histerese dinâmica
    M0: float = 0.003           # V, histerese instantânea
    gama: float = 60.0          # velocidade com que h vai a ±1
    hyst_planta: bool = True
    hyst_ekf: bool = True
    # temperatura
    Tref: float = 25.0
    Barr: float = 3000.0        # K, Arrhenius da resistência
    Cth: float = 85.0           # J/K
    hA: float = 0.12            # W/K
    # limites de operação
    Qnom: float = 3.0
    Vmax: float = 3.65
    Vmin: float = 2.50
    # proteção
    Imax_dis: float = 9.0       # 3C
    Imax_chg: float = 3.0       # 1C
    Tmax_dis: float = 60.0
    Tmax_chg: float = 45.0
    Tmin_dis: float = -20.0
    Tmin_chg: float = 0.0
    Vov: float = 3.75
    Vuv: float = 2.40
    Non: tuple = (3, 3, 5, 5, 5, 5, 5, 5)  # amostras para disparar cada falha
    Noff: int = 60                         # amostras dentro da faixa para rearmar
    # sensores
    sig_V: float = 0.002
    adc_V: float = 0.001
    sig_I: float = 0.020
    off_I: float = 0.015
    sig_T: float = 0.3
    # filtros passa-baixa
    tauI: float = 2.0
    tauV: float = 2.0
    tauT: float = 10.0
    # EKF
    soc_ekf0: float = 0.80
    Qekf: tuple = (1e-9, 1e-6, 1e-6, 1e-5)
    Rekf: float = 2e-5


FALHAS = ("sobrecorrente descarga", "sobrecorrente carga", "sobretemperatura descarga",
          "sobretemperatura carga", "subtemperatura descarga", "subtemperatura carga",
          "sobretensão", "subtensão")


# ------------------------------------------------------------------ célula

def ocv(z):
    """OCV do LFP: patamar de ~1,2 mV/% com joelhos nas pontas."""
    z = np.clip(z, -0.05, 1.05)
    return 3.27 + 0.12 * (z - 0.5) - 0.55 * np.exp(-z / 0.04) + 0.32 * np.exp(-(1 - z) / 0.03)


def docv(z):
    z = np.clip(z, -0.05, 1.05)
    return 0.12 + 0.55 / 0.04 * np.exp(-z / 0.04) + 0.32 / 0.03 * np.exp(-(1 - z) / 0.03)


def fator_r(z):
    """Polarização: a resistência cresce perto de vazia e de cheia."""
    z = np.clip(z, 0, 1)
    return 1 + 2.0 * np.exp(-z / 0.08) + 0.4 * np.exp(-(1 - z) / 0.06)


def arrhenius(T, p: Params):
    return np.exp(p.Barr * (1 / (np.asarray(T) + 273.15) - 1 / (p.Tref + 273.15)))


class Pack:
    def __init__(self, p: Params, z0=1.0, h0=1.0, T0=25.0):
        self.p = p
        self.z = np.full(N, z0, dtype=float)
        self.i1 = np.zeros(N)
        self.i2 = np.zeros(N)
        self.h = np.full(N, h0, dtype=float)
        self.s = np.full(N, np.sign(h0) if h0 else 0.0)
        self.T = np.full(N, T0, dtype=float)

    def r0(self, I=0.0):
        return self.p.R0 * arrhenius(self.T, self.p) * fator_r(self.z)

    def tensao_sem_r0(self):
        p = self.p
        k = 1.0 if p.hyst_planta else 0.0
        return ocv(self.z) + k * (p.M0 * self.s + p.M * self.h) - p.R1 * self.i1 - p.R2 * self.i2

    def tensao(self, I):
        return self.tensao_sem_r0() - self.r0() * I

    def passo(self, I, Tamb):
        """Avança Ts com corrente I constante; devolve a tensão no início do passo."""
        p = self.p
        R0 = self.r0()
        V = self.tensao_sem_r0() - R0 * I
        ie = I if I >= 0 else p.eta_carga * I
        a1, a2 = np.exp(-p.Ts / p.tau1), np.exp(-p.Ts / p.tau2)
        Ah = np.exp(-np.abs(ie * p.gama * p.Ts / (3600 * p.Q)))
        if abs(I) > 1e-6:
            self.s = np.full(N, -np.sign(I))
        self.h = Ah * self.h + (1 - Ah) * (-np.sign(I)) if abs(I) > 1e-6 else self.h
        q_gen = R0 * I ** 2 + p.R1 * self.i1 ** 2 + p.R2 * self.i2 ** 2
        self.T = self.T + p.Ts / p.Cth * (q_gen - p.hA * (self.T - Tamb))
        self.z = self.z - p.Ts * ie / (3600 * p.Q)
        self.i1 = a1 * self.i1 + (1 - a1) * I
        self.i2 = a2 * self.i2 + (1 - a2) * I
        return V


# ------------------------------------------------------------------ BMS

class Sensores:
    def __init__(self, p: Params, rng):
        self.p, self.rng = p, rng

    def medir(self, I, V, T):
        p, r = self.p, self.rng
        Vm = V + r.normal(0, p.sig_V, N)
        if p.adc_V > 0:
            Vm = np.round(Vm / p.adc_V) * p.adc_V
        Im = I + p.off_I + r.normal(0, p.sig_I)
        Tm = T + r.normal(0, p.sig_T, N)
        return Im, Vm, Tm


class Filtros:
    """Passa-baixa de 1ª ordem: y += α(u − y), α = Ts/(τ + Ts)."""

    def __init__(self, p: Params):
        self.aI = p.Ts / (p.tauI + p.Ts)
        self.aV = p.Ts / (p.tauV + p.Ts)
        self.aT = p.Ts / (p.tauT + p.Ts)
        self.yI = None

    def filtrar(self, Im, Vm, Tm):
        if self.yI is None:
            self.yI, self.yV, self.yT = float(Im), Vm.copy(), Tm.copy()
        self.yI += self.aI * (Im - self.yI)
        self.yV = self.yV + self.aV * (Vm - self.yV)
        self.yT = self.yT + self.aT * (Tm - self.yT)
        return self.yI, self.yV, self.yT


class Protecao:
    def __init__(self, p: Params):
        self.p = p
        self.f = np.zeros(8, dtype=bool)
        self.con = np.zeros(8, dtype=int)
        self.coff = np.zeros(8, dtype=int)

    def avaliar(self, If, Vf, Tf):
        p = self.p
        Tmax, Tmin = Tf.max(), Tf.min()
        setc = np.array([If > p.Imax_dis, If < -p.Imax_chg, Tmax > p.Tmax_dis, Tmax > p.Tmax_chg,
                         Tmin < p.Tmin_dis, Tmin < p.Tmin_chg, Vf.max() > p.Vov, Vf.min() < p.Vuv])
        # rearme só com folga (histerese de rearme) para não oscilar na fronteira
        clrc = np.array([If < 0.9 * p.Imax_dis, If > -0.9 * p.Imax_chg, Tmax < p.Tmax_dis - 5,
                         Tmax < p.Tmax_chg - 5, Tmin > p.Tmin_dis + 5, Tmin > p.Tmin_chg + 5,
                         Vf.max() < p.Vmax, Vf.min() > p.Vmin + 0.2])
        for j in range(8):
            if not self.f[j]:
                self.con[j] = (self.con[j] + 1) * setc[j]
                if self.con[j] >= p.Non[j]:
                    self.f[j], self.coff[j] = True, 0
            else:
                self.coff[j] = (self.coff[j] + 1) * clrc[j]
                if self.coff[j] >= p.Noff:
                    self.f[j], self.con[j] = False, 0
        f = self.f
        kdis = not (f[0] or f[2] or f[4] or f[7])
        kchg = not (f[1] or f[3] or f[5] or f[6])
        return kdis, kchg, f.copy()


class EKF:
    """Um EKF por célula, processado em lote. Estado x = [SOC, i1, i2, h]."""

    def __init__(self, p: Params, z0: float):
        self.p = p
        self.x = np.zeros((N, 4))
        self.x[:, 0] = z0
        self.x[:, 3] = 1.0
        self.P = np.tile(np.diag([0.04, 1e-4, 1e-4, 1.0]), (N, 1, 1))
        self.s = np.ones(N)
        self.Qk = np.diag(p.Qekf)

    def passo(self, Im, Vm, Tf):
        p = self.p
        k = 1.0 if p.hyst_ekf else 0.0
        Mh, M0 = k * p.M, k * p.M0
        i = float(Im)
        ie = i if i >= 0 else p.eta_carga * i
        a1, a2 = np.exp(-p.Ts / p.tau1), np.exp(-p.Ts / p.tau2)
        Ah = np.exp(-abs(ie * p.gama * p.Ts / (3600 * p.Qnom)))
        if abs(i) > 0.05:
            self.s[:] = -np.sign(i)
        x = self.x
        # 1) predição: contagem de Coulomb + dinâmica dos RC e da histerese
        xp = np.column_stack([x[:, 0] - p.Ts * ie / (3600 * p.Qnom),
                              a1 * x[:, 1] + (1 - a1) * i,
                              a2 * x[:, 2] + (1 - a2) * i,
                              Ah * x[:, 3] + (1 - Ah) * (-np.sign(i) if abs(i) > 0.05 else 0.0)])
        A = np.diag([1.0, a1, a2, Ah])
        Pp = A @ self.P @ A.T + self.Qk
        # 2) tensão que o modelo espera
        R0p = np.mean(p.R0) * arrhenius(Tf, p) * fator_r(xp[:, 0])
        yhat = ocv(xp[:, 0]) + M0 * self.s + Mh * xp[:, 3] - p.R1 * xp[:, 1] - p.R2 * xp[:, 2] - R0p * i
        # 3) ganho
        C = np.column_stack([docv(xp[:, 0]), np.full(N, -p.R1), np.full(N, -p.R2), np.full(N, Mh)])
        S = np.einsum("ni,nij,nj->n", C, Pp, C) + p.Rekf
        K = np.einsum("nij,nj->ni", Pp, C) / S[:, None]
        # 4) correção com a tensão medida
        self.x = xp + K * (Vm - yhat)[:, None]
        self.x[:, 0] = np.clip(self.x[:, 0], -0.05, 1.05)   # SOC fisicamente possível
        self.x[:, 3] = np.clip(self.x[:, 3], -1, 1)
        I4 = np.eye(4)
        self.P = np.einsum("nij,njk->nik", I4 - np.einsum("ni,nj->nij", K, C), Pp)
        return self.x[:, 0].copy()


# ------------------------------------------------------------------ bancada

def simular(p: Params, controle, t_max: int, semente: int = 0, z0: float = 1.0, h0: float = 1.0,
            T0: float = 25.0, tamb=lambda t: 25.0) -> dict:
    """Roda o laço fechado bancada → bateria → sensores → filtros → proteção/EKF.

    controle(t, pack, med) -> (corrente pedida, parar?). A proteção pode cortar a corrente.
    """
    rng = np.random.default_rng(semente)
    pack = Pack(p, z0, h0, T0)
    sens, filt, prot, ekf = Sensores(p, rng), Filtros(p), Protecao(p), EKF(p, p.soc_ekf0)
    zcc = p.soc_ekf0
    kdis = kchg = True
    reg = {k: [] for k in ("t", "I", "Ireq", "Im", "If", "V", "Vm", "Vf", "ocv", "z", "zekf", "zcc", "T", "Tm",
                           "Tf", "h", "kdis", "kchg", "falhas", "Tamb")}
    med = None
    for k in range(int(t_max)):
        t = k * p.Ts
        Ireq, parar = controle(t, pack, med)
        if parar:
            break
        I = Ireq
        if (I > 0 and not kdis) or (I < 0 and not kchg):
            I = 0.0
        Ta = tamb(t)
        z_antes, ocv_antes, T_antes, h_antes = pack.z.copy(), ocv(pack.z), pack.T.copy(), pack.h.copy()
        V = pack.passo(I, Ta)
        Im, Vm, Tm = sens.medir(I, V, T_antes)
        If, Vf, Tf = filt.filtrar(Im, Vm, Tm)
        # o BMS decide com a medida deste segundo e a decisão vale no próximo (atraso 1/z)
        kdis, kchg, f = prot.avaliar(If, Vf, Tf)
        zekf = ekf.passo(Im, Vm, Tf)
        zcc -= p.Ts * (Im if Im >= 0 else p.eta_carga * Im) / (3600 * p.Qnom)
        med = {"Vm": Vm, "Vf": Vf, "Im": Im, "If": If, "Tf": Tf}
        for nome, v in (("t", t), ("I", I), ("Ireq", Ireq), ("Im", Im), ("If", If), ("V", V), ("Vm", Vm),
                        ("Vf", Vf), ("ocv", ocv_antes), ("z", z_antes), ("zekf", zekf), ("zcc", zcc),
                        ("T", T_antes), ("Tm", Tm), ("Tf", Tf), ("h", h_antes), ("kdis", kdis),
                        ("kchg", kchg), ("falhas", f), ("Tamb", Ta)):
            reg[nome].append(v)
    return {k: np.array(v) for k, v in reg.items()}


def controle_ciclo(p: Params, c_desc=1.0, c_carga=0.5, repouso=1800):
    """Descarga CC até a célula mais fraca chegar em Vmin, repouso, carga CC até Vmax e CV até C/20."""
    est = {"fase": "descarga", "t_fase": 0.0}
    Id, Ic, Icorte = c_desc * p.Qnom, c_carga * p.Qnom, p.Qnom / 20

    def ctrl(t, pack, med):
        f = est["fase"]
        if f == "descarga":
            if pack.tensao(Id).min() <= p.Vmin:
                est.update(fase="repouso", t_fase=t)
                return 0.0, False
            return Id, False
        if f == "repouso":
            if t - est["t_fase"] >= repouso:
                est["fase"] = "cc"
            return 0.0, False
        if f == "cc":
            if pack.tensao(-Ic).max() >= p.Vmax:
                est.update(fase="cv", t_cv=t)
            else:
                return -Ic, False
        # CV: maior corrente que mantém a célula mais alta em Vmax
        folga = (p.Vmax - pack.tensao_sem_r0()) / pack.r0()
        I = -float(np.clip(folga.min(), 0, Ic))
        if -I < Icorte:
            return 0.0, True
        return I, False

    ctrl.estado = est
    return ctrl


def controle_descarga(p: Params, c: float):
    I = c * p.Qnom

    def ctrl(t, pack, med):
        if pack.tensao(I).min() <= p.Vmin:
            return 0.0, True
        return I, False
    return ctrl


def controle_lento(p: Params, c: float = 0.1):
    """C/10: descarrega de cheia até Vmin e carrega de volta até Vmax."""
    est = {"fase": "descarga"}
    I = c * p.Qnom

    def ctrl(t, pack, med):
        if est["fase"] == "descarga":
            if pack.tensao(I).min() <= p.Vmin:
                est["fase"] = "carga"
            else:
                return I, False
        if pack.tensao(-I).max() >= p.Vmax:
            return 0.0, True
        return -I, False
    return ctrl


def controle_falhas(p: Params, t_regen=600, t_pico=1500):
    """Uso normal (±1 A alternando a cada 5 min) com falhas provocadas."""
    def ctrl(t, pack, med):
        if t_regen <= t < t_regen + 20:
            return -6.0, False
        if t_pico <= t < t_pico + 10:
            return 15.0, False
        return (1.0 if (t // 300) % 2 == 0 else -1.0), False
    return ctrl


def tamb_falhas(t):
    """Ambiente esquentando a partir de 1 h: 25 °C → 75 °C em 2 h."""
    return 25.0 if t < 3600 else min(25.0 + (t - 3600) / 7200 * 50, 75.0)


# ------------------------------------------------------------------ ensaios prontos

def ensaio_ciclo(p: Params, c_desc=1.0, c_carga=0.5, repouso=1800, semente=0):
    ctrl = controle_ciclo(p, c_desc, c_carga, repouso)
    r = simular(p, ctrl, 40000, semente)
    r["t_cv"] = ctrl.estado.get("t_cv", np.nan)
    return r


def ensaio_lento(p: Params, c=0.1, semente=0):
    """Ensaio lento com passo de 10 s: a dinâmica mais rápida que importa aqui (RC de 20 s)
    já está em regime, e o ensaio de 20 h fica 10x mais barato."""
    p10 = replace(p, Ts=10.0)
    return simular(p10, controle_lento(p10, c), int(2.4 * 3600 / c / 10), semente)


def ensaio_falhas(p: Params, semente=0):
    return simular(p, controle_falhas(p), 3600 * 3, semente, z0=0.5, h0=0.0, tamb=tamb_falhas)


def ensaio_descarga(p: Params, c: float, semente=0):
    return simular(p, controle_descarga(p, c), int(3600 / c * 1.2), semente)


def ah(r) -> np.ndarray:
    """Carga acumulada (Ah) ao longo do ensaio, positiva na descarga."""
    return np.cumsum(r["I"]) / 3600


def fases(r):
    """Índices de descarga (I>0) e carga (I<0)."""
    return r["I"] > 1e-6, r["I"] < -1e-6


def erro_soc(r):
    """Erro do EKF e da contagem de Coulomb contra o SOC real, em pontos percentuais."""
    e = 100 * (r["zekf"] - r["z"])
    ecc = 100 * (r["zcc"] - r["z"].mean(axis=1))
    return e, ecc


def rms(x, inicio=0):
    x = np.asarray(x)[inicio:]
    return float(np.sqrt(np.mean(x ** 2)))


def com(p: Params, **kw) -> Params:
    return replace(p, **kw)
