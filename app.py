import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import bms as b

import ui
from ui import TEAL, DARK, RED, GRAY, BLUE, AMB_VIVO as AMB, caixa, como_ler, dica, eyebrow, lead, resultado

CEL = ["#0F766E", "#B91C1C", "#1D4ED8", "#7C3AED"]
st.set_page_config(page_title="BMS LiFePO4 · simulação", page_icon=str(Path(__file__).parent / "icone.png"), layout="wide")
ui.aplicar()
st.markdown("""<style>
.flow { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:6px 0 14px; }
.flow span { background:#F1F7F6; border:1px solid #D5E8E5; color:#1E293B; border-radius:10px; padding:9px 13px; font-weight:500; font-size:.92rem; }
.flow span.on { background:#0F766E; border-color:#0F766E; color:#fff; }
.flow i { color:#94A3B8; font-style:normal; font-size:1.2rem; }
</style>""", unsafe_allow_html=True)

ui.hero("Sistemas embarcados · estimação de estado",
        "BMS para células LiFePO4",
        "Uma bancada virtual para um pack de quatro células: a bateria, os sensores com ruído, os filtros, a proteção "
        "e um filtro de Kalman que tenta adivinhar quanta carga resta. A pergunta central é o que acontece quando o "
        "BMS ignora a histerese, um efeito de 18 mV que no LiFePO4 vale até 15 pontos de carga.",
        [("pack", "4S · 12,8 V · 3 Ah"), ("passo", "1 s"), ("erro de SOC", "0,4% → 7,0%"), ("testes", "14")],
        "Caio Gadotti · Projeto da faculdade · Engenharia de Sistemas Ciberfísicos (ESCF) · PUC-SP")
ui.escopo(
    "Medir o estado de carga (SOC) de uma bateria não é possível: só dá para estimar a partir de tensão, corrente e "
    "temperatura, todas com ruído. No LiFePO4 isso é difícil porque a tensão quase não muda entre 10% e 90% de carga "
    "e ainda depende de a célula estar carregando ou descarregando (histerese). O trabalho mede quanto essa histerese "
    "atrapalha o estimador e testa se o BMS protege o pack quando algo sai do limite.",
    ["Célula por circuito equivalente 2RC + histerese de Plett, com efeito de temperatura (Arrhenius) e aquecimento",
     "Pack 4S com células diferentes entre si (2,94 a 3,05 Ah)",
     "Sensores com ruído, offset e quantização de ADC",
     "Filtro passa-baixa, proteção com 8 falhas, debounce e rearme",
     "Filtro de Kalman estendido (EKF) por célula, com e sem modelo de histerese",
     "Ensaios: ciclo CC/CV, ensaio lento C/10, falhas provocadas e taxas de descarga"],
    ["Balanceamento das células",
     "Envelhecimento e perda de capacidade ao longo dos ciclos",
     "Parâmetros medidos em célula real: vêm de datasheet e literatura",
     "Hardware (microcontrolador, MOSFETs) e proteção contra curto-circuito",
     "Estimadores alternativos (UKF, filtro de partículas)"])


def layout(fig, h=360, **kw):
    kw.setdefault("hovermode", "x unified")
    fig.update_layout(height=h, **kw)
    return fig


