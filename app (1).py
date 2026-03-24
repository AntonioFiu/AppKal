import streamlit as st
import pandas as pd
from datetime import date
import time
import uuid
from pymongo import MongoClient
from pymongo.server_api import ServerApi

st.set_page_config(page_title="Calorie Tracker App", page_icon="🍎", layout="wide")

st.markdown("""
    <style>
    .main-title {
        font-size: 44px;
        font-weight: 800;
        margin-bottom: 0;
    }
    .subtitle {
        font-size: 16px;
        color: #b0b0b0;
        margin-top: 0;
        margin-bottom: 25px;
    }
    </style>
""", unsafe_allow_html=True)

ENTRY_COLUMNS = [
    "ID", "Fecha", "Comida", "Alimento", "Porciones",
    "Calorías", "Proteína", "Carbohidratos", "Grasas", "Fuente"
]

LOG_COLUMNS = [
    "timestamp", "action", "status", "detail", "duration_ms"
]

FOOD_DATA = {
    "Manzana (1 pieza)": {"calories": 95, "protein": 0.5, "carbs": 25, "fat": 0.3},
    "Plátano (1 pieza)": {"calories": 105, "protein": 1.3, "carbs": 27, "fat": 0.4},
    "Pechuga de pollo (100 g)": {"calories": 165, "protein": 31, "carbs": 0, "fat": 3.6},
    "Arroz cocido (1 taza)": {"calories": 206, "protein": 4.3, "carbs": 45, "fat": 0.4},
    "Huevo (1 pieza)": {"calories": 78, "protein": 6, "carbs": 0.6, "fat": 5},
    "Pan integral (1 rebanada)": {"calories": 69, "protein": 3.6, "carbs": 12, "fat": 1.1},
    "Yogur griego (1 porción)": {"calories": 130, "protein": 11, "carbs": 9, "fat": 4},
    "Aguacate (1/2 pieza)": {"calories": 120, "protein": 1.5, "carbs": 6, "fat": 11},
}

MEALS = ["Desayuno", "Comida", "Cena", "Snack"]

@st.cache_resource
def get_client():
    return MongoClient(
        st.secrets["MONGODB_URI"],
        server_api=ServerApi("1")
    )

def get_entries_collection():
    client = get_client()
    db = client[st.secrets["MONGODB_DB"]]
    return db[st.secrets["MONGODB_COLLECTION"]]

def get_logs_collection():
    client = get_client()
    db = client[st.secrets["MONGODB_DB"]]
    return db[st.secrets.get("MONGODB_LOGS_COLLECTION", "logs")]

