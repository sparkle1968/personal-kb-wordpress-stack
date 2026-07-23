import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kb-import.py"
SPEC = importlib.util.spec_from_file_location("kb_import", MODULE_PATH)
assert SPEC and SPEC.loader
KB_IMPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KB_IMPORT)


def flatten(value):
    values = []

    def add(item):
        index = len(values)
        values.append(None)
        if isinstance(item, dict):
            encoded = {}
            values[index] = encoded
            for key, child in item.items():
                encoded[f"_{add(str(key))}"] = add(child)
        elif isinstance(item, list):
            values[index] = [add(child) for child in item]
        else:
            values[index] = item
        return index

    add(value)
    return values


class XArticleImportTest(unittest.TestCase):
    def test_extracts_and_formats_full_text_from_x_stream(self):
        source = (
            '$R[1]={__id:"article",__typename:"ArticleEntity",'
            'rest_id:"1234567890",title:"Obsidian 入门",preview_text:"只有摘要",'
            'cover_media_results:$R[2]={__ref:"cover"},'
            'plain_text:"完整开头。\\n\\n一、下载安装\\n\\n'
            '1. 安装桌面版\\n访问 \\x3Chttps://obsidian.md>",'
            'content_state:null}'
        )

        article = KB_IMPORT.x_article_entity_from_stream(source)
        result = KB_IMPORT.content_from_x_article_entity(
            article,
            SimpleNamespace(
                title="",
                excerpt="",
                source_url="",
                source_site="",
                source_author="",
            ),
            "https://x.com/example/status/1234567890",
            "示例作者",
            "https://x.com/example",
        )

        self.assertEqual(article["title"], "Obsidian 入门")
        self.assertIn("完整开头", article["text"])
        self.assertIn("<https://obsidian.md>", article["text"])
        self.assertIn("<h2>一、下载安装</h2>", result["content"])
        self.assertIn("<h3>1. 安装桌面版</h3>", result["content"])
        self.assertIn('href="https://obsidian.md"', result["content"])
        self.assertNotIn("文章导读", result["content"])
        self.assertIn("完整开头", result["excerpt"])

    def test_keeps_preview_fallback_when_full_text_is_missing(self):
        article = {
            "rest_id": "1234567890",
            "title": "仅摘要文章",
            "preview": "这是文章摘要。",
            "text": "",
            "cover_url": "",
            "url": "https://x.com/i/article/1234567890",
        }
        result = KB_IMPORT.content_from_x_article_entity(
            article,
            SimpleNamespace(
                title="",
                excerpt="",
                source_url="",
                source_site="",
                source_author="",
            ),
            "https://x.com/example/status/1234567890",
            "",
            "",
        )

        self.assertIn("<h2>文章导读</h2>", result["content"])
        self.assertIn("这是文章摘要", result["content"])