def passo(x, n=1500):
    return max(len(x) // n, 1)


with st.sidebar:
    st.markdown("### O pack")
    st.markdown("""
- **4S1P**: 4 células em série, 12,8 V, 3,0 Ah, 38,4 Wh
- **Células 26650 LiFePO4** de 2,94 a 3,05 Ah, diferentes de propósito
- **Carga:** CC 0,5C até 3,65 V, depois CV até C/20
- **Descarga:** até 2,50 V na célula mais fraca
- **Sinal:** corrente positiva é descarga
""")
    st.divider()
    st.markdown("**Ensaios com passo de 1 s.** Mexer num controle roda a bancada de novo, o que leva alguns segundos.")
    semente = st.number_input("Semente do ruído dos sensores", 0, 999, 0,
                              help="Muda o sorteio do ruído. Os resultados variam pouco de uma semente para outra, o que mostra que não dependem de sorte.")
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

tabs = st.tabs([":material/sports_esports: Brinque", ":material/schema: O modelo", ":material/show_chart: Carga e descarga",
                ":material/sync_alt: Histerese", ":material/my_location: Estado de carga (EKF)",
                ":material/shield: Filtros e proteção", ":material/speed: Taxa de descarga"], on_change="rerun", key="aba")

# ---------------------------------------------------------------- brinque
with tabs[0]:
    if tabs[0].open:
        st.markdown("### Bancada ao vivo")
        lead("O mesmo modelo de célula, sensores, filtros, proteção e filtro de Kalman, rodando em tempo real no seu "
             "navegador. O pack começa cheio e o filtro começa achando que está em 80%. As outras abas rodam ensaios "
             "fechados e medem os resultados.")
        pr = b.Params()
        dados = {k: (v.tolist() if isinstance(v, np.ndarray) else list(v) if isinstance(v, tuple) else v)
                 for k, v in asdict(pr).items()}
        dados.update(R0m=float(np.mean(pr.R0)), eta=pr.eta_carga)
        html = (Path(__file__).parent / "brinque.html").read_text(encoding="utf-8").replace("__DADOS__", json.dumps(dados))
        st.iframe(html, height=820)
        como_ler([
            ("Corrente", "A · + descarga", "O que a bancada pede ao pack. Positivo tira energia da bateria, negativo carrega. "
             "Se a chave daquele sentido estiver aberta, a corrente real vira zero."),
            ("Barra verde da célula", "SOC real, %", "Quanta carga a célula tem de verdade. Só o simulador conhece esse valor."),
            ("Tracejado amarelo", "SOC do EKF, %", "O que o BMS acha que a célula tem. Começa em 80% de propósito e precisa convergir."),
            ("Tensão da célula", "V", "Tensão nos terminais, já com a queda nas resistências internas e o efeito da histerese."),
            ("Temperatura", "°C", "Esquenta pelas perdas I²R e troca calor com o ambiente. Verde abaixo de 35 °C, amarelo até 45 °C, vermelho acima."),
            ("Chaves", "aberta / fechada", "MOSFETs de carga e de descarga, separados: dá para bloquear só a carga e deixar a bateria descarregar."),
            ("Alarmes", "8 falhas", "Acendem quando o valor filtrado passa do limite por algumas amostras seguidas. Só apagam depois de 60 s dentro da faixa."),
            ("Erro do SOC estimado", "pontos percentuais", "SOC do EKF menos SOC real, na célula 2. Desligue a histerese no filtro e veja esse número crescer."),
            ("Velocidade", "s simulados por s", "Quantos segundos de bateria passam a cada segundo real. 60 = um minuto por segundo."),
        ])

# ---------------------------------------------------------------- modelo
with tabs[1]:
    if tabs[1].open:
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
                      "A aba Estado de carga mostra isso acontecendo.")
        como_ler([
            ("SOC (z)", "0 a 1", "Estado de carga: fração da capacidade que ainda está na célula."),
            ("OCV(z)", "V", "Tensão de circuito aberto: a tensão da célula em repouso total, sem corrente e sem histerese."),
            ("R₀", "mΩ", "Resistência ôhmica. Dá a queda imediata quando a corrente muda. Cresce no frio e perto de vazia ou cheia."),
            ("R₁C₁, R₂C₂", "mΩ · s", "Dois ramos RC que imitam a difusão dentro da célula. Por causa deles a tensão continua mudando depois que a corrente para."),
            ("h, M, M₀", "−1 a 1 · mV", "Histerese. h vai a +1 depois de carregar e a −1 depois de descarregar; M é o tamanho desse efeito; M₀ é a parte que muda na hora."),
            ("γ", "adimensional", "Quão rápido h troca de lado quando a corrente inverte."),
            ("η", "≈ 0,999", "Eficiência coulômbica na carga: um pouco da carga que entra não fica guardada."),
            ("Cth, hA", "J/K · W/K", "Capacidade térmica da célula e troca de calor com o ar. Juntas definem quanto e quão rápido ela esquenta."),
            ("C (taxa)", "1C = 3 A", "Corrente em múltiplos da capacidade. 1C esvaziaria a bateria em 1 hora, 0,5C em 2 horas."),
        ])

