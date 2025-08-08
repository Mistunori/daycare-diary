import streamlit as st
import openai
from datetime import date

# --- APIキー設定 ---
openai.api_key = st.secrets["OPENAI_API_KEY"]

st.title("🌼 保育日誌 自動生成ツール")

# 入力フォーム
col1, col2 = st.columns(2)
with col1:
    record_date = st.date_input("記録日", value=date.today())
with col2:
    class_name = st.text_input("クラス名（例：オリーブ組）")

activity_title = st.text_input("活動タイトル（例：室内遊び／段ボールなど）")
child_obs = st.text_area("子どもの様子")
teacher_obs = st.text_area("保育士の気づき")

if st.button("文章を生成"):
    prompt = f"""
    以下の情報をもとに保育日誌の文章を作成してください。
    柔らかく丁寧な文体で、保護者にも伝わるように。
    活動タイトルは冒頭に入れ、その後に子どもの様子・保育士の気づきの順に構成してください。
    200〜300文字程度にまとめてください。

    ■ 記録日: {record_date}
    ■ クラス名: {class_name}
    ■ 活動タイトル: {activity_title}
    ■ 子どもの様子: {child_obs}
    ■ 保育士の気づき: {teacher_obs}
    """

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    output_text = response.choices[0].message["content"].strip()

    st.subheader("生成された文章")
    st.write(output_text)

    # コピー用
    st.code(output_text)

