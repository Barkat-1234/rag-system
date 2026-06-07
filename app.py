import streamlit as st
import requests
import json
from datetime import datetime

# API Configuration
API_BASE_URL = "http://localhost:8000/api/v1"

# Page configuration
st.set_page_config(
    page_title="RAG AI Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for ChatGPT-like styling
st.markdown("""
<style>
    /* Main chat container */
    .stApp {
        background-color: #343541;
    }
    
    /* Chat messages */
    .user-message {
        background-color: #40414F;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        color: white;
        font-family: 'Segoe UI', sans-serif;
    }
    
    .assistant-message {
        background-color: #444654;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        color: white;
        font-family: 'Segoe UI', sans-serif;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background-color: #202123;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: white !important;
    }
    
    /* Input box */
    .stTextInput input {
        background-color: #40414F;
        color: white;
        border: 1px solid #565869;
    }
    
    /* Buttons */
    .stButton button {
        background-color: #10A37F;
        color: white;
        border-radius: 5px;
        border: none;
    }
    
    .stButton button:hover {
        background-color: #1a7f64;
    }
    
    /* File uploader */
    .stFileUploader {
        background-color: #40414F;
        border-radius: 10px;
        padding: 20px;
    }
    
    /* Success/Warning messages */
    .stAlert {
        background-color: #444654;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None
if "documents" not in st.session_state:
    st.session_state.documents = []

# Sidebar - Authentication & Document Management
with st.sidebar:
    st.image("https://img.icons8.com/color/96/artificial-intelligence.png", width=80)
    st.title("🤖 RAG Assistant")
    st.markdown("---")
    
    # Authentication Section
    if not st.session_state.token:
        st.subheader("🔐 Login / Register")
        tab1, tab2 = st.tabs(["Login", "Register"])
        
        with tab1:
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            if st.button("Login", use_container_width=True):
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/auth/login",
                        json={"username": login_username, "password": login_password}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.token = data["access_token"]
                        st.session_state.user = data["username"]
                        st.success(f"✅ Welcome {data['username']}!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
                except Exception as e:
                    st.error(f"Connection error: {e}")
        
        with tab2:
            reg_username = st.text_input("Username", key="reg_username")
            reg_email = st.text_input("Email", key="reg_email")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            if st.button("Register", use_container_width=True):
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/auth/register",
                        json={"username": reg_username, "email": reg_email, "password": reg_password}
                    )
                    if response.status_code == 200:
                        st.success("✅ Registration successful! Please login.")
                    else:
                        st.error("Registration failed")
                except Exception as e:
                    st.error(f"Connection error: {e}")
    
    else:
        # User info
        st.success(f"✅ Logged in as: **{st.session_state.user}**")
        
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.token = None
            st.session_state.user = None
            st.session_state.messages = []
            st.rerun()
        
        st.markdown("---")
        
        # Document Management
        st.subheader("📄 Document Management")
        
        # Upload Document
        uploaded_file = st.file_uploader("Upload PDF/TXT", type=['pdf', 'txt'])
        if uploaded_file and st.button("📤 Upload Document", use_container_width=True):
            if st.session_state.token:
                files = {"file": uploaded_file}
                headers = {"Authorization": f"Bearer {st.session_state.token}"}
                
                with st.spinner("Processing document..."):
                    response = requests.post(
                        f"{API_BASE_URL}/upload",
                        files=files,
                        headers=headers
                    )
                if response.status_code == 200:
                    st.success(f"✅ {uploaded_file.name} uploaded successfully!")
                    st.rerun()
                else:
                    st.error("Upload failed")
        
        # List Documents
        if st.button("📋 Refresh Documents", use_container_width=True):
            headers = {"Authorization": f"Bearer {st.session_state.token}"}
            response = requests.get(f"{API_BASE_URL}/documents", headers=headers)
            if response.status_code == 200:
                st.session_state.documents = response.json().get("documents", [])
        
        # Display documents
        if st.session_state.documents:
            st.write(f"**📁 Your Documents ({len(st.session_state.documents)})**")
            for doc in st.session_state.documents:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"📄 {doc['filename']} ({doc['chunks_created']} chunks)")
                with col2:
                    if st.button("🗑️", key=f"del_{doc['id']}"):
                        headers = {"Authorization": f"Bearer {st.session_state.token}"}
                        requests.delete(f"{API_BASE_URL}/documents/{doc['id']}", headers=headers)
                        st.rerun()

# Main Chat Area
st.markdown("<h1 style='text-align: center;'>🤖 AI RAG Assistant</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>Chat with your documents using AI</p>", unsafe_allow_html=True)

# Chat history display
chat_container = st.container()
with chat_container:
    for message in st.session_state.messages:
        if message["role"] == "user":
            st.markdown(f"""
            <div class="user-message">
                <strong>👤 You:</strong><br>
                {message["content"]}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="assistant-message">
                <strong>🤖 Assistant:</strong><br>
                {message["content"]}
                <br><br>
                <small style="color: #888;">📚 Sources: {message.get("sources", "None")}</small>
            </div>
            """, unsafe_allow_html=True)

# Chat input
if st.session_state.token:
    with st.container():
        col1, col2 = st.columns([5, 1])
        with col1:
            user_input = st.text_input("Message", placeholder="Ask me anything about your documents...", key="chat_input", label_visibility="collapsed")
        with col2:
            send_button = st.button("📤 Send", use_container_width=True)
        
        if (send_button or (user_input and user_input != st.session_state.get("last_input", ""))) and user_input:
            st.session_state.last_input = user_input
            
            # Add user message
            st.session_state.messages.append({"role": "user", "content": user_input})
            
            # Call API
            headers = {"Authorization": f"Bearer {st.session_state.token}"}
            data = {"query": user_input}
            
            with st.spinner("🤔 Thinking..."):
                response = requests.post(
                    f"{API_BASE_URL}/query",
                    data=data,
                    headers=headers
                )
            
            if response.status_code == 200:
                result = response.json()
                assistant_response = result.get("answer", "No response")
                sources = result.get("sources", [])
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_response,
                    "sources": ", ".join(sources)
                })
                st.rerun()
            else:
                st.error(f"Error: {response.status_code}")
else:
    st.info("👈 Please login to start chatting with your documents!")

# Footer
st.markdown("---")
st.markdown("<p style='text-align: center; color: #888;'>Powered by Gemini AI | RAG System</p>", unsafe_allow_html=True)