# ---------------------------------------------------------------- carga e descarga
with tabs[2]:
    if tabs[2].open:
        st.markdown("### Um ciclo completo: descarga, repouso e carga")
        lead("A bancada descarrega o pack até a célula mais fraca chegar em 2,50 V, espera 30 minutos e recarrega em "
             "corrente constante (CC) até 3,65 V, segurando a tensão (CV) até a corrente cair a C/20. O ciclo roda duas "
             "vezes, com e sem histerese, para comparar.")
        c1, c2 = st.columns(2)
        cd = c1.select_slider("Corrente de descarga", [0.5, 1.0, 1.5, 2.0], 1.0, format_func=lambda v: f"{v:g}C",
                              help="1C = 3 A, esvaziaria a bateria em uma hora.")
        cc = c2.select_slider("Corrente de carga (fase CC)", [0.25, 0.5, 1.0], 0.5, format_func=lambda v: f"{v:g}C",
                              help="Corrente usada até a primeira célula chegar a 3,65 V.")
        with st.spinner("Rodando o ciclo com e sem histerese..."):
            rc = ciclo((), cd, cc, semente)
            rs = ciclo(tuple(SEM.items()), cd, cc, semente)
        d, c = b.fases(rc)
        ds, cs = b.fases(rs)
        ah_d = rc["I"][d].sum() / 3600
        desloc = 1000 * (np.median(rs["V"][ds][:, 0]) - np.median(rc["V"][d][:, 0]))
        k = st.columns(4)
        k[0].metric("Capacidade descarregada", f"{ah_d:.2f} Ah", f"sem histerese {rs['I'][ds].sum() / 3600:.2f} Ah",
                    delta_color="off", delta_arrow="off",
                    help="Carga que saiu do pack até a célula mais fraca bater em 2,50 V. Fica abaixo dos 2,94 Ah dela porque a queda na resistência leva a tensão ao limite antes de a célula esvaziar.")
        k[1].metric("Deslocamento pela histerese", f"±{desloc:.0f} mV",
                    help="Diferença mediana entre a curva de descarga com e sem histerese. Na carga o deslocamento é o mesmo, para cima.")
        k[2].metric("Temperatura máxima", f"{rc['T'].max():.1f} °C", "ambiente 25 °C", delta_color="off", delta_arrow="off",
                    help="Célula mais quente em todo o ciclo, aquecida pelas perdas I²R.")
        k[3].metric("Ciclo completo", f"{rc['t'][-1] / 3600:.1f} h", f"CV: {(rc['t'][-1] - rc['t_cv']) / 60:.0f} min",
                    delta_color="off", delta_arrow="off",
                    help="Descarga + 30 min de repouso + carga CC/CV. A fase CV é a parte final, com a tensão parada em 3,65 V e a corrente caindo.")

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
        como_ler([
            ("Carga movimentada", "Ah", "Carga que entrou ou saiu desde o começo daquela fase. As duas curvas começam em zero para dar para comparar."),
            ("Patamar", "≈ 3,1 a 3,35 V", "A parte plana da curva, onde fica a maior parte da energia do LFP."),
            ("Joelho", "fim da curva", "Onde a tensão despenca (perto de vazia) ou dispara (perto de cheia)."),
            ("Fase CC", "corrente fixa", "Carga com corrente constante até a primeira célula chegar a 3,65 V."),
            ("Fase CV", "tensão fixa", "O carregador segura 3,65 V e a corrente vai caindo; termina em C/20 (0,15 A)."),
            ("Célula mais fraca", "célula 2 · 2,94 Ah", "Define o fim da descarga do pack inteiro, mesmo com as outras ainda com carga."),
        ])

