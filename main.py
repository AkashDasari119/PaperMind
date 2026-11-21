import streamlit as st
from utilities import GEMINI_MODELS, init_session_state, encode_pdf
from gemini_interface import (
    initialize_gemini,
    analyze_pdf_content,
    process_query_stream,
    get_api_key,
    is_transient_error,
)


def main():
    st.set_page_config(
        page_title="PaperMind – AI-Powered Research Paper Analysis",
        page_icon="📚",
        layout="wide",
    )
    st.title("📚 PaperMind – AI-Powered Research Paper Analysis and Understanding System")
    init_session_state()

    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")

        # API Key Configuration
        st.subheader("🔑 API Key")
        env_key = get_api_key()
        if "gemini_api_key_input" not in st.session_state and env_key:
            st.session_state.gemini_api_key_input = env_key

        api_key_input = st.text_input(
            "Gemini API Key",
            key="gemini_api_key_input",
            type="password",
            placeholder="Paste your Gemini API key...",
            help="Get your API key from Google AI Studio (ai.google.dev). If not entered here, PaperMind checks .env (GEMINI_API_KEY or GOOGLE_API_KEY).",
        )
        st.session_state.api_key = api_key_input.strip() or env_key

        # Initialize client gracefully without crashing if key is missing
        if st.session_state.api_key:
            try:
                st.session_state.client = initialize_gemini(st.session_state.api_key)
                st.caption("🟢 API Key configured")
            except Exception as e:
                st.session_state.client = None
                st.caption(f"🔴 Client initialization error: {e}")
        else:
            st.session_state.client = None
            st.caption("🟡 No API key detected. Enter one above or set in `.env`.")

        # Model selection
        st.subheader("🤖 Model Selection")
        selected_model_name = st.selectbox(
            "Choose Gemini Model",
            options=list(GEMINI_MODELS.keys()),
            key="model_selector",
            help="Select the Gemini model you want to use for analysis",
        )
        model_id = GEMINI_MODELS[selected_model_name]
        st.session_state.selected_model = model_id

        # File Upload
        st.subheader("📤 File Upload")
        uploaded_file = st.file_uploader(
            "Upload Research Paper (PDF)", type=["pdf"], key="pdf_uploader"
        )

        if uploaded_file is not None:
            pdf_content = encode_pdf(uploaded_file.getvalue())
            st.session_state.pdf_content = pdf_content

            if st.button("✅ Analyze Paper", key="analyze_button", use_container_width=True):
                if not st.session_state.client:
                    st.error("Please configure a valid Gemini API key first!")
                else:
                    st.session_state.messages = []  # Clear previous messages
                    st.session_state.start_analysis = True

        # Clear chat button
        if st.button("🧹 Clear Chat", key="clear_chat_button", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # Perform analysis in the main area
    if st.session_state.start_analysis:
        if not st.session_state.client:
            st.error("Please configure your Gemini API key in the sidebar first!")
            st.session_state.start_analysis = False
        elif not st.session_state.pdf_content:
            st.error("Please upload a PDF first!")
            st.session_state.start_analysis = False
        else:
            with st.spinner(f"Analyzing research paper with {st.session_state.selected_model}..."):
                message_placeholder = st.empty()
                full_response = []
                analysis_saved = False
                try:
                    for chunk in analyze_pdf_content(
                        st.session_state.client,
                        st.session_state.selected_model,
                        st.session_state.pdf_content,
                    ):
                        if chunk:
                            full_response.append(chunk)
                            # Progressive streaming display
                            message_placeholder.markdown("".join(full_response))

                    notes = "".join(full_response)
                    if notes:
                        # Clear the streaming placeholder so its content
                        # does not persist alongside the chat history bubble.
                        message_placeholder.empty()
                        st.session_state.notes = notes
                        # Save to session state exactly once after streaming completes.
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": "📑 Research Paper Analysis\n\n" + notes,
                            }
                        )
                        analysis_saved = True
                except Exception as e:
                    err_msg = str(e)
                    if is_transient_error(e) or "503" in err_msg or "high demand" in err_msg:
                        message_placeholder.empty()
                        st.warning(
                            f"⏳ **Model Currently Busy (503 High Demand)**\n\n"
                            f"Google's servers reported that **`{st.session_state.selected_model}`** is temporarily experiencing high demand, even after 3 automatic retries with exponential backoff.\n\n"
                            f"💡 **Suggested Action**:\n"
                            f"- In the sidebar **Model Selection** dropdown, select **Gemini 3.5 Flash Lite (Active & Fast)** and click **Analyze Paper**.\n"
                            f"- Or wait a minute and retry with your current model.\n\n"
                            f"*(Your uploaded paper and settings remain preserved.)*"
                        )
                    else:
                        message_placeholder.empty()
                        st.error(f"⚠️ Analysis error: {e}")
            st.session_state.start_analysis = False

    # Main chat interface
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input and streaming response
    prompt = st.chat_input("Ask a question about the paper")
    if prompt:
        if not st.session_state.client:
            st.error("Please configure your Gemini API key in the sidebar first!")
            return

        if not st.session_state.pdf_content or not st.session_state.notes:
            st.error("Please upload a PDF first and click 'Analyze Paper'!")
            return

        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Process streaming response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = []
            try:
                for chunk in process_query_stream(
                    st.session_state.client,
                    st.session_state.selected_model,
                    st.session_state.pdf_content,
                    st.session_state.notes,
                    prompt,
                ):
                    if chunk:
                        full_response.append(chunk)
                        message_placeholder.markdown("".join(full_response))

                complete_response = "".join(full_response)
                st.session_state.messages.append(
                    {"role": "assistant", "content": complete_response}
                )
            except Exception as e:
                err_msg = str(e)
                if is_transient_error(e) or "503" in err_msg or "high demand" in err_msg:
                    message_placeholder.warning(
                        f"⏳ Model `{st.session_state.selected_model}` is temporarily busy (503). Please retry in a few seconds or switch models in the sidebar."
                    )
                else:
                    message_placeholder.error(f"⚠️ Error: {e}")

    # Welcome message
    if not st.session_state.messages:
        st.info(
            "👋 Welcome to PaperMind! Please configure your Gemini API key in the sidebar, upload a research paper PDF, and click 'Analyze Paper' to get started."
        )


if __name__ == "__main__":
    main()

