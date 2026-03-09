# 飞书开放平台 API 提取参考

如果用户提供了 `app_id` 和 `app_secret`，可以使用飞书 OpenAPI 进行更高效、结构化的内容提取。

## 1. 核心接口

### 获取文档所有块 (Blocks)
- **Endpoint**: `GET /open-apis/docx/v1/documents/:document_id/blocks`
- **用途**: 分页获取文档中所有的内容块，包括段落、图片、表格、画板占位符等。

### 获取文档纯文本内容
- **Endpoint**: `GET /open-apis/docx/v1/documents/:document_id/raw_content`
- **用途**: 快速获取全文 Markdown 或纯文本，适用于不需要处理画板的简单场景。

### 画板块 (Whiteboard Block) 处理
在 `blocks` 接口返回的数据中，找 `block_type == 23` (Whiteboard)。
- 返回的对象包含一个 `whiteboard_token`。
- 目前 OpenAPI 对画板内部元素的结构化提取支持有限，通常返回的是一个引用的 Token。

## 2. 权限要求
应用需要启用以下权限：
- `docx:document:readonly` (读取文档内容)
- `drive:file:readonly` (读取云空间文件信息)

## 3. 内容提取逻辑（代码示例 - Python）

```python
import httpx

def get_docx_content(document_id, tenant_access_token):
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks"
    headers = {"Authorization": f"Bearer {tenant_access_token}"}
    
    # 递归或循环分页获取所有 blocks
    response = httpx.get(url, headers=headers)
    blocks = response.json().get("data", {}).get("items", [])
    
    for block in blocks:
        if block["block_type"] == 2:  # 段落
            print(block["paragraph"]["elements"])
        elif block["block_type"] == 23: # 画板
            print(f"找到画板，Token: {block['whiteboard']['token']}")
```

## 4. 限制
- **API 频率限制**: 注意 QPS 限制。
- **画板深度内容**: 如前所述，API 往往只能拿到画板的 Token，具体图形数据仍需结合浏览器截图或导出功能。