# ---------------------------------------------------------------- histerese
with tabs[3]:
    if tabs[3].open:
        st.markdown("### O mesmo SOC, duas tensões")
        st.markdown('<div class="box">Carregando e descarregando bem devagar (C/10), a queda nas resistências fica pequena. '
                    'O que sobra de diferença entre a curva de carga e a de descarga é a <b>histerese</b>. No LFP ela vem '
                    'das partículas mudando de fase uma a uma: carga e descarga seguem caminhos diferentes.</div>',
                    unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        M = c1.slider("M: histerese dinâmica (mV)", 0, 40, 15,
                      help="Quanto a tensão se desloca depois de a célula passar um tempo carregando ou descarregando.") / 1000
        M0 = c2.slider("M₀: histerese instantânea (mV)", 0, 10, 3,
                       help="Parte da histerese que troca de lado na hora em que a corrente muda de sentido.") / 1000
        gama = c3.slider("γ: velocidade de troca do estado h", 10, 200, 60, 10,
                         help="Maior γ = h chega a ±1 com menos carga movimentada.")
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
            k[0].metric("Separação sem histerese", f"{s0:.0f} mV",
                        help="Distância média entre a curva de carga e a de descarga entre 20% e 80% de SOC. Sem histerese, sobra só a queda nas resistências.")
            k[1].metric("Separação com histerese", f"{s1:.0f} mV", help="A mesma distância com a histerese ligada.")
            resultado(f"{s1 - s0:.0f} mV",
                      f"é a diferença entre os laços, igual a 2·(M + M₀) = {2000 * (M + M0):.0f} mV. Com os valores padrão "
                      "fica em 36 mV, na faixa medida em células LFP reais (Roscher e Sauer, 2011). Os 24 mV que sobram "
                      "sem histerese são só a resistência interna.")
        como_ler([
            ("C/10", "0,3 A", "Corrente bem baixa: a carga leva 10 horas. Assim a queda nas resistências fica pequena e a histerese aparece."),
            ("Laço", "curva fechada", "O caminho de descarga fica embaixo e o de carga em cima. A distância entre eles é o que se mede."),
            ("Separação", "mV", "Média da distância entre os dois caminhos, de 20% a 80% de SOC."),
            ("2·(M + M₀)", "mV", "O quanto a histerese abre o laço: M + M₀ para cima na carga e o mesmo para baixo na descarga."),
        ])

# ---------------------------------------------------------------- SOC
with tabs[4]:
    if tabs[4].open:
        st.markdown("### Quanto de carga tem a bateria?")
        st.markdown('<div class="box">SOC não se mede, se estima. O <b>filtro de Kalman estendido</b> prevê o SOC contando a '
                    'corrente e corrige olhando a tensão medida: se a tensão veio diferente do que o modelo esperava, a '
                    'diferença vai para o SOC. O filtro começa <b>errado de propósito</b> para ver se ele corrige. '
                    'Três cenários:<br>(a) bateria sem histerese · (b) bateria com histerese, filtro não sabe · '
                    '(c) os dois com histerese.</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        z0 = c1.slider("SOC inicial do filtro (%)", 50, 100, 80, 5,
                       help="O chute inicial do filtro. A bateria começa cheia (100%), então 80% é um erro de 20 pontos.") / 100
        off = c2.slider("Offset do sensor de corrente (mA)", 0, 60, 15, 5,
                        help="Erro fixo do sensor de corrente. Na contagem de Coulomb ele acumula sem parar.") / 1000
        sv = c3.slider("Ruído do sensor de tensão σ (mV)", 0.5, 8.0, 2.0, 0.5,
                       help="Desvio-padrão do ruído na leitura de tensão de cada célula.") / 1000
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
                    f'O modelo acontecendo. Só contar corrente termina com {t.iloc[2]["Contagem de Coulomb no fim (pp)"]:.0f} '
                    'pontos de erro: não corrige o chute inicial e ainda acumula o offset do sensor.</div>',
                    unsafe_allow_html=True)
        como_ler([
            ("Erro de SOC", "pontos percentuais (pp)", "SOC estimado menos SOC real. +5 pp quer dizer que o BMS acha que tem 5% a mais do que tem."),
            ("Erro RMS", "pp", "Raiz da média dos erros ao quadrado, depois dos 10 primeiros minutos. Resume o erro típico do ciclo inteiro."),
            ("Pico", "pp", "Maior erro em módulo depois dos 10 primeiros minutos: o pior momento."),
            ("Contagem de Coulomb", "integral da corrente", "Somar a corrente medida no tempo. Simples, mas não corrige o chute inicial e acumula o offset do sensor."),
            ("EKF", "filtro de Kalman estendido", "Prevê com a contagem de Coulomb e corrige com a tensão medida, pesando qual dos dois está mais confiável."),
            ("Cenário (b)", "planta ≠ modelo", "A bateria tem histerese e o filtro não sabe. Ele atribui ao SOC um desvio de tensão que na verdade é histerese."),
        ])

