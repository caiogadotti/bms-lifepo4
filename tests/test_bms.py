import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bms as b  # noqa: E402

P = b.Params()
P0 = b.com(P, hyst_planta=False, hyst_ekf=False)


@pytest.fixture(scope="module")
def ciclo():
    return b.ensaio_ciclo(P)


@pytest.fixture(scope="module")
def ciclo_b():
    return b.ensaio_ciclo(b.com(P, hyst_ekf=False))


@pytest.fixture(scope="module")
def ciclo_a():
    return b.ensaio_ciclo(P0)


def test_contagem_de_coulomb_fecha_com_a_capacidade():
    """Descarregar Q Ah a corrente constante tira exatamente 100% de SOC."""
    pack = b.Pack(b.com(P, Q=np.full(4, 3.0)), z0=1.0)
    for _ in range(1800):
        pack.passo(3.0, 25.0)
    assert pack.z == pytest.approx(np.full(4, 0.5), abs=1e-9)


def test_ocv_monotona_e_patamar_plano():
    z = np.linspace(0, 1, 501)
    assert np.all(np.diff(b.ocv(z)) > 0)
    assert b.docv(0.5) == pytest.approx(0.0012 * 100, rel=0.01)  # 1,2 mV por ponto percentual


def test_derivada_da_ocv_bate_com_diferenca_finita():
    z = np.linspace(0.02, 0.98, 50)
    num = (b.ocv(z + 1e-6) - b.ocv(z - 1e-6)) / 2e-6
    assert np.allclose(num, b.docv(z), rtol=1e-4)


def test_histerese_vai_para_mais_um_e_menos_um():
    pack = b.Pack(P, z0=0.5, h0=0.0)
    for _ in range(1200):
        pack.passo(3.0, 25.0)
    assert pack.h == pytest.approx(np.full(4, -1.0), abs=0.01)
    for _ in range(1200):
        pack.passo(-3.0, 25.0)
    assert pack.h == pytest.approx(np.full(4, 1.0), abs=0.01)


def test_laco_de_histerese_c10():
    def separacao(r):
        d, c = b.fases(r)
        zs = np.linspace(0.2, 0.8, 13)
        zd, vd, zc, vc = r["z"][d][:, 0], r["V"][d][:, 0], r["z"][c][:, 0], r["V"][c][:, 0]
        return np.mean(np.interp(zs, zc, vc) - np.interp(zs, zd[::-1], vd[::-1]))
    sem, com = separacao(b.ensaio_lento(P0)), separacao(b.ensaio_lento(P))
    assert com - sem == pytest.approx(2 * (P.M + P.M0), abs=0.004)


def test_descarga_para_na_celula_mais_fraca(ciclo):
    d, _ = b.fases(ciclo)
    fim = np.where(d)[0][-1]
    assert np.argmin(ciclo["V"][fim]) == int(np.argmin(P.Q))
    assert ciclo["V"][fim].min() == pytest.approx(P.Vmin, abs=0.01)


def test_carga_nunca_passa_de_vmax(ciclo):
    _, c = b.fases(ciclo)
    assert ciclo["V"][c].max() <= P.Vmax + 1e-3


def test_ekf_converge_do_soc_errado(ciclo):
    e, ecc = b.erro_soc(ciclo)
    assert ecc[0] < -19          # o chute inicial (80% com a bateria cheia) é o mesmo da contagem de Coulomb
    assert b.rms(e, 600) < 2


def test_ignorar_histerese_piora_o_soc(ciclo, ciclo_a, ciclo_b):
    ea, _ = b.erro_soc(ciclo_a)
    eb, _ = b.erro_soc(ciclo_b)
    ec, _ = b.erro_soc(ciclo)
    assert b.rms(eb, 600) > 3 * max(b.rms(ea, 600), b.rms(ec, 600))
    assert np.abs(eb[600:]).max() > 10


def test_coulomb_puro_nao_corrige_o_erro_inicial(ciclo):
    _, ecc = b.erro_soc(ciclo)
    assert ecc[-1] < -18


def test_filtro_reduz_ruido():
    p = b.com(P, off_I=0.0)
    r = b.simular(p, lambda t, pack, m: (1.0, False), 600, z0=0.5)
    assert np.std(r["If"][60:] - 1.0) < 0.6 * np.std(r["Im"][60:] - 1.0)
    assert np.std((r["Tf"] - r["T"])[60:]) < 0.4 * np.std((r["Tm"] - r["T"])[60:])


def test_protecao_dispara_e_abre_a_chave_certa():
    r = b.ensaio_falhas(P)
    t, f = r["t"], r["falhas"]
    primeiro = {j: t[np.argmax(f[:, j])] if f[:, j].any() else None for j in range(8)}
    assert 600 < primeiro[1] <= 605          # sobrecorrente de carga
    assert 1500 < primeiro[0] <= 1505        # sobrecorrente de descarga
    assert primeiro[3] < primeiro[2]         # carga bloqueia antes (45 °C < 60 °C)
    k = int(np.argmax(f[:, 3]))
    assert not r["kchg"][k] and r["kdis"][k]  # a 45 °C bloqueia só a carga
    assert primeiro[6] is None and primeiro[7] is None


def test_sem_disparo_falso_em_uso_normal():
    r = b.simular(P, lambda t, pack, m: (1.0 if (t // 300) % 2 == 0 else -1.0, False), 3600, z0=0.5, h0=0.0)
    assert not r["falhas"].any()


def test_c_rate_maior_baixa_tensao_e_capacidade_e_esquenta():
    res = [b.ensaio_descarga(P, c) for c in (0.5, 2.0)]
    ah = [r["I"].sum() / 3600 for r in res]
    assert res[1]["V"].mean() < res[0]["V"].mean()
    assert ah[1] < ah[0]
    assert res[1]["T"].max() > res[0]["T"].max()
