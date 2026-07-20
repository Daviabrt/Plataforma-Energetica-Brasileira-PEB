"""
Plataforma de Análise para Localização de Data Centers
Versão Streamlit - Interface completa com mapa interativo
"""

import streamlit as st
import pandas as pd
import json
import requests
from datetime import datetime
import folium
from streamlit_folium import folium_static
from folium.plugins import MarkerCluster
import plotly.express as px
import plotly.graph_objects as go
from scipy.spatial import KDTree
import numpy as np

# ============================================
# CONFIGURAÇÕES INICIAIS
# ============================================

st.set_page_config(
    page_title="Data Center Site Analyzer",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    .metric-card {
        background: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        margin: 5px;
    }
    .metric-value {
        font-size: 28px;
        font-weight: bold;
        color: #1f77b4;
    }
    .metric-label {
        font-size: 14px;
        color: #666;
    }
    .status-high {
        color: #2ecc71;
        font-weight: bold;
    }
    .status-medium {
        color: #f39c12;
        font-weight: bold;
    }
    .status-low {
        color: #e74c3c;
        font-weight: bold;
    }
    .region-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        cursor: pointer;
        transition: all 0.3s;
    }
    .region-card:hover {
        background: #f8f9fa;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .region-card.selected {
        border-color: #1f77b4;
        background: #e3f2fd;
    }
    .fiber-indicator {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
    }
    .fiber-high {
        background: #d4edda;
        color: #155724;
    }
    .fiber-medium {
        background: #fff3cd;
        color: #856404;
    }
    .fiber-low {
        background: #f8d7da;
        color: #721c24;
    }
    .stButton > button {
        width: 100%;
    }
    .sidebar-section {
        margin-bottom: 20px;
        padding: 10px;
        background: #f8f9fa;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def load_data():
    """Carrega os dados dos arquivos JSON"""
    data = {
        'cables': [],
        'water': [],
        'energy': [],
        'municipalities': []
    }
    
    try:
        with open('cables.json', 'r', encoding='utf-8') as f:
            data['cables'] = json.load(f)
    except:
        st.warning("Arquivo cables.json não encontrado")
    
    try:
        with open('water.json', 'r', encoding='utf-8') as f:
            data['water'] = json.load(f)
    except:
        st.warning("Arquivo water.json não encontrado")
    
    try:
        with open('energy.json', 'r', encoding='utf-8') as f:
            data['energy'] = json.load(f)
    except:
        st.warning("Arquivo energy.json não encontrado")
        # Tenta buscar da ANEEL
        if st.button("🔄 Buscar dados da ANEEL"):
            data['energy'] = fetch_aneel_data()
    
    return data

def fetch_aneel_data():
    """Busca dados atualizados da ANEEL"""
    with st.spinner("Buscando dados da ANEEL..."):
        try:
            url = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search"
            params = {
                "resource_id": "2f65a1b0-19b8-4360-8238-b34ab4693d55",
                "limit": 5000
            }
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            records = data.get('result', {}).get('records', [])
            
            # Normaliza os dados
            normalized = []
            for record in records:
                lat = parse_brazilian_number(record.get('NumCoordNEmpreendimento'))
                lng = parse_brazilian_number(record.get('NumCoordEEmpreendimento'))
                if lat and lng and lat != 0 and lng != 0:
                    normalized.append({
                        'id': record.get('_id'),
                        'name': record.get('NomEmpreendimento', ''),
                        'type': classify_energy_type(record.get('NomFonteCombustivel', '')),
                        'capacity_mw': kw_to_mw(record.get('MdaPotenciaOutorgadaKw')),
                        'owner': record.get('DscPropriRegimePariticipacao', ''),
                        'city': record.get('DscMuninicpios', '').split(' - ')[0],
                        'state': record.get('SigUFPrincipal', ''),
                        'lat': lat,
                        'lng': lng,
                        'phase': record.get('DscFaseUsina', '')
                    })
            
            return normalized
        except Exception as e:
            st.error(f"Erro ao buscar dados da ANEEL: {e}")
            return []

def parse_brazilian_number(value):
    """Converte número no formato brasileiro para float"""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except:
        return None

def kw_to_mw(value):
    """Converte kW para MW"""
    kw = parse_brazilian_number(value)
    return kw / 1000 if kw else 0

def classify_energy_type(value):
    """Classifica o tipo de energia"""
    if not value:
        return "Outro"
    value = value.lower()
    if "vento" in value:
        return "Eólica"
    if "sol" in value or "fotovoltaica" in value:
        return "Solar"
    if "hidráulico" in value or "hídrica" in value:
        return "Hidro"
    if "biomassa" in value or "cana" in value or "biogás" in value:
        return "Biomassa"
    return "Outro"

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calcula distância em km entre dois pontos (Haversine)"""
    import math
    R = 6371
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def get_energy_stats(energy_data):
    """Calcula estatísticas das usinas"""
    df = pd.DataFrame(energy_data)
    
    stats = {
        'total': len(df),
        'total_capacity': df['capacity_mw'].sum() if 'capacity_mw' in df else 0,
        'by_type': df['type'].value_counts().to_dict() if 'type' in df else {},
        'by_state': df['state'].value_counts().to_dict() if 'state' in df else {},
        'top_plants': df.nlargest(10, 'capacity_mw')[['name', 'capacity_mw', 'type', 'city', 'state']].to_dict('records') if 'capacity_mw' in df else []
    }
    return stats

def get_region_score(region_data, weights):
    """Calcula score de uma região"""
    scores = region_data.get('scores', {})
    total_weight = sum(weights.values())
    weighted_sum = sum(scores.get(key, 0) * weight for key, weight in weights.items())
    return round(weighted_sum / total_weight) if total_weight > 0 else 0

def get_score_class(score):
    """Classifica o score"""
    if score >= 80:
        return "Alta aptidão", "high"
    elif score >= 60:
        return "Condicionada", "medium"
    else:
        return "Alto risco", "low"

# ============================================
# FUNÇÕES DE RENDERIZAÇÃO DO MAPA
# ============================================

def create_base_map(center=[-15.7801, -47.9292], zoom=4):
    """Cria o mapa base com estilo escuro"""
    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles='CartoDB dark_matter'
    )
    return m

def add_energy_layers(m, energy_data, show=True):
    """Adiciona camada de energia ao mapa"""
    if not show or not energy_data:
        return
    
    # Agrupa por célula (grid)
    df = pd.DataFrame(energy_data)
    if df.empty:
        return
    
    # Cria grid de células
    lat_step = 0.5
    lng_step = 0.5
    
    df['lat_bin'] = (df['lat'] / lat_step).round() * lat_step
    df['lng_bin'] = (df['lng'] / lng_step).round() * lng_step
    
    grid = df.groupby(['lat_bin', 'lng_bin']).agg({
        'capacity_mw': 'sum',
        'type': lambda x: list(x)
    }).reset_index()
    
    # Cores por tipo
    type_colors = {
        'Solar': '#facc15',
        'Eólica': '#22c55e',
        'Hidro': '#38bdf8',
        'Biomassa': '#fb923c',
        'Outro': '#94a3b8'
    }
    
    for _, row in grid.iterrows():
        lat = row['lat_bin']
        lng = row['lng_bin']
        capacity = row['capacity_mw']
        types = row['type']
        
        # Cor baseada no tipo dominante
        if types:
            dominant = max(set(types), key=types.count)
            color = type_colors.get(dominant, '#94a3b8')
        else:
            color = '#94a3b8'
        
        # Tamanho baseado na capacidade
        radius = max(3, min(15, 3 + capacity / 100))
        popup_text = f"""
        <b>Energia no grid</b><br>
        Capacidade: {capacity:.1f} MW<br>
        Tipos: {', '.join(set(types)) if types else 'N/A'}<br>
        Usinas: {len(types) if types else 0}
        """
        
        folium.CircleMarker(
            location=[lat, lng],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.6,
            popup=popup_text,
            weight=1
        ).add_to(m)

def add_water_layers(m, water_data, show=True):
    """Adiciona camada de água ao mapa"""
    if not show or not water_data:
        return
    
    for w in water_data[:200]:  # Limita para performance
        popup_text = f"""
        <b>{w.get('city', '')}</b><br>
        Estado: {w.get('state', '')}<br>
        População: {w.get('population', 0):,}<br>
        Serviço: {w.get('service_type', '')}
        """
        
        folium.CircleMarker(
            location=[w.get('lat', 0), w.get('lng', 0)],
            radius=3,
            color='#0ea5e9',
            fill=True,
            fill_color='#0ea5e9',
            fill_opacity=0.7,
            popup=popup_text,
            weight=1
        ).add_to(m)

def add_cables_layers(m, cables_data, show=True):
    """Adiciona camada de cabos submarinos ao mapa"""
    if not show or not cables_data:
        return
    
    for cable in cables_data:
        geometry = cable.get('geometry', {})
        coords = geometry.get('coordinates', [])
        
        # Converte coordenadas para formato Folium
        lines = []
        if geometry.get('type') == 'LineString':
            if coords:
                lines.append([[lat, lng] for lng, lat in coords])
        elif geometry.get('type') == 'MultiLineString':
            for line in coords:
                if line:
                    lines.append([[lat, lng] for lng, lat in line])
        
        for line in lines:
            if len(line) > 1:
                folium.PolyLine(
                    locations=line,
                    color='#3b82f6',
                    weight=2,
                    opacity=0.6,
                    popup=f"{cable.get('name', 'Cabo')}<br>Ano: {cable.get('rfs_year', 'N/A')}"
                ).add_to(m)

def add_site_marker(m, lat, lng, radius_km=100, score=None):
    """Adiciona marcador do site e círculo de raio"""
    if not lat or not lng:
        return
    
    # Marcador principal
    folium.Marker(
        location=[lat, lng],
        popup=f"📍 Site<br>Raio: {radius_km} km<br>Score: {score if score else 'N/A'}",
        icon=folium.Icon(color='red', icon='server', prefix='fa')
    ).add_to(m)
    
    # Círculo de raio
    folium.Circle(
        location=[lat, lng],
        radius=radius_km * 1000,
        color='#0c6b58',
        fill=True,
        fill_color='#0c6b58',
        fill_opacity=0.08,
        weight=2,
        popup=f"Raio de análise: {radius_km} km"
    ).add_to(m)

# ============================================
# FUNÇÕES DE ANÁLISE
# ============================================

def analyze_site(lat, lng, radius_km, data, weights):
    """Analisa recursos no raio do site"""
    energy_in_radius = []
    water_in_radius = []
    cables_in_radius = []
    
    # Energia
    for plant in data.get('energy', []):
        dist = calculate_distance(lat, lng, plant.get('lat', 0), plant.get('lng', 0))
        if dist <= radius_km:
            energy_in_radius.append({
                **plant,
                'distance_km': round(dist, 1)
            })
    
    # Água
    for w in data.get('water', []):
        dist = calculate_distance(lat, lng, w.get('lat', 0), w.get('lng', 0))
        if dist <= radius_km:
            water_in_radius.append({
                **w,
                'distance_km': round(dist, 1)
            })
    
    # Cabos (simplificado)
    for cable in data.get('cables', []):
        # Pega primeiro ponto do cabo
        coords = cable.get('geometry', {}).get('coordinates', [])
        if coords and coords[0] and len(coords[0]) > 0:
            cable_lat = coords[0][0][1] if coords[0][0] else 0
            cable_lng = coords[0][0][0] if coords[0][0] else 0
            dist = calculate_distance(lat, lng, cable_lat, cable_lng)
            if dist <= radius_km:
                cables_in_radius.append({
                    **cable,
                    'distance_km': round(dist, 1)
                })
    
    # Estatísticas
    total_capacity = sum(p.get('capacity_mw', 0) for p in energy_in_radius)
    types = {}
    for p in energy_in_radius:
        t = p.get('type', 'Outro')
        types[t] = types.get(t, 0) + p.get('capacity_mw', 0)
    
    return {
        'energy': {
            'count': len(energy_in_radius),
            'total_capacity_mw': round(total_capacity, 1),
            'types': types,
            'plants': energy_in_radius[:10]
        },
        'water': {
            'count': len(water_in_radius),
            'services': list(set(w.get('service_type', '') for w in water_in_radius)),
            'municipalities': len(set(w.get('city', '') for w in water_in_radius)),
            'items': water_in_radius[:5]
        },
        'cables': {
            'count': len(cables_in_radius),
            'nearest': cables_in_radius[0] if cables_in_radius else None
        }
    }

def generate_regions(data):
    """Gera regiões candidatas a partir dos dados de água"""
    regions = []
    
    # Agrupa por estado e cidade
    grouped = {}
    for w in data.get('water', []):
        key = f"{w.get('city', '')}_{w.get('state', '')}"
        if key not in grouped:
            grouped[key] = {
                'id': key,
                'name': w.get('city', ''),
                'state': w.get('state', ''),
                'lat': w.get('lat', 0),
                'lng': w.get('lng', 0),
                'population': w.get('population', 0),
                'services': set()
            }
        grouped[key]['services'].add(w.get('service_type', ''))
    
    # Para cada região, calcula scores
    for key, region in grouped.items():
        # Energia no entorno (100km)
        energy_near = []
        for plant in data.get('energy', []):
            dist = calculate_distance(
                region['lat'], region['lng'],
                plant.get('lat', 0), plant.get('lng', 0)
            )
            if dist <= 100:
                energy_near.append(plant)
        
        # Score de energia renovável
        total_capacity = sum(p.get('capacity_mw', 0) for p in energy_near)
        renewable_score = min(100, total_capacity * 2)  # 50 MW = 100 pontos
        
        # Score de água
        water_score = 80 if len(region['services']) >= 2 else 60 if len(region['services']) == 1 else 30
        
        # Score de conectividade (baseado em cabos próximos)
        cable_score = 50  # Valor padrão
        for cable in data.get('cables', []):
            coords = cable.get('geometry', {}).get('coordinates', [])
            if coords and coords[0] and len(coords[0]) > 0:
                cable_lat = coords[0][0][1] if coords[0][0] else 0
                cable_lng = coords[0][0][0] if coords[0][0] else 0
                dist = calculate_distance(region['lat'], region['lng'], cable_lat, cable_lng)
                if dist <= 100:
                    cable_score = max(cable_score, 100 - dist)
                    break
        
        # Score de licenciamento (baseado na população)
        pop = region['population']
        licensing_score = min(100, pop / 5000) if pop > 0 else 30
        
        region['scores'] = {
            'renewables': renewable_score,
            'grid': 50,  # Valor padrão, poderia ser calculado com dados de transmissão
            'water': water_score,
            'connectivity': round(cable_score),
            'licensing': round(licensing_score)
        }
        
        region['services'] = list(region['services'])
        region['energy_count'] = len(energy_near)
        region['energy_capacity'] = round(total_capacity, 1)
        
        regions.append(region)
    
    return regions

# ============================================
# INTERFACE PRINCIPAL STREAMLIT
# ============================================

def main():
    # Sidebar - Controles
    with st.sidebar:
        st.title("🏢 Data Center Analyzer")
        st.markdown("---")
        
        # Configurações de peso
        st.subheader("⚙️ Pesos dos Critérios")
        
        weights = {
            'renewables': st.slider("Energia Renovável", 0, 10, 5),
            'grid': st.slider("Infraestrutura Elétrica", 0, 10, 4),
            'water': st.slider("Segurança Hídrica", 0, 10, 5),
            'connectivity': st.slider("Conectividade", 0, 10, 3),
            'licensing': st.slider("Segurança Regulatória", 0, 10, 4)
        }
        
        st.markdown("---")
        
        # Configurações do site
        st.subheader("📡 Configurações do Site")
        radius_km = st.slider("Raio de Análise (km)", 10, 300, 100)
        it_load_mw = st.number_input("Carga TI (MW)", min_value=1, max_value=500, value=50)
        
        st.markdown("---")
        
        # Filtros
        st.subheader("🔍 Filtros")
        show_energy = st.checkbox("Mostrar Energia", value=True)
        show_water = st.checkbox("Mostrar Água", value=True)
        show_cables = st.checkbox("Mostrar Cabos", value=True)
        
        st.markdown("---")
        
        # Botões de ação
        if st.button("🔄 Atualizar Dados"):
            st.cache_data.clear()
            st.rerun()
    
    # Área principal
    st.title("📍 Análise de Localização para Data Centers")
    st.markdown("Clique no mapa para simular um data center e analisar os recursos disponíveis.")
    
    # Carrega dados
    with st.spinner("Carregando dados..."):
        data = load_data()
    
    if not data['energy'] and not data['water']:
        st.error("❌ Nenhum dado carregado. Verifique os arquivos JSON.")
        return
    
    # Estatísticas rápidas
    energy_stats = get_energy_stats(data['energy'])
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("⚡ Usinas", energy_stats['total'])
    with col2:
        st.metric("🔌 Capacidade Total", f"{energy_stats['total_capacity']:.0f} MW")
    with col3:
        st.metric("💧 Municípios com Água", len(data['water']))
    with col4:
        st.metric("🌊 Cabos Submarinos", len(data['cables']))
    
    # Layout principal: Mapa + Resultados
    col_map, col_results = st.columns([3, 2])
    
    with col_map:
        # Cria mapa
        m = create_base_map()
        
        # Adiciona camadas
        add_energy_layers(m, data['energy'], show_energy)
        add_water_layers(m, data['water'], show_water)
        add_cables_layers(m, data['cables'], show_cables)
        
        # Site no mapa (se existir)
        if 'site_lat' in st.session_state and 'site_lng' in st.session_state:
            score = st.session_state.get('site_score', None)
            add_site_marker(m, st.session_state.site_lat, st.session_state.site_lng, radius_km, score)
        
        # Exibe mapa
        folium_static(m, width=800, height=600)
        
        # Instrução de clique
        st.caption("💡 Clique no mapa para adicionar/atualizar o site")
    
    with col_results:
        st.subheader("📊 Resultados da Análise")
        
        # Se tem site, mostra análise
        if 'site_lat' in st.session_state and 'site_lng' in st.session_state:
            site_analysis = analyze_site(
                st.session_state.site_lat,
                st.session_state.site_lng,
                radius_km,
                data,
                weights
            )
            
            # Score geral
            energy_score = min(100, site_analysis['energy']['total_capacity_mw'] * 2)
            water_score = 80 if site_analysis['water']['count'] > 0 else 30
            cable_score = 100 if site_analysis['cables']['count'] > 0 else 30
            
            total_score = int((energy_score * weights['renewables'] +
                             water_score * weights['water'] +
                             cable_score * weights['connectivity']) / 
                            (weights['renewables'] + weights['water'] + weights['connectivity']))
            
            st.session_state.site_score = total_score
            
            # Score card
            status_label, status_class = get_score_class(total_score)
            color = "green" if status_class == "high" else "orange" if status_class == "medium" else "red"
            
            st.markdown(f"""
            <div style="background: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; border-left: 4px solid {color};">
                <div style="font-size: 14px; color: #666;">APTIDÃO GERAL</div>
                <div style="font-size: 48px; font-weight: bold; color: {color};">{total_score}</div>
                <div style="font-size: 16px; color: {color};">{status_label}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Detalhes da análise
            with st.expander("📋 Detalhes da Análise", expanded=True):
                # Energia
                st.markdown("**⚡ Energia Renovável**")
                st.metric("Usinas", site_analysis['energy']['count'])
                st.metric("Capacidade", f"{site_analysis['energy']['total_capacity_mw']:.1f} MW")
                
                if site_analysis['energy']['types']:
                    st.write("**Tipos:**")
                    for t, cap in site_analysis['energy']['types'].items():
                        st.progress(min(1.0, cap / 1000), text=f"{t}: {cap:.1f} MW")
                
                # Água
                st.markdown("**💧 Infraestrutura Hídrica**")
                st.metric("Pontos", site_analysis['water']['count'])
                st.metric("Municípios", site_analysis['water']['municipalities'])
                if site_analysis['water']['services']:
                    st.write(f"**Serviços:** {', '.join(site_analysis['water']['services'])}")
                
                # Cabos
                st.markdown("**🌊 Conectividade**")
                st.metric("Cabos no raio", site_analysis['cables']['count'])
                if site_analysis['cables']['nearest']:
                    nearest = site_analysis['cables']['nearest']
                    st.write(f"**Mais próximo:** {nearest.get('name', 'N/A')} ({nearest.get('distance_km', 0):.1f} km)")
            
            # Ranking de usinas próximas
            if site_analysis['energy']['plants']:
                with st.expander("🏭 Usinas Mais Próximas"):
                    df_plants = pd.DataFrame(site_analysis['energy']['plants'])
                    st.dataframe(
                        df_plants[['name', 'type', 'capacity_mw', 'distance_km']],
                        use_container_width=True,
                        hide_index=True
                    )
        
        else:
            st.info("👆 Clique no mapa para adicionar um site e ver a análise")
        
        # Regiões candidatas
        st.subheader("🏆 Regiões Candidatas")
        
        with st.spinner("Gerando regiões..."):
            regions = generate_regions(data)
            # Ordena por score
            for r in regions:
                r['score'] = get_region_score(r, weights)
            regions = sorted(regions, key=lambda x: x['score'], reverse=True)[:10]
        
        for i, region in enumerate(regions[:5]):
            status_label, status_class = get_score_class(region['score'])
            color = "#2ecc71" if status_class == "high" else "#f39c12" if status_class == "medium" else "#e74c3c"
            
            with st.container():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"""
                    <div class="region-card" onclick="console.log('{region['id']}')">
                        <b>{region['name']}</b> - {region['state']}
                        <br><small>Pop: {region['population']:,} · Energia: {region.get('energy_capacity', 0):.1f} MW</small>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"<div style='text-align: right; font-size: 20px; color: {color};'>{region['score']}</div>", unsafe_allow_html=True)
        
        # Gráfico de distribuição de energia
        if data['energy']:
            st.subheader("📊 Distribuição de Energia")
            df_energy = pd.DataFrame(data['energy'])
            if 'type' in df_energy.columns:
                type_counts = df_energy['type'].value_counts().reset_index()
                type_counts.columns = ['Tipo', 'Quantidade']
                fig = px.pie(type_counts, values='Quantidade', names='Tipo', hole=0.4)
                st.plotly_chart(fig, use_container_width=True)

# ============================================
# INTERAÇÃO COM O MAPA (usando JavaScript)
# ============================================

# Adiciona script para capturar cliques no mapa
st.markdown("""
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Observa cliques no mapa Folium
    const mapElement = document.querySelector('.folium-map');
    if (mapElement) {
        mapElement.addEventListener('click', function(e) {
            // Obtém coordenadas do clique
            const lat = e.latlng.lat;
            const lng = e.latlng.lng;
            
            // Envia para o Streamlit via query params
            window.location.href = `?lat=${lat}&lng=${lng}`;
        });
    }
});
</script>
""", unsafe_allow_html=True)

# Processa clique no mapa (via URL params)
import streamlit as st
query_params = st.query_params
if 'lat' in query_params and 'lng' in query_params:
    try:
        st.session_state.site_lat = float(query_params['lat'])
        st.session_state.site_lng = float(query_params['lng'])
        st.rerun()
    except:
        pass

# ============================================
# EXECUÇÃO
# ============================================

if __name__ == "__main__":
    main()