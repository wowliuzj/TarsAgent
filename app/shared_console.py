from rich.console import Console

# 共享的 Rich Console 实例，避免多实例冲突导致终端刷新问题
console = Console()

# 全局活跃的 status (spinner) 引用，便于在人机协同交互时暂停/恢复
active_status = None
