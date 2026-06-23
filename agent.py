#!/usr/bin/env python3
"""
AI自动化智能体引擎 v1.0
========================
模块化智能体框架，支持多角色协作、定时任务、消息推送。

快速开始:
    python agent.py --config config.yaml

依赖:
    pip install requests pyyaml schedule
"""

import os
import sys
import yaml
import json
import time
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable

# ─── 配置 ───────────────────────────────────────────────

DEFAULT_CONFIG = {
    "agent": {
        "name": "AutoAgent",
        "role": "assistant",
        "debug": False,
    },
    "logging": {
        "level": "INFO",
        "file": "agent.log",
    },
    "modules": {
        "messenger": {"enabled": False},
        "scheduler": {"enabled": False},
    }
}


class Config:
    """配置管理 - 支持YAML文件和环境变量"""

    def __init__(self, path: str = "config.yaml"):
        self.data = DEFAULT_CONFIG.copy()
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if loaded:
                    self._deep_merge(self.data, loaded)
        # 环境变量覆盖
        self._env_override()

    def _deep_merge(self, base: dict, override: dict):
        """递归合并配置"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _env_override(self):
        """AGENT_xxx 环境变量覆盖配置"""
        for key, val in os.environ.items():
            if key.startswith("AGENT_"):
                parts = key[6:].lower().split("__")
                target = self.data
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = val

    def get(self, *keys, default=None):
        """安全获取嵌套配置"""
        target = self.data
        for key in keys:
            if isinstance(target, dict):
                target = target.get(key)
            else:
                return default
        return target if target is not None else default


class Logger:
    """结构化日志系统"""

    def __init__(self, name: str = "agent", level: str = "INFO", file: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        if file:
            fh = logging.FileHandler(file, encoding="utf-8")
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

    def info(self, msg: str, **ctx):
        extra = f" | {json.dumps(ctx, ensure_ascii=False)}" if ctx else ""
        self.logger.info(f"{msg}{extra}")

    def error(self, msg: str, **ctx):
        extra = f" | {json.dumps(ctx, ensure_ascii=False)}" if ctx else ""
        self.logger.error(f"{msg}{extra}")

    def debug(self, msg: str, **ctx):
        extra = f" | {json.dumps(ctx, ensure_ascii=False)}" if ctx else ""
        self.logger.debug(f"{msg}{extra}")


class Messenger:
    """多通道消息推送 - 支持飞书/企业微信/邮件"""

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", False)
        self.channels = config.get("channels", {})

    def send(self, title: str, content: str, channel: str = "default") -> bool:
        """发送消息到指定通道"""
        if not self.enabled:
            return False

        channel_config = self.channels.get(channel) or self.channels.get("default")
        if not channel_config:
            return False

        channel_type = channel_config.get("type", "")

        if channel_type == "feishu":
            return self._send_feishu(channel_config, title, content)
        elif channel_type == "wechat":
            return self._send_wechat(channel_config, title, content)
        elif channel_type == "smtp":
            return self._send_email(channel_config, title, content)
        return False

    def _send_feishu(self, config: dict, title: str, content: str) -> bool:
        """发送飞书消息"""
        import requests
        webhook = config.get("webhook")
        if not webhook:
            return False
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": content}],
            }
        }
        try:
            resp = requests.post(webhook, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def _send_wechat(self, config: dict, title: str, content: str) -> bool:
        """发送企业微信消息"""
        import requests
        webhook = config.get("webhook")
        if not webhook:
            return False
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": f"## {title}\n{content}"}
        }
        try:
            resp = requests.post(webhook, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def _send_email(self, config: dict, title: str, content: str) -> bool:
        """发送邮件"""
        import smtplib
        from email.mime.text import MIMEText
        try:
            msg = MIMEText(content, "plain", "utf-8")
            msg["Subject"] = title
            msg["From"] = config.get("from_addr")
            msg["To"] = config.get("to_addr")
            with smtplib.SMTP_SSL(config.get("host", "smtp.qq.com"),
                                  config.get("port", 465), timeout=10) as s:
                s.login(config.get("user"), config.get("password"))
                s.send_message(msg)
            return True
        except Exception:
            return False


class Scheduler:
    """定时任务调度器"""

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", False)
        self.tasks = []

    def add_task(self, name: str, callback: Callable, interval: int = 300):
        """添加定时任务
        Args:
            name: 任务名称
            callback: 回调函数
            interval: 执行间隔(秒)
        """
        self.tasks.append({
            "name": name,
            "callback": callback,
            "interval": interval,
            "last_run": 0
        })

    def tick(self):
        """检查并执行到期的任务"""
        now = time.time()
        for task in self.tasks:
            if now - task["last_run"] >= task["interval"]:
                try:
                    task["callback"]()
                    task["last_run"] = now
                except Exception as e:
                    logging.error(f"Task {task['name']} failed: {e}")


class Agent:
    """核心智能体引擎"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = Config(config_path)
        self.logger = Logger(
            name=self.config.get("agent", "name", default="Agent"),
            level=self.config.get("logging", "level", default="INFO"),
            file=self.config.get("logging", "file"),
        )
        self.messenger = Messenger(
            self.config.get("modules", "messenger", default={})
        )
        self.scheduler = Scheduler(
            self.config.get("modules", "scheduler", default={})
        )
        self.running = False
        self.modules = {}
        self.logger.info("Agent initialized", name=self.config.get("agent", "name"))

    def register_module(self, name: str, module: Any):
        """注册扩展模块"""
        self.modules[name] = module
        self.logger.info(f"Module registered: {name}")

    def run_once(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行单次任务"""
        self.logger.info(f"Executing task: {task.get('name', 'unknown')}")
        try:
            result = {"status": "success", "data": {}, "timestamp": datetime.now().isoformat()}
            # 任务处理逻辑
            task_type = task.get("type", "generic")
            if task_type == "process_file":
                result["data"] = self._process_file(task.get("path"))
            elif task_type == "send_notification":
                result["data"] = self._send_notification(task)
            else:
                result["data"] = {"message": f"Task {task.get('name')} completed"}
            return result
        except Exception as e:
            self.logger.error(f"Task failed: {task.get('name')}", error=str(e))
            return {"status": "error", "error": str(e)}

    def _process_file(self, path: str) -> Dict:
        """处理文件"""
        if not path or not os.path.exists(path):
            return {"error": f"File not found: {path}"}
        stat = os.stat(path)
        return {
            "path": path,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "hash": self._file_hash(path),
        }

    def _file_hash(self, path: str, algo: str = "sha256") -> str:
        """计算文件哈希"""
        h = hashlib.new(algo)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _send_notification(self, task: Dict) -> Dict:
        """发送通知"""
        success = self.messenger.send(
            title=task.get("title", "Notification"),
            content=task.get("content", ""),
            channel=task.get("channel", "default"),
        )
        return {"sent": success, "channel": task.get("channel")}

    def start(self):
        """启动Agent循环"""
        self.running = True
        self.logger.info("Agent started")
        try:
            while self.running:
                if self.scheduler.enabled:
                    self.scheduler.tick()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Agent stopped by user")
        finally:
            self.running = False

    def stop(self):
        """停止Agent"""
        self.running = False
        self.logger.info("Agent stopped")


# ─── CLI 入口 ──────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI自动化智能体引擎")
    parser.add_argument("--config", "-c", default="config.yaml", help="配置文件路径")
    parser.add_argument("--task", "-t", help="执行单次任务类型")
    parser.add_argument("--task-data", "-d", default="{}", help="任务数据JSON")
    parser.add_argument("--once", action="store_true", help="单次运行模式")
    args = parser.parse_args()

    agent = Agent(args.config)

    if args.once or args.task:
        task_data = json.loads(args.task_data)
        task_data["type"] = args.task or "generic"
        result = agent.run_once(task_data)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        agent.start()


if __name__ == "__main__":
    main()
