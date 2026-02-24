import json
import difflib
from datetime import datetime

import anthropic
import streamlit as st

# ─── ページ設定 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="保育ドキュメント 添削・推敲ツール",
    page_icon="📝",
    layout="wide",
)

# ─── スタイル ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.diff-box {
    font-family: sans-serif;
    font-size: 0.95rem;
    line-height: 1.8;
    padding: 1rem;
    border-radius: 6px;
    background: #f9f9f9;
    border: 1px solid #e0e0e0;
    white-space: pre-wrap;
    word-break: break-all;
}
.del { background: #ffd7d7; text-decoration: line-through; border-radius: 3px; padding: 0 2px; }
.ins { background: #d4f7d4; border-radius: 3px; padding: 0 2px; }
.correction-card {
    background: #f0f4ff;
    border-left: 4px solid #4f7cff;
    border-radius: 4px;
    padding: 0.6rem 0.9rem;
    margin-bottom: 0.5rem;
}
.summary-box {
    background: #fffbe6;
    border-left: 4px solid #f0b429;
    border-radius: 4px;
    padding: 0.6rem 0.9rem;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# ─── 定数 ─────────────────────────────────────────────────────────────────────
DOC_TYPES = ["連絡帳", "保育日誌", "ドキュメンテーション", "その他"]

DOC_SYSTEM_PROMPTS = {
    "連絡帳": (
        "あなたは保育園の連絡帳文章の添削専門家です。"
        "連絡帳は保護者向けの文章です。温かみ・親しみやすさを大切にし、"
        "敬語を自然に使い、保護者が読んで安心・喜べる表現に整えます。"
        "個人情報の扱いに注意し、子どもの名前や具体的なエピソードを活かします。"
    ),
    "保育日誌": (
        "あなたは保育日誌文章の添削専門家です。"
        "保育日誌は施設内の記録文書です。事実と観察・考察を明確に区別し、"
        "客観的かつ正確な表現を心がけます。専門的な保育用語を適切に使い、"
        "記録としての明瞭さと再現性を重視します。"
    ),
    "ドキュメンテーション": (
        "あなたは保育ドキュメンテーションの添削専門家です。"
        "ドキュメンテーションは子どもの学び・発達・探求を記録するものです。"
        "子ども主体の視点で、具体的なエピソードや言葉を大切にしながら、"
        "保護者や同僚にも伝わる生き生きとした描写に整えます。"
    ),
    "その他": (
        "あなたは日本語文章の添削専門家です。"
        "読みやすさ・正確さ・自然な日本語表現を重視して添削します。"
    ),
}

TONE_INSTRUCTIONS = {
    "丁寧": "より丁寧で改まった表現・敬語に整えてください。",
    "やわらか": "より柔らかく親しみやすい、温もりのある表現に整えてください。",
    "簡潔": "冗長な表現を省き、簡潔でわかりやすい文章に整えてください。",
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "corrected_text": {"type": "string"},
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "corrected": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["original", "corrected", "reason"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["corrected_text", "corrections", "summary"],
}

# ─── セッション初期化 ──────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []
if "current_result" not in st.session_state:
    st.session_state.current_result = None
if "edited_text" not in st.session_state:
    st.session_state.edited_text = ""
if "restore_index" not in st.session_state:
    st.session_state.restore_index = None

# ─── Anthropicクライアント ────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    try:
        return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    except Exception:
        return None

client = get_client()

# ─── ユーティリティ関数 ───────────────────────────────────────────────────────
def build_inline_diff(original: str, corrected: str) -> tuple[str, str]:
    """文字レベルの差分HTMLを生成する。"""
    matcher = difflib.SequenceMatcher(None, original, corrected)
    orig_html, corr_html = [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        orig_chunk = original[i1:i2]
        corr_chunk = corrected[j1:j2]
        if op == "equal":
            orig_html.append(orig_chunk)
            corr_html.append(corr_chunk)
        elif op == "delete":
            orig_html.append(f'<span class="del">{orig_chunk}</span>')
        elif op == "insert":
            corr_html.append(f'<span class="ins">{corr_chunk}</span>')
        elif op == "replace":
            orig_html.append(f'<span class="del">{orig_chunk}</span>')
            corr_html.append(f'<span class="ins">{corr_chunk}</span>')
    return "".join(orig_html), "".join(corr_html)


def call_proofread_api(
    doc_type: str,
    text: str,
    context: str = "",
    tone: str | None = None,
) -> dict | None:
    """Claude APIで添削を実行してJSONを返す。"""
    if client is None:
        st.error("APIキーが設定されていません。`.streamlit/secrets.toml` に `ANTHROPIC_API_KEY` を設定してください。")
        return None

    system_prompt = DOC_SYSTEM_PROMPTS[doc_type]
    system_prompt += (
        "\n\n必ず以下のJSON形式のみで返答してください。余分な説明は不要です。\n"
        '{"corrected_text": "修正後の完全な文章", '
        '"corrections": [{"original": "元の表現", "corrected": "修正後", "reason": "理由"}], '
        '"summary": "全体コメント"}'
    )

    user_content = f"【文書種別】{doc_type}\n"
    if context:
        user_content += f"【コンテキスト】{context}\n"
    if tone:
        user_content += f"【文体調整】{TONE_INSTRUCTIONS[tone]}\n"
    user_content += f"\n【添削対象の文章】\n{text}"

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text.strip()
        # コードブロックを除去
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError:
        st.error("AIの応答の解析に失敗しました。もう一度お試しください。")
        return None
    except anthropic.AuthenticationError:
        st.error("APIキーが無効です。`.streamlit/secrets.toml` を確認してください。")
        return None
    except Exception as e:
        st.error(f"APIエラーが発生しました: {e}")
        return None


def save_to_history(doc_type: str, original: str, result: dict):
    entry = {
        "timestamp": datetime.now().strftime("%H:%M"),
        "doc_type": doc_type,
        "original": original,
        "corrected": result["corrected_text"],
        "corrections": result.get("corrections", []),
        "summary": result.get("summary", ""),
    }
    st.session_state.history.insert(0, entry)
    if len(st.session_state.history) > 20:
        st.session_state.history.pop()


def render_result(original: str, result: dict):
    """添削結果エリアを描画する。"""
    st.divider()
    st.subheader("添削結果")

    # 全体コメント
    if result.get("summary"):
        st.markdown(
            f'<div class="summary-box">💬 {result["summary"]}</div>',
            unsafe_allow_html=True,
        )

    tab_diff, tab_corrections = st.tabs(["差分表示", "修正点リスト"])

    with tab_diff:
        orig_html, corr_html = build_inline_diff(original, result["corrected_text"])
        col_orig, col_corr = st.columns(2)
        with col_orig:
            st.markdown("**修正前**")
            st.markdown(f'<div class="diff-box">{orig_html}</div>', unsafe_allow_html=True)
        with col_corr:
            st.markdown("**修正後**")
            st.markdown(f'<div class="diff-box">{corr_html}</div>', unsafe_allow_html=True)

    with tab_corrections:
        corrections = result.get("corrections", [])
        if not corrections:
            st.info("修正点はありませんでした。")
        else:
            for i, c in enumerate(corrections, 1):
                st.markdown(
                    f'<div class="correction-card">'
                    f"<b>{i}. 修正前：</b>「{c['original']}」<br>"
                    f"<b>修正後：</b>「{c['corrected']}」<br>"
                    f"<b>理由：</b>{c['reason']}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.divider()
    st.subheader("修正後の文章（編集可）")

    # edited_textを現在の結果で初期化（初回のみ）
    if st.session_state.edited_text != result["corrected_text"]:
        if not st.session_state.get("tone_adjusted"):
            st.session_state.edited_text = result["corrected_text"]

    edited = st.text_area(
        "以下を直接編集できます",
        value=st.session_state.edited_text or result["corrected_text"],
        height=150,
        key="edit_area",
    )
    st.session_state.edited_text = edited

    st.markdown("**文体を調整する**")
    tone_cols = st.columns(3)
    tones = list(TONE_INSTRUCTIONS.keys())
    for i, tone in enumerate(tones):
        with tone_cols[i]:
            if st.button(tone, key=f"tone_{tone}"):
                with st.spinner(f"「{tone}」に調整中..."):
                    adjusted = call_proofread_api(
                        st.session_state.get("selected_doc_type", "その他"),
                        original,
                        st.session_state.get("context_input", ""),
                        tone=tone,
                    )
                if adjusted:
                    st.session_state.current_result = adjusted
                    st.session_state.edited_text = adjusted["corrected_text"]
                    st.session_state.tone_adjusted = True
                    save_to_history(
                        st.session_state.get("selected_doc_type", "その他"),
                        original,
                        adjusted,
                    )
                    st.rerun()

    st.markdown("**コピー用**")
    st.code(edited, language=None)


# ─── サイドバー ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("設定")

    doc_type = st.radio("文書の種類", DOC_TYPES, index=0)
    st.session_state.selected_doc_type = doc_type

    context_input = st.text_input(
        "コンテキスト（任意）",
        placeholder="例: りす組、5歳児クラス",
        help="クラス名や対象年齢など、添削の参考になる情報を入力します",
    )
    st.session_state.context_input = context_input

    st.divider()

    st.header("添削履歴")
    if not st.session_state.history:
        st.caption("まだ履歴がありません")
    else:
        for idx, entry in enumerate(st.session_state.history):
            label = f"{entry['timestamp']} [{entry['doc_type']}] {entry['original'][:15]}..."
            if st.button(label, key=f"hist_{idx}", use_container_width=True):
                st.session_state.restore_index = idx
                st.rerun()

# ─── メインエリア ─────────────────────────────────────────────────────────────
st.title("📝 保育ドキュメント 添削・推敲ツール")
st.caption("連絡帳・保育日誌・ドキュメンテーションなどの文章をAIが添削・推敲します")

# 履歴復元
restore_text = ""
if st.session_state.restore_index is not None:
    idx = st.session_state.restore_index
    if 0 <= idx < len(st.session_state.history):
        entry = st.session_state.history[idx]
        restore_text = entry["original"]
        st.session_state.current_result = {
            "corrected_text": entry["corrected"],
            "corrections": entry["corrections"],
            "summary": entry["summary"],
        }
        st.session_state.edited_text = entry["corrected"]
    st.session_state.restore_index = None

input_text = st.text_area(
    "添削したい文章を入力してください",
    value=restore_text,
    height=180,
    placeholder="ここに文章を入力してください...",
    key="input_text_area",
)

col_btn, col_clear = st.columns([3, 1])
with col_btn:
    proofread_clicked = st.button("添削する", type="primary", use_container_width=True)
with col_clear:
    if st.button("クリア", use_container_width=True):
        st.session_state.current_result = None
        st.session_state.edited_text = ""
        st.session_state.tone_adjusted = False
        st.rerun()

if proofread_clicked:
    if not input_text.strip():
        st.warning("文章を入力してください。")
    else:
        st.session_state.tone_adjusted = False
        with st.spinner("添削中..."):
            result = call_proofread_api(doc_type, input_text, context_input)
        if result:
            st.session_state.current_result = result
            st.session_state.edited_text = result["corrected_text"]
            save_to_history(doc_type, input_text, result)

if st.session_state.current_result:
    # 元テキストの特定（入力欄 or 復元された履歴）
    original = input_text or restore_text
    render_result(original, st.session_state.current_result)
