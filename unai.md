# Unai — プロジェクト概要・開発者ドキュメント

> **"un-AI"**（発音: ユーナイ）— LLMを一切使わない、コミュニティ製の非AIアシスタント

---

## コンセプト

Unaiは、外見は通常のAIチャットサービスと同じだが、中身はLLMではなく軽量アルゴリズムの組み合わせで動いているアシスタントです。

**核心となる思想：**
- LLMを使わないことで、**速く・安く・消費電力を抑える**
- 対応範囲の狭さを欠点ではなく**設計思想**として打ち出す
- 対応できない入力には正直に「対応するSkillがありません」と返す
- コミュニティが作った**Skill**を追加することで機能を無限に拡張できる

---

## アーキテクチャ概要

```
ユーザー入力
     ↓
priority.json の順番に従って各Skillのmatch()を呼ぶ
     ↓ 最初にTrueを返したSkillが発動
respond() で返答を生成
     ↓
トークン数・処理時間・t/s を計算して一緒に表示
```

### ファイル構成

```
C:\Users\Kasam\unai\
├── main.py              # CLIエントリーポイント
├── app.py               # Web UI用Flaskサーバー
├── priority.json        # Skillの優先順位と有効/無効状態
├── unai.bat             # CLIを起動するバッチファイル
├── templates/
│   └── index.html       # Web UIフロントエンド（単一ファイル）
└── skills/
    ├── greeting/        # Skill例
    │   ├── skill.py
    │   └── meta.json
    ├── help/
    ├── calc/
    ├── joke/
    └── wikipedia/
        ├── skill.py
        ├── meta.json
        └── request_urls.txt   # 外部リクエスト先URL一覧
```

### priority.json の構造

```json
{
  "order": ["greeting", "help", "calc", "wikipedia", "joke"],
  "disabled": []
}
```

- `order`: Skillが試される順番（上から順に `match()` を呼ぶ）
- `disabled`: 無効化されているSkill IDのリスト

---

## Skill の仕様

### 基本構造

各Skillは `skills/<skill_id>/` フォルダとして存在し、以下のファイルを含む：

| ファイル | 必須 | 説明 |
|---|---|---|
| `skill.py` | ✅ | `match(text)` と `respond(text)` を実装 |
| `meta.json` | ✅ | Skillのメタ情報 |
| `request_urls.txt` | 外部通信する場合のみ | 改行区切りでリクエスト先URLを列挙 |

### skill.py の実装規約

```python
def match(text: str) -> bool:
    """この入力がこのSkillで処理すべきかを判定する"""
    ...

def respond(text: str) -> str:
    """入力を処理して返答文字列を返す"""
    ...
```

### meta.json の構造

```json
{
  "name": "表示名",
  "description": "このSkillが何をするかの説明",
  "author": "作者名",
  "version": "1.0.0"
}
```

### Skill の制約ルール

| 制約 | 内容 |
|---|---|
| 使用可能なライブラリ | 指定された許可ライブラリのみ（現時点: 標準ライブラリ + sympy） |
| フォルダ合計サイズ | 500MB 以下 |
| 外部通信 | `request_urls.txt` に記載したURLへのみ許可 |
| 組み込みAI | 0.5Mパラメーターを超えるモデルは禁止 |

> **透明性の担保：** 外部リクエスト先URLはすべて `request_urls.txt` に明記する。ユーザーはSkillが何にアクセスするかを事前に確認できる。

---

## デフォルトSkill一覧

| Skill ID | 機能 | 外部通信 |
|---|---|---|
| `greeting` | 挨拶・雑談（ルールベース + レーベンシュタイン距離） | なし |
| `help` | 使い方の説明 | なし |
| `calc` | 数式計算・方程式（sympy使用、途中式表示） | なし |
| `wikipedia` | Wikipedia要約の取得 | `ja.wikipedia.org` |
| `joke` | ランダムジョーク（リストからランダム選択） | なし |

---

## 起動方法

### CLI モード

```bat
C:\Users\Kasam\unai\unai.bat
```

または直接：

```bash
C:\Users\Kasam\.pyenv\pyenv-win\versions\3.12.0\python.exe main.py
```

### Web UI モード

```bash
C:\Users\Kasam\.pyenv\pyenv-win\versions\3.12.0\python.exe app.py
```

ブラウザで `http://localhost:5000` にアクセス。

> **注意：** `python` コマンドは優先度の問題で意図しないインタープリタを呼ぶ場合がある。フルパスで指定すること。

---

## Web UI の機能

- チャット画面（AIチャットサービスと同様のUI）
- 各返答の下に **[Skill名] トークン数 · 処理時間ms · t/s** を表示
- ⚙ Skills パネル（右上ボタンで開閉）
  - Skillの一覧表示
  - トグルで有効/無効の切り替え
  - ドラッグ＆ドロップで優先順位を変更
  - 変更はリアルタイムで `priority.json` に保存

---

## Web API エンドポイント（app.py）

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/` | Web UIを返す |
| POST | `/api/chat` | `{"message": "..."}` を受け取り応答を返す |
| GET | `/api/skills` | 優先順位順のSkill一覧を返す |
| POST | `/api/skills/toggle` | `{"id": "skill_id"}` でSkillの有効/無効を切り替え |
| POST | `/api/skills/reorder` | `{"order": ["id1","id2",...]}` で優先順位を更新 |

---

## 表示オプション（ユーザー向け付加情報）

各返答に以下の統計情報を表示する：

- **トークン数**（空白区切りの単語数で近似）
- **処理時間**（ミリ秒）
- **t/s**（tokens per second）— LLMより高速であることを実感させるため
- *(将来)* **節約した消費電力の推定量**

> t/sはLLMとは処理の性質が異なるため厳密な比較にはならないが、速度感の演出として有効。

---

## Python環境

| 項目 | 値 |
|---|---|
| 推奨インタープリタ | `C:\Users\Kasam\.pyenv\pyenv-win\versions\3.12.0\python.exe` |
| インストール済みパッケージ | `sympy`, `flask` |

---

## 将来の拡張アイデア

- **天気Skill**: 天気APIを参照（`request_urls.txt` に記載）
- **株価Skill**: 株価APIを参照
- **Skill マーケットプレイス**: Skillをアップロード・評価（星5段階）できる公開サーバー
- **プリセット機能**: 有効なSkillセットを名前をつけて保存・切り替え
- **生成風アニメーション**: 文字が流れるように表示されるタイピングエフェクト
- **絞り込み検索**: 作者・サイズ・競合・名前でSkillを絞り込み・並び替え