import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import bms as b

TEAL, AMB, DARK, RED, GRAY, BLUE = "#0F766E", "#F59E0B", "#0B2E2B", "#DC2626", "#94A3B8", "#2563EB"
CEL = ["#0F766E", "#DC2626", "#2563EB", "#9333EA"]
st.set_page_config(page_title="BMS LiFePO4", page_icon="🔋", layout="wide")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Inter:wght@400;600&display=swap');
html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
h1, h2, h3 {{ font-family: 'Instrument Serif', serif !important; font-weight: 400 !important; }}
.hero {{ background: {DARK}; color: #fff; padding: 28px 32px; border-radius: 18px; margin-bottom: 18px; }}
.hero h1 {{ color: #fff; margin: 0; font-size: 2.8rem !important; }}
.hero p {{ color: #99F6E4; font-size: 1.1rem; margin: 6px 0 0; }}
.box {{ background: #E6F2F1; color: #1E293B; border-radius: 14px; padding: 14px 18px; margin-bottom: 12px; }}
.box b {{ color: {TEAL}; }}
.eyebrow {{ color: {TEAL}; font-weight: 600; letter-spacing: .12em; font-size: .78rem; text-transform: uppercase; }}
.result {{ background: {DARK}; color: #fff; border-radius: 14px; padding: 16px 20px; margin-bottom: 12px; }}
.result .num {{ font-family: 'Instrument Serif', serif; font-size: 2.4rem; color: {AMB}; line-height: 1.1; }}
div[data-testid="stMetric"] {{ background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 10px 14px; }}
.stTabs [data-baseweb="tab"] {{ font-size: 1rem; padding: 10px 16px; }}
.stTabs [data-baseweb="tab-list"] {{ flex-wrap: wrap; }}
.hint {{ color:#475569; font-size:.95rem; background:#FFF7ED; border-radius:10px; padding:10px 14px; margin-top:10px; }}
.flow {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:6px 0 14px; }}
.flow span {{ background:#E6F2F1; color:#1E293B; border-radius:12px; padding:10px 14px; font-weight:600; }}
.flow span.on {{ background:{TEAL}; color:#fff; }}
.flow i {{ color:{GRAY}; font-style:normal; font-size:1.3rem; }}
</style>""", unsafe_allow_html=True)

st.markdown("""<div class="hero"><h1>🔋 BMS para células LiFePO4</h1>
<p>Bateria virtual, sensores com ruído, filtros, proteção e filtro de Kalman, com e sem a histerese do LFP</p>
<p style="color:#CBD5E1;font-size:.95rem;margin-top:14px">Caio Gadotti · Projeto da faculdade · ESCF, Engenharia de Sistemas Ciberfísicos · PUC-SP</p></div>""",
            unsafe_allow_html=True)


def layout(fig, h=360, **kw):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="#fff", paper_bgcolor="#fff",
                      font=dict(family="Inter", color="#1E293B"), legend=dict(orientation="h", y=1.14), **kw)
    fig.update_xaxes(gridcolor="#F1F5F9")
    fig.update_yaxes(gridcolor="#F1F5F9")
    return fig


def resultado(num, texto):
    st.markdown(f'<div class="result"><div class="num">{num}</div>{texto}</div>', unsafe_allow_html=True)


def passo(x, n=1500):
    return max(len(x) // n, 1)


with st.sidebar:
    st.markdown("### O pack")
    st.markdown("""**4S1P · 12,8 V · 3,0 Ah**
Células 26650 LiFePO4 com capacidades de 2,94 a 3,05 Ah, para o pack ter uma célula mais fraca, como na vida real.

**Carga:** CC 0,5C até 3,65 V + CV até C/20
**Descarga:** até 2,50 V na célula mais fraca
**Corrente positiva = descarga**""")
    st.divider()
    st.markdown("**Ensaios simulados com passo de 1 s.** Cada mudança nos controles roda a bancada de novo "
                "(alguns segundos).")
    semente = st.number_input("Semente do ruído dos sensores", 0, 999, 0)
    st.divider()
    st.markdown("**Caio Gadotti**  \nProjeto da faculdade · ESCF (Engenharia de Sistemas Ciberfísicos), PUC-SP")


@st.cache_data(show_spinner=False)
def ciclo(kw, c_desc=1.0, c_carga=0.5, semente=0):
    return b.ensaio_ciclo(b.com(b.Params(), **dict(kw)), c_desc, c_carga, semente=semente)


@st.cache_data(show_spinner=False)
def lento(kw):
    return b.ensaio_lento(b.com(b.Params(), **dict(kw)))


@st.cache_data(show_spinner=False)
def falhas(kw, semente):
    return b.ensaio_falhas(b.com(b.Params(), **dict(kw)), semente)


@st.cache_data(show_spinner=False)
def descarga(kw, c, semente):
    return b.ensaio_descarga(b.com(b.Params(), **dict(kw)), c, semente)


SEM = dict(hyst_planta=False, hyst_ekf=False)

tabs = st.tabs(["🔋 O modelo", "📈 Carga e descarga", "🔁 Histerese", "🎯 Estado de carga (EKF)",
                "🛡️ Filtros e proteção", "⚡ Taxa de descarga"])

# ---------------------------------------------------------------- modelo
with tabs[0]:
    st.markdown('<div class="flow"><span>Fonte (bancada)</span><i>→</i><span class="on">Bateria 4S</span><i>→</i>'
                '<span>Sensores com ruído</span><i>→</i><span>Filtros</span><i>→</i><span>Proteção</span><i>↺</i>'
                '<span>chaves de carga e descarga</span></div>', unsafe_allow_html=True)
    st.caption("Em paralelo aos filtros, um filtro de Kalman estendido por célula estima o estado de carga (SOC). "
               "A decisão da proteção vale no segundo seguinte, como num microcontrolador.")
    a, c2 = st.columns([3, 2])
    with a:
        st.markdown('<div class="eyebrow">Célula: circuito equivalente 2RC + histerese</div>', unsafe_allow_html=True)
        st.latex(r"z_{k+1} = z_k - \frac{\eta\,T_s\,i_k}{3600\,Q}")
        st.latex(r"v = \mathrm{OCV}(z) + M_0\,s + M\,h - R_1 i_1 - R_2 i_2 - R_0(T,z)\,i")
        st.latex(r"h_{k+1} = e^{-|\eta i \gamma T_s / 3600Q|}\,h_k + \left(1-e^{-|\eta i \gamma T_s/3600Q|}\right)(-\mathrm{sgn}\,i)")
        st.latex(r"C_{th}\frac{dT}{dt} = R_0 i^2 + R_1 i_1^2 + R_2 i_2^2 - hA\,(T-T_{amb})")
        st.markdown('<div class="box"><b>R₀</b> dá a queda instantânea e cresce no frio (Arrhenius) e nas pontas da '
                    'carga. <b>R₁C₁</b> (20 s) e <b>R₂C₂</b> (7 min) fazem a tensão continuar mudando depois que a '
                    'corrente para. <b>h</b> é a histerese: vai a +1 na carga e a −1 na descarga, na proporção da '
                    'carga que passou.</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="eyebrow">Parâmetros</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([
            ("Pack", "4S1P · 12,8 V · 3,0 Ah · 38,4 Wh"),
            ("Capacidades", "3,05 · 2,94 · 3,00 · 3,02 Ah"),
            ("R₀ · R₁C₁ · R₂C₂", "18 mΩ · 10 mΩ/20 s · 12 mΩ/420 s"),
            ("Histerese", "M = 15 mV · M₀ = 3 mV"),
            ("Proteção corrente", "9 A descarga (3C) · 3 A carga (1C)"),
            ("Proteção temperatura", "carga 0–45 °C · descarga −20–60 °C"),
            ("Sensores", "σ 2 mV + ADC 1 mV · 20 mA + 15 mA offset · 0,3 °C"),
        ], columns=["Item", "Valor"]), width="stretch", hide_index=True)
    st.markdown('<div class="eyebrow">Por que a histerese importa tanto no LiFePO4</div>', unsafe_allow_html=True)
    z = np.linspace(0, 1, 300)
    p = b.Params()
    fig = go.Figure()
    fig.add_scatter(x=100 * z, y=b.ocv(z) + p.M + p.M0, name="depois de carregar", line=dict(color=RED))
    fig.add_scatter(x=100 * z, y=b.ocv(z), name="OCV de equilíbrio", line=dict(color=DARK, dash="dot"))
    fig.add_scatter(x=100 * z, y=b.ocv(z) - p.M - p.M0, name="depois de descarregar", line=dict(color=BLUE))
    layout(fig, 340, xaxis_title="estado de carga (%)", yaxis=dict(title="tensão em repouso (V)", range=[3.0, 3.55]))
    a, c2 = st.columns([3, 2])
    with a:
        st.plotly_chart(fig, width="stretch")
    with c2:
        resultado("18 mV ÷ 1,2 mV/% ≈ 15%",
                  "No meio da curva a tensão do LFP muda só 1,2 mV por ponto de SOC. Os 18 mV da histerese, se o "
                  "estimador não souber deles, viram cerca de 15 pontos de erro no estado de carga. "
                  "A aba 🎯 mostra isso acontecendo.")

# ---------------------------------------------------------------- carga e descarga
with tabs[1]:
    c1, c2 = st.columns(2)
    cd = c1.select_slider("Corrente de descarga", [0.5, 1.0, 1.5, 2.0], 1.0, format_func=lambda v: f"{v:g}C")
    cc = c2.select_slider("Corrente de carga (fase CC)", [0.25, 0.5, 1.0], 0.5, format_func=lambda v: f"{v:g}C")
    with st.spinner("Rodando o ciclo com e sem histerese..."):
        rc = ciclo((), cd, cc, semente)
        rs = ciclo(tuple(SEM.items()), cd, cc, semente)
    d, c = b.fases(rc)
    ds, cs = b.fases(rs)
    ah_d = rc["I"][d].sum() / 3600
    desloc = 1000 * (np.median(rs["V"][ds][:, 0]) - np.median(rc["V"][d][:, 0]))
    k = st.columns(4)
    k[0].metric("Capacidade descarregada", f"{ah_d:.2f} Ah", f"sem histerese {rs['I'][ds].sum() / 3600:.2f} Ah",
                delta_color="off", delta_arrow="off")
    k[1].metric("Deslocamento pela histerese", f"±{desloc:.0f} mV", delta_color="off")
    k[2].metric("Temperatura máxima", f"{rc['T'].max():.1f} °C", "ambiente 25 °C", delta_color="off", delta_arrow="off")
    k[3].metric("Ciclo completo", f"{rc['t'][-1] / 3600:.1f} h", f"CV: {(rc['t'][-1] - rc['t_cv']) / 60:.0f} min",
                delta_color="off", delta_arrow="off")

    a, c2 = st.columns(2)
    with a:
        st.markdown('<div class="eyebrow">Curvas de carga e descarga (célula 1)</div>', unsafe_allow_html=True)
        fig = go.Figure()
        for r, nome, cor, dash in [(rs, "sem histerese", GRAY, "dot"), (rc, "com histerese", AMB, "solid")]:
            dd, ccg = b.fases(r)
            q = np.cumsum(r["I"]) / 3600
            fig.add_scatter(x=q[dd], y=r["V"][dd][:, 0], name=f"descarga · {nome}", line=dict(color=cor, dash=dash))
            fig.add_scatter(x=-(q[ccg] - q[ccg][0]),
                            y=r["V"][ccg][:, 0], name=f"carga · {nome}", line=dict(color=cor, dash=dash, width=3))
        layout(fig, 380, xaxis_title="carga movimentada desde o início da fase (Ah)", yaxis=dict(title="tensão (V)", range=[2.4, 3.75]))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown('<div class="eyebrow">O ciclo no tempo (com histerese)</div>', unsafe_allow_html=True)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.65, .35], vertical_spacing=.06)
        s = passo(rc["t"])
        th = rc["t"][::s] / 3600
        for i in range(4):
            fig.add_scatter(x=th, y=rc["V"][::s, i], name=f"célula {i + 1} ({b.Params().Q[i]:.2f} Ah)",
                            line=dict(color=CEL[i], width=1.5), row=1, col=1)
        fig.add_scatter(x=th, y=rc["I"][::s], name="corrente", line=dict(color=DARK, width=1.5), showlegend=False, row=2, col=1)
        fig.update_yaxes(title_text="V", row=1, col=1)
        fig.update_yaxes(title_text="A", row=2, col=1)
        fig.update_xaxes(title_text="hora", row=2, col=1)
        layout(fig, 380)
        st.plotly_chart(fig, width="stretch")
    st.markdown(f'<div class="hint">A descarga termina quando a <b>célula 2</b>, a mais fraca (2,94 Ah), chega a 2,50 V. '
                f'As outras param entre {rc["V"][np.where(d)[0][-1]][[0, 2, 3]].min():.2f} e '
                f'{rc["V"][np.where(d)[0][-1]][[0, 2, 3]].max():.2f} V, ainda com carga. No repouso a tensão sobe sozinha '
                '(os ramos RC relaxando). A histerese desloca as curvas mas quase não mexe na capacidade.</div>',
                unsafe_allow_html=True)

# ---------------------------------------------------------------- histerese
with tabs[2]:
    st.markdown("### O mesmo SOC, duas tensões")
    st.markdown('<div class="box">Carregando e descarregando bem devagar (C/10), a queda nas resistências fica pequena. '
                'O que sobra de diferença entre a curva de carga e a de descarga é a <b>histerese</b>. No LFP ela vem '
                'das partículas mudando de fase uma a uma: carga e descarga seguem caminhos diferentes.</div>',
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    M = c1.slider("M: histerese dinâmica (mV)", 0, 40, 15) / 1000
    M0 = c2.slider("M₀: histerese instantânea (mV)", 0, 10, 3) / 1000
    gama = c3.slider("γ: velocidade de troca do estado h", 10, 200, 60, 10)
    with st.spinner("Ensaio lento (C/10, ~20 h simuladas)..."):
        rl = lento((("M", M), ("M0", M0), ("gama", float(gama))))
        rl0 = lento(tuple(SEM.items()))
    zs = np.linspace(0.2, 0.8, 13)

    def separacao(r):
        dd, ccg = b.fases(r)
        zd, vd, zc, vc = r["z"][dd][:, 0], r["V"][dd][:, 0], r["z"][ccg][:, 0], r["V"][ccg][:, 0]
        return 1000 * np.mean(np.interp(zs, zc, vc) - np.interp(zs, zd[::-1], vd[::-1]))

    a, c2 = st.columns([3, 2])
    with a:
        fig = go.Figure()
        for r, nome, cor in [(rl0, "sem histerese", GRAY), (rl, "com histerese", AMB)]:
            dd, ccg = b.fases(r)
            fig.add_scatter(x=100 * r["z"][dd][:, 0], y=r["V"][dd][:, 0], name=f"descarga · {nome}", line=dict(color=cor, dash="dot"))
            fig.add_scatter(x=100 * r["z"][ccg][:, 0], y=r["V"][ccg][:, 0], name=f"carga · {nome}", line=dict(color=cor))
        layout(fig, 400, xaxis_title="estado de carga real (%)", yaxis=dict(title="tensão (V)", range=[3.1, 3.5]))
        st.plotly_chart(fig, width="stretch")
    with c2:
        s0, s1 = separacao(rl0), separacao(rl)
        k = st.columns(2)
        k[0].metric("Separação sem histerese", f"{s0:.0f} mV")
        k[1].metric("Separação com histerese", f"{s1:.0f} mV")
        resultado(f"{s1 - s0:.0f} mV",
                  f"é a diferença entre os laços, igual a 2·(M + M₀) = {2000 * (M + M0):.0f} mV. Com os valores padrão "
                  "fica em 36 mV, na faixa medida em células LFP reais (Roscher e Sauer, 2011). Os 24 mV que sobram "
                  "sem histerese são só a resistência interna.")

# ---------------------------------------------------------------- SOC
with tabs[3]:
    st.markdown("### Quanto de carga tem a bateria?")
    st.markdown('<div class="box">SOC não se mede, se estima. O <b>filtro de Kalman estendido</b> prevê o SOC contando a '
                'corrente e corrige olhando a tensão medida: se a tensão veio diferente do que o modelo esperava, a '
                'diferença vai para o SOC. O filtro começa <b>errado de propósito</b> para ver se ele corrige. '
                'Três cenários:<br>(a) bateria sem histerese · (b) bateria com histerese, filtro não sabe · '
                '(c) os dois com histerese.</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    z0 = c1.slider("SOC inicial do filtro (a bateria começa cheia)", 50, 100, 80, 5) / 100
    off = c2.slider("Offset do sensor de corrente (mA)", 0, 60, 15, 5) / 1000
    sv = c3.slider("Ruído do sensor de tensão σ (mV)", 0.5, 8.0, 2.0, 0.5) / 1000
    base = (("soc_ekf0", z0), ("off_I", off), ("sig_V", sv))
    with st.spinner("Rodando os três cenários..."):
        cen = {"(a) sem histerese": ciclo(base + tuple(SEM.items()), semente=semente),
               "(b) com histerese, EKF ignora": ciclo(base + (("hyst_ekf", False),), semente=semente),
               "(c) EKF modela a histerese": ciclo(base, semente=semente)}
    cores = [GRAY, RED, TEAL]
    linhas = []
    fig = go.Figure()
    for (nome, r), cor in zip(cen.items(), cores):
        e, ecc = b.erro_soc(r)
        s = passo(r["t"])
        fig.add_scatter(x=r["t"][::s] / 3600, y=e[::s, 1], name=nome, line=dict(color=cor, width=2))
        linhas.append({"Cenário": nome, "Erro RMS (pp)": b.rms(e, 600), "Pico (pp)": np.abs(e[600:]).max(),
                       "Contagem de Coulomb no fim (pp)": ecc[-1]})
    r = cen["(c) EKF modela a histerese"]
    _, ecc = b.erro_soc(r)
    s = passo(r["t"])
    fig.add_scatter(x=r["t"][::s] / 3600, y=ecc[::s], name="só contagem de Coulomb", line=dict(color=AMB, dash="dot"))
    fig.add_hline(y=0, line_color=DARK, line_width=1)
    layout(fig, 400, xaxis_title="hora", yaxis=dict(title="erro de SOC (pp, célula 2)", range=[-25, 25]))
    st.plotly_chart(fig, width="stretch")
    t = pd.DataFrame(linhas)
    k = st.columns(3)
    for col, (_, row), cor in zip(k, t.iterrows(), ["(a)", "(b)", "(c)"]):
        with col:
            resultado(f"{row['Erro RMS (pp)']:.1f}%", f"erro RMS {row['Cenário'][4:]} · pico {row['Pico (pp)']:.1f}%")
    st.caption("Erro RMS a partir de 10 min (o tempo de o filtro convergir do chute inicial), nas 4 células.")
    st.markdown(f'<div class="hint">Sem saber da histerese, o filtro vê uma tensão 18 mV fora do que esperava e '
                f'"explica" a diferença mexendo no SOC: o pico de {t.iloc[1]["Pico (pp)"]:.0f}% é a conta de 15% da aba '
                f'🔋 acontecendo. Só contar corrente termina com {t.iloc[2]["Contagem de Coulomb no fim (pp)"]:.0f} '
                'pontos de erro: não corrige o chute inicial e ainda acumula o offset do sensor.</div>',
                unsafe_allow_html=True)

# ---------------------------------------------------------------- filtros e proteção
with tabs[4]:
    st.markdown("### Filtrar sem ficar lento, proteger sem alarme falso")
    st.markdown('<div class="box">Ensaio de 3 h com uso normal (±1 A) e falhas provocadas: <b>regeneração de −6 A</b> '
                '(2C de carga) aos 600 s, <b>pico de 15 A</b> (5C) aos 1500 s e o <b>ambiente esquentando</b> de 25 °C '
                'a 75 °C a partir de 1 h. Cada falha só dispara se durar algumas amostras seguidas (debounce) e só '
                'rearma depois de 60 s dentro da faixa.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    tauI = c1.slider("τ do filtro de corrente e tensão (s)", 0.5, 10.0, 2.0, 0.5)
    tauT = c2.slider("τ do filtro de temperatura (s)", 2.0, 30.0, 10.0, 1.0)
    with st.spinner("Rodando o ensaio de falhas..."):
        rf = falhas((("tauI", tauI), ("tauV", tauI), ("tauT", tauT)), semente)
    f = rf["falhas"]
    ev = []
    for j in range(8):
        on = np.where(np.diff(np.r_[0, f[:, j].astype(int)]) == 1)[0]
        for i in on[:2]:
            ev.append({"Falha": b.FALHAS[j], "Detectada (s)": int(rf["t"][i]),
                       "Ação": "abre descarga" if j in (0, 2, 4, 7) else "abre carga"})
    a, c2 = st.columns([3, 2])
    with a:
        jan = slice(540, 1600)
        fig = go.Figure()
        fig.add_scatter(x=rf["t"][jan], y=rf["Im"][jan], name="medida", line=dict(color=GRAY, width=1))
        fig.add_scatter(x=rf["t"][jan], y=rf["If"][jan], name="filtrada", line=dict(color=BLUE, width=2))
        fig.add_scatter(x=rf["t"][jan], y=rf["Ireq"][jan], name="pedida pela bancada", line=dict(color=DARK, dash="dot"))
        fig.add_scatter(x=rf["t"][jan], y=rf["I"][jan], name="real (depois da chave)", line=dict(color=TEAL, width=2))
        layout(fig, 280, xaxis_title="segundos", yaxis_title="corrente (A)")
        st.markdown('<div class="eyebrow">Os dois eventos de corrente</div>', unsafe_allow_html=True)
        st.plotly_chart(fig, width="stretch")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.06, row_heights=[.6, .4])
        s = passo(rf["t"], 2000)
        th = rf["t"][::s] / 3600
        fig.add_scatter(x=th, y=rf["Tf"][::s].max(axis=1), name="célula mais quente (filtrada)", line=dict(color=RED), row=1, col=1)
        fig.add_scatter(x=th, y=rf["Tamb"][::s], name="ambiente", line=dict(color=AMB, dash="dot"), row=1, col=1)
        for y, nome in [(45, "limite de carga"), (60, "limite de descarga")]:
            fig.add_hline(y=y, line_dash="dash", line_color=GRAY, row=1, col=1, annotation_text=nome,
                          annotation_position="top left")
        fig.add_scatter(x=th, y=rf["kchg"][::s].astype(int) + 0.04, name="chave de carga", line=dict(color=TEAL, shape="hv"), row=2, col=1)
        fig.add_scatter(x=th, y=rf["kdis"][::s].astype(int) - 0.04, name="chave de descarga", line=dict(color=DARK, shape="hv"), row=2, col=1)
        fig.update_yaxes(title_text="°C", row=1, col=1)
        fig.update_yaxes(tickvals=[0, 1], ticktext=["aberta", "fechada"], row=2, col=1)
        fig.update_xaxes(title_text="hora", row=2, col=1)
        layout(fig, 420)
        st.markdown('<div class="eyebrow">Temperatura e chaves no ensaio inteiro</div>', unsafe_allow_html=True)
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.dataframe(pd.DataFrame(ev), width="stretch", hide_index=True)
        oc = [e["Detectada (s)"] for e in ev if e["Falha"] == "sobrecorrente carga"]
        atraso = oc[0] - 600 if oc else "—"
        sem_evento = (rf["t"] > 60) & (rf["t"] < 540)
        rI = np.std(rf["Im"][sem_evento] - rf["I"][sem_evento] - b.Params().off_I)
        fI = np.std(rf["If"][sem_evento] - rf["I"][sem_evento] - b.Params().off_I)
        rT = np.std((rf["Tm"] - rf["T"])[sem_evento])
        fT = np.std((rf["Tf"] - rf["T"])[sem_evento])
        resultado(f"{1000 * rI:.0f} → {1000 * fI:.0f} mA",
                  f"de ruído na corrente (desvio-padrão) e {rT:.2f} → {fT:.2f} °C na temperatura. "
                  f"O preço é atraso: com τ = {tauI:g} s, a sobrecorrente leva "
                  f"{atraso} s para ser detectada.")
        st.markdown(f'<div class="hint">A 45 °C o BMS bloqueia <b>só a carga</b> e a bateria continua podendo '
                    'descarregar; a 60 °C bloqueia tudo. Com τ muito curto o ruído passa e a proteção fica nervosa; '
                    'com τ muito longo a detecção atrasa. Curto-circuito precisa de proteção em hardware, '
                    'bem mais rápida que qualquer filtro digital.</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- C-rate
with tabs[5]:
    st.markdown("### Quanto mais corrente, menos bateria")
    st.markdown('<div class="box">1C é a corrente que esvaziaria a bateria em uma hora (3 A); 2C, em meia hora. '
                'Mais corrente é mais queda dentro da célula: a curva desce, bate em 2,50 V antes e a célula '
                'esquenta mais.</div>', unsafe_allow_html=True)
    rates = st.multiselect("Taxas", [0.2, 0.5, 1.0, 2.0, 3.0], [0.5, 1.0, 2.0], format_func=lambda v: f"{v:g}C")
    if rates:
        with st.spinner("Descarregando em cada taxa..."):
            res = {c: descarga((), c, semente) for c in sorted(rates)}
        a, c2 = st.columns([3, 2])
        pal = [TEAL, BLUE, AMB, RED, DARK]
        linhas = []
        with a:
            fig = go.Figure()
            for (cr, r), cor in zip(res.items(), pal):
                q = np.cumsum(r["I"]) / 3600
                fig.add_scatter(x=q, y=r["V"][:, 1], name=f"{cr:g}C", line=dict(color=cor, width=2.5))
                linhas.append({"Taxa": f"{cr:g}C", "Corrente (A)": cr * 3, "Capacidade (Ah)": r["I"].sum() / 3600,
                               "Tensão média (V)": r["V"].mean(), "Temperatura máx. (°C)": r["T"].max(),
                               "Duração (min)": len(r["t"]) / 60})
            layout(fig, 380, xaxis_title="carga descarregada (Ah)", yaxis=dict(title="tensão da célula 2 (V)", range=[2.4, 3.4]))
            st.plotly_chart(fig, width="stretch")
        with c2:
            t = pd.DataFrame(linhas)
            st.dataframe(t.style.format({"Corrente (A)": "{:.1f}", "Capacidade (Ah)": "{:.2f}", "Tensão média (V)": "{:.3f}",
                                         "Temperatura máx. (°C)": "{:.1f}", "Duração (min)": "{:.0f}"}),
                         width="stretch", hide_index=True)
            if len(t) >= 2:
                resultado(f"{1000 * (t['Tensão média (V)'].iloc[-1] - t['Tensão média (V)'].iloc[0]):.0f} mV",
                          f"de tensão média e {100 * (t['Capacidade (Ah)'].iloc[-1] / t['Capacidade (Ah)'].iloc[0] - 1):.0f}% "
                          f"de capacidade de {t['Taxa'].iloc[0]} para {t['Taxa'].iloc[-1]}; "
                          f"a célula chega a {t['Temperatura máx. (°C)'].iloc[-1]:.1f} °C.")