def load_entries():
    try:
        docs = list(get_entries_collection().find({}, {"_id": 0}))
        df = pd.DataFrame(docs)
        if df.empty:
            return pd.DataFrame(columns=ENTRY_COLUMNS)
        for col in ENTRY_COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[ENTRY_COLUMNS].copy()
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        for col in ["Porciones", "Calorías", "Proteína", "Carbohidratos", "Grasas"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return df
    except Exception as e:
        st.error(f"Error al cargar datos desde MongoDB: {e}")
        return pd.DataFrame(columns=ENTRY_COLUMNS)

def load_logs():
    try:
        docs = list(get_logs_collection().find({}, {"_id": 0}))
        df = pd.DataFrame(docs)
        if df.empty:
            return pd.DataFrame(columns=LOG_COLUMNS)
        for col in LOG_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[LOG_COLUMNS].copy()
    except Exception as e:
        st.error(f"Error al cargar logs desde MongoDB: {e}")
        return pd.DataFrame(columns=LOG_COLUMNS)

def log_event(action, status, detail, duration_ms=0):
    try:
        get_logs_collection().insert_one({
            "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "status": status,
            "detail": detail,
            "duration_ms": round(float(duration_ms), 2)
        })
    except Exception as e:
        st.warning(f"No se pudo guardar el log: {e}")

def add_entry_and_persist(entry):
    try:
        get_entries_collection().insert_one(entry)
        current_df = load_entries()
        st.session_state.entries = current_df.to_dict("records")
    except Exception as e:
        st.error(f"Error al guardar en MongoDB: {e}")

def delete_all_entries():
    try:
        get_entries_collection().delete_many({})
        st.session_state.entries = []
        st.session_state.custom_foods = {}
    except Exception as e:
        st.error(f"Error al borrar registros: {e}")

def build_custom_foods(entries_df):
    custom_foods = {}
    if entries_df.empty:
        return custom_foods
    custom_entries = entries_df[entries_df["Fuente"] == "custom_sidebar"].copy()
    if custom_entries.empty:
        return custom_foods
    for _, row in custom_entries.iterrows():
        grams = float(row["Porciones"]) if pd.notna(row["Porciones"]) else 0
        if grams > 0:
            custom_foods[f'{row["Alimento"]} (custom)'] = {
                "calories": float(row["Calorías"]) * 100 / grams,
                "protein": float(row["Proteína"]) * 100 / grams,
                "carbs": float(row["Carbohidratos"]) * 100 / grams,
                "fat": float(row["Grasas"]) * 100 / grams
            }
    return custom_foods

def get_all_foods():
    foods = FOOD_DATA.copy()
    foods.update(st.session_state.custom_foods)
    return foods

def validate_standard_entry(food_name, servings):
    errors = []
    if not food_name or str(food_name).strip() == "":
        errors.append("Selecciona un alimento válido.")
    if servings <= 0:
        errors.append("Las porciones deben ser mayores a 0.")
    if servings > 10:
        errors.append("Las porciones no pueden ser mayores a 10 en una sola captura.")
    return errors

def validate_custom_entry(name, grams, cals_100, protein_100, carbs_100, fat_100):
    errors = []
    if not name or name.strip() == "":
        errors.append("Escribe el nombre del alimento.")
    if grams <= 0:
        errors.append("La cantidad consumida en gramos debe ser mayor a 0.")
    if grams > 5000:
        errors.append("La cantidad consumida en gramos es demasiado alta.")
    if any(v < 0 for v in [cals_100, protein_100, carbs_100, fat_100]):
        errors.append("Los valores nutricionales no pueden ser negativos.")
    if cals_100 == 0 and protein_100 == 0 and carbs_100 == 0 and fat_100 == 0:
        errors.append("Agrega al menos un valor nutricional mayor a 0.")
    return errors

def create_standard_entry(selected_date, meal, food, servings, food_info):
    return {
        "ID": str(uuid.uuid4()),
        "Fecha": str(selected_date),
        "Comida": meal,
        "Alimento": food,
        "Porciones": round(float(servings), 2),
        "Calorías": round(food_info["calories"] * servings, 1),
        "Proteína": round(food_info["protein"] * servings, 1),
        "Carbohidratos": round(food_info["carbs"] * servings, 1),
        "Grasas": round(food_info["fat"] * servings, 1),
        "Fuente": "standard"
    }

def create_custom_entry(selected_date, meal, name, grams, cals_100, protein_100, carbs_100, fat_100):
    return {
        "ID": str(uuid.uuid4()),
        "Fecha": str(selected_date),
        "Comida": meal,
        "Alimento": name,
        "Porciones": round(float(grams), 2),
        "Calorías": round(cals_100 * grams / 100, 1),
        "Proteína": round(protein_100 * grams / 100, 1),
        "Carbohidratos": round(carbs_100 * grams / 100, 1),
        "Grasas": round(fat_100 * grams / 100, 1),
        "Fuente": "custom_sidebar"
    }

def get_metrics(df):
    if df.empty:
        return {
            "total_registros": 0,
            "dias_activos": 0,
            "calorias_promedio": 0,
            "feature_mas_usada": "Sin datos",
            "tiempo_promedio_ms": 0
        }
    work = df.copy()
    work["Fecha"] = pd.to_datetime(work["Fecha"], errors="coerce")
    logs = load_logs()
    total_registros = len(work)
    dias_activos = work["Fecha"].dt.date.nunique()
    calories_by_day = work.groupby(work["Fecha"].dt.date)["Calorías"].sum()
    calorias_promedio = round(calories_by_day.mean(), 1) if not calories_by_day.empty else 0
    feature_mas_usada = work["Comida"].mode().iloc[0] if not work["Comida"].mode().empty else "Sin datos"
    add_logs = logs[logs["action"].isin(["add_standard_food", "add_custom_food"])] if not logs.empty else pd.DataFrame()
    tiempo_promedio_ms = round(pd.to_numeric(add_logs["duration_ms"], errors="coerce").fillna(0).mean(), 2) if not add_logs.empty else 0
    return {
        "total_registros": total_registros,
        "dias_activos": dias_activos,
        "calorias_promedio": calorias_promedio,
        "feature_mas_usada": feature_mas_usada,
        "tiempo_promedio_ms": tiempo_promedio_ms
    }

if "daily_goal" not in st.session_state:
    st.session_state.daily_goal = 2000

if "entries" not in st.session_state:
    initial_entries_df = load_entries()
    st.session_state.entries = initial_entries_df.to_dict("records")

if "custom_foods" not in st.session_state:
    existing_df = pd.DataFrame(st.session_state.entries)
    st.session_state.custom_foods = build_custom_foods(existing_df) if not existing_df.empty else {}

with st.sidebar:
    st.title("⚙️ Configuración")
    st.session_state.daily_goal = st.number_input(
        "Meta diaria de calorías",
        min_value=1000,
        max_value=5000,
        value=st.session_state.daily_goal,
        step=50
    )
    selected_date = st.date_input("Fecha", value=date.today())
    st.markdown("---")
    st.subheader("➕ Añadir alimento por gramaje")
    st.caption("Agrega un alimento personalizado con datos por 100 g")

    with st.form("sidebar_custom_food_form"):
        custom_name = st.text_input("Nombre del alimento")
        custom_meal = st.selectbox("Tipo de comida", MEALS, key="custom_meal")
        cals_100 = st.number_input("Calorías por 100 g", min_value=0.0, value=0.0, step=1.0)
        protein_100 = st.number_input("Proteína por 100 g", min_value=0.0, value=0.0, step=1.0)
        carbs_100 = st.number_input("Carbohidratos por 100 g", min_value=0.0, value=0.0, step=1.0)
        fat_100 = st.number_input("Grasas por 100 g", min_value=0.0, value=0.0, step=1.0)
        grams = st.number_input("Cantidad consumida (g)", min_value=0.0, value=100.0, step=10.0)
        add_custom = st.form_submit_button("Agregar alimento personalizado")

        if add_custom:
            start_time = time.perf_counter()
            errors = validate_custom_entry(custom_name, grams, cals_100, protein_100, carbs_100, fat_100)
            if errors:
                for err in errors:
                    st.warning(err)
                log_event("add_custom_food", "failed", " | ".join(errors), (time.perf_counter() - start_time) * 1000)
            else:
                entry = create_custom_entry(selected_date, custom_meal, custom_name.strip(), grams, cals_100, protein_100, carbs_100, fat_100)
                st.session_state.custom_foods[f"{custom_name.strip()} (custom)"] = {
                    "calories": cals_100,
                    "protein": protein_100,
                    "carbs": carbs_100,
                    "fat": fat_100
                }
                add_entry_and_persist(entry)
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_event("add_custom_food", "success", f"{custom_name.strip()} agregado", duration_ms)
                st.success(f"{custom_name.strip()} agregado correctamente.")

st.markdown('<p class="main-title">🍎 Calorie Tracker App</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Controla tus calorías, registra alimentos y visualiza tu progreso de forma simple.</p>', unsafe_allow_html=True)

df = pd.DataFrame(st.session_state.entries)
if not df.empty:
    for col in ENTRY_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[ENTRY_COLUMNS].copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

with st.expander("🥗 Registro rápido de alimentos", expanded=True):
    st.image("https://images.unsplash.com/photo-1547592180-85f173990554?w=1200", width=500)
    foods = get_all_foods()
    search = st.text_input("Buscar alimento", placeholder="Ej. arroz, pollo, huevo")
    filtered_foods = [f for f in foods if search.lower() in f.lower()]
    if not filtered_foods:
        filtered_foods = list(foods.keys())
    col1, col2 = st.columns(2)
    with col1:
        food = st.selectbox("Selecciona alimento", filtered_foods)
    with col2:
        meal = st.selectbox("Tipo de comida", MEALS)
    servings = st.number_input("Porciones", min_value=0.5, max_value=10.0, value=1.0, step=0.5)

    if st.button("Agregar alimento"):
        start_time = time.perf_counter()
        errors = validate_standard_entry(food, servings)
        if errors:
            for err in errors:
                st.warning(err)
            log_event("add_standard_food", "failed", " | ".join(errors), (time.perf_counter() - start_time) * 1000)
        else:
            entry = create_standard_entry(selected_date, meal, food, servings, foods[food])
            add_entry_and_persist(entry)
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_event("add_standard_food", "success", f"{food} agregado", duration_ms)
            st.success(f"{food} agregado correctamente.")

df = pd.DataFrame(st.session_state.entries)
if not df.empty:
    for col in ENTRY_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[ENTRY_COLUMNS].copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    today_df = df[df["Fecha"].dt.date == selected_date].copy()
else:
    today_df = pd.DataFrame(columns=ENTRY_COLUMNS)

with st.expander("📊 Resumen diario", expanded=False):
    st.image("https://images.unsplash.com/photo-1576402187878-974f70c890a5?w=1200", width=500)
    if not today_df.empty:
        calories = today_df["Calorías"].sum()
        remaining = st.session_state.daily_goal - calories
        c1, c2, c3 = st.columns(3)
        c1.metric("Consumidas", f"{int(calories)} kcal")
        c2.metric("Meta", f"{st.session_state.daily_goal} kcal")
        c3.metric("Restantes", f"{int(remaining)} kcal")
        progress = min(calories / st.session_state.daily_goal, 1.0)
        st.progress(progress)
    else:
        st.info("Todavía no hay alimentos registrados para esta fecha.")

with st.expander("📋 Tus alimentos registrados", expanded=False):
    st.image("https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=1200", width=500)
    if not df.empty:
        show_df = df.copy()
        show_df["Fecha"] = show_df["Fecha"].dt.date
        st.dataframe(show_df.drop(columns=["ID", "Fuente"]), use_container_width=True)
        export_df = show_df.drop(columns=["ID"], errors="ignore")
        st.download_button(
            label="Descargar respaldo CSV",
            data=export_df.to_csv(index=False, encoding="utf-8-sig"),
            file_name="calorie_tracker_backup.csv",
            mime="text/csv"
        )
        logs_df = load_logs()
        st.download_button(
            label="Descargar logs CSV",
            data=logs_df.to_csv(index=False, encoding="utf-8-sig"),
            file_name="calorie_tracker_logs.csv",
            mime="text/csv"
        )
    else:
        st.info("No hay registros todavía.")

with st.expander("🥑 Macronutrientes del día", expanded=False):
    st.image("https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200", width=500)
    if not today_df.empty:
        macros = pd.DataFrame({
            "Macro": ["Proteína", "Carbohidratos", "Grasas"],
            "Gramos": [
                today_df["Proteína"].sum(),
                today_df["Carbohidratos"].sum(),
                today_df["Grasas"].sum()
            ]
        })
        st.bar_chart(macros.set_index("Macro"))
    else:
        st.info("No hay datos suficientes para mostrar macronutrientes.")

with st.expander("📈 Gráficas de progreso", expanded=False):
    st.image("https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=1200", width=500)
    if not df.empty:
        view = st.selectbox("Ver progreso por", ["Diario", "Semanal", "Mensual"])
        progress_df = df.copy()
        if view == "Diario":
            chart_df = progress_df.groupby("Fecha", as_index=False)["Calorías"].sum()
            chart_df = chart_df.sort_values("Fecha")
            chart_df["Fecha"] = chart_df["Fecha"].dt.date
            st.line_chart(chart_df.set_index("Fecha")["Calorías"])
        elif view == "Semanal":
            progress_df["Semana"] = progress_df["Fecha"].dt.to_period("W").astype(str)
            chart_df = progress_df.groupby("Semana", as_index=False)["Calorías"].sum()
            st.bar_chart(chart_df.set_index("Semana")["Calorías"])
        else:
            progress_df["Mes"] = progress_df["Fecha"].dt.to_period("M").astype(str)
            chart_df = progress_df.groupby("Mes", as_index=False)["Calorías"].sum()
            st.bar_chart(chart_df.set_index("Mes")["Calorías"])
        st.markdown("#### Métricas del uso")
        metrics = get_metrics(df)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Registros", metrics["total_registros"])
        m2.metric("Días activos", metrics["dias_activos"])
        m3.metric("Promedio diario", f'{metrics["calorias_promedio"]} kcal')
        m4.metric("Tiempo promedio", f'{metrics["tiempo_promedio_ms"]} ms')
        st.caption(f'Tipo de comida más registrado: {metrics["feature_mas_usada"]}')
        logs_df = load_logs()
        if not logs_df.empty:
            st.markdown("#### Eventos recientes")
            st.dataframe(logs_df.tail(8).iloc[::-1], use_container_width=True)
    else:
        st.info("Necesitas más registros para ver el progreso.")

with st.expander("💡 Sugerencia del día", expanded=False):
    st.image("https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=1200", width=500)
    if not today_df.empty:
        calories = today_df["Calorías"].sum()
        if calories < st.session_state.daily_goal * 0.5:
            st.info("Vas por debajo de tu meta. Puedes agregar una comida balanceada o un snack saludable.")
        elif calories <= st.session_state.daily_goal:
            st.success("Vas dentro de tu meta diaria. Buen trabajo manteniendo el balance.")
        else:
            st.warning("Superaste tu meta diaria. Mañana puedes ajustar porciones.")
    else:
        st.info("Registra alimentos para recibir sugerencias.")

st.markdown("---")
if st.button("Borrar registros"):
    start_time = time.perf_counter()
    delete_all_entries()
    duration_ms = (time.perf_counter() - start_time) * 1000
    log_event("delete_all_entries", "success", "Se borraron todos los registros", duration_ms)
    st.rerun()
