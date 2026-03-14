# Unai Library

Unaiは、特定のURLのみへのHTTPリクエストを制限するPythonライブラリです。

## 機能

- `import unai`を実行すると、呼び出し元のPythonファイルと同じディレクトリにある`request_urls.txt`を読み込みます
- `unai.request()`メソッドは、引数で受け取ったURLが`request_urls.txt`に含まれる場合のみリクエストを送信します
- GET、POST、PUT、DELETEなどのHTTPメソッドをサポートしています
- **正規表現をサポート** - `request_urls.txt`に正規表現パターンを記述できます

## 使い方

1. プロジェクトディレクトリに`request_urls.txt`を作成し、許可するURLまたは正規表現パターンを1行に1つずつ記述します：

```
# 正確なURLマッチ
https://api.example.com/data

# 正規表現パターン（ワイルドカード）
https://httpbin\.org/.*
https://api\.github\.com/users/.*

# 複雑な正規表現
https://.*\.wikipedia\.org/api/.*
https://jsonplaceholder\.typicode\.com/posts/\d+
```

2. Pythonコードでライブラリをインポートして使用します：

```python
import unai

# GETリクエスト
response = unai.get("https://httpbin.org/get")
if response:
    print(response.json())

# POSTリクエスト
response = unai.post("https://httpbin.org/post", json={"key": "value"})
if response:
    print(response.json())

# 一般的なリクエスト
response = unai.request("https://httpbin.org/put", method="PUT", json={"data": "test"})
if response:
    print(response.json())

# request_urls.txtにないURLや一致しないパターンはブロックされます
response = unai.get("https://unauthorized-site.com")
# responseはNoneになります
```

## 正規表現のサポート

`request_urls.txt`には以下の2種類のパターンを記述できます：

### 1. 正確なURLマッチ
```
https://api.example.com/endpoint
```

### 2. 正規表現パターン
```
# httpbin.orgのすべてのパスを許可
https://httpbin\.org/.*

# GitHub APIのユーザーエンドポイントを許可
https://api\.github\.com/users/.*

# 数字のIDを持つ投稿を許可
https://jsonplaceholder\.typicode\.com/posts/\d+

# すべてのWikipedia APIエンドポイントを許可
https://.*\.wikipedia\.org/api/.*
```

**注意**: 正規表現ではドット（`.`）などの特殊文字はエスケープする必要があります（例：`httpbin\.org`）

## API

### `unai.request(url, method='GET', **kwargs)`
指定されたURLにHTTPリクエストを送信します。URLが`request_urls.txt`のパターンに一致する場合のみ実行されます。

- `url`: リクエスト先のURL
- `method`: HTTPメソッド（GET、POST、PUT、DELETEなど）
- `**kwargs`: `requests.request`に渡される追加の引数

### `unai.get(url, **kwargs)`
GETリクエストを送信します。

### `unai.post(url, **kwargs)`
POSTリクエストを送信します。

### `unai.put(url, **kwargs)`
PUTリクエストを送信します。

### `unai.delete(url, **kwargs)`
DELETEリクエストを送信します。

## セキュリティ

このライブラリは、意図しないURLへのリクエストを防ぐために設計されています。`request_urls.txt`に明示的に記載されたURLや正規表現パターンのみにアクセスを制限することで、セキュリティを強化します。

## 注意事項

- `request_urls.txt`が見つからない場合、警告が表示され、すべてのリクエストがブロックされます
- 許可されていないURLへのリクエスト試行時には警告が表示されます
- リクエストが失敗した場合も警告が表示されます
- 正規表現が無効な場合は、正確な文字列マッチとして扱われます
