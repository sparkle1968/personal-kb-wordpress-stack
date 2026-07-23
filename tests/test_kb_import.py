import importlib.util
import json
from pathlib import Path
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
                            "parts": ["**结论**\n\n- 第一项\n- 第二项"],
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
        self.assertIn("<h2>提问</h2>", body)
        self.assertIn("<h2>ChatGPT 回答</h2>", body)
        self.assertIn("<strong>结论</strong>", body)
        self.assertIn("https://example.com/attachment.png", body)
        self.assertNotIn("隐藏指令", body)
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
        self.assertEqual(text, "这是最终回答正文。")

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
