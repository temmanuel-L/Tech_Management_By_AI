"""
告警通知器 — 飞书 / 钉钉 Webhook 推送

═══════════════════════════════════════════════════════════════════════════════
映射《An Elegant Puzzle》:
  - 2.8节 "管理手段": 及时暴露问题并促成快速纠偏
  - 附录: "管理看板" — 当指标偏离目标时, 迅速调动资源或调整流程
═══════════════════════════════════════════════════════════════════════════════
"""

import hashlib
import hmac
import base64
import json
import logging
import time

import httpx

from tech_mgmt_ai.config import settings

logger = logging.getLogger(__name__)


def send_feishu_alert(
    title: str,
    content: str,
    webhook_url: str | None = None,
) -> bool:
    """
    通过飞书 Webhook 发送告警消息

    飞书自定义机器人文档:
    https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot

    Args:
        title: 消息标题
        content: 消息正文 (支持飞书富文本格式)
        webhook_url: Webhook 地址, 默认从 settings 读取

    Returns:
        True 如果发送成功
    """
    url = webhook_url or settings.FEISHU_WEBHOOK_URL
    if not url:
        logger.warning("飞书 Webhook 未配置, 跳过告警发送")
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🔔 {title}"},
                "template": "red" if "danger" in content.lower() or "告警" in title else "orange",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content,
                },
            ],
        },
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            logger.info(f"飞书告警发送成功: {title}")
            return True
        else:
            logger.error(f"飞书告警发送失败: {result}")
            return False
    except Exception as e:
        logger.error(f"飞书告警发送异常: {e}")
        return False


def send_dingtalk_alert(
    title: str,
    content: str,
    webhook_url: str | None = None,
    secret: str | None = None,
) -> bool:
    """
    通过钉钉 Webhook 发送告警消息

    钉钉自定义机器人文档:
    https://open.dingtalk.com/document/robots/custom-robot-access

    Args:
        title: 消息标题
        content: 消息正文 (Markdown 格式)
        webhook_url: Webhook 地址, 默认从 settings 读取
        secret: 签名密钥, 默认从 settings 读取

    Returns:
        True 如果发送成功
    """
    url = webhook_url or settings.DINGTALK_WEBHOOK_URL
    if not url:
        logger.warning("钉钉 Webhook 未配置, 跳过告警发送")
        return False

    # 钉钉签名认证
    sec = secret or (
        settings.DINGTALK_SECRET.get_secret_value() if settings.DINGTALK_SECRET else None
    )
    if sec:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{sec}"
        hmac_code = hmac.new(
            sec.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        url = f"{url}&timestamp={timestamp}&sign={sign}"

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": f"## 🔔 {title}\n\n{content}",
        },
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        result = resp.json()
        if result.get("errcode") == 0:
            logger.info(f"钉钉告警发送成功: {title}")
            return True
        else:
            logger.error(f"钉钉告警发送失败: {result}")
            return False
    except Exception as e:
        logger.error(f"钉钉告警发送异常: {e}")
        return False


def send_alert(title: str, content: str) -> None:
    """
    向所有已配置的通知渠道发送告警

    会自动检测哪些渠道已配置, 并向所有可用渠道发送。
    """
    sent = False
    if settings.FEISHU_WEBHOOK_URL:
        sent = send_feishu_alert(title, content) or sent
    if settings.DINGTALK_WEBHOOK_URL:
        sent = send_dingtalk_alert(title, content) or sent
    if not sent:
        logger.warning(f"告警未发送 (无可用通知渠道): {title}")
