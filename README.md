# daycare-diary

保育ドキュメント 添削・推敲ツール — Streamlit + OpenAI API (gpt-4o-mini)

連絡帳・保育日誌・ドキュメンテーションなどの文章をAIが添削・推敲します。

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. APIキーの設定

`.streamlit/secrets.toml` を作成し、OpenAI APIキーを設定します。

```toml
OPENAI_API_KEY = "sk-..."
```

### 3. アプリの起動

```bash
streamlit run app.py
```

ブラウザが自動で開き、添削ツールが利用可能になります。
