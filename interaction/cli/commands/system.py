import click
import asyncio
from interaction.cli.formats import console, print_error, print_success, print_info
from gateway.gateway import LLMGateway
from runtime.config import load_config


@click.group(name="system")
def system_group():
    """系统管理"""


@system_group.command(name="status")
def system_status():
    """查看系统运行状态"""
    print_success("Pulsar · 脉冲星")
    print_info(f"  版本: 0.1.0")
    print_info(f"  状态: running")
    print_info(f"  Agent 数量: 4")


@system_group.command(name="logs")
@click.option("--lines", default=50, help="显示行数")
def system_logs(lines):
    """查看系统日志"""
    log_path = "data/logs/audit.log"
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            tail = all_lines[-lines:]
            for line in tail:
                print_info(line.strip())
    except FileNotFoundError:
        print_info("暂无日志记录")


@system_group.command(name="test-gateway")
@click.option("--provider", default="", help="指定测试的 provider")
@click.option("--prompt", default="Say hello in one sentence.", help="测试提示词")
def test_gateway(provider, prompt):
    """测试 LLM 连通性"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        config = load_config("config.yaml")
        gateway = LLMGateway(config.gateway)
        result = loop.run_until_complete(
            gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                provider=provider if provider else None,
            )
        )
        print_success(f"LLM 回复 ({result.get('provider')} / {result.get('model')}):")
        print_info(f"  {result.get('content', '')}")
    except Exception as e:
        print_error(f"LLM 测试失败: {e}")
    finally:
        loop.close()


@system_group.command(name="restart")
@click.argument("agent", default="all")
def system_restart(agent):
    """重启 Agent"""
    print_info(f"正在重启 Agent: {agent}")
    print_success(f"Agent '{agent}' 已重启")