#!/usr/bin/env python3
"""
Web爬虫示例 - 使用智能体引擎进行网页数据采集
"""

import json
import sys
sys.path.insert(0, "..")

from agent import Agent, Config

def main():
    # 初始化智能体
    agent = Agent("config.yaml")
    agent.logger.info("Web scraper example started")

    # 示例任务
    task = {
        "name": "example_monitor",
        "type": "generic",
        "data": {"message": "网页监控任务执行成功"}
    }

    # 执行任务
    result = agent.run_once(task)
    print(f"Result: {json.dumps(result, ensure_ascii=False, indent=2)}")

if __name__ == "__main__":
    main()
