import pandas as pd
import requests
import streamlit as st

# O endereço da vossa API que já está a correr
API_URL = "http://127.0.0.1:8000/api/v1/process-telemetry"

# Configuração da página
st.set_page_config(page_title="Campero Sistemas", page_icon="🚜", layout="wide")

st.title("🚜 Campero Sistemas")
st.markdown("### Fim da cegueira multimarca no campo.")

# Barra lateral para o utilizador fazer o carregamento (upload) dos ficheiros do pendrive
st.sidebar.header("📂 Ingestão de Dados")
st.sidebar.write("Faça o upload dos dados extraídos das máquinas.")
leituras_file = st.sidebar.file_uploader("1. Dados de Telemetria (CSV)", type=["csv"])
talhoes_file = st.sidebar.file_uploader("2. Cadastro de Talhões (CSV)", type=["csv"])

if st.sidebar.button("Processar Frota", type="primary"):
    if leituras_file and talhoes_file:
        with st.spinner("A processar dados no motor Campero..."):
            # Preparar os ficheiros para enviar para a API (simulando um formulário web)
            files = {
                "leituras_file": (leituras_file.name, leituras_file.getvalue(), "text/csv"),
                "talhoes_file": (talhoes_file.name, talhoes_file.getvalue(), "text/csv")
            }
            
            try:
                # Fazer o pedido POST à vossa API
                response = requests.post(API_URL, files=files)
                
                if response.status_code == 200:
                    dados = response.json()
                    st.success("Dados processados e unificados com sucesso!")
                    
                    resumo = dados.get("resumo_operacional", [])
                    alertas = dados.get("alertas", {})
                    
                    if resumo:
                        df_resumo = pd.DataFrame(resumo)
                        
                        # --- SECÇÃO 1: KPIs (Indicadores Principais) ---
                        st.markdown("---")
                        st.subheader("📊 Resumo Operacional da Frota")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Total Combustível (L)", f"{df_resumo['combustivel_consumido_l'].sum():.2f} L")
                        col2.metric("Total Horas Trabalhadas", f"{df_resumo['horas_trabalhadas'].sum():.2f} h")
                        col3.metric("Média de Consumo (L/h)", f"{df_resumo['litros_por_hora'].mean():.2f} L/h")
                        
                        # --- SECÇÃO 2: Alertas de Ociosidade e Roubo/Queda ---
                        st.markdown("---")
                        st.subheader("⚠️ Alertas de Ineficiência (Ação Necessária)")
                        
                        col_alert1, col_alert2 = st.columns(2)
                        
                        with col_alert1:
                            ociosidade = alertas.get("ociosidade", [])
                            if ociosidade:
                                st.error(f"🚨 {len(ociosidade)} evento(s) de motor ocioso detetado(s)!")
                                for o in ociosidade:
                                    st.write(f"- **Trator {o['tractor_id']}**: {o['mensagem']} *(Início: {o['inicio']})*")
                            else:
                                st.success("Nenhuma ociosidade anormal detetada.")
                                
                        with col_alert2:
                            quedas = alertas.get("queda_combustivel", [])
                            if quedas:
                                st.warning(f"⛽ {len(quedas)} queda(s) suspeita(s) de combustível!")
                                for q in quedas:
                                    st.write(f"- **Trator {q['tractor_id']}**: {q['mensagem']} *(Data: {q['quando']})*")
                            else:
                                st.success("Nenhuma queda abrupta de combustível detetada.")

                        # --- SECÇÃO 3: Tabelas e Gráficos ---
                        st.markdown("---")
                        st.subheader("📈 Análise Detalhada por Talhão e Trator")
                        
                        # Exibir a tabela limpa
                        st.dataframe(df_resumo, use_container_width=True)
                        
                        # Exibir um gráfico de barras simples cruzando Trator, Talhão e Consumo
                        if "litros_por_hectare" in df_resumo.columns:
                            st.write("**Consumo de Combustível (Litros por Hectare)**")
                            st.bar_chart(data=df_resumo, x="talhao_id", y="litros_por_hectare", color="tractor_id")
                            
                else:
                    st.error(f"Erro na API Campero: Código {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                st.error("Falha de comunicação. Verifique se o servidor FastAPI (Uvicorn) está a correr noutro terminal.")
    else:
        st.sidebar.warning("Por favor, faça o upload de ambos os ficheiros CSV para iniciar.")