# ---------------------------------------------------------------- filtros e proteção
with tabs[5]:
    if tabs[5].open:
        st.markdown("### Filtrar sem ficar lento, proteger sem alarme falso")
        st.markdown('<div class="box">Ensaio de 3 h com uso normal (±1 A) e falhas provocadas: <b>regeneração de −6 A</b> '
                    '(2C de carga) aos 600 s, <b>pico de 15 A</b> (5C) aos 1500 s e o <b>ambiente esquentando</b> de 25 °C '
                    'a 75 °C a partir de 1 h. Cada falha só dispara se durar algumas amostras seguidas (debounce) e só '
                    'rearma depois de 60 s dentro da faixa.</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        tauI = c1.slider("τ do filtro de corrente e tensão (s)", 0.5, 10.0, 2.0, 0.5,
                         help="Constante de tempo do passa-baixa. Maior τ = sinal mais limpo e resposta mais lenta.")
        tauT = c2.slider("τ do filtro de temperatura (s)", 2.0, 30.0, 10.0, 1.0,
                         help="Temperatura muda devagar, então aguenta um filtro mais pesado sem perder nada.")
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
        como_ler([
            ("τ (tau)", "s", "Constante de tempo do filtro passa-baixa: depois de τ segundos o sinal filtrado percorreu 63% de um degrau."),
            ("Medida / filtrada", "A", "Cinza é o que o sensor leu (com ruído e offset); azul é o que o BMS usa para decidir."),
            ("Pedida / real", "A", "Pontilhado é o que a bancada pediu; verde é o que passou de fato. Quando a chave abre, a real vai a zero."),
            ("Debounce", "3 a 5 amostras", "A falha precisa ficar ativa algumas leituras seguidas. Evita disparo por um único pico de ruído."),
            ("Rearme", "60 s", "Depois de disparar, a falha só limpa quando o valor passa 60 s dentro da faixa com folga."),
            ("Detectada (s)", "s", "Instante em que a falha disparou. A diferença para o evento é o atraso do filtro mais o debounce."),
            ("Ruído (desvio-padrão)", "mA · °C", "Espalhamento do sinal em torno do valor real, antes e depois do filtro, num trecho sem eventos."),
        ])

# ---------------------------------------------------------------- C-rate
with tabs[6]:
    if tabs[6].open:
        st.markdown("### Quanto mais corrente, menos bateria")
        st.markdown('<div class="box">1C é a corrente que esvaziaria a bateria em uma hora (3 A); 2C, em meia hora. '
                    'Mais corrente é mais queda dentro da célula: a curva desce, bate em 2,50 V antes e a célula '
                    'esquenta mais.</div>', unsafe_allow_html=True)
        rates = st.multiselect("Taxas de descarga para comparar", [0.2, 0.5, 1.0, 2.0, 3.0], [0.5, 1.0, 2.0],
                               format_func=lambda v: f"{v:g}C ({3 * v:g} A)")
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
        else:
            st.info("Escolha pelo menos uma taxa para comparar.", icon=":material/touch_app:")
        como_ler([
            ("Taxa (C)", "1C = 3 A", "Corrente em múltiplos da capacidade nominal."),
            ("Capacidade", "Ah", "Carga entregue até a célula 2 chegar a 2,50 V. Cai com corrente maior porque o limite chega antes."),
            ("Tensão média", "V", "Média da tensão nos terminais durante a descarga. Mais corrente, mais queda interna, tensão menor."),
            ("Temperatura máx.", "°C", "Aquecimento por I²R: dobrar a corrente quadruplica a potência perdida."),
            ("Duração", "min", "Tempo até o corte. A 2C, um pouco menos de meia hora."),
        ])
