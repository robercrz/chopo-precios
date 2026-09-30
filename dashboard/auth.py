# ============================================================
# dashboard/auth.py
# Sistema de Autenticación Criptográfica Robusta (PBKDF2-SHA256)
# ============================================================

import os
import hmac
import hashlib
import binascii
import streamlit as st

# Hash criptográfico de contraseñas (PBKDF2-HMAC-SHA256 con 100,000 iteraciones y sal fija)
# Las contraseñas en texto plano NUNCA se guardan en el repositorio ni en código.
DEFAULT_ADMIN_HASH = "pbkdf2_sha256:100000:6c636d5f63686f706f5f61646d5f3236:8d1e410c6d250f891852cfca6bac3b8d9c066f386c4c4af7b5c3821fff5efb2f"
DEFAULT_USER_HASH  = "pbkdf2_sha256:100000:6c636d5f63686f706f5f7573725f3236:489f58c3d135d306e095c69e8f8b85c73586a7558ec4ae08467195ee3cdfa1b6"


def verify_hash(password: str, stored_hash: str) -> bool:
    """Verifica una contraseña contra un hash PBKDF2-SHA256 con protección contra ataques de tiempo."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split(":")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = binascii.unhexlify(parts[2])
        expected_key = binascii.unhexlify(parts[3])
        calculated_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(calculated_key, expected_key)
    except Exception:
        return False


def get_configured_hashes():
    """Obtiene los hashes desde st.secrets, entorno o por defecto."""
    admin_h = DEFAULT_ADMIN_HASH
    user_h = DEFAULT_USER_HASH

    # 1. Checar st.secrets si existen hashes o contraseñas
    try:
        if hasattr(st, "secrets"):
            if "ADMIN_PASSWORD_HASH" in st.secrets:
                admin_h = str(st.secrets["ADMIN_PASSWORD_HASH"])
            if "APP_PASSWORD_HASH" in st.secrets:
                user_h = str(st.secrets["APP_PASSWORD_HASH"])
    except Exception:
        pass

    # 2. Checar variables de entorno
    admin_h = os.getenv("ADMIN_PASSWORD_HASH", admin_h)
    user_h = os.getenv("APP_PASSWORD_HASH", user_h)

    return admin_h, user_h


def logout():
    """Cierra la sesión actual y limpia el estado de sesión."""
    st.session_state["authenticated"] = False
    st.session_state["is_admin"] = False
    st.session_state.pop("user_favorites_set", None)
    st.rerun()


def require_auth() -> bool:
    """
    Control de acceso estricto a nivel de aplicación.
    Si el usuario no está autenticado, renderiza el formulario de acceso y DETIENE la ejecución (st.stop()).
    Garantiza que ningún componente ni dato se cargue sin autenticación previa.
    """
    # Verificación estricta de tipo booleano para prevenir inyección de session_state
    if st.session_state.get("authenticated") is True:
        return True

    # Asegurar que esté inicializado en False
    st.session_state["authenticated"] = False
    st.session_state["is_admin"] = False

    admin_hash, user_hash = get_configured_hashes()

    _, col_login, _ = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="background:#ffffff;padding:32px;border-radius:14px;box-shadow:0 6px 20px rgba(0,0,0,0.08);text-align:center;border:1px solid #e2e8f0;">
                <div style="font-size:2.8rem; margin-bottom:8px;">🔬</div>
                <h2 style="color:#0f172a;margin-bottom:6px;font-size:1.6rem;font-weight:800;">Chopo Price Intelligence</h2>
                <p style="color:#64748b;font-size:0.92rem;margin-bottom:22px;">Portal de Análisis y Comparativa de Precios · Mérida, Yucatán</p>
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px 14px; text-align:left; margin-bottom:18px;">
                    <span style="color:#334155; font-size:0.88rem; font-weight:600;">🔒 Acceso Restringido</span>
                    <p style="color:#64748b; font-size:0.8rem; margin:3px 0 0 0;">Ingresa tu clave de acceso autorizada para consultar el catálogo y las herramientas de comparación.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=True):
            password_input = st.text_input(
                "Clave de acceso",
                type="password",
                placeholder="Escribe tu clave de acceso aquí...",
                label_visibility="collapsed"
            )
            submit = st.form_submit_button("🔓 Ingresar al Portal", type="primary", use_container_width=True)

            if submit:
                # Comprobación segura contra hashes
                is_admin = verify_hash(password_input, admin_hash)
                is_user = verify_hash(password_input, user_hash)

                # Soporte de compatibilidad si st.secrets tiene contraseña en texto plano
                if not is_admin and not is_user:
                    try:
                        if hasattr(st, "secrets"):
                            if "ADMIN_PASSWORD" in st.secrets and password_input == str(st.secrets["ADMIN_PASSWORD"]):
                                is_admin = True
                            elif "APP_PASSWORD" in st.secrets and password_input == str(st.secrets["APP_PASSWORD"]):
                                is_user = True
                    except Exception:
                        pass

                if is_admin:
                    st.session_state["authenticated"] = True
                    st.session_state["is_admin"] = True
                    st.rerun()
                elif is_user:
                    st.session_state["authenticated"] = True
                    st.session_state["is_admin"] = False
                    st.rerun()
                else:
                    st.error("❌ Clave incorrecta. Por favor verifícala.")

        st.caption("🔒 Seguridad activa: Credenciales encriptadas con PBKDF2-SHA256. El nivel de permisos se asigna automáticamente.")

    # Detener la ejecución del script aquí para evitar cualquier fuga de datos o renderizado
    st.stop()
    return False
