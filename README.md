# Web Proxy (Fly.io版)

Termux → Fly.io → 外部API/サイト の構成で動くリバースプロキシ。

---

## Termuxセットアップ手順

### 1. flyctl インストール

```bash
# ARM64用バイナリを直接ダウンロード
curl -L https://github.com/superfly/flyctl/releases/latest/download/flyctl_Linux_arm64.tar.gz -o flyctl.tar.gz
tar -xzf flyctl.tar.gz
mv flyctl $PREFIX/bin/
rm flyctl.tar.gz

# 確認
flyctl version
```

### 2. Fly.io にログイン

```bash
flyctl auth login
# ブラウザが開くのでアカウント作成 or ログイン
```

### 3. アプリ作成 & デプロイ

```bash
# このフォルダに移動
cd fly-proxy

# 初回セットアップ（fly.toml を上書きしてOK）
flyctl launch --no-deploy

# 認証トークンを環境変数にセット
flyctl secrets set PROXY_TOKEN=自分で決めたトークン

# デプロイ
flyctl deploy
```

### 4. URLを確認

```bash
flyctl status
# → https://アプリ名.fly.dev が表示される
```

---

## 使い方

```bash
PROXY="https://アプリ名.fly.dev"
TOKEN="自分で決めたトークン"

# GETリクエスト
curl "$PROXY/proxy?url=https://api.example.com/data&token=$TOKEN"

# POSTリクエスト
curl -X POST "$PROXY/proxy?url=https://api.example.com/data" \
  -H "X-Proxy-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'

# 死活確認
curl "$PROXY/health"
```

---

## 便利なコマンド

```bash
flyctl logs          # ログ確認
flyctl status        # 状態確認
flyctl deploy        # 再デプロイ
flyctl secrets list  # 設定済みの環境変数一覧
```

---

## 無料枠について

Fly.ioの無料枠（2024年時点）:
- 共有CPU × 3台まで無料
- RAM 256MB
- `auto_stop_machines = true` にしてあるので、アクセスがない時は自動停止して節約