class ChatGPTShareImportTest(unittest.TestCase):
    def test_extracts_visible_messages_and_images(self):
        conversation = {
            "title": "脱敏示例对话",
            "mapping": {},
            "current_node": "assistant",
            "linear_conversation": [
                {
                    "message": {
                        "author": {"role": "system"},
                        "content": {"content_type": "text", "parts": ["隐藏指令"]},
                    }
                },
                {
                    "message": {
                        "author": {"role": "user"},
                        "content": {
                            "content_type": "multimodal_text",
                            "parts": [
                                {
                                    "content_type": "image_asset_pointer",
                                    "asset_pointer": "sediment://file_example123?shared_conversation_id=share-example-1234",
                                },
                                "请分析这份脱敏资料。",
                            ],
                        },
                    }
                },
                {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": [
                                "# 检查结论\n\n"
                                "| 项目 | 结果 |\n| --- | --- |\n| CEA | 30.3 |\n\n"
                                "**总体判断**：继续结合影像检查。citeturn0search0"
                            ],
                        },
                    }
                },
            ],
        }
        root = {"loaderData": {"share": {"serverResponse": {"data": conversation}}}}
        stream = json.dumps(flatten(root), ensure_ascii=False, separators=(",", ":")) + "\n"
        source = (
            "<html><body><script>"
            "window.__reactRouterContext.streamController.enqueue("
            + json.dumps(stream, ensure_ascii=False)
            + ");</script></body></html>"
        )

        parsed = KB_IMPORT.chatgpt_share_conversation(source)
        body, text = KB_IMPORT.chatgpt_conversation_to_html(
            parsed,
            lambda _: "https://example.com/attachment.png",
        )

        self.assertEqual(parsed["title"], "脱敏示例对话")
        self.assertIn('class="kb-chat-transcript"', body)
        self.assertIn('class="kb-chat-message kb-chat-message-user"', body)
        self.assertIn('class="kb-chat-message kb-chat-message-assistant"', body)
        self.assertIn('<span class="kb-chat-role">提问</span>', body)
        self.assertIn('<span class="kb-chat-role">ChatGPT 回答</span>', body)
        self.assertIn("<h2>检查结论</h2>", body)
        self.assertIn("<table>", body)
        self.assertIn("<th>项目</th>", body)
        self.assertIn("<td>30.3</td>", body)
        self.assertIn("<strong>总体判断</strong>", body)
        self.assertIn("https://example.com/attachment.png", body)
        self.assertNotIn("隐藏指令", body)
        self.assertNotIn("cite", body)
        self.assertNotIn("<h1>", body)
        self.assertIn("请分析这份脱敏资料", text)

    def test_extracts_new_post_message_slice(self):
        post = {
            "id": "t_example1234567890",
            "text": "新版分享标题",
            "og_title": "看看这段聊天",
            "attachments": [
                {
                    "kind": "message_slice",
                    "messages": [
                        {
                            "author": {"role": "assistant"},
                            "recipient": "python",
                            "content": {"content_type": "code", "text": "隐藏工具代码"},
                        },
                        {
                            "author": {"role": "assistant"},
                            "recipient": "all",
                            "channel": "final",
                            "content": {
                                "content_type": "text",
                                "parts": ["fast|https://example.com/internal"],
                            },
                        },
                        {
                            "author": {"role": "assistant"},
                            "recipient": "all",
                            "channel": "final",
                            "content": {"content_type": "text", "parts": ["这是最终回答正文。"]},
                        },
                    ],
                }
            ],
        }
        root = {
            "loaderData": {
                "routes/s.$postId": {
                    "kind": "post_with_profile",
                    "postWithProfile": {"post": post},
                }
            }
        }
        stream = json.dumps(flatten(root), ensure_ascii=False, separators=(",", ":")) + "\n"
        source = (
            "<html><body><script>"
            "window.__reactRouterContext.streamController.enqueue("
            + json.dumps(stream, ensure_ascii=False)
            + ");</script></body></html>"
        )

        parsed = KB_IMPORT.chatgpt_share_conversation(source)
        body, text = KB_IMPORT.chatgpt_conversation_to_html(parsed, lambda value: value)

        self.assertEqual(parsed["title"], "新版分享标题")
        self.assertEqual(parsed["shared_conversation_id"], "t_example1234567890")
        self.assertIn("这是最终回答正文", body)
        self.assertNotIn("隐藏工具代码", body)
        self.assertNotIn("fast|", body)
        self.assertEqual(text, "这是最终回答正文。")

    def test_keeps_file_attachment_context(self):
        conversation = {
            "linear_conversation": [
                {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": [""]},
                        "metadata": {
                            "attachments": [
                                {
                                    "name": "脱敏检查报告.pdf",
                                    "mime_type": "application/pdf",
                                }
                            ]
                        },
                    }
                },
                {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["已阅读附件。"]},
                    }
                },
            ]
        }

        body, _ = KB_IMPORT.chatgpt_conversation_to_html(conversation, lambda _: "")

        self.assertIn("1 次提问 · 1 段回答", body)
        self.assertIn("文件附件", body)
        self.assertIn("脱敏检查报告.pdf", body)

    def test_markdown_table_and_heading_offset(self):
        rendered = KB_IMPORT.markdown_to_html(
            "# 一级标题\n\n| 项目 | 结果 |\n| :--- | ---: |\n| CA15-3 | 19.3 |",
            heading_offset=1,
        )

        self.assertIn("<h2>一级标题</h2>", rendered)
        self.assertIn("<table>", rendered)
        self.assertIn("<thead>", rendered)
        self.assertIn("<tbody>", rendered)
        self.assertIn("<td>CA15-3</td>", rendered)

    def test_recognizes_supported_share_hosts(self):
        self.assertTrue(KB_IMPORT.is_chatgpt_share_url("https://chatgpt.com/share/example-id"))
        self.assertTrue(KB_IMPORT.is_chatgpt_share_url("https://chat.openai.com/share/example-id"))
        self.assertTrue(KB_IMPORT.is_chatgpt_share_url("https://chatgpt.com/s/t_example1234567890"))
        self.assertFalse(KB_IMPORT.is_chatgpt_share_url("https://example.com/share/example-id"))
        self.assertEqual(
            KB_IMPORT.chatgpt_share_id("https://chatgpt.com/s/t_example1234567890"),
            "t_example1234567890",
        )


if __name__ == "__main__":
    unittest.main